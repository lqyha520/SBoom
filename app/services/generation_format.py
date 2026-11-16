"""响应已结束后共享一次恢复额度；未知状态和已有正文的截断不重发。"""
from fastapi import HTTPException

from app.blocking import run_sync
from app.services.generation_policy import current_policy
from app.services.generation_trace import rejected
from app.services.llm_client import OutputTruncated
from app.services.model_json import ModelFormatError, extract_json


async def parse_response(call, messages, expected_key, *, empty_reasoning_call=None):
    try:
        raw = await call(messages)
        return await run_sync(extract_json, raw, expected_key=expected_key)
    except (ModelFormatError, HTTPException) as error:
        policy = current_policy.get()
        empty_stop = (isinstance(error, HTTPException) and isinstance(error.detail, dict)
                      and error.detail.get('code') == 'provider_empty_text')
        reasoning_limit = isinstance(error, OutputTruncated) and error.reasoning_only
        recover_reasoning = empty_reasoning_call is not None and (empty_stop or reasoning_limit)
        retryable = (error.reason == 'invalid_json' if isinstance(error, ModelFormatError) else empty_stop) or recover_reasoning
        if not retryable or policy is None or policy.format_retries_remaining <= 0:
            raise
        # 仅恢复上游明确结束的响应；共享一次额度，沿用原调用时限和 token 预算。
        policy.format_retries_remaining -= 1
        retry = [dict(message) for message in messages]
        if recover_reasoning:
            rejected('reasoning', '模型已结束但只有推理、没有题目正文；本任务仅此次恢复关闭深度思考，后续复核保留原设置')
            retry[-1]['content'] += '\n上一次调用已经结束但没有输出题目正文。请直接按给定契约返回题目JSON；题目仍须满足全部教学要求。'
            raw = await empty_reasoning_call(retry)
        else:
            rejected('format', '模型完整响应缺少有效JSON正文，使用本任务的一次格式重试额度')
            retry[-1]['content'] += ('\n上一次完整响应没有有效JSON正文，未通过JSON语法校验。请重新完成当前任务，结束思考后必须输出一个合法JSON对象；'
                                      '使用双引号，转义字符串内部的引号与换行，不使用JSON注释或LaTeX裸反斜杠。')
            raw = await call(retry)
        return await run_sync(extract_json, raw, expected_key=expected_key)
