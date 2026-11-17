"""使用真实异步请求流与线程验证上传限额，不连接数据库。"""

import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import ClientDisconnect, Request

from app.routers.xhs_workspace import upload


class UploadAdmissionTests(unittest.IsolatedAsyncioTestCase):
    def request(self, receive):
        return Request({'type': 'http', 'headers': [(b'content-type', b'video/mp4')]}, receive)

    async def test_busy_upload_is_rejected_before_reading_and_cancel_keeps_slot(self):
        release = threading.Event()
        entered = 0
        reads = 0

        def create(*args):
            nonlocal entered
            entered += 1
            release.wait(5)
            return {'id': 'saved'}

        async def receive():
            nonlocal reads
            reads += 1
            return {'type': 'http.request', 'body': b'video', 'more_body': False}

        with patch('app.routers.xhs_workspace.service.create_asset', create):
            tasks = [asyncio.create_task(upload(self.request(receive), '视频', SimpleNamespace(id=1))) for _ in range(2)]
            try:
                async with asyncio.timeout(3):
                    while entered != 2:
                        await asyncio.sleep(0.005)
                tasks[0].cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await tasks[0]
                with self.assertRaises(HTTPException) as busy:
                    await upload(self.request(receive), '视频', SimpleNamespace(id=1))
                self.assertEqual(busy.exception.status_code, 429)
                self.assertEqual(busy.exception.headers['Retry-After'], '3')
                self.assertEqual(reads, 2)
            finally:
                release.set()
                await asyncio.gather(*tasks, return_exceptions=True)
                # 工作线程与 done callback 归还两个名额。
                await asyncio.sleep(0.05)
            self.assertEqual(await upload(self.request(receive), '视频', SimpleNamespace(id=1)), {'id': 'saved'})

    async def test_read_failures_release_slots(self):
        async def disconnected():
            return {'type': 'http.disconnect'}

        async def empty():
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        for _ in range(3):
            with self.assertRaises(ClientDisconnect):
                await upload(self.request(disconnected), '视频', SimpleNamespace(id=1))
            with self.assertRaises(HTTPException) as invalid:
                await upload(self.request(empty), '视频', SimpleNamespace(id=1))
            self.assertEqual(invalid.exception.status_code, 422)
