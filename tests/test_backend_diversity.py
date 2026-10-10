"""多样性与避重回归；仅使用一次性数据库和模拟模型。"""
import json
import time
import unittest
from unittest.mock import AsyncMock, patch

import test_backend_reliability as fixtures

from app import security
from app.config import get_settings
from app.db import db
from app.deps import SESSION_COOKIE
from app.routers import generate
from app.services.prompt_builder import prompt_builder
from app.services.question_diversity import MAX_PROMPT_CHARS, DiversityContext, recent_questions, word_problem_pattern
from app.services.question_qc import filter_questions, question_fingerprint


class Fingerprints(unittest.TestCase):
    def test_equivalent_presentations_are_duplicates(self):
        pairs = [
            ({"type": "oral_math", "stem": "8 + 5 =", "answer": 13},
             {"type": "vertical_calc", "stem": "５＋８＝____", "answer": 13}),
            ({"type": "oral_math", "stem": "4 × 6 =", "answer": 24},
             {"type": "oral_math", "stem": "6 * 4 =", "answer": 24}),
            ({"type": "oral_math", "stem": "8 + 5 =", "answer": 13},
             {"type": "fill_blank", "stem": "5 + 8 = ____", "answer": 13}),
            ({"type": "number_split", "top": 9, "left": 5, "right": "____", "answer": 4},
             {"type": "number_split", "top": "9", "left": "__", "right": "5", "answer": 4}),
            ({"type": "compare", "left_expr": "3+5", "right_expr": "9", "answer": "<"},
             {"type": "compare", "left_expr": "9", "right_expr": "5+3", "answer": ">"}),
            ({"type": "multiple_choice", "stem": "选出单数", "options": ["1", "2"], "answer": 0},
             {"type": "multiple_choice", "stem": "选出单数", "options": ["2", "1"], "answer": 1}),
            ({"type": "match_pair", "left_items": ["2+3", "3+4"], "right_items": ["5", "7"], "answer": [[0, 0], [1, 1]]},
             {"type": "match_pair", "left_items": ["3+4", "2+3"], "right_items": ["7", "5"], "answer": [[0, 0], [1, 1]]}),
        ]
        for first, second in pairs:
            with self.subTest(kind=first["type"]):
                self.assertEqual(question_fingerprint(first), question_fingerprint(second))

    def test_normal_drills_and_distinct_reading_contexts_remain_distinct(self):
        values = [
            {"type": "oral_math", "stem": stem, "answer": answer}
            for stem, answer in [("8+5=", 13), ("7+6=", 13), ("8-5=", 3), ("5-8=", -3), ("12/4=", 3)]
        ]
        self.assertEqual(len({question_fingerprint(q) for q in values}), len(values))
        question = {"type": "reading", "stem": "文章的主要内容是什么？", "answer": "例文"}
        self.assertNotEqual(question_fingerprint(question, "文章甲"), question_fingerprint(question, "文章乙"))
        self.assertEqual(len(filter_questions(values)[0]), len(values))
        self.assertFalse(word_problem_pattern(values[0]))

    def test_only_changing_names_and_numbers_is_a_similar_word_problem(self):
        first = {"type": "word_problem", "stem": "小明有 8 支铅笔，又买了 3 支，一共有多少支？"}
        second = {"type": "word_problem", "stem": "小红有 9 支铅笔，又买了 4 支，一共有多少支？"}
        different = {"type": "word_problem", "stem": "小红有 9 支铅笔，送给同学 4 支，还剩多少支？"}
        self.assertEqual(word_problem_pattern(first), word_problem_pattern(second))
        self.assertNotEqual(word_problem_pattern(first), word_problem_pattern(different))
        self.assertNotEqual(question_fingerprint(first), question_fingerprint(second))

    def test_bad_fields_do_not_crash_duplicate_filter(self):
        valid, blocked = filter_questions([{"type": "multiple_choice", "stem": "题目", "options": 42, "answer": 0}, None])
        self.assertEqual(valid, [])
        self.assertEqual(len(blocked), 2)

    def test_user_message_has_no_extra_generation_instructions(self):
        for build in (prompt_builder.build_user_message, prompt_builder.build_batch_user_message):
            value = build("20以内加法")
            self.assertEqual(value, "请生成题目。")
        context = DiversityContext(examples=[{"stem": "历史题目" * 50}] * 100)
        context.remember([{"type": "fill_blank", "stem": "本次已保留的题目____", "answer": 1}])
        prompt = context.prompt()
        self.assertLess(len(prompt), MAX_PROMPT_CHARS + 500)
        self.assertIn("本次已保留", prompt)
        self.assertNotIn('"answer"', prompt)


class DiversityContracts(unittest.TestCase):
    setUp = fixtures.BackendReliability.setUp
    send = fixtures.BackendReliability.send

    def test_history_does_not_change_model_output_or_prompt(self):
        self.send()
        raw = {"sections": [{**fixtures.section(), "questions": fixtures.questions() + fixtures.questions(start=20)}]}
        result, model = self.send(raw, request_id="fresh")
        self.assertEqual(result.status_code, 200)
        section = result.json()["sections"][0]
        self.assertEqual(section["questions"][0]["stem"], "1 + 8 = ____")
        self.assertEqual(section["missing_count"], 0)
        self.assertNotIn("1 + 8 = ____", model.call_args.args[1])
        self.assertEqual(model.await_count, 1)

    def test_repair_only_receives_basic_conditions_and_replay_never_calls_model(self):
        self.send()
        get_settings().generation_repair_limit = 3
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(side_effect=[
            {"sections": [{**fixtures.section(), "questions": []}]},
            {"game_type": "fill_blank", "questions": fixtures.questions(start=30)},
        ])) as model:
            result = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "repaired"})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["sections"][0]["questions"][0]["stem"], "30 + 8 = ____")
            self.assertNotIn("1 + 8 = ____", model.call_args_list[1].args[1])
            self.assertEqual(model.await_count, 2)
            replay = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "repaired"})
            self.assertEqual(result.json(), replay.json())
            self.assertEqual(model.await_count, 2)

    def test_repeated_practice_does_not_trigger_history_warnings(self):
        self.send()
        response, model = self.send(request_id="review")
        section = response.json()["sections"][0]
        self.assertEqual(len(section["questions"]), 2)
        self.assertEqual(section["missing_count"], 0)
        self.assertFalse(section["quality_warnings"])
        model.assert_awaited_once()

    def test_history_is_scoped_by_account_and_teaching_conditions(self):
        self.send()
        self.assertEqual(len(recent_questions(self.user.id, "小学三年级", "数学", "加法").recent), 2)
        for owner, grade, subject, keyword in [
            (self.other.id, "小学三年级", "数学", "加法"),
            (self.user.id, "小学二年级", "数学", "加法"),
            (self.user.id, "小学三年级", "英语", "加法"),
            (self.user.id, "小学三年级", "数学", "减法"),
        ]:
            self.assertFalse(recent_questions(owner, grade, subject, keyword).recent)
        self.client.cookies.set(SESSION_COOKIE, security.create_token(self.other.id))
        response, model = self.send(request_id="other-account")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("已出题数据", model.call_args.args[1])

    def test_expired_and_oversized_history_is_ignored_and_question_limit_is_bounded(self):
        self.send()
        with db() as conn:
            conn.execute("UPDATE generation_requests SET created_at = ?", (int(time.time()) - 8 * 86400,))
        self.assertFalse(recent_questions(self.user.id, "小学三年级", "数学", "加法").recent)
        source = {"grade": "小学三年级", "subject": "数学", "topic": "加法", "questions": fixtures.questions(count=120)}
        with db() as conn:
            conn.execute("UPDATE generation_requests SET created_at = ?, result_json = ?",
                         (int(time.time()), json.dumps({"sections": [source]})))
        context = recent_questions(self.user.id, "小学三年级", "数学", "加法")
        self.assertEqual(len(context.recent), 100)
        with db() as conn:
            conn.execute("UPDATE generation_requests SET result_json = ?", (json.dumps({"huge": "x" * 300_000}),))
        self.assertFalse(recent_questions(self.user.id, "小学三年级", "数学", "加法").recent)

    def test_similar_word_problems_do_not_force_a_different_teaching_relation(self):
        self.body["items"] = [{"section_id": "s1", "game_type": "word_problem", "question_count": 2}]
        stems = [
            "小明有8支铅笔，又买了3支，一共有多少支？",
            "小红有9支铅笔，又买了4支，一共有多少支？",
            "小红有9支铅笔，送给同学4支，还剩多少支？",
        ]
        values = [{"type": "word_problem", "stem": stem, "answer": answer} for stem, answer in zip(stems, [11, 13, 5], strict=True)]
        response, model = self.send({"sections": [{"section_id": "s1", "game_type": "word_problem", "questions": values}]})
        self.assertEqual([q["stem"] for q in response.json()["sections"][0]["questions"]], stems[:2])
        model.assert_awaited_once()

    def test_swapped_calculations_across_sections_are_preserved(self):
        self.body["items"] = [
            {"section_id": "s1", "game_type": "oral_math", "question_count": 1},
            {"section_id": "s2", "game_type": "vertical_calc", "question_count": 1},
        ]
        response, model = self.send({"sections": [
            {"section_id": "s1", "game_type": "oral_math", "questions": [{"type": "oral_math", "stem": "8+5=", "answer": 13}]},
            {"section_id": "s2", "game_type": "vertical_calc", "questions": [{"type": "vertical_calc", "stem": "5+8=", "answer": 13}]},
        ]})
        self.assertEqual(response.status_code, 200, response.text)
        sections = response.json()["sections"]
        self.assertEqual([len(section["questions"]) for section in sections], [1, 1])
        self.assertEqual(sections[1]["missing_count"], 0)
        model.assert_awaited_once()

    def test_single_generation_does_not_inject_history(self):
        self.send()
        get_settings().generation_repair_limit = 0
        body = {key: value for key, value in self.body.items() if key != "items"}
        body.update(game_type="fill_blank", question_count=2)
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(return_value={
            "game_type": "fill_blank", "questions": fixtures.questions() + fixtures.questions(start=40),
        })) as model:
            response = self.client.post("/api/v1/generate", json=body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["questions"][0]["stem"], "1 + 8 = ____")
        self.assertNotIn("已出题数据", model.call_args.args[1])
