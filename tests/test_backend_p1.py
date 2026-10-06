"""P1 成本、租约、缓存、上传准入及会话续期回归；外部服务全部模拟。"""
import io
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import test_backend_reliability as reliability
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.testclient import TestClient
from PIL import Image

from app.cache_policy import CachePolicy
from app.config import get_settings
from app.db import db
from app.deps import require_user
from app.routers import auth, generate, library
from app.services import generation_budget, mini_auth, resource_admission
from app.services import generation_control as control
from app.services.generation_results import completed_sections
from app.services.llm_client import LLMClient, OutputTruncated
from app.services.rate_limit import client_key


class BudgetLeaseContracts(unittest.TestCase):
    setUp = reliability.BackendReliability.setUp

    def test_budget_is_atomic_and_rolls_over(self):
        settings = get_settings()
        with patch.object(settings, "generation_global_daily_tokens", 100), patch.object(settings, "generation_global_daily_images", 2):
            def reserve(_):
                try:
                    generation_budget.reserve(tokens=25)
                    return True
                except HTTPException as error:
                    self.assertEqual(error.status_code, 429)
                    return False
            with ThreadPoolExecutor(max_workers=8) as workers:
                self.assertEqual(sum(workers.map(reserve, range(12))), 4)
            generation_budget.reserve(images=2)
            with self.assertRaises(HTTPException):
                generation_budget.reserve(images=1)
            with db() as conn:
                conn.execute("UPDATE generation_budget SET created_at = ?", (int(time.time()) - 86401,))
            generation_budget.reserve(tokens=100, images=2)

    def test_heartbeat_and_terminal_status_are_monotonic(self):
        control._begin(self.user.id, "lease", "batch", {})
        with db() as conn:
            conn.execute("UPDATE generation_requests SET lease_expires_at = 1 WHERE request_id = 'lease'")
        control._renew(self.user.id, "lease")
        control.reclaim_expired()
        self.assertEqual(control.request_status(self.user.id, "lease")["status"], "running")
        control._finish(self.user.id, "lease", control.Usage(), "succeeded", {"sections": []})
        control._finish(self.user.id, "lease", control.Usage(), "unknown")
        self.assertEqual(control.request_status(self.user.id, "lease")["status"], "succeeded")
        control._begin(self.user.id, "dead", "batch", {})
        with db() as conn:
            conn.execute("UPDATE generation_requests SET lease_expires_at = 1 WHERE request_id = 'dead'")
        control.reclaim_expired()
        self.assertEqual(control.request_status(self.user.id, "dead")["status"], "unknown")

    def test_batch_over_thirty_rejected_before_model(self):
        body = {**self.body, "items": [
            {"section_id": str(i), "game_type": "fill_blank", "question_count": 20} for i in range(2)]}
        response, model = reliability.BackendReliability.send(self, body=body)
        self.assertEqual(response.status_code, 422)
        model.assert_not_awaited()

    def test_original_instance_recovers_result_after_lease_cleanup(self):
        control._begin(self.user.id, "late", "batch", {})
        with db() as conn:
            conn.execute("UPDATE generation_requests SET lease_expires_at = 1 WHERE request_id = 'late'")
        control.reclaim_expired(limit=100)
        self.assertEqual(control.request_status(self.user.id, "late")["status"], "unknown")
        result = {"sections": [{"questions": [{"stem": "late result"}]}]}
        usage = control.Usage(model_calls=1, reported_calls=1, prompt_tokens=12, completion_tokens=34)
        with patch.object(control, "_INSTANCE", "another-worker"):
            control._finish(self.user.id, "late", usage, "succeeded", result)
        self.assertIsNone(control.request_status(self.user.id, "late")["result"])
        control._finish(self.user.id, "late", usage, "succeeded", result)
        self.assertEqual(control.request_status(self.user.id, "late")["result"], result)
        self.assertEqual(control._begin(self.user.id, "late", "batch", {}), result)
        with db() as conn:
            row = conn.execute("SELECT model_calls, prompt_tokens, completion_tokens FROM generation_requests WHERE request_id = 'late'").fetchone()
        self.assertEqual(tuple(row.values()), (1, 12, 34))
        control._finish(self.user.id, "late", control.Usage(), "unknown")
        self.assertEqual(control.request_status(self.user.id, "late")["status"], "succeeded")

    def test_confirmed_failure_cannot_be_overwritten_by_late_completion(self):
        control._begin(self.user.id, "failed-terminal", "batch", {})
        control._finish(self.user.id, "failed-terminal", control.Usage(), "unknown", error=(503, {"error": "interrupted"}))
        control._finish(self.user.id, "failed-terminal", control.Usage(), "succeeded", {"sections": []})
        status = control.request_status(self.user.id, "failed-terminal")
        self.assertEqual(status["status"], "unknown")
        self.assertEqual(status["error_status"], 503)
        self.assertIsNone(status["result"])

    def test_cleanup_rechecks_tasks_that_finish_or_renew_while_waiting_for_lock(self):
        for finished in (True, False):
            with self.subTest(finished=finished):
                request_id = "cleanup-finish" if finished else "cleanup-renew"
                control._begin(self.user.id, request_id, "batch", {})
                with db() as conn:
                    conn.execute("UPDATE generation_requests SET lease_expires_at = 1 WHERE request_id = ?", (request_id,))
                with ThreadPoolExecutor(max_workers=1) as workers:
                    with db() as blocker:
                        pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
                        if finished:
                            blocker.execute("UPDATE generation_requests SET status = 'succeeded', result_json = ? WHERE request_id = ?",
                                            (json.dumps({"sections": []}), request_id))
                        else:
                            blocker.execute("UPDATE generation_requests SET lease_expires_at = ? WHERE request_id = ?",
                                            (int(time.time()) + 90, request_id))
                        pending = workers.submit(control.reclaim_expired, 100)
                        deadline = time.monotonic() + 5
                        waiting = False
                        while time.monotonic() < deadline:
                            with db() as observer:
                                waiting = observer.execute("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname = current_database() AND ? = ANY(pg_blocking_pids(pid)))", (pid,)).fetchone()[0]
                            if waiting:
                                break
                            time.sleep(0.01)
                        self.assertTrue(waiting, "清理必须先等待生成事务的行锁")
                    pending.result(timeout=5)
                self.assertEqual(control.request_status(self.user.id, request_id)["status"], "succeeded" if finished else "running")

    def test_truncation_preserves_complete_sections_and_replays_without_repairs(self):
        self.body['items'].append({'section_id': 's2', 'game_type': 'fill_blank', 'question_count': 2})
        raw = '<think>分析</think>```json\n{"sections": [' + json.dumps(reliability.section()) + ', {"section_id": "s2", "questions": ['
        with patch.object(get_settings(), 'generation_repair_limit', 3), patch.object(generate, '_call_llm_and_parse', side_effect=OutputTruncated(raw)) as model:
            response = self.client.post('/api/v1/generate-batch', json=self.body, headers={'X-Request-ID': 'truncated'})
            replay = self.client.post('/api/v1/generate-batch', json=self.body, headers={'X-Request-ID': 'truncated'})
        self.assertEqual(response.status_code, 422, response.text)
        partial = response.json()['detail']['partial_sections']
        self.assertEqual([value['section_id'] for value in partial], ['s1'])
        self.assertEqual(len(partial[0]['questions']), 2)
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(model.await_count, 1)
        status = self.client.get('/api/v1/me/generations/truncated').json()
        self.assertEqual(status['error']['partial_sections'], partial)

    def test_truncation_does_not_accept_ambiguous_invalid_or_short_sections(self):
        candidates = [
            [reliability.section(), reliability.section()],
            [reliability.section(count=1)],
            [{**reliability.section(), 'section_id': None}],
            [{**reliability.section(), 'game_type': 'reading'}],
            [{**reliability.section(), 'questions': [{'stem': '缺答案'}]}],
        ]
        for index, sections in enumerate(candidates):
            with self.subTest(index=index), patch.object(get_settings(), 'generation_repair_limit', 3), patch.object(generate, '_call_llm_and_parse', side_effect=OutputTruncated(json.dumps({'sections': sections}))) as model:
                response = self.client.post('/api/v1/generate-batch', json=self.body, headers={'X-Request-ID': f'bad-{index}'})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()['detail']['partial_sections'], [])
                self.assertEqual(model.await_count, 1)

    def test_sliding_reader_session_preserves_token_and_revocation(self):
        result = mini_auth.register("reader-p1", "password-test", admin=True)
        token = result["token"]
        with db() as conn:
            conn.execute("UPDATE mini_user_sessions SET expires_at = ?", (int(time.time()) + 60,))
        mini_auth.resolve_session(token)
        with db() as conn:
            expires = conn.execute("SELECT expires_at FROM mini_user_sessions WHERE token_hash = ?", (mini_auth.digest(token),)).fetchone()[0]
        self.assertGreater(expires, int(time.time()) + 2 * 86400)
        mini_auth.logout(token)
        with self.assertRaises(HTTPException):
            mini_auth.resolve_session(token)


class HttpContracts(unittest.IsolatedAsyncioTestCase):
    async def test_ip_denial_does_not_create_username_key(self):
        request = SimpleNamespace(client=SimpleNamespace(host="2001:db8::1"))
        with patch.object(auth, "allow", return_value=False) as limiter:
            with self.assertRaises(HTTPException):
                await auth.login(auth.Credentials(username="someone", password="password"), request, Response())
            limiter.assert_called_once_with("login-ip:2001:db8::/64", 30, 300)
        self.assertEqual(client_key("2001:db8::dead"), client_key("2001:db8::1"))
        self.assertEqual(client_key("::ffff:192.0.2.1"), "192.0.2.1")

    async def test_busy_zip_does_not_read_upload(self):
        app = FastAPI()
        app.include_router(library.router)
        app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=1)
        reads = []
        async def body():
            reads.append(True)
            yield b"zip"
        with patch.object(resource_admission._slots, "acquire", return_value=False), patch.object(library.library, "get_paper", return_value={}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.put("/api/v1/library/papers/paper/files", content=body(), headers={"content-type": "application/zip"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(reads, [])

    async def test_truncated_provider_does_not_retry(self):
        client = LLMClient()
        response = httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]},
                                  request=httpx.Request("POST", "https://fixture/chat/completions"))
        try:
            with patch.object(httpx.AsyncClient, "send", return_value=response) as post:
                with self.assertRaises(HTTPException) as raised:
                    await client.chat([{"role": "user", "content": "hello"}], base_url="https://fixture", api_key="fake")
                self.assertEqual(raised.exception.detail["code"], "generation_truncated")
                self.assertIsInstance(raised.exception, OutputTruncated)
                self.assertEqual(raised.exception.partial_text, 'partial')
                self.assertEqual(post.call_count, 1)
        finally:
            await client.close()


class CacheAndMediaContracts(unittest.TestCase):
    def test_partial_parser_only_decodes_closed_top_level_sections(self):
        section = {'section_id': 's1', 'questions': [{'stem': '括号 } ] 和引号 \"'}]}
        text = json.dumps(section)
        self.assertEqual(completed_sections('{"topic": "test", "sections": [' + text + ', {"section_id":'), [section])
        self.assertEqual(completed_sections('{"topic": {"sections": [' + text + ']}'), [])
        self.assertEqual(completed_sections('{"sections": [' + text[:-1]), [])
        self.assertEqual(completed_sections('<think>{"sections": [' + text), [])

    def test_cache_headers_preserve_explicit_public_assets(self):
        app = FastAPI()
        app.add_middleware(CachePolicy)
        @app.get("/api/private")
        def private():
            raise HTTPException(401)
        @app.get("/api/asset")
        def asset():
            return Response(b"image", headers={"Cache-Control": "public, max-age=60"})
        @app.get("/")
        def home():
            return HTMLResponse("html")
        @app.get("/assets/main-hash.js")
        def javascript():
            return Response("js")
        with TestClient(app) as client:
            response = client.get("/api/private")
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertIn("Authorization", response.headers["vary"])
            self.assertEqual(client.get("/api/asset").headers["cache-control"], "public, max-age=60")
            self.assertEqual(client.get("/").headers["cache-control"], "no-cache")
            self.assertIn("immutable", client.get("/assets/main-hash.js").headers["cache-control"])

    def test_oversized_avatar_rejected_before_decode(self):
        import base64

        from app.services.mini_avatars import normalize_image
        output = io.BytesIO()
        Image.new("RGB", (2100, 2000)).save(output, "PNG")
        with patch.object(Image.Image, "load", side_effect=AssertionError("pixels decoded")):
            with self.assertRaises(HTTPException) as raised:
                normalize_image(base64.b64encode(output.getvalue()).decode())
        self.assertEqual(raised.exception.status_code, 413)
