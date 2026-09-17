"""Separate process liveness from database readiness."""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db import database_ready

router = APIRouter(tags=["系统"])


@router.get("/health")
async def health():
    return {"status": "healthy"}


@router.get("/readyz")
async def readiness(request: Request):
    # Share a pending probe so timeouts cannot accumulate blocked worker threads.
    task = getattr(request.app.state, "readiness_probe", None)
    if task is None or task.done():
        task = asyncio.create_task(asyncio.to_thread(database_ready))
        request.app.state.readiness_probe = task
    try:
        ready = await asyncio.wait_for(asyncio.shield(task), timeout=2.5)
    except Exception:
        ready = False
    return JSONResponse(
        {"status": "ready" if ready else "unavailable"},
        status_code=200 if ready else 503,
        headers={"Cache-Control": "no-store"},
    )
