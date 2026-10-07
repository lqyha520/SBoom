"""请求追踪、安全响应头与 Cookie 跨站写入保护。"""

import logging
import re
import time
import uuid
from contextvars import ContextVar
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from app.config import get_settings

request_id: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("app.access")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


class RequestContext:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        supplied = headers.get("x-correlation-id", "")
        identifier = supplied if re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", supplied) else uuid.uuid4().hex
        token = request_id.set(identifier)
        started, status = time.monotonic(), 500

        async def wrapped_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                out = MutableHeaders(scope=message)
                out["X-Correlation-ID"] = identifier
                out.setdefault("X-Content-Type-Options", "nosniff")
                out.setdefault("X-Frame-Options", "DENY")
                out.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                out.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
                out.setdefault("Content-Security-Policy-Report-Only", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self'")
                if get_settings().force_https:
                    out.setdefault("Strict-Transport-Security", "max-age=31536000")
            await send(message)

        try:
            if (scope["method"] not in ("GET", "HEAD", "OPTIONS") and "lc_session=" in headers.get("cookie", "")):
                origin = headers.get("origin")
                allowed = {value.strip().rstrip("/") for value in get_settings().cors_origins.split(",") if value.strip()}
                same_origin = not origin or (urlsplit(origin).netloc == headers.get("host") and urlsplit(origin).scheme == scope.get("scheme"))
                if headers.get("sec-fetch-site") == "cross-site" and origin not in allowed or not same_origin and origin not in allowed:
                    return await JSONResponse({"detail": {"error": "跨站请求已拒绝", "code": "csrf_rejected"}}, status_code=403,
                                              headers={"Cache-Control": "no-store"})(scope, receive, wrapped_send)
            await self.app(scope, receive, wrapped_send)
        finally:
            route = scope.get("route")
            logger.info("request", extra={"method": scope["method"], "route": getattr(route, "path", "unmatched"),
                                          "status": status, "duration_ms": round((time.monotonic() - started) * 1000, 2)})
            request_id.reset(token)
