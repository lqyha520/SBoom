"""Consumer-only login and administrator-managed memberships. No account binding."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.deps import require_admin
from app.library_deps import bearer_token, no_store, require_mini_user
from app.models.mini import AdminProfileUpdate, MembershipUpdate, MiniCredentials, MiniPasswordUpdate, MiniProfileUpdate
from app.services import mini_auth
from app.services.mini_auth import MiniUser
from app.services.rate_limit import allow
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1", tags=["小程序账号"], dependencies=[Depends(no_store)])


class CodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=256)


def _limit(request: Request, name: str, count=30, seconds=300):
    ip = request.client.host if request.client else "unknown"
    if not allow(f"mini:{name}:{ip}", count, seconds):
        mini_auth._error("操作过于频繁，请稍后再试", 429)


@router.post("/mini/login")
@router.post("/mini/login-public")
async def public_login(body: CodeInput, request: Request):
    _limit(request, "login")
    identity = await mini_auth.exchange_code(body.code)
    return await asyncio.to_thread(mini_auth.login_public_identity, identity)


@router.post("/mini/login-password")
def password_login(body: MiniCredentials, request: Request):
    _limit(request, "password")
    _limit(request, "password:" + body.username, 10)
    return mini_auth.login_password(body.username, body.password)


@router.post("/mini/register", status_code=201)
def register(body: MiniCredentials, request: Request):
    _limit(request, "register", 10, 3600)
    return mini_auth.register(body.username, body.password)


@router.get("/mini/me")
def me(user: MiniUser = Depends(require_mini_user)):
    return user.public()


@router.patch("/mini/me")
def update_me(body: MiniProfileUpdate, request: Request, user: MiniUser = Depends(require_mini_user)):
    """用户自己改昵称与头像。只能改自己的账号——目标由登录态决定，接口不接受 user_id。"""
    _limit(request, "profile:" + user.id, 40, 300)
    return mini_auth.update_profile(user.id, body)


@router.post("/mini/password")
def change_password(body: MiniPasswordUpdate, request: Request, authorization: str | None = Header(None),
                    user: MiniUser = Depends(require_mini_user)):
    """改密码；已有密码的账号必须带对当前密码，微信账号则是首次设置密码。"""
    _limit(request, "password-change:" + user.id, 10, 300)
    return mini_auth.update_password(user.id, body, bearer_token(authorization))


@router.post("/mini/logout", status_code=204)
def logout(authorization: str | None = Header(None), user: MiniUser = Depends(require_mini_user)):
    mini_auth.logout(bearer_token(authorization))
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/admin/mini-users")
def users(q: str = Query("", max_length=120), membership: Literal["", "regular", "vip"] = "",
          limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000),
          user: CurrentUser = Depends(require_admin)):
    return mini_auth.list_users(q, membership, limit, offset)


@router.post("/admin/mini-users", status_code=201)
def create_user(body: MiniCredentials, user: CurrentUser = Depends(require_admin)):
    result = mini_auth.register(body.username, body.password, admin=True)
    mini_auth.logout(result["token"])
    return mini_auth.admin_user(result["user"]["id"])


@router.put("/admin/mini-users/{user_id}")
def update_user(user_id: str, body: MembershipUpdate, user: CurrentUser = Depends(require_admin)):
    return mini_auth.update_membership(user.id, user_id, body)


@router.patch("/admin/mini-users/{user_id}")
def admin_update_profile(user_id: str, body: AdminProfileUpdate, user: CurrentUser = Depends(require_admin)):
    """管理员改小程序用户的昵称 / 头像 / 重置密码。"""
    return mini_auth.update_admin_profile(user.id, user_id, body)


@router.delete("/admin/mini-users/{user_id}")
def admin_delete_user(user_id: str, user: CurrentUser = Depends(require_admin)):
    """彻底删除小程序账号（连带会话、收藏、下载记录），不可恢复。"""
    return mini_auth.delete_user(user.id, user_id)
