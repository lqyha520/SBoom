"""Workbench cookies and consumer bearer sessions use disjoint account domains."""

import asyncio
from typing import Optional

from fastapi import Cookie, Header, HTTPException, Response

from app.deps import SESSION_COOKIE, require_user
from app.services.mini_auth import resolve_session


def no_store(response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail={"error": "请先登录"})
    return authorization[7:]


async def require_library_user(
    token: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
    authorization: Optional[str] = Header(None),
    workspace_user: Optional[str] = Header(None, alias="X-Workspace-User"),
):
    if authorization is not None:
        raise HTTPException(403, detail={"error": "小程序账号不可访问出题工作台的私人资料"})
    return await require_user(token=token, workspace_user=workspace_user)


async def require_mini_user(authorization: Optional[str] = Header(None),
                            mini_user: Optional[str] = Header(None, alias="X-Mini-User")):
    user = await asyncio.to_thread(resolve_session, bearer_token(authorization))
    if mini_user is not None and mini_user != user.id:
        raise HTTPException(409, detail={"error": "登录账号已变化，请重新登录", "code": "account_changed"})
    return user
