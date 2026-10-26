"""按事件循环复用无凭据 HTTP 连接池；认证头只能由单次请求传入。"""

import asyncio
import weakref
from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException

from app.provider_policy import PROVIDER_HEADERS, origin, pin_provider_request, validate_endpoint

_clients: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


@asynccontextmanager
async def borrow_client(kind: str, timeout: float = 30, *, base_url: str | None = None):
    if kind == "image-generation" and base_url is not None:
        validate_endpoint(base_url, resolve=False)
        allowed_origin = origin(base_url)

        async def pin_same_origin(request: httpx.Request) -> None:
            # httpcore 按固定后的 IP 复用连接，因此一个池只能服务同一个原始 TLS 来源。
            if origin(str(request.url)) != allowed_origin:
                raise HTTPException(422, detail={"code": "provider_address_rejected", "error": "生图请求不能跨服务来源"})
            await pin_provider_request(request)

        # 一个候选独占一个短生命周期连接池。轮询复用连接，切换、超时或取消都立即关闭。
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10, pool=5), trust_env=False,
                                     follow_redirects=False, headers=PROVIDER_HEADERS,
                                     limits=httpx.Limits(max_connections=1, max_keepalive_connections=1, keepalive_expiry=15),
                                     event_hooks={"request": [pin_same_origin]}) as client:
            yield client
        return
    clients = _clients.setdefault(asyncio.get_running_loop(), {})
    key = (kind, timeout)
    if key not in clients or clients[key].is_closed:
        provider = kind == "image-generation"
        # Image providers share a client. Do not reuse an IP connection across
        # different original TLS hostnames after pinning.
        clients[key] = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10, pool=5), trust_env=False,
                                        follow_redirects=False, headers=PROVIDER_HEADERS,
                                        limits=httpx.Limits(max_connections=4, max_keepalive_connections=0 if provider else 2),
                                        event_hooks={"request": [pin_provider_request]} if provider else {})
    yield clients[key]


async def close_clients() -> None:
    for client in _clients.pop(asyncio.get_running_loop(), {}).values():
        await client.aclose()
