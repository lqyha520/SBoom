"""热门计数覆盖幂等、并发、回滚、级联删除与已有数据迁移。"""

import unittest
from concurrent.futures import ThreadPoolExecutor

import test_backend_catalog as fixtures

from app import db as database
from app.catalog_popularity_schema import migrate
from app.services import public_catalog


class CatalogPopularityContracts(unittest.TestCase):
    setUp = fixtures.PublicCatalogContracts.setUp
    sign_in = fixtures.PublicCatalogContracts.sign_in
    source = fixtures.PublicCatalogContracts.source
    draft = fixtures.PublicCatalogContracts.draft
    update = fixtures.PublicCatalogContracts.update
    publish = fixtures.PublicCatalogContracts.publish

    def counts(self, identifier):
        with database.db() as conn:
            row = conn.execute("SELECT favorite_count, download_users FROM catalog_popularity WHERE catalog_id = ?", (identifier,)).fetchone()
        return tuple(row.values()) if row else (0, 0)

    def test_counts_remain_exact_for_repeated_actions_and_account_deletion(self):
        paper = self.publish()
        for _ in range(2):
            public_catalog.favorite_paper(self.viewer.id, paper["id"], True)
            public_catalog.request_download(self.viewer.id, paper["id"])
        self.assertEqual(self.counts(paper["id"]), (1, 1))
        public_catalog.favorite_paper(self.viewer.id, paper["id"], False)
        self.assertEqual(self.counts(paper["id"]), (0, 1))
        with database.db() as conn:
            conn.execute("DELETE FROM mini_users WHERE id = ?", (self.viewer.id,))
        self.assertEqual(self.counts(paper["id"]), (0, 0))
        public_catalog.delete_paper(paper["id"], paper["revision"])
        with database.db() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM catalog_popularity WHERE catalog_id = ?", (paper["id"],)).fetchone())

    def test_counts_rollback_with_the_underlying_records(self):
        paper = self.publish()
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with database.db() as conn:
                conn.execute("INSERT INTO mini_catalog_favorites(user_id, catalog_id, created_at) VALUES (?, ?, 1)", (self.viewer.id, paper["id"]))
                raise RuntimeError("rollback")
        self.assertEqual(self.counts(paper["id"]), (0, 0))

    def test_concurrent_and_batch_changes_have_no_lost_updates(self):
        papers = [self.publish(), self.publish()]
        def favorite(user_id):
            for paper in papers:
                public_catalog.favorite_paper(user_id, paper["id"], True)
        with ThreadPoolExecutor(max_workers=2) as workers:
            list(workers.map(favorite, [self.viewer.id, self.other.id]))
        self.assertEqual([self.counts(paper["id"]) for paper in papers], [(2, 0), (2, 0)])
        def remove(user_id):
            with database.db() as conn:
                conn.execute("DELETE FROM mini_catalog_favorites WHERE user_id = ?", (user_id,))
        with ThreadPoolExecutor(max_workers=2) as workers:
            list(workers.map(remove, [self.viewer.id, self.other.id]))
        self.assertEqual([self.counts(paper["id"]) for paper in papers], [(0, 0), (0, 0)])

    def test_popular_offset_and_cursor_queries_use_the_same_scores(self):
        papers = [self.publish() for _ in range(3)]
        public_catalog.favorite_paper(self.viewer.id, papers[1]["id"], True)
        public_catalog.request_download(self.viewer.id, papers[2]["id"])
        public_catalog.favorite_paper(self.viewer.id, papers[2]["id"], True)
        expected = [papers[index]["id"] for index in (2, 1, 0)]
        result = public_catalog.list_papers(None, sort="popular")
        self.assertEqual([paper["id"] for paper in result["items"]], expected)
        first = public_catalog.list_papers(None, sort="popular", pagination="cursor", limit=1)
        second = public_catalog.list_papers(None, sort="popular", pagination="cursor", limit=2, cursor=first["next_cursor"])
        self.assertEqual([paper["id"] for paper in first["items"] + second["items"]], expected)
        admin = public_catalog.list_papers(self.admin.id, admin=True, sort="popular")
        self.assertEqual([(paper["favorite_count"], paper["download_users"]) for paper in admin["items"]], [(1, 1), (1, 0), (0, 0)])

    def test_batch_inserts_and_record_moves_update_both_catalogs(self):
        first, second = self.publish(), self.publish()
        with database.db() as conn:
            conn.execute("INSERT INTO mini_catalog_favorites(user_id, catalog_id, created_at) VALUES (?, ?, 1), (?, ?, 1)",
                         (self.viewer.id, first["id"], self.other.id, second["id"]))
            conn.execute("INSERT INTO mini_catalog_downloads(user_id, catalog_id, requested_at) VALUES (?, ?, 1), (?, ?, 1)",
                         (self.viewer.id, first["id"], self.other.id, second["id"]))
        self.assertEqual([self.counts(p["id"]) for p in (first, second)], [(1, 1), (1, 1)])
        with database.db() as conn:
            for table in ("mini_catalog_favorites", "mini_catalog_downloads"):
                conn.execute(f"UPDATE {table} SET catalog_id = ? WHERE user_id = ?", (second["id"], self.viewer.id))
        self.assertEqual([self.counts(p["id"]) for p in (first, second)], [(0, 0), (2, 2)])
        with database.db() as conn:
            conn.execute("DELETE FROM catalog_papers WHERE id = ?", (second["id"],))
        self.assertEqual(self.counts(second["id"]), (0, 0))

    def test_migration_backfills_existing_rows_and_is_idempotent(self):
        paper = self.publish()
        public_catalog.favorite_paper(self.viewer.id, paper["id"], True)
        public_catalog.request_download(self.viewer.id, paper["id"])
        with database.db(ddl=True) as conn:
            conn.execute("DROP TABLE catalog_popularity")
            migrate(conn)
            migrate(conn)
        self.assertEqual(self.counts(paper["id"]), (1, 1))
        public_catalog.favorite_paper(self.other.id, paper["id"], True)
        self.assertEqual(self.counts(paper["id"]), (2, 1))
