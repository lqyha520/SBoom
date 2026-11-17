"""mini 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class MiniAdminDeleteUserRemoved(ApiResponseModel):
    mini_catalog_downloads: int
    mini_catalog_favorites: int
    mini_content_requests: int
    mini_favorite_groups: int
    mini_feedback: int
    mini_membership_events: int
    mini_notice_subscriptions: int
    mini_notifications: int
    mini_recent_views: int
    mini_usage_events: int
    mini_user_avatars: int
    mini_user_sessions: int


class MiniAdminDeleteUserResponse(ApiResponseModel):
    removed: MiniAdminDeleteUserRemoved
    status: str
    username: str


class MiniAdminUpdateProfileResponse(ApiResponseModel):
    avatar: str
    avatar_url: str | None
    created_at: int
    has_password: bool
    has_wechat: bool
    id: str
    is_active: bool
    is_vip: bool
    login_method: str
    membership: str
    membership_status: str
    nickname: str
    referral_code: str
    revision: int
    updated_at: int
    username: str
    vip_expires_at: int | None


class MiniChangePasswordResponse(ApiResponseModel):
    avatar: str
    avatar_url: str | None
    has_password: bool
    has_wechat: bool
    id: str
    is_vip: bool
    membership: str
    membership_status: str
    nickname: str
    referral_code: str
    username: str
    vip_expires_at: int | None


MiniCreateUserResponse = MiniAdminUpdateProfileResponse


class MiniReferralEntryResponse(ApiResponseModel):
    destination: str
    tracked: bool
    visit_id: str


class MiniReferralStartResponse(ApiResponseModel):
    ok: bool


class MiniRefreshWechatSessionResponse(ApiResponseModel):
    refreshed: bool


MiniUpdateUserResponse = MiniAdminUpdateProfileResponse


class MiniUsersItemsItem(ApiResponseModel):
    avatar: str
    avatar_url: None | str
    created_at: int
    has_password: bool
    has_wechat: bool
    id: str
    is_active: bool
    is_vip: bool
    login_method: str
    membership: str
    membership_status: str
    nickname: str
    referral_code: str
    revision: int
    updated_at: int
    username: str
    vip_expires_at: int | None


class MiniUsersResponse(ApiResponseModel):
    has_more: bool
    items: list[MiniUsersItemsItem]
    total: int
