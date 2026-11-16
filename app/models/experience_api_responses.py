"""experience 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, JsonValue

from app.models.responses import ArchiveSnapshotResponse


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ExperienceAdminFeedbackItemsItem(ApiResponseModel):
    admin_id: int | None
    body: str
    catalog_id: str | None
    created_at: int
    id: str
    internal_note: str
    is_vip: bool
    kind: str
    membership: str
    membership_status: str
    nickname: str
    paper_title: str
    reply: str
    revision: int
    status: str
    updated_at: int
    user_id: str
    username: str
    vip_expires_at: int | None


class ExperienceAdminFeedbackResponse(ApiResponseModel):
    has_more: bool
    items: list[ExperienceAdminFeedbackItemsItem]
    total: int


ExperienceAdminFeedbackDetailResponse = ExperienceAdminFeedbackItemsItem


class ExperienceAdminSupportResponse(ApiResponseModel):
    benefits: str
    email: str
    hours: str
    phone: str
    qr_url: str
    revision: int
    wechat: str


class ExperienceAdminTopicsItemsItemPapersItem(ApiResponseModel):
    catalog_id: str
    file_status: str
    status: str
    title: str


class ExperienceAdminTopicsItemsItem(ApiResponseModel):
    created_at: int
    description: str
    id: str
    is_visible: bool
    paper_count: int
    paper_ids: list[str]
    papers: list[ExperienceAdminTopicsItemsItemPapersItem]
    revision: int
    sort_order: int
    title: str
    updated_at: int


class ExperienceAdminTopicsResponse(ApiResponseModel):
    items: list[ExperienceAdminTopicsItemsItem]


class ExperienceAnalyticsDownloadFailuresItem(ApiResponseModel):
    catalog_id: None | str
    title: None | str
    total: int


class ExperienceAnalyticsSearchMissesItem(ApiResponseModel):
    query: str
    total: int


class ExperienceAnalyticsTimelineItem(ApiResponseModel):
    active_users: int
    date: str
    download_failed: int
    download_ok: int
    search_miss: int


class ExperienceAnalyticsResponse(ApiResponseModel):
    daily_active: int
    download_failures: list[ExperienceAnalyticsDownloadFailuresItem]
    monthly_active: int
    retention_days: int
    search_misses: list[ExperienceAnalyticsSearchMissesItem]
    timeline: list[ExperienceAnalyticsTimelineItem]
    timezone: str
    weekly_active: int


class ExperienceAssignGroupResponse(ApiResponseModel):
    group_id: str


class ExperienceBatchResponse(ApiResponseModel):
    updated: int


class ExperienceBatchFavoritesResponse(ApiResponseModel):
    action: str
    count: int
    group_id: None | str


class ExperienceCreateGroupResponse(ApiResponseModel):
    created_at: int
    id: str
    name: str
    revision: int
    user_id: str


class ExperienceCreateTopicResponse(ApiResponseModel):
    created_at: int
    description: str
    id: str
    is_visible: int
    revision: int
    sort_order: int
    title: str
    updated_at: int


class ExperienceFeedbackItemsItem(ApiResponseModel):
    body: str
    catalog_id: None | str
    created_at: int
    id: str
    kind: str
    nickname: str
    paper_title: str
    reply: str
    revision: int
    status: str
    updated_at: int
    user_id: str
    username: str


class ExperienceFeedbackResponse(ApiResponseModel):
    has_more: bool
    items: list[ExperienceFeedbackItemsItem]
    total: int


class ExperienceFeedbackDetailResponse(ApiResponseModel):
    body: str
    catalog_id: str | None
    created_at: int
    id: str
    kind: str
    paper_title: str
    reply: str
    revision: int
    status: str
    updated_at: int
    user_id: str


class ExperienceGroupsItemsItem(ApiResponseModel):
    created_at: int
    id: str
    name: str
    paper_count: int
    revision: int
    user_id: str


class ExperienceGroupsResponse(ApiResponseModel):
    items: list[ExperienceGroupsItemsItem]


class ExperienceMemberEventsItemsItemAfter(ApiResponseModel):
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
    note: str | None = None
    referral_code: str
    renewal_days: int | None = None
    revision: int
    updated_at: int
    username: str
    vip_expires_at: int


class ExperienceMemberEventsItemsItemBefore(ApiResponseModel):
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


class ExperienceMemberEventsItemsItem(ApiResponseModel):
    admin_name: str
    after: ExperienceMemberEventsItemsItemAfter
    before: ExperienceMemberEventsItemsItemBefore
    created_at: int
    id: str


class ExperienceMemberEventsResponse(ApiResponseModel):
    has_more: bool
    items: list[ExperienceMemberEventsItemsItem]
    total: int


class ExperiencePreviewAssetsItem(ApiResponseModel):
    byte_size: int
    id: str
    kind: str
    mime_type: str
    page_number: int
    thumbnail_url: str | None = None
    url: str


class ExperiencePreviewEditionsItem(ApiResponseModel):
    byte_size: int
    kind: str
    label: str
    mode: str
    url: str | None = None


class ExperiencePreviewReviewHistoryItem(ApiResponseModel):
    admin_id: int
    answer_readiness: str
    reviewed_at: int
    revision: int


class ExperiencePreviewTagsItem(ApiResponseModel):
    id: str
    kind: str
    name: str
    paper_count: float | int | None = None


class ExperiencePreviewVersionsItem(ApiResponseModel):
    created_at: int
    note: str
    release_number: int


class ExperiencePreviewResponse(ApiResponseModel):
    answer_readiness: str
    assets: list[ExperiencePreviewAssetsItem]
    can_download: bool
    can_view: bool
    category: str
    category_id: str
    created_at: int
    description: str
    difficulty: str
    download_access: str
    download_mode: str
    editions: list[ExperiencePreviewEditionsItem]
    favorite: bool
    featured: bool
    file_error: str
    file_status: str
    folder_id: JsonValue
    folder_name: JsonValue
    grade: str
    group_id: str
    group_name: str
    id: str
    keyword: str
    page_count: int
    preview_membership: str
    published_at: int
    publisher_id: int
    publisher_name: str
    question_count: int
    question_types: list[str]
    release_number: int
    required_download: str
    required_view: str
    review_history: list[ExperiencePreviewReviewHistoryItem]
    reviewed_at: int
    revision: int
    scope: str
    snapshot: ArchiveSnapshotResponse | None
    source_id: str
    status: str
    subject: str
    tags: list[ExperiencePreviewTagsItem]
    thumbnail_id: None | str
    thumbnail_url: None | str
    title: str
    update_note: str
    updated_at: int
    version: int
    versions: list[ExperiencePreviewVersionsItem]
    view_access: str


class ExperienceRenewResponse(ApiResponseModel):
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
    vip_expires_at: int


class ExperienceReviseEditionsItem(ApiResponseModel):
    byte_size: int
    kind: str
    label: str
    mode: str
    paper_id: str
    url: str


class ExperienceReviseResponse(ApiResponseModel):
    answer_readiness: str
    assets: list[ExperiencePreviewAssetsItem]
    can_download: bool
    can_view: bool
    category: str
    category_id: str
    created_at: int
    description: str
    difficulty: str
    download_access: str
    download_mode: str
    editions: list[ExperienceReviseEditionsItem]
    external_code: str
    external_url: str
    favorite: bool
    featured: bool
    file_error: str
    file_status: str
    folder_id: JsonValue
    folder_name: JsonValue
    grade: str
    group_id: str
    group_name: str
    id: str
    keyword: str
    page_count: int
    published_at: int
    publisher_id: int
    publisher_name: str
    question_count: int
    question_types: list[str]
    release_number: int
    required_download: str
    required_view: str
    review_history: list[ExperiencePreviewReviewHistoryItem]
    reviewed_at: int
    revision: int
    scope: str
    snapshot: ArchiveSnapshotResponse
    source_id: str
    status: str
    subject: str
    tags: list[ExperiencePreviewTagsItem]
    thumbnail_id: str
    thumbnail_url: str
    title: str
    update_note: str
    updated_at: int
    version: int
    versions: list[ExperiencePreviewVersionsItem]
    view_access: str


ExperienceSaveSupportResponse = ExperienceAdminSupportResponse


class ExperienceSubmitFeedbackResponse(ApiResponseModel):
    body: str
    catalog_id: None | str
    created_at: int
    id: str
    kind: str
    paper_title: str
    reply: str
    revision: int
    status: str
    updated_at: int
    user_id: str


ExperienceSupportResponse = ExperienceAdminSupportResponse


ExperienceTopicsResponse = ExperienceAdminTopicsResponse


class ExperienceUpdateFeedbackResponse(ApiResponseModel):
    admin_id: int
    body: str
    catalog_id: None | str
    created_at: int
    id: str
    internal_note: str
    is_vip: bool
    kind: str
    membership: str
    membership_status: str
    nickname: str
    paper_title: str
    reply: str
    revision: int
    status: str
    updated_at: int
    user_id: str
    username: str
    vip_expires_at: int | None


ExperienceUpdateGroupResponse = ExperienceCreateGroupResponse


ExperienceUpdateTopicResponse = ExperienceCreateTopicResponse
