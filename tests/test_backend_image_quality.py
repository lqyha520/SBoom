"""图片内容检查的计费、恢复和教学约束回归；供应商全部模拟。"""
import asyncio
import json
from unittest.mock import patch

import httpx
import pytest
import test_backend_image_generation as fixtures
from fastapi import HTTPException

from app.models.image_generation import ImageWorksheetRequest
from app.models.model_profiles import TextModelProfile
from app.services import app_config, image_review
from app.services.image_prompt import allowed_types, build_prompt
from app.services.llm_client import LLMClient, prompt_budget


def report(count=4):
    return {"checks": {name: "pass" for name in image_review.Checks.model_fields},
            "counts": [{"game_type": "oral_math", "count": count}], "issues": []}


def request(**changes):
    return ImageWorksheetRequest.model_validate({"grade": "小学一年级", "subject": "数学", "keyword": "10以内加减法",
        "items": [{"game_type": "oral_math", "question_count": 4}], **changes})


@pytest.fixture
def case():
    fixture = fixtures.ImageGenerationContracts(methodName="runTest")
    fixture.setUp()
    client = LLMClient()
    fixture.stack.enter_context(patch.object(image_review, "llm_client", client))
    app_config.save_llm_models([TextModelProfile(id="reviewer", baseUrl="https://provider.invalid/v1",
        model="vision-model", apiKey="review-test-key", imageReview=True, timeout=30)])
    fixture.body = request().model_dump(mode="json")
    try:
        yield fixture
    finally:
        fixture.client.portal.call(client.close)
        fixture.doCleanups()


def reviewed_handler(value, *, failure=False):
    def handle(req):
        if req.url.path.endswith("/chat/completions"):
            if failure:
                return httpx.Response(500, json={"error": "private provider details"})
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(value)}, "finish_reason": "stop"}],
                                            "usage": {"prompt_tokens": 101, "completion_tokens": 49}})
        return httpx.Response(200, json={"data": [{"b64_json": fixtures.base64.b64encode(fixtures.png()).decode()}]})
    return handle


def test_subject_and_age_are_enforced_before_paid_request(case):
    for index, change in enumerate([{"subject": "语文"}, {"items": [{"game_type": "reading", "question_count": 1}]}]):
        result = case.send("invalid-" + str(index), {**case.body, **change})
        assert result.status_code == 400
    assert case.calls == []
    assert "oral_math" not in allowed_types("小学三年级", "语文")
    assert "smart_calc" not in allowed_types("小学三年级", "数学")
    assert "challenge" not in allowed_types("小学四年级", "英语")
    assert "challenge" in allowed_types("小学五年级", "英语")


def test_auto_subjects_and_explicit_quantity_contract():
    prompt = build_prompt(request(subject="语文", items=[]))
    line = next(line for line in prompt.splitlines() if line.startswith("题型及题量："))
    assert "口算" not in line and "竖式" not in line
    math = build_prompt(request())
    assert "整页恰好4道题" in math and "一个待计算的算式" in math
    assert "装饰不能被误当成计数对象" in math
    assert "题目区域只有题号、算式与作答空格" in math
    assert "划掉或标出拿走" in build_prompt(request(requirements="请配数量图"))
    assert build_prompt(request(image_count=2, image_index=1)) != build_prompt(request(image_count=2, image_index=2))


def test_actual_count_overrides_models_all_pass_claim():
    result = image_review.assess(json.dumps(report(12)), request())
    assert result["status"] == "issues" and result["checks"]["quantity"] == "fail"
    assert "12" in result["issues"][0]["message"]


def test_phonetic_choices_use_same_character_without_answer_hints():
    prompt = build_prompt(request(grade="小学三年级", subject="语文", keyword="多音字读音",
                                  items=[{"game_type": "quiz", "question_count": 4}]))
    assert "只有一个正确选项" in prompt
    assert "2个完整选项" in prompt and "3至4个" not in prompt
    assert "确有多个读音的汉字" in prompt and "选项只列该字的两个候选读音" in prompt


def test_missing_or_uncertain_checks_cannot_be_approved():
    value = report()
    value["checks"]["diagram"] = "uncertain"
    assert image_review.assess(json.dumps(value), request())["status"] == "issues"
    del value["checks"]["diagram"]
    with pytest.raises(ValueError):
        image_review.assess(json.dumps(value), request())
    value = report()
    value["counts"] *= 2
    with pytest.raises(ValueError):
        image_review.assess(json.dumps(value), request())


def test_review_is_metered_persisted_and_never_repeated_on_replay(case):
    case.handler = reviewed_handler(report())
    first = case.send("review-once")
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["quality_review"]["status"] == "passed"
    assert result["quality_review"]["human_status"] == "pending"
    assert "b64_json" not in result
    assert [r.url.path for r in case.calls] == ["/v1/images/generations", "/v1/chat/completions"]
    review_body = json.loads(case.calls[-1].content)
    assert review_body["messages"][-1]["content"][-1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert review_body["chat_template_kwargs"] == {"enable_thinking": False}
    assert case.send("review-once").json() == result
    saved = case.client.get("/api/v1/me/generations/review-once").json()
    assert saved["result"] == result
    assert saved["usage"]["model_calls"] == 2 and saved["usage"]["prompt_tokens"] == 101
    assert len(case.calls) == 2


def test_failed_review_keeps_image_and_does_not_regenerate(case):
    case.handler = reviewed_handler(report(), failure=True)
    response = case.send("review-failed")
    assert response.status_code == 200
    result = response.json()
    assert result["quality_review"]["status"] == "unavailable"
    assert "private provider" not in response.text
    assert case.client.get(result["url"]).status_code == 200
    assert case.send("review-failed").json() == result and len(case.calls) == 2


@pytest.mark.parametrize('kind', ['model_issue', 'count_mismatch', 'uncertain'])
def test_review_findings_survive_http_serialization_and_replay(case, kind):
    value = report(12 if kind == 'count_mismatch' else 4)
    if kind == 'model_issue':
        value['issues'] = [{'question': '第2题', 'message': '题干条件不足，请核对'}]
        value['checks']['solvability'] = 'fail'
    elif kind == 'uncertain':
        value['checks']['text'] = 'uncertain'
    case.handler = reviewed_handler(value)
    response = case.send('review-findings')
    assert response.status_code == 200, response.text
    result = response.json()
    review = result['quality_review']
    assert review['status'] == 'issues' and review['human_status'] == 'pending'
    assert review['issues'] and all(item['question'] and item['message'] for item in review['issues'])
    assert case.client.get(result['url']).status_code == 200
    assert case.send('review-findings').json() == result
    assert case.client.get('/api/v1/me/generations/review-findings').json()['result'] == result
    assert len(case.calls) == 2


def test_review_budget_failure_preserves_original(case):
    case.handler = reviewed_handler(report())
    with patch("app.services.llm_client.reserve", side_effect=HTTPException(429, "budget")):
        result = case.send("review-budget").json()
    assert result["quality_review"]["status"] == "unavailable"
    assert len(case.calls) == 1
    assert case.client.get(result["url"]).status_code == 200


def test_interrupt_after_asset_saved_recovers_without_another_paid_call(case):
    from app.services.generation_control import request_status
    from app.services.image_recovery import _claim, recover

    case.handler = reviewed_handler(report())
    with patch.object(image_review, "review_image", side_effect=HTTPException(503, "interrupted")):
        assert case.send("review-interrupted").status_code == 503
    lease = _claim(case.user.id, "review-interrupted")
    assert lease is not None
    asyncio.run(recover(lease))
    result = request_status(case.user.id, "review-interrupted")["result"]
    assert result["quality_review"]["status"] == "unavailable"
    assert result["quality_review"]["human_status"] == "pending"
    assert case.client.get(result["url"]).status_code == 200
    assert len(case.calls) == 1


def test_visual_budget_does_not_count_base64_as_text():
    message = [{"role": "user", "content": [{"type": "text", "text": "检查"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 2_000_000}}]}]
    assert 16384 < prompt_budget(message) < 17000
    text = [{"role": "user", "content": "原有文本预算"}]
    assert prompt_budget(text) == len(json.dumps(text, ensure_ascii=False).encode())
