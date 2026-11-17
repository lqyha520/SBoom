"""公共习题管理归属隔离：列表、文件、写入及批量请求均不能跨创建人。"""

import unittest

import test_backend_catalog as fixtures
from fastapi import HTTPException

from app.db import db
from app.models.catalog import CatalogUpdate
from app.routers import engagement, experience
from app.services import admin_access, public_catalog, user_store


class CatalogOwnershipTests(unittest.TestCase):
    sign_in = fixtures.PublicCatalogContracts.sign_in
    source = fixtures.PublicCatalogContracts.source
    update = fixtures.PublicCatalogContracts.update

    def setUp(self):
        fixtures.PublicCatalogContracts.setUp(self)
        for router in (experience.router, engagement.router):
            self.client.app.include_router(router)
        self.editor = user_store.create_user('catalog-editor', 'test-password', role='admin')
        self.peer = user_store.create_user('catalog-peer', 'test-password', role='admin')
        for user in (self.editor, self.peer):
            admin_access.save_permissions(self.admin.id, user.id, 1, {
                'papers': ['view', 'create', 'update', 'delete', 'export', 'publish'], 'topics': ['view'],
            })

    def create(self, owner, title, published=False):
        source = self.source(owner)
        self.sign_in(owner)
        response = self.client.post('/api/v1/admin/catalog/papers', json={'paper_id': source['id'], 'title': title})
        self.assertEqual(response.status_code, 201, response.text)
        item = response.json()
        if published:
            response = self.update(item, status='published', confirm_publication=True)
            self.assertEqual(response.status_code, 200, response.text)
            item = response.json()
        return item

    def test_list_search_pagination_statistics_and_options_use_creator_scope(self):
        own = self.create(self.editor, '自己的已发布', True)
        draft = self.create(self.editor, '自己的草稿')
        foreign = self.create(self.peer, '其他管理员资料', True)
        public_catalog.favorite_paper(self.viewer.id, foreign['id'], True)
        public_catalog.request_download(self.viewer.id, foreign['id'])
        self.sign_in(self.editor)
        path = '/api/v1/admin/catalog/papers'
        first = self.client.get(path, params={'limit': 1}).json()
        second = self.client.get(path, params={'limit': 1, 'offset': 1}).json()
        self.assertEqual(first['total'], 2)
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])
        self.assertEqual({first['items'][0]['id'], second['items'][0]['id']}, {own['id'], draft['id']})
        for query in ({'q': '其他管理员'}, {'publisher_id': self.peer.id, 'q': '其他管理员'}, {'status': 'withdrawn'}):
            result = self.client.get(path, params=query).json()
            self.assertEqual(result['total'], 0)
        self.assertEqual(self.client.get(path, params={'status': 'published'}).json()['total'], 1)
        self.assertEqual(self.client.get('/api/v1/admin/catalog/summary').json(),
                         {'total': 2, 'draft': 1, 'published': 1, 'withdrawn': 0, 'favorites': 0, 'downloads': 0})
        options = self.client.get('/api/v1/admin/options/topics/papers').json()
        self.assertEqual([item['id'] for item in options['items']], [own['id']])
        self.sign_in(self.admin)
        all_items = self.client.get(path).json()
        self.assertEqual(all_items['total'], 3)
        self.assertEqual({item['publisher_name'] for item in all_items['items']}, {'catalog-editor', 'catalog-peer'})
        self.assertEqual(self.client.get('/api/v1/admin/catalog/summary').json()['downloads'], 1)

    def test_foreign_details_files_and_all_mutations_are_denied_before_effects(self):
        foreign = self.create(self.peer, '他人的资料')
        self.sign_in(self.editor)
        path = '/api/v1/admin/catalog/papers/' + foreign['id']
        requests = [
            ('GET', path, {}), ('GET', path + '/preview', {}), ('GET', path + '/edition-sources', {}),
            ('GET', foreign['thumbnail_url'], {}),
            *[('GET', asset['url'], {}) for asset in foreign['assets']],
            ('PUT', path, {'json': {'revision': 1, 'title': '越权修改', 'status': 'draft'}}),
            ('DELETE', path + '?revision=1', {}),
            ('PUT', path + '/labels', {'json': {'revision': 1, 'tag_ids': []}}),
            ('PUT', path + '/editions', {'json': {'revision': 1, 'kind': 'answers', 'paper_id': None}}),
            ('POST', path + '/revision', {'json': {'revision': 1, 'paper_id': 'missing', 'note': '越权修订'}}),
            ('POST', path + '/editions/import?revision=1', {'content': b'%PDF-placeholder', 'headers': {'Content-Type': 'application/pdf'}}),
        ]
        for method, url, kwargs in requests:
            with self.subTest(method=method, path=url):
                response = self.client.request(method, url, **kwargs)
                self.assertEqual(response.status_code, 404, response.text)
        with db() as conn:
            row = conn.execute('SELECT title,revision,publisher_id FROM catalog_papers WHERE id=?', (foreign['id'],)).fetchone()
            self.assertEqual(tuple(row.values()), ('他人的资料', 1, self.peer.id))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM paper_archives').fetchone()[0], 1)
        with self.assertRaises(HTTPException) as error:
            public_catalog.update_paper(self.editor.id, foreign['id'], CatalogUpdate(revision=1, title='直调越权', status='draft'))
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(HTTPException) as error:
            public_catalog.delete_paper(foreign['id'], 1, admin_id=self.editor.id)
        self.assertEqual(error.exception.status_code, 404)

    def test_mixed_batch_is_atomic_and_super_can_update_other_creators(self):
        own = self.create(self.editor, '自己的资料')
        foreign = self.create(self.peer, '他人的资料')
        self.sign_in(self.editor)
        body = {'items': [{'id': item['id'], 'revision': 1} for item in (own, foreign)],
                'action': 'published', 'confirm_publication': True}
        response = self.client.post('/api/v1/admin/catalog/batch', json=body)
        self.assertEqual(response.status_code, 404, response.text)
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM catalog_papers WHERE status='draft' AND revision=1").fetchone()[0], 2)
        response = self.update(own, title='自己的资料已修改')
        self.assertEqual(response.status_code, 200, response.text)
        body['items'][0]['revision'] = response.json()['revision']
        self.sign_in(self.admin)
        response = self.client.post('/api/v1/admin/catalog/batch', json=body)
        self.assertEqual(response.status_code, 200, response.text)
        current = self.client.get('/api/v1/admin/catalog/papers/' + foreign['id']).json()
        response = self.update(current, title='超级管理员修改')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['publisher_id'], self.peer.id)
        self.sign_in(self.peer)
        self.assertEqual(self.client.get('/api/v1/admin/catalog/papers').json()['items'][0]['title'], '超级管理员修改')

    def test_revision_does_not_transfer_creator_and_public_reader_keeps_published_access(self):
        item = self.create(self.editor, '原创建人资料', True)
        self.sign_in(self.admin)
        source = self.source(self.admin)
        response = self.client.post('/api/v1/admin/catalog/papers/' + item['id'] + '/revision', json={
            'revision': item['revision'], 'paper_id': source['id'], 'note': '超级管理员补充修订', 'confirm_publication': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['publisher_id'], self.editor.id)
        self.sign_in(self.editor)
        self.assertEqual(self.client.get('/api/v1/admin/catalog/papers/' + item['id']).status_code, 200)
        self.sign_in(self.peer)
        self.assertEqual(self.client.get('/api/v1/admin/catalog/papers/' + item['id']).status_code, 404)
        self.sign_in(self.viewer)
        public = self.client.get('/api/v1/catalog/papers/' + item['id'])
        self.assertEqual(public.status_code, 200)
        self.assertNotIn('publisher_id', public.json())
        self.assertNotIn('publisher_name', public.json())

    def test_legacy_unowned_entries_are_only_visible_to_super_admin(self):
        item = self.create(self.editor, '历史资料')
        with db() as conn:
            conn.execute('UPDATE catalog_papers SET publisher_id=NULL WHERE id=?', (item['id'],))
        self.sign_in(self.editor)
        self.assertEqual(self.client.get('/api/v1/admin/catalog/papers').json()['total'], 0)
        self.assertEqual(self.client.get('/api/v1/admin/catalog/papers/' + item['id']).status_code, 404)
        self.sign_in(self.admin)
        response = self.client.get('/api/v1/admin/catalog/papers/' + item['id'])
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['publisher_name'])
