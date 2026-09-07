"""请求级依赖 —— 登录用户解析 / 管理员权限校验"""

import logging
from typing import Optional

from fastapi import Cookie, Depends, HTTPException

from app.security import parse_token
from app.services.user_store import CurrentUser, get_user_by_id

logger = logging.getLogger(__name__)

SESSION_COOKIE = "lc_session"


async def require_user(token: Optional[str] = Cookie(None, alias=SESSION_COOKIE)) -> CurrentUser:
    """从 httpOnly Cookie 中解析会话令牌，返回当前用户；未登录/过期抛 401。"""
    if not token:
        raise HTTPException(status_code=401, detail={"error": "请先登录"})
    user_id = parse_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail={"error": "登录已过期，请重新登录"})
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail={"error": "账号不存在"})
    if not user.is_active:
        raise HTTPException(status_code=403, detail={"error": "账号已被禁用，请联系管理员"})
    return user


async def require_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    """要求当前用户是管理员，否则 403。"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail={"error": "需要管理员权限"})
    return user
