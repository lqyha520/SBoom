"""Full-order refunds require review; only signed provider success revokes a grant."""

import re
import time
import uuid
from datetime import datetime

from app.db import db
from app.security import decrypt_secret
from app.services import membership_ledger, mini_auth, mini_orders
from app.services.mini_errors import fail
from app.services.mini_messages import notify
from app.services.wechat_pay import PaymentError, WeChatPay
from app.services.wechat_virtual_pay import VirtualPay


def request(order_id, user_id, body):
    with db(serialized="accounts") as conn:
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
    with db(serialized="accounts") as conn:
        refund = conn.execute("SELECT * FROM mini_refunds WHERE id = ?", (identifier,)).fetchone()
        if not refund:
            fail("退款申请不存在", 404)
        if refund["revision"] != body.revision or refund["status"] != "requested":
            fail("退款申请已处理，请刷新后重试", 409)
        order = mini_orders.owned(conn, refund["order_id"])
        if order["status"] != "paid":
            fail("订单状态不支持退款", 409)
        if body.action == "approve" and order["payment_channel"] == "virtual" and order["virtual_order_type"] in (7, 8):
            fail("iOS 虚拟支付订单需由用户在系统内申请退款，管理员不能发起", 422)
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
    with db(serialized="accounts") as conn:
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
        if order["payment_channel"] == "virtual":
            openid = decrypt_secret(order["payer_enc"])
            if not openid:
                fail("订单付款人信息不可用，请联系客服", 422)
            try:
                value = VirtualPay().refund_order(order, snapshot, openid)
            except PaymentError as error:
                # 重复发起或退款处理中都不是失败；保持 processing 由查单收敛。
                if error.code in ("XPAY_PENDING", "XPAY_268490004"):
                    return
                raise
            provider_id = value.get("refund_wx_order_id") or value.get("refund_order_id") or ""
            if isinstance(provider_id, str) and 8 <= len(provider_id) <= 64:
                with db(serialized="accounts") as conn:
                    conn.execute("UPDATE mini_refunds SET provider_id = ? WHERE id = ? AND provider_id = ''", (provider_id, identifier))
            return
        value = WeChatPay().refund(order, snapshot)
        apply(value, expected=identifier)
    finally:
        with db(serialized="accounts") as conn:
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
    with db(serialized="accounts") as conn:
        refund = conn.execute("SELECT * FROM mini_refunds WHERE id = ?", (identifier,)).fetchone()
        if not refund:
            fail("退款申请不存在", 404)
        order = mini_orders.owned(conn, refund["order_id"])
        if order["payment_channel"] != "wechat":
            fail("退款通知与订单支付渠道不一致", 400)
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


def settle_virtual(order_id, value):
    """按虚拟支付查单结果收敛退款：5/8 成功，7 异常；推送只作触发，不直接采信。"""
    if not isinstance(value, dict) or value.get("order_id") != order_id:
        fail("退款查询结果与订单不一致", 400)
    status = value.get("status")
    if type(status) is not int:
        fail("退款查询结果状态无效", 400)
    now = int(time.time())
    with db(serialized="accounts") as conn:
        order = mini_orders.owned(conn, order_id)
        if order["payment_channel"] != "virtual":
            fail("退款查询结果与订单支付渠道不一致", 400)
        order_fee = value.get("order_fee")
        if type(order_fee) is int and order_fee != order["amount_fen"]:
            fail("退款金额与订单不一致", 400)
        refund_fee = value.get("refund_fee")
        if type(refund_fee) is int and not 0 <= refund_fee <= order["amount_fen"]:
            fail("退款金额异常", 400)
        refund = conn.execute("SELECT * FROM mini_refunds WHERE order_id = ?", (order_id,)).fetchone()
        if status == 7:
            if not refund or refund["status"] == "success":
                return mini_orders.public_order(conn, order)
            conn.execute("UPDATE mini_refunds SET status = 'abnormal', revision = revision + 1, updated_at = ? WHERE id = ? AND status IN ('processing', 'abnormal')", (now, refund["id"]))
            if order["user_id"]:
                notify(conn, order["user_id"], "refund-result:" + refund["id"] + ":abnormal", "order", "退款需要进一步处理", "退款暂未完成，请在订单中查看状态或联系客服。", "order", order["id"])
            conn.execute("INSERT INTO mini_payment_events(id, order_id, kind, created_at) VALUES (?, ?, 'refund_abnormal', ?) ON CONFLICT(id) DO NOTHING", ("virtual-refund:" + order_id + ":7", order_id, now))
            return mini_orders.public_order(conn, order)
        if status not in (5, 8):
            return mini_orders.public_order(conn, order)
        if refund and refund["status"] == "success":
            return mini_orders.public_order(conn, order)
        provider_id = value.get("wx_order_id") or value.get("wxpay_order_id") or ""
        provider_id = provider_id if isinstance(provider_id, str) and 8 <= len(provider_id) <= 64 else ""
        paid_time = value.get("paid_time")
        paid_at = paid_time if type(paid_time) is int and 0 < paid_time <= now + 300 else now
        transaction = provider_id or (value.get("channel_order_id") if isinstance(value.get("channel_order_id"), str) else "")
        if order["paid_at"] is None and transaction:
            duplicate = conn.execute("SELECT id FROM mini_orders WHERE (transaction_id = ? OR virtual_order_id = ?) AND id <> ?", (transaction, transaction, order_id)).fetchone()
            if duplicate:
                fail("此支付交易已用于其他订单", 400)
            order_type = value.get("order_type") if type(value.get("order_type")) is int else 0
            conn.execute("UPDATE mini_orders SET paid_at = ?, transaction_id = ?, virtual_order_id = ?, virtual_order_type = ?, updated_at = ? WHERE id = ?",
                         (paid_at, transaction, transaction, order_type, now, order_id))
        if refund is None:
            # 虚拟支付查单结果只有 paid_time（支付时间），没有退款完成时间，只能记录确认成功的时刻。
            refund_identifier = uuid.uuid4().hex
            conn.execute("INSERT INTO mini_refunds(id, order_id, reason, reply, status, provider_id, created_at, updated_at, completed_at) VALUES (?, ?, ?, '', 'success', ?, ?, ?, ?)",
                         (refund_identifier, order_id, "用户通过微信支付申请退款", provider_id, now, now, now))
        else:
            refund_identifier = refund["id"]
            conn.execute("UPDATE mini_refunds SET status = 'success', provider_id = ?, revision = revision + 1, updated_at = ?, completed_at = ? WHERE id = ?",
                         (provider_id or refund["provider_id"], now, now, refund_identifier))
        user = conn.execute("SELECT * FROM mini_users WHERE id = ?", (order["user_id"],)).fetchone()
        before = mini_auth._admin_item(user) if user else None
        seconds = membership_ledger.revoke(conn, order_id)
        conn.execute("UPDATE mini_orders SET status = 'refunded', revision = revision + 1, updated_at = ? WHERE id = ?", (now, order_id))
        if user:
            after = mini_auth._admin_item(conn.execute("SELECT * FROM mini_users WHERE id = ?", (user["id"],)).fetchone())
            mini_auth._record_event(conn, None, user["id"], before, {**after, "refund_order": order_id, "revoked_seconds": seconds})
            notify(conn, user["id"], "refunded:" + refund_identifier, "order", "退款已成功", "款项已原路退回，相应未使用会员时长已处理，到账时间以支付账户为准。", "order", order_id)
        conn.execute("INSERT INTO mini_payment_events(id, order_id, kind, created_at) VALUES (?, ?, 'refund_success', ?) ON CONFLICT(id) DO NOTHING",
                     ("virtual-refund:" + order_id + ":" + str(status), order_id, now))
        return mini_orders.public_order(conn, mini_orders.owned(conn, order_id))


def sync_order(order_id):
    """退款推送只带订单号：找到对应退款申请后按退款查单收敛。"""
    with db() as conn:
        refund = conn.execute("SELECT id FROM mini_refunds WHERE order_id = ?", (order_id,)).fetchone()
    if not refund:
        return None
    return sync(refund["id"])


def sync(identifier, user_id=None):
    with db() as conn:
        refund = conn.execute("SELECT * FROM mini_refunds WHERE id = ?", (identifier,)).fetchone()
        if not refund:
            fail("退款申请不存在", 404)
        order = mini_orders.owned(conn, refund["order_id"], user_id)
        mini_orders.ensure_tenant(order)
        if order["payment_channel"] == "virtual":
            if refund["status"] not in ("processing", "abnormal"):
                return mini_orders.public_order(conn, order, user_id is None)
            openid = decrypt_secret(order["payer_enc"])
            if not openid:
                fail("订单付款人信息不可用，请联系客服", 422)
            order_id, status = order["id"], refund["status"]
        else:
            if refund["status"] not in ("processing", "abnormal"):
                return mini_orders.public_order(conn, order, user_id is None)
            order_id, status = order["id"], refund["status"]
    if order["payment_channel"] == "virtual":
        value = VirtualPay().query_order(openid, order_id)
        settle_virtual(order_id, value)
        return mini_orders.detail(order_id, user_id)
    try:
        value = WeChatPay().query_refund(identifier)
        apply(value, expected=identifier)
    except PaymentError as error:
        if error.code in ("RESOURCE_NOT_EXISTS", "REFUND_NOT_EXIST", "NOT_FOUND") and status == "processing":
            dispatch(identifier)
        else:
            raise
    return mini_orders.detail(order_id, user_id)
