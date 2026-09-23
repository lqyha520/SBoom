"""Server-priced orders, idempotent payment confirmation and membership fulfillment."""

import hashlib
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from app.config import get_settings
from app.db import db
from app.security import decrypt_secret
from app.services import membership_ledger, mini_auth
from app.services.mini_errors import fail
from app.services.mini_messages import notify
from app.services.wechat_pay import PaymentError, WeChatPay, configuration

PUBLIC_FIELDS = ("id", "plan_id", "plan_name", "plan_days", "amount_fen", "currency", "status", "revision", "created_at", "expires_at", "paid_at", "closed_at", "updated_at")
REFUND_FIELDS = ("id", "reason", "reply", "status", "revision", "created_at", "updated_at", "completed_at")
#: 列表查询把退款与下单人一次 LEFT JOIN 带出来（列名加前缀避免和订单列撞名），public_order(joined=True) 直接消费
JOINED_COLUMNS = ", ".join(f"f.{key} AS refund_{key}" for key in REFUND_FIELDS) + ", u.username AS owner_username, u.nickname AS owner_nickname"
JOINED_TABLES = "mini_orders o LEFT JOIN mini_users u ON u.id = o.user_id LEFT JOIN mini_refunds f ON f.order_id = o.id"


def public_order(conn, row, admin=False, *, joined=False):
    """订单对外视图。

    单条查询（detail/create/pay 等）保持原样按需补查退款与下单人；
    列表查询传 joined=True，退款/下单人已随 JOINED_COLUMNS 一并取回，不再逐行补查（原来 50 行要打 100 次库）。
    mini_refunds.order_id 是 UNIQUE，LEFT JOIN 不会让订单行翻倍。
    """
    result = {key: row[key] for key in PUBLIC_FIELDS}
    if joined:
        result["refund"] = {key: row["refund_" + key] for key in REFUND_FIELDS} if row["refund_id"] else None
        if admin:
            result.update(user_id=row["user_id"], username=row["owner_username"] if row["owner_username"] is not None else "已注销用户",
                          nickname=row["owner_nickname"] if row["owner_username"] is not None else "", transaction_id=row["transaction_id"])
        return result
    refund = conn.execute("SELECT * FROM mini_refunds WHERE order_id = ?", (row["id"],)).fetchone()
    result["refund"] = {key: refund[key] for key in REFUND_FIELDS} if refund else None
    if admin:
        owner = conn.execute("SELECT username, nickname FROM mini_users WHERE id = ?", (row["user_id"],)).fetchone()
        result.update(user_id=row["user_id"], username=owner["username"] if owner else "已注销用户", nickname=owner["nickname"] if owner else "", transaction_id=row["transaction_id"])
    return result


def owned(conn, identifier, user_id=None):
    row = conn.execute("SELECT * FROM mini_orders WHERE id = ?" + (" AND user_id = ?" if user_id is not None else ""), (identifier, user_id) if user_id is not None else (identifier,)).fetchone()
    if not row:
        fail("订单不存在", 404)
    return row


def detail(identifier, user_id=None):
    with db() as conn:
        return public_order(conn, owned(conn, identifier, user_id), user_id is None)


def plans(admin=False):
    with db() as conn:
        items = [dict(row) for row in conn.execute("SELECT * FROM mini_membership_plans " + ("" if admin else "WHERE is_active = 1 ") + "ORDER BY sort_order, created_at, id")]
    status = configuration()
    return {"items": items, "checkout_enabled": status["ready"], "ios_enabled": status["ios_enabled"], **({"configuration": status} if admin else {})}


def save_plan(body, identifier=None):
    now = int(time.time())
    # 套餐维护是单行 revision 乐观锁写入：FOR UPDATE 行锁即可。下单侧读到的永远是已提交快照，
    # 并按 plan_revision 校验，所以不需要 accounts 全局锁把它和下单串起来。
    with db() as conn:
        if identifier:
            row = conn.execute("SELECT revision FROM mini_membership_plans WHERE id = ? FOR UPDATE", (identifier,)).fetchone()
            if not row:
                fail("会员套餐不存在", 404)
            if row[0] != body.revision:
                fail("套餐已更新，请刷新后重试")
            conn.execute("UPDATE mini_membership_plans SET name = ?, description = ?, days = ?, price_fen = ?, is_active = ?, sort_order = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
                         (body.name, body.description, body.days, body.price_fen, int(body.is_active), body.sort_order, now, identifier))
        else:
            if conn.execute("SELECT COUNT(*) FROM mini_membership_plans").fetchone()[0] >= 100:
                fail("套餐数量已达上限，请编辑已有套餐", 422)
            identifier = uuid.uuid4().hex
            conn.execute("INSERT INTO mini_membership_plans(id, name, description, days, price_fen, is_active, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (identifier, body.name, body.description, body.days, body.price_fen, int(body.is_active), body.sort_order, now, now))
        return dict(conn.execute("SELECT * FROM mini_membership_plans WHERE id = ?", (identifier,)).fetchone())


def create(user_id, body):
    now = int(time.time())
    request_key = hashlib.sha256((user_id + ":" + body.request_id).encode()).hexdigest()
    with db(serialized="accounts") as conn:
        previous = conn.execute("SELECT * FROM mini_orders WHERE request_key = ?", (request_key,)).fetchone()
        if previous:
            if previous["plan_id"] != body.plan_id:
                fail("请求标识已用于另一套餐，请重新下单")
            return public_order(conn, previous)
        if not configuration()["ready"]:
            fail("在线开通暂未开放，请联系客服", 503)
        user = conn.execute("SELECT * FROM mini_users WHERE id = ? AND is_active = 1", (user_id,)).fetchone()
        if not user:
            fail("账号不可用，请重新登录", 403)
        openid = decrypt_secret(user["wechat_openid_enc"])
        if not openid or mini_auth.digest(get_settings().wechat_app_id + ":" + openid) != user["wechat_identity"]:
            fail("请在微信小程序重新登录后开通会员", 422)
        if user["membership"] == "vip" and user["vip_expires_at"] is None:
            fail("你已是长期会员，无需重复购买", 422)
        plan = conn.execute("SELECT * FROM mini_membership_plans WHERE id = ? AND is_active = 1", (body.plan_id,)).fetchone()
        if not plan:
            fail("套餐已下架，请重新选择", 404)
        if plan["revision"] != body.plan_revision:
            fail("套餐价格或权益已更新，请重新确认后下单")
        if max(now, user["vip_expires_at"] or 0) + plan["days"] * 86400 > 253402300799:
            fail("会员到期日期超出支持范围", 422)
        if conn.execute("SELECT COUNT(*) FROM mini_orders WHERE user_id = ? AND status IN ('created', 'pending')", (user_id,)).fetchone()[0] >= 3:
            fail("请先支付或取消已有的未付款订单", 429)
        if conn.execute("SELECT COUNT(*) FROM mini_orders WHERE user_id = ? AND created_at >= ?", (user_id, now - 86400)).fetchone()[0] >= 20:
            fail("下单较频繁，请稍后重试", 429)
        identifier = uuid.uuid4().hex
        settings = get_settings()
        conn.execute("INSERT INTO mini_orders(id, user_id, request_key, plan_id, plan_name, plan_days, amount_fen, appid, mchid, payer_enc, created_at, expires_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (identifier, user_id, request_key, plan["id"], plan["name"], plan["days"], plan["price_fen"], settings.wechat_app_id, settings.wechat_pay_mchid, user["wechat_openid_enc"], now, now + 900, now))
        return public_order(conn, owned(conn, identifier))


def ensure_tenant(order):
    settings = get_settings()
    if order["appid"] != settings.wechat_app_id or order["mchid"] != settings.wechat_pay_mchid:
        fail("订单所属支付配置已变化，请联系管理员处理", 409)


def pay(identifier, user_id):
    now, lease = int(time.time()), uuid.uuid4().hex
    provider = WeChatPay()
    with db(serialized="accounts") as conn:
        order = owned(conn, identifier, user_id)
        ensure_tenant(order)
        if order["status"] not in ("created", "pending") or order["expires_at"] <= now:
            fail("订单已付款、关闭或超时，请刷新订单", 409)
        user = conn.execute("SELECT * FROM mini_users WHERE id = ? AND is_active = 1", (user_id,)).fetchone()
        if not user or user["membership"] == "vip" and user["vip_expires_at"] is None:
            fail("当前账号无需重复购买，请取消此订单", 422)
        if order["lease_until"] > now:
            fail("订单正在处理，请稍后刷新", 409)
        if order["prepay_id"]:
            return {"order": public_order(conn, order), "payment": provider.payment_parameters(order["prepay_id"])}
        conn.execute("UPDATE mini_orders SET lease_key = ?, lease_until = ?, status = 'pending', updated_at = ? WHERE id = ?", (lease, now + 45, now, identifier))
        snapshot = dict(order)
    try:
        result = provider.prepay(snapshot, decrypt_secret(snapshot["payer_enc"]))
        parameters = provider.payment_parameters(result.get("prepay_id"))
    except PaymentError:
        with db(serialized="accounts") as conn:
            conn.execute("UPDATE mini_orders SET lease_key = '', lease_until = 0 WHERE id = ? AND lease_key = ?", (identifier, lease))
        raise
    with db(serialized="accounts") as conn:
        current = owned(conn, identifier, user_id)
        if current["lease_key"] != lease:
            fail("订单状态已变化，请刷新订单", 409)
        conn.execute("UPDATE mini_orders SET prepay_id = ?, lease_key = '', lease_until = 0 WHERE id = ?", (result["prepay_id"], identifier))
        return {"order": public_order(conn, owned(conn, identifier, user_id)), "payment": parameters if current["status"] in ("created", "pending") else None}


def validate_payment(order, value):
    amount, payer = value.get("amount", {}), value.get("payer", {})
    if (not isinstance(amount, dict) or not isinstance(payer, dict) or
            value.get("appid") != order["appid"] or value.get("mchid") != order["mchid"] or
            not isinstance(amount.get("total"), int) or isinstance(amount.get("total"), bool) or
            amount["total"] != order["amount_fen"] or amount.get("currency") != "CNY"):
        fail("支付通知与订单金额或商户不一致", 400)
    if order["payer_enc"] and payer.get("openid") != decrypt_secret(order["payer_enc"]):
        fail("支付用户与订单不一致", 400)
    transaction = value.get("transaction_id")
    if not isinstance(transaction, str) or not 8 <= len(transaction) <= 64:
        fail("支付交易标识无效", 400)
    return transaction


def confirm_payment(value, event_id=None):
    if not isinstance(value, dict):
        fail("支付通知格式无效", 400)
    if not isinstance(value.get("out_trade_no"), str) or not re.fullmatch(r"[0-9a-f]{32}", value["out_trade_no"]):
        fail("支付订单标识无效", 400)
    if value.get("trade_state") != "SUCCESS":
        fail("支付尚未完成", 409)
    now = int(time.time())
    with db(serialized="accounts") as conn:
        order = owned(conn, value.get("out_trade_no", ""))
        transaction = validate_payment(order, value)
        if order["paid_at"] is not None:
            if order["transaction_id"] != transaction:
                fail("订单交易标识不一致", 400)
            return public_order(conn, order)
        duplicate = conn.execute("SELECT id FROM mini_orders WHERE transaction_id = ?", (transaction,)).fetchone()
        if duplicate and duplicate[0] != order["id"]:
            fail("此支付交易已用于其他订单", 400)
        try:
            stamp = datetime.fromisoformat(value["success_time"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("Payment time needs a timezone")
            paid_at = int(stamp.timestamp())
            if paid_at < order["created_at"] - 300 or paid_at > now + 300:
                raise ValueError("Invalid payment time")
        except (KeyError, ValueError, TypeError, OverflowError, AttributeError):
            fail("支付完成时间无效", 400)
        conn.execute("UPDATE mini_orders SET status = 'paid', transaction_id = ?, paid_at = ?, revision = revision + 1, updated_at = ? WHERE id = ?", (transaction, paid_at, now, order["id"]))
        user = conn.execute("SELECT * FROM mini_users WHERE id = ?", (order["user_id"],)).fetchone()
        if user:
            before = mini_auth._admin_item(user)
            membership_ledger.append(conn, user, order["plan_days"], order["id"])
            after = mini_auth._admin_item(conn.execute("SELECT * FROM mini_users WHERE id = ?", (user["id"],)).fetchone())
            mini_auth._record_event(conn, None, user["id"], before, {**after, "order_id": order["id"], "paid_fen": order["amount_fen"]})
            notify(conn, user["id"], "paid:" + order["id"], "order", "会员订单已付款", f"{order['plan_name']}付款成功，请查看会员权益与到期时间。", "order", order["id"])
        conn.execute("INSERT INTO mini_payment_events(id, order_id, kind, created_at) VALUES (?, ?, 'paid', ?) ON CONFLICT(id) DO NOTHING", ("paid:" + (event_id or transaction), order["id"], now))
        return public_order(conn, owned(conn, order["id"]))


def sync(identifier, user_id=None):
    with db() as conn:
        order = dict(owned(conn, identifier, user_id))
    ensure_tenant(order)
    value = WeChatPay().query(identifier)
    if value.get("out_trade_no") != identifier or value.get("mchid") != order["mchid"] or value.get("appid") != order["appid"]:
        fail("查询结果与订单不一致", 400)
    if value.get("trade_state") == "SUCCESS":
        confirm_payment(value)
    elif value.get("trade_state") in ("CLOSED", "REVOKED", "PAYERROR"):
        with db(serialized="accounts") as conn:
            conn.execute("UPDATE mini_orders SET status = 'closed', closed_at = ?, updated_at = ?, revision = revision + 1 WHERE id = ? AND paid_at IS NULL AND status IN ('created', 'pending')", (int(time.time()), int(time.time()), identifier))
    return detail(identifier, user_id)


def cancel(identifier, user_id=None):
    now, lease = int(time.time()), uuid.uuid4().hex
    with db(serialized="accounts") as conn:
        order = dict(owned(conn, identifier, user_id))
        if order["status"] == "closed":
            return public_order(conn, order, user_id is None)
        if order["paid_at"] is not None:
            fail("已付款订单请申请退款", 409)
        if order["lease_until"] > time.time():
            fail("订单正在处理，请稍后再取消", 409)
        ensure_tenant(order)
        if order["status"] == "created" and not order["prepay_id"]:
            conn.execute("UPDATE mini_orders SET status = 'closed', closed_at = ?, updated_at = ?, revision = revision + 1 WHERE id = ?", (int(time.time()), int(time.time()), identifier))
            return public_order(conn, owned(conn, identifier), user_id is None)
        conn.execute("UPDATE mini_orders SET lease_key = ?, lease_until = ? WHERE id = ?", (lease, now + 45, identifier))
    try:
        try:
            WeChatPay().close(identifier)
        except PaymentError as error:
            if error.code == "ORDERPAID":
                return sync(identifier, user_id)
            if error.code not in ("ORDER_NOT_EXIST", "ORDERNOTEXIST", "ORDERCLOSED"):
                raise
        with db(serialized="accounts") as conn:
            conn.execute("UPDATE mini_orders SET status = 'closed', closed_at = ?, updated_at = ?, revision = revision + 1 WHERE id = ? AND lease_key = ? AND paid_at IS NULL AND status IN ('created', 'pending')", (int(time.time()), int(time.time()), identifier, lease))
    finally:
        with db(serialized="accounts") as conn:
            conn.execute("UPDATE mini_orders SET lease_key = '', lease_until = 0 WHERE id = ? AND lease_key = ?", (identifier, lease))
    return detail(identifier, user_id)


def listing(user_id=None, status="", q="", limit=20, offset=0, start_date="", end_date=""):
    clauses, args = [], []
    if user_id is not None:
        clauses.append("o.user_id = ?")
        args.append(user_id)
    if status.startswith("refund_"):
        clauses.append("EXISTS (SELECT 1 FROM mini_refunds f WHERE f.order_id = o.id AND f.status = ?)")
        args.append(status.removeprefix("refund_"))
    elif status:
        clauses.append("o.status = ?")
        args.append(status)
    try:
        zone = timezone(timedelta(hours=8))
        if start_date and end_date and date.fromisoformat(start_date) > date.fromisoformat(end_date):
            raise ValueError("Reversed range")
        if start_date:
            clauses.append("o.created_at >= ?")
            args.append(int(datetime.combine(date.fromisoformat(start_date), datetime.min.time(), zone).timestamp()))
        if end_date:
            clauses.append("o.created_at < ?")
            args.append(int(datetime.combine(date.fromisoformat(end_date) + timedelta(days=1), datetime.min.time(), zone).timestamp()))
    except (ValueError, OverflowError):
        fail("订单日期范围无效", 422)
    if q:
        clauses.append("(o.id LIKE ? ESCAPE '\\' OR LOWER(u.username) LIKE ? ESCAPE '\\' OR LOWER(u.nickname) LIKE ? ESCAPE '\\')")
        escaped = "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        args.extend([escaped] * 3)
    where = " AND ".join(clauses) or "1=1"
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM mini_orders o LEFT JOIN mini_users u ON u.id = o.user_id WHERE {where}", args).fetchone()[0]
        rows = conn.execute(f"SELECT o.*, {JOINED_COLUMNS} FROM {JOINED_TABLES} WHERE {where} ORDER BY o.created_at DESC, o.id DESC LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
        items = [public_order(conn, row, user_id is None, joined=True) for row in rows]
        summary = dict(conn.execute("SELECT COUNT(*) AS orders, COALESCE(SUM(CASE WHEN o.paid_at IS NOT NULL THEN o.amount_fen ELSE 0 END),0) AS paid_fen, "
                                   "COALESCE(SUM(CASE WHEN o.status = 'refunded' THEN o.amount_fen ELSE 0 END),0) AS refunded_fen "
                                   f"FROM mini_orders o LEFT JOIN mini_users u ON u.id = o.user_id WHERE {where}", args).fetchone())
    return {"items": items, "total": total, "has_more": offset + len(items) < total, "summary": summary}


def ensure_deletable(conn, user_id):
    if conn.execute("SELECT 1 FROM mini_orders WHERE user_id = ? AND status IN ('created', 'pending')", (user_id,)).fetchone():
        fail("此账号仍有未结订单，请先支付、取消或核对订单", 409)
    if conn.execute("SELECT 1 FROM mini_refunds f JOIN mini_orders o ON o.id = f.order_id WHERE o.user_id = ? AND f.status IN ('requested', 'processing', 'abnormal')", (user_id,)).fetchone():
        fail("此账号的退款尚未处理完成，请先处理退款", 409)
