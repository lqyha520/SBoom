"""认证路由 —— 注册 / 登录 / 登出 / 当前用户

注册始终创建普通用户；管理员由 .env 的 ADMIN_USERNAME / ADMIN_PASSWORD
在启动时创建，或由已有管理员明确授予权限。

注：REGISTRATION_ENABLED=false 可关闭注册（管理员可在后台开用户）。
"""

import logging
import re
import time

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field

from app.blocking import run_sync, run_sync_in
from app.config import get_settings
from app.deps import SESSION_COOKIE, require_user
from app.security import create_token, parse_token
from app.services import user_store
from app.services.rate_limit import allow, client_key
from app.services.user_store import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["认证"])
settings = get_settings()

_USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fa5-]{2,32}$")


def _client_ip(request: Request) -> str:
    return client_key(request.client.host) if request.client else "unknown"


class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class Registration(Credentials):
    password: str = Field(min_length=8, max_length=128)

class AuthCapabilities(BaseModel):
    registration_enabled: bool


@router.get("/capabilities", response_model=AuthCapabilities)
def capabilities(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return AuthCapabilities(registration_enabled=settings.registration_enabled)


def _set_session_cookie(response: Response, user_id: int, issued_after: int = 0, expected_hash: str | None = None) -> str:
    from app.services.workspace_sessions import create
    token = create_token(user_id, session_id=create(user_id, expected_hash=expected_hash, expected_after=issued_after), issued_after=issued_after)
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
def register(req: Registration, request: Request, response: Response):
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

    role = "user"
    try:
        user = user_store.create_user(req.username, req.password, role=role)
    except UniqueViolation:
        # 并发注册同名用户：UNIQUE 约束冲突 → 友好 409（而非 500）
        raise HTTPException(status_code=409, detail={"error": "用户名已被占用"}) from None
    _set_session_cookie(response, user.id)
    logger.info(f"新用户注册: {user.username} (id={user.id}, role={role})")
    return {"id": user.id, "username": user.username, "role": role}


@router.post("/login", summary="登录")
async def login(req: Credentials, request: Request, response: Response):
    # 防爆破：按 IP+用户名 组合限流（5 分钟内最多 10 次），也按 IP 全局限流兜底
    ip = _client_ip(request)
    if not allow(f"login-ip:{ip}", 30, 300) or not allow(f"login:{ip}:{req.username}", 10, 300):
        logger.warning(f"登录限流触发: ip={ip} username={req.username!r}")
        raise HTTPException(status_code=429, detail={"error": "尝试次数过多，请 5 分钟后再试"})
    # PBKDF2 校验是 240k 迭代的纯 CPU 操作（约 50-150ms），放线程池避免阻塞事件循环
    row = await run_sync_in("auth", user_store.authenticate, req.username, req.password)
    if row is None:
        raise HTTPException(status_code=401, detail={"error": "用户名或密码错误"})
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail={"error": "账号已被禁用，请联系管理员"})
    await run_sync(_set_session_cookie, response, row["id"], int(row["token_valid_after"] or 0), row["password_hash"])
    logger.info(f"用户登录: {row['username']} (id={row['id']}, role={row['role']})")
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


@router.post("/logout", summary="登出")
async def logout(response: Response, token: str | None = Cookie(None, alias=SESSION_COOKIE),
                 workspace_user: str | None = Header(None, alias="X-Workspace-User")):
    """删 Cookie 的同时在服务端吊销该会话：旧 Cookie 即使被复制走也不能再用。

    不走 require_user：令牌已失效/账号已禁用时也应正常清 Cookie 返回 ok。
    吊销点取 max(现在, 本令牌 iat + 1)——同一秒内签发的旧令牌也会被拒，
    而下一秒起的新登录不受影响。
    """
    payload = parse_token(token) if token else None
    if payload is not None and workspace_user is not None and workspace_user != str(payload["sub"]):
        raise HTTPException(409, detail={"error": "登录账号已变化，请刷新后继续", "code": "account_changed"})
    if payload is not None:
        if payload.get("sid"):
            from app.services.workspace_sessions import revoke
            await run_sync(revoke, payload["sid"], payload["sub"])
        else:
            not_before = max(int(time.time()), int(payload.get("iat", 0)) + 1)
            await run_sync(user_store.revoke_sessions, payload["sub"], not_before)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "ok"}


@router.get("/me", summary="当前登录用户")
async def me(user: CurrentUser = Depends(require_user)):
    return {"id": user.id, "username": user.username, "role": user.role}
