"""复核后补题共用预算、保留有效题与阅读正文。"""

import asyncio
import json
from unittest.mock import AsyncMock

from app.models import GameResult, GenerateRequest, KnowledgeScope, Question
from app.services.generation_control import Usage, current_usage
from app.services.review_refill import refill_reviewed


def test_refill_preserves_accepted_questions_and_reviews_only_new_ones():
    request = GenerateRequest(grade='小学三年级', subject='数学', keyword='加法', game_type='oral_math', question_count=2)
    original = Question(id=1, type='oral_math', stem='2 + 3 =', answer=5, analysis='2+3=5', quality_status='passed')
    section = GameResult(game_type='oral_math', grade=request.grade, subject=request.subject, topic=request.keyword,
                         difficulty='easy', questions=[original], missing_count=1)
    model = AsyncMock(return_value={'questions': [{'type': 'oral_math', 'stem': '4 + 3 =', 'answer': 7}]})
    reviewer = AsyncMock(return_value={'reviews': [{'review_id': 'q1', 'status': 'passed', 'reason': '', 'analysis': '4+3=7'}]})
    usage = Usage(repairs=2)
    token = current_usage.set(usage)
    try:
        asyncio.run(refill_reviewed([section], request, KnowledgeScope(grade=request.grade, subject=request.subject, allowed=[], forbidden=[]), model, reviewer))
    finally:
        current_usage.reset(token)
    assert section.questions[0] is original
    assert section.missing_count == 0
    assert [q.id for q in section.questions] == [1, 2]
    assert usage.repairs == 3
    reviewed = json.loads(reviewer.await_args.args[1])['sections'][0]['questions']
    assert len(reviewed) == 1 and reviewed[0]['stem'] == '4 + 3 ='


def test_exhausted_budget_never_calls_model_or_changes_original_passage():
    request = GenerateRequest(grade='小学五年级', subject='语文', keyword='阅读', game_type='reading', question_count=1)
    section = GameResult(game_type='reading', grade=request.grade, subject=request.subject, topic=request.keyword,
                         difficulty='easy', passage='原文', questions=[], missing_count=1)
    model, reviewer = AsyncMock(), AsyncMock()
    token = current_usage.set(Usage(repairs=10))
    try:
        asyncio.run(refill_reviewed([section], request, KnowledgeScope(grade=request.grade, subject=request.subject, allowed=[], forbidden=[]), model, reviewer))
    finally:
        current_usage.reset(token)
    model.assert_not_awaited()
    reviewer.assert_not_awaited()
    assert section.passage == '原文' and section.missing_count == 1
