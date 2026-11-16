"""promotion_finance 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, JsonValue


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class PromotionFinanceArchiveItemsItem(ApiResponseModel):
    amount_fen: int
    beneficiary: str
    kind: str
    occurred_at: int
    original_at: int
    source: str
    statement_id: str


class PromotionFinanceArchiveTotals(ApiResponseModel):
    adjustment: int
    payment: int
    personal: int
    reward: int
    tax: int
    void_personal: int
    void_reward: int
    void_tax: int


class PromotionFinanceArchiveResponse(ApiResponseModel):
    admin_id: int
    admin_name: str
    archive_id: str
    archived_at: int
    as_of: int
    closing_fen: int
    items: list[PromotionFinanceArchiveItemsItem]
    month: str
    opening_fen: int
    quote_digest: str
    totals: PromotionFinanceArchiveTotals


class PromotionFinanceControlsResponse(ApiResponseModel):
    revision: int
    separate_payment: bool
    separate_review: bool


class PromotionFinanceCostVouchersItemsItemEntriesItem(ApiResponseModel):
    amount_fen: float | int
    id: str
    kind: str
    source_ref: str


class PromotionFinanceCostVouchersItemsItemFilesItem(ApiResponseModel):
    created_at: float | int
    id: str
    media_type: str
    name: str


class PromotionFinanceCostVouchersItemsItem(ApiResponseModel):
    admin_id: float | int
    count: float | int
    deduction_fen: float | int
    deduction_remaining_fen: float | int
    entries: list[PromotionFinanceCostVouchersItemsItemEntriesItem]
    evidence: str
    expense_fen: float | int
    expense_remaining_fen: float | int
    files: list[PromotionFinanceCostVouchersItemsItemFilesItem]
    id: str
    name: str
    reference: str
    revision: float | int
    total_fen: float | int


class PromotionFinanceCostVouchersResponse(ApiResponseModel):
    items: list[PromotionFinanceCostVouchersItemsItem]
    page: int | None = None
    total: int | None = None


class PromotionFinanceCreateDisputeFilesItem(ApiResponseModel):
    created_at: float | int
    id: str
    media_type: str
    name: str


class PromotionFinanceCreateDisputeMessagesItem(ApiResponseModel):
    actor_id: int
    actor_name: str
    content: str
    created_at: int
    evidence: str
    id: int


class PromotionFinanceCreateDisputeResponse(ApiResponseModel):
    beneficiary: str
    created_at: int
    files: list[PromotionFinanceCreateDisputeFilesItem]
    id: str
    messages: list[PromotionFinanceCreateDisputeMessagesItem]
    request_key: str
    revision: int
    status: str
    target_id: str
    target_kind: str
    title: str
    updated_at: int


class PromotionFinanceCreateVoucherResponse(ApiResponseModel):
    admin_id: float | int
    count: float | int
    created_at: int | None = None
    deduction_fen: float | int
    deduction_remaining_fen: float | int
    entries: list[PromotionFinanceCostVouchersItemsItemEntriesItem]
    evidence: str
    expense_fen: float | int
    expense_remaining_fen: float | int
    files: list[PromotionFinanceCostVouchersItemsItemFilesItem]
    foreign_count: int | None = None
    id: str
    name: str
    reference: str
    revision: float | int
    total_fen: float | int


class PromotionFinanceDisputeDetailFilesItem(ApiResponseModel):
    created_at: int
    id: str
    media_type: str
    name: str


class PromotionFinanceDisputeDetailResponse(ApiResponseModel):
    beneficiary: str
    created_at: int
    files: list[PromotionFinanceDisputeDetailFilesItem]
    id: str
    messages: list[PromotionFinanceCreateDisputeMessagesItem]
    request_key: str
    revision: int
    status: str
    target_id: str
    target_kind: str
    title: str
    updated_at: int


class PromotionFinanceDisputesResponse(ApiResponseModel):
    items: list[PromotionFinanceCreateDisputeResponse]
    total: int


class PromotionFinanceFinanceExpensesItemsItem(ApiResponseModel):
    active: bool
    admin_id: float | int
    admin_name: str
    amount_fen: float | int
    campaign_id: str
    campaign_name: str
    category: str
    created_at: float | int
    evidence: str
    expense_date: str
    id: str
    included_in_baseline: bool | None = None
    note: str
    revision: float | int
    source_ref: str | None = None


class PromotionFinanceFinanceExpensesResponse(ApiResponseModel):
    baseline_fen: float | int
    cumulative_fen: float | int
    items: list[PromotionFinanceFinanceExpensesItemsItem]
    period_fen: float | int
    total: float | int
    unknown_campaigns: float | int


class PromotionFinanceMonthEndBillsItem(ApiResponseModel):
    day: str
    differences: int
    reason: str


class PromotionFinanceMonthEndArchiveItem(ApiResponseModel):
    beneficiary: str
    admin_id: int
    admin_name: str | None
    closing_fen: int


class PromotionFinanceMonthEndArchives(ApiResponseModel):
    items: list[PromotionFinanceMonthEndArchiveItem]
    total: int
    page: int


class PromotionFinanceMonthEndResponse(ApiResponseModel):
    # SUM(bigint) 返回 Decimal；以金额整数契约序列化，避免泛 JSON 拒绝合法余额。
    archives: PromotionFinanceMonthEndArchives | None
    as_of: int
    bills: list[PromotionFinanceMonthEndBillsItem] | None
    costs: JsonValue
    disputes: JsonValue
    ended: bool
    month: str
    month_end: str


class PromotionFinanceMonthlyResponse(ApiResponseModel):
    admin_id: int
    admin_name: str
    archive_id: None | str
    archived_at: int | None = None
    as_of: int
    closing_fen: int
    items: list[PromotionFinanceArchiveItemsItem]
    month: str
    opening_fen: int
    quote_digest: str
    totals: PromotionFinanceArchiveTotals


PromotionFinanceReplyResponse = PromotionFinanceDisputeDetailResponse


PromotionFinanceSaveControlsResponse = PromotionFinanceControlsResponse


PromotionFinanceUpdateVoucherResponse = PromotionFinanceCreateVoucherResponse


class PromotionFinanceUploadResponse(ApiResponseModel):
    id: str


PromotionFinanceUploadVoucherResponse = PromotionFinanceUploadResponse
