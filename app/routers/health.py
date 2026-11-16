"""Separate process liveness, database readiness, and provider observation."""
import asyncio

from fastapi import APIRouter, Request, Response

from app.blocking import run_sync_in
from app.db import database_ready
from app.models.health_api_responses import (
    HealthHealthDetailResponse,
    HealthHealthResponse,
    HealthReadinessResponse,
)

router = APIRouter(tags=["系统"])

async def probe_database(request: Request) -> bool:
    # Both probes share one pending task, even when a caller times out.
    task = getattr(request.app.state, "readiness_probe", None)
    if task is None or task.done():
        task = asyncio.create_task(run_sync_in("probe", database_ready))
        request.app.state.readiness_probe = task
    try:
        return bool(await asyncio.wait_for(asyncio.shield(task), timeout=2.5))
    except Exception:
        return False

@router.get("/health", response_model=HealthHealthResponse, response_model_exclude_unset=True)
async def health():
    return {"status": "healthy"}

@router.get("/readyz", response_model=HealthReadinessResponse, response_model_exclude_unset=True, responses={503: {'model': HealthReadinessResponse}})
async def readiness(request: Request, response: Response):
    ready = await probe_database(request)
    response.status_code = 200 if ready else 503
    response.headers['Cache-Control'] = 'no-store'
    return {"status": "ready" if ready else "unavailable"}

@router.get("/health/detail", response_model=HealthHealthDetailResponse, response_model_exclude_unset=True, responses={503: {'model': HealthHealthDetailResponse}})
async def health_detail(request: Request, response: Response):
    ready = await probe_database(request)
    response.status_code = 200 if ready else 503
    response.headers['Cache-Control'] = 'no-store'
    return {"status": "healthy" if ready else "degraded", "checks": {"database": ready, "provider_connectivity": "not_probed"}}
