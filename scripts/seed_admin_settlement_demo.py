"""为已有 WSL 管理员按当前规则创建待申请演示订单，不代为申请或结算。

仅由固定 WSL 目标的包装器调用，并设置 LC_WSL_SETTLEMENT_DEMO=authorized-local-only。
seed(username, batch, apply=False) 默认只预检；apply=True 才写入。
grant_access=True 显式允许补充结算查看/申请权限，保留其他权限和账号密码。
每批普通微信、虚拟安卓、虚拟 iOS 各两单，均为独立客户首次付款且已过等待期。
订单、客户、套餐均有演示标记；不调用微信、开通会员或转账。批次重复执行不覆盖。
"""

import json
import os
import re
import time
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import patch

from app.db import db
from app.models.settlements import SettlementPreviewInput
from app.services import admin_access, referrals, settlements
from app.services.settlement_channels import CHANNEL_LABELS, channel_key, channel_rate


def seed(username, batch, *, apply=False, grant_access=False):
    if os.environ.get('LC_WSL_SETTLEMENT_DEMO') != 'authorized-local-only':
        raise RuntimeError('仅允许显式授权的本地 WSL 演示导入')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', batch):
        raise ValueError('演示批次必须为 1 至 64 位字母、数字、下划线或短横线')
    batch_key = 'admin_settlement_demo:' + batch
    with db(serialized='accounts') as conn:
        previous = conn.execute('SELECT value FROM app_config WHERE key=?', (batch_key,)).fetchone()
        if previous:
            previous_result = json.loads(previous['value'])
            if previous_result['username'] != username:
                raise RuntimeError('同批次已用于其他管理员，拒绝覆盖')
            return previous_result
        target = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if not target or target['role'] != 'admin' or not target['is_active'] or target['is_super_admin']:
            raise RuntimeError('目标必须是已存在且启用的普通管理员')
        actor = conn.execute("SELECT id FROM users WHERE username='lqyha' AND is_super_admin AND is_active=1").fetchone()
        if not actor:
            raise RuntimeError('本地超级管理员不存在')
        rules = settlements.policy(conn)
        if not rules['enabled'] or rules['rate_bps'] <= 0:
            raise RuntimeError('当前首付奖励未启用，不能按当前规则创建可申请奖励')
        beneficiary = 'admin:' + str(target['id'])
        if conn.execute("SELECT 1 FROM referral_settlement_requests WHERE beneficiary=? AND status IN ('pending','reviewing','approved')", (beneficiary,)).fetchone():
            raise RuntimeError('目标已有未完成申请，请先处理；不会代为撤回')
        if conn.execute("SELECT 1 FROM referral_statements WHERE beneficiary=? AND status IN ('draft','approved')", (beneficiary,)).fetchone():
            raise RuntimeError('目标已有未完成结算单，请先处理')
        existing_access = set(target['admin_permissions'].get('settlements', []))
        needs_access = not {'view', 'create'}.issubset(existing_access)
        if needs_access and not grant_access:
            raise RuntimeError('目标缺少查看/申请权限，需显式授权补充')
        scenarios = [(channel, platform, amount) for channel, platform in
                     [('wechat', 'android'), ('virtual', 'android'), ('virtual', 'ios')]
                     for amount in (10000, 19900)]
        if any(channel_rate(rules, channel, platform) is None for channel, platform, _ in scenarios):
            raise RuntimeError('当前规则缺少渠道费率，不能给出完整的申请预览')
        result: dict[str, Any] = {'batch': batch, 'username': username, 'admin_id': target['id'], 'policy': rules,
                                  'order_count': len(scenarios), 'actual_payment': False,
                                  'granted_settlement_access': needs_access, 'status': 'preview'}
        if not apply:
            return result

        @contextmanager
        def transaction(*args, **kwargs):
            yield conn

        # 同一事务调用归属、规则快照及首付服务；验证失败整批回滚。
        with ExitStack() as stack:
            for module in (admin_access, referrals, settlements):
                stack.enter_context(patch.object(module, 'db', transaction))
            if needs_access:
                permissions = {**target['admin_permissions'], 'settlements': sorted(existing_access | {'view', 'create'})}
                admin_access.save_permissions(actor['id'], target['id'], target['permissions_revision'], permissions)
            referral_code = referrals.admin_code(actor['id'], target['id'])['code']
            now = int(time.time())
            plan_id = 'demo_' + batch + '_plan'
            conn.execute('INSERT INTO mini_membership_plans(id,name,description,days,price_fen,is_active,created_at,updated_at) VALUES(?,?,?,?,?,0,?,?)',
                         (plan_id, '【演示】管理员结算体验套餐', '本地模拟，未上架，无真实支付及会员权益', 30, 10000, now, now))
            order_ids = []
            for index, (channel, platform, amount) in enumerate(scenarios, 1):
                paid_at = now - (rules['hold_days'] + index) * 86400
                user_id = f'demo_{batch}_buyer_{index}'
                order_id = f'demo_{batch}_order_{index}'
                label = CHANNEL_LABELS[channel_key(channel, platform)]
                conn.execute('INSERT INTO mini_users(id,username,nickname,is_active,created_at,updated_at) VALUES(?,?,?,0,?,?)',
                             (user_id, user_id, f'【演示】{username}推广客户{index}', paid_at - 120, now))
                referrals.initialize_user(conn, user_id, referral_code)
                user = conn.execute('SELECT * FROM mini_users WHERE id=?', (user_id,)).fetchone()
                relation = {**user['referral'], 'buyer_id': user_id, 'bound_at': paid_at - 120, 'demo_batch': batch}
                conn.execute('UPDATE mini_users SET referral=?::jsonb WHERE id=?', (json.dumps(relation), user_id))
                conn.execute("INSERT INTO mini_orders(id,user_id,request_key,plan_id,plan_name,plan_days,amount_fen,status,appid,mchid,transaction_id,payment_channel,device_platform,virtual_env,created_at,expires_at,paid_at,updated_at,referral) VALUES(?,?,?,?,?,30,?,'paid',?,?,?,?,?,0,?,?,?,?,?::jsonb)",
                             (order_id, user_id, order_id, plan_id, f'【演示·未真实付款】{label}', amount,
                              'demo-local-no-provider', 'demo-local-no-provider', 'DEMO-NOT-REAL-' + order_id,
                              channel, platform, paid_at - 60, paid_at + 900, paid_at, now, json.dumps(relation)))
                settlements.snapshot_order(conn, order_id, user)
                settlements.record_payment(conn, order_id)
                reward = settlements.reward_row(conn, order_id)
                settlements.available(conn, reward)
                if reward['beneficiary'] != beneficiary or reward['request_id'] or reward['statement_id']:
                    raise RuntimeError('演示订单归属或待申请状态错误')
                if reward['policy']['revision'] != rules['revision']:
                    raise RuntimeError('订单规则与当前配置不一致')
                order_ids.append(order_id)
            quote = settlements.preview_request(target['id'], SettlementPreviewInput(order_ids=order_ids))
            if len(quote['snapshot']['items']) != len(scenarios) or settlements.policy(conn) != rules:
                raise RuntimeError('导入后的可申请数量或规则校验失败')
            result.update(status='seeded', order_ids=order_ids, preview=quote['snapshot'])
            conn.execute('INSERT INTO app_config(key,value) VALUES(?,?)', (batch_key, json.dumps(result)))
            settlements.audit(conn, actor['id'], 'seed_admin_local_demo', batch, result)
            return result
