"""Anonymous discovery and explicit photo/profile updates across HTTP and persistence."""

import base64
import io
import unittest
from unittest.mock import AsyncMock, patch

import test_backend_catalog as fixtures
from PIL import Image, PngImagePlugin
from app import db as database
from app.routers import engagement, experience, site
from app.services import mini_auth


class GuestProfileContracts(unittest.TestCase):
    sign_in = fixtures.PublicCatalogContracts.sign_in
    source = fixtures.PublicCatalogContracts.source
    draft = fixtures.PublicCatalogContracts.draft
    update = fixtures.PublicCatalogContracts.update
    publish = fixtures.PublicCatalogContracts.publish
    restricted = fixtures.PublicCatalogContracts.restricted
    membership = fixtures.PublicCatalogContracts.membership

    def setUp(self):
        fixtures.PublicCatalogContracts.setUp(self)
        for router in (site.router, site.admin_router, engagement.router, experience.router):
            self.client.app.include_router(router)

    def guest(self):
        self.client.cookies.clear()
        self.client.headers.pop("Authorization", None)
        self.client.headers.pop("X-Mini-User", None)

    @staticmethod
    def photo(size=(320, 200)):
        output = io.BytesIO()
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("source", "private-photo-metadata")
        Image.new("RGB", size, "#307e61").save(output, "PNG", pnginfo=metadata)
        return base64.b64encode(output.getvalue()).decode("ascii")

    def test_guests_browse_home_search_topics_tags_and_free_previews(self):
        paper = self.publish()
        hidden = self.draft()
        self.guest()
        for path in ("/api/v1/site/home", "/api/v1/site/topics", "/api/v1/site/catalog-tags", "/api/v1/catalog/summary"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("no-store", response.headers["cache-control"])
        result = self.client.get("/api/v1/catalog/papers", params={"q": "公共单元", "only_free": True}).json()
        self.assertEqual([item["id"] for item in result["items"]], [paper["id"]])
        self.assertFalse(result["items"][0]["favorite"])
        self.assertFalse(result["items"][0]["can_download"])
        detail = self.client.get("/api/v1/catalog/papers/" + paper["id"]).json()
        self.assertIsNotNone(detail["snapshot"])
        self.assertNotIn("private-only-marker", str(detail))
        self.assertTrue(detail["assets"])
        for asset in detail["assets"]:
            self.assertEqual(asset["kind"], "page")
            self.assertEqual(self.client.get(asset["url"]).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/catalog/papers/" + hidden["id"]).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/catalog/summary").json()["favorites"], 0)
        with database.db() as conn:
            for table in ("mini_recent_views", "mini_catalog_downloads", "mini_catalog_favorites", "mini_usage_events"):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_guests_cannot_use_member_access_personal_records_or_pdf_urls(self):
        free, vip = self.publish(), self.restricted()
        free_pdf = next(asset["url"] for asset in free["assets"] if asset["kind"] == "pdf").replace("/admin/catalog/", "/catalog/")
        vip_page = next(asset["url"] for asset in vip["assets"] if asset["kind"] == "page").replace("/admin/catalog/", "/catalog/")
        # Workbench cookies cannot confer mini-program membership.
        detail = self.client.get("/api/v1/catalog/papers/" + vip["id"]).json()
        self.assertFalse(detail["can_view"])
        self.guest()
        detail = self.client.get("/api/v1/catalog/papers/" + vip["id"]).json()
        self.assertIsNone(detail["snapshot"])
        self.assertIsNone(detail["thumbnail_url"])
        self.assertEqual(detail["assets"], [])
        self.assertEqual(self.client.get(vip_page).status_code, 403)
        self.assertEqual(self.client.get(free_pdf).status_code, 401)
        prefix = "/api/v1/catalog/papers/" + free["id"]
        self.assertEqual(self.client.post(prefix + "/download").status_code, 401)
        self.assertEqual(self.client.put(prefix + "/favorite", json={"favorite": True}).status_code, 401)
        for query in ({"favorite": True}, {"downloaded": True}, {"recent": True}, {"favorite_group": "another-user"}):
            self.assertEqual(self.client.get("/api/v1/catalog/papers", params=query).status_code, 401)
        for path in ("/api/v1/mini/me", "/api/v1/mini/messages", "/api/v1/mini/favorite-groups", "/api/v1/admin/catalog/papers"):
            self.assertEqual(self.client.get(path).status_code, 401, path)
        self.assertEqual(self.client.get("/api/v1/catalog/papers", headers={"Authorization": "Bearer invalid"}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/catalog/papers", headers={"X-Mini-User": self.viewer.id}).status_code, 401)

    def test_wechat_supported_profile_method_saves_unicode_without_changing_login(self):
        self.sign_in(self.viewer)
        for nickname in ("一", "小明 😀", "👩‍🏫 王老师", " 🌿 ", "😀" * 32):
            response = self.client.put("/api/v1/mini/me", json={"nickname": nickname})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["nickname"], nickname.strip())
            self.assertEqual(response.json()["username"], self.viewer.username)
        self.assertEqual(mini_auth.login_password(self.viewer.username, "test-password")["user"]["nickname"], "😀" * 32)
        for nickname in (" ", "a\nb", "a\u202eb", "😀" * 33):
            self.assertEqual(self.client.put("/api/v1/mini/me", json={"nickname": nickname}).status_code, 422)
        self.assertEqual(self.client.put("/api/v1/mini/me", json={"nickname": "合法昵称", "membership": "vip"}).status_code, 422)

    def test_photo_and_nickname_save_together_and_survive_reload(self):
        self.sign_in(self.viewer)
        response = self.client.post("/api/v1/mini/me/avatar", json={"image": self.photo(), "nickname": "小读者 😀"})
        self.assertEqual(response.status_code, 200, response.text)
        user = response.json()
        self.assertEqual(user["nickname"], "小读者 😀")
        self.assertEqual(user["username"], self.viewer.username)
        self.assertTrue(user["avatar"].startswith("photo:"))
        image = self.client.get(user["avatar_url"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers["content-type"], "image/jpeg")
        self.assertIn("no-store", image.headers["cache-control"])
        self.assertNotIn(b"private-photo-metadata", image.content)
        with Image.open(io.BytesIO(image.content)) as photo:
            self.assertEqual(photo.size, (256, 256))
            self.assertFalse(photo.getexif())
        database.init_db()
        self.assertEqual(self.client.get("/api/v1/mini/me").json()["avatar_url"], user["avatar_url"])
        changed = self.client.put("/api/v1/mini/me", json={"nickname": "新名字"}).json()
        self.assertEqual(changed["avatar_url"], user["avatar_url"])

    def test_new_wechat_accounts_get_short_nicknames_and_separate_ascii_accounts(self):
        self.guest()
        with patch.object(mini_auth, "exchange_code", AsyncMock(return_value="new-wechat-profile")):
            first = self.client.post("/api/v1/mini/login", json={"code": "fixture-code"})
            self.assertEqual(first.status_code, 200, first.text)
            user = first.json()["user"]
            self.assertRegex(user["username"], r"^wx[0-9]{10}$")
            self.assertRegex(user["nickname"], r"^[\u4e00-\u9fff]{2,4}$")
            self.assertNotEqual(user["username"], user["nickname"])
            repeated = self.client.post("/api/v1/mini/login", json={"code": "fresh-code"}).json()["user"]
            self.assertEqual(repeated, user)

    def test_wechat_account_collisions_retry_without_lengthening_nicknames(self):
        with patch.object(mini_auth.secrets, "randbelow", side_effect=[7, 7, 8]):
            first = mini_auth.login_public_identity("wechat-collision-one")["user"]
            second = mini_auth.login_public_identity("wechat-collision-two")["user"]
        self.assertEqual(first["username"], "wx0000000007")
        self.assertEqual(second["username"], "wx0000000008")
        self.assertLessEqual(len(second["nickname"]), 4)

    def test_new_registration_disallows_chinese_but_legacy_accounts_still_log_in(self):
        self.guest()
        for name in ("中文账号", "账号reader", "ｒｅａｄｅｒ", "réader", "reader space", "reader@example"):
            result = self.client.post("/api/v1/mini/register", json={"username": name, "password": "test-password"})
            self.assertEqual(result.status_code, 422, result.text)
            self.assertIn("不能使用中文", result.text)
        created = self.client.post("/api/v1/mini/register", json={"username": "reader_2026-test", "password": "test-password"})
        self.assertEqual(created.status_code, 201, created.text)
        self.sign_in(self.admin)
        rejected = self.client.post("/api/v1/admin/mini-users", json={"username": "新的中文账号", "password": "test-password"})
        self.assertEqual(rejected.status_code, 422)
        with database.db() as conn:
            conn.execute("UPDATE mini_users SET username = ?, nickname = ? WHERE id = ?", ("旧的中文账号", "小读者", self.viewer.id))
        self.guest()
        legacy = self.client.post("/api/v1/mini/login-password", json={"username": "旧的中文账号", "password": "test-password"})
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(legacy.json()["user"]["id"], self.viewer.id)
        self.assertEqual(legacy.json()["user"]["nickname"], "小读者")

    def test_existing_wechat_accounts_keep_their_login_identifier_and_edited_nickname(self):
        user = mini_auth.login_public_identity("existing-wechat-profile")["user"]
        with database.db() as conn:
            conn.execute("UPDATE mini_users SET username = ?, nickname = ? WHERE id = ?", ("认真的小鹿1234", "向阳", user["id"]))
        returned = mini_auth.login_public_identity("existing-wechat-profile")["user"]
        self.assertEqual(returned["username"], "认真的小鹿1234")
        self.assertEqual(returned["nickname"], "向阳")

    def test_all_five_presets_can_replace_an_uploaded_photo_and_survive_reload(self):
        self.sign_in(self.viewer)
        photo = self.client.post("/api/v1/mini/me/avatar", json={"image": self.photo()}).json()
        for preset in ("fox", "panda", "penguin", "deer", "rabbit"):
            result = self.client.put("/api/v1/mini/me", json={"avatar": preset})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["avatar"], preset)
            self.assertIsNone(result.json()["avatar_url"])
            self.assertEqual(self.client.get("/api/v1/mini/me").json()["avatar"], preset)
        database.init_db()
        self.assertEqual(self.client.get("/api/v1/mini/me").json()["avatar"], "rabbit")
        self.assertEqual(self.client.get(photo["avatar_url"]).status_code, 404)

    def test_photo_access_is_owner_scoped_and_admin_requires_its_own_session(self):
        self.sign_in(self.viewer)
        user = self.client.post("/api/v1/mini/me/avatar", json={"image": self.photo()}).json()
        self.sign_in(self.other)
        self.assertEqual(self.client.get(user["avatar_url"]).status_code, 404)
        self.assertIsNone(self.client.get("/api/v1/mini/me").json()["avatar_url"])
        self.guest()
        self.assertEqual(self.client.get(user["avatar_url"]).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/mini/me/avatar", json={"image": self.photo()}).status_code, 401)
        self.sign_in(self.admin)
        admin_user = next(item for item in self.client.get("/api/v1/admin/mini-users").json()["items"] if item["id"] == user["id"])
        self.assertEqual(self.client.get(admin_user["avatar_url"]).status_code, 200)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get(admin_user["avatar_url"]).status_code, 401)

    def test_replacing_resetting_and_deleting_remove_the_previous_photo(self):
        self.sign_in(self.viewer)
        first = self.client.post("/api/v1/mini/me/avatar", json={"image": self.photo()}).json()
        second = self.client.post("/api/v1/mini/me/avatar", json={"image": self.photo()}).json()
        self.assertNotEqual(first["avatar_url"], second["avatar_url"])
        self.assertEqual(self.client.get(first["avatar_url"]).status_code, 404)
        reset = self.client.put("/api/v1/mini/me", json={"avatar": ""}).json()
        self.assertIsNone(reset["avatar_url"])
        self.assertEqual(self.client.get(second["avatar_url"]).status_code, 404)
        self.client.post("/api/v1/mini/me/avatar", json={"image": self.photo()})
        self.sign_in(self.admin)
        removed = self.client.delete("/api/v1/admin/mini-users/" + self.viewer.id)
        self.assertEqual(removed.status_code, 200, removed.text)
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_user_avatars").fetchone()[0], 0)

    def test_invalid_photo_cannot_partially_change_profile_or_inject_an_image_url(self):
        self.sign_in(self.viewer)
        old = self.client.get("/api/v1/mini/me").json()
        cases = [
            ({"image": "https://example.test/photo.jpg", "nickname": "应保留原名"}, 422),
            ({"image": base64.b64encode(b'<svg onload="alert(1)"/>').decode()}, 422),
            ({"image": self.photo(), "nickname": " "}, 422),
            ({"image": self.photo((4097, 1)), "nickname": "应保留原名"}, 413),
            ({"image": "A" * (3 * 1024 * 1024)}, 413),
        ]
        for body, status in cases:
            response = self.client.post("/api/v1/mini/me/avatar", json=body)
            self.assertEqual(response.status_code, status, response.text[:300])
            self.assertEqual(self.client.get("/api/v1/mini/me").json(), old)
        self.assertEqual(self.client.put("/api/v1/mini/me", json={"avatar": "photo:" + "a" * 24}).status_code, 422)
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_user_avatars").fetchone()[0], 0)

    def test_stale_or_disabled_sessions_cannot_change_photos(self):
        self.sign_in(self.viewer)
        response = self.client.post("/api/v1/mini/me/avatar", headers={"X-Mini-User": self.other.id}, json={"image": self.photo()})
        self.assertEqual(response.status_code, 409)
        self.membership(self.viewer, level="regular", active=False)
        self.assertEqual(self.client.post("/api/v1/mini/me/avatar", json={"image": self.photo()}).status_code, 401)
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_user_avatars").fetchone()[0], 0)
