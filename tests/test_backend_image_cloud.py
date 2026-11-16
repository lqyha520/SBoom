"""Image worksheets stay private in the cloud until an administrator publishes them."""

import unittest
from unittest.mock import patch

import test_backend_catalog as fixtures
from test_backend_catalog_import import tiny_pdf

from app import db as database
from app.services import paper_library


class ImageCloudContracts(unittest.TestCase):
    setUp = fixtures.PublicCatalogContracts.setUp
    sign_in = fixtures.PublicCatalogContracts.sign_in

    def save(self, content=None, **overrides):
        return self.client.post('/api/v1/library/import', params={
            'request_id': 'a' * 64, 'title': '图片加减练习', 'grade': '小学三年级', 'subject': '数学',
            'keyword': '加减法', 'question_types': 'quiz,fill_blank', 'question_count': 8, **overrides,
        }, content=content or tiny_pdf(), headers={'Content-Type': 'application/pdf'})

    def test_large_image_group_metadata_is_not_capped_at_ten_images(self):
        response = self.save(question_count=960)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['question_count'], 960)

    def test_private_cloud_archive_can_later_be_published_without_uploading_again(self):
        folder = self.client.post('/api/v1/library/folders', json={'name': '图片练习'}).json()
        response = self.save(folder_id=folder['id'])
        self.assertEqual(response.status_code, 201, response.text)
        archive = response.json()
        self.assertEqual((archive['file_status'], archive['page_count'], archive['question_count']), ('ready', 1, 8))
        self.assertEqual(archive['folder_id'], folder['id'])
        self.assertIsNone(archive['publication_id'])
        self.assertEqual(archive['snapshot']['paper']['declared_question_types'], ['quiz', 'fill_blank'])
        pdf_url = next(asset['url'] for asset in archive['assets'] if asset['kind'] == 'pdf')
        self.assertEqual(self.client.get(pdf_url).content, tiny_pdf())
        self.assertIn(archive['id'], [item['id'] for item in self.client.get('/api/v1/library/papers').json()['items']])
        self.assertIn(archive['id'], [item['id'] for item in self.client.get('/api/v1/admin/catalog/sources').json()['items']])
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get('/api/v1/catalog/papers').json()['total'], 0)
        self.assertEqual(self.client.get(pdf_url).status_code, 403)
        self.sign_in(self.admin)
        draft = self.client.post('/api/v1/admin/catalog/papers', json={'paper_id': archive['id'], 'title': archive['title']})
        self.assertEqual(draft.status_code, 201, draft.text)
        draft = draft.json()
        self.assertEqual(draft['status'], 'draft')
        self.assertEqual(self.client.get('/api/v1/library/papers').json()['items'][0]['publication_id'], draft['id'])
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get('/api/v1/catalog/papers').json()['total'], 0)
        self.sign_in(self.admin)
        published = self.client.put(f"/api/v1/admin/catalog/papers/{draft['id']}", json={
            'revision': draft['revision'], 'title': draft['title'], 'status': 'published', 'confirm_publication': True,
        })
        self.assertEqual(published.status_code, 200, published.text)
        self.sign_in(self.viewer)
        detail = self.client.get(f"/api/v1/catalog/papers/{draft['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        public_pdf = next(asset['url'] for asset in detail.json()['assets'] if asset['kind'] == 'pdf')
        self.assertEqual(self.client.get(public_pdf).content, tiny_pdf())

    def test_retry_after_reload_reuses_the_batch_even_when_pdf_timestamps_change(self):
        first = self.save().json()
        second = self.save(content=tiny_pdf('Rebuilt PDF'), title='Edited title')
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()['id'], first['id'])
        self.assertEqual(second.json()['title'], first['title'])
        with database.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM paper_archives').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM catalog_papers').fetchone()[0], 0)
        new_batch = self.save(request_id='b' * 64).json()
        self.assertNotEqual(new_batch['id'], first['id'])

    def test_regular_teachers_can_save_but_other_accounts_cannot_read_or_publish_their_files(self):
        self.sign_in(self.author)
        response = self.save()
        self.assertEqual(response.status_code, 201, response.text)
        archive = response.json()
        self.assertEqual(self.client.post('/api/v1/admin/catalog/papers', json={'paper_id': archive['id']}).status_code, 403)
        self.sign_in(self.admin)
        self.assertEqual(self.client.get(f"/api/v1/library/papers/{archive['id']}").status_code, 404)
        self.assertEqual(self.client.get(archive['assets'][0]['url']).status_code, 404)
        self.assertEqual(self.client.post('/api/v1/admin/catalog/papers', json={'paper_id': archive['id']}).status_code, 404)
        self.assertNotEqual(self.save().json()['id'], archive['id'])
        self.sign_in(self.viewer)
        self.assertEqual(self.save().status_code, 403)
        self.client.headers.pop('Authorization', None)
        self.assertEqual(self.save().status_code, 401)

    def test_failed_file_storage_can_resume_the_same_archive(self):
        with patch.object(paper_library, 'publish_bundle', side_effect=RuntimeError('storage offline')):
            with self.assertRaisesRegex(RuntimeError, 'storage offline'):
                self.save()
        pending = self.client.get('/api/v1/library/papers').json()['items'][0]
        self.assertEqual(pending['file_status'], 'pending')
        retried = self.save()
        self.assertEqual(retried.status_code, 201, retried.text)
        self.assertEqual(retried.json()['id'], pending['id'])
        self.assertEqual(retried.json()['file_status'], 'ready')

    def test_import_validates_metadata_file_type_and_folder_ownership(self):
        folder = self.client.post('/api/v1/library/folders', json={'name': '管理员资料'}).json()
        self.sign_in(self.author)
        self.assertEqual(self.save(folder_id=folder['id']).status_code, 404)
        for changes in ({'request_id': 'invalid'}, {'grade': ''}, {'subject': ' '}, {'question_types': 'invalid'}, {'question_count': 961}):
            self.assertEqual(self.save(**changes).status_code, 422, changes)
        self.assertEqual(self.save(content=b'not-pdf').status_code, 422)
        response = self.client.post('/api/v1/library/import', params={
            'request_id': 'a' * 64, 'title': 'practice', 'grade': '三年级', 'subject': '数学',
        }, content=tiny_pdf(), headers={'Content-Type': 'image/png'})
        self.assertEqual(response.status_code, 415)
        self.assertEqual(self.client.get('/api/v1/library/papers').json()['total'], 0)
