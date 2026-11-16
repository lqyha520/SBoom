"""菜单、按钮授权的接口隔离与迁移回归。"""
import unittest

from fastapi import Depends

from app import admin_access_schema, admin_permissions
from app.db import db
from app.deps import require_admin
from app.routers import admin_local_access, engagement, site, xhs_workflow, xhs_workspace
from app.services import admin_access, user_store
from tests import test_backend_catalog as catalog_tests


class AdminPermissionsTests(unittest.TestCase):
    setUp = catalog_tests.PublicCatalogContracts.setUp
    sign_in = catalog_tests.PublicCatalogContracts.sign_in
    source = catalog_tests.PublicCatalogContracts.source
    draft = catalog_tests.PublicCatalogContracts.draft
    update = catalog_tests.PublicCatalogContracts.update

    def restricted(self, permissions=None):
        user = user_store.create_user('restricted-admin', 'test-password', role='admin')
        if permissions:
            admin_access.save_permissions(self.admin.id, user.id, 1, permissions)
        self.sign_in(user)
        return user

    def test_unassigned_and_view_only_admin(self):
        target = self.restricted()
        for path in ('/stats', '/users', '/catalog/papers', '/access/catalog'):
            response = self.client.get('/api/v1/admin' + path)
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(response.json()['detail']['code'], 'permission_denied')
        admin_access.save_permissions(self.admin.id, target.id, 1, {'papers': ['view']})
        self.assertEqual(self.client.get('/api/v1/admin/catalog/papers').status_code, 200)
        self.assertEqual(self.client.post('/api/v1/admin/catalog/papers', json={}).status_code, 403)
        self.assertEqual(self.client.delete('/api/v1/admin/catalog/papers/absent?revision=1').status_code, 403)
        admin_access.save_permissions(self.admin.id, target.id, 2, {})
        self.assertEqual(self.client.get('/api/v1/admin/catalog/papers').status_code, 403)

    def test_button_grants_are_independent(self):
        target = self.restricted({'users': ['create']})
        created = self.client.post('/api/v1/admin/users', json={'username': 'created-user', 'password': 'password-123'})
        self.assertEqual(created.status_code, 200, created.text)
        identifier = created.json()['id']
        self.assertEqual(self.client.put(f'/api/v1/admin/users/{identifier}', json={'is_active': False}).status_code, 403)
        admin_access.save_permissions(self.admin.id, target.id, 2, {'users': ['update']})
        self.assertEqual(self.client.put(f'/api/v1/admin/users/{identifier}', json={'is_active': False}).status_code, 200)
        self.assertEqual(self.client.delete(f'/api/v1/admin/users/{identifier}').status_code, 403)
        admin_access.save_permissions(self.admin.id, target.id, 3, {'users': ['delete']})
        self.assertEqual(self.client.delete(f'/api/v1/admin/users/{identifier}').status_code, 200)

    def test_user_manager_cannot_manage_admins_or_grant_roles(self):
        target = self.restricted({'users': ['view', 'create', 'update', 'delete']})
        users = self.client.get('/api/v1/admin/users').json()['users']
        self.assertTrue(all(row['role'] == 'user' for row in users))
        for identifier in (self.admin.id, target.id):
            for response in (
                self.client.put(f'/api/v1/admin/users/{identifier}', json={'password': 'takeover-123'}),
                self.client.delete(f'/api/v1/admin/users/{identifier}'),
                self.client.get(f'/api/v1/admin/users/{identifier}/templates'),
                self.client.put(f'/api/v1/admin/access/users/{identifier}', json={'revision': 1, 'permissions': {'users': ['delete']}}),
            ):
                self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.client.get('/api/v1/admin/users?role=admin').status_code, 403)
        self.assertEqual(self.client.get(f'/api/v1/admin/users/+{self.admin.id}/templates').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/users/not-a-number/templates').status_code, 422)
        self.assertEqual(self.client.post('/api/v1/admin/users', json={'username': 'new-admin', 'password': 'password-123', 'role': 'admin'}).status_code, 403)
        self.assertEqual(self.client.put(f'/api/v1/admin/users/{self.author.id}', json={'role': 'admin'}).status_code, 403)
        self.assertEqual(self.client.put(f'/api/v1/admin/users/{self.author.id}', json={'is_super_admin': True}).status_code, 422)

    def test_assignment_revision_audit_and_super_protection(self):
        target = self.restricted()
        self.sign_in(self.admin)
        url = f'/api/v1/admin/access/users/{target.id}'
        response = self.client.put(url, json={'revision': 1, 'permissions': {'papers': ['create']}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['admin_permissions'], {'papers': ['view', 'create']})
        self.assertEqual(self.client.put(url, json={'revision': 1, 'permissions': {}}).status_code, 409)
        self.assertEqual(self.client.put(url, json={'revision': 2, 'permissions': {'adminAccounts': ['view']}}).status_code, 422)
        self.assertEqual(self.client.put(url, json={'revision': 2, 'permissions': {'papers': ['bogus']}}).status_code, 422)
        self.assertEqual(self.client.put(f'/api/v1/admin/access/users/{self.admin.id}', json={'revision': 1, 'permissions': {}}).status_code, 400)
        with db() as conn:
            rows = conn.execute('SELECT * FROM admin_permission_audit WHERE target_id=?', (target.id,)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['actor_id'], self.admin.id)
        self.assertEqual(rows[0]['revision'], 2)

    def test_migration_only_promotes_named_active_admin_once(self):
        named = user_store.create_user('lqyha', 'test-password', role='admin')
        other = user_store.create_user('other-admin', 'test-password', role='admin')
        with db() as conn:
            conn.execute("DELETE FROM app_config WHERE key='admin_access_initialized'")
            admin_access_schema.migrate(conn)
        self.assertTrue(user_store.get_user_by_id(named.id).is_super_admin)
        self.assertFalse(user_store.get_user_by_id(other.id).is_super_admin)
        with db() as conn:
            conn.execute('UPDATE users SET is_super_admin=false WHERE id=?', (named.id,))
            admin_access_schema.migrate(conn)
        self.assertFalse(user_store.get_user_by_id(named.id).is_super_admin)

    def test_unknown_route_denied_even_to_super(self):
        @self.client.app.get('/api/v1/admin/unclassified')
        def unclassified(admin=Depends(require_admin)):
            return {'leak': True}
        self.assertEqual(self.client.get('/api/v1/admin/unclassified').status_code, 403)

    def test_admin_routes_have_permission_mapping(self):
        # OpenAPI 会展开 FastAPI 延迟注册的 include_router。
        from app.main import app
        for path, operations in app.openapi()['paths'].items():
            if not path.startswith('/api/v1/admin/'):
                continue
            for method in operations:
                kinds = next((parameter['schema']['enum'] for parameter in operations[method].get('parameters', [])
                              if parameter['name'] == 'kind' and 'enum' in parameter.get('schema', {})), ('ideas', 'materials', 'drafts', 'publications'))
                for kind in kinds:
                    if '/options/' in path:
                        for menu, options in admin_permissions.LOOKUPS.items():
                            for option in options:
                                self.assertEqual(admin_permissions.route_permission(path.replace('{menu}', menu).replace('{kind}', option), method.upper()), (menu, 'view'))
                        continue
                    self.assertIsNotNone(admin_permissions.route_permission(path.replace('{kind}', kind), method.upper()), f'{method} {path}')

    def test_publish_requires_separate_grant(self):
        target = self.restricted({'papers': ['create', 'update']})
        item = self.draft(self.source(target))
        response = self.update(item, status='published', confirm_publication=True)
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()['detail']['action'], 'publish')

    def test_local_capability_is_operation_bound_and_live(self):
        self.client.app.include_router(admin_local_access.router)
        target = self.restricted({'xhsAccounts': ['view']})
        origin = 'http://localhost:5174'
        body = {'path': '/accounts', 'method': 'GET'}
        issued = self.client.post('/api/v1/local-access/issue', json=body, headers={'Origin': origin})
        self.assertEqual(issued.status_code, 200, issued.text)
        proof = {**body, 'origin': origin, 'token': issued.json()['token']}
        self.assertEqual(self.client.post('/api/v1/local-access/verify', json=proof).status_code, 200)
        self.assertEqual(self.client.post('/api/v1/local-access/verify', json={**proof, 'path': '/accounts/add', 'method': 'POST'}).status_code, 403)
        admin_access.save_permissions(self.admin.id, target.id, 2, {})
        self.assertEqual(self.client.post('/api/v1/local-access/verify', json=proof).status_code, 403)

    def test_every_menu_read_has_isolated_authorization(self):
        for router in (site.admin_router, engagement.router, xhs_workflow.router, xhs_workspace.router):
            self.client.app.include_router(router)
        self.restricted({'papers': ['view']})
        for path in ('/site/categories', '/site/dictionary', '/catalog/tags', '/engagement/closures', '/xhs-workflow/records/ideas', '/xhs-workspace/assets', '/xhs-workspace/tutorial'):
            self.assertEqual(self.client.get('/api/v1/admin' + path).status_code, 403, path)

    def test_all_admin_operations_reject_unassigned_admin_before_side_effects(self):
        import re

        from fastapi.testclient import TestClient

        from app.deps import SESSION_COOKIE
        from app.main import app
        from app.security import create_token

        target = self.restricted()
        # 不进入应用 lifespan，不启动外部服务；沿用本测试的一次性数据库。
        client = TestClient(app)
        self.addCleanup(client.close)
        client.cookies.set(SESSION_COOKIE, create_token(target.id))
        for path, operations in app.openapi()['paths'].items():
            if not path.startswith('/api/v1/admin/'):
                continue
            concrete = path.replace('{menu}', 'papers').replace('{kind}', 'categories' if '/options/' in path else 'ideas')
            concrete = re.sub(r'\{[^}]+\}', '1', concrete)
            for method in operations:
                response = client.request(method.upper(), concrete, **({'json': {}} if method in ('post', 'put', 'patch') else {}))
                if path == '/api/v1/admin/sessions' and method == 'get':
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()['sessions'], [])
                    continue
                if path == '/api/v1/admin/sessions/{identifier}' and method == 'delete':
                    self.assertEqual(response.status_code, 404)
                    continue
                self.assertEqual(response.status_code, 403, f'{method} {path}: {response.text}')
                self.assertEqual(response.json()['detail']['code'], 'permission_denied', path)

    def test_menu_options_do_not_open_configuration_menus(self):
        self.restricted({'papers': ['view'], 'topics': ['view'], 'orders': ['view']})
        for kind in ('categories', 'dictionary', 'tags'):
            response = self.client.get(f'/api/v1/admin/options/papers/{kind}')
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get('/api/v1/admin/options/topics/papers').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/admin/options/orders/payment').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/admin/options/papers/payment').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/options/banners/categories').status_code, 403)

    def test_pdf_export_is_separate_from_preview_view(self):
        target = self.restricted({'papers': ['create']})
        item = self.draft(self.source(target))
        admin_access.save_permissions(self.admin.id, target.id, 2, {'papers': ['view']})
        detail = self.client.get(f"/api/v1/admin/catalog/papers/{item['id']}").json()
        preview = next(asset for asset in detail['assets'] if asset['mime_type'].startswith('image/'))
        pdf = next(asset for asset in detail['assets'] if asset['mime_type'] == 'application/pdf')
        self.assertEqual(self.client.get(preview['url']).status_code, 200)
        self.assertEqual(self.client.get(pdf['url']).status_code, 403)
        admin_access.save_permissions(self.admin.id, target.id, 3, {'papers': ['export']})
        self.assertEqual(self.client.get(pdf['url']).status_code, 200)

    def test_asset_preview_is_view_only_and_does_not_remove_download_guard(self):
        import io

        from PIL import Image

        self.client.app.include_router(xhs_workspace.router)
        target = self.restricted({'xhsAssets': ['create']})
        output = io.BytesIO()
        Image.new('RGB', (8, 8), 'green').save(output, 'PNG')
        created = self.client.post('/api/v1/admin/xhs-workspace/assets/file?title=preview', content=output.getvalue(), headers={'Content-Type': 'image/png'})
        self.assertEqual(created.status_code, 201, created.text)
        path = '/api/v1/admin/xhs-workspace/assets/' + created.json()['id']
        admin_access.save_permissions(self.admin.id, target.id, 2, {'xhsAssets': ['view']})
        preview = self.client.get(path + '/preview')
        self.assertEqual(preview.status_code, 200, preview.text if preview.status_code != 200 else '')
        self.assertTrue(preview.headers['content-disposition'].startswith('inline;'))
        self.assertEqual(preview.content, output.getvalue())
        self.assertEqual(self.client.get(path + '/file').status_code, 403)
        self.assertEqual(self.client.delete(path + '?revision=1').status_code, 403)
