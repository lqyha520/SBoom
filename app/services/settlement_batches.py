"""人工付款清单及银行回单匹配；不调用支付渠道。"""

import csv
import hashlib
import io
import json
import re
import time
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException

from app.db import db
from app.models.settlements import ReceiptInput
from app.security import decrypt_secret
from app.services import settlement_access, settlements
from app.services.mini_errors import fail
from app.services.settlement_queries import ZONE
from app.sql_utils import escape_like

HEADERS = ['结算单', '收款人', '收款方式', '开户行', '收款账号', '金额（元）', '流水号', '实际付款时间', '结果', '说明']


def candidate(conn, actor, row):
    issues = []
    reserved = conn.execute("SELECT b.id,b.name FROM referral_payout_batch_items i JOIN referral_payout_batches b ON b.id=i.batch_id WHERE i.statement_id=? AND i.status IN ('pending','failed')", (row['id'],)).fetchone()
    if reserved:
        issues.append('已加入付款批次：' + reserved['name'])
    if row['status'] != 'approved':
        issues.append('结算单已变化，不再是待付款状态')
    else:
        if max(0, row['net_fen']) > 0 and (not row['snapshot'].get('payee') or not conn.execute('SELECT 1 FROM referral_payout_accounts WHERE statement_id=?', (row['id'],)).fetchone()):
            issues.append('尚未留存本单收款资料')
        try:
            settlements.check_statement(conn, row)
            settlement_access.check_payment(conn, actor, row)
        except HTTPException as error:
            if error.status_code not in (403, 409, 422):
                raise
            issues.append(error.detail['error'] if isinstance(error.detail, dict) else str(error.detail))
    return {**dict(row), 'payout_issues': issues, 'batch_id': reserved['id'] if reserved else None}


def candidates(actor, page=1):
    with db(read_only_snapshot=True) as conn:
        settlement_access.authorize(conn, actor, 'Payout')
        total = conn.execute("SELECT COUNT(*) FROM referral_statements WHERE status='approved'").fetchone()[0]
        page = min(page, max(1, (total + 19) // 20))
        rows = conn.execute("SELECT * FROM referral_statements WHERE status='approved' ORDER BY created_at,id LIMIT 20 OFFSET ?", ((page - 1) * 20,))
        return {'items': [candidate(conn, actor, row) for row in rows], 'total': total, 'page': page}


def selection(actor, identifiers):
    with db(read_only_snapshot=True) as conn:
        settlement_access.authorize(conn, actor, 'Payout')
        ids = list(dict.fromkeys(identifiers))
        rows = {row['id']: row for row in conn.execute('SELECT * FROM referral_statements WHERE id=ANY(?)', (ids,))}
        items = [candidate(conn, actor, rows[key]) if key in rows else {'id': key, 'net_fen': 0, 'payout_issues': ['结算单不存在']} for key in ids]
        return {'items': items, 'total_fen': sum(max(0, item['net_fen'] or 0) for item in items),
                'blocked': sum(bool(item['payout_issues']) for item in items)}


def csv_text(value):
    return "'" + value if value and value[0] in '=+-@\t\r' else value


def batch(conn, actor, identifier, write=False):
    settlement_access.authorize(conn, actor, 'Payout', 'run' if write else 'view')
    row = conn.execute('SELECT * FROM referral_payout_batches WHERE id=?', (identifier,)).fetchone()
    if not row:
        fail('付款批次不存在', 404)
    return row


def detail(conn, actor, identifier):
    row = batch(conn, actor, identifier)
    items = [dict(r) for r in conn.execute('SELECT b.*,s.status AS statement_status,s.receipt,s.payout FROM referral_payout_batch_items b JOIN referral_statements s ON s.id=b.statement_id WHERE batch_id=? ORDER BY statement_id', (identifier,))]
    return {**dict(row), 'items': items, 'item_count': len(items), 'total_fen': sum(item['snapshot']['amount_fen'] for item in items)}


def listing(actor, page=1, q='', status=''):
    with db(read_only_snapshot=True) as conn:
        settlement_access.authorize(conn, actor, 'Payout', 'view')
        where, args = 'TRUE', []
        if q.strip():
            where += " AND (b.name ILIKE ? ESCAPE '\\' OR b.id ILIKE ? ESCAPE '\\')"
            args.extend(['%' + escape_like(q.strip()) + '%'] * 2)
        if status:
            where += ' AND b.status=?'
            args.append(status)
        rows = conn.execute(
            'SELECT b.id,b.name,b.status,b.revision,b.created_at, '
            "COALESCE(SUM((i.snapshot->>'amount_fen')::bigint),0) AS total_fen, "
            'COUNT(i.statement_id) AS item_count '
            f'FROM referral_payout_batches b LEFT JOIN referral_payout_batch_items i ON i.batch_id=b.id WHERE {where} '
            'GROUP BY b.id,b.name,b.status,b.revision,b.created_at ORDER BY b.created_at DESC,b.id LIMIT 20 OFFSET ?',
            [*args, (page - 1) * 20],
        ).fetchall()
        # 列表只返回汇总；付款单明细在用户打开批次时由 detail 接口按需读取。
        return {'items': [dict(row) for row in rows], 'total': conn.execute(f'SELECT COUNT(*) FROM referral_payout_batches b WHERE {where}', args).fetchone()[0]}


def create(actor, body):
    with db(serialized='accounts') as conn:
        settlement_access.authorize(conn, actor, 'Payout')
        prior = conn.execute('SELECT id,name FROM referral_payout_batches WHERE request_key=?', (body.request_key,)).fetchone()
        if prior:
            result = detail(conn, actor, prior[0])
            if prior['name'] != body.name or {r['statement_id'] for r in result['items']} != set(body.statement_ids):
                fail('请求编号已用于其他付款批次', 409)
            return result
        if len(body.statement_ids) != len(set(body.statement_ids)):
            fail('结算单不能重复选择', 422)
        values = []
        for identifier in body.statement_ids:
            row = settlements.statement_row(conn, identifier)
            if row['status'] != 'approved':
                fail('只能将已审核待付款结算单加入批次', 409)
            settlements.check_statement(conn, row)
            settlement_access.check_payment(conn, actor, row)
            if max(0, row['net_fen']) > 0 and (not row['snapshot'].get('payee') or not conn.execute('SELECT 1 FROM referral_payout_accounts WHERE statement_id=?', (identifier,)).fetchone()):
                fail('请先为非零结算单留存收款资料', 409)
            if conn.execute("SELECT 1 FROM referral_payout_batch_items WHERE statement_id=? AND status IN ('pending','failed')", (identifier,)).fetchone():
                fail('结算单已在其他付款批次中', 409)
            values.append((identifier, {'revision': row['revision'], 'amount_fen': max(0, row['net_fen']), 'payee': row['snapshot'].get('payee'), 'beneficiary_name': row['beneficiary_name']}))
        key, now = uuid.uuid4().hex, int(time.time())
        conn.execute('INSERT INTO referral_payout_batches(id,name,request_key,actor_id,created_at) VALUES(?,?,?,?,?)', (key, body.name, body.request_key, actor, now))
        for identifier, snapshot in values:
            conn.execute('INSERT INTO referral_payout_batch_items(batch_id,statement_id,snapshot) VALUES(?,?,?::jsonb)', (key, identifier, json.dumps(snapshot)))
        settlements.audit(conn, actor, 'payout_batch_created', key, {'statement_ids': body.statement_ids})
        return detail(conn, actor, key)


def export(actor, identifier):
    with db(serialized='accounts') as conn:
        row = batch(conn, actor, identifier, True)
        settlement_access.authorize(conn, actor, 'Payout', 'export')
        if row['status'] != 'active':
            fail('此批次已结束，不能生成待付款清单', 409)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(HEADERS)
        for item in detail(conn, actor, identifier)['items']:
            if item['status'] not in ('pending', 'failed'):
                continue
            statement = settlements.statement_row(conn, item['statement_id'])
            if statement['status'] != 'approved' or statement['revision'] != item['snapshot']['revision']:
                fail('批次结算单已变化，请取消批次后重新生成', 409)
            settlements.check_statement(conn, statement)
            settlement_access.check_payment(conn, actor, statement)
            account = conn.execute('SELECT value_enc FROM referral_payout_accounts WHERE statement_id=?', (statement['id'],)).fetchone()
            payee = json.loads(decrypt_secret(account[0])) if account else {}
            account = payee.get('account', '')
            # CSV 中的账号作为文本，回单导入时移除这个保护前缀。
            writer.writerow([statement['id'], csv_text(payee.get('name', '')), payee.get('method', ''), csv_text(payee.get('bank', '')),
                             "'" + account if account else '', format(Decimal(item['snapshot']['amount_fen']) / 100, '.2f'), '', '', '', ''])
        settlements.audit(conn, actor, 'payout_batch_exported', identifier, {})
        return ('\ufeff' + output.getvalue()).encode('utf-8')


def parse(content):
    try:
        reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')), strict=True)
        if reader.fieldnames != HEADERS:
            fail('请使用本批次导出的付款清单填写回单，列名与顺序须保留', 422)
        rows = list(reader)
        if not rows or len(rows) > 200:
            fail('一次回单须包含 1 至 200 条记录', 422)
        seen, result = set(), []
        for row in rows:
            if None in row or any(value is None for value in row.values()):
                fail('回单列数不一致', 422)
            identifier = row['结算单'].strip()
            if not identifier or identifier in seen:
                fail('回单结算单编号为空或重复', 422)
            seen.add(identifier)
            issues, amount, stamp = [], None, None
            try:
                text = row['金额（元）'].strip()
                if not re.fullmatch(r'\d{1,9}(\.\d{1,2})?', text):
                    raise ValueError
                amount = int(Decimal(text) * 100)
            except (InvalidOperation, ValueError):
                issues.append('金额格式无效，最多两位小数')
            status = {'成功': 'paid', '失败': 'failed', '待确认': 'pending', '': 'pending'}.get(row['结果'].strip())
            if status is None:
                issues.append('结果只支持成功、失败或待确认')
            if status == 'paid':
                if amount != 0 or row['实际付款时间'].strip():
                    try:
                        stamp = int(datetime.strptime(row['实际付款时间'].strip(), '%Y-%m-%d %H:%M:%S').replace(tzinfo=ZONE).timestamp())
                    except (ValueError, OverflowError):
                        issues.append('实际付款时间须为北京时间 YYYY-MM-DD HH:mm:ss')
                if not 2 <= len(row['流水号'].strip()) <= 500:
                    issues.append('成功回单须填写 2 至 500 字流水号')
            result.append({'statement_id': identifier, 'account': row['收款账号'].strip().removeprefix("'"), 'payee_name': row['收款人'].strip().removeprefix("'"), 'method': row['收款方式'].strip(), 'amount_fen': amount,
                           'receipt': row['流水号'].strip(), 'transferred_at': stamp, 'status': status,
                           'reason': row['说明'].strip()[:500], 'issues': issues})
        return result
    except csv.Error:
        fail('CSV 回单格式无效', 422)


def match(conn, actor, identifier, content):
    batch(conn, actor, identifier, True)
    items = {r['statement_id']: r for r in detail(conn, actor, identifier)['items']}
    rows = parse(content)
    receipts = set()
    for row in rows:
        item = items.get(row['statement_id'])
        if not item:
            row['issues'].append('不属于此付款批次')
            continue
        statement = settlements.statement_row(conn, row['statement_id'])
        if item['snapshot']['amount_fen'] != row['amount_fen']:
            row['issues'].append('回单金额与批次最终应付不一致')
        account = conn.execute('SELECT value_enc FROM referral_payout_accounts WHERE statement_id=?', (row['statement_id'],)).fetchone()
        expected = json.loads(decrypt_secret(account[0])) if account else {}
        if expected.get('account', '') != row['account']:
            row['issues'].append('收款账号与本单留存账号不一致')
        if expected.get('name', '') != row['payee_name'] or expected.get('method', '') != row['method']:
            row['issues'].append('收款人或收款方式与本单留存资料不一致')
        if row['status'] == 'paid':
            if row['receipt'] in receipts:
                row['issues'].append('同一流水号不能匹配多张结算单')
            receipts.add(row['receipt'])
            if item['status'] == 'paid' and statement['receipt'] == row['receipt']:
                continue
            if statement['status'] != 'approved' or statement['revision'] != item['snapshot']['revision']:
                row['issues'].append('结算单已变化或已付款')
            if row['transferred_at'] is not None and not statement['created_at'] <= row['transferred_at'] <= int(time.time()) + 60:
                row['issues'].append('转账时间早于制单或属于未来时间')
            if conn.execute("SELECT 1 FROM referral_statements WHERE status='paid' AND receipt=? AND id<>?", (row['receipt'], row['statement_id'])).fetchone():
                row['issues'].append('流水号已用于其他付款')
            try:
                settlements.check_statement(conn, statement)
                settlement_access.check_payment(conn, actor, statement)
            except HTTPException as e:
                reason = e.detail.get('error', str(e.detail)) if isinstance(e.detail, dict) else str(e.detail)
                row['issues'].append(reason)
        elif item['status'] in ('paid', 'cancelled'):
            row['issues'].append('已付款或已取消的记录不能更改状态')
    return rows


def preview(actor, identifier, content):
    with db(read_only_snapshot=True) as conn:
        rows = match(conn, actor, identifier, content)
        for row in rows:
            row.pop('account')
            row.pop('payee_name')
            row.pop('method')
        return {'items': rows, 'matched': sum(not r['issues'] for r in rows), 'blocked': sum(bool(r['issues']) for r in rows)}


def import_receipts(actor, identifier, body):
    digest = hashlib.sha256(body.content.encode()).hexdigest()
    with db(serialized='accounts') as conn:
        header = batch(conn, actor, identifier, True)
        prior = conn.execute('SELECT result FROM referral_payout_imports WHERE batch_id=? AND digest=?', (identifier, digest)).fetchone()
        if prior:
            return {**prior[0], 'duplicate': True}
        if header['status'] != 'active' or header['revision'] != body.revision:
            fail('付款批次已变化或结束，请刷新', 409)
        rows = match(conn, actor, identifier, body.content)
        result: dict[str, Any] = {'paid': 0, 'failed': 0, 'pending': 0, 'blocked': 0, 'issues': []}
        for row in rows:
            if row['issues']:
                result['blocked'] += 1
                result['issues'].append({'statement_id': row['statement_id'], 'reasons': row['issues']})
                continue
            if row['status'] == 'paid':
                item = conn.execute('SELECT snapshot FROM referral_payout_batch_items WHERE batch_id=? AND statement_id=?', (identifier, row['statement_id'])).fetchone()
                settlements._record_payout(conn, actor, row['statement_id'], ReceiptInput(revision=item[0]['revision'], amount_fen=row['amount_fen'], receipt=row['receipt'], transferred_at=row['transferred_at']), identifier)
            if row['status'] in ('paid', 'failed'):
                conn.execute('UPDATE referral_payout_batch_items SET status=?,reason=? WHERE batch_id=? AND statement_id=?', (row['status'], row['reason'], identifier, row['statement_id']))
            result[row['status']] += 1
        pending = conn.execute("SELECT COUNT(*) FROM referral_payout_batch_items WHERE batch_id=? AND status IN ('pending','failed')", (identifier,)).fetchone()[0]
        conn.execute('UPDATE referral_payout_batches SET revision=revision+1,status=? WHERE id=?', ('active' if pending else 'completed', identifier))
        conn.execute('INSERT INTO referral_payout_imports(batch_id,digest,result,actor_id,created_at) VALUES(?,?,?::jsonb,?,?)', (identifier, digest, json.dumps(result), actor, int(time.time())))
        settlements.audit(conn, actor, 'payout_batch_imported', identifier, result)
        return result


def cancel(actor, identifier, revision):
    with db(serialized='accounts') as conn:
        row = batch(conn, actor, identifier, True)
        if row['revision'] != revision or row['status'] != 'active':
            fail('批次已变化或结束', 409)
        conn.execute("UPDATE referral_payout_batch_items SET status='cancelled' WHERE batch_id=? AND status IN ('pending','failed')", (identifier,))
        conn.execute("UPDATE referral_payout_batches SET status='cancelled',revision=revision+1 WHERE id=?", (identifier,))
        settlements.audit(conn, actor, 'payout_batch_cancelled', identifier, {})
        return detail(conn, actor, identifier)
