"""整卷统筹回归：模拟模型，不调用收费接口；数据库由 fixture 隔离。"""

import hashlib
import json
import random
import unittest
from unittest.mock import AsyncMock, patch

import test_backend_reliability as fixtures

from app.config import get_settings
from app.db import db
from app.routers import generate
from app.services.question_diversity import recent_questions
from app.services.question_planning import arrange_answers, calculation_relations
from app.services.question_qc import question_fingerprint, question_issue


def question(kind, stem, answer, **extra):
    return {"type": kind, "stem": stem, "answer": answer, **extra}


class PaperRules(unittest.TestCase):
    def test_swapped_true_false_statements_are_same_question_but_false_claim_is_different(self):
        original = question("true_false", "9 + 8 = 17（　）", "√")
        swapped = question("true_false", "８＋９＝１７（ ）", "对")
        incorrect = question("true_false", "8 + 9 = 18（　）", "×")
        self.assertEqual(question_fingerprint(original), question_fingerprint(swapped))
        self.assertNotEqual(question_fingerprint(original), question_fingerprint(incorrect))
        self.assertIsNone(question_issue(incorrect))
        self.assertIsNotNone(question_issue({**incorrect, "answer": "√"}))
        self.assertIsNone(question_issue(question("true_false", "8加4，把4分成2和2（　）", "√")))

    def test_same_fact_across_question_forms_and_different_facts_with_same_answer(self):
        variants = [
            question("oral_math", "9 + 8 =", 17),
            question("fill_blank", "____ + 9 = 17", 8),
            question("fill_blank", "9 + 8 = 10 + ____", 7),
            question("true_false", "8 + 9 = 18（　）", "×"),
            question("number_split", "", 9, top=17, left=8, right="____"),
            question("compare", "", ">", left_expr="8 + 9", right_expr="16"),
        ]
        first = calculation_relations(variants[0])
        self.assertTrue(first)
        self.assertTrue(all(calculation_relations(value) == first for value in variants))
        self.assertNotEqual(first, calculation_relations(question("oral_math", "10 + 7 =", 17)))
        self.assertFalse(calculation_relations(question("word_problem", "原来9支笔，又买8支，一共多少支？", 17)))

    def test_process_blanks_validate_each_answer_and_intermediate_step(self):
        value = question("fill_blank", "8 + 7 = 8 + ____ + 5\n= 10 + ____ = ____", "2，5，15")
        self.assertIsNone(question_issue(value))
        self.assertEqual(calculation_relations(value), calculation_relations(question("oral_math", "8+7=", 15)))
        for wrong in ("2，4，15", "2，5", "2，5，16", "随便填", "2，5，15，0"):
            self.assertIsNotNone(question_issue({**value, "answer": wrong}), wrong)
        self.assertIsNotNone(question_issue(question("fill_blank", "9 + ____ = 16", 6)))
        self.assertIsNone(question_issue(question("fill_blank", "12 ÷ ____ = 4", 3)))
        self.assertIsNone(question_issue(question("fill_blank", "3 ÷ ____ = 6", "1/2")))
        self.assertIsNone(question_issue(question("fill_blank", "3 - ____ = 5", -2)))
        self.assertIsNone(question_issue(question("fill_blank", "春天的颜色是____。", "绿色")))

    def test_answer_order_is_not_a_cycle_and_question_answer_pairs_never_change(self):
        for kind, answers in [("true_false", ["√", "×"] * 3), ("compare", [">", "<", "="] * 2)]:
            values = [question(kind, f"独立题{i}", answer, analysis=f"解析{i}") for i, answer in enumerate(answers)]
            for seed in range(20):
                rng = random.Random(seed)
                with patch("app.services.question_planning.random.shuffle", side_effect=rng.shuffle):
                    result, warnings = arrange_answers(values, kind)
                sequence = [q["answer"] for q in result]
                self.assertNotEqual(sequence[:len(answers) // 2], sequence[len(answers) // 2:])
                self.assertCountEqual(result, values)
                self.assertFalse(warnings)
        ordered = [question("true_false", "根据上一题判断（　）", answer) for answer in ["√", "×"] * 3]
        self.assertEqual(arrange_answers(ordered, "true_false")[0], ordered)
        self.assertTrue(arrange_answers(ordered, "true_false")[1])
        self.assertTrue(arrange_answers([question("true_false", "正确的陈述", "√")] * 6, "true_false")[1])
        self.assertEqual(arrange_answers(ordered, "reading"), (ordered, []))


class PaperContracts(unittest.TestCase):
    def setUp(self):
        fixtures.BackendReliability.setUp(self)

    send = fixtures.BackendReliability.send

    def test_same_relation_across_sections_does_not_trigger_replacement(self):
        kinds = ["oral_math", "compare", "true_false"]
        self.body["items"] = [{"section_id": f"s{i}", "game_type": kind, "question_count": 1}
                              for i, kind in enumerate(kinds)]
        rows = [
            [question("oral_math", "9+9=", 18)],
            [question("compare", "", "=", left_expr="9+9", right_expr="10+8")],
            [question("true_false", "9+9=19（　）", "×"), question("true_false", "8+4=12（　）", "√")],
        ]
        raw = {"sections": [{"section_id": f"s{i}", "game_type": kind, "questions": rows[i]}
                            for i, kind in enumerate(kinds)]}
        response, model = self.send(raw)
        sections = response.json()["sections"]
        self.assertEqual(sections[2]["questions"][0]["stem"], "9+9=19（　）")
        self.assertTrue(all(s["missing_count"] == 0 for s in sections))
        model.assert_awaited_once()

    def test_completed_chunks_are_current_paper_and_respect_owner(self):
        self.body["items"] = [
            {"section_id": "s1", "game_type": "oral_math", "question_count": 1},
            {"section_id": "s2", "game_type": "compare", "question_count": 1},
        ]
        self.send({"sections": [
            {"section_id": "s1", "game_type": "oral_math", "questions": [question("oral_math", "9+9=", 18)]},
            {"section_id": "s2", "game_type": "compare",
             "questions": [question("compare", "", "=", left_expr="9+9", right_expr="18")]},
        ]}, request_id="first-chunk")
        context = recent_questions(self.user.id, "小学三年级", "数学", "加法", ["first-chunk"])
        self.assertEqual(max(context.relations.values()), 2)
        self.assertFalse(context.recent)
        self.assertFalse(recent_questions(self.other.id, "小学三年级", "数学", "加法", ["first-chunk"]).relations)
        self.assertFalse(recent_questions(self.user.id, "小学三年级", "数学", "减法", ["first-chunk"]).relations)
        self.body["previous_request_ids"] = ["first-chunk"]
        self.body["items"] = [{"section_id": "s3", "game_type": "true_false", "question_count": 1}]
        response, model = self.send({"sections": [{"section_id": "s3", "game_type": "true_false", "questions": [
            question("true_false", "9+9=19（　）", "×"), question("true_false", "8+4=12（　）", "√"),
        ]}]}, request_id="second-chunk")
        self.assertEqual(response.json()["sections"][0]["questions"][0]["stem"], "9+9=19（　）")
        self.assertNotIn("9+9=", model.call_args.args[1])

    def test_exact_question_in_previous_chunk_is_rejected_without_unbounded_repairs(self):
        self.send(request_id="first-chunk")
        self.body["previous_request_ids"] = ["first-chunk"]
        response, model = self.send(request_id="second-chunk")
        sections = fixtures.incomplete_sections(response)
        self.assertEqual(sections[0]["missing_count"], 2)
        self.assertEqual(sections[0]["questions"], [])
        self.assertIn("完全重复", "；".join(sections[0]["quality_warnings"]))
        model.assert_awaited_once()

    def test_complete_sections_from_truncation_are_loaded_without_other_failed_output(self):
        self.send(request_id="partial")
        partial = {"code": "generation_truncated", "partial_sections": [{
            "grade": "小学三年级", "subject": "数学", "topic": "加法", "game_type": "oral_math",
            "questions": [question("oral_math", "9+9=", 18)],
        }]}
        with db() as conn:
            conn.execute("UPDATE generation_requests SET status = 'failed', result_json = '', error_json = ?",
                         (json.dumps(partial),))
        context = recent_questions(self.user.id, "小学三年级", "数学", "加法", ["partial"])
        self.assertEqual(len(context.current_fingerprints), 1)
        self.assertFalse(context.warnings)
        partial["code"] = "provider_timeout"
        with db() as conn:
            conn.execute("UPDATE generation_requests SET error_json = ?", (json.dumps(partial),))
        self.assertFalse(recent_questions(self.user.id, "小学三年级", "数学", "加法", ["partial"]).current_fingerprints)

    def test_history_does_not_block_swapped_judgement_in_new_paper(self):
        self.body["items"] = [{"section_id": "s1", "game_type": "true_false", "question_count": 1}]
        self.send({"sections": [{"section_id": "s1", "game_type": "true_false",
                                 "questions": [question("true_false", "9+8=17（　）", "√")]}]})
        response, _ = self.send({"sections": [{"section_id": "s1", "game_type": "true_false", "questions": [
            question("true_false", "8+9=17（　）", "√"), question("true_false", "9+3=12（　）", "√"),
        ]}]}, request_id="new-paper")
        self.assertEqual(response.json()["sections"][0]["questions"][0]["stem"], "8+9=17（　）")

    def test_practice_preserves_process_and_inverse_questions_without_template_repairs(self):
        self.body.update(grade="小学一年级", keyword="20以内进位加法（凑十法）")
        self.body["items"] = [{"section_id": "s1", "game_type": "fill_blank", "question_count": 8}]
        values = [question("fill_blank", f"9 + {n} = 10 + ____", n - 1,
                           analysis=f"9+{n}=10+{n - 1}={n + 9}") for n in range(2, 6)]
        patch_values = [
            question("fill_blank", "8 + 7 = 8 + ____ + 5\n= 10 + ____ = ____", "2，5，15", analysis="8+7=8+2+5=10+5=15"),
            question("fill_blank", "____ + 8 = 12", 4, analysis="12-8=4"),
            question("fill_blank", "8凑成10，还差____。", 2, analysis="10-8=2"),
            question("fill_blank", "8 + 3 = ____", 11, analysis="8+3=8+2+1=11"),
        ]
        get_settings().generation_repair_limit = 3
        with patch.object(generate, "_call_llm_and_parse", new=AsyncMock(side_effect=[
            {"sections": [{"section_id": "s1", "game_type": "fill_blank", "questions": values + patch_values}]},
        ])) as model:
            response = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "planned"})
            output = response.json()["sections"][0]
            self.assertEqual(len(output["questions"]), 8)
            self.assertEqual(output["missing_count"], 0)
            self.assertEqual(sum("= 10 + ____" in q["stem"] and "\n" not in q["stem"] for q in output["questions"]), 4)
            self.assertIn(patch_values[0]["stem"], [q["stem"] for q in output["questions"]])
            self.assertFalse(output["quality_warnings"])
            self.assertEqual(model.await_count, 1)
            self.assertIn("过程必须写在stem", model.call_args_list[0].args[0])
            self.assertNotIn("未要求过程填空时，不写解题步骤", model.call_args_list[0].args[0])
            replay = self.client.post("/api/v1/generate-batch", json=self.body, headers={"X-Request-ID": "planned"})
            self.assertEqual(response.json(), replay.json())
            self.assertEqual(model.await_count, 1)

    def test_valid_practice_never_triggers_paid_repairs_just_to_meet_template_quotas(self):
        self.body.update(grade="小学一年级", keyword="20以内进位加法（凑十法）")
        self.body["items"] = [{"section_id": "s1", "game_type": "fill_blank", "question_count": 8}]
        values = [question("fill_blank", f"9 + {n} = 10 + ____", n - 1,
                           analysis=f"9+{n}=10+{n - 1}={n + 9}") for n in range(2, 10)]
        raw = {"sections": [{"section_id": "s1", "game_type": "fill_blank", "questions": values}]}
        get_settings().generation_repair_limit = 1
        response, model = self.send(raw)
        output = response.json()["sections"][0]
        self.assertEqual(len(output["questions"]), 8)
        self.assertEqual(len({q["stem"] for q in output["questions"]}), 8)
        self.assertFalse(output["quality_warnings"])
        self.assertEqual(model.await_count, 1)

    def test_original_payload_without_optional_context_still_replays(self):
        original, _ = self.send()
        old_payload = {**self.body, "items": [{**self.body["items"][0]}]}
        fingerprint = hashlib.sha256(json.dumps({"kind": "batch", "payload": old_payload},
                                               sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        with db() as conn:
            conn.execute("UPDATE generation_requests SET payload_hash = ? WHERE user_id = ?", (fingerprint, self.user.id))
        replay, model = self.send()
        self.assertEqual(original.json(), replay.json())
        model.assert_not_awaited()
        self.body["previous_request_ids"] = ["changed-context"]
        conflict, model = self.send()
        self.assertEqual(conflict.status_code, 409)
        model.assert_not_awaited()

    def test_invalid_context_is_rejected_but_missing_history_does_not_affect_generation(self):
        self.body["previous_request_ids"] = ["x"] * 61
        response, model = self.send()
        self.assertEqual(response.status_code, 422)
        model.assert_not_awaited()
        self.body["previous_request_ids"] = ["missing"]
        response, _ = self.send()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["sections"][0]["quality_warnings"])
