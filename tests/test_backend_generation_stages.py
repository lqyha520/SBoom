"""分阶段出题的协议、映射、费用计量和部分失败回归；全部使用离线模型。"""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
import test_backend_reliability as fixtures
from fastapi import HTTPException

from app.config import get_settings
from app.models import BatchItem, GameResult, GameType, GenerateRequest, KnowledgeScope, Question
from app.routers import generate
from app.services.generation_control import Usage, current_usage, request_status
from app.services.generation_policy import GenerationPolicy, current_policy
from app.services.llm_client import llm_client
from app.services.prompt_builder import prompt_builder
from app.services.question_review import review_results


def explained(_system, message, count):
    questions = [q for s in json.loads(message)['sections'] for q in s['questions']]
    assert len(questions) == count
    return {'reviews': [{'review_id': q['review_id'], 'status': 'passed', 'reason': '',
                         'analysis': q['stem'].replace('____', str(q['answer']))}
                        for q in reversed(questions)]}


def sample(count=13):
    return GameResult(game_type='fill_blank', section_id='s1', grade='小学三年级', subject='数学',
                      topic='加法', difficulty='medium', questions=[
                          Question(id=i + 1, **{k: v for k, v in q.items() if k != 'analysis'})
                          for i, q in enumerate(fixtures.questions(count))])


def request():
    return GenerateRequest(grade='小学三年级', subject='数学', keyword='加法', game_type='fill_blank', question_count=13)


class StagePrompts(unittest.TestCase):
    def test_first_stage_contract_omits_analysis_for_every_type(self):
        for kind in GameType:
            body = GenerateRequest(grade='小学六年级', subject='数学', keyword='专项练习', game_type=kind)
            scope = KnowledgeScope(grade=body.grade, subject=body.subject, allowed=[], forbidden=[])
            prompts = [prompt_builder.build_system_prompt(body, scope), prompt_builder.build_batch_prompt(
                body.grade, body.subject, body.keyword, 'medium', [BatchItem(game_type=kind.value)], scope)]
            for prompt in prompts:
                contract = json.loads(prompt.splitlines()[-1])
                section = contract.get('sections', [contract])[0]
                self.assertNotIn('analysis', section['questions'][0])
                self.assertIn('本阶段只生成题目和简短答案', prompt)
                self.assertNotIn('完整解析', prompt)
            stream = prompt_builder.build_system_prompt(body, scope, include_analysis=True)
            self.assertIn('analysis', json.loads(stream.splitlines()[-1])['questions'][0])


class StageProtocol(unittest.IsolatedAsyncioTestCase):
    async def test_cross_question_analysis_is_repaired_only_for_its_original_id(self):
        section = GameResult(game_type='number_split', grade='小学一年级', subject='数学', topic='数的分成',
                             difficulty='easy', questions=[
                                 Question(id=1, type='number_split', top='____', left=2, right=5, answer=7),
                                 Question(id=2, type='number_split', top='____', left=8, right=1, answer=9)])
        original = [q.model_dump(exclude={'analysis', 'quality_status', 'quality_issues'}) for q in section.questions]
        model = AsyncMock(side_effect=[
            {'reviews': [
                {'review_id': 'q1', 'status': 'passed', 'reason': '', 'analysis': '2和5合起来是7，因为2+5=7。'},
                {'review_id': 'q2', 'status': 'passed', 'reason': '', 'analysis': '2和5合起来是7，因为8+1=9。'}]},
            {'reviews': [{'review_id': 'q2', 'status': 'passed', 'reason': '',
                          'analysis': '8和1合起来是9，因为8+1=9。', 'answer': 99, 'left': 99}]}])
        usage = Usage()
        token = current_usage.set(usage)
        try:
            await review_results([section], request(), model, generate_analysis=True)
        finally:
            current_usage.reset(token)
        self.assertEqual(model.await_count, 2)
        sent = json.loads(model.await_args_list[1].args[1])['sections'][0]['questions']
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['review_id'], 'q2')
        self.assertEqual((sent[0]['left'], sent[0]['right'], sent[0]['answer']), (8, 1, 9))
        self.assertIn('总数与题目不一致', sent[0]['analysis_issue'])
        self.assertEqual(usage.repairs, 1)
        self.assertTrue(all(q.quality_status == 'passed' for q in section.questions))
        self.assertEqual(section.questions[0].analysis, '2和5合起来是7，因为2+5=7。')
        self.assertEqual(section.questions[1].analysis, '8和1合起来是9，因为8+1=9。')
        self.assertEqual([q.model_dump(exclude={'analysis', 'quality_status', 'quality_issues'})
                          for q in section.questions], original)
        self.assertEqual(section.quality_warnings, [])

    async def test_analysis_repair_is_bounded_and_obeys_remaining_budget(self):
        for remaining in (0, 1):
            section = sample(1)
            model = AsyncMock(return_value={'reviews': [
                {'review_id': 'q1', 'status': 'passed', 'reason': '', 'analysis': '1+8=999'}]})
            with patch('app.services.question_review.reserve_repairs', return_value=remaining) as reserve:
                await review_results([section], request(), model, generate_analysis=True)
            reserve.assert_called_once_with(1)
            self.assertEqual(model.await_count, 1 + remaining)
            self.assertEqual(section.questions[0].answer, '9')
            self.assertEqual(section.questions[0].analysis, '')
            self.assertEqual(section.questions[0].quality_status, 'needs_review')
            self.assertEqual(len(section.quality_warnings), 1)

    async def test_failed_analysis_repair_preserves_other_results_and_original_question(self):
        for retry in ({'reviews': []}, TimeoutError(),
                      {'reviews': [{'review_id': 'q1', 'status': 'reject', 'reason': '疑似答案错误', 'analysis': ''}]}):
            section = sample(2)
            first = explained('', json.dumps({'sections': [{'questions': [
                {'review_id': f'q{i + 1}', **q.model_dump()} for i, q in enumerate(section.questions)]}]}), 2)
            first['reviews'][-1]['analysis'] = '1+8=999'
            model = AsyncMock(side_effect=[first, retry])
            await review_results([section], request(), model, generate_analysis=True)
            self.assertEqual(model.await_count, 2)
            self.assertEqual(len(section.questions), 2)
            self.assertEqual(section.missing_count, 0)
            self.assertEqual(section.questions[0].answer, '9')
            self.assertNotEqual(section.questions[0].quality_status, 'passed')
            self.assertEqual(section.questions[1].quality_status, 'passed')
            self.assertTrue(section.questions[1].analysis)

    async def test_analysis_repair_rate_limit_stops_later_batches_and_cancellation_propagates(self):
        for failure in (HTTPException(429, {'code': 'generation_budget'}), asyncio.CancelledError()):
            section = sample(13)
            async def initial(system, message, count):
                value = explained(system, message, count)
                value['reviews'][-1]['analysis'] = '1+8=999'
                return value
            model = AsyncMock(side_effect=[await initial('', json.dumps({'sections': [{'questions': [
                {'review_id': f'q{i + 1}', **q.model_dump()} for i, q in enumerate(section.questions[:6])]}]}), 6), failure])
            if isinstance(failure, asyncio.CancelledError):
                with self.assertRaises(asyncio.CancelledError):
                    await review_results([section], request(), model, generate_analysis=True)
            else:
                await review_results([section], request(), model, generate_analysis=True)
                self.assertTrue(all(q.quality_status == 'unchecked' for q in section.questions[6:]))
            self.assertEqual(model.await_count, 2)
            self.assertTrue(all(q.quality_status == 'passed' for q in section.questions[1:6]))

    async def test_analysis_repair_deadline_preserves_already_passed_questions(self):
        section = sample(7)
        calls = 0
        async def model(system, message, count):
            nonlocal calls
            calls += 1
            if calls == 2:
                await asyncio.Event().wait()
            value = explained(system, message, count)
            value['reviews'][-1]['analysis'] = '1+8=999'
            return value
        token = current_policy.set(GenerationPolicy('text', {}, 10, deadline=asyncio.get_running_loop().time() + 5.1))
        try:
            await asyncio.wait_for(review_results([section], request(), model, generate_analysis=True), 1)
        finally:
            current_policy.reset(token)
        self.assertEqual(calls, 2)
        self.assertTrue(all(q.quality_status == 'passed' and q.analysis for q in section.questions[1:6]))
        self.assertNotEqual(section.questions[0].quality_status, 'passed')
        self.assertEqual(section.questions[6].quality_status, 'unchecked')

    async def test_batches_use_global_ids_and_preserve_original_questions(self):
        section = sample()
        original = [(q.stem, q.answer) for q in section.questions]
        model = AsyncMock(side_effect=explained)
        await review_results([section], request(), model, generate_analysis=True)
        self.assertEqual([c.args[2] for c in model.await_args_list], [6, 6, 1])
        self.assertEqual([(q.stem, q.answer) for q in section.questions], original)
        self.assertTrue(all(q.quality_status == 'passed' and str(q.answer) in q.analysis for q in section.questions))
        self.assertEqual([q.id for q in section.questions], list(range(1, 14)))

    async def test_failed_middle_batch_keeps_questions_and_other_explanations(self):
        section = sample()
        calls = 0

        async def model(system, message, count):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise TimeoutError()
            return explained(system, message, count)

        await review_results([section], request(), model, generate_analysis=True)
        self.assertEqual(calls, 3)
        self.assertEqual(len(section.questions), 13)
        self.assertTrue(all(q.analysis and q.quality_status == 'passed' for q in section.questions[:6] + section.questions[12:]))
        self.assertTrue(all(not q.analysis and q.quality_status == 'unchecked' for q in section.questions[6:12]))
        self.assertTrue(any('解析生成与独立复核未完成' in warning for warning in section.quality_warnings))

    async def test_missing_duplicate_or_wrong_batch_ids_do_not_partially_apply(self):
        for bad in ('missing', 'duplicate', 'wrong_id', 'missing_analysis', 'empty_analysis', 'oversize_analysis'):
            section = sample(2)
            async def model(system, message, count, bad=bad):
                result = explained(system, message, count)
                records = result['reviews']
                if bad == 'missing':
                    records.pop()
                elif bad == 'duplicate':
                    records[0]['review_id'] = records[1]['review_id']
                elif bad == 'wrong_id':
                    records[0]['review_id'] = 'q7'
                elif bad == 'missing_analysis':
                    records[0].pop('analysis')
                else:
                    records[0]['analysis'] = '' if bad == 'empty_analysis' else '长' * 1201
                return result
            await review_results([section], request(), model, generate_analysis=True)
            self.assertTrue(all(not q.analysis and q.quality_status == 'unchecked' for q in section.questions), bad)

    async def test_wrong_generated_analysis_cannot_be_marked_passed(self):
        section = sample(2)
        async def model(system, message, count):
            result = explained(system, message, count)
            result['reviews'][-1]['analysis'] = '1+8=999'
            result['reviews'][-1]['answer'] = 999
            return result
        await review_results([section], request(), model, generate_analysis=True)
        self.assertEqual(section.questions[0].answer, '9')
        self.assertEqual(section.questions[0].analysis, '')
        self.assertEqual(section.questions[0].quality_status, 'needs_review')
        self.assertEqual(section.questions[1].quality_status, 'passed')

    async def test_reading_batches_keep_the_correct_complete_passage(self):
        sections = [GameResult(game_type='reading', section_id=f's{i}', grade='小学三年级', subject='语文',
                              topic='阅读', difficulty='medium', passage=f'正文{i}，必须完整保留。', questions=[
                                  Question(id=j + 1, type='multiple_choice', stem=f'正文{i}问题{j}',
                                           options=['甲', '乙'], answer=0) for j in range(7)]) for i in (1, 2)]
        sent = []
        async def model(system, message, count):
            payload = json.loads(message)['sections']
            sent.append(payload)
            return {'reviews': [{'review_id': q['review_id'], 'analysis': '依据原文可知答案为甲。',
                                 'status': 'passed', 'reason': ''} for s in payload for q in s['questions']]}
        await review_results(sections, request(), model, generate_analysis=True)
        self.assertEqual([sum(len(s['questions']) for s in batch) for batch in sent], [6, 6, 2])
        for batch in sent:
            for section in batch:
                self.assertTrue(all(q['stem'][:3] == section['passage'][:3] and q['answer'] == 0 for q in section['questions']))
        self.assertTrue(all(q.analysis for s in sections for q in s.questions))

    async def test_budget_rejection_stops_remaining_batches_and_cancellation_propagates(self):
        section = sample()
        model = AsyncMock(side_effect=HTTPException(429, {'code': 'generation_budget'}))
        await review_results([section], request(), model, generate_analysis=True)
        model.assert_awaited_once()
        self.assertTrue(all(q.quality_status == 'unchecked' and q.quality_issues for q in section.questions))
        model = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await review_results([sample()], request(), model, generate_analysis=True)
        model.assert_awaited_once()

    async def test_task_deadline_preserves_finished_batches_and_marks_remaining(self):
        section = sample()
        calls = 0
        async def model(system, message, count):
            nonlocal calls
            calls += 1
            if calls == 2:
                await asyncio.Event().wait()
            return explained(system, message, count)
        token = current_policy.set(GenerationPolicy('text', {}, 10, deadline=asyncio.get_running_loop().time() + 5.1))
        try:
            await asyncio.wait_for(review_results([section], request(), model, generate_analysis=True), 1)
        finally:
            current_policy.reset(token)
        self.assertEqual(calls, 2)
        self.assertTrue(all(q.analysis for q in section.questions[:6]))
        self.assertTrue(all(q.quality_status == 'unchecked' and q.quality_issues for q in section.questions[6:]))


class StageAPI(unittest.TestCase):
    def setUp(self):
        original_review = generate._call_quality_review
        fixtures.BackendReliability.setUp(self)
        self.stack.enter_context(patch.object(generate, '_call_quality_review', new=original_review))
        self.body['items'][0]['question_count'] = 27
        params = {'api_key': 'offline-key', 'base_url': 'https://unused.invalid/v1', 'model': 'offline',
                  'timeout': 5, 'max_tokens': 16384}
        self.stack.enter_context(patch.object(generate, '_merged_llm_params', return_value=params))
        self.calls = []
        self.fail_batch = 0
        self.bad_analysis_once = False

        def respond(request):
            payload = json.loads(request.content)
            self.calls.append(payload)
            system, message = [m['content'] for m in payload['messages']]
            if len(self.calls) == 1:
                section = fixtures.section(count=self.body['items'][0]['question_count'])
                for question in section['questions']:
                    question.pop('analysis')
                contract = json.loads(system.splitlines()[-1])
                result = {'sections': [section]} if 'sections' in contract else section
            else:
                if len(self.calls) - 1 == self.fail_batch:
                    return httpx.Response(503)
                count = sum(len(s['questions']) for s in json.loads(message)['sections'])
                result = explained(system, message, count)
                if self.bad_analysis_once and len(self.calls) == 2:
                    result['reviews'][-1]['analysis'] = '1+8=999'
            return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(result)}, 'finish_reason': 'stop'}],
                                            'usage': {'prompt_tokens': 100, 'completion_tokens': 200}})

        client = httpx.AsyncClient(base_url='https://unused.invalid/v1', transport=httpx.MockTransport(respond))
        self.addCleanup(lambda: asyncio.run(client.aclose()))
        self.stack.enter_context(patch.object(llm_client, '_get_client_for', return_value=client))

    def test_invalid_analysis_is_automatically_repaired_persisted_and_replayed(self):
        get_settings().generation_repair_limit = 1
        self.body['items'][0]['question_count'] = 2
        self.bad_analysis_once = True
        headers = {'X-Request-ID': 'automatic-analysis-repair'}
        response = self.client.post('/api/v1/generate-batch', json=self.body, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        questions = response.json()['sections'][0]['questions']
        self.assertEqual([q['answer'] for q in questions], ['9', '10'])
        self.assertTrue(all(q['analysis'] and q['quality_status'] == 'passed' for q in questions))
        self.assertEqual(response.json()['sections'][0]['quality_warnings'], [])
        self.assertEqual(len(self.calls), 3)
        retry = json.loads(self.calls[-1]['messages'][1]['content'])['sections'][0]['questions']
        self.assertEqual(len(retry), 1)
        self.assertEqual(retry[0]['review_id'], 'q1')
        saved = request_status(self.user.id, 'automatic-analysis-repair')
        self.assertEqual(saved['result']['sections'][0]['questions'], questions)
        self.assertEqual(saved['usage']['model_calls'], 3)
        replay = self.client.post('/api/v1/generate-batch', json=self.body, headers=headers)
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(len(self.calls), 3)

    def test_27_questions_use_one_draft_and_five_explanation_calls_with_replay(self):
        def send():
            return self.client.post('/api/v1/generate-batch', json=self.body, headers={'X-Request-ID': 'staged-27'})
        response = send()
        self.assertEqual(response.status_code, 200, response.text)
        questions = response.json()['sections'][0]['questions']
        self.assertEqual(len(questions), 27)
        self.assertTrue(all(q['analysis'] and q['quality_status'] == 'passed' for q in questions))
        self.assertEqual(len(self.calls), 6)
        self.assertTrue(all(p['max_tokens'] == 16384 for p in self.calls))
        self.assertNotIn('"analysis"', self.calls[0]['messages'][0]['content'].splitlines()[-1])
        for payload in self.calls[1:]:
            self.assertIn('本阶段补充解析并核对答案', payload['messages'][0]['content'])
        self.assertEqual(send().json(), response.json())
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(request_status(self.user.id, 'staged-27')['usage'],
                         {'model_calls': 6, 'reported_calls': 6, 'prompt_tokens': 600, 'completion_tokens': 1200})

    def test_explanation_failure_still_returns_and_persists_the_questions(self):
        self.body['items'][0]['question_count'] = 13
        self.fail_batch = 2
        response = self.client.post('/api/v1/generate-batch', json=self.body, headers={'X-Request-ID': 'staged-partial'})
        self.assertEqual(response.status_code, 200, response.text)
        section = response.json()['sections'][0]
        self.assertEqual(len(section['questions']), 13)
        self.assertEqual([q['quality_status'] for q in section['questions']], ['passed'] * 6 + ['unchecked'] * 6 + ['passed'])
        stored = request_status(self.user.id, 'staged-partial')
        self.assertEqual(stored['status'], 'succeeded')
        self.assertEqual(stored['result']['sections'], response.json()['sections'])
        self.assertEqual(stored['usage']['model_calls'], 4)

    def test_single_question_uses_two_stages_and_replays_without_model_calls(self):
        self.body['items'][0]['question_count'] = 1
        body = request().model_copy(update={'question_count': 1}).model_dump(mode='json')
        response = self.client.post('/api/v1/generate', json=body, headers={'X-Request-ID': 'staged-single'})
        self.assertEqual(response.status_code, 200, response.text)
        question = response.json()['questions'][0]
        self.assertEqual(question['quality_status'], 'passed')
        self.assertTrue(question['analysis'])
        self.assertEqual(len(self.calls), 2)
        replay = self.client.post('/api/v1/generate', json=body, headers={'X-Request-ID': 'staged-single'})
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(request_status(self.user.id, 'staged-single')['usage']['model_calls'], 2)
