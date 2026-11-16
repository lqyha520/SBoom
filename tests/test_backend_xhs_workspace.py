"""工作台扩展：文件权限、排期边界、建议证据和示例幂等。"""
import io
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import test_backend_catalog as fixtures
import test_backend_xhs_workflow as workflow_tests
from PIL import Image

from app.db import db
from app.models.xhs_workflow import Publication
from app.routers import xhs_workflow, xhs_workspace
from app.services import user_store

BASE = '/api/v1/admin/xhs-workspace'


class XhsWorkspaceContracts(fixtures.PublicCatalogContracts):
    create = workflow_tests.XhsWorkflowContracts.create
    edit = workflow_tests.XhsWorkflowContracts.edit
    chain = workflow_tests.XhsWorkflowContracts.chain

    def setUp(self):
        super().setUp()
        self.client.app.include_router(xhs_workflow.router)
        self.client.app.include_router(xhs_workspace.router)

    def image(self):
        output = io.BytesIO()
        Image.new('RGB', (8, 8), 'green').save(output, 'PNG')
        return output.getvalue()

    def upload(self, content=None, media='image/png'):
        return self.client.post(BASE + '/assets/file?title=练习配图', content=content if content is not None else self.image(), headers={'Content-Type': media})

    def test_publication_media_roundtrip_order_and_review_reset(self):
        from app.services.xhs_publication import CHECKS

        asset = self.upload().json()
        self.client.put(f"{BASE}/assets/{asset['id']}", json={'revision': asset['revision'], 'data': {**asset['data'], 'rights': 'original'}}).raise_for_status()
        library = {'id': 'library', 'asset_id': asset['id'], 'name': '素材.png', 'media_type': 'image/png', 'size_bytes': asset['size_bytes'], 'last_modified': 0}
        local = {**library, 'id': 'local', 'asset_id': '', 'name': '本机.png', 'size_bytes': 3, 'last_modified': 12345}
        record = self.create('publications', Publication(title='配图草稿', source='custom', account='数学号', custom_content={'headline': '数学练习', 'body': '每天一道练习题，先观察再动笔。'}, media=[library, local]).model_dump(mode='json'))
        path = f"/api/v1/admin/xhs-workflow/records/publications/{record['id']}"
        self.assertEqual(self.client.get(path).json()['data']['media'], [library, local])
        ready = self.edit(record, status='ready', **dict.fromkeys(CHECKS, True))
        self.assertEqual(ready.status_code, 200, ready.text)
        reordered = self.edit(ready.json(), media=[local, library])
        self.assertEqual(reordered.status_code, 200, reordered.text)
        self.assertEqual(reordered.json()['status'], 'planned')
        self.assertTrue(all(not reordered.json()['data'][key] for key in CHECKS))
        self.assertEqual(self.client.get(path).json()['data']['media'], [local, library])
        versions = self.client.get(path + '/versions').json()['items']
        self.assertEqual(versions[-1]['data']['media'], [library, local])

    def test_publication_media_checks_asset_ownership_rights_and_file_metadata(self):
        asset = self.upload().json()
        reference = {'id': 'library', 'asset_id': asset['id'], 'name': '素材.png', 'media_type': 'image/png', 'size_bytes': asset['size_bytes']}

        def create(reference):
            return self.client.post('/api/v1/admin/xhs-workflow/records/publications', json={'id': str(uuid4()), 'data': {'title': '配图', 'source': 'custom', 'media': [reference]}})

        self.assertEqual(create(reference).status_code, 422)
        self.client.put(f"{BASE}/assets/{asset['id']}", json={'revision': 1, 'data': {**asset['data'], 'rights': 'original'}}).raise_for_status()
        self.assertEqual(create({**reference, 'size_bytes': 1}).status_code, 422)
        self.assertEqual(create(reference).status_code, 201)
        self.client.put(f"{BASE}/assets/{asset['id']}", json={'revision': 2, 'data': {**asset['data'], 'rights': 'original', 'archived': True}}).raise_for_status()
        self.assertEqual(create(reference).status_code, 422)
        self.sign_in(user_store.create_user('media-other-admin', 'test-password', role='admin', is_super_admin=True))
        self.assertEqual(create(reference).status_code, 422)

    def test_publication_media_rejects_duplicate_ids_mixed_types_and_oversized_files(self):
        reference = {'id': 'local', 'name': '本机.png', 'media_type': 'image/png', 'size_bytes': 3}
        invalid = [[reference, reference], [{**reference, 'size_bytes': 11 * 1024 * 1024}],
                   [reference, {**reference, 'id': 'video', 'name': '视频.mp4', 'media_type': 'video/mp4'}],
                   [{**reference, 'id': str(index), 'size_bytes': 8 * 1024 * 1024} for index in range(4)]]
        for media in invalid:
            with self.subTest(media=media):
                response = self.client.post('/api/v1/admin/xhs-workflow/records/publications', json={'id': str(uuid4()), 'data': {'title': '配图', 'source': 'custom', 'media': media}})
                self.assertEqual(response.status_code, 422, response.text)

    def test_assets_roundtrip_dedup_rights_versions_and_permissions(self):
        first = self.upload()
        self.assertEqual(first.status_code, 201, first.text)
        asset = first.json()
        self.assertTrue(self.upload().json()['duplicate'])
        self.assertEqual(self.client.get(BASE + '/assets').json()['total'], 1)
        path = f"{BASE}/assets/{asset['id']}"
        self.assertEqual(self.client.get(path + '/file').content, self.image())
        metadata = {**asset['data'], 'tags': ['数学', '练习'], 'rights': 'licensed'}
        self.assertEqual(self.client.put(path, json={'revision': 1, 'data': metadata}).status_code, 422)
        metadata['source'] = '作者授权用于本账号发布'
        changed = self.client.put(path, json={'revision': 1, 'data': metadata})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.client.put(path, json={'revision': 1, 'data': metadata}).status_code, 409)
        self.assertEqual(self.client.get(BASE + '/assets?q=数学').json()['total'], 1)
        self.assertEqual(self.client.delete(path + '?revision=2').status_code, 409)
        metadata['archived'] = True
        self.assertEqual(self.client.put(path, json={'revision': 2, 'data': metadata}).status_code, 200)
        self.assertEqual(self.client.get(BASE + '/assets').json()['total'], 0)
        self.assertEqual(self.client.get(BASE + '/assets?archived=true').json()['total'], 1)
        self.sign_in(user_store.create_user('assets-second-admin', 'test-password', role='admin', is_super_admin=True))
        self.assertEqual(self.client.get(path + '/file').status_code, 404)
        self.assertEqual(self.client.put(path, json={'revision': 3, 'data': metadata}).status_code, 404)
        self.assertEqual(self.client.delete(path + '?revision=3').status_code, 404)
        self.assertEqual(self.client.get(BASE + '/assets').json()['total'], 0)
        self.sign_in(self.admin)
        self.assertEqual(self.client.delete(path + '?revision=2').status_code, 409)
        self.assertEqual(self.client.delete(path + '?revision=3').status_code, 204)
        self.assertEqual(self.client.get(path + '/file').status_code, 404)

    def test_invalid_uploads_quota_and_template_preservation(self):
        self.assertEqual(self.upload(b'not-image').status_code, 422)
        self.assertEqual(self.upload(b'<svg/>', 'image/svg+xml').status_code, 415)
        self.assertEqual(self.upload(b'').status_code, 422)
        self.assertEqual(self.upload(b'not-video', 'video/mp4').status_code, 422)
        self.assertEqual(self.client.post(BASE + '/assets/file?title=large', content=b'x', headers={'Content-Type': 'image/png', 'Content-Length': str(11 * 1024 * 1024)}).status_code, 413)
        with patch('app.services.xhs_workspace.QUOTA', 1):
            self.assertEqual(self.upload().status_code, 409)
        data = {'data': {'title': '封面', 'rights': 'original'}, 'template': {'theme': 'orange', 'cover_title': '数字规律', 'cards': [{'heading': '练一练', 'body': '1, 2, 3, __'}]}}
        first = self.client.post(BASE + '/assets/template', json=data)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(self.client.post(BASE + '/assets/template', json=data).json()['id'], first.json()['id'])
        self.assertEqual(self.client.get(BASE + '/assets?kind=template').json()['items'][0]['template']['cards'][0]['heading'], '练一练')

    def legacy_asset(self):
        from app.services.paper_storage import storage_for
        asset = self.upload().json()
        with db() as conn:
            key = conn.execute('SELECT storage_key FROM xhs_assets WHERE id=?', (asset['id'],)).fetchone()[0]
            conn.execute("UPDATE xhs_assets SET content=?,storage_key='',thumbnail=NULL WHERE id=?", (self.image(), asset['id']))
        storage_for().delete(key)
        return asset

    def test_asset_files_support_ranges_and_backup_without_exposing_paths(self):
        import psycopg

        from app.config import get_settings
        from app.services.file_retention import referenced
        from scripts.backup_restore import private_files
        asset = self.upload().json()
        path = f"{BASE}/assets/{asset['id']}/file"
        with db() as conn:
            stored = conn.execute('SELECT content,storage_key FROM xhs_assets WHERE id=?', (asset['id'],)).fetchone()
            self.assertIsNone(stored['content'])
            self.assertTrue(referenced(conn, 'local', stored['storage_key']))
        with psycopg.connect(get_settings().database_url) as conn:
            self.assertIn(('local', stored['storage_key']), private_files(conn))
        self.assertNotIn('storage_key', asset)
        response = self.client.get(path, headers={'Range': 'bytes=0-7'})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, self.image()[:8])
        self.assertEqual(response.headers['cache-control'], 'private, no-store')
        self.sign_in(user_store.create_user('asset-consumer', 'test-password'))
        self.assertIn(self.client.get(path, headers={'Range': 'bytes=0-7'}).status_code, (401, 403))

    def test_legacy_asset_migration_is_idempotent_and_preserves_metadata(self):
        from app.services.xhs_asset_storage import migrate_batch
        asset = self.legacy_asset()
        self.assertEqual(migrate_batch(), 1)
        self.assertEqual(migrate_batch(), 0)
        self.assertEqual(self.client.get(f"{BASE}/assets/{asset['id']}/file").content, self.image())
        self.assertEqual(self.client.get(f"{BASE}/assets/{asset['id']}/thumbnail").status_code, 200)
        with db() as conn:
            stored = conn.execute('SELECT content,storage_key,revision FROM xhs_assets WHERE id=?', (asset['id'],)).fetchone()
        self.assertIsNone(stored['content'])
        self.assertTrue(stored['storage_key'].startswith('xhs/'))
        self.assertEqual(stored['revision'], asset['revision'])

    def test_failed_migration_keeps_database_original_and_can_retry(self):
        from app.services.xhs_asset_storage import migrate_batch
        asset = self.legacy_asset()
        with patch('app.services.xhs_asset_storage.write_file', side_effect=OSError('disk full')):
            self.assertEqual(migrate_batch(), 0)
        with db() as conn:
            stored = conn.execute('SELECT content,storage_key FROM xhs_assets WHERE id=?', (asset['id'],)).fetchone()
        self.assertEqual(bytes(stored['content']), self.image())
        self.assertEqual(stored['storage_key'], '')
        self.assertEqual(migrate_batch(), 1)

    def test_failed_fsync_preserves_legacy_original(self):
        from app.services.xhs_asset_storage import migrate_one
        asset = self.legacy_asset()
        with patch('app.services.xhs_asset_storage.os.fsync', side_effect=OSError('sync failed')):
            with self.assertRaises(OSError):
                migrate_one(self.admin.id, asset['id'])
        with db() as conn:
            row = conn.execute('SELECT content,storage_key FROM xhs_assets WHERE id=?', (asset['id'],)).fetchone()
        self.assertEqual(bytes(row['content']), self.image())
        self.assertEqual(row['storage_key'], '')

    def test_failed_migration_does_not_starve_later_assets(self):
        from app.services.xhs_asset_storage import migrate_batch
        asset = self.legacy_asset()
        with db() as conn:
            conn.execute("INSERT INTO xhs_assets(id,admin_id,digest,media_type,size_bytes,metadata_json,content) VALUES ('000-broken',?,'bad','image/png',1,'{}',?)",
                         (self.admin.id, b'x'))
        self.assertEqual(migrate_batch(limit=1), 0)
        self.assertEqual(migrate_batch(limit=1), 1)
        self.assertEqual(self.client.get(f"{BASE}/assets/{asset['id']}/file").content, self.image())
        self.assertEqual(migrate_batch(limit=1), 0)
        self.assertEqual(migrate_batch(limit=1), 0)
        with db() as conn:
            self.assertEqual(bytes(conn.execute("SELECT content FROM xhs_assets WHERE id='000-broken'").fetchone()[0]), b'x')

    def test_backup_supports_legacy_schema_before_file_migration(self):
        import psycopg

        from app.config import get_settings
        from scripts.backup_restore import private_files
        asset = self.legacy_asset()
        with db() as conn:
            conn.execute('ALTER TABLE xhs_assets DROP COLUMN storage, DROP COLUMN storage_key')
        with psycopg.connect(get_settings().database_url) as conn:
            private_files(conn)
            self.assertEqual(bytes(conn.execute('SELECT content FROM xhs_assets WHERE id=%s', (asset['id'],)).fetchone()[0]), self.image())

    def test_delete_enqueues_file_and_cleanup_keeps_referenced_assets(self):
        from app.services.file_retention import drain
        from app.services.paper_storage import storage_for
        asset = self.upload().json()
        with db() as conn:
            key = conn.execute('SELECT storage_key FROM xhs_assets WHERE id=?', (asset['id'],)).fetchone()[0]
            conn.execute("INSERT INTO file_deletions(storage,storage_key,next_attempt) VALUES ('local',?,0)", (key,))
        drain()
        self.assertTrue(storage_for().path(key).is_file())
        path = f"{BASE}/assets/{asset['id']}"
        self.client.put(path, json={'revision': 1, 'data': {**asset['data'], 'archived': True}}).raise_for_status()
        self.assertEqual(self.client.delete(path + '?revision=2').status_code, 204)
        with db() as conn:
            self.assertTrue(conn.execute('SELECT 1 FROM file_deletions WHERE storage_key=?', (key,)).fetchone())
            conn.execute('UPDATE file_deletions SET next_attempt=0 WHERE storage_key=?', (key,))
        drain()
        self.assertFalse(storage_for().path(key).exists())

    def test_calendar_includes_all_pages_timezone_and_boundary_conflicts(self):
        start = datetime(2026, 10, 26, tzinfo=UTC)
        for i in range(25):
            data = Publication(title=f'计划{i}', source='custom', account='数学账号', account_id='account-a', scheduled_at=start + timedelta(days=1, minutes=i)).model_dump(mode='json')
            self.create('publications', data)
        outside = self.create('publications', Publication(title='边界前', source='custom', account='B', scheduled_at=start - timedelta(minutes=15)).model_dump(mode='json'))
        inside = self.create('publications', Publication(title='边界后', source='custom', account='B', scheduled_at=start + timedelta(minutes=15)).model_dump(mode='json'))
        self.create('publications', Publication(title='未排期', source='custom', account='C').model_dump(mode='json'))
        response = self.client.get(BASE + '/calendar', params={'start': start.isoformat(), 'end': (start + timedelta(days=7)).isoformat()})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(len(result['items']), 26)
        self.assertEqual(len(result['unscheduled']), 1)
        self.assertEqual(next(item for item in result['items'] if item['id'] == inside['id'])['conflicts'], [outside['id']])
        self.assertEqual(self.client.get(BASE + '/calendar', params={'start': '2026-10-26', 'end': '2026-11-02'}).status_code, 422)
        self.sign_in(user_store.create_user('calendar-second', 'test-password', role='admin', is_super_admin=True))
        self.assertEqual(self.client.get(BASE + '/calendar', params={'start': start.isoformat(), 'end': (start + timedelta(days=7)).isoformat()}).json()['items'], [])

    def test_review_preview_uses_selected_checkpoint_and_keeps_provenance(self):
        *_, publication = self.chain()
        identifier = publication['id']
        path = f'{BASE}/analytics/{identifier}/idea-preview'
        self.assertEqual(self.client.get(path).status_code, 409)
        metric = {'checkpoint': 7, 'revision': 0, 'measured_at': datetime.now(UTC).isoformat(), 'views': 1000, 'likes': 20, 'saves': 50, 'comments': 5}
        self.client.put(f'/api/v1/admin/xhs-workflow/metrics/{identifier}', json=metric).raise_for_status()
        self.edit(publication, conclusion='家长对例题的讲解有疑问', next_action='下一篇做逐步讲解').raise_for_status()
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json()
        self.assertIn('收藏率 5.00%', ' '.join(preview['reasons']))
        self.assertIn('样本不足 3 篇', ' '.join(preview['reasons']))
        self.assertEqual(preview['data']['source_publication_id'], identifier)
        self.assertEqual(preview['data']['angle'], '下一篇做逐步讲解')
        self.assertEqual(self.client.get(path + '?checkpoint=1').status_code, 409)
        idea_id = str(uuid4())
        saved = self.create('ideas', preview['data'], identifier=idea_id)
        self.assertEqual(self.create('ideas', preview['data'], identifier=idea_id)['id'], saved['id'])
        self.sign_in(user_store.create_user('review-second', 'test-password', role='admin', is_super_admin=True))
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.post('/api/v1/admin/xhs-workflow/records/ideas', json={'id': str(uuid4()), 'data': preview['data']}).status_code, 404)

    def test_tutorial_is_explicit_idempotent_and_never_published(self):
        self.assertEqual(self.client.get(BASE + '/tutorial').json()['records'], {})
        first = self.client.post(BASE + '/tutorial').json()['records']
        self.assertEqual(len(first), 4)
        idea = self.client.get('/api/v1/admin/xhs-workflow/records/ideas/' + first['ideas']).json()
        self.edit(idea, title='我修改后的选题').raise_for_status()
        self.assertEqual(self.client.post(BASE + '/tutorial').json()['records'], first)
        self.assertEqual(self.client.get('/api/v1/admin/xhs-workflow/records/ideas/' + first['ideas']).json()['title'], '我修改后的选题')
        publication = self.client.get('/api/v1/admin/xhs-workflow/records/publications/' + first['publications']).json()
        self.assertEqual(publication['status'], 'planned')
        self.assertIsNone(publication['data']['published_at'])
        self.assertEqual(self.client.get('/api/v1/admin/xhs-workflow/analytics').json()['total'], 0)

    def test_review_benchmark_aggregates_only_same_account_stage_and_eligible_samples(self):
        from app.services.xhs_publication import CHECKS
        now = datetime.now(UTC)
        records = []
        for index, (account, views, saves, checkpoint) in enumerate([
                ('账号 A', 100, 10, 7), ('账号 A', 100, 20, 7), ('账号 A', 100, 30, 7), ('账号 A', 100, 40, 7),
                ('账号 B', 100, 90, 7), ('账号 A', 99, 90, 7), ('账号 A', 100, 90, 1), ('账号 A', 100, 15, 7)]):
            data = Publication(title=f'样本 {index}', source='custom', account=account, status='published',
                               custom_content={'headline': f'独立标题 {index}', 'body': f'独立内容 {index}'},
                               published_at=now - timedelta(days=8), url=f'https://xhslink.com/a/sample-{index}', **dict.fromkeys(CHECKS, True)).model_dump(mode='json')
            record = self.create('publications', data)
            records.append(record)
            self.client.put('/api/v1/admin/xhs-workflow/metrics/' + record['id'], json={'checkpoint': checkpoint, 'revision': 0, 'measured_at': now.isoformat(), 'views': views, 'saves': saves, 'likes': 0, 'comments': 0}).raise_for_status()
        preview = self.client.get(f"{BASE}/analytics/{records[-1]['id']}/idea-preview?checkpoint=7").json()
        self.assertIn('4 篇其他内容的收藏率中位数为 25.00%', ' '.join(preview['reasons']))

    def test_account_profile_is_passed_to_model_and_returned_as_snapshot(self):
        _, material, *_ = self.chain()
        profile = {'id': 'account-a', 'name': '数学账号', 'audience': '一年级家长', 'direction': '分层练习', 'style': '温和简洁', 'topics': '#找规律'}
        body = {'material_id': material['id'], 'material_revision': material['revision'], 'account_profile': profile, 'audience': '三年级家长', 'angle': '生活中的规律'}
        generated = {'headline': '练一练', 'body': '从简单规律开始', 'cover_title': '找规律'}
        with patch.object(xhs_workflow, '_call_llm_and_parse', AsyncMock(return_value=generated)) as model:
            response = self.client.post('/api/v1/admin/xhs-workflow/generate-copy', json=body, headers={'X-Request-ID': str(uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(json.loads(model.call_args.args[1])['account_profile'], profile)
        self.assertEqual(response.json()['draft']['account_profile'], profile)
        self.assertEqual(response.json()['draft']['audience'], body['audience'])
        draft = self.create('drafts', response.json()['draft'], material['id'])
        self.assertEqual(self.client.get('/api/v1/admin/xhs-workflow/records/drafts/' + draft['id']).json()['data']['angle'], body['angle'])

    def test_thumbnail_is_small_preserves_original_and_checks_owner(self):
        content = io.BytesIO()
        Image.new('RGBA', (1200, 800), (0, 200, 100, 80)).save(content, 'PNG')
        asset = self.upload(content.getvalue()).json()
        path = BASE + '/assets/' + asset['id']
        thumb = self.client.get(path + '/thumbnail')
        self.assertEqual(thumb.status_code, 200)
        self.assertEqual(thumb.headers['content-type'], 'image/jpeg')
        self.assertEqual(thumb.headers['cache-control'], 'private, no-store')
        with Image.open(io.BytesIO(thumb.content)) as image:
            self.assertLessEqual(max(image.size), 320)
        self.assertEqual(self.client.get(path + '/file').content, content.getvalue())
        self.sign_in(user_store.create_user('thumbnail-other', 'test-password', role='admin', is_super_admin=True))
        self.assertEqual(self.client.get(path + '/thumbnail').status_code, 404)

    def test_persisted_thumbnail_skips_decoding_and_legacy_backfill_is_shared(self):
        from concurrent.futures import ThreadPoolExecutor

        from app.services import xhs_workspace as service

        asset = self.upload().json()
        path = BASE + '/assets/' + asset['id']
        with patch.object(service, 'thumbnail_bytes', side_effect=AssertionError('重复解码原图')):
            first = self.client.get(path + '/thumbnail')
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(self.client.get(path + '/thumbnail').content, first.content)
        with db() as conn:
            conn.execute('UPDATE xhs_assets SET thumbnail=NULL WHERE id=?', (asset['id'],))
        with patch.object(service, 'thumbnail_bytes', wraps=service.thumbnail_bytes) as builder, ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(service.asset_thumbnail, self.admin.id, asset['id']) for _ in range(3)]
            self.assertEqual([future.result(timeout=5) for future in futures], [first.content] * 3)
            self.assertEqual(builder.call_count, 1)
        self.assertEqual(self.client.get(path).json()['revision'], 1)
        self.sign_in(user_store.create_user('cached-thumbnail-other', 'test-password', role='admin', is_super_admin=True))
        self.assertEqual(self.client.get(path + '/thumbnail').status_code, 404)

    def test_concurrent_uploads_cannot_exceed_the_same_admin_quota(self):
        from concurrent.futures import ThreadPoolExecutor

        from fastapi import HTTPException

        from app.models.xhs_workflow import AssetMetadata
        from app.services import xhs_workspace as service

        content = self.image()
        other = io.BytesIO()
        Image.new('RGB', (8, 8), 'blue').save(other, 'PNG')

        def upload(value):
            try:
                service.create_asset(self.admin.id, AssetMetadata(title='并发素材').model_dump(), 'image/png', value)
                return 201
            except HTTPException as error:
                return error.status_code

        with patch.object(service, 'QUOTA', len(content) + len(other.getvalue()) - 1), ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(upload, value) for value in (content, other.getvalue())]
            self.assertEqual(sorted(future.result(timeout=5) for future in futures), [201, 409])
        self.assertEqual(self.client.get(BASE + '/assets').json()['total'], 1)

    def test_private_asset_writes_keep_public_metadata_cache(self):
        with patch('app.public_cache.invalidate') as invalidate:
            asset = self.upload().json()
            self.client.put(BASE + '/assets/' + asset['id'], json={'revision': 1, 'data': {**asset['data'], 'title': '新的素材名称'}}).raise_for_status()
            invalidate.assert_not_called()

    def test_calendar_migration_backfills_old_dates_without_changing_editor_revision(self):
        from app.xhs_workflow_schema import migrate

        start = datetime(2026, 10, 26, tzinfo=UTC)
        record = self.create('publications', Publication(title='旧排期', source='custom', scheduled_at=start).model_dump(mode='json'))
        with db() as conn:
            conn.execute('UPDATE xhs_workflow_records SET scheduled_at=NULL WHERE id=?', (record['id'],))
            migrate(conn)
            migrate(conn)
            row = conn.execute('SELECT scheduled_at,revision FROM xhs_workflow_records WHERE id=?', (record['id'],)).fetchone()
        self.assertEqual((row['scheduled_at'], row['revision']), (start, 1))

    def test_calendar_filters_long_history_and_paginates_unscheduled_by_account(self):
        start = datetime(2026, 10, 26, tzinfo=UTC)
        historical = Publication(title='旧计划', source='custom', account='旧账号', scheduled_at=start - timedelta(days=100)).model_dump(mode='json')
        with db() as conn:
            conn.execute("""INSERT INTO xhs_workflow_records(id,admin_id,kind,title,status,data_json,create_hash,scheduled_at)
                SELECT 'audit-history-' || n,?,'publications','旧计划',CASE WHEN n%2=0 THEN 'archived' ELSE 'planned' END,?,'audit',?
                FROM generate_series(1,5100) n""", (self.admin.id, json.dumps(historical), start - timedelta(days=100)))
        planned = self.create('publications', Publication(title='本周计划', source='custom', account='数学', account_id='account-a', scheduled_at=start).model_dump(mode='json'))
        for i in range(25):
            self.create('publications', Publication(title=f'未排期{i}', source='custom', account='数学' if i < 15 else '语文', account_id='account-a' if i < 15 else 'account-b').model_dump(mode='json'))
        query = {'start': start.isoformat(), 'end': (start + timedelta(days=7)).isoformat()}
        first = self.client.get(BASE + '/calendar', params=query)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual([item['id'] for item in first.json()['items']], [planned['id']])
        self.assertEqual((first.json()['unscheduled_total'], len(first.json()['unscheduled'])), (25, 20))
        second = self.client.get(BASE + '/calendar', params={**query, 'unscheduled_page': 2}).json()
        self.assertEqual((second['unscheduled_page'], len(second['unscheduled'])), (2, 5))
        self.assertFalse({item['id'] for item in first.json()['unscheduled']} & {item['id'] for item in second['unscheduled']})
        filtered = self.client.get(BASE + '/calendar', params={**query, 'account': 'account-b'}).json()
        self.assertEqual((filtered['items'], filtered['unscheduled_total'], len(filtered['unscheduled'])), ([], 10, 10))

    def test_dense_calendar_reports_full_conflict_count_with_bounded_references(self):
        start = datetime(2026, 10, 26, tzinfo=UTC)
        data = Publication(title='密集排期', source='custom', account='数学', account_id='account-a', scheduled_at=start).model_dump(mode='json')
        with db() as conn:
            conn.execute("""INSERT INTO xhs_workflow_records(id,admin_id,kind,title,status,data_json,create_hash,scheduled_at)
                SELECT 'dense-' || n,?,'publications','密集排期','planned',?,'audit',? FROM generate_series(1,1000) n""",
                         (self.admin.id, json.dumps(data), start))
        result = self.client.get(BASE + '/calendar', params={'start': start.isoformat(), 'end': (start + timedelta(days=7)).isoformat()}).json()
        self.assertEqual(len(result['items']), 1000)
        self.assertTrue(all(item['conflict_count'] == 999 and len(item['conflicts']) == 10 for item in result['items']))

    def test_analytics_filters_and_sorts_all_pages_with_missing_ratios_last(self):
        now = datetime.now(UTC) - timedelta(days=8)
        identifiers = []
        for index in range(25):
            data = Publication(title=f'排序{index}', source='custom', custom_content={'headline':f'练习{index}', 'body':'从简单的规律开始观察，再说出变化。'}, account='数学号', account_id='account-a', status='published', published_at=now + timedelta(minutes=index), url=f'https://www.xiaohongshu.com/explore/{index:024x}', rights_checked=True, truth_checked=True, privacy_checked=True, media_checked=True, platform_checked=True).model_dump(mode='json')
            record = self.create('publications', data)
            identifiers.append(record['id'])
            self.client.put('/api/v1/admin/xhs-workflow/metrics/' + record['id'], json={'checkpoint': 7, 'revision': 0, 'measured_at': datetime.now(UTC).isoformat(), 'views': 100 if index else 0, 'saves': index, 'likes': 0, 'comments': 0}).raise_for_status()
        base = '/api/v1/admin/xhs-workflow/analytics'
        response = self.client.get(base, params={'sort': 'save_rate', 'account': 'account-a'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['total'], 25)
        self.assertEqual(response.json()['items'][0]['id'], identifiers[-1])
        self.assertEqual(self.client.get(base + '?sort=save_rate&page=2').json()['items'][-1]['id'], identifiers[0])
        self.assertEqual(self.client.get(base, params={'start': now.isoformat(), 'end': (now + timedelta(minutes=1)).isoformat()}).json()['total'], 1)
        self.assertEqual(self.client.get(base + '?account=other').json()['total'], 0)
        self.assertEqual(self.client.get(base + '?start=2026-10-30').status_code, 422)
        self.sign_in(user_store.create_user('analytics-other', 'test-password', role='admin', is_super_admin=True))
        self.assertEqual(self.client.get(base).json()['accounts'], [])

    def test_today_tasks_include_overdue_plans_and_each_missing_checkpoint(self):
        now = datetime.now(UTC)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        params = {'start': start.isoformat(), 'end': (start + timedelta(days=1)).isoformat()}
        _, material, draft, publication = self.chain()
        planned = self.create('publications', Publication(title='逾期待发布', source='custom', scheduled_at=start - timedelta(hours=1)).model_dump(mode='json'))
        due = self.client.get(BASE + '/today', params={**params, 'category': 'publish'}).json()
        self.assertIn(planned['id'], [item['id'] for item in due['items']])
        self.edit(publication, published_at=(now - timedelta(days=8)).isoformat()).raise_for_status()
        pending = self.client.get(BASE + '/today', params={**params, 'category': 'analytics'}).json()
        self.assertEqual(sorted(item['checkpoint'] for item in pending['items']), [1, 3, 7])
        self.client.put('/api/v1/admin/xhs-workflow/metrics/' + publication['id'], json={'checkpoint': 1, 'revision': 0, 'measured_at': now.isoformat(), 'views': 100, 'saves': 1, 'likes': 0, 'comments': 0}).raise_for_status()
        self.assertEqual(self.client.get(BASE + '/today', params={**params, 'category': 'analytics'}).json()['total'], 2)
        self.assertEqual(self.client.get(BASE + '/today', params={**params, 'start': '2026-10-30'}).status_code, 422)
        self.sign_in(user_store.create_user('today-other', 'test-password', role='admin', is_super_admin=True))
        self.assertEqual(self.client.get(BASE + '/today', params=params).json()['items'], [])
