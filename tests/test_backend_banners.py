"""Banner upload, versioned public images and migration using disposable data."""

import importlib.util
import io
import os
import time
import unittest
from pathlib import Path

import psycopg
import test_backend_catalog as fixtures
from PIL import Image

from app import db as database
from app.config import get_settings
from app.routers import site
from app.services import file_retention
from app.site_schema import init_site_schema


def backup_script():
    """按路径加载备份脚本（scripts/ 不是包），用来核对备份清单。"""
    spec = importlib.util.spec_from_file_location("backup_restore", Path(__file__).resolve().parents[1] / "scripts" / "backup_restore.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BannerContracts(unittest.TestCase):
    sign_in = fixtures.PublicCatalogContracts.sign_in

    def setUp(self):
        fixtures.PublicCatalogContracts.setUp(self)
        self.client.app.include_router(site.router)
        self.client.app.include_router(site.admin_router)

    @staticmethod
    def photo(color="#426aa1", size=(1200, 500), format="PNG"):
        output = io.BytesIO()
        Image.new("RGB", size, color).save(output, format)
        return output.getvalue()

    def create(self, **changes):
        result = self.client.post("/api/v1/admin/site/banners", json={"title": "新学期练习", **changes})
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def upload(self, item, data=None, mime="image/png", revision=None):
        return self.client.put(f"/api/v1/admin/site/banners/{item['id']}/image",
                               params={"revision": revision or item["revision"]},
                               content=data if data is not None else self.photo(), headers={"Content-Type": mime})

    def update(self, item, **changes):
        body = {key: item[key] for key in ("revision", "title", "kicker", "subtitle", "action_label",
                                          "target_type", "target_value", "image_fit", "sort_order", "is_visible")}
        response = self.client.put(f"/api/v1/admin/site/banners/{item['id']}", json={**body, **changes})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_upload_replace_and_fit_are_visible_to_guests_with_new_image_urls(self):
        item = self.create(image_fit="cover", target_type="keyword", target_value="阅读")
        uploaded = self.upload(item)
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        first = uploaded.json()
        replacement = self.photo("#be7750", format="WEBP")
        result = self.upload(first, replacement, "image/webp")
        self.assertEqual(result.status_code, 200, result.text)
        second = result.json()
        self.assertNotEqual(first["image_url"], second["image_url"])
        second = self.update(second, image_fit="contain")
        self.client.cookies.clear()
        home = self.client.get("/api/v1/site/home").json()["banners"][0]
        self.assertEqual(home["image_fit"], "contain")
        self.assertEqual(home["image_url"], second["image_url"])
        self.assertEqual(home["target_value"], "阅读")
        self.assertNotIn("image_key", home)
        image = self.client.get(home["image_url"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.content, replacement)
        self.assertIn("no-store", image.headers["cache-control"])

    def test_stale_upload_does_not_overwrite_a_newer_image(self):
        item = self.create()
        original = self.photo()
        uploaded = self.upload(item, original).json()
        stale = self.upload(item, self.photo("#be7750"))
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(self.client.get(uploaded["image_url"]).content, original)
        current = self.client.get("/api/v1/admin/site/banners").json()["items"][0]
        self.assertEqual(current["revision"], uploaded["revision"])

    def test_hidden_banners_allow_admin_preview_but_not_public_images(self):
        item = self.create(is_visible=False)
        image = self.upload(item).json()
        self.assertEqual(self.client.get(f"/api/v1/admin/site/banners/{item['id']}/image").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/site/home").json()["banners"], [])
        self.assertEqual(self.client.get(image["image_url"]).status_code, 404)
        image = self.update(image, is_visible=True)
        cleared = self.client.delete(f"/api/v1/admin/site/banners/{item['id']}/image", params={"revision": image["revision"]})
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.json()["image_url"])
        self.assertIsNone(self.client.get("/api/v1/site/home").json()["banners"][0]["image_url"])
        self.assertEqual(self.client.get(image["image_url"]).status_code, 404)

    def test_invalid_files_and_invalid_fit_leave_the_banner_unchanged(self):
        item = self.create()
        for data, mime, status in ((b"broken", "image/png", 422), (b"x", "text/plain", 415),
                                   (self.photo(size=(2401, 500)), "image/png", 422),
                                   (b"x" * (2 * 1024 * 1024 + 1), "image/png", 413)):
            response = self.upload(item, data, mime)
            self.assertEqual(response.status_code, status, response.text)
        response = self.client.post("/api/v1/admin/site/banners", json={"title": "测试", "image_fit": "stretch"})
        self.assertEqual(response.status_code, 422)
        current = self.client.get("/api/v1/admin/site/banners").json()["items"][0]
        self.assertEqual(current["revision"], item["revision"])
        self.assertIsNone(current["image_url"])

    def test_existing_banner_rows_migrate_without_losing_copy_or_visibility(self):
        item = self.create(is_visible=False, subtitle="保留的文案")
        with database.db() as conn:
            conn.execute("ALTER TABLE site_banners DROP COLUMN image_fit")
            init_site_schema(conn)
            init_site_schema(conn)
        current = self.client.get("/api/v1/admin/site/banners").json()["items"][0]
        self.assertEqual(current["id"], item["id"])
        self.assertEqual(current["subtitle"], "保留的文案")
        self.assertFalse(current["is_visible"])
        self.assertEqual(current["revision"], item["revision"])
        self.assertEqual(current["image_fit"], "contain")

    def test_upload_requires_an_admin_session(self):
        item = self.create()
        self.client.cookies.clear()
        self.assertEqual(self.upload(item).status_code, 401)

    def test_orphan_scan_keeps_live_banner_images_and_collects_leftovers(self):
        # 回归：孤儿回收曾只认试卷与生图文件，上传满 24 小时的 Banner 图会被当成孤儿删掉
        uploaded = self.upload(self.create()).json()
        folder = self.root / "files" / "site" / "banners"
        [live] = list(folder.iterdir())
        leftover = folder / f"{'c' * 32}.png"  # 替换或删除 Banner 时没删掉的旧图
        leftover.write_bytes(self.photo())
        stale = time.time() - 90000
        for path in (live, leftover):
            os.utime(path, (stale, stale))
        file_retention._scan = None
        file_retention.scan_orphans()
        file_retention.drain()
        self.assertTrue(live.exists())
        self.assertFalse(leftover.exists())
        self.client.cookies.clear()
        self.assertEqual(self.client.get(uploaded["image_url"]).status_code, 200)

    def test_backup_manifest_includes_banner_images(self):
        uploaded = self.upload(self.create()).json()
        with database.db() as conn:
            key = conn.execute("SELECT image_key FROM site_banners WHERE id = ?", (uploaded["id"],)).fetchone()[0]
        with psycopg.connect(get_settings().database_url) as conn:
            files = backup_script().private_files(conn)
        self.assertIn(("local", key), files)


if __name__ == "__main__":
    unittest.main()
