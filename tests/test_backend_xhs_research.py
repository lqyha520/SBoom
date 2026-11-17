"""小红书公开搜索采集任务的鉴权、状态与快照契约。"""

import test_backend_catalog as fixtures

from app.db import db
from app.routers import xhs_research
from app.services import user_store


class XhsResearchContracts(fixtures.PublicCatalogContracts):
    def setUp(self):
        super().setUp()
        self.client.app.include_router(xhs_research.router)

    def create_task(self, **patch):
        body = {"grade": "一年级", "subject": "数学", "keyword": "看图列式", "period": "week",
                "sort_by": "popular", "note_limit": 20, **patch}
        response = self.client.post("/api/v1/admin/xhs-research/tasks", json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_admin_can_create_start_and_save_deduplicated_public_snapshots(self):
        task = self.create_task()
        self.assertEqual((task["status"], task["note_count"], task["keyword"]), ("queued", 0, "看图列式"))
        path = f"/api/v1/admin/xhs-research/tasks/{task['id']}"
        self.assertEqual(self.client.post(path + "/results", json={"items": []}).status_code, 409)
        self.assertEqual(self.client.post(path + "/start").json()["status"], "running")
        notes = [
            {"note_id": "65abcdef0123456789abcdef", "title": "看图列式计算", "author": "作者甲",
             "published_text": "2天前", "likes_text": "1.2万", "likes_count": 12000,
             "url": "https://www.xiaohongshu.com/search_result/65abcdef0123456789abcdef?xsec_source=pc_search",
             "sort_rank": 1, "captured_at": "2026-10-28T10:00:00Z"},
            {"note_id": "65abcdef0123456789abcdef", "title": "重复笔记", "author": "作者甲",
             "published_text": "2天前", "likes_text": "1.2万", "likes_count": 12000,
             "url": "https://www.xiaohongshu.com/search_result/65abcdef0123456789abcdef", "sort_rank": 2,
             "captured_at": "2026-10-28T10:00:00Z"},
            {"note_id": "65abcdef0123456789abcdee", "title": "找规律", "author": "作者乙",
             "published_text": "昨天", "likes_text": "100", "likes_count": 100,
             "url": "https://www.xiaohongshu.com/explore/65abcdef0123456789abcdee", "sort_rank": 3,
             "captured_at": "2026-10-28T10:00:00Z"},
        ]
        completed = self.client.post(path + "/results", json={"items": notes}).json()
        self.assertEqual((completed["status"], completed["note_count"]), ("completed", 2))
        self.assertEqual((completed["median_likes"], completed["average_likes"]), (6050, 6050))
        self.assertEqual([note["title"] for note in completed["items"]], ["看图列式计算", "找规律"])
        self.assertEqual(self.client.post(path + "/start").status_code, 409)
        listed = self.client.get("/api/v1/admin/xhs-research/tasks").json()["items"]
        self.assertEqual(listed[0]["id"], task["id"])
        self.assertEqual(listed[0]["note_count"], 2)

    def test_task_history_is_server_paginated_with_total(self):
        for _ in range(12):
            self.create_task()

        first = self.client.get("/api/v1/admin/xhs-research/tasks?page=1&page_size=10").json()
        second = self.client.get("/api/v1/admin/xhs-research/tasks?page=2&page_size=10").json()

        self.assertEqual((first["total"], first["page"], first["page_size"]), (12, 1, 10))
        self.assertEqual(len(first["items"]), 10)
        self.assertEqual((second["total"], second["page"], second["page_size"]), (12, 2, 10))
        self.assertEqual(len(second["items"]), 2)
        self.assertFalse({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})
        self.assertEqual(self.client.get("/api/v1/admin/xhs-research/tasks?page=0").status_code, 422)
        self.assertEqual(self.client.get("/api/v1/admin/xhs-research/tasks?page_size=101").status_code, 422)

    def test_snapshot_and_library_contracts_preserve_unknown_likes(self):
        task = self.create_task()
        base = '/api/v1/admin/xhs-research'
        path = base + '/tasks/' + task['id']
        self.client.post(path + '/start').raise_for_status()
        snapshot = {
            'title': '未公开点赞数', 'likes_text': '赞', 'likes_count': None,
            'url': 'https://www.xiaohongshu.com/explore/65abcdef0123456789abcdef',
        }
        for _ in range(2):
            response = self.client.post(path + '/results', json={'items': [snapshot]})
            self.assertEqual(response.status_code, 200, response.text)
            completed = response.json()
            self.assertIsNone(completed['average_likes'])
            self.assertIsNone(completed['items'][0]['likes_count'])
            self.assertEqual(completed['items'][0]['sort_rank'], 0)
            self.assertNotIn('favorite', completed['items'][0])
        self.assertEqual(self.client.get(path).json(), completed)
        note_id = completed['items'][0]['note_id']
        for suffix in ('/notes', '/notes?task_id=' + task['id'], '/notes/' + note_id + '/history'):
            response = self.client.get(base + suffix)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIsNone(response.json()['items'][0]['likes_count'])
        note = self.client.get(base + '/notes/' + note_id)
        self.assertEqual(note.status_code, 200, note.text)
        self.assertIsNone(note.json()['likes_count'])
        self.assertFalse(note.json()['favorite'])

    def test_failed_task_can_be_retried_and_deleted(self):
        task = self.create_task()
        path = f"/api/v1/admin/xhs-research/tasks/{task['id']}"
        self.client.post(path + "/start").raise_for_status()
        self.assertEqual(self.client.post(path + "/failure", json={"error": "需要手动登录"}).json()["status"], "failed")
        retried = self.client.post(path + "/start").json()
        self.assertEqual((retried["status"], retried["error"]), ("running", ""))
        self.client.post(path + "/failure", json={"error": "再次失败"}).raise_for_status()
        self.client.delete(path).raise_for_status()
        self.assertEqual(self.client.get(path).status_code, 404)
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM xhs_research_items WHERE task_id = ?", (task["id"],)).fetchone()[0], 0)

    def test_rejects_bad_scope_and_non_xhs_note_links(self):
        self.assertEqual(self.client.post("/api/v1/admin/xhs-research/tasks", json={
            "grade": "一年级<script>", "subject": "数学", "period": "week", "sort_by": "popular", "note_limit": 20,
        }).status_code, 422)
        task = self.create_task()
        path = f"/api/v1/admin/xhs-research/tasks/{task['id']}"
        self.client.post(path + "/start").raise_for_status()
        response = self.client.post(path + "/results", json={"items": [{
            "title": "坏链接", "url": "https://evil.example/search_result/65abcdef0123456789abcdef",
        }]})
        self.assertEqual(response.status_code, 422)

    def test_only_admin_can_access_research_tasks(self):
        self.sign_in(self.author)
        for response in (
            self.client.get("/api/v1/admin/xhs-research/tasks"),
            self.client.post("/api/v1/admin/xhs-research/tasks", json={"grade": "一年级", "subject": "数学"}),
        ):
            self.assertEqual(response.status_code, 403)

    def collected(self, *, title='一年级口算', author='数学老师', likes=200, captured_at='2026-10-29T08:00:00Z', **task_patch):
        task = self.create_task(**task_patch)
        path = f"/api/v1/admin/xhs-research/tasks/{task['id']}"
        self.client.post(path + '/start').raise_for_status()
        response = self.client.post(path + '/results', json={'items': [{
            'note_id': 'untrusted-other-id', 'title': title, 'author': author, 'likes_count': likes, 'likes_text': str(likes),
            'url': 'https://www.xiaohongshu.com/explore/65abcdef0123456789abcdef', 'captured_at': captured_at,
        }]})
        response.raise_for_status()
        return task

    def test_xhs_library_dedup_preserves_marks_and_history_after_task_deletion(self):
        first = self.collected(likes=100)
        note_id = '65abcdef0123456789abcdef'
        base = '/api/v1/admin/xhs-research'
        marked = self.client.put(f'{base}/notes/{note_id}/mark', json={
            'favorite': True, 'status': 'planned', 'remark': '下周做口算题', 'revision': 0,
        })
        self.assertEqual(marked.status_code, 200, marked.text)
        second = self.collected(likes=300)
        notes = self.client.get(base + '/notes').json()
        self.assertEqual(notes['total'], 1)
        note = notes['items'][0]
        self.assertEqual((note['note_id'], note['likes_count'], note['seen_count']), (note_id, 300, 2))
        self.assertEqual((note['favorite'], note['mark_status'], note['remark']), (True, 'planned', '下周做口算题'))
        first_notes = self.client.get(base + '/notes', params={'task_id': first['id']}).json()['items']
        self.assertEqual((first_notes[0]['likes_count'], first_notes[0]['seen_before']), (100, False))
        self.assertEqual(self.client.get(base + '/notes', params={'task_id': second['id'], 'hide_seen': True}).json()['total'], 0)
        for task in (first, second):
            self.client.delete(base + '/tasks/' + task['id']).raise_for_status()
        self.assertEqual(self.client.get(base + '/notes?favorite_only=true').json()['total'], 1)
        history = self.client.get(f'{base}/notes/{note_id}/history').json()
        self.assertEqual([item['likes_count'] for item in history['items']], [300, 100])

    def test_recovered_older_task_keeps_newer_library_snapshot(self):
        self.collected(likes=500, captured_at='2026-10-29T16:00:00+08:00')
        older = self.collected(likes=100, captured_at='2026-10-28T08:00:00Z')
        base = '/api/v1/admin/xhs-research/notes'
        note = self.client.get(base).json()['items'][0]
        self.assertEqual((note['likes_count'], note['seen_count']), (500, 2))
        self.assertEqual(self.client.get(base, params={'task_id': older['id']}).json()['items'][0]['likes_count'], 100)

    def test_xhs_annotations_are_private_and_reject_stale_edits(self):
        self.collected()
        base = '/api/v1/admin/xhs-research'
        path = base + '/notes/65abcdef0123456789abcdef/mark'
        payload = {'favorite': True, 'status': 'reference', 'remark': '我的备注', 'revision': 0}
        self.assertEqual(self.client.put(path, json=payload).status_code, 200)
        self.assertEqual(self.client.put(path, json=payload).status_code, 409)
        other_admin = user_store.create_user('other-xhs-admin', 'test-password', role='admin', is_super_admin=True)
        self.sign_in(other_admin)
        note = self.client.get(base + '/notes').json()['items'][0]
        self.assertEqual((note['favorite'], note['remark'], note['revision']), (False, '', 0))
        self.assertEqual(self.client.get(base + '/notes?favorite_only=true').json()['total'], 0)
        self.sign_in(self.author)
        self.assertEqual(self.client.get(base + '/notes').status_code, 403)
        self.assertEqual(self.client.put(path, json=payload).status_code, 403)
        self.assertEqual(self.client.post(base + '/notes/export', json={'filters': {}}).status_code, 403)

    def test_xhs_note_filters_escape_wildcards_and_export_actual_xlsx(self):
        import io
        from xml.etree import ElementTree
        from zipfile import ZipFile

        self.collected(title='=HYPERLINK("恶意公式") 100%口算', author='李老师', likes=400)
        base = '/api/v1/admin/xhs-research/notes'
        for query, total in (({'q': '100%', 'author': '李', 'min_likes': 400}, 1),
                             ({'q': '100_'}, 0), ({'exclude': '卖课,口算'}, 0), ({'min_likes': 401}, 0)):
            response = self.client.get(base, params=query)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['total'], total)
        response = self.client.post(base + '/export', json={'filters': {'q': '口算'}})
        self.assertEqual(response.status_code, 200, response.text[:200] if response.status_code != 200 else '')
        self.assertIn('spreadsheetml', response.headers['content-type'])
        with ZipFile(io.BytesIO(response.content)) as archive:
            xml = ElementTree.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            self.assertEqual(len(xml.findall('.//s:row', ns)), 2)
            self.assertEqual(xml.findall('.//s:f', ns), [])
            self.assertEqual(xml.find('.//s:c[@r="A2"]', ns).attrib['t'], 'inlineStr')
        self.assertEqual(self.client.post(base + '/export', json={'filters': {}, 'note_ids': []}).status_code, 200)

    def test_xhs_batch_is_durable_ordered_deduplicated_and_owned(self):
        base = '/api/v1/admin/xhs-research/batches'
        response = self.client.post(base, json={'grade': '一年级', 'subject': '数学', 'keywords': ['口算', '应用题', ' 口算 ']})
        self.assertEqual(response.status_code, 201, response.text)
        batch = response.json()
        self.assertEqual([item['keyword'] for item in batch['items']], ['口算', '应用题'])
        self.assertEqual([item['batch_position'] for item in batch['items']], [0, 1])
        self.assertEqual(self.client.get(base + '/' + batch['id']).json(), batch)
        self.assertEqual(self.client.get(base).json()['items'][0]['total'], 2)
        self.assertEqual(self.client.post(base, json={'grade': '一年级', 'subject': '数学', 'keywords': [' ']}).status_code, 422)
        self.sign_in(user_store.create_user('batch-other-admin', 'test-password', role='admin', is_super_admin=True))
        self.assertEqual(self.client.get(base).json()['items'], [])
        self.assertEqual(self.client.get(base + '/' + batch['id']).status_code, 404)

    def test_task_endpoints_and_snapshot_filters_reject_another_admin(self):
        base = '/api/v1/admin/xhs-research'
        batch = self.client.post(base + '/batches', json={'grade': '一年级', 'subject': '数学', 'keywords': ['口算']}).json()
        task_id = batch['items'][0]['id']
        collected = self.collected()
        self.sign_in(user_store.create_user('task-isolation-admin', 'test-password', role='admin', is_super_admin=True))
        own = self.create_task(keyword='自己的任务')
        listing = self.client.get(base + '/tasks').json()
        self.assertEqual((listing['total'], [item['id'] for item in listing['items']]), (1, [own['id']]))
        for identifier in (task_id, collected['id']):
            path = base + '/tasks/' + identifier
            for response in (
                self.client.get(path), self.client.post(path + '/start'),
                self.client.post(path + '/results', json={'items': []}),
                self.client.post(path + '/failure', json={'error': '其他账号覆盖'}), self.client.delete(path),
                self.client.get(base + '/notes', params={'task_id': identifier}),
                self.client.post(base + '/notes/export', json={'filters': {'task_id': identifier}}),
            ):
                self.assertEqual(response.status_code, 404, response.text)
        # 公开参考笔记仍可共享，不能借此修改其他账号的任务或读取私人备注。
        note = self.client.get(base + '/notes/65abcdef0123456789abcdef')
        self.assertEqual(note.status_code, 200, note.text)
        self.assertEqual(note.json()['remark'], '')
        self.sign_in(self.admin)
        self.assertEqual(self.client.get(base + '/tasks/' + task_id).json()['status'], 'queued')
        self.assertEqual(self.client.get(base + '/tasks/' + collected['id']).json()['status'], 'completed')

    def test_concurrent_admin_snapshots_keep_the_latest_capture_and_both_observations(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch

        from app.services import xhs_research as service

        other = user_store.create_user('snapshot-concurrent-admin', 'test-password', role='admin', is_super_admin=True)
        tasks = [service.create_task(owner, '一年级', '数学', '口算', 'week', 'popular', 20)
                 for owner in (self.admin.id, other.id)]
        for owner, task in zip((self.admin.id, other.id), tasks, strict=True):
            service.start_task(owner, task['id'])
        barrier = threading.Barrier(2)
        capture = service._capture_time

        def simultaneous(value):
            barrier.wait(timeout=3)
            return capture(value)

        note = {'title': '并发快照', 'author': '数学老师', 'published_text': '', 'likes_text': '',
                'url': 'https://www.xiaohongshu.com/explore/65abcdef0123456789abcdef', 'sort_rank': 1}
        with patch.object(service, '_capture_time', side_effect=simultaneous), ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(service.save_items, owner, task['id'], [{**note, 'likes_count': likes, 'captured_at': when}])
                       for owner, task, likes, when in ((self.admin.id, tasks[0], 500, '2026-10-31T12:00:00Z'),
                                                      (other.id, tasks[1], 100, '2026-10-30T12:00:00Z'))]
            for future in futures:
                self.assertEqual(future.result(timeout=5)['status'], 'completed')
        library = service.get_note(self.admin.id, '65abcdef0123456789abcdef')
        self.assertEqual((library['likes_count'], library['seen_count']), (500, 2))

    def test_xhs_migration_backfills_old_snapshots_and_is_idempotent(self):
        from app.xhs_research_schema import migrate

        self.collected()
        with db() as conn:
            conn.execute('DELETE FROM xhs_research_observations')
            conn.execute('DELETE FROM xhs_research_notes')
            migrate(conn)
            migrate(conn)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM xhs_research_notes').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM xhs_research_observations').fetchone()[0], 1)

    def test_snapshot_time_migration_matches_runtime_for_old_and_invalid_times(self):
        from datetime import UTC, datetime

        from app.xhs_research_schema import migrate

        self.collected()
        with db() as conn:
            conn.execute("SET LOCAL TIME ZONE 'Asia/Shanghai'")
            for value, expected in (
                ('2026-10-29T08:00:00', datetime(2026, 10, 29, 8, tzinfo=UTC)),
                ('2026-10-29T08:00:00+08:00', datetime(2026, 10, 29, tzinfo=UTC)),
                ('20261029T080000', datetime(2026, 10, 29, 8, tzinfo=UTC)),
                ('now', datetime.min.replace(tzinfo=UTC)),
                ('', datetime.min.replace(tzinfo=UTC)),
            ):
                conn.execute('ALTER TABLE xhs_research_notes ALTER COLUMN captured_epoch DROP NOT NULL')
                conn.execute('UPDATE xhs_research_notes SET captured_at=?,captured_epoch=NULL', (value,))
                migrate(conn)
                migrate(conn)
                self.assertEqual(conn.execute('SELECT captured_epoch FROM xhs_research_notes').fetchone()[0], expected.timestamp())
