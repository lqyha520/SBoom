"""核定应付余额的不可覆盖事件账本；参考奖励不计入余额。"""

import hashlib
import json
import time
import uuid
from datetime import datetime

from app.db import db
from app.services import settlement_access
from app.services.mini_errors import fail
from app.services.settlement_export import date_time, money, workbook
from app.services.settlement_queries import ZONE

LABELS = {'reward': '核定税前奖励', 'adjustment': '奖励调整', 'personal': '个人费用', 'tax': '代扣个税',
          'payment': '已付款', 'void_reward': '作废核定奖励', 'void_personal': '作废个人费用', 'void_tax': '作废个税'}


def event(conn, source, beneficiary, kind, amount, stamp, statement=''):
    last = conn.execute('SELECT MAX(month) FROM referral_monthly_reports WHERE beneficiary=?', (beneficiary,)).fetchone()[0]
    effective = max(stamp, month_range(last)[1]) if last else stamp
    conn.execute('INSERT INTO referral_ledger_events(source,beneficiary,kind,amount_fen,occurred_at,original_at,statement_id) VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING',
                 (source, beneficiary, kind, amount, effective, stamp, statement))


def statement_events(conn, row):
    key, owner = row['id'], row['beneficiary']
    if row['approved_at']:
        for kind, amount in (('reward', row['gross_fen']), ('personal', -row['personal_fen']), ('tax', -(row['tax_fen'] or 0))):
            event(conn, kind + ':' + key, owner, kind, amount, row['approved_at'], key)
        if row['status'] == 'void':
            void = conn.execute("SELECT created_at FROM referral_settlement_audit WHERE target=? AND kind='void_statement' ORDER BY id DESC LIMIT 1", (key,)).fetchone()
            for kind, amount in (('reward', -row['gross_fen']), ('personal', row['personal_fen']), ('tax', row['tax_fen'] or 0)):
                event(conn, 'void_' + kind + ':' + key, owner, 'void_' + kind, amount, void[0] if void else row['updated_at'], key)
    if row['status'] == 'paid':
        event(conn, 'payment:' + key, owner, 'payment', -max(0, row['net_fen']), row['payout'].get('transferred_at') or row['paid_at'], key)


def record(conn, kind, target, value):
    if kind in ('approve', 'record_payout', 'void_statement'):
        row = conn.execute('SELECT * FROM referral_statements WHERE id=?', (target,)).fetchone()
        if row:
            statement_events(conn, row)
    elif kind == 'adjustment' and not target.startswith('carry:'):
        row = conn.execute('SELECT * FROM referral_adjustments WHERE source=?', (target,)).fetchone()
        if row:
            event(conn, 'adjustment:' + target, row['beneficiary'], 'adjustment', row['amount_fen'], row['created_at'])


def backfill(conn):
    # carry 只是余额结转，不能再作为新债项重复扣回。
    for row in conn.execute('SELECT * FROM referral_statements WHERE approved_at IS NOT NULL').fetchall():
        statement_events(conn, row)
    for row in conn.execute("SELECT * FROM referral_adjustments WHERE source NOT LIKE 'carry:%'").fetchall():
        event(conn, 'adjustment:' + row['source'], row['beneficiary'], 'adjustment', row['amount_fen'], row['created_at'])


def month_range(month):
    try:
        start = datetime.strptime(month, '%Y-%m').replace(tzinfo=ZONE)
        if start.strftime('%Y-%m') != month:
            raise ValueError
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        if start > datetime.now(ZONE):
            raise ValueError
        return int(start.timestamp()), int(end.timestamp())
    except (ValueError, OverflowError):
        fail('月份无效或尚未开始', 422)


def target_owner(conn, actor, admin_id):
    owner = settlement_access.owner_id(conn, actor)
    if owner is not None and owner != admin_id:
        fail('不能查看其他推广人的月度对账单', 403)
    row = conn.execute("SELECT username FROM users WHERE id=? AND role='admin'", (admin_id,)).fetchone()
    if not row:
        fail('推广人不存在', 404)
    return 'admin:' + str(admin_id), row[0]


def report_digest(report):
    quoted = {key: report[key] for key in ('admin_id', 'admin_name', 'month', 'opening_fen', 'closing_fen', 'totals', 'items')}
    return hashlib.sha256(json.dumps(quoted, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def preview(conn, actor, admin_id, month):
    owner, name = target_owner(conn, actor, admin_id)
    start, end = month_range(month)
    saved = conn.execute('SELECT id,snapshot,created_at FROM referral_monthly_reports WHERE beneficiary=? AND month=?', (owner, month)).fetchone()
    if saved:
        return {**saved['snapshot'], 'quote_digest': report_digest(saved['snapshot']), 'archive_id': saved['id'], 'archived_at': saved['created_at']}
    opening = int(conn.execute('SELECT COALESCE(SUM(amount_fen),0) FROM referral_ledger_events WHERE beneficiary=? AND occurred_at<?', (owner, start)).fetchone()[0])
    rows = [dict(r) for r in conn.execute('SELECT * FROM referral_ledger_events WHERE beneficiary=? AND occurred_at>=? AND occurred_at<? ORDER BY occurred_at,source', (owner, start, end))]
    totals = {kind: sum(row['amount_fen'] for row in rows if row['kind'] == kind) for kind in LABELS}
    result = {'admin_id': admin_id, 'admin_name': name, 'month': month, 'opening_fen': opening,
            'closing_fen': opening + sum(row['amount_fen'] for row in rows), 'totals': totals, 'items': rows,
            'as_of': int(time.time()), 'archive_id': None}
    return {**result, 'quote_digest': report_digest(result)}


def monthly(actor, admin_id, month):
    with db(read_only_snapshot=True) as conn:
        return preview(conn, actor, admin_id, month)


def archive(actor, body):
    with db(serialized='accounts') as conn:
        settlement_access.authorize(conn, actor, 'Review')
        result = preview(conn, actor, body.admin_id, body.month)
        if result['quote_digest'] != body.quote_digest:
            fail('月度账本已变化，请刷新后重新核对再留档', 409)
        if result['archive_id']:
            return result
        if month_range(body.month)[1] > int(time.time()):
            fail('当月尚未结束，请在下月留档', 422)
        key, now = uuid.uuid4().hex, int(time.time())
        conn.execute('INSERT INTO referral_monthly_reports(id,beneficiary,month,snapshot,actor_id,created_at) VALUES(?,?,?,?::jsonb,?,?)',
                     (key, 'admin:' + str(body.admin_id), body.month, json.dumps(result), actor, now))
        from app.services.settlements import audit
        audit(conn, actor, 'monthly_archived', key, {'beneficiary': 'admin:' + str(body.admin_id), 'month': body.month})
        return {**result, 'archive_id': key, 'archived_at': now}


def export(actor, admin_id, month):
    report = monthly(actor, admin_id, month)
    summary = [['推广人', '月份', '期初核定余额（元）', '期末核定余额（元）', '留档状态'],
               [report['admin_name'], month, money(report['opening_fen']), money(report['closing_fen']), '已留档' if report['archive_id'] else '实时预览']]
    totals = [['项目', '余额变动（元）']] + [[label, money(report['totals'][kind])] for kind, label in LABELS.items()]
    rows = [['账本来源', '结算单', '项目', '余额变动（元）', '入账时间（北京时间）', '原发生时间（北京时间）']] + [
        [r['source'], r['statement_id'], LABELS[r['kind']], money(r['amount_fen']), date_time(r['occurred_at']), date_time(r.get('original_at') or r['occurred_at'])] for r in report['items']]
    return workbook({'月度对账': summary, '项目汇总': totals, '余额明细': rows,
                     '口径说明': [['口径'], ['仅包含已核定奖励、原始调整、核定扣费与付款；未审核奖励不计入余额。'],
                              ['付款按实际转账时间归集，历史缺少转账时间时使用登记时间。'], ['留档不可覆盖；迟到记录归入下个未留档月份，原发生时间单独保留。']]})
