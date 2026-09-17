"""Concurrency and pagination regressions against disposable PostgreSQL data."""

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from unittest.mock import patch

import pg_support

pg_support.install_module_database({"SECRET_KEY": "optimization-tests-disposable-secret"})

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import db as database, security
from app.deps import SESSION_COOKIE
from app.routers import admin
from app.services import generation_control, user_store


class OptimizationContracts(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        pg_support.case_database(self.stack)
        database.init_db()
        self.user = user_store.create_user("optimization-admin", "test-password", role="admin")
        app = FastAPI()
        app.include_router(admin.router)
        self.client = self.stack.enter_context(TestClient(app))
        self.client.cookies.set(SESSION_COOKIE, security.create_token(self.user.id))

    def test_users_are_bounded_filtered_and_counted_on_the_server(self):
        with database.db() as conn:
            conn.executemany("INSERT INTO users(username, password_hash) VALUES (?, ?)",
                             [(f"page-user-{index:02}", "unused-test-hash") for index in range(43)])
            conn.execute("INSERT INTO users(username, password_hash) VALUES (?, ?)", ("literal_%", "unused-test-hash"))
        first = self.client.get("/api/v1/admin/users?role=user&limit=20").json()
        second = self.client.get("/api/v1/admin/users?role=user&limit=20&offset=20").json()
        self.assertEqual(first["total"], 44)
        self.assertEqual(len(first["users"]), 20)
        self.assertEqual(len(second["users"]), 20)
        self.assertFalse({row["id"] for row in first["users"]} & {row["id"] for row in second["users"]})
        result = self.client.get("/api/v1/admin/users", params={"query": "_%", "role": "user"}).json()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["users"][0]["username"], "literal_%")
        self.assertEqual(self.client.get("/api/v1/admin/users?role=admin").json()["total"], 1)
        empty = self.client.get("/api/v1/admin/users?role=user&offset=100").json()
        self.assertEqual(empty["users"], [])
        self.assertEqual(empty["total"], 44)
        for query in ("limit=0", "limit=101", "offset=-1"):
            self.assertEqual(self.client.get("/api/v1/admin/users?" + query).status_code, 422)

    def test_account_transaction_does_not_block_content_or_generation(self):
        held, release, blocked = threading.Event(), threading.Event(), threading.Event()

        def hold_account():
            with database.db(serialized="accounts"):
                held.set()
                release.wait(5)

        def same_domain():
            with database.db(serialized="accounts"):
                blocked.set()

        def content_write():
            with database.db(serialized=True) as conn:
                conn.execute("INSERT INTO app_config(key, value) VALUES ('lock-test', 'ok')")

        with ThreadPoolExecutor(max_workers=4) as pool:
            owner = pool.submit(hold_account)
            self.assertTrue(held.wait(2))
            follower = pool.submit(same_domain)
            try:
                pool.submit(content_write).result(timeout=2)
                result = pool.submit(generation_control._begin, self.user.id, "independent-generation", "single", {}).result(timeout=2)
                self.assertIsNone(result)
                self.assertFalse(blocked.is_set(), "account transactions must still serialize")
            finally:
                release.set()
            owner.result(timeout=2)
            follower.result(timeout=2)
            self.assertTrue(blocked.is_set())

    def test_concurrent_admin_creation_returns_conflict_instead_of_server_error(self):
        barrier = threading.Barrier(2)
        lookup = user_store.get_user_by_username

        def synchronized_lookup(name):
            result = lookup(name)
            barrier.wait(timeout=2)
            return result

        def create():
            return self.client.post("/api/v1/admin/users", json={
                "username": "concurrent-user", "password": "test-password", "role": "user",
            }).status_code

        with patch.object(user_store, "get_user_by_username", side_effect=synchronized_lookup), ThreadPoolExecutor(max_workers=2) as pool:
            requests = [pool.submit(create) for _ in range(2)]
            self.assertEqual(sorted(request.result(timeout=5) for request in requests), [200, 409])

    def test_cross_domain_transactions_protect_both_domains(self):
        held, release = threading.Event(), threading.Event()
        completed = {scope: threading.Event() for scope in ("content", "accounts")}

        def mixed():
            with database.db(serialized=("accounts", "content")):
                held.set()
                release.wait(5)

        def write(scope):
            with database.db(serialized=scope):
                completed[scope].set()

        with ThreadPoolExecutor(max_workers=3) as pool:
            owner = pool.submit(mixed)
            self.assertTrue(held.wait(2))
            followers = [pool.submit(write, scope) for scope in completed]
            try:
                for event in completed.values():
                    self.assertFalse(event.wait(.1))
            finally:
                release.set()
            owner.result(timeout=2)
            for job in followers:
                job.result(timeout=2)

    def test_readiness_checks_database_and_recovers_after_pool_shutdown(self):
        self.assertTrue(database.database_ready())
        database.close_pg_pool()
        self.assertFalse(database.database_ready())
        with database.db() as conn:
            conn.execute("SELECT 1")
        self.assertTrue(database.database_ready())
