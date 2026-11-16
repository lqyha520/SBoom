"""关键读接口的响应契约；与输入校验分开，兼容已保存的历史快照。"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.xhs_workflow import AssetMetadata, CoverTemplate, Draft, Idea, Kind, Material, Publication


class LooseResponse(BaseModel):
    """为仍需兼容历史快照的读接口声明核心字段，同时保留新增字段。"""

    model_config = ConfigDict(extra='allow')


class PageLooseResponse(LooseResponse):
    items: list[Any] = Field(default_factory=list)
    total: int | None = None


class PayoutSnapshotResponse(LooseResponse):
    revision: int
    amount_fen: int
    beneficiary_name: str
    payee: dict[str, Any] | None = None


class PayoutBatchItemResponse(LooseResponse):
    statement_id: str
    status: Literal['pending', 'failed', 'paid', 'cancelled']
    statement_status: str
    reason: str
    receipt: str
    snapshot: PayoutSnapshotResponse


class PayoutBatchSummaryResponse(LooseResponse):
    id: str
    name: str
    status: Literal['active', 'completed', 'cancelled']
    revision: int
    created_at: int
    total_fen: int
    item_count: int


class PayoutBatchResponse(PayoutBatchSummaryResponse):
    items: list[PayoutBatchItemResponse]


class PayoutBatchPageResponse(BaseModel):
    items: list[PayoutBatchSummaryResponse]
    total: int


class PayoutImportIssueResponse(LooseResponse):
    statement_id: str
    reasons: list[str]


class PayoutImportResponse(BaseModel):
    paid: int
    failed: int
    pending: int
    blocked: int
    duplicate: bool = False
    issues: list[PayoutImportIssueResponse] = Field(default_factory=list)


class PayoutMatchResponse(LooseResponse):
    statement_id: str
    status: str | None = None
    amount_fen: int | None = None
    receipt: str = ''
    issues: list[str] = Field(default_factory=list)


class PayoutPreviewResponse(BaseModel):
    items: list[PayoutMatchResponse]
    matched: int
    blocked: int


class PayoutCandidateResponse(LooseResponse):
    id: str
    status: str
    revision: int
    beneficiary_name: str
    net_fen: int
    snapshot: dict[str, Any]
    payout_issues: list[str] = Field(default_factory=list)
    batch_id: str | None = None


class PayoutCandidatePageResponse(BaseModel):
    items: list[PayoutCandidateResponse]
    total: int


class PayoutSelectionResponse(BaseModel):
    items: list[PayoutCandidateResponse]
    total_fen: int
    blocked: int


class SettlementSummaryCount(BaseModel):
    count: int
    amount_fen: int
    unknown: int = 0


class SettlementSummaryResponse(LooseResponse):
    available: SettlementSummaryCount
    holding: SettlementSummaryCount
    exception: SettlementSummaryCount
    pending: SettlementSummaryCount
    reviewing: SettlementSummaryCount
    approved: SettlementSummaryCount
    paid: SettlementSummaryCount
    stalled: int
    review_overdue: int
    payout_overdue: int
    overdue: int


class SettlementListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int


class GenerationPolicyResponse(BaseModel):
    revision: str
    timeout_ms: int
    task_timeout_seconds: float


class GenerationUsageResponse(BaseModel):
    requests: int
    succeeded: int
    failed: int
    running: int
    unknown: int
    quota_used: int
    model_calls: int
    reported_calls: int
    prompt_tokens: int
    completion_tokens: int
    daily_limit: int
    failure_limit: int


class ArchiveAssetResponse(BaseModel):
    id: str
    kind: Literal['pdf', 'page']
    page_number: int
    mime_type: str
    byte_size: int
    url: str
    edition: Literal['answers'] | None = None
    label: str | None = None


class ArchiveSummaryResponse(BaseModel):
    id: str
    source_id: str
    version: int
    title: str
    grade: str
    subject: str
    keyword: str
    question_count: int
    folder_id: str | None
    folder_name: str | None
    group_id: str
    group_name: str
    favorite: bool
    file_status: Literal['pending', 'uploading', 'failed', 'ready']
    file_error: str
    page_count: int
    created_at: int
    updated_at: int
    publication_id: str | None
    thumbnail_id: str | None
    thumbnail_url: str | None


class ArchiveSnapshotResponse(BaseModel):
    # 导入 PDF 没有可编辑题目，历史卷面还含前端排版扩展字段，读取时不能套用创建校验。
    model_config = ConfigDict(extra='allow')
    schema_version: Literal[1, 2]
    paper: dict
    additional_papers: list[dict] = Field(default_factory=list)
    collection_title: str = ''
    template: dict
    style: dict
    export_options: dict


class ArchiveDetailResponse(ArchiveSummaryResponse):
    snapshot: ArchiveSnapshotResponse
    assets: list[ArchiveAssetResponse]


class ArchivePageResponse(BaseModel):
    items: list[ArchiveSummaryResponse]
    total: int
    has_more: bool


class WorkflowChildResponse(BaseModel):
    id: str
    kind: Kind
    title: str
    status: str


class WorkflowParentResponse(BaseModel):
    id: str
    kind: Kind
    title: str
    revision: int


class WorkflowRecordResponse(BaseModel):
    id: str
    admin_id: int
    parent_id: str | None
    title: str
    status: str
    revision: int
    created_at: datetime
    updated_at: datetime
    children: list[WorkflowChildResponse] = Field(default_factory=list)
    parent: WorkflowParentResponse | None = None


class PublicationDataResponse(Publication):
    draft_snapshot: Draft | None = None
    draft_revision: int | None = None


class IdeaRecordResponse(WorkflowRecordResponse):
    kind: Literal['ideas']
    data: Idea


class MaterialRecordResponse(WorkflowRecordResponse):
    kind: Literal['materials']
    data: Material


class DraftRecordResponse(WorkflowRecordResponse):
    kind: Literal['drafts']
    data: Draft


class PublicationRecordResponse(WorkflowRecordResponse):
    kind: Literal['publications']
    data: PublicationDataResponse


WorkflowResponse = Annotated[IdeaRecordResponse | MaterialRecordResponse | DraftRecordResponse | PublicationRecordResponse, Field(discriminator='kind')]


class WorkflowPageResponse(BaseModel):
    items: list[WorkflowResponse]
    total: int
    page: int
    page_size: int


class AssetResponse(BaseModel):
    id: str
    media_type: str
    size_bytes: int
    data: AssetMetadata
    template: CoverTemplate | None
    revision: int
    created_at: datetime
    updated_at: datetime
    duplicate: bool = False


class AssetPageResponse(BaseModel):
    items: list[AssetResponse]
    total: int
    used_bytes: int
    quota_bytes: int
