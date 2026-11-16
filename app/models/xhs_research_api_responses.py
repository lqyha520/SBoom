"""xhs_research 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class XhsResearchSnapshot(ApiResponseModel):
    """任务中的原始采集快照，不包含笔记库标记和历史聚合字段。"""

    author: str
    captured_at: str | datetime
    likes_count: int | None
    likes_text: str
    note_id: str
    published_text: str
    sort_rank: int
    title: str
    url: str


class XhsResearchGetNoteResponse(ApiResponseModel):
    author: str
    captured_at: str | datetime
    captured_epoch: float
    favorite: bool
    grade: str
    keyword: str
    likes_count: int | None
    likes_text: str
    mark_status: str
    note_id: str
    period: str
    published_text: str
    remark: str
    revision: int
    seen_before: bool
    seen_count: int
    sort_by: str
    subject: str
    title: str
    url: str


class XhsResearchTaskSummary(ApiResponseModel):
    average_likes: int | None
    batch_id: str
    batch_position: int
    created_at: str | datetime
    error: str
    finished_at: str | datetime
    grade: str
    id: str
    keyword: str
    median_likes: int | None
    note_count: int
    note_limit: int
    period: str
    sort_by: str
    status: str
    subject: str


class XhsResearchCreateBatchResponse(ApiResponseModel):
    id: str
    items: list[XhsResearchTaskSummary]


class XhsResearchGetTaskResponse(XhsResearchTaskSummary):
    items: list[XhsResearchSnapshot]


XhsResearchCreateTaskResponse = XhsResearchGetTaskResponse


XhsResearchFailTaskResponse = XhsResearchGetTaskResponse


XhsResearchGetBatchResponse = XhsResearchCreateBatchResponse


class XhsResearchListBatchesItemsItem(ApiResponseModel):
    completed: int
    created_at: str | datetime
    id: str
    total: int


class XhsResearchListBatchesResponse(ApiResponseModel):
    items: list[XhsResearchListBatchesItemsItem]


class XhsResearchListNotesItemsItem(ApiResponseModel):
    author: str
    captured_at: str | datetime
    captured_epoch: float | None = None
    favorite: bool
    grade: str
    id: int | None = None
    keyword: str
    likes_count: int | None
    likes_text: str
    mark_status: str
    note_id: str
    period: str
    published_text: str
    remark: str
    revision: int
    seen_before: bool
    seen_count: int
    sort_by: str
    subject: str
    task_id: str | None = None
    title: str
    url: str


class XhsResearchListNotesResponse(ApiResponseModel):
    items: list[XhsResearchListNotesItemsItem]
    page: int
    page_size: int
    total: int


class XhsResearchListTasksResponse(ApiResponseModel):
    items: list[XhsResearchTaskSummary]
    page: int
    page_size: int
    total: int


class XhsResearchNoteHistoryItemsItem(ApiResponseModel):
    captured_at: str | datetime
    grade: str
    keyword: str
    likes_count: int | None
    likes_text: str
    period: str
    sort_by: str
    subject: str
    task_id: str


class XhsResearchNoteHistoryResponse(ApiResponseModel):
    items: list[XhsResearchNoteHistoryItemsItem]
    page: int
    page_size: int
    total: int


class XhsResearchSaveMarkResponse(ApiResponseModel):
    favorite: bool
    mark_status: str
    remark: str
    revision: int


XhsResearchSaveResultsResponse = XhsResearchGetTaskResponse


XhsResearchStartTaskResponse = XhsResearchGetTaskResponse
