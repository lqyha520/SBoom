"""按事件循环复用无凭据 HTTP 连接池；认证头只能由单次请求传入。"""

import asyncio
import weakref
from contextlib import asynccontextmanager

import httpx

_clients: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


@asynccontextmanager
async def borrow_client(kind: str, timeout: float = 30):
    clients = _clients.setdefault(asyncio.get_running_loop(), {})
    key = (kind, timeout)
    if key not in clients or clients[key].is_closed:
        clients[key] = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10, pool=5), trust_env=False,
                                        follow_redirects=False, limits=httpx.Limits(max_connections=4, max_keepalive_connections=2))
    yield clients[key]


async def close_clients() -> None:
    for client in _clients.pop(asyncio.get_running_loop(), {}).values():
        await client.aclose()
