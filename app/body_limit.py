"""在读取请求体时执行全局限额；文件上传由各接口执行独立限额。"""

import re

from fastapi import HTTPException
from starlette.responses import JSONResponse

# 仅精确放行具有流式限额读取器的接口，不能按整个业务前缀豁免。
UPLOAD_ROUTES = (
    ("POST", re.compile(r"/api/v1/library/papers/?")),
    ("PUT", re.compile(r"/api/v1/library/papers/[^/]+/files/?")),
    ("POST", re.compile(r"/api/v1/admin/catalog/import/?")),
    ("POST", re.compile(r"/api/v1/admin/catalog/papers/[^/]+/editions/import/?")),
    ("PUT", re.compile(r"/api/v1/admin/site/banners/[^/]+/image/?")),
    ("POST", re.compile(r"/api/v1/mini/me/avatar/?")),
    ("POST", re.compile(r"/api/v1/payments/wechat/(?:notify|refund-notify)/?")),
)


def has_upload_limit(method: str, path: str) -> bool:
    return any(method == verb and pattern.fullmatch(path) is not None for verb, pattern in UPLOAD_ROUTES)


class BodySizeLimit:
    """声明长度提前检查，实际字节数在 receive 阶段累计，不缓冲整份请求。"""

    def __init__(self, app, limit: int):
        self.app = app
        self.limit = int(limit)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or has_upload_limit(scope.get("method", ""), scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        detail = {"error": "请求体过大", "code": "payload_too_large", "limit_bytes": self.limit}
        for name, value in scope.get("headers", ()):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = -1
                if declared < 0:
                    await JSONResponse({"detail": {"error": "无效的请求长度"}}, status_code=400)(scope, receive, send)
                    return
                if declared > self.limit:
                    await JSONResponse({"detail": detail}, status_code=413)(scope, receive, send)
                    return

        received = 0
        exceeded = False
        started = False

        async def limited_receive():
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    exceeded = True
                    # FastAPI 在解析 JSON 阶段识别 HTTPException，保留 413 而非转换为 400。
                    raise HTTPException(413, detail=detail)
            return message

        async def track_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, track_send)
        except HTTPException:
            if not exceeded or started:
                raise
            # 也支持不提供 HTTPException 处理器的下游 ASGI 应用。
            await JSONResponse({"detail": detail}, status_code=413)(scope, receive, send)
