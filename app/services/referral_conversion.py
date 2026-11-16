"""按注册批次统计获客转化，注册、下单、付费共用同一个用户集合。"""

import time

from app.db import db
from app.services import referrals
from app.services.referral_metrics import cohort_orders


def counts(row):
    registered, ordered, paid = (int(row[key]) for key in ('registrations', 'ordered_users', 'paying_users'))
    return {**row, 'registrations': registered, 'ordered_users': ordered, 'paying_users': paid,
            'not_ordered_users': registered - ordered, 'unpaid_users': ordered - paid,
            'order_rate_bps': ordered * 10000 // registered if registered else None,
            'pay_rate_bps': paid * 10000 // registered if registered else None,
            'order_pay_rate_bps': paid * 10000 // ordered if ordered else None}


def conversion(actor, admin_id=None, start_date='', end_date='', campaign_id='', page=1):
    stamp = int(time.time())
    with db() as conn:
        where, args = referrals.scope(conn, actor, admin_id)
        clauses = [where, 'u.created_at <= t.at']
        referrals.date_filter(clauses, args, 'u', start_date, end_date)
        if campaign_id:
            clauses.append("u.referral->>'campaign_id'=?")
            args.append(campaign_id)
        # 只统计同一注册归属下的真实订单，补录来源之前的其他归属订单不计入。
        order_scope = cohort_orders()
        # 一条语句取得全量汇总与分页，避免翻页改变分母或并发注册造成汇总不一致。
        query = f"""WITH observed AS (SELECT ?::bigint AS at), cohort AS MATERIALIZED (
            SELECT u.id, COALESCE(u.referral->>'admin_id','') AS admin_id,
                COALESCE(u.referral->>'admin_name','') AS admin_name,
                COALESCE(u.referral->>'campaign_id','') AS campaign_id,
                CASE WHEN u.referral->>'campaign_id' IS NOT NULL THEN 'campaign:' || (u.referral->>'campaign_id')
                     WHEN u.referral->>'admin_id' IS NOT NULL THEN 'admin:' || (u.referral->>'admin_id')
                     ELSE 'source:' || COALESCE(u.referral->>'source','legacy') END AS key,
                CASE WHEN u.referral->>'campaign_id' IS NOT NULL THEN COALESCE(c.name,u.referral->>'campaign_name','未命名活动')
                     WHEN u.referral->>'admin_id' IS NOT NULL THEN '未分活动'
                     WHEN u.referral->>'source'='natural' THEN '自然注册'
                     WHEN u.referral->>'source'='user' THEN '用户邀请（无归属管理员）'
                     ELSE '历史来源未知' END AS name,
                COALESCE(c.source,u.referral->>'campaign_source','') AS source,
                EXISTS(SELECT 1 FROM mini_orders o WHERE {order_scope}) AS ordered,
                EXISTS(SELECT 1 FROM mini_orders o WHERE {order_scope}
                    AND o.amount_fen>0 AND o.paid_at>=u.created_at AND o.paid_at<=t.at) AS paid
            FROM mini_users u CROSS JOIN observed t
            LEFT JOIN referral_campaigns c ON c.id=u.referral->>'campaign_id'
            WHERE {' AND '.join(clauses)}
        ), grouped AS (
            SELECT key, MAX(admin_id) AS admin_id, MAX(admin_name) AS admin_name,
                MAX(campaign_id) AS campaign_id, MAX(name) AS name, MAX(source) AS source,
                COUNT(*) AS registrations, COUNT(*) FILTER(WHERE ordered) AS ordered_users,
                COUNT(*) FILTER(WHERE paid) AS paying_users FROM cohort GROUP BY key
        ) SELECT
            (SELECT row_to_json(s) FROM (SELECT COUNT(*) AS registrations,
                COUNT(*) FILTER(WHERE ordered) AS ordered_users, COUNT(*) FILTER(WHERE paid) AS paying_users FROM cohort) s) AS summary,
            (SELECT COALESCE(jsonb_agg(g),'[]'::jsonb) FROM
                (SELECT * FROM grouped ORDER BY paying_users DESC,registrations DESC,key LIMIT 20 OFFSET ?) g) AS items,
            (SELECT COUNT(*) FROM grouped) AS total"""
        row = conn.execute(query, [stamp, *args, (page - 1) * 20]).fetchone()
    return {'summary': counts(row['summary']), 'items': [counts(item) for item in row['items']],
            'total': row['total'], 'page': page, 'as_of': stamp}
