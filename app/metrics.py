"""Bounded request labels and process-safe operational metrics."""
import inspect
import time
from contextvars import ContextVar
from functools import wraps

from prometheus_client import Counter, Gauge, Histogram
from starlette.types import ASGIApp, Receive, Scope, Send

from app.metrics_exporter import start_metrics_server as start_metrics_server

api_requests_total = Counter("api_requests_total", "Completed HTTP requests", ["method", "endpoint", "status"])
api_request_duration = Histogram("api_request_duration_seconds", "Full response duration", ["method", "endpoint"])
llm_calls_total = Counter("llm_calls_total", "Provider operations", ["model", "status"])
llm_attempts_total = Counter("llm_attempts_total", "Actual provider attempts", ["model"])
llm_request_duration = Histogram("llm_request_duration_seconds", "Provider operation duration", ["model"], buckets=(1,5,10,30,60,120,300))
llm_tokens_total = Counter("llm_tokens_total", "Reported provider tokens", ["model", "token_type"])
generation_requests_total = Counter("generation_requests_total", "Generation outcomes", ["kind", "status"])
db_pool_connections = Gauge("db_pool_connections", "Pool connections", ["state"], multiprocess_mode="livesum")
db_wait = Histogram("db_wait_seconds", "Database pool and lock wait", ["kind"])
thread_wait = Histogram("thread_wait_seconds", "Wait before synchronous work starts")
maintenance_failures = Counter("maintenance_failures_total", "Failed maintenance iterations")
app_info = Gauge("app_build_info", "Application version", ["version", "name"], multiprocess_mode="livemax")
database_busy_total = Counter("database_busy_total", "Database admission or pool timeouts")
thread_capacity = Gauge("thread_capacity", "Thread limiter usage", ["kind", "state"], multiprocess_mode="livesum")
provider_model: ContextVar[str] = ContextVar("provider_model", default="unknown")

class RequestMetrics:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started, status = time.perf_counter(), 500
        async def tracked_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
        try:
            await self.app(scope, receive, tracked_send)
        finally:
            # Never use attacker-controlled raw paths, IDs or query strings as labels.
            endpoint = getattr(scope.get("route"), "path", None) or "__static_or_unmatched__"
            method = scope["method"] if scope["method"] in {"GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS"} else "OTHER"
            api_requests_total.labels(method, endpoint, str(status)).inc()
            api_request_duration.labels(method, endpoint).observe(time.perf_counter() - started)

def observe_provider(function):
    signature = inspect.signature(function)
    def begin(args, kwargs):
        from app.config import get_settings
        bound = signature.bind_partial(*args, **kwargs).arguments
        model = (bound.get("config") or {}).get("model") or bound.get("model") or get_settings().llm_model
        return str(model)[:120]
    if inspect.isasyncgenfunction(function):
        @wraps(function)
        async def stream(*args, **kwargs):
            model, started, status = begin(args, kwargs), time.perf_counter(), "error"
            token = provider_model.set(model)
            try:
                async for item in function(*args, **kwargs):
                    yield item
                status = "success"
            finally:
                provider_model.reset(token)
                llm_calls_total.labels(model, status).inc()
                llm_request_duration.labels(model).observe(time.perf_counter() - started)
        return stream
    @wraps(function)
    async def call(*args, **kwargs):
        model, started, status = begin(args, kwargs), time.perf_counter(), "error"
        token = provider_model.set(model)
        try:
            result = await function(*args, **kwargs)
            status = "success"
            return result
        finally:
            provider_model.reset(token)
            llm_calls_total.labels(model, status).inc()
            llm_request_duration.labels(model).observe(time.perf_counter() - started)
    return call

def init_metrics(app_version: str) -> None:
    app_info.labels(app_version, "learning-coach").set(1)



def update_db_pool_metrics(active: int, idle: int) -> None:
    db_pool_connections.labels("active").set(active)
    db_pool_connections.labels("idle").set(idle)
