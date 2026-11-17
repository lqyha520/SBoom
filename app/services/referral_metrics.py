"""推广统计共享口径：真实订单与同一注册归属的用户进度。"""


def real_order(alias='o'):
    return f"NOT ({alias}.payment_channel='virtual' AND {alias}.virtual_env=1)"


def cohort_orders(observed='t.at'):
    return f"""o.user_id=u.id AND o.created_at>=u.created_at AND o.created_at<={observed}
        AND {real_order()}
        AND o.referral->>'admin_id' IS NOT DISTINCT FROM u.referral->>'admin_id'
        AND o.referral->>'campaign_id' IS NOT DISTINCT FROM u.referral->>'campaign_id'"""


def progress_join():
    return f"""LEFT JOIN LATERAL (
        SELECT COUNT(*)>0 AS ordered,
            COALESCE(BOOL_OR(o.amount_fen>0 AND o.paid_at>=u.created_at AND o.paid_at<=t.at),FALSE) AS paid,
            MAX(o.created_at) AS last_order_at,
            MAX(o.paid_at) FILTER(WHERE o.amount_fen>0 AND o.paid_at>=u.created_at AND o.paid_at<=t.at) AS last_paid_at
        FROM mini_orders o WHERE {cohort_orders()}
    ) progress ON TRUE"""


STAGES = {'all': 'TRUE', 'ordered': 'progress.ordered', 'paid': 'progress.paid',
          'not_ordered': 'NOT progress.ordered', 'unpaid': 'progress.ordered AND NOT progress.paid'}
