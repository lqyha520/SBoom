"""模型链内不等待、不重复同一候选；本地拒绝与取消始终向上传播。"""

import logging
from collections.abc import Awaitable, Callable

import httpx
from fastapi import HTTPException

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


async def run_with_failover[T](candidates: list[dict], invoke: Callable[[dict], Awaitable[T]],
                               *, summarize_failures: bool = False) -> T:
    if not candidates:
        raise HTTPException(400, detail={"error": "没有启用的模型，请联系管理员配置"})
    failures = []
    for index, candidate in enumerate(candidates):
        try:
            return await invoke(candidate)
        except Exception as error:
            if not can_failover(error):
                raise
            detail: dict = error.detail if isinstance(error, HTTPException) and isinstance(error.detail, dict) else {}
            if summarize_failures:
                failures.append({"position": index + 1, "error": detail.get("error", "模型服务调用失败"),
                                 "upstream_status": detail.get("upstream_status"), "reason": detail.get("reason")})
                logger.warning("图片模型候选 %s/%s 失败（%s，HTTP %s，分类 %s）",
                               index + 1, len(candidates), type(error).__name__,
                               detail.get("upstream_status", "未知"), detail.get("reason", "未知"))
            if index + 1 == len(candidates):
                if summarize_failures and len(failures) > 1 and isinstance(error, HTTPException):
                    summary = "；".join(f"模型 {item['position']}：{item['error']}" for item in failures)
                    raise HTTPException(error.status_code, detail={
                        **detail, "code": "model_chain_exhausted", "attempts": failures,
                        "error": f"已依次尝试 {len(failures)} 个启用模型，均未成功。{summary}",
                    }, headers=error.headers) from error
                raise
            # 不记录地址、密钥或上游正文；用位置定位后台配置。
            logger.warning("模型候选 %s/%s 失败（%s），立即切换下一模型",
                           index + 1, len(candidates), type(error).__name__)
    raise RuntimeError("模型候选列表为空")
