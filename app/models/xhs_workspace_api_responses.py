"""xhs_workspace 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, JsonValue


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class XhsWorkspaceCalendarAccountsItem(ApiResponseModel):
    id: str
    last_published_at: JsonValue
    name: str


class XhsWorkspaceCalendarItemsItem(ApiResponseModel):
    account_key: str
    admin_id: int
    calendar_at: str | datetime
    conflict_count: int
    conflicts: list[str]
    created_at: str | datetime
    data: dict[str, JsonValue]
    id: str
    kind: str
    parent_id: str | None
    revision: int
    status: str
    title: str
    updated_at: str | datetime


class XhsWorkspaceCalendarUnscheduledItem(ApiResponseModel):
    account_key: str
    admin_id: int
    calendar_at: str | datetime | None
    conflicts: list[str]
    created_at: str | datetime
    data: dict[str, JsonValue]
    id: str
    kind: str
    parent_id: str | None
    revision: int
    status: str
    title: str
    updated_at: str | datetime


class XhsWorkspaceCalendarResponse(ApiResponseModel):
    accounts: list[XhsWorkspaceCalendarAccountsItem]
    items: list[XhsWorkspaceCalendarItemsItem]
    page_size: int
    unscheduled: list[XhsWorkspaceCalendarUnscheduledItem]
    unscheduled_page: int
    unscheduled_total: int


class XhsWorkspaceCreateTutorialRecords(ApiResponseModel):
    drafts: str
    ideas: str
    materials: str
    publications: str


class XhsWorkspaceCreateTutorialResponse(ApiResponseModel):
    records: XhsWorkspaceCreateTutorialRecords


class XhsWorkspaceIdeaPreviewResponse(ApiResponseModel):
    checkpoint: int
    data: dict[str, JsonValue]
    reasons: list[str]
    series: str


class XhsWorkspaceTodayItemsItem(ApiResponseModel):
    admin_id: int
    checkpoint: int | None = None
    created_at: str | datetime
    data: dict[str, JsonValue]
    due_at: str | datetime | None = None
    id: str
    kind: str
    parent_id: None | str
    revision: int
    status: str
    title: str
    updated_at: str | datetime


class XhsWorkspaceTodayResponse(ApiResponseModel):
    day_start: str
    items: list[XhsWorkspaceTodayItemsItem]
    page: int
    page_size: int
    total: int


class XhsWorkspaceTutorialResponse(ApiResponseModel):
    records: dict[str, JsonValue]
