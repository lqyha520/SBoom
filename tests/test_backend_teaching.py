"""真实一次性 PostgreSQL 验证功能下线、题库隔离、排期竞态与文件体检。"""

import asyncio
import socket
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import httpx
import test_backend_catalog as fixtures

from app.db import db
from app.models.teaching import ScheduleInput
from app.routers import teaching
from app.services import catalog_operations


class TeachingContracts(unittest.TestCase):
    sign_in = fixtures.PublicCatalogContracts.sign_in
    source = fixtures.PublicCatalogContracts.source
    draft = fixtures.PublicCatalogContracts.draft
    update = fixtures.PublicCatalogContracts.update
    publish = fixtures.PublicCatalogContracts.publish

    def setUp(self):
        fixtures.PublicCatalogContracts.setUp(self)
        self.client.app.include_router(teaching.router)

    def bank_content(self, **changes):
        return {'title': '加法练习', 'grade': '一年级', 'subject': '数学', 'topic': '十以内加法',
                'section_type': 'oral_math', 'difficulty': 'easy',
                'questions': [{'stem': '2 + 3 = __', 'answer': 5, 'analysis': '2 加 3 等于 5', 'quality_status': 'passed'}], **changes}

    def test_curriculum_is_retired_and_due_subscriptions_no_longer_send_messages(self):
        import threading
        from types import SimpleNamespace

        from app.services import curriculum, mini_jobs

        paper = self.publish()
        now = int(time.time())
        with db() as conn:
            conn.execute("INSERT INTO mini_curriculum_subscriptions(id,user_id,grade,subject,notify,created_at) VALUES ('retired',?,?,?,1,?)", (self.viewer.id, paper['grade'], paper['subject'], now - 86401))
            conn.execute("INSERT INTO mini_curriculum_digest(subscription_id,checked_at) VALUES ('retired',?)", (now - 86401,))
        self.sign_in(self.viewer)
        for method, path in [('GET', ''), ('PUT', ''), ('GET', '/recommendations'), ('GET', '/textbooks'), ('DELETE', '/retired')]:
            response = self.client.request(method, '/api/v1/mini/curriculum' + path)
            self.assertEqual(response.status_code, 410, response.text)
            self.assertIn('请到习题库', response.text)
        settings = SimpleNamespace(maintenance_enabled=False, teaching_jobs_enabled=True, wechat_subscribe_template_id='', wechat_pay_auto_reconcile=False)
        with patch('app.services.mini_jobs.get_settings', return_value=settings), patch('app.services.mini_jobs.configuration', return_value={'ready': False}), patch('app.services.wechat_virtual_pay.configuration', return_value={'ready': False}), patch('app.services.catalog_operations.schedule_tick') as schedule, patch('app.services.curriculum.digest_tick') as digest:
            mini_jobs.tick(threading.Event())
            schedule.assert_called_once()
            digest.assert_not_called()
        curriculum.digest_tick(now)
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_notifications WHERE kind='curriculum'").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT checked_at FROM mini_curriculum_digest WHERE subscription_id='retired'").fetchone()[0], now - 86401)

    def test_retired_curriculum_history_opens_library_and_obsolete_disclosure_is_hidden(self):
        from app.services import site_content
        from app.services.wechat_notices import destination

        self.assertEqual(destination({'target_type': 'curriculum', 'target_id': 'old-subscription'}), 'pages/library/index')
        disclosure = '你主动设置的教材关注（年级、学科、教材和上新提醒开关）保存在账号中，供跨设备推荐资料和发送上新提醒；取消关注后删除相应设置。'
        body = '管理员的隐私说明。' + disclosure + '联系客服可申请删除账号。'
        with db() as conn:
            conn.execute("UPDATE site_documents SET body=?,revision=3 WHERE key='privacy'", (body,))
        result = site_content.get_document('privacy')
        self.assertEqual(result['body'], body.replace(disclosure, ''))
        self.assertEqual(result['revision'], 3)
        with db() as conn:
            self.assertEqual(conn.execute("SELECT body FROM site_documents WHERE key='privacy'").fetchone()[0], body)

    def test_pending_retired_notices_are_skipped_without_sending_or_consuming_credit(self):
        from app.services import wechat_notices

        now = int(time.time())
        with db() as conn:
            conn.execute("INSERT INTO mini_notice_subscriptions(user_id,template_id,credits,updated_at) VALUES (?,'template',1,?)", (self.viewer.id, now))
            conn.execute("INSERT INTO mini_notifications(id,user_id,event_key,kind,title,body,target_type,target_id,created_at) VALUES ('legacy-news',?,'legacy','curriculum','教材上新','旧消息','curriculum','',?)", (self.viewer.id, now))
            conn.execute("INSERT INTO mini_notice_deliveries(notification_id,updated_at) VALUES ('legacy-news',?)", (now,))
        with patch('app.services.wechat_notices.configuration', return_value={'available': True}), patch('app.services.wechat_notices.send') as send:
            self.assertTrue(wechat_notices.dispatch_one())
            send.assert_not_called()
        with db() as conn:
            delivery = conn.execute("SELECT status,error_code FROM mini_notice_deliveries WHERE notification_id='legacy-news'").fetchone()
            self.assertEqual((delivery['status'], delivery['error_code']), ('skipped', 'FEATURE_RETIRED'))
            self.assertEqual(conn.execute('SELECT credits FROM mini_notice_subscriptions WHERE user_id=?', (self.viewer.id,)).fetchone()[0], 1)

    def test_bank_dedup_metadata_conflict_account_isolation_and_quality(self):
        self.sign_in(self.author)
        item = self.client.post('/api/v1/question-bank', json=self.bank_content()).json()
        self.assertEqual(item['questions'][0]['quality_status'], 'unchecked')
        duplicate = self.client.post('/api/v1/question-bank', json=self.bank_content()).json()
        self.assertEqual(item['id'], duplicate['id'])
        path = '/api/v1/question-bank/' + item['id']
        body = {'title': '好题', 'topic': '加法', 'difficulty': 'medium', 'revision': 1}
        self.assertEqual(self.client.patch(path, json=body).json()['revision'], 2)
        self.assertEqual(self.client.patch(path, json=body).status_code, 409)
        self.assertEqual(self.client.get('/api/v1/question-bank', params={'q': '好题', 'difficulty': 'medium'}).json()['total'], 1)
        self.assertEqual(self.client.delete(path + '?revision=1').status_code, 409)
        self.sign_in(self.admin)
        self.assertEqual(self.client.get('/api/v1/question-bank').json()['total'], 0)
        self.assertEqual(self.client.patch(path, json=body).status_code, 404)
        self.assertEqual(self.client.post('/api/v1/question-bank/selection', json={'ids': [item['id']]}).status_code, 404)
        self.assertEqual(self.client.delete(path + '?revision=2').status_code, 404)
        self.sign_in(self.author)
        self.assertEqual(self.client.delete(path + '?revision=2').status_code, 204)

    def test_bank_rejects_samples_invalid_reading_mixed_grade_and_retains_order(self):
        self.sign_in(self.author)
        for body in (self.bank_content(questions=[{'stem': '示例', 'answer': 1, '_preview': True}]),
                     self.bank_content(section_type='reading'), self.bank_content(questions=[])):
            self.assertEqual(self.client.post('/api/v1/question-bank', json=body).status_code, 422)
        first = self.client.post('/api/v1/question-bank', json=self.bank_content()).json()
        second = self.client.post('/api/v1/question-bank', json=self.bank_content(section_type='reading', passage='小明在读书。',
                                  questions=[{'stem': '谁在读书？', 'answer': '小明', 'analysis': '依据第一句'}])).json()
        third = self.client.post('/api/v1/question-bank', json=self.bank_content(grade='二年级')).json()
        selected = self.client.post('/api/v1/question-bank/selection', json={'ids': [second['id'], first['id']]}).json()
        self.assertEqual([i['id'] for i in selected['items']], [second['id'], first['id']])
        self.assertEqual(selected['items'][0]['passage'], '小明在读书。')
        self.assertEqual(self.client.post('/api/v1/question-bank/selection', json={'ids': [third['id'], first['id']]}).status_code, 422)




    def test_schedule_publishes_once_and_leaves_a_review(self):
        draft = self.draft()
        now = int(time.time())
        response = self.client.put('/api/v1/admin/catalog/schedules/' + draft['id'],
                                   json={'scheduled_at': now + 120, 'catalog_revision': draft['revision'], 'confirm_publication': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get('/api/v1/admin/catalog/schedules').json()['total'], 1)
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(catalog_operations.schedule_tick, [now + 121, now + 121]))
        with db() as conn:
            self.assertEqual(conn.execute('SELECT status FROM catalog_papers WHERE id=?', (draft['id'],)).fetchone()[0], 'published')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM catalog_reviews WHERE catalog_id=?', (draft['id'],)).fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT status FROM catalog_schedules WHERE catalog_id=?', (draft['id'],)).fetchone()[0], 'published')

    def test_schedule_changed_content_and_files_are_never_published(self):
        now = int(time.time())
        draft = self.draft()
        catalog_operations.schedule(self.admin.id, draft['id'], ScheduleInput(scheduled_at=now + 120, catalog_revision=1, confirm_publication=True))
        self.update(draft, title='修改后的资料')
        catalog_operations.schedule_tick(now + 121)
        with db() as conn:
            self.assertEqual(conn.execute('SELECT status FROM catalog_papers WHERE id=?', (draft['id'],)).fetchone()[0], 'draft')
            self.assertEqual(conn.execute('SELECT status FROM catalog_schedules WHERE catalog_id=?', (draft['id'],)).fetchone()[0], 'failed')
        draft = self.draft()
        catalog_operations.schedule(self.admin.id, draft['id'], ScheduleInput(scheduled_at=now + 120, catalog_revision=1, confirm_publication=True))
        with db() as conn:
            asset = conn.execute("SELECT storage_key FROM paper_assets WHERE paper_id=(SELECT paper_id FROM catalog_papers WHERE id=?) AND kind='pdf'", (draft['id'],)).fetchone()
        from app.services.paper_storage import storage_for
        storage_for().path(asset[0]).unlink()
        catalog_operations.schedule_tick(now + 121)
        health = next(i for i in catalog_operations.health(self.admin.id)['items'] if i['catalog_id'] == draft['id'])
        self.assertTrue(any(i['code'] == 'asset_unavailable' for i in health['issues']))

    def test_cancel_schedule_and_permission_revocation(self):
        now = int(time.time())
        draft = self.draft()
        scheduled = catalog_operations.schedule(self.admin.id, draft['id'], ScheduleInput(scheduled_at=now + 120, catalog_revision=1, confirm_publication=True))
        path = '/api/v1/admin/catalog/schedules/' + draft['id']
        self.assertEqual(self.client.delete(path + '?revision=9').status_code, 409)
        self.assertEqual(self.client.delete(path + '?revision=' + str(scheduled['revision'])).status_code, 204)
        catalog_operations.schedule_tick(now + 121)
        scheduled = catalog_operations.schedule(self.admin.id, draft['id'], ScheduleInput(scheduled_at=now + 120, catalog_revision=1, schedule_revision=scheduled['revision'] + 1, confirm_publication=True))
        with db() as conn:
            conn.execute('UPDATE users SET is_active=0 WHERE id=?', (self.admin.id,))
        catalog_operations.schedule_tick(now + 121)
        with db() as conn:
            self.assertEqual(conn.execute('SELECT status FROM catalog_schedules WHERE catalog_id=?', (draft['id'],)).fetchone()[0], 'failed')

    def test_link_probe_always_blocks_private_network_and_redirects(self):
        request = httpx.Request('GET', 'https://example.com/share')
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
        with patch('app.services.catalog_operations.socket.getaddrinfo', return_value=addresses):
            with self.assertRaises(ValueError):
                asyncio.run(catalog_operations._pin_link(request))
        with self.assertRaises(ValueError):
            asyncio.run(catalog_operations._pin_link(httpx.Request('GET', 'https://example.com:55432/')))

    def test_schedule_rejects_stale_timetable_and_changed_effective_access(self):
        now = int(time.time())
        draft = self.draft()
        body = ScheduleInput(scheduled_at=now + 120, catalog_revision=1, confirm_publication=True)
        first = catalog_operations.schedule(self.admin.id, draft['id'], body)
        stale = self.client.put('/api/v1/admin/catalog/schedules/' + draft['id'], json=body.model_dump())
        self.assertEqual(stale.status_code, 409)
        with db() as conn:
            kind = conn.execute('SELECT question_type FROM catalog_question_types WHERE catalog_id=? LIMIT 1', (draft['id'],)).fetchone()[0]
            conn.execute("INSERT INTO catalog_type_rules(question_type,view_access,download_access,revision,updated_at) VALUES (?,'vip','vip',1,?) "
                         "ON CONFLICT(question_type) DO UPDATE SET view_access='vip',download_access='vip',revision=catalog_type_rules.revision+1", (kind, now))
        catalog_operations.schedule_tick(now + 121)
        with db() as conn:
            result = conn.execute('SELECT status,message FROM catalog_schedules WHERE catalog_id=?', (draft['id'],)).fetchone()
            self.assertEqual(result['status'], 'failed')
            self.assertIn('权限已变化', result['message'])
            self.assertEqual(first['status'], 'pending')

    def test_schedule_and_health_follow_creator_scope_and_revoked_publish_grant(self):
        from app.services import admin_access, user_store
        foreign = self.draft()
        editor = user_store.create_user('teaching-editor', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, editor.id, 1, {'papers': ['view', 'create', 'publish']})
        self.sign_in(editor)
        source = self.source(editor)
        own = self.client.post('/api/v1/admin/catalog/papers', json={'paper_id': source['id']}).json()
        response = self.client.get('/api/v1/admin/catalog/health')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([i['catalog_id'] for i in response.json()['items']], [own['id']])
        self.assertEqual(self.client.get('/api/v1/admin/catalog/schedules/' + foreign['id']).status_code, 404)
        now = int(time.time())
        body = {'scheduled_at': now + 120, 'catalog_revision': 1, 'confirm_publication': True}
        self.assertEqual(self.client.put('/api/v1/admin/catalog/schedules/' + foreign['id'], json=body).status_code, 404)
        self.assertEqual(self.client.put('/api/v1/admin/catalog/schedules/' + own['id'], json=body).status_code, 200)
        admin_access.save_permissions(self.admin.id, editor.id, 2, {'papers': ['view']})
        self.assertEqual(self.client.delete('/api/v1/admin/catalog/schedules/' + own['id'] + '?revision=1').status_code, 403)
        catalog_operations.schedule_tick(now + 121)
        with db() as conn:
            self.assertEqual(conn.execute('SELECT status FROM catalog_schedules WHERE catalog_id=?', (own['id'],)).fetchone()[0], 'failed')


    def test_bank_filter_choices_use_all_own_saved_questions_even_when_search_is_empty(self):
        self.sign_in(self.author)
        self.client.post('/api/v1/question-bank', json=self.bank_content())
        self.client.post('/api/v1/question-bank', json=self.bank_content(grade='二年级', subject='语文'))
        response = self.client.get('/api/v1/question-bank', params={'q': '不存在的题目'}).json()
        self.assertEqual(response['total'], 0)
        self.assertEqual(response['bank_total'], 2)
        self.assertEqual(response['available'], {'一年级': ['数学'], '二年级': ['语文']})
        self.sign_in(self.admin)
        empty = self.client.get('/api/v1/question-bank').json()
        self.assertEqual(empty['bank_total'], 0)
        self.assertEqual(empty['available'], {})

    def test_health_finds_file_issues_beyond_first_page_and_counts_each_affected_paper(self):
        from app.models.catalog import CatalogCreate
        from app.services import public_catalog
        from app.services.paper_storage import storage_for
        bad = self.draft()
        normal = [public_catalog.create_paper(self.admin.id, CatalogCreate(title=f'正常资料 {index}', grade='小学一年级', subject='数学',
                  download_mode='external', external_url='https://example.com/share')) for index in range(23)]
        for value in normal:
            catalog_operations.record_link(self.admin.id, value['id'], 'https://example.com/share', 'confirmed', '已核验')
        with db() as conn:
            conn.execute("INSERT INTO catalog_tags(id,kind,name) VALUES ('health-book','textbook','体检教材')")
            conn.execute("INSERT INTO catalog_paper_tags(catalog_id,tag_id) SELECT id,'health-book' FROM catalog_papers")
            conn.execute("UPDATE catalog_papers SET reviewed_at=1,answer_readiness='included',updated_at=100")
            conn.execute('UPDATE catalog_papers SET updated_at=0 WHERE id=?', (bad['id'],))
            asset = conn.execute("SELECT storage_key FROM paper_assets WHERE paper_id=(SELECT paper_id FROM catalog_papers WHERE id=?) AND kind='pdf'", (bad['id'],)).fetchone()
        storage_for().path(asset[0]).unlink()
        first = self.client.get('/api/v1/admin/catalog/health').json()
        self.assertEqual(first['total'], 24)
        self.assertNotIn(bad['id'], [item['catalog_id'] for item in first['items']])
        issues = self.client.get('/api/v1/admin/catalog/health', params={'only_issues': True}).json()
        self.assertEqual([item['catalog_id'] for item in issues['items']], [bad['id']])
        self.assertEqual(issues['counts']['all'], 24)
        self.assertEqual(issues['counts']['file'], 1)
        self.assertEqual(issues['total'], 1)
        self.assertFalse(issues['has_more'])
        filtered = self.client.get('/api/v1/admin/catalog/health', params={'category': 'file', 'offset': 1}).json()
        self.assertEqual(filtered['total'], 1)
        self.assertEqual(filtered['items'], [])
        self.assertEqual(self.client.get('/api/v1/admin/catalog/health', params={'category': 'preview'}).json()['total'], 0)
        with db() as conn:
            conn.execute("UPDATE catalog_papers SET answer_readiness='unknown' WHERE id=?", (normal[0]['id'],))
        answers = self.client.get('/api/v1/admin/catalog/health', params={'category': 'answers'}).json()
        self.assertEqual(answers['total'], 1)
        self.assertEqual(answers['counts']['issues'], 2)
        searched = self.client.get('/api/v1/admin/catalog/health', params={'q': '正常资料', 'category': 'file'}).json()
        self.assertEqual(searched['total'], 0)
        self.assertEqual(searched['counts']['all'], 23)

    def test_schedule_status_counts_and_health_categories_remain_creator_scoped(self):
        from app.services import admin_access, user_store
        now = int(time.time())
        foreign = self.draft()
        catalog_operations.schedule(self.admin.id, foreign['id'], ScheduleInput(scheduled_at=now + 120, catalog_revision=1, confirm_publication=True))
        editor = user_store.create_user('scoped-teaching-editor', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, editor.id, 1, {'papers': ['view', 'create', 'publish']})
        self.sign_in(editor)
        own = self.draft(self.source(editor))
        other = self.draft(self.source(editor))
        for value in (own, other):
            catalog_operations.schedule(editor.id, value['id'], ScheduleInput(scheduled_at=now + 120, catalog_revision=1, confirm_publication=True))
        self.sign_in(self.admin)
        self.assertEqual(self.update(own, title='排期后发生变更').status_code, 200)
        self.sign_in(editor)
        catalog_operations.schedule_tick(now + 121)
        failed = self.client.get('/api/v1/admin/catalog/schedules', params={'status': 'failed'}).json()
        self.assertEqual([item['catalog_id'] for item in failed['items']], [own['id']])
        self.assertEqual(failed['counts'], {'all': 2, 'failed': 1, 'pending': 0, 'published': 1, 'cancelled': 0})
        self.assertEqual(failed['total'], 1)
        self.assertEqual(self.client.get('/api/v1/admin/catalog/schedules', params={'status': 'pending'}).json()['items'], [])
        health = self.client.get('/api/v1/admin/catalog/health', params={'category': 'textbook'}).json()
        self.assertEqual(health['counts']['all'], 2)
        self.assertEqual({item['catalog_id'] for item in health['items']}, {own['id'], other['id']})
        self.assertEqual(self.client.get('/api/v1/admin/catalog/health', params={'category': 'invalid'}).status_code, 422)
        self.assertEqual(self.client.get('/api/v1/admin/catalog/schedules', params={'status': 'invalid'}).status_code, 422)
