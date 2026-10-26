"""Offline regression tests. Every database and secret file is disposable."""

import asyncio
import gzip
import json
import os
import tempfile
import time
import unittest
import zlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pg_support  # noqa: E402  建一次性测试库，必须在 import app 之前

pg_support.install_module_database({"SECRET_KEY": "test-reliability-secret-not-for-production",
                                    "LLM_API_KEY": "", "ADMIN_USERNAME": "", "ADMIN_PASSWORD": ""})

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import db as database
from app import security
from app.config import Settings, get_settings
from app.deps import SESSION_COOKIE
from app.routers import generate, me
from app.services import generation_control as control
from app.services import user_store
from app.services.llm_client import LLMClient
from app.services.question_qc import arithmetic_value, question_issue


def questions(count=2, start=1, kind="fill_blank"):
    return [{"type": kind, "stem": f"{start + i} + 8 = ____", "answer": str(start + i + 8),
             "analysis": f"{start + i}+8={start + i + 8}"}
            for i in range(count)]


def section(section_id="s1", count=2, start=1, kind="fill_blank"):
    return {"section_id": section_id, "game_type": kind, "questions": questions(count, start, kind)}


def incomplete_sections(response):
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "generation_incomplete", detail
    return detail["partial_sections"]


async def passed_review(_system, user_message, _count):
    """生成链路回归隔离第二次模型调用；复核协议另有专门的集成测试。"""
    payload = json.loads(user_message)
    return {"reviews": [{"review_id": question["review_id"], "status": "passed", "reason": ""}
                        for section in payload["sections"] for question in section["questions"]]}


class BackendReliability(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        _root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="lc-test-")))
        pg_support.case_database(self.stack)
        self.stack.enter_context(patch.object(get_settings(), "generation_repair_limit", 0))
        self.stack.enter_context(patch.object(get_settings(), "generation_daily_limit", 100))
        self.stack.enter_context(patch.object(get_settings(), "generation_daily_failure_limit", 1000))
        self.stack.enter_context(patch.object(get_settings(), "generation_user_concurrency", 3))
        self.stack.enter_context(patch.object(get_settings(), "generation_global_concurrency", 6))
        self.stack.enter_context(patch.object(generate, "_call_quality_review", new=AsyncMock(side_effect=passed_review)))
        # An accidental provider request is a test failure, never real traffic.
        self.stack.enter_context(patch.object(httpx.AsyncClient, "post", side_effect=AssertionError("External HTTP disabled")))
        database.init_db()
        self.user = user_store.create_user("teacher-one", "test-password")
        self.other = user_store.create_user("teacher-two", "test-password")
        app = FastAPI()
        app.include_router(generate.router)
        app.include_router(me.router)
        self.client = self.stack.enter_context(TestClient(app))
        self.client.cookies.set(SESSION_COOKIE, security.create_token(self.user.id))
        self.body = {"grade": "小学三年级", "subject": "数学", "keyword": "加法", "difficulty": "medium",
                     "items": [{"section_id": "s1", "game_type": "fill_blank", "question_count": 2}]}

    def send(self, data=None, request_id="job-one", body=None):
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(return_value=data or {"sections": [section()]})) as mock:
            result = self.client.post("/api/v1/generate-batch", json=body or self.body,
                                      headers={"X-Request-ID": request_id})
        return result, mock

    def test_reordered_repeated_types_match_by_section_id(self):
        self.body["items"] = [{"section_id": "four", "game_type": "fill_blank", "question_count": 4},
                              {"section_id": "six", "game_type": "fill_blank", "question_count": 6}]
        response, mock = self.send({"sections": [section("six", 6, 20), section("four", 4)]})
        self.assertEqual(response.status_code, 200, response.text)
        values = response.json()["sections"]
        self.assertEqual([x["section_id"] for x in values], ["four", "six"])
        self.assertEqual([len(x["questions"]) for x in values], [4, 6])
        self.assertEqual(values[0]["questions"][0]["stem"], "1 + 8 = ____")
        self.assertEqual(mock.await_count, 1)

    def test_duplicate_section_ids_rejected_before_model(self):
        self.body["items"] *= 2
        response, mock = self.send()
        self.assertEqual(response.status_code, 422)
        mock.assert_not_awaited()

    def test_ambiguous_legacy_sections_not_reused(self):
        self.body["items"].append({"section_id": "s2", "game_type": "fill_blank", "question_count": 2})
        legacy = [{"game_type": "fill_blank", "questions": questions(2, i * 10)} for i in range(2)]
        response, _ = self.send({"sections": legacy})
        self.assertEqual([x["missing_count"] for x in incomplete_sections(response)], [2, 2])

    def test_unique_legacy_type_remains_supported(self):
        response, _ = self.send({"sections": [{"game_type": "fill_blank", "questions": questions()}]})
        self.assertEqual(response.json()["sections"][0]["missing_count"], 0)

    def test_reading_preserves_passage_without_unrelated_repairs(self):
        get_settings().generation_repair_limit = 3
        self.body["items"] = [{"section_id": "reading", "game_type": "reading", "question_count": 2}]
        raw = {"sections": [{"section_id": "reading", "game_type": "reading", "passage": "春天来了。小明去公园。",
                            "questions": [{"type": "multiple_choice", "stem": "小明去了哪里？", "options": ["公园", "学校"], "answer": 0}]}]}
        response, mock = self.send(raw)
        result = incomplete_sections(response)[0]
        self.assertEqual(result["passage"], raw["sections"][0]["passage"])
        self.assertEqual(result["missing_count"], 1)
        self.assertEqual(mock.await_count, 1)

    def test_reading_without_passage_is_not_accepted(self):
        self.body["items"] = [{"section_id": "s1", "game_type": "reading", "question_count": 2}]
        response, _ = self.send({"sections": [section(kind="reading")]})
        result = incomplete_sections(response)[0]
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["missing_count"], 2)

    def test_malformed_output_never_fabricates_stems(self):
        raw = section()
        raw["questions"] = [{"answer": "2"}, None, "not a question"]
        response, _ = self.send({"sections": [raw]})
        result = incomplete_sections(response)[0]
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["missing_count"], 2)
        self.assertTrue(result["quality_warnings"])

    def test_excess_questions_are_truncated_and_metadata_is_owned(self):
        raw = section(count=8)
        raw.update(grade="wrong", subject="wrong", difficulty="wrong", total_score="not a number")
        response, _ = self.send({"sections": [raw]})
        result = response.json()["sections"][0]
        self.assertEqual(len(result["questions"]), 2)
        self.assertEqual(result["grade"], self.body["grade"])
        self.assertEqual(result["total_score"], 100)

    def test_repairs_share_one_bounded_budget(self):
        get_settings().generation_repair_limit = 2
        raw = {"sections": [section(count=0)]}
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(return_value=raw)) as mock:
            response = self.client.post("/api/v1/generate-batch", json=self.body)
        self.assertEqual(mock.await_count, 2)
        self.assertEqual(incomplete_sections(response)[0]["missing_count"], 2)

    def test_identical_questions_are_rejected_across_sections(self):
        self.body["items"].append({"section_id": "s2", "game_type": "fill_blank", "question_count": 2})
        response, model = self.send({"sections": [section(), section("s2")]})
        values = incomplete_sections(response)
        self.assertEqual([x["missing_count"] for x in values], [0, 2])
        self.assertEqual([len(x["questions"]) for x in values], [2, 0])
        model.assert_awaited_once()

    def test_incomplete_is_failed_and_replay_preserves_questions_without_model_calls(self):
        response, model = self.send({"sections": [section(count=1)]})
        kept = incomplete_sections(response)
        model.assert_awaited_once()
        status = self.client.get("/api/v1/me/generations/job-one").json()
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["error"]["partial_sections"], kept)
        replay, model = self.send()
        self.assertEqual(replay.json(), response.json())
        model.assert_not_awaited()
        self.assertEqual(self.client.get("/api/v1/me/usage").json()["succeeded"], 0)

    def test_incomplete_single_keeps_valid_questions(self):
        body = {key: value for key, value in self.body.items() if key != "items"}
        body.update(game_type="fill_blank", question_count=2)
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(return_value=section(count=1))) as model:
            response = self.client.post("/api/v1/generate", json=body)
        kept = incomplete_sections(response)[0]
        self.assertEqual((len(kept["questions"]), kept["missing_count"]), (1, 1))
        model.assert_awaited_once()

    def test_fullwidth_math_survives_without_paid_repairs(self):
        get_settings().generation_repair_limit = 3
        self.body["items"] = [{"section_id": "s1", "game_type": "oral_math", "question_count": 2},
                              {"section_id": "s2", "game_type": "compare", "question_count": 1}]
        raw = {"sections": [
            {"section_id": "s1", "game_type": "oral_math", "questions": [
                {"type": "oral_math", "stem": "９＋４＝（　）", "answer": "13"},
                {"type": "oral_math", "stem": "８＋６＝____", "answer": "14"},
            ]},
            {"section_id": "s2", "game_type": "compare", "questions": [
                {"type": "compare", "left_expr": "９＋６", "right_expr": "１４", "answer": ">"},
            ]},
        ]}
        response, model = self.send(raw)
        self.assertEqual(response.status_code, 200, response.text)
        model.assert_awaited_once()
        self.assertEqual([len(s["questions"]) for s in response.json()["sections"]], [2, 1])

    def test_rejection_details_include_initial_and_repair_failures(self):
        get_settings().generation_repair_limit = 1
        bad = {"type": "oral_math", "stem": "9+4=", "answer": "99"}
        self.body["items"] = [{"section_id": "s1", "game_type": "oral_math", "question_count": 1}]
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(side_effect=[
            {"sections": [{"section_id": "s1", "questions": [bad]}]},
            {"questions": [{"type": "oral_math", "stem": "计算9+4", "answer": 13}]},
        ])) as model:
            response = self.client.post("/api/v1/generate-batch", json=self.body)
        warnings = incomplete_sections(response)[0]["quality_warnings"]
        self.assertIn("计算题答案不正确", warnings[0])
        self.assertIn("补题", warnings[1])
        self.assertIn("计算题算式格式不正确", warnings[1])
        self.assertEqual(model.await_count, 2)

    def test_same_request_replays_once_and_changed_payload_conflicts(self):
        first, _ = self.send()
        second, mock = self.send()
        self.assertEqual(first.json(), second.json())
        mock.assert_not_awaited()
        self.body["keyword"] = "different"
        response, mock = self.send()
        self.assertEqual(response.status_code, 409)
        mock.assert_not_awaited()

    def test_timeout_is_recorded_without_retry(self):
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(side_effect=HTTPException(504, {"error": "Timed out"}))) as mock:
            for _ in range(2):
                result = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "timeout"})
                self.assertEqual(result.status_code, 504)
            self.assertEqual(mock.await_count, 1)
        status = self.client.get("/api/v1/me/generations/timeout").json()
        self.assertEqual(status["status"], "unknown")
        self.assertEqual(result.json()["detail"]["request_id"], "timeout")

    def test_gzip_provider_response_generates_paper_and_replays_without_new_call(self):
        calls = []
        body = json.dumps({
            "choices": [{"message": {"content": json.dumps({"sections": [section()]})}}],
            "usage": {"prompt_tokens": 123, "completion_tokens": 456},
        }).encode()
        def respond(request):
            calls.append(request)
            return httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(body))
        http = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://provider.invalid")
        try:
            with patch.object(generate.llm_client, "_get_client_for", return_value=http), \
                    patch.object(generate, "_merged_llm_params", return_value={
                        "base_url": "https://provider.invalid", "model": "test", "api_key": "fake",
                        "timeout": 120, "max_tokens": 16384,
                    }):
                first = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "gzip-paper"})
                self.assertEqual(first.status_code, 200, first.text)
                self.assertEqual(len(first.json()["sections"][0]["questions"]), 2)
                replay = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "gzip-paper"})
                self.assertEqual(first.json(), replay.json())
                self.assertEqual(len(calls), 1)
            status = self.client.get("/api/v1/me/generations/gzip-paper").json()
            self.assertEqual(status["status"], "succeeded")
            self.assertEqual(status["result"]["sections"], first.json()["sections"])
        finally:
            asyncio.run(http.aclose())

    def test_broken_provider_compression_has_specific_error_without_retry(self):
        with patch.object(generate.llm_client, "chat", new=AsyncMock(side_effect=httpx.DecodingError("bad compression"))) as model, \
                patch.object(generate, "_merged_llm_params", return_value={
                    "base_url": "https://provider.invalid", "model": "test", "api_key": "fake",
                    "timeout": 120, "max_tokens": 16384,
                }):
            response = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "broken-gzip"})
            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.json()["detail"]["code"], "provider_decoding_error")
            self.assertNotIn("bad compression", response.text)
            model.assert_awaited_once()
            self.assertEqual(self.client.get("/api/v1/me/generations/broken-gzip").json()["status"], "unknown")

    def test_daily_quota_and_replay_do_not_spend_twice(self):
        get_settings().generation_daily_limit = 1
        self.assertEqual(self.send()[0].status_code, 200)
        self.assertEqual(self.send()[0].status_code, 200)
        response, mock = self.send(request_id="new-job")
        self.assertEqual(response.status_code, 429)
        mock.assert_not_awaited()
        self.assertEqual(self.client.get("/api/v1/me/usage").json()["requests"], 1)

    def test_failed_requests_return_quota_but_consume_failure_allowance(self):
        """上游失败要把次数退还用户，但另设失败上限，防止对着坏上游无限重试烧预算。"""
        settings = get_settings()
        settings.generation_daily_limit = 2
        settings.generation_daily_failure_limit = 6
        now = int(time.time())
        with database.db() as conn:
            for index in range(5):
                conn.execute(
                    "INSERT INTO generation_requests(user_id,request_id,kind,payload_hash,status,created_at) "
                    "VALUES (?, ?, 'image', 'old', 'failed', ?)", (self.user.id, f"down-{index}", now),
                )
        control._begin(self.user.id, "after-failures", "batch", {})
        with database.db() as conn:
            for index in range(2):
                conn.execute(
                    "INSERT INTO generation_requests(user_id,request_id,kind,payload_hash,status,created_at) "
                    "VALUES (?, ?, 'image', 'old', 'succeeded', ?)", (self.user.id, f"done-{index}", now),
                )
        with self.assertRaises(HTTPException) as quota:
            control._begin(self.user.id, "over-quota", "batch", {})
        self.assertEqual(quota.exception.status_code, 429)
        self.assertEqual(quota.exception.detail["code"], "generation_quota")
        settings.generation_daily_limit = 10  # 放开成功额度，让失败上限成为唯一约束
        settings.generation_daily_failure_limit = 4
        with self.assertRaises(HTTPException) as cap:
            control._begin(self.user.id, "over-failures", "batch", {})
        self.assertEqual(cap.exception.detail["code"], "generation_failure_quota")
        usage = self.client.get("/api/v1/me/usage").json()
        self.assertEqual((usage["succeeded"], usage["failed"], usage["quota_used"]), (2, 5, 3))

    def test_parallel_admission_is_atomic(self):
        def admit(index):
            try:
                control._begin(self.user.id, f"parallel-{index}", "batch", {})
                return 200
            except HTTPException as exc:
                return exc.status_code
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(admit, range(12)))
        self.assertEqual(statuses.count(200), 3)
        self.assertEqual(statuses.count(429), 9)

    def test_zero_daily_limit_allows_requests_beyond_default_and_preserves_replay(self):
        get_settings().generation_daily_limit = 0
        self.assertEqual(Settings(generation_daily_limit=0).generation_daily_limit, 0)
        with self.assertRaises(ValidationError):
            Settings(generation_daily_limit=-1)
        with database.db() as conn:
            for index in range(20):
                conn.execute(
                    "INSERT INTO generation_requests(user_id,request_id,kind,payload_hash,status,created_at) "
                    "VALUES (?, ?, 'batch', 'old', 'failed', ?)",
                    (self.user.id, f"past-{index}", int(time.time())),
                )
        first, model = self.send()
        self.assertEqual(first.status_code, 200)
        model.assert_awaited_once()
        replay, model = self.send()
        self.assertEqual(first.json(), replay.json())
        model.assert_not_awaited()
        usage = self.client.get("/api/v1/me/usage").json()
        self.assertEqual((usage["requests"], usage["daily_limit"]), (21, 0))

    def test_zero_daily_limit_keeps_concurrency_protection(self):
        get_settings().generation_daily_limit = 0
        for index in range(3):
            control._begin(self.user.id, f"active-{index}", "batch", {})
        response, model = self.send()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"]["code"], "generation_busy")
        model.assert_not_awaited()

    def test_running_request_is_not_started_again(self):
        control._begin(self.user.id, "running", "batch", {})
        with self.assertRaises(HTTPException) as context:
            control._begin(self.user.id, "running", "batch", {})
        self.assertEqual(context.exception.status_code, 409)

    def test_results_are_account_isolated(self):
        self.send()
        self.client.cookies.set(SESSION_COOKIE, security.create_token(self.other.id))
        self.assertEqual(self.client.get("/api/v1/me/generations/job-one").status_code, 404)
        response, mock = self.send()
        self.assertEqual(response.status_code, 200)
        mock.assert_awaited_once()

    def test_expired_cache_does_not_restart_provider(self):
        self.send()
        with database.db() as conn:
            conn.execute("UPDATE generation_requests SET finished_at = ?", (int(time.time()) - 86400 * 10,))
        status = self.client.get("/api/v1/me/generations/job-one").json()
        self.assertTrue(status["cache_expired"])
        self.assertIsNone(status["result"])
        response, mock = self.send()
        self.assertEqual(response.status_code, 410)
        mock.assert_not_awaited()

    def test_provider_usage_is_reported_not_estimated(self):
        async def model(*_, **kwargs):
            control.record_attempt()
            control.record_usage({"prompt_tokens": 42, "completion_tokens": 21})
            return {"sections": [section()]}
        with patch.object(generate, "_call_llm_and_parse", new=model):
            self.client.post("/api/v1/generate-batch", json=self.body).raise_for_status()
        usage = self.client.get("/api/v1/me/usage").json()
        self.assertEqual((usage["model_calls"], usage["reported_calls"], usage["prompt_tokens"], usage["completion_tokens"]), (1, 1, 42, 21))

    def test_owned_request_exposes_only_its_recorded_usage(self):
        async def model(*_, **kwargs):
            control.record_attempt()
            control.record_usage({"prompt_tokens": 42, "completion_tokens": 21})
            return {"sections": [section()]}
        with patch.object(generate, "_call_llm_and_parse", new=model):
            response = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "usage-one"})
        self.assertEqual(response.status_code, 200)
        result = self.client.get("/api/v1/me/generations/usage-one").json()
        self.assertEqual(result["usage"], {"model_calls": 1, "reported_calls": 1, "prompt_tokens": 42, "completion_tokens": 21})
        self.assertNotIn("user_id", result)

    def test_stream_is_metered_and_not_replayed(self):
        async def stream(*args, **kwargs):
            control.record_attempt()
            yield json.dumps({"questions": questions()})
        body = {key: value for key, value in self.body.items() if key != "items"}
        body.update(game_type="fill_blank", question_count=2)
        with patch.object(generate, "_merged_llm_params", return_value={"base_url": "http://unused", "model": "test", "api_key": "fake", "timeout": 120, "max_tokens": 16384}), \
                patch.object(generate.llm_client, "chat_stream", new=stream):
            response = self.client.post("/api/v1/generate/stream", json=body, headers={"X-Request-ID": "stream-one"})
        self.assertIn("[DONE]", response.text)
        self.assertEqual(response.headers["X-Request-ID"], "stream-one")
        self.assertEqual(control.request_status(self.user.id, "stream-one")["status"], "succeeded")
        with self.assertRaises(HTTPException) as context:
            control._begin(self.user.id, "stream-one", "stream", generate.GenerateRequest(**body).model_dump(mode="json"))
        self.assertEqual(context.exception.status_code, 410)

    def test_template_revision_conflict_preserves_current_data(self):
        template = {"name": "Lesson", "cards": [], "title": "original"}
        first = self.client.put("/api/v1/me/templates", json={"template": template, "expected_revision": 0})
        self.assertEqual(first.json()["revision"], 1)
        template["title"] = "new"
        saved = self.client.put("/api/v1/me/templates", json={"template": template, "expected_revision": 1})
        self.assertEqual(saved.json()["revision"], 2)
        template["title"] = "stale"
        for revision in (0, 1):
            self.assertEqual(self.client.put("/api/v1/me/templates", json={"template": template, "expected_revision": revision}).status_code, 409)
        self.assertEqual(self.client.delete("/api/v1/me/templates", params={"name": "Lesson", "expected_revision": 1}).status_code, 409)
        current = self.client.get("/api/v1/me/templates").json()["templates"][0]
        self.assertEqual((current["title"], current["_revision"]), ("new", 2))

    def test_bulk_migration_never_overwrites_newer_template(self):
        user_store.upsert_template(self.user.id, "Lesson", {"name": "Lesson", "title": "new"})
        count = user_store.bulk_upsert_templates(self.user.id, [{"name": "Lesson", "title": "old"}, {"name": "Other"}])
        self.assertEqual(count, 1)
        self.assertEqual(next(t for t in user_store.list_templates(self.user.id) if t["name"] == "Lesson")["title"], "new")

    def test_additive_migrations_are_repeatable(self):
        user_store.upsert_template(self.user.id, "Keep", {"name": "Keep"})
        database.init_db()
        database.init_db()
        self.assertEqual(user_store.list_templates(self.user.id)[0]["name"], "Keep")

    def test_stale_revision_cannot_overwrite_a_recreated_template(self):
        revision = user_store.upsert_template(self.user.id, "Same", {"name": "Same"}, 0)
        user_store.delete_template(self.user.id, "Same", revision)
        recreated = user_store.upsert_template(self.user.id, "Same", {"name": "Same", "title": "new"}, 0)
        self.assertGreater(recreated, revision)
        with self.assertRaises(user_store.TemplateConflict):
            user_store.upsert_template(self.user.id, "Same", {"name": "Same", "title": "stale"}, revision)

    def test_account_change_header_blocks_writes_under_a_different_cookie(self):
        response = self.client.post("/api/v1/generate-batch", json=self.body,
                                    headers={"X-Workspace-User": str(self.other.id)})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "account_changed")
        self.assertEqual(control.usage_summary(self.user.id)["requests"], 0)


class QuestionQuality(unittest.TestCase):
    def test_fullwidth_format_is_accepted_but_wrong_answers_and_unsafe_math_are_not(self):
        from app.services.question_qc import question_fingerprint

        normal = {"type": "oral_math", "stem": "9+4=", "answer": 13}
        for stem in ("９＋４＝", "9＋4＝____", "９＋４＝（　）", "９＋４＝（？）"):
            question = {**normal, "stem": stem}
            self.assertIsNone(question_issue(question), stem)
            self.assertEqual(question_fingerprint(question), question_fingerprint(normal))
            self.assertEqual(question_issue({**question, "answer": 99}), "计算题答案不正确")
        for expression in ("２**１００", "2²+1", "１／０", "__import__('os')"):
            self.assertIsNone(arithmetic_value(expression))
        self.assertIsNotNone(question_issue({**normal, "stem": "9+4=13"}))

    def test_fixed_evaluation_cases(self):
        cases = json.loads((Path(__file__).parent / "fixtures" / "question-quality.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                self.assertEqual(question_issue(case["question"]) is None, case["valid"], question_issue(case["question"]))

    def test_arithmetic_does_not_execute_expressions(self):
        for value in ["__import__('os').system('bad')", "2 ** 100000000", "1 / 0", "a+1", "[1,2]*100"]:
            self.assertIsNone(arithmetic_value(value))


class SecurityConfiguration(unittest.TestCase):
    def test_dotenv_key_is_used(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ):
            os.environ.pop("SECRET_KEY", None)
            env = Path(root) / ".env"
            env.write_text("SECRET_KEY=dotenv-test-secret-abcdefghijklmnopqrstuvwxyz\n", encoding="utf-8")
            configured = Settings(_env_file=env)
            with patch.object(security, "_cached_secret", None), patch.object(security, "get_settings", return_value=configured):
                self.assertEqual(security.get_secret(), b"dotenv-test-secret-abcdefghijklmnopqrstuvwxyz")

    def test_legacy_ciphertext_and_base64_survive_key_source_fix(self):
        with tempfile.TemporaryDirectory() as root:
            secret_file = Path(root) / "secret.txt"
            secret_file.write_text("legacy-file-key", encoding="utf-8")
            encrypted = "enc:" + security._fernet(b"legacy-file-key").encrypt(b"legacy-api-key").decode()
            with patch.object(security, "_SECRET_FILE", secret_file), patch.object(security, "_cached_secret", None):
                self.assertEqual(security.decrypt_secret(encrypted), "legacy-api-key")
                self.assertEqual(security.decrypt_secret("b64:bGVnYWN5LWFwaS1rZXk="), "legacy-api-key")
                self.assertTrue(security.encrypt_secret("new-api-key").startswith("enc:"))

    def test_empty_secret_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            secret_file = Path(root) / "secret.txt"
            secret_file.touch()
            with patch.object(security, "_SECRET_FILE", secret_file), patch.object(security, "_DATA_DIR", Path(root)), \
                    patch.object(security, "_cached_secret", None), patch.object(security, "get_settings", return_value=Settings(_env_file=None, secret_key="")), \
                    patch.object(security.time, "sleep"):
                with self.assertRaises(RuntimeError):
                    security.get_secret()
                self.assertIsNone(security._cached_secret)

    def test_generation_configuration_is_bounded(self):
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, generation_repair_limit=-1)


class ProviderRetry(unittest.IsolatedAsyncioTestCase):
    async def test_compressed_responses_are_decoded_once_and_usage_is_preserved(self):
        content = '{"sections":[{"topic":"加法练习"}]}'
        body = json.dumps({
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 123, "completion_tokens": 456},
        }, ensure_ascii=False).encode()

        class Chunks(httpx.AsyncByteStream):
            def __init__(self, value):
                self.value = value

            async def __aiter__(self):
                for index in range(0, len(self.value), 7):
                    yield self.value[index:index + 7]

        for encoding, compressor in (("identity", lambda value: value), ("gzip", gzip.compress), ("deflate", zlib.compress)):
            with self.subTest(encoding=encoding):
                calls = []
                def respond(request, calls=calls, encoding=encoding, compressor=compressor):
                    calls.append(request)
                    return httpx.Response(200, headers={"Content-Encoding": encoding},
                                          stream=Chunks(compressor(body)))
                client = LLMClient()
                usage = control.Usage()
                token = control.current_usage.set(usage)
                try:
                    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://provider.invalid") as http:
                        with patch.object(client, "_get_client_for", return_value=http), patch("app.services.llm_client.reserve"):
                            self.assertEqual(await client.chat([], api_key="fake"), content)
                    self.assertEqual(len(calls), 1)
                    self.assertEqual((usage.model_calls, usage.prompt_tokens, usage.completion_tokens), (1, 123, 456))
                finally:
                    control.current_usage.reset(token)

    async def test_lru_eviction_keeps_active_borrowers_open(self):
        client = LLMClient()
        try:
            with patch.object(LLMClient, "MAX_CACHED_CLIENTS", 1):
                async with client._borrow_client("http://unused-one", "fake") as first:
                    async with client._borrow_client("http://unused-one", "fake") as shared:
                        self.assertIs(first, shared)
                        async with client._borrow_client("http://unused-two", "fake") as second:
                            await asyncio.sleep(0)
                            self.assertFalse(first.is_closed)
                            self.assertFalse(second.is_closed)
                            self.assertEqual(len(client._clients), 2)
                        await asyncio.sleep(0)
                        self.assertTrue(second.is_closed)
                        self.assertFalse(first.is_closed)
                    self.assertFalse(first.is_closed)
                async with client._borrow_client("http://unused-three", "fake"):
                    await asyncio.sleep(0)
                    self.assertTrue(first.is_closed)
                    self.assertEqual(len(client._clients), 1)
        finally:
            await client.close()

    async def test_uncertain_transport_failures_are_not_retried(self):
        for error in (httpx.ReadTimeout("timeout"), httpx.ReadError("read"), httpx.WriteError("write"), httpx.RemoteProtocolError("protocol"), httpx.DecodingError("decode")):
            client = LLMClient()
            fake = AsyncMock(spec=httpx.AsyncClient)
            fake.post.side_effect = error
            @asynccontextmanager
            async def streamed(*args, fake=fake, **kwargs):
                yield await fake.post(*args, **kwargs)
            fake.stream.side_effect = streamed
            with patch.object(client, "_get_client_for", return_value=fake):
                with self.assertRaises(type(error)):
                    await client.chat([], base_url="http://unused", api_key="fake")
            self.assertEqual(fake.post.await_count, 1)

    async def test_connect_retry_does_not_close_shared_client(self):
        client = LLMClient()
        fake = AsyncMock(spec=httpx.AsyncClient)
        result = httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}, request=httpx.Request("POST", "http://unused"))
        fake.post.side_effect = [httpx.ConnectError("connect"), result]
        @asynccontextmanager
        async def streamed(*args, fake=fake, **kwargs):
            yield await fake.post(*args, **kwargs)
        fake.stream.side_effect = streamed
        with patch.object(client, "_get_client_for", return_value=fake), patch("app.services.llm_client.asyncio.sleep", new=AsyncMock()):
            self.assertEqual(await client.chat([], base_url="http://unused", api_key="fake"), "ok")
        fake.aclose.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
