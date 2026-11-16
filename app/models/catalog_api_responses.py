"""catalog 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, JsonValue

from app.models.responses import ArchiveSnapshotResponse


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class CatalogAdminPaperAssetsItem(ApiResponseModel):
    byte_size: int
    id: str
    kind: str
    mime_type: str
    page_number: int
    thumbnail_url: str | None = None
    url: str


class CatalogAdminPaperEditionsItem(ApiResponseModel):
    byte_size: int
    kind: str
    label: str
    mode: str
    paper_id: str
    url: str


class CatalogAdminPaperReviewHistoryItem(ApiResponseModel):
    admin_id: int
    answer_readiness: str
    reviewed_at: int
    revision: int


class CatalogAdminPaperTagsItem(ApiResponseModel):
    id: str
    kind: str
    name: str


class CatalogAdminPaperVersionsItem(ApiResponseModel):
    created_at: int
    note: str
    release_number: int


class CatalogAdminPaperResponse(ApiResponseModel):
    answer_readiness: str
    assets: list[CatalogAdminPaperAssetsItem]
    can_download: bool
    can_view: bool
    category: str
    category_id: str
    created_at: int
    description: str
    difficulty: None | str
    download_access: str
    download_mode: str
    editions: list[CatalogAdminPaperEditionsItem]
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
    publisher_id: int | None
    publisher_name: None | str
    question_count: int
    question_types: list[str]
    release_number: int
    required_download: str
    required_view: str
    review_history: list[CatalogAdminPaperReviewHistoryItem]
    reviewed_at: int
    revision: int
    scope: str
    snapshot: ArchiveSnapshotResponse
    source_id: str
    status: str
    subject: str
    tags: list[CatalogAdminPaperTagsItem]
    thumbnail_id: str
    thumbnail_url: str
    title: str
    update_note: str
    updated_at: int
    version: int
    versions: list[CatalogAdminPaperVersionsItem]
    view_access: str


class CatalogAdminPapersItemsItemTagsItem(ApiResponseModel):
    id: str
    kind: str
    name: str
    paper_count: float | int | None = None


class CatalogAdminPapersItemsItem(ApiResponseModel):
    answer_readiness: str
    can_download: bool
    can_view: bool
    category: str
    category_id: str
    created_at: int
    description: str
    download_access: str
    download_mode: str
    download_users: int
    external_code: str
    external_url: str
    favorite: bool
    favorite_count: int
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
    reviewed_at: int
    revision: int
    scope: str
    source_id: str
    status: str
    subject: str
    tags: list[CatalogAdminPapersItemsItemTagsItem]
    thumbnail_id: str
    thumbnail_url: str
    title: str
    update_note: str
    updated_at: int
    version: int
    view_access: str


class CatalogAdminPapersResponse(ApiResponseModel):
    has_more: bool
    items: list[CatalogAdminPapersItemsItem]
    next_cursor: str | None
    total: int


class CatalogAdminSummaryResponse(ApiResponseModel):
    downloads: int
    draft: int
    favorites: int
    published: int
    total: int
    withdrawn: int


class CatalogCatalogWindowItemsItem(ApiResponseModel):
    answer_readiness: str
    can_download: bool
    can_view: bool
    category: str
    category_id: str
    created_at: int
    description: str
    download_access: str
    download_mode: str
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
    question_count: int
    question_types: list[str]
    release_number: int
    required_download: str
    required_view: str
    reviewed_at: int
    revision: int
    scope: str
    source_id: str
    status: str
    subject: str
    thumbnail_id: str | None
    thumbnail_url: str | None
    title: str
    update_note: str
    updated_at: int
    version: int
    view_access: str


class CatalogCatalogWindowResponse(ApiResponseModel):
    items: list[CatalogCatalogWindowItemsItem]


class CatalogCreateEditionsItem(ApiResponseModel):
    byte_size: int
    kind: str
    label: str
    mode: str
    paper_id: str | None = None
    url: str


class CatalogCreateResponse(ApiResponseModel):
    answer_readiness: str
    assets: list[CatalogAdminPaperAssetsItem]
    can_download: bool
    can_view: bool
    category: str
    category_id: str
    created_at: int
    description: str
    difficulty: None | str
    download_access: str
    download_mode: str
    editions: list[CatalogCreateEditionsItem]
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
    review_history: list[CatalogAdminPaperReviewHistoryItem]
    reviewed_at: int
    revision: int
    scope: str
    snapshot: ArchiveSnapshotResponse
    source_id: str
    status: str
    subject: str
    tags: list[CatalogAdminPapersItemsItemTagsItem]
    thumbnail_id: None | str
    thumbnail_url: None | str
    title: str
    update_note: str
    updated_at: int
    version: int
    versions: list[CatalogAdminPaperVersionsItem]
    view_access: str


class CatalogDownloadResponse(ApiResponseModel):
    byte_size: int | None = None
    extraction_code: str | None = None
    id: str | None = None
    kind: str
    mime_type: str | None = None
    page_number: int | None = None
    url: str


class CatalogFavoriteResponse(ApiResponseModel):
    favorite: bool


class CatalogImportEditionResponse(ApiResponseModel):
    editions: list[CatalogAdminPaperEditionsItem]
    revision: int


class CatalogImportPaperResponse(ApiResponseModel):
    answer_readiness: str
    assets: list[CatalogAdminPaperAssetsItem]
    can_download: bool
    can_view: bool
    category: str
    category_id: str
    created_at: int
    description: str
    difficulty: str | None
    download_access: str
    download_mode: str
    editions: list[CatalogAdminPaperEditionsItem]
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
    review_history: list[CatalogAdminPaperReviewHistoryItem]
    reviewed_at: int
    revision: int
    scope: str
    snapshot: ArchiveSnapshotResponse
    source_id: str
    status: str
    subject: str
    tags: list[CatalogAdminPapersItemsItemTagsItem]
    thumbnail_id: str
    thumbnail_url: str
    title: str
    update_note: str
    updated_at: int
    version: int
    versions: list[CatalogAdminPaperVersionsItem]
    view_access: str


class CatalogPaperEditionsItem(ApiResponseModel):
    byte_size: int
    kind: str
    label: str
    mode: str
    url: str | None = None


class CatalogPaperResponse(ApiResponseModel):
    answer_readiness: str
    assets: list[CatalogAdminPaperAssetsItem]
    can_download: bool
    can_view: bool
    category: str
    category_id: str
    created_at: int
    description: str
    difficulty: None | str
    download_access: str
    download_mode: str
    editions: list[CatalogPaperEditionsItem]
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
    question_count: int
    question_types: list[str]
    release_number: int
    required_download: str
    required_view: str
    reviewed_at: int
    revision: int
    scope: str
    source_id: str
    status: str
    subject: str
    tags: list[CatalogAdminPapersItemsItemTagsItem]
    thumbnail_id: None | str
    thumbnail_url: None | str
    title: str
    update_note: str
    updated_at: int
    version: int
    versions: list[CatalogAdminPaperVersionsItem]
    view_access: str


class CatalogPapersItemsItem(ApiResponseModel):
    activity_at: int | None = None
    answer_readiness: str
    can_download: bool
    can_view: bool
    category: str
    category_id: str
    created_at: int
    description: str
    download_access: str
    download_mode: str
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
    question_count: int
    question_types: list[str]
    release_number: int
    required_download: str
    required_view: str
    reviewed_at: int
    revision: int
    scope: str
    source_id: str
    status: str
    subject: str
    tags: list[CatalogAdminPaperTagsItem]
    thumbnail_id: None | str
    thumbnail_url: None | str
    title: str
    topic_order: int | None = None
    update_note: str
    updated_at: int
    version: int
    view_access: str


class CatalogPapersResponse(ApiResponseModel):
    has_more: bool
    items: list[CatalogPapersItemsItem]
    next_cursor: None | str
    total: int | None


class CatalogSourcesItemsItem(ApiResponseModel):
    file_status: str
    grade: str
    id: str
    question_count: int
    subject: str
    title: str
    version: int


class CatalogSourcesResponse(ApiResponseModel):
    has_more: bool
    items: list[CatalogSourcesItemsItem]
    total: int


class CatalogSummaryCategoriesItem(ApiResponseModel):
    description: str
    icon: str
    id: str
    name: str
    paper_count: int


class CatalogSummaryResponse(ApiResponseModel):
    categories: list[CatalogSummaryCategoriesItem]
    downloads: int
    favorites: int
    grades: list[str]
    papers: int
    subjects: list[str]
    unread: int


class CatalogTypeRulesItemsItem(ApiResponseModel):
    download_access: str
    label: str
    paper_count: int
    question_type: str
    revision: int
    updated_at: int
    view_access: str


class CatalogTypeRulesResponse(ApiResponseModel):
    items: list[CatalogTypeRulesItemsItem]


class CatalogUpdateResponse(ApiResponseModel):
    answer_readiness: str
    assets: list[CatalogAdminPaperAssetsItem]
    can_download: bool
    can_view: bool
    category: str
    category_id: str
    created_at: int
    description: str
    difficulty: None | str
    download_access: str
    download_mode: str
    editions: list[CatalogCreateEditionsItem]
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
    review_history: list[CatalogAdminPaperReviewHistoryItem]
    reviewed_at: int
    revision: int
    scope: str
    snapshot: ArchiveSnapshotResponse
    source_id: str
    status: str
    subject: str
    tags: list[CatalogAdminPapersItemsItemTagsItem]
    thumbnail_id: None | str
    thumbnail_url: None | str
    title: str
    update_note: str
    updated_at: int
    version: int
    versions: list[CatalogAdminPaperVersionsItem]
    view_access: str


CatalogUpdateTypeRuleResponse = CatalogTypeRulesItemsItem
