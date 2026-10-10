"""字典关联与只读官方教材目录的回归；只使用隔离测试数据库。"""

import test_backend_catalog as fixtures

from app.db import db
from app.routers import site
from app.services.knowledge_scope import knowledge_scope_service


class DictionaryContracts(fixtures.PublicCatalogContracts):
    def setUp(self):
        super().setUp()
        self.client.app.include_router(site.router)
        self.client.app.include_router(site.admin_router)

    def grade(self, value):
        items = self.client.get('/api/v1/admin/site/dictionary?kind=grade').json()['items']
        return next(item for item in items if item['value'] == value)

    def subject(self, value):
        items = self.client.get('/api/v1/admin/site/dictionary?kind=subject').json()['items']
        return next(item for item in items if item['value'] == value)

    def legacy_point(self):
        grade, math = self.grade('小学一年级'), self.subject('数学')
        parent = f"{grade['id']}|{math['id']}"
        with db() as conn:
            conn.execute(
                "INSERT INTO site_dictionary(id, kind, parent, value, label, sort_order, is_visible, revision, created_at, updated_at) "
                "VALUES ('legacy-point', 'knowledge_point', ?, '旧数据库知识点', '', 1, 1, 1, 1, 1)", (parent,))
        return parent

    def test_startup_seeds_series_links_but_no_legacy_points(self):
        links = self.client.get('/api/v1/admin/site/dictionary/links').json()['links']
        self.assertEqual(len(links), 16)
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM site_dictionary WHERE kind = 'knowledge_point'").fetchone()[0], 0)
        home = self.client.get('/api/v1/site/home').json()['dictionaries']
        self.assertEqual(len(home['grades']), 6)
        self.assertCountEqual(home['subjects_by_grade']['小学一年级'], ['语文', '数学'])

    def test_available_scopes_intersect_links_with_verified_catalog(self):
        available = self.client.get('/api/v1/scope/available').json()['available']
        self.assertEqual(len(available), 6)
        self.assertNotIn('英语', available['小学一年级'])
        for grade_value, subjects in available.items():
            for subject_value in subjects:
                self.assertTrue(knowledge_scope_service.get_scope(grade_value, subject_value).books)
        grade = self.grade('小学一年级')
        math = self.subject('数学')
        self.client.put(f"/api/v1/admin/site/dictionary/links/{grade['id']}",
                        json={'subject_ids': [math['id']]}).raise_for_status()
        available = self.client.get('/api/v1/scope/available').json()['available']
        self.assertEqual(available['小学一年级'], ['数学'])
        response = self.client.put(f"/api/v1/admin/site/dictionary/links/{grade['id']}",
                                   json={'subject_ids': ['nope']})
        self.assertEqual(response.status_code, 422)

    def test_old_database_points_never_override_or_appear_as_current_catalog(self):
        self.legacy_point()
        scope = self.client.get('/api/v1/scope', params={'grade': '小学一年级', 'subject': '数学'}).json()
        self.assertNotIn('旧数据库知识点', scope['allowed'])
        self.assertIn('100以内的笔算加、减法', scope['semesters']['下册'])
        self.assertTrue(all(book['source_url'].startswith('https://book.pep.com.cn/') for book in scope['books']))
        self.assertEqual(self.client.get('/api/v1/admin/site/dictionary?kind=knowledge_point').json()['items'], [])
        self.assertFalse(any(item['kind'] == 'knowledge_point' for item in
                             self.client.get('/api/v1/admin/site/dictionary').json()['items']))

    def test_legacy_knowledge_point_writes_are_rejected(self):
        parent = self.legacy_point()
        response = self.client.post('/api/v1/admin/site/dictionary', json={
            'kind': 'knowledge_point', 'parent': parent, 'value': '任意新知识点'})
        self.assertEqual(response.status_code, 422)
        response = self.client.put('/api/v1/admin/site/dictionary/legacy-point', json={
            'revision': 1, 'value': '改名旧知识点', 'label': '', 'sort_order': 1, 'is_visible': True})
        self.assertEqual(response.status_code, 422)

    def test_deleting_subject_cascades_legacy_links_without_changing_books(self):
        parent = self.legacy_point()
        math = self.subject('数学')
        self.client.delete(f"/api/v1/admin/site/dictionary/{math['id']}",
                           params={'revision': math['revision']}).raise_for_status()
        with db() as conn:
            self.assertFalse(conn.execute("SELECT 1 FROM site_dictionary WHERE parent = ?", (parent,)).fetchone())
            self.assertFalse(conn.execute("SELECT 1 FROM site_dict_links WHERE child_id = ?", (math['id'],)).fetchone())
        self.assertTrue(knowledge_scope_service.get_scope('小学一年级', '数学').books)

    def test_unknown_or_unverified_scope_has_no_old_fallback(self):
        for grade, subject in [('未知年级', '数学'), ('小学一年级', '英语')]:
            value = self.client.get('/api/v1/scope', params={'grade': grade, 'subject': subject}).json()
            self.assertEqual(value['allowed'], [])
            self.assertEqual(value['books'], [])
