"""批量读取奖励资格，并为申请、核对和列表提供同一阻塞原因。"""

from app.services.mini_errors import fail


def reward_orders(conn, *, order_ids=None, beneficiary=None, pending_only=False, limit=None, offset=0, where='TRUE', args=()):
    clauses, values = [where], list(args)
    if order_ids is not None:
        clauses.append('r.order_id=ANY(?)')
        values.append(list(order_ids))
    if beneficiary is not None:
        clauses.append('r.beneficiary=?')
        values.append(beneficiary)
    if pending_only:
        clauses.append("r.status='pending' AND r.statement_id IS NULL AND r.request_id IS NULL")
    query = f"""SELECT r.*,o.amount_fen,o.paid_at,o.payment_channel,o.device_platform,
        o.status AS order_status,f.status AS refund_status,fp.order_id AS first_order_id,
        old.id AS blocking_order_id FROM referral_rewards r
        JOIN mini_orders o ON o.id=r.order_id
        LEFT JOIN mini_refunds f ON f.order_id=o.id
        LEFT JOIN referral_first_payments fp ON fp.buyer=r.buyer
        LEFT JOIN LATERAL (SELECT id FROM mini_orders previous
            WHERE previous.reward_buyer=r.buyer AND previous.paid_at IS NULL
            AND previous.status IN ('created','pending') AND previous.created_at<=o.paid_at
            ORDER BY previous.created_at,previous.id LIMIT 1) old ON TRUE
        WHERE {' AND '.join(clauses)} ORDER BY r.created_at DESC,r.order_id DESC"""
    if limit is not None:
        query += ' LIMIT ? OFFSET ?'
        values.extend([limit, offset])
    return [dict(row) for row in conn.execute(query, values)]


def issue(row, now):
    order_id = row['order_id']
    if row['status'] != 'pending':
        return {'code': 'inactive', 'reason': row['reason'] or '奖励已结算或失效', 'order_id': order_id}
    if row['refund_status'] in ('requested', 'processing', 'abnormal', 'success'):
        return {'code': 'refund', 'reason': '退款已完成，奖励不能结算' if row['refund_status'] == 'success' else '退款待处理，暂不能结算', 'order_id': order_id}
    if row['order_status'] != 'paid':
        return {'code': 'unpaid', 'reason': '订单未处于已付款状态', 'order_id': order_id}
    if row['first_order_id'] != order_id:
        return {'code': 'not_first', 'reason': '此订单不是该用户的首次付费订单', 'order_id': row['first_order_id'] or order_id}
    if row['blocking_order_id']:
        return {'code': 'earlier_order', 'reason': '仍有较早的未完成订单，请先查单或关闭后再结算', 'order_id': row['blocking_order_id']}
    if row['paid_at'] + row['policy']['hold_days'] * 86400 > now:
        return {'code': 'holding', 'reason': '尚未到结算等待期', 'order_id': order_id}
    return None


def require_available(row, now):
    blocked = issue(row, now)
    if blocked:
        fail(blocked['reason'], 409)
    return row


def public_reward(row, now):
    value = {key: item for key, item in row.items() if key not in ('buyer', 'first_order_id', 'blocking_order_id')}
    blocked = issue(row, now)
    state = row['status'] if row['status'] != 'pending' else 'statement' if row['statement_id'] else 'requested' if row['request_id'] else (
        'available' if blocked is None else 'holding' if blocked['code'] == 'holding' else 'exception')
    value.update(application_state=state, eligibility_issue=blocked if state in ('exception', 'holding') else None,
                 available_at=row['paid_at'] + row['policy']['hold_days'] * 86400)
    return value
