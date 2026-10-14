"""组合搜索应在分页前匹配可见教学标签，并保留资料权限边界。"""

from test_backend_growth import GrowthBase

from app.services import public_catalog


class CatalogSearchContracts(GrowthBase):
    def assign(self, paper, tags):
        response = self.client.put('/api/v1/admin/catalog/papers/' + paper['id'] + '/labels', json={
            'revision': paper['revision'], 'tag_ids': [tag['id'] for tag in tags],
        })
        self.assertEqual(response.status_code, 200, response.text)

    def test_words_across_title_category_archive_and_tags_before_pagination(self):
        tags = [self.tag('knowledge', '进位运算'), self.tag('textbook', '人教版')]
        papers = [self.publish() for _ in range(3)]
        for paper in papers[:2]:
            self.assign(paper, tags)
        query = '公共\u3000三年级 数学 加减法 人教版 进位运算 公共'
        first = public_catalog.list_papers(None, q=query, limit=1)
        second = public_catalog.list_papers(None, q=query, limit=1, offset=1)
        self.assertEqual(first['total'], 2)
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])
        self.assertEqual({first['items'][0]['id'], second['items'][0]['id']}, {p['id'] for p in papers[:2]})
        cursor = public_catalog.list_papers(None, q=query, limit=1, pagination='cursor')
        tail = public_catalog.list_papers(None, q=query, limit=1, pagination='cursor', cursor=cursor['next_cursor'])
        self.assertNotEqual(cursor['items'][0]['id'], tail['items'][0]['id'])
        self.assertFalse(tail['has_more'])
        self.assertEqual(public_catalog.list_papers(None, q='进位运算 不存在的主题')['total'], 0)
        self.assertEqual(public_catalog.list_papers(None, q='单元练习')['total'], 3)

    def test_hidden_tags_unpublished_papers_and_vip_assets_remain_protected(self):
        visible, hidden = self.tag('knowledge', '可见知识'), self.tag('knowledge', '内部标记')
        free, locked, draft = self.publish(), self.publish(), self.draft()
        locked = self.update(locked, view_access='vip', download_access='vip', confirm_publication=True).json()
        for paper in (free, locked, draft):
            self.assign(paper, [visible, hidden])
        self.client.put('/api/v1/admin/catalog/tags/' + hidden['id'], json={
            **{key: hidden[key] for key in ('kind', 'name', 'revision')}, 'is_visible': False,
        }).raise_for_status()
        self.client.cookies.clear()
        self.client.headers.pop('Authorization', None)
        result = self.client.get('/api/v1/catalog/papers', params={'q': '可见知识'}).json()
        self.assertEqual(result['total'], 2)
        self.assertNotIn(draft['id'], [p['id'] for p in result['items']])
        protected = next(p for p in result['items'] if p['id'] == locked['id'])
        self.assertFalse(protected['can_view'])
        self.assertIsNone(protected['thumbnail_url'])
        self.assertEqual(self.client.get('/api/v1/catalog/papers', params={'q': '内部标记'}).json()['total'], 0)
        self.assertEqual(public_catalog.list_papers(None, q='可见知识', only_free=True)['total'], 1)
        self.assertEqual(self.client.get(f"/api/v1/catalog/papers/{draft['id']}").status_code, 404)

    def test_literal_wildcards_case_and_whitespace(self):
        tagged, untagged = self.publish(), self.publish()
        self.assign(tagged, [self.tag('knowledge', r'Rate_50%\PDF')])
        for query in ('rate_50%', 'RATE_50%\\PDF', '%', '_', '\\'):
            with self.subTest(query=query):
                result = public_catalog.list_papers(None, q=query)
                self.assertEqual([p['id'] for p in result['items']], [tagged['id']])
        self.assertEqual(public_catalog.list_papers(None, q='  \t\u3000')['total'], 2)
        self.assertNotEqual(tagged['id'], untagged['id'])
