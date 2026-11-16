"""私人归档批量删除：只使用一次性测试数据库和临时文件。"""

import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import test_backend_catalog as fixtures

from app.config import get_settings
from app.db import db
from app.services import paper_library


class LibraryBatchDeleteContracts(unittest.TestCase):
    setUp = fixtures.PublicCatalogContracts.setUp
    sign_in = fixtures.PublicCatalogContracts.sign_in
    source = fixtures.PublicCatalogContracts.source
    draft = fixtures.PublicCatalogContracts.draft
    update = fixtures.PublicCatalogContracts.update
    publish = fixtures.PublicCatalogContracts.publish

    def preview(self, ids):
        response = self.client.post('/api/v1/library/papers/batch-delete/preview', json={'ids': ids})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def remove(self, ids):
        response = self.client.post('/api/v1/library/papers/batch-delete', json={'ids': ids, 'confirmed': True})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_preview_is_read_only_and_batch_preserves_public_files(self):
        source = self.source()
        published = self.publish(self.draft(source))
        unused = self.source()
        before = self.client.get('/api/v1/library/summary').json()['storage_bytes']
        preview = self.preview([unused['id'], source['id']])
        self.assertEqual(preview['deletable_count'], 1)
        self.assertEqual(self.client.get('/api/v1/library/summary').json()['storage_bytes'], before)
        self.assertEqual(self.client.get(unused['assets'][0]['url']).status_code, 200)
        result = self.remove([unused['id'], source['id'], unused['id']])
        self.assertEqual(result['deleted_ids'], [unused['id']])
        self.assertEqual(result['skipped'][0]['id'], source['id'])
        self.assertEqual(result['released_bytes'], preview['reclaimable_bytes'])
        self.assertEqual(self.client.get('/api/v1/library/summary').json()['storage_bytes'], before - result['released_bytes'])
        self.assertEqual(self.client.get(unused['assets'][0]['url']).status_code, 404)
        with db() as conn:
            self.assertGreater(conn.execute('SELECT COUNT(*) FROM file_deletions').fetchone()[0], 0)
        fixtures.pg_support.drain_after_file_grace()
        self.sign_in(self.viewer)
        public = self.client.get(f"/api/v1/catalog/papers/{published['id']}").json()
        self.assertTrue(public['assets'])
        for asset in public['assets']:
            self.assertEqual(self.client.get(asset['url']).status_code, 200)

    def test_drafts_hidden_revisions_and_editions_are_all_protected(self):
        source = self.source()
        catalog = self.draft(source)
        history, edition, edition_history = self.source(), self.source(), self.source()
        with db(serialized=True) as conn:
            conn.execute('INSERT INTO catalog_versions(id,catalog_id,paper_id,release_number,note,created_at) VALUES (?,?,?,?,?,?)',
                         ('batch-history', catalog['id'], history['id'], 1, '历史', 1))
            conn.execute('INSERT INTO catalog_print_editions(catalog_id,kind,paper_id) VALUES (?,?,?)',
                         (catalog['id'], 'answers', edition['id']))
            conn.execute('INSERT INTO catalog_edition_history(catalog_id,paper_id,kind,release_number,created_at) VALUES (?,?,?,?,?)',
                         (catalog['id'], edition_history['id'], 'answers', 1, 1))
        ids = [item['id'] for item in [source, history, edition, edition_history]]
        self.assertEqual(self.preview(ids)['deletable_count'], 0)
        self.assertEqual(len(self.remove(ids)['skipped']), 4)
        for paper_id in ids:
            self.assertEqual(self.client.delete('/api/v1/library/papers/' + paper_id).status_code, 409)
        with db(serialized=True) as conn:
            conn.execute("UPDATE catalog_papers SET status='hidden' WHERE id=?", (catalog['id'],))
        self.assertEqual(self.remove([source['id']])['deleted_ids'], [])

    def test_ownership_auth_confirmation_and_selection_limit(self):
        own, other = self.source(), self.source(owner=self.author)
        preview = self.preview([other['id'], 'missing'])
        self.assertEqual(preview['items'][0]['reason'], preview['items'][1]['reason'])
        self.assertTrue(all(item['title'] is None and item['storage_bytes'] == 0 for item in preview['items']))
        for body in ({'ids': [own['id']]}, {'ids': [own['id']], 'confirmed': False},
                     {'ids': [], 'confirmed': True}, {'ids': [own['id']] * 51, 'confirmed': True},
                     {'ids': ['x' * 65], 'confirmed': True}):
            self.assertEqual(self.client.post('/api/v1/library/papers/batch-delete', json=body).status_code, 422)
        self.assertEqual(self.remove([other['id']])['deleted_ids'], [])
        self.assertEqual(self.client.post('/api/v1/library/papers/batch-delete', json={'ids': [own['id']], 'confirmed': True},
                                          headers={'X-Workspace-User': str(self.author.id)}).status_code, 409)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.post('/api/v1/library/papers/batch-delete', json={'ids': [own['id']], 'confirmed': True}).status_code, 403)

    def test_publication_added_after_preview_is_rechecked(self):
        paper = self.source()
        self.assertEqual(self.preview([paper['id']])['deletable_count'], 1)
        self.draft(paper)
        self.assertEqual(self.remove([paper['id']])['deleted_ids'], [])

    def test_active_upload_is_skipped_expired_upload_can_be_removed(self):
        paper = self.source(ready=False)
        with db() as conn:
            conn.execute("UPDATE paper_archives SET file_status='uploading',upload_started_at=? WHERE id=?", (int(time.time()), paper['id']))
        self.assertIn('上传', self.remove([paper['id']])['skipped'][0]['reason'])
        self.assertEqual(self.client.delete('/api/v1/library/papers/' + paper['id']).status_code, 409)
        with db() as conn:
            conn.execute('UPDATE paper_archives SET upload_started_at=0 WHERE id=?', (paper['id'],))
        self.assertEqual(self.remove([paper['id']])['deleted_ids'], [paper['id']])
        self.assertEqual(self.remove([paper['id']])['released_bytes'], 0)

    def test_unexpected_failure_rolls_back_deletions_and_cleanup_queue(self):
        papers = [self.source(), self.source()]
        original = paper_library._remove_archive

        def fail_second(conn, user_id, paper_id):
            original(conn, user_id, paper_id)
            if paper_id == papers[1]['id']:
                raise RuntimeError('模拟事务失败')

        with patch.object(paper_library, '_remove_archive', side_effect=fail_second), self.assertRaises(RuntimeError):
            paper_library.batch_delete(self.admin.id, [paper['id'] for paper in papers])
        for paper in papers:
            self.assertEqual(self.client.get(paper['assets'][0]['url']).status_code, 200)
        with db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM file_deletions').fetchone()[0], 0)

    def test_concurrent_publication_lock_prevents_cascade_deletion(self):
        paper = self.source()
        started = Event()

        def remove():
            started.set()
            return paper_library.batch_delete(self.admin.id, [paper['id']])

        with ThreadPoolExecutor(max_workers=1) as pool:
            with db(serialized=True) as conn:
                task = pool.submit(remove)
                self.assertTrue(started.wait(3))
                conn.execute('INSERT INTO catalog_papers(id,paper_id,publisher_id,title,created_at,updated_at) VALUES (?,?,?,?,?,?)',
                             ('concurrent-publication', paper['id'], self.admin.id, '并发发布', 1, 1))
            self.assertEqual(task.result(timeout=5)['deleted_ids'], [])
        self.assertEqual(self.client.get(paper['assets'][0]['url']).status_code, 200)

    def test_five_gb_quota_accepts_over_512_mb_but_still_limits_uploads(self):
        old = self.source()
        new = self.source(ready=False)
        with patch.object(get_settings(), 'archive_storage_mb', 5120):
            self.assertEqual(self.client.get('/api/v1/library/summary').json()['storage_limit_bytes'], 5 * 1024 ** 3)
            with db() as conn:
                conn.execute('UPDATE paper_assets SET byte_size=? WHERE id=?', (600 * 1024 ** 2, old['assets'][0]['id']))
            self.assertEqual(paper_library.publish_bundle(self.admin.id, new['id'], fixtures.bundle())['file_status'], 'ready')
            last = self.source(ready=False)
            with db() as conn:
                conn.execute('UPDATE paper_assets SET byte_size=? WHERE id=?', (5 * 1024 ** 3, old['assets'][0]['id']))
            response = self.client.put('/api/v1/library/papers/' + last['id'] + '/files', content=fixtures.bundle(), headers={'Content-Type': 'application/zip'})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(self.client.get('/api/v1/library/papers/' + last['id']).status_code, 200)
