"""仅在显式授权的 WSL 部署造结算演示数据；重复执行返回原批次，不覆盖已有记录。

由 WSL 部署包装器设置 LC_WSL_SETTLEMENT_DEMO=authorized-local-only，通过标准输入
提供仅供演示账号的随机密码：{"passwords": {"settle_demo_apply": "...", ...}}。
事务内创建标记清晰的模拟订单和结算，不调用微信、通知、模型或实际转账。
"""
import json
import os
import sys
import time
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import patch

from app.db import db
from app.models.settlements import (
    CostsInput,
    PayeeInput,
    PolicyInput,
    ReceiptInput,
    ReviewInput,
    Revision,
    SettlementApplyInput,
    SettlementPreviewInput,
    StatementInput,
)
from app.services import admin_access, referrals, settlement_operations, settlements, user_store

BATCH = 'settlement_demo_wsl_20261111'
SCENARIOS = {'apply': ('待申请', [10000, 19900]), 'review': ('待对账', [9900, 29900]),
             'pay': ('待付款', [49900]), 'paid': ('已结算', [10000])}


def seed(passwords):
    if os.environ.get('LC_WSL_SETTLEMENT_DEMO') != 'authorized-local-only':
        raise RuntimeError('仅允许已授权的 WSL 演示导入')
    with db(serialized='accounts') as conn:
        previous = conn.execute('SELECT value FROM app_config WHERE key=?', (BATCH,)).fetchone()
        if previous:
            return json.loads(previous['value'])
        super_row = conn.execute("SELECT * FROM users WHERE username='lqyha' AND is_super_admin AND is_active=1").fetchone()
        if not super_row:
            raise RuntimeError('WSL 超级管理员不存在')
        actor = super_row['id']
        names = ['settle_demo_' + kind for kind in SCENARIOS]
        if set(passwords) != set(names) or any(len(value) < 16 for value in passwords.values()):
            raise ValueError('演示账号必须使用独立强密码')
        if any(conn.execute('SELECT 1 FROM users WHERE username=?', (name,)).fetchone() for name in names):
            raise RuntimeError('演示账号名称已存在，拒绝覆盖')

        @contextmanager
        def transaction(*args, **kwargs):
            yield conn

        # 同一真实事务内调用业务服务；任一步失败整批回滚，不向业务库留下半成品。
        with ExitStack() as stack:
            for module in (user_store, admin_access, referrals, settlements, settlement_operations):
                stack.enter_context(patch.object(module, 'db', transaction))
            rules = settlements.get_policy(actor)
            if rules.get('channel_rate_bps') is None:
                rules = settlements.save_policy(actor, PolicyInput(**{**rules, 'channel_rate_bps': 60,
                    'reason': 'WSL 演示起步渠道费率 0.6%，保持原奖励启用状态，可按渠道合同修改'}))
            now, paid_at = int(time.time()), int(time.time()) - 20 * 86400
            plan_id = BATCH + '_plan'
            conn.execute('INSERT INTO mini_membership_plans(id,name,description,days,price_fen,is_active,created_at,updated_at) VALUES(?,?,?,?,?,0,?,?)',
                         (plan_id, '【演示】推广结算测试套餐', '仅本地演示，未上架，无真实支付或会员权益', 30, 10000, now, now))
            result: dict[str, Any] = {'batch': BATCH, 'accounts': [], 'order_count': 0, 'actual_payment': False}
            demo_rules = {**rules, 'enabled': True, 'rate_bps': 1000, 'hold_days': 14, 'channel_rate_bps': 60,
                          'shared_fees': [{'name': '演示服务成本', 'mode': 'percent', 'rate_bps': 500, 'basis': 'after_channel'}]}
            for kind, (label, amounts) in SCENARIOS.items():
                username = 'settle_demo_' + kind
                admin = user_store.create_user(username, passwords[username], role='admin')
                settlement_operations.save_payee(admin.id, PayeeInput(name='【演示】模拟收款人', method='wechat', account='DEMO-NOT-A-REAL-ACCOUNT', bank=''))
                admin_access.save_permissions(actor, admin.id, 1, {'settlements': ['view', 'create', 'export'], 'referrals': ['view']})
                code = referrals.admin_code(actor, admin.id)['code']
                order_ids = []
                for index, amount in enumerate(amounts, 1):
                    user_id = f'{BATCH}_{kind}_{index}'
                    order_id = f'demo_{kind}_{index}_20261111'
                    conn.execute('INSERT INTO mini_users(id,username,nickname,is_active,created_at,updated_at) VALUES(?,?,?,0,?,?)',
                                 (user_id, f'demo_buyer_{kind}_{index}', f'【演示】{label}客户{index}', paid_at, now))
                    referrals.initialize_user(conn, user_id, code)
                    user = conn.execute('SELECT * FROM mini_users WHERE id=?', (user_id,)).fetchone()
                    relation = {**user['referral'], 'admin_name': f'【演示·{label}】{username}', 'buyer_id': user_id}
                    conn.execute('UPDATE mini_users SET referral=?::jsonb WHERE id=?', (json.dumps(relation), user_id))
                    conn.execute("INSERT INTO mini_orders(id,user_id,request_key,plan_id,plan_name,plan_days,amount_fen,status,appid,mchid,transaction_id,payment_channel,device_platform,created_at,expires_at,paid_at,updated_at,referral,reward_policy,reward_buyer) VALUES(?,?,?,?,?,30,?,'paid',?,?,?,'wechat','android',?,?,?,?,?::jsonb,?::jsonb,?)",
                                 (order_id, user_id, order_id, plan_id, '【演示】' + label + '推广订单', amount,
                                  'demo-local-no-provider', 'demo-local-no-provider', 'DEMO-NOT-REAL-' + order_id,
                                  paid_at - 60, paid_at + 900, paid_at, now, json.dumps(relation), json.dumps(demo_rules), 'user:' + user_id))
                    settlements.record_payment(conn, order_id)
                    order_ids.append(order_id)
                application = None
                if kind != 'apply':
                    quote = settlements.preview_request(admin.id, SettlementPreviewInput(order_ids=order_ids))
                    application = settlements.apply_request(admin.id, SettlementApplyInput(order_ids=order_ids,
                        request_key=BATCH + '_' + kind, quote_digest=quote['quote_digest'], confirmed=True,
                        note='【演示数据】用于本地查看结算流程，无真实交易或付款'))
                    if kind in ('pay', 'paid'):
                        settlements.start_request(actor, application['id'], Revision(revision=application['revision']))
                        for order_id in order_ids:
                            reward = settlements.reward_row(conn, order_id)
                            settlements.confirm_costs(actor, order_id, CostsInput(revision=reward['revision'], channel_rate_bps=60,
                                shared_fees=demo_rules['shared_fees'], evidence='【演示】渠道费率 0.6%，服务成本 5%，非真实账单', confirmed=True))
                        draft = settlements.create_statement(actor, StatementInput(order_ids=order_ids, settlement_request_id=application['id']))
                        approved = settlements.approve(actor, draft['id'], ReviewInput(revision=draft['revision'],
                            personal_fees=[{'name': '演示转账费用', 'amount_fen': 10}], tax_fen=0,
                            evidence='【演示】个人费用 0.10 元，税款仅为演示设 0，实际税款另行核定', confirmed=True))
                        if kind == 'paid':
                            settlements.record_payout(actor, draft['id'], ReceiptInput(revision=approved['revision'], amount_fen=approved['net_fen'],
                                receipt='DEMO-模拟付款-未实际转账-20261111', transferred_at=now))
                        application = settlements.request_detail(admin.id, application['id'])['request']
                result['accounts'].append({'username': username, 'label': label, 'admin_id': admin.id, 'order_ids': order_ids,
                                           'application_id': application['id'] if application else None})
                result['order_count'] += len(order_ids)
            conn.execute('INSERT INTO app_config(key,value) VALUES(?,?)', (BATCH, json.dumps(result)))
            settlements.audit(conn, actor, 'seed_local_demo', BATCH, result)
            return result


if __name__ == '__main__':
    print(json.dumps(seed(json.load(sys.stdin)['passwords']), ensure_ascii=False))
