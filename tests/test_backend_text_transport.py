"""文本调用的异常协议、候选边界和资源回收；全部使用离线响应。"""

import asyncio
import json
import threading
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.models import GameResult, GenerateRequest, Question
from app.routers import generate
from app.services import generation_control as control
from app.services.llm_client import LLMClient, OutputTruncated, parse_stream_chunk
from app.services.question_review import review_results


def completion(content='{"questions":[]}', reason="stop", **message):
    return {"choices": [{"message": {"content": content, **message}, "finish_reason": reason}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7}}


class TextTransport(unittest.IsolatedAsyncioTestCase):
    async def test_bad_protocol_switches_once_and_counts_both_attempts(self):
        candidates = [{"api_key": "fake", "base_url": "https://unused.invalid", "model": name,
                       "timeout": 5, "max_tokens": 4096} for name in ("first", "second")]
        invalid = [
            completion(refusal="declined"), completion(reason="content_filter"),
            completion(reason="tool_calls"), completion(tool_calls=[{"id": "call"}]),
            completion(function_call={"name": "unexpected"}), completion(reason="unexpected"),
            completion(reason=5), completion(content="  "), completion(content={"unexpected": True}),
            {**completion(), "error": {"message": "private upstream error"}},
            {**completion(), "choices": {}}, {**completion(), "choices": [None]},
            completion(content='{"error":"private error"}'), completion(content='{"reviews":[]}'),
        ]
        for body in invalid:
            with self.subTest(body=body):
                outputs = [body, completion()]
                sent = []

                def respond(request, sent=sent, outputs=outputs):
                    sent.append(json.loads(request.content))
                    return httpx.Response(200, json=outputs.pop(0))

                usage = control.Usage()
                token = control.current_usage.set(usage)
                try:
                    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://unused.invalid") as http:
                        with patch.object(generate, "_merged_llm_params", return_value={"models": candidates}), \
                                patch.object(generate.llm_client, "_get_client_for", return_value=http), \
                                patch("app.services.llm_client.reserve"):
                            self.assertEqual(await generate._call_llm_and_parse("system", "user", 2, expected_key="questions"), {"questions": []})
                    self.assertEqual([request["model"] for request in sent], ["first", "second"])
                    self.assertEqual((usage.model_calls, usage.reported_calls, usage.prompt_tokens, usage.completion_tokens), (2, 2, 24, 14))
                finally:
                    control.current_usage.reset(token)

    async def test_truncation_preserves_partial_and_missing_finish_reason_is_compatible(self):
        client = LLMClient()
        for reason in ("length", None):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request, reason=reason: httpx.Response(
                    200, json=completion("partial", reason))), base_url="https://unused.invalid") as http:
                with patch.object(client, "_get_client_for", return_value=http):
                    if reason == "length":
                        with self.assertRaises(OutputTruncated) as caught:
                            await client.chat([], api_key="fake")
                        self.assertEqual(caught.exception.partial_text, "partial")
                    else:
                        self.assertEqual(await client.chat([], api_key="fake"), "partial")

    async def test_json_decode_runs_off_event_loop(self):
        loop_thread = threading.get_ident()
        worker_threads = []
        loads = json.loads

        def decode(value, *args, **kwargs):
            if isinstance(value, bytearray):
                worker_threads.append(threading.get_ident())
            return loads(value, *args, **kwargs)

        body = json.dumps(completion()).encode()
        client = LLMClient()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)),
                                     base_url="https://unused.invalid") as http:
            with patch.object(client, "_get_client_for", return_value=http), patch("app.services.llm_client.json.loads", side_effect=decode):
                self.assertEqual(await client.chat([], api_key="fake"), '{"questions":[]}')
        self.assertTrue(worker_threads)
        self.assertNotIn(loop_thread, worker_threads)

    async def test_oversized_response_stops_reading_and_closes_stream(self):
        consumed = []
        closed = []

        class Chunks(httpx.AsyncByteStream):
            async def __aiter__(self):
                for index in range(5):
                    consumed.append(index)
                    yield b"x" * (64 * 1024)

            async def aclose(self):
                closed.append(True)

        client = LLMClient()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Chunks())),
                                     base_url="https://unused.invalid") as http:
            with patch.object(client, "_get_client_for", return_value=http), \
                    patch.object(get_settings(), "provider_max_response_bytes", 64 * 1024):
                with self.assertRaises(HTTPException) as caught:
                    await client.chat([], api_key="fake")
        self.assertEqual(caught.exception.detail["code"], "provider_response_too_large")
        self.assertEqual(consumed, [0, 1])
        self.assertEqual(closed, [True])

    async def test_close_waits_for_evicted_connection_cleanup(self):
        closing, release = asyncio.Event(), asyncio.Event()

        async def close():
            closing.set()
            await release.wait()

        old = AsyncMock(spec=httpx.AsyncClient)
        old.aclose.side_effect = close
        client = LLMClient()
        client._clients[("unused", "fake")] = old
        client._evict_oldest(free_slots=client.MAX_CACHED_CLIENTS)
        await asyncio.wait_for(closing.wait(), 1)
        task = asyncio.create_task(client.close())
        try:
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            release.set()
            await asyncio.wait_for(task, 1)
            self.assertFalse(client._closing)
            old.aclose.assert_awaited_once()
        finally:
            release.set()
            await task

    async def test_whitespace_only_stream_is_not_success(self):
        body = 'data: {"choices":[{"delta":{"content":"  "},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        client = LLMClient()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)),
                                     base_url="https://unused.invalid") as http:
            with patch.object(client, "_get_client_for", return_value=http):
                with self.assertRaises(HTTPException) as caught:
                    _ = [part async for part in client.chat_stream([], api_key="fake")]
        self.assertEqual(caught.exception.detail["code"], "provider_incomplete_stream")

    def test_stream_rejects_refusal_tools_and_unknown_finish(self):
        for delta, reason in (({"refusal": "no"}, None), ({"tool_calls": [{"id": "a"}]}, None),
                              ({"content": "text"}, "unknown"), ({"content": "text"}, "content_filter")):
            with self.subTest(delta=delta, reason=reason), self.assertRaises(HTTPException) as caught:
                parse_stream_chunk(json.dumps({"choices": [{"delta": delta, "finish_reason": reason}]}))
            self.assertEqual(caught.exception.status_code, 502)

    async def test_parsing_is_inside_candidate_deadline(self):
        candidates = [{"api_key": "fake", "base_url": "https://unused.invalid", "model": name,
                       "timeout": 0.05 if name == "first" else 1, "max_tokens": 4096} for name in ("first", "second")]
        run_sync = generate.run_sync
        parsings = []

        async def slow_parse(function, *args, **kwargs):
            if function is generate._extract_json:
                parsings.append(True)
                if len(parsings) == 1:
                    await asyncio.Event().wait()
            return await run_sync(function, *args, **kwargs)

        with patch.object(generate, "_merged_llm_params", return_value={"models": candidates}), \
                patch.object(generate, "run_sync", side_effect=slow_parse), \
                patch.object(generate.llm_client, "chat", new=AsyncMock(return_value='{"questions":[]}')) as model:
            self.assertEqual(await generate._call_llm_and_parse("system", "user", 2, expected_key="questions"), {"questions": []})
        self.assertEqual([call.kwargs["model"] for call in model.await_args_list], ["first", "second"])

    async def test_review_uses_low_temperature_without_reducing_generation_budget(self):
        params = {"api_key": "fake", "base_url": "https://unused.invalid", "model": "configured",
                  "timeout": 5, "max_tokens": 8000}
        with patch.object(generate, "_merged_llm_params", return_value=params), \
                patch.object(generate.llm_client, "chat", new=AsyncMock(side_effect=['{"questions":[]}', '{"reviews":[]}'])) as model:
            await generate._call_llm_and_parse("system", "user", 10)
            await generate._call_quality_review("system", "user", 10)
        first, review = [call.kwargs for call in model.await_args_list]
        self.assertIsNone(first["temperature"])
        self.assertEqual(review["temperature"], 0.1)
        self.assertEqual(review["max_tokens"], first["max_tokens"])
        self.assertEqual(review["model"], "configured")
        self.assertEqual(review["max_attempts"], 1)

    async def test_review_reserves_time_for_backup_and_honors_shorter_configured_timeout(self):
        candidates = [{"api_key": "fake", "base_url": "https://unused.invalid", "model": name,
                       "timeout": 0.05 if name == "first" else 600, "max_tokens": 4096} for name in ("first", "second")]

        async def chat(*args, **kwargs):
            if kwargs["model"] == "first":
                await asyncio.Event().wait()
            return '{"reviews":[]}'

        with patch.object(generate, "_merged_llm_params", return_value={"models": candidates}), \
                patch.object(generate, "QUALITY_REVIEW_TIMEOUT", 1), \
                patch.object(generate.llm_client, "chat", new=AsyncMock(side_effect=chat)) as model:
            self.assertEqual(await generate._call_quality_review("system", "user", 1), {"reviews": []})
        self.assertEqual([call.kwargs["timeout"] for call in model.await_args_list], [0.05, 0.5])
        self.assertEqual([call.kwargs["model"] for call in model.await_args_list], ["first", "second"])

    async def test_review_total_deadline_cancels_and_retains_unchecked_questions(self):
        params = {"api_key": "fake", "base_url": "https://unused.invalid", "model": "configured",
                  "timeout": 600, "max_tokens": 8000}
        cancelled = asyncio.Event()

        async def hang(*args, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        body = GenerateRequest(grade="小学一年级", subject="数学", keyword="10以内加法", game_type="oral_math", question_count=1)
        value = GameResult(game_type="oral_math", grade=body.grade, subject=body.subject, topic=body.keyword,
                           difficulty="easy", questions=[Question(id=1, type="oral_math", stem="1+1=", answer=2, analysis="1+1=2")])
        with patch.object(generate, "_merged_llm_params", return_value=params), \
                patch.object(generate, "QUALITY_REVIEW_TIMEOUT", 0.1), \
                patch.object(generate.llm_client, "chat", new=AsyncMock(side_effect=hang)) as model:
            await asyncio.wait_for(review_results([value], body, generate._call_quality_review), 2)
        self.assertTrue(cancelled.is_set())
        model.assert_awaited_once()
        self.assertEqual(model.await_args.kwargs["timeout"], 0.1)
        self.assertEqual(len(value.questions), 1)
        self.assertEqual(value.questions[0].quality_status, "unchecked")
        self.assertEqual(value.missing_count, 0)
        self.assertTrue(value.quality_warnings)
