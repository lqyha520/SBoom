"""Explicit demo imports preserve account separation, file integrity and user edits.

源库（demo 包）本质是 SQLite 文件，importer 保留 sqlite3 只读读取；
测试在一次性 PG 库的独立 schema 里构造源数据，再导出为 SQLite 源文件。
"""

import os
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import ExitStack, closing
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qsl, urlencode, urlsplit

import pg_support  # 建一次性测试库，必须在 import app 之前
import psycopg
from psycopg import sql

pg_support.install_module_database()

from test_backend_library import bundle, snapshot

from app import db as database
from app.config import get_settings
from app.models.catalog import CatalogCreate, CatalogUpdate, TypeAccessUpdate
from app.models.library import ArchiveCreate
from app.models.mini import MembershipUpdate
from app.services import catalog_access, mini_auth, paper_library, public_catalog, user_store
from app.services.paper_storage import LocalStorage
from scripts.import_demo_catalog import import_catalog

# 导出为 SQLite 源文件所需的表：users 供 importer 校验身份，其余为导入清单
_EXPORT_TABLES = ("users", "mini_users", "mini_user_sessions", "paper_archives", "paper_assets",
                  "catalog_papers", "catalog_access", "catalog_question_types", "catalog_type_rules",
                  "mini_catalog_favorites", "mini_catalog_downloads", "mini_membership_events")

_PG_INT_TYPES = ("smallint", "integer", "bigint", "boolean")


def export_pg_schema_to_sqlite(dsn: str, sqlite_path: Path, tables) -> None:
    """把当前 search_path 指向的 PG schema 导出到 SQLite 文件（列名与顺序保持一致）。"""
    with closing(sqlite3.connect(sqlite_path)) as conn, psycopg.connect(dsn) as pg:
        for table in tables:
            columns = pg.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position",
                (table,)).fetchall()
            if not columns:
                continue
            ddl = ", ".join(f'"{name}" {"INTEGER" if data_type in _PG_INT_TYPES else "TEXT"}'
                            for name, data_type in columns)
            conn.execute(f'CREATE TABLE "{table}" ({ddl})')
            rows = pg.execute(f'SELECT * FROM "{table}"').fetchall()
            if rows:
                names = [name for name, _ in columns]
                placeholders = ", ".join("?" for _ in names)
                conn.executemany(f'INSERT INTO "{table}" ({", ".join(names)}) VALUES ({placeholders})', rows)
        conn.commit()


class DemoImportContracts(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="lc-demo-import-")))
        self.source_db = self.root / "source.db"
        self.source_files = self.root / "source-files"
        pg_support.case_database(self.stack)  # 目标库（导入的目的地）
        self.stack.enter_context(patch.object(get_settings(), "archive_local_dir", str(self.root / "target-files")))
        self.stack.enter_context(patch.object(get_settings(), "mini_registration_enabled", True))
        self._build_sqlite_source()
        database.init_db()
        user_store.create_user("existing-user", "unchanged-password")
        self.admin = user_store.create_user("existing-admin", "unchanged-password", role="admin")
        with database.db() as conn:
            conn.execute("INSERT INTO app_config(key, value) VALUES ('llm_model', 'existing-model')")

    def _build_sqlite_source(self):
        """在独立 schema 里构造 demo 源数据，导出为 SQLite 源文件后丢弃 schema。"""
        module_dsn = os.environ["DATABASE_URL"]
        base = urlsplit(module_dsn)
        schema = "case_" + uuid.uuid4().hex
        with psycopg.connect(module_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        self.stack.callback(self._drop_schema, module_dsn, schema)
        query = dict(parse_qsl(base.query))
        query["options"] = "-csearch_path=" + schema
        source_dsn = base._replace(query=urlencode(query)).geturl()
        database.close_pg_pool()
        with patch.object(get_settings(), "database_url", source_dsn), \
                patch.object(get_settings(), "archive_local_dir", str(self.source_files)):
            database.init_db()
            publisher = user_store.create_user("admin_console", "demo-password", role="admin")
            teacher = user_store.create_user("ui_teacher", "demo-password")
            self.reader = mini_auth.register("ui_reader", "reader-pass-123")
            self.vip = mini_auth.register("ui_vip", "vip-pass-123")
            mini_auth.update_membership(publisher.id, self.vip["user"]["id"], MembershipUpdate(
                revision=1, membership="vip", vip_expires_at=None, is_active=True))
            source = paper_library.create_paper(publisher.id, ArchiveCreate(
                request_id="demo-public", source_id="demo-public", snapshot=snapshot()))
            paper_library.publish_bundle(publisher.id, source["id"], bundle())
            self.paper = public_catalog.create_paper(publisher.id, CatalogCreate(paper_id=source["id"]))
            public_catalog.update_paper(publisher.id, self.paper["id"], CatalogUpdate(
                revision=1, title="Public demo", status="published", confirm_publication=True))
            catalog_access.update_type_rule("quiz", TypeAccessUpdate(
                revision=0, view_access="vip", download_access="vip"))
            public_catalog.favorite_paper(self.reader["user"]["id"], self.paper["id"], True)
            paper_library.create_paper(teacher.id, ArchiveCreate(
                request_id="private-only", source_id="private-only", snapshot=snapshot()))
        database.close_pg_pool()
        export_pg_schema_to_sqlite(source_dsn, self.source_db, _EXPORT_TABLES)

    @staticmethod
    def _drop_schema(module_dsn, schema):
        try:
            with psycopg.connect(module_dsn, autocommit=True) as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        except Exception:
            pass

    def run_import(self, apply=True):
        return import_catalog(self.source_db, self.source_files, self.admin.id, apply=apply)

    def test_dry_run_does_not_write_accounts_or_files(self):
        self.assertEqual(self.run_import(False)["status"], "dry_run")
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_users").fetchone()[0], 0)
        self.assertFalse((self.root / "target-files").exists())

    def test_import_preserves_permissions_sessions_and_existing_workbench_data(self):
        result = self.run_import()
        self.assertEqual(result["status"], "imported")
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM paper_archives").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT user_id FROM paper_archives").fetchone()[0], self.admin.id)
            self.assertEqual(conn.execute("SELECT value FROM app_config WHERE key = 'llm_model'").fetchone()[0], "existing-model")
            self.assertIsNone(conn.execute("SELECT admin_id FROM mini_membership_events").fetchone()[0])
        self.assertTrue(mini_auth.resolve_session(self.vip["token"]).is_vip)
        restricted = public_catalog.get_paper(self.reader["user"]["id"], self.paper["id"])
        self.assertFalse(restricted["can_view"])
        self.assertNotIn("snapshot", restricted)
        detail = public_catalog.get_paper(self.vip["user"]["id"], self.paper["id"])
        self.assertTrue(detail["can_download"])
        for asset in detail["assets"]:
            stored = public_catalog.get_asset(self.paper["id"], asset["id"], user_id=self.vip["user"]["id"])
            self.assertTrue(LocalStorage().path(stored["storage_key"]).is_file())

    def test_repeat_import_does_not_overwrite_later_membership_changes(self):
        self.run_import()
        mini_auth.update_membership(self.admin.id, self.vip["user"]["id"], MembershipUpdate(
            revision=2, membership="regular", vip_expires_at=None, is_active=True))
        self.assertEqual(self.run_import()["status"], "already_imported")
        self.assertFalse(mini_auth.get_user(self.vip["user"]["id"]).is_vip)

    def test_existing_consumer_data_is_not_merged_or_overwritten(self):
        mini_auth.register("real-consumer", "unchanged-password")
        with self.assertRaisesRegex(ValueError, "already contains consumer data"):
            self.run_import()
        self.assertFalse((self.root / "target-files").exists())

    def test_damaged_source_file_fails_before_writing(self):
        asset = next(self.source_files.rglob("*.jpg"))
        asset.write_bytes(b"damaged")
        with self.assertRaisesRegex(ValueError, "damaged"):
            self.run_import()
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_users").fetchone()[0], 0)

    def test_non_admin_publisher_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "administrator"):
            import_catalog(self.source_db, self.source_files, 1, apply=True)
