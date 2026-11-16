"""site 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class SiteAdoptDictionaryItemsItem(ApiResponseModel):
    created_at: float | int
    id: str
    is_visible: bool
    kind: str
    label: str
    parent: str
    revision: float | int
    sort_order: float | int
    updated_at: float | int
    value: str


class SiteAdoptDictionaryResponse(ApiResponseModel):
    added: int
    items: list[SiteAdoptDictionaryItemsItem]


class SiteAnalyticsByCategoryItem(ApiResponseModel):
    downloads: float | int
    favorites: float | int
    name: str
    papers: float | int


class SiteAnalyticsEngagement(ApiResponseModel):
    downloads: float | int
    favorites: float | int


class SiteAnalyticsIdlePapersItem(ApiResponseModel):
    category: str
    id: str
    published_at: float | int
    title: str


class SiteAnalyticsNewUsersTimelineItem(ApiResponseModel):
    date: str
    total: float | int


class SiteAnalyticsPapers(ApiResponseModel):
    draft: float | int
    published: float | int
    total: float | int
    withdrawn: float | int


class SiteAnalyticsTopDownloadsItem(ApiResponseModel):
    category: str
    id: str
    title: str
    total: float | int


class SiteAnalyticsUsers(ApiResponseModel):
    active: float | int
    new_30d: float | int
    new_7d: float | int
    total: float | int
    vip: float | int


class SiteAnalyticsResponse(ApiResponseModel):
    by_category: list[SiteAnalyticsByCategoryItem]
    engagement: SiteAnalyticsEngagement
    idle_papers: list[SiteAnalyticsIdlePapersItem]
    new_users_timeline: list[SiteAnalyticsNewUsersTimelineItem]
    papers: SiteAnalyticsPapers
    papers_without_category: float | int
    top_downloads: list[SiteAnalyticsTopDownloadsItem]
    top_favorites: list[SiteAnalyticsTopDownloadsItem]
    users: SiteAnalyticsUsers


class SiteBannersItemsItem(ApiResponseModel):
    action_label: str
    created_at: int
    id: str
    image_bytes: int
    image_fit: str
    image_key: str
    image_mime: str
    image_storage: str
    image_url: None | str
    is_visible: bool
    kicker: str
    revision: int
    sort_order: int
    subtitle: str
    target_type: str
    target_value: str
    title: str
    updated_at: int


class SiteBannersResponse(ApiResponseModel):
    items: list[SiteBannersItemsItem]


class SiteCategoriesItemsItem(ApiResponseModel):
    created_at: float | int
    description: str
    icon: str
    id: str
    is_visible: bool
    name: str
    paper_count: float | int
    revision: float | int
    sort_order: float | int
    updated_at: float | int


class SiteCategoriesResponse(ApiResponseModel):
    items: list[SiteCategoriesItemsItem]


class SiteClearBannerImageResponse(ApiResponseModel):
    action_label: str
    created_at: int
    id: str
    image_bytes: int
    image_fit: str
    image_key: str
    image_mime: str
    image_storage: str
    image_url: str | None
    is_visible: bool
    kicker: str
    revision: int
    sort_order: int
    subtitle: str
    target_type: str
    target_value: str
    title: str
    updated_at: int


SiteCreateBannerResponse = SiteClearBannerImageResponse


class SiteCreateCategoryResponse(ApiResponseModel):
    created_at: int
    description: str
    icon: str
    id: str
    is_visible: bool
    name: str
    paper_count: int
    revision: int
    sort_order: int
    updated_at: int


class SiteCreateDictionaryResponse(ApiResponseModel):
    created_at: int
    id: str
    is_visible: bool
    kind: str
    label: str
    parent: str
    revision: int
    sort_order: int
    updated_at: int
    value: str


class SiteCreateNoticeResponse(ApiResponseModel):
    body: str
    created_at: float | int
    ends_at: float | int
    id: str
    is_visible: bool
    level: str
    placement: str
    revision: float | int
    starts_at: float | int
    state: str
    title: str
    updated_at: float | int


class SiteDictionaryResponse(ApiResponseModel):
    items: list[SiteCreateDictionaryResponse]


class SiteDictionaryLinksLinksItem(ApiResponseModel):
    child_id: str
    parent_id: str


class SiteDictionaryLinksResponse(ApiResponseModel):
    links: list[SiteDictionaryLinksLinksItem]


class SiteDocumentResponse(ApiResponseModel):
    body: str
    key: str
    title: str
    updated_at: int


class SiteDocumentsItemsItem(ApiResponseModel):
    body: str
    key: str
    revision: int
    title: str
    updated_at: int


class SiteDocumentsResponse(ApiResponseModel):
    items: list[SiteDocumentsItemsItem]


class SiteHomeBannersItem(ApiResponseModel):
    action_label: str
    id: str
    image_fit: str | None = None
    image_url: None | str
    kicker: str
    revision: int | None = None
    subtitle: str
    target_type: str
    target_value: str
    title: str


class SiteHomeCategoriesItem(ApiResponseModel):
    description: str
    icon: str
    id: str
    name: str
    paper_count: float | int | None = None


class SiteHomeDictionariesSubjectsByGrade(ApiResponseModel):
    小学一年级: list[str]
    小学三年级: list[str]
    小学二年级: list[str]
    小学五年级: list[str]
    小学六年级: list[str]
    小学四年级: list[str]


class SiteHomeDictionaries(ApiResponseModel):
    grades: list[str]
    subjects: list[str]
    subjects_by_grade: SiteHomeDictionariesSubjectsByGrade | None = None


class SiteHomeNoticesBannerItem(ApiResponseModel):
    body: str
    id: str
    level: str
    placement: str
    title: str


class SiteHomeNotices(ApiResponseModel):
    banner: list[SiteHomeNoticesBannerItem]
    popup: list[SiteHomeNoticesBannerItem]


class SiteHomeResponse(ApiResponseModel):
    banner_mode: str | None = None
    banners: list[SiteHomeBannersItem]
    categories: list[SiteHomeCategoriesItem]
    dictionaries: SiteHomeDictionaries
    notices: SiteHomeNotices


class SiteNoticesResponse(ApiResponseModel):
    items: list[SiteCreateNoticeResponse]


SiteOrderCategoriesResponse = SiteCategoriesResponse


SiteReorderDictionaryResponse = SiteDictionaryResponse


class SiteSetDictionaryLinksResponse(ApiResponseModel):
    grade_id: str
    subject_ids: list[str]
    subject_values: list[str]


class SiteUnlistedDictionaryResponse(ApiResponseModel):
    grade: list[str]
    subject: list[str]


class SiteUpdateBannerResponse(ApiResponseModel):
    action_label: str
    created_at: int
    id: str
    image_bytes: int
    image_fit: str
    image_key: str
    image_mime: str
    image_storage: str
    image_url: str | None
    is_visible: bool
    kicker: str
    revision: int
    sort_order: int
    subtitle: str
    target_type: str
    target_value: str
    title: str
    updated_at: int


SiteUpdateCategoryResponse = SiteCreateCategoryResponse


SiteUpdateDictionaryResponse = SiteAdoptDictionaryItemsItem


SiteUpdateDocumentResponse = SiteDocumentsItemsItem


SiteUpdateNoticeResponse = SiteCreateNoticeResponse


SiteUploadBannerImageResponse = SiteUpdateBannerResponse
