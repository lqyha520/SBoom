"""Regression coverage for storage, import and bounded window validation."""
import io
import os
import time
import unittest
from unittest.mock import patch

import test_backend_catalog as fixtures
from PIL import Image
from test_backend_catalog_import import tiny_pdf

from app.config import get_settings
from app.db import db
from app.models.catalog import CatalogCreate
from app.services import catalog_import, file_retention, maintenance, paper_library, public_catalog


class OptimizationContracts(unittest.TestCase):
    setUp = fixtures.PublicCatalogContracts.setUp
    sign_in = fixtures.PublicCatalogContracts.sign_in
    source = fixtures.PublicCatalogContracts.source
    draft = fixtures.PublicCatalogContracts.draft
    update = fixtures.PublicCatalogContracts.update
    publish = fixtures.PublicCatalogContracts.publish

    def test_import_deduplicates_before_render_and_preserves_declared_metadata(self):
        raw = tiny_pdf()
        paper = catalog_import.import_paper(self.admin.id, "Metadata", "三年级", "数学", raw, "student", keyword="两位数", question_types=["quiz"], question_count=8)
        with patch.object(catalog_import, "_render_pages", side_effect=AssertionError("must not render twice")):
            replay = catalog_import.import_paper(self.admin.id, "Metadata", "三年级", "数学", raw, "student")
        self.assertEqual(replay["id"], paper["id"])
        draft = public_catalog.create_paper(self.admin.id, CatalogCreate(paper_id=paper["id"]))
        self.assertEqual(draft["question_types"], ["quiz"])
        self.assertEqual(draft["question_count"], 8)
        self.assertEqual(draft["keyword"], "两位数")
        self.assertEqual(draft["snapshot"]["paper"]["sections"], [])

    def test_render_gate_rejects_queued_pdf(self):
        catalog_import._import_gate.acquire()
        try:
            result = self.client.post("/api/v1/admin/catalog/import?grade=三年级&subject=数学", content=tiny_pdf(), headers={"Content-Type": "application/pdf"})
            self.assertEqual(result.status_code, 429)
        finally:
            catalog_import._import_gate.release()

    def test_published_answer_upload_preflight_and_confirmation(self):
        paper = self.publish()
        url = f"/api/v1/admin/catalog/papers/{paper['id']}/editions/import"
        with patch.object(catalog_import, "import_paper", side_effect=AssertionError("must preflight")):
            self.assertEqual(self.client.post(url, content=tiny_pdf(), headers={"Content-Type": "application/pdf"}).status_code, 422)
        result = self.client.post(url, params={"revision": paper["revision"], "confirm_publication": "true"}, content=tiny_pdf("Answers"), headers={"Content-Type": "application/pdf"})
        self.assertEqual(result.status_code, 200, result.text)
        detail = public_catalog.get_paper(self.admin.id, paper["id"], admin=True)
        self.assertEqual(detail["answer_readiness"], "separate")
        self.assertTrue(detail["reviewed_at"])
        self.assertEqual(detail["review_history"][0]["admin_id"], self.admin.id)

    def test_thumbnail_is_separate_and_revalidation_obeys_access_and_withdrawal(self):
        paper = self.publish()
        response = self.client.get(paper["thumbnail_url"])
        with Image.open(io.BytesIO(response.content)) as image:
            self.assertLessEqual(image.width, 320)
        self.assertNotIn(paper["thumbnail_id"], [asset["id"] for asset in paper["assets"]])
        private = self.update(paper, view_access="vip", download_access="vip").json()
        self.sign_in(self.viewer)
        result = self.client.post("/api/v1/catalog/window", json={"ids": [paper["id"], "missing"]})
        self.assertEqual(len(result.json()["items"]), 1)
        self.assertIsNone(result.json()["items"][0]["thumbnail_url"])
        self.sign_in(self.admin)
        self.update(private, status="withdrawn")
        self.sign_in(self.viewer)
        self.assertEqual(self.client.post("/api/v1/catalog/window", json={"ids": [paper["id"]]}).json()["items"], [])

    def test_failed_deletion_is_durable_and_retried(self):
        source = self.source()
        from app.services.paper_storage import LocalStorage
        with patch.object(LocalStorage, "delete", side_effect=PermissionError("busy")):
            paper_library.delete_paper(self.admin.id, source["id"])
        with db() as conn:
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM file_deletions").fetchone()[0], 0)
            conn.execute("UPDATE file_deletions SET next_attempt = 0")
        file_retention.drain()
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM file_deletions").fetchone()[0], 0)
        self.assertFalse(any((self.root / "files").rglob("*.pdf")))

    def test_orphan_grace_and_referenced_files_are_preserved(self):
        source = self.source()
        root = self.root / "files"
        orphans = root / "images" / "1"
        orphans.mkdir(parents=True)
        old, fresh = orphans / f"{'a' * 32}.png", orphans / f"{'b' * 32}.png"
        # 不是应用生成的存储键（例如 ARCHIVE_LOCAL_DIR 误指到数据目录时的密钥文件）：再旧也不能被回收
        foreign = root / "secret_key.txt"
        for path, data in ((old, b"old"), (fresh, b"new"), (foreign, b"secret")):
            path.write_bytes(data)
        with db() as conn:
            rows = conn.execute("SELECT storage_key FROM paper_assets WHERE paper_id = ?", (source["id"],)).fetchall()
        kept = [root / row["storage_key"] for row in rows]
        stale = time.time() - 90000
        for path in (old, foreign, *kept):
            os.utime(path, (stale, stale))
        file_retention._scan = None
        file_retention.scan_orphans()
        file_retention.drain()
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())
        self.assertTrue(foreign.exists())
        self.assertTrue(kept)
        self.assertTrue(all(path.exists() for path in kept))
        self.assertEqual(len(paper_library.get_paper(self.admin.id, source["id"])["assets"]), 2)

    def test_import_default_policy_is_explicit(self):
        with patch.object(get_settings(), "import_default_view_access", "vip"):
            raw = catalog_import.import_paper(self.admin.id, "Imported", "三年级", "数学", tiny_pdf())
            draft = public_catalog.create_paper(self.admin.id, CatalogCreate(paper_id=raw["id"]))
        self.assertEqual((draft["view_access"], draft["download_access"]), ("vip", "vip"))

    def test_legacy_thumbnail_is_backfilled_without_changing_detail_page_count(self):
        source = self.source()
        with db() as conn:
            conn.execute("DELETE FROM paper_assets WHERE paper_id = ? AND kind = 'thumbnail'", (source["id"],))
        before = paper_library.get_paper(self.admin.id, source["id"])
        maintenance.backfill_thumbnails()
        after = paper_library.get_paper(self.admin.id, source["id"])
        self.assertNotEqual(before["thumbnail_id"], after["thumbnail_id"])
        self.assertEqual(before["page_count"], after["page_count"])
        self.assertEqual(len(after["assets"]), 2)
