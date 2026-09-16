"""Banner upload, versioned public images and migration using disposable data."""

import io
import unittest

import test_backend_catalog as fixtures
from PIL import Image
from app import db as database
from app.routers import site
from app.site_schema import init_site_schema


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


if __name__ == "__main__":
    unittest.main()
