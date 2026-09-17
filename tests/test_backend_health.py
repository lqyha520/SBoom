"""Liveness/readiness and event-loop responsiveness without external services."""

import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from app.deps import require_user
from app.routers import auth, generate, health


class HealthContracts(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(health.router)
        self.app.include_router(auth.router)
        self.app.include_router(generate.router)
        self.app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=1)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_readiness_failure_is_503_without_exposing_details_and_recovers(self):
        with patch.object(health, "database_ready", side_effect=[False, True]):
            failed = await self.client.get("/readyz")
            self.assertEqual(failed.status_code, 503)
            self.assertEqual(failed.json(), {"status": "unavailable"})
            self.assertEqual(failed.headers["cache-control"], "no-store")
            self.assertEqual((await self.client.get("/health")).status_code, 200)
            self.assertEqual((await self.client.get("/readyz")).json(), {"status": "ready"})

    async def test_slow_probe_times_out_and_overlapping_probes_share_one_worker(self):
        entered, release = threading.Event(), threading.Event()
        def slow():
            entered.set()
            release.wait(4)
            return True
        with patch.object(health, "database_ready", side_effect=slow) as probe:
            first = asyncio.create_task(self.client.get("/readyz"))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                second = asyncio.create_task(self.client.get("/readyz"))
                self.assertEqual((await self.client.get("/health")).status_code, 200)
                self.assertEqual((await first).status_code, 503)
                self.assertEqual((await second).status_code, 503)
                self.assertEqual(probe.call_count, 1)
            finally:
                release.set()
                await self.app.state.readiness_probe

    async def test_registration_and_scope_io_do_not_block_the_event_loop(self):
        for route in ("register", "scope"):
            with self.subTest(route=route):
                entered, release = threading.Event(), threading.Event()
                resumed_before_return = []
                def slow(*args, **kwargs):
                    entered.set()
                    resumed_before_return.append(release.wait(1))
                    return (SimpleNamespace(id=1, username="worker-user") if route == "register" else
                            {"grade": "小学一年级", "subject": "数学", "allowed": [], "forbidden": []})
                target, name = (auth.user_store, "create_user") if route == "register" else (generate.knowledge_scope_service, "get_scope")
                with patch.object(target, name, side_effect=slow), patch.object(auth.user_store, "get_user_by_username", return_value=None), \
                        patch.object(auth, "allow", return_value=True), patch.object(auth.settings, "registration_enabled", True):
                    job = asyncio.create_task(self.client.post("/api/v1/auth/register", json={"username": "worker-user", "password": "password"}) if route == "register" else
                                              self.client.get("/api/v1/scope?grade=小学一年级&subject=数学"))
                    try:
                        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                        self.assertEqual((await self.client.get("/health")).status_code, 200)
                    finally:
                        release.set()
                    self.assertEqual((await job).status_code, 200)
                    self.assertEqual(resumed_before_return, [True])
