"""engagement 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, JsonValue


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class EngagementAdminRequestsDemandItem(ApiResponseModel):
    fingerprint: str
    grade: str
    requests: int
    subject: str
    title: str
    users: int


class EngagementAdminRequestsItemsItem(ApiResponseModel):
    catalog_id: str | None
    created_at: int
    details: str
    fingerprint: str
    grade: str
    id: str
    nickname: str
    paper_file_status: str | None
    paper_status: str | None
    paper_title: str | None
    paper_visible: JsonValue
    reply: str
    revision: int
    status: str
    subject: str
    title: str
    updated_at: int
    user_id: str
    username: str


class EngagementAdminRequestsResponse(ApiResponseModel):
    demand: list[EngagementAdminRequestsDemandItem]
    has_more: bool
    items: list[EngagementAdminRequestsItemsItem]
    total: int


class EngagementAdminTagsItemsItem(ApiResponseModel):
    id: str
    is_visible: bool
    kind: str
    name: str
    paper_count: int
    revision: int
    sort_order: int


class EngagementAdminTagsResponse(ApiResponseModel):
    items: list[EngagementAdminTagsItemsItem]


class EngagementCancelClosureRequest(ApiResponseModel):
    account_name: str
    admin_id: float | int | None
    created_at: int
    id: str
    reason: str
    reply: str
    revision: int
    status: str
    updated_at: int
    user_id: str


class EngagementCancelClosureResponse(ApiResponseModel):
    request: EngagementCancelClosureRequest


EngagementClosureResponse = EngagementCancelClosureResponse


class EngagementClosuresItemsItem(ApiResponseModel):
    id: str
    reason: str
    reply: str
    revision: float | int
    status: str
    updated_at: float | int


class EngagementClosuresResponse(ApiResponseModel):
    has_more: bool
    items: list[EngagementClosuresItemsItem]
    total: int


class EngagementCreateRequestResponse(ApiResponseModel):
    catalog_id: str | None
    created_at: int
    details: str
    fingerprint: str
    grade: str
    id: str
    reply: str
    revision: int
    status: str
    subject: str
    title: str
    updated_at: int
    user_id: str


class EngagementCreateTagResponse(ApiResponseModel):
    id: str
    is_visible: int
    kind: str
    name: str
    revision: int
    sort_order: int


class EngagementDeliveryStatusResponse(ApiResponseModel):
    available: bool
    delivery_counts: dict[str, int]
    template_id: str


class EngagementEditionSourcesItemsItem(ApiResponseModel):
    id: str
    mode: str
    owned_by: str
    title: str
    version: int


class EngagementEditionSourcesResponse(ApiResponseModel):
    items: list[EngagementEditionSourcesItemsItem]
    loose: bool


class EngagementEditionsEditionsItem(ApiResponseModel):
    byte_size: int
    kind: str
    label: str
    mode: str
    paper_id: str | None = None
    url: str


class EngagementEditionsResponse(ApiResponseModel):
    editions: list[EngagementEditionsEditionsItem]
    revision: int


class EngagementInboxItemsItem(ApiResponseModel):
    body: str
    created_at: int
    id: str
    kind: str
    read_at: JsonValue
    target_id: str
    target_type: str
    title: str


class EngagementInboxResponse(ApiResponseModel):
    has_more: bool
    items: list[EngagementInboxItemsItem]
    total: int
    unread: int


class EngagementLabelsTagsItem(ApiResponseModel):
    id: str
    kind: str
    name: str


class EngagementLabelsResponse(ApiResponseModel):
    revision: int
    tags: list[EngagementLabelsTagsItem]


class EngagementReadAllResponse(ApiResponseModel):
    unread: int


EngagementReadMessageResponse = EngagementReadAllResponse


EngagementRequestClosureResponse = EngagementCancelClosureResponse


class EngagementRequestDetailResponse(ApiResponseModel):
    catalog_id: None | str
    created_at: float | int
    details: str
    grade: str
    id: str
    paper_title: None | str = None
    reply: str
    revision: float | int
    status: str
    subject: str
    title: str
    updated_at: float | int


class EngagementRequestsItemsItem(ApiResponseModel):
    catalog_id: str | None
    created_at: int
    details: str
    grade: str
    id: str
    paper_file_status: None | str
    paper_status: None | str
    paper_title: str | None
    reply: str
    revision: int
    status: str
    subject: str
    title: str
    updated_at: int


class EngagementRequestsResponse(ApiResponseModel):
    demand: list[EngagementAdminRequestsDemandItem]
    has_more: bool
    items: list[EngagementRequestsItemsItem]
    total: int


class EngagementResolveRequestResponse(ApiResponseModel):
    catalog_id: str
    created_at: int
    details: str
    fingerprint: str
    grade: str
    id: str
    reply: str
    revision: int
    status: str
    subject: str
    title: str
    updated_at: int
    user_id: str


class EngagementReviewClosureResponse(ApiResponseModel):
    account_name: str
    admin_id: int
    created_at: int
    id: str
    reason: str
    reply: str
    revision: int
    status: str
    updated_at: int
    user_id: int | str | None


class EngagementSubscribeResponse(ApiResponseModel):
    accepted: bool


class EngagementSubscriptionResponse(ApiResponseModel):
    available: bool
    template_id: str


EngagementTagsResponse = EngagementAdminTagsResponse


EngagementUpdateTagResponse = EngagementCreateTagResponse
