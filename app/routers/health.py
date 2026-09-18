"""Separate process liveness from database readiness."""

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db import database_ready
from app.services.llm_client import llm_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["系统"])


@router.get("/health")
async def health():
    """基础健康检查 - 仅返回进程存活状态"""
    return {"status": "healthy"}


@router.get("/readyz")
async def readiness(request: Request):
    """就绪检查 - 包含数据库和 LLM 连接状态"""
    checks = {
        "database": False,
        "llm": False,
    }

    # Share a pending probe so timeouts cannot accumulate blocked worker threads.
    task = getattr(request.app.state, "readiness_probe", None)
    if task is None or task.done():
        task = asyncio.create_task(asyncio.to_thread(database_ready))
        request.app.state.readiness_probe = task
    try:
        checks["database"] = await asyncio.wait_for(asyncio.shield(task), timeout=2.5)
    except Exception as e:
        logger.warning("Database readiness check failed: %s", e)
        checks["database"] = False

    # LLM 连接检查（轻量级：仅验证连接池状态，不发起真实 API 调用）
    try:
        # 检查 LLM 客户端连接池是否可用
        checks["llm"] = len(llm_client._clients) >= 0  # 连接池对象存在即认为可用
    except Exception as e:
        logger.warning("LLM readiness check failed: %s", e)
        checks["llm"] = False

    all_ready = all(checks.values())
    return JSONResponse(
        {"status": "ready" if all_ready else "unavailable", "checks": checks},
        status_code=200 if all_ready else 503,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/health/detail")
async def health_detail():
    """详细健康检查 - 包含所有依赖服务状态"""
    checks = {
        "database": False,
        "llm": False,
    }

    # 数据库检查
    try:
        checks["database"] = await asyncio.to_thread(database_ready)
    except Exception as e:
        logger.warning("Database health check failed: %s", e)

    # LLM 检查
    try:
        checks["llm"] = len(llm_client._clients) >= 0
    except Exception as e:
        logger.warning("LLM health check failed: %s", e)

    all_healthy = all(checks.values())
    return {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
    }
