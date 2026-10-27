"""多模型配置与故障切换；只用一次性数据库和离线模型响应。"""

import asyncio
import json
import socket
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch

import httpx
import test_backend_reliability as fixtures
from fastapi import HTTPException

from app.config import get_settings
from app.db import db
from app.deps import SESSION_COOKIE
from app.http_limits import limited_lines
from app.models.model_profiles import ImageModelProfile, TextModelProfile
from app.routers import admin, generate, image_generation
from app.security import create_token
from app.services import app_config, image_config, user_store
from app.services.generation_control import request_status
from app.services.llm_client import OutputTruncated, llm_client
from app.services.provider_failover import run_with_failover
from scripts.rotate_encryption import rotate


def profile(identifier, **changes):
    return TextModelProfile(id=identifier, baseUrl="https://provider.invalid/v1",
                            model=f"model-{identifier}", apiKey=f"secret-{identifier}", **changes)


def sse(*events, done=True):
    text = "".join("data:" + (json.dumps(event) if not isinstance(event, str) else event) + "\n\n" for event in events)
    return httpx.Response(200, text=text + ("data: [DONE]\n\n" if done else ""), headers={"Content-Type": "text/event-stream"})


def stream_event(text="", reason=None, usage=None):
    return {"choices": [{"delta": {"content": text}, "finish_reason": reason}], "usage": usage}


class ModelFailover(unittest.TestCase):
    def setUp(self):
        fixtures.BackendReliability.setUp(self)
        # 此类逐项覆盖故障协议；跨请求的冷却/恢复单独由运行策略测试验证。
        self.stack.enter_context(patch.object(get_settings(), "provider_failure_threshold", 1000))
        self.client.app.include_router(admin.router)
        self.client.app.include_router(image_generation.router)
        self.admin = user_store.create_user("model-admin", "test-password", role="admin")
        self.profiles = [profile("first"), profile("off", enabled=False), profile("second")]
        app_config.save_llm_models(self.profiles)
        self.calls = []
        self.outputs = []
        self.default = {"choices": [{"message": {"content": '{"is_oob":false,"oob_points":[],"suggestion":""}'}}],
                        "usage": {"prompt_tokens": 12, "completion_tokens": 7}}

        def handle(request):
            self.calls.append(request)
            output = self.outputs.pop(0) if self.outputs else httpx.Response(200, json=self.default)
            if isinstance(output, Exception):
                raise output
            return output

        asyncio.run(llm_client.close())
        self.addCleanup(lambda: asyncio.run(llm_client.close()))
        client = httpx.AsyncClient
        self.stack.enter_context(patch.object(httpx, "AsyncClient", side_effect=lambda **kw: client(**kw, transport=httpx.MockTransport(handle))))
        resolve = socket.getaddrinfo

        def public(host, *args, **kwargs):
            if host in ("provider.invalid", "other.invalid"):
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
            return resolve(host, *args, **kwargs)
        self.stack.enter_context(patch("app.provider_policy.socket.getaddrinfo", side_effect=public))

    def login_admin(self):
        self.client.cookies.set(SESSION_COOKIE, create_token(self.admin.id))

    def validate(self, request_id="fallback"):
        return self.client.post("/api/v1/validate", json={
            "grade": "小学三年级", "subject": "数学", "question_content": "1+2=?",
        }, headers={"X-Request-ID": request_id})

    def stream(self, request_id):
        return self.client.post("/api/v1/generate/stream", json={
            "grade": "小学三年级", "subject": "数学", "keyword": "加法",
            "game_type": "fill_blank", "question_count": 1,
        }, headers={"X-Request-ID": request_id})

    def test_provider_errors_switch_once_in_order_without_backoff_and_replay(self):
        original_sleep = asyncio.sleep

        async def no_backoff(delay):
            self.assertNotIn(delay, (2, 4))
            await original_sleep(delay)

        for index, output in enumerate([
            httpx.Response(401), httpx.Response(429), httpx.Response(503),
            httpx.ConnectError("unreachable"), httpx.ReadTimeout("possibly billed"),
            httpx.DecodingError("invalid compressed data"), httpx.Response(200, text="not json"),
            httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]}),
        ]):
            with self.subTest(output=type(output).__name__):
                self.calls.clear()
                self.outputs = [output]
                with patch("app.services.llm_client.asyncio.sleep", new=no_backoff):
                    result = self.validate(f"fallback-{index}")
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual([json.loads(call.content)["model"] for call in self.calls], ["model-first", "model-second"])
                self.assertEqual([call.headers["authorization"] for call in self.calls], ["Bearer secret-first", "Bearer secret-second"])
                self.assertEqual(self.validate(f"fallback-{index}").json(), result.json())
                self.assertEqual(len(self.calls), 2)
                status = request_status(self.user.id, f"fallback-{index}")
                self.assertEqual(status["usage"]["model_calls"], 2)
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM generation_requests").fetchone()[0], 8)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM generation_budget").fetchone()[0], 16)

    def test_success_never_contacts_backup_and_configured_timeout_is_honored(self):
        app_config.save_llm_models([profile("first", timeout=10), profile("second", timeout=20)])
        self.assertEqual(self.validate().status_code, 200)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0].extensions["timeout"]["read"], 10)

    def test_dns_failure_switches_but_private_address_rejection_stops(self):
        app_config.save_llm_models([
            profile("first").model_copy(update={"baseUrl": "https://other.invalid/v1"}),
            profile("second"),
        ])
        public = socket.getaddrinfo

        def broken(host, *args, **kwargs):
            if host == "other.invalid":
                raise socket.gaierror("temporary DNS failure")
            return public(host, *args, **kwargs)

        with patch("app.provider_policy.socket.getaddrinfo", side_effect=broken):
            self.assertEqual(self.validate("dns").status_code, 200)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(json.loads(self.calls[0].content)["model"], "model-second")
        def private(host, *args, **kwargs):
            if host == "other.invalid":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
            return public(host, *args, **kwargs)

        with patch("app.provider_policy.socket.getaddrinfo", side_effect=private):
            result = self.validate("private")
        self.assertEqual(result.status_code, 422)
        self.assertEqual(result.json()["detail"]["code"], "provider_address_rejected")
        self.assertEqual(len(self.calls), 1)

    def test_all_failures_are_bounded_and_replayed(self):
        self.outputs = [httpx.Response(503), httpx.ReadTimeout("secret upstream detail")]
        result = self.validate()
        self.assertEqual(result.status_code, 504)
        self.assertNotIn("secret", result.text)
        self.assertEqual(self.validate().json(), result.json())
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(request_status(self.user.id, "fallback")["status"], "unknown")

    def test_budget_stops_chain_before_another_billable_call(self):
        self.outputs = [httpx.Response(503)]
        from app.services.generation_budget import reserve
        reservations = 0

        def limited(**kwargs):
            nonlocal reservations
            reservations += 1
            if reservations == 2:
                raise HTTPException(429, detail={"code": "generation_budget", "error": "预算已用尽"})
            return reserve(**kwargs)
        with patch("app.services.llm_client.reserve", side_effect=limited):
            result = self.validate()
        self.assertEqual(result.status_code, 429)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(request_status(self.user.id, "fallback")["usage"]["model_calls"], 1)

    def test_disabled_and_empty_models_do_not_restore_environment_provider(self):
        for profiles in ([], [profile("first", enabled=False)]):
            app_config.save_llm_models(profiles)
            with patch.object(get_settings(), "llm_api_key", "environment-secret"):
                result = self.validate(f"disabled-{len(profiles)}")
                self.assertEqual(result.status_code, 400)
                self.login_admin()
                self.assertFalse(self.client.get("/api/v1/admin/stats").json()["llmConfigured"])
        self.assertEqual(self.calls, [])

    def test_stream_discards_failed_partial_output(self):
        used = []

        async def stream(*args, **kwargs):
            used.append(kwargs["model"])
            if kwargs["model"] == "model-first":
                yield "FAILED-PARTIAL"
                raise httpx.ReadTimeout("interrupted")
            yield '{"questions":[]}'

        with patch.object(llm_client, "chat_stream", new=stream):
            result = self.client.post("/api/v1/generate/stream", json={
                "grade": "小学三年级", "subject": "数学", "keyword": "加法", "game_type": "fill_blank", "question_count": 1,
            }, headers={"X-Request-ID": "stream-fallback"})
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("FAILED-PARTIAL", result.text)
        self.assertIn("[DONE]", result.text)
        self.assertEqual(used, ["model-first", "model-second"])

    def test_config_round_trip_binds_blank_keys_to_id_and_masks_every_key(self):
        self.login_admin()
        value = self.client.get("/api/v1/admin/llm-config").json()
        self.assertEqual([model["id"] for model in value["models"]], ["first", "off", "second"])
        self.assertNotIn("secret-", json.dumps(value))
        self.assertNotIn("api_key", json.dumps(value))
        changed = [item.model_copy(update={"apiKey": ""}) for item in reversed(self.profiles)]
        result = self.client.put("/api/v1/admin/llm-config", json={"revision": value["revision"], "models": [item.model_dump() for item in changed]})
        self.assertEqual(result.status_code, 200, result.text)
        config = app_config.get_llm(with_key=True)
        self.assertEqual([(item["id"], item["api_key"]) for item in config["models"]],
                         [("second", "secret-second"), ("off", "secret-off"), ("first", "secret-first")])
        config["models"][0]["model"] = "cache-poison"
        self.assertEqual(app_config.get_llm()["models"][0]["model"], "model-second")
        with db() as conn:
            self.assertNotIn("secret-", conn.execute("SELECT value FROM app_config WHERE key='llm'").fetchone()[0])

    def test_config_validation_is_atomic_and_old_client_cannot_erase_chain(self):
        self.login_admin()
        saved = app_config.get_llm()
        revision = self.client.get("/api/v1/admin/llm-config").json()["revision"]
        first = self.profiles[0].model_dump()
        for models in (
            [first, first], [{**first, "apiKey": "", "baseUrl": "https://other.invalid/v1"}],
            [{**first, "apiKey": "", "id": "new"}],
            [{**first, "timeout": 601}], [{**first, "apiKeyEnc": "forged"}],
            [{**first, "id": str(index)} for index in range(9)],
        ):
            result = self.client.put("/api/v1/admin/llm-config", json={"revision": revision, "models": models})
            self.assertIn(result.status_code, (400, 422), result.text)
            self.assertNotIn("secret-first", result.text)
            self.assertEqual(app_config.get_llm(), saved)
        old = {key: first[key] for key in ("baseUrl", "model", "apiKey", "timeout", "maxTokens")}
        self.assertEqual(self.client.put("/api/v1/admin/llm-config", json=old).status_code, 409)
        self.assertEqual(app_config.get_llm(), saved)

    def test_probe_uses_selected_key_and_never_borrows_for_unknown_id(self):
        self.login_admin()
        self.outputs = [sse(stream_event("ok"))]
        result = self.client.post("/api/v1/admin/test-llm", json={"id": "second", "model": "model-second"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.calls[0].headers["authorization"], "Bearer secret-second")
        self.assertEqual(self.client.post("/api/v1/admin/test-llm", json={
            "id": "unknown", "baseUrl": "https://other.invalid/v1",
        }).status_code, 400)
        self.assertEqual(len(self.calls), 1)

    def test_probe_accepts_reasoning_only_stream_as_connected(self):
        self.login_admin()
        self.outputs = [sse({"choices": [{"delta": {"reasoning_content": "先想一下"}, "finish_reason": "length"}]})]
        result = self.client.post("/api/v1/admin/test-llm", json={"id": "first"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["status"], "ok")

    def test_model_list_uses_selected_key_and_normalizes_ids(self):
        self.login_admin()
        self.outputs = [httpx.Response(200, json={"data": [
            {"id": "zeta"}, {"id": "Alpha"}, {"id": "Alpha"}, {"id": "x" * 121}, 42,
        ]})]
        result = self.client.post("/api/v1/admin/llm-models", json={"id": "second", "timeout": 30})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), {"status": "ok", "models": ["Alpha", "zeta"], "count": 2})
        self.assertEqual(self.calls[0].method, "GET")
        self.assertEqual(self.calls[0].url.path, "/v1/models")
        self.assertEqual(self.calls[0].headers["authorization"], "Bearer secret-second")
        self.assertNotIn("secret-second", result.text)

    def test_image_model_list_uses_the_saved_image_candidate_key(self):
        self.login_admin()
        image_config.save_models([ImageModelProfile(id="image", baseUrl="https://provider.invalid/v1",
                                                    model="image-draft", apiKey="image-secret")])
        self.outputs = [httpx.Response(200, json={"models": [
            {"id": "gpt-image-2.5-sunburst"}, {"id": "gpt-image-2"},
        ]})]
        result = self.client.post("/api/v1/admin/llm-models", json={"id": "image", "kind": "image"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), {"status": "ok",
                                        "models": ["gpt-image-2", "gpt-image-2.5-sunburst"], "count": 2})
        self.assertEqual(self.calls[0].url.path, "/v1/models")
        self.assertEqual(self.calls[0].headers["authorization"], "Bearer image-secret")
        self.assertNotIn("image-secret", result.text)

    def test_model_list_never_borrows_keys_across_text_and_image_configs(self):
        self.login_admin()
        image_config.save_models([ImageModelProfile(id="image", baseUrl="https://provider.invalid/v1",
                                                    model="image-draft", apiKey="image-secret")])
        for payload in ({"id": "image"}, {"id": "image", "kind": "text"}, {"id": "first", "kind": "image"}):
            with self.subTest(payload=payload):
                result = self.client.post("/api/v1/admin/llm-models", json=payload)
                self.assertEqual(result.status_code, 400, result.text)
        self.assertEqual(len(self.calls), 0)
        self.outputs = [httpx.Response(200, json={"data": [{"id": "image-draft"}]})]
        typed = self.client.post("/api/v1/admin/llm-models", json={
            "id": "image", "kind": "image", "apiKey": "typed-image-key",
        })
        self.assertEqual(typed.status_code, 200, typed.text)
        self.assertEqual(typed.json()["models"], ["image-draft"])
        self.assertEqual(self.calls[0].headers["authorization"], "Bearer typed-image-key")

    def test_model_list_rejects_unknown_ids_and_unusable_responses(self):
        self.login_admin()
        rejected = self.client.post("/api/v1/admin/llm-models", json={
            "id": "unknown", "baseUrl": "https://other.invalid/v1",
        })
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(len(self.calls), 0)
        for payload in ({"data": []}, {"data": "wrong"}, {"object": "list"}, {"data": [{"name": "no-id"}]}):
            with self.subTest(payload=payload):
                self.outputs = [httpx.Response(200, json=payload)]
                result = self.client.post("/api/v1/admin/llm-models", json={"id": "first"})
                self.assertEqual(result.status_code, 502, result.text)
                self.assertIn("手动填写模型名称", result.text)
        self.assertEqual(len(self.calls), 4)

    def test_model_list_rejects_private_addresses_without_connecting(self):
        self.login_admin()
        for base in ("http://169.254.169.254", "http://127.0.0.1", "http://127.0.0.1:11434/v1", "ftp://example.com"):
            with self.subTest(base=base):
                result = self.client.post("/api/v1/admin/llm-models", json={"baseUrl": base, "apiKey": "k"})
                self.assertEqual(result.status_code, 400, result.text)
                self.assertEqual(result.json()["detail"]["error"], "接口地址不允许")
        self.assertEqual(len(self.calls), 0)

    def test_legacy_configuration_preserves_key_on_upgrade_and_clear_disables(self):
        app_config.clear_llm()
        app_config.save_llm("https://provider.invalid/v1", "old", "old-key", 60)
        self.login_admin()
        saved = self.client.get("/api/v1/admin/llm-config").json()
        legacy = saved["models"][0]
        self.assertEqual(legacy["id"], "legacy")
        legacy.pop("hasKey")
        result = self.client.put("/api/v1/admin/llm-config", json={"revision": saved["revision"], "models": [legacy]})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(app_config.get_llm(with_key=True)["models"][0]["api_key"], "old-key")
        self.assertEqual(self.client.delete("/api/v1/admin/llm-config", headers={"If-Match": result.json()["revision"]}).status_code, 200)
        self.assertEqual(app_config.get_llm()["models"], [])

    def test_rotation_covers_nested_text_and_image_credentials_and_rolls_back(self):
        image_config.save_models([ImageModelProfile(id="image", baseUrl="https://provider.invalid/v1",
                                                    model="image-model", apiKey="image-secret")])
        with db() as conn:
            before = {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM app_config").fetchall()}
        settings = get_settings()
        with patch.object(settings, "encryption_active_key", "v2"), patch.object(settings, "encryption_keys", {"v2": "new-test-encryption-secret-32-bytes-long"}):
            self.assertEqual(rotate()["would_change"], 4)
            self.assertEqual(rotate(apply=True)["changed"], 4)
            self.assertEqual(rotate(apply=True)["changed"], 0)
            self.assertEqual(app_config.get_llm(with_key=True)["models"][2]["api_key"], "secret-second")
            self.assertEqual(image_config.get_config(with_key=True)["models"][0]["api_key"], "image-secret")
        with db() as conn:
            for key, raw in before.items():
                value = json.loads(raw)
                if key == image_config.KEY:
                    value["models"][0]["apiKeyEnc"] = "enc2:missing:broken"
                conn.execute("UPDATE app_config SET value=? WHERE key=?", (json.dumps(value), key))
            corrupted = {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM app_config").fetchall()}
        with patch.object(settings, "encryption_active_key", "v2"), patch.object(settings, "encryption_keys", {"v2": "new-test-encryption-secret-32-bytes-long"}):
            with self.assertRaises(ValueError):
                rotate(apply=True)
        with db() as conn:
            self.assertEqual({row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM app_config").fetchall()}, corrupted)

    def test_concurrent_configuration_updates_have_exactly_one_winner(self):
        original = app_config.get_admin_config()["revision"]

        def save(name):
            try:
                result = app_config.save_llm_models([profile(name)], expected_revision=original)
                return result
            except HTTPException as exc:
                self.assertEqual(exc.status_code, 409)
                self.assertEqual(exc.detail["code"], "model_config_conflict")
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, ["first", "second"]))
        winner = [result for result in results if result is not None]
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0], app_config.get_admin_config())

    def test_stale_clear_and_save_never_erase_a_new_configuration(self):
        self.login_admin()
        original = self.client.get("/api/v1/admin/llm-config").json()
        latest = app_config.save_llm_models([profile("third")])
        for result in [
            self.client.put("/api/v1/admin/llm-config", json={"revision": original["revision"], "models": []}),
            self.client.delete("/api/v1/admin/llm-config", headers={"If-Match": original["revision"]}),
            self.client.delete("/api/v1/admin/llm-config"),
        ]:
            self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(self.client.get("/api/v1/admin/llm-config").json(), latest)

    def test_admin_reads_and_probe_do_not_use_stale_runtime_cache(self):
        app_config.get_llm()
        with db() as conn:
            row = conn.execute("SELECT value FROM app_config WHERE key='llm'").fetchone()
            raw = json.loads(row[0])
            raw["models"][0]["model"] = "fresh-model"
            conn.execute("UPDATE app_config SET value=? WHERE key='llm'", (json.dumps(raw),))
        self.assertEqual(app_config.get_llm()["model"], "model-first")
        self.login_admin()
        self.assertEqual(self.client.get("/api/v1/admin/llm-config").json()["model"], "fresh-model")
        self.outputs = [sse(stream_event("ok"))]
        self.assertEqual(self.client.post("/api/v1/admin/test-llm", json={"id": "first"}).status_code, 200)
        self.assertEqual(json.loads(self.calls[0].content)["model"], "fresh-model")

    def test_disabled_models_can_be_saved_when_dns_is_unavailable(self):
        self.login_admin()
        value = self.client.get("/api/v1/admin/llm-config").json()
        disabled = self.profiles[0].model_dump() | {"enabled": False, "apiKey": ""}
        with patch("app.provider_policy.socket.getaddrinfo", side_effect=AssertionError("disabled model must not resolve")):
            result = self.client.put("/api/v1/admin/llm-config", json={"revision": value["revision"], "models": [disabled]})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertFalse(result.json()["models"][0]["enabled"])

    def test_invalid_urls_fail_safely_without_writing(self):
        self.login_admin()
        original = self.client.get("/api/v1/admin/llm-config").json()
        for url in ("https://[invalid/v1", "https://host.invalid:99999", "https://host.invalid:0", "https://bad host.invalid"):
            body = self.profiles[0].model_dump() | {"baseUrl": url}
            result = self.client.put("/api/v1/admin/llm-config", json={"revision": original["revision"], "models": [body]})
            self.assertEqual(result.status_code, 422, result.text)
        self.assertEqual(self.client.get("/api/v1/admin/llm-config").json(), original)

    def test_probe_rejects_empty_error_and_malformed_success_responses(self):
        self.login_admin()
        for response in [
            httpx.Response(200, text="<html>error page</html>"), sse(),
            sse({"error": {"message": "content failed"}}), sse({"choices": []}),
            sse(["wrong"]), sse(stream_event({"unexpected": "object"})),
            sse(stream_event("", "content_filter")), sse("not json"),
        ]:
            self.outputs = [response]
            result = self.client.post("/api/v1/admin/test-llm", json={"id": "first"})
            self.assertEqual(result.status_code, 502, result.text)
            self.assertNotIn("secret-first", result.text)

    def test_config_validation_errors_never_echo_plaintext_credentials(self):
        self.login_admin()
        for endpoint, body in [
            ("test-llm", {"apiKey": "private-probe-key", "timeout": 999}),
            ("image-config", {"apiKey": "private-image-key", "baseUrl": "https://example.test", "model": "m", "size": "wrong"}),
            ("llm-config", {"apiKey": "private-text-key", "timeout": 999}),
        ]:
            method = self.client.post if endpoint == "test-llm" else self.client.put
            response = method(f"/api/v1/admin/{endpoint}", json=body)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(body["apiKey"], response.text)
            self.assertNotIn('"input"', response.text)

    def test_bad_streams_switch_and_never_emit_failed_partial_content(self):
        for index, response in enumerate([
            sse(stream_event("POISON"), {"error": "provider failure"}),
            sse(stream_event({"bad": True})), sse(["unexpected"]),
            sse("not json"), sse(),
            sse(stream_event('{"questions":[]}'), done=False),
            sse(stream_event("POISON"), {"choices": [{"delta": {"refusal": "declined"}}]}),
            sse(stream_event("POISON", "tool_calls")),
            sse(stream_event("POISON", "unexpected")),
            sse(stream_event('{"reviews":[]}', "stop")),
        ]):
            self.calls.clear()
            self.outputs = [response, sse(stream_event('{"questions":[]}', "stop"))]
            result = self.stream(f"bad-stream-{index}")
            self.assertIn("[DONE]", result.text)
            self.assertNotIn("POISON", result.text)
            self.assertEqual(len(self.calls), 2)
            self.assertEqual(request_status(self.user.id, f"bad-stream-{index}")["status"], "succeeded")

    def test_stream_usage_is_counted_once_per_provider_even_after_failure(self):
        usage = {"prompt_tokens": 10, "completion_tokens": 4}
        self.outputs = [
            sse(stream_event("POISON", usage=usage), {"choices": [], "usage": usage}, {"error": "failure"}),
            sse(stream_event('{"questions":[]}', "stop", usage),
                {"choices": [], "usage": usage}, {"choices": [], "usage": {"prompt_tokens": "bad"}}),
        ]
        result = self.stream("stream-usage")
        self.assertIn("[DONE]", result.text)
        self.assertEqual(request_status(self.user.id, "stream-usage")["usage"], {
            "model_calls": 2, "reported_calls": 2, "prompt_tokens": 20, "completion_tokens": 8,
        })

    def test_rejected_stream_keeps_latest_usage_snapshot_before_switching(self):
        first = {"prompt_tokens": 10, "completion_tokens": 3}
        final = {"prompt_tokens": 10, "completion_tokens": 7}
        for index, event in enumerate([
            {"choices": [{"delta": {"refusal": "no"}}], "usage": final},
            stream_event("", "content_filter", final),
            stream_event("", "tool_calls", final),
            {"error": "failure", "usage": final},
        ]):
            self.calls.clear()
            self.outputs = [sse(stream_event("POISON", usage=first), event),
                            sse(stream_event('{"questions":[]}', "stop", first))]
            result = self.stream(f"rejected-usage-{index}")
            self.assertNotIn("POISON", result.text)
            self.assertIn("[DONE]", result.text)
            self.assertEqual(len(self.calls), 2)
            self.assertEqual(request_status(self.user.id, f"rejected-usage-{index}")["usage"], {
                "model_calls": 2, "reported_calls": 2, "prompt_tokens": 20, "completion_tokens": 10,
            })


class FailoverBoundaries(unittest.IsolatedAsyncioTestCase):
    async def test_small_stream_events_are_delivered_without_waiting_for_a_full_buffer(self):
        class SlowStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices":[]}\n\n'
                await asyncio.Event().wait()

        response = httpx.Response(200, stream=SlowStream())
        lines = limited_lines(response, 1024)
        try:
            first = await asyncio.wait_for(anext(lines), 1)
            self.assertEqual(first, 'data: {"choices":[]}')
        finally:
            await lines.aclose()
            await response.aclose()

    async def test_text_candidate_total_deadline_immediately_uses_next(self):
        candidates = [{"api_key": "fake", "base_url": "https://unused.invalid", "model": name,
                       "timeout": 0.01 if name == "first" else 1, "max_tokens": 4096} for name in ("first", "second")]

        async def chat(*args, **kwargs):
            if kwargs["model"] == "first":
                await asyncio.Event().wait()
            return '{"ok":true}'

        with patch.object(generate, "_merged_llm_params", return_value={"models": candidates}), \
                patch.object(llm_client, "chat", new=AsyncMock(side_effect=chat)) as model:
            self.assertEqual(await generate._call_llm_and_parse("system", "user"), {"ok": True})
        self.assertEqual([call.kwargs["model"] for call in model.await_args_list], ["first", "second"])
        self.assertTrue(all(call.kwargs["max_attempts"] == 1 for call in model.await_args_list))

    async def test_local_rejection_cancellation_and_unexpected_errors_do_not_switch(self):
        for error in [HTTPException(429, {"code": "generation_budget"}), HTTPException(400, "invalid endpoint"),
                      asyncio.CancelledError(), httpx.PoolTimeout("pool busy"), RuntimeError("local bug")]:
            invoke = AsyncMock(side_effect=error)
            with self.assertRaises(type(error)):
                await run_with_failover([{"id": "a"}, {"id": "b"}], invoke)
            self.assertEqual(invoke.await_count, 1)

    async def test_truncation_switches_and_last_partial_is_preserved(self):
        error = OutputTruncated('{"partial":"retained"}')
        invoke = AsyncMock(side_effect=[error, {"ok": True}])
        self.assertEqual(await run_with_failover([{}, {}], invoke), {"ok": True})
        invoke = AsyncMock(side_effect=error)
        with self.assertRaises(OutputTruncated) as caught:
            await run_with_failover([{}, {}], invoke)
        self.assertEqual(caught.exception.partial_text, '{"partial":"retained"}')
