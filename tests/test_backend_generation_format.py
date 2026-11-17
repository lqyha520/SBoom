"""完整语法错误的有界重试；未知传输、截断及语义歧义不重发。"""
import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from app.services.generation_format import parse_response
from app.services.generation_policy import GenerationPolicy, current_policy
from app.services.llm_client import OutputTruncated
from app.services.model_json import ModelFormatError


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_one_shared_format_retry_preserves_input_and_stops_after_exhaustion():
    messages = [{'role': 'system', 'content': '任务'}, {'role': 'user', 'content': '原请求'}]
    token = current_policy.set(GenerationPolicy('text', {}, 120))
    try:
        call = AsyncMock(side_effect=['{"questions":[,]}', '{"questions":[]}'])
        assert await parse_response(call, messages, 'questions') == {'questions': []}
        assert call.await_count == 2 and messages[-1]['content'] == '原请求'
        assert 'JSON语法' in call.await_args.args[0][-1]['content']
        second = AsyncMock(return_value='{"questions":[,]}')
        with pytest.raises(ModelFormatError):
            await parse_response(second, messages, 'questions')
        assert second.await_count == 1
    finally:
        current_policy.reset(token)


@pytest.mark.anyio
@pytest.mark.parametrize('failure', [httpx.ReadTimeout('unknown'), asyncio.CancelledError(),
                                    '{"questions":[', '{"questions":[],"questions":[]}'])
async def test_transport_truncation_and_ambiguity_are_not_retried(failure):
    token = current_policy.set(GenerationPolicy('text', {}, 120))
    call = AsyncMock(side_effect=failure) if isinstance(failure, BaseException) else AsyncMock(return_value=failure)
    try:
        with pytest.raises((httpx.ReadTimeout, asyncio.CancelledError, ModelFormatError)):
            await parse_response(call, [{'role': 'user', 'content': 'request'}], 'questions')
        assert call.await_count == 1 and current_policy.get().format_retries_remaining == 1
    finally:
        current_policy.reset(token)


@pytest.mark.anyio
async def test_completed_empty_text_uses_same_single_retry_budget():
    token = current_policy.set(GenerationPolicy('text', {}, 120))
    call = AsyncMock(side_effect=[HTTPException(502, {'code': 'provider_empty_text'}), '{"questions":[]}'])
    try:
        assert await parse_response(call, [{'role': 'user', 'content': 'request'}], 'questions') == {'questions': []}
        assert call.await_count == 2 and current_policy.get().format_retries_remaining == 0
    finally:
        current_policy.reset(token)


@pytest.mark.anyio
async def test_empty_reasoning_recovery_uses_shared_budget_and_does_not_repeat_failure():
    token = current_policy.set(GenerationPolicy('text', {}, 120))
    failure = OutputTruncated('', reasoning_only=True)
    call, recovery = AsyncMock(side_effect=failure), AsyncMock(side_effect=failure)
    try:
        with pytest.raises(OutputTruncated):
            await parse_response(call, [{'role': 'user', 'content': 'request'}], 'questions', empty_reasoning_call=recovery)
        assert call.await_count == recovery.await_count == 1
        assert current_policy.get().format_retries_remaining == 0
        with pytest.raises(OutputTruncated):
            await parse_response(call, [{'role': 'user', 'content': 'request'}], 'questions', empty_reasoning_call=recovery)
        assert recovery.await_count == 1
    finally:
        current_policy.reset(token)


@pytest.mark.anyio
@pytest.mark.parametrize('failure', [OutputTruncated('{"questions":[', reasoning_only=True),
                                    OutputTruncated('', reasoning_only=False), httpx.ReadTimeout('unknown')])
async def test_partial_or_unconfirmed_responses_cannot_use_reasoning_recovery(failure):
    token = current_policy.set(GenerationPolicy('text', {}, 120))
    call, recovery = AsyncMock(side_effect=failure), AsyncMock()
    try:
        with pytest.raises((OutputTruncated, httpx.ReadTimeout)):
            await parse_response(call, [{'role': 'user', 'content': 'request'}], 'questions', empty_reasoning_call=recovery)
        assert recovery.await_count == 0 and current_policy.get().format_retries_remaining == 1
    finally:
        current_policy.reset(token)
