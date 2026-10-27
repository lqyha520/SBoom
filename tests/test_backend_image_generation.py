"""Image generation contracts. Disposable PostgreSQL only; all provider I/O mocked."""

import asyncio
import base64
import io
import json
import socket
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import pg_support

pg_support.install_module_database({"SECRET_KEY": "image-tests-only", "ADMIN_USERNAME": "", "ADMIN_PASSWORD": ""})

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app import db as database
from app import security
from app.deps import SESSION_COOKIE
from app.models.image_generation import ImageModelConfig
from app.models.model_profiles import ImageModelProfile
from app.routers import image_generation, me
from app.services import image_config, user_store
from app.services import image_generation as service


def png():
    stream = io.BytesIO()
    Image.new("RGB", (24, 32), "white").save(stream, format="PNG")
    return stream.getvalue()


class ImageGenerationContracts(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        pg_support.case_database(self.stack)
        from app.config import get_settings
        self.stack.enter_context(patch.object(get_settings(), "provider_failure_threshold", 1000))
        self.stack.enter_context(patch.object(get_settings(), "archive_local_dir", self.stack.enter_context(tempfile.TemporaryDirectory(prefix="lc-image-test-"))))
        database.init_db()
        self.user = user_store.create_user("image-teacher", "test-password")
        self.admin = user_store.create_user("image-admin", "test-password", role="admin")
        self.other = user_store.create_user("image-other", "test-password")
        app = FastAPI()
        app.include_router(image_generation.router)
        app.include_router(me.router)
        self.client = self.stack.enter_context(TestClient(app))
        self.login(self.user)
        self.config = {"baseUrl": "https://provider.invalid/v1", "model": "custom-image-model", "apiKey": "secret-image-test", "timeout": 60, "size": "1024x1536", "responseFormat": "auto"}
        image_config.save_config(ImageModelConfig(**self.config))
        self.body = {"grade": "小学三年级", "subject": "数学", "keyword": "两位数加减法", "difficulty": "medium",
                     "items": [{"game_type": "fill_blank", "question_count": 4}, {"game_type": "quiz", "question_count": 2}], "style": "black_white", "requirements": "用小动物辅助理解"}
        self.calls = []
        self.handler = lambda req: httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png()).decode()}]})
        def handle(req):
            self.calls.append(req)
            return self.handler(req)
        original_client = httpx.AsyncClient
        self.stack.enter_context(patch.object(service.httpx, "AsyncClient", side_effect=lambda **kw: original_client(**kw, transport=httpx.MockTransport(handle))))
        self.system_resolver = socket.getaddrinfo
        self.provider_addresses = dict.fromkeys(
            ("provider.invalid", "images.invalid", "public.invalid"), "93.184.216.34",
        )
        self.provider_addresses["internal.invalid"] = "127.0.0.1"

        def resolve(host, *args, **kwargs):
            name = host.decode("ascii") if isinstance(host, bytes) else host
            if name in self.provider_addresses:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (self.provider_addresses[name], 443))]
            # socket is shared with psycopg: database DNS must remain real.
            return self.system_resolver(host, *args, **kwargs)

        self.stack.enter_context(patch("app.provider_policy.socket.getaddrinfo", side_effect=resolve))

    def login(self, user):
        self.client.cookies.set(SESSION_COOKIE, security.create_token(user.id))

    def send(self, request_id="image-one", body=None):
        return self.client.post("/api/v1/generate-image", json=body or self.body, headers={"X-Request-ID": request_id, "X-Workspace-User": str(self.user.id)})

    def test_provider_dns_fixture_preserves_localhost_resolution(self):
        self.assertEqual(
            socket.getaddrinfo("localhost", 5432, type=socket.SOCK_STREAM),
            self.system_resolver("localhost", 5432, type=socket.SOCK_STREAM),
        )

    def test_prompt_uses_all_conditions_without_a_model_call(self):
        response = self.client.post("/api/v1/image-generation/prompt", json=self.body)
        self.assertEqual(response.status_code, 200, response.text)
        prompt = response.json()["prompt"]
        for value in ["小学三年级", "数学", "两位数加减法", "填空题 4 道", "选择题 2 道", "黑白打印", "小动物"]:
            self.assertIn(value, prompt)
        self.assertIn("不使用工作台的试卷模板", prompt)
        self.assertIn("每种题量都必须准确落实", prompt)
        self.assertNotIn("题量自动安排", prompt)
        self.assertEqual(self.calls, [])

    def test_prompt_accepts_omitted_null_and_mixed_quantities(self):
        for items in [
            [{"game_type": "fill_blank"}, {"game_type": "quiz", "question_count": None}],
            [{"game_type": "fill_blank"}, {"game_type": "quiz", "question_count": 6}],
        ]:
            with self.subTest(items=items):
                response = self.client.post("/api/v1/image-generation/prompt", json={**self.body, "items": items})
                self.assertEqual(response.status_code, 200, response.text)
                prompt = response.json()["prompt"]
                self.assertIn("填空题（题量自动安排）", prompt)
                self.assertIn("未指定题量的题型", prompt)
                self.assertIn("整张合计不超过 24 道", prompt)
                self.assertNotIn("填空题 4 道", prompt)
                self.assertNotIn("None", prompt)
                if items[1]["question_count"] is not None:
                    self.assertIn("选择题 6 道", prompt)
                else:
                    self.assertIn("选择题（题量自动安排）", prompt)
        self.assertEqual(self.calls, [])

    def test_grade_and_subject_only_use_their_curriculum_and_age_appropriate_types(self):
        body = {"grade": "小学一年级", "subject": "数学"}
        response = self.client.post("/api/v1/image-generation/prompt", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        prompt = response.json()["prompt"]
        scope = service.knowledge_scope_service.get_scope(body["grade"], body["subject"])
        self.assertIn("知识点：自动安排", prompt)
        self.assertIn("题型及题量：自动安排", prompt)
        self.assertIn("、".join(scope.allowed), prompt)
        self.assertIn("、".join(scope.forbidden), prompt)
        types_line = next(line for line in prompt.splitlines() if line.startswith("题型及题量："))
        self.assertIn("1 至 5 种", types_line)
        self.assertNotIn("简便计算", types_line)
        self.assertNotIn("脱式计算", types_line)
        self.assertIn("整张合计不超过 24 道", prompt)
        self.assertEqual(self.calls, [])

    def test_automatic_topics_use_official_books_and_reject_unknown_scopes(self):
        body = {"grade": "小学一年级", "subject": "数学"}
        response = self.client.post("/api/v1/image-generation/prompt", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("1221001101241", response.json()["prompt"])
        self.assertIn("100以内的笔算加、减法", response.json()["prompt"])
        self.assertNotIn("认识钟表", response.json()["prompt"])
        for index, change in enumerate([{"grade": "未知年级"}, {"subject": "未知科目"}]):
            self.assertEqual(self.send(f"unknown-auto-{index}", {**body, **change}).status_code, 400)
        scope = service.knowledge_scope_service.get_scope(body["grade"], body["subject"])
        with patch.object(service.knowledge_scope_service, "get_scope", return_value=scope.model_copy(update={"allowed": []})):
            self.assertEqual(self.send("no-auto-content", body).status_code, 400)
        self.assertEqual(self.calls, [])

    def test_automatic_requests_keep_manual_topics_or_types_and_replay_without_duplicates(self):
        body = {"grade": "小学一年级", "subject": "数学"}
        first = self.send("automatic-worksheet", body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self.send("automatic-worksheet", {**body, "keyword": "  ", "items": []}).json(), first.json())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.send("automatic-worksheet", {**body, "keyword": "加法"}).status_code, 409)
        for change, required, automatic in [
            ({"keyword": "20以内加法"}, "知识点：20以内加法", "题型及题量：自动安排"),
            ({"items": [{"game_type": "fill_blank", "question_count": 6}]}, "填空题 6 道", "知识点：自动安排"),
        ]:
            response = self.client.post("/api/v1/image-generation/prompt", json={**body, **change})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn(required, response.json()["prompt"])
            self.assertIn(automatic, response.json()["prompt"])

    def test_grade_and_subject_remain_required(self):
        for body in [{"grade": "小学一年级"}, {"subject": "数学"}, {"grade": "小学一年级", "subject": ""},
                     {"grade": "小学一年级", "subject": "  "}, {"grade": "", "subject": "数学"}]:
            with self.subTest(body=body):
                self.assertEqual(self.send(body=body).status_code, 422)
        self.assertEqual(self.calls, [])

    def test_optional_quantity_generation_replay_normalizes_omitted_and_null(self):
        body = {**self.body, "items": [{"game_type": "quiz"}, {"game_type": "fill_blank", "question_count": 3}]}
        first = self.send("auto-count", body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertIn("选择题（题量自动安排）", json.loads(self.calls[0].content)["prompt"])
        self.assertIn("填空题 3 道", json.loads(self.calls[0].content)["prompt"])
        body["items"][0]["question_count"] = None
        replay = self.send("auto-count", body)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json(), first.json())
        body["items"][0]["question_count"] = 4
        self.assertEqual(self.send("auto-count", body).status_code, 409)
        self.assertEqual(len(self.calls), 1)

    def test_quantity_validation_reserves_capacity_for_automatic_types(self):
        for count in [0, -1, 21, 1.5, True, "4"]:
            with self.subTest(count=count):
                response = self.send(body={**self.body, "items": [{"game_type": "quiz", "question_count": count}]})
                self.assertEqual(response.status_code, 422, response.text)
        for count, expected in [(3, 200), (4, 422)]:
            response = self.client.post("/api/v1/image-generation/prompt", json={**self.body, "items": [
                {"game_type": "quiz", "question_count": 20},
                {"game_type": "fill_blank", "question_count": count},
                {"game_type": "true_false"},
            ]})
            self.assertEqual(response.status_code, expected, response.text)
        self.assertEqual(self.calls, [])

    def test_config_is_admin_only_encrypted_and_independent(self):
        self.assertEqual(self.client.get("/api/v1/admin/image-config").status_code, 403)
        self.login(self.admin)
        self.assertNotIn("secret-image-test", self.client.get("/api/v1/admin/image-config").text)
        with database.db() as conn:
            raw = conn.execute("SELECT value FROM app_config WHERE key = ?", (image_config.KEY,)).fetchone()[0]
        self.assertNotIn("secret-image-test", raw)
        response = self.client.put("/api/v1/admin/image-config", json={**self.config, "apiKey": "", "model": "new-image-model"})
        self.assertTrue(response.json()["hasKey"])
        self.assertEqual(image_config.get_config(with_key=True)["api_key"], "secret-image-test")
        self.assertEqual(self.client.delete("/api/v1/admin/image-config").status_code, 200)
        self.assertFalse(self.client.get("/api/v1/image-generation/options").json()["configured"])

    def test_config_validation_rejects_credentials_query_and_unknown_fields(self):
        self.login(self.admin)
        for change in [{"baseUrl": "https://user:secret@provider.invalid/v1"}, {"baseUrl": "https://provider.invalid/v1?key=secret"}, {"timeout": 601}, {"size": "oversized"}, {"unexpected": True}]:
            self.assertEqual(self.client.put("/api/v1/admin/image-config", json={**self.config, **change}).status_code, 422)

    def configure_failover(self):
        image_config.save_models([
            ImageModelProfile(**{**self.config, "apiKey": ""}, id="legacy"),
            ImageModelProfile(**{**self.config, "apiKey": "", "model": "disabled"}, id="off", enabled=False),
            ImageModelProfile(**{**self.config, "apiKey": "backup-key", "model": "backup-image"}, id="backup"),
        ])

    def test_image_failover_switches_on_timeout_http_and_invalid_images(self):
        self.configure_failover()
        good = self.handler
        for index, failure in enumerate([
            httpx.ReadTimeout("upstream possibly billed"), httpx.Response(401), httpx.Response(429),
            httpx.Response(503), httpx.Response(200, json={"data": [{"b64_json": "bad image"}]}),
        ]):
            with self.subTest(index=index):
                self.calls.clear()

                def handle(req, failure=failure):
                    if json.loads(req.content)["model"] == "custom-image-model":
                        if isinstance(failure, Exception):
                            raise failure
                        return failure
                    return good(req)

                self.handler = handle
                result = self.send(f"failover-{index}")
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual([json.loads(req.content)["model"] for req in self.calls], ["custom-image-model", "backup-image"])
                self.assertEqual(self.calls[1].headers["authorization"], "Bearer backup-key")
                self.assertEqual(self.send(f"failover-{index}").json(), result.json())
                self.assertEqual(len(self.calls), 2)
                status = self.client.get(f"/api/v1/me/generations/failover-{index}").json()
                self.assertEqual(status["usage"]["model_calls"], 2)
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT SUM(images) FROM generation_budget").fetchone()[0], 10)

    def test_image_all_fail_and_budget_exhaustion_never_loop(self):
        self.configure_failover()
        self.handler = lambda req: httpx.Response(503)
        result = self.send("all-failed")
        self.assertEqual(result.status_code, 502)
        self.assertEqual(self.send("all-failed").json(), result.json())
        self.assertEqual(len(self.calls), 2)
        from app.config import get_settings
        with patch.object(get_settings(), "generation_global_daily_images", 3):
            result = self.send("budget-failed")
        self.assertEqual(result.status_code, 429)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.client.get("/api/v1/me/generations/budget-failed").json()["usage"]["model_calls"], 1)

    def test_http_400_failover_reports_each_attempt_without_leaking_provider_body(self):
        self.configure_failover()

        def rejected(req):
            primary = json.loads(req.content)["model"] == "custom-image-model"
            return httpx.Response(400 if primary else 403, json={"error": {
                "param": "size", "message": "invalid size secret-image-test backup-key https://private.invalid prompt",
            }})

        self.handler = rejected
        result = self.send("rejected-chain")
        self.assertEqual(result.status_code, 502)
        detail = result.json()["detail"]
        self.assertEqual(detail["code"], "model_chain_exhausted")
        self.assertIn("2 个启用模型", detail["error"])
        self.assertEqual([item["upstream_status"] for item in detail["attempts"]], [400, 403])
        self.assertEqual([item["reason"] for item in detail["attempts"]], ["size", "authentication"])
        for secret in ("secret-image-test", "backup-key", "private.invalid", "prompt"):
            self.assertNotIn(secret, result.text)
        self.assertEqual(self.send("rejected-chain").json(), result.json())
        self.assertEqual(len(self.calls), 2)

    def test_error_body_invalid_or_oversized_still_switches_to_backup(self):
        self.configure_failover()
        good = self.handler
        for index, payload in enumerate([b"<html>private error</html>", b"x" * 9000, b'{"error": []}']):
            self.calls.clear()
            self.handler = lambda req, payload=payload: (
                httpx.Response(400, content=payload) if json.loads(req.content)["model"] == "custom-image-model"
                else good(req)
            )
            result = self.send(f"bad-error-{index}")
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(len(self.calls), 2)

    def test_slow_error_body_is_closed_and_does_not_stall_failover(self):
        self.configure_failover()
        good = self.handler

        class SlowError(httpx.AsyncByteStream):
            closed = False

            async def __aiter__(self):
                yield b'{"error":'
                await asyncio.Event().wait()

            async def aclose(self):
                self.closed = True

        stream = SlowError()
        self.handler = lambda req: (
            httpx.Response(400, stream=stream) if json.loads(req.content)["model"] == "custom-image-model"
            else good(req)
        )
        result = self.send("slow-error")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(stream.closed)

    def test_image_multi_config_masks_keys_reorders_and_can_disable_all(self):
        self.configure_failover()
        self.login(self.admin)
        value = self.client.get("/api/v1/admin/image-config").json()
        self.assertEqual(len(value["models"]), 3)
        self.assertNotIn("secret-image-test", json.dumps(value))
        self.assertNotIn("backup-key", json.dumps(value))
        payload = [{**model, "apiKey": ""} for model in reversed(value["models"])]
        for model in payload:
            model.pop("hasKey")
            model["enabled"] = False
        result = self.client.put("/api/v1/admin/image-config", json={"revision": value["revision"], "models": payload})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(image_config.get_config(with_key=True)["models"][0]["api_key"], "backup-key")
        self.assertFalse(self.client.get("/api/v1/image-generation/options").json()["configured"])
        self.login(self.user)
        self.assertEqual(self.send("disabled").status_code, 400)
        self.assertEqual(self.calls, [])

    def test_image_save_and_clear_reject_stale_revision(self):
        self.configure_failover()
        self.login(self.admin)
        original = self.client.get("/api/v1/admin/image-config").json()
        latest = image_config.save_models([ImageModelProfile(**self.config, id="new")])
        for result in [
            self.client.put("/api/v1/admin/image-config", json={"revision": original["revision"], "models": []}),
            self.client.delete("/api/v1/admin/image-config", headers={"If-Match": original["revision"]}),
            self.client.delete("/api/v1/admin/image-config"),
        ]:
            self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(self.client.get("/api/v1/admin/image-config").json(), latest)
        self.assertEqual(self.client.delete("/api/v1/admin/image-config", headers={"If-Match": latest["revision"]}).status_code, 200)

    def test_generation_round_trip_and_idempotent_replay(self):
        response = self.send()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual((result["width"], result["height"], result["mime_type"]), (24, 32, "image/png"))
        self.assertEqual(result["request_id"], "image-one")
        self.assertNotIn("b64_json", result)
        asset = self.client.get(result["url"])
        self.assertEqual(asset.status_code, 200)
        with Image.open(io.BytesIO(asset.content)) as decoded:
            self.assertEqual(decoded.format, "PNG")
        call = self.calls[0]
        body = json.loads(call.content)
        self.assertEqual(str(call.url), "https://93.184.216.34/v1/images/generations")
        self.assertEqual(call.headers["host"], "provider.invalid")
        self.assertEqual(call.extensions["sni_hostname"], "provider.invalid")
        self.assertEqual(body["model"], "custom-image-model")
        self.assertEqual(body["n"], 1)
        self.assertNotIn("response_format", body)
        self.assertEqual(call.headers["authorization"], "Bearer secret-image-test")
        self.assertEqual(self.send().json(), result)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.send(body={**self.body, "keyword": "不同知识点"}).status_code, 409)
        recovered = self.client.get("/api/v1/me/generations/image-one").json()
        self.assertEqual(recovered["kind"], "image")
        self.assertEqual(recovered["result"], result)
        with database.db() as conn:
            saved = conn.execute("SELECT result_json FROM generation_requests WHERE user_id = ? AND request_id = ?", (self.user.id, "image-one")).fetchone()[0]
            self.assertLess(len(saved), 6000)
            self.assertNotIn("b64_json", saved)
        self.login(self.other)
        self.assertEqual(self.client.get(result["url"]).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/me/generations/image-one").status_code, 404)

    def test_paid_image_waits_for_local_media_capacity_without_another_provider_call(self):
        from fastapi import HTTPException

        normalize = service.normalize_image
        attempts = 0

        def busy_once(raw):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise HTTPException(429, detail={"error": "图片处理繁忙"})
            return normalize(raw)

        with patch.object(service, "normalize_image", side_effect=busy_once):
            response = self.send("media-busy")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(attempts, 2)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.client.get(response.json()["url"]).status_code, 200)
        self.assertEqual(self.send("media-busy").json(), response.json())
        self.assertEqual(len(self.calls), 1)

    def test_local_media_timeout_does_not_start_a_paid_backup(self):
        from fastapi import HTTPException

        self.configure_failover()
        config = image_config.get_config(with_key=True)
        for profile in config['models']:
            profile['timeout'] = 0.12
        with patch.object(image_config, 'get_config', return_value=config), \
                patch.object(service, 'normalize_image', side_effect=HTTPException(429)):
            response = self.send('media-timeout')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['detail']['code'], 'image_processing_busy')
        self.assertEqual(len(self.calls), 1)

    def test_batch_pages_are_independent_and_prompt_contains_page_position(self):
        results = []
        for index in range(1, 4):
            body = {**self.body, "image_count": 3, "image_index": index}
            response = self.send(f"batch-{index}", body)
            self.assertEqual(response.status_code, 200)
            results.append(response.json())
            prompt = json.loads(self.calls[-1].content)["prompt"]
            self.assertIn(f"共 3 张，这是第 {index} 张", prompt)
            self.assertIn("不要把多张图拼在一起", prompt)
            self.assertIn("填空题 4 道", prompt)
            self.assertEqual(json.loads(self.calls[-1].content)["n"], 1)
            self.assertEqual(self.send(f"batch-{index}", body).json(), results[-1])
        self.assertEqual(len(self.calls), 3)
        for index, result in enumerate(results, 1):
            self.assertEqual(self.client.get(f"/api/v1/me/generations/batch-{index}").json()["result"], result)

    def test_batch_count_and_page_index_are_bounded_before_provider_call(self):
        for change in ({"image_count": 0}, {"image_count": 11}, {"image_count": 1.5},
                       {"image_index": 0}, {"image_index": 2}, {"image_count": 3, "image_index": 4}):
            self.assertEqual(self.send(body={**self.body, **change}).status_code, 422)
        self.assertEqual(self.calls, [])

    def test_auth_owner_and_request_validation_precede_provider(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.post("/api/v1/generate-image", json=self.body).status_code, 401)
        self.login(self.other)
        self.assertEqual(self.send().status_code, 409)
        self.login(self.user)
        for change in [{"keyword": None}, {"items": None}, {"items": [{"game_type": "bogus", "question_count": 4}]}, {"layout": {}}, {"api_key": "client-key"}, {"items": self.body["items"] * 2}, {"items": [{"game_type": "quiz", "question_count": 20}, {"game_type": "fill_blank", "question_count": 20}]}]:
            self.assertEqual(self.send(body={**self.body, **change}).status_code, 422)
        self.assertEqual(self.send("unsupported", {**self.body, "grade": "大学一年级"}).status_code, 400)
        self.assertEqual(self.send("too-young", {**self.body, "grade": "小学一年级", "items": [{"game_type": "smart_calc", "question_count": 2}]}).status_code, 400)
        self.assertEqual(self.calls, [])

    def test_missing_config_never_calls_provider(self):
        image_config.clear_config()
        self.assertEqual(self.send().status_code, 400)
        self.assertEqual(self.calls, [])

    def test_timeout_is_not_automatically_retried_and_does_not_leak_secrets(self):
        def timeout(req):
            raise httpx.ReadTimeout("secret-image-test", request=req)
        self.handler = timeout
        response = self.send()
        self.assertEqual(response.status_code, 504)
        self.assertNotIn("secret-image-test", response.text)
        self.assertEqual(self.send().status_code, 504)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.client.get("/api/v1/me/generations/image-one").json()["status"], "unknown")

    def test_bad_provider_responses_are_safe_errors(self):
        for i, data in enumerate([{}, {"data": []}, {"data": [{"b64_json": "invalid-base64"}]}, {"data": [{"b64_json": base64.b64encode(b'<svg></svg>').decode()}]}]):
            self.handler = lambda req, value=data: httpx.Response(200, json=value)
            self.assertEqual(self.send(f"bad-{i}").status_code, 502)
        self.handler = lambda req: httpx.Response(401, text="secret-image-test")
        response = self.send("bad-key")
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret-image-test", response.text)

    def test_completed_image_with_task_metadata_is_not_polled_or_failed_over(self):
        self.configure_failover()

        def handler(req):
            if req.method == "POST":
                # 服务商同步响应同时包含成品图片和任务编号，编号只是追踪元数据。
                return httpx.Response(200, json={"created": 1792067768, "task_id": "finished-job",
                    "data": [{"url": "https://images.invalid/output.png"}]})
            self.assertEqual(req.url.path, "/output.png")
            self.assertNotIn("authorization", req.headers)
            return httpx.Response(200, content=png())

        self.handler = handler
        response = self.send("completed-with-task-id")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get(response.json()["url"]).status_code, 200)
        self.assertEqual(self.send("completed-with-task-id").json(), response.json())
        self.assertEqual([req.method for req in self.calls], ["POST", "GET"])
        recovered = self.client.get("/api/v1/me/generations/completed-with-task-id").json()
        self.assertEqual(recovered["status"], "succeeded")
        self.assertEqual(recovered["usage"]["model_calls"], 1)

    def test_completed_base64_image_ignores_unused_poll_metadata(self):
        self.handler = lambda req: httpx.Response(200, json={"object": "image.task", "id": "done",
            "status": "succeeded", "poll_url": "https://unrelated.invalid/tasks/done",
            "data": [{"b64_json": base64.b64encode(png()).decode()}]})
        response = self.send("completed-base64-with-task")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.calls), 1)

    def test_task_with_empty_image_placeholder_still_polls(self):
        def handler(req):
            if req.method == "POST":
                return httpx.Response(202, json={"task_id": "queued-job", "poll_url": "/tasks",
                    "data": [{"url": ""}]})
            return httpx.Response(200, json={"id": "queued-job", "status": "succeeded",
                "data": [{"b64_json": base64.b64encode(png()).decode()}]})

        self.handler = handler
        with patch.object(service, "TASK_POLL_INTERVAL", 0):
            response = self.send("empty-image-placeholder")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([req.method for req in self.calls], ["POST", "GET"])

    def test_async_negotiation_polls_then_persists_and_replays_without_resubmitting(self):
        polls = 0

        def handler(req):
            nonlocal polls
            if req.method == "POST":
                body = json.loads(req.content)
                if not body.get("async"):
                    return httpx.Response(400, json={"error": {"code": "bad_request", "message": "图片 API 仅支持异步任务，请传 async: true"}})
                self.assertEqual(body["model"], "custom-image-model")
                self.assertEqual(body["size"], "1024x1536")
                return httpx.Response(202, json={"object": "image_task", "task_id": "job-1", "status": "queued",
                                                "poll_url": "https://provider.invalid/api/image-tasks?ids=job-1"})
            if req.url.path == "/api/image-tasks":
                polls += 1
                self.assertEqual(req.url.params["ids"], "job-1")
                self.assertEqual(req.headers["authorization"], "Bearer secret-image-test")
                self.assertEqual(req.headers["host"], "provider.invalid")
                self.assertEqual(req.extensions["sni_hostname"], "provider.invalid")
                return httpx.Response(200, json={"items": [{"id": "job-1", "status": "running" if polls == 1 else "success",
                    "results": [] if polls == 1 else [{"url": "https://images.invalid/output.png"}]}]})
            self.assertNotIn("authorization", req.headers)
            return httpx.Response(200, content=png())

        self.handler = handler
        with patch.object(service, "TASK_POLL_INTERVAL", 0):
            response = self.send()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()["width"], response.json()["height"]), (24, 32))
        self.assertEqual(self.client.get(response.json()["url"]).status_code, 200)
        self.assertEqual(self.send().json(), response.json())
        self.assertEqual(len(self.calls), 5)
        status = self.client.get("/api/v1/me/generations/image-one").json()
        self.assertEqual(status["status"], "succeeded")
        self.assertEqual(status["usage"]["model_calls"], 2)
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT SUM(images) FROM generation_budget").fetchone()[0], 1)

    def test_async_direct_acceptance_retries_only_transient_gets(self):
        polls = 0

        def handler(req):
            nonlocal polls
            if req.method == "POST":
                return httpx.Response(202, json={"task_id": "job-1", "poll_url": "/api/image-tasks?ids=job-1"})
            polls += 1
            if polls == 1:
                return httpx.Response(503)
            return httpx.Response(200, json={"items": [{"id": "job-1", "status": "success",
                "results": [{"b64_json": base64.b64encode(png()).decode()}]}]})

        self.handler = handler
        with patch.object(service, "TASK_POLL_INTERVAL", 0):
            response = self.send()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([call.method for call in self.calls], ["POST", "GET", "GET"])

    def test_configured_async_mode_accepts_single_task_data_response(self):
        image_config.save_config(ImageModelConfig(**self.config, requestMode="async"))
        self.assertEqual(image_config.get_admin_config()["models"][0]["requestMode"], "async")

        def handler(req):
            if req.method == "POST":
                self.assertTrue(json.loads(req.content)["async"])
                return httpx.Response(202, json={"object": "image.task", "id": "img-1", "status": "queued",
                                                "poll_url": "https://provider.invalid/v1/images/tasks/img-1"})
            return httpx.Response(200, json={"object": "image.task", "id": "img-1", "status": "succeeded",
                "data": [{"b64_json": base64.b64encode(png()).decode()}]})

        self.handler = handler
        with patch.object(service, "TASK_POLL_INTERVAL", 0):
            response = self.send()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([call.method for call in self.calls], ["POST", "GET"])

    def test_sync_mode_does_not_negotiate_and_invalid_mode_is_rejected(self):
        image_config.save_config(ImageModelConfig(**self.config, requestMode="sync"))
        self.handler = lambda req: httpx.Response(400, json={"error": {"code": "async_required"}})
        response = self.send()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(ValueError):
            ImageModelConfig(**self.config, requestMode="invalid")

    def test_async_task_failure_switches_provider_and_hides_task_error(self):
        self.configure_failover()
        good = self.handler

        def handler(req):
            if req.method == "GET":
                return httpx.Response(200, json={"items": [{"id": "job-1", "status": "failed", "terminal": True,
                    "public_error": "secret-image-test private-address prompt", "results": []}]})
            if json.loads(req.content)["model"] == "custom-image-model":
                return httpx.Response(202, json={"task_id": "job-1", "poll_url": "/api/image-tasks?ids=job-1"})
            return good(req)

        self.handler = handler
        with patch.object(service, "TASK_POLL_INTERVAL", 0):
            response = self.send()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([call.method for call in self.calls], ["POST", "GET", "POST"])
        self.assertEqual(self.calls[-1].headers["authorization"], "Bearer backup-key")
        self.assertNotIn("secret-image-test", response.text)

    def test_explicit_model_error_is_not_hidden_by_generic_tool_message(self):
        self.handler = lambda req: httpx.Response(400, json={"error": {
            "code": "unsupported_model", "message": "图片生成工具发生错误，请稍后重试。 secret-image-test",
        }})
        response = self.send("model-unavailable")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["reason"], "model")
        self.assertNotIn("secret-image-test", response.text)
        self.assertEqual(self.send("model-unavailable").json(), response.json())
        self.assertEqual(len(self.calls), 1)

    def test_async_task_model_errors_keep_classification_without_exposing_raw_detail(self):
        cases = [
            ({"error_code": "unsupported_model"}, "model"),
            ({"error": {"code": "model_not_found", "message": "secret-image-test"}}, "model"),
            ({"error_code": "MODEL_NOT_SUPPORTED"}, "model"),
            ({"error_code": {"unexpected": "secret-image-test"}}, "generation_failed"),
            ({"error": "secret-image-test"}, "generation_failed"),
            ({"error_code": "unsupported_model", "status": "text_review"}, "content_policy"),
        ]
        for index, (error_fields, reason) in enumerate(cases):
            with self.subTest(error_fields=error_fields):
                self.calls.clear()
                task = {"id": "job-1", "status": "failed", "terminal": True,
                        "public_error": "图片生成工具发生错误 secret-image-test", "raw_error": "private-address",
                        **error_fields}
                self.handler = lambda req, task=task, index=index: (
                    httpx.Response(202, json={"task_id": "job-1", "poll_url": "/tasks"}) if req.method == "POST"
                    else httpx.Response(200, json=task if index % 2 else {"items": [task]})
                )
                with patch.object(service, "TASK_POLL_INTERVAL", 0):
                    response = self.send(f"task-model-{index}")
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.json()["detail"]["reason"], reason)
                self.assertNotIn("secret-image-test", response.text)
                self.assertNotIn("private-address", response.text)
                self.assertEqual(self.send(f"task-model-{index}").json(), response.json())
                self.assertEqual([call.method for call in self.calls], ["POST", "GET"])

    def test_async_poll_urls_never_receive_key_outside_configured_origin(self):
        for i, url in enumerate([
            "https://public.invalid/tasks", "//public.invalid/tasks", "http://provider.invalid/tasks",
            "https://provider.invalid:444/tasks", "https://user:password@provider.invalid/tasks",
            "https://provider.invalid/tasks#fragment", "https://127.0.0.1/tasks", " /api/tasks",
        ]):
            with self.subTest(url=url):
                self.calls.clear()
                self.handler = lambda req, url=url: httpx.Response(202, json={"task_id": "job-1", "poll_url": url})
                response = self.send(f"bad-poll-{i}")
                self.assertEqual(response.status_code, 502, response.text)
                self.assertEqual(len(self.calls), 1)

    def test_async_rejects_mismatched_missing_and_malformed_tasks(self):
        for i, payload in enumerate([
            {"items": [], "missing_ids": ["job-1"]},
            {"items": [{"id": "other-job", "status": "success", "results": []}]},
            {"items": [{"id": "job-1", "status": "success", "results": []}]},
            {"items": [{"id": "job-1", "status": "unexpected"}]},
            {"items": [{"id": "job-1", "status": "running", "terminal": True}]},
        ]):
            with self.subTest(payload=payload):
                self.calls.clear()
                self.handler = lambda req, payload=payload: httpx.Response(202, json={"task_id": "job-1", "poll_url": "/tasks"}) if req.method == "POST" else httpx.Response(200, json=payload)
                with patch.object(service, "TASK_POLL_INTERVAL", 0):
                    self.assertEqual(self.send(f"malformed-task-{i}").status_code, 502)
                self.assertEqual(len(self.calls), 2)

    def test_async_polling_obeys_total_timeout_without_post_retry(self):
        config = {**image_config.get_config(with_key=True), "timeout": 0.05}
        self.handler = lambda req: httpx.Response(202, json={"task_id": "job-1", "poll_url": "/tasks"}) if req.method == "POST" else httpx.Response(200, json={"items": [{"id": "job-1", "status": "running"}]})
        with patch.object(image_config, "get_config", return_value=config), patch.object(service, "TASK_POLL_INTERVAL", 0.01):
            response = self.send()
        self.assertEqual(response.status_code, 504, response.text)
        self.assertEqual(sum(call.method == "POST" for call in self.calls), 1)

    def test_async_negotiation_happens_at_most_once_and_only_on_explicit_rejection(self):
        for i, error in enumerate([
            {"code": "bad_request", "message": "invalid size"},
            {"code": "async_required", "message": "图片 API 仅支持异步任务，请传 async: true"},
        ]):
            self.calls.clear()
            self.handler = lambda req, error=error: httpx.Response(400, json={"error": error})
            self.assertEqual(self.send(f"async-rejected-{i}").status_code, 502)
            self.assertEqual(len(self.calls), i + 1)

    def test_url_responses_use_public_pinned_ip_without_credentials(self):
        def handler(req):
            if req.method == "POST":
                return httpx.Response(200, json={"data": [{"url": "https://images.invalid/output.png?signature=abc"}]})
            self.assertEqual(req.url.host, "93.184.216.34")
            self.assertEqual(req.headers["host"], "images.invalid")
            self.assertEqual(req.extensions["sni_hostname"], "images.invalid")
            self.assertNotIn("authorization", req.headers)
            return httpx.Response(200, content=png())
        self.handler = handler
        self.assertEqual(self.send().status_code, 200)
        self.assertEqual(len(self.calls), 2)

    def test_private_image_urls_and_redirects_cannot_reach_internal_services(self):
        self.handler = lambda req: httpx.Response(200, json={"data": [{"url": "https://internal.invalid/a.png"}]})
        self.assertEqual(self.send().status_code, 502)
        self.assertEqual(len(self.calls), 1)
        def handler(req):
            if req.method == "POST":
                return httpx.Response(200, json={"data": [{"url": "https://public.invalid/a.png"}]})
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        self.handler = handler
        self.assertEqual(self.send("redirect").status_code, 502)
        self.assertEqual(len(self.calls), 3)

    def test_configured_response_format_and_complete_endpoint_are_preserved(self):
        image_config.save_config(ImageModelConfig(**{**self.config, "baseUrl": "https://provider.invalid/custom/v1/images/generations", "responseFormat": "b64_json", "size": "1024x1792"}))
        self.assertEqual(self.send().status_code, 200)
        self.assertEqual(str(self.calls[0].url), "https://93.184.216.34/custom/v1/images/generations")
        body = json.loads(self.calls[0].content)
        self.assertEqual(body["response_format"], "b64_json")
        self.assertEqual(body["size"], "1024x1792")
        self.assertEqual(service.generation_url("https://provider.invalid"), "https://provider.invalid/v1/images/generations")

    def test_response_size_limit_is_enforced(self):
        self.handler = lambda req: httpx.Response(200, content=b"x" * 101)
        with patch.object(service, "MAX_RESPONSE_BYTES", 100):
            self.assertEqual(self.send().status_code, 502)

    def test_image_expiry_keeps_tombstone_and_cleans_file(self):
        import time

        from app.services import maintenance
        result = self.send("expire-image").json()
        with database.db() as conn:
            conn.execute("UPDATE image_assets SET expires_at = ?", (int(time.time()) - 1,))
            conn.execute("UPDATE generation_requests SET finished_at = ?", (int(time.time()) - 400 * 86400,))
        self.assertEqual(self.client.get(result["url"]).status_code, 410)
        maintenance.tick()
        self.assertEqual(self.client.get(result["url"]).status_code, 404)
        self.assertEqual(self.send("expire-image").status_code, 410)
        self.assertEqual(len(self.calls), 1)
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM image_assets").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM generation_tombstones").fetchone()[0], 1)

    def test_image_quota_rejects_before_paid_provider_call(self):
        from app.config import get_settings
        from app.services.generation_control import _begin
        with patch.object(get_settings(), "image_storage_mb", 16):
            _begin(self.user.id, "reserved-image", "image", self.body)
            result = self.send("quota-image")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.json()["detail"]["code"], "image_storage_quota")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
