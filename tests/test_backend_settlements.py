"""首付奖励及财务状态机回归，仅连接隔离测试库。"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from unittest.mock import patch

import test_backend_growth as growth
import test_backend_virtual_pay as virtual
from fastapi import HTTPException

from app import settlement_schema
from app.config import get_settings
from app.db import db
from app.models.commerce import OrderInput, RefundInput
from app.models.settlements import (
    AdjustmentInput,
    BatchCostsInput,
    CostsInput,
    PayeeInput,
    PolicyInput,
    ReceiptInput,
    ReviewInput,
    Revision,
    SettlementApplyInput,
    SettlementPreviewInput,
    StatementInput,
    VoidInput,
)
from app.routers import settlements as routes
from app.services import (
    admin_access,
    mini_auth,
    mini_orders,
    mini_refunds,
    referrals,
    settlement_operations,
    settlements,
    user_store,
)


class SettlementContracts(growth.GrowthBase):
    configure = growth.CommerceContracts.configure
    create_order = growth.CommerceContracts.create_order
    paid_value = growth.CommerceContracts.paid_value

    def setUp(self):
        super().setUp()
        self.client.app.include_router(routes.router)
        self.configure()
        self.promoter = user_store.create_user('reward-admin', 'test-password', role='admin')
        self.code = referrals.admin_code(self.admin.id, self.promoter.id)['code']
        with db() as conn:
            referrals.initialize_user(conn, self.viewer.id, self.code)
        self.rules()
        settlement_operations.save_payee(self.promoter.id, PayeeInput(name='测试收款人', method='bank', account='6222000012345678', bank='测试银行'))

    def rules(self, **changes):
        value = settlements.get_policy(self.admin.id)
        value.update(enabled=True, rate_bps=2000, hold_days=0, channel_rate_bps=None, channel_rates=None, reason='首次推广规则')
        return settlements.save_policy(self.admin.id, PolicyInput(**{**value, **changes}))

    def reward(self, order):
        with db() as conn:
            return dict(settlements.reward_row(conn, order['id']))

    def costs(self, order, fee=12, shared=100):
        row = self.reward(order)
        return settlements.confirm_costs(self.admin.id, order['id'], CostsInput(revision=row['revision'], channel_fee_fen=fee,
                                           shared_fees=[{'name': '资料服务成本', 'amount_fen': shared}], evidence='支付账单及成本凭据', confirmed=True))

    def paid(self, key='paid-first', at=None):
        order = self.create_order(key)
        value = self.paid_value(order)
        if at is not None:
            value['success_time'] = datetime.fromtimestamp(at, UTC).isoformat()
        mini_orders.confirm_payment(value)
        return order

    def another(self, key):
        identity = mini_auth.digest(get_settings().wechat_app_id + ':' + key)
        user = mini_auth.login_public_identity(identity, openid=key, referral_code=self.code)['user']
        order = mini_orders.create(user['id'], OrderInput(plan_id=self.plan['id'], plan_revision=self.plan['revision'], request_id=key))
        mini_orders.confirm_payment({**self.paid_value(order), 'payer': {'openid': key}})
        return order

    def draft(self, order):
        self.costs(order)
        return settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']]))

    def approve(self, item, personal=10, tax=20):
        return settlements.approve(self.admin.id, item['id'], ReviewInput(revision=item['revision'], personal_fees=[{'name': '转账服务费', 'amount_fen': personal}], tax_fen=tax, evidence='财务核定税款与费用凭据', difference_reason='按实际账单及历史调整核定差异', confirmed=True))

    def payout(self, item):
        if item['net_fen'] > 0 and not item['snapshot'].get('payee'):
            current = settlement_operations.statement_detail(self.admin.id, item['id'])['statement']
            if current['status'] != 'paid':
                if not settlement_operations.payee(self.promoter.id):
                    settlement_operations.save_payee(self.promoter.id, PayeeInput(name='测试收款人', method='bank', account='6222000012345678', bank='测试银行'))
                item = settlement_operations.attach_payee(self.admin.id, item['id'], current['revision'])
        return settlements.record_payout(self.admin.id, item['id'], ReceiptInput(revision=item['revision'], amount_fen=max(0, item['net_fen']), receipt='银行流水-' + item['id'], transferred_at=int(time.time())))

    def refund(self, order):
        item = mini_refunds.request(order['id'], mini_orders.detail(order['id'])['user_id'], RefundInput(reason='测试全额退款'))
        identifier = item['refund']['id']
        with db() as conn:
            conn.execute("UPDATE mini_refunds SET status='processing' WHERE id=?", (identifier,))
        value = {'out_refund_no': identifier, 'out_trade_no': order['id'], 'transaction_id': 'wxtransaction-' + order['id'], 'refund_id': 'wxrefund-' + identifier,
                 'refund_status': 'SUCCESS', 'success_time': datetime.now(UTC).isoformat(), 'amount': {'total': order['amount_fen'], 'refund': order['amount_fen']}}
        mini_refunds.apply(value)
        mini_refunds.apply(value)

    def test_first_success_not_first_created_and_duplicate_callbacks(self):
        earlier_created = self.create_order('created-first')
        paid_first = self.paid(at=int(time.time()) - 2)
        values = [self.paid_value(earlier_created), self.paid_value(paid_first)] * 3
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(mini_orders.confirm_payment, values))
        items = settlements.listing(self.admin.id)['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['order_id'], paid_first['id'])
        self.assertEqual(items[0]['beneficiary'], 'admin:' + str(self.promoter.id))

    def test_channel_percentage_rounding_snapshot_and_application(self):
        self.rules(channel_rate_bps=60, rate_bps=1000, shared_fees=[{'name': '服务成本', 'mode': 'percent', 'rate_bps': 500, 'basis': 'after_channel'}])
        order = self.paid()
        quote = settlements.preview_request(self.promoter.id, SettlementPreviewInput(order_ids=[order['id']]))
        item = quote['snapshot']['items'][0]
        self.assertEqual(item['reference_channel_rate_bps'], 60)
        self.assertEqual(item['reference_channel_fen'], 12)  # 1990分 × 0.6% = 11.94分，四舍五入。
        self.assertEqual(item['reference_fees'][0]['amount_fen'], 98)
        self.assertEqual(item['reference_commission_fen'], 188)
        result = settlements.confirm_costs(self.admin.id, order['id'], CostsInput(revision=1, channel_rate_bps=60,
            shared_fees=[{'name': '服务成本', 'mode': 'percent', 'rate_bps': 500, 'basis': 'after_channel'}], evidence='支付渠道合同及账单', confirmed=True))
        self.assertEqual(result['costs']['channel_fee_fen'], 12)
        self.assertEqual(result['costs']['channel_base_fen'], 1990)
        self.assertEqual(result['costs']['channel_rounding'], 'half_up')
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']]))
        paid = self.payout(self.approve(draft, 0, 0))
        self.rules(channel_rate_bps=1000)
        saved = settlements.listing(self.admin.id, 'statements')['items'][0]
        self.assertEqual(saved, paid)
        self.assertEqual(saved['snapshot']['items'][0]['costs']['channel_rate_bps'], 60)
        for amount, rate, expected in ((1, 5000, 1), (1, 4999, 0), (1990, 0, 0), (1990, 10000, 1990), (10000, 60, 60)):
            self.assertEqual(settlements.channel_fee(amount, rate), expected)

    def test_channel_percentage_rejects_missing_or_client_amount_and_invalid_rates(self):
        order = self.paid()
        base = {'revision': 1, 'shared_fees': [], 'evidence': '核对依据', 'confirmed': True}
        url = '/api/v1/admin/settlements/rewards/' + order['id'] + '/costs'
        for extra in ({}, {'channel_rate_bps': -1}, {'channel_rate_bps': 10001}, {'channel_rate_bps': 0.6},
                      {'channel_rate_bps': '60'}, {'channel_rate_bps': 60, 'channel_fee_fen': 12},
                      {'channel_rate_bps': 60, 'channel_base_fen': 1990}):
            self.assertEqual(self.client.put(url, json={**base, **extra}).status_code, 422)
        response = self.client.put(url, json={**base, 'channel_rate_bps': 0})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['costs']['channel_fee_fen'], 0)

    def batch_order(self, key, paid_at, platform='android', channel='virtual', amount=10000):
        """在一次性库中建立互相独立的首付身份，不调用真实支付。"""
        with db() as conn:
            conn.execute('INSERT INTO mini_users(id,username,created_at,updated_at) VALUES(?,?,?,?)', (key, key, paid_at, paid_at))
            referrals.initialize_user(conn, key, self.code)
            user = conn.execute('SELECT * FROM mini_users WHERE id=?', (key,)).fetchone()
            conn.execute("INSERT INTO mini_orders(id,user_id,request_key,plan_id,plan_name,plan_days,amount_fen,status,appid,mchid,payment_channel,device_platform,created_at,expires_at,paid_at,updated_at,referral) "
                         "VALUES(?,?,?,?,?,30,?,'paid','isolated-app','isolated-mch',?,?,?,?,?,?,?::jsonb)",
                         (key, key, key, self.plan['id'], '合并结算测试', amount, channel, platform, paid_at - 60, paid_at + 900, paid_at, paid_at, json.dumps(user['referral'])))
            settlements.snapshot_order(conn, key, user)
            settlements.record_payment(conn, key)
        return {'id': key}

    def test_channel_rates_follow_order_platform_and_keep_historical_snapshot(self):
        self.rules(channel_rates={'wechat': 60, 'virtual_android': 100, 'virtual_ios': 1200}, rate_bps=1000)
        stamp = int(time.time()) - 100
        for platform, channel, rate in [('android', 'virtual', 100), ('ios', 'virtual', 1200), ('harmony', 'virtual', 100),
                                        ('windows', 'virtual', 100), ('ios', 'wechat', 60), ('', 'virtual', None)]:
            key = 'platform-' + platform + channel
            self.batch_order(key, stamp, platform, channel)
            quote = settlements.preview_request(self.promoter.id, SettlementPreviewInput(order_ids=[key]))
            item = quote['snapshot']['items'][0]
            self.assertEqual(item['reference_channel_rate_bps'], rate)
            self.assertEqual(item['reference_channel_fen'], rate)
            self.assertEqual(item['policy']['channel_rate_bps'], rate)
        self.rules(channel_rates={'wechat': 30, 'virtual_android': 500, 'virtual_ios': 1700})
        quote = settlements.preview_request(self.promoter.id, SettlementPreviewInput(order_ids=['platform-iosvirtual']))
        self.assertEqual(quote['snapshot']['items'][0]['reference_channel_rate_bps'], 1200)
        self.assertEqual(quote['snapshot']['channels'][0]['label'], '虚拟支付 · iOS')
        self.rules(channel_rate_bps=60, channel_rates=None)
        self.batch_order('legacy-single-rate', stamp, 'ios')
        self.assertEqual(self.reward({'id': 'legacy-single-rate'})['policy']['channel_rate_bps'], 60)

    def test_all_eligible_combines_months_and_excludes_hold_refund(self):
        now = int(time.time())
        self.rules(hold_days=14, channel_rates={'wechat': 60, 'virtual_android': 100, 'virtual_ios': 1200})
        for key, age in [('older-month', 90), ('mature', 15), ('holding', 1), ('refund', 16)]:
            self.batch_order(key, now - age * 86400)
        with db() as conn:
            conn.execute("UPDATE mini_orders SET status='refunded' WHERE id='refund'")
        quote = settlements.preview_request(self.promoter.id, SettlementPreviewInput(all_eligible=True))
        self.assertEqual([item['order_id'] for item in quote['snapshot']['items']], ['mature', 'older-month'])
        self.assertEqual({item['order_id'] for item in quote['snapshot']['excluded']}, {'refund', 'holding'})
        self.assertNotIn('month', quote['snapshot'])
        self.assertEqual(settlements.listing(self.promoter.id, limit=1)['total'], 4)
        # 在当前月内刚结束等待期也可申请，无月末限制。
        self.rules(hold_days=0)
        self.batch_order('current-month', now - 60)
        quote = settlements.preview_request(self.promoter.id, SettlementPreviewInput(all_eligible=True))
        self.assertEqual(len(quote['snapshot']['items']), 3)

    def test_all_eligible_over_200_orders_apply_idempotence_and_statement(self):
        self.rules(channel_rates={'wechat': 60, 'virtual_android': 100, 'virtual_ios': 1200}, rate_bps=1000)
        stamp = int(datetime(2026, 10, 1, tzinfo=UTC).timestamp())
        with patch('app.services.settlements.time.time', return_value=datetime(2026, 11, 20, tzinfo=UTC).timestamp()):
            for index in range(201):
                self.batch_order(f'monthly-{index:03}', stamp, 'ios' if index == 200 else 'android')
            queries = []
            from app import db as database
            execute = database._PgConn.execute
            def record_query(conn, sql, args=()):
                queries.append(sql)
                return execute(conn, sql, args)
            with patch.object(database._PgConn, 'execute', record_query):
                quote = settlements.preview_request(self.promoter.id, SettlementPreviewInput(all_eligible=True))
            self.assertLessEqual(len(queries), 10)
            self.assertFalse(any('advisory' in query for query in queries))
            self.assertEqual(len(quote['snapshot']['items']), 201)
            self.assertEqual(quote['snapshot']['reference_gross_fen'], 200 * 990 + 880)
            body = SettlementApplyInput(all_eligible=True, request_key='all-pages-month', quote_digest=quote['quote_digest'], confirmed=True)
            application = settlements.apply_request(self.promoter.id, body)
            self.assertEqual(settlements.apply_request(self.promoter.id, body), application)
            other = user_store.create_user('batch-other-admin', 'test-password', role='admin')
            with self.assertRaises(HTTPException):
                settlements.request_detail(other.id, application['id'])
            queries.clear()
            with patch.object(database._PgConn, 'execute', record_query):
                settlements.start_request(self.admin.id, application['id'], Revision(revision=1))
            self.assertLessEqual(len(queries), 15)
            for item in quote['snapshot']['items']:
                row = self.reward({'id': item['order_id']})
                settlements.confirm_costs(self.admin.id, item['order_id'], CostsInput(revision=row['revision'],
                    channel_rate_bps=item['reference_channel_rate_bps'], shared_fees=[], evidence='合并账单核对', confirmed=True))
            draft = settlements.create_statement(self.admin.id, StatementInput(settlement_request_id=application['id']))
            self.assertEqual(len(draft['snapshot']['items']), 201)
            self.assertNotIn('month', draft['snapshot'])
            self.assertEqual(sum(group['commission_fen'] for group in draft['snapshot']['channels']), draft['gross_fen'])
            final = self.payout(self.approve(draft, 0, 0))
            self.assertEqual(final['net_fen'], 198880)
            retry = settlements.preview_request(self.promoter.id, SettlementPreviewInput(all_eligible=True))
            self.assertEqual(retry['snapshot']['items'], [])
            self.assertEqual(retry['snapshot']['excluded'], [])
            with self.assertRaises(HTTPException) as error:
                settlements.apply_request(self.promoter.id, SettlementApplyInput(all_eligible=True, request_key='empty-all-key', quote_digest=retry['quote_digest'], confirmed=True))
            self.assertEqual(error.exception.status_code, 422)
            self.assertEqual(settlements.request_detail(self.promoter.id, application['id'])['request']['snapshot'], quote['snapshot'])

    def test_all_eligible_preview_changes_and_invalid_scope_cannot_be_submitted(self):
        stamp = int(datetime(2026, 10, 5, tzinfo=UTC).timestamp())
        with patch('app.services.settlements.time.time', return_value=datetime(2026, 11, 20, tzinfo=UTC).timestamp()):
            self.batch_order('month-original', stamp)
            quote = settlements.preview_request(self.promoter.id, SettlementPreviewInput(all_eligible=True))
            self.batch_order('month-late-callback', stamp)
            with self.assertRaises(HTTPException) as error:
                settlements.apply_request(self.promoter.id, SettlementApplyInput(all_eligible=True, request_key='month-stale-key', quote_digest=quote['quote_digest'], confirmed=True))
            self.assertEqual(error.exception.status_code, 409)
        for body in [{'all_eligible': 'true'}, {'all_eligible': 1}, {'all_eligible': True, 'order_ids': ['x']}, {}, {'month': '2026-10'}]:
            self.assertEqual(self.client.post('/api/v1/admin/settlements/requests/preview', json=body).status_code, 422)

    def test_channel_migration_preserves_custom_rules_old_orders_and_repeated_runs(self):
        self.rules(channel_rate_bps=30, rate_bps=2700)
        order = self.paid()
        with db() as conn:
            old = dict(conn.execute('SELECT * FROM mini_orders WHERE id=?', (order['id'],)).fetchone())
            conn.execute("UPDATE referral_policy SET value=value-'channel_rates' WHERE id=1")
            settlement_schema.migrate(conn)
            current = settlements.policy(conn)
            self.assertEqual(current['rate_bps'], 2700)
            self.assertEqual(current['channel_rates'], {'wechat': 30, 'virtual_android': 100, 'virtual_ios': 1200})
            settlement_schema.migrate(conn)
            self.assertEqual(settlements.policy(conn), current)
            self.assertEqual(dict(conn.execute('SELECT * FROM mini_orders WHERE id=?', (order['id'],)).fetchone()), old)

    def application_body(self, orders, key='apply-first-key'):
        ids = [order['id'] for order in orders]
        quote = settlements.preview_request(self.promoter.id, SettlementPreviewInput(order_ids=ids))
        return SettlementApplyInput(order_ids=ids, request_key=key, quote_digest=quote['quote_digest'], note='请核对本次推广奖励', confirmed=True)

    def test_historical_statement_and_request_details_keep_partial_snapshots_and_events(self):
        order = self.paid()
        application = settlements.apply_request(self.promoter.id, self.application_body([order]))
        settlements.start_request(self.admin.id, application['id'], Revision(revision=application['revision']))
        self.costs(order)
        statement = settlements.create_statement(self.admin.id, StatementInput(settlement_request_id=application['id']))
        snapshot = statement['snapshot']
        for field in ('channels', 'payee', 'service_terms'):
            snapshot.pop(field, None)
        item = snapshot['items'][0]
        for field in ('device_platform', 'payment_channel'):
            item.pop(field, None)
        for field in ('max_reward_fen', 'payout_days', 'review_days', 'channel_rates', 'channel_rate_key'):
            item['policy'].pop(field, None)
        snapshot['historical_version'] = 1
        event = {'reason': '历史人工审核', 'amount_fen': 10}
        with db() as conn:
            conn.execute('UPDATE referral_statements SET snapshot=?::jsonb WHERE id=?', (json.dumps(snapshot), statement['id']))
            settlements.audit(conn, None, 'historical_review', statement['id'], event)
            settlements.audit(conn, None, 'historical_policy', order['id'], {'policy': item['policy']})
        self.sign_in(self.admin)
        response = self.client.get('/api/v1/admin/settlements/statements/' + statement['id'])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['statement']['snapshot'], snapshot)
        history = next(row for row in response.json()['timeline'] if row['kind'] == 'historical_review')
        self.assertIsNone(history['actor_name'])
        self.assertEqual(history['value'], event)
        response = self.client.get('/api/v1/admin/settlements/requests/' + application['id'])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['statement']['snapshot'], snapshot)
        history = next(row for row in response.json()['timeline'] if row['kind'] == 'historical_policy')
        self.assertEqual(history['value']['policy'], item['policy'])

    def test_batch_costs_are_atomic_scoped_and_report_current_progress(self):
        orders = [self.paid(), self.another('batch-second')]
        applied = settlements.apply_request(self.promoter.id, self.application_body(orders))
        reviewing = settlements.start_request(self.admin.id, applied['id'], Revision(revision=applied['revision']))
        items = [{'order_id': order['id'], 'revision': self.reward(order)['revision'], 'channel_rate_bps': rate,
                  'shared_fees': [], 'evidence': '分渠道核对实际账单', 'confirmed': True} for order, rate in zip(orders, (100, 1200), strict=True)]
        stale = [{**items[0]}, {**items[1], 'revision': 999}]
        with self.assertRaises(HTTPException):
            settlements.confirm_request_costs(self.admin.id, applied['id'], BatchCostsInput(revision=reviewing['revision'], items=stale))
        self.assertIsNone(self.reward(orders[0])['costs'])
        self.assertIsNone(self.reward(orders[1])['costs'])
        outside = self.another('batch-outside')
        with self.assertRaises(HTTPException):
            settlements.confirm_request_costs(self.admin.id, applied['id'], BatchCostsInput(revision=reviewing['revision'], items=[{**items[0], 'order_id': outside['id']}]))
        result = settlements.confirm_request_costs(self.admin.id, applied['id'], BatchCostsInput(revision=reviewing['revision'], items=items))
        self.assertEqual(result['revision'], reviewing['revision'] + 1)
        self.assertEqual([self.reward(order)['costs']['channel_fee_fen'] for order in orders], [20, 239])
        summary = settlements.listing(self.promoter.id, 'requests')['items'][0]
        self.assertEqual(summary['confirmed_orders'], 2)
        self.assertIsNone(summary['statement_summary'])
        with self.assertRaises(HTTPException):
            settlements.confirm_request_costs(self.admin.id, applied['id'], BatchCostsInput(revision=reviewing['revision'], items=items))
        draft = settlements.create_statement(self.admin.id, StatementInput(settlement_request_id=applied['id']))
        approved = self.approve(draft)
        summary = settlements.listing(self.promoter.id, 'requests')['items'][0]
        self.assertEqual(summary['statement_summary']['net_fen'], approved['net_fen'])
        self.assertEqual(summary['statement_summary']['status'], 'approved')

    def test_batch_cost_api_permissions_duplicates_and_refund_race(self):
        orders = [self.paid(), self.another('batch-refund')]
        application = settlements.apply_request(self.promoter.id, self.application_body(orders))
        current = settlements.start_request(self.admin.id, application['id'], Revision(revision=application['revision']))
        items = [{'order_id': o['id'], 'revision': self.reward(o)['revision'], 'channel_rate_bps': 100,
                  'shared_fees': [], 'evidence': '批量费用核对凭据', 'confirmed': True} for o in orders]
        path = '/api/v1/admin/settlements/requests/' + current['id'] + '/costs'
        admin_access.save_permissions(self.admin.id, self.promoter.id, 1, {'settlements': ['view', 'create']})
        self.sign_in(self.promoter)
        self.assertEqual(self.client.put(path, json={'revision': current['revision'], 'items': items}).status_code, 403)
        self.sign_in(self.admin)
        self.assertEqual(self.client.put(path, json={'revision': current['revision'], 'items': [items[0], items[0]]}).status_code, 422)
        mini_refunds.request(orders[1]['id'], mini_orders.detail(orders[1]['id'])['user_id'], RefundInput(reason='尚未退款先阻止核费'))
        response = self.client.put(path, json={'revision': current['revision'], 'items': items})
        self.assertEqual(response.status_code, 409)
        self.assertIsNone(self.reward(orders[0])['costs'])

    def test_personal_percentage_uses_whole_statement_and_saved_bases(self):
        orders = [self.paid(), self.another('personal-percentage')]
        for order in orders:
            self.costs(order, fee=0, shared=0)
        settlements.manual_adjustment(self.admin.id, AdjustmentInput(beneficiary='admin:' + str(self.promoter.id),
            amount_fen=-100, request_id='personal-adjustment', reason='上期应扣回', evidence='核实的历史凭据'))
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[o['id'] for o in orders]))
        self.assertEqual(draft['gross_fen'], 796)
        approved = settlements.approve(self.admin.id, draft['id'], ReviewInput(revision=draft['revision'], personal_fees=[
            {'name': '协作费用', 'mode': 'percent', 'rate_bps': 333, 'basis': 'reward_gross'},
            {'name': '转账服务', 'mode': 'percent', 'rate_bps': 500, 'basis': 'after_adjustment'},
            {'name': '固定费用', 'amount_fen': 7}], tax_fen=10, evidence='个人费用约定及税款凭据', confirmed=True))
        fees = approved['review']['personal_fees']
        self.assertEqual([f['amount_fen'] for f in fees], [26, 34, 7])
        self.assertEqual([f['base_fen'] for f in fees[:2]], [796, 696])
        self.assertEqual(approved['net_fen'], 619)
        paid = self.payout(approved)
        self.rules(rate_bps=1000)
        self.assertEqual(settlements.listing(self.promoter.id, 'statements')['items'][0]['review'], paid['review'])
        self.assertIn('reward_gross', settlements.export_statements(self.promoter.id))

    def test_personal_percentage_api_rejects_forged_amount_and_over_deductions(self):
        draft = self.draft(self.paid())
        self.sign_in(self.admin)
        path = '/api/v1/admin/settlements/statements/' + draft['id'] + '/approve'
        base = {'revision': draft['revision'], 'tax_fen': 0, 'evidence': '个人费用核定', 'confirmed': True}
        fee = {'name': '个人服务', 'mode': 'percent', 'rate_bps': 500, 'basis': 'reward_gross'}
        for invalid in ({**fee, 'amount_fen': 0}, {**fee, 'base_fen': 0}, {**fee, 'rate_bps': 10001}, {**fee, 'basis': 'order_gross'}):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.client.post(path, json={**base, 'personal_fees': [invalid]}).status_code, 422)
        self.assertEqual(self.client.post(path, json={**base, 'personal_fees': [{**fee, 'rate_bps': 10000}, {'name': '其他个人费用', 'amount_fen': 1}]}).status_code, 422)
        response = self.client.post(path, json={**base, 'personal_fees': [fee]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['personal_fen'], 18)

    def test_application_reference_is_explicit_and_original_snapshot_survives_payout(self):
        self.rules(channel_rate_bps=0, shared_fees=[{'name': '服务费', 'mode': 'percent', 'rate_bps': 500, 'basis': 'after_channel'}])
        order = self.paid()
        body = self.application_body([order])
        applied = settlements.apply_request(self.promoter.id, body)
        snapshot = applied['snapshot']
        self.assertEqual(snapshot['unconfirmed_orders'], 1)
        self.assertEqual(snapshot['reference_gross_fen'], 378)
        self.assertEqual(snapshot['items'][0]['reference_fees'][0]['amount_fen'], 99)
        self.assertIsNone(snapshot['net_fen'])
        self.assertIsNone(snapshot['tax_fen'])
        self.assertIsNone(snapshot['personal_fen'])
        self.assertEqual(self.reward(order)['request_id'], applied['id'])
        with self.assertRaises(HTTPException):
            settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']]))
        reviewing = settlements.start_request(self.admin.id, applied['id'], Revision(revision=applied['revision']))
        self.assertEqual(reviewing['status'], 'reviewing')
        self.costs(order)
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']], settlement_request_id=applied['id']))
        approved = self.approve(draft)
        self.assertEqual(settlements.request_detail(self.promoter.id, applied['id'])['request']['status'], 'approved')
        self.assertEqual(self.payout(approved), self.payout(approved))
        final = settlements.request_detail(self.promoter.id, applied['id'])
        self.assertEqual(final['request']['status'], 'paid')
        self.assertEqual(final['request']['snapshot'], snapshot)
        self.assertEqual(final['statement']['net_fen'], 345)
        self.assertNotIn('buyer', final['rewards'][0])

    def test_unknown_channel_fee_stays_unknown_through_application_and_review(self):
        from app.services import settlement_queries

        self.rules(shared_fees=[{'name': '服务费', 'mode': 'percent', 'rate_bps': 500, 'basis': 'after_channel'}])
        unknown = self.paid('unknown-fee')
        self.rules(channel_rate_bps=0, shared_fees=[])
        known = self.another('known-zero-fee')
        quote = settlements.preview_request(self.promoter.id, SettlementPreviewInput(order_ids=[unknown['id'], known['id']]))
        snapshot = quote['snapshot']
        self.assertIsNone(snapshot['reference_gross_fen'])
        self.assertIsNone(snapshot['reference_after_adjustment_fen'])
        self.assertEqual((snapshot['unknown_orders'], snapshot['known_reference_gross_fen']), (1, 398))
        item = next(item for item in snapshot['items'] if item['order_id'] == unknown['id'])
        self.assertIsNone(item['reference_channel_fen'])
        self.assertIsNone(item['reference_commission_fen'])
        self.assertNotIn('amount_fen', item['reference_fees'][0])
        self.assertIsNone(snapshot['channels'][0]['commission_fen'])
        body = SettlementApplyInput(order_ids=[unknown['id'], known['id']], request_key='unknown-fee-application', quote_digest=quote['quote_digest'], confirmed=True)
        request = settlements.apply_request(self.promoter.id, body)
        self.assertEqual(settlements.apply_request(self.promoter.id, body), request)
        self.assertEqual(settlement_queries.summary(self.promoter.id)['pending'], {'count': 1, 'amount_fen': 0, 'unknown': 1})
        detail = settlements.request_detail(self.promoter.id, request['id'])
        self.assertIsNone(detail['difference']['reference_gross_fen'])
        self.assertIsNone(next(row for row in detail['difference']['items'] if row['order_id'] == unknown['id'])['fees'][0]['before_fen'])
        settlements.start_request(self.admin.id, request['id'], Revision(revision=request['revision']))
        self.costs(unknown)
        self.costs(known)
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[], settlement_request_id=request['id']))
        self.assertEqual(settlement_queries.summary(self.promoter.id)['reviewing'], {'count': 1, 'amount_fen': 750, 'unknown': 0})
        self.payout(self.approve(draft))
        self.assertEqual(settlements.request_detail(self.promoter.id, request['id'])['request']['snapshot'], snapshot)

    def test_legacy_unknown_reference_is_masked_without_rewriting_snapshot(self):
        from app.services import settlement_export, settlement_queries

        order = self.paid('legacy-unknown-fee')
        body = self.application_body([order])
        request = settlements.apply_request(self.promoter.id, body)
        stored = request['snapshot']
        stored['reference_gross_fen'] = 398
        stored['reference_after_adjustment_fen'] = 398
        stored['items'][0].update(reference_channel_fen=0, reference_commission_fen=398)
        with db() as conn:
            conn.execute('UPDATE referral_settlement_requests SET snapshot=?::jsonb WHERE id=?', (json.dumps(stored), request['id']))
        self.assertIsNone(settlements.listing(self.promoter.id, 'requests')['items'][0]['snapshot']['reference_gross_fen'])
        self.assertIsNone(settlements.request_detail(self.promoter.id, request['id'])['difference']['reference_gross_fen'])
        self.assertEqual(settlement_queries.summary(self.promoter.id)['pending']['unknown'], 1)
        self.assertTrue(settlement_export.export(self.promoter.id, 'requests', None).startswith(b'PK'))
        with db() as conn:
            self.assertEqual(conn.execute('SELECT snapshot FROM referral_settlement_requests WHERE id=?', (request['id'],)).fetchone()[0], stored)

    def test_list_application_state_matches_server_eligibility(self):
        self.rules(channel_rate_bps=60)
        old = self.create_order('older-unfinished')
        order = self.paid('newer-paid')
        self.assertEqual(settlements.listing(self.promoter.id)['items'][0]['application_state'], 'exception')
        with db() as conn:
            conn.execute("UPDATE mini_orders SET status='closed' WHERE id=?", (old['id'],))
        self.assertEqual(settlements.listing(self.promoter.id)['items'][0]['application_state'], 'available')
        request = settlements.apply_request(self.promoter.id, self.application_body([order]))
        self.assertEqual(settlements.listing(self.promoter.id)['items'][0]['application_state'], 'requested')
        settlements.start_request(self.admin.id, request['id'], Revision(revision=request['revision']))
        self.costs(order)
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[], settlement_request_id=request['id']))
        self.assertEqual(settlements.listing(self.promoter.id)['items'][0]['application_state'], 'statement')
        self.payout(self.approve(draft))
        self.assertEqual(settlements.listing(self.promoter.id)['items'][0]['application_state'], 'paid')

    def test_processing_targets_are_optional_and_preserved_with_application(self):
        self.assertIsNone(settlements.public_rules(self.promoter.id)['review_days'])
        self.rules(channel_rate_bps=60, review_days=3, payout_days=2)
        order = self.paid('timing-target')
        body = self.application_body([order])
        request = settlements.apply_request(self.promoter.id, body)
        self.assertEqual(request['snapshot']['service_terms'], {'review_days': 3, 'payout_days': 2})
        self.rules(review_days=7, payout_days=5)
        self.assertEqual(settlements.public_rules(self.promoter.id)['review_days'], 7)
        self.assertEqual(settlements.request_detail(self.promoter.id, request['id'])['request']['snapshot']['service_terms']['review_days'], 3)
        settlements.start_request(self.admin.id, request['id'], Revision(revision=request['revision']))
        self.costs(order)
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[], settlement_request_id=request['id']))
        self.assertEqual(draft['snapshot']['service_terms'], {'review_days': 3, 'payout_days': 2})
        approved = self.approve(draft)
        listed = settlements.listing(self.promoter.id, 'requests')['items'][0]
        self.assertEqual(listed['statement_summary']['approved_at'], approved['approved_at'])
        current = settlements.get_policy(self.admin.id)
        current.pop('review_days')
        current.pop('payout_days')
        current['reason'] = '兼容旧客户端保存'
        saved = settlements.save_policy(self.admin.id, PolicyInput(**current))
        self.assertEqual((saved['review_days'], saved['payout_days']), (7, 5))
        self.sign_in(self.admin)
        for invalid in (0, -1, 91, 1.5, True):
            response = self.client.put('/api/v1/admin/settlements/policy', json={**saved, 'review_days': invalid, 'reason': '校验处理目标'})
            self.assertEqual(response.status_code, 422)

    def test_application_permissions_ownership_and_confirmation(self):
        order = self.paid()
        base = '/api/v1/admin/settlements/requests'
        admin_access.save_permissions(self.admin.id, self.promoter.id, 1, {'settlements': ['view']})
        self.sign_in(self.promoter)
        self.assertEqual(self.client.post(base + '/preview', json={'order_ids': [order['id']]}).status_code, 403)
        admin_access.save_permissions(self.admin.id, self.promoter.id, 2, {'settlements': ['view', 'create']})
        self.sign_in(self.promoter)
        quote = self.client.post(base + '/preview', json={'order_ids': [order['id']]})
        self.assertEqual(quote.status_code, 200, quote.text)
        data = {'order_ids': [order['id']], 'request_key': 'own-application', 'quote_digest': quote.json()['quote_digest']}
        self.assertEqual(self.client.post(base, json=data).status_code, 422)
        submitted = self.client.post(base, json={**data, 'confirmed': True})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        applied = submitted.json()
        for action in ('start', 'reject'):
            self.assertEqual(self.client.post(base + '/' + applied['id'] + '/' + action, json={'revision': 1, 'reason': '越权测试'}).status_code, 403)
        other = user_store.create_user('other-applicant', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, other.id, 1, {'settlements': ['view', 'create']})
        self.sign_in(other)
        self.assertEqual(self.client.get('/api/v1/admin/settlements/list/requests').json()['total'], 0)
        self.assertEqual(self.client.get(base + '/' + applied['id']).status_code, 404)
        self.assertEqual(self.client.post(base + '/' + applied['id'] + '/cancel', json={'revision': 1, 'reason': '越权撤回'}).status_code, 404)
        self.assertEqual(self.client.post(base + '/preview', json={'order_ids': [order['id']]}).status_code, 404)
        self.assertEqual(self.client.post(base, json={**data, 'confirmed': True}).status_code, 404)
        self.sign_in(self.promoter)
        self.assertEqual(self.client.get(base + '/' + applied['id']).status_code, 200)

    def test_application_quote_stale_after_costs_or_adjustment_requires_new_preview(self):
        order = self.paid()
        body = self.application_body([order])
        self.costs(order)
        with self.assertRaises(HTTPException) as stale:
            settlements.apply_request(self.promoter.id, body)
        self.assertEqual(stale.exception.status_code, 409)
        body = self.application_body([order])
        settlements.manual_adjustment(self.admin.id, AdjustmentInput(beneficiary='admin:' + str(self.promoter.id), amount_fen=-20,
                                     reason='历史核对差额', evidence='差额核对凭据', request_id='quote-adjust-key'))
        with self.assertRaises(HTTPException):
            settlements.apply_request(self.promoter.id, body)
        applied = settlements.apply_request(self.promoter.id, self.application_body([order]))
        self.assertEqual(applied['snapshot']['unconfirmed_orders'], 0)
        self.assertEqual(applied['snapshot']['reference_after_adjustment_fen'], 355)
        self.assertIsNone(applied['snapshot']['net_fen'])

    def test_application_concurrent_idempotence_and_single_open_request(self):
        order = self.paid()
        other = self.another('second-application-order')
        body = self.application_body([order])
        another_body = self.application_body([other], 'different-application')
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: settlements.apply_request(self.promoter.id, body), range(3)))
        self.assertEqual(len({item['id'] for item in results}), 1)
        with self.assertRaises(HTTPException):
            settlements.apply_request(self.promoter.id, body.model_copy(update={'note': '不同内容'}))
        with self.assertRaises(HTTPException):
            settlements.apply_request(self.promoter.id, another_body)
        self.assertEqual(settlements.listing(self.promoter.id, 'requests')['total'], 1)
        applied = results[0]
        cancelled = settlements.close_request(self.promoter.id, applied['id'], VoidInput(revision=applied['revision'], reason='更换申请范围'), cancel=True)
        self.assertEqual(cancelled['status'], 'cancelled')
        self.assertIsNone(self.reward(order)['request_id'])
        self.assertEqual(settlements.apply_request(self.promoter.id, body)['status'], 'cancelled')
        fresh = self.application_body([order, other], 'new-application-key')
        self.assertEqual(len(settlements.apply_request(self.promoter.id, fresh)['snapshot']['items']), 2)

    def test_application_cannot_omit_reserved_orders_or_withdraw_during_review(self):
        order = self.paid()
        other = self.another('batch-application-order')
        applied = settlements.apply_request(self.promoter.id, self.application_body([order, other]))
        reviewing = settlements.start_request(self.admin.id, applied['id'], Revision(revision=1))
        with self.assertRaises(HTTPException):
            settlements.close_request(self.promoter.id, applied['id'], VoidInput(revision=reviewing['revision'], reason='对账中撤回'), cancel=True)
        self.costs(order)
        self.costs(other)
        with self.assertRaises(HTTPException):
            settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']], settlement_request_id=applied['id']))
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id'], other['id']], settlement_request_id=applied['id']))
        current = settlements.request_detail(self.admin.id, applied['id'])['request']
        rejected = settlements.close_request(self.admin.id, applied['id'], VoidInput(revision=current['revision'], reason='凭据待补充'))
        self.assertEqual(rejected['status'], 'rejected')
        detail = settlements.request_detail(self.promoter.id, applied['id'])
        self.assertEqual(detail['statement']['id'], draft['id'])
        self.assertEqual(detail['statement']['status'], 'void')
        self.assertTrue(all(not row['request_id'] and not row['statement_id'] for row in detail['rewards']))
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM referral_settlement_audit WHERE target=? AND kind='settlement_request_rejected'", (applied['id'],)).fetchone()[0], 1)

    def test_application_refund_releases_other_orders_and_blocks_payment(self):
        for stage in ('pending', 'reviewing', 'approved'):
            with self.subTest(stage=stage):
                order = self.another('refund-application-' + stage)
                other = self.another('unrefunded-application-' + stage)
                applied = settlements.apply_request(self.promoter.id, self.application_body([order, other], 'refund-application-' + stage))
                if stage != 'pending':
                    settlements.start_request(self.admin.id, applied['id'], Revision(revision=1))
                if stage == 'approved':
                    self.costs(order)
                    self.costs(other)
                    draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id'], other['id']], settlement_request_id=applied['id']))
                    approved = self.approve(draft)
                self.refund(order)
                current = settlements.request_detail(self.promoter.id, applied['id'])
                self.assertEqual(current['request']['status'], 'invalidated')
                self.assertIsNone(self.reward(other)['request_id'])
                self.assertIsNone(self.reward(other)['statement_id'])
                if stage == 'approved':
                    with self.assertRaises(HTTPException):
                        self.payout(approved)

    def test_application_hold_and_pending_refund_cannot_submit(self):
        self.rules(hold_days=14)
        held = self.paid()
        with self.assertRaises(HTTPException):
            self.application_body([held])
        self.rules(hold_days=0)
        order = self.another('refund-pending-application')
        body = self.application_body([order])
        mini_refunds.request(order['id'], mini_orders.detail(order['id'])['user_id'], RefundInput(reason='测试申请退款'))
        with self.assertRaises(HTTPException):
            settlements.apply_request(self.promoter.id, body)

    def test_application_new_debt_is_applied_without_rewriting_submission(self):
        previous = self.paid()
        self.payout(self.approve(self.draft(previous)))
        order = self.another('application-after-paid')
        applied = settlements.apply_request(self.promoter.id, self.application_body([order]))
        self.refund(previous)
        self.assertEqual(settlements.request_detail(self.promoter.id, applied['id'])['request']['snapshot']['adjustment_fen'], 0)
        settlements.start_request(self.admin.id, applied['id'], Revision(revision=1))
        self.costs(order, 0, 0)
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']], settlement_request_id=applied['id']))
        self.assertEqual(draft['adjustment_fen'], -375)
        final = self.payout(self.approve(draft, personal=0, tax=0))
        self.assertEqual(final['net_fen'], 23)

    def test_scheme_one_floor_rounding_snapshots_and_idempotent_payout(self):
        order = self.paid()
        item = self.draft(order)
        self.assertEqual(item['gross_fen'], 375)  # (1990-12-100)*20%=375.6分，向下取整。
        self.assertIsNone(item['tax_fen'])
        self.assertIsNone(item['net_fen'])
        self.rules(rate_bps=9000, shared_fees=[{'name': '新费用', 'amount_fen': 99}])
        with self.assertRaises(HTTPException):
            self.costs(order)
        item = self.approve(item)
        self.assertEqual(item['net_fen'], 345)
        with self.assertRaises(HTTPException):
            settlements.record_payout(self.admin.id, item['id'], ReceiptInput(revision=item['revision'], amount_fen=346, receipt='错误付款金额'))
        self.assertEqual(self.payout(item), self.payout(item))
        final = settlements.listing(self.admin.id, 'statements')['items'][0]
        self.assertEqual(final['snapshot']['items'][0]['policy']['rate_bps'], 2000)
        self.assertEqual(final['snapshot']['items'][0]['costs']['channel_fee_fen'], 12)
        with self.assertRaises(HTTPException):
            settlements.cancel_statement(self.admin.id, item['id'], VoidInput(revision=final['revision'], reason='不能覆盖历史'))

    def test_disabled_unattributed_and_historical_orders_do_not_earn_renewals(self):
        self.rules(enabled=False)
        first = self.paid()
        self.rules()
        renewed = self.paid('renewal-order')
        self.assertEqual(settlements.listing(self.admin.id)['total'], 0)
        # 模拟升级：只保留历史付款、重新建立一次迁移基线。
        with db() as conn:
            conn.execute('DELETE FROM referral_first_payments')
            settlement_schema.migrate(conn)
            settlement_schema.migrate(conn)
            row = conn.execute('SELECT * FROM referral_first_payments').fetchone()
        self.assertTrue(row['historical'])
        self.assertIn(row['order_id'], [first['id'], renewed['id']])
        self.paid('historical-renewal')
        self.assertEqual(settlements.listing(self.admin.id)['total'], 0)

    def test_pending_costs_and_tax_must_be_explicit_and_wait_period_enforced(self):
        self.rules(hold_days=7)
        order = self.paid()
        self.costs(order)
        with self.assertRaises(HTTPException) as held:
            settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']]))
        self.assertIn('等待期', held.exception.detail['error'])
        self.rules(hold_days=0)
        new = self.another('confirmed-zero-costs')
        with self.assertRaises(HTTPException):
            settlements.create_statement(self.admin.id, StatementInput(order_ids=[new['id']]))
        self.costs(new, 0, 0)
        statement = settlements.create_statement(self.admin.id, StatementInput(order_ids=[new['id']]))
        url = '/api/v1/admin/settlements/statements/' + statement['id'] + '/approve'
        self.assertEqual(self.client.post(url, json={'revision': 1, 'personal_fees': [], 'evidence': '已核对', 'confirmed': True}).status_code, 422)
        self.assertEqual(self.client.post(url, json={'revision': 1, 'personal_fees': [], 'tax_fen': 0, 'evidence': '依法无需代扣', 'confirmed': True}).status_code, 200)

    def test_refund_invalidates_draft_and_never_restores_first_payment(self):
        order = self.paid()
        item = self.draft(order)
        self.refund(order)
        self.assertEqual(settlements.listing(self.admin.id, 'statements')['items'][0]['status'], 'void')
        self.assertEqual(self.reward(order)['status'], 'void')
        with self.assertRaises(HTTPException):
            self.approve(item)
        self.paid('after-refund')
        self.assertEqual(settlements.listing(self.admin.id)['total'], 1)
        self.assertEqual(settlements.listing(self.admin.id, 'adjustments')['total'], 0)

    def test_paid_refund_creates_one_debt_carries_and_preserves_paid_snapshot(self):
        order = self.paid()
        paid = self.payout(self.approve(self.draft(order)))
        self.refund(order)
        adjustments = settlements.listing(self.admin.id, 'adjustments')['items']
        self.assertEqual(len(adjustments), 1)
        self.assertEqual(adjustments[0]['amount_fen'], -375)
        self.assertEqual(settlements.listing(self.admin.id, 'statements')['items'][0], paid)
        another = self.another('smaller-new-reward')
        self.costs(another, 990, 0)  # 200分奖励，抵扣后剩余175分债项。
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[another['id']]))
        approved = self.approve(draft, 0, 0)
        self.assertEqual(approved['net_fen'], -175)
        self.payout(approved)
        self.payout(approved)
        remaining = [row for row in settlements.listing(self.admin.id, 'adjustments')['items'] if row['statement_id'] is None]
        self.assertEqual([row['amount_fen'] for row in remaining], [-175])

    def test_new_refund_debt_invalidates_other_approved_statement(self):
        first = self.paid()
        self.payout(self.approve(self.draft(first)))
        second = self.another('second-new-user')
        approved = self.approve(self.draft(second))
        self.refund(first)
        with self.assertRaises(HTTPException):
            self.payout(approved)
        with db() as conn:
            self.assertEqual(settlements.statement_row(conn, approved['id'])['status'], 'void')
        self.assertIsNone(self.reward(second)['statement_id'])

    def test_refund_in_progress_blocks_payout_and_costs_do_not_become_negative(self):
        order = self.paid()
        self.costs(order, 2000, 0)
        self.assertEqual(self.reward(order)['commission_fen'], 0)
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']]))
        approved = self.approve(draft, 0, 0)
        mini_refunds.request(order['id'], self.viewer.id, RefundInput(reason='退款处理中不可结算'))
        with self.assertRaises(HTTPException):
            self.payout(approved)

    def test_out_of_order_notification_reassigns_first_and_reverses_paid_reward(self):
        earlier = self.create_order('earlier-paid-late-notify')
        later = self.paid('later-paid-first-notify')
        # 未知订单未收敛前禁止结算。关闭后仍有可能收到迟到的成功通知。
        self.costs(later)
        with self.assertRaises(HTTPException):
            settlements.create_statement(self.admin.id, StatementInput(order_ids=[later['id']]))
        with db() as conn:
            conn.execute("UPDATE mini_orders SET status='closed' WHERE id=?", (earlier['id'],))
        item = settlements.create_statement(self.admin.id, StatementInput(order_ids=[later['id']]))
        self.payout(self.approve(item))
        value = self.paid_value(earlier)
        value['success_time'] = datetime.fromtimestamp(int(time.time()) - 10, UTC).isoformat()
        mini_orders.confirm_payment(value)
        self.assertEqual(self.reward(later)['status'], 'void')
        self.assertEqual(self.reward(earlier)['status'], 'pending')
        self.assertEqual(settlements.listing(self.admin.id, 'adjustments')['items'][0]['amount_fen'], -375)

    def test_snapshot_at_creation_no_retroactive_rate_and_user_shares_pay_admin(self):
        inviter = mini_auth.login_public_identity('inviter', referral_code=self.code)['user']
        with db() as conn:
            referrals.initialize_user(conn, self.viewer.id, inviter['referral_code'])
        order = self.create_order()
        self.rules(rate_bps=8000)
        mini_orders.confirm_payment(self.paid_value(order))
        self.assertEqual(self.reward(order)['policy']['rate_bps'], 2000)
        self.assertEqual(self.reward(order)['beneficiary'], 'admin:' + str(self.promoter.id))

    def test_identity_deletion_and_reregistration_preserve_consumed_eligibility(self):
        order = self.paid()
        with db() as conn:
            identity = conn.execute('SELECT wechat_identity FROM mini_users WHERE id=?', (self.viewer.id,)).fetchone()[0]
            mini_auth.delete_user_data(conn, self.viewer.id)
        user = mini_auth.login_public_identity(identity, openid='fixture-openid', referral_code=self.code)['user']
        renewed = mini_orders.create(user['id'], OrderInput(plan_id=self.plan['id'], plan_revision=self.plan['revision'], request_id='reregistered-order'))
        mini_orders.confirm_payment(self.paid_value(renewed))
        self.assertEqual(settlements.listing(self.admin.id)['total'], 1)
        self.assertEqual(self.reward(order)['status'], 'pending')

    def test_manual_adjustment_credit_can_settle_without_new_orders_and_deduplicates(self):
        order = self.paid()
        paid = self.payout(self.approve(self.draft(order)))
        body = AdjustmentInput(beneficiary=paid['beneficiary'], amount_fen=20, request_id='tax-refund-once', reason='实际退税返还', evidence='退税入账凭证')
        self.assertEqual(settlements.manual_adjustment(self.admin.id, body), settlements.manual_adjustment(self.admin.id, body))
        with self.assertRaises(HTTPException):
            settlements.manual_adjustment(self.admin.id, body.model_copy(update={'amount_fen': 30}))
        draft = settlements.create_statement(self.admin.id, StatementInput(beneficiary=paid['beneficiary']))
        approved = self.approve(draft, 0, 0)
        self.assertEqual(approved['net_fen'], 20)
        self.payout(approved)

    def test_concurrent_statement_and_payout_cannot_double_pay(self):
        order = self.paid()
        self.costs(order)
        def attempt(_):
            try:
                return settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']]))
            except HTTPException:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = [item for item in pool.map(attempt, range(2)) if item]
        self.assertEqual(len(result), 1)
        approved = self.approve(result[0])
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: self.payout(approved), range(2)))
        self.assertEqual(settlements.listing(self.admin.id, 'statements')['total'], 1)
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM referral_settlement_audit WHERE kind='record_payout'").fetchone()[0], 1)

    def test_duplicate_fee_categories_and_stale_configuration_are_rejected(self):
        rules = settlements.get_policy(self.admin.id)
        self.rules(rate_bps=3000)
        with self.assertRaises(HTTPException):
            settlements.save_policy(self.admin.id, PolicyInput(**rules, reason='过期配置'))
        order = self.paid()
        for name in ('微信手续费', '个人所得税'):
            with self.assertRaises(HTTPException):
                settlements.confirm_costs(self.admin.id, order['id'], CostsInput(revision=1, channel_fee_fen=12,
                    shared_fees=[{'name': name, 'amount_fen': 12}], evidence='重复扣费不可确认', confirmed=True))
        draft = self.draft(order)
        for name in ('资料服务成本', '个人所得税', '微信手续费'):
            with self.assertRaises(HTTPException):
                settlements.approve(self.admin.id, draft['id'], ReviewInput(revision=draft['revision'], personal_fees=[{'name': name, 'amount_fen': 1}], tax_fen=0, evidence='重复扣费不可批准', confirmed=True))

    def test_admin_scope_routes_export_and_super_only_financial_writes(self):
        order = self.paid()
        self.payout(self.approve(self.draft(order)))
        another = user_store.create_user('other-promoter', 'test-password', role='admin')
        self.sign_in(self.promoter)
        self.assertEqual(self.client.get('/api/v1/admin/settlements/list/rewards').status_code, 403)
        for admin in (self.promoter, another):
            admin_access.save_permissions(self.admin.id, admin.id, 1, {'settlements': ['view', 'export']})
            self.sign_in(admin)
            for kind in ('rewards', 'statements'):
                result = self.client.get('/api/v1/admin/settlements/list/' + kind)
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()['total'], int(admin.id == self.promoter.id))
            self.assertEqual(self.client.get('/api/v1/admin/settlements/policy').status_code, 403)
            self.assertEqual(self.client.post('/api/v1/admin/settlements/statements', json={'order_ids': [order['id']]}).status_code, 403)
            self.assertEqual(self.client.put('/api/v1/admin/settlements/rewards/' + order['id'] + '/costs', json={}).status_code, 403)
            exported = self.client.get('/api/v1/admin/settlements/export')
            self.assertEqual(exported.status_code, 200)
            self.assertEqual(order['id'] in exported.text, admin.id == self.promoter.id)

    def test_virtual_pay_sandbox_and_refund_before_payment_notification(self):
        virtual.VirtualPayContracts.configure(self, wechat_virtual_env=1)
        sandbox = self.create_order('sandbox-first')
        mini_orders.confirm_virtual_payment(virtual.VirtualPayContracts.query_value(self, sandbox))
        self.assertEqual(settlements.listing(self.admin.id)['total'], 0)
        with db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM referral_first_payments').fetchone()[0], 0)
        with patch.object(get_settings(), 'wechat_virtual_env', 0):
            real = self.create_order('real-refund-before-notify')
            mini_refunds.settle_virtual(real['id'], virtual.VirtualPayContracts.query_value(self, real, status=5))
            renew = self.create_order('real-renewal')
            mini_orders.confirm_virtual_payment(virtual.VirtualPayContracts.query_value(self, renew))
        self.assertEqual(settlements.listing(self.admin.id)['total'], 0)

    def test_real_virtual_payment_and_refund_use_same_reward_ledger(self):
        virtual.VirtualPayContracts.configure(self)
        order = self.create_order('virtual-real')
        mini_orders.confirm_virtual_payment(virtual.VirtualPayContracts.query_value(self, order))
        self.payout(self.approve(self.draft(order)))
        mini_refunds.settle_virtual(order['id'], virtual.VirtualPayContracts.query_value(self, order, status=5))
        self.assertEqual(settlements.listing(self.admin.id, 'adjustments')['items'][0]['amount_fen'], -375)

    def test_virtual_refund_without_payment_timestamp_consumes_eligibility(self):
        virtual.VirtualPayContracts.configure(self)
        order = self.create_order('unknown-refund-time')
        value = virtual.VirtualPayContracts.query_value(self, order, status=5)
        value.pop('paid_time')
        mini_refunds.settle_virtual(order['id'], value)
        renewed = self.create_order('renew-after-unknown-refund')
        mini_orders.confirm_virtual_payment(virtual.VirtualPayContracts.query_value(self, renewed, paid_time=int(time.time()) - 1))
        self.assertEqual(settlements.listing(self.admin.id)['total'], 0)

    def test_mixed_percentage_fees_use_independent_bases_and_snapshot_refunds(self):
        fees = [{'name': '技术服务', 'mode': 'percent', 'rate_bps': 500, 'basis': 'after_channel'},
                {'name': '运营分摊', 'mode': 'percent', 'rate_bps': 1000, 'basis': 'order_gross'},
                {'name': '固定资料费', 'amount_fen': 11}]
        self.rules(shared_fees=fees)
        order = self.paid()
        result = settlements.confirm_costs(self.admin.id, order['id'], CostsInput(revision=1, channel_fee_fen=12,
            shared_fees=fees, evidence='服务约定及微信账单已核对', confirmed=True))
        self.assertEqual([fee['amount_fen'] for fee in result['costs']['shared_fees']], [98, 199, 11])
        self.assertEqual([fee.get('base_fen') for fee in result['costs']['shared_fees']], [1978, 1990, None])
        self.assertEqual(result['commission_fen'], 334)
        item = settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']]))
        self.rules(rate_bps=9000, shared_fees=[])
        paid = self.payout(self.approve(item, personal=10, tax=20))
        self.assertEqual(paid['net_fen'], 304)
        self.assertEqual(paid['snapshot']['items'][0]['costs'], result['costs'])
        self.refund(order)
        self.assertEqual(settlements.listing(self.admin.id, 'adjustments')['items'][0]['amount_fen'], -334)
        self.assertEqual(settlements.listing(self.admin.id, 'statements')['items'][0], paid)
        export = settlements.export_statements(self.admin.id)
        self.assertIn('rate_bps', export)
        self.assertIn('base_fen', export)

    def test_percentage_input_rejects_client_calculated_amount_and_invalid_rates(self):
        order = self.paid()
        self.sign_in(self.admin)
        url = '/api/v1/admin/settlements/rewards/' + order['id'] + '/costs'
        invalid = [{'mode': 'percent', 'rate_bps': 500, 'amount_fen': 0},
                   {'mode': 'percent', 'rate_bps': 500, 'base_fen': 0},
                   {'mode': 'percent'}, {'mode': 'fixed'}, {'mode': 'fixed', 'amount_fen': 1, 'rate_bps': 500},
                   {'mode': 'percent', 'rate_bps': -1}, {'mode': 'percent', 'rate_bps': 10001},
                   {'mode': 'percent', 'rate_bps': 0.5}, {'mode': 'percent', 'rate_bps': True},
                   {'mode': 'percent', 'rate_bps': 500, 'basis': 'remaining'}]
        for value in invalid:
            with self.subTest(value=value):
                response = self.client.put(url, json={'revision': 1, 'channel_fee_fen': 12,
                    'shared_fees': [{'name': '技术服务', **value}], 'confirmed': True, 'evidence': '费用凭据'})
                self.assertEqual(response.status_code, 422, response.text)
        self.assertIsNone(self.reward(order)['costs'])

    def test_percentage_rounding_zero_and_excess_costs_do_not_produce_negative_reward(self):
        order = self.paid()
        for fee, channel, expected_cost in [
            ({'name': '零比例', 'mode': 'percent', 'rate_bps': 0}, 0, 0),
            ({'name': '小比例', 'mode': 'percent', 'rate_bps': 1}, 0, 0),
            ({'name': '净额比例', 'mode': 'percent', 'rate_bps': 10000}, 2000, 0),
            ({'name': '实收比例', 'mode': 'percent', 'rate_bps': 10000, 'basis': 'order_gross'}, 2000, 1990),
        ]:
            result = settlements.confirm_costs(self.admin.id, order['id'], CostsInput(
                revision=self.reward(order)['revision'], channel_fee_fen=channel, shared_fees=[fee],
                evidence='费用边界测试凭据', confirmed=True))
            self.assertEqual(result['costs']['shared_fees'][0]['amount_fen'], expected_cost)
            self.assertEqual(result['commission_fen'], 0 if channel == 2000 else 398)

    def test_percentage_duplicate_categories_and_personal_fee_double_deduction_are_rejected(self):
        order = self.paid()
        for name in ('微信手续费', '个人所得税'):
            with self.assertRaises(HTTPException):
                settlements.confirm_costs(self.admin.id, order['id'], CostsInput(revision=1, channel_fee_fen=0,
                    shared_fees=[{'name': name, 'mode': 'percent', 'rate_bps': 100}], evidence='防止重复扣费', confirmed=True))
        settlements.confirm_costs(self.admin.id, order['id'], CostsInput(revision=1, channel_fee_fen=0,
            shared_fees=[{'name': '服务成本', 'mode': 'percent', 'rate_bps': 500}], evidence='服务费用约定', confirmed=True))
        item = settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']]))
        with self.assertRaises(HTTPException):
            settlements.approve(self.admin.id, item['id'], ReviewInput(revision=item['revision'], personal_fees=[
                {'name': ' 服务成本 ', 'amount_fen': 10}], tax_fen=0, confirmed=True, evidence='不能再次扣除'))

    def test_starter_migration_only_updates_pristine_policy_and_preserves_orders(self):
        from app.db import SCHEMA_VERSION, init_db
        order = self.paid()
        original = {'enabled': False, 'beneficiary': 'admin', 'rate_bps': 0, 'hold_days': 7, 'shared_fees': []}
        with db() as conn:
            before = dict(conn.execute('SELECT * FROM mini_orders WHERE id=?', (order['id'],)).fetchone())
            conn.execute('DELETE FROM schema_migrations WHERE version=?', (SCHEMA_VERSION,))
            conn.execute('INSERT INTO schema_migrations(version) VALUES(2026111005) ON CONFLICT DO NOTHING')
            conn.execute('UPDATE referral_policy SET value=?::jsonb,revision=1,updated_at=0 WHERE id=1', (json.dumps(original),))
        init_db(migrate=True)
        rules = settlements.get_policy(self.admin.id)
        self.assertEqual(rules, {**settlement_schema.STARTER_POLICY, 'revision': 2})
        self.assertFalse(rules['enabled'])
        with db() as conn:
            settlement_schema.seed_starter_policy(conn)
            self.assertEqual(dict(conn.execute('SELECT * FROM mini_orders WHERE id=?', (order['id'],)).fetchone()), before)
        self.assertEqual(settlements.get_policy(self.admin.id), rules)
        custom = self.rules(rate_bps=3500, hold_days=21, shared_fees=[{'name': '已约定成本', 'amount_fen': 123}])
        with db() as conn:
            settlement_schema.seed_starter_policy(conn)
        self.assertEqual(settlements.get_policy(self.admin.id), custom)
