"""在读取期间执行限额，拒绝过大的请求或供应商响应。"""

from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException, Request


async def limited_body(request: Request, limit: int, *, error: str = "请求过大") -> bytes:
    try:
        declared = int(request.headers.get("content-length", "0"))
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "无效的请求长度"}) from exc
    if declared < 0 or declared > limit:
        raise HTTPException(413, detail={"error": error})
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > limit:
            raise HTTPException(413, detail={"error": error})
        content.extend(chunk)
    return bytes(content)


async def limited_lines(response: httpx.Response, limit: int) -> AsyncIterator[str]:
    pending = bytearray()
    total = 0
    async for chunk in response.aiter_bytes(chunk_size=65536):
        total += len(chunk)
        if total > limit:
            raise HTTPException(502, detail={"code": "provider_response_too_large", "error": "模型响应超过安全上限"})
        pending.extend(chunk)
        while b"\n" in pending:
            line, _, pending = pending.partition(b"\n")
            yield line.decode("utf-8", errors="replace").rstrip("\r")
    if pending:
        yield pending.decode("utf-8", errors="replace").rstrip("\r")
