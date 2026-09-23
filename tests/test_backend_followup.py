"""PDF 提前准入与退出登录账号绑定的隔离回归。"""
import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI, HTTPException

from app.deps import require_admin
from app.routers import auth, catalog
from app.services import catalog_import


class FollowupContracts(unittest.IsolatedAsyncioTestCase):
    async def test_busy_import_is_rejected_without_reading_body(self):
        app = FastAPI()
        app.include_router(catalog.admin_router)
        app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)
        reads = []

        async def body():
            reads.append(True)
            yield b"%PDF-" + b"x" * (5 * 1024 * 1024)

        catalog_import._import_gate.acquire()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                for url in ("/api/v1/admin/catalog/import", "/api/v1/admin/catalog/papers/fixture/editions/import"):
                    response = await client.post(url, content=body(), headers={"content-type": "application/pdf"})
                    self.assertEqual(response.status_code, 429, response.text)
                    self.assertEqual(response.headers["retry-after"], "3")
            self.assertEqual(reads, [])
        finally:
            catalog_import._import_gate.release()

    async def test_disconnect_does_not_release_slot_while_renderer_is_running(self):
        started, finish = threading.Event(), threading.Event()

        @catalog_import.bounded_import
        def render():
            started.set()
            if not finish.wait(3):
                raise RuntimeError("test render timed out")
            return "done"

        @catalog_import.admitted_import
        async def upload():
            return await asyncio.to_thread(render)

        pending = asyncio.create_task(upload())
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
            self.assertTrue(catalog_import._import_gate.locked())
            with self.assertRaises(HTTPException) as rejected:
                await upload()
            self.assertEqual(rejected.exception.status_code, 429)
        finally:
            finish.set()
            for _ in range(100):
                if not catalog_import._import_gate.locked():
                    break
                await asyncio.sleep(0.01)
        self.assertFalse(catalog_import._import_gate.locked())
        self.assertEqual(await upload(), "done")

    async def test_body_failure_releases_import_slot(self):
        @catalog_import.admitted_import
        async def fail():
            raise HTTPException(413, "too large")

        with self.assertRaises(HTTPException):
            await fail()
        self.assertFalse(catalog_import._import_gate.locked())

    async def test_old_page_cannot_log_out_new_cookie_owner(self):
        app = FastAPI()
        app.include_router(auth.router)
        with patch.object(auth, "parse_token", return_value={"sub": 2, "iat": 1}), patch.object(auth.user_store, "revoke_sessions") as revoke:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/auth/logout", headers={"Cookie": "lc_session=fixture", "X-Workspace-User": "1"})
                self.assertEqual(response.status_code, 409)
                self.assertNotIn("set-cookie", response.headers)
                revoke.assert_not_called()
                response = await client.post("/api/v1/auth/logout", headers={"Cookie": "lc_session=fixture", "X-Workspace-User": "2"})
                self.assertEqual(response.status_code, 200)
                self.assertIn("set-cookie", response.headers)
                self.assertEqual(revoke.call_args.args[0], 2)
