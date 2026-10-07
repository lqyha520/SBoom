"""按事件循环复用无凭据 HTTP 连接池；认证头只能由单次请求传入。"""

import asyncio
import weakref
from contextlib import asynccontextmanager

import httpx

from app.provider_policy import pin_provider_request

_clients: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


@asynccontextmanager
async def borrow_client(kind: str, timeout: float = 30):
    clients = _clients.setdefault(asyncio.get_running_loop(), {})
    key = (kind, timeout)
    if key not in clients or clients[key].is_closed:
        provider = kind == "image-generation"
        # Image providers share a client. Do not reuse an IP connection across
        # different original TLS hostnames after pinning.
        clients[key] = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10, pool=5), trust_env=False,
                                        follow_redirects=False, limits=httpx.Limits(max_connections=4, max_keepalive_connections=0 if provider else 2),
                                        event_hooks={"request": [pin_provider_request]} if provider else {})
    yield clients[key]


async def close_clients() -> None:
    for client in _clients.pop(asyncio.get_running_loop(), {}).values():
        await client.aclose()
