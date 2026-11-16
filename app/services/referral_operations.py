"""管理员多个来源码、明确的收款统计口径及预算预警。"""

import time
import uuid
from datetime import datetime

from app.db import db
from app.services import catalog_scope, referrals, settlements
from app.services.mini_errors import fail
from app.services.referral_growth import validate_destination
from app.services.referral_metrics import real_order
from app.services.settlement_queries import ZONE, dates, reference_sql
from app.sql_utils import escape_like


def campaign_scope(conn, actor, target=None):
    owner = catalog_scope.owner_id(conn, actor)
    if owner is not None and target is not None and target != owner:
        fail('不能操作其他管理员的推广活动', 403)
    return owner if owner is not None else target


def save_campaign(actor, body, identifier=None):
    with db(serialized='accounts') as conn:
        target = campaign_scope(conn, actor, body.admin_id) or actor
        if not conn.execute("SELECT 1 FROM users WHERE id=? AND role='admin' AND is_active=1", (target,)).fetchone():
            fail('管理员不存在或已停用', 422)
        now = int(time.time())
        if identifier:
            row = conn.execute('SELECT * FROM referral_campaigns WHERE id=?', (identifier,)).fetchone()
            if not row or row['admin_id'] != target:
                fail('推广活动不存在', 404)
            if row['revision'] != body.revision:
                fail('推广活动已变化，请刷新', 409)
            conn.execute('UPDATE referral_campaigns SET name=?,source=?,active=?,budget_fen=?,revision=revision+1,updated_at=? WHERE id=?',
                         (body.name, body.source, body.active, body.budget_fen, now, identifier))
        else:
            if conn.execute('SELECT COUNT(*) FROM referral_campaigns WHERE admin_id=?', (target,)).fetchone()[0] >= 200:
                fail('每位管理员最多 200 个活动', 422)
            identifier = uuid.uuid4().hex
            conn.execute('INSERT INTO referral_campaigns(id,admin_id,code,name,source,budget_fen,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                         (identifier, target, referrals.code('a'), body.name, body.source, body.budget_fen, now, now))
        current = conn.execute('SELECT * FROM referral_campaigns WHERE id=?', (identifier,)).fetchone()
        extra = {key: getattr(body, key) if key in body.model_fields_set else current[key]
                 for key in ('spend_fen', 'landing_kind', 'landing_id')}
        validate_destination(conn, extra['landing_kind'], extra['landing_id'])
        from app.services.referral_expenses import validate_baseline
        validate_baseline(conn, identifier, extra['spend_fen'])
        conn.execute('UPDATE referral_campaigns SET spend_fen=?,landing_kind=?,landing_id=? WHERE id=?',
                     (extra['spend_fen'], extra['landing_kind'], extra['landing_id'], identifier))
        settlements.audit(conn, actor, 'campaign_saved', identifier, {'beneficiary': 'admin:' + str(target), **body.model_dump()})
        return dict(conn.execute('SELECT * FROM referral_campaigns WHERE id=?', (identifier,)).fetchone())


def campaigns(actor, admin_id=None, q="", state="all", source="", page=1, limit=20, identifier=""):
    with db() as conn:
        target = campaign_scope(conn, actor, admin_id)
        clauses, args = ['TRUE'], []
        if target is not None:
            clauses.append('c.admin_id=?')
            args.append(target)
        if state != 'all':
            clauses.append('c.active=?')
            args.append(state == 'active')
        for value, column in ((q, 'c.name'), (source, 'c.source')):
            if value:
                clauses.append(f"{column} ILIKE ? ESCAPE '\\'")
                args.append('%' + escape_like(value) + '%')
        if identifier:
            clauses.append('c.id=?')
            args.append(identifier)
        where = ' AND '.join(clauses)
        total = conn.execute('SELECT COUNT(*) FROM referral_campaigns c WHERE ' + where, args).fetchone()[0]
        rows = conn.execute('SELECT c.*,u.username AS admin_name FROM referral_campaigns c JOIN users u ON u.id=c.admin_id '
                            f'WHERE {where} ORDER BY c.created_at DESC,c.id DESC LIMIT ? OFFSET ?',
                            [*args, limit, (page - 1) * limit]).fetchall()
        ids = [row['id'] for row in rows]
        registered = {row['id']: row['count'] for row in conn.execute("SELECT referral->>'campaign_id' AS id,COUNT(*) AS count FROM mini_users WHERE referral->>'campaign_id'=ANY(?) GROUP BY referral->>'campaign_id'", (ids,))}
        paying = {row['id']: row['count'] for row in conn.execute("SELECT referral->>'campaign_id' AS id,COUNT(DISTINCT reward_buyer) AS count FROM mini_orders o WHERE referral->>'campaign_id'=ANY(?) AND paid_at IS NOT NULL AND amount_fen>0 AND NOT (payment_channel='virtual' AND virtual_env=1) GROUP BY referral->>'campaign_id'", (ids,))}
        rewards = {row['id']: row for row in conn.execute(f"SELECT o.referral->>'campaign_id' AS id,COALESCE(SUM({reference_sql()}),0) AS used,COUNT(*) FILTER(WHERE {reference_sql()} IS NULL) AS unknown,COUNT(*) FILTER(WHERE {reference_sql()} IS NOT NULL) AS known FROM referral_rewards r JOIN mini_orders o ON o.id=r.order_id WHERE o.referral->>'campaign_id'=ANY(?) AND r.status<>'void' GROUP BY o.referral->>'campaign_id'", (ids,))}
        result = []
        for row in rows:
            item = dict(row)
            item['path'] = 'pages/home/index?ref=' + item['code']
            item['registrations'] = registered.get(item['id'], 0)
            item['paying_users'] = paying.get(item['id'], 0)
            value = rewards.get(item['id'], {'used': 0, 'unknown': 0, 'known': 0})
            item.update(reward_fen=int(value['used']), unknown=value['unknown'], reward_known=value['known'])
            item['budget_reached'] = item['budget_fen'] is not None and item['reward_fen'] >= item['budget_fen']
            result.append(item)
        return {'items': result, 'total': total, 'page': page}


def campaign_code(actor, identifier):
    with db() as conn:
        row = conn.execute('SELECT c.*,u.username AS admin_name FROM referral_campaigns c JOIN users u ON u.id=c.admin_id WHERE c.id=? AND c.active AND u.is_active=1', (identifier,)).fetchone()
        if not row:
            fail('推广活动不存在或已停用', 404)
        campaign_scope(conn, actor, row['admin_id'])
        return {**dict(row), 'path': 'pages/home/index?ref=' + row['code']}


def budget(actor, admin_id, body=None):
    with db(serialized='accounts' if body else False) as conn:
        target = campaign_scope(conn, actor, admin_id) or actor
        beneficiary = 'admin:' + str(target)
        row = conn.execute('SELECT * FROM referral_budgets WHERE beneficiary=?', (beneficiary,)).fetchone()
        if body:
            settlements.require_super(conn, actor)
            if not conn.execute("SELECT 1 FROM users WHERE id=? AND role='admin'", (target,)).fetchone():
                fail('管理员不存在', 404)
            if (row['revision'] if row else 0) != body.revision:
                fail('预算已变化，请刷新', 409)
            conn.execute('INSERT INTO referral_budgets(beneficiary,budget_fen,updated_at) VALUES(?,?,?) ON CONFLICT(beneficiary) DO UPDATE SET budget_fen=excluded.budget_fen,revision=referral_budgets.revision+1,updated_at=excluded.updated_at',
                         (beneficiary, body.budget_fen, int(time.time())))
            settlements.audit(conn, actor, 'budget_saved', beneficiary, body.model_dump())
            row = conn.execute('SELECT * FROM referral_budgets WHERE beneficiary=?', (beneficiary,)).fetchone()
        start = int(datetime.now(ZONE).replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
        stats = conn.execute(f'SELECT COALESCE(SUM({reference_sql()}),0) AS used,COUNT(*) FILTER(WHERE {reference_sql()} IS NULL) AS unknown,COUNT(*) FILTER(WHERE {reference_sql()} IS NOT NULL) AS known '
                             "FROM referral_rewards r JOIN mini_orders o ON o.id=r.order_id WHERE r.beneficiary=? AND r.status<>'void' AND o.paid_at>=?", (beneficiary, start)).fetchone()
        value = dict(row) if row else {'revision': 0, 'budget_fen': None, 'beneficiary': beneficiary}
        return {**value, 'used_fen': int(stats['used']), 'unknown': stats['unknown'], 'reward_known': stats['known'], 'reached': value['budget_fen'] is not None and stats['used'] >= value['budget_fen']}


def analytics(actor, admin_id=None, start_date='', end_date='', q='', date_basis='created', campaign_id=''):
    a, b = dates(start_date, end_date)
    with db() as conn:
        def scope(alias, stamp):
            where, args = referrals.scope(conn, actor, admin_id, alias)
            clauses = [where, real_order(alias)] if alias == 'o' else [where]
            if campaign_id:
                clauses.append(f"{alias}.referral->>'campaign_id'=?")
                args.append(campaign_id)
            for value, sign in ((a, '>='), (b, '<')):
                if value is not None:
                    clauses.append(f'{stamp} {sign} ?')
                    args.append(value)
            if q:
                word = '%' + escape_like(q.lower()) + '%'
                if alias == 'u':
                    clauses.append("(LOWER(u.username) LIKE ? ESCAPE '\\' OR LOWER(u.nickname) LIKE ? ESCAPE '\\')")
                    args.extend([word] * 2)
                else:
                    clauses.append("(LOWER(o.id) LIKE ? ESCAPE '\\' OR EXISTS(SELECT 1 FROM mini_users mu WHERE mu.id=o.user_id AND (LOWER(mu.username) LIKE ? ESCAPE '\\' OR LOWER(mu.nickname) LIKE ? ESCAPE '\\')))")
                    args.extend([word] * 3)
            return ' AND '.join(clauses), args
        clause, args = scope('u', 'u.created_at')
        registrations = conn.execute('SELECT COUNT(*) FROM mini_users u WHERE ' + clause, args).fetchone()[0]
        clause, args = scope('o', 'o.paid_at' if date_basis == 'paid' else 'o.created_at')
        stats = dict(conn.execute("SELECT COUNT(*) AS orders,COUNT(DISTINCT o.reward_buyer) FILTER(WHERE o.paid_at IS NOT NULL) AS paying_users,"
                                 "COUNT(*) FILTER(WHERE fp.order_id IS NOT NULL) AS first_paying_users,"
                                 "COALESCE(SUM(o.amount_fen) FILTER(WHERE o.paid_at IS NOT NULL),0) AS paid_fen,"
                                 "COALESCE(SUM(o.amount_fen) FILTER(WHERE fp.order_id IS NOT NULL),0) AS first_paid_fen,"
                                 "COALESCE(SUM(o.amount_fen) FILTER(WHERE o.paid_at IS NOT NULL AND fp.order_id IS NULL),0) AS renewal_paid_fen "
                                 f'FROM mini_orders o LEFT JOIN referral_first_payments fp ON fp.order_id=o.id WHERE {clause}', args).fetchone())
        rewards = conn.execute(f'SELECT COALESCE(SUM({reference_sql()}),0) AS value,COUNT(*) FILTER(WHERE {reference_sql()} IS NULL) AS unknown,COUNT(*) FILTER(WHERE {reference_sql()} IS NOT NULL) AS known '
                               f"FROM mini_orders o JOIN referral_rewards r ON r.order_id=o.id WHERE {clause} AND r.status<>'void'", args).fetchone()
        refund_where, refund_args = scope('o', 'f.completed_at' if date_basis == 'paid' else 'o.created_at')
        refunded = conn.execute(f"SELECT COALESCE(SUM(o.amount_fen),0) FROM mini_orders o JOIN mini_refunds f ON f.order_id=o.id WHERE {refund_where} AND f.status='success'", refund_args).fetchone()[0]
    return {**{key: int(value) for key, value in stats.items()}, 'registrations': registrations, 'refunded_fen': int(refunded),
            'net_fen': int(stats['paid_fen'] - refunded), 'reward_reference_fen': int(rewards['value']), 'reward_unknown': rewards['unknown'], 'reward_known': rewards['known'],
            'after_reward_reference_fen': int(stats['paid_fen'] - refunded - rewards['value']), 'date_basis': date_basis}


def performance(actor, identifier):
    result = campaigns(actor, identifier=identifier)
    if not result['items']:
        fail('推广活动不存在', 404)
    campaign = result['items'][0]
    stats = analytics(actor, campaign_id=identifier, date_basis='paid')
    from app.services.referral_expenses import spend_totals
    with db() as conn:
        cost = spend_totals(conn, campaign)
        spend = cost['total_fen']
    remainder = None if spend is None or stats['reward_unknown'] else stats['after_reward_reference_fen'] - spend
    with db() as conn:
        trend = [dict(row) for row in conn.execute(f"""SELECT TO_CHAR(TO_TIMESTAMP(o.paid_at) AT TIME ZONE 'Asia/Shanghai','YYYY-MM-DD') AS day,
            SUM(o.amount_fen) AS paid_fen,COUNT(DISTINCT o.reward_buyer) AS paying_users
            FROM mini_orders o WHERE o.referral->>'campaign_id'=? AND o.paid_at>=? AND {real_order()}
            GROUP BY day ORDER BY day""", (identifier, int(time.time()) - 30 * 86400))]
    return {'campaign': campaign, 'income': stats, 'spend_fen': spend, 'known_spend_fen': cost['known_fen'], 'remainder_fen': remainder,
            'return_bps': remainder * 10000 // spend if remainder is not None and spend else None, 'trend': trend}
