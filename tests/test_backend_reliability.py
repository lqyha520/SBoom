"""Offline regression tests. Every database and secret file is disposable."""

import asyncio
import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.update({"DATABASE_URL": "", "SECRET_KEY": "test-reliability-secret-not-for-production",
                   "LLM_API_KEY": "", "ADMIN_USERNAME": "", "ADMIN_PASSWORD": ""})

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app import db as database, security
from app.config import Settings, get_settings
from app.deps import SESSION_COOKIE
from app.routers import generate, me
from app.services import generation_control as control, user_store
from app.services.llm_client import LLMClient
from app.services.question_qc import arithmetic_value, question_issue


def questions(count=2, start=1, kind="fill_blank"):
    return [{"type": kind, "stem": f"{start + i} + 8 = ____", "answer": str(start + i + 8)}
            for i in range(count)]


def section(section_id="s1", count=2, start=1, kind="fill_blank"):
    return {"section_id": section_id, "game_type": kind, "questions": questions(count, start, kind)}


class BackendReliability(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="lc-test-")))
        self.stack.enter_context(patch.object(database, "DB_PATH", root / "test.db"))
        self.stack.enter_context(patch.object(get_settings(), "generation_repair_limit", 0))
        self.stack.enter_context(patch.object(get_settings(), "generation_daily_limit", 100))
        self.stack.enter_context(patch.object(get_settings(), "generation_user_concurrency", 3))
        self.stack.enter_context(patch.object(get_settings(), "generation_global_concurrency", 6))
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
        self.assertEqual([x["missing_count"] for x in response.json()["sections"]], [2, 2])

    def test_unique_legacy_type_remains_supported(self):
        response, _ = self.send({"sections": [{"game_type": "fill_blank", "questions": questions()}]})
        self.assertEqual(response.json()["sections"][0]["missing_count"], 0)

    def test_reading_preserves_passage_without_unrelated_repairs(self):
        get_settings().generation_repair_limit = 3
        self.body["items"] = [{"section_id": "reading", "game_type": "reading", "question_count": 2}]
        raw = {"sections": [{"section_id": "reading", "game_type": "reading", "passage": "春天来了。小明去公园。",
                            "questions": [{"type": "multiple_choice", "stem": "小明去了哪里？", "options": ["公园", "学校"], "answer": 0}]}]}
        response, mock = self.send(raw)
        result = response.json()["sections"][0]
        self.assertEqual(result["passage"], raw["sections"][0]["passage"])
        self.assertEqual(result["missing_count"], 1)
        self.assertEqual(mock.await_count, 1)

    def test_reading_without_passage_is_not_accepted(self):
        self.body["items"] = [{"section_id": "s1", "game_type": "reading", "question_count": 2}]
        response, _ = self.send({"sections": [section(kind="reading")]})
        result = response.json()["sections"][0]
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["missing_count"], 2)

    def test_malformed_output_never_fabricates_stems(self):
        raw = section()
        raw["questions"] = [{"answer": "2"}, None, "not a question"]
        response, _ = self.send({"sections": [raw]})
        result = response.json()["sections"][0]
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
        self.assertEqual(mock.await_count, 3)
        self.assertEqual(response.json()["sections"][0]["missing_count"], 2)

    def test_duplicate_questions_are_removed_across_sections(self):
        self.body["items"].append({"section_id": "s2", "game_type": "fill_blank", "question_count": 2})
        response, _ = self.send({"sections": [section(), section("s2")]})
        self.assertEqual([x["missing_count"] for x in response.json()["sections"]], [0, 2])

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

    def test_daily_quota_and_replay_do_not_spend_twice(self):
        get_settings().generation_daily_limit = 1
        self.assertEqual(self.send()[0].status_code, 200)
        self.assertEqual(self.send()[0].status_code, 200)
        response, mock = self.send(request_id="new-job")
        self.assertEqual(response.status_code, 429)
        mock.assert_not_awaited()
        self.assertEqual(self.client.get("/api/v1/me/usage").json()["requests"], 1)

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
        async def model(*_):
            control.record_attempt()
            control.record_usage({"prompt_tokens": 42, "completion_tokens": 21})
            return {"sections": [section()]}
        with patch.object(generate, "_call_llm_and_parse", new=model):
            self.client.post("/api/v1/generate-batch", json=self.body).raise_for_status()
        usage = self.client.get("/api/v1/me/usage").json()
        self.assertEqual((usage["model_calls"], usage["reported_calls"], usage["prompt_tokens"], usage["completion_tokens"]), (1, 1, 42, 21))

    def test_stream_is_metered_and_not_replayed(self):
        async def stream(*args, **kwargs):
            control.record_attempt()
            yield json.dumps({"questions": questions()})
        body = {key: value for key, value in self.body.items() if key != "items"}
        body.update(game_type="fill_blank", question_count=2)
        with patch.object(generate, "_merged_llm_params", return_value={"base_url": "http://unused", "model": "test", "api_key": "fake", "timeout": 120}), \
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
        for error in (httpx.ReadTimeout("timeout"), httpx.ReadError("read"), httpx.WriteError("write"), httpx.RemoteProtocolError("protocol")):
            client = LLMClient()
            fake = AsyncMock(spec=httpx.AsyncClient)
            fake.post.side_effect = error
            with patch.object(client, "_get_client_for", return_value=fake):
                with self.assertRaises(type(error)):
                    await client.chat([], base_url="http://unused", api_key="fake")
            self.assertEqual(fake.post.await_count, 1)

    async def test_connect_retry_does_not_close_shared_client(self):
        client = LLMClient()
        fake = AsyncMock(spec=httpx.AsyncClient)
        result = httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}, request=httpx.Request("POST", "http://unused"))
        fake.post.side_effect = [httpx.ConnectError("connect"), result]
        with patch.object(client, "_get_client_for", return_value=fake), patch("app.services.llm_client.asyncio.sleep", new=AsyncMock()):
            self.assertEqual(await client.chat([], base_url="http://unused", api_key="fake"), "ok")
        fake.aclose.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
