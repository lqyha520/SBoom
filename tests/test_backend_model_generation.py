"""所有题型统一调用模型的回归；模拟模型响应，不访问收费接口。"""

import json
import unittest
from unittest.mock import AsyncMock, patch

import test_backend_reliability as fixtures
from fastapi import HTTPException

from app.config import get_settings
from app.db import db
from app.models import GameType
from app.routers import generate
from app.services.knowledge_topics import GENERAL_TOPIC, LEGACY_TOPIC, canonical_topic

DIFFICULTIES = ("easy", "medium", "hard")

QUESTIONS = [
    {"type": "oral_math", "stem": "7 + 6 =", "answer": 13},
    {"type": "fill_blank", "stem": "8 + ____ = 12", "answer": 4},
    {"type": "number_split", "top": 9, "left": 4, "right": "____", "answer": 5},
    {"type": "compare", "left_expr": "9 + 6", "right_expr": "14", "answer": ">"},
    {"type": "true_false", "stem": "7 + 5 = 12（　）", "answer": "√"},
]

PROVIDER_CONFIG = {"api_key": "test-key", "base_url": "https://example.invalid/v1", "model": "test-model",
                   "timeout": 120, "max_tokens": 4096}
MODEL_SECTIONS = {
    **{question["type"]: {"game_type": question["type"], "questions": [question]} for question in QUESTIONS},
    "quiz": {"questions": [{"type": "multiple_choice", "stem": "3 + 4 = ?", "options": ["6", "7"], "answer": 1}]},
    "challenge": {"questions": [{"type": "multiple_choice", "stem": "3 + 5 = ?", "options": ["7", "8"], "answer": 1,
                                 "difficulty_level": 1}]},
    "match_pair": {"questions": [{"type": "match_pair", "left_items": ["3 + 4", "5 + 6"],
                                  "right_items": ["11", "7"], "answer": [[0, 1], [1, 0]]}]},
    "reading": {"passage": "小明有7朵花，又买5朵。", "questions": [
        {"type": "multiple_choice", "stem": "小明一共有几朵花？", "options": ["12", "11"], "answer": 0}]},
    "vertical_calc": {"questions": [{"type": "vertical_calc", "stem": "123 + 456 =", "answer": 579}]},
    "recursive_calc": {"questions": [{"type": "recursive_calc", "stem": "10 + 2 * 3 =", "answer": 16}]},
    "smart_calc": {"questions": [{"type": "smart_calc", "stem": "25 * 4 =", "answer": 100}]},
    "word_problem": {"questions": [{"type": "word_problem", "stem": "有7朵花，又买5朵，一共几朵？", "answer": "12朵"}]},
}


def section(question, section_id="s1"):
    return {"section_id": section_id, "game_type": question["type"], "questions": [question]}


class KnowledgeTopics(unittest.TestCase):
    def test_old_labels_are_not_silently_rewritten_as_new_catalog_topics(self):
        self.assertEqual(canonical_topic(LEGACY_TOPIC), LEGACY_TOPIC)
        self.assertEqual(canonical_topic("上册·" + LEGACY_TOPIC), "上册·" + LEGACY_TOPIC)
        for topic in ("9加几", "20以内的进位加法（8加几专项）", GENERAL_TOPIC + "，只用偶数",
                      LEGACY_TOPIC + "，只用偶数", "20以内的退位减法"):
            self.assertEqual(canonical_topic(topic), topic)


class ModelGenerationAPI(unittest.TestCase):
    send = fixtures.BackendReliability.send

    def setUp(self):
        fixtures.BackendReliability.setUp(self)
        self.body.update(grade="小学一年级", keyword="上册·" + GENERAL_TOPIC)
        self.body["items"] = [
            {"game_type": question["type"], "section_id": f"s{index}", "question_count": 1}
            for index, question in enumerate(QUESTIONS)
        ]

    def single_body(self, question):
        return {key: self.body[key] for key in ("grade", "subject", "keyword", "difficulty")} | {
            "game_type": question["type"], "question_count": 1,
        }

    def assert_model_question(self, actual, expected):
        for key, value in expected.items():
            self.assertEqual(actual[key], value)

    def test_every_supported_type_calls_provider_for_batch_and_single_at_every_difficulty(self):
        self.assertEqual(set(MODEL_SECTIONS), {kind.value for kind in GameType})
        with patch.object(generate, "_merged_llm_params", return_value=PROVIDER_CONFIG):
            for kind, value in MODEL_SECTIONS.items():
                for difficulty in DIFFICULTIES:
                    for endpoint in ("generate", "generate-batch"):
                        with self.subTest(kind=kind, difficulty=difficulty, endpoint=endpoint):
                            body = {"grade": "小学六年级", "subject": "数学", "keyword": "综合练习",
                                    "difficulty": difficulty}
                            result = {**value, "game_type": kind, "section_id": "s1"}
                            if endpoint == "generate":
                                body.update(game_type=kind, question_count=1)
                                output = result
                            else:
                                body["items"] = [{"game_type": kind, "section_id": "s1", "question_count": 1}]
                                output = {"sections": [result]}
                            with patch.object(generate.llm_client, "chat", new=AsyncMock(
                                return_value=json.dumps(output, ensure_ascii=False),
                            )) as model:
                                response = self.client.post(f"/api/v1/{endpoint}", json=body)
                            self.assertEqual(response.status_code, 200, response.text)
                            model.assert_awaited_once()
                            self.assertIn("难度", model.call_args.args[0][0]["content"])
                            actual = response.json() if endpoint == "generate" else response.json()["sections"][0]
                            self.assertEqual(actual["missing_count"], 0)
                            self.assert_model_question(actual["questions"][0], value["questions"][0])

    def test_streaming_every_type_always_uses_provider_stream(self):
        with patch.object(generate, "_merged_llm_params", return_value=PROVIDER_CONFIG):
            for kind, value in MODEL_SECTIONS.items():
                with self.subTest(kind=kind):
                    output = json.dumps({**value, "game_type": kind, "questions": value["questions"] * 2}, ensure_ascii=False)

                    async def tokens(*args, text=output, **kwargs):
                        yield text

                    with patch.object(generate.llm_client, "chat_stream", side_effect=tokens) as model:
                        response = self.client.post("/api/v1/generate/stream", json={
                            "grade": "小学六年级", "subject": "数学", "keyword": "综合练习",
                            "game_type": kind, "question_count": 2,
                        })
                    self.assertEqual(response.status_code, 200, response.text)
                    model.assert_called_once()
                    self.assertIn("data: [DONE]", response.text)
                    self.assertIn('"token":', response.text)
                    self.assertIn("流式结果尚未独立复核", response.text)
                    self.assertIn("本次生成的题目不要重复。", model.call_args.args[0][0]["content"])

    def test_duplicate_questions_are_rejected_for_every_type_in_single_and_batch(self):
        get_settings().generation_repair_limit = 0
        for kind, value in MODEL_SECTIONS.items():
            for endpoint in ("generate", "generate-batch"):
                with self.subTest(kind=kind, endpoint=endpoint):
                    body = {"grade": "小学六年级", "subject": "数学", "keyword": "综合练习"}
                    output = {**value, "game_type": kind, "section_id": "s1", "questions": value["questions"] * 2}
                    if endpoint == "generate":
                        body.update(game_type=kind, question_count=2)
                    else:
                        body["items"] = [{"game_type": kind, "section_id": "s1", "question_count": 2}]
                        output = {"sections": [output]}
                    with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(return_value=output)) as model:
                        response = self.client.post(f"/api/v1/{endpoint}", json=body)
                    result = fixtures.incomplete_sections(response)[0]
                    self.assertEqual([q["id"] for q in result["questions"]], [1])
                    self.assertEqual(result["missing_count"], 1)
                    self.assertTrue(result["quality_warnings"])
                    model.assert_awaited_once()
                    self.assertIn("本次生成的题目不要重复。", model.call_args.args[0])

    def test_repair_does_not_reintroduce_identical_questions(self):
        get_settings().generation_repair_limit = 3
        self.body["items"] = [{"game_type": "oral_math", "section_id": "s1", "question_count": 2}]
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(side_effect=[
            {"sections": [section(QUESTIONS[0])]},
            {"game_type": "oral_math", "questions": [QUESTIONS[0]]},
        ])) as model:
            response = self.client.post("/api/v1/generate-batch", json=self.body)
        result = fixtures.incomplete_sections(response)[0]
        self.assertEqual(len(result["questions"]), 1)
        self.assertEqual(result["missing_count"], 1)
        self.assertTrue(result["quality_warnings"])
        self.assertEqual(model.await_count, 2)
        self.assertIn("本次生成的题目不要重复。", model.call_args.args[0])

    def test_six_calculations_and_eight_blanks_remain_complete_with_shared_expressions(self):
        get_settings().generation_repair_limit = 3
        oral = [{"type": "oral_math", "stem": f"8+{n}=", "answer": 8 + n} for n in range(3, 9)]
        blanks = [{"type": "fill_blank", "stem": f"8+{n}=___", "answer": 8 + n} for n in range(2, 10)]
        self.body["items"] = [{"section_id": "s1", "game_type": "oral_math", "question_count": 6},
                              {"section_id": "s2", "game_type": "fill_blank", "question_count": 8}]
        response, model = self.send({"sections": [
            {"section_id": "s1", "game_type": "oral_math", "questions": oral},
            {"section_id": "s2", "game_type": "fill_blank", "questions": blanks},
        ]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([len(s["questions"]) for s in response.json()["sections"]], [6, 8])
        self.assertTrue(all(s["missing_count"] == 0 for s in response.json()["sections"]))
        model.assert_awaited_once()

    def test_out_of_scope_validation_calls_provider_instead_of_local_judgement(self):
        expected = {"is_oob": True, "oob_points": ["乘法"], "suggestion": "改为加法"}
        with patch.object(generate, "_merged_llm_params", return_value=PROVIDER_CONFIG), \
             patch.object(generate.llm_client, "chat", new=AsyncMock(return_value=json.dumps(expected))) as model:
            response = self.client.post("/api/v1/validate", json={
                "grade": "小学一年级", "subject": "数学", "question_content": "3 * 4 =",
            })
        self.assertEqual(response.status_code, 200, response.text)
        model.assert_awaited_once()
        for key, value in expected.items():
            self.assertEqual(response.json()[key], value)

    def test_all_elementary_types_and_difficulties_use_model_in_batch(self):
        raw = {"sections": [section(question, f"s{index}") for index, question in enumerate(QUESTIONS)]}
        for difficulty in DIFFICULTIES:
            with self.subTest(difficulty=difficulty):
                self.body["difficulty"] = difficulty
                response, model = self.send(raw, request_id=f"batch-{difficulty}")
                self.assertEqual(response.status_code, 200, response.text)
                model.assert_awaited_once()
                self.assertEqual(model.call_args.args[2], len(QUESTIONS))
                prompt = model.call_args.args[0]
                self.assertIn("难度", prompt)
                self.assertIn("上册·" + GENERAL_TOPIC, prompt)
                sections = response.json()["sections"]
                self.assertEqual(len(sections), len(QUESTIONS))
                for result, expected in zip(sections, QUESTIONS, strict=True):
                    self.assertIn(result["game_type"], prompt)
                    self.assertEqual(result["difficulty"], difficulty)
                    self.assertEqual(result["topic"], "上册·" + GENERAL_TOPIC)
                    self.assertEqual(result["missing_count"], 0)
                    self.assert_model_question(result["questions"][0], expected)

    def test_all_elementary_types_and_difficulties_use_model_in_single_endpoint(self):
        for difficulty in DIFFICULTIES:
            self.body["difficulty"] = difficulty
            for question in QUESTIONS:
                with self.subTest(difficulty=difficulty, kind=question["type"]):
                    raw = {"game_type": question["type"], "questions": [question]}
                    with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(return_value=raw)) as model:
                        response = self.client.post("/api/v1/generate", json=self.single_body(question))
                    self.assertEqual(response.status_code, 200, response.text)
                    model.assert_awaited_once()
                    self.assertIn("难度", model.call_args.args[0])
                    self.assertEqual(model.call_args.args[2], 1)
                    self.assert_model_question(response.json()["questions"][0], question)

    def test_mixed_paper_sends_every_section_to_model(self):
        word = {"type": "word_problem", "stem": "有7朵花，又买5朵，一共几朵？", "answer": "12朵"}
        self.body["items"] = [
            {"game_type": "oral_math", "section_id": "oral", "question_count": 1},
            {"game_type": "word_problem", "section_id": "word", "question_count": 1},
        ]
        raw = {"sections": [section(QUESTIONS[0], "oral"), section(word, "word")]}
        response, model = self.send(raw)
        self.assertEqual(response.status_code, 200, response.text)
        model.assert_awaited_once()
        self.assertEqual(model.call_args.args[2], 2)
        self.assertIn('"section_id":"oral"', model.call_args.args[0])
        self.assertIn('"section_id":"word"', model.call_args.args[0])
        self.assertEqual([value["missing_count"] for value in response.json()["sections"]], [0, 0])

    def test_new_requests_call_provider_but_original_request_replays(self):
        self.body["items"] = [{"game_type": "oral_math", "section_id": "s1", "question_count": 1}]
        raw = json.dumps({"sections": [section(QUESTIONS[0])]})
        with patch.object(generate, "_merged_llm_params", return_value=PROVIDER_CONFIG), \
             patch.object(generate.llm_client, "chat", new=AsyncMock(return_value=raw)) as model:
            first = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "first"})
            self.assertEqual(first.status_code, 200, first.text)
            model.assert_awaited_once()
            replay = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "first"})
            self.assertEqual(replay.json(), first.json())
            model.assert_awaited_once()
            second = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "second"})
            self.assertEqual(second.status_code, 200, second.text)
            self.assertEqual(model.await_count, 2)
        with db() as conn:
            statuses = conn.execute("SELECT status FROM generation_requests WHERE user_id = ?", (self.user.id,)).fetchall()
        self.assertTrue(all(row["status"] == "succeeded" for row in statuses))

    def test_missing_model_configuration_never_falls_back_to_local_questions(self):
        for endpoint, body in (("generate-batch", self.body), ("generate", self.single_body(QUESTIONS[0]))):
            with self.subTest(endpoint=endpoint), \
                 patch.object(generate, "_merged_llm_params", return_value={"api_key": ""}), \
                 patch.object(generate.llm_client, "chat", new=AsyncMock()) as model:
                response = self.client.post(f"/api/v1/{endpoint}", json=body)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn("尚未配置模型", response.text)
                model.assert_not_awaited()
                self.assertNotIn("questions", response.json())
                self.assertNotIn("sections", response.json())

    def test_model_failure_never_falls_back_to_local_questions(self):
        for endpoint, body in (("generate-batch", self.body), ("generate", self.single_body(QUESTIONS[0]))):
            with self.subTest(endpoint=endpoint), patch.object(
                generate, "_call_llm_and_parse",
                new=AsyncMock(side_effect=HTTPException(504, detail={"error": "模型超时"})),
            ) as model:
                response = self.client.post(f"/api/v1/{endpoint}", json=body)
                self.assertEqual(response.status_code, 504, response.text)
                model.assert_awaited_once()
                self.assertNotIn("questions", response.json())
                self.assertNotIn("sections", response.json())

    def test_short_or_invalid_model_output_is_not_filled_with_local_questions(self):
        self.body["items"] = [{"game_type": "oral_math", "section_id": "s1", "question_count": 2}]
        raw = {"sections": [{"section_id": "s1", "game_type": "oral_math",
                             "questions": [QUESTIONS[0], {"type": "oral_math", "stem": "8 + 6 =", "answer": 99}]}]}
        response, model = self.send(raw)
        self.assertEqual(response.status_code, 422, response.text)
        model.assert_awaited_once()
        result = fixtures.incomplete_sections(response)[0]
        self.assertEqual(result["missing_count"], 1)
        self.assertEqual(len(result["questions"]), 1)
        self.assert_model_question(result["questions"][0], QUESTIONS[0])

    def test_plain_arithmetic_stem_gets_display_equals_without_local_generation(self):
        self.body["items"] = [{"game_type": "oral_math", "section_id": "s1", "question_count": 2}]
        raw = {"sections": [{"section_id": "s1", "game_type": "oral_math", "questions": [
            {"type": "oral_math", "stem": "9＋2", "answer": 11},
            {"type": "oral_math", "stem": "8 + 4 =", "answer": 12},
        ]}]}
        response, model = self.send(raw, request_id="display-equals")
        self.assertEqual(response.status_code, 200, response.text)
        model.assert_awaited_once()
        stems = [question["stem"] for question in response.json()["sections"][0]["questions"]]
        self.assertEqual(stems, ["9＋2 =", "8 + 4 ="])

    def test_ordinary_math_fill_blank_rejects_long_stem_and_instruction_prefix(self):
        self.body["items"] = [{"game_type": "fill_blank", "section_id": "s1", "question_count": 1}]
        raw = {"sections": [{"section_id": "s1", "game_type": "fill_blank", "questions": [
            {"type": "fill_blank", "stem": "在____里填‘＞’‘＜’或‘＝’：12____15。", "answer": "＜"},
        ]}]}
        response, model = self.send(raw, request_id="compact-fill-blank")
        self.assertEqual(response.status_code, 422, response.text)
        model.assert_awaited_once()
        result = fixtures.incomplete_sections(response)[0]
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["missing_count"], 1)

    def test_elementary_repairs_also_come_from_model(self):
        get_settings().generation_repair_limit = 1
        self.body["items"] = [{"game_type": "oral_math", "section_id": "s1", "question_count": 1}]
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(side_effect=[
            {"sections": [{"section_id": "s1", "game_type": "oral_math", "questions": []}]},
            {"game_type": "oral_math", "questions": [QUESTIONS[0]]},
        ])) as model:
            response = self.client.post("/api/v1/generate-batch", json=self.body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(model.await_count, 2)
        result = response.json()["sections"][0]
        self.assertEqual(result["missing_count"], 0)
        self.assert_model_question(result["questions"][0], QUESTIONS[0])
