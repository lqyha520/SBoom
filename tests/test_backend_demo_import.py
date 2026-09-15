"""Explicit demo imports preserve account separation, file integrity and user edits."""

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from app import db as database
from app.config import get_settings
from app.models.catalog import CatalogCreate, CatalogUpdate, TypeAccessUpdate
from app.models.library import ArchiveCreate
from app.models.mini import MembershipUpdate
from app.services import catalog_access, mini_auth, paper_library, public_catalog, user_store
from app.services.paper_storage import LocalStorage
from scripts.import_demo_catalog import import_catalog
from test_backend_library import bundle, snapshot


class DemoImportContracts(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="lc-demo-import-")))
        self.source_db = self.root / "source.db"
        self.source_files = self.root / "source-files"
        self.stack.enter_context(patch.object(get_settings(), "database_url", ""))
        self.stack.enter_context(patch.object(get_settings(), "archive_storage", "local"))
        self.stack.enter_context(patch.object(get_settings(), "mini_registration_enabled", True))
        with patch.object(database, "DB_PATH", self.source_db), \
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
        self.stack.enter_context(patch.object(database, "DB_PATH", self.root / "target.db"))
        self.stack.enter_context(patch.object(get_settings(), "archive_local_dir", str(self.root / "target-files")))
        database.init_db()
        user_store.create_user("existing-user", "unchanged-password")
        self.admin = user_store.create_user("existing-admin", "unchanged-password", role="admin")
        with database.db() as conn:
            conn.execute("INSERT INTO app_config(key, value) VALUES ('llm_model', 'existing-model')")

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
        self.assertIsNone(restricted["snapshot"])
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
