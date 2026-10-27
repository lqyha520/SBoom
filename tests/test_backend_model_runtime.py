"""模型运行策略回归：仅使用一次性 PostgreSQL 和离线供应商。"""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import test_backend_model_failover as fixtures
from fastapi import HTTPException
from test_backend_reliability import questions, section

from app.config import get_settings
from app.db import db
from app.routers import generate
from app.services import app_config, provider_health
from app.services.generation_policy import current_policy, load_policy
from app.services.llm_client import llm_client
from app.services.provider_failover import stream_with_health


@pytest.fixture
def case():
    fixture = fixtures.ModelFailover(methodName="runTest")
    fixture.setUp()
    try:
        yield fixture
    finally:
        fixture.doCleanups()


def test_task_timeout_follows_config_and_includes_repairs_review_and_transport(case):
    app_config.save_llm_models([fixtures.profile("first", timeout=10), fixtures.profile("second", timeout=20)])
    with patch.object(get_settings(), "generation_repair_limit", 3):
        result = case.client.get("/api/v1/generation/options?kind=text")
    assert result.status_code == 200
    assert "no-store" in result.headers["Cache-Control"]
    assert result.json()["task_timeout_seconds"] == 180
    assert result.json()["timeout_ms"] == 210000
    assert "secret" not in result.text and "provider.invalid" not in result.text
    app_config.save_llm_models([fixtures.profile("first", timeout=600)])
    with patch.object(get_settings(), "generation_repair_limit", 3):
        assert load_policy("text").timeout_seconds == 2550
    with patch.object(get_settings(), "generation_lease_seconds", 60):
        assert load_policy("text").timeout_seconds == 55


def test_revision_race_rejects_before_recording_or_billing_but_replay_still_works(case):
    policy = case.client.get("/api/v1/generation/options").json()
    first = case.validate("recorded-before-update")
    app_config.save_llm_models([fixtures.profile("new")])
    body = {"grade": "小学三年级", "subject": "数学", "question_content": "1+2=?"}
    headers = {"X-Request-ID": "not-accepted", "X-Model-Config-Revision": policy["revision"]}
    result = case.client.post("/api/v1/validate", json=body, headers=headers)
    assert result.status_code == 409 and result.json()["detail"]["code"] == "model_config_changed"
    assert len(case.calls) == 1
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM generation_requests WHERE request_id = 'not-accepted'").fetchone()[0] == 0
    headers["X-Request-ID"] = "recorded-before-update"
    replay = case.client.post("/api/v1/validate", json=body, headers=headers)
    assert replay.json() == first.json() and len(case.calls) == 1


def test_new_task_bypasses_another_workers_old_cache(case):
    app_config.get_llm()
    with db() as conn:
        raw = json.loads(conn.execute("SELECT value FROM app_config WHERE key='llm'").fetchone()[0])
        raw["revision"] = "other-worker-revision"
        raw["models"][0]["model"] = "new-model"
        raw["models"][0]["timeout"] = 300
        conn.execute("UPDATE app_config SET value = ? WHERE key='llm'", (json.dumps(raw),))
    assert app_config.get_llm()["model"] == "model-first"
    assert case.client.get("/api/v1/generation/options").json()["revision"] == "other-worker-revision"
    assert case.validate("fresh-runtime").status_code == 200
    assert json.loads(case.calls[0].content)["model"] == "new-model"


def test_running_task_keeps_one_config_snapshot_for_repairs(case):
    models = []

    async def chat(*args, **kwargs):
        models.append(kwargs["model"])
        if len(models) == 1:
            app_config.save_llm_models([fixtures.profile("replacement")])
            return json.dumps({"sections": [section(count=1)]})
        return json.dumps({"questions": questions(1, start=20)})

    with patch.object(get_settings(), "generation_repair_limit", 1), patch.object(llm_client, "chat", new=chat):
        response = case.client.post("/api/v1/generate-batch", json=case.body, headers={"X-Request-ID": "snapshot"})
    assert response.status_code == 200, response.text
    assert models == ["model-first", "model-first"]
    assert generate._merged_llm_params()["models"][0]["model"] == "model-replacement"


def test_partial_primary_is_recovered_when_backup_times_out_and_replay_does_not_bill(case):
    partial = '{"sections":[' + json.dumps(section()) + ',{"section_id":'
    case.outputs = [httpx.Response(200, json={"choices": [{"message": {"content": partial}, "finish_reason": "length"}]}),
                    httpx.ReadTimeout("offline timeout")]
    response = case.client.post("/api/v1/generate-batch", json=case.body, headers={"X-Request-ID": "keep-primary"})
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "generation_truncated"
    assert len(detail["partial_sections"]) == 1 and len(detail["partial_sections"][0]["questions"]) == 2
    replay = case.client.post("/api/v1/generate-batch", json=case.body, headers={"X-Request-ID": "keep-primary"})
    assert replay.json() == response.json() and len(case.calls) == 2


def test_real_json_probe_uses_saved_compatibility_and_never_borrows_unknown_keys(case):
    app_config.save_llm_models([fixtures.profile("first", samplingMode="omit", tokenParameter="max_completion_tokens")])
    case.login_admin()
    case.outputs = [httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})]
    response = case.client.post("/api/v1/admin/test-llm-generation", json={"id": "first"})
    assert response.status_code == 200, response.text
    payload = json.loads(case.calls[0].content)
    assert payload["max_completion_tokens"] == 1024
    assert "temperature" not in payload and "top_p" not in payload and "max_tokens" not in payload
    assert payload["stream"] is False
    assert case.client.post("/api/v1/admin/test-llm-generation", json={"id": "unknown"}).status_code == 400
    assert len(case.calls) == 1
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM generation_requests").fetchone()[0] == 0


def test_real_probe_exposes_parameter_incompatibility_without_provider_body(case):
    case.login_admin()
    case.outputs = [fixtures.sse(fixtures.stream_event("ok")),
                    httpx.Response(400, json={"error": "secret-provider-body"})]
    assert case.client.post("/api/v1/admin/test-llm", json={"id": "first"}).status_code == 200
    response = case.client.post("/api/v1/admin/test-llm-generation", json={"id": "first"})
    assert response.status_code == 502 and "secret-provider-body" not in response.text
    payload = json.loads(case.calls[1].content)
    assert "temperature" in payload and "top_p" in payload
    response = case.client.post("/api/v1/admin/test-llm-generation", json={"apiKey": "private-key", "timeout": 999})
    assert response.status_code == 422 and "private-key" not in response.text


def test_real_probe_truncation_has_probe_specific_error(case):
    case.login_admin()
    case.outputs = [httpx.Response(200, json={"choices": [{"message": {"content": "private-partial"}, "finish_reason": "length"}]})]
    response = case.client.post("/api/v1/admin/test-llm-generation", json={"id": "first"})
    assert response.status_code == 422 and "token 上限" in response.text
    assert "查询原请求" not in response.text and "private-partial" not in response.text
    assert len(case.calls) == 1


def test_single_stream_tracks_health_skips_cooling_and_recovers(case):
    app_config.save_llm_models([fixtures.profile("first")])
    with patch.object(get_settings(), "provider_failure_threshold", 1):
        case.outputs = [httpx.Response(503)]
        assert "error" in case.stream("stream-failure").text
        candidate = generate._merged_llm_params()["models"][0]
        assert provider_health.summary([candidate])[0]["state"] == "cooling"
        assert "provider_cooling" in case.stream("stream-cooling").text
        assert len(case.calls) == 1
        with db() as conn:
            conn.execute("UPDATE provider_health SET cooldown_until=0")
        case.outputs = [fixtures.sse(fixtures.stream_event('{"questions":[]}', "stop"))]
        assert "[DONE]" in case.stream("stream-recovery").text
        health = provider_health.summary([candidate])[0]
        assert health["state"] == "healthy" and health["failures"] == 1 and health["successes"] == 1


def test_closing_single_stream_releases_recovery_probe_without_recording_failure(case):
    candidate = generate._merged_llm_params()["models"][0]
    with patch.object(get_settings(), "provider_failure_threshold", 1):
        assert provider_health.claim(candidate)
        provider_health.record(candidate, 0.1, success=False)
        with db() as conn:
            conn.execute("UPDATE provider_health SET cooldown_until=0")

        async def tokens(_candidate):
            yield "first-token"
            yield "next-token"

        async def consume():
            stream = stream_with_health(candidate, tokens)
            assert await anext(stream) == "first-token"
            assert provider_health.summary([candidate])[0]["state"] == "probing"
            await stream.aclose()

        asyncio.run(consume())
        health = provider_health.summary([candidate])[0]
        assert health["state"] == "recovering" and health["failures"] == 1 and health["successes"] == 0


def test_health_cools_failures_and_recovers_one_candidate_at_a_time(case):
    with patch.object(get_settings(), "provider_failure_threshold", 2):
        for index in range(2):
            case.outputs = [httpx.Response(503)]
            assert case.validate(f"failure-{index}").status_code == 200
        case.calls.clear()
        assert case.validate("skips-cooling").status_code == 200
        assert [json.loads(call.content)["model"] for call in case.calls] == ["model-second"]
        primary = generate._merged_llm_params()["models"][0]
        assert provider_health.summary([primary])[0]["state"] == "cooling"
        with db() as conn:
            conn.execute("UPDATE provider_health SET cooldown_until=0 WHERE profile_id='first'")
        candidates = [dict(primary) for _ in range(6)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            claims = list(pool.map(provider_health.claim, candidates))
        assert sum(claims) == 1
        provider_health.record(candidates[claims.index(True)], 0.2, success=True)
        assert provider_health.summary([primary])[0]["state"] == "healthy"
        assert case.validate("restored").status_code == 200
        assert json.loads(case.calls[-1].content)["model"] == "model-first"


def test_config_change_resets_cooling_and_old_inflight_results_do_not_pollute_it(case):
    with patch.object(get_settings(), "provider_failure_threshold", 1):
        old = generate._merged_llm_params()["models"][0]
        assert provider_health.claim(old)
        provider_health.record(old, 1, success=False)
        assert not provider_health.claim(old)
        app_config.save_llm_models(case.profiles)
        fresh = generate._merged_llm_params()["models"][0]
        assert provider_health.claim(fresh)
        provider_health.record(old, 1, success=False)
        assert provider_health.summary([fresh])[0]["failures"] == 0


def test_all_cooling_never_calls_provider_and_local_errors_do_not_open_circuit(case):
    app_config.save_llm_models([fixtures.profile("first")])
    with patch.object(get_settings(), "provider_failure_threshold", 1):
        case.outputs = [httpx.Response(503)]
        assert case.validate("open-circuit").status_code == 502
        result = case.validate("no-new-bill")
        assert result.status_code == 429 and result.json()["detail"]["code"] == "provider_cooling"
        assert len(case.calls) == 1
    app_config.save_llm_models([fixtures.profile("first")])
    with patch.object(llm_client, "chat", new=AsyncMock(side_effect=HTTPException(429, {"code": "generation_budget"}))):
        assert case.validate("local-budget").status_code == 429
    primary = generate._merged_llm_params()["models"][0]
    assert provider_health.summary([primary])[0]["failures"] == 0
    assert current_policy.get() is None


def test_health_admin_api_is_private_and_distinguishes_same_model_names(case):
    assert case.client.get("/api/v1/admin/model-health").status_code == 403
    app_config.save_llm_models([fixtures.profile("first").model_copy(update={"model": "shared-name"}),
                               fixtures.profile("second").model_copy(update={"model": "shared-name"})])
    case.validate("health-record")
    case.login_admin()
    response = case.client.get("/api/v1/admin/model-health?kind=text")
    assert response.status_code == 200 and "secret" not in response.text and "provider.invalid" not in response.text
    models = response.json()["models"]
    assert models[0]["id"] == "first" and models[0]["successes"] == 1
    assert models[1]["id"] == "second" and models[1]["successes"] == 0
    assert response.json()["task_timeout_seconds"] > 0


def test_existing_database_upgrade_creates_health_table_and_preserves_config(case):
    from app import db as database
    saved = app_config.get_admin_config()
    with db() as conn:
        conn.execute("DROP TABLE provider_health")
        conn.execute("DELETE FROM schema_migrations WHERE version = ?", (database.SCHEMA_VERSION,))
        conn.execute("INSERT INTO schema_migrations(version) VALUES (?) ON CONFLICT DO NOTHING", (2026102402,))
    database.init_db(migrate=True)
    database.init_db(migrate=False)
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM provider_health").fetchone()[0] == 0
    assert app_config.get_admin_config() == saved
