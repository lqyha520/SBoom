"""Dictionary contracts: explicit grade-subject links, knowledge points and scope/available."""


import test_backend_catalog as fixtures  # Initializes isolated environment before app imports.

from app.routers import site


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

    def test_startup_seeds_links_and_knowledge_points_from_default_scope(self):
        links = self.client.get('/api/v1/admin/site/dictionary/links').json()['links']
        self.assertEqual(len(links), 18)  # 6 grades x 3 subjects
        points = self.client.get('/api/v1/admin/site/dictionary?kind=knowledge_point').json()['items']
        self.assertGreater(len(points), 100)
        for point in points:
            grade_id, _, subject_id = point['parent'].partition('|')
            self.assertTrue(grade_id and subject_id)
        home = self.client.get('/api/v1/site/home').json()['dictionaries']
        self.assertEqual(len(home['grades']), 6)
        self.assertEqual(home['subjects'], ['语文', '数学', '英语'])
        self.assertEqual(home['subjects_by_grade']['小学一年级'], ['语文', '数学', '英语'])

    def test_available_scopes_follow_explicit_links(self):
        available = self.client.get('/api/v1/scope/available').json()['available']
        self.assertEqual(len(available), 6)
        self.assertEqual(available['小学六年级'], ['语文', '数学', '英语'])
        grade = self.grade('小学六年级')
        chinese, english = self.subject('语文'), self.subject('英语')
        self.client.put(f"/api/v1/admin/site/dictionary/links/{grade['id']}",
                        json={'subject_ids': [chinese['id'], english['id']]}).raise_for_status()
        available = self.client.get('/api/v1/scope/available').json()['available']
        self.assertEqual(available['小学六年级'], ['语文', '英语'])
        # 其他年级不受影响
        self.assertEqual(available['小学五年级'], ['语文', '数学', '英语'])
        # 未知科目 id 被拒绝
        response = self.client.put(f"/api/v1/admin/site/dictionary/links/{grade['id']}",
                                   json={'subject_ids': ['nope']})
        self.assertEqual(response.status_code, 422)

    def test_knowledge_point_crud_overrides_generation_scope(self):
        grade, math = self.grade('小学二年级'), self.subject('数学')
        parent = f"{grade['id']}|{math['id']}"
        created = self.client.post('/api/v1/admin/site/dictionary', json={
            'kind': 'knowledge_point', 'parent': parent, 'value': '测试知识点甲'})
        self.assertEqual(created.status_code, 201, created.text)
        point = created.json()
        # 同组合重复值被拒；不同组合的同名值允许
        self.assertEqual(self.client.post('/api/v1/admin/site/dictionary', json={
            'kind': 'knowledge_point', 'parent': parent, 'value': '测试知识点甲'}).status_code, 409)
        other_grade = self.grade('小学三年级')
        self.assertEqual(self.client.post('/api/v1/admin/site/dictionary', json={
            'kind': 'knowledge_point', 'parent': f"{other_grade['id']}|{math['id']}",
            'value': '测试知识点甲'}).status_code, 201)
        # parent 过滤
        listed = self.client.get('/api/v1/admin/site/dictionary',
                                 params={'kind': 'knowledge_point', 'parent': parent}).json()['items']
        self.assertIn('测试知识点甲', [item['value'] for item in listed])
        # 知识点进入出题知识范围 allowed
        scope = self.client.get('/api/v1/scope', params={'grade': '小学二年级', 'subject': '数学'}).json()
        self.assertIn('测试知识点甲', scope['allowed'])
        # 隐藏后不再进入
        self.client.put(f"/api/v1/admin/site/dictionary/{point['id']}", json={
            'revision': point['revision'], 'value': '测试知识点甲', 'label': '',
            'sort_order': point['sort_order'], 'is_visible': False}).raise_for_status()
        scope = self.client.get('/api/v1/scope', params={'grade': '小学二年级', 'subject': '数学'}).json()
        self.assertNotIn('测试知识点甲', scope['allowed'])

    def test_knowledge_point_requires_existing_scope_pair(self):
        response = self.client.post('/api/v1/admin/site/dictionary', json={
            'kind': 'knowledge_point', 'parent': 'missing|pair', 'value': '孤儿知识点'})
        self.assertEqual(response.status_code, 422)
        response = self.client.post('/api/v1/admin/site/dictionary', json={
            'kind': 'grade', 'value': '小学六年级', 'parent': 'grade-x|subject-y'})
        self.assertEqual(response.status_code, 422)

    def test_deleting_grade_or_subject_cascades_links_and_points(self):
        grade, math = self.grade('小学二年级'), self.subject('数学')
        parent = f"{grade['id']}|{math['id']}"
        self.client.post('/api/v1/admin/site/dictionary', json={
            'kind': 'knowledge_point', 'parent': parent, 'value': '待级联知识点甲'}).raise_for_status()
        self.client.delete(f"/api/v1/admin/site/dictionary/{math['id']}",
                           params={'revision': math['revision']}).raise_for_status()
        self.assertEqual([link for link in
                          self.client.get('/api/v1/admin/site/dictionary/links').json()['links']
                          if link['child_id'] == math['id'] or link['parent_id'] == math['id']], [])
        remaining = self.client.get('/api/v1/admin/site/dictionary?kind=knowledge_point').json()['items']
        self.assertNotIn(parent, [item['parent'] for item in remaining])
        # 被删的科目条目本身也消失（默认值补齐只发生在下次 init_db）
        subject_values = [item['value'] for item in
                          self.client.get('/api/v1/admin/site/dictionary?kind=subject').json()['items']]
        self.assertNotIn('数学', subject_values)

    def test_update_and_reorder_within_pair_keep_parent(self):
        grade, math = self.grade('小学四年级'), self.subject('数学')
        parent = f"{grade['id']}|{math['id']}"
        _first = self.client.post('/api/v1/admin/site/dictionary', json={
            'kind': 'knowledge_point', 'parent': parent, 'value': '排序知识点甲'}).json()
        second = self.client.post('/api/v1/admin/site/dictionary', json={
            'kind': 'knowledge_point', 'parent': parent, 'value': '排序知识点乙', 'sort_order': 20}).json()
        # 把乙移到最前
        self.client.put(f"/api/v1/admin/site/dictionary/{second['id']}", json={
            'revision': second['revision'], 'value': second['value'], 'label': '',
            'sort_order': 5, 'is_visible': True}).raise_for_status()
        listed = self.client.get('/api/v1/admin/site/dictionary',
                                 params={'kind': 'knowledge_point', 'parent': parent}).json()['items']
        ordered = [item['value'] for item in sorted(listed, key=lambda item: item['sort_order'])]
        self.assertLess(ordered.index('排序知识点乙'), ordered.index('排序知识点甲'))
