"""完成观察窗口的注册用户质量；未满窗口用户单独列出。"""

import time

from app.db import db
from app.services import referrals
from app.services.referral_metrics import cohort_orders


def quality(actor, admin_id=None, campaign_id='', start_date='', end_date='', page=1):
    stamp = int(time.time())
    with db(read_only_snapshot=True) as conn:
        where, args = referrals.scope(conn, actor, admin_id)
        clauses = [where, 'u.created_at<=?']
        args.append(stamp)
        referrals.date_filter(clauses, args, 'u', start_date, end_date)
        if campaign_id:
            clauses.append("u.referral->>'campaign_id'=?")
            args.append(campaign_id)
        scope = ' AND '.join(clauses)
        query = f"""WITH cohort AS (
            SELECT u.*, COALESCE(NULLIF(u.referral->>'campaign_id',''),'admin:' || COALESCE(u.referral->>'admin_id','0')) AS group_key,
                COALESCE(c.name,u.referral->>'campaign_name','未分活动') AS campaign_name
            FROM mini_users u LEFT JOIN referral_campaigns c ON c.id=u.referral->>'campaign_id' WHERE {scope}
        ), measured AS (
            SELECT u.group_key,u.campaign_name,u.referral->>'admin_name' AS admin_name,w.days,
                u.created_at+w.days*86400<=? AS mature,
                p.payments,p.collected_fen,p.refunded_fen
            FROM cohort u CROSS JOIN (VALUES(30),(60),(90)) AS w(days)
            CROSS JOIN LATERAL (
                SELECT COUNT(*) AS payments,COALESCE(SUM(o.amount_fen),0) AS collected_fen,
                    COALESCE(SUM(CASE WHEN f.status='success' AND f.completed_at<=u.created_at+w.days*86400 THEN o.amount_fen ELSE 0 END),0) AS refunded_fen
                FROM mini_orders o LEFT JOIN mini_refunds f ON f.order_id=o.id
                WHERE {cohort_orders('u.created_at+w.days*86400')}
                    AND o.paid_at>=u.created_at AND o.paid_at<=u.created_at+w.days*86400 AND o.amount_fen>0
            ) p
        ), grouped AS (
            SELECT group_key,MAX(campaign_name) AS campaign_name,MAX(admin_name) AS admin_name,days,
                COUNT(*) FILTER(WHERE mature) AS observed_users,COUNT(*) FILTER(WHERE NOT mature) AS waiting_users,
                COUNT(*) FILTER(WHERE mature AND payments>0) AS paying_users,
                COUNT(*) FILTER(WHERE mature AND payments>1) AS renewing_users,
                COUNT(*) FILTER(WHERE mature AND refunded_fen>0) AS refunded_users,
                COALESCE(SUM(collected_fen) FILTER(WHERE mature),0) AS collected_fen,
                COALESCE(SUM(refunded_fen) FILTER(WHERE mature),0) AS refunded_fen
            FROM measured GROUP BY group_key,days
        ), keys AS (SELECT DISTINCT group_key FROM grouped ORDER BY group_key LIMIT 20 OFFSET ?)
        SELECT (SELECT COUNT(DISTINCT group_key) FROM grouped) AS total,
            COALESCE((SELECT jsonb_agg(g ORDER BY g.group_key,g.days) FROM grouped g JOIN keys USING(group_key)),'[]'::jsonb) AS items"""
        result = conn.execute(query, [*args, stamp, (page - 1) * 20]).fetchone()
        items = result['items']
        for item in items:
            observed = item['observed_users']
            item.update(net_fen=item['collected_fen'] - item['refunded_fen'],
                        pay_rate_bps=item['paying_users'] * 10000 // observed if observed else None,
                        renewal_rate_bps=item['renewing_users'] * 10000 // item['paying_users'] if item['paying_users'] else None,
                        value_per_user_fen=(item['collected_fen'] - item['refunded_fen']) // observed if observed else None)
        return {'as_of': stamp, 'items': items, 'total': result['total']}
