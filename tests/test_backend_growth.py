"""Discovery, account service and commerce against disposable DBs and signed fixtures."""

import base64
import hashlib
import json
import time
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import test_backend_catalog as fixtures  # Initializes isolated environment before app imports.
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException

from app import db as database
from app import security
from app.config import get_settings
from app.models.commerce import OrderInput, PlanInput, RefundInput, RefundReview
from app.models.engagement import SubscriptionGrant
from app.models.library import ArchiveCreate
from app.models.mini import MembershipUpdate
from app.routers import commerce, engagement, experience
from app.services import (
    membership_ledger,
    mini_auth,
    mini_messages,
    mini_orders,
    mini_refunds,
    paper_library,
    payment_bills,
    wechat_notices,
)
from app.services.wechat_pay import PaymentError, WeChatPay, configuration


class GrowthBase(unittest.TestCase):
    sign_in = fixtures.PublicCatalogContracts.sign_in
    source = fixtures.PublicCatalogContracts.source
    draft = fixtures.PublicCatalogContracts.draft
    update = fixtures.PublicCatalogContracts.update
    publish = fixtures.PublicCatalogContracts.publish

    def setUp(self):
        fixtures.PublicCatalogContracts.setUp(self)
        for router in (engagement.router, commerce.router, experience.router):
            self.client.app.include_router(router)
        # 这些用例固定验证普通微信支付，不随开发机 .env 的虚拟支付开关漂移。
        for key, value in {"wechat_pay_enabled": False, "wechat_virtual_pay_enabled": False, "wechat_subscribe_template_id": "", "wechat_pay_auto_reconcile": False}.items():
            self.stack.enter_context(patch.object(get_settings(), key, value))

    def tag(self, kind, name):
        result = self.client.post('/api/v1/admin/catalog/tags', json={'kind': kind, 'name': name})
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()


class EngagementContracts(GrowthBase):
    def test_tag_combination_before_pagination_and_visibility(self):
        tags = [self.tag('textbook', '人教版'), self.tag('unit', '第一单元'), self.tag('knowledge', '两位数加法')]
        papers = [self.publish() for _ in range(3)]
        for index, paper in enumerate(papers):
            self.client.put('/api/v1/admin/catalog/papers/' + paper['id'] + '/labels', json={'revision': paper['revision'], 'tag_ids': [tag['id'] for tag in tags[:3 if index < 2 else 1]]}).raise_for_status()
        self.sign_in(self.viewer)
        path = '/api/v1/catalog/papers?limit=1&textbook=' + tags[0]['id'] + '&knowledge=' + tags[2]['id']
        result = self.client.get(path).json()
        self.assertEqual(result['total'], 2)
        self.assertTrue(result['has_more'])
        self.assertEqual(len(result['items'][0]['tags']), 3)
        self.assertNotEqual(result['items'][0]['id'], self.client.get(path + '&offset=1').json()['items'][0]['id'])
        self.sign_in(self.admin)
        tag = tags[2]
        self.client.put('/api/v1/admin/catalog/tags/' + tag['id'], json={**{k: tag[k] for k in ('kind', 'name', 'revision')}, 'is_visible': False}).raise_for_status()
        self.assertEqual(self.client.delete('/api/v1/admin/catalog/tags/' + tag['id'] + '?revision=2').status_code, 422)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get(path).json()['total'], 0)
        self.assertEqual(len(self.client.get('/api/v1/site/catalog-tags').json()['items']), 2)

    def test_tag_validation_conflicts_and_authorization(self):
        tags = [self.tag('term', name) for name in ('上学期', '下学期')]
        paper = self.publish()
        path = '/api/v1/admin/catalog/papers/' + paper['id'] + '/labels'
        self.assertEqual(self.client.put(path, json={'revision': 999, 'tag_ids': []}).status_code, 409)
        self.assertEqual(self.client.put(path, json={'revision': paper['revision'], 'tag_ids': [x['id'] for x in tags]}).status_code, 422)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.put(path, json={'revision': paper['revision'], 'tag_ids': []}).status_code, 401)

    def test_feedback_message_dedup_private_notes_and_read_ownership(self):
        self.sign_in(self.viewer)
        feedback = self.client.post('/api/v1/mini/feedback', json={'kind': 'other', 'body': '请补充使用帮助页面'}).json()
        self.sign_in(self.admin)
        path = '/api/v1/admin/experience/feedback/' + feedback['id']
        body = {'revision': 1, 'status': 'pending', 'reply': '', 'internal_note': 'private-note'}
        self.client.put(path, json=body).raise_for_status()
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get('/api/v1/mini/messages').json()['unread'], 0)
        self.sign_in(self.admin)
        self.client.put(path, json={**body, 'revision': 2, 'reply': '已补充使用说明', 'status': 'resolved'}).raise_for_status()
        self.sign_in(self.viewer)
        inbox = self.client.get('/api/v1/mini/messages').json()
        self.assertEqual(inbox['unread'], 1)
        self.assertNotIn('private-note', json.dumps(inbox))
        message = inbox['items'][0]
        self.sign_in(self.other)
        self.assertEqual(self.client.post('/api/v1/mini/messages/' + message['id'] + '/read').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/mini/feedback/' + feedback['id']).status_code, 404)
        self.sign_in(self.viewer)
        self.assertNotIn('private-note', self.client.get('/api/v1/mini/feedback/' + feedback['id']).text)
        for _ in range(2):
            self.assertEqual(self.client.post('/api/v1/mini/messages/' + message['id'] + '/read').json()['unread'], 0)
        self.assertEqual(self.client.get('/api/v1/mini/messages?unread=true').json()['total'], 0)

    def test_expiry_messages_are_once_per_expiry_and_state(self):
        mini_auth.update_membership(self.admin.id, self.viewer.id, MembershipUpdate(revision=1, membership='vip', vip_expires_at=int(time.time()) + 1000, is_active=True))
        self.assertEqual(mini_messages.inbox(self.viewer.id)['unread'], 1)
        self.assertEqual(mini_messages.inbox(self.viewer.id)['unread'], 1)
        mini_messages.read(self.viewer.id)
        self.assertEqual(mini_messages.inbox(self.viewer.id)['unread'], 0)

    def test_request_dedup_quota_aggregation_and_fulfillment(self):
        paper, draft = self.publish(), self.draft()
        self.sign_in(self.viewer)
        body = {'title': '分数应用题', 'grade': '六年级', 'subject': '数学'}
        result = self.client.post('/api/v1/mini/requests', json=body).json()
        self.assertEqual(self.client.post('/api/v1/mini/requests', json=body).json()['id'], result['id'])
        for i in range(4):
            self.client.post('/api/v1/mini/requests', json={**body, 'title': '测试资料' + str(i)}).raise_for_status()
        self.assertEqual(self.client.post('/api/v1/mini/requests', json={**body, 'title': '超过限额资料'}).status_code, 429)
        self.sign_in(self.other)
        self.assertEqual(self.client.get('/api/v1/mini/requests').json()['total'], 0)
        self.assertEqual(self.client.get('/api/v1/mini/requests/' + result['id']).status_code, 404)
        self.client.post('/api/v1/mini/requests', json=body).raise_for_status()
        self.sign_in(self.admin)
        demand = self.client.get('/api/v1/admin/engagement/requests').json()['demand']
        self.assertEqual(demand[0]['users'], 2)
        path = '/api/v1/admin/engagement/requests/' + result['id']
        resolution = {'revision': 1, 'status': 'fulfilled', 'reply': '已补齐相关资料', 'catalog_id': draft['id']}
        self.assertEqual(self.client.put(path, json=resolution).status_code, 404)
        self.client.put(path, json={**resolution, 'catalog_id': paper['id']}).raise_for_status()
        self.assertEqual(self.client.put(path, json=resolution).status_code, 409)
        self.sign_in(self.viewer)
        self.assertEqual(mini_messages.inbox(self.viewer.id)['items'][0]['target_type'], 'request')
        self.sign_in(self.admin)
        self.update(paper, status='withdrawn').raise_for_status()
        self.sign_in(self.viewer)
        resolved = next(x for x in self.client.get('/api/v1/mini/requests').json()['items'] if x['id'] == result['id'])
        self.assertIsNone(resolved['catalog_id'])
        self.assertIsNone(resolved['paper_title'])

    def test_alternative_editions_match_content_permissions_and_revision(self):
        original = self.source()
        paper = self.publish(self.draft(original))
        with database.db() as conn:
            value = json.loads(conn.execute('SELECT snapshot_json FROM paper_archives WHERE id = ?', (original['id'],)).fetchone()[0])
        value['export_options']['mode'] = 'answersOnly'
        alternate = paper_library.create_paper(self.admin.id, ArchiveCreate(request_id='answer-edition', source_id='answer-source', snapshot=value))
        paper_library.publish_bundle(self.admin.id, alternate['id'], fixtures.bundle())
        path = '/api/v1/admin/catalog/papers/' + paper['id'] + '/editions'
        body = {'revision': paper['revision'], 'kind': 'answers', 'paper_id': alternate['id']}
        self.assertEqual(self.client.put(path, json=body).status_code, 422)
        self.client.put(path, json={**body, 'confirm_publication': True}).raise_for_status()
        self.assertEqual(self.client.delete('/api/v1/library/papers/' + alternate['id']).status_code, 409)
        self.sign_in(self.viewer)
        detail = self.client.get('/api/v1/catalog/papers/' + paper['id']).json()
        self.assertEqual(len(detail['editions']), 2)
        asset = self.client.post('/api/v1/catalog/papers/' + paper['id'] + '/download?edition=answers').json()
        self.assertEqual(self.client.get(asset['url']).status_code, 200)
        self.sign_in(self.admin)
        current = self.client.get('/api/v1/admin/catalog/papers/' + paper['id']).json()
        self.update(current, download_access='vip').raise_for_status()
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get(asset['url']).status_code, 403)
        self.assertNotIn('url', self.client.get('/api/v1/catalog/papers/' + paper['id']).json()['editions'][1])
        self.sign_in(self.admin)
        current = self.client.get('/api/v1/admin/catalog/papers/' + paper['id']).json()
        self.client.post('/api/v1/admin/catalog/papers/' + paper['id'] + '/revision', json={'revision': current['revision'], 'paper_id': self.source()['id'], 'note': '更换题目', 'confirm_publication': True}).raise_for_status()
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get(asset['url']).status_code, 404)

    def test_closure_consent_cancel_conflict_and_deletion(self):
        self.sign_in(self.viewer)
        self.assertEqual(self.client.post('/api/v1/mini/closure', json={'acknowledge': False}).status_code, 422)
        request = self.client.post('/api/v1/mini/closure', json={'acknowledge': True, 'reason': '暂不再使用'}).json()['request']
        self.assertEqual(self.client.delete('/api/v1/mini/closure?revision=99').status_code, 409)
        self.assertEqual(self.client.delete('/api/v1/mini/closure?revision=1').json()['request']['status'], 'cancelled')
        request = self.client.post('/api/v1/mini/closure', json={'acknowledge': True}).json()['request']
        self.sign_in(self.admin)
        path = '/api/v1/admin/engagement/closures/' + request['id']
        body = {'action': 'approve', 'revision': request['revision'], 'reply': '按申请完成注销'}
        self.assertEqual(self.client.put(path, json=body).status_code, 422)
        result = self.client.put(path, json={**body, 'confirm_deletion': True})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['account_name'], '已注销用户')
        self.assertIsNone(result.json()['user_id'])
        with self.assertRaises(HTTPException) as removed:
            mini_auth.get_user(self.viewer.id)
        self.assertEqual(removed.exception.status_code, 401)

    def test_subscription_grants_dedup_and_unknown_delivery_is_not_retried(self):
        settings = get_settings()
        for key, value in {'wechat_app_id': 'wx0123456789abcdef', 'wechat_app_secret': 'fixture', 'wechat_subscribe_template_id': 'fixture-template', 'wechat_subscribe_title_field': 'thing1', 'wechat_subscribe_body_field': 'thing2', 'wechat_subscribe_time_field': 'time3'}.items():
            self.stack.enter_context(patch.object(settings, key, value))
        with database.db() as conn:
            conn.execute('UPDATE mini_users SET wechat_openid_enc = ? WHERE id = ?', (security.encrypt_secret('fixture-openid'), self.viewer.id))
        grant = SubscriptionGrant(template_id='fixture-template', request_id='subscription-one')
        for _ in range(2):
            wechat_notices.grant(self.viewer.id, grant)
        with database.db() as conn:
            self.assertEqual(conn.execute('SELECT credits FROM mini_notice_subscriptions').fetchone()[0], 1)
            mini_messages.notify(conn, self.viewer.id, 'event-one', 'request', '资料已补齐', '请查看新资料', 'request', 'request-one')
        with patch.object(wechat_notices, 'send', side_effect=httpx.ReadTimeout('fixture')) as send:
            self.assertTrue(wechat_notices.dispatch_one())
            self.assertFalse(wechat_notices.dispatch_one())
            self.assertEqual(send.call_count, 1)
        self.assertEqual(wechat_notices.status()['delivery_counts']['unknown'], 1)
        self.assertEqual(mini_messages.inbox(self.viewer.id)['unread'], 1)


class CommerceContracts(GrowthBase):
    def configure(self):
        self.merchant_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.platform_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private, public = self.root / 'merchant.pem', self.root / 'platform.pem'
        private.write_bytes(self.merchant_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        public.write_bytes(self.platform_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        for key, value in {'wechat_pay_enabled': True, 'wechat_app_id': 'wx0123456789abcdef', 'wechat_pay_mchid': '1900000001', 'wechat_pay_serial_no': 'FIXTURE_MERCHANT', 'wechat_pay_private_key_path': str(private), 'wechat_pay_platform_serial': 'PUB_KEY_ID_FIXTURE', 'wechat_pay_platform_key_path': str(public), 'wechat_pay_api_v3_key': '12345678901234567890123456789012', 'wechat_pay_notify_origin': 'https://payments.example.test'}.items():
            self.stack.enter_context(patch.object(get_settings(), key, value))
        with database.db() as conn:
            conn.execute('UPDATE mini_users SET wechat_identity = ?, wechat_openid_enc = ? WHERE id = ?', (mini_auth.digest(get_settings().wechat_app_id + ':fixture-openid'), security.encrypt_secret('fixture-openid'), self.viewer.id))
        self.plan = mini_orders.save_plan(PlanInput(name='测试月会员', days=30, price_fen=1990, is_active=True))

    def create_order(self, key='fixture-order-one'):
        return mini_orders.create(self.viewer.id, OrderInput(plan_id=self.plan['id'], plan_revision=self.plan['revision'], request_id=key))

    def paid_value(self, order):
        return {'out_trade_no': order['id'], 'appid': get_settings().wechat_app_id, 'mchid': get_settings().wechat_pay_mchid, 'payer': {'openid': 'fixture-openid'}, 'amount': {'total': order['amount_fen'], 'currency': 'CNY'}, 'trade_state': 'SUCCESS', 'transaction_id': 'wxtransaction-' + order['id'], 'success_time': datetime.now(UTC).isoformat()}

    def signed_headers(self, raw, timestamp=None):
        timestamp, nonce = str(timestamp or int(time.time())), 'fixture-nonce'
        signature = self.platform_key.sign(timestamp.encode() + b'\n' + nonce.encode() + b'\n' + raw + b'\n', padding.PKCS1v15(), hashes.SHA256())
        return {'Wechatpay-Timestamp': timestamp, 'Wechatpay-Nonce': nonce, 'Wechatpay-Signature': base64.b64encode(signature).decode(), 'Wechatpay-Serial': get_settings().wechat_pay_platform_serial}

    def callback(self, value, kind='TRANSACTION.SUCCESS', event='fixture-event'):
        nonce, associated = 'fixtureNonce', 'transaction'
        encrypted = AESGCM(get_settings().wechat_pay_api_v3_key.encode()).encrypt(nonce.encode(), json.dumps(value).encode(), associated.encode())
        raw = json.dumps({'id': event, 'event_type': kind, 'resource': {'algorithm': 'AEAD_AES_256_GCM', 'nonce': nonce, 'associated_data': associated, 'ciphertext': base64.b64encode(encrypted).decode()}}).encode()
        return raw, self.signed_headers(raw)

    def refund(self, order):
        mini_refunds.request(order['id'], self.viewer.id, RefundInput(reason='测试整单退款申请'))
        refund = mini_orders.detail(order['id'])['refund']
        with patch.object(mini_refunds, 'dispatch'):
            mini_refunds.review(self.admin.id, refund['id'], RefundReview(action='approve', revision=refund['revision'], reply='确认原路退回', confirm_refund=True))
        value = {'out_refund_no': refund['id'], 'refund_id': 'wxrefund-' + refund['id'], 'out_trade_no': order['id'], 'transaction_id': self.paid_value(order)['transaction_id'], 'mchid': get_settings().wechat_pay_mchid, 'amount': {'total': order['amount_fen'], 'refund': order['amount_fen'], 'currency': 'CNY'}, 'refund_status': 'SUCCESS', 'success_time': datetime.now(UTC).isoformat()}
        return value

    def test_unconfigured_has_no_seeded_products_or_checkout(self):
        self.sign_in(self.viewer)
        result = self.client.get('/api/v1/mini/membership/plans').json()
        self.assertFalse(result['checkout_enabled'])
        self.assertEqual(result['items'], [])
        self.assertEqual(self.client.post('/api/v1/mini/orders', json={'plan_id': 'fake', 'plan_revision': 1, 'request_id': 'request-one'}).status_code, 503)
        with patch.object(get_settings(), 'wechat_pay_notify_origin', 'https://[invalid'):
            self.assertFalse(configuration()['ready'])

    def test_server_price_snapshot_idempotency_and_stale_plan(self):
        self.configure()
        order = self.create_order()
        self.assertEqual(self.create_order()['id'], order['id'])
        mini_orders.save_plan(PlanInput(name='更新月会员', days=31, price_fen=2900, is_active=True, revision=1), self.plan['id'])
        self.assertEqual(mini_orders.detail(order['id'])['amount_fen'], 1990)
        with self.assertRaises(HTTPException) as stale:
            self.create_order('different-request')
        self.assertEqual(stale.exception.status_code, 409)
        self.sign_in(self.other)
        self.assertEqual(self.client.get('/api/v1/mini/orders/' + order['id']).status_code, 404)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.post('/api/v1/mini/orders', json={'plan_id': self.plan['id'], 'plan_revision': 2, 'request_id': 'tampered-amount', 'amount_fen': 1}).status_code, 422)

    def test_signed_callback_duplicate_fulfills_once_and_forgery_fails(self):
        self.configure()
        order = self.create_order()
        raw, headers = self.callback(self.paid_value(order))
        path = '/api/v1/payments/wechat/notify'
        self.assertEqual(self.client.post(path, content=raw + b' ', headers=headers).status_code, 400)
        self.assertEqual(self.client.post(path, content=raw, headers=self.signed_headers(raw, int(time.time()) - 1000)).status_code, 400)
        for _ in range(2):
            response = self.client.post(path, content=raw, headers=headers)
            self.assertEqual(response.status_code, 204, response.text)
        self.assertAlmostEqual(mini_auth.get_user(self.viewer.id).vip_expires_at, time.time() + 30 * 86400, delta=3)
        with database.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM mini_membership_grants').fetchone()[0], 1)

    def test_signed_mismatched_amount_identity_tenant_and_malformed_data_rejected(self):
        self.configure()
        order = self.create_order()
        value = self.paid_value(order)
        for changes in ({'amount': {'total': 1, 'currency': 'CNY'}}, {'payer': {'openid': 'someone-else'}}, {'mchid': 'other'}, {'amount': []}, {'payer': None}, {'success_time': '2026-01-01T00:00:00'}, {'success_time': 123}):
            raw, headers = self.callback({**value, **changes})
            self.assertEqual(self.client.post('/api/v1/payments/wechat/notify', content=raw, headers=headers).status_code, 400, changes)
        self.assertEqual(mini_auth.get_user(self.viewer.id).membership, 'regular')
        raw = json.dumps({'id': 'invalid', 'event_type': 'TRANSACTION.SUCCESS', 'resource': []}).encode()
        self.assertEqual(self.client.post('/api/v1/payments/wechat/notify', content=raw, headers=self.signed_headers(raw)).status_code, 400)

    def test_provider_request_signature_and_verified_response(self):
        self.configure()
        order = self.create_order()
        def transport(request):
            self.assertEqual(request.url.host, 'api.mch.weixin.qq.com')
            self.assertIn('WECHATPAY2-SHA256-RSA2048', request.headers['Authorization'])
            fields = dict(item.split('=', 1) for item in request.headers['Authorization'].split(' ', 1)[1].replace('"', '').split(','))
            signed = '\n'.join([request.method, request.url.raw_path.decode(), fields['timestamp'], fields['nonce_str'], request.content.decode(), '']).encode()
            self.merchant_key.public_key().verify(base64.b64decode(fields['signature']), signed, padding.PKCS1v15(), hashes.SHA256())
            self.assertEqual(json.loads(request.content)['amount']['total'], 1990)
            raw = b'{"prepay_id":"fixture_prepay"}'
            return httpx.Response(200, content=raw, headers=self.signed_headers(raw))
        provider = WeChatPay(httpx.MockTransport(transport))
        with database.db() as conn:
            stored = dict(mini_orders.owned(conn, order['id']))
        self.assertEqual(provider.prepay(stored, 'fixture-openid')['prepay_id'], 'fixture_prepay')
        params = provider.payment_parameters('fixture_prepay')
        signed = '\n'.join([get_settings().wechat_app_id, params['timeStamp'], params['nonceStr'], params['package'], '']).encode()
        self.merchant_key.public_key().verify(base64.b64decode(params['paySign']), signed, padding.PKCS1v15(), hashes.SHA256())

    def test_cancel_lease_blocks_cached_prepay_and_releases_after_failure(self):
        self.configure()
        order = self.create_order()
        with database.db() as conn:
            conn.execute("UPDATE mini_orders SET status = 'pending', prepay_id = 'cached-prepay' WHERE id = ?", (order['id'],))
        def close(_):
            with self.assertRaises(HTTPException) as busy:
                mini_orders.pay(order['id'], self.viewer.id)
            self.assertEqual(busy.exception.status_code, 409)
            raise PaymentError('SYSTEM_ERROR')
        with patch.object(WeChatPay, 'close', side_effect=close):
            with self.assertRaises(PaymentError):
                mini_orders.cancel(order['id'], self.viewer.id)
        with database.db() as conn:
            self.assertEqual(mini_orders.owned(conn, order['id'])['lease_until'], 0)
        with patch.object(WeChatPay, 'close'):
            self.assertEqual(mini_orders.cancel(order['id'], self.viewer.id)['status'], 'closed')

    def test_prepay_is_cached_and_blocks_concurrent_cancellation(self):
        self.configure()
        order = self.create_order()
        def prepay(*args):
            with self.assertRaises(HTTPException) as busy:
                mini_orders.cancel(order['id'], self.viewer.id)
            self.assertEqual(busy.exception.status_code, 409)
            return {'prepay_id': 'one-prepay-id'}
        with patch.object(WeChatPay, 'prepay', side_effect=prepay) as dispatch:
            first = mini_orders.pay(order['id'], self.viewer.id)
            second = mini_orders.pay(order['id'], self.viewer.id)
            self.assertEqual(first['payment']['package'], second['payment']['package'])
            self.assertEqual(dispatch.call_count, 1)

    def test_invalid_rsa_keys_make_readiness_false_and_block_checkout(self):
        self.configure()
        from cryptography.exceptions import UnsupportedAlgorithm
        with patch('app.services.wechat_pay._key_material', side_effect=UnsupportedAlgorithm('Unsupported key format')):
            self.assertFalse(configuration()['ready'])
            with self.assertRaises(HTTPException) as error:
                self.create_order()
            self.assertEqual(error.exception.status_code, 503)
        (self.root / 'merchant.pem').write_text('not-a-private-key')
        self.assertFalse(configuration()['ready'])
        with self.assertRaises(HTTPException) as error:
            self.create_order()
        self.assertEqual(error.exception.status_code, 503)

    def test_date_filter_export_and_refund_queue_agree(self):
        self.configure()
        order = self.create_order()
        mini_orders.confirm_payment(self.paid_value(order))
        mini_refunds.request(order['id'], self.viewer.id, RefundInput(reason='测试退款筛选功能'))
        self.assertEqual(mini_orders.listing(status='refund_requested')['total'], 1)
        self.assertEqual(mini_orders.listing(status='refund_processing')['total'], 0)
        self.assertEqual(mini_orders.listing(end_date='2000-01-01')['total'], 0)
        self.assertNotIn(order['id'], payment_bills.export_orders(end_date='2000-01-01'))
        with self.assertRaises(HTTPException):
            mini_orders.listing(start_date='2026-02-31')
        with self.assertRaises(HTTPException):
            mini_orders.listing(start_date='2026-03-01', end_date='2026-02-01')

    def test_payment_races_close_callback_wins(self):
        self.configure()
        order = self.create_order()
        with database.db() as conn:
            conn.execute("UPDATE mini_orders SET status = 'pending' WHERE id = ?", (order['id'],))
        with patch.object(WeChatPay, 'close', side_effect=lambda _: mini_orders.confirm_payment(self.paid_value(order))):
            self.assertEqual(mini_orders.cancel(order['id'], self.viewer.id)['status'], 'paid')

    def test_refund_reflows_later_purchase_and_manual_renewal(self):
        self.configure()
        orders = [self.create_order('purchase-' + str(index)) for index in range(3)]
        for order in orders:
            mini_orders.confirm_payment(self.paid_value(order))
        with database.db() as conn:
            membership_ledger.append(conn, conn.execute('SELECT * FROM mini_users WHERE id = ?', (self.viewer.id,)).fetchone(), 10)
        expiry = mini_auth.get_user(self.viewer.id).vip_expires_at
        for index in (0, 2):
            value = self.refund(orders[index])
            self.assertEqual(mini_refunds.apply(value)['status'], 'refunded')
            mini_refunds.apply(value)
        self.assertAlmostEqual(mini_auth.get_user(self.viewer.id).vip_expires_at, expiry - 60 * 86400, delta=4)
        with database.db() as conn:
            grants = conn.execute('SELECT starts_at, ends_at FROM mini_membership_grants WHERE revoked_at IS NULL ORDER BY starts_at').fetchall()
            self.assertEqual(grants[0]['ends_at'], grants[1]['starts_at'])
            self.assertEqual(grants[1]['ends_at'] - grants[1]['starts_at'], 10 * 86400)

    def test_refund_preserves_absolute_override_and_disabled_status(self):
        self.configure()
        order = self.create_order()
        mini_orders.confirm_payment(self.paid_value(order))
        user = mini_auth.get_user(self.viewer.id)
        with database.db() as conn:
            revision = conn.execute('SELECT revision FROM mini_users WHERE id = ?', (user.id,)).fetchone()[0]
        mini_auth.update_membership(self.admin.id, user.id, MembershipUpdate(revision=revision, membership='vip', vip_expires_at=None, is_active=False))
        mini_refunds.apply(self.refund(order))
        with database.db() as conn:
            row = conn.execute('SELECT vip_expires_at, is_active FROM mini_users WHERE id = ?', (user.id,)).fetchone()
            self.assertIsNone(row['vip_expires_at'])
            self.assertFalse(row['is_active'])

    def test_refund_requires_review_and_rejects_partial_or_conflicting_callback(self):
        self.configure()
        order = self.create_order()
        mini_orders.confirm_payment(self.paid_value(order))
        value = self.refund(order)
        for changes in ({'amount': None}, {'amount': {'total': 1990, 'refund': 100}}, {'success_time': '2000-01-01T00:00:00+00:00'}):
            with self.assertRaises(HTTPException) as invalid:
                mini_refunds.apply({**value, **changes})
            self.assertEqual(invalid.exception.status_code, 400)
        raw, headers = self.callback(value, 'REFUND.CLOSED')
        self.assertEqual(self.client.post('/api/v1/payments/wechat/refund-notify', content=raw, headers=headers).status_code, 400)
        raw, headers = self.callback(value, 'REFUND.SUCCESS')
        self.assertEqual(self.client.post('/api/v1/payments/wechat/refund-notify', content=raw, headers=headers).status_code, 204)

    def test_closure_blocks_open_orders_and_retains_anonymous_financial_record(self):
        self.configure()
        order = self.create_order()
        self.sign_in(self.viewer)
        self.assertEqual(self.client.post('/api/v1/mini/closure', json={'acknowledge': True}).status_code, 409)
        mini_orders.confirm_payment(self.paid_value(order))
        closure = self.client.post('/api/v1/mini/closure', json={'acknowledge': True}).json()['request']
        mini_refunds.request(order['id'], self.viewer.id, RefundInput(reason='关闭账号前退款'))
        self.sign_in(self.admin)
        path = '/api/v1/admin/engagement/closures/' + closure['id']
        body = {'revision': closure['revision'], 'action': 'approve', 'reply': '完成注销申请', 'confirm_deletion': True}
        self.assertEqual(self.client.put(path, json=body).status_code, 409)
        value = self.refund(order)
        mini_refunds.apply(value)
        self.client.put(path, json=body).raise_for_status()
        with database.db() as conn:
            row = mini_orders.owned(conn, order['id'])
            self.assertIsNone(row['user_id'])
            self.assertEqual(row['payer_enc'], '')
            self.assertEqual(row['status'], 'refunded')

    def test_bill_download_url_hash_and_truncation_validation(self):
        self.configure()
        content = '微信订单号,商户订单号,交易状态,订单金额\n总交易单数\n`0\n'.encode()
        def transport(request):
            if request.url.path == '/v3/bill/tradebill':
                raw = json.dumps({'download_url': 'https://api.mch.weixin.qq.com/v3/bill/downloadurl?token=fixture', 'hash_type': 'SHA1', 'hash_value': hashlib.sha1(content).hexdigest()}).encode()
                return httpx.Response(200, content=raw, headers=self.signed_headers(raw))
            return httpx.Response(200, content=content)
        provider = WeChatPay(httpx.MockTransport(transport))
        self.assertEqual(payment_bills.parse_bill(provider.bill('2026-01-01')), [])
        with patch.object(provider, 'request', return_value={'download_url': 'https://other.example/v3/bill/downloadurl'}):
            with self.assertRaises(PaymentError):
                provider.bill('2026-01-01')
        with self.assertRaises(PaymentError):
            payment_bills.parse_bill(content.decode().split('总交易')[0])
        for value in ('NaN', '-1', '0.001'):
            with self.assertRaises(PaymentError):
                payment_bills.money(value)

    def test_separate_payment_and_refund_bills_count_same_day_correctly(self):
        self.configure()
        order = self.create_order()
        mini_orders.confirm_payment(self.paid_value(order))
        refund = self.refund(order)
        mini_refunds.apply(refund)
        day = (datetime.now(payment_bills.ZONE) - timedelta(days=1)).date()
        stamp = int(datetime.combine(day, datetime.min.time(), payment_bills.ZONE).timestamp()) + 3600
        with database.db() as conn:
            conn.execute('UPDATE mini_orders SET paid_at = ? WHERE id = ?', (stamp, order['id']))
            conn.execute('UPDATE mini_refunds SET completed_at = ? WHERE id = ?', (stamp + 10, refund['out_refund_no']))
        header = '微信订单号,商户订单号,交易状态,订单金额,商户退款单号,申请退款金额,退款状态\n'
        # A payment can already be marked REFUND when the daily SUCCESS bill is generated.
        record = f"`{refund['transaction_id']},`{order['id']},`REFUND,`19.90,`{refund['out_refund_no']},`19.90,`SUCCESS\n总交易单数\n`1\n"
        with patch.object(WeChatPay, 'bill', return_value=header + record) as bill:
            result = payment_bills.reconcile(self.admin.id, day.isoformat())
        self.assertEqual([call.args[1] for call in bill.call_args_list], ['SUCCESS', 'REFUND'])
        self.assertEqual(result['summary']['differences'], 0)
        self.assertEqual(result['summary']['wechat_paid_fen'], 1990)
        self.assertEqual(result['summary']['wechat_refunded_fen'], 1990)
        with database.db() as conn:
            conn.execute("UPDATE mini_orders SET plan_name = '=FORMULA()' WHERE id = ?", (order['id'],))
        self.assertIn("'=FORMULA()", payment_bills.export_orders())
