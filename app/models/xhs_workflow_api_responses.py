"""xhs_workflow 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, JsonValue


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class XhsWorkflowAnalyticsAccountsItem(ApiResponseModel):
    id: str
    name: str


class XhsWorkflowAnalyticsItemsItemMetric(ApiResponseModel):
    checkpoint: int
    comments: int
    downloads: float | int | None
    follows: JsonValue
    likes: int
    measured_at: str | datetime
    notes: str
    revision: int
    saves: int
    views: int


class XhsWorkflowAnalyticsItemsItem(ApiResponseModel):
    admin_id: int
    created_at: str | datetime
    data: dict[str, JsonValue]
    due_at: str | datetime
    id: str
    interaction_rate: float | None
    kind: str
    metric: XhsWorkflowAnalyticsItemsItemMetric | None
    needs_recording: bool
    parent_id: None | str
    revision: int
    save_rate: float | None
    status: str
    title: str
    updated_at: str | datetime


class XhsWorkflowAnalyticsResponse(ApiResponseModel):
    accounts: list[XhsWorkflowAnalyticsAccountsItem]
    items: list[XhsWorkflowAnalyticsItemsItem]
    page: int
    page_size: int
    total: int


class XhsWorkflowGenerateCopyDraftAccountProfile(ApiResponseModel):
    audience: str
    direction: str
    id: str
    name: str
    style: str
    topics: str


class XhsWorkflowGenerateCopyDraftCardsItem(ApiResponseModel):
    body: str
    heading: str


class XhsWorkflowGenerateCopyDraft(ApiResponseModel):
    account_profile: XhsWorkflowGenerateCopyDraftAccountProfile
    angle: str
    audience: str
    body: str
    cards: list[XhsWorkflowGenerateCopyDraftCardsItem]
    cover_subtitle: str
    cover_title: str
    generation_request_id: str
    hashtags: str
    headline: str
    notes: str
    source_material_revision: int
    status: str
    theme: str
    title: str
    title_options: list[str]


class XhsWorkflowGenerateCopyResponse(ApiResponseModel):
    draft: XhsWorkflowGenerateCopyDraft
    material_id: str
    material_revision: int
    request_id: str


class XhsWorkflowMetricsResponse(ApiResponseModel):
    items: list[XhsWorkflowAnalyticsItemsItemMetric]


class XhsWorkflowPublicationCheckDuplicatesItem(ApiResponseModel):
    id: str
    title: str


class XhsWorkflowPublicationCheckFindingsItem(ApiResponseModel):
    code: str
    evidence: list[str]
    message: str
    title: str


class XhsWorkflowPublicationCheckResponse(ApiResponseModel):
    blockers: list[str]
    duplicates: list[XhsWorkflowPublicationCheckDuplicatesItem]
    findings: list[XhsWorkflowPublicationCheckFindingsItem]
    notice: str


XhsWorkflowSaveMetricResponse = XhsWorkflowMetricsResponse


class XhsWorkflowSaveReviewRecord(ApiResponseModel):
    admin_id: int
    created_at: str | datetime
    data: dict[str, JsonValue]
    id: str
    kind: str
    parent_id: str
    revision: int
    status: str
    title: str
    updated_at: str | datetime


class XhsWorkflowSaveReviewResponse(ApiResponseModel):
    items: list[XhsWorkflowAnalyticsItemsItemMetric]
    record: XhsWorkflowSaveReviewRecord


class XhsWorkflowVersionsItemsItem(ApiResponseModel):
    created_at: str | datetime
    data: dict[str, JsonValue]
    revision: int


class XhsWorkflowVersionsResponse(ApiResponseModel):
    items: list[XhsWorkflowVersionsItemsItem]
    total: int
