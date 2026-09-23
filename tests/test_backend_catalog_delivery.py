"""PDF and external-link delivery share publication and membership boundaries."""

import time
from types import SimpleNamespace

import test_backend_catalog as fixtures

from app import db as database
from app.services import catalog_ops


class CatalogDeliveryContracts(fixtures.PublicCatalogContracts):
    def link_draft(self, **changes):
        response = self.client.post('/api/v1/admin/catalog/papers', json={
            'title': '网盘数学资料', 'grade': '三年级', 'subject': '数学', 'download_mode': 'external',
            'external_url': 'https://pan.example.com/s/math?from=school', 'external_code': 'aB12', **changes})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_link_only_publication_is_discoverable_without_pdf_and_records_link_requests(self):
        with database.db() as conn:
            conn.execute("INSERT INTO site_categories(id, name, created_at, updated_at) VALUES ('links', '网盘资料', 1, 1)")
        item = self.publish(self.link_draft(category_id='links'))
        self.assertEqual(item['assets'], [])
        self.assertNotEqual(item['file_status'], 'ready')
        path = f"/api/v1/catalog/papers/{item['id']}"
        self.client.cookies.clear()
        for response in (self.client.get(path), self.client.get('/api/v1/catalog/papers')):
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('pan.example.com', response.text)
            self.assertNotIn('aB12', response.text)
        self.assertEqual(self.client.post(path + '/download').status_code, 401)
        self.sign_in(self.viewer)
        result = self.client.post(path + '/download').json()
        self.assertEqual(result, {'kind': 'external', 'url': item['external_url'], 'extraction_code': 'aB12'})
        self.client.post(path + '/download')
        self.assertEqual(self.client.get('/api/v1/catalog/papers?downloaded=true').json()['total'], 1)
        summary = self.client.get('/api/v1/catalog/summary').json()
        self.assertEqual(summary['downloads'], 1)
        self.assertEqual(summary['papers'], 1)
        self.assertEqual(next(row['paper_count'] for row in summary['categories'] if row['id'] == 'links'), 1)
        self.sign_in(self.admin)
        withdrawn = self.update(item, status='withdrawn').json()
        self.sign_in(self.viewer)
        self.assertEqual(self.client.post(path + '/download').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/catalog/papers?downloaded=true').json()['total'], 0)
        self.sign_in(self.admin)
        catalog_ops.batch(SimpleNamespace(action='published', items=[SimpleNamespace(id=item['id'], revision=withdrawn['revision'])]))
        self.assertEqual(self.client.get(path).status_code, 200)

    def test_vip_links_are_protected_and_old_pdf_urls_are_disabled_in_link_mode(self):
        source = self.source()
        item = self.publish(self.link_draft(paper_id=source['id'], download_access='vip'))
        path = f"/api/v1/catalog/papers/{item['id']}"
        pdf_id = next(asset['id'] for asset in source['assets'] if asset['kind'] == 'pdf')
        self.sign_in(self.viewer)
        self.assertEqual(self.client.post(path + '/download').status_code, 403)
        self.assertNotIn('external_url', self.client.get(path).json())
        self.assertTrue(all(asset['kind'] != 'pdf' for asset in self.client.get(path).json()['assets']))
        self.membership(self.viewer, expires=int(time.time()) + 3600)
        self.assertEqual(self.client.post(path + '/download?edition=answers').json()['kind'], 'external')
        self.assertNotIn('external_url', self.client.get(path).json())
        self.assertEqual(self.client.get(path + '/assets/' + pdf_id).status_code, 404)
        self.membership(self.viewer, expires=int(time.time()) - 1)
        self.assertEqual(self.client.post(path + '/download').status_code, 403)
        self.sign_in(self.admin)
        preview = catalog_ops.preview(self.admin.id, item['id'], 'regular')
        self.assertNotIn('external_url', preview)
        self.assertNotIn('external_code', preview)
        self.assertEqual(preview['editions'], [])

    def test_legacy_edits_preserve_links_and_switching_back_to_pdf_clears_destination(self):
        item = self.publish(self.link_draft(paper_id=self.source()['id']))
        changed = self.update(item, title='只修改标题').json()
        self.assertEqual(changed['external_url'], item['external_url'])
        self.assertEqual(changed['external_code'], 'aB12')
        database.init_db()
        self.assertEqual(self.client.get(f"/api/v1/admin/catalog/papers/{item['id']}").json()['download_mode'], 'external')
        switched = self.update(changed, download_mode='pdf').json()
        self.assertEqual((switched['external_url'], switched['external_code']), ('', ''))
        self.assertEqual(self.update(changed, download_mode='external').status_code, 409)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.post(f"/api/v1/catalog/papers/{item['id']}/download").json()['kind'], 'pdf')
        self.sign_in(self.admin)
        link_only = self.link_draft()
        self.assertEqual(self.update(link_only, download_mode='pdf').status_code, 409)
        self.assertEqual(self.update(link_only, external_url='').status_code, 422)

    def test_invalid_links_and_failed_creation_do_not_leave_metadata_archives(self):
        with database.db() as conn:
            before = conn.execute('SELECT COUNT(*) FROM paper_archives').fetchone()[0]
        for url in ('', 'javascript:alert(1)', 'data:text/plain,test', '//pan.example.com/s/a',
                    'https://user:pass@pan.example.com/a', 'https://pan.example.com/a 提取码:1234'):
            with self.subTest(url=url):
                response = self.client.post('/api/v1/admin/catalog/papers', json={
                    'title': '资料', 'grade': '三年级', 'subject': '数学', 'download_mode': 'external', 'external_url': url})
                self.assertEqual(response.status_code, 422, response.text)
        response = self.client.post('/api/v1/admin/catalog/papers', json={
            'title': '资料', 'grade': '三年级', 'subject': '数学', 'download_mode': 'external',
            'external_url': 'https://pan.example.com/s/a', 'category_id': 'missing-category'})
        self.assertEqual(response.status_code, 404)
        with database.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM paper_archives').fetchone()[0], before)
