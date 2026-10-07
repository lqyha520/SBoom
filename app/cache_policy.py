"""应用自身声明缓存边界，避免代理默认缓存泄漏会话响应。"""
from starlette.datastructures import MutableHeaders


class CachePolicy:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")

        async def response(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if path.startswith("/api/"):
                    if "cache-control" not in headers:
                        headers["Cache-Control"] = "no-store"
                    vary = [v.strip() for v in headers.get("vary", "").split(",") if v.strip()]
                    for value in ("Cookie", "Authorization"):
                        if value.lower() not in {v.lower() for v in vary}:
                            vary.append(value)
                    headers["Vary"] = ", ".join(vary)
                elif "text/html" in headers.get("content-type", ""):
                    headers["Cache-Control"] = "no-cache"
                elif message["status"] == 200 and path.startswith(("/assets/", "/admin/assets/", "/static/assets/")):
                    headers["Cache-Control"] = "public, max-age=31536000, immutable"
            await send(message)

        await self.app(scope, receive, response)
