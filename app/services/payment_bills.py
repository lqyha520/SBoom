"""Read-only reconciliation against an authenticated WeChat daily trade bill."""

import csv
import io
import json
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from app.db import db
from app.services.mini_errors import fail
from app.services.wechat_pay import PaymentError, WeChatPay

ZONE = timezone(timedelta(hours=8))


def money(value):
    try:
        number = Decimal(value.lstrip("`")) * 100
        if not number.is_finite() or number < 0 or number != number.to_integral_value():
            raise ValueError("Invalid bill amount")
        return int(number)
    except (ValueError, InvalidOperation):
        raise PaymentError("INVALID_BILL_AMOUNT")


def parse_bill(content, record_kind=None):
    rows = csv.reader(io.StringIO(content), strict=True)
    header = None
    result: list[dict] = []
    footer = False
    for values in rows:
        if not values:
            continue
        if header is None:
            if "商户订单号" in values:
                header = [value.strip().lstrip("\ufeff") for value in values]
                if not {"微信订单号", "商户订单号", "交易状态", "订单金额"}.issubset(header):
                    raise PaymentError("UNSUPPORTED_BILL_FORMAT")
            continue
        if values[0].startswith("总交易单数"):
            footer = True
            totals = next(rows, None)
            if not totals or not totals[0].lstrip("`").isdigit() or int(totals[0].lstrip("`")) != len(result):
                raise PaymentError("INVALID_BILL_TOTAL")
            break
        if len(values) != len(header):
            raise PaymentError("INVALID_BILL_ROW")
        row = {key: value.lstrip("`").strip() for key, value in zip(header, values)}
        if row["交易状态"] not in ("SUCCESS", "REFUND") or not row["商户订单号"] or not row["微信订单号"]:
            raise PaymentError("INVALID_BILL_ROW")
        result.append({"order_id": row["商户订单号"], "transaction_id": row["微信订单号"], "status": record_kind or row["交易状态"],
                       "amount_fen": money(row["订单金额"]), "refund_id": row.get("商户退款单号", ""),
                       "refund_fen": money(row.get("申请退款金额") or "0"), "refund_status": row.get("退款状态", "")})
        if len(result) > 100000:
            raise PaymentError("OVERSIZED_BILL")
    if header is None or not footer:
        raise PaymentError("INVALID_BILL_HEADER")
    return result


def compare(conn, rows, bill_date):
    start = int(datetime.combine(date.fromisoformat(bill_date), datetime.min.time(), ZONE).timestamp())
    end = start + 86400
    differences, seen_payments, seen_refunds = [], set(), set()
    paid_fen, refunded_fen = 0, 0
    for row in rows:
        order = conn.execute("SELECT * FROM mini_orders WHERE id = ?", (row["order_id"],)).fetchone()
        reason = ""
        if row["status"] == "SUCCESS":
            if row["order_id"] in seen_payments:
                raise PaymentError("DUPLICATE_BILL_ORDER")
            seen_payments.add(row["order_id"])
            paid_fen += row["amount_fen"]
            if not order:
                reason = "微信已收款，本地未找到订单"
            elif order["amount_fen"] != row["amount_fen"]:
                reason = "订单金额不一致"
            elif order["paid_at"] is None:
                reason = "微信已付款，本地待同步"
            elif order["transaction_id"] != row["transaction_id"]:
                reason = "微信交易号不一致"
        elif row["refund_status"] == "SUCCESS":
            if not row["refund_id"] or row["refund_id"] in seen_refunds:
                raise PaymentError("DUPLICATE_BILL_REFUND")
            seen_refunds.add(row["refund_id"])
            refunded_fen += row["refund_fen"]
            refund = conn.execute("SELECT * FROM mini_refunds WHERE id = ? AND order_id = ?", (row["refund_id"], row["order_id"])).fetchone()
            if not order or not refund:
                reason = "微信退款未在本系统登记，请核对商户平台操作"
            elif row["refund_fen"] != order["amount_fen"] or row["amount_fen"] != order["amount_fen"]:
                reason = "退款金额不一致"
            elif order["transaction_id"] != row["transaction_id"]:
                reason = "退款对应的微信交易号不一致"
            elif refund["status"] != "success":
                reason = "微信已退款，本地待同步"
        if reason:
            differences.append({"order_id": row["order_id"], "refund_id": row["refund_id"], "reason": reason,
                                "remote_fen": row["refund_fen"] if row["status"] == "REFUND" else row["amount_fen"], "local_fen": order["amount_fen"] if order else None})
    local_paid = conn.execute("SELECT id, amount_fen FROM mini_orders WHERE paid_at >= ? AND paid_at < ?", (start, end)).fetchall()
    local_refunds = conn.execute("SELECT f.id, f.order_id, o.amount_fen FROM mini_refunds f JOIN mini_orders o ON o.id = f.order_id WHERE f.status = 'success' AND f.completed_at >= ? AND f.completed_at < ?", (start, end)).fetchall()
    for row in local_paid:
        if row["id"] not in seen_payments:
            differences.append({"order_id": row["id"], "refund_id": "", "reason": "本地有收款记录，微信当日账单未找到", "local_fen": row["amount_fen"], "remote_fen": None})
    for row in local_refunds:
        if row["id"] not in seen_refunds:
            differences.append({"order_id": row["order_id"], "refund_id": row["id"], "reason": "本地有退款记录，微信当日账单未找到", "local_fen": row["amount_fen"], "remote_fen": None})
    summary = {"wechat_paid_fen": paid_fen, "wechat_refunded_fen": refunded_fen,
               "local_paid_fen": sum(row["amount_fen"] for row in local_paid), "local_refunded_fen": sum(row["amount_fen"] for row in local_refunds),
               "wechat_orders": len(seen_payments), "local_orders": len(local_paid), "differences": len(differences)}
    return summary, differences


def reconcile(admin_id, bill_date):
    day = date.fromisoformat(bill_date)
    today = datetime.now(ZONE).date()
    if day >= today or day < today - timedelta(days=90):
        fail("请选择最近 90 天内、昨天及以前的账单日期", 422)
    identifier, now = uuid.uuid4().hex, int(time.time())
    with db(serialized="accounts") as conn:
        if conn.execute("SELECT 1 FROM mini_reconciliations WHERE bill_date = ? AND status = 'running' AND updated_at > ?", (bill_date, now - 300)).fetchone():
            fail("该日账单正在核对，请稍后刷新", 409)
        conn.execute("UPDATE mini_reconciliations SET status = 'error', error = '上次核对中断，可重新核对' WHERE bill_date = ? AND status = 'running'", (bill_date,))
        conn.execute("INSERT INTO mini_reconciliations(id, bill_date, status, admin_id, created_at, updated_at) VALUES (?, ?, 'running', ?, ?, ?)", (identifier, bill_date, admin_id, now, now))
    try:
        # Separate provider bill scopes avoid counting a same-day refund as a missing
        # payment, or counting a refund of an older order as today's payment.
        provider, rows = WeChatPay(), []
        for kind in ("SUCCESS", "REFUND"):
            try:
                rows.extend(parse_bill(provider.bill(bill_date, kind), kind))
            except PaymentError as error:
                if error.code != "NO_STATEMENT_EXIST":
                    raise
        with db(serialized="accounts") as conn:
            summary, differences = compare(conn, rows, bill_date)
            conn.execute("UPDATE mini_reconciliations SET status = 'complete', summary_json = ?, differences_json = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(summary), json.dumps(differences[:5000], ensure_ascii=False), int(time.time()), identifier))
    except (PaymentError, ValueError, csv.Error) as error:
        message = "微信账单暂不可用，请检查配置或在账单生成后重试"
        with db(serialized="accounts") as conn:
            conn.execute("UPDATE mini_reconciliations SET status = 'error', error = ?, updated_at = ? WHERE id = ?", (message, int(time.time()), identifier))
        if isinstance(error, PaymentError):
            raise
        raise PaymentError("INVALID_BILL") from error
    return get(identifier)


def get(identifier):
    with db() as conn:
        row = conn.execute("SELECT * FROM mini_reconciliations WHERE id = ?", (identifier,)).fetchone()
    if not row:
        fail("核对记录不存在", 404)
    result = dict(row)
    result["summary"] = json.loads(result.pop("summary_json"))
    result["differences"] = json.loads(result.pop("differences_json"))
    return result


def listing(limit=20, offset=0):
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM mini_reconciliations").fetchone()[0]
        rows = conn.execute("SELECT id, bill_date, status, error, summary_json, created_at, updated_at FROM mini_reconciliations ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["summary"] = json.loads(item.pop("summary_json"))
        items.append(item)
    return {"items": items, "total": total, "has_more": offset + len(items) < total}


def export_orders(status="", q="", start_date="", end_date=""):
    from app.services.mini_orders import listing as orders
    page = orders(status=status, q=q, limit=5000, start_date=start_date, end_date=end_date)
    if page["total"] > 5000:
        fail("结果超过 5000 条，请缩小筛选范围再导出", 422)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["订单号", "账号", "套餐", "天数", "金额（元）", "状态", "微信交易号", "创建时间", "退款状态"])
    def safe(value):
        value = str(value or "")
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value
    for item in page["items"]:
        writer.writerow([safe(item["id"]), safe(item["username"]), safe(item["plan_name"]), item["plan_days"], f"{item['amount_fen'] / 100:.2f}",
                         item["status"], safe(item["transaction_id"]), datetime.fromtimestamp(item["created_at"], ZONE).isoformat(), item["refund"]["status"] if item["refund"] else ""])
    return "\ufeff" + output.getvalue()
