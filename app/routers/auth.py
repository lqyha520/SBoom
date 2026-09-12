"""认证路由 —— 注册 / 登录 / 登出 / 当前用户

角色规则：数据库中尚无管理员时，新注册的第一个用户自动成为管理员；
也可以用 .env 的 ADMIN_USERNAME / ADMIN_PASSWORD 在启动时种子一个管理员。

注：REGISTRATION_ENABLED=false 可关闭注册（管理员可在后台开用户）。
"""

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import get_settings
from app.deps import SESSION_COOKIE, require_user
from app.security import create_token, hash_password, verify_password
from app.services import user_store
from app.services.rate_limit import allow
from app.services.user_store import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["认证"])
settings = get_settings()

_USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fa5-]{2,32}$")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)


def _set_session_cookie(response: Response, user_id: int) -> str:
    token = create_token(user_id)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=30 * 24 * 3600,
        httponly=True,   # 防 XSS 读取
        samesite="lax",  # 防 CSRF 跨站携带
        secure=settings.force_https,  # HTTPS 部署时仅经加密连接发送
        path="/",
    )
    return token


@router.post("/register", summary="注册新用户")
async def register(req: Credentials, request: Request, response: Response):
    if not settings.registration_enabled:
        raise HTTPException(status_code=403, detail={"error": "注册已关闭，请联系管理员开通账号"})
    if not allow(f"register:{_client_ip(request)}", 10, 3600):
        raise HTTPException(status_code=429, detail={"error": "注册过于频繁，请稍后再试"})
    if not _USERNAME_RE.match(req.username):
        raise HTTPException(
            status_code=400,
            detail={"error": "用户名需为 2-32 位字母、数字、下划线、中文"},
        )
    if user_store.get_user_by_username(req.username):
        raise HTTPException(status_code=409, detail={"error": "用户名已被占用"})

    # 首个用户自动成为管理员（此后注册的都是普通用户）
    role = "admin" if user_store.count_admins() == 0 else "user"
    try:
        user = user_store.create_user(req.username, req.password, role=role)
    except Exception:
        # 并发注册同名用户：UNIQUE 约束冲突 → 友好 409（而非 500）
        raise HTTPException(status_code=409, detail={"error": "用户名已被占用"})
    _set_session_cookie(response, user.id)
    logger.info(f"新用户注册: {user.username} (id={user.id}, role={role})")
    return {"id": user.id, "username": user.username, "role": role}


@router.post("/login", summary="登录")
async def login(req: Credentials, request: Request, response: Response):
    # 防爆破：按 IP+用户名 组合限流（5 分钟内最多 10 次），也按 IP 全局限流兜底
    ip = _client_ip(request)
    if not allow(f"login:{ip}:{req.username}", 10, 300) or not allow(f"login-ip:{ip}", 30, 300):
        logger.warning(f"登录限流触发: ip={ip} username={req.username!r}")
        raise HTTPException(status_code=429, detail={"error": "尝试次数过多，请 5 分钟后再试"})
    # PBKDF2 校验是 240k 迭代的纯 CPU 操作（约 50-150ms），放线程池避免阻塞事件循环
    row = await asyncio.to_thread(user_store.authenticate, req.username, req.password)
    if row is None:
        raise HTTPException(status_code=401, detail={"error": "用户名或密码错误"})
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail={"error": "账号已被禁用，请联系管理员"})
    _set_session_cookie(response, row["id"])
    logger.info(f"用户登录: {row['username']} (id={row['id']}, role={row['role']})")
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


@router.post("/logout", summary="登出")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "ok"}


@router.get("/me", summary="当前登录用户")
async def me(user: CurrentUser = Depends(require_user)):
    return {"id": user.id, "username": user.username, "role": user.role}
