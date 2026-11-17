"""同一自然日范围的活动对比，收入和投入按各自发生日归集。"""

from datetime import datetime

from app.db import db
from app.services.mini_errors import fail
from app.services.referral_metrics import real_order
from app.services.referral_operations import campaign_scope
from app.services.settlement_queries import ZONE, dates


def comparison(actor, start_date, end_date, admin_id=None, campaign_id='', sort='paying_users', direction='desc', page=1):
    start, end = dates(start_date, end_date)
    if start is None or end is None or not 0 < end - start <= 366 * 86400:
        fail('请选择完整日期范围，最长 366 天', 422)
    if end_date > datetime.now(ZONE).strftime('%Y-%m-%d'):
        fail('截止日期不能晚于今天', 422)
    previous_start = start - (end - start)
    previous_dates = [datetime.fromtimestamp(value, ZONE).strftime('%Y-%m-%d') for value in (previous_start, start - 1)]
    with db(read_only_snapshot=True) as conn:
        owner = campaign_scope(conn, actor, admin_id)
        where, args = 'TRUE', []
        if owner is not None:
            where += ' AND c.admin_id=?'
            args.append(owner)
        if campaign_id:
            where += ' AND c.id=?'
            args.append(campaign_id)
        count = conn.execute('SELECT COUNT(*) FROM referral_campaigns c WHERE ' + where, args).fetchone()[0]
        page = min(page, max(1, (count + 19) // 20))
        query = f"""WITH scoped AS (SELECT c.*,u.username AS admin_name FROM referral_campaigns c LEFT JOIN users u ON u.id=c.admin_id WHERE {where}),
        periods AS (SELECT 'current' AS period,?::bigint AS a,?::bigint AS b,?::text AS day_a,?::text AS day_b
            UNION ALL SELECT 'previous',?::bigint,?::bigint,?::text,?::text),
        paid AS (SELECT p.period,o.referral->>'campaign_id' AS campaign_id,COUNT(*) AS orders,
            COUNT(DISTINCT COALESCE(NULLIF(o.reward_buyer,''),o.user_id,o.id)) AS paying_users,SUM(o.amount_fen) AS paid_fen,
            COUNT(*) FILTER(WHERE EXISTS(SELECT 1 FROM mini_refunds f WHERE f.order_id=o.id AND f.status='success')) AS refunded_orders
            FROM mini_orders o JOIN periods p ON o.paid_at>=p.a AND o.paid_at<p.b
            JOIN scoped c ON c.id=o.referral->>'campaign_id' WHERE {real_order()} AND o.amount_fen>0 GROUP BY p.period,campaign_id),
        refunded AS (SELECT p.period,o.referral->>'campaign_id' AS campaign_id,SUM(o.amount_fen) AS refunded_fen
            FROM mini_refunds f JOIN mini_orders o ON o.id=f.order_id JOIN periods p ON f.completed_at>=p.a AND f.completed_at<p.b
            JOIN scoped c ON c.id=o.referral->>'campaign_id' WHERE f.status='success' AND {real_order()} GROUP BY p.period,campaign_id),
        expenses AS (SELECT p.period,e.campaign_id,SUM(e.amount_fen) AS spend_fen FROM referral_campaign_expenses e
            JOIN periods p ON e.expense_date>=p.day_a AND e.expense_date<=p.day_b JOIN scoped c ON c.id=e.campaign_id
            WHERE e.active GROUP BY p.period,e.campaign_id),
        baseline AS (SELECT e.campaign_id,SUM(e.amount_fen) AS included_fen FROM referral_campaign_expenses e
            JOIN scoped c ON c.id=e.campaign_id WHERE e.active AND e.included_in_baseline GROUP BY e.campaign_id),
        measured AS (SELECT c.id,c.name,c.source,c.admin_id,c.admin_name,p.period,
            c.spend_fen IS NOT NULL AND c.spend_fen<=COALESCE(baseline.included_fen,0) AS cost_complete,
            COALESCE(expenses.spend_fen,0)::bigint AS spend_fen,COALESCE(paid.paying_users,0) AS paying_users,
            COALESCE(paid.paid_fen,0)::bigint AS paid_fen,COALESCE(refunded.refunded_fen,0)::bigint AS refunded_fen,
            (COALESCE(paid.paid_fen,0)-COALESCE(refunded.refunded_fen,0))::bigint AS net_fen,
            CASE WHEN paid.orders>0 THEN paid.refunded_orders*10000/paid.orders END AS refund_rate_bps,
            CASE WHEN paid.paying_users>0 AND c.spend_fen IS NOT NULL AND c.spend_fen<=COALESCE(baseline.included_fen,0)
                THEN FLOOR(COALESCE(expenses.spend_fen,0)/paid.paying_users)::bigint END AS cost_per_payer_fen
            FROM scoped c CROSS JOIN periods p LEFT JOIN paid ON paid.campaign_id=c.id AND paid.period=p.period
            LEFT JOIN refunded ON refunded.campaign_id=c.id AND refunded.period=p.period
            LEFT JOIN expenses ON expenses.campaign_id=c.id AND expenses.period=p.period LEFT JOIN baseline ON baseline.campaign_id=c.id)
        SELECT current.*,to_jsonb(previous) AS previous FROM measured current JOIN measured previous ON previous.id=current.id AND previous.period='previous'
        WHERE current.period='current'"""
        columns = {'paying_users': 'paying_users', 'spend': 'spend_fen', 'cost_per_payer': 'cost_per_payer_fen', 'refund_rate': 'refund_rate_bps', 'net': 'net_fen'}
        if sort not in columns or direction not in ('asc', 'desc'):
            fail('排序条件无效', 422)
        params = [*args, start, end, start_date, end_date, previous_start, start, *previous_dates, (page - 1) * 20]
        rows = conn.execute(query + f' ORDER BY current.{columns[sort]} {direction} NULLS LAST,current.id LIMIT 20 OFFSET ?', params)
        return {'items': [dict(row) for row in rows], 'total': count, 'page': page,
                'start_date': start_date, 'end_date': end_date, 'previous_start': previous_dates[0], 'previous_end': previous_dates[1],
                'as_of': int(datetime.now(ZONE).timestamp())}
