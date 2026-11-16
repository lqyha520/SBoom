"""从选题到复盘的关联、并发、版本和账号隔离契约。"""
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import test_backend_catalog as fixtures

from app.db import db
from app.models.xhs_workflow import Draft, Idea, Material, Publication
from app.routers import xhs_workflow
from app.services import user_store
from app.services.xhs_publication import CHECKS

BASE = '/api/v1/admin/xhs-workflow'


class XhsWorkflowContracts(fixtures.PublicCatalogContracts):
    def setUp(self):
        super().setUp()
        self.client.app.include_router(xhs_workflow.router)

    def create(self, kind, data, parent=None, identifier=None):
        response = self.client.post(f'{BASE}/records/{kind}', json={'id': identifier or str(uuid4()), 'parent_id': parent, 'data': data})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def edit(self, record, **changes):
        data = {k: v for k, v in record['data'].items() if k not in ('draft_snapshot', 'draft_revision')}
        return self.client.put(f"{BASE}/records/{record['kind']}/{record['id']}", json={'revision': record['revision'], 'data': {**data, **changes}})

    def chain(self):
        idea = self.create('ideas', Idea(title='找规律分层练习', keyword='找规律', audience='一年级家长').model_dump(mode='json'))
        material = self.create('materials', Material(title='找规律练习', keyword='找规律', questions=[{'stem': '1, 2, 3, __', 'answer': '4', 'analysis': '每次增加1'}]).model_dump(mode='json'), idea['id'])
        draft = self.create('drafts', Draft(title='方案A', headline='一年级找规律练习', body='三步练习方法', cover_title='找规律').model_dump(mode='json'), material['id'])
        publication = self.create('publications', Publication(title='首篇发布', account='测试账号', status='published', url='https://www.xiaohongshu.com/explore/65abcdef0123456789abcdef', published_at=datetime.now(UTC)-timedelta(days=8), **dict.fromkeys(CHECKS, True)).model_dump(mode='json'), draft['id'])
        return idea, material, draft, publication

    def test_workflow_links_revisions_and_idempotent_creation(self):
        identifier = str(uuid4())
        data = Idea(title='原创选题').model_dump(mode='json')
        first = self.create('ideas', data, identifier=identifier)
        second = self.create('ideas', data, identifier=identifier)
        self.assertEqual(first['id'], second['id'])
        changed = self.edit(first, angle='新增切入点')
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.edit(first, angle='过期修改').status_code, 409)
        history = self.client.get(f'{BASE}/records/ideas/{identifier}/versions').json()['items']
        self.assertEqual([v['revision'] for v in history], [2, 1])
        self.assertEqual(history[-1]['data']['angle'], '')
        self.assertEqual(self.create('ideas', data, identifier=identifier)['revision'], 2)
        self.assertEqual(self.client.get(f'{BASE}/records/ideas?q=原创').json()['total'], 1)

    def test_workflow_parent_types_and_other_admin_are_isolated(self):
        idea, material, draft, publication = self.chain()
        self.assertEqual(self.client.get(f"{BASE}/records/ideas/{idea['id']}").json()['children'][0]['id'], material['id'])
        self.assertEqual(self.client.post(f'{BASE}/records/drafts', json={'id':str(uuid4()),'parent_id':idea['id'],'data':Draft(title='错误父级').model_dump()}).status_code, 404)
        self.sign_in(user_store.create_user('workflow-admin-two', 'test-password', role='admin', is_super_admin=True))
        for item in (idea, material, draft, publication):
            self.assertEqual(self.client.get(f"{BASE}/records/{item['kind']}/{item['id']}").status_code, 404)
            self.assertEqual(self.edit(item, title='越权').status_code, 404)
        self.assertEqual(self.client.get(f'{BASE}/records/ideas').json()['total'], 0)
        self.assertEqual(self.client.get(f"{BASE}/metrics/{publication['id']}").status_code, 404)
        self.assertEqual(self.client.get(f'{BASE}/analytics').json()['total'], 0)
        self.sign_in(self.author)
        self.assertEqual(self.client.get(f'{BASE}/records/ideas').status_code, 403)

    def test_unchanged_save_preserves_revision_timestamp_and_history(self):
        for record in self.chain():
            with self.subTest(kind=record['kind']):
                saved = self.edit(record)
                self.assertEqual(saved.status_code, 200, saved.text)
                self.assertEqual(saved.json()['revision'], record['revision'])
                self.assertEqual(saved.json()['updated_at'], record['updated_at'])
                history = self.client.get(f"{BASE}/records/{record['kind']}/{record['id']}/versions").json()
                self.assertEqual(history['total'], 1)
                changed = self.edit(record, title=record['title'] + ' · 修改')
                self.assertEqual(changed.status_code, 200, changed.text)
                self.assertEqual(changed.json()['revision'], record['revision'] + 1)
                self.assertEqual(self.edit(record).status_code, 409)

    def test_legacy_defaults_do_not_create_false_content_changes(self):
        _, material, draft, _ = self.chain()
        material = self.edit(material, status='ready', accuracy_checked=True, scope_checked=True, layout_checked=True).json()
        for record, missing in [(material, ('game_type', 'difficulty', 'question_count')), (draft, ('source_material_revision',))]:
            with self.subTest(kind=record['kind']):
                legacy = {key: value for key, value in record['data'].items() if key not in missing}
                with db() as conn:
                    conn.execute('UPDATE xhs_workflow_records SET data_json=? WHERE id=?', (json.dumps(legacy), record['id']))
                current = self.client.get(f"{BASE}/records/{record['kind']}/{record['id']}").json()
                saved = self.edit(current)
                self.assertEqual(saved.status_code, 200, saved.text)
                self.assertEqual(saved.json()['revision'], record['revision'])
                self.assertEqual(saved.json()['status'], record['status'])

    def test_workflow_material_edit_invalidates_review_and_archiving_keeps_links(self):
        idea, material, _, _ = self.chain()
        self.assertEqual(self.edit(material, status='ready').status_code, 422)
        checked = self.edit(material, status='ready', accuracy_checked=True, scope_checked=True, layout_checked=True).json()
        self.assertEqual(checked['status'], 'ready')
        changed = self.edit(checked, questions=[{'stem':'2, 4, __','answer':'6','analysis':'每次增加2'}]).json()
        self.assertEqual(changed['status'], 'draft')
        self.assertFalse(changed['data']['accuracy_checked'])
        self.assertEqual(self.edit(idea, status='archived').status_code, 200)
        self.assertEqual(self.client.get(f'{BASE}/records/ideas').json()['total'], 0)
        self.assertEqual(self.client.get(f'{BASE}/records/ideas?status=archived').json()['total'], 1)
        self.assertEqual(self.client.get(f"{BASE}/records/materials/{material['id']}").status_code, 200)

    def test_material_generation_settings_invalidate_all_review_checks(self):
        _, material, _, _ = self.chain()
        for field, value in [('game_type', 'quiz'), ('difficulty', 'hard'), ('question_count', 20)]:
            with self.subTest(field=field):
                checked = self.edit(material, status='ready', accuracy_checked=True, scope_checked=True, layout_checked=True).json()
                changed = self.edit(checked, **{field: value})
                self.assertEqual(changed.status_code, 200, changed.text)
                material = changed.json()
                self.assertEqual(material['status'], 'draft')
                self.assertFalse(any(material['data'][check] for check in ('accuracy_checked', 'scope_checked', 'layout_checked')))

    def test_missing_parent_names_the_correct_creation_stage(self):
        for kind, model, message in [('materials', Material, '请先选择关联选题'), ('drafts', Draft, '请先选择关联资料')]:
            with self.subTest(kind=kind):
                result = self.client.post(f'{BASE}/records/{kind}', json={'id': str(uuid4()), 'data': model(title='新内容').model_dump(mode='json')})
                self.assertEqual(result.status_code, 422)
                self.assertEqual(result.json()['detail']['error'], message)

    def test_workflow_publication_keeps_original_draft_snapshot(self):
        _, _, draft, publication = self.chain()
        self.edit(draft, body='全新正文').raise_for_status()
        current = self.client.get(f"{BASE}/records/publications/{publication['id']}").json()
        self.assertEqual(current['data']['draft_snapshot']['body'], '三步练习方法')
        self.assertEqual(current['data']['draft_revision'], 1)
        edited = self.edit(current, notes='发布备注')
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()['data']['draft_snapshot']['body'], '三步练习方法')
        self.assertEqual(self.edit(current, url='javascript:alert(1)').status_code, 422)
        self.assertEqual(self.edit(edited.json(), published_at=None).status_code, 422)

    def test_workflow_metrics_keep_checkpoints_distinct_and_missing_is_not_zero(self):
        *_, publication = self.chain()
        initial = self.client.get(f'{BASE}/analytics?checkpoint=7').json()['items'][0]
        self.assertIsNone(initial['metric'])
        self.assertTrue(initial['needs_recording'])
        metric = {'checkpoint':1,'revision':0,'measured_at':datetime.now(UTC).isoformat(),'views':1000,'likes':20,'saves':50,'comments':5}
        path = f"{BASE}/metrics/{publication['id']}"
        self.assertEqual(self.client.put(path,json=metric).status_code, 200)
        self.assertEqual(self.client.put(path,json=metric).status_code, 409)
        day_one = self.client.get(f'{BASE}/analytics?checkpoint=1').json()['items'][0]
        self.assertEqual((day_one['save_rate'],day_one['interaction_rate']), (5.0,7.5))
        self.assertIsNone(day_one['metric']['downloads'])
        self.assertIsNone(self.client.get(f'{BASE}/analytics?checkpoint=7').json()['items'][0]['metric'])
        self.assertEqual(self.client.put(path,json={**metric,'checkpoint':3,'views':0,'saves':0}).status_code,200)
        self.assertIsNone(self.client.get(f'{BASE}/analytics?checkpoint=3').json()['items'][0]['save_rate'])
        self.assertEqual(self.client.put(path,json={**metric,'checkpoint':7,'views':-1}).status_code,422)
        self.assertEqual(self.client.put(path,json={**metric,'checkpoint':7,'measured_at':(datetime.now(UTC)-timedelta(days=10)).isoformat()}).status_code,422)
        self.assertEqual(self.client.get(f'{BASE}/analytics?checkpoint=2').status_code,422)

    def review_payload(self, record, **changes):
        return {'revision': record['revision'], 'conclusion': '读者喜欢分层说明', 'next_action': '再做进阶版',
                'metric': {'checkpoint': 7, 'revision': 0, 'measured_at': datetime.now(UTC).isoformat(),
                           'views': 100, 'likes': 5, 'saves': 10, 'comments': 2}, **changes}

    def test_review_saves_metrics_conclusion_and_version_together(self):
        *_, record = self.chain()
        payload = self.review_payload(record)
        result = self.client.put(f"{BASE}/reviews/{record['id']}", json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        saved = result.json()
        self.assertEqual(saved['record']['data']['conclusion'], payload['conclusion'])
        self.assertEqual(saved['record']['data']['draft_snapshot'], record['data']['draft_snapshot'])
        self.assertEqual(saved['record']['revision'], record['revision'] + 1)
        self.assertEqual(saved['items'][0]['views'], 100)
        self.assertEqual(saved['items'][0]['revision'], 1)
        self.assertEqual(self.client.get(f"{BASE}/records/publications/{record['id']}/versions").json()['total'], 2)

    def test_review_record_conflict_does_not_save_metrics(self):
        *_, record = self.chain()
        self.edit(record, notes='其他窗口刚修改').raise_for_status()
        result = self.client.put(f"{BASE}/reviews/{record['id']}", json=self.review_payload(record))
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(self.client.get(f"{BASE}/metrics/{record['id']}").json()['items'], [])
        current = self.client.get(f"{BASE}/records/publications/{record['id']}").json()
        self.assertEqual(current['data']['conclusion'], '')
        self.assertEqual(current['data']['notes'], '其他窗口刚修改')

    def test_review_metric_conflict_and_invalid_time_leave_conclusion_unchanged(self):
        *_, record = self.chain()
        payload = self.review_payload(record)
        self.client.put(f"{BASE}/metrics/{record['id']}", json=payload['metric']).raise_for_status()
        result = self.client.put(f"{BASE}/reviews/{record['id']}", json=payload)
        self.assertEqual(result.status_code, 409, result.text)
        bad = {**payload, 'metric': {**payload['metric'], 'revision': 1, 'measured_at': (datetime.now(UTC) - timedelta(days=20)).isoformat()}}
        self.assertEqual(self.client.put(f"{BASE}/reviews/{record['id']}", json=bad).status_code, 422)
        current = self.client.get(f"{BASE}/records/publications/{record['id']}").json()
        self.assertEqual(current['revision'], record['revision'])
        self.assertEqual(current['data']['conclusion'], '')
        self.assertEqual(self.client.get(f"{BASE}/metrics/{record['id']}").json()['items'][0]['revision'], 1)

    def test_review_late_database_failure_rolls_back_metrics_and_record(self):
        from app.services import xhs_workflow as service
        *_, record = self.chain()
        with patch.object(service, '_metrics', side_effect=RuntimeError('模拟提交前失败')):
            with self.assertRaises(RuntimeError):
                service.save_review(self.admin.id, record['id'], self.review_payload(record))
        self.assertEqual(self.client.get(f"{BASE}/metrics/{record['id']}").json()['items'], [])
        current = self.client.get(f"{BASE}/records/publications/{record['id']}").json()
        self.assertEqual(current['revision'], record['revision'])
        self.assertEqual(current['data']['conclusion'], '')

    def test_review_other_admin_cannot_write_either_part(self):
        *_, record = self.chain()
        self.sign_in(user_store.create_user('review-other', 'test-password', role='admin', is_super_admin=True))
        self.assertEqual(self.client.put(f"{BASE}/reviews/{record['id']}", json=self.review_payload(record)).status_code, 404)
        self.sign_in(self.admin)
        self.assertEqual(self.client.get(f"{BASE}/metrics/{record['id']}").json()['items'], [])

    def test_publication_lookup_backfill_preserves_history_and_normalizes_links(self):
        from app.services.xhs_publication import content_hash, url_key
        from app.xhs_workflow_schema import migrate
        *_, record = self.chain()
        with db() as conn:
            conn.execute('UPDATE xhs_workflow_records SET publication_url_key=NULL,publication_content_hash=NULL WHERE id=?', (record['id'],))
            migrate(conn)
            row = conn.execute('SELECT publication_url_key,publication_content_hash,revision FROM xhs_workflow_records WHERE id=?', (record['id'],)).fetchone()
        self.assertEqual(row['publication_url_key'], url_key(record['data']['url']))
        self.assertEqual(row['publication_content_hash'], content_hash(record['data']))
        self.assertEqual(row['revision'], record['revision'])
        duplicate = self.custom(status='published', url='https://xiaohongshu.com/discovery/item/65ABCDEF0123456789ABCDEF?share=1', published_at=datetime.now(UTC), **dict.fromkeys(CHECKS, True))
        self.assertEqual(self.client.post(BASE + '/records/publications', json={'id': str(uuid4()), 'data': duplicate}).status_code, 409)

    def test_duplicate_report_is_bounded_and_includes_old_archived_content(self):
        data = self.custom()
        for index in range(14):
            self.create('publications', {**data, 'title': f'旧发布 {index}', 'status': 'archived'})
        report = self.client.post(BASE + '/publication-check', json={'data': data}).json()
        self.assertEqual(len(report['duplicates']), 10)
        self.assertIn('duplicate', {item['code'] for item in report['findings']})

    def test_workflow_ai_copy_uses_owned_material_and_replays_same_request(self):
        _, material, _, _ = self.chain()
        payload = {'material_id':material['id'],'material_revision':material['revision'],'audience':'一年级家长','angle':'循序练习'}
        generated = {'headline':'找规律练习','title_options':['循序练习'],'body':'练习方法','cover_title':'找规律','cover_subtitle':'分层练习','hashtags':'#数学','cards':[{'heading':'练习方法','body':'按顺序完成'}]}
        mocked = AsyncMock(return_value=generated)
        with patch.object(xhs_workflow,'_call_llm_and_parse',mocked):
            headers = {'X-Request-ID':'workflow-copy-dedup'}
            first = self.client.post(BASE+'/generate-copy',json=payload,headers=headers)
            second = self.client.post(BASE+'/generate-copy',json=payload,headers=headers)
            self.assertEqual(first.status_code,200,first.text)
            self.assertEqual(first.json(),second.json())
            self.assertEqual(mocked.await_count,1)
            self.assertEqual(first.json()['draft']['headline'],'找规律练习')
            self.assertEqual(first.json()['material_revision'], material['revision'])
            self.assertEqual(first.json()['draft']['source_material_revision'], material['revision'])
            draft = self.create('drafts', first.json()['draft'], material['id'])
            self.assertEqual(draft['data']['source_material_revision'], material['revision'])
            changed = self.edit(material, instructions='新的资料使用方式').json()
            self.assertEqual(changed['revision'], material['revision'] + 1)
            self.assertEqual(self.client.get(f"{BASE}/records/drafts/{draft['id']}").json()['data']['source_material_revision'], material['revision'])
            self.assertIn('1, 2, 3, __',mocked.call_args.args[1])
            stale = self.client.post(BASE+'/generate-copy',json={**payload,'material_revision':999},headers={'X-Request-ID':'workflow-copy-stale'})
            self.assertEqual(stale.status_code,409)
            self.assertEqual(mocked.await_count,1)

    def test_workflow_list_pagination_and_search_are_stable(self):
        for n in range(23):
            self.create('ideas',Idea(title=f'计划 {n} 100%').model_dump())
        first = self.client.get(BASE+'/records/ideas?page=1').json()
        second = self.client.get(BASE+'/records/ideas?page=2').json()
        self.assertEqual((len(first['items']),len(second['items']),first['total']),(20,3,23))
        self.assertEqual(self.client.get(BASE+'/records/ideas?q=100_').json()['total'],0)

    def custom(self, **changes):
        return Publication(title='自定义计划', source='custom', account='我的账号', custom_content={'headline':'观察生活中的数学','body':'记录今天观察到的三个生活例子。'}, **changes).model_dump(mode='json')

    def test_publication_custom_requires_no_parent_and_supports_full_lifecycle(self):
        data = self.custom()
        record = self.create('publications', data)
        self.assertIsNone(record['parent_id'])
        self.assertNotIn('draft_snapshot', record['data'])
        self.assertEqual(self.edit(record,status='ready').status_code,422)
        ready = self.edit(record,status='ready',**dict.fromkeys(CHECKS,True))
        self.assertEqual(ready.status_code,200,ready.text)
        ready = ready.json()
        published = self.edit(ready,status='published',url='https://xhslink.com/a/unique-note',published_at=(datetime.now(UTC)-timedelta(days=8)).isoformat())
        self.assertEqual(published.status_code,200,published.text)
        record = published.json()
        self.assertEqual(self.client.get(BASE+'/analytics').json()['items'][0]['id'],record['id'])
        metric={'checkpoint':7,'revision':0,'measured_at':datetime.now(UTC).isoformat(),'views':100,'likes':3,'saves':5,'comments':2}
        self.assertEqual(self.client.put(f"{BASE}/metrics/{record['id']}",json=metric).status_code,200)
        self.assertEqual(self.edit(record,status='planned').status_code,409)
        archived=self.edit(record,status='archived').json()
        self.assertEqual(self.client.get(BASE+'/analytics').json()['total'],0)
        self.assertEqual(len(self.client.get(f"{BASE}/metrics/{record['id']}").json()['items']),1)
        self.assertEqual(self.edit(archived,status='published').status_code,200)

    def test_publication_preflight_returns_context_and_does_not_change_records(self):
        data=self.custom()
        data['custom_content']['body']='保证提分，关注后领取，扫码加微信。'
        before=self.client.get(BASE+'/records/publications').json()['total']
        report=self.client.post(BASE+'/publication-check',json={'data':data})
        self.assertEqual(report.status_code,200,report.text)
        report=report.json()
        self.assertTrue({'claims','contact','engagement'}.issubset({item['code'] for item in report['findings']}))
        self.assertIn('保证提分',str(report['findings']))
        self.assertTrue(report['blockers'])
        self.assertEqual(self.client.get(BASE+'/records/publications').json()['total'],before)
        data.update(status='ready',**dict.fromkeys(CHECKS,True))
        failed=self.client.post(BASE+'/records/publications',json={'id':str(uuid4()),'data':data})
        self.assertEqual(failed.status_code,422)
        data['custom_content']['body']='记录今天观察到的三个生活例子。'
        self.create('publications',data)

    def test_publication_changed_content_invalidates_review_and_duplicate_is_visible(self):
        record=self.create('publications',self.custom(status='ready',**dict.fromkeys(CHECKS,True)))
        modified=self.edit(record,custom_content={**record['data']['custom_content'],'body':'修改后的原创正文。'})
        self.assertEqual(modified.status_code,200,modified.text)
        modified=modified.json()
        self.assertEqual(modified['status'],'planned')
        self.assertFalse(any(modified['data'][key] for key in CHECKS))
        report=self.client.post(BASE+'/publication-check',json={'data':modified['data']}).json()
        self.assertIn('duplicate',{item['code'] for item in report['findings']})
        same=self.client.post(BASE+'/publication-check',json={'record_id':modified['id'],'data':modified['data']}).json()
        self.assertEqual(same['duplicates'],[])

    def test_publication_duplicate_link_rejects_tracking_and_domain_variants(self):
        *_, record=self.chain()
        data=self.custom(status='published',url='https://xiaohongshu.com/discovery/item/65abcdef0123456789abcdef?share=1',published_at=datetime.now(UTC),**dict.fromkeys(CHECKS,True))
        result=self.client.post(BASE+'/records/publications',json={'id':str(uuid4()),'data':data})
        self.assertEqual(result.status_code,409,result.text)
        self.assertEqual(self.edit(record,notes='正常编辑原记录').status_code,200)

    def test_publication_refresh_is_explicit_versioned_and_unavailable_after_publication(self):
        _,_,draft,published=self.chain()
        planned=self.create('publications',Publication(title='另一发布计划',account='另一账号').model_dump(mode='json'),draft['id'])
        self.edit(draft,body='新版正文').raise_for_status()
        unchanged=self.client.get(f"{BASE}/records/publications/{planned['id']}").json()
        self.assertEqual(unchanged['data']['draft_snapshot']['body'],'三步练习方法')
        path=f"{BASE}/publications/{planned['id']}/refresh-draft"
        self.assertEqual(self.client.post(path,json={'revision':999}).status_code,409)
        refreshed=self.client.post(path,json={'revision':planned['revision']})
        self.assertEqual(refreshed.status_code,200,refreshed.text)
        refreshed=refreshed.json()
        self.assertEqual(refreshed['data']['draft_snapshot']['body'],'新版正文')
        self.assertEqual(refreshed['data']['draft_revision'],2)
        self.assertFalse(refreshed['data']['rights_checked'])
        self.assertEqual(self.client.get(f"{BASE}/records/publications/{planned['id']}/versions").json()['total'],2)
        self.assertEqual(self.client.post(f"{BASE}/publications/{published['id']}/refresh-draft",json={'revision':published['revision']}).status_code,409)

    def test_publication_source_permissions(self):
        _,_,draft,published=self.chain()
        self.assertEqual(self.edit(published,source='custom').status_code,409)
        self.assertEqual(self.client.post(BASE+'/records/publications',json={'id':str(uuid4()),'parent_id':draft['id'],'data':self.custom()}).status_code,422)
        self.sign_in(user_store.create_user('publishing-other-admin','test-password',role='admin', is_super_admin=True))
        self.assertEqual(self.client.post(BASE+'/publication-check',json={'record_id':published['id'],'data':self.custom()}).status_code,404)
        self.assertEqual(self.client.post(f"{BASE}/publications/{published['id']}/refresh-draft",json={'revision':1}).status_code,404)
        self.assertEqual(self.client.post(BASE+'/publication-check',json={'parent_id':draft['id'],'data':Publication(title='越权').model_dump()}).status_code,404)
        self.assertEqual(self.client.post(BASE+'/publication-check',json={'data':self.custom()}).json()['duplicates'],[])

    def test_publication_legacy_snapshot_can_be_read_and_amended(self):
        import json

        *_, current=self.chain()
        old={key:value for key,value in current['data'].items() if key not in (*CHECKS,'source','custom_content','review_notes')}
        with db() as conn:
            conn.execute('UPDATE xhs_workflow_records SET data_json=? WHERE id=?',(json.dumps(old),current['id']))
        loaded=self.client.get(f"{BASE}/records/publications/{current['id']}").json()
        self.assertEqual(loaded['data']['source'],'linked')
        self.assertFalse(loaded['data']['rights_checked'])
        edited=self.edit(loaded,notes='历史记录补充说明')
        self.assertEqual(edited.status_code,200,edited.text)
        self.assertEqual(edited.json()['data']['draft_snapshot'],old['draft_snapshot'])

    def test_publication_validates_links_future_time_and_existing_metrics(self):
        record=self.create('publications',self.custom())
        for url in ('https://xiaohongshu.com/','https://xiaohongshu.com/search_result?keyword=test','https://xiaohongshu.com.evil.test/explore/abc','http://xhslink.com/a/abc','https://user@xhslink.com/a/abc','https://xhslink.com:999/a/abc','javascript:alert(1)'):
            self.assertEqual(self.edit(record,url=url).status_code,422,url)
        future=(datetime.now(UTC)+timedelta(days=1)).isoformat()
        self.assertEqual(self.edit(record,published_at=future).status_code,422)
        self.assertEqual(self.edit(record,scheduled_at=future).status_code,200)
        *_, published=self.chain()
        measured=(datetime.now(UTC)-timedelta(days=1)).isoformat()
        metric={'checkpoint':7,'revision':0,'measured_at':measured,'views':100,'likes':3,'saves':5,'comments':2}
        self.assertEqual(self.client.put(f"{BASE}/metrics/{published['id']}",json=metric).status_code,200)
        self.assertEqual(self.edit(published,published_at=datetime.now(UTC).isoformat()).status_code,409)
