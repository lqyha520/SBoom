"""核心层优化回归：连接池/超时配置、请求体上限、登出吊销、test-llm 防 SSRF、缓存与超时策略。

所有数据库都是一次性测试库；不访问任何外部服务。
"""

import asyncio
import os
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pg_support  # noqa: E402  建一次性测试库，必须在 import app 之前

pg_support.install_module_database({"SECRET_KEY": "test-core-opt-secret-not-for-production",
                                    "LLM_API_KEY": "", "ADMIN_USERNAME": "", "ADMIN_PASSWORD": "",
                                    "FORCE_HTTPS": "false", "CORS_ORIGINS": ""})

import httpx
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import db as database
from app.config import get_settings
from app.deps import SESSION_COOKIE, require_admin
from app.routers import admin, auth
from app.services import app_config, user_store, wechat_pay
from app.services import generation_control as control
from app.services.llm_client import RETRYABLE, LLMClient


class PoolAndTranslationContracts(unittest.TestCase):
    def test_connection_options_merge_existing_dsn_options(self):
        settings = SimpleNamespace(db_statement_timeout_ms=30000, db_lock_timeout_ms=10000,
                                   db_idle_in_transaction_timeout_ms=60000)
        merged = database._connection_options(
            "postgresql://u:p@127.0.0.1:5432/db?options=-csearch_path%3Dcase_x", settings)
        self.assertTrue(merged.startswith("-csearch_path=case_x "))
        self.assertIn("-c statement_timeout=30000", merged)
        self.assertIn("-c lock_timeout=10000", merged)
        self.assertIn("-c idle_in_transaction_session_timeout=60000", merged)
        plain = database._connection_options("postgresql://u:p@127.0.0.1:5432/db", settings)
        self.assertTrue(plain.startswith("-c statement_timeout=30000"))

    def test_sql_translation_is_cached_and_pure(self):
        sql = "SELECT 1 FROM t WHERE id = ? AND label = 'a?b' AND x LIKE 'import-%'"
        expected = "SELECT 1 FROM t WHERE id = %s AND label = 'a?b' AND x LIKE 'import-%%'"
        before = database._to_pg_sql.cache_info().hits
        self.assertEqual(database._to_pg_sql(sql), expected)
        self.assertEqual(database._to_pg_sql(sql), expected)
        self.assertGreater(database._to_pg_sql.cache_info().hits, before)

    def test_mixed_row_keeps_positional_and_named_access(self):
        row = database._MixedRow(["id", "name"], (7, "x"))
        self.assertEqual((row[0], row[1], row["id"], row["name"]), (7, "x", 7, "x"))
        self.assertEqual(dict(row), {"id": 7, "name": "x"})

    def test_pool_metrics_are_sampled_at_most_once_per_second(self):
        calls = []
        pool = SimpleNamespace(get_stats=lambda: calls.append(1) or {"pool_size": 3, "pool_available": 1})
        with patch.object(database, "_pool_stats_sampled_at", 0.0):
            database._sample_pool_metrics(pool)
            database._sample_pool_metrics(pool, returning=True)
            database._sample_pool_metrics(pool)
        self.assertEqual(len(calls), 1)

    def test_session_timeouts_are_applied_and_ddl_transactions_are_unbounded(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        pg_support.case_database(stack)
        with database.db() as conn:
            self.assertEqual(conn.execute("SHOW statement_timeout").fetchone()[0], "30s")
            self.assertEqual(conn.execute("SHOW lock_timeout").fetchone()[0], "2500ms")
            self.assertEqual(conn.execute("SHOW idle_in_transaction_session_timeout").fetchone()[0], "1min")
        with database.db(ddl=True) as conn:
            self.assertEqual(conn.execute("SHOW statement_timeout").fetchone()[0], "0")
            self.assertEqual(conn.execute("SHOW lock_timeout").fetchone()[0], "30s")
        with database.db() as conn:  # SET LOCAL 不能泄漏到下一个事务
            self.assertEqual(conn.execute("SHOW statement_timeout").fetchone()[0], "30s")


class LlmClientTimeoutContracts(unittest.TestCase):
    def test_connect_and_pool_timeouts_stay_short_even_for_long_requests(self):
        timeout = LLMClient._req_timeout(600)
        self.assertEqual((timeout.read, timeout.write, timeout.connect, timeout.pool), (600.0, 600.0, 10.0, 10.0))
        default = LLMClient._req_timeout(None)
        self.assertEqual((default.read, default.connect), (LLMClient.DEFAULT_TIMEOUT, 10.0))

    def test_connect_timeout_is_retryable_but_read_timeout_is_not(self):
        self.assertIn(httpx.ConnectTimeout, RETRYABLE)
        self.assertNotIn(httpx.ReadTimeout, RETRYABLE)
        self.assertNotIn(httpx.TimeoutException, RETRYABLE)


class BodySizeLimitContracts(unittest.TestCase):
    def make_app(self, limit=1024):
        from app.main import BodySizeLimit
        app = FastAPI()

        @app.post("/api/v1/me/templates")
        async def small(request: Request):
            return {"size": len(await request.body())}

        @app.post("/api/v1/library/papers")
        async def upload(request: Request):
            return {"size": len(await request.body())}

        app.add_middleware(BodySizeLimit, limit=limit)
        return app

    def test_oversized_declared_body_is_rejected_before_routing(self):
        with TestClient(self.make_app()) as client:
            rejected = client.post("/api/v1/me/templates", content=b"x" * 2048,
                                   headers={"Content-Type": "application/octet-stream"})
            self.assertEqual(rejected.status_code, 413)
            self.assertEqual(rejected.json()["detail"]["code"], "payload_too_large")
            accepted = client.post("/api/v1/me/templates", content=b"x" * 512,
                                   headers={"Content-Type": "application/octet-stream"})
            self.assertEqual(accepted.json(), {"size": 512})

    def test_streaming_upload_endpoints_keep_their_own_limits(self):
        with TestClient(self.make_app()) as client:
            result = client.post("/api/v1/library/papers", content=b"x" * 4096,
                                 headers={"Content-Type": "application/zip"})
            self.assertEqual(result.json(), {"size": 4096})

    def test_main_app_registers_the_limit_with_upload_exemptions(self):
        from app import main
        names = [middleware.cls.__name__ for middleware in main.app.user_middleware]
        self.assertIn("BodySizeLimit", names)
        from app.body_limit import has_upload_limit
        from app.config import Settings
        for path in ("/api/v1/library/papers", "/api/v1/admin/catalog/import", "/api/v1/mini/me/avatar",
                     "/api/v1/payments/wechat/notify", "/api/v1/admin/catalog/papers/example/editions/import"):
            self.assertTrue(has_upload_limit("POST", path), path)
        # 检查默认配置定义，不依赖开发机 .env 或外部环境变量。
        self.assertEqual(Settings.model_fields["max_request_body_bytes"].default, 4 * 1024 * 1024)
        self.assertEqual(Settings.model_fields["log_format"].default, "auto")
        self.assertEqual(main.logging.getLogger("httpx").level, main.logging.WARNING)
        self.assertEqual(main.logging.getLogger("httpcore").level, main.logging.WARNING)


class LogoutRevocationContracts(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        pg_support.case_database(self.stack)
        database.init_db()
        self.user = user_store.create_user("logout-user", "test-password")
        app = FastAPI()
        app.include_router(auth.router)
        self.client = self.stack.enter_context(TestClient(app))

    def test_logout_rejects_the_old_cookie_server_side(self):
        login = self.client.post("/api/v1/auth/login", json={"username": "logout-user", "password": "test-password"})
        self.assertEqual(login.status_code, 200, login.text)
        old_cookie = login.cookies[SESSION_COOKIE]
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/logout").json(), {"status": "ok"})
        # 把旧 Cookie 复制回来：不仅浏览器端被删，服务端也必须拒绝
        self.client.cookies.set(SESSION_COOKIE, old_cookie)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(user_store.get_user_by_id(self.user.id).token_valid_after, 0)  # 单设备退出不吊销其他设备

    def test_logout_without_valid_cookie_still_succeeds(self):
        self.client.cookies.set(SESSION_COOKIE, "not-a-token")
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 200)
        self.client.cookies.clear()
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 200)
        self.assertEqual(user_store.get_user_by_id(self.user.id).token_valid_after, 0)

    def test_unknown_username_still_runs_password_verification(self):
        with patch.object(user_store, "verify_password", return_value=False) as verify:
            self.assertIsNone(user_store.authenticate("nobody-here", "whatever"))
        verify.assert_called_once()
        self.assertEqual(verify.call_args[0][1], user_store._dummy_password_hash())


class TestLlmSsrfContracts(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(admin.router)
        app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, username="admin", role="admin")
        self.client = TestClient(app)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(app_config, "get_llm", return_value={
            "baseUrl": "https://api.example.invalid", "model": "m", "timeout": 30, "hasKey": True, "api_key": "k"}))
        self.stack.enter_context(patch.object(httpx.AsyncClient, "stream", side_effect=AssertionError("must not connect")))

    def test_private_and_metadata_addresses_are_rejected_without_connecting(self):
        for base in ("http://169.254.169.254", "http://127.0.0.1", "http://127.0.0.1:11434/v1",
                     "http://localhost:8000", "http://10.0.0.8/v1", "ftp://example.com", "http://user:pw@example.com"):
            result = self.client.post("/api/v1/admin/test-llm", json={"baseUrl": base, "model": "m", "apiKey": "k", "timeout": 30})
            self.assertIn(result.status_code, (400, 422), base)
            self.assertEqual(result.json()["detail"]["error"], "接口地址不允许")

    def test_public_address_is_pinned_to_its_resolved_ip(self):
        with patch.object(admin.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            pinned, host = admin._pin_public_url("https://api.example.com/v1")
        self.assertEqual((pinned, host), ("https://93.184.216.34/v1", "api.example.com"))
        with patch.object(admin.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 8443)), (2, 1, 6, "", ("10.1.1.1", 8443))]):
            with self.assertRaises(ValueError):
                admin._pin_public_url("https://api.example.com:8443/v1")


class GenerationInterruptContracts(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        pg_support.case_database(self.stack)
        database.init_db()
        self.user = user_store.create_user("interrupt-user", "test-password")

    def run_metered(self, error):
        @control.metered("batch")
        async def handler(*, request, user, http_request=None):
            raise error

        request = SimpleNamespace(model_dump=lambda mode="json": {"kind": "probe"})
        http_request = SimpleNamespace(headers={"X-Request-ID": "interrupt-one"})
        return asyncio.run(handler(request=request, user=self.user, http_request=http_request))

    def test_process_signals_are_not_translated_into_503(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_metered(KeyboardInterrupt())
        self.assertEqual(control.request_status(self.user.id, "interrupt-one")["status"], "unknown")

    def test_ordinary_failures_still_become_http_errors(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as failed:
            self.run_metered(RuntimeError("provider exploded"))
        self.assertEqual(failed.exception.status_code, 503)
        self.assertEqual(failed.exception.detail["request_id"], "interrupt-one")


class AppConfigStaleWhileRevalidateContracts(unittest.TestCase):
    def setUp(self):
        app_config._invalidate_cache()
        self.addCleanup(app_config._invalidate_cache)

    def test_expired_value_is_served_while_one_thread_refreshes(self):
        with patch.object(app_config, "_load_llm_raw", return_value={"model": "old"}), \
                patch.object(app_config.time, "monotonic", return_value=100):
            self.assertEqual(app_config.get_llm()["model"], "old")
        started, release = threading.Event(), threading.Event()

        def slow_load():
            started.set()
            self.assertTrue(release.wait(5))
            return {"model": "new"}

        with patch.object(app_config, "_load_llm_raw", side_effect=slow_load) as loader, \
                patch.object(app_config.time, "monotonic", return_value=200):
            refresher = threading.Thread(target=app_config.get_llm)
            refresher.start()
            try:
                self.assertTrue(started.wait(2))
                deadline = time.perf_counter()
                self.assertEqual(app_config.get_llm()["model"], "old")  # 不等刷新，直接拿旧值
                self.assertLess(time.perf_counter() - deadline, 1.0)
            finally:
                release.set()
                refresher.join(5)
            self.assertEqual(app_config.get_llm()["model"], "new")
            self.assertEqual(loader.call_count, 1)


class WeChatPayConfigurationCacheContracts(unittest.TestCase):
    def test_configuration_is_cached_and_invalidated_by_setting_or_key_file_changes(self):
        root = Path(tempfile.mkdtemp(prefix="lc-pay-"))
        self.addCleanup(lambda: [p.unlink() for p in root.iterdir()] and root.rmdir())
        private = root / "merchant.pem"
        private.write_text("placeholder")
        with patch.object(get_settings(), "wechat_pay_private_key_path", str(private)), \
                patch.object(wechat_pay, "_compute_configuration", wraps=wechat_pay._compute_configuration) as compute, \
                patch.object(wechat_pay, "_config_cache", None):
            first = wechat_pay.configuration()
            self.assertEqual(wechat_pay.configuration(), first)
            self.assertEqual(compute.call_count, 1)
            first["missing"].append("mutated")  # 调用方改返回值不能污染缓存
            self.assertNotIn("mutated", wechat_pay.configuration()["missing"])
            with patch.object(get_settings(), "wechat_pay_mchid", "1900000001"):
                wechat_pay.configuration()
            self.assertEqual(compute.call_count, 2)
            time.sleep(0.02)
            private.write_text("placeholder-changed")
            wechat_pay.configuration()
            self.assertEqual(compute.call_count, 3)

    def test_shared_http_client_is_reused_unless_a_transport_is_injected(self):
        self.assertIs(wechat_pay._http_client(), wechat_pay._http_client())
        from app.services import wechat_notices
        self.assertIs(wechat_notices._http_client(), wechat_notices._http_client())


class RunLauncherContracts(unittest.TestCase):
    def test_forwarded_ips_warning_only_for_https_behind_default_trust(self):
        import run
        with patch.object(run.settings, "force_https", True):
            with patch.dict(os.environ, {"FORWARDED_ALLOW_IPS": ""}):
                self.assertIn("FORWARDED_ALLOW_IPS", run.forwarded_ips_warning())
            with patch.dict(os.environ, {"FORWARDED_ALLOW_IPS": "127.0.0.1"}):
                self.assertIsNotNone(run.forwarded_ips_warning())
            with patch.dict(os.environ, {"FORWARDED_ALLOW_IPS": "172.18.0.1"}):
                self.assertIsNone(run.forwarded_ips_warning())
        with patch.object(run.settings, "force_https", False), patch.dict(os.environ, {"FORWARDED_ALLOW_IPS": ""}):
            self.assertIsNone(run.forwarded_ips_warning())


if __name__ == "__main__":
    unittest.main()
