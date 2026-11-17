"""模型 JSON 格式兼容与失败分类；只使用模拟响应和一次性测试库。"""

import asyncio
import json
import unittest
from unittest.mock import patch

import httpx
import test_backend_reliability as fixtures

from app.routers import generate
from app.services.generation_control import request_status
from app.services.llm_client import llm_client
from app.services.model_json import ModelFormatError, extract_json


class ModelJSON(unittest.TestCase):
    def test_valid_content_is_preserved_including_think_tags_and_escapes(self):
        data = {"questions": [{"stem": '正文 <think>不应删除</think>，括号 { [ ] }，引号 "。\n换行',
                               "analysis": r"\frac{1}{2}，原样的 ,] 与 ,}"}]}
        for prefix, suffix in (("", ""), ("```json\n", "\n```"), ("\ufeff", "")):
            self.assertEqual(extract_json(prefix + json.dumps(data, ensure_ascii=False) + suffix,
                                          expected_key="questions"), data)

    def test_explanation_objects_do_not_hide_the_unique_task_result(self):
        result = {"sections": [{"section_id": "s1", "questions": []}]}
        for prefix in ('说明：{这里是格式说明}\n', '{"example": "字段说明"}\n',
                       '<think>{"sections":[{"wrong":"思考中的示例"}]}</think>\n',
                       '<THINK>思考中未配平的 {</THINK>\n'):
            self.assertEqual(extract_json(prefix + '```json\n' + json.dumps(result) + '\n```',
                                          expected_key="sections"), result)

    def test_only_syntax_defects_are_repaired_without_changing_strings(self):
        text = '{"questions":[{"stem":"第一行\n第二行\r\n\t缩进，符号 ,] 和 ,}","answer":3,},],}'
        result = extract_json(text, expected_key="questions")
        self.assertEqual(result, {"questions": [{"stem": "第一行\n第二行\r\n\t缩进，符号 ,] 和 ,}", "answer": 3}]})

    def test_every_truncated_prefix_is_rejected_without_completing_answers(self):
        text = json.dumps({"sections": [fixtures.section()]}, ensure_ascii=False)
        for end in range(1, len(text)):
            with self.subTest(end=end), self.assertRaises(ModelFormatError):
                extract_json(text[:end], expected_key="sections")

    def test_wrong_root_missing_data_and_ambiguous_content_are_not_guessed(self):
        samples = [
            ('[{"sections":[]}]', "invalid_root"),
            ('{"data":{"sections":[]}}', "missing_container"),
            ('{"sections":"[]"}', "container_type"),
            ('{"error":"secret error"}', "error_object"),
            ('{"sections":[],"sections":[{}]}', "duplicate_key"),
            ('{"sections":[],"answer":NaN}', "invalid_json"),
            ('{"sections":[]}\n{"sections":[{}]}', "ambiguous_json"),
            ('{"sections":[,]}', "invalid_json"),
            ('{"sections":[{},,]}', "invalid_json"),
            ('{"sections":[{answer:3}]}', "invalid_json"),
            ('{"sections":[{"answer":3 "stem":"secret"}]}', "invalid_json"),
            ('<think>{"sections":[]}', "incomplete_json"),
            ('secret text without json', "no_json"),
        ]
        for text, reason in samples:
            with self.subTest(reason=reason), self.assertRaises(ModelFormatError) as caught:
                extract_json(text, expected_key="sections")
            self.assertEqual(caught.exception.reason, reason)
            self.assertNotIn("secret", str(caught.exception))

    def test_complexity_is_bounded_and_incomplete_trailing_results_are_rejected(self):
        for text in ('{"sections":[]}\n{"sections":[', '说明 ' + '[' * 130 + '0' + ']' * 130,
                     ' '.join('{"example":1}' for _ in range(17)) + '{"sections":[]}'):
            with self.assertRaises(ModelFormatError):
                extract_json(text, expected_key="sections")


class ModelJSONAPI(unittest.TestCase):
    def setUp(self):
        fixtures.BackendReliability.setUp(self)
        self.candidate = {"api_key": "fake-secret-key", "base_url": "https://provider.invalid/v1",
                          "model": "offline", "timeout": 5, "max_tokens": 4096}
        self.stack.enter_context(patch.object(generate, "_merged_llm_params", return_value=self.candidate))
        self.outputs: list[str] = []
        self.calls = []

        def respond(request):
            self.calls.append(request)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": self.outputs.pop(0)}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 832, "completion_tokens": 5030},
            })

        client = httpx.AsyncClient(base_url="https://provider.invalid/v1", transport=httpx.MockTransport(respond))
        self.addCleanup(lambda: asyncio.run(client.aclose()))
        self.stack.enter_context(patch.object(llm_client, "_get_client_for", return_value=client))

    def generate(self, request_id="format-case"):
        return self.client.post('/api/v1/generate-batch', json=self.body, headers={"X-Request-ID": request_id})

    def test_repaired_batch_passes_question_validation_and_replay_does_not_call_model(self):
        section = fixtures.section()
        section['questions'][0]['analysis'] += '\n分步核对。'
        content = json.dumps({"sections": [section]}, ensure_ascii=False).replace('\\n', '\n')
        self.outputs = ['说明 {字段示例}\n```json\n' + content[:-1] + ',}\n```']
        response = self.generate()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['sections'][0]['questions'][0]['analysis'], section['questions'][0]['analysis'])
        self.assertEqual(self.generate().json(), response.json())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(request_status(self.user.id, 'format-case')['usage']['completion_tokens'], 5030)

    def test_failure_is_classified_persisted_and_logs_exclude_content_and_credentials(self):
        for index, (content, reason) in enumerate((
            ('{"data":{"sections":[]},"secret":"private model text"}', 'missing_container'),
            ('{"sections":[{"secret":"private model text"}', 'incomplete_json'),
            ('{"sections":[{"secret":"private model text",} broken]}', 'invalid_json'),
        )):
            self.outputs = [content]
            with self.assertLogs('app', level='INFO') as logs:
                response = self.generate(f'bad-format-{index}')
            self.assertEqual(response.status_code, 502, response.text)
            self.assertEqual(response.json()['detail']['code'], 'generation_invalid_format')
            self.assertEqual(response.json()['detail']['reason'], reason)
            record = next(r for r in logs.records if hasattr(r, 'format_reason'))
            self.assertEqual(record.format_reason, reason)
            self.assertEqual(record.response_chars, len(content))
            self.assertEqual(record.expected_container, 'sections')
            completion = next(r for r in logs.records if hasattr(r, 'finish_reason'))
            self.assertEqual(completion.finish_reason, 'stop')
            self.assertEqual(completion.output_limit, 4096)
            for secret in ('private model text', 'fake-secret-key', 'provider.invalid'):
                self.assertNotIn(secret, repr([r.__dict__ for r in logs.records]) + response.text)
            self.assertEqual(self.generate(f'bad-format-{index}').json(), response.json())
            self.assertEqual(len(self.calls), index + 1)

    def test_unrepairable_format_still_uses_configured_backup_once(self):
        self.outputs = ['{"questions":[]}', json.dumps({"sections": [fixtures.section()]})]
        with patch.object(generate, '_merged_llm_params', return_value={
            'models': [self.candidate, {**self.candidate, 'model': 'backup'}],
        }):
            response = self.generate()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([json.loads(call.content)['model'] for call in self.calls], ['offline', 'backup'])
        self.assertEqual(request_status(self.user.id, 'format-case')['usage']['model_calls'], 2)

    def test_complete_syntax_failure_retries_once_and_replay_is_free(self):
        from app.config import get_settings
        get_settings().generation_repair_limit = 1
        self.outputs = ['{"sections":[,]}', json.dumps({'sections': [fixtures.section()]})]
        response = self.generate('syntax-retry')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.generate('syntax-retry').json(), response.json())
        self.assertEqual(len(self.calls), 2)
        status = request_status(self.user.id, 'syntax-retry')
        self.assertEqual(status['usage']['model_calls'], 2)
        self.assertTrue(any(item['stage'] == 'format' for item in status['trace']['rejections']))
