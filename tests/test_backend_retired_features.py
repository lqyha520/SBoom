"""已下线功能没有接口或权限入口，历史授权仍可更新。"""
import unittest

from fastapi.testclient import TestClient

from app import admin_permissions
from app.main import app
from tests import test_backend_catalog as fixtures


class RetiredFeatureTests(unittest.TestCase):
    setUp = fixtures.PublicCatalogContracts.setUp
    sign_in = fixtures.PublicCatalogContracts.sign_in

    def test_removed_routes_are_unavailable_to_logged_in_users(self):
        client = TestClient(app)
        self.addCleanup(client.close)
        self.sign_in(self.admin)
        client.cookies.update(self.client.cookies)
        self.assertEqual(client.get('/api/v1/admin/generation-reviews').status_code, 404)
        # 静态页面兜底对未匹配的写请求返回 405；两种响应均不会执行审核。
        self.assertIn(client.put('/api/v1/admin/generation-reviews/1/old/1', json={}).status_code, (404, 405))
        self.sign_in(self.viewer)
        client.cookies.clear()
        client.headers['Authorization'] = self.client.headers['Authorization']
        self.assertEqual(client.get('/api/v1/mini/me/export').status_code, 404)
        paths = app.openapi()['paths']
        self.assertFalse(any('/generation-reviews' in path or path == '/api/v1/mini/me/export' for path in paths))

    def test_old_review_grants_are_ignored_without_losing_other_permissions(self):
        self.assertNotIn('generationReview', {menu['id'] for menu in admin_permissions.catalog()})
        self.assertIsNone(admin_permissions.route_permission('/api/v1/admin/generation-reviews', 'GET'))
        self.assertEqual(admin_permissions.normalize({'generationReview': ['view', 'update'], 'papers': ['view']}),
                         {'papers': ['view']})
