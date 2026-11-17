"""推广归属、支付快照与后台范围：仅使用隔离的 lc_test_* 数据库。"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import httpx
import test_backend_growth as growth
import test_backend_virtual_pay as virtual
from fastapi import HTTPException

from app import referral_schema
from app.db import db
from app.models.commerce import RefundInput
from app.routers import referrals as referral_routes
from app.services import admin_access, mini_auth, mini_orders, mini_refunds, payment_bills, referrals, user_store


class ReferralContracts(growth.GrowthBase):
    configure = growth.CommerceContracts.configure
    create_order = growth.CommerceContracts.create_order
    paid_value = growth.CommerceContracts.paid_value

    def setUp(self):
        super().setUp()
        self.client.app.include_router(referral_routes.router)
        self.a = user_store.create_user('promoter-a', 'test-password', role='admin')
        self.b = user_store.create_user('promoter-b', 'test-password', role='admin')
        self.ca = referrals.admin_code(self.admin.id, self.a.id)['code']
        self.cb = referrals.admin_code(self.admin.id, self.b.id)['code']
        self.stack.enter_context(patch.object(referral_routes, 'allow', return_value=True))

    def value(self, user_id):
        with db() as conn:
            return conn.execute('SELECT referral FROM mini_users WHERE id=?', (user_id,)).fetchone()[0]

    def attach(self, user_id, code):
        with db() as conn:
            referrals.initialize_user(conn, user_id, code)

    def test_wechat_first_registration_and_user_sharing(self):
        with patch.object(mini_auth, 'exchange_code', return_value='wechat-referral-one'):
            response = self.client.post('/api/v1/mini/login', json={'code': 'wechat-once', 'referral_code': self.ca})
        self.assertEqual(response.status_code, 200, response.text)
        first = response.json()['user']
        self.assertEqual(self.value(first['id'])['admin_id'], self.a.id)
        self.assertNotIn('referral', first)
        child = mini_auth.login_public_identity('wechat-referral-child', referral_code=first['referral_code'])['user']
        relation = self.value(child['id'])
        self.assertEqual((relation['admin_id'], relation['inviter_id'], relation['source']), (self.a.id, first['id'], 'user'))
        mini_auth.login_public_identity('wechat-referral-one', referral_code=self.cb)
        self.assertEqual(self.value(first['id'])['admin_id'], self.a.id)
        self.assertEqual(mini_auth.get_user(first['id']).referral_code, first['referral_code'])

    def test_natural_invalid_disabled_and_legacy_logins(self):
        for number, code in enumerate(('', 'a_' + '0' * 20, 'u_' + '0' * 20)):
            result = mini_auth.login_public_identity('natural-' + str(number), referral_code=code)['user']
            self.assertEqual(self.value(result['id'])['source'], 'natural')
            mini_auth.login_public_identity('natural-' + str(number), referral_code=self.ca)
            self.assertEqual(self.value(result['id'])['source'], 'natural')
        with db() as conn:
            conn.execute('UPDATE users SET is_active=0 WHERE id=?', (self.a.id,))
            conn.execute("UPDATE mini_users SET referral='{}'::jsonb || '{\"source\":\"legacy\"}'::jsonb WHERE id=?", (self.viewer.id,))
        result = mini_auth.login_public_identity('disabled-promoter', referral_code=self.ca)['user']
        self.assertEqual(self.value(result['id'])['source'], 'natural')
        mini_auth.login_password(self.viewer.username, 'test-password')
        self.assertEqual(self.value(self.viewer.id)['source'], 'legacy')

    def test_registration_contract_and_concurrent_identity(self):
        response = self.client.post('/api/v1/mini/register', json={'username': 'h5-referral', 'password': 'test-password', 'referral_code': self.ca})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.value(response.json()['user']['id'])['admin_id'], self.a.id)
        self.assertEqual(self.client.post('/api/v1/mini/login', json={'code': 'x', 'referral_code': 'arbitrary-admin-id'}).status_code, 422)
        self.assertEqual(self.client.post('/api/v1/mini/login', json={'code': 'x', 'admin_id': self.a.id}).status_code, 422)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda code: mini_auth.login_public_identity('same-concurrent-identity', referral_code=code), [self.ca, self.cb]))
        self.assertEqual(results[0]['user']['id'], results[1]['user']['id'])
        self.assertIn(self.value(results[0]['user']['id'])['admin_id'], (self.a.id, self.b.id))

    def test_user_listing_preserves_all_attribution_shapes(self):
        natural = mini_auth.login_public_identity('contract-natural')['user']
        invited = mini_auth.login_public_identity('contract-natural-invite', referral_code=natural['referral_code'])['user']
        self.attach(self.other.id, self.ca)
        with db() as conn:
            conn.execute("UPDATE mini_users SET referral='{\"source\":\"legacy\"}'::jsonb WHERE id=?", (self.viewer.id,))
        self.sign_in(self.admin)
        response = self.client.get('/api/v1/admin/referrals/users')
        self.assertEqual(response.status_code, 200, response.text)
        items = {item['id']: item for item in response.json()['items']}
        for identifier in (natural['id'], invited['id'], self.viewer.id, self.other.id):
            with self.subTest(identifier=identifier):
                self.assertEqual(items[identifier]['referral'], self.value(identifier))
        self.assertNotIn('admin_id', items[natural['id']]['referral'])
        self.assertIsNone(items[invited['id']]['referral']['admin_id'])
        self.assertEqual(items[self.viewer.id]['referral'], {'source': 'legacy'})
        unassigned = self.client.get('/api/v1/admin/referrals/users?admin_id=0').json()
        self.assertEqual({item['id'] for item in unassigned['items']}, {natural['id'], invited['id'], self.viewer.id})
        response = self.client.put('/api/v1/admin/referrals/users/' + self.viewer.id,
                                   json={'admin_id': self.a.id, 'reason': '核对历史登记'})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.get('/api/v1/admin/referrals/users?q=' + self.viewer.username)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['items'][0]['referral'], self.value(self.viewer.id))
        self.assertNotIn('code', response.json()['items'][0]['referral'])
        self.assertEqual(self.client.get('/api/v1/admin/referrals/users?q=nonexistent-person').json()['items'], [])

    def test_quality_accepts_unassigned_and_unobserved_cohorts(self):
        self.sign_in(self.admin)
        response = self.client.get('/api/v1/admin/referrals/quality')
        self.assertEqual(response.status_code, 200, response.text)
        items = response.json()['items']
        self.assertEqual({item['days'] for item in items}, {30, 60, 90})
        for item in items:
            self.assertIsNone(item['admin_name'])
            self.assertEqual(item['observed_users'], 0)
            for field in ('pay_rate_bps', 'renewal_rate_bps', 'value_per_user_fen'):
                self.assertIsNone(item[field])
        with db() as conn:
            conn.execute('UPDATE mini_users SET created_at=? WHERE id=?',
                         (int(time.time()) - 100 * 86400, self.viewer.id))
        response = self.client.get('/api/v1/admin/referrals/quality')
        self.assertEqual(response.status_code, 200, response.text)
        for item in response.json()['items']:
            self.assertEqual(item['observed_users'], 1)
            self.assertEqual(item['pay_rate_bps'], 0)
            self.assertEqual(item['value_per_user_fen'], 0)
            self.assertIsNone(item['renewal_rate_bps'])
        self.assertEqual(self.client.get('/api/v1/admin/referrals/quality?start_date=2099-01-01').json()['items'], [])

    def test_membership_order_endpoints_preserve_attribution_snapshots(self):
        self.configure()
        self.sign_in(self.admin)
        relations = [
            {'source': 'legacy'},
            {'source': 'natural', 'bound_at': 1794000000},
            {'source': 'manual', 'admin_id': self.a.id, 'admin_name': 'promoter-a', 'bound_at': 1794000000},
            {'source': 'user', 'admin_id': None, 'admin_name': '', 'inviter_id': self.other.id,
             'inviter_type': 'user', 'inviter_name': self.other.username, 'code': self.other.referral_code},
            {'source': 'admin', 'admin_id': self.a.id, 'admin_name': 'promoter-a', 'code': self.ca,
             'campaign_id': 'historical-campaign', 'campaign_name': '历史活动', 'campaign_source': '微信群'},
        ]
        for index, relation in enumerate(relations):
            with self.subTest(source=relation['source']):
                with db() as conn:
                    conn.execute('UPDATE mini_users SET referral=?::jsonb WHERE id=?', (json.dumps(relation), self.viewer.id))
                order = self.create_order('contract-attribution-' + str(index))
                snapshot = {**relation, 'buyer_id': self.viewer.id}
                detail = self.client.get('/api/v1/admin/commerce/orders/' + order['id'])
                self.assertEqual(detail.status_code, 200, detail.text)
                self.assertEqual(detail.json()['referral'], snapshot)
                listing = self.client.get('/api/v1/admin/commerce/orders?q=' + order['id'])
                self.assertEqual(listing.status_code, 200, listing.text)
                self.assertEqual(listing.json()['items'][0]['referral'], snapshot)
                closed = self.client.post('/api/v1/admin/commerce/orders/' + order['id'] + '/cancel')
                self.assertEqual(closed.status_code, 200, closed.text)
                self.assertEqual(closed.json()['referral'], snapshot)
                self.assertEqual(closed.json()['status'], 'closed')

    def test_scoped_users_summary_codes_and_exports(self):
        self.attach(self.viewer.id, self.ca)
        self.attach(self.other.id, self.cb)
        self.sign_in(self.a)
        self.assertEqual(self.client.get('/api/v1/admin/referrals/users').status_code, 403)
        admin_access.save_permissions(self.admin.id, self.a.id, 1, {'referrals': ['view']})
        self.assertEqual(self.client.post('/api/v1/admin/referrals/code', json={}).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/referrals/export/users').status_code, 403)
        for endpoint in ('users', 'summary', 'orders'):
            self.assertEqual(self.client.get('/api/v1/admin/referrals/' + endpoint + '?admin_id=' + str(self.b.id)).status_code, 403)
        result = self.client.get('/api/v1/admin/referrals/users?limit=1').json()
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['id'], self.viewer.id)
        self.assertEqual(self.client.get('/api/v1/admin/referrals/summary').json()['registrations'], 1)
        admin_access.save_permissions(self.admin.id, self.a.id, 2, {'referrals': ['create', 'export']})
        self.assertEqual(self.client.post('/api/v1/admin/referrals/code', json={}).json()['code'], self.ca)
        self.assertEqual(self.client.post('/api/v1/admin/referrals/code', json={'admin_id': self.b.id}).status_code, 403)
        exported = self.client.get('/api/v1/admin/referrals/export/users').text
        self.assertIn(self.viewer.username, exported)
        self.assertNotIn(self.other.username, exported)
        self.assertEqual(self.client.get('/api/v1/admin/referrals/users?start_date=invalid').status_code, 422)
        self.assertEqual(self.client.get('/api/v1/admin/referrals/users?start_date=2026-11-11&end_date=2026-11-01').status_code, 422)

    def test_historical_supplement_is_super_only_audited_and_not_retroactive(self):
        self.configure()
        with db() as conn:
            conn.execute("UPDATE mini_users SET referral='{\"source\":\"legacy\"}'::jsonb WHERE id=?", (self.viewer.id,))
        old_order = self.create_order()
        self.sign_in(self.a)
        admin_access.save_permissions(self.admin.id, self.a.id, 1, {'referrals': ['view']})
        url = '/api/v1/admin/referrals/users/' + self.viewer.id
        self.assertEqual(self.client.put(url, json={'admin_id': self.a.id, 'reason': '历史推广补录'}).status_code, 403)
        self.sign_in(self.admin)
        response = self.client.put(url, json={'admin_id': self.a.id, 'reason': '核对历史登记表'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.put(url, json={'admin_id': self.b.id, 'reason': '不能覆盖归属'}).status_code, 409)
        self.assertEqual(self.client.get(url + '/audit').json()['items'][0]['reason'], '核对历史登记表')
        self.assertEqual(mini_orders.detail(old_order['id'])['referral']['source'], 'legacy')
        self.assertEqual(self.create_order()['id'], old_order['id'])
        renewed = self.create_order('after-supplement')
        self.assertEqual(mini_orders.detail(renewed['id'])['referral']['admin_id'], self.a.id)

    def test_orders_payment_refund_and_scope_survive_identity_changes(self):
        self.configure()
        self.attach(self.viewer.id, self.ca)
        first = self.create_order()
        second = self.create_order('renewal-order')
        for order in (first, second):
            mini_orders.confirm_payment(self.paid_value(order))
        refund = mini_refunds.request(first['id'], self.viewer.id, RefundInput(reason='测试退款归属保持'))
        with db() as conn:
            conn.execute("UPDATE mini_refunds SET status='processing' WHERE id=?", (refund['refund']['id'],))
            conn.execute('UPDATE users SET username=? WHERE id=?', ('renamed-promoter', self.a.id))
        mini_refunds.apply({'out_refund_no': refund['refund']['id'], 'out_trade_no': first['id'], 'transaction_id': 'wxtransaction-' + first['id'],
                             'refund_id': 'provider-refund-12345', 'refund_status': 'SUCCESS', 'success_time': self.paid_value(first)['success_time'],
                             'amount': {'total': 1990, 'refund': 1990, 'currency': 'CNY'}})
        self.attach(self.viewer.id, self.cb)
        summary = referrals.summary(self.a.id)
        self.assertEqual((summary['paid_fen'], summary['refunded_fen'], summary['net_fen'], summary['paying_users']), (3980, 1990, 1990, 1))
        self.assertEqual(referrals.summary(self.b.id)['orders'], 0)
        self.assertEqual(mini_orders.detail(first['id'])['referral']['admin_name'], 'promoter-a')
        admin_access.save_permissions(self.admin.id, self.b.id, 1, {'orders': ['view', 'export', 'run', 'update'], 'referrals': ['export']})
        self.sign_in(self.b)
        for endpoint in ('/api/v1/admin/commerce/orders', '/api/v1/admin/referrals/orders'):
            self.assertEqual(self.client.get(endpoint).json()['total'], 0)
        for response in (self.client.get('/api/v1/admin/commerce/orders/' + first['id']),
                         self.client.post('/api/v1/admin/commerce/orders/' + first['id'] + '/sync'),
                         self.client.post('/api/v1/admin/commerce/refunds/' + refund['refund']['id'] + '/sync')):
            self.assertEqual(response.status_code, 404, response.text)
        self.assertNotIn(first['id'], self.client.get('/api/v1/admin/referrals/export/orders').text)
        self.assertIn('promoter-a', payment_bills.export_orders(admin_actor_id=self.a.id))

    def test_virtual_payment_uses_same_snapshot(self):
        virtual.VirtualPayContracts.configure(self)
        self.attach(self.viewer.id, self.ca)
        order = self.create_order()
        mini_orders.confirm_virtual_payment(virtual.VirtualPayContracts.query_value(self, order))
        mini_refunds.settle_virtual(order['id'], {'order_id': order['id'], 'status': 5, 'order_fee': 1990, 'refund_fee': 1990})
        self.assertEqual(mini_orders.detail(order['id'])['referral']['admin_id'], self.a.id)
        self.assertEqual(referrals.summary(self.a.id)['net_fen'], 0)

    def test_migration_preserves_unknown_history_and_existing_binding(self):
        self.attach(self.viewer.id, self.ca)
        with db() as conn:
            before = self.value(self.viewer.id)
            conn.execute("UPDATE mini_users SET referral_code='',referral='{\"source\":\"legacy\"}'::jsonb WHERE id=?", (self.other.id,))
            referral_schema.migrate(conn)
            referral_schema.migrate(conn)
        self.assertEqual(self.value(self.viewer.id), before)
        self.assertEqual(self.value(self.other.id)['source'], 'legacy')
        self.assertTrue(mini_auth.get_user(self.other.id).referral_code.startswith('u_'))

    def test_qrcode_provider_payload_and_error_handling(self):
        from app.config import get_settings
        with patch.object(get_settings(), 'wechat_app_id', 'fixture'), patch.object(get_settings(), 'wechat_app_secret', 'fixture'), \
                patch.object(referrals.wechat_notices, 'access_token', return_value='private-token'), \
                patch.object(referrals.wechat_notices, '_http_client') as client:
            client.return_value.post.return_value = httpx.Response(200, content=b'\x89PNG\r\n\x1a\nfixture', request=httpx.Request('POST', 'https://api.weixin.qq.com'))
            image, kind = referrals.qrcode(self.a.id, env_version='trial')
            self.assertEqual(kind, 'image/png')
            self.assertTrue(image)
            self.assertEqual(client.return_value.post.call_args.kwargs['json']['scene'], self.ca)
            self.assertEqual(client.return_value.post.call_args.kwargs['json']['env_version'], 'trial')
            client.return_value.post.return_value = httpx.Response(200, json={'errcode': 40013}, request=httpx.Request('POST', 'https://api.weixin.qq.com'))
            with self.assertRaises(HTTPException) as failure:
                referrals.qrcode(self.a.id)
            self.assertEqual(failure.exception.status_code, 502)

    def test_statistics_do_not_double_count_deleted_buyers(self):
        self.configure()
        self.attach(self.viewer.id, self.ca)
        for key in ('delete-order-one', 'delete-order-two'):
            order = self.create_order(key)
            mini_orders.confirm_payment(self.paid_value(order))
        with db() as conn:
            conn.execute('DELETE FROM mini_users WHERE id=?', (self.viewer.id,))
        self.assertEqual(referrals.summary(self.a.id)['paying_users'], 1)
        self.assertEqual(referrals.summary(self.a.id)['paid_fen'], 3980)
