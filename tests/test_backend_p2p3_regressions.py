"""P2/P3 并发、会话、轮换与快照协议回归，只使用临时数据库和文件。"""

import asyncio
import os
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import psycopg
import test_backend_catalog as catalog_tests
import test_backend_reliability as reliability
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from psycopg.errors import LockNotAvailable
from psycopg_pool import PoolTimeout, TooManyRequests

from app.config import get_settings
from app.constants import LOCK_IDS, MAINTENANCE_LOCK
from app.db import db
from app.db_admission import DatabaseBusy
from app.http_limits import limited_lines
from app.main import database_busy
from app.models.site import DictionaryInput, DictionaryReorder
from app.security import create_token, decrypt_secret, encrypt_secret, parse_token
from app.services import membership_cards, mini_auth, site_content, user_store, workspace_sessions
from scripts import backup_restore, rotate_encryption


class DataRegressions(unittest.TestCase):
    setUp = reliability.BackendReliability.setUp

    def test_two_concurrent_cards_preserve_both_grants_and_replay_is_rejected(self):
        reader = mini_auth.register("cards-reader", "test-password", admin=True)["user"]["id"]
        codes = [item["code"] for item in membership_cards.create(self.user.id, 30, 2)["items"]]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda code: membership_cards.redeem(reader, code), codes))
        ends = sorted(item["vip_expires_at"] for item in results)
        self.assertEqual(ends[1] - ends[0], 30 * 86400)
        with self.assertRaises(HTTPException):
            membership_cards.redeem(reader, codes[0])

    def test_same_card_race_has_exactly_one_winner(self):
        readers = [mini_auth.register(f"race-reader-{n}", "test-password", admin=True)["user"]["id"] for n in range(2)]
        code = membership_cards.create(self.user.id, 30, 1)["items"][0]["code"]
        def redeem(reader):
            try:
                membership_cards.redeem(reader, code)
                return True
            except HTTPException:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(redeem, readers)), 1)
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mini_membership_grants").fetchone()[0], 1)

    def test_expired_and_disabled_cards_cannot_be_consumed(self):
        reader = mini_auth.register("invalid-card-reader", "test-password", admin=True)["user"]["id"]
        expired = membership_cards.create(self.user.id, 30, 1, int(time.time()) - 1)["items"][0]["code"]
        disabled = membership_cards.create(self.user.id, 30, 1)["items"][0]["code"]
        with db() as conn:
            identifier = conn.execute("SELECT id FROM mini_membership_cards WHERE code_hash = ?", (membership_cards._hash(disabled),)).fetchone()[0]
        membership_cards.disable(identifier)
        for code in (expired, disabled):
            with self.assertRaises(HTTPException):
                membership_cards.redeem(reader, code)

    def test_device_logout_and_idle_expiry(self):
        first, second = [workspace_sessions.create(self.user.id) for _ in range(2)]
        workspace_sessions.revoke(first, self.user.id)
        self.assertFalse(workspace_sessions.valid(first, self.user.id))
        self.assertTrue(workspace_sessions.valid(second, self.user.id))
        with db() as conn:
            conn.execute("UPDATE workspace_sessions SET last_seen_at = 1 WHERE id = ?", (second,))
        self.assertFalse(workspace_sessions.valid(second, self.user.id))
        workspace_sessions.prune()
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM workspace_sessions").fetchone()[0], 0)

    def test_new_login_in_reset_second_is_valid_and_old_token_is_not(self):
        with patch("app.security.time.time", return_value=2000000000):
            old = create_token(self.user.id)
            user_store.update_user(self.user.id, password="changed-password")
            cutoff = user_store.get_user_by_username(self.user.username)["token_valid_after"]
            new = create_token(self.user.id, issued_after=cutoff)
            self.assertLess(parse_token(old)["iat"], cutoff)
            self.assertGreaterEqual(parse_token(new)["iat"], cutoff)

    def test_keyring_rotation_is_atomic_and_preserves_plaintext(self):
        reader = mini_auth.register("rotation-reader", "test-password", admin=True)["user"]["id"]
        settings = get_settings()
        with patch.object(settings, "encryption_active_key", ""), patch.object(settings, "encryption_keys", {}):
            original = encrypt_secret("private-wechat-openid")
        with db() as conn:
            conn.execute("UPDATE mini_users SET wechat_openid_enc = ? WHERE id = ?", (original, reader))
        with patch.object(settings, "encryption_active_key", "v2"), patch.object(settings, "encryption_keys", {"v2": "new-test-encryption-secret-32-bytes-long"}):
            self.assertEqual(rotate_encryption.rotate()["would_change"], 1)
            self.assertEqual(rotate_encryption.rotate(apply=True)["changed"], 1)
            with db() as conn:
                value = conn.execute("SELECT wechat_openid_enc FROM mini_users WHERE id = ?", (reader,)).fetchone()[0]
            self.assertTrue(value.startswith("enc2:v2:"))
            self.assertEqual(decrypt_secret(value), "private-wechat-openid")
            self.assertEqual(rotate_encryption.rotate(apply=True)["changed"], 0)

    def test_dictionary_reorder_rejects_stale_group_atomically(self):
        a = site_content.create_dictionary(DictionaryInput(kind="grade", value="extra-grade-a"))
        b = site_content.create_dictionary(DictionaryInput(kind="grade", value="extra-grade-b"))
        items = site_content.list_dictionary("grade", "")["items"]
        body = DictionaryReorder(kind="grade", items=[{"id": row["id"], "revision": row["revision"]} for row in reversed(items)])
        result = site_content.reorder_dictionary(body)
        self.assertEqual([row["id"] for row in result["items"]], [row["id"] for row in reversed(items)])
        with self.assertRaises(HTTPException) as caught:
            site_content.reorder_dictionary(body)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(result, site_content.list_dictionary("grade", ""))
        self.assertNotEqual(a["id"], b["id"])

    def test_backup_releases_business_locks_before_dump_and_retains_maintenance_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = root / "service.env"
            env.write_text("fixture=true", encoding="utf-8")
            def dump(args, dsn, program, file, snapshot):
                with psycopg.connect(dsn, autocommit=True) as other:
                    for key in LOCK_IDS.values():
                        self.assertTrue(other.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()[0])
                        other.execute("SELECT pg_advisory_unlock(%s)", (key,))
                    self.assertFalse(other.execute("SELECT pg_try_advisory_lock(%s)", (MAINTENANCE_LOCK,)).fetchone()[0])
                file.write_bytes(b"fixture-dump")
            with patch.dict(os.environ, {"DATABASE_URL": get_settings().database_url}), patch.object(backup_restore, "pg_tool", side_effect=dump):
                backup_restore.backup(SimpleNamespace(destination=root / "backup", files_root=root / "files", env_file=env, secret_file=None, pg_container=None))
            self.assertTrue((root / "backup" / "manifest.json").is_file())


class CursorRegressions(unittest.TestCase):
    setUp = catalog_tests.PublicCatalogContracts.setUp
    sign_in = catalog_tests.PublicCatalogContracts.sign_in
    source = catalog_tests.PublicCatalogContracts.source
    draft = catalog_tests.PublicCatalogContracts.draft
    update = catalog_tests.PublicCatalogContracts.update
    publish = catalog_tests.PublicCatalogContracts.publish

    def test_cursor_pages_are_complete_without_duplicates_and_filter_bound(self):
        for _ in range(3):
            self.publish()
        self.client.cookies.clear()
        for sort in ("featured", "latest", "popular"):
            items, cursor = [], ""
            for _ in range(3):
                response = self.client.get("/api/v1/catalog/papers", params={"pagination": "cursor", "sort": sort, "limit": 1, "cursor": cursor})
                self.assertEqual(response.status_code, 200, response.text)
                page = response.json()
                self.assertIsNone(page["total"])
                items.extend(row["id"] for row in page["items"])
                cursor = page["next_cursor"]
            self.assertEqual(len(set(items)), 3)
            self.assertIsNone(cursor)
        response = self.client.get("/api/v1/catalog/papers", params={"pagination": "cursor", "cursor": "tampered"})
        self.assertEqual(response.status_code, 422)


class BoundaryRegressions(unittest.TestCase):
    def test_only_structured_app_access_log_is_emitted(self):
        # 独立进程避免改变其他测试的全局日志配置；模拟 Uvicorn 启动时的旧 handler。
        result = subprocess.run([sys.executable, "-c", """
import logging
from app.logging_config import configure_logging
access = logging.getLogger('uvicorn.access')
access.addHandler(logging.StreamHandler())
configure_logging()
configure_logging()
access.info('GET /orders?private-query-fixture=1')
logging.getLogger('app.access').info('route=/orders')
"""], capture_output=True, text=True, check=True, env={**os.environ, "LOG_TO_FILE": "false", "LOG_FORMAT": "json"})
        output = result.stdout + result.stderr
        self.assertNotIn("private-query-fixture", output)
        self.assertEqual(output.count('"name": "app.access"'), 1)

    def test_db_errors_have_retryable_json_contract(self):
        for kind in (DatabaseBusy, PoolTimeout, TooManyRequests, LockNotAvailable):
            app = FastAPI()
            app.add_exception_handler(kind, database_busy)
            def failing():
                raise kind("fixture")  # noqa: B023 - 每轮在下轮赋值前同步发起请求
            app.add_api_route("/busy", failing)
            with TestClient(app) as client:
                response = client.get("/busy")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers["Retry-After"], "2")
            self.assertEqual(response.json()["detail"]["code"], "database_busy")

    def test_stream_without_line_breaks_is_bounded(self):
        async def consume():
            response = httpx.Response(200, content=b"x" * 70000)
            return [line async for line in limited_lines(response, 1000)]
        with self.assertRaises(HTTPException) as caught:
            asyncio.run(consume())
        self.assertEqual(caught.exception.status_code, 502)

    def test_restore_rejects_hostaddr_and_port_before_reading_backup(self):
        for query in ("?hostaddr=192.0.2.1", "?port=6543", "?service=remote"):
            with patch.dict(os.environ, {"LC_RESTORE_DATABASE_URL": "postgresql://u:p@localhost/lc_test_fixture" + query}):
                with self.assertRaisesRegex(ValueError, "local disposable"):
                    backup_restore.restore(SimpleNamespace())
