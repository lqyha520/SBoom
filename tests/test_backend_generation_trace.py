"""真实计量路径上的追踪、缓存重放与解析恢复；使用离线 HTTP transport。"""
import json
import unittest
from unittest.mock import AsyncMock, patch

import test_backend_generation_stages as stage_fixtures
from test_backend_generation_stages import explained

from app.routers import admin, generate
from app.services.generation_control import request_status


class GenerationTraceTests(unittest.TestCase):
    setUp = stage_fixtures.StageAPI.setUp

    def test_actual_calls_stages_tokens_replay_and_privacy(self):
        self.body['items'][0]['question_count'] = 7
        def send():
            return self.client.post('/api/v1/generate-batch', json=self.body, headers={'X-Request-ID': 'trace-original'})
        self.assertEqual(send().status_code, 200)
        result = request_status(self.user.id, 'trace-original')
        trace = result['trace']
        self.assertEqual([call['stage'] for call in trace['calls']], ['generate', 'review', 'review'])
        self.assertTrue(all(call['model'] == 'offline' and call['prompt_tokens'] == 100 for call in trace['calls']))
        self.assertTrue(all(call['duration_ms'] >= 0 and call['status'] == 'success' for call in trace['calls']))
        self.assertEqual([stage['stage'] for stage in trace['stages']], ['generate', 'validate_refill', 'review'])
        self.assertNotIn('offline-key', json.dumps(trace))
        self.assertNotIn('unused.invalid', json.dumps(trace))
        self.assertEqual(send().status_code, 200)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(request_status(self.user.id, 'trace-original')['replay_count'], 1)
        self.assertEqual(self.client.get('/api/v1/me/generations/nonexistent').status_code, 404)
        self.client.app.include_router(admin.router)
        self.assertEqual(self.client.get('/api/v1/admin/generation-traces').status_code, 403)

    def test_retry_only_failed_analysis_preserves_questions_and_replays(self):
        self.body['items'][0]['question_count'] = 7
        self.fail_batch = 1
        source = self.client.post('/api/v1/generate-batch', json=self.body, headers={'X-Request-ID': 'partial-analysis'})
        before = source.json()['sections'][0]['questions']
        self.assertEqual([q['quality_status'] for q in before], ['unchecked'] * 6 + ['passed'])
        model = AsyncMock(side_effect=explained)
        with patch.object(generate, '_call_quality_review', model):
            body = {'source_request_id': 'partial-analysis'}
            result = self.client.post('/api/v1/retry-analysis', json=body, headers={'X-Request-ID': 'retry-one'})
            self.assertEqual(result.status_code, 200, result.text)
            after = result.json()['sections'][0]['questions']
            self.assertEqual([(q['id'], q['stem'], q['answer']) for q in after], [(q['id'], q['stem'], q['answer']) for q in before])
            self.assertEqual(model.await_args.args[2], 6)
            self.assertTrue(all(q['quality_status'] == 'passed' for q in after))
            replay = self.client.post('/api/v1/retry-analysis', json=body, headers={'X-Request-ID': 'retry-one'})
            self.assertEqual(result.json(), replay.json())
            self.assertEqual(model.await_count, 1)
        self.assertEqual(request_status(self.user.id, 'partial-analysis')['result']['sections'][0]['questions'], before)
        from app import security
        from app.deps import SESSION_COOKIE
        self.client.cookies.set(SESSION_COOKIE, security.create_token(self.other.id))
        self.assertEqual(self.client.post('/api/v1/retry-analysis', json=body).status_code, 404)

    def test_retry_reject_marks_question_for_review_without_removing_it(self):
        self.body['items'][0]['question_count'] = 1
        self.fail_batch = 1
        self.client.post('/api/v1/generate-batch', json=self.body, headers={'X-Request-ID': 'retry-reject-source'})
        model = AsyncMock(return_value={'reviews': [{'review_id': 'q1', 'status': 'reject', 'reason': '需要人工核对', 'analysis': ''}]})
        with patch.object(generate, '_call_quality_review', model):
            result = self.client.post('/api/v1/retry-analysis', json={'source_request_id': 'retry-reject-source'})
        self.assertEqual(result.status_code, 200, result.text)
        questions = result.json()['sections'][0]['questions']
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]['quality_status'], 'needs_review')
