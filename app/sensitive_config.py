"""模型配置校验错误不回显请求输入，防止密钥进入前端报错或诊断日志。"""

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

_PATHS = {"/api/v1/admin/llm-config", "/api/v1/admin/image-config", "/api/v1/admin/test-llm"}


class SensitiveConfigRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                if request.url.path not in _PATHS:
                    raise
                raise HTTPException(422, detail={
                    "error": "模型配置参数无效，请检查填写内容",
                    "issues": [{"loc": error["loc"], "msg": error["msg"]} for error in exc.errors()],
                }) from None
        return guarded
