"""Consumer/admin workflows exercised across real HTTP, permissions and persistence."""

import time
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import test_backend_catalog as fixtures

from app import db as database
from app.models.mini import MembershipUpdate
from app.routers import engagement, experience, site
from app.services import mini_auth, mini_experience


class ExperienceContracts(unittest.TestCase):
    sign_in = fixtures.PublicCatalogContracts.sign_in
    source = fixtures.PublicCatalogContracts.source
    draft = fixtures.PublicCatalogContracts.draft
    update = fixtures.PublicCatalogContracts.update
    publish = fixtures.PublicCatalogContracts.publish

    def setUp(self):
        fixtures.PublicCatalogContracts.setUp(self)
        for router in (experience.router, site.router, site.admin_router, engagement.router):
            self.client.app.include_router(router)

    def test_favorite_batch_assign_ungrouped_remove_and_account_isolation(self):
        papers = [self.publish(), self.publish()]
        ids = [paper["id"] for paper in papers]
        self.sign_in(self.viewer)
        for identifier in ids:
            self.client.put(f"/api/v1/catalog/papers/{identifier}/favorite", json={"favorite": True}).raise_for_status()
        group = self.client.post("/api/v1/mini/favorite-groups", json={"name": "复习资料"}).json()
        path = "/api/v1/mini/favorites/batch"
        response = self.client.post(path, json={"ids": ids, "action": "assign", "group_id": group["id"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get("/api/v1/catalog/papers?favorite=true&ungrouped=true").json()["total"], 0)
        self.assertEqual(self.client.get("/api/v1/catalog/papers", params={"favorite_group": group["id"]}).json()["total"], 2)
        self.client.post(path, json={"ids": [ids[0]], "action": "assign"}).raise_for_status()
        result = self.client.get("/api/v1/catalog/papers?favorite=true&ungrouped=true").json()
        self.assertEqual([item["id"] for item in result["items"]], [ids[0]])
        self.sign_in(self.other)
        self.assertEqual(self.client.get("/api/v1/catalog/papers?ungrouped=true").json()["total"], 0)
        self.assertEqual(self.client.post(path, json={"ids": ids, "action": "assign", "group_id": group["id"]}).status_code, 404)
        self.client.post(path, json={"ids": ids, "action": "remove"}).raise_for_status()
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get("/api/v1/catalog/papers?favorite=true").json()["total"], 2)
        for _ in range(2):
            self.client.post(path, json={"ids": ids, "action": "remove"}).raise_for_status()
        self.assertEqual(self.client.get("/api/v1/catalog/papers?favorite=true").json()["total"], 0)
        self.assertEqual(self.client.get("/api/v1/mini/favorite-groups").json()["items"][0]["paper_count"], 0)
        self.client.headers.pop("Authorization")
        self.assertEqual(self.client.get("/api/v1/catalog/papers?ungrouped=true").status_code, 401)
        self.assertEqual(self.client.post(path, json={"ids": ids, "action": "remove"}).status_code, 401)

    def test_favorite_batch_conflict_is_atomic_and_inputs_are_bounded(self):
        paper = self.publish()
        self.sign_in(self.viewer)
        self.client.put(f"/api/v1/catalog/papers/{paper['id']}/favorite", json={"favorite": True}).raise_for_status()
        group = self.client.post("/api/v1/mini/favorite-groups", json={"name": "原分组"}).json()
        other = self.client.post("/api/v1/mini/favorite-groups", json={"name": "新分组"}).json()
        path = "/api/v1/mini/favorites/batch"
        self.client.post(path, json={"ids": [paper["id"]], "action": "assign", "group_id": group["id"]}).raise_for_status()
        response = self.client.post(path, json={"ids": [paper["id"], "missing"], "action": "assign", "group_id": other["id"]})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.client.get("/api/v1/catalog/papers", params={"favorite_group": group["id"]}).json()["total"], 1)
        for ids in ([], [paper["id"], paper["id"]], ["x" * 65], [str(i) for i in range(201)]):
            self.assertEqual(self.client.post(path, json={"ids": ids, "action": "remove"}).status_code, 422)
        self.assertEqual(self.client.post(path, json={"ids": [paper["id"]], "action": "remove", "group_id": group["id"]}).status_code, 422)

    def test_home_mode_defaults_to_welcome_and_rejects_stale_updates(self):
        path = '/api/v1/admin/site/home-settings'
        self.assertEqual(self.client.get(path).json(), {'revision': 0, 'banner_mode': 'welcome'})
        response = self.client.put(path, json={'revision': 0, 'banner_mode': 'operations'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get('/api/v1/site/home').json()['banner_mode'], 'operations')
        self.assertEqual(self.client.put(path, json={'revision': 0, 'banner_mode': 'welcome'}).status_code, 409)
        self.assertEqual(self.client.put(path, json={'revision': 1, 'banner_mode': 'invalid'}).status_code, 422)
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/v1/site/home').json()['banner_mode'], 'operations')
        self.assertEqual(self.client.get(path).status_code, 401)

    def test_current_documents_are_readable_before_login(self):
        docs = self.client.get('/api/v1/admin/site/documents').json()['items']
        document = next(item for item in docs if item['key'] == 'privacy')
        response = self.client.put('/api/v1/admin/site/documents/privacy', json={
            'revision': document['revision'], 'title': '正式隐私政策', 'body': '本服务的正式联系渠道。'})
        self.assertEqual(response.status_code, 200, response.text)
        database.init_db()
        self.client.cookies.clear()
        response = self.client.get('/api/v1/site/documents/privacy')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['body'], '本服务的正式联系渠道。')
        self.assertEqual(self.client.get('/api/v1/site/documents/agreement').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/admin/site/documents').status_code, 401)

    def test_nickname_does_not_change_login_and_migration_keeps_edits(self):
        self.sign_in(self.viewer)
        response = self.client.patch('/api/v1/mini/me', json={'nickname': '新的昵称'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['username'], self.viewer.username)
        self.assertEqual(response.json()['nickname'], '新的昵称')
        database.init_db()
        self.assertEqual(mini_auth.get_user(self.viewer.id).nickname, '新的昵称')
        self.assertEqual(mini_auth.login_password(self.viewer.username, 'test-password')['user']['nickname'], '新的昵称')
        # Display names can repeat; a second account never acquires this login identity.
        self.sign_in(self.other)
        self.assertEqual(self.client.patch('/api/v1/mini/me', json={'nickname': '新的昵称'}).status_code, 200)

    def test_feedback_reply_is_scoped_and_internal_notes_stay_private(self):
        paper = self.publish()
        self.sign_in(self.viewer)
        response = self.client.post('/api/v1/mini/feedback', json={'catalog_id': paper['id'], 'kind': 'correction', 'body': '第三题的答案需要核对。'})
        self.assertEqual(response.status_code, 201, response.text)
        item = response.json()
        self.sign_in(self.other)
        self.assertEqual(self.client.get('/api/v1/mini/feedback').json()['total'], 0)
        self.assertEqual(self.client.get('/api/v1/admin/experience/feedback').status_code, 401)
        self.sign_in(self.admin)
        body = {'revision': item['revision'], 'status': 'resolved', 'reply': '已修正答案，感谢反馈。', 'internal_note': 'internal-only-marker'}
        path = '/api/v1/admin/experience/feedback/' + item['id']
        self.assertEqual(self.client.put(path, json=body).status_code, 200)
        self.assertEqual(self.client.put(path, json=body).status_code, 409)
        self.sign_in(self.viewer)
        response = self.client.get('/api/v1/mini/feedback')
        self.assertEqual(response.json()['items'][0]['reply'], body['reply'])
        self.assertNotIn('internal-only-marker', response.text)

    def test_feedback_validation_and_public_support_settings(self):
        response = self.client.put('/api/v1/admin/experience/support', json={'revision': 0, 'wechat': 'coach-help', 'benefits': '会员资料说明'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.put('/api/v1/admin/experience/support', json={'revision': 0}).status_code, 409)
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/v1/site/support').json()['wechat'], 'coach-help')
        self.sign_in(self.viewer)
        self.assertEqual(self.client.post('/api/v1/mini/feedback', json={'kind': 'correction', 'body': '没有关联具体资料'}).status_code, 422)
        self.assertEqual(self.client.post('/api/v1/mini/feedback', json={'kind': 'membership', 'body': '我想续期一个月'}).status_code, 201)

    def test_feedback_submission_limit_is_scoped_per_account(self):
        self.sign_in(self.viewer)
        body = {'kind': 'other', 'body': '请协助核实使用问题'}
        for _ in range(10):
            self.assertEqual(self.client.post('/api/v1/mini/feedback', json=body).status_code, 201)
        self.assertEqual(self.client.post('/api/v1/mini/feedback', json=body).status_code, 429)
        self.sign_in(self.other)
        self.assertEqual(self.client.post('/api/v1/mini/feedback', json=body).status_code, 201)

    def test_renewal_adds_to_existing_expiry_and_rejects_replay(self):
        expiry = int(time.time()) + 3 * 86400
        updated = mini_auth.update_membership(self.admin.id, self.viewer.id, MembershipUpdate(
            revision=1, membership='vip', vip_expires_at=expiry, is_active=True))
        path = '/api/v1/admin/mini-users/' + self.viewer.id
        self.assertEqual(self.client.get('/api/v1/admin/mini-users?membership=expiring').json()['total'], 1)
        body = {'revision': updated['revision'], 'days': 30, 'note': '续期已核实'}
        response = self.client.post(path + '/renew', json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['vip_expires_at'], expiry + 30 * 86400)
        self.assertEqual(self.client.post(path + '/renew', json=body).status_code, 409)
        events = self.client.get(path + '/events').json()['items']
        self.assertTrue(any(item['after'].get('note') == body['note'] for item in events))
        self.sign_in(self.other)
        self.assertEqual(self.client.get(path + '/events').status_code, 401)

    def test_expired_renewal_starts_now_and_lifetime_cannot_extend(self):
        row = mini_auth.update_membership(self.admin.id, self.viewer.id, MembershipUpdate(
            revision=1, membership='vip', vip_expires_at=int(time.time()) - 100, is_active=False))
        path = '/api/v1/admin/mini-users/' + self.viewer.id + '/renew'
        response = self.client.post(path, json={'revision': row['revision'], 'days': 30})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()['is_active'])
        self.assertAlmostEqual(response.json()['vip_expires_at'], int(time.time()) + 30 * 86400, delta=3)
        row = mini_auth.update_membership(self.admin.id, self.viewer.id, MembershipUpdate(
            revision=response.json()['revision'], membership='vip', vip_expires_at=None, is_active=True))
        self.assertEqual(self.client.post(path, json={'revision': row['revision'], 'days': 30}).status_code, 409)

    def test_batch_conflict_rolls_back_all_items(self):
        first, second = self.draft(), self.draft()
        body = {'action': 'published', 'confirm_publication': True, 'items': [{'id': first['id'], 'revision': 1}, {'id': second['id'], 'revision': 999}]}
        self.assertEqual(self.client.post('/api/v1/admin/catalog/batch', json=body).status_code, 409)
        self.assertEqual(self.client.get('/api/v1/admin/catalog/papers/' + first['id']).json()['status'], 'draft')
        body['items'][1]['revision'] = second['revision']
        self.assertEqual(self.client.post('/api/v1/admin/catalog/batch', json=body).json()['updated'], 2)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get('/api/v1/catalog/papers').json()['total'], 2)

    def test_batch_category_and_permission_preview(self):
        paper = self.publish()
        category = self.client.post('/api/v1/admin/site/categories', json={'name': '期末复习'}).json()
        result = self.client.post('/api/v1/admin/catalog/batch', json={'action': 'category', 'category_id': category['id'], 'items': [{'id': paper['id'], 'revision': paper['revision']}]})
        self.assertEqual(result.status_code, 200, result.text)
        result = self.client.post('/api/v1/admin/catalog/batch', json={'action': 'access', 'view_access': 'vip', 'download_access': 'vip', 'items': [{'id': paper['id'], 'revision': paper['revision'] + 1}]})
        self.assertEqual(result.status_code, 200, result.text)
        path = '/api/v1/admin/catalog/papers/' + paper['id'] + '/preview'
        normal = self.client.get(path + '?membership=regular').json()
        self.assertFalse(normal['can_view'])
        self.assertIsNone(normal['snapshot'])
        self.assertEqual(normal['assets'], [])
        self.assertTrue(self.client.get(path + '?membership=vip').json()['can_download'])
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get('/api/v1/catalog/papers?only_free=true').json()['total'], 0)

    def test_batch_tags_merge_and_validation(self):
        first, second = self.publish(), self.publish()
        path = '/api/v1/admin/catalog/tags'
        def tag(kind, name):
            result = self.client.post(path, json={'kind': kind, 'name': name})
            self.assertEqual(result.status_code, 201, result.text)
            return result.json()
        old_book, new_book = tag('textbook', '北师大版'), tag('textbook', '人教版')
        addition, subtraction = tag('knowledge', '加法'), tag('knowledge', '减法')
        self.client.put('/api/v1/admin/catalog/papers/' + first['id'] + '/labels',
                        json={'revision': first['revision'], 'tag_ids': [old_book['id'], addition['id']]}).raise_for_status()
        first = self.client.get('/api/v1/admin/catalog/papers/' + first['id']).json()
        body = {'action': 'tags', 'tag_ids': [new_book['id'], addition['id'], subtraction['id']],
                'items': [{'id': first['id'], 'revision': first['revision']}, {'id': second['id'], 'revision': second['revision']}]}
        self.assertEqual(self.client.post('/api/v1/admin/catalog/batch', json=body).status_code, 200, body)
        def names(paper):
            return sorted(item['name'] for item in self.client.get('/api/v1/admin/catalog/papers/' + paper['id']).json()['tags'])
        # 旧教材被覆盖，知识点去重后追加；另一份从零打上
        self.assertEqual(names(first), ['人教版', '减法', '加法'])
        self.assertEqual(names(second), ['人教版', '减法', '加法'])
        # 教材选了两个 → 422 且不落库
        body['tag_ids'] = [new_book['id'], tag('textbook', '苏教版')['id']]
        self.assertEqual(self.client.post('/api/v1/admin/catalog/batch', json=body).status_code, 422)
        self.assertEqual(names(first), ['人教版', '减法', '加法'])
        # 空标签 → 422
        self.assertEqual(self.client.post('/api/v1/admin/catalog/batch', json={'action': 'tags', 'tag_ids': [], 'items': body['items']}).status_code, 422)

    def test_free_filter_resolves_inheritance_before_pagination(self):
        rule = next(item for item in self.client.get('/api/v1/admin/catalog/type-rules').json()['items'] if item['question_type'] == 'quiz')
        response = self.client.put('/api/v1/admin/catalog/type-rules/quiz', json={
            'revision': rule['revision'], 'view_access': 'vip', 'download_access': 'vip'})
        self.assertEqual(response.status_code, 200, response.text)
        self.publish()  # Both permissions inherit VIP access.
        free = [self.publish(), self.publish()]
        for item in free:
            self.assertEqual(self.update(item, view_access='free', download_access='free').status_code, 200)
        preview_only = self.publish()
        self.assertEqual(self.update(preview_only, view_access='free', download_access='vip').status_code, 200)
        self.sign_in(self.viewer)
        first = self.client.get('/api/v1/catalog/papers?only_free=true&limit=1').json()
        second = self.client.get('/api/v1/catalog/papers?only_free=true&limit=1&offset=1').json()
        self.assertEqual(first['total'], 2)
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])
        self.assertEqual({first['items'][0]['id'], second['items'][0]['id']}, {item['id'] for item in free})

    def test_admin_analytics_count_only_enabled_current_members(self):
        now = int(time.time())
        mini_auth.update_membership(self.admin.id, self.viewer.id, MembershipUpdate(
            revision=1, membership='vip', vip_expires_at=now - 60, is_active=True))
        current = mini_auth.update_membership(self.admin.id, self.other.id, MembershipUpdate(
            revision=1, membership='vip', vip_expires_at=now + 86400, is_active=True))
        response = self.client.get('/api/v1/admin/site/analytics')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['users']['vip'], 1)
        mini_auth.update_membership(self.admin.id, self.other.id, MembershipUpdate(
            revision=current['revision'], membership='vip', vip_expires_at=now + 86400, is_active=False))
        self.assertEqual(self.client.get('/api/v1/admin/site/analytics').json()['users']['vip'], 0)

    def test_topics_keep_order_and_hide_unpublished_items(self):
        first, second, hidden = self.publish(), self.publish(), self.draft()
        body = {'title': '复习专题', 'is_visible': True, 'paper_ids': [second['id'], hidden['id'], first['id']]}
        response = self.client.post('/api/v1/admin/experience/topics', json=body)
        self.assertEqual(response.status_code, 201, response.text)
        topic = response.json()
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get('/api/v1/site/topics').json()['items'][0]['paper_count'], 2)
        response = self.client.get('/api/v1/catalog/papers?topic=' + topic['id'])
        self.assertEqual([item['id'] for item in response.json()['items']], [second['id'], first['id']])
        self.sign_in(self.admin)
        self.assertEqual(self.client.put('/api/v1/admin/experience/topics/' + topic['id'], json={**body, 'revision': 99}).status_code, 409)

    def test_groups_are_private_and_deleting_group_preserves_favorites(self):
        paper = self.publish()
        self.sign_in(self.viewer)
        self.client.put('/api/v1/catalog/papers/' + paper['id'] + '/favorite', json={'favorite': True})
        group = self.client.post('/api/v1/mini/favorite-groups', json={'name': '复习收藏'}).json()
        path = '/api/v1/mini/favorite-groups/papers/' + paper['id']
        self.assertEqual(self.client.put(path, json={'group_id': group['id']}).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/catalog/papers?favorite_group=' + group['id']).json()['total'], 1)
        self.sign_in(self.other)
        self.client.put('/api/v1/catalog/papers/' + paper['id'] + '/favorite', json={'favorite': True})
        self.assertEqual(self.client.put(path, json={'group_id': group['id']}).status_code, 404)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.delete('/api/v1/mini/favorite-groups/' + group['id'] + '?revision=1').status_code, 204)
        self.assertEqual(self.client.get('/api/v1/catalog/papers?favorite=true').json()['total'], 1)

    def test_history_is_owned_and_clear_does_not_remove_favorites(self):
        paper = self.publish()
        self.sign_in(self.viewer)
        self.client.put('/api/v1/catalog/papers/' + paper['id'] + '/favorite', json={'favorite': True}).raise_for_status()
        self.assertEqual(self.client.post('/api/v1/mini/history/' + paper['id']).status_code, 204)
        self.assertEqual(self.client.get('/api/v1/catalog/papers?recent=true').json()['total'], 1)
        self.sign_in(self.other)
        self.assertEqual(self.client.get('/api/v1/catalog/papers?recent=true').json()['total'], 0)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.delete('/api/v1/mini/history').status_code, 204)
        self.assertEqual(self.client.get('/api/v1/catalog/papers?recent=true').json()['total'], 0)
        self.assertEqual(self.client.get('/api/v1/catalog/papers?favorite=true').json()['total'], 1)

    def test_revision_preserves_subscriptions_and_blocks_old_asset_urls(self):
        original = self.source()
        paper = self.publish(self.draft(original))
        source = self.source()
        old_asset = paper['assets'][0]['url'].replace('/admin/catalog/', '/catalog/')
        self.sign_in(self.viewer)
        self.client.put('/api/v1/catalog/papers/' + paper['id'] + '/favorite', json={'favorite': True})
        self.client.post('/api/v1/catalog/papers/' + paper['id'] + '/download')
        self.sign_in(self.admin)
        body = {'revision': paper['revision'], 'paper_id': source['id'], 'note': '修正第 3 题答案', 'confirm_publication': True}
        path = '/api/v1/admin/catalog/papers/' + paper['id'] + '/revision'
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['release_number'], 2)
        self.assertEqual(self.client.post(path, json=body).status_code, 409)
        self.assertEqual(self.client.post('/api/v1/admin/catalog/papers', json={'paper_id': original['id']}).status_code, 409)
        self.assertEqual(self.client.delete('/api/v1/library/papers/' + original['id']).status_code, 409)
        self.sign_in(self.viewer)
        detail = self.client.get('/api/v1/catalog/papers/' + paper['id']).json()
        self.assertTrue(detail['favorite'])
        self.assertEqual(detail['update_note'], body['note'])
        self.assertEqual(self.client.get('/api/v1/catalog/papers?downloaded=true').json()['total'], 1)
        self.assertEqual(self.client.get(old_asset).status_code, 404)

    def test_usage_deduplicates_and_does_not_count_unrequested_downloads(self):
        paper = self.publish()
        self.sign_in(self.viewer)
        event = {'event_id': 'unique-active-event', 'kind': 'active'}
        self.assertEqual(self.client.post('/api/v1/mini/events', json=event).status_code, 204)
        self.assertEqual(self.client.post('/api/v1/mini/events', json=event).status_code, 204)
        event = {'event_id': 'unique-download-event', 'kind': 'download_failed', 'catalog_id': paper['id']}
        self.assertEqual(self.client.post('/api/v1/mini/events', json=event).status_code, 422)
        self.client.post('/api/v1/catalog/papers/' + paper['id'] + '/download')
        self.assertEqual(self.client.post('/api/v1/mini/events', json=event).status_code, 204)
        self.assertEqual(self.client.post('/api/v1/mini/events', json=event).status_code, 204)
        self.client.get('/api/v1/catalog/papers?q=完全不存在的内容')
        self.sign_in(self.admin)
        data = self.client.get('/api/v1/admin/experience/analytics').json()
        self.assertEqual(data['daily_active'], 1)
        self.assertEqual(data['download_failures'][0]['total'], 1)
        self.assertEqual(data['search_misses'][0]['query'], '完全不存在的内容')

    def test_usage_analytics_empty_window_has_thirty_zero_days(self):
        data = self.client.get('/api/v1/admin/experience/analytics').json()
        self.assertEqual((data['daily_active'], data['weekly_active'], data['monthly_active']), (0, 0, 0))
        self.assertEqual(len(data['timeline']), 30)
        self.assertTrue(all(point['active_users'] == point['download_ok'] == point['download_failed'] == point['search_miss'] == 0
                            for point in data['timeline']))
        self.assertEqual(data['search_misses'], [])
        self.assertEqual(data['download_failures'], [])

    def test_usage_analytics_respects_shanghai_boundaries_and_unique_users(self):
        today = datetime(2026, 9, 18, tzinfo=timezone(timedelta(hours=8)))
        midnight = int(today.timestamp())
        start, week = midnight - 29 * 86400, midnight - 6 * 86400
        with database.db() as conn:
            conn.executemany("INSERT INTO mini_users(id, username, created_at, updated_at) VALUES (?, ?, 0, 0)",
                             [(key, key) for key in ('old-only', 'month-only', 'week-only', 'future-only')])
            events = [
                ('old-only', 'search_miss', start - 1, 'outside-window'),
                ('month-only', 'active', start, ''),
                ('month-only', 'download_ok', week - 1, ''),
                ('week-only', 'search_miss', week, 'week-boundary'),
                (self.viewer.id, 'active', midnight - 1, ''),
                (self.viewer.id, 'download_ok', midnight, ''),
                (self.viewer.id, 'download_ok', midnight + 1, ''),
                (self.other.id, 'download_failed', midnight + 2, ''),
                (self.other.id, 'search_miss', midnight + 3, 'today-query'),
                ('future-only', 'search_miss', midnight + 86400, 'future-query'),
                ('future-only', 'download_failed', midnight + 86400, ''),
            ]
            conn.executemany("INSERT INTO mini_usage_events(id, user_id, kind, created_at, detail) VALUES (?, ?, ?, ?, ?)",
                             [(f'boundary-{index}', *event) for index, event in enumerate(events)])

        @contextmanager
        def utc_database():
            with database.db() as conn:
                conn.execute("SET LOCAL TIME ZONE 'UTC'")
                yield conn

        with patch.object(mini_experience.time, 'time', return_value=midnight + 12 * 3600), \
                patch.object(mini_experience, 'db', utc_database):
            response = self.client.get('/api/v1/admin/experience/analytics')
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual((data['daily_active'], data['weekly_active'], data['monthly_active']), (2, 3, 4))
        self.assertEqual(len(data['timeline']), 30)
        self.assertEqual(data['timeline'][0]['date'], '2026-08-20')
        self.assertEqual(data['timeline'][0]['active_users'], 1)
        self.assertEqual(data['timeline'][-2]['active_users'], 1)
        self.assertEqual(data['timeline'][-1], {'date': '2026-09-18', 'active_users': 2,
                                               'download_ok': 2, 'download_failed': 1, 'search_miss': 1})
        self.assertEqual(data['search_misses'], [{'query': 'today-query', 'total': 1}, {'query': 'week-boundary', 'total': 1}])
        self.assertEqual(data['download_failures'], [{'catalog_id': None, 'title': None, 'total': 1}])
        self.assertEqual(data['timezone'], 'Asia/Shanghai')

    def test_usage_analytics_limits_rankings_and_keeps_event_counts(self):
        now = int(time.time())
        with database.db() as conn:
            conn.executemany("INSERT INTO mini_usage_events(id, user_id, kind, detail, created_at) VALUES (?, ?, 'search_miss', ?, ?)",
                             [(f'miss-{query}-{event}', self.viewer.id, f'query-{query:02}', now)
                              for query in range(25) for event in range(query + 1)])
        data = self.client.get('/api/v1/admin/experience/analytics').json()
        self.assertEqual((data['daily_active'], data['weekly_active'], data['monthly_active']), (1, 1, 1))
        self.assertEqual(data['timeline'][-1]['search_miss'], 325)
        self.assertEqual(len(data['search_misses']), 20)
        self.assertEqual(data['search_misses'][0], {'query': 'query-24', 'total': 25})
        self.assertEqual(data['search_misses'][-1], {'query': 'query-05', 'total': 6})
