"""密码重置与登录签发的并发回归；数据库由 pg_support 创建和清理。"""

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_backend_reliability as reliability
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import security
from app.db import db
from app.deps import SESSION_COOKIE
from app.models.mini import MiniPasswordUpdate
from app.routers import auth
from app.services import mini_auth, user_store


class AuthRaceContracts(unittest.TestCase):
    setUp = reliability.BackendReliability.setUp

    def auth_client(self):
        app = FastAPI()
        app.include_router(auth.router)
        return TestClient(app)

    def test_mini_reset_rejects_already_verified_old_password(self):
        reader = mini_auth.register("race-reader", "old-password", admin=True)["user"]["id"]
        entered, release = threading.Event(), threading.Event()
        original = mini_auth.verify_password
        main_thread = threading.get_ident()

        def paused_verify(password, stored):
            matched = original(password, stored)
            if threading.get_ident() != main_thread and password == "old-password":
                entered.set()
                self.assertTrue(release.wait(5), "未释放旧密码校验线程")
            return matched

        with patch.object(mini_auth, "verify_password", side_effect=paused_verify), ThreadPoolExecutor(1) as pool:
            pending = pool.submit(mini_auth.login_password, "race-reader", "old-password")
            try:
                self.assertTrue(entered.wait(5), "旧密码校验未到达屏障")
                mini_auth.update_password(reader, MiniPasswordUpdate(current_password="old-password", new_password="new-password"))
            finally:
                release.set()
            with self.assertRaises(HTTPException) as caught:
                pending.result(timeout=5)
        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(caught.exception.detail["code"], "credentials_changed")
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_user_sessions WHERE user_id = ?", (reader,)).fetchone()[0], 0)
        current = mini_auth.login_password("race-reader", "new-password")
        self.assertEqual(mini_auth.resolve_session(current["token"]).id, reader)

    def test_workspace_reset_rejects_already_verified_old_password(self):
        entered, release = threading.Event(), threading.Event()
        original = user_store.verify_password

        def paused_verify(password, stored):
            matched = original(password, stored)
            if password == "test-password":
                entered.set()
                self.assertTrue(release.wait(5), "未释放旧密码校验线程")
            return matched

        with patch.object(security.time, "time", return_value=2000000000) as clock, patch.object(user_store, "verify_password", side_effect=paused_verify), self.auth_client() as client, ThreadPoolExecutor(1) as pool:
            pending = pool.submit(client.post, "/api/v1/auth/login", json={"username": self.user.username, "password": "test-password"})
            try:
                self.assertTrue(entered.wait(5), "旧密码校验未到达屏障")
                user_store.update_user(self.user.id, password="new-password")
                # 超过 cutoff 才签发也必须拒绝，不能只靠 JWT iat 挡住同秒请求。
                clock.return_value = 2000000002
            finally:
                release.set()
            response = pending.result(timeout=5)
            self.assertEqual(response.status_code, 401, response.text)
            self.assertEqual(response.json()["detail"]["code"], "credentials_changed")
            self.assertNotIn(SESSION_COOKIE, response.cookies)
            fresh = client.post("/api/v1/auth/login", json={"username": self.user.username, "password": "new-password"})
            self.assertEqual(fresh.status_code, 200, fresh.text)
            self.assertEqual(client.get("/api/v1/auth/me").status_code, 200)

    def assert_inserted_session_revoked_before_delayed_jwt(self, invalidate):
        entered, release = threading.Event(), threading.Event()
        original = auth.create_token
        inserted = {}

        def delayed_token(user_id, *args, **kwargs):
            # _set_session_cookie 已完成会话 INSERT 和 COMMIT，此处再暂停 JWT 签发。
            inserted["sid"] = kwargs["session_id"]
            entered.set()
            self.assertTrue(release.wait(5), "未释放 JWT 签发线程")
            return original(user_id, *args, **kwargs)

        with patch.object(security.time, "time", return_value=2000000000) as clock, patch.object(auth, "create_token", side_effect=delayed_token), self.auth_client() as client, ThreadPoolExecutor(1) as pool:
            pending = pool.submit(client.post, "/api/v1/auth/login", json={"username": self.user.username, "password": "test-password"})
            try:
                self.assertTrue(entered.wait(5), "JWT 签发未到达屏障")
                with db() as conn:
                    self.assertIsNotNone(conn.execute("SELECT id FROM workspace_sessions WHERE id = ?", (inserted["sid"],)).fetchone())
                invalidate()
                clock.return_value = 2000000002
            finally:
                release.set()
            response = pending.result(timeout=5)
            self.assertEqual(response.status_code, 200, response.text)
            token = security.parse_token(response.cookies[SESSION_COOKIE])
            cutoff = user_store.get_user_by_username(self.user.username)["token_valid_after"]
            self.assertGreaterEqual(token["iat"], cutoff)
            self.assertEqual(client.get("/api/v1/auth/me").status_code, 401)
        with db() as conn:
            self.assertIsNone(conn.execute("SELECT id FROM workspace_sessions WHERE id = ?", (inserted["sid"],)).fetchone())

    def test_password_reset_revokes_inserted_session_before_delayed_jwt(self):
        self.assert_inserted_session_revoked_before_delayed_jwt(lambda: user_store.update_user(self.user.id, password="new-password"))

    def test_emergency_seed_reset_revokes_inserted_session_before_delayed_jwt(self):
        self.assert_inserted_session_revoked_before_delayed_jwt(lambda: user_store.ensure_admin(self.user.username, "new-password", reset=True))

    def test_global_revoke_revokes_inserted_session_before_delayed_jwt(self):
        self.assert_inserted_session_revoked_before_delayed_jwt(lambda: user_store.revoke_sessions(self.user.id, 2000000001))

    def test_workspace_hash_upgrade_still_issues_usable_session(self):
        with patch.object(security, "_PBKDF2_ITER", 200):
            user = user_store.create_user("upgrade-workspace", "old-password")
        with self.auth_client() as client:
            response = client.post("/api/v1/auth/login", json={"username": user.username, "password": "old-password"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(client.get("/api/v1/auth/me").json()["id"], user.id)
        self.assertFalse(security.password_needs_upgrade(user_store.get_user_by_username(user.username)["password_hash"]))

    def test_mini_hash_upgrade_still_issues_usable_session(self):
        with patch.object(security, "_PBKDF2_ITER", 200):
            reader = mini_auth.register("upgrade-mini", "old-password", admin=True)["user"]["id"]
        response = mini_auth.login_password("upgrade-mini", "old-password")
        self.assertEqual(mini_auth.resolve_session(response["token"]).id, reader)
        with db() as conn:
            stored = conn.execute("SELECT password_hash FROM mini_users WHERE id = ?", (reader,)).fetchone()[0]
        self.assertFalse(security.password_needs_upgrade(stored))
