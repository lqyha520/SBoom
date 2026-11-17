"""settlements 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, JsonValue


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class SettlementsAdjustmentResponse(ApiResponseModel):
    amount_fen: int
    beneficiary: str
    beneficiary_name: str
    created_at: int
    evidence: str
    id: int
    reason: str
    source: str
    statement_id: str | None


class SettlementsAdminsItemsItem(ApiResponseModel):
    id: int
    username: str


class SettlementsAdminsResponse(ApiResponseModel):
    items: list[SettlementsAdminsItemsItem]


class SettlementsApplyRequestSnapshotAdjustmentsItem(ApiResponseModel):
    amount_fen: float | int
    beneficiary: str
    beneficiary_name: str
    evidence: str
    id: float | int
    reason: str
    source: str
    statement_id: None | str


class SettlementsApplyRequestSnapshotChannelsItem(ApiResponseModel):
    amount_fen: float | int
    channel_fen: float | int | None
    commission_fen: float | int | None
    key: str
    label: str
    orders: float | int
    shared_fen: float | int | None
    unknown_rates: float | int


class SettlementsApplyRequestSnapshotExcludedItem(ApiResponseModel):
    available_at: float | int
    order_id: str
    reason: str


class SettlementsApplyRequestSnapshotItemsItemCostsSharedFeesItem(ApiResponseModel):
    amount_fen: float | int | None = None
    base_fen: float | int | None = None
    basis: str | None = None
    mode: str | None = None
    name: str
    rate_bps: float | int | None = None
    source_ref: str | None = None


class SettlementsApplyRequestSnapshotItemsItemCosts(ApiResponseModel):
    bill_row_id: float | int | None = None
    channel_base_fen: float | int | None = None
    channel_fee_fen: float | int
    channel_rate_bps: float | int | None = None
    channel_rounding: str | None = None
    confirmed: bool
    evidence: str
    shared_fees: list[SettlementsApplyRequestSnapshotItemsItemCostsSharedFeesItem]


class SettlementsApplyRequestSnapshotItemsItemPolicyChannelRates(ApiResponseModel):
    virtual_android: float | int
    virtual_ios: float | int
    wechat: float | int


class SettlementsApplyRequestSnapshotItemsItemPolicy(ApiResponseModel):
    beneficiary: str
    channel_rate_bps: float | int | None = None
    channel_rate_key: str | None = None
    channel_rates: SettlementsApplyRequestSnapshotItemsItemPolicyChannelRates | None = None
    enabled: bool
    hold_days: float | int
    max_reward_fen: float | int | None = None
    payout_days: float | int | None = None
    rate_bps: float | int
    review_days: float | int | None = None
    revision: float | int
    shared_fees: list[SettlementsApplyRequestSnapshotItemsItemCostsSharedFeesItem]


class SettlementsApplyRequestSnapshotItemsItem(ApiResponseModel):
    amount_fen: float | int
    costs: SettlementsApplyRequestSnapshotItemsItemCosts | None
    device_platform: str | None = None
    order_id: str
    paid_at: int | None = None
    payment_channel: str | None = None
    policy: SettlementsApplyRequestSnapshotItemsItemPolicy
    reference_channel_fen: float | int | None
    reference_channel_rate_bps: float | int | None = None
    reference_commission_fen: float | int | None
    reference_fees: list[SettlementsApplyRequestSnapshotItemsItemCostsSharedFeesItem]
    revision: float | int


class SettlementsApplyRequestSnapshotRecoveryExcludedItem(ApiResponseModel):
    order_id: str
    reason: str


class SettlementsApplyRequestSnapshotServiceTerms(ApiResponseModel):
    payout_days: float | int | None = None
    review_days: float | int | None = None


class SettlementsApplyRequestSnapshot(ApiResponseModel):
    adjustment_fen: float | int
    adjustments: list[SettlementsApplyRequestSnapshotAdjustmentsItem]
    all_eligible: bool | None = None
    channels: list[SettlementsApplyRequestSnapshotChannelsItem] | None = None
    excluded: list[SettlementsApplyRequestSnapshotExcludedItem] | None = None
    items: list[SettlementsApplyRequestSnapshotItemsItem]
    known_reference_gross_fen: float | int | None = None
    net_fen: float | int | None
    personal_fen: float | int | None
    recovery_excluded: list[SettlementsApplyRequestSnapshotRecoveryExcludedItem] | None = None
    reference_after_adjustment_fen: float | int | None
    reference_gross_fen: float | int | None
    service_terms: SettlementsApplyRequestSnapshotServiceTerms | None = None
    source_request_id: str | None = None
    tax_fen: float | int | None
    unconfirmed_orders: float | int
    unknown_orders: float | int | None = None


class SettlementsApplyRequestStatementSummary(ApiResponseModel):
    approved_at: float | int | None = None
    gross_fen: float | int
    id: str
    net_fen: float | int | None
    personal_fen: float | int
    receipt: str
    status: str
    tax_fen: float | int | None


class SettlementsApplyRequestResponse(ApiResponseModel):
    beneficiary: str
    beneficiary_name: str
    confirmed_orders: float | int | None = None
    created_at: float | int
    id: str
    note: str
    quote_digest: str
    reason: str
    request_key: str
    revision: float | int
    snapshot: SettlementsApplyRequestSnapshot
    statement_id: None | str
    statement_summary: SettlementsApplyRequestStatementSummary | None = None
    status: str
    updated_at: float | int


class SettlementsApproveReviewPersonalFeesItem(ApiResponseModel):
    amount_fen: int
    base_fen: int
    basis: str
    mode: str
    name: str
    rate_bps: int


class SettlementsApproveReview(ApiResponseModel):
    confirmed: bool
    confirmed_at: int
    confirmed_by: int
    difference_reason: str
    evidence: str
    personal_fees: list[SettlementsApproveReviewPersonalFeesItem]
    tax_fen: int


class SettlementsApproveSnapshotAdjustmentsItem(ApiResponseModel):
    amount_fen: float | int
    beneficiary: str
    beneficiary_name: str
    evidence: str
    id: float | int
    reason: str
    source: str
    statement_id: None | str


class SettlementsApproveSnapshotChannelsItem(ApiResponseModel):
    amount_fen: int
    channel_fen: int
    commission_fen: int
    key: str
    label: str
    orders: int
    shared_fen: int
    unknown_rates: int


class SettlementsApproveSnapshotItemsItemCostsSharedFeesItem(ApiResponseModel):
    amount_fen: int
    basis: str
    mode: str
    name: str


class SettlementsApproveSnapshotItemsItemCosts(ApiResponseModel):
    channel_fee_fen: int
    confirmed: bool
    confirmed_at: int
    confirmed_by: int
    evidence: str
    shared_fees: list[SettlementsApproveSnapshotItemsItemCostsSharedFeesItem]


class SettlementsApproveSnapshotItemsItemPolicySharedFeesItem(ApiResponseModel):
    basis: str
    mode: str
    name: str
    rate_bps: int


class SettlementsApproveSnapshotItemsItemPolicy(ApiResponseModel):
    beneficiary: str
    channel_rate_bps: float | int | None
    channel_rate_key: str
    channel_rates: JsonValue
    enabled: bool
    hold_days: int
    max_reward_fen: float | int | None
    payout_days: float | int | None
    rate_bps: int
    review_days: float | int | None
    revision: int
    shared_fees: list[SettlementsApproveSnapshotItemsItemPolicySharedFeesItem]


class SettlementsApproveSnapshotItemsItem(ApiResponseModel):
    amount_fen: int
    commission_fen: int
    costs: SettlementsApproveSnapshotItemsItemCosts
    device_platform: str
    order_id: str
    paid_at: int
    payment_channel: str
    policy: SettlementsApproveSnapshotItemsItemPolicy


class SettlementsApproveSnapshotPayee(ApiResponseModel):
    account: str
    bank: str
    method: str
    name: str
    revision: int


class SettlementsApproveSnapshotServiceTerms(ApiResponseModel):
    payout_days: float | int | None
    review_days: float | int | None


class SettlementsApproveSnapshot(ApiResponseModel):
    adjustments: list[SettlementsApproveSnapshotAdjustmentsItem]
    channels: list[SettlementsApproveSnapshotChannelsItem]
    items: list[SettlementsApproveSnapshotItemsItem]
    payee: SettlementsApproveSnapshotPayee
    service_terms: SettlementsApproveSnapshotServiceTerms


class SettlementsApproveResponse(ApiResponseModel):
    adjustment_fen: int
    approved_at: int
    beneficiary: str
    beneficiary_name: str
    created_at: int
    gross_fen: int
    id: str
    net_fen: int
    paid_at: float | int | None
    payout: dict[str, JsonValue]
    personal_fen: int
    reason: str
    receipt: str
    review: SettlementsApproveReview
    revision: int
    snapshot: SettlementsApproveSnapshot
    status: str
    tax_fen: int
    updated_at: int


class SettlementsAttachPayeeReview(ApiResponseModel):
    confirmed: bool
    confirmed_at: int
    confirmed_by: int
    difference_reason: str
    evidence: str
    personal_fees: list[SettlementsApproveSnapshotItemsItemCostsSharedFeesItem]
    tax_fen: int


class SettlementsAttachPayeeSnapshotItemsItemPolicy(ApiResponseModel):
    beneficiary: str
    channel_rate_bps: int
    channel_rate_key: str
    channel_rates: JsonValue
    enabled: bool
    hold_days: int
    max_reward_fen: float | int | None
    payout_days: float | int | None
    rate_bps: int
    review_days: float | int | None
    revision: int
    shared_fees: list[SettlementsApproveSnapshotItemsItemPolicySharedFeesItem]


class SettlementsAttachPayeeSnapshotItemsItem(ApiResponseModel):
    amount_fen: int
    commission_fen: int
    costs: SettlementsApproveSnapshotItemsItemCosts
    device_platform: str
    order_id: str
    paid_at: int
    payment_channel: str
    policy: SettlementsAttachPayeeSnapshotItemsItemPolicy


class SettlementsAttachPayeeSnapshot(ApiResponseModel):
    adjustments: list[SettlementsApproveSnapshotAdjustmentsItem]
    channels: list[SettlementsApproveSnapshotChannelsItem]
    items: list[SettlementsAttachPayeeSnapshotItemsItem]
    payee: SettlementsApproveSnapshotPayee
    service_terms: SettlementsApproveSnapshotServiceTerms


class SettlementsAttachPayeeResponse(ApiResponseModel):
    adjustment_fen: int
    approved_at: int
    beneficiary: str
    beneficiary_name: str
    created_at: int
    gross_fen: int
    id: str
    net_fen: int
    paid_at: float | int | None
    payout: dict[str, JsonValue]
    personal_fen: int
    reason: str
    receipt: str
    review: SettlementsAttachPayeeReview
    revision: int
    snapshot: SettlementsAttachPayeeSnapshot
    status: str
    tax_fen: int
    updated_at: int


SettlementsBatchCostsResponse = SettlementsApplyRequestResponse


class SettlementsBillDetailItemsItemCheckWechatReconciliation(ApiResponseModel):
    differences: list[str]
    id: str


class SettlementsBillDetailItemsItemCheck(ApiResponseModel):
    bill_row_id: float | int | None
    can_adopt: bool
    channel_fee_fen: float | int | None
    confirmed_fee_fen: float | int | None
    differences: list[str]
    fee_difference: bool
    order_id: str
    wechat_reconciliation: SettlementsBillDetailItemsItemCheckWechatReconciliation | None


class SettlementsBillDetailItemsItem(ApiResponseModel):
    amount_fen: float | int
    channel_fee_fen: float | int
    channel_label: str
    check: SettlementsBillDetailItemsItemCheck | None
    id: float | int
    order_id: str
    refunded_fen: float | int


class SettlementsBillDetailResponse(ApiResponseModel):
    items: list[SettlementsBillDetailItemsItem]


class SettlementsBillsItemsItem(ApiResponseModel):
    created_at: float | int
    evidence: str
    id: str
    name: str
    orders: float | int


class SettlementsBillsResponse(ApiResponseModel):
    items: list[SettlementsBillsItemsItem]


SettlementsCancelRequestResponse = SettlementsApplyRequestResponse


class SettlementsCostsCosts(ApiResponseModel):
    channel_base_fen: int
    channel_fee_fen: int
    channel_rate_bps: int
    channel_rounding: str
    confirmed: bool
    confirmed_at: int
    confirmed_by: int
    evidence: str
    shared_fees: list[SettlementsApplyRequestSnapshotItemsItemCostsSharedFeesItem]


class SettlementsCostsResponse(ApiResponseModel):
    beneficiary: str
    beneficiary_name: str
    buyer: str
    commission_fen: int
    costs: SettlementsCostsCosts
    created_at: int
    order_id: str
    policy: SettlementsApproveSnapshotItemsItemPolicy
    reason: str
    request_id: str | None
    revision: int
    statement_id: str | None
    status: str


class SettlementsCreateSnapshotItemsItemCostsSharedFeesItem(ApiResponseModel):
    amount_fen: int
    base_fen: int | None = None
    basis: str
    mode: str
    name: str
    rate_bps: int | None = None
    source_ref: str | None = None


class SettlementsCreateSnapshotItemsItemCosts(ApiResponseModel):
    bill_row_id: int | None = None
    channel_base_fen: int | None = None
    channel_fee_fen: int
    channel_rate_bps: int | None = None
    channel_rounding: str | None = None
    confirmed: bool
    confirmed_at: int
    confirmed_by: int
    evidence: str
    shared_fees: list[SettlementsCreateSnapshotItemsItemCostsSharedFeesItem]


class SettlementsCreateSnapshotItemsItemPolicyChannelRates(ApiResponseModel):
    virtual_android: int
    virtual_ios: int
    wechat: int


class SettlementsCreateSnapshotItemsItemPolicySharedFeesItem(ApiResponseModel):
    amount_fen: int | None = None
    basis: str
    mode: str
    name: str
    rate_bps: int | None = None


class SettlementsCreateSnapshotItemsItemPolicy(ApiResponseModel):
    beneficiary: str
    channel_rate_bps: int | None
    channel_rate_key: str
    channel_rates: SettlementsCreateSnapshotItemsItemPolicyChannelRates | None
    enabled: bool
    hold_days: int
    max_reward_fen: float | int | None
    payout_days: int | None
    rate_bps: int
    review_days: int | None
    revision: int
    shared_fees: list[SettlementsCreateSnapshotItemsItemPolicySharedFeesItem]


class SettlementsCreateSnapshotItemsItem(ApiResponseModel):
    amount_fen: int
    commission_fen: int
    costs: SettlementsCreateSnapshotItemsItemCosts
    device_platform: str
    order_id: str
    paid_at: int
    payment_channel: str
    policy: SettlementsCreateSnapshotItemsItemPolicy


class SettlementsCreateSnapshotServiceTerms(ApiResponseModel):
    payout_days: int | None
    review_days: int | None


class SettlementsCreateSnapshot(ApiResponseModel):
    adjustments: list[SettlementsAdjustmentResponse]
    channels: list[SettlementsApproveSnapshotChannelsItem]
    items: list[SettlementsCreateSnapshotItemsItem]
    payee: SettlementsApproveSnapshotPayee | None = None
    service_terms: SettlementsCreateSnapshotServiceTerms


class SettlementsCreateResponse(ApiResponseModel):
    adjustment_fen: int
    approved_at: float | int | None
    beneficiary: str
    beneficiary_name: str
    created_at: int
    gross_fen: int
    id: str
    net_fen: float | int | None
    paid_at: float | int | None
    payout: dict[str, JsonValue]
    personal_fen: int
    reason: str
    receipt: str
    review: JsonValue
    revision: int
    snapshot: SettlementsCreateSnapshot
    status: str
    tax_fen: float | int | None
    updated_at: int


class SettlementsImportBillResponse(ApiResponseModel):
    duplicate: bool
    id: str
    orders: int


class SettlementsNoticesItemsItem(ApiResponseModel):
    created_at: float | int
    id: float | int
    kind: str
    target: str


class SettlementsNoticesResponse(ApiResponseModel):
    items: list[SettlementsNoticesItemsItem]
    last_id: float | int
    unread: float | int


class SettlementsPaidPayout(ApiResponseModel):
    payee: SettlementsApproveSnapshotPayee | None
    registered_at: int
    transferred_at: int | None


class SettlementsPaidReviewPersonalFeesItem(ApiResponseModel):
    amount_fen: int
    base_fen: int | None = None
    basis: str
    mode: str
    name: str
    rate_bps: int | None = None


class SettlementsPaidReview(ApiResponseModel):
    confirmed: bool
    confirmed_at: int
    confirmed_by: int
    difference_reason: str
    evidence: str
    personal_fees: list[SettlementsPaidReviewPersonalFeesItem]
    tax_fen: int


class SettlementsPaidSnapshotItemsItemCosts(ApiResponseModel):
    channel_base_fen: int | None = None
    channel_fee_fen: int
    channel_rate_bps: int | None = None
    channel_rounding: str | None = None
    confirmed: bool
    confirmed_at: int
    confirmed_by: int
    evidence: str
    shared_fees: list[SettlementsCreateSnapshotItemsItemCostsSharedFeesItem]


class SettlementsPaidSnapshotItemsItemPolicy(ApiResponseModel):
    beneficiary: str
    channel_rate_bps: int | None
    channel_rate_key: str
    channel_rates: SettlementsCreateSnapshotItemsItemPolicyChannelRates | None
    enabled: bool
    hold_days: int
    max_reward_fen: float | int | None
    payout_days: float | int | None
    rate_bps: int
    review_days: float | int | None
    revision: int
    shared_fees: list[SettlementsCreateSnapshotItemsItemPolicySharedFeesItem]


class SettlementsPaidSnapshotItemsItem(ApiResponseModel):
    amount_fen: int
    commission_fen: int
    costs: SettlementsPaidSnapshotItemsItemCosts
    device_platform: str
    order_id: str
    paid_at: int
    payment_channel: str
    policy: SettlementsPaidSnapshotItemsItemPolicy


class SettlementsPaidSnapshot(ApiResponseModel):
    adjustments: list[SettlementsAdjustmentResponse]
    channels: list[SettlementsApproveSnapshotChannelsItem]
    items: list[SettlementsPaidSnapshotItemsItem]
    payee: SettlementsApproveSnapshotPayee | None = None
    service_terms: SettlementsApproveSnapshotServiceTerms


class SettlementsPaidResponse(ApiResponseModel):
    adjustment_fen: int
    approved_at: int
    beneficiary: str
    beneficiary_name: str
    created_at: int
    gross_fen: int
    id: str
    net_fen: int
    paid_at: int
    payout: SettlementsPaidPayout
    personal_fen: int
    reason: str
    receipt: str
    review: SettlementsPaidReview
    revision: int
    snapshot: SettlementsPaidSnapshot
    status: str
    tax_fen: int
    updated_at: int


SettlementsPayeeResponse = SettlementsApproveSnapshotPayee | None


class SettlementsPolicyResponse(ApiResponseModel):
    beneficiary: str
    channel_rate_bps: int | None
    channel_rates: SettlementsCreateSnapshotItemsItemPolicyChannelRates | None
    enabled: bool
    hold_days: int
    max_reward_fen: int | None = None
    payout_days: int | None = None
    rate_bps: int
    review_days: int | None = None
    revision: int
    shared_fees: list[SettlementsCreateSnapshotItemsItemPolicySharedFeesItem]


class SettlementsPreviewRecoveryResponse(ApiResponseModel):
    excluded: list[SettlementsApplyRequestSnapshotRecoveryExcludedItem]
    order_ids: list[str]
    revision: int


class SettlementsPreviewRequestResponse(ApiResponseModel):
    quote_digest: str
    snapshot: SettlementsApplyRequestSnapshot


class SettlementsReadNoticesResponse(ApiResponseModel):
    ok: bool


class SettlementsRecoverSnapshotItemsItemCosts(ApiResponseModel):
    bill_row_id: float | int | None = None
    channel_base_fen: float | int | None = None
    channel_fee_fen: float | int
    channel_rate_bps: float | int | None = None
    channel_rounding: str | None = None
    confirmed: bool
    confirmed_at: int | None = None
    confirmed_by: int | None = None
    evidence: str
    shared_fees: list[SettlementsApplyRequestSnapshotItemsItemCostsSharedFeesItem]


class SettlementsRecoverSnapshotItemsItem(ApiResponseModel):
    amount_fen: float | int
    costs: SettlementsRecoverSnapshotItemsItemCosts | None
    device_platform: str | None = None
    order_id: str
    paid_at: int | None = None
    payment_channel: str | None = None
    policy: SettlementsApplyRequestSnapshotItemsItemPolicy
    reference_channel_fen: float | int | None
    reference_channel_rate_bps: float | int | None = None
    reference_commission_fen: float | int | None
    reference_fees: list[SettlementsApplyRequestSnapshotItemsItemCostsSharedFeesItem]
    revision: float | int


class SettlementsRecoverSnapshot(ApiResponseModel):
    adjustment_fen: float | int
    adjustments: list[SettlementsApplyRequestSnapshotAdjustmentsItem]
    all_eligible: bool | None = None
    channels: list[SettlementsApplyRequestSnapshotChannelsItem] | None = None
    excluded: list[SettlementsApplyRequestSnapshotExcludedItem] | None = None
    items: list[SettlementsRecoverSnapshotItemsItem]
    known_reference_gross_fen: float | int | None = None
    net_fen: float | int | None
    personal_fen: float | int | None
    recovery_excluded: list[SettlementsApplyRequestSnapshotRecoveryExcludedItem] | None = None
    reference_after_adjustment_fen: float | int | None
    reference_gross_fen: float | int | None
    service_terms: SettlementsApplyRequestSnapshotServiceTerms | None = None
    source_request_id: str | None = None
    tax_fen: float | int | None
    unconfirmed_orders: float | int
    unknown_orders: float | int | None = None


class SettlementsRecoverResponse(ApiResponseModel):
    beneficiary: str
    beneficiary_name: str
    confirmed_orders: float | int | None = None
    created_at: float | int
    id: str
    note: str
    quote_digest: str
    reason: str
    request_key: str
    revision: float | int
    snapshot: SettlementsRecoverSnapshot
    statement_id: None | str
    statement_summary: SettlementsApplyRequestStatementSummary | None = None
    status: str
    updated_at: float | int


SettlementsRejectRequestResponse = SettlementsApplyRequestResponse


class SettlementsRequestDetailAttachmentsItem(ApiResponseModel):
    created_at: float | int
    id: str
    media_type: str
    name: str


class SettlementsRequestDetailDifferenceItemsItemFeesItem(ApiResponseModel):
    after_fen: float | int | None
    before_fen: float | int | None
    name: str


class SettlementsRequestDetailDifferenceItemsItem(ApiResponseModel):
    after_fen: float | int | None
    before_fen: float | int | None
    channel_after_fen: float | int | None
    channel_before_fen: float | int | None
    fees: list[SettlementsRequestDetailDifferenceItemsItemFeesItem]
    order_id: str


class SettlementsRequestDetailDifference(ApiResponseModel):
    actual_gross_fen: float | int | None
    adjustment_after_fen: float | int | None
    adjustment_before_fen: float | int
    items: list[SettlementsRequestDetailDifferenceItemsItem]
    reason: str
    reference_gross_fen: float | int | None


class SettlementsRequestDetailRewardsItemEligibilityIssue(ApiResponseModel):
    code: str
    order_id: str
    reason: str


class SettlementsRequestDetailRewardsItem(ApiResponseModel):
    amount_fen: float | int
    application_state: str | None = None
    available_at: float | int
    beneficiary: str
    beneficiary_name: str
    commission_fen: float | int | None
    costs: SettlementsApplyRequestSnapshotItemsItemCosts | None
    created_at: int | None = None
    device_platform: str
    eligibility_issue: SettlementsRequestDetailRewardsItemEligibilityIssue | None = None
    order_id: str
    order_status: str | None = None
    paid_at: float | int
    payment_channel: str
    policy: SettlementsApplyRequestSnapshotItemsItemPolicy
    reason: str
    refund_status: None | str
    request_id: None | str = None
    revision: float | int
    statement_id: None | str
    status: str


class SettlementsRequestDetailStatementPayout(ApiResponseModel):
    registered_at: float | int | None = None
    transferred_at: float | int | None = None


class SettlementsRequestDetailStatementReview(ApiResponseModel):
    difference_reason: str | None = None
    evidence: str
    personal_fees: list[SettlementsApplyRequestSnapshotItemsItemCostsSharedFeesItem]
    tax_fen: float | int


class SettlementsRequestDetailStatementSnapshotItemsItemPolicy(ApiResponseModel):
    beneficiary: str
    channel_rate_bps: float | int | None = None
    channel_rates: SettlementsApplyRequestSnapshotItemsItemPolicyChannelRates | None = None
    enabled: bool
    hold_days: float | int
    max_reward_fen: float | int | None = None
    payout_days: float | int | None = None
    rate_bps: float | int
    review_days: float | int | None = None
    revision: float | int
    shared_fees: list[SettlementsApplyRequestSnapshotItemsItemCostsSharedFeesItem]


class SettlementsRequestDetailStatementSnapshotItemsItem(ApiResponseModel):
    amount_fen: float | int
    commission_fen: float | int
    costs: SettlementsApplyRequestSnapshotItemsItemCosts
    device_platform: str | None = None
    order_id: str
    payment_channel: str | None = None
    policy: SettlementsRequestDetailStatementSnapshotItemsItemPolicy


class SettlementsRequestDetailStatementSnapshotPayee(ApiResponseModel):
    account: str
    bank: str
    method: str
    name: str
    revision: float | int


class SettlementsRequestDetailStatementSnapshot(ApiResponseModel):
    adjustments: list[SettlementsApplyRequestSnapshotAdjustmentsItem]
    channels: list[SettlementsApplyRequestSnapshotChannelsItem] | None = None
    items: list[SettlementsRequestDetailStatementSnapshotItemsItem]
    payee: SettlementsRequestDetailStatementSnapshotPayee | None = None
    service_terms: SettlementsApplyRequestSnapshotServiceTerms | None = None


class SettlementsRequestDetailStatement(ApiResponseModel):
    adjustment_fen: float | int
    approved_at: float | int | None = None
    beneficiary: str
    beneficiary_name: str
    created_at: float | int
    gross_fen: float | int
    id: str
    net_fen: float | int | None
    paid_at: float | int | None = None
    payout: SettlementsRequestDetailStatementPayout | None = None
    personal_fen: float | int
    reason: str
    receipt: str
    review: SettlementsRequestDetailStatementReview | None
    revision: float | int
    snapshot: SettlementsRequestDetailStatementSnapshot
    status: str
    tax_fen: float | int | None


class SettlementsRequestDetailTimelineItemValue(ApiResponseModel):
    all_eligible: bool | None = None
    beneficiary: str | None = None
    difference_reason: str | None = None
    evidence: str | None = None
    name: str | None = None
    new_request_id: str | None = None
    order_ids: list[str] | None = None
    policy: SettlementsApplyRequestSnapshotItemsItemPolicy | None = None
    quote_digest: str | None = None
    reason: str | None = None
    source_request_id: str | None = None


class SettlementsRequestDetailTimelineItem(ApiResponseModel):
    actor_name: None | str = None
    created_at: float | int
    id: float | int
    kind: str
    target: str
    value: SettlementsRequestDetailTimelineItemValue


class SettlementsRequestDetailResponse(ApiResponseModel):
    attachments: list[SettlementsRequestDetailAttachmentsItem] | None = None
    bill_checks: list[SettlementsBillDetailItemsItemCheck] | None = None
    difference: SettlementsRequestDetailDifference | None = None
    request: SettlementsApplyRequestResponse
    rewards: list[SettlementsRequestDetailRewardsItem]
    statement: SettlementsRequestDetailStatement | None
    timeline: list[SettlementsRequestDetailTimelineItem] | None = None


class SettlementsRevealPayeeResponse(ApiResponseModel):
    account: str
    bank: str
    method: str
    name: str


class SettlementsRulesResponse(ApiResponseModel):
    beneficiary: str
    channel_rate_bps: int
    channel_rates: SettlementsCreateSnapshotItemsItemPolicyChannelRates
    enabled: bool
    hold_days: int
    max_reward_fen: float | int | None
    payout_days: float | int | None
    rate_bps: int
    review_days: float | int | None
    revision: int
    shared_fees: list[SettlementsApproveSnapshotItemsItemPolicySharedFeesItem]


SettlementsSavePayeeResponse = SettlementsApproveSnapshotPayee


class SettlementsSavePolicyResponse(ApiResponseModel):
    beneficiary: str
    channel_rate_bps: int | None
    channel_rates: SettlementsCreateSnapshotItemsItemPolicyChannelRates | None
    enabled: bool
    hold_days: int
    max_reward_fen: int | None
    payout_days: int | None
    rate_bps: int
    review_days: int | None
    revision: int
    shared_fees: list[SettlementsCreateSnapshotItemsItemPolicySharedFeesItem]


SettlementsStartRequestResponse = SettlementsApplyRequestResponse


class SettlementsStatementDetailAttachmentsItem(ApiResponseModel):
    created_at: float | int
    id: str
    media_type: str
    name: str


class SettlementsStatementDetailBillDifferencesItem(ApiResponseModel):
    order_id: str
    reasons: list[str]


class SettlementsStatementDetailStatement(ApiResponseModel):
    adjustment_fen: int
    approved_at: float | int | None
    beneficiary: str
    beneficiary_name: str
    created_at: int
    gross_fen: int
    id: str
    net_fen: float | int | None
    paid_at: float | int | None
    payout: dict[str, JsonValue]
    personal_fen: int
    reason: str
    receipt: str
    review: JsonValue
    revision: int
    # 查看历史结算单沿用历史快照契约，不要求后来新增的渠道、收款资料和服务期限。
    snapshot: SettlementsRequestDetailStatementSnapshot
    status: str
    tax_fen: float | int | None
    updated_at: int


class SettlementsStatementDetailTimelineItemValue(ApiResponseModel):
    order_ids: list[str] | None = None


class SettlementsStatementDetailTimelineItem(ApiResponseModel):
    actor_name: str | None
    created_at: int
    id: int
    kind: str
    target: str
    value: SettlementsStatementDetailTimelineItemValue


class SettlementsStatementDetailResponse(ApiResponseModel):
    attachments: list[SettlementsStatementDetailAttachmentsItem]
    bill_differences: list[SettlementsStatementDetailBillDifferencesItem]
    operation_issues: list[str]
    payout_batch_id: JsonValue
    statement: SettlementsStatementDetailStatement
    timeline: list[SettlementsStatementDetailTimelineItem]


class SettlementsUploadAttachmentResponse(ApiResponseModel):
    id: str


class SettlementsVoidResponse(ApiResponseModel):
    adjustment_fen: int
    approved_at: int
    beneficiary: str
    beneficiary_name: str
    created_at: int
    gross_fen: int
    id: str
    net_fen: int
    paid_at: float | int | None
    payout: dict[str, JsonValue]
    personal_fen: int
    reason: str
    receipt: str
    review: SettlementsAttachPayeeReview
    revision: int
    snapshot: SettlementsApproveSnapshot
    status: str
    tax_fen: int
    updated_at: int
