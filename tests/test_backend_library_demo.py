"""Demo fixtures use real archive contracts without touching non-test storage."""

import hashlib
import json
import tempfile
import unittest
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pg_support  # 建一次性测试库，必须在 import app 之前

pg_support.install_module_database()

from test_backend_library import bundle
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db as database, security
from app.config import get_settings
from app.deps import SESSION_COOKIE
from app.models.library import ArchiveCreate, ArchiveUpdate
from app.models.catalog import CatalogUpdate
from app.models.mini import MembershipUpdate
from app.routers import library
from app.services import mini_auth, paper_library, public_catalog, user_store
from library_demo import DATASET, FOLDERS, catalog, catalog_digest, seed_library, seed_public_catalog


class DemoLibraryContracts(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="learn-coach-ui-demo-test-")))
        pg_support.case_database(self.stack)
        for field, value in {"archive_local_dir": str(self.root / "private-papers"),
                             "archive_max_papers": 1000, "archive_storage_mb": 512, "archive_max_bundle_mb": 40}.items():
            self.stack.enter_context(patch.object(get_settings(), field, value))
        database.init_db()
        self.user = user_store.create_user("ui_teacher", "teacher-pass-123")
        self.other = user_store.create_user("another-teacher", "test-pass-123")
        self.reader = mini_auth.get_user(mini_auth.register("ui_vip", "vip-pass-123", admin=True)["user"]["id"])
        self.regular = mini_auth.get_user(mini_auth.register("ui_reader", "reader-pass-123", admin=True)["user"]["id"])
        mini_auth.update_membership(self.user.id, self.reader.id, MembershipUpdate(revision=1, membership="vip", is_active=True))
        self.assets = self.root / "demo"
        self.assets.mkdir()
        self.entries = catalog()
        content = bundle()
        self.manifest = {"dataset": DATASET, "catalog_sha256": catalog_digest(self.entries), "bundles": {}}
        for item in self.entries:
            if item["file_status"] == "ready":
                directory = self.assets / item["key"]
                directory.mkdir()
                (directory / "bundle.zip").write_bytes(content)
                self.manifest["bundles"][item["key"]] = {"sha256": hashlib.sha256(content).hexdigest(), "pages": 1}
        self.write_manifest()

    def write_manifest(self):
        (self.assets / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def seed(self):
        return seed_library(self.user, self.root, self.assets)

    def test_catalog_is_deterministic_and_matches_archive_schema(self):
        self.assertEqual(catalog(), self.entries)
        self.assertEqual(len(self.entries), 24)
        self.assertEqual(len({item["request"]["request_id"] for item in self.entries}), 24)
        for item in self.entries:
            ArchiveCreate.model_validate(item["request"])
        self.assertEqual({item["request"]["snapshot"]["paper"]["subject"] for item in self.entries}, {"数学", "语文", "英语"})
        self.assertEqual(len({item["request"]["snapshot"]["paper"]["grade"] for item in self.entries}), 6)
        self.assertEqual(sum(item["favorite"] for item in self.entries), 6)
        self.assertEqual({item["folder"] for item in self.entries if item["folder"]}, set(FOLDERS))

    def test_seed_has_files_versions_and_incomplete_states(self):
        result = self.seed()
        self.assertEqual((result["created"], result["papers"], result["favorites"], result["unfiled"]), (24, 24, 6, 11))
        self.assertGreater(result["storage_bytes"], 0)
        items = paper_library.list_papers(self.user.id, limit=100)["items"]
        self.assertEqual(Counter(item["file_status"] for item in items), {"ready": 22, "pending": 1, "failed": 1})
        versions = [item for item in items if item["source_id"] == "demo-math-unit"]
        self.assertEqual(sorted(item["version"] for item in versions), [1, 2])
        self.assertEqual(items[0]["version"], 2)
        for item in items:
            detail = paper_library.get_paper(self.user.id, item["id"])
            self.assertTrue(detail["snapshot"]["paper"]["sections"])
            if item["file_status"] == "ready":
                self.assertEqual({asset["kind"] for asset in detail["assets"]}, {"page", "pdf"})
            else:
                self.assertEqual(detail["assets"], [])
        self.assertEqual(paper_library.library_summary(self.other.id)["papers"], 0)

    def test_rerun_does_not_duplicate_or_overwrite_user_metadata(self):
        first = self.seed()
        item = paper_library.list_papers(self.user.id)["items"][0]
        changed = paper_library.update_paper(self.user.id, item["id"], ArchiveUpdate(title="我修改的标题", favorite=False, folder_id=None))
        folder = paper_library.list_folders(self.user.id)["items"][0]
        paper_library.save_folder(self.user.id, "我修改的文件夹", folder["id"])
        second = self.seed()
        self.assertEqual((second["created"], second["papers"], second["favorites"]), (0, 24, 5))
        self.assertEqual(first["storage_bytes"], second["storage_bytes"])
        self.assertEqual(paper_library.get_paper(self.user.id, item["id"]), changed)
        folders = paper_library.list_folders(self.user.id)["items"]
        self.assertEqual(len(folders), 4)
        self.assertIn("我修改的文件夹", [folder["name"] for folder in folders])

    def test_api_pagination_filters_and_private_downloads(self):
        self.seed()
        app = FastAPI()
        app.include_router(library.router)
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE, security.create_token(self.user.id))
            first = client.get("/api/v1/library/papers").json()
            second = client.get("/api/v1/library/papers?offset=20").json()
            self.assertEqual((len(first["items"]), first["has_more"], len(second["items"]), second["has_more"]), (20, True, 4, False))
            self.assertEqual(len({item["id"] for item in first["items"] + second["items"]}), 24)
            self.assertEqual(client.get("/api/v1/library/papers?favorite=true").json()["total"], 6)
            self.assertEqual(client.get("/api/v1/library/papers?folder_id=unfiled").json()["total"], 11)
            self.assertEqual(client.get("/api/v1/library/papers", params={"subject": "英语"}).json()["total"], 2)
            self.assertEqual(client.get("/api/v1/library/papers", params={"q": "第一单元"}).json()["total"], 2)
            folder = client.get("/api/v1/library/folders").json()["items"][0]
            self.assertEqual(client.get("/api/v1/library/papers", params={"folder_id": folder["id"]}).json()["total"], folder["paper_count"])
            paper = client.get(f"/api/v1/library/papers/{first['items'][0]['id']}").json()
            for asset in paper["assets"]:
                response = client.get(asset["url"])
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.content), asset["byte_size"])
                self.assertEqual(response.headers["cache-control"], "private, no-store")
            url = paper["assets"][0]["url"]
            client.cookies.set(SESSION_COOKIE, security.create_token(self.other.id))
            self.assertEqual(client.get(url).status_code, 404)
            client.cookies.clear()
            self.assertEqual(client.get(url).status_code, 401)

    def test_seeder_rejects_non_fixture_targets_before_writing(self):
        # 指向业务库（非一次性测试库）必须被拒绝，防止种子污染真实数据
        with patch.object(get_settings(), "database_url", "postgresql://learncoach:learncoach@127.0.0.1:5432/learncoach"):
            with self.assertRaisesRegex(ValueError, "disposable UI fixture"):
                self.seed()
        for field, value in (("database_url", "postgresql://not-a-test"),
                             ("archive_local_dir", str(self.root / "elsewhere"))):
            with self.subTest(field=field), patch.object(get_settings(), field, value):
                with self.assertRaisesRegex(ValueError, "disposable UI fixture"):
                    self.seed()
        with self.assertRaisesRegex(ValueError, "disposable UI fixture"):
            seed_library(self.other, self.root, self.assets)
        self.assertEqual(paper_library.library_summary(self.user.id)["papers"], 0)
        self.assertFalse((self.root / "private-papers").exists())

    def test_stale_or_damaged_assets_fail_before_creating_records(self):
        self.manifest["catalog_sha256"] = "stale"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "stale or incomplete"):
            self.seed()
        self.manifest["catalog_sha256"] = catalog_digest(self.entries)
        self.write_manifest()
        (self.assets / "math-unit-v1/bundle.zip").write_bytes(b"incomplete")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.seed()
        self.assertEqual(paper_library.library_summary(self.user.id)["papers"], 0)
        self.assertEqual(paper_library.list_folders(self.user.id)["items"], [])

    def test_public_demo_has_separate_sources_and_only_ready_publications(self):
        self.seed()
        publisher = user_store.create_user("admin_console", "admin-pass-123", role="admin")
        result = seed_public_catalog(publisher, self.reader, self.root, self.assets)
        self.assertEqual((result["created"], result["published"], result["draft"], result["favorites"], result["downloads"]), (24, 22, 2, 6, 3))
        self.assertEqual(paper_library.library_summary(self.user.id)["papers"], 24)
        self.assertEqual(paper_library.library_summary(publisher.id)["papers"], 25)
        self.assertEqual(public_catalog.list_sources(publisher.id)["total"], 1)
        self.assertEqual(public_catalog.list_papers(self.regular.id)["total"], 22)
        self.assertEqual(paper_library.library_summary(self.other.id)["papers"], 0)
        self.assertEqual(public_catalog.summary(self.regular.id)["favorites"], 0)
        self.assertEqual(public_catalog.summary(self.reader.id)["downloads"], 3)

    def test_public_demo_rerun_preserves_metadata_withdrawal_and_reader_choices(self):
        publisher = user_store.create_user("admin_console", "admin-pass-123", role="admin")
        seed_public_catalog(publisher, self.reader, self.root, self.assets)
        item = public_catalog.list_papers(self.reader.id, favorite=True)["items"][0]
        public_catalog.favorite_paper(self.reader.id, item["id"], False)
        changed = public_catalog.update_paper(publisher.id, item["id"], CatalogUpdate(
            revision=item["revision"], title="管理员改过的标题", status="withdrawn", category="自定义分类"))
        again = seed_public_catalog(publisher, self.reader, self.root, self.assets)
        self.assertEqual((again["created"], again["total"], again["published"], again["withdrawn"], again["favorites"]), (0, 24, 21, 1, 5))
        self.assertEqual(public_catalog.get_paper(publisher.id, item["id"], admin=True), changed)
        self.assertEqual(paper_library.library_summary(publisher.id)["papers"], 25)

    def test_public_seeder_enforces_fixture_accounts_and_storage_before_writing(self):
        publisher = user_store.create_user("admin_console", "admin-pass-123", role="admin")
        with self.assertRaisesRegex(ValueError, "disposable UI fixture"):
            seed_public_catalog(self.other, self.user, self.root, self.assets)
        with self.assertRaisesRegex(ValueError, "disposable UI fixture"):
            seed_public_catalog(publisher, self.other, self.root, self.assets)
        with patch.object(get_settings(), "database_url", "postgresql://learncoach:learncoach@127.0.0.1:5432/learncoach"):
            with self.assertRaisesRegex(ValueError, "disposable UI fixture"):
                seed_public_catalog(publisher, self.reader, self.root, self.assets)
        for field, value in (("database_url", "postgresql://not-a-test"),
                             ("archive_local_dir", str(self.root / "elsewhere"))):
            with self.subTest(field=field), patch.object(get_settings(), field, value):
                with self.assertRaisesRegex(ValueError, "disposable UI fixture"):
                    seed_public_catalog(publisher, self.reader, self.root, self.assets)
        self.manifest["catalog_sha256"] = "stale"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "stale or incomplete"):
            seed_public_catalog(publisher, self.reader, self.root, self.assets)
        self.assertEqual(public_catalog.admin_summary()["total"], 0)
        self.assertEqual(paper_library.library_summary(publisher.id)["papers"], 0)
        self.assertFalse((self.root / "private-papers").exists())


if __name__ == "__main__":
    unittest.main()
