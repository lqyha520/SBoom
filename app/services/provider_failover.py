"""模型链内不等待、不重复同一候选；本地拒绝与取消始终向上传播。"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
from fastapi import HTTPException

from app.blocking import run_sync
from app.config import get_settings
from app.services import provider_health
from app.services.llm_client import OutputTruncated

logger = logging.getLogger(__name__)


def can_failover(error: Exception) -> bool:
    if isinstance(error, httpx.PoolTimeout):
        return False
    if isinstance(error, (httpx.HTTPError, TimeoutError)):
        return True
    if isinstance(error, HTTPException):
        detail: dict = error.detail if isinstance(error.detail, dict) else {}
        return error.status_code in (502, 504) or detail.get("code") == "generation_truncated"
    return False


def _cooling_error() -> HTTPException:
    return HTTPException(429, detail={"code": "provider_cooling", "error": "模型服务暂时不可用，正在冷却，请稍后重试"},
                         headers={"Retry-After": str(get_settings().provider_cooldown_seconds)})


async def _record_health(candidate: dict, started: float, *, success: bool, fallback: bool = False,
                         error: Exception | None = None) -> None:
    detail: dict = error.detail if isinstance(error, HTTPException) and isinstance(error.detail, dict) else {}
    try:
        await run_sync(provider_health.record, candidate, time.monotonic() - started, success=success, fallback=fallback,
                       cooling_failure=not isinstance(error, OutputTruncated) and detail.get("code") != "provider_content_filtered")
    except Exception:
        # 统计失败不能丢弃成功结果，或替换原始失败后触发额外付费调用。
        logger.warning("模型健康统计保存失败", exc_info=False)


async def stream_with_health[T](candidate: dict, invoke: Callable[[dict], AsyncIterator[T]]) -> AsyncIterator[T]:
    """单候选实时流也遵守冷却；已经下发的 token 不会与其他模型拼接。"""
    if not await run_sync(provider_health.claim, candidate):
        raise _cooling_error()
    started = time.monotonic()
    try:
        async for chunk in invoke(candidate):
            yield chunk
    except BaseException as error:
        if isinstance(error, Exception) and can_failover(error):
            await _record_health(candidate, started, success=False, error=error)
        else:
            await run_sync(provider_health.release, candidate)
        raise
    else:
        await _record_health(candidate, started, success=True)


async def run_with_failover[T](candidates: list[dict], invoke: Callable[[dict], Awaitable[T]],
                               *, summarize_failures: bool = False) -> T:
    if not candidates:
        raise HTTPException(400, detail={"error": "没有启用的模型，请联系管理员配置"})
    failures = []
    last_error: Exception | None = None
    best_partial: OutputTruncated | None = None
    best_count = 0
    for index, candidate in enumerate(candidates):
        if not await run_sync(provider_health.claim, candidate):
            continue
        started = time.monotonic()
        try:
            result = await invoke(candidate)
        except asyncio.CancelledError:
            await run_sync(provider_health.release, candidate)
            raise
        except Exception as error:
            if not can_failover(error):
                await run_sync(provider_health.release, candidate)
                raise
            last_error = error
            detail: dict = error.detail if isinstance(error, HTTPException) and isinstance(error.detail, dict) else {}
            await _record_health(candidate, started, success=False, fallback=index > 0, error=error)
            if isinstance(error, OutputTruncated):
                from app.services.generation_results import completed_sections
                count = len(await run_sync(completed_sections, error.partial_text))
                if count > best_count:
                    best_partial, best_count = error, count
            if summarize_failures:
                failures.append({"position": index + 1, "error": detail.get("error", "模型服务调用失败"),
                                 "upstream_status": detail.get("upstream_status"), "reason": detail.get("reason")})
                logger.warning("图片模型候选 %s/%s 失败（%s，HTTP %s，分类 %s）",
                               index + 1, len(candidates), type(error).__name__,
                               detail.get("upstream_status", "未知"), detail.get("reason", "未知"))
            # 不记录地址、密钥或上游正文；用位置定位后台配置。
            logger.warning("模型候选 %s/%s 失败（%s），立即切换下一模型",
                           index + 1, len(candidates), type(error).__name__)
        else:
            await _record_health(candidate, started, success=True, fallback=index > 0)
            return result
    if best_partial is not None:
        raise best_partial
    if last_error is not None:
        if summarize_failures and len(failures) > 1 and isinstance(last_error, HTTPException):
            detail = last_error.detail if isinstance(last_error.detail, dict) else {}
            summary = "；".join(f"模型 {item['position']}：{item['error']}" for item in failures)
            raise HTTPException(last_error.status_code, detail={
                **detail, "code": "model_chain_exhausted", "attempts": failures,
                "error": f"已依次尝试 {len(failures)} 个启用模型，均未成功。{summary}",
            }, headers=last_error.headers) from last_error
        raise last_error
    raise _cooling_error()
