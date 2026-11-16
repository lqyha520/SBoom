"""方案一：共同费用先扣、首付按比例奖励，核对后生成结算快照。"""

import csv
import hashlib
import io
import json
import time
import unicodedata
import uuid

from fastapi import HTTPException

from app.db import db
from app.models.settlements import SharedFee
from app.services import catalog_scope, settlement_access
from app.services.mini_errors import fail
from app.services.settlement_channels import channel_key, channel_rate, channel_totals
from app.services.settlement_eligibility import public_reward, require_available, reward_orders
from app.services.settlement_reference import reference_snapshot

CHANNEL_NAMES = {'支付渠道费', '支付渠道手续费', '渠道手续费', '微信手续费', '微信服务费', '支付手续费'}
TAX_NAMES = {'个税', '个人所得税', '代扣个税', '代扣个人所得税'}


def cost_reference(value):
    """关联编号忽略全半角、大小写和空白；同一凭据的不同费用项使用不同后缀。"""
    return ''.join(unicodedata.normalize('NFKC', value or '').split()).casefold()


def fee_references(fees):
    refs = [cost_reference(fee.get('source_ref')) for fee in fees if cost_reference(fee.get('source_ref'))]
    if len(refs) != len(set(refs)):
        fail('同一凭据费用项不能重复扣除，请核对关联编号', 422)
    return set(refs)


def fee_names(fees):
    fee_references(fees)
    names = [''.join(fee['name'].split()).casefold() for fee in fees]
    if len(names) != len(set(names)):
        fail('同一费用不能重复列入', 422)
    return set(names)


def audit(conn, actor, kind, target, value):
    conn.execute('INSERT INTO referral_settlement_audit(actor_id,kind,target,value,created_at) VALUES(?,?,?,?::jsonb,?)',
                 (actor, kind, target, json.dumps(value), int(time.time())))
    if kind in ('approve', 'record_payout', 'void_statement', 'adjustment'):
        from app.services.settlement_ledger import record
        record(conn, kind, target, value)


def require_super(conn, actor):
    if catalog_scope.owner_id(conn, actor) is not None:
        fail('仅超级管理员可以配置和核对结算', 403)


def policy(conn):
    row = conn.execute('SELECT * FROM referral_policy WHERE id=1').fetchone()
    return {'channel_rate_bps': None, **row['value'], 'revision': row['revision']}


def get_policy(actor):
    with db() as conn:
        require_super(conn, actor)
        return policy(conn)


def service_terms(value):
    return {key: value.get(key) for key in ('review_days', 'payout_days')}


def public_rules(actor):
    with db() as conn:
        catalog_scope.owner_id(conn, actor)
        value = policy(conn)
        return {key: value.get(key) for key in ('revision', 'enabled', 'beneficiary', 'rate_bps', 'hold_days',
                'max_reward_fen', 'channel_rate_bps', 'channel_rates', 'shared_fees', 'review_days', 'payout_days')}


def save_policy(actor, body):
    with db(serialized='accounts') as conn:
        require_super(conn, actor)
        previous = policy(conn)
        if previous['revision'] != body.revision:
            fail('奖励规则已修改，请刷新', 409)
        value = body.model_dump(exclude={'revision', 'reason'})
        value['shared_fees'] = [fee.model_dump(exclude_none=True) for fee in body.shared_fees]
        if fee_references(value['shared_fees']):
            fail('默认费用规则不能绑定实际凭据，请在订单核费时填写关联编号', 422)
        for key in ('review_days', 'payout_days'):
            if key not in body.model_fields_set:
                value[key] = previous.get(key)
        if 'max_reward_fen' not in body.model_fields_set and 'max_reward_fen' in previous:
            value['max_reward_fen'] = previous['max_reward_fen']
        if 'channel_rates' not in body.model_fields_set and previous.get('channel_rates') is not None:
            value['channel_rates'] = previous['channel_rates']
        if body.enabled and body.rate_bps == 0:
            fail('启用奖励前请设置分成比例', 422)
        if fee_names(value['shared_fees']) & (CHANNEL_NAMES | TAX_NAMES):
            fail('支付渠道费和个人所得税请使用专门的核对栏位', 422)
        conn.execute('UPDATE referral_policy SET value=?::jsonb,revision=revision+1,updated_at=? WHERE id=1', (json.dumps(value), int(time.time())))
        audit(conn, actor, 'policy', '1', {'before': previous, 'after': value, 'reason': body.reason})
        return policy(conn)


def snapshot_order(conn, order_id, user):
    # 微信身份摘要在注销后重新注册时仍一致，防止用新账号反复领取首付奖励。
    buyer = user['wechat_identity'] or 'user:' + user['id']
    order = conn.execute('SELECT payment_channel,device_platform FROM mini_orders WHERE id=?', (order_id,)).fetchone()
    value = policy(conn)
    value.update(channel_rate_bps=channel_rate(value, order['payment_channel'], order['device_platform']),
                 channel_rate_key=channel_key(order['payment_channel'], order['device_platform']))
    conn.execute('UPDATE mini_orders SET reward_policy=?::jsonb,reward_buyer=? WHERE id=?', (json.dumps(value), buyer, order_id))


def void_statement(conn, identifier, reason, actor=None):
    row = conn.execute('SELECT * FROM referral_statements WHERE id=?', (identifier,)).fetchone()
    if not row or row['status'] in ('paid', 'void'):
        return
    conn.execute("UPDATE referral_statements SET status='void',reason=?,revision=revision+1,updated_at=? WHERE id=?", (reason, int(time.time()), identifier))
    conn.execute('UPDATE referral_rewards SET statement_id=NULL,revision=revision+1 WHERE statement_id=?', (identifier,))
    conn.execute('UPDATE referral_adjustments SET statement_id=NULL WHERE statement_id=?', (identifier,))
    application = conn.execute('SELECT id FROM referral_settlement_requests WHERE statement_id=?', (identifier,)).fetchone()
    if application:
        finish_request(conn, application['id'], 'invalidated', reason, actor)
    audit(conn, actor, 'void_statement', identifier, {'reason': reason})


def add_adjustment(conn, beneficiary, name, amount, source, reason, evidence, actor=None):
    if not amount:
        return
    if conn.execute('SELECT 1 FROM referral_adjustments WHERE source=?', (source,)).fetchone():
        return
    # 新债项进入时，旧的待付金额必须重新核对，防止仍按旧金额出款。
    opened = conn.execute("SELECT id FROM referral_statements WHERE beneficiary=? AND status IN ('draft','approved')", (beneficiary,)).fetchone()
    if opened:
        void_statement(conn, opened['id'], '新增结算调整，需重新核对', actor)
    conn.execute('INSERT INTO referral_adjustments(beneficiary,beneficiary_name,amount_fen,source,reason,evidence,created_at) VALUES(?,?,?,?,?,?,?)',
                 (beneficiary, name, amount, source, reason, evidence, int(time.time())))
    audit(conn, actor, 'adjustment', source, {'beneficiary': beneficiary, 'amount_fen': amount, 'reason': reason, 'evidence': evidence})


def revoke_reward(conn, order_id, reason):
    reward = conn.execute('SELECT * FROM referral_rewards WHERE order_id=?', (order_id,)).fetchone()
    if not reward or reward['status'] == 'void':
        return
    if reward['status'] == 'paid':
        # 退回全部税前奖励；已发生的个人费用、已代扣税款不自动返还，凭核实凭证另记调整。
        add_adjustment(conn, reward['beneficiary'], reward['beneficiary_name'], -reward['commission_fen'],
                       'reversal:' + order_id, reason, '原结算单：' + reward['statement_id'])
    elif reward['statement_id']:
        void_statement(conn, reward['statement_id'], reason)
    elif reward['request_id']:
        finish_request(conn, reward['request_id'], 'invalidated', reason)
    conn.execute("UPDATE referral_rewards SET status='void',reason=?,revision=revision+1 WHERE order_id=?", (reason, order_id))
    audit(conn, None, 'revoke_reward', order_id, {'reason': reason})


def record_payment(conn, order_id, *, historical=False):
    """与支付确认同一 accounts 事务；按支付时间排序处理重复、并发及乱序通知。"""
    order = conn.execute('SELECT * FROM mini_orders WHERE id=?', (order_id,)).fetchone()
    if order['payment_channel'] == 'virtual' and order['virtual_env'] == 1:
        return
    buyer = order['reward_buyer'] or 'user:' + (order['referral'].get('buyer_id') or order['user_id'] or order_id)
    paid_at = order['paid_at'] or order['updated_at']
    first = conn.execute('SELECT * FROM referral_first_payments WHERE buyer=?', (buyer,)).fetchone()
    if first:
        if historical or first['order_id'] == order_id or first['paid_at'] <= paid_at:
            return
        revoke_reward(conn, first['order_id'], '收到更早的付款记录，原订单不再是首次付费')
        conn.execute('UPDATE referral_first_payments SET order_id=?,paid_at=? WHERE buyer=?', (order_id, paid_at, buyer))
        if first['historical']:
            return
    else:
        conn.execute('INSERT INTO referral_first_payments(buyer,order_id,paid_at,historical) VALUES(?,?,?,?)', (buyer, order_id, paid_at, historical))
        if historical:
            return
    value, relation = order['reward_policy'], order['referral']
    if not value.get('enabled') or order['status'] == 'refunded' or order['amount_fen'] <= 0:
        return
    if relation.get('admin_id'):
        beneficiary, name = 'admin:' + str(relation['admin_id']), relation.get('admin_name', '')
    else:
        return
    conn.execute('INSERT INTO referral_rewards(order_id,buyer,beneficiary,beneficiary_name,policy,created_at) VALUES(?,?,?,?,?::jsonb,?) ON CONFLICT DO NOTHING',
                 (order_id, buyer, beneficiary, name, json.dumps(value), int(time.time())))
    audit(conn, None, 'first_reward', order_id, {'beneficiary': beneficiary, 'policy': value})


def scope(conn, actor, alias=''):
    owner = settlement_access.owner_id(conn, actor)
    return (f'{alias}beneficiary=?', ['admin:' + str(owner)]) if owner is not None else ('1=1', [])


def listing(actor, kind='rewards', offset=0, limit=20, filters=None):
    from app.services.settlement_queries import where as filtered_where
    with db() as conn:
        where, args = filtered_where(conn, actor, kind, filters)
        table = {'rewards': 'referral_rewards', 'statements': 'referral_statements', 'adjustments': 'referral_adjustments',
                 'requests': 'referral_settlement_requests'}[kind]
        total = conn.execute(f'SELECT COUNT(*) FROM {table} r WHERE {where}', args).fetchone()[0]
        if kind == 'rewards':
            rows = reward_orders(conn, where=where, args=args, limit=limit, offset=offset)
            now = time.time()
            items = [public_reward(row, now) for row in rows]
        else:
            rows = conn.execute(f'SELECT r.* FROM {table} r WHERE {where} ORDER BY r.created_at DESC,r.id DESC LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
            items = [dict(row) for row in rows]
            if kind == 'requests' and items:
                ids = [item['id'] for item in items]
                placeholders = ','.join('?' for _ in ids)
                progress = {row['request_id']: row['confirmed'] for row in conn.execute(
                    f'SELECT request_id,COUNT(*) FILTER (WHERE costs IS NOT NULL) AS confirmed FROM referral_rewards WHERE request_id IN ({placeholders}) GROUP BY request_id', ids)}
                statements = {row['id']: dict(row) for row in conn.execute(
                    'SELECT s.id,s.status,s.gross_fen,s.personal_fen,s.tax_fen,s.net_fen,s.receipt,s.approved_at FROM referral_statements s '
                    f'JOIN referral_settlement_requests r ON r.statement_id=s.id WHERE r.id IN ({placeholders})', ids)}
                for item in items:
                    item['snapshot'] = reference_snapshot(item['snapshot'])
                    item['confirmed_orders'] = progress.get(item['id'], 0)
                    item['statement_summary'] = statements.get(item['statement_id'])
    return {'items': items, 'total': total}


def reward_row(conn, identifier):
    row = conn.execute('SELECT * FROM referral_rewards WHERE order_id=?', (identifier,)).fetchone()
    if not row:
        fail('奖励不存在', 404)
    return row


def available(conn, reward):
    return require_available(reward_orders(conn, order_ids=[reward['order_id']])[0], time.time())


def resolve_shared_fees(fees, amount_fen, channel_fee_fen):
    """比例费用逐项按指定基数计算到分；保存计算输入与结果，历史结算不重算。"""
    result = []
    for fee in fees:
        value = fee.model_dump(exclude_none=True)
        if value.get('source_ref'):
            value['source_ref'] = cost_reference(value['source_ref'])
        if fee.mode == 'percent':
            base = amount_fen if fee.basis == 'order_gross' else max(0, amount_fen - channel_fee_fen)
            value.update(base_fen=base, amount_fen=base * fee.rate_bps // 10000)
        result.append(value)
    return result


def channel_fee(amount_fen, rate_bps):
    """渠道费按实收乘费率，四舍五入到分；整数计算避免浮点误差。"""
    return (amount_fen * rate_bps + 5000) // 10000


def capped_reward(value, policy):
    cap = policy.get('max_reward_fen')
    return min(value, cap) if cap is not None else value


def confirm_costs(actor, identifier, body):
    with db(serialized='accounts') as conn:
        return _confirm_costs(conn, actor, identifier, body)


def _confirm_costs(conn, actor, identifier, body):
    settlement_access.authorize(conn, actor, 'Costs')
    from app.services.settlement_bills import validate_cost
    validate_cost(conn, identifier, body)
    row = reward_row(conn, identifier)
    if row['revision'] != body.revision or row['status'] != 'pending' or row['statement_id']:
        fail('奖励已变化或已进入结算单，请刷新', 409)
    order = conn.execute('SELECT amount_fen,status FROM mini_orders WHERE id=?', (identifier,)).fetchone()
    if order['status'] != 'paid':
        fail('订单已退款，不能核对奖励', 409)
    channel = channel_fee(order['amount_fen'], body.channel_rate_bps) if body.channel_rate_bps is not None else body.channel_fee_fen
    shared = resolve_shared_fees(body.shared_fees, order['amount_fen'], channel)
    fees = channel + sum(fee['amount_fen'] for fee in shared)
    if fee_names([fee.model_dump() for fee in body.shared_fees]) & (CHANNEL_NAMES | TAX_NAMES):
        fail('支付渠道费和个人所得税不能重复列入共同费用', 422)
    # 共同费用超过实收时奖励为零；绝不产生负奖励或浮点舍入。
    commission = capped_reward(max(0, order['amount_fen'] - fees) * row['policy']['rate_bps'] // 10000, row['policy'])
    value = body.model_dump(exclude={'revision', 'order_id'}, exclude_none=True)
    value.update(channel_fee_fen=channel, shared_fees=shared, confirmed_by=actor, confirmed_at=int(time.time()))
    if body.channel_rate_bps is not None:
        value.update(channel_base_fen=order['amount_fen'], channel_rounding='half_up')
    conn.execute('UPDATE referral_rewards SET costs=?::jsonb,commission_fen=?,revision=revision+1 WHERE order_id=?', (json.dumps(value), commission, identifier))
    from app.services.cost_vouchers import validate_references
    validate_references(conn, [fee.get('source_ref') for fee in shared])
    audit(conn, actor, 'costs', identifier, {'before': row['costs'], 'after': value, 'commission_fen': commission})
    return dict(reward_row(conn, identifier))


def confirm_request_costs(actor, identifier, body):
    """申请内批量核对，包含过期版本、退款或越界订单时整批回滚。"""
    with db(serialized='accounts') as conn:
        settlement_access.authorize(conn, actor, 'Costs')
        request = request_row(conn, identifier, actor)
        if request['revision'] != body.revision or request['status'] != 'reviewing' or request['statement_id']:
            fail('申请已变化或未处于订单核对阶段，请刷新', 409)
        requested = {item['order_id'] for item in request['snapshot']['items']}
        rewards = {row['order_id']: row for row in reward_orders(conn, order_ids=[item.order_id for item in body.items])}
        now = time.time()
        for item in body.items:
            reward = rewards.get(item.order_id)
            if reward is None:
                fail('奖励不存在', 404)
            if item.order_id not in requested or reward['request_id'] != identifier or reward['beneficiary'] != request['beneficiary']:
                fail('只能核对此申请包含的订单', 409)
            require_available(reward, now)
            _confirm_costs(conn, actor, item.order_id, item)
        conn.execute('UPDATE referral_settlement_requests SET revision=revision+1,updated_at=? WHERE id=?', (int(time.time()), identifier))
        audit(conn, actor, 'batch_confirm_costs', identifier, {'order_ids': [item.order_id for item in body.items]})
        return dict(request_row(conn, identifier, actor))


def resolve_personal_fees(fees, gross, adjustment):
    """个人比例费用在整张结算单计算一次，负的调整后余额按零作基数。"""
    result = []
    for fee in fees:
        value = fee.model_dump(exclude_none=True)
        if value.get('source_ref'):
            value['source_ref'] = cost_reference(value['source_ref'])
        if fee.mode == 'percent':
            base = gross if fee.basis == 'reward_gross' else max(0, gross + adjustment)
            value.update(base_fen=base, amount_fen=base * fee.rate_bps // 10000)
        result.append(value)
    return result


def statement_row(conn, identifier):
    row = conn.execute('SELECT * FROM referral_statements WHERE id=?', (identifier,)).fetchone()
    if not row:
        fail('结算单不存在', 404)
    return row


def create_statement(actor, body):
    with db(serialized='accounts') as conn:
        return _create_statement(conn, actor, body)


def _create_statement(conn, actor, body):
    settlement_access.authorize(conn, actor, 'Costs')
    ids = list(dict.fromkeys(body.order_ids))
    if body.settlement_request_id and not ids:
        requested = conn.execute('SELECT snapshot FROM referral_settlement_requests WHERE id=?', (body.settlement_request_id,)).fetchone()
        if not requested:
            fail('结算申请不存在', 404)
        ids = [item['order_id'] for item in requested['snapshot']['items']]
    rewards = reward_orders(conn, order_ids=ids)
    if len(rewards) != len(ids):
        fail('奖励不存在', 404)
    if rewards:
        beneficiary, name = rewards[0]['beneficiary'], rewards[0]['beneficiary_name']
    else:
        target = conn.execute('SELECT beneficiary,beneficiary_name FROM referral_adjustments WHERE beneficiary=? AND statement_id IS NULL LIMIT 1', (body.beneficiary,)).fetchone()
        if not target:
            fail('请选择奖励订单或有待处理调整的管理员', 422)
        beneficiary, name = target['beneficiary'], target['beneficiary_name']
    if any(item['beneficiary'] != beneficiary for item in rewards):
        fail('一张结算单只能属于同一个推广人', 422)
    application = conn.execute("SELECT * FROM referral_settlement_requests WHERE beneficiary=? AND status IN ('pending','reviewing','approved')", (beneficiary,)).fetchone()
    if application:
        requested_ids = {item['order_id'] for item in application['snapshot']['items']}
        if (body.settlement_request_id != application['id'] or requested_ids != set(ids)
                or application['status'] != 'reviewing' or application['statement_id']):
            fail('请从该管理员的结算申请开始对账，并按申请订单生成结算单', 409)
        if any(item['request_id'] != application['id'] for item in rewards):
            fail('申请订单已发生变化，请重新核对', 409)
    elif body.settlement_request_id or any(item['request_id'] for item in rewards):
        fail('结算申请已失效，请刷新', 409)
    if conn.execute("SELECT 1 FROM referral_statements WHERE beneficiary=? AND status IN ('draft','approved')", (beneficiary,)).fetchone():
        fail('此推广人已有未完成结算单，请先完成或作废', 409)
    items = []
    for reward in rewards:
        order = require_available(reward, time.time())
        if reward['statement_id'] or reward['costs'] is None:
            fail('订单费用尚未核对或已进入结算单', 409)
        items.append({'order_id': reward['order_id'], 'amount_fen': order['amount_fen'], 'paid_at': order['paid_at'],
                      'payment_channel': order['payment_channel'], 'device_platform': order['device_platform'],
                      'costs': reward['costs'], 'policy': reward['policy'], 'commission_fen': reward['commission_fen']})
    adjustments = [dict(row) for row in conn.execute('SELECT * FROM referral_adjustments WHERE beneficiary=? AND statement_id IS NULL ORDER BY id', (beneficiary,))]
    gross = sum(item['commission_fen'] for item in items)
    adjustment = sum(item['amount_fen'] for item in adjustments)
    if not rewards and adjustment <= 0:
        fail('只有待扣回款项，保留至后续奖励抵扣即可', 422)
    identifier, now = uuid.uuid4().hex, int(time.time())
    snapshot = {'items': items, 'adjustments': adjustments, 'channels': channel_totals(items),
                'service_terms': application['snapshot'].get('service_terms', {}) if application else service_terms(policy(conn))}
    conn.execute('INSERT INTO referral_statements(id,beneficiary,beneficiary_name,snapshot,gross_fen,adjustment_fen,created_at,updated_at) VALUES(?,?,?,?::jsonb,?,?,?,?)',
                 (identifier, beneficiary, name, json.dumps(snapshot), gross, adjustment, now, now))
    from app.services.settlement_operations import capture_payee
    payee = capture_payee(conn, identifier, beneficiary)
    if payee:
        snapshot['payee'] = payee
        conn.execute('UPDATE referral_statements SET snapshot=?::jsonb WHERE id=?', (json.dumps(snapshot), identifier))
    conn.execute('UPDATE referral_rewards SET statement_id=?,revision=revision+1 WHERE order_id=ANY(?)', (identifier, ids))
    conn.execute('UPDATE referral_adjustments SET statement_id=? WHERE beneficiary=? AND statement_id IS NULL', (identifier, beneficiary))
    if application:
        conn.execute('UPDATE referral_settlement_requests SET statement_id=?,revision=revision+1,updated_at=? WHERE id=?',
                     (identifier, now, application['id']))
    audit(conn, actor, 'create_statement', identifier, {'order_ids': ids})
    return dict(statement_row(conn, identifier))


def check_statement(conn, row):
    from app.services.settlement_disputes import blockers
    if blockers(conn, row):
        fail('结算存在未处理异议，请先完成异议处理', 409)
    from app.services.settlement_bills import validate_statement
    validate_statement(conn, row)
    rewards = {item['order_id']: item for item in reward_orders(conn, order_ids=[item['order_id'] for item in row['snapshot']['items']])}
    for item in row['snapshot']['items']:
        reward = rewards.get(item['order_id'])
        if reward is None:
            fail('奖励不存在', 404)
        require_available(reward, time.time())
        if reward['statement_id'] != row['id'] or reward['commission_fen'] != item['commission_fen']:
            fail('结算单已发生变化，请作废后重建', 409)


def approve(actor, identifier, body):
    with db(serialized='accounts') as conn:
        settlement_access.authorize(conn, actor, 'Review')
        row = statement_row(conn, identifier)
        if row['status'] != 'draft' or row['revision'] != body.revision:
            fail('结算单已变化，请刷新', 409)
        check_statement(conn, row)
        settlement_access.check_review(conn, actor, row)
        request = conn.execute('SELECT snapshot FROM referral_settlement_requests WHERE statement_id=?', (identifier,)).fetchone()
        if request:
            request = {'snapshot': reference_snapshot(request['snapshot'])}
        if request and (request['snapshot']['reference_gross_fen'] != row['gross_fen'] or request['snapshot']['adjustment_fen'] != row['adjustment_fen']) and len(body.difference_reason.strip()) < 2:
            fail('与申请时的奖励或历史调整有差异，请填写差异原因', 422)
        names = fee_names([fee.model_dump() for fee in body.personal_fees])
        shared_refs = {cost_reference(fee.get('source_ref')) for item in row['snapshot']['items'] for fee in item['costs']['shared_fees']} - {''}
        if fee_references([fee.model_dump() for fee in body.personal_fees]) & shared_refs:
            fail('此凭据费用项已计入共同费用，不能再次作为个人费用扣除', 422)
        shared_names = {''.join(fee['name'].split()).casefold() for item in row['snapshot']['items'] for fee in item['costs']['shared_fees']}
        if names & (shared_names | CHANNEL_NAMES | TAX_NAMES):
            fail('已计入共同费用、支付渠道费或个税的项目不能再次扣除', 422)
        personal_fees = resolve_personal_fees(body.personal_fees, row['gross_fen'], row['adjustment_fen'])
        personal = sum(fee['amount_fen'] for fee in personal_fees)
        if personal + body.tax_fen > max(0, row['gross_fen'] + row['adjustment_fen']):
            fail('个人费用与税费不能超过本期抵扣后可用奖励，请核对金额', 422)
        net = row['gross_fen'] + row['adjustment_fen'] - personal - body.tax_fen
        value, now = body.model_dump(exclude={'revision'}), int(time.time())
        value.update(personal_fees=personal_fees, confirmed_by=actor, confirmed_at=now)
        conn.execute("UPDATE referral_statements SET status='approved',personal_fen=?,tax_fen=?,net_fen=?,review=?::jsonb,approved_at=?,updated_at=?,revision=revision+1 WHERE id=?",
                     (personal, body.tax_fen, net, json.dumps(value), now, now, identifier))
        conn.execute("UPDATE referral_settlement_requests SET status='approved',revision=revision+1,updated_at=? WHERE statement_id=?", (now, identifier))
        from app.services.cost_vouchers import validate_references
        validate_references(conn, [fee.get('source_ref') for fee in personal_fees])
        audit(conn, actor, 'approve', identifier, value)
        return dict(statement_row(conn, identifier))


def record_payout(actor, identifier, body):
    with db(serialized='accounts') as conn:
        return _record_payout(conn, actor, identifier, body)


def _record_payout(conn, actor, identifier, body, batch_id=None):
    settlement_access.authorize(conn, actor, 'Payout')
    row = statement_row(conn, identifier)
    if row['status'] == 'paid' and row['receipt'] == body.receipt and body.amount_fen == max(0, row['net_fen']):
        return dict(row)
    if row['status'] != 'approved' or row['revision'] != body.revision:
        fail('结算单未批准或已经支付，请刷新', 409)
    check_statement(conn, row)
    settlement_access.check_payment(conn, actor, row)
    reserved = conn.execute("SELECT batch_id FROM referral_payout_batch_items WHERE statement_id=? AND status IN ('pending','failed')", (identifier,)).fetchone()
    if reserved and reserved[0] != batch_id:
        fail('此单已进入付款批次，请通过批次回单登记或先取消批次', 409)
    if body.amount_fen != max(0, row['net_fen']):
        fail('付款金额必须与结算单最终应付一致', 422)
    if conn.execute("SELECT 1 FROM referral_statements WHERE status='paid' AND receipt=?", (body.receipt,)).fetchone():
        fail('该付款凭证已经用于另一结算单', 409)
    if body.amount_fen > 0:
        if not row['snapshot'].get('payee') or not conn.execute(
                'SELECT 1 FROM referral_payout_accounts WHERE statement_id=?', (identifier,)).fetchone():
            fail('非零付款须先留存本结算单的收款资料', 422)
        if body.transferred_at is None:
            fail('非零付款须填写实际付款时间', 422)
    now = int(time.time())
    if body.transferred_at is not None and (body.transferred_at > now + 60 or body.transferred_at < row['created_at']):
        fail('实际付款时间须在结算单创建后，且不能为未来时间', 422)
    conn.execute("UPDATE referral_statements SET status='paid',receipt=?,paid_at=?,updated_at=?,revision=revision+1 WHERE id=?", (body.receipt, now, now, identifier))
    conn.execute('UPDATE referral_statements SET payout=?::jsonb WHERE id=?',
                 (json.dumps({'transferred_at': body.transferred_at, 'registered_at': now, 'payee': row['snapshot'].get('payee')}), identifier))
    conn.execute("UPDATE referral_rewards SET status='paid',revision=revision+1 WHERE statement_id=?", (identifier,))
    conn.execute("UPDATE referral_settlement_requests SET status='paid',revision=revision+1,updated_at=? WHERE statement_id=?", (now, identifier))
    if row['net_fen'] < 0:
        add_adjustment(conn, row['beneficiary'], row['beneficiary_name'], row['net_fen'], 'carry:' + identifier, '上期未抵扣完的奖励扣回', '结算单：' + identifier, actor)
    audit(conn, actor, 'record_payout', identifier, body.model_dump())
    return dict(statement_row(conn, identifier))


def cancel_statement(actor, identifier, body):
    with db(serialized='accounts') as conn:
        settlement_access.authorize(conn, actor, 'Review')
        row = statement_row(conn, identifier)
        if row['revision'] != body.revision or row['status'] not in ('draft', 'approved'):
            fail('只能作废尚未付款的结算单', 409)
        void_statement(conn, identifier, body.reason, actor)
        return dict(statement_row(conn, identifier))


def manual_adjustment(actor, body):
    with db(serialized='accounts') as conn:
        require_super(conn, actor)
        previous = conn.execute('SELECT * FROM referral_adjustments WHERE source=?', ('manual:' + body.request_id,)).fetchone()
        if previous:
            if (previous['beneficiary'], previous['amount_fen'], previous['reason'], previous['evidence']) != (body.beneficiary, body.amount_fen, body.reason, body.evidence):
                fail('请求标识已用于其他调整', 409)
            return dict(previous)
        if not body.amount_fen:
            fail('调整金额不能为零', 422)
        target = conn.execute('SELECT beneficiary_name FROM referral_rewards WHERE beneficiary=? LIMIT 1', (body.beneficiary,)).fetchone()
        if not target:
            fail('推广人尚无奖励账本', 404)
        add_adjustment(conn, body.beneficiary, target[0], body.amount_fen, 'manual:' + body.request_id, body.reason, body.evidence, actor)
        return dict(conn.execute('SELECT * FROM referral_adjustments WHERE source=?', ('manual:' + body.request_id,)).fetchone())


def request_row(conn, identifier, actor):
    where, args = scope(conn, actor)
    row = conn.execute(f'SELECT * FROM referral_settlement_requests WHERE id=? AND {where}', [identifier, *args]).fetchone()
    if not row:
        fail('结算申请不存在或无权查看', 404)
    return row


def finish_request(conn, identifier, status, reason, actor=None):
    row = conn.execute('SELECT * FROM referral_settlement_requests WHERE id=?', (identifier,)).fetchone()
    if not row or row['status'] not in ('pending', 'reviewing', 'approved'):
        return
    conn.execute('UPDATE referral_settlement_requests SET status=?,reason=?,revision=revision+1,updated_at=? WHERE id=?',
                 (status, reason, int(time.time()), identifier))
    conn.execute('UPDATE referral_rewards SET request_id=NULL,revision=revision+1 WHERE request_id=?', (identifier,))
    audit(conn, actor, 'settlement_request_' + status, identifier, {'reason': reason})


def _request_quote(conn, actor, order_ids, all_eligible=False):
    catalog_scope.owner_id(conn, actor)
    beneficiary = 'admin:' + str(actor)
    if conn.execute("SELECT 1 FROM referral_settlement_requests WHERE beneficiary=? AND status IN ('pending','reviewing','approved')", (beneficiary,)).fetchone():
        fail('已有未完成的结算申请，请先查看处理进度', 409)
    if conn.execute("SELECT 1 FROM referral_statements WHERE beneficiary=? AND status IN ('draft','approved')", (beneficiary,)).fetchone():
        fail('已有未完成的结算单，请等待处理', 409)
    excluded = []
    rows = reward_orders(conn, beneficiary=beneficiary, order_ids=None if all_eligible else order_ids,
                         pending_only=all_eligible, limit=5001 if all_eligible else None)
    rewards = {row['order_id']: row for row in rows}
    now = time.time()
    if all_eligible:
        if len(rows) > 5000:
            fail('待结算订单超过 5000 笔，请勾选订单分批申请', 422)
        order_ids = []
        for row in sorted(rows, key=lambda item: item['order_id']):
            try:
                require_available(row, now)
            except HTTPException as error:
                if error.status_code != 409:
                    raise
                excluded.append({'order_id': row['order_id'], 'reason': error.detail['error'] if isinstance(error.detail, dict) else str(error.detail),
                                 'available_at': row['paid_at'] + row['policy']['hold_days'] * 86400})
            else:
                order_ids.append(row['order_id'])
    items = []
    for identifier in sorted(set(order_ids)):
        reward = rewards.get(identifier)
        if not reward:
            fail('只能申请本人推广订单的奖励', 404)
        order = require_available(reward, now)
        if reward['statement_id'] or reward['request_id']:
            fail('订单已在结算或申请中，不能重复提交', 409)
        costs = reward['costs']
        # 按下单费率试算，旧订单缺少费率时明确标识未知，不能伪装为已核对。
        channel_rate = costs.get('channel_rate_bps') if costs else reward['policy'].get('channel_rate_bps')
        channel = costs['channel_fee_fen'] if costs else channel_fee(order['amount_fen'], channel_rate) if channel_rate is not None else None
        fees = costs['shared_fees'] if costs else reward['policy']['shared_fees'] if channel is None else resolve_shared_fees(
            [SharedFee.model_validate(fee) for fee in reward['policy']['shared_fees']], order['amount_fen'], channel)
        reference = reward['commission_fen'] if costs else None if channel is None else capped_reward(max(0, order['amount_fen'] - channel - sum(fee['amount_fen'] for fee in fees)) * reward['policy']['rate_bps'] // 10000, reward['policy'])
        items.append({'order_id': identifier, 'revision': reward['revision'], 'amount_fen': order['amount_fen'],
                      'payment_channel': order['payment_channel'], 'device_platform': order['device_platform'],
                      'paid_at': order['paid_at'], 'policy': reward['policy'], 'costs': costs,
                      'reference_channel_fen': channel, 'reference_channel_rate_bps': channel_rate,
                      'reference_fees': fees, 'reference_commission_fen': reference})
    adjustments = [dict(row) for row in conn.execute('SELECT * FROM referral_adjustments WHERE beneficiary=? AND statement_id IS NULL ORDER BY id', (beneficiary,))]
    adjustment = sum(item['amount_fen'] for item in adjustments)
    snapshot = reference_snapshot({'items': items, 'adjustments': adjustments, 'adjustment_fen': adjustment,
                'all_eligible': all_eligible, 'excluded': excluded, 'service_terms': service_terms(policy(conn)),
                'unconfirmed_orders': sum(item['costs'] is None for item in items),
                'personal_fen': None, 'tax_fen': None, 'net_fen': None})
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()
    return {'snapshot': snapshot, 'quote_digest': hashlib.sha256(encoded).hexdigest()}


def preview_request(actor, body):
    with db(read_only_snapshot=True) as conn:
        return _request_quote(conn, actor, body.order_ids, body.all_eligible)


def apply_request(actor, body):
    with db(serialized='accounts') as conn:
        catalog_scope.owner_id(conn, actor)
        beneficiary = 'admin:' + str(actor)
        previous = conn.execute('SELECT * FROM referral_settlement_requests WHERE beneficiary=? AND request_key=?', (beneficiary, body.request_key)).fetchone()
        if previous:
            if (previous['quote_digest'] != body.quote_digest or previous['note'] != body.note
                    or previous['snapshot'].get('all_eligible', False) != body.all_eligible
                    or (not body.all_eligible and sorted(set(body.order_ids)) != [item['order_id'] for item in previous['snapshot']['items']])):
                fail('申请编号已用于其他内容', 409)
            return dict(previous)
        quote = _request_quote(conn, actor, body.order_ids, body.all_eligible)
        if not quote['snapshot']['items']:
            fail('暂无可申请的奖励订单，请查看未纳入原因', 422)
        if quote['quote_digest'] != body.quote_digest:
            fail('费用或奖励已变化，请重新查看申请明细后确认', 409)
        name = conn.execute('SELECT username FROM users WHERE id=?', (actor,)).fetchone()[0]
        identifier, now = uuid.uuid4().hex, int(time.time())
        conn.execute('INSERT INTO referral_settlement_requests(id,beneficiary,beneficiary_name,request_key,quote_digest,snapshot,note,created_at,updated_at) VALUES(?,?,?,?,?,?::jsonb,?,?,?)',
                     (identifier, beneficiary, name, body.request_key, quote['quote_digest'], json.dumps(quote['snapshot']), body.note, now, now))
        conn.execute('UPDATE referral_rewards SET request_id=?,revision=revision+1 WHERE order_id=ANY(?)',
                     (identifier, [item['order_id'] for item in quote['snapshot']['items']]))
        audit(conn, actor, 'apply_settlement', identifier, {'quote_digest': quote['quote_digest'], 'all_eligible': body.all_eligible,
                                                        'order_ids': [item['order_id'] for item in quote['snapshot']['items']]})
        return dict(request_row(conn, identifier, actor))


def request_detail(actor, identifier):
    with db(read_only_snapshot=True) as conn:
        row = dict(request_row(conn, identifier, actor))
        row['snapshot'] = reference_snapshot(row['snapshot'])
        identifiers = [item['order_id'] for item in row['snapshot']['items']]
        rewards = reward_orders(conn, order_ids=identifiers, beneficiary=row['beneficiary'])
        items = [public_reward(item, time.time()) for item in sorted(rewards, key=lambda reward: reward['order_id'])]
        statement = dict(statement_row(conn, row['statement_id'])) if row['statement_id'] else None
        from app.services import settlement_bills, settlement_operations
        targets = [identifier, *identifiers] + ([statement['id']] if statement else [])
        return {'request': dict(row), 'rewards': items, 'statement': statement,
                'difference': settlement_operations.difference(row, statement, items),
                'timeline': settlement_operations.timeline(conn, targets),
                'attachments': settlement_operations.attachments(conn, statement['id']) if statement else [],
                'bill_checks': settlement_bills.checks(conn, identifiers) if settlement_access.owner_id(conn, actor) is None else []}


def start_request(actor, identifier, body):
    with db(serialized='accounts') as conn:
        settlement_access.authorize(conn, actor, 'Costs')
        row = request_row(conn, identifier, actor)
        if row['revision'] != body.revision or row['status'] != 'pending':
            fail('申请已变化，请刷新', 409)
        rewards = {reward['order_id']: reward for reward in reward_orders(conn, order_ids=[item['order_id'] for item in row['snapshot']['items']])}
        now = time.time()
        for item in row['snapshot']['items']:
            reward = rewards.get(item['order_id'])
            if reward is None:
                fail('奖励不存在', 404)
            require_available(reward, now)
        conn.execute("UPDATE referral_settlement_requests SET status='reviewing',revision=revision+1,updated_at=? WHERE id=?", (int(time.time()), identifier))
        audit(conn, actor, 'start_settlement_review', identifier, {})
        return dict(request_row(conn, identifier, actor))


def close_request(actor, identifier, body, *, cancel=False):
    with db(serialized='accounts') as conn:
        row = request_row(conn, identifier, actor)
        if cancel:
            if row['beneficiary'] != 'admin:' + str(actor) or row['status'] != 'pending':
                fail('只能撤回本人尚未开始对账的申请', 409)
        else:
            settlement_access.authorize(conn, actor, 'Costs')
        if row['revision'] != body.revision or row['status'] not in ('pending', 'reviewing'):
            fail('申请已变化或已批准，请刷新', 409)
        # 有草稿时先释放结算占用，申请仍保留原提交快照及退回原因。
        if row['statement_id']:
            void_statement(conn, row['statement_id'], body.reason, actor)
            # 作废草稿已释放占用，显式退回仍单独留审计记录。
            conn.execute("UPDATE referral_settlement_requests SET status='rejected',revision=revision+1,updated_at=? WHERE id=?",
                         (int(time.time()), identifier))
            audit(conn, actor, 'settlement_request_rejected', identifier, {'reason': body.reason})
        else:
            finish_request(conn, identifier, 'cancelled' if cancel else 'rejected', body.reason, actor)
        return dict(request_row(conn, identifier, actor))


def export_statements(actor):
    from app.services.referrals import csv_safe
    result = listing(actor, 'statements', limit=5000)
    if result['total'] > 5000:
        fail('结算单超过导出上限，请联系管理员分批归档', 422)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['结算单', '推广人', '状态', '税前奖励(分)', '历史调整(分)', '个人费用(分)', '代扣个税(分)', '应付(分)', '结转扣回(分)', '付款凭证', '明细快照'])
    for row in result['items']:
        net = row['net_fen']
        writer.writerow([csv_safe(str(value) if value is not None else '') for value in [row['id'], row['beneficiary_name'], row['status'], row['gross_fen'], row['adjustment_fen'],
                          row['personal_fen'], row['tax_fen'], max(0, net) if net is not None else '', min(0, net) if net is not None else '',
                          row['receipt'], json.dumps({'snapshot': row['snapshot'], 'review': row['review']}, ensure_ascii=False)]])
    return '\ufeff' + output.getvalue()
