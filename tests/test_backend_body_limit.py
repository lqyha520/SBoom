"""请求体限制必须覆盖分块 JSON，并保留独立的 PDF 上传限制。"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from app.body_limit import BodySizeLimit
from app.deps import require_admin
from app.routers import catalog


class Message(BaseModel):
    text: str


class BodyLimits(unittest.IsolatedAsyncioTestCase):
    async def test_chunked_body_stops_before_parsing_or_calling_the_handler(self):
        app = FastAPI()
        handled = []

        @app.post("/message")
        def receive_message(body: Message):
            handled.append(body.text)
            return {"ok": True}

        app.add_middleware(BodySizeLimit, limit=1024)
        chunks_read = []

        async def chunks():
            yield b'{"text":"'
            for index in range(10):
                chunks_read.append(index)
                yield b"x" * 600
            yield b'"}'

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for headers in ({}, {"content-length": "100"}):
                chunks_read.clear()
                response = await client.post("/message", content=chunks(), headers=headers)
                self.assertEqual(response.status_code, 413)
                self.assertEqual(response.json()["detail"]["code"], "payload_too_large")
                self.assertEqual(len(chunks_read), 2)
            self.assertEqual(handled, [])
            self.assertEqual((await client.post("/message", json={"text": "ok"})).status_code, 200)

    async def test_edition_upload_keeps_32_mib_limit_in_the_full_middleware_stack(self):
        from app.services import catalog_editions

        app = FastAPI()
        app.include_router(catalog.admin_router)
        app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)
        app.add_middleware(BodySizeLimit, limit=4 * 1024 * 1024)
        detail = {"revision": 1, "status": "draft", "title": "test", "grade": "三年级", "subject": "数学"}
        with patch.object(catalog.catalog, "get_paper", return_value=detail), patch.object(
            catalog.catalog_import, "import_paper", return_value={"id": "archive"}
        ) as importer, patch.object(catalog_editions, "assign", return_value={"revision": 2}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                url = "/api/v1/admin/catalog/papers/example/editions/import?revision=1"
                response = await client.post(url, content=b"%PDF-" + b"x" * (5 * 1024 * 1024), headers={"content-type": "application/pdf"})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(importer.call_count, 1)
                response = await client.post(url, content=b"", headers={"content-type": "application/pdf", "content-length": str(33 * 1024 * 1024)})
                self.assertEqual(response.status_code, 413)
                self.assertEqual(importer.call_count, 1)

    async def test_similar_routes_and_other_methods_are_not_exempt(self):
        app = FastAPI()
        app.add_middleware(BodySizeLimit, limit=1024)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for method, path in (
                ("PUT", "/api/v1/library/papers/id"),
                ("PUT", "/api/v1/admin/site/documents/privacy"),
                ("POST", "/api/v1/admin/catalog/import-other"),
                ("PATCH", "/api/v1/admin/catalog/papers/id/editions/import"),
            ):
                response = await client.request(method, path, content=b"x" * 2048)
                self.assertEqual(response.status_code, 413, path)
