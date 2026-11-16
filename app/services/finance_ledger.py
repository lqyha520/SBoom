"""经营收支账本：幂等写入、版本校验、作废与修改审计。"""

import csv
import io
import json
import time
import uuid
from datetime import date

from fastapi import HTTPException

from app.db import db
from app.models.finance_ledger import FinanceLedgerInput
from app.sql_utils import escape_like

FIELDS = ('entry_date', 'direction', 'category', 'amount_fen', 'tax_fen', 'counterparty', 'reference', 'note', 'attachment')


def _audit(conn, actor_id, action, before, after):
    conn.execute('INSERT INTO finance_ledger_audit(entry_id,actor_id,action,before_json,after_json,created_at) VALUES (?,?,?,?,?,?)',
                 (after['id'], actor_id, action, json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), int(time.time())))


def list_entries(*, page=1, page_size=30, direction="", status="active", q="", start_date="", end_date=""):
    for value in (start_date, end_date):
        if value:
            try:
                if len(value) != 10:
                    raise ValueError()
                date.fromisoformat(value)
            except ValueError:
                raise HTTPException(422, detail={'error': '筛选日期必须是有效的 YYYY-MM-DD'}) from None
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, detail={'error': '起始日期不能晚于截止日期'})
    clauses, args = ["1=1"], []
    if direction:
        clauses.append("direction = ?")
        args.append(direction)
    if status:
        clauses.append("status = ?")
        args.append(status)
    if q:
        clauses.append("(identifier ILIKE ? OR category ILIKE ? OR counterparty ILIKE ? OR reference ILIKE ? OR note ILIKE ?)")
        args.extend([f"%{escape_like(q)}%"] * 5)
    if start_date:
        clauses.append("entry_date >= ?")
        args.append(start_date)
    if end_date:
        clauses.append("entry_date <= ?")
        args.append(end_date)
    where = " AND ".join(clauses)
    with db(read_only_snapshot=True) as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM finance_ledger_entries WHERE {where}", args).fetchone()[0])
        rows = [dict(row) for row in conn.execute(
            f"SELECT * FROM finance_ledger_entries WHERE {where} ORDER BY entry_date DESC, created_at DESC, id DESC LIMIT ? OFFSET ?",
            (*args, page_size, (page - 1) * page_size),
        )]
        summary = conn.execute(
            f"SELECT COALESCE(SUM(CASE WHEN direction='income' AND status='active' THEN amount_fen ELSE 0 END),0) income_fen, "
            f"COALESCE(SUM(CASE WHEN direction='expense' AND status='active' THEN amount_fen ELSE 0 END),0) expense_fen, "
            f"COALESCE(SUM(CASE WHEN status='active' THEN tax_fen ELSE 0 END),0) tax_fen FROM finance_ledger_entries WHERE {where}", args,
        ).fetchone()
    return {"items": rows, "total": total, "page": page, "page_size": page_size,
            "summary": {"income_fen": int(summary[0]), "expense_fen": int(summary[1]), "tax_fen": int(summary[2]),
                         "net_fen": int(summary[0]) - int(summary[1])}}


def create(actor_id: int, body: dict) -> dict:
    body = FinanceLedgerInput.model_validate(body).model_dump()
    now = int(time.time())
    identifier = body['identifier'] or uuid.uuid4().hex
    with db(serialized="accounts") as conn:
        existing = conn.execute("SELECT * FROM finance_ledger_entries WHERE identifier = ?", (identifier,)).fetchone()
        if existing:
            if any(existing[key] != body[key] for key in FIELDS):
                raise HTTPException(409, detail={'error': '该保存标识已用于其他内容，请刷新核对', 'code': 'idempotency_conflict'})
            return dict(existing)
        row = dict(conn.execute(
            "INSERT INTO finance_ledger_entries(id, identifier, entry_date, direction, category, amount_fen, tax_fen, counterparty, reference, note, attachment, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *",
            (uuid.uuid4().hex, identifier, *(body[key] for key in FIELDS), actor_id, now, now),
        ).fetchone())
        _audit(conn, actor_id, 'create', {}, row)
    return row


def _current(conn, identifier: str, revision: int):
    row = conn.execute("SELECT * FROM finance_ledger_entries WHERE identifier = ? FOR UPDATE", (identifier,)).fetchone()
    if not row:
        raise HTTPException(404, detail={"error": "账本记录不存在"})
    if row["revision"] != revision:
        raise HTTPException(409, detail={"error": "账本记录已更新，请刷新后重试", "code": "revision_conflict"})
    if row['status'] != 'active':
        raise HTTPException(409, detail={'error': '已作废的记录不能修改，请新增正确记录'})
    return dict(row)


def update(actor_id: int, identifier: str, revision: int, body: dict) -> dict:
    body = FinanceLedgerInput.model_validate(body).model_dump()
    if body['identifier'] and body['identifier'] != identifier:
        raise HTTPException(422, detail={'error': '不能修改账本标识'})
    with db(serialized="accounts") as conn:
        before = _current(conn, identifier, revision)
        row = dict(conn.execute(
            "UPDATE finance_ledger_entries SET entry_date=?, direction=?, category=?, amount_fen=?, tax_fen=?, counterparty=?, reference=?, note=?, attachment=?, revision=revision+1, updated_at=? "
            "WHERE identifier=? RETURNING *", (*(body[key] for key in FIELDS), int(time.time()), identifier),
        ).fetchone())
        _audit(conn, actor_id, 'update', before, row)
    return row


def void(actor_id: int, identifier: str, revision: int) -> dict:
    with db(serialized="accounts") as conn:
        before = _current(conn, identifier, revision)
        row = dict(conn.execute("UPDATE finance_ledger_entries SET status='void', revision=revision+1, updated_at=? WHERE identifier=? RETURNING *",
                                (int(time.time()), identifier)).fetchone())
        _audit(conn, actor_id, 'void', before, row)
    return row


def _csv_cell(value):
    # Excel 打开 CSV 时，用户填写的对方名称、备注等不可被当作公式。
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def export_csv(**filters) -> str:
    result = list_entries(page=1, page_size=10000, **filters)
    if result['total'] > 10000:
        raise HTTPException(422, detail={'error': '导出超过一万条，请按日期缩小范围'})
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["标识", "日期", "方向", "分类", "含税金额(分)", "税额(分)", "对方", "凭据", "备注", "状态"])
    for row in result["items"]:
        writer.writerow([_csv_cell(row[key]) for key in ('identifier', 'entry_date', 'direction', 'category', 'amount_fen', 'tax_fen', 'counterparty', 'reference', 'note', 'status')])
    return output.getvalue()