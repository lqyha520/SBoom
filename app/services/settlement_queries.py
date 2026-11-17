"""结算查询、工作量汇总与范围过滤共用一个权限边界。"""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import db
from app.models.settlements import SettlementFilters
from app.services import settlement_access
from app.services.mini_errors import fail
from app.sql_utils import escape_like

ZONE = timezone(timedelta(hours=8))


def dates(start, end):
    try:
        a = datetime.strptime(start, '%Y-%m-%d').replace(tzinfo=ZONE) if start else None
        b = datetime.strptime(end, '%Y-%m-%d').replace(tzinfo=ZONE) if end else None
        if a and b and a > b:
            raise ValueError
        return int(a.timestamp()) if a else None, int((b + timedelta(days=1)).timestamp()) if b else None
    except (ValueError, OverflowError):
        fail('日期范围无效', 422)


def channel_sql(alias='o'):
    return f"CASE WHEN {alias}.payment_channel='wechat' THEN 'wechat' WHEN {alias}.payment_channel='virtual' AND {alias}.device_platform='ios' THEN 'virtual_ios' WHEN {alias}.payment_channel='virtual' AND {alias}.device_platform IN ('android','harmony','harmonyos','ohos','windows') THEN 'virtual_android' ELSE 'unknown' END"


def eligibility():
    return """r.status='pending' AND r.statement_id IS NULL AND r.request_id IS NULL AND EXISTS (
        SELECT 1 FROM mini_orders eo JOIN referral_first_payments ep ON ep.order_id=eo.id AND ep.buyer=r.buyer
        WHERE eo.id=r.order_id AND eo.status='paid'
        AND NOT EXISTS(SELECT 1 FROM mini_refunds ef WHERE ef.order_id=eo.id AND ef.status IN ('requested','processing','abnormal','success'))
        AND NOT EXISTS(SELECT 1 FROM mini_orders old WHERE old.reward_buyer=r.buyer AND old.paid_at IS NULL
            AND old.status IN ('created','pending') AND old.created_at<=eo.paid_at))"""


def reward_state(state):
    maturity = "(SELECT paid_at FROM mini_orders WHERE id=r.order_id)+COALESCE((r.policy->>'hold_days')::bigint,0)*86400"
    if state in ('available', 'holding'):
        return f"({eligibility()}) AND {maturity} {'<=' if state == 'available' else '>'} EXTRACT(EPOCH FROM now())"
    if state == 'exception':
        return f"r.status='pending' AND r.statement_id IS NULL AND r.request_id IS NULL AND NOT ({eligibility()})"
    return None


def application_state():
    # 列表选择与汇总筛选复用服务端资格判断，较早未完成订单同样阻止申请。
    return f"""CASE WHEN r.status<>'pending' THEN r.status
        WHEN r.statement_id IS NOT NULL THEN 'statement'
        WHEN r.request_id IS NOT NULL THEN 'requested'
        WHEN {reward_state('available')} THEN 'available'
        WHEN {reward_state('holding')} THEN 'holding' ELSE 'exception' END"""


def timing_sql(kind, timing):
    active = "r.status IN ('pending','reviewing','approved')" if kind == 'requests' else "r.status IN ('draft','approved')"
    if timing == 'stalled':
        return f"{active} AND r.updated_at < EXTRACT(EPOCH FROM now())-3*86400"
    if timing == 'review_overdue':
        return ("r.status IN ('pending','reviewing') AND (r.snapshot->'service_terms'->>'review_days')::bigint > 0 "
                "AND r.created_at+(r.snapshot->'service_terms'->>'review_days')::bigint*86400 < EXTRACT(EPOCH FROM now())") if kind == 'requests' else 'FALSE'
    approved = "(SELECT approved_at FROM referral_statements s WHERE s.id=r.statement_id)" if kind == 'requests' else 'r.approved_at'
    return ("r.status='approved' AND (r.snapshot->'service_terms'->>'payout_days')::bigint > 0 "
            f"AND {approved}+(r.snapshot->'service_terms'->>'payout_days')::bigint*86400 < EXTRACT(EPOCH FROM now())")


def where(conn, actor, kind, filters=None):
    return _where(kind, filters or SettlementFilters(), settlement_access.owner_id(conn, actor))


def _where(kind, f, owner):
    """内部复用已在当前事务中核验的权限范围。"""
    if owner is not None and f.admin_id is not None and owner != f.admin_id:
        fail('不能查看其他管理员的结算', 403)
    target = owner if owner is not None else f.admin_id
    clauses, args = [], []
    if target is not None:
        clauses.append('r.beneficiary=?')
        args.append('admin:' + str(target))
    a, b = dates(f.start_date, f.end_date)
    stamp_column = 'r.created_at'
    if f.date_basis == 'paid':
        stamp_column = "(r.payout->>'transferred_at')::bigint" if kind == 'statements' else (
            "(SELECT (s.payout->>'transferred_at')::bigint FROM referral_statements s WHERE s.id=r.statement_id AND s.status='paid')")
        clauses.append(stamp_column + ' IS NOT NULL')
        if kind == 'statements':
            clauses.append("r.status='paid'")
    for stamp, operator in ((a, '>='), (b, '<')):
        if stamp is not None:
            clauses.append(stamp_column + ' ' + operator + ' ?')
            args.append(stamp)
    if f.timing:
        clauses.append(timing_sql(kind, f.timing) if kind in ('requests', 'statements') else 'FALSE')
    if f.status:
        special = reward_state(f.status) if kind == 'rewards' else None
        if special:
            clauses.append(special)
        elif kind == 'adjustments':
            if f.status not in ('open', 'settled'):
                fail('调整状态无效', 422)
            clauses.append('r.statement_id IS ' + ('NULL' if f.status == 'open' else 'NOT NULL'))
        else:
            allowed = {'rewards': ('pending', 'void', 'paid'), 'statements': ('draft', 'approved', 'paid', 'void'),
                       'requests': ('pending', 'reviewing', 'approved', 'paid', 'rejected', 'cancelled', 'invalidated')}[kind]
            if f.status not in allowed:
                fail('筛选状态无效', 422)
            clauses.append('r.status=?')
            args.append(f.status)
    if f.q:
        word = '%' + escape_like(f.q.lower()) + '%'
        column = 'r.order_id' if kind == 'rewards' else 'r.id::text'
        parts = [f"LOWER({column}) LIKE ? ESCAPE '\\'", "LOWER(r.beneficiary_name) LIKE ? ESCAPE '\\'"]
        args.extend([word, word])
        if kind in ('requests', 'statements'):
            parts.append("EXISTS(SELECT 1 FROM jsonb_array_elements(r.snapshot->'items') j WHERE LOWER(j->>'order_id') LIKE ? ESCAPE '\\')")
            args.append(word)
        clauses.append('(' + ' OR '.join(parts) + ')')
    if f.channel:
        if kind == 'rewards':
            clauses.append(f'EXISTS(SELECT 1 FROM mini_orders o WHERE o.id=r.order_id AND {channel_sql()}=?)')
        elif kind in ('requests', 'statements'):
            clauses.append(f"EXISTS(SELECT 1 FROM jsonb_array_elements(r.snapshot->'items') j JOIN mini_orders o ON o.id=j->>'order_id' WHERE {channel_sql()}=?)")
        else:
            clauses.append('FALSE')
        args.append(f.channel) if kind != 'adjustments' else None
    return ' AND '.join(clauses) or '1=1', args


def reference_sql():
    # 与整数分计算一致；未知渠道费不按零显示成确定金额。
    channel = "((o.amount_fen*(r.policy->>'channel_rate_bps')::bigint+5000)/10000)"
    shared = f"""COALESCE((SELECT SUM(CASE WHEN f->>'mode'='percent' THEN
        (CASE WHEN f->>'basis'='order_gross' THEN o.amount_fen ELSE GREATEST(0,o.amount_fen-{channel}) END)
        *(f->>'rate_bps')::bigint/10000 ELSE COALESCE((f->>'amount_fen')::bigint,0) END)
        FROM jsonb_array_elements(COALESCE(r.policy->'shared_fees','[]'::jsonb)) f),0)"""
    result = f"FLOOR(GREATEST(0,o.amount_fen-{channel}-{shared})*(r.policy->>'rate_bps')::bigint/10000)"
    return f"COALESCE(r.commission_fen,CASE WHEN r.policy->>'channel_rate_bps' IS NOT NULL THEN LEAST({result},COALESCE((r.policy->>'max_reward_fen')::bigint,9223372036854775807)) END)"


def summary(actor, filters=None):
    f = (filters or SettlementFilters()).model_copy(update={'status': '', 'timing': ''})
    result: dict[str, Any] = {state: {'count': 0, 'amount_fen': 0, 'unknown': 0}
                              for state in ('available', 'holding', 'exception', 'pending', 'reviewing')}
    result.update({state: {'count': 0, 'amount_fen': 0} for state in ('approved', 'paid')})
    with db(read_only_snapshot=True) as conn:
        owner = settlement_access.owner_id(conn, actor)
        clause, args = _where('rewards', f, owner)
        maturity = "o.paid_at+COALESCE((r.policy->>'hold_days')::bigint,0)*86400"
        # 每条奖励的资格和参考金额只计算一次，再按状态分组；未知金额仍单独计数。
        rows = conn.execute(f"""WITH rewards AS MATERIALIZED (
            SELECT CASE WHEN NOT ({eligibility()}) THEN 'exception'
                WHEN {maturity} <= EXTRACT(EPOCH FROM now()) THEN 'available'
                WHEN {maturity} > EXTRACT(EPOCH FROM now()) THEN 'holding' END AS state,
                {reference_sql()} AS amount_fen
            FROM referral_rewards r JOIN mini_orders o ON o.id=r.order_id
            WHERE ({clause}) AND r.status='pending' AND r.statement_id IS NULL AND r.request_id IS NULL)
            SELECT state,COUNT(*) AS count,COALESCE(SUM(amount_fen),0) AS amount_fen,
                COUNT(*) FILTER(WHERE amount_fen IS NULL) AS unknown FROM rewards GROUP BY state""", args)
        for row in rows:
            if row['state'] is not None:
                result[row['state']] = {key: int(row[key]) for key in ('count', 'amount_fen', 'unknown')}

        clause, args = _where('statements', f, owner)
        for row in conn.execute(f"SELECT r.status,COUNT(*) AS count,COALESCE(SUM(GREATEST(0,r.net_fen)),0) AS amount_fen "
                                f"FROM referral_statements r WHERE ({clause}) AND r.status IN ('approved','paid') GROUP BY r.status", args):
            result[row['status']] = {key: int(row[key]) for key in ('count', 'amount_fen')}

        clause, args = _where('requests', f, owner)
        timings = ('stalled', 'review_overdue', 'payout_overdue')
        timing_columns = ','.join(f'{timing_sql("requests", name)} AS {name}' for name in timings)
        unknown = """EXISTS(SELECT 1 FROM jsonb_array_elements(r.snapshot->'items') item
            WHERE (item->'costs' IS NULL OR item->'costs'='null'::jsonb)
            AND item->>'reference_channel_rate_bps' IS NULL)"""
        aggregates: list[str] = []
        for state in ('pending', 'reviewing'):
            condition = f"status='{state}'"
            aggregates.extend((f'COUNT(*) FILTER(WHERE {condition}) AS {state}_count',
                               f'COALESCE(SUM(amount_fen) FILTER(WHERE {condition}),0) AS {state}_amount_fen',
                               f'COUNT(*) FILTER(WHERE {condition} AND statement_id IS NULL AND unknown) AS {state}_unknown'))
        aggregates.extend(f'COUNT(*) FILTER(WHERE {name}) AS {name}' for name in timings)
        # 一次读取申请，同时汇总金额和处理时效；沿用列表的日期、渠道和权限条件。
        row = conn.execute(f"""WITH requests AS MATERIALIZED (
            SELECT r.status,s.id AS statement_id,s.status AS statement_status,s.net_fen,
                s.gross_fen+s.adjustment_fen AS draft_fen,
                CASE WHEN r.status IN ('pending','reviewing') THEN {unknown} ELSE FALSE END AS unknown,
                CASE WHEN r.status IN ('pending','reviewing') THEN r.snapshot->>'reference_after_adjustment_fen' END AS reference_fen,
                {timing_columns}
            FROM referral_settlement_requests r LEFT JOIN referral_statements s ON s.id=r.statement_id WHERE {clause}
        ), amounts AS (
            SELECT *,CASE WHEN net_fen IS NOT NULL THEN GREATEST(0,net_fen)
                WHEN statement_status='draft' THEN GREATEST(0,draft_fen)
                WHEN unknown THEN NULL ELSE reference_fen::bigint END AS amount_fen FROM requests
        ) SELECT {','.join(aggregates)} FROM amounts""", args).fetchone()
        for state in ('pending', 'reviewing'):
            result[state] = {key: int(row[f'{state}_{key}']) for key in ('count', 'amount_fen', 'unknown')}
        for timing in timings:
            result[timing] = int(row[timing])
        result['overdue'] = result['review_overdue'] + result['payout_overdue']
    return result
