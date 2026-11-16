"""渠道账单只用于核对；导入不会改变订单、退款或奖励状态。"""

import csv
import hashlib
import io
import json
import time
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.db import db
from app.services import settlements
from app.services.mini_errors import fail
from app.services.settlement_channels import CHANNEL_LABELS, channel_key

HEADERS = ['订单号', '交易号', '渠道', '实收（元）', '手续费（元）', '退款（元）', '交易日期']


def template():
    return '\ufeff' + ','.join(HEADERS) + '\r\n'


def money(value):
    try:
        amount = Decimal(value.strip()) * 100
        if not amount.is_finite() or amount < 0 or amount > 100000000000 or amount != amount.to_integral_value():
            raise ValueError
        return int(amount)
    except (ValueError, InvalidOperation):
        fail('账单金额必须为非负数，最多两位小数', 422)


def import_bill(actor, body):
    with db() as conn:
        from app.services.settlement_access import authorize
        authorize(conn, actor, 'Costs')
    try:
        reader = csv.DictReader(io.StringIO(body.content.lstrip('\ufeff')), strict=True)
        if reader.fieldnames != HEADERS:
            fail('账单列名或顺序不符，请使用下载的 CSV 模板', 422)
        rows: list[dict[str, Any]] = []
        seen = set()
        for row in reader:
            if len(rows) >= 5000 or None in row or any(value is None for value in row.values()):
                fail('账单格式不正确或超过 5000 行', 422)
            key, transaction = row['订单号'].strip(), row['交易号'].strip()
            if not key or len(key) > 200 or key in seen or not transaction or len(transaction) > 200:
                fail('订单号或交易号缺失、过长，或订单重复', 422)
            seen.add(key)
            channel = row['渠道'].strip()
            if channel not in ('wechat', 'virtual_android', 'virtual_ios'):
                fail('渠道填写 wechat、virtual_android 或 virtual_ios', 422)
            day = datetime.strptime(row['交易日期'].strip(), '%Y-%m-%d').strftime('%Y-%m-%d')
            values = [money(row[name]) for name in HEADERS[3:6]]
            if values[2] > values[0]:
                fail('退款金额不能超过实收', 422)
            rows.append({'order_id': key, 'transaction_id': transaction, 'channel': channel,
                         'amount_fen': values[0], 'channel_fee_fen': values[1], 'refunded_fen': values[2], 'bill_date': day})
    except (csv.Error, ValueError):
        fail('账单格式或交易日期无效', 422)
    if not rows:
        fail('账单没有明细', 422)
    digest = hashlib.sha256(json.dumps(sorted(rows, key=lambda r: r['order_id']), sort_keys=True).encode()).hexdigest()
    with db(serialized='accounts') as conn:
        authorize(conn, actor, 'Costs')
        previous = conn.execute('SELECT id FROM referral_bill_imports WHERE digest=?', (digest,)).fetchone()
        if previous:
            return {'id': previous['id'], 'orders': len(rows), 'duplicate': True}
        identifier = uuid.uuid4().hex
        conn.execute('INSERT INTO referral_bill_imports(id,digest,name,evidence,actor_id,created_at) VALUES(?,?,?,?,?,?)',
                     (identifier, digest, body.name, body.evidence, actor, int(time.time())))
        for row in rows:
            conn.execute('INSERT INTO referral_bill_rows(import_id,order_id,transaction_id,channel,amount_fen,channel_fee_fen,refunded_fen,bill_date) VALUES(?,?,?,?,?,?,?,?)',
                         (identifier, *row.values()))
        settlements.audit(conn, actor, 'bill_imported', identifier, {'name': body.name, 'orders': len(rows), 'digest': digest})
    return {'id': identifier, 'orders': len(rows), 'duplicate': False}


def checks(conn, ids):
    if not ids:
        return []
    rows = conn.execute('SELECT o.id,o.amount_fen,o.transaction_id,o.paid_at,o.payment_channel,o.device_platform,o.status,r.costs, '
                        'f.status AS refund_status,b.id AS bill_row_id,b.amount_fen AS bill_amount_fen,b.channel_fee_fen,b.refunded_fen,b.channel,b.transaction_id AS bill_transaction_id,b.bill_date '
                        'FROM mini_orders o LEFT JOIN referral_rewards r ON r.order_id=o.id LEFT JOIN mini_refunds f ON f.order_id=o.id '
                        'LEFT JOIN LATERAL (SELECT * FROM referral_bill_rows WHERE order_id=o.id ORDER BY id DESC LIMIT 1) b ON TRUE WHERE o.id=ANY(?)', (ids,)).fetchall()
    from app.services.settlement_queries import ZONE
    days = {row['id']: datetime.fromtimestamp(row['paid_at'], ZONE).strftime('%Y-%m-%d')
            for row in rows if row['payment_channel'] == 'wechat' and row['paid_at']}
    daily: dict[str, str] = {}
    issues: dict[str, dict[str, Any]] = {}
    incomplete: dict[str, str] = {}
    if days:
        # 每个账单日取最新已完成结果，后续退款日的差异也须纳入，避免只检查原付款日。
        records = conn.execute("WITH latest AS (SELECT DISTINCT ON (bill_date) id,bill_date,differences_json, "
                               "COALESCE((summary_json::jsonb->>'differences')::bigint,jsonb_array_length(differences_json::jsonb)) "
                               "<> jsonb_array_length(differences_json::jsonb) AS incomplete "
                               "FROM mini_reconciliations WHERE status='complete' AND bill_date>=? ORDER BY bill_date,created_at DESC,id DESC) "
                               "SELECT l.id,l.bill_date,l.incomplete,v.value->>'order_id' AS order_id,v.value->>'reason' AS reason FROM latest l "
                               "LEFT JOIN LATERAL (SELECT value FROM jsonb_array_elements(l.differences_json::jsonb) "
                               "WHERE value->>'order_id'=ANY(?)) v ON TRUE WHERE l.bill_date=ANY(?) OR v.value IS NOT NULL OR l.incomplete",
                               (min(days.values()), list(days), list(set(days.values())))).fetchall()
        for record in records:
            daily[record['bill_date']] = record['id']
            if record['incomplete']:
                incomplete[record['bill_date']] = record['id']
            if record['order_id']:
                entry = issues.setdefault(record['order_id'], {'id': record['id'], 'differences': []})
                entry['differences'].append(record['reason'])
        for bill_day, identifier in incomplete.items():
            for order_id, paid_day in days.items():
                if paid_day <= bill_day:
                    entry = issues.setdefault(order_id, {'id': identifier, 'differences': []})
                    entry['differences'].append(bill_day + ' 微信账单差异未完整留存，请重新核对当日账单')
    result = []
    for row in rows:
        differences = []
        expected_fee = row['costs']['channel_fee_fen'] if row['costs'] else None
        if row['bill_row_id']:
            if row['amount_fen'] != row['bill_amount_fen']:
                differences.append('实收金额不一致')
            if row['transaction_id'] != row['bill_transaction_id']:
                differences.append('交易号不一致')
            if channel_key(row['payment_channel'], row['device_platform']) != row['channel']:
                differences.append('支付渠道不一致')
            if row['status'] != 'paid' or row['refund_status'] in ('requested', 'processing', 'abnormal', 'success') or row['refunded_fen']:
                differences.append('存在退款或订单未付款')
            if not row['paid_at'] or datetime.fromtimestamp(row['paid_at'], ZONE).strftime('%Y-%m-%d') != row['bill_date']:
                differences.append('付款日期不一致')
        # 微信线上日账单是收退款核对结果；没有手续费字段时明确标为仍需核对。
        reconciliation = None
        if row['id'] in days:
            reconciliation = issues.get(row['id'])
            if reconciliation is None and days[row['id']] in daily:
                reconciliation = {'id': daily[days[row['id']]], 'differences': []}
        result.append({'order_id': row['id'], 'bill_row_id': row['bill_row_id'], 'channel_fee_fen': row['channel_fee_fen'],
                       'confirmed_fee_fen': expected_fee, 'fee_difference': expected_fee is not None and row['channel_fee_fen'] is not None and expected_fee != row['channel_fee_fen'],
                       'differences': differences, 'can_adopt': bool(row['bill_row_id']) and not differences, 'wechat_reconciliation': reconciliation})
    return result


def validate_cost(conn, order_id, body):
    if body.bill_row_id is None:
        return
    row = checks(conn, [order_id])[0]
    if not row['can_adopt'] or row['bill_row_id'] != body.bill_row_id or body.channel_fee_fen != row['channel_fee_fen'] or body.channel_rate_bps is not None:
        fail('账单已变化、存在差异或手续费不匹配，请刷新核对', 409)


def statement_differences(conn, statement):
    """核对最新账单与已留存费用；没有导入账单时仍允许据实人工核对。"""
    result = []
    for row in checks(conn, [item['order_id'] for item in statement['snapshot']['items']]):
        reasons = list(row['differences'])
        if row['fee_difference']:
            reasons.append('已核定手续费与最新账单不同')
        if row['wechat_reconciliation']:
            reasons.extend(row['wechat_reconciliation']['differences'])
        if reasons:
            result.append({'order_id': row['order_id'], 'reasons': list(dict.fromkeys(reasons))})
    return result


def validate_statement(conn, statement):
    differences = statement_differences(conn, statement)
    if differences:
        fail('最新账单存在未处理差异，请作废结算单后重新核对：' + '；'.join(
            item['order_id'] + '：' + '、'.join(item['reasons']) for item in differences[:5]), 409)


def listing(actor, identifier=None):
    with db() as conn:
        from app.services.settlement_access import authorize
        authorize(conn, actor, 'Costs', 'view')
        if identifier:
            rows = [dict(row) for row in conn.execute('SELECT * FROM referral_bill_rows WHERE import_id=? ORDER BY id', (identifier,))]
            values = {row['order_id']: row for row in checks(conn, [row['order_id'] for row in rows])}
            return {'items': [{**row, 'channel_label': CHANNEL_LABELS[row['channel']], 'check': values.get(row['order_id'])} for row in rows]}
        return {'items': [dict(row) for row in conn.execute('SELECT b.id,b.name,b.evidence,b.created_at,COUNT(r.id) AS orders FROM referral_bill_imports b LEFT JOIN referral_bill_rows r ON r.import_id=b.id GROUP BY b.id ORDER BY b.created_at DESC,b.id DESC LIMIT 30')]}
