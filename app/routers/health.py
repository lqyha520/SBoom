"""Separate process liveness, database readiness, and provider observation."""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db import database_ready

router = APIRouter(tags=["系统"])

async def probe_database(request: Request) -> bool:
    # Both probes share one pending task, even when a caller times out.
    task = getattr(request.app.state, "readiness_probe", None)
    if task is None or task.done():
        task = asyncio.create_task(asyncio.to_thread(database_ready))
        request.app.state.readiness_probe = task
    try:
        return bool(await asyncio.wait_for(asyncio.shield(task), timeout=2.5))
    except Exception:
        return False

@router.get("/health")
async def health():
    return {"status": "healthy"}

@router.get("/readyz")
async def readiness(request: Request):
    ready = await probe_database(request)
    return JSONResponse({"status": "ready" if ready else "unavailable"},
                        status_code=200 if ready else 503, headers={"Cache-Control": "no-store"})

@router.get("/health/detail")
async def health_detail(request: Request):
    ready = await probe_database(request)
    return JSONResponse({"status": "healthy" if ready else "degraded",
                         "checks": {"database": ready, "provider_connectivity": "not_probed"}},
                        status_code=200 if ready else 503, headers={"Cache-Control": "no-store"})
