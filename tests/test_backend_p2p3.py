"""P2/P3 安全边界、资金正确性与锁准入回归；仅使用一次性测试库。"""

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_backend_reliability as reliability
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import db as database
from app.config import get_settings
from app.db import db
from app.db_admission import DatabaseBusy, admission
from app.provider_policy import require_new_key, validate_endpoint
from app.request_context import RequestContext
from app.services import membership_cards, mini_auth, user_store
from app.services.payment_admission import execute


class DataContracts(unittest.TestCase):
    setUp = reliability.BackendReliability.setUp

    def test_seed_does_not_reactivate_or_reset_existing_account(self):
        user_store.update_user(self.user.id, is_active=False)
        before = user_store.get_user_by_username(self.user.username)
        user_store.ensure_admin(self.user.username, "different-password")
        after = user_store.get_user_by_username(self.user.username)
        self.assertEqual(after["password_hash"], before["password_hash"])
        self.assertFalse(after["is_active"])
        self.assertEqual(after["role"], "user")
        user_store.ensure_admin(self.user.username, "different-password", reset=True)
        after = user_store.get_user_by_username(self.user.username)
        self.assertEqual(after["role"], "admin")
        self.assertTrue(after["is_active"])
        self.assertGreater(after["token_valid_after"], 0)

    def test_permanent_member_keeps_card_and_finite_member_can_redeem(self):
        reader = mini_auth.register("p2-reader", "test-password", admin=True)["user"]["id"]
        with db() as conn:
            conn.execute("UPDATE mini_users SET membership = 'vip', vip_expires_at = NULL WHERE id = ?", (reader,))
        code = membership_cards.create(self.user.id, 30, 1)["items"][0]["code"]
        with self.assertRaises(HTTPException):
            membership_cards.redeem(reader, code)
        self.assertEqual(membership_cards.listing()["items"][0]["status"], "active")
        with db() as conn:
            conn.execute("UPDATE mini_users SET membership = 'regular' WHERE id = ?", (reader,))
        result = membership_cards.redeem(reader, code)
        self.assertGreater(result["vip_expires_at"], 0)
        with self.assertRaises(HTTPException):
            membership_cards.redeem(reader, code)

    def test_current_schema_does_not_repeat_ddl(self):
        with patch.object(database, "_migrate_pg", side_effect=AssertionError("DDL repeated")):
            database.init_db()
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 1)


class BoundaryContracts(unittest.TestCase):
    def test_provider_key_is_bound_to_origin(self):
        for endpoint in ("https://evil.example/v1", "https://api.example:444/v1", "http://api.example/v1"):
            with self.assertRaises(HTTPException):
                require_new_key("https://api.example/v1", endpoint, "")
        require_new_key("https://api.example/v1", "https://api.example/v2", "")
        require_new_key("https://api.example/v1", "https://evil.example/v1", "new-key")
        with patch.object(get_settings(), "provider_allow_private", False):
            for endpoint in ("http://example.org", "https://user:pass@example.org", "https://example.org?q=secret"):
                with self.assertRaises(HTTPException):
                    validate_endpoint(endpoint, resolve=False)

    def test_waiting_lock_does_not_borrow_connection(self):
        entered, release = threading.Event(), threading.Event()
        def hold():
            with admission(("content",), None, 1):
                entered.set()
                release.wait(2)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(hold)
            entered.wait(1)
            try:
                with self.assertRaises(DatabaseBusy), admission(("content",), None, 0.02):
                    self.fail("entered locked domain")
            finally:
                release.set()
            future.result()

    def test_duplicate_payment_calls_share_work(self):
        started, release = threading.Event(), threading.Event()
        calls = []
        def pay(identifier):
            calls.append(identifier)
            started.set()
            release.wait(2)
            return "paid"
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(execute, pay, "same-order")
            started.wait(1)
            second = executor.submit(execute, pay, "same-order")
            # 待第二个请求已进入共享 Future 后再释放首个调用。
            import time
            time.sleep(0.05)
            release.set()
            self.assertEqual(first.result(), second.result())
        self.assertEqual(calls, ["same-order"])

    def test_csrf_and_response_headers(self):
        app = FastAPI()
        app.add_middleware(RequestContext)
        @app.post("/write")
        def write():
            return {"ok": True}
        with TestClient(app) as client:
            client.cookies.set("lc_session", "example")
            response = client.post("/write", headers={"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"})
            self.assertEqual(response.status_code, 403)
            response = client.post("/write", headers={"Origin": "http://testserver"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
            self.assertTrue(response.headers["X-Correlation-ID"])
