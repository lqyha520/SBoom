"""Database startup must not race when multiple PostgreSQL workers boot."""

import unittest
from contextlib import ExitStack
from unittest.mock import call, patch

import pg_support

pg_support.install_module_database({"SECRET_KEY": "startup-tests-disposable-secret"})

from app import db as database  # noqa: E402


class DatabaseStartupContracts(unittest.TestCase):
    def test_postgres_schema_initialization_holds_the_shared_lock(self):
        with ExitStack() as stack:
            pg_support.case_database(stack, fresh=True)
            with patch.object(database, "db", wraps=database.db) as connection:
                database.init_db()
            self.assertIn(call(serialized=tuple(database._LOCK_IDS), ddl=True), connection.call_args_list)

    def test_missing_database_url_fails_closed(self):
        from app import config

        with patch.object(config.get_settings(), "database_url", ""):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                database._database_url()


class FreshSchemaContracts(unittest.TestCase):
    """回归：init_db() 的所有建表共用一个事务，事务里任何一条语句失败都会整体回滚。

    曾经的线上事故：app/db_indexes.py 引用了并不存在的 commerce_orders /
    membership_ledger 表（真实表名 mini_orders / mini_membership_grants）以及
    catalog_papers.grade/subject（这两列其实在 paper_archives 上）。异常被
    `try/except: pass` 吞掉，但事务已经进入 aborted —— 最终 commit 退化成 ROLLBACK，
    全新库里只剩 users 等 7 张表，日志却打印"PostgreSQL 数据库就绪"。
    已有数据库（表早就建好）完全看不出问题，所以只有空库首次部署才会炸。
    """

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        # 每次 case 一个全新的空 schema：这才是"首次部署"的真实形态
        pg_support.case_database(self.stack, fresh=True)

    def _tables(self) -> set:
        with database.db() as conn:
            rows = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema()"
            ).fetchall()
        return {row[0] for row in rows}

    def _indexes(self) -> set:
        with database.db() as conn:
            rows = conn.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
            ).fetchall()
        return {row[0] for row in rows}

    def test_fresh_schema_gets_every_core_table(self):
        database.init_db()
        present = self._tables()
        missing = [name for name in database._CORE_TABLES if name not in present]
        self.assertEqual(missing, [], f"init_db() 后仍缺少核心表：{missing}")
        # 跨模块的建表总量有个下限，防止"部分 schema 函数被静默跳过"
        self.assertGreaterEqual(len(present), 50)

    def test_init_db_is_idempotent(self):
        database.init_db()
        before = self._tables()
        database.init_db()
        self.assertTrue(before.issubset(self._tables()))

    def test_declared_optimization_indexes_all_exist(self):
        """索引写错表名/列名时，事务会被拖回滚 —— 这条测试能第一时间拦住。"""
        from app.db_indexes import _INDEXES

        database.init_db()
        declared = {name for name, _ in _INDEXES}
        self.assertEqual(declared - self._indexes(), set())
