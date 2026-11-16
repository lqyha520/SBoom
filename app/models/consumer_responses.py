"""账号、会员、交易与个人数据接口的响应契约。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue


class ItemsResponse[T](BaseModel):
    items: list[T]


class PageResponse[T](ItemsResponse[T]):
    total: int
    has_more: bool


class StatusResponse(BaseModel):
    status: str


class MiniUserResponse(BaseModel):
    id: str
    username: str
    nickname: str
    avatar: str
    avatar_url: str | None
    has_password: bool
    has_wechat: bool
    membership: str
    is_vip: bool
    vip_expires_at: int | None
    referral_code: str
    membership_status: Literal['active', 'expired', 'regular']


class MiniMeResponse(MiniUserResponse):
    unread: int


class MiniLoginResponse(BaseModel):
    status: str
    token: str
    expires_at: int
    user: MiniUserResponse


class RenewalResponse(BaseModel):
    status: Literal['regular', 'active', 'expiring', 'expired', 'lifetime']
    expires_at: int | None
    renewal_due: bool
    automatic_renewal: Literal[False]
    starts_at: int | None


class MembershipPlanResponse(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    name: str
    description: str
    days: int
    price_fen: int
    is_active: bool
    sort_order: int
    revision: int
    purchase_limit: int
    virtual_product_id: str
    price_fen_ios: int
    virtual_product_id_ios: str
    created_at: int
    updated_at: int
    ios_available: bool | None = None
    purchased: int | None = None
    pending: int | None = None
    pending_order: str | None = None
    pending_expires_at: int | None = None
    renewal_due: bool | None = None
    renewal_label: str | None = None
    renewal_status: str | None = None
    projected_expires_at: int | None = None


class MembershipPlansResponse(ItemsResponse[MembershipPlanResponse]):
    model_config = ConfigDict(extra='allow')
    checkout_enabled: bool
    ios_enabled: bool
    checkout_channel: Literal['wechat', 'virtual']
    renewal: RenewalResponse | None


class RefundResponse(BaseModel):
    id: str
    reason: str
    reply: str
    status: str
    revision: int
    created_at: int
    updated_at: int
    completed_at: int | None


class OrderResponse(BaseModel):
    id: str
    plan_id: str
    plan_name: str
    plan_days: int
    amount_fen: int
    currency: str
    status: str
    payment_channel: str
    device_platform: str
    revision: int
    created_at: int
    expires_at: int
    paid_at: int | None
    closed_at: int | None
    updated_at: int
    refund: RefundResponse | None


class AdminOrderResponse(OrderResponse):
    user_id: str | None
    username: str
    nickname: str
    transaction_id: str | None
    virtual_env: int
    virtual_offer_id: str
    virtual_product_id: str
    virtual_order_id: str
    virtual_order_type: int
    delivered_at: int | None
    # 归属是下单时保存的 JSON 对象，历史来源和不同邀请方式的字段各不相同。
    referral: dict[str, JsonValue]


class OrdersSummary(BaseModel):
    orders: int
    paid_fen: int
    refunded_fen: int


class OrdersResponse[T](PageResponse[T]):
    summary: OrdersSummary


class PaymentResponse(BaseModel):
    order: OrderResponse
    payment: dict[str, str] | None


class CardCodeResponse(BaseModel):
    code: str
    days: int
    expires_at: int | None


class CardResponse(BaseModel):
    id: str
    code_hint: str
    days: int
    status: str
    redeemed_by: str | None
    redeemed_at: int | None
    created_at: int
    expires_at: int | None


class CardRedeemResponse(BaseModel):
    user: MiniUserResponse
    days: int
    vip_expires_at: int


class ReconciliationResponse(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    bill_date: str
    status: str
    error: str
    summary: dict[str, JsonValue]
    differences_complete: bool
    created_at: int
    updated_at: int


class TemplatesResponse(BaseModel):
    templates: list[dict[str, JsonValue]]


class TemplateSavedResponse(StatusResponse):
    revision: int


class TemplatesImportedResponse(StatusResponse):
    imported: int


class GenerationRequestUsage(BaseModel):
    model_calls: int
    reported_calls: int
    prompt_tokens: int
    completion_tokens: int


class GenerationStatusResponse(BaseModel):
    request_id: str
    kind: str
    status: str
    result: dict[str, JsonValue] | None
    recoverable: bool
    error: dict[str, JsonValue] | None
    error_status: int
    cache_expired: bool
    trace: dict[str, JsonValue] | None
    replay_count: int
    usage: GenerationRequestUsage
