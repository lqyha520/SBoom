"""Public catalog publication, privacy and self-service login contracts."""

"""Public catalog publication, privacy and self-service login contracts."""

import copy
import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "")  # 防御：下面 install_module_database 会覆盖为一次性测试库

import pg_support  # noqa: E402  建一次性测试库，必须在 import app 之前

pg_support.install_module_database({"SECRET_KEY": "catalog-tests-disposable-secret-no-production",
                                    "LLM_API_KEY": "", "ADMIN_USERNAME": "", "ADMIN_PASSWORD": ""})

from test_backend_library import bundle, snapshot
from app import db as database, security
from app.config import get_settings
from app.deps import SESSION_COOKIE
from app.models.library import ArchiveCreate
from app.models.mini import MembershipUpdate, MiniPasswordUpdate, MiniProfileUpdate
from app.routers import admin, auth, catalog, generate, library, mini
from app.services import mini_auth, paper_library, user_store


class PublicCatalogContracts(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="lc-catalog-test-")))
        pg_support.case_database(self.stack)
        for field, value in {"archive_local_dir": str(self.root / "files"),
                             "registration_enabled": True, "mini_registration_enabled": True, "archive_max_papers": 1000, "archive_storage_mb": 512}.items():
            self.stack.enter_context(patch.object(get_settings(), field, value))
        self.stack.enter_context(patch.object(mini, "allow", return_value=True))
        self.stack.enter_context(patch.object(auth, "allow", return_value=True))
        database.init_db()
        self.admin = user_store.create_user("catalog-admin", "test-password", role="admin")
        self.author = user_store.create_user("catalog-reader", "author-password")
        self.viewer = mini_auth.get_user(mini_auth.register("catalog-reader", "test-password")["user"]["id"])
        self.other = mini_auth.get_user(mini_auth.register("other-reader", "test-password")["user"]["id"])
        app = FastAPI()
        for router in (catalog.router, catalog.admin_router, library.router, auth.router, mini.router, admin.router, generate.router):
            app.include_router(router)
        self.client = self.stack.enter_context(TestClient(app))
        self.sign_in(self.admin)
        self.source_number = 0

    def sign_in(self, user):
        self.client.cookies.clear()
        self.client.headers.pop("Authorization", None)
        if isinstance(user, mini_auth.MiniUser):
            result = mini_auth.login_password(user.username, "test-password")
            self.client.headers["Authorization"] = "Bearer " + result["token"]
        else:
            self.client.cookies.set(SESSION_COOKIE, security.create_token(user.id))

    def source(self, owner=None, ready=True):
        self.source_number += 1
        value = snapshot()
        value["paper"]["private_editor_state"] = "private-only-marker"
        value["paper"]["sections"][0]["data"]["questions"][0]["prompt"] = "private-only-marker"
        value["template"]["headerExtra"] = "private-only-marker"
        paper = paper_library.create_paper((owner or self.admin).id, ArchiveCreate(
            request_id=f"catalog-request-{self.source_number}", source_id=f"catalog-source-{self.source_number}",
            group_name="private-only-marker", snapshot=value))
        return paper_library.publish_bundle((owner or self.admin).id, paper["id"], bundle()) if ready else paper

    def draft(self, source=None):
        source = source or self.source()
        result = self.client.post("/api/v1/admin/catalog/papers", json={"paper_id": source["id"], "title": "公共单元练习", "category": "单元练习"})
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def update(self, item, **changes):
        body = {"revision": item["revision"], "title": item["title"], "description": item["description"],
                "category": item["category"], "status": item["status"], "featured": item["featured"], **changes}
        return self.client.put(f"/api/v1/admin/catalog/papers/{item['id']}", json=body)

    def publish(self, item=None):
        result = self.update(item or self.draft(), status="published", confirm_publication=True)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_private_archives_and_drafts_are_not_public(self):
        source = self.source()
        draft = self.draft(source)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get("/api/v1/catalog/papers").json()["total"], 0)
        self.assertEqual(self.client.get(f"/api/v1/catalog/papers/{draft['id']}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/library/papers/{source['id']}").status_code, 403)
        self.assertEqual(self.client.get(draft["assets"][0]["url"]).status_code, 401)
        self.client.cookies.clear()
        self.client.headers.pop("Authorization", None)
        self.assertEqual(self.client.get("/api/v1/catalog/papers").json()["total"], 0)
        self.assertEqual(self.client.get("/api/v1/catalog/summary").json()["papers"], 0)

    def test_published_content_and_files_are_available_to_other_users(self):
        source = self.source()
        published = self.publish(self.draft(source))
        self.sign_in(self.viewer)
        response = self.client.get(f"/api/v1/catalog/papers/{published['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("private-only-marker", response.text)
        self.assertNotIn("archive_id", response.text)
        self.assertEqual(response.json()["scope"], "catalog")
        for asset in response.json()["assets"]:
            self.assertEqual(self.client.get(asset["url"]).status_code, 200)
            self.assertEqual(self.client.get(asset["url"]).headers["cache-control"], "private, no-store")
        self.assertEqual(self.client.get(source["assets"][0]["url"]).status_code, 403)
        public_url = response.json()["assets"][0]["url"]
        self.client.cookies.clear()
        self.client.headers.pop("Authorization", None)
        self.assertEqual(self.client.get(public_url).status_code, 401)

    def test_publish_needs_explicit_confirmation_and_complete_files(self):
        draft = self.draft()
        self.assertEqual(self.update(draft, status="published").status_code, 422)
        pending = self.draft(self.source(ready=False))
        self.assertEqual(self.update(pending, status="published", confirm_publication=True).status_code, 409)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get("/api/v1/catalog/papers").json()["total"], 0)

    def test_only_admin_can_manage_catalog_and_only_owned_sources_can_be_selected(self):
        source = self.source(self.author)
        self.assertEqual(self.client.post("/api/v1/admin/catalog/papers", json={"paper_id": source["id"]}).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/admin/catalog/sources").json()["total"], 0)
        published = self.publish()
        self.sign_in(self.author)
        for path in ("/api/v1/admin/catalog/papers", "/api/v1/admin/catalog/sources", "/api/v1/admin/catalog/summary"):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.post("/api/v1/admin/catalog/papers", json={"paper_id": source["id"]}).status_code, 403)
        self.assertEqual(self.update(published, title="unauthorized").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/v1/admin/catalog/papers/{published['id']}?revision=2").status_code, 403)

    def test_favorites_and_download_history_are_per_user_and_idempotent(self):
        item = self.publish()
        path = f"/api/v1/catalog/papers/{item['id']}"
        self.sign_in(self.viewer)
        for _ in range(2):
            self.assertEqual(self.client.put(path + "/favorite", json={"favorite": True}).status_code, 200)
            self.assertEqual(self.client.post(path + "/download").status_code, 200)
        summary = self.client.get("/api/v1/catalog/summary").json()
        self.assertEqual((summary["favorites"], summary["downloads"]), (1, 1))
        self.assertEqual(self.client.get("/api/v1/catalog/papers?downloaded=true").json()["total"], 1)
        self.sign_in(self.other)
        self.assertFalse(self.client.get(path).json()["favorite"])
        self.assertEqual(self.client.get("/api/v1/catalog/summary").json()["downloads"], 0)
        self.sign_in(self.admin)
        row = self.client.get("/api/v1/admin/catalog/papers").json()["items"][0]
        self.assertEqual((row["favorite_count"], row["download_users"]), (1, 1))
        self.assertFalse(paper_library.list_papers(self.admin.id)["items"][0]["favorite"])

    def test_withdrawal_revokes_details_files_favorites_and_download_requests(self):
        item = self.publish()
        path = f"/api/v1/catalog/papers/{item['id']}"
        self.sign_in(self.viewer)
        detail = self.client.get(path).json()
        self.client.put(path + "/favorite", json={"favorite": True})
        self.client.post(path + "/download")
        self.sign_in(self.admin)
        self.assertEqual(self.update(item, status="withdrawn").status_code, 200)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get(path).status_code, 404)
        for asset in detail["assets"]:
            self.assertEqual(self.client.get(asset["url"]).status_code, 404)
        self.assertEqual(self.client.post(path + "/download").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/catalog/papers?favorite=true").json()["total"], 0)
        self.assertEqual(self.client.get("/api/v1/catalog/summary").json()["downloads"], 0)

    def test_personal_lists_sort_by_activity_instead_of_publication_featured_order(self):
        first, second = self.publish(), self.publish()
        self.assertEqual(self.update(first, featured=True).status_code, 200)
        self.sign_in(self.viewer)
        for item in (first, second):
            path = f"/api/v1/catalog/papers/{item['id']}"
            self.client.put(path + "/favorite", json={"favorite": True}).raise_for_status()
            self.client.post(path + "/download").raise_for_status()
        with database.db() as conn:
            for item, stamp in ((first, 100), (second, 200)):
                conn.execute("UPDATE mini_catalog_favorites SET created_at = ? WHERE user_id = ? AND catalog_id = ?",
                             (stamp, self.viewer.id, item["id"]))
                conn.execute("UPDATE mini_catalog_downloads SET requested_at = ? WHERE user_id = ? AND catalog_id = ?",
                             (stamp, self.viewer.id, item["id"]))
        for query in ("favorite=true", "downloaded=true", "favorite=true&sort=latest", "downloaded=true&sort=latest"):
            result = self.client.get("/api/v1/catalog/papers?" + query).json()["items"]
            self.assertEqual([item["id"] for item in result], [second["id"], first["id"]])
            self.assertEqual([item["activity_at"] for item in result], [200, 100])
        self.assertEqual(self.client.get("/api/v1/catalog/papers").json()["items"][0]["id"], first["id"])

    def test_latest_feed_uses_publication_time_and_keeps_filters_and_pagination(self):
        first, second = self.publish(), self.publish()
        self.assertEqual(self.update(first, featured=True).status_code, 200)
        self.draft()
        with database.db() as conn:
            for item, stamp in ((first, 100), (second, 200)):
                conn.execute("UPDATE catalog_papers SET published_at = ? WHERE id = ?", (stamp, item["id"]))
        self.sign_in(self.viewer)
        base = "/api/v1/catalog/papers"
        self.assertEqual(self.client.get(base).json()["items"][0]["id"], first["id"])
        latest = self.client.get(base, params={"sort": "latest", "limit": 1, "category": "单元练习"}).json()
        self.assertEqual(latest["items"][0]["id"], second["id"])
        self.assertEqual((latest["total"], latest["has_more"]), (2, True))
        next_page = self.client.get(base, params={"sort": "latest", "limit": 1, "offset": 1}).json()
        self.assertEqual(next_page["items"][0]["id"], first["id"])
        self.assertFalse(next_page["has_more"])
        self.assertEqual(self.client.get(base, params={"sort": "latest", "subject": "语文"}).json()["total"], 0)
        self.assertEqual(self.client.get(base, params={"sort": "c.id; DROP TABLE catalog_papers"}).status_code, 422)
        self.sign_in(self.admin)
        self.assertEqual(self.client.get("/api/v1/admin/catalog/papers").json()["items"][0]["id"], first["id"])

    def test_asset_id_cannot_cross_publications_or_private_archives(self):
        item = self.publish()
        private = self.source()
        second = self.publish()
        self.sign_in(self.viewer)
        for asset in (private["assets"][0], second["assets"][0]):
            self.assertEqual(self.client.get(f"/api/v1/catalog/papers/{item['id']}/assets/{asset['id']}").status_code, 404)

    def test_revision_conflicts_and_publication_deletion_preserve_source(self):
        source = self.source()
        draft = self.draft(source)
        self.assertEqual(self.client.post("/api/v1/admin/catalog/papers", json={"paper_id": source["id"]}).status_code, 409)
        published = self.publish(draft)
        self.assertEqual(self.update(draft, title="stale").status_code, 409)
        self.assertEqual(self.client.delete(f"/api/v1/admin/catalog/papers/{draft['id']}?revision=1").status_code, 409)
        self.assertEqual(self.client.delete(f"/api/v1/library/papers/{source['id']}").status_code, 409)
        with self.assertRaises(user_store.UserHasCatalogPapers):
            user_store.delete_user(self.admin.id)
        self.assertEqual(self.client.delete(f"/api/v1/admin/catalog/papers/{published['id']}?revision=2").status_code, 204)
        self.assertEqual(self.client.get(f"/api/v1/library/papers/{source['id']}").status_code, 200)
        self.assertEqual(self.client.get(source["assets"][0]["url"]).status_code, 200)

    def test_filters_pagination_and_repeated_schema_initialization(self):
        first = self.publish()
        self.publish()
        database.init_db()
        self.sign_in(self.viewer)
        result = self.client.get("/api/v1/catalog/papers?limit=1").json()
        self.assertEqual((len(result["items"]), result["total"], result["has_more"]), (1, 2, True))
        self.assertFalse(self.client.get("/api/v1/catalog/papers?limit=1&offset=1").json()["has_more"])
        self.assertEqual(self.client.get("/api/v1/catalog/papers", params={"subject": "数学", "category": "单元练习"}).json()["total"], 2)
        self.assertEqual(self.client.get("/api/v1/catalog/papers", params={"q": "%"}).json()["total"], 0)
        self.assertEqual(self.client.get(f"/api/v1/catalog/papers/{first['id']}").status_code, 200)

    def test_new_wechat_users_login_without_binding_and_never_become_admin(self):
        self.client.cookies.clear()
        with patch.object(mini_auth, "exchange_code", new=AsyncMock(return_value="verified-wechat-identity")):
            first = self.client.post("/api/v1/mini/login-public", json={"code": "wx-code"})
            second = self.client.post("/api/v1/mini/login-public", json={"code": "new-wx-code"})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["status"], "authenticated")
        self.assertEqual(first.json()["user"], second.json()["user"])
        user = mini_auth.get_user(first.json()["user"]["id"])
        self.assertEqual(user.membership, "regular")
        with database.db() as conn:
            self.assertFalse(conn.execute("SELECT id FROM users WHERE username = ?", (user.username,)).fetchone())
        self.client.headers["Authorization"] = "Bearer " + first.json()["token"]
        self.assertEqual(self.client.get("/api/v1/catalog/papers").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/admin/catalog/papers").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        mini_auth.update_membership(self.admin.id, user.id, MembershipUpdate(revision=1, membership="regular", is_active=False))
        self.assertEqual(self.client.get("/api/v1/catalog/papers").status_code, 401)

    def test_concurrent_wechat_signup_and_registration_switch(self):
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(lambda _: mini_auth.login_public_identity("same-identity"), range(3)))
        self.assertEqual(len({result["user"]["id"] for result in results}), 1)
        with patch.object(get_settings(), "mini_registration_enabled", False):
            self.assertEqual(mini_auth.login_public_identity("same-identity")["status"], "authenticated")
            with self.assertRaises(Exception) as error:
                mini_auth.login_public_identity("new-identity")
            self.assertEqual(error.exception.status_code, 403)

    def test_public_registration_does_not_bootstrap_an_administrator(self):
        with database.db() as conn:
            conn.execute("UPDATE users SET role = 'user'")
        self.client.cookies.clear()
        result = self.client.post("/api/v1/auth/register", json={"username": "new-public-reader", "password": "test-password"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["role"], "user")
        self.assertEqual(user_store.count_admins(), 0)
        self.assertEqual(self.client.get("/api/v1/admin/catalog/papers").status_code, 403)

    def membership(self, member, level="vip", expires=None, active=True):
        before = mini_auth.admin_user(member.id)
        return mini_auth.update_membership(self.admin.id, member.id, MembershipUpdate(
            revision=before["revision"], membership=level, vip_expires_at=expires, is_active=active))

    def restricted(self, view="vip", download="vip"):
        item = self.publish()
        response = self.update(item, view_access=view, download_access=download)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_account_domains_and_registration_are_independent(self):
        self.assertEqual(self.client.get("/api/v1/catalog/papers").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/mini/me").status_code, 401)
        self.client.cookies.clear()
        wrong = self.client.post("/api/v1/mini/login-password", json={"username": self.author.username, "password": "author-password"})
        self.assertEqual(wrong.status_code, 401)
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        for path in ("/api/v1/library/papers", "/api/v1/library/folders", "/api/v1/library/summary"):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.client.cookies.clear()
        self.client.headers.clear()
        with patch.object(get_settings(), "registration_enabled", False):
            result = self.client.post("/api/v1/mini/register", json={"username": "independent", "password": "test-password"})
        self.assertEqual(result.status_code, 201, result.text)
        self.assertFalse(result.json()["user"]["is_vip"])
        self.assertNotIn("set-cookie", result.headers)
        self.assertEqual(self.client.post("/api/v1/mini/register", json={"username": "upgrade", "password": "test-password", "membership": "vip"}).status_code, 422)
        with patch.object(get_settings(), "mini_registration_enabled", False):
            self.assertEqual(self.client.post("/api/v1/mini/register", json={"username": "closed", "password": "test-password"}).status_code, 403)

    def test_consumers_edit_their_own_nickname_and_avatar(self):
        self.sign_in(self.viewer)
        changed = self.client.patch("/api/v1/mini/me", json={"nickname": "向阳的小海豚", "avatar": "fox"})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["nickname"], "向阳的小海豚")
        self.assertEqual(changed.json()["username"], self.viewer.username)
        self.assertEqual(changed.json()["avatar"], "fox")
        only_avatar = self.client.patch("/api/v1/mini/me", json={"avatar": "panda"})
        self.assertEqual(only_avatar.json()["nickname"], "向阳的小海豚")
        self.assertEqual(self.client.patch("/api/v1/mini/me", json={"avatar": "panda"}).status_code, 200)
        # Display names can repeat, and the legacy username field changes only the display name.
        self.assertEqual(self.client.patch("/api/v1/mini/me", json={"username": self.other.username}).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/mini/me").json()["username"], self.viewer.username)
        for payload in ({"nickname": " "}, {"nickname": "bad\nname"}, {"nickname": "长" * 33}, {"avatar": "dragon"}, {}):
            self.assertEqual(self.client.patch("/api/v1/mini/me", json=payload).status_code, 422, payload)
        self.assertEqual(self.client.patch("/api/v1/mini/me", json={"nickname": "测试昵称", "membership": "vip"}).status_code, 422)

    def test_profile_edits_are_scoped_to_the_signed_in_account(self):
        self.sign_in(self.viewer)
        self.assertEqual(self.client.patch("/api/v1/mini/me", json={"avatar": "koala"}).status_code, 200)
        self.client.cookies.clear()
        self.client.headers.pop("Authorization", None)
        self.assertEqual(self.client.patch("/api/v1/mini/me", json={"avatar": "owl"}).status_code, 401)
        # 换第二个账号登录：看不到、也改不了别人的头像
        self.sign_in(self.other)
        self.assertEqual(self.client.get("/api/v1/mini/me").json()["avatar"], "")
        self.assertEqual(self.client.patch("/api/v1/mini/me", json={"avatar": "owl"}).json()["avatar"], "owl")
        self.client.cookies.clear()
        self.client.headers["Authorization"] = "Bearer " + mini_auth.login_password(self.viewer.username, "test-password")["token"]
        self.assertEqual(self.client.get("/api/v1/mini/me").json()["avatar"], "koala")

    def test_password_change_requires_the_current_one_and_revokes_other_sessions(self):
        self.sign_in(self.viewer)
        # viewer 是用账号密码注册的：必须带对当前密码
        self.assertTrue(self.client.get("/api/v1/mini/me").json()["has_password"])
        self.assertEqual(self.client.post("/api/v1/mini/password", json={"new_password": "next-password"}).status_code, 400)
        wrong = self.client.post("/api/v1/mini/password", json={"current_password": "nope", "new_password": "next-password"})
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(wrong.json()["detail"]["code"], "password_mismatch")
        self.assertEqual(self.client.post("/api/v1/mini/password", json={"current_password": "test-password", "new_password": "test-password"}).status_code, 400)
        self.assertEqual(self.client.post("/api/v1/mini/password", json={"current_password": "test-password", "new_password": "short"}).status_code, 422)
        # 另开一个会话，改密后它应被踢下线，而发起改密的这个会话保留
        stale = mini_auth.login_password(self.viewer.username, "test-password")["token"]
        changed = self.client.post("/api/v1/mini/password", json={"current_password": "test-password", "new_password": "next-password"})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.client.get("/api/v1/mini/me").status_code, 200)
        self.client.headers["Authorization"] = "Bearer " + stale
        self.assertEqual(self.client.get("/api/v1/mini/me").status_code, 401)
        # 老密码失效、新密码可登录
        self.assertEqual(self.client.post("/api/v1/mini/login-password", json={"username": self.viewer.username, "password": "test-password"}).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/mini/login-password", json={"username": self.viewer.username, "password": "next-password"}).status_code, 200)

    def test_wechat_accounts_can_set_a_password_and_keep_their_nickname(self):
        self.client.cookies.clear()
        with patch.object(mini_auth, "exchange_code", new=AsyncMock(return_value="wx-openid-edit")):
            result = self.client.post("/api/v1/mini/login", json={"code": "wx-code"}).json()
        token = result["token"]
        self.client.headers["Authorization"] = "Bearer " + token
        self.assertFalse(result["user"]["has_password"])
        # 微信账号还没有密码：不带 current_password 直接设置
        self.assertEqual(self.client.post("/api/v1/mini/password", json={"current_password": "乱填", "new_password": "reader-password"}).status_code, 400)
        self.assertEqual(self.client.post("/api/v1/mini/password", json={"new_password": "reader-password"}).status_code, 200)
        self.assertTrue(self.client.get("/api/v1/mini/me").json()["has_password"])
        # 设置密码后昵称（微信注册时的默认昵称）没有被改动
        username = self.client.get("/api/v1/mini/me").json()["username"]
        self.assertTrue(username)
        self.assertEqual(self.client.patch("/api/v1/mini/me", json={"nickname": "小读者"}).json()["nickname"], "小读者")
        self.assertEqual(self.client.post("/api/v1/mini/login-password", json={"username": username, "password": "reader-password"}).status_code, 200)
        # 设置密码不会把微信登录这条链路顶掉
        with patch.object(mini_auth, "exchange_code", new=AsyncMock(return_value="wx-openid-edit")):
            self.assertEqual(self.client.post("/api/v1/mini/login", json={"code": "wx-code"}).status_code, 200)

    def test_disabled_accounts_cannot_edit_profile_or_password(self):
        token = mini_auth.login_password(self.viewer.username, "test-password")["token"]
        self.membership(self.viewer, level="regular", active=False)
        self.client.headers["Authorization"] = "Bearer " + token
        self.assertEqual(self.client.get("/api/v1/mini/me").status_code, 401)
        # 就算有人握着某个还没过期的会话，服务层也会在改动落库前拦下
        with self.assertRaises(HTTPException) as profile:
            mini_auth.update_profile(self.viewer.id, MiniProfileUpdate(avatar="fox"))
        self.assertEqual(profile.exception.status_code, 403)
        with self.assertRaises(HTTPException) as password:
            mini_auth.update_password(self.viewer.id, MiniPasswordUpdate(new_password="next-password"))
        self.assertEqual(password.exception.status_code, 403)
        self.assertEqual(mini_auth.admin_user(self.viewer.id)["avatar"], "")

    def test_regular_users_cannot_fetch_vip_snapshots_thumbnails_or_direct_assets(self):
        item = self.restricted()
        self.sign_in(self.viewer)
        path = f"/api/v1/catalog/papers/{item['id']}"
        result = self.client.get(path).json()
        self.assertFalse(result["can_view"])
        self.assertIsNone(result["snapshot"])
        self.assertEqual(result["assets"], [])
        self.assertIsNone(result["thumbnail_url"])
        self.assertIsNone(self.client.get("/api/v1/catalog/papers").json()["items"][0]["thumbnail_id"])
        for asset in item["assets"]:
            response = self.client.get(asset["url"].replace("/admin/catalog/", "/catalog/"))
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(response.json()["detail"]["code"], "vip_required")
        self.assertEqual(self.client.post(path + "/download").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/catalog/summary").json()["downloads"], 0)
        self.assertEqual(self.client.put(path + "/favorite", json={"favorite": True}).status_code, 200)
        self.assertFalse(self.client.get("/api/v1/catalog/papers?favorite=true").json()["items"][0]["can_view"])

    def test_free_preview_can_require_vip_for_download(self):
        item = self.restricted(view="free")
        self.sign_in(self.viewer)
        result = self.client.get(f"/api/v1/catalog/papers/{item['id']}").json()
        self.assertTrue(result["can_view"])
        self.assertFalse(result["can_download"])
        self.assertTrue(result["snapshot"])
        self.assertEqual({asset["kind"] for asset in result["assets"]}, {"page"})
        self.assertEqual(self.client.get(result["assets"][0]["url"]).status_code, 200)
        pdf = next(asset for asset in item["assets"] if asset["kind"] == "pdf")
        self.assertEqual(self.client.get(pdf["url"].replace("/admin/catalog/", "/catalog/")).status_code, 403)

    def test_membership_expiry_revocation_and_reenable_are_checked_on_every_file_request(self):
        item = self.restricted()
        self.membership(self.viewer, expires=int(time.time()) + 3600)
        self.sign_in(self.viewer)
        path = f"/api/v1/catalog/papers/{item['id']}"
        result = self.client.get(path).json()
        self.assertTrue(result["can_view"])
        for asset in result["assets"]:
            self.assertEqual(self.client.get(asset["url"]).status_code, 200)
        self.assertEqual(self.client.post(path + "/download").status_code, 200)
        self.membership(self.viewer, expires=int(time.time()) - 1)
        self.assertEqual(self.client.get("/api/v1/mini/me").json()["membership_status"], "expired")
        self.assertFalse(self.client.get(path).json()["can_view"])
        for asset in result["assets"]:
            self.assertEqual(self.client.get(asset["url"]).status_code, 403)
        self.assertFalse(self.client.get("/api/v1/catalog/papers?downloaded=true").json()["items"][0]["can_download"])
        self.membership(self.viewer)
        self.assertTrue(self.client.get(path).json()["can_download"])
        self.membership(self.viewer, level="regular")
        self.assertEqual(self.client.post(path + "/download").status_code, 403)
        self.membership(self.viewer, active=False)
        self.assertEqual(self.client.get("/api/v1/mini/me").status_code, 401)
        self.membership(self.viewer, active=True)
        self.assertEqual(self.client.get("/api/v1/mini/me").status_code, 401)
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_membership_events WHERE user_id = ?", (self.viewer.id,)).fetchone()[0], 6)

    def test_type_rules_apply_to_existing_content_and_overrides_are_explicit(self):
        item = self.publish()
        rules = self.client.get("/api/v1/admin/catalog/type-rules").json()["items"]
        rule = next(row for row in rules if row["question_type"] == "quiz")
        url = "/api/v1/admin/catalog/type-rules/quiz"
        body = {"revision": rule["revision"], "view_access": "vip", "download_access": "vip"}
        changed = self.client.put(url, json=body)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.client.put(url, json=body).status_code, 409)
        self.sign_in(self.viewer)
        self.assertFalse(self.client.get(f"/api/v1/catalog/papers/{item['id']}").json()["can_view"])
        self.sign_in(self.admin)
        self.assertEqual(self.update(item, view_access="free", download_access="free").status_code, 200)
        self.sign_in(self.viewer)
        self.assertTrue(self.client.get(f"/api/v1/catalog/papers/{item['id']}").json()["can_download"])
        self.assertEqual(self.client.put(url, json=body).status_code, 401)

    def test_mixed_question_types_use_strictest_rule_and_inherited_view_protects_pdf(self):
        value = snapshot()
        value["paper"]["sections"].append({**copy.deepcopy(value["paper"]["sections"][0]), "type": "reading"})
        source = paper_library.create_paper(self.admin.id, ArchiveCreate(request_id="mixed-request", source_id="mixed-source", snapshot=value))
        source = paper_library.publish_bundle(self.admin.id, source["id"], bundle())
        item = self.publish(self.draft(source))
        self.assertEqual(self.client.put("/api/v1/admin/catalog/type-rules/reading", json={"revision": 0, "view_access": "vip", "download_access": "vip"}).status_code, 200)
        response = self.update(item, view_access="inherit", download_access="free")
        self.assertEqual(response.json()["required_download"], "vip")
        self.sign_in(self.viewer)
        detail = self.client.get(f"/api/v1/catalog/papers/{item['id']}").json()
        self.assertFalse(detail["can_view"])
        self.assertFalse(detail["can_download"])
        self.assertEqual(set(detail["question_types"]), {"quiz", "reading"})

    def test_admin_membership_crud_filters_conflicts_and_privilege_boundaries(self):
        path = f"/api/v1/admin/mini-users/{self.viewer.id}"
        body = {"revision": 1, "membership": "vip", "vip_expires_at": None, "is_active": True}
        result = self.client.put(path, json=body)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.client.put(path, json=body).status_code, 409)
        self.assertEqual(self.client.get("/api/v1/admin/mini-users?membership=vip").json()["total"], 1)
        self.assertEqual(self.client.get("/api/v1/admin/mini-users?membership=regular").json()["total"], 1)
        self.assertEqual(self.client.get("/api/v1/admin/mini-users?q=%25").json()["total"], 0)
        created = self.client.post("/api/v1/admin/mini-users", json={"username": "staff-created", "password": "test-password"})
        self.assertEqual(created.status_code, 201)
        self.assertNotIn("token", created.json())
        self.assertFalse(created.json()["is_vip"])
        self.sign_in(self.viewer)
        self.assertEqual(self.client.put(path, json={**body, "revision": 2}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/admin/mini-users").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/mini/me", headers={"X-Mini-User": self.other.id}).status_code, 409)

    def test_admin_edits_consumer_profile_and_resets_password(self):
        """后台能改小程序用户的昵称/头像，也能代用户重置密码。"""
        path = f"/api/v1/admin/mini-users/{self.viewer.id}"
        changed = self.client.patch(path, json={"revision": 1, "username": "后台改的名", "avatar": "owl"})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual((changed.json()["nickname"], changed.json()["avatar"]), ("后台改的名", "owl"))
        self.assertEqual(changed.json()["revision"], 2)
        # 乐观锁：拿着旧 revision 再提交会被挡住
        self.assertEqual(self.client.patch(path, json={"revision": 1, "username": "又一次改名"}).status_code, 409)
        # 登录账号不随昵称改变；头像必须在预设键表里；必须真的改了东西
        self.assertEqual(changed.json()["username"], self.viewer.username)
        self.assertEqual(self.client.patch(path, json={"revision": 2, "avatar": "dragon"}).status_code, 422)
        self.assertEqual(self.client.patch(path, json={"revision": 2}).status_code, 422)
        self.assertEqual(self.client.patch(path, json={"revision": 2, "new_password": "123"}).status_code, 422)
        self.assertEqual(self.client.patch("/api/v1/admin/mini-users/missing-account", json={"revision": 1, "avatar": "owl"}).status_code, 404)

        # 后台改名不该动用户自己的登录态，重置密码才让旧会话与旧密码一起失效
        token = mini_auth.login_password(self.viewer.username, "test-password")["token"]
        self.assertEqual(self.client.get("/api/v1/mini/me", headers={"Authorization": "Bearer " + token}).status_code, 200)
        reset = self.client.patch(path, json={"revision": 2, "new_password": "new-password"})
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertTrue(reset.json()["has_password"])
        with database.db() as conn:
            records = [json.loads(row[0]) for row in conn.execute(
                "SELECT after_json FROM mini_membership_events WHERE user_id = ?", (self.viewer.id,))]
        self.assertTrue(any(item.get("password_reset") for item in records))
        self.assertNotIn("new-password", json.dumps(records))
        self.assertEqual(self.client.get("/api/v1/mini/me", headers={"Authorization": "Bearer " + token}).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/mini/login-password",
                                          json={"username": self.viewer.username, "password": "test-password"}).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/mini/login-password",
                                          json={"username": self.viewer.username, "password": "new-password"}).status_code, 200)

        # 普通小程序用户拿着自己的 token 打不动后台接口
        self.sign_in(self.other)
        self.assertEqual(self.client.patch(path, json={"revision": 3, "username": "越权改名"}).status_code, 401)
        self.assertEqual(self.client.delete(path).status_code, 401)

    def test_admin_deletes_consumer_account_and_cleans_related_rows(self):
        """删除小程序账号：会话、收藏、下载记录、操作留痕一并清掉，不可恢复。"""
        item = self.publish()
        detail = f"/api/v1/catalog/papers/{item['id']}"
        target = f"/api/v1/admin/mini-users/{self.viewer.id}"
        self.assertEqual(self.client.put(target, json={"revision": 1, "membership": "vip",
                                                       "vip_expires_at": None, "is_active": True}).status_code, 200)
        self.sign_in(self.viewer)
        self.client.put(detail + "/favorite", json={"favorite": True})
        self.client.post(detail + "/download")
        token = self.client.headers["Authorization"].split(" ", 1)[1]

        self.sign_in(self.admin)
        listed = self.client.get("/api/v1/admin/mini-users", params={"q": self.viewer.username}).json()
        self.assertEqual(listed["total"], 1)
        removed = self.client.delete(target)
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json()["username"], self.viewer.username)
        self.assertGreaterEqual(removed.json()["removed"]["mini_user_sessions"], 1)
        self.assertEqual(removed.json()["removed"]["mini_catalog_favorites"], 1)
        self.assertEqual(removed.json()["removed"]["mini_catalog_downloads"], 1)
        self.assertEqual(removed.json()["removed"]["mini_membership_events"], 1)

        # 五张表里都不该再有这个账号的任何痕迹，其它账号不受影响
        with database.db() as conn:
            for table in ("mini_users", "mini_user_sessions", "mini_catalog_favorites", "mini_catalog_downloads",
                          "mini_membership_events"):
                key = "id" if table == "mini_users" else "user_id"
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {key} = ?", (self.viewer.id,)).fetchone()[0], 0)
        self.assertEqual(self.client.get("/api/v1/admin/mini-users", params={"q": self.viewer.username}).json()["total"], 0)
        self.assertEqual(self.client.get("/api/v1/admin/mini-users", params={"q": self.other.username}).json()["total"], 1)
        self.assertEqual(self.client.get("/api/v1/mini/me", headers={"Authorization": "Bearer " + token}).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/mini/login-password",
                                          json={"username": self.viewer.username, "password": "test-password"}).status_code, 401)
        self.assertEqual(self.client.delete(target).status_code, 404)
        # 同名账号可以重新注册，说明 UNIQUE 约束没有留下残影
        self.assertEqual(self.client.post("/api/v1/admin/mini-users",
                                          json={"username": self.viewer.username, "password": "test-password"}).status_code, 201)

    def test_invalid_access_policies_and_consumer_elevation_are_rejected(self):
        item = self.publish()
        self.assertEqual(self.update(item, view_access="vip", download_access="free").status_code, 422)
        self.assertEqual(self.update(item, view_access="unknown").status_code, 422)
        self.assertEqual(self.client.put("/api/v1/admin/catalog/type-rules/quiz", json={"revision": 0, "view_access": "vip", "download_access": "free"}).status_code, 422)

    def test_metadata_edits_without_policy_fields_preserve_existing_vip_restrictions(self):
        item = self.restricted()
        result = self.update(item, title="更新后的标题")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual((result.json()["view_access"], result.json()["required_download"]), ("vip", "vip"))
        rejected = self.update(result.json(), download_access="free")
        self.assertEqual(rejected.status_code, 422)


    def test_console_accounts_split_into_authors_and_administrators(self):
        """后台「出题用户」与「管理员账号」两页按 role 取数，概览统计口径与之一致。"""
        second_admin = user_store.create_user("second-admin", "test-password", role="admin")
        everything = self.client.get("/api/v1/admin/users").json()["users"]
        authors = self.client.get("/api/v1/admin/users", params={"role": "user"}).json()["users"]
        admins = self.client.get("/api/v1/admin/users", params={"role": "admin"}).json()["users"]
        self.assertEqual({row["id"] for row in authors} | {row["id"] for row in admins}, {row["id"] for row in everything})
        self.assertTrue(all(row["role"] == "user" for row in authors))
        self.assertTrue(all(row["role"] == "admin" for row in admins))
        self.assertIn(second_admin.id, {row["id"] for row in admins})
        self.assertNotIn(second_admin.id, {row["id"] for row in authors})
        self.assertEqual(self.client.get("/api/v1/admin/users", params={"role": "super"}).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/admin/users", params={"role": "admin", "query": "second"}).json()["users"][0]["id"], second_admin.id)

        stats = self.client.get("/api/v1/admin/stats").json()
        self.assertEqual(stats["users"], len(authors))
        self.assertEqual(stats["admins"], len(admins))

        promoted = self.client.put(f"/api/v1/admin/users/{self.author.id}", json={"role": "admin"})
        self.assertEqual(promoted.status_code, 200, promoted.text)
        self.assertIn(self.author.id, {row["id"] for row in self.client.get("/api/v1/admin/users", params={"role": "admin"}).json()["users"]})
        self.assertNotIn(self.author.id, {row["id"] for row in self.client.get("/api/v1/admin/users", params={"role": "user"}).json()["users"]})
        self.assertEqual(self.client.get("/api/v1/admin/stats").json()["users"], len(authors) - 1)


if __name__ == "__main__":
    unittest.main()
