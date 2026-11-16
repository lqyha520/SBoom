"""referrals 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, JsonValue

from app.models.image_generation_api_responses import ImageGenerationGenerateQualityReview


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ReferralsAcquisitionResponse(ApiResponseModel):
    as_of: int
    paid: int
    registered: int
    started: int
    tracking_since: int
    visits: int


class ReferralsAddExpenseResponse(ApiResponseModel):
    active: bool
    actor_id: int
    amount_fen: int
    campaign_id: str
    category: str
    created_at: int
    evidence: str
    expense_date: str
    id: str
    included_in_baseline: bool
    note: str
    request_digest: str
    request_key: str
    revision: int
    source_ref: str


class ReferralsAdminsItemsItem(ApiResponseModel):
    id: float | int
    is_active: float | int
    username: str


class ReferralsAdminsResponse(ApiResponseModel):
    items: list[ReferralsAdminsItemsItem]


class ReferralsAuditItemsItemAfterJson(ApiResponseModel):
    admin_id: int
    admin_name: str
    bound_at: int
    source: str


class ReferralsAuditItemsItemBeforeJson(ApiResponseModel):
    source: str


class ReferralsAuditItemsItem(ApiResponseModel):
    actor_id: int
    actor_name: str
    after_json: ReferralsAuditItemsItemAfterJson
    before_json: ReferralsAuditItemsItemBeforeJson
    created_at: int
    id: int
    reason: str
    user_id: str


class ReferralsAuditResponse(ApiResponseModel):
    items: list[ReferralsAuditItemsItem]


class ReferralsBudgetResponse(ApiResponseModel):
    beneficiary: str
    budget_fen: int | None
    reached: bool
    revision: int
    reward_known: int
    unknown: int
    updated_at: int | None = None
    used_fen: int


class ReferralsCampaignsItemsItem(ApiResponseModel):
    active: bool
    admin_id: int
    admin_name: str
    budget_fen: int | None
    budget_reached: bool
    code: str
    created_at: int
    id: str
    landing_id: str
    landing_kind: str
    name: str
    path: str
    paying_users: int
    registrations: int
    revision: int
    reward_fen: int
    reward_known: int
    source: str
    spend_fen: int | None
    unknown: int
    updated_at: int


class ReferralsCampaignsResponse(ApiResponseModel):
    items: list[ReferralsCampaignsItemsItem]
    page: int
    total: int


class ReferralsCodeResponse(ApiResponseModel):
    admin_id: int
    admin_name: str
    code: str
    path: str


class ReferralsComparisonItemsItemPrevious(ApiResponseModel):
    admin_id: int
    admin_name: str
    cost_complete: bool
    cost_per_payer_fen: int | None
    id: str
    name: str
    net_fen: int
    paid_fen: int
    paying_users: int
    period: str
    refund_rate_bps: int | None
    refunded_fen: int
    source: str
    spend_fen: int


class ReferralsComparisonItemsItem(ApiResponseModel):
    admin_id: int
    admin_name: str
    cost_complete: bool
    cost_per_payer_fen: int | None
    id: str
    name: str
    net_fen: int
    paid_fen: int
    paying_users: int
    period: str
    previous: ReferralsComparisonItemsItemPrevious
    refund_rate_bps: int | None
    refunded_fen: int
    source: str
    spend_fen: int


class ReferralsComparisonResponse(ApiResponseModel):
    as_of: int
    end_date: str
    items: list[ReferralsComparisonItemsItem]
    page: int
    previous_end: str
    previous_start: str
    start_date: str
    total: int


class ReferralsCreateCampaignResponse(ApiResponseModel):
    active: bool
    admin_id: int
    budget_fen: int | None
    code: str
    created_at: int
    id: str
    landing_id: str
    landing_kind: str
    name: str
    revision: int
    source: str
    spend_fen: int | None
    updated_at: int


class ReferralsExpensesResponse(ApiResponseModel):
    admin_id: int
    baseline_fen: int | None
    cumulative_fen: int | None
    items: list[ReferralsAddExpenseResponse]
    known_cumulative_fen: int
    period_fen: int
    total: int


class ReferralsOrdersItemsItemRefund(ApiResponseModel):
    completed_at: float | int | None
    created_at: float | int
    id: str
    reason: str
    reply: str
    revision: float | int
    status: str
    updated_at: float | int


class ReferralsOrdersItemsItem(ApiResponseModel):
    amount_fen: float | int
    created_at: float | int
    currency: str
    device_platform: str | None = None
    expires_at: float | int
    id: str
    paid_at: float | int | None
    payment_channel: str | None = None
    plan_days: float | int
    plan_id: str
    plan_name: str
    refund: ReferralsOrdersItemsItemRefund | None
    revision: float | int
    status: str


class ReferralsOrdersSummary(ApiResponseModel):
    orders: int
    paid_fen: int
    refunded_fen: int


class ReferralsOrdersResponse(ApiResponseModel):
    has_more: bool
    items: list[ReferralsOrdersItemsItem]
    summary: ReferralsOrdersSummary
    total: int


class ReferralsPerformanceCampaign(ApiResponseModel):
    active: bool
    admin_id: int
    admin_name: str
    budget_fen: int | None
    budget_reached: bool
    code: str
    created_at: int
    id: str
    landing_id: str
    landing_kind: str
    name: str
    path: str
    paying_users: int
    registrations: int
    revision: int
    reward_fen: int
    reward_known: int
    source: str
    spend_fen: int | None
    unknown: int
    updated_at: int


class ReferralsPerformanceIncome(ApiResponseModel):
    after_reward_reference_fen: int
    date_basis: str
    first_paid_fen: int
    first_paying_users: int
    net_fen: int
    orders: int
    paid_fen: int
    paying_users: int
    refunded_fen: int
    registrations: int
    renewal_paid_fen: int
    reward_known: int
    reward_reference_fen: int
    reward_unknown: int


class ReferralsPerformanceTrendItem(ApiResponseModel):
    day: str
    paid_fen: int
    paying_users: int


class ReferralsPerformanceResponse(ApiResponseModel):
    campaign: ReferralsPerformanceCampaign
    income: ReferralsPerformanceIncome
    known_spend_fen: int
    remainder_fen: int | None
    return_bps: int | None
    spend_fen: int | None
    trend: list[ReferralsPerformanceTrendItem]


class ReferralsPosterQualityReview(ImageGenerationGenerateQualityReview):
    """推广海报与习题图片共用检查结果结构。"""


class ReferralsPosterResponse(ApiResponseModel):
    asset_id: str
    byte_size: int
    expires_at: int
    height: int
    mime_type: str
    prompt: str
    quality_review: ReferralsPosterQualityReview
    request_id: str
    url: str
    width: int


class ReferralsQualityItemsItem(ApiResponseModel):
    admin_name: str | None
    campaign_name: str
    collected_fen: int
    days: int
    group_key: str
    net_fen: int
    observed_users: int
    pay_rate_bps: int | None
    paying_users: int
    refunded_fen: int
    refunded_users: int
    renewal_rate_bps: int | None
    renewing_users: int
    value_per_user_fen: int | None
    waiting_users: int


class ReferralsQualityResponse(ApiResponseModel):
    as_of: int
    items: list[ReferralsQualityItemsItem]
    total: int


class ReferralsRulesChannelRates(ApiResponseModel):
    virtual_android: int
    virtual_ios: int
    wechat: int


class ReferralsRulesSharedFeesItem(ApiResponseModel):
    basis: str
    mode: str
    name: str
    rate_bps: int


class ReferralsRulesResponse(ApiResponseModel):
    beneficiary: str
    channel_rate_bps: int
    channel_rates: ReferralsRulesChannelRates
    enabled: bool
    hold_days: int
    max_reward_fen: float | int | None
    payout_days: float | int | None
    rate_bps: int
    review_days: float | int | None
    revision: int
    shared_fees: list[ReferralsRulesSharedFeesItem]


ReferralsSaveBudgetResponse = ReferralsBudgetResponse


ReferralsSummaryResponse = ReferralsPerformanceIncome


ReferralsSupplementResponse = ReferralsAuditItemsItemAfterJson


ReferralsUpdateCampaignResponse = ReferralsCreateCampaignResponse


ReferralsUpdateExpenseResponse = ReferralsAddExpenseResponse


class ReferralsUsersItemsItemReferral(ApiResponseModel):
    # 历史、自然注册、用户邀请和人工补录各自只保存适用的归属字段。
    admin_id: int | None = None
    admin_name: str | None = None
    bound_at: int | None = None
    code: str | None = None
    inviter_id: str | None = None
    inviter_name: str | None = None
    inviter_type: str | None = None
    source: str


class ReferralsUsersItemsItem(ApiResponseModel):
    created_at: int
    id: str
    last_order_at: JsonValue
    last_paid_at: JsonValue
    nickname: str
    referral: ReferralsUsersItemsItemReferral
    stage: str
    username: str


class ReferralsUsersResponse(ApiResponseModel):
    has_more: bool
    items: list[ReferralsUsersItemsItem]
    total: int
