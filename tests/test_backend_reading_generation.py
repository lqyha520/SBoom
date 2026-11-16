"""阅读格式兼容及初次缺题的原文补题回归，不调用外部模型。"""

import asyncio
import copy
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models import BatchItem, GenerateRequest, KnowledgeScope
from app.services.generation_control import Usage, current_usage
from app.services.generation_results import _take_questions, normalize_result
from app.services.question_review import review_results
from app.services.review_refill import refill_reviewed

PASSAGE = '春天，小明和奶奶在院子里种菜。小明每天浇水、捉虫，终于等到了收获。'
ORIGINAL = {'type': 'multiple_choice', 'stem': '小明和谁种菜？', 'options': ['奶奶', '爷爷'], 'answer': 0}
PATCH = {'type': 'reading', 'stem': '小明每天怎样照顾蔬菜？', 'answer': '浇水、捉虫。'}


def test_reading_multi_blank_array_preserves_answer_order_and_input():
    question = {'type': 'fill_blank', 'stem': '做事情要有________，还要付出________。', 'answer': ['耐心', '劳动']}
    original = copy.deepcopy(question)
    kept, rejected = _take_questions({'questions': [question]}, 'reading', 1)
    assert not rejected and kept[0]['answer'] == '耐心；劳动'
    assert question == original


@pytest.mark.parametrize('stem,answer', [
    ('要有___，付出___。', ['耐心']),
    ('要有___。', ['耐心', '劳动']),
    ('解释这句话。', ['耐心']),
    ('要有___，付出___。', ['耐心', ' ']),
    ('要有___，付出___。', ['耐心', None]),
    ('要有___，付出___。', ['耐心', True]),
    ('要有___，付出___。', [['耐心'], ['劳动']]),
])
def test_reading_does_not_guess_ambiguous_blank_arrays(stem, answer):
    kept, rejected = _take_questions({'questions': [{'type': 'fill_blank', 'stem': stem, 'answer': answer}]}, 'reading', 1)
    assert not kept and rejected


def test_short_answer_alias_is_limited_to_reading_without_options():
    question = {**PATCH, 'type': 'short_answer'}
    kept, rejected = _take_questions({'questions': [question]}, 'reading', 1)
    assert not rejected and kept[0]['type'] == 'reading' and kept[0]['answer'] == PATCH['answer']
    for kind, bad in [('quiz', question), ('reading', {**question, 'options': ['甲', '乙']}),
                      ('reading', {**question, 'type': 'unknown'}), ('reading', {**question, 'type': ['reading']})]:
        kept, rejected = _take_questions({'questions': [bad]}, kind, 1)
        assert not kept and rejected


def passed_review(_system, message, _count):
    return {'reviews': [{'review_id': q['review_id'], 'status': 'passed', 'reason': '', 'analysis': '原文写明小明与奶奶种菜，每天浇水、捉虫。'}
                        for section in json.loads(message)['sections'] for q in section['questions']]}


async def run_reading_refill(raw, model, reviewer, usage=None):
    request = GenerateRequest(grade='小学三年级', subject='语文', keyword='阅读理解', game_type='reading', question_count=2)
    scope = KnowledgeScope(grade=request.grade, subject=request.subject, allowed=[], forbidden=[])
    token = current_usage.set(usage or Usage())
    try:
        section = await normalize_result(raw, request, BatchItem(game_type='reading', question_count=2, section_id='s1'), scope, model)
        await review_results([section], request, reviewer, generate_analysis=True)
        originals = list(section.questions)
        await refill_reviewed([section], request, scope, model, reviewer)
        assert all(section.questions[index] is question for index, question in enumerate(originals))
        return section
    finally:
        current_usage.reset(token)


@pytest.mark.parametrize('include_passage', [True, False])
def test_initial_format_rejection_refills_only_missing_question_with_original_passage(include_passage):
    raw = {'passage': PASSAGE, 'questions': [ORIGINAL, {**PATCH, 'type': 'unsupported'}]}
    patch = {'questions': [PATCH], **({'passage': PASSAGE} if include_passage else {})}
    model, reviewer = AsyncMock(return_value=patch), AsyncMock(side_effect=passed_review)
    usage = Usage()
    section = asyncio.run(run_reading_refill(raw, model, reviewer, usage))
    assert section.passage == PASSAGE and section.missing_count == 0
    assert [q.stem for q in section.questions] == [ORIGINAL['stem'], PATCH['stem']]
    assert [q.id for q in section.questions] == [1, 2]
    assert all(q.quality_status == 'passed' and q.analysis for q in section.questions)
    assert usage.repairs == 1
    model.assert_awaited_once()
    assert model.await_args.args[2] == 1 and PASSAGE in model.await_args.args[0]
    contract = json.loads(model.await_args.args[0].split('\n只补缺少的题。')[0].splitlines()[-1])
    assert 'passage' not in contract
    assert len(reviewer.await_args_list) == 2
    payloads = [json.loads(call.args[1])['sections'][0] for call in reviewer.await_args_list]
    assert all(s['passage'] == PASSAGE and len(s['questions']) == 1 for s in payloads)
    assert payloads[1]['questions'][0]['stem'] == PATCH['stem']


@pytest.mark.parametrize('separator', ['\\n\\n', '\r\n\r\n', '\\r\\n\\r\\n'])
def test_reading_refill_accepts_equivalent_newlines_and_keeps_normalized_original(separator):
    original = PASSAGE + separator + '收获以后，小明和奶奶一起分享蔬菜。'
    normalized = original.replace(separator, '\n\n')
    model = AsyncMock(return_value={'passage': normalized, 'questions': [PATCH]})
    reviewer = AsyncMock(side_effect=passed_review)
    section = asyncio.run(run_reading_refill({'passage': original, 'questions': [ORIGINAL]}, model, reviewer))
    assert section.passage == normalized and section.missing_count == 0
    assert [q.stem for q in section.questions] == [ORIGINAL['stem'], PATCH['stem']]
    model.assert_awaited_once()
    reviewed = json.loads(reviewer.await_args.args[1])['sections'][0]
    assert reviewed['passage'] == normalized


@pytest.mark.parametrize('patch', [
    {'passage': '另一篇文章', 'questions': [PATCH]},
    {'questions': [ORIGINAL]},
    {'questions': [{**PATCH, 'answer': []}]},
])
def test_refill_rejects_replaced_passage_duplicates_and_malformed_answers(patch):
    model, reviewer = AsyncMock(return_value=patch), AsyncMock(side_effect=passed_review)
    usage = Usage()
    section = asyncio.run(run_reading_refill({'passage': PASSAGE, 'questions': [ORIGINAL]}, model, reviewer, usage))
    assert section.passage == PASSAGE and section.missing_count == 1 and len(section.questions) == 1
    assert usage.repairs == 3 and model.await_count == 3
    reviewer.assert_awaited_once()


def test_review_rejected_patch_is_not_delivered_and_consumes_shared_budget():
    model = AsyncMock(return_value={'questions': [PATCH]})
    reviewer = AsyncMock(side_effect=[
        passed_review('', json.dumps({'sections': [{'questions': [{'review_id': 'q1'}]}]}), 1),
        {'reviews': [{'review_id': 'q1', 'status': 'reject', 'reason': '与原文矛盾', 'analysis': '答案错误。'}]},
    ])
    usage = Usage(repairs=2)
    section = asyncio.run(run_reading_refill({'passage': PASSAGE, 'questions': [ORIGINAL]}, model, reviewer, usage))
    assert section.missing_count == 1 and len(section.questions) == 1 and usage.repairs == 3
    model.assert_awaited_once()
    assert reviewer.await_count == 2


@pytest.mark.parametrize('passage', [None, '', '  '])
def test_missing_passage_never_triggers_refill(passage):
    model, reviewer = AsyncMock(), AsyncMock()
    section = asyncio.run(run_reading_refill({'passage': passage, 'questions': [ORIGINAL]}, model, reviewer))
    assert section.missing_count == 2 and not section.questions
    model.assert_not_awaited()
    reviewer.assert_not_awaited()


def test_refill_transport_failure_does_not_retry_or_discard_accepted_questions():
    model, reviewer = AsyncMock(side_effect=HTTPException(504)), AsyncMock(side_effect=passed_review)
    section = asyncio.run(run_reading_refill({'passage': PASSAGE, 'questions': [ORIGINAL]}, model, reviewer))
    assert section.missing_count == 1 and len(section.questions) == 1 and section.passage == PASSAGE
    model.assert_awaited_once()
