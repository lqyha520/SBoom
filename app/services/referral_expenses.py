import hashlib
import json
import time
import uuid
from datetime import date, datetime

from app.db import db
from app.services import referral_operations, settlements
from app.services.mini_errors import fail
from app.services.settlement_queries import ZONE, dates
from app.sql_utils import escape_like


def campaign(conn, actor, identifier):
    row = conn.execute('SELECT * FROM referral_campaigns WHERE id=?', (identifier,)).fetchone()
    if not row:
        fail('活动不存在', 404)
    referral_operations.campaign_scope(conn, actor, row['admin_id'])
    return row


def spend(conn, row):
    return spend_totals(conn, row)['total_fen']


def spend_totals(conn, row):
    stats = conn.execute('SELECT COUNT(*) AS count,COALESCE(SUM(amount_fen) FILTER(WHERE NOT included_in_baseline),0) AS total FROM referral_campaign_expenses WHERE campaign_id=? AND active', (row['id'],)).fetchone()
    known = (row['spend_fen'] or 0) + int(stats['total'])
    return {'known_fen': known, 'complete': row['spend_fen'] is not None,
            'total_fen': known if row['spend_fen'] is not None else None}


def validate_baseline(conn, identifier, baseline, expense_id=None, included_fen=0):
    total = conn.execute('SELECT COALESCE(SUM(amount_fen),0) FROM referral_campaign_expenses WHERE campaign_id=? AND active AND included_in_baseline AND id<>?', (identifier, expense_id or '')).fetchone()[0] + included_fen
    if total and (baseline is None or total > baseline):
        fail('历史补录合计不能超过此前累计投入，请先核对活动累计值或改为新增投入', 422)


def listing(actor, identifier, start_date='', end_date='', page=1):
    dates(start_date, end_date)
    with db(read_only_snapshot=True) as conn:
        owner = campaign(conn, actor, identifier)
        where, args = 'campaign_id=?', [identifier]
        for value, op in ((start_date, '>='), (end_date, '<=')):
            if value:
                where += ' AND expense_date ' + op + ' ?'
                args.append(value)
        stats = conn.execute(f'SELECT COUNT(*) AS count,COALESCE(SUM(amount_fen) FILTER(WHERE active),0) AS total FROM referral_campaign_expenses WHERE {where}', args).fetchone()
        totals = spend_totals(conn, owner)
        return {'items': [dict(row) for row in conn.execute(f'SELECT * FROM referral_campaign_expenses WHERE {where} ORDER BY expense_date DESC,id LIMIT 20 OFFSET ?', [*args, (page - 1) * 20])],
                'total': stats['count'], 'period_fen': int(stats['total']), 'baseline_fen': owner['spend_fen'],
                'cumulative_fen': totals['total_fen'], 'known_cumulative_fen': totals['known_fen'], 'admin_id': owner['admin_id']}


def finance_listing(actor, admin_id=None, campaign_id='', q='', start_date='', end_date='', state='all', page=1):
    with db(read_only_snapshot=True) as conn:
        return _finance_listing(conn, actor, admin_id, campaign_id, q, start_date, end_date, state, page)


def _finance_listing(conn, actor, admin_id=None, campaign_id='', q='', start_date='', end_date='', state='all', page=1, limit=20):
    """财务按活动汇总原投入明细；累计值不受明细日期和作废状态影响。"""
    from app.services import settlement_access

    dates(start_date, end_date)
    settlement_access.authorize(conn, actor, 'Costs', 'view')
    scope, args = 'TRUE', []
    if admin_id is not None:
        scope += ' AND c.admin_id=?'
        args.append(admin_id)
    if campaign_id:
        scope += ' AND c.id=?'
        args.append(campaign_id)
    if q.strip():
        scope += " AND (c.name ILIKE ? ESCAPE '\\' OR u.username ILIKE ? ESCAPE '\\')"
        args.extend(['%' + escape_like(q.strip()) + '%'] * 2)
    joined = 'referral_campaigns c LEFT JOIN users u ON u.id=c.admin_id'
    baseline = conn.execute(f'SELECT COALESCE(SUM(c.spend_fen),0) AS total,COUNT(*) FILTER(WHERE c.spend_fen IS NULL) AS unknown FROM {joined} WHERE {scope}', args).fetchone()
    rows_from = 'referral_campaign_expenses e JOIN referral_campaigns c ON e.campaign_id=c.id LEFT JOIN users u ON u.id=c.admin_id'
    full = conn.execute(f'SELECT COALESCE(SUM(e.amount_fen),0) FROM {rows_from} WHERE {scope} AND e.active AND NOT e.included_in_baseline', args).fetchone()[0]
    where, row_args = scope, list(args)
    for value, op in ((start_date, '>='), (end_date, '<=')):
        if value:
            where += ' AND e.expense_date ' + op + ' ?'
            row_args.append(value)
    if state != 'all':
        where += ' AND e.active=?'
        row_args.append(state == 'active')
    stats = conn.execute(f'SELECT COUNT(*) AS count,COALESCE(SUM(e.amount_fen) FILTER(WHERE e.active),0) AS total FROM {rows_from} WHERE {where}', row_args).fetchone()
    rows = conn.execute(f'SELECT e.*,c.name AS campaign_name,c.admin_id,COALESCE(u.username,\'历史账号\') AS admin_name FROM {rows_from} WHERE {where} ORDER BY e.expense_date DESC,e.created_at DESC,e.id LIMIT ? OFFSET ?', [*row_args, limit, (page - 1) * 20]).fetchall()
    return {'items': [dict(row) for row in rows], 'total': stats['count'], 'period_fen': int(stats['total']),
            'baseline_fen': int(baseline['total']), 'cumulative_fen': int(baseline['total']) + int(full), 'unknown_campaigns': baseline['unknown']}


def finance_export(actor, admin_id=None, campaign_id='', q='', start_date='', end_date='', state='all'):
    from app.services import settlement_access
    from app.services.settlement_export import date_time, money, workbook

    with db(read_only_snapshot=True) as conn:
        settlement_access.authorize(conn, actor, 'Costs', 'export')
        data = _finance_listing(conn, actor, admin_id, campaign_id, q, start_date, end_date, state, limit=5000)
        if data['total'] > 5000:
            fail('成本明细超过 5000 条，请缩小管理员或日期范围后导出', 422)
    records = [['记录编号', '活动编号', '活动名称', '管理员编号', '管理员', '投入日期', '类别', '投入金额（元）', '状态', '凭据', '备注', '版本', '首次登记（北京时间）', '凭据关联编号', '累计处理']]
    for row in data['items']:
        records.append([row['id'], row['campaign_id'], row['campaign_name'], row['admin_id'], row['admin_name'], str(row['expense_date']), row['category'], money(row['amount_fen']), '有效投入' if row['active'] else '已作废', row['evidence'], row['note'], row['revision'], date_time(row['created_at']), row['source_ref'], '历史累计内补录，不重复增加' if row['included_in_baseline'] else '新增计入累计'])
    scope = [['筛选项目', '筛选值'], ['管理员编号', admin_id or '全部'], ['活动编号', campaign_id or '全部'], ['关键词', q], ['投入起始日期', start_date], ['投入截止日期', end_date], ['记录状态', {'all': '全部', 'active': '有效投入', 'void': '已作废'}[state]], ['导出记录数', data['total']], ['日期范围有效投入（元）', money(data['period_fen'])], ['此前累计投入（元，已填写）', money(data['baseline_fen'])], ['全部累计投入（元，已知小计）', money(data['cumulative_fen'])], ['未填写此前累计投入的活动数', data['unknown_campaigns']], ['累计口径', '按管理员、活动与名称范围计算；不受日期和作废状态筛选影响。']]
    scope.append(['历史补录口径', '明细日期范围包括有效历史补录；全部累计为此前累计加有效新增明细，补录不再次叠加。'])
    return workbook({'成本明细': records, '筛选口径': scope})


def save(actor, identifier, body, expense_id=None):
    try:
        if date.fromisoformat(body.expense_date) > datetime.now(ZONE).date():
            fail('投放日期不能为未来日期', 422)
    except ValueError:
        fail('投放日期无效', 422)
    with db(serialized='accounts') as conn:
        owner = campaign(conn, actor, identifier)
        source_ref = settlements.cost_reference(body.source_ref)
        included = body.included_in_baseline
        if body.source_ref and len(source_ref) < 2:
            fail('凭据关联编号至少两个有效字符', 422)
        values = (body.expense_date, body.category, body.amount_fen, body.evidence, body.note)
        active = body.active if expense_id else True
        if expense_id:
            row = conn.execute('SELECT * FROM referral_campaign_expenses WHERE id=? AND campaign_id=?', (expense_id, identifier)).fetchone()
            if not row:
                fail('投入记录不存在', 404)
            if row['revision'] != body.revision:
                fail('投入记录已变化，请刷新', 409)
            if 'source_ref' not in body.model_fields_set:
                source_ref = row['source_ref']
            if 'included_in_baseline' not in body.model_fields_set:
                included = row['included_in_baseline']
        else:
            # 兼容旧请求的摘要，响应丢失后重试仍返回原记录。
            digest_values = (*values, source_ref, body.included_in_baseline) if source_ref or body.included_in_baseline else values
            digest = hashlib.sha256(json.dumps(digest_values, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            prior = conn.execute('SELECT * FROM referral_campaign_expenses WHERE campaign_id=? AND request_key=?', (identifier, body.request_key)).fetchone()
            if prior:
                if prior['request_digest'] != digest:
                    fail('本次投入请求已登记，请刷新后查看；更正请修改已有记录', 409)
                return dict(prior)
        if active and source_ref and conn.execute('SELECT 1 FROM referral_campaign_expenses WHERE active AND source_ref=? AND id<>?', (source_ref, expense_id or '')).fetchone():
            fail('此凭据费用项已有有效投入记录，请修改原记录；分摊到不同活动时请使用不同费用项编号', 409)
        validate_baseline(conn, identifier, owner['spend_fen'], expense_id, body.amount_fen if active and included else 0)
        if expense_id:
            conn.execute('UPDATE referral_campaign_expenses SET expense_date=?,category=?,amount_fen=?,evidence=?,note=?,source_ref=?,included_in_baseline=?,active=?,revision=revision+1 WHERE id=?', (*values, source_ref, included, active, expense_id))
        else:
            expense_id = uuid.uuid4().hex
            conn.execute('INSERT INTO referral_campaign_expenses(id,campaign_id,expense_date,category,amount_fen,evidence,note,source_ref,included_in_baseline,actor_id,created_at,request_key,request_digest) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (expense_id, identifier, *values, source_ref, body.included_in_baseline, actor, int(time.time()), body.request_key, digest))
        from app.services.cost_vouchers import validate_references
        validate_references(conn, [source_ref])
        settlements.audit(conn, actor, 'campaign_expense_saved', expense_id, {'campaign_id': identifier, **body.model_dump(), 'source_ref': source_ref, 'included_in_baseline': included})
        return dict(conn.execute('SELECT * FROM referral_campaign_expenses WHERE id=?', (expense_id,)).fetchone())
