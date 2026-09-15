"""Library and mini-program contracts. Disposable DB/files, no real WeChat or COS."""

import asyncio
import copy
import io
import json
import os
import tempfile
import time
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.update({"DATABASE_URL": "", "SECRET_KEY": "library-tests-disposable-secret-no-production",
                   "LLM_API_KEY": "", "ADMIN_USERNAME": "", "ADMIN_PASSWORD": ""})

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app import db as database, security
from app.config import get_settings
from app.deps import SESSION_COOKIE
from app.models.library import ArchiveCreate
from app.routers import auth, generate, library, mini
from app.services import mini_auth, paper_library, user_store
from app.services.paper_storage import LocalStorage, storage_for


def snapshot():
    return {
        "schema_version": 1,
        "paper": {"grade": "小学三年级", "subject": "数学", "keyword": "加减法", "title": "单元练习", "difficulty": "medium", "day": 2,
                  "titleHtml": "<b>单元练习</b>", "hiddenElements": ["reward"], "footerOverride": "保留页脚",
                  "sections": [{"type": "quiz", "name": "选择题", "layout": {"qCols": 2, "optCols": 2, "showNo": True, "tableBorder": "none", "fontSize": ""},
                                "data": {"questions": [{"stem": "12 + 8 = ?", "_stemHtml": "<b>12 + 8</b> = ?", "type": "multiple_choice",
                                                         "options": ["19", "20"], "answer": 1, "analysis": "相加。"}]}}]},
        "template": {"id": "exam", "name": "标准", "tag": "考试", "showInfoRow": True, "showNotice": True, "showScore": True,
                     "titlePrefix": "", "titleSuffix": "测试卷", "footer": "卷终", "headerExtra": ""},
        "style": {"bg": "none", "bgOpacity": 70, "banner": False, "secColor": False, "frame": "none", "encourage": False,
                  "reward": False, "kidFont": "off", "exportBg": False, "titleScale": 1, "titleOffsetY": 0},
        "export_options": {"mode": "student", "addDay": True, "renderer_version": "web-v1"},
    }


def bundle(names=None):
    image = io.BytesIO()
    Image.new("RGB", (210, 297), "white").save(image, "JPEG")
    values = names or {"paper.pdf": b"%PDF-1.4\nfixture-only\n%%EOF\n", "page-1.jpg": image.getvalue()}
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, value in values.items():
            archive.writestr(name, value)
    return data.getvalue()


class PaperLibraryContracts(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="lc-library-test-")))
        self.stack.enter_context(patch.object(database, "DB_PATH", self.root / "users.db"))
        for field, value in {"database_url": "", "archive_storage": "local", "archive_local_dir": str(self.root / "private"),
                             "archive_max_papers": 1000, "archive_storage_mb": 512, "archive_max_bundle_mb": 40,
                             "wechat_app_id": "", "wechat_app_secret": "", "mini_registration_enabled": True}.items():
            self.stack.enter_context(patch.object(get_settings(), field, value))
        self.stack.enter_context(patch.object(httpx.AsyncClient, "get", side_effect=AssertionError("External requests disabled")))
        self.stack.enter_context(patch.object(mini, "allow", return_value=True))
        database.init_db()
        self.user = user_store.create_user("library-one", "test-password")
        self.other = user_store.create_user("library-two", "test-password")
        app = FastAPI()
        for router in (auth.router, library.router, mini.router, generate.router):
            app.include_router(router)
        self.client = self.stack.enter_context(TestClient(app))
        self.client.cookies.set(SESSION_COOKIE, security.create_token(self.user.id))
        self.body = {"request_id": "request-one", "source_id": "source-paper-one", "snapshot": snapshot()}

    def create(self, body=None):
        response = self.client.post("/api/v1/library/papers", json=body or self.body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def upload(self, paper_id, content=None):
        return self.client.put(f"/api/v1/library/papers/{paper_id}/files", content=content or bundle(), headers={"Content-Type": "application/zip"})

    def authenticate_phone(self):
        return mini_auth.login_public_identity("fixture-identity")["token"]

    def test_additive_schema_is_idempotent(self):
        paper = self.create()
        database.init_db()
        self.assertEqual(self.client.get(f"/api/v1/library/papers/{paper['id']}").status_code, 200)

    def test_snapshot_preserves_all_export_context(self):
        saved = self.create()
        self.assertEqual(saved["snapshot"], self.body["snapshot"])
        self.assertEqual(saved["file_status"], "pending")
        self.assertEqual(saved["version"], 1)
        self.assertIsNone(saved["thumbnail_url"])

    def test_duplicate_replay_and_content_deduplication(self):
        first = self.create()
        self.assertEqual(self.create()["id"], first["id"])
        self.body["request_id"] = "request-two"
        self.assertEqual(self.create()["id"], first["id"])
        self.assertEqual(self.client.get("/api/v1/library/papers").json()["total"], 1)

    def test_new_versions_do_not_mutate_old_snapshots(self):
        original = self.create()
        changed = copy.deepcopy(self.body)
        changed["snapshot"]["paper"]["title"] = "第二版"
        self.assertEqual(self.client.post("/api/v1/library/papers", json=changed).status_code, 409)
        changed["request_id"] = "request-two"
        current = self.create(changed)
        self.assertEqual(current["version"], 2)
        old = self.client.get(f"/api/v1/library/papers/{original['id']}").json()
        self.assertEqual(old["snapshot"]["paper"]["title"], "单元练习")
        self.client.delete(f"/api/v1/library/papers/{current['id']}")
        changed["request_id"] = "request-three"
        self.assertEqual(self.create(changed)["version"], 3)

    def test_incomplete_snapshot_and_readonly_updates_rejected(self):
        del self.body["snapshot"]["style"]["exportBg"]
        self.assertEqual(self.client.post("/api/v1/library/papers", json=self.body).status_code, 422)
        self.body["snapshot"] = snapshot()
        paper = self.create()
        response = self.client.patch(f"/api/v1/library/papers/{paper['id']}", json={"snapshot": snapshot()})
        self.assertEqual(response.status_code, 422)

    def test_non_finite_snapshot_values_return_validation_errors(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                self.body["snapshot"]["style"]["titleScale"] = value
                response = self.client.post("/api/v1/library/papers", content=json.dumps(self.body),
                                            headers={"Content-Type": "application/json"})
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get("/api/v1/library/papers").json()["total"], 0)

    def test_consumer_cannot_mutate_private_metadata_even_with_workbench_headers(self):
        paper = self.create()
        folder = self.client.post("/api/v1/library/folders", json={"name": "数学"}).json()
        token = self.authenticate_phone()
        self.client.cookies.clear()
        headers = {"Authorization": "Bearer " + token, "X-Workspace-User": str(self.user.id)}
        renamed = self.client.put(f"/api/v1/library/folders/{folder['id']}", json={"name": "单元复习"}, headers=headers)
        self.assertEqual(renamed.status_code, 403, renamed.text)
        changed = self.client.put(f"/api/v1/library/papers/{paper['id']}",
                                  json={"title": "手机重命名", "favorite": True, "folder_id": folder["id"]}, headers=headers)
        self.assertEqual(changed.status_code, 403, changed.text)
        moved = self.client.put(f"/api/v1/library/papers/{paper['id']}", json={"folder_id": None}, headers=headers)
        self.assertEqual(moved.status_code, 403)
        headers["X-Workspace-User"] = str(self.other.id)
        self.assertEqual(self.client.put(f"/api/v1/library/papers/{paper['id']}", json={"favorite": False}, headers=headers).status_code, 403)
        self.client.cookies.set(SESSION_COOKIE, security.create_token(self.user.id))
        self.assertEqual(self.client.put(f"/api/v1/library/papers/{paper['id']}", json={"favorite": True}, headers=headers).status_code, 403)
        self.assertEqual(self.client.get(f"/api/v1/library/papers/{paper['id']}").json()["snapshot"], paper["snapshot"])

    def test_no_auth_or_cross_user_access(self):
        paper = self.create()
        ready = self.upload(paper["id"]).json()
        self.client.cookies.set(SESSION_COOKIE, security.create_token(self.other.id))
        self.assertEqual(self.client.get(f"/api/v1/library/papers/{paper['id']}").status_code, 404)
        self.assertEqual(self.upload(paper["id"]).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/v1/library/papers/{paper['id']}", json={"favorite": True}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/library/papers/{paper['id']}").status_code, 404)
        self.assertEqual(self.client.get(ready["assets"][0]["url"]).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/library/papers").json()["total"], 0)
        self.client.cookies.clear()
        self.assertEqual(self.client.get(ready["assets"][0]["url"]).status_code, 401)

    def test_folder_ownership_and_delete_preserves_papers(self):
        folder = self.client.post("/api/v1/library/folders", json={"name": "数学"}).json()
        self.body["folder_id"] = folder["id"]
        paper = self.create()
        self.client.cookies.set(SESSION_COOKIE, security.create_token(self.other.id))
        self.assertEqual(self.client.post("/api/v1/library/papers", json=self.body).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/v1/library/folders/{folder['id']}", json={"name": " чужой "}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/library/folders/{folder['id']}").status_code, 404)
        self.client.cookies.set(SESSION_COOKIE, security.create_token(self.user.id))
        self.assertEqual(self.client.delete(f"/api/v1/library/folders/{folder['id']}").status_code, 204)
        self.assertIsNone(self.client.get(f"/api/v1/library/papers/{paper['id']}").json()["folder_id"])

    def test_favorites_filters_rename_and_pagination(self):
        first = self.create()
        self.body.update(request_id="request-two", source_id="source-paper-two")
        self.body["snapshot"]["paper"].update(title="100% 巩固练习", subject="语文")
        second = self.create()
        self.client.patch(f"/api/v1/library/papers/{first['id']}", json={"favorite": True, "title": "收藏练习"})
        self.assertEqual(self.client.get("/api/v1/library/papers?favorite=true").json()["items"][0]["id"], first["id"])
        self.assertEqual(self.client.get("/api/v1/library/papers", params={"q": "%"}).json()["total"], 1)
        self.assertEqual(self.client.get("/api/v1/library/papers", params={"subject": "语文"}).json()["items"][0]["id"], second["id"])
        self.assertTrue(self.client.get("/api/v1/library/papers?limit=1").json()["has_more"])
        self.assertFalse(self.client.get("/api/v1/library/papers?limit=1&offset=1").json()["has_more"])
        summary = self.client.get("/api/v1/library/summary").json()
        self.assertEqual((summary["papers"], summary["favorites"], summary["unfiled"]), (2, 1, 2))
        self.assertEqual(self.client.get(f"/api/v1/library/papers/{first['id']}").json()["snapshot"]["paper"]["title"], "单元练习")

    def test_archive_and_folder_limits(self):
        get_settings().archive_max_papers = 1
        self.create()
        self.body.update(request_id="request-two", source_id="source-paper-two")
        self.assertEqual(self.client.post("/api/v1/library/papers", json=self.body).status_code, 409)
        self.assertEqual(self.client.post("/api/v1/library/folders", json={"name": "  "}).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/library/folders", json={"name": "数学"}).status_code, 201)
        self.assertEqual(self.client.post("/api/v1/library/folders", json={"name": "数学"}).status_code, 409)

    def test_valid_bundle_ready_and_private_assets(self):
        paper = self.create()
        response = self.upload(paper["id"])
        self.assertEqual(response.status_code, 200, response.text)
        ready = response.json()
        self.assertEqual((ready["file_status"], ready["page_count"], len(ready["assets"])), ("ready", 1, 2))
        for asset in ready["assets"]:
            downloaded = self.client.get(asset["url"])
            self.assertEqual(downloaded.status_code, 200)
            self.assertEqual(downloaded.headers["cache-control"], "private, no-store")
            self.assertEqual(len(downloaded.content), asset["byte_size"])
        self.assertIn("attachment", self.client.get(ready["assets"][0]["url"]).headers["content-disposition"])
        self.assertGreater(self.client.get("/api/v1/library/summary").json()["storage_bytes"], 0)

    def test_completed_files_are_never_replaced(self):
        paper = self.create()
        first = self.upload(paper["id"]).json()
        second = self.upload(paper["id"], b"retry-with-different-content").json()
        self.assertEqual(first["assets"], second["assets"])

    def test_failed_upload_has_no_partial_manifest_and_can_retry(self):
        paper = self.create()
        original_put = LocalStorage.put
        calls = 0

        def flaky(store, *args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("fixture storage offline")
            return original_put(store, *args)

        with patch.object(LocalStorage, "put", flaky):
            self.assertEqual(self.upload(paper["id"]).status_code, 503)
        failed = self.client.get(f"/api/v1/library/papers/{paper['id']}").json()
        self.assertEqual((failed["file_status"], failed["assets"]), ("failed", []))
        self.assertEqual(failed["snapshot"], self.body["snapshot"])
        self.assertEqual(list((self.root / "private").rglob("*.pdf")), [])
        self.assertEqual(self.upload(paper["id"]).json()["file_status"], "ready")

    def test_upload_lease_and_storage_quota(self):
        paper = self.create()
        with database.db() as conn:
            conn.execute("UPDATE paper_archives SET file_status = 'uploading', upload_started_at = ? WHERE id = ?", (int(time.time()), paper["id"]))
        self.assertEqual(self.upload(paper["id"]).status_code, 409)
        with database.db() as conn:
            conn.execute("UPDATE paper_archives SET upload_started_at = 0 WHERE id = ?", (paper["id"],))
        get_settings().archive_storage_mb = 0
        self.assertEqual(self.upload(paper["id"]).status_code, 409)
        get_settings().archive_storage_mb = 512
        self.assertEqual(self.upload(paper["id"]).status_code, 200)

    def test_bad_zip_traversal_missing_pages_and_image_rejected(self):
        paper = self.create()
        for content in (b"bad zip", bundle({"../paper.pdf": b"x", "page-1.jpg": b"x"}),
                        bundle({"paper.pdf": b"%PDF-1.4\n%%EOF", "page-2.jpg": b"x"}),
                        bundle({"paper.pdf": b"%PDF-1.4\n%%EOF", "page-1.jpg": b"<script>bad</script>"})):
            self.assertEqual(self.upload(paper["id"], content).status_code, 422)
        self.assertFalse((self.root / "private").exists())

    def test_body_size_limit_and_content_type(self):
        get_settings().archive_max_bundle_mb = 1
        paper = self.create()
        self.assertEqual(self.upload(paper["id"], b"x" * (1024 * 1024 + 1)).status_code, 413)
        self.assertEqual(self.client.put(f"/api/v1/library/papers/{paper['id']}/files", content=b"bad").status_code, 415)

    def test_delete_removes_assets(self):
        paper = self.create()
        ready = self.upload(paper["id"]).json()
        self.assertEqual(self.client.delete(f"/api/v1/library/papers/{paper['id']}").status_code, 204)
        self.assertEqual(self.client.get(ready["assets"][0]["url"]).status_code, 404)
        self.assertEqual(list((self.root / "private").rglob("*.jpg")), [])

    def test_cos_never_falls_back_to_local_when_unconfigured(self):
        get_settings().archive_storage = "cos"
        with self.assertRaises(Exception):
            storage_for()
        with self.assertRaises(ValueError):
            LocalStorage().path("../../users.db")

    def test_concurrent_saves_deduplicate(self):
        request = ArchiveCreate.model_validate(self.body)
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: paper_library.create_paper(self.user.id, request), range(4)))
        self.assertEqual(len({value["id"] for value in results}), 1)

    def test_binding_endpoints_are_removed(self):
        for path in ("/api/v1/me/mini-bindings", "/api/v1/mini/bind/claim", "/api/v1/mini/bind/complete"):
            self.assertEqual(self.client.post(path, json={}).status_code, 404)

    def test_mini_token_is_scoped_and_revocable(self):
        paper = self.create()
        token = self.authenticate_phone()
        self.client.cookies.clear()
        self.client.headers["Authorization"] = "Bearer " + token
        self.assertNotEqual(self.client.get("/api/v1/mini/me").json()["id"], self.user.id)
        self.assertEqual(self.client.get(f"/api/v1/library/papers/{paper['id']}").status_code, 403)
        self.assertEqual(self.client.post("/api/v1/library/papers", json=self.body).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/me/mini-bindings").status_code, 404)
        self.assertEqual(self.client.post("/api/v1/mini/logout").status_code, 204)
        self.assertEqual(self.client.get("/api/v1/mini/me").status_code, 401)

    def test_legacy_bindings_never_reuse_workbench_users(self):
        with database.db() as conn:
            conn.execute("INSERT INTO mini_accounts(identity, user_id, created_at) VALUES (?, ?, ?)", ("fixture-identity", self.user.id, int(time.time())))
        result = mini_auth.login_public_identity("fixture-identity")
        self.assertNotEqual(result["user"]["id"], self.user.id)
        self.assertEqual(result["user"]["membership"], "regular")
        self.assertEqual(self.client.get("/api/v1/auth/me").json()["id"], self.user.id)

    def test_workbench_changes_do_not_change_consumer_accounts(self):
        token = self.authenticate_phone()
        member = mini_auth.resolve_session(token)
        with database.db() as conn:
            conn.execute("UPDATE users SET token_valid_after = ? WHERE id = ?", (int(time.time()) + 1, self.user.id))
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/v1/mini/me", headers={"Authorization": "Bearer " + token}).status_code, 200)
        with database.db() as conn:
            conn.execute("UPDATE users SET token_valid_after = 0, is_active = 0 WHERE id = ?", (self.user.id,))
        self.assertEqual(self.client.get("/api/v1/mini/me", headers={"Authorization": "Bearer " + token}).status_code, 200)
        with database.db() as conn:
            conn.execute("UPDATE mini_users SET is_active = 0 WHERE id = ?", (member.id,))
        self.assertEqual(self.client.get("/api/v1/mini/me", headers={"Authorization": "Bearer " + token}).status_code, 403)

    def test_expired_and_legacy_tokens_fail(self):
        token = self.authenticate_phone()
        with database.db() as conn:
            row = conn.execute("SELECT token_hash FROM mini_user_sessions").fetchone()
            self.assertNotEqual(row["token_hash"], token)
            conn.execute("UPDATE mini_user_sessions SET expires_at = 0")
        for value in (token, "lc_mini_legacy-token", "invalid"):
            self.assertEqual(self.client.get("/api/v1/mini/me", headers={"Authorization": "Bearer " + value}).status_code, 401)

    def test_wechat_login_requires_config_and_exchanges_code_server_side(self):
        self.assertEqual(self.client.post("/api/v1/mini/login", json={"code": "wx-code"}).status_code, 503)
        get_settings().wechat_app_id = "test-appid"
        get_settings().wechat_app_secret = "test-app-secret"
        response = httpx.Response(200, json={"openid": "fixture-openid", "session_key": "never-send-to-client"}, request=httpx.Request("GET", "https://api.weixin.qq.com"))
        with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=response)) as exchange:
            result = self.client.post("/api/v1/mini/login", json={"code": "wx-code"})
        self.assertEqual(result.json()["status"], "authenticated")
        self.assertNotIn("never-send-to-client", result.text)
        self.assertNotIn("fixture-openid", result.text)
        self.assertEqual(exchange.call_args.kwargs["params"]["js_code"], "wx-code")


if __name__ == "__main__":
    unittest.main()
