"""曾缺少响应模型的运营读写入口使用真实服务验证，而非简化的成功替身。"""

import unittest

from app.db import db
from app.routers import engagement, settlements, site
from tests import test_backend_catalog as fixtures


class PlatformResponseContracts(unittest.TestCase):
    sign_in = fixtures.PublicCatalogContracts.sign_in

    def setUp(self):
        fixtures.PublicCatalogContracts.setUp(self)
        for router in (site.router, site.admin_router, engagement.router, settlements.router):
            self.client.app.include_router(router)

    def test_site_create_list_update_contracts(self):
        response = self.client.post('/api/v1/admin/site/categories', json={'name': '契约分类'})
        self.assertEqual(response.status_code, 201, response.text)
        category = response.json()
        response = self.client.put('/api/v1/admin/site/categories/' + category['id'], json={'revision': category['revision'], 'name': '更新分类'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['name'], '更新分类')
        response = self.client.get('/api/v1/admin/site/categories')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['items'][0]['id'], category['id'])
        notice = self.client.post('/api/v1/admin/site/notices', json={'title': '公告', 'body': '通知正文'})
        self.assertEqual(notice.status_code, 201, notice.text)
        item = notice.json()
        response = self.client.put('/api/v1/admin/site/notices/' + item['id'], json={'revision': item['revision'], 'title': '新版公告', 'body': '通知正文', 'is_visible': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['state'], 'active')
        self.assertEqual(self.client.get('/api/v1/admin/site/notices').json()['items'][0]['id'], item['id'])
        response = self.client.get('/api/v1/site/home')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['notices']['popup'] or response.json()['notices']['banner'])

    def test_admin_observation_nullable_payee_and_dictionary_contracts(self):
        with db() as conn:
            conn.execute('INSERT INTO generation_requests(user_id,request_id,kind,payload_hash,status,created_at) VALUES (?,?,?,?,?,?)',
                         (self.admin.id, 'contract-running', 'batch', 'hash', 'running', 1))
        traces = self.client.get('/api/v1/admin/generation-traces')
        self.assertEqual(traces.status_code, 200, traces.text)
        self.assertEqual(traces.json()['requests'][0]['request_id'], 'contract-running')
        self.assertIsNone(traces.json()['requests'][0]['trace'])
        for path in ('/api/v1/admin/feedbacks', '/api/v1/admin/access/catalog', '/api/v1/admin/site/dictionary/unlisted',
                     '/api/v1/admin/engagement/closures', '/api/v1/admin/settlements/bills'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, (path, response.text))
        payee = self.client.get('/api/v1/admin/settlements/payee')
        self.assertEqual(payee.status_code, 200, payee.text)
        self.assertIsNone(payee.json())
        response = self.client.post('/api/v1/admin/site/dictionary/adopt', json={'kind': 'grade', 'values': ['契约年级']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['added'], 1)
        repeated = self.client.post('/api/v1/admin/site/dictionary/adopt', json={'kind': 'grade', 'values': ['契约年级']})
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()['added'], 0)

    def test_delivery_status_accepts_empty_and_partial_counts(self):
        from app.services.mini_messages import notify

        response = self.client.get('/api/v1/admin/engagement/delivery-status')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['delivery_counts'], {})
        with db() as conn:
            for state in ('pending', 'sent'):
                notify(conn, self.viewer.id, 'delivery-' + state, 'order', '订单提醒', '测试投递状态')
                identifier = conn.execute('SELECT id FROM mini_notifications WHERE user_id=? AND event_key=?',
                                          (self.viewer.id, 'delivery-' + state)).fetchone()[0]
                conn.execute('INSERT INTO mini_notice_deliveries(notification_id,status,updated_at) VALUES (?,?,?)',
                             (identifier, state, 1))
        response = self.client.get('/api/v1/admin/engagement/delivery-status')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['delivery_counts'], {'pending': 1, 'sent': 1})
