"""教学条件、基础练习边界与模型补题回归；模型均为模拟响应。"""

import unittest
from unittest.mock import AsyncMock, patch

import test_backend_reliability as fixtures

from app.config import get_settings
from app.models import BatchItem, Difficulty, GenerateRequest, KnowledgeScope
from app.routers import generate
from app.services.generation_results import _normalize_question
from app.services.knowledge_topics import GENERAL_TOPIC, is_make_ten_practice
from app.services.prompt_builder import prompt_builder
from app.services.question_diversity import DiversityContext, recent_questions
from app.services.question_qc import make_ten_issue, question_issue


def oral(stem="8 + 7 =", answer=15):
    return {"type": "oral_math", "stem": stem, "answer": answer, "analysis": f"{stem} {answer}"}


class TeachingRules(unittest.TestCase):
    def test_calculation_format_preserves_model_content_and_existing_equals(self):
        for kind in ("oral_math", "vertical_calc", "recursive_calc", "smart_calc"):
            for stem, expected in (("9＋2", "9＋2 ="), (" 9＋2 ", "9＋2 ="),
                                   ("９＋２＝", "９＋２＝"), ("9 + 2 =", "9 + 2 =")):
                with self.subTest(kind=kind, stem=stem):
                    original = {"type": kind, "stem": stem, "answer": 11, "analysis": "9加2等于11"}
                    normalized = _normalize_question(original, kind)
                    self.assertEqual(normalized, {**original, "stem": expected})
                    self.assertEqual(original["stem"], stem)
        invalid = oral("计算9+2", 11)
        self.assertEqual(_normalize_question(invalid, "oral_math"), invalid)
        self.assertIsNotNone(question_issue(invalid))

    def test_compact_fill_blank_only_exempts_numeric_process_stems(self):
        for stem in ("请先仔细观察下面的数字然后想一想再填上合适的数____。",
                     "请先仔细观察下面的数字\n然后想一想再填上合适的数____。",
                     "在____里填：12____15。"):
            value = {"type": "fill_blank", "stem": stem, "answer": "<"}
            with self.subTest(stem=stem):
                self.assertIsNotNone(question_issue(value, compact_fill_blank=True, allow_fill_blank_steps=True))
                self.assertIsNone(question_issue(value))
        process = {"type": "fill_blank", "stem": "8 + 7 = 8 + ____ + 5\n= 10 + ____ = ____", "answer": "2，5，15"}
        self.assertIsNotNone(question_issue(process, compact_fill_blank=True))
        self.assertIsNone(question_issue(process, compact_fill_blank=True, allow_fill_blank_steps=True))
        self.assertIsNotNone(question_issue({**process, "answer": "2，5，16"},
                                            compact_fill_blank=True, allow_fill_blank_steps=True))

    def test_practice_profile_is_scoped_and_keeps_explicit_topics(self):
        for keyword in (GENERAL_TOPIC, "上册·" + GENERAL_TOPIC, "9加几", "8加几专项", GENERAL_TOPIC + "，只用偶数"):
            self.assertTrue(is_make_ten_practice("小学一年级", "数学", keyword), keyword)
        for grade, subject, keyword in (
            ("小学三年级", "数学", GENERAL_TOPIC),
            ("小学一年级", "语文", GENERAL_TOPIC),
            ("小学一年级", "数学", "100以内进位加法"),
            ("小学一年级", "数学", "120以内进位加法"),
            ("小学一年级", "数学", "20以内退位减法"),
            ("小学一年级", "数学", "凑十法与三项连加"),
            ("小学一年级", "数学", "加减混合"),
        ):
            self.assertFalse(is_make_ten_practice(grade, subject, keyword))

    def test_batch_and_single_include_difficulty_teaching_goals_and_output_contract(self):
        scope = KnowledgeScope(grade="小学一年级", subject="数学", allowed=[GENERAL_TOPIC], forbidden=["乘法"])
        for keyword in (GENERAL_TOPIC, "9加几", "8加几专项"):
            for kind in ("oral_math", "fill_blank", "number_split", "compare", "true_false"):
                with self.subTest(keyword=keyword, kind=kind):
                    request = GenerateRequest(
                        grade=scope.grade, subject=scope.subject, keyword=keyword, game_type=kind, question_count=8,
                    )
                    prompts = [
                        prompt_builder.build_system_prompt(request, scope),
                        prompt_builder.build_batch_prompt(
                            scope.grade, scope.subject, keyword, "medium",
                            [BatchItem(game_type=kind, question_count=8)], scope,
                        ),
                    ]
                    for prompt in prompts:
                        self.assertIn(f"年级：{scope.grade}\n科目：{scope.subject}\n题数：8\n知识点：{keyword}", prompt)
                        for rule in ("最多出现2次", "至少安排3种", "15 个字", "约 20 字符"):
                            self.assertNotIn(rule, prompt)
                        self.assertIn("难度：标准", prompt)
                        self.assertIn("教学目标", prompt)
                        self.assertIn('"questions"', prompt)
                        self.assertIn("本次生成的题目不要重复。", prompt)
                        if kind == "oral_math":
                            self.assertIn("末尾必须保留等号", prompt)
                        if kind == "fill_blank":
                            self.assertIn("24个字符以内", prompt)
                            self.assertIn("空缺处用___（三个下划线）表示", prompt)
                    self.assertEqual(prompt_builder.build_user_message(keyword), "请生成题目。")
                    self.assertEqual(prompt_builder.build_batch_user_message(keyword), "请生成题目。")
        first = prompt_builder.build_batch_user_message(GENERAL_TOPIC)
        self.assertEqual(first, prompt_builder.build_batch_user_message(GENERAL_TOPIC))
        self.assertNotIn("批次编号", first)
        self.assertNotIn("不要重复常见", first)
        request = GenerateRequest(grade=scope.grade, subject=scope.subject, keyword=GENERAL_TOPIC)
        self.assertNotEqual(
            prompt_builder.build_system_prompt(request, scope),
            prompt_builder.build_system_prompt(request.model_copy(update={"difficulty": Difficulty.HARD}), scope),
        )

    def test_fill_blank_length_rule_is_only_for_ordinary_math(self):
        for subject, keyword in (("语文", "古诗"), ("英语", "日常问候")):
            with self.subTest(subject=subject, keyword=keyword):
                scope = KnowledgeScope(grade="小学三年级", subject=subject, allowed=[keyword], forbidden=[])
                request = GenerateRequest(grade=scope.grade, subject=subject, keyword=keyword, game_type="fill_blank")
                for prompt in (
                    prompt_builder.build_system_prompt(request, scope),
                    prompt_builder.build_batch_prompt(scope.grade, subject, keyword, "medium", [
                        BatchItem(game_type="fill_blank", question_count=2),
                    ], scope),
                ):
                    self.assertNotIn("24个字符以内", prompt)
                    self.assertIn("简短内容", prompt)
        math_prompt = prompt_builder.build_system_prompt(
            GenerateRequest(grade="小学一年级", subject="数学", keyword="凑十法过程填空", game_type="fill_blank"),
            KnowledgeScope(grade="小学一年级", subject="数学", allowed=["凑十法过程填空"], forbidden=[]),
        )
        self.assertIn("24个字符以内", math_prompt)
        self.assertIn("过程可换行", math_prompt)

    def test_rejects_actual_off_target_questions_and_accepts_method_steps(self):
        rejected = [
            oral("18 + 2 =", 20), oral("17 + 3 =", 20), oral("4 + 5 + 3 =", 12),
            oral("8 + 2 =", 10),
            {"type": "compare", "left_expr": "4 + 5 + 3", "right_expr": "13", "answer": "<"},
            {"type": "true_false", "stem": "8 + 2 + 5 = 15（　）", "answer": "√"},
            {"type": "fill_blank", "stem": "17 + ____ = 20", "answer": 3},
            {"type": "number_split", "top": 15, "left": 8, "right": "____", "answer": 7},
        ]
        accepted = [
            oral(), oral("9 + 9 =", 18),
            {"type": "fill_blank", "stem": "8 + ____ = 10", "answer": 2},
            {"type": "fill_blank", "stem": "8 + 7 = 8 + ____ + 5\n= 10 + ____ = ____", "answer": "2，5，15"},
            {"type": "number_split", "top": 7, "left": 2, "right": "____", "answer": 5},
            {"type": "number_split", "top": "____", "left": 2, "right": 8, "answer": 10},
            {"type": "compare", "left_expr": "8 + 7", "right_expr": "16", "answer": "<"},
            {"type": "compare", "left_expr": "8 + 7", "right_expr": "9 + 5", "answer": ">"},
            {"type": "true_false", "stem": "8 + 7 = 16（　）", "answer": "×"},
            {"type": "true_false", "stem": "8 + 2 = 10（　）", "answer": "√"},
            {"type": "true_false", "stem": "8加7，把7分成2和5（　）", "answer": "√"},
        ]
        for question in rejected + accepted:
            self.assertIsNone(question_issue(question), question)
            self.assertEqual(make_ten_issue(question) is None, question in accepted, question)
        self.assertIsNotNone(make_ten_issue(oral("９＋１＋３＝", 13)))
        self.assertIsNone(make_ten_issue(oral("９＋９＝", 18)))

    def test_practice_context_does_not_treat_history_or_fact_counts_as_a_ban(self):
        context = DiversityContext(practice_repetition=True, examples=[{"stem": "不应进入提示词的历史题"}])
        context.remember([oral()] * 3)
        self.assertEqual(context.defer_reason(oral(), "", [], 8), "")
        self.assertIn("8 + 7", context.prompt())
        self.assertNotIn("不应进入提示词", context.prompt())
        self.assertNotIn("最多用2次", context.prompt())


class TeachingAPI(unittest.TestCase):
    send = fixtures.BackendReliability.send

    def setUp(self):
        fixtures.BackendReliability.setUp(self)
        self.body.update(grade="小学一年级", keyword=GENERAL_TOPIC)
        self.body["items"] = [{"section_id": "s1", "game_type": "oral_math", "question_count": 2}]

    def test_new_model_response_may_repeat_previous_practice_without_repair(self):
        raw = {"sections": [{"section_id": "s1", "game_type": "oral_math",
                             "questions": [oral(), oral("9 + 6 =", 15)]}]}
        self.send(raw)
        get_settings().generation_repair_limit = 3
        response, model = self.send(raw, request_id="new-practice")
        model.assert_awaited_once()
        self.assertEqual(response.json()["sections"][0]["missing_count"], 0)
        self.assertFalse(response.json()["sections"][0]["quality_warnings"])
        self.assertNotIn("已出题数据", model.call_args.args[1])
        context = recent_questions(self.user.id, self.body["grade"], "数学", GENERAL_TOPIC)
        self.assertTrue(context.practice_repetition)
        self.assertFalse(context.recent)

    def test_streaming_uses_the_same_minimal_prompt(self):
        body = {key: value for key, value in self.body.items() if key != "items"}
        body.update(game_type="oral_math", question_count=2)

        async def tokens(*args, **kwargs):
            yield '{"questions":[]}'

        with patch.object(generate, "_merged_llm_params", return_value={
            "api_key": "test-key", "base_url": "https://example.invalid", "model": "test",
            "timeout": 120, "max_tokens": 4096,
        }), patch.object(generate.llm_client, "chat_stream", side_effect=tokens) as model:
            response = self.client.post("/api/v1/generate/stream", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        model.assert_called_once()
        prompt = model.call_args.args[0][0]["content"]
        self.assertIn("题数：2", prompt)
        self.assertIn("知识点：" + GENERAL_TOPIC, prompt)
        self.assertIn("教学目标", prompt)
        self.assertIn("本次生成的题目不要重复。", prompt)

    def test_same_fact_across_skills_allowed_but_exact_repeat_in_previous_chunks_rejected(self):
        self.body["items"] = [
            {"section_id": f"s{i}", "game_type": kind, "question_count": 1}
            for i, kind in enumerate(("oral_math", "compare", "true_false"))
        ]
        questions = [
            oral(), {"type": "compare", "left_expr": "8 + 7", "right_expr": "16", "answer": "<"},
            {"type": "true_false", "stem": "8 + 7 = 16（　）", "answer": "×"},
        ]
        raw = {"sections": [{"section_id": f"s{i}", "game_type": q["type"], "questions": [q]}
                            for i, q in enumerate(questions)]}
        get_settings().generation_repair_limit = 3
        response, model = self.send(raw)
        model.assert_awaited_once()
        self.assertTrue(all(not section["missing_count"] for section in response.json()["sections"]))
        get_settings().generation_repair_limit = 0
        self.body["previous_request_ids"] = ["job-one"]
        response, model = self.send(raw, request_id="same-paper-next-chunk")
        self.assertTrue(all(section["missing_count"] == 1 for section in fixtures.incomplete_sections(response)))
        model.assert_awaited_once()

    def test_scoped_make_ten_boundary_triggers_model_repair(self):
        get_settings().generation_repair_limit = 1
        for endpoint in ("generate", "generate-batch"):
            with self.subTest(endpoint=endpoint):
                bad = {"section_id": "s1", "game_type": "oral_math",
                       "questions": [oral("18 + 2 =", 20), oral("17 + 3 =", 20)]}
                body = dict(self.body)
                if endpoint == "generate":
                    body.pop("items")
                    body.update(game_type="oral_math", question_count=2)
                    raw = bad
                else:
                    raw = {"sections": [bad]}
                fixed = {"game_type": "oral_math", "questions": [oral(), oral("9 + 6 =", 15)]}
                with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(side_effect=[raw, fixed])) as model:
                    response = self.client.post(f"/api/v1/{endpoint}", json=body)
                self.assertEqual(response.status_code, 200, response.text)
                output = response.json() if endpoint == "generate" else response.json()["sections"][0]
                self.assertEqual([q["stem"] for q in output["questions"]], ["8 + 7 =", "9 + 6 ="])
                self.assertEqual(model.await_count, 2)
                for call in model.call_args_list:
                    self.assertIn("两个加数均为1～9的整数", call.args[0])

    def test_wrong_answers_still_fail_but_old_teaching_boundary_does_not_apply(self):
        raw = {"sections": [{"section_id": "s1", "game_type": "oral_math",
                             "questions": [oral("18 + 2 =", 20), oral("17 + 3 =", 20)]}]}
        get_settings().generation_repair_limit = 1
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(return_value={
            "game_type": "oral_math", "questions": [oral("18 + 2 =", 99)],
        })) as model:
            response = self.client.post("/api/v1/generate-batch", json=self.body)
        self.assertEqual(model.await_count, 2)
        output = fixtures.incomplete_sections(response)[0]
        self.assertEqual(output["questions"], [])
        self.assertEqual(output["missing_count"], 2)
        self.body["keyword"] = "20以内加法"
        response, model = self.send(raw, request_id="general-addition")
        self.assertEqual(model.await_count, 1)
        self.assertEqual(response.json()["sections"][0]["missing_count"], 0)
