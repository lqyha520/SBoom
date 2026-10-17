"""质量回归：确定性反例、误报边界、独立复核协议和实际 API 流程（模型离线模拟）。"""

import json
import unittest
from unittest.mock import AsyncMock, patch

import test_backend_reliability as fixtures

from app.models import BatchGenerateRequest, BatchItem, GameResult, GenerateRequest, KnowledgeScope, Question
from app.routers import generate
from app.services.generation_results import _take_questions, normalize_result
from app.services.llm_client import OutputTruncated
from app.services.prompt_builder import prompt_builder
from app.services.question_qc import arithmetic_statement, exact_question_key, question_issue
from app.services.question_review import review_results


def choice(answer=1, options=None):
    return {"type": "multiple_choice", "stem": "2 + 3 等于多少？", "options": options or ["4", "5", "6"],
            "answer": answer, "analysis": "2 + 3 = 5"}


def result(*questions):
    return GameResult(game_type="quiz", section_id="s1", grade="小学一年级", subject="数学", topic="20以内加法",
                      difficulty="medium", questions=[Question(id=i + 1, **q) for i, q in enumerate(questions)])


def request():
    return GenerateRequest(grade="小学一年级", subject="数学", keyword="20以内加法", game_type="quiz")


class QualityRules(unittest.TestCase):
    def test_arithmetic_choice_checks_value_not_just_index(self):
        self.assertIsNone(question_issue(choice()))
        self.assertIsNotNone(question_issue(choice(0)))
        self.assertIsNotNone(question_issue(choice(1, ["4", "5", "10/2"])))
        self.assertIsNotNone(question_issue(choice(1, ["4", "7", "6"])))

    def test_choice_reverse_question_is_not_treated_as_direct_calculation(self):
        q = {**choice(0), "stem": "关于2+3，哪个答案是错误的？"}
        self.assertIsNone(question_issue(q))

    def test_wrong_analysis_and_pair_answers_are_rejected(self):
        self.assertIsNotNone(question_issue({**choice(), "analysis": "2加3等于4。"}))
        self.assertIsNotNone(question_issue({"type": "oral_math", "stem": "2+3=", "answer": 5, "analysis": "2+3=4"}))
        self.assertIsNotNone(question_issue({"type": "match_pair", "left_items": ["2+3", "4+2"],
                                             "right_items": ["5", "6"], "answer": [[0, 1], [1, 0]]}))

    def test_discussion_of_wrong_solution_is_not_a_false_positive(self):
        for analysis in ("2+3=4是错误的，正确结果为5。", "不能写成2+3=4，应为2+3=5。", "小明说“2+3=4”，应当纠正。"):
            self.assertIsNone(question_issue({**choice(), "analysis": analysis}))

    def test_higher_grade_repeated_addition_is_valid(self):
        self.assertIsNone(question_issue({"type": "fill_blank", "stem": "3+3+3=3×___", "answer": 3}))

    def test_math_typography_and_english_spacing_are_not_flattened_into_other_questions(self):
        for first, second in (("2²=___", "22=___"), ("a long", "along"), ("US", "us")):
            self.assertNotEqual(exact_question_key({"stem": first}), exact_question_key({"stem": second}))
        self.assertEqual(exact_question_key({"stem": "８ × ２ ="}), exact_question_key({"stem": "8*2="}))
        self.assertIsNone(question_issue({"type": "fill_blank", "stem": "2²=___", "answer": 4}))
        self.assertIsNone(arithmetic_statement("2²=22"))

    def test_exact_dedup_preserves_different_skills_and_passages(self):
        q = {"type": "oral_math", "stem": "8 + 7 =", "answer": 15}
        seen = set()
        kept, rejected = _take_questions({"questions": [q, {**q, "stem": "８＋７＝"}, {**q, "stem": "7+8="}]}, "oral_math", 3, seen=seen)
        self.assertEqual(len(kept), 2)
        self.assertEqual(sum(rejected.values()), 1)
        kept, _ = _take_questions({"questions": [{"type": "fill_blank", "stem": "8+___=15", "answer": 7}]}, "fill_blank", 1, seen=seen)
        self.assertEqual(len(kept), 1)
        for passage in ("正文甲", "正文乙"):
            kept, _ = _take_questions({"questions": [choice()]}, "reading", 1, seen=seen, passage=passage)
            self.assertEqual(len(kept), 1)

    def test_difficulty_changes_both_prompts_and_retains_explicit_scope(self):
        scope = KnowledgeScope(grade="小学一年级", subject="数学", allowed=["9加几"], forbidden=[])
        prompts, batches = [], []
        for difficulty in ("easy", "medium", "hard"):
            body = request().model_copy(update={"keyword": "9加几，只用偶数"})
            body = GenerateRequest(**{**body.model_dump(), "difficulty": difficulty})
            prompts.append(prompt_builder.build_system_prompt(body, scope))
            batches.append(prompt_builder.build_batch_prompt(body.grade, body.subject, body.keyword, difficulty, [BatchItem(game_type="quiz")], scope))
        self.assertEqual(len(set(prompts)), 3)
        self.assertEqual(len(set(batches)), 3)
        self.assertTrue(all("9加几，只用偶数" in prompt for prompt in prompts + batches))


class ReviewProtocol(unittest.IsolatedAsyncioTestCase):
    async def test_compact_review_retains_all_solving_data_and_zero_answers(self):
        source = [
            {**choice(0), "acceptable_answers": ["四"], "difficulty_level": 1, "tags": ["internal"],
             "expected_time_seconds": 30},
            {"type": "number_split", "top": 5, "left": 5, "right": "____", "answer": 0, "analysis": "5-5=0"},
            {"type": "match_pair", "left_items": ["a", "b"], "right_items": ["B", "A"],
             "answer": [[0, 1], [1, 0]], "analysis": "大小写对应"},
            {"type": "compare", "left_expr": "1+2", "right_expr": "3", "answer": "=", "analysis": ""},
        ]
        value = result(*source)
        value.passage = "审查所需的完整正文。"
        original = json.dumps({"sections": [{"game_type": value.game_type, "passage": value.passage, "questions": [
            {"review_id": f"q{i}", **q.model_dump(exclude={"quality_status", "quality_issues"})}
            for i, q in enumerate(value.questions, 1)]}]}, ensure_ascii=False)
        call = AsyncMock(side_effect=fixtures.passed_review)
        await review_results([result(), value], request(), call)
        serialized = call.await_args.args[1]
        sent = json.loads(serialized)["sections"]
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["passage"], value.passage)
        for index, (raw, compact) in enumerate(zip(source, sent[0]["questions"], strict=True), 1):
            self.assertEqual(compact["review_id"], f"q{index}")
            for key, content in raw.items():
                if key not in {"tags", "expected_time_seconds"}:
                    self.assertEqual(compact[key], content)
            self.assertNotIn("id", compact)
            self.assertNotIn("quality_status", compact)
            self.assertNotIn("tags", compact)
            self.assertNotIn(None, compact.values())
        self.assertLess(len(serialized.encode()), len(original.encode()) * 0.75)
        self.assertEqual(value.questions[-1].quality_status, "needs_review")

    async def test_process_fill_prompt_and_validator_agree_for_carrying_addition(self):
        body = GenerateRequest(grade="小学一年级", subject="数学", keyword="20以内的进位加法", game_type="fill_blank", question_count=1)
        scope = KnowledgeScope(grade=body.grade, subject=body.subject, allowed=[body.keyword], forbidden=[])
        question = {"type": "fill_blank", "stem": "8 + 7 = 8 + ____ + 5\n= 10 + ____ = ____", "answer": "2，5，15", "analysis": "8+7=8+2+5=15"}
        call = AsyncMock()
        normalized = await normalize_result({"questions": [question]}, body, BatchItem(game_type="fill_blank", question_count=1), scope, call)
        self.assertEqual(normalized.missing_count, 0)
        call.assert_not_awaited()
        self.assertIn("本课可安排方法填空", prompt_builder.build_system_prompt(body, scope))

    async def test_reject_uncertain_and_pass_are_bound_to_ids_not_order(self):
        values = [result(choice(), {**choice(), "stem": "另一题"}, {**choice(), "stem": "第三题"})]
        call = AsyncMock(return_value={"reviews": [
            {"review_id": "q3", "status": "passed", "reason": ""},
            {"review_id": "q1", "status": "reject", "reason": "独立求解发现答案错误"},
            {"review_id": "q2", "status": "needs_review", "reason": "条件可能不足"},
        ]})
        await review_results(values, request(), call)
        call.assert_awaited_once()
        self.assertEqual(values[0].missing_count, 1)
        self.assertEqual([q.id for q in values[0].questions], [1, 2])
        self.assertEqual([q.quality_status for q in values[0].questions], ["needs_review", "passed"])
        self.assertEqual(values[0].questions[0].quality_issues, ["条件可能不足"])

    async def test_invalid_reviews_or_timeout_never_look_passed(self):
        for raw in ({}, {"reviews": []}, {"reviews": [{"review_id": "q99", "status": "passed", "reason": ""}]},
                    {"reviews": [{"review_id": "q1", "status": "reject", "reason": ""}]}, TimeoutError()):
            with self.subTest(raw=raw):
                value = result(choice())
                call = AsyncMock(side_effect=raw) if isinstance(raw, Exception) else AsyncMock(return_value=raw)
                await review_results([value], request(), call)
                self.assertEqual(len(value.questions), 1)
                self.assertEqual(value.questions[0].quality_status, "unchecked")
                self.assertTrue(value.quality_warnings)
                call.assert_awaited_once()

    async def test_missing_analysis_cannot_pass_and_empty_batch_does_not_call(self):
        value = result({**choice(), "analysis": ""})
        call = AsyncMock(side_effect=fixtures.passed_review)
        await review_results([value], request(), call)
        self.assertEqual(value.questions[0].quality_status, "needs_review")
        call.reset_mock()
        await review_results([result()], request(), call)
        call.assert_not_awaited()

    async def test_generation_cannot_forge_review_metadata(self):
        value = {"game_type": "quiz", "questions": [{**choice(), "quality_status": "passed", "quality_issues": []}]}
        scope = KnowledgeScope(grade=request().grade, subject="数学", allowed=[], forbidden=[])
        normalized = await normalize_result(value, request(), BatchItem(game_type="quiz", question_count=1), scope, AsyncMock())
        self.assertEqual(normalized.questions[0].quality_status, "unchecked")


class ReviewAPI(unittest.TestCase):
    setUp = fixtures.BackendReliability.setUp

    def test_discarded_truncated_section_does_not_hide_a_later_complete_section(self):
        self.body["items"] = [{"game_type": "quiz", "section_id": "s1", "question_count": 2},
                              {"game_type": "quiz", "section_id": "s2", "question_count": 1}]
        raw = {"sections": [{"game_type": "quiz", "section_id": key, "questions": [choice()]} for key in ("s1", "s2")]}
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(side_effect=OutputTruncated(json.dumps(raw)))) as model, \
             patch.object(generate, "_call_quality_review", new=AsyncMock()) as reviewer:
            response = self.client.post("/api/v1/generate-batch", json=self.body)
        self.assertEqual(response.status_code, 422)
        sections = response.json()["detail"]["partial_sections"]
        self.assertEqual([section["section_id"] for section in sections], ["s2"])
        self.assertEqual(sections[0]["questions"][0]["quality_status"], "unchecked")
        model.assert_awaited_once()
        reviewer.assert_not_awaited()

    def test_batch_reviews_once_and_replay_does_not_regenerate_or_rereview(self):
        self.body["items"] = [{"game_type": "quiz", "section_id": "s1", "question_count": 1},
                              {"game_type": "word_problem", "section_id": "s2", "question_count": 1}]
        raw = {"sections": [{"game_type": "quiz", "section_id": "s1", "questions": [choice()]},
                            {"game_type": "word_problem", "section_id": "s2", "questions": [{
                                "type": "word_problem", "stem": "有2支铅笔，又买3支，一共有多少支？", "answer": "4支", "analysis": "一共有4支。"}]}]}
        reviewed = {"reviews": [{"review_id": "q1", "status": "passed", "reason": ""},
                                {"review_id": "q2", "status": "reject", "reason": "2+3=5，应为5支"}]}
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(return_value=raw)) as model, \
             patch.object(generate, "_call_quality_review", new=AsyncMock(return_value=reviewed)) as reviewer:
            first = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "quality-one"})
            sections = fixtures.incomplete_sections(first)
            self.assertEqual([value["missing_count"] for value in sections], [0, 1])
            second = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "quality-one"})
            self.assertEqual(first.json(), second.json())
            model.assert_awaited_once()
            reviewer.assert_awaited_once()
            sent = json.loads(reviewer.call_args.args[1])
            self.assertEqual(len(sent["sections"]), 2)

    def test_duplicate_previous_request_is_scoped_to_current_account(self):
        from app.services.question_review import previous_question_keys

        response, _ = fixtures.BackendReliability.send(self)
        self.assertEqual(response.status_code, 200)
        body = BatchGenerateRequest(**{**self.body, "previous_request_ids": ["job-one"]})
        self.assertTrue(previous_question_keys(self.user.id, body))
        self.assertFalse(previous_question_keys(self.other.id, body))
