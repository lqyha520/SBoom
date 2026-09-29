"""请求级依赖 —— 登录用户解析 / 管理员权限校验"""

import logging

from fastapi import Cookie, Depends, Header, HTTPException

from app.blocking import run_sync_in
from app.security import parse_token
from app.services.user_store import CurrentUser, get_user_by_id

logger = logging.getLogger(__name__)

SESSION_COOKIE = "lc_session"


async def require_user(token: str | None = Cookie(None, alias=SESSION_COOKIE),
                       workspace_user: str | None = Header(None, alias="X-Workspace-User")) -> CurrentUser:
    """从 httpOnly Cookie 中解析会话令牌，返回当前用户；未登录/过期抛 401。"""
    if not token:
        raise HTTPException(status_code=401, detail={"error": "请先登录"})
    payload = parse_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail={"error": "登录已过期，请重新登录"})
    user_id = payload["sub"]
    # DB 查询是同步 PG I/O，放线程池执行，避免阻塞事件循环
    user = await run_sync_in("auth", get_user_by_id, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail={"error": "账号不存在"})
    if not user.is_active:
        raise HTTPException(status_code=403, detail={"error": "账号已被禁用，请联系管理员"})
    if workspace_user is not None and workspace_user != str(user.id):
        raise HTTPException(status_code=409, detail={"error": "登录账号已变化，请刷新后继续", "code": "account_changed"})
    # 改密/重置密码后吊销旧会话：早于 token_valid_after 签发的令牌不再有效
    if user.token_valid_after and payload.get("iat", 0) < user.token_valid_after:
        raise HTTPException(status_code=401, detail={"error": "会话已失效，请重新登录"})
    if payload.get("sid"):
        from app.services.workspace_sessions import valid
        if not await run_sync_in("auth", valid, payload["sid"], user.id):
            raise HTTPException(401, detail={"error": "会话已退出或长时间未使用，请重新登录"})
    return user


async def require_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    """要求当前用户是管理员，否则 403。"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail={"error": "需要管理员权限"})
    return user


async def require_recent_admin(token: str | None = Cookie(None, alias=SESSION_COOKIE),
                               user: CurrentUser = Depends(require_admin)) -> CurrentUser:
    import time
    payload = parse_token(token) if token else None
    if not payload or time.time() - payload.get("iat", 0) > 900:
        raise HTTPException(401, detail={"code": "reauth_required", "error": "此敏感操作需要重新登录确认身份，编辑内容已保留"})
    return user
