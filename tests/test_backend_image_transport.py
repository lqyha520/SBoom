"""图片传输的连接复用、来源隔离和事件循环响应性；不访问业务库或付费服务。"""

import asyncio
import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.provider_policy import pin_provider_request, reachable_ip
from app.services import image_generation as service
from app.services.provider_http import borrow_client, close_clients


class ImageTransport(unittest.IsolatedAsyncioTestCase):
    async def test_polling_reuses_one_connection_and_releases_it(self):
        connections, requests = [], []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def setup(self):
                super().setup()
                connections.append(self.connection)

            def do_GET(self):
                requests.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch.object(get_settings(), "provider_allow_private", True):
                async with borrow_client("image-generation", 5) as baseline:
                    for index in range(5):
                        response = await baseline.get(endpoint + f"/baseline/{index}")
                        self.assertEqual(response.json(), {})
                await close_clients()
                self.assertEqual(len(connections), 5)
                before = len(connections)
                async with borrow_client("image-generation", 5, base_url=endpoint) as client:
                    for index in range(5):
                        response = await client.get(endpoint + f"/poll/{index}")
                        self.assertEqual(response.json(), {})
                    self.assertFalse(client.is_closed)
                self.assertTrue(client.is_closed)
            self.assertEqual(len(requests), 10)
            self.assertEqual(len(connections) - before, 1, "轮询不能每次都重建 TCP/TLS 连接")
        finally:
            await asyncio.to_thread(server.shutdown)
            server.server_close()
            thread.join(timeout=2)

    async def test_same_ip_providers_have_separate_pools_and_cross_origin_is_blocked(self):
        sent, clients = [], []
        original = httpx.AsyncClient

        def create(**kwargs):
            client = original(**kwargs, transport=httpx.MockTransport(lambda request: sent.append(request) or httpx.Response(200)))
            clients.append(client)
            return client

        with patch.object(httpx, "AsyncClient", side_effect=create), \
                patch.object(get_settings(), "provider_allow_private", False), \
                patch("app.provider_policy.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 443))]):
            async with borrow_client("image-generation", 5, base_url="https://first.example/v1") as first:
                await first.get("https://first.example/poll", headers={"Authorization": "Bearer first-key"})
                with self.assertRaises(HTTPException) as error:
                    await first.get("https://second.example/poll", headers={"Authorization": "Bearer first-key"})
                self.assertEqual(error.exception.status_code, 422)
                async with borrow_client("image-generation", 5, base_url="https://second.example/v1") as second:
                    self.assertIsNot(first, second)
                    await second.get("https://second.example/poll", headers={"Authorization": "Bearer second-key"})
                # 连接复用也必须再次检查 DNS，不能用旧连接跳过运行时地址护栏。
                with patch("app.provider_policy.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
                    with self.assertRaises(HTTPException):
                        await first.get("https://first.example/poll")
        self.assertEqual([request.headers["host"] for request in sent], ["first.example", "second.example"])
        self.assertEqual([request.extensions["sni_hostname"] for request in sent], ["first.example", "second.example"])
        self.assertTrue(all(client.is_closed for client in clients))

    async def test_provider_requests_carry_browser_fingerprint(self):
        """上游多挂在 Cloudflare/Nginx 后，默认 python-httpx 指纹会被区别对待。"""
        sent = []
        original = httpx.AsyncClient

        def create(**kwargs):
            return original(**kwargs, transport=httpx.MockTransport(lambda request: sent.append(request) or httpx.Response(200)))

        with patch.object(httpx, "AsyncClient", side_effect=create), \
                patch.object(get_settings(), "provider_allow_private", False), \
                patch("app.provider_policy.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 443))]):
            async with borrow_client("image-generation", 5, base_url="https://first.example/v1") as client:
                await client.post("https://first.example/v1/images/generations", headers={"Authorization": "Bearer k"}, json={"model": "m"})
            async with borrow_client("public-image", 7) as download:
                await download.get("https://images.example/a.png")
            await close_clients()
            from app.services.llm_client import LLMClient

            llm = LLMClient()._get_client_for("https://llm.example/v1", "sk-k")
        for request in sent:
            self.assertTrue(request.headers["user-agent"].startswith("Mozilla/5.0"), "上游请求必须伪装成浏览器")
            self.assertNotIn("python-httpx", request.headers["user-agent"])
        self.assertEqual(sent[0].headers["authorization"], "Bearer k", "默认头不能覆盖单次请求的认证头")
        self.assertTrue(llm.headers["user-agent"].startswith("Mozilla/5.0"))
        self.assertEqual(llm.headers["authorization"], "Bearer sk-k")
        await llm.aclose()

    async def test_cancelled_operation_closes_its_client(self):
        entered = asyncio.Event()
        clients = []

        async def operation():
            async with borrow_client("image-generation", 5, base_url="https://provider.example") as client:
                clients.append(client)
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(operation())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(clients[0].is_closed)

    async def test_large_json_parser_runs_in_worker_while_loop_remains_responsive(self):
        main_thread = threading.get_ident()
        entered, release = threading.Event(), threading.Event()
        original = json.loads

        def parse(value):
            self.assertNotEqual(threading.get_ident(), main_thread)
            entered.set()
            self.assertTrue(release.wait(3))
            return original(value)

        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'{"data":[]}'))) as client:
            with patch.object(service.json, "loads", side_effect=parse):
                task = asyncio.create_task(service._provider_json(client, "GET", "https://fixture.example/poll", {}))
                try:
                    async with asyncio.timeout(2):
                        while not entered.is_set():
                            await asyncio.sleep(0.005)
                    self.assertFalse(task.done())
                finally:
                    release.set()
                self.assertEqual(await task, {"data": []})

    async def test_fragmented_response_is_bounded_after_decoding(self):
        class Fragments(httpx.AsyncByteStream):
            async def __aiter__(self):
                for _ in range(1000):
                    yield b"x" * 100

        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Fragments()))) as client:
            async with client.stream("GET", "https://fixture.example") as response:
                self.assertEqual(len(await service._read_limited(response, 100_000)), 100_000)
            async with client.stream("GET", "https://fixture.example") as response:
                with self.assertRaises(ValueError):
                    await service._read_limited(response, 99_999)

    async def test_waiting_for_media_is_cancellable_and_does_not_hide_other_errors(self):
        with patch.object(service, "normalize_image", side_effect=HTTPException(429)) as normalize:
            with self.assertRaises(TimeoutError):
                async with asyncio.timeout(0.12):
                    await service._normalize_when_available(b"fixture")
            self.assertGreater(normalize.call_count, 0)
            calls = normalize.call_count
            await asyncio.sleep(0.1)
            self.assertEqual(normalize.call_count, calls)
        with patch.object(service, "normalize_image", side_effect=ValueError("invalid image")) as normalize:
            with self.assertRaises(ValueError):
                await service._normalize_when_available(b"fixture")
            self.assertEqual(normalize.call_count, 1)


DEAD_IP = "104.21.53.109"
LIVE_IP = "172.67.212.55"


def _probe(address, **kwargs):
    """模拟境内访问部分 Cloudflare 地址时首条记录静默丢包。"""
    if address[0] == DEAD_IP:
        raise OSError("connection timed out")
    return MagicMock()


class ProviderIpFallback(unittest.IsolatedAsyncioTestCase):
    def test_single_address_needs_no_probe(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("不应发起探测")) as create:
            self.assertEqual(reachable_ip([LIVE_IP], 443), LIVE_IP)
        create.assert_not_called()

    def test_unreachable_first_address_falls_back_to_the_next(self):
        with patch.object(socket, "create_connection", side_effect=_probe) as create:
            self.assertEqual(reachable_ip([DEAD_IP, LIVE_IP], 443), LIVE_IP)
        self.assertEqual([call.args[0][0] for call in create.call_args_list], [DEAD_IP, LIVE_IP])

    def test_all_unreachable_keeps_the_first_address(self):
        with patch.object(socket, "create_connection", side_effect=OSError):
            self.assertEqual(reachable_ip([DEAD_IP, LIVE_IP], 443), DEAD_IP)

    async def test_provider_request_pins_to_a_reachable_ip(self):
        sent = []
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (DEAD_IP, 443)),
                     (socket.AF_INET, socket.SOCK_STREAM, 6, "", (LIVE_IP, 443))]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: sent.append(request) or httpx.Response(200)),
                                     event_hooks={"request": [pin_provider_request]}, follow_redirects=False) as client:
            with patch.object(get_settings(), "provider_allow_private", False), \
                    patch.object(socket, "getaddrinfo", return_value=addresses), \
                    patch.object(socket, "create_connection", side_effect=_probe):
                await client.post("https://provider.invalid/v1/images/generations", headers={"Authorization": "Bearer fixture"})
        self.assertEqual(str(sent[0].url), f"https://{LIVE_IP}/v1/images/generations")
        self.assertEqual(sent[0].headers["host"], "provider.invalid")
        self.assertEqual(sent[0].extensions["sni_hostname"], "provider.invalid")

    async def test_image_download_skips_the_unreachable_address(self):
        sent = []
        original = httpx.AsyncClient
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (DEAD_IP, 443)),
                     (socket.AF_INET, socket.SOCK_STREAM, 6, "", (LIVE_IP, 443))]

        def handle(request):
            sent.append(request)
            return httpx.Response(200, content=b"fixture")

        with patch.object(service.httpx, "AsyncClient", side_effect=lambda **kw: original(**kw, transport=httpx.MockTransport(handle))), \
                patch.object(socket, "getaddrinfo", return_value=addresses), \
                patch.object(socket, "create_connection", side_effect=_probe):
            self.assertEqual(await service._public_image("https://images.invalid/output.png"), b"fixture")
        self.assertEqual(sent[0].url.host, LIVE_IP)
        self.assertEqual(sent[0].headers["host"], "images.invalid")
