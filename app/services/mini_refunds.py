"""Full-order refunds require review; only signed provider success revokes a grant."""

import time
import re
import uuid
from datetime import datetime
from app.db import db
from app.services import mini_auth, mini_orders, membership_ledger
from app.services.mini_errors import fail
from app.services.mini_messages import notify
from app.services.wechat_pay import PaymentError, WeChatPay


def request(order_id, user_id, body):
    with db(serialized=True) as conn:
        order = mini_orders.owned(conn, order_id, user_id)
        if order["status"] != "paid":
            fail("仅已付款订单可以申请退款", 409)
        existing = conn.execute("SELECT * FROM mini_refunds WHERE order_id = ?", (order_id,)).fetchone()
        if existing:
            return mini_orders.public_order(conn, order)
        now = int(time.time())
        conn.execute("INSERT INTO mini_refunds(id, order_id, reason, created_at, updated_at) VALUES (?, ?, ?, ?, ?)", (uuid.uuid4().hex, order_id, body.reason, now, now))
        return mini_orders.public_order(conn, order)


def review(admin_id, identifier, body):
    with db(serialized=True) as conn:
        refund = conn.execute("SELECT * FROM mini_refunds WHERE id = ?", (identifier,)).fetchone()
        if not refund:
            fail("退款申请不存在", 404)
        if refund["revision"] != body.revision or refund["status"] != "requested":
            fail("退款申请已处理，请刷新后重试", 409)
        order = mini_orders.owned(conn, refund["order_id"])
        if order["status"] != "paid":
            fail("订单状态不支持退款", 409)
        if body.action == "approve" and not body.confirm_refund:
            fail("请确认向原支付账户退还整单金额", 422)
        status = "processing" if body.action == "approve" else "rejected"
        conn.execute("UPDATE mini_refunds SET status = ?, reply = ?, admin_id = ?, revision = revision + 1, updated_at = ? WHERE id = ?", (status, body.reply, admin_id, int(time.time()), identifier))
        if order["user_id"]:
            notify(conn, order["user_id"], "refund-review:" + identifier, "order", "退款申请审核通过" if body.action == "approve" else "退款申请处理结果",
                   body.reply, "order", order["id"])
    if body.action == "approve":
        dispatch(identifier)
    return mini_orders.detail(order["id"])


def dispatch(identifier):
    now, lease = int(time.time()), uuid.uuid4().hex
    with db(serialized=True) as conn:
        refund = conn.execute("SELECT * FROM mini_refunds WHERE id = ?", (identifier,)).fetchone()
        if not refund or refund["status"] != "processing":
            fail("退款不在处理中", 409)
        if refund["lease_until"] > now:
            fail("退款正在处理，请稍后刷新", 409)
        order = dict(mini_orders.owned(conn, refund["order_id"]))
        mini_orders.ensure_tenant(order)
        conn.execute("UPDATE mini_refunds SET lease_key = ?, lease_until = ? WHERE id = ?", (lease, now + 45, identifier))
        snapshot = dict(refund)
    try:
        value = WeChatPay().refund(order, snapshot)
        apply(value, expected=identifier)
    finally:
        with db(serialized=True) as conn:
            conn.execute("UPDATE mini_refunds SET lease_key = '', lease_until = 0 WHERE id = ? AND lease_key = ?", (identifier, lease))


def apply(value, event_id=None, expected=None):
    if not isinstance(value, dict):
        fail("退款通知格式无效", 400)
    identifier = value.get("out_refund_no", "")
    if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        fail("退款申请标识无效", 400)
    if expected is not None and identifier != expected:
        fail("退款查询结果不一致", 400)
    state = value.get("refund_status") or value.get("status")
    states = {"SUCCESS": "success", "PROCESSING": "processing", "CLOSED": "closed", "ABNORMAL": "abnormal"}
    if not isinstance(state, str) or state not in states:
        fail("未知退款状态", 400)
    now = int(time.time())
    completed_at = None
    if state == "SUCCESS":
        try:
            stamp = datetime.fromisoformat(value["success_time"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("Refund time needs a timezone")
            completed_at = int(stamp.timestamp())
            if completed_at > now + 300:
                raise ValueError("Future refund")
        except (KeyError, ValueError, TypeError, OverflowError, AttributeError):
            fail("退款完成时间无效", 400)
    with db(serialized=True) as conn:
        refund = conn.execute("SELECT * FROM mini_refunds WHERE id = ?", (identifier,)).fetchone()
        if not refund:
            fail("退款申请不存在", 404)
        order = mini_orders.owned(conn, refund["order_id"])
        amount = value.get("amount", {})
        if completed_at is not None and completed_at < max(refund["created_at"], order["paid_at"] or 0) - 300:
            fail("退款完成时间早于申请时间", 400)
        if (not isinstance(amount, dict) or value.get("out_trade_no") != order["id"] or value.get("transaction_id") != order["transaction_id"] or
                value.get("mchid", order["mchid"]) != order["mchid"] or amount.get("currency", "CNY") != "CNY" or
                type(amount.get("total")) is not int or type(amount.get("refund")) is not int or
                amount["total"] != order["amount_fen"] or amount["refund"] != order["amount_fen"]):
            fail("退款金额、商户或订单不一致", 400)
        provider_id = value.get("refund_id", "")
        if not isinstance(provider_id, str) or not 8 <= len(provider_id) <= 64 or refund["provider_id"] and refund["provider_id"] != provider_id:
            fail("退款交易标识不一致", 400)
        if refund["status"] == "success":
            return mini_orders.public_order(conn, order)
        if refund["status"] in ("requested", "rejected"):
            fail("退款尚未批准", 409)
        if refund["status"] == "closed" and state != "CLOSED":
            fail("已关闭退款收到冲突状态，请核对微信账单", 409)
        conn.execute("UPDATE mini_refunds SET status = ?, provider_id = ?, revision = revision + 1, updated_at = ?, completed_at = ? WHERE id = ?",
                     (states[state], provider_id, now, completed_at, identifier))
        if state == "SUCCESS":
            user = conn.execute("SELECT * FROM mini_users WHERE id = ?", (order["user_id"],)).fetchone()
            before = mini_auth._admin_item(user) if user else None
            seconds = membership_ledger.revoke(conn, order["id"])
            conn.execute("UPDATE mini_orders SET status = 'refunded', revision = revision + 1, updated_at = ? WHERE id = ?", (now, order["id"]))
            if user:
                after = mini_auth._admin_item(conn.execute("SELECT * FROM mini_users WHERE id = ?", (user["id"],)).fetchone())
                mini_auth._record_event(conn, refund["admin_id"], user["id"], before, {**after, "refund_order": order["id"], "revoked_seconds": seconds})
                notify(conn, user["id"], "refunded:" + identifier, "order", "退款已成功", "款项已原路退回，相应未使用会员时长已处理，到账时间以支付账户为准。", "order", order["id"])
        elif state in ("ABNORMAL", "CLOSED") and order["user_id"]:
            notify(conn, order["user_id"], "refund-result:" + identifier + ":" + state, "order", "退款需要进一步处理", "退款暂未完成，请在订单中查看状态或联系客服。", "order", order["id"])
        conn.execute("INSERT INTO mini_payment_events(id, order_id, kind, created_at) VALUES (?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
                     ("refund:" + (event_id or identifier + ":" + state), order["id"], "refund_" + states[state], now))
        return mini_orders.public_order(conn, mini_orders.owned(conn, order["id"]))


def sync(identifier, user_id=None):
    with db() as conn:
        refund = conn.execute("SELECT * FROM mini_refunds WHERE id = ?", (identifier,)).fetchone()
        if not refund:
            fail("退款申请不存在", 404)
        order = mini_orders.owned(conn, refund["order_id"], user_id)
        mini_orders.ensure_tenant(order)
        if refund["status"] not in ("processing", "abnormal"):
            return mini_orders.public_order(conn, order, user_id is None)
        status = refund["status"]
    try:
        value = WeChatPay().query_refund(identifier)
        apply(value, expected=identifier)
    except PaymentError as error:
        if error.code in ("RESOURCE_NOT_EXISTS", "REFUND_NOT_EXIST", "NOT_FOUND") and status == "processing":
            dispatch(identifier)
        else:
            raise
    return mini_orders.detail(order["id"], user_id)
