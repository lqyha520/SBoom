"""推理开关与生产空正文截断回归；使用离线响应和一次性数据库。"""
import json
from unittest.mock import patch

import httpx
import pytest
import test_backend_model_failover as fixtures
import test_backend_model_runtime as runtime
from test_backend_reliability import section

from app.routers import generate
from app.services import app_config
from app.services.generation_control import request_status

REVIEW = generate._call_quality_review
case = runtime.case


def response(value):
    return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(value)}, 'finish_reason': 'stop'}],
                                    'usage': {'prompt_tokens': 40, 'completion_tokens': 20}})


def test_thinking_setting_round_trip_saved_key_and_default_compatibility(case):
    case.login_admin()
    current = case.client.get('/api/v1/admin/llm-config').json()
    assert all(p['thinkingMode'] == 'default' for p in current['models'])
    profiles = [fixtures.profile('first', thinkingMode='disabled').model_dump()]
    profiles[0]['apiKey'] = ''
    saved = case.client.put('/api/v1/admin/llm-config', json={'models': profiles, 'revision': current['revision']})
    assert saved.status_code == 200, saved.text
    assert saved.json()['models'][0]['thinkingMode'] == 'disabled'
    assert saved.json()['models'][0]['hasKey'] is True
    assert 'secret-first' not in saved.text
    assert app_config.get_llm(fresh=True)['models'][0]['thinkingMode'] == 'disabled'


def test_both_generation_stages_disable_thinking_and_replay_keeps_usage(case):
    app_config.save_llm_models([fixtures.profile('first', thinkingMode='disabled')])
    draft = section()
    for q in draft['questions']:
        q.pop('analysis')
    case.outputs = [response({'sections': [draft]}), response({'reviews': [
        {'review_id': 'q1', 'status': 'passed', 'reason': '', 'analysis': '1+8=9'},
        {'review_id': 'q2', 'status': 'passed', 'reason': '', 'analysis': '2+8=10'},
    ]})]
    with patch.object(generate, '_call_quality_review', new=REVIEW):
        result = case.client.post('/api/v1/generate-batch', json=case.body, headers={'X-Request-ID': 'no-thinking'})
        assert result.status_code == 200, result.text
        assert all(q['quality_status'] == 'passed' and q['analysis'] for q in result.json()['sections'][0]['questions'])
        replay = case.client.post('/api/v1/generate-batch', json=case.body, headers={'X-Request-ID': 'no-thinking'})
    assert replay.json() == result.json()
    assert len(case.calls) == 2
    assert all(json.loads(c.content)['chat_template_kwargs'] == {'enable_thinking': False} for c in case.calls)
    assert request_status(case.user.id, 'no-thinking')['usage']['model_calls'] == 2


def test_fallback_has_its_own_thinking_policy(case):
    app_config.save_llm_models([fixtures.profile('first', thinkingMode='disabled'), fixtures.profile('second')])
    case.outputs = [httpx.Response(503)]
    assert case.validate('reasoning-fallback').status_code == 200
    assert json.loads(case.calls[0].content)['chat_template_kwargs'] == {'enable_thinking': False}
    assert 'chat_template_kwargs' not in json.loads(case.calls[1].content)


def test_saved_policy_is_used_by_real_json_probe_connection_probe_and_stream(case):
    app_config.save_llm_models([fixtures.profile('first', thinkingMode='disabled')])
    case.login_admin()
    case.outputs = [response({'ok': True}), fixtures.sse(fixtures.stream_event('ok', 'stop')),
                    fixtures.sse(fixtures.stream_event(json.dumps(section(count=1)), 'stop'))]
    assert case.client.post('/api/v1/admin/test-llm-generation', json={'id': 'first'}).status_code == 200
    assert case.client.post('/api/v1/admin/test-llm', json={'id': 'first'}).status_code == 200
    assert '[DONE]' in case.stream('thinking-stream').text
    assert len(case.calls) == 3
    assert all(json.loads(c.content)['chat_template_kwargs'] == {'enable_thinking': False} for c in case.calls)


@pytest.mark.parametrize('usage', [
    {'prompt_tokens': 35, 'completion_tokens': 1024, 'reasoning_tokens': 1024},
    {'prompt_tokens': 35, 'completion_tokens': 1024, 'completion_tokens_details': {'reasoning_tokens': 1024}},
])
def test_reasoning_only_limit_has_specific_message_and_safe_metadata(case, caplog, usage):
    app_config.save_llm_models([fixtures.profile('first')])
    case.outputs = [httpx.Response(200, json={'choices': [{'message': {'content': '', 'reasoning_content': 'private reasoning'},
                                                        'finish_reason': 'length'}], 'usage': usage})]
    with caplog.at_level('INFO'):
        result = case.client.post('/api/v1/generate-batch', json=case.body, headers={'X-Request-ID': 'thinking-limit'})
    assert result.status_code == 422
    assert result.json()['detail']['code'] == 'generation_truncated'
    assert '推理阶段耗尽输出额度' in result.json()['detail']['error']
    assert '减少单次题量' not in result.text
    assert 'private reasoning' not in result.text + caplog.text
    logged = next(r for r in caplog.records if hasattr(r, 'reasoning_tokens'))
    assert logged.reasoning_tokens == 1024 and logged.response_chars == 0
    assert request_status(case.user.id, 'thinking-limit')['usage']['completion_tokens'] == 1024
    assert len(case.calls) == 1


def test_normal_stop_without_body_has_one_bounded_retry_and_never_exposes_reasoning(case, caplog):
    from app.config import get_settings
    app_config.save_llm_models([fixtures.profile('first')])
    case.outputs = [httpx.Response(200, json={'choices': [{'message': {'content': '', 'reasoning_content': 'private reasoning'},
                                                        'finish_reason': 'stop'}],
                                           'usage': {'prompt_tokens': 35, 'completion_tokens': 1024}}),
                    response({'sections': [section()]})]
    with patch.object(get_settings(), 'generation_repair_limit', 1), caplog.at_level('INFO'):
        result = case.client.post('/api/v1/generate-batch', json=case.body, headers={'X-Request-ID': 'empty-stop'})
    assert result.status_code == 200, result.text
    assert len(case.calls) == 2
    assert 'private reasoning' not in result.text + caplog.text
    assert request_status(case.user.id, 'empty-stop')['usage']['model_calls'] == 2


@pytest.mark.parametrize('finish_reason', ['length', 'stop'])
def test_qwen_empty_reasoning_recovers_once_keeps_review_policy_and_replay_usage(case, caplog, finish_reason):
    from app.config import get_settings
    app_config.save_llm_models([fixtures.profile('first').model_copy(update={'model': 'qwen3.8-27b'})])
    draft = section()
    for question in draft['questions']:
        question.pop('analysis')
    case.outputs = [httpx.Response(200, json={
        'choices': [{'message': {'content': '', 'reasoning_content': 'private reasoning'}, 'finish_reason': finish_reason}],
        'usage': {'prompt_tokens': 35, 'completion_tokens': 1024}}),
        response({'sections': [draft]}), response({'reviews': [
            {'review_id': 'q1', 'status': 'passed', 'reason': '', 'analysis': '1+8=9'},
            {'review_id': 'q2', 'status': 'passed', 'reason': '', 'analysis': '2+8=10'}]})]
    with patch.object(get_settings(), 'generation_repair_limit', 1), patch.object(generate, '_call_quality_review', new=REVIEW), caplog.at_level('INFO'):
        result = case.client.post('/api/v1/generate-batch', json=case.body, headers={'X-Request-ID': 'reasoning-recovery'})
        assert result.status_code == 200, result.text
        replay = case.client.post('/api/v1/generate-batch', json=case.body, headers={'X-Request-ID': 'reasoning-recovery'})
    assert replay.json() == result.json() and len(case.calls) == 3
    payloads = [json.loads(call.content) for call in case.calls]
    assert 'chat_template_kwargs' not in payloads[0] and 'chat_template_kwargs' not in payloads[2]
    assert payloads[1]['chat_template_kwargs'] == {'enable_thinking': False}
    assert app_config.get_llm(fresh=True)['models'][0]['thinkingMode'] == 'default'
    assert 'private reasoning' not in result.text + caplog.text
    status = request_status(case.user.id, 'reasoning-recovery')
    assert status['usage']['model_calls'] == 3 and status['usage']['completion_tokens'] == 1064
    assert any(item['stage'] == 'reasoning' for item in status['trace']['rejections'])
