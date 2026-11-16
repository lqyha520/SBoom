"""admin 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, JsonValue

from app.models.consumer_responses import RenewalResponse


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class AdminClearLlmConfigModelsItem(ApiResponseModel):
    baseUrl: str
    enabled: bool
    hasKey: bool
    id: str
    imageReview: bool
    maxTokens: int
    model: str
    name: str
    samplingMode: str
    thinkingMode: str
    timeout: int
    tokenParameter: str


class AdminClearLlmConfigResponse(ApiResponseModel):
    baseUrl: str
    hasKey: bool
    imageReview: bool
    maxTokens: int
    message: str
    model: str
    models: list[AdminClearLlmConfigModelsItem]
    revision: str
    samplingMode: str
    status: str
    thinkingMode: str
    timeout: int
    tokenParameter: str


class AdminCreateUserResponse(ApiResponseModel):
    id: int
    role: str
    username: str


class AdminDeleteUserResponse(ApiResponseModel):
    status: str


class AdminGenerationTracesRequestsItemTraceCallsItem(ApiResponseModel):
    completion_tokens: float | int | None
    duration_ms: float | int | None = None
    model: str
    prompt_tokens: float | int | None
    stage: str
    status: str


class AdminGenerationTracesRequestsItemTraceProgress(ApiResponseModel):
    batch: float | int | None = None
    completed_questions: float | int | None = None
    total_batches: float | int | None = None


class AdminGenerationTracesRequestsItemTraceRejectionsItem(ApiResponseModel):
    count: float | int
    reason: str
    stage: str


class AdminGenerationTracesRequestsItemTraceStagesItem(ApiResponseModel):
    duration_ms: float | int
    stage: str
    status: str


class AdminGenerationTracesRequestsItemTrace(ApiResponseModel):
    calls: list[AdminGenerationTracesRequestsItemTraceCallsItem]
    elapsed_ms: float | int
    phase: str
    progress: AdminGenerationTracesRequestsItemTraceProgress
    rejections: list[AdminGenerationTracesRequestsItemTraceRejectionsItem]
    revision: str
    source: str
    stages: list[AdminGenerationTracesRequestsItemTraceStagesItem]
    version: float | int


class AdminGenerationTracesRequestsItem(ApiResponseModel):
    completion_tokens: int
    created_at: int
    finished_at: int
    kind: str
    model_calls: int
    prompt_tokens: int
    replay_count: int
    reported_calls: int
    request_id: str
    status: str
    trace: AdminGenerationTracesRequestsItemTrace | None
    user_id: int


class AdminGenerationTracesResponse(ApiResponseModel):
    requests: list[AdminGenerationTracesRequestsItem]


class AdminGetLlmConfigResponse(ApiResponseModel):
    baseUrl: str
    enabled: bool
    hasKey: bool
    id: str
    imageReview: bool
    maxTokens: int
    model: str
    models: list[AdminClearLlmConfigModelsItem]
    name: str
    revision: str
    samplingMode: str
    thinkingMode: str
    timeout: int
    tokenParameter: str


class AdminGetUserTemplateResponse(ApiResponseModel):
    template: dict[str, JsonValue]


class AdminListFeedbacksFeedbacksItem(ApiResponseModel):
    comment: str
    created_at: str | datetime
    game_id: str
    id: int
    is_oob: int
    user_id: int | None
    username: str


class AdminListFeedbacksResponse(ApiResponseModel):
    feedbacks: list[AdminListFeedbacksFeedbacksItem]


class AdminListLlmModelsResponse(ApiResponseModel):
    count: int
    models: list[str]
    status: str


class AdminListUserTemplatesTemplatesItem(ApiResponseModel):
    id: int
    name: str
    updated_at: str | datetime


class AdminListUserTemplatesResponse(ApiResponseModel):
    templates: list[AdminListUserTemplatesTemplatesItem]


class AdminListUsersUsersItem(ApiResponseModel):
    created_at: str | datetime
    id: int
    is_active: int
    is_super_admin: bool
    permissions_revision: int
    role: str
    template_count: int
    username: str


class AdminListUsersResponse(ApiResponseModel):
    limit: int
    offset: int
    total: int
    users: list[AdminListUsersUsersItem]


class AdminMenuOptionsConfiguration(ApiResponseModel):
    enabled: bool
    ios_enabled: bool
    missing: list[str]
    payment_callback: str
    ready: bool
    refund_callback: str


class AdminMenuOptionsItemsItem(ApiResponseModel):
    created_at: int | None = None
    file_status: str | None = None
    grade: str | None = None
    id: str
    is_visible: bool | None = None
    kind: str | None = None
    label: str | None = None
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    parent: str | None = None
    question_count: int | None = None
    revision: int | None = None
    sort_order: int | None = None
    status: str | None = None
    subject: str | None = None
    title: str | None = None
    updated_at: int | None = None
    value: str | None = None


class AdminMenuOptionsVirtualConfiguration(ApiResponseModel):
    enabled: bool
    env: int
    ios_enabled: bool
    missing: list[str]
    mode: str
    offer_id: str
    ready: bool
    sandbox: bool


class AdminMenuOptionsBase(ApiResponseModel):
    checkout_channel: str | None = None
    checkout_enabled: bool | None = None
    configuration: AdminMenuOptionsConfiguration | None = None
    has_more: bool | None = None
    ios_enabled: bool | None = None
    items: list[AdminMenuOptionsItemsItem] | None = None
    next_cursor: str | None = None
    renewal: RenewalResponse | None = None
    total: int | None = None
    virtual_configuration: AdminMenuOptionsVirtualConfiguration | None = None


class AdminDataOptionsResponse(AdminMenuOptionsBase):
    items: list[AdminMenuOptionsItemsItem]


class AdminPaymentOptionsResponse(AdminMenuOptionsBase):
    checkout_channel: str
    checkout_enabled: bool
    ios_enabled: bool


AdminMenuOptionsResponse = AdminDataOptionsResponse | AdminPaymentOptionsResponse


class AdminModelHealthModelsItem(ApiResponseModel):
    average_seconds: float | None
    failures: int
    fallback_calls: int
    id: str
    last_seconds: float | None
    retry_after_seconds: int
    state: str
    success_rate: float | None
    successes: int


class AdminModelHealthResponse(ApiResponseModel):
    models: list[AdminModelHealthModelsItem]
    revision: str
    task_timeout_seconds: float
    timeout_ms: int


class AdminPermissionCatalogMenusItem(ApiResponseModel):
    actions: list[str]
    group: str
    id: str
    label: str
    super_only: bool


class AdminPermissionCatalogResponse(ApiResponseModel):
    actions: dict[str, str]
    menus: list[AdminPermissionCatalogMenusItem]


class AdminSaveLlmConfigResponse(ApiResponseModel):
    baseUrl: str
    enabled: bool | None = None
    hasKey: bool
    id: str | None = None
    imageReview: bool
    maxTokens: int
    message: str
    model: str
    models: list[AdminClearLlmConfigModelsItem]
    name: str | None = None
    revision: str
    samplingMode: str
    status: str
    thinkingMode: str
    timeout: int
    tokenParameter: str


class AdminStatsGenerationUsage(ApiResponseModel):
    completion_tokens: int
    daily_limit: int
    failed: int
    failure_limit: int
    model_calls: int
    prompt_tokens: int
    quota_used: int
    reported_calls: int
    requests: int
    running: int
    succeeded: int
    unknown: int


class AdminStatsServer(ApiResponseModel):
    encryption: str
    model: str
    version: str


class AdminStatsResponse(ApiResponseModel):
    activeUsers: int
    admins: int
    feedbacks: int
    feedbacksOob: int
    generationUsage: AdminStatsGenerationUsage
    llmConfigured: bool
    securityWarnings: list[str]
    server: AdminStatsServer
    templates: int
    users: int


class AdminTailLogsResponse(ApiResponseModel):
    logs: str


class AdminTestLlmResponse(ApiResponseModel):
    reply: str
    status: str


class AdminTestLlmGenerationResponse(ApiResponseModel):
    reply: str
    seconds: float
    status: str


class AdminUpdatePermissionsResponse(ApiResponseModel):
    admin_permissions: dict[str, list[str]]
    id: int
    is_super_admin: bool
    permissions_revision: int
    username: str


AdminUpdateUserResponse = AdminDeleteUserResponse


class AdminUserPermissionsResponse(ApiResponseModel):
    admin_permissions: dict[str, list[str]]
    id: int
    is_super_admin: bool
    permissions_revision: int
    username: str
