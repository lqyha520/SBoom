"""复核业务降级不能混入成功指标；无需数据库或真实模型。"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app import metrics
from app.models import GameResult, GenerateRequest, Question
from app.services.question_review import review_results


def candidate():
    return GameResult(game_type="quiz", grade="小学一年级", subject="数学", topic="加法", difficulty="easy",
                      questions=[Question(id=1, type="quiz", stem="2+3=?", answer=5, analysis="2+3=5")])


@pytest.mark.parametrize(("raw", "status", "quality"), [
    ({"reviews": [{"review_id": "q1", "status": "passed", "reason": ""}]}, "success", "passed"),
    ({}, "degraded", "unchecked"),
    (TimeoutError(), "degraded", "unchecked"),
])
def test_review_business_outcome(raw, status, quality):
    section = candidate()
    call = AsyncMock(side_effect=raw) if isinstance(raw, Exception) else AsyncMock(return_value=raw)
    with patch.object(metrics.generation_stage_duration, "labels") as labels:
        asyncio.run(review_results([section], GenerateRequest(grade="小学一年级", subject="数学", keyword="加法"), call))
    labels.assert_called_once_with("review", status)
    labels.return_value.observe.assert_called_once()
    assert section.questions[0].quality_status == quality


def test_empty_review_is_skipped_and_cancellation_is_error():
    async def run():
        await review_results([], None, AsyncMock())
        with pytest.raises(asyncio.CancelledError):
            async with metrics.generation_stage("generate"):
                raise asyncio.CancelledError()
    with patch.object(metrics.generation_stage_duration, "labels") as labels:
        asyncio.run(run())
    assert [call.args for call in labels.call_args_list] == [("review", "skipped"), ("generate", "error")]


def test_status_usage_is_owned_and_read_only():
    from app.services import generation_control

    row = {"request_id": "eval-one", "kind": "single", "status": "succeeded", "created_at": 1,
           "lease_expires_at": 1, "finished_at": 0, "result_json": "{}", "error_json": "", "error_status": 0,
           "model_calls": 2, "reported_calls": 1, "prompt_tokens": 42, "completion_tokens": 21}
    with patch.object(generation_control, "db") as database:
        query = database.return_value.__enter__.return_value.execute
        query.return_value.fetchone.return_value = row
        result = generation_control.request_status(7, "eval-one")
    assert query.call_args.args[1] == (7, "eval-one")
    assert result["usage"] == {key: row[key] for key in ("model_calls", "reported_calls", "prompt_tokens", "completion_tokens")}
