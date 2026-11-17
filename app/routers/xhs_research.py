"""管理员发起并查看小红书教育内容趋势采集。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.deps import require_admin
from app.http_contracts import binary_responses
from app.library_deps import no_store
from app.models.xhs_research_api_responses import (
    XhsResearchCreateBatchResponse,
    XhsResearchCreateTaskResponse,
    XhsResearchFailTaskResponse,
    XhsResearchGetBatchResponse,
    XhsResearchGetNoteResponse,
    XhsResearchGetTaskResponse,
    XhsResearchListBatchesResponse,
    XhsResearchListNotesResponse,
    XhsResearchListTasksResponse,
    XhsResearchNoteHistoryResponse,
    XhsResearchSaveMarkResponse,
    XhsResearchSaveResultsResponse,
    XhsResearchStartTaskResponse,
)
from app.services import xhs_research
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1/admin/xhs-research", tags=["小红书选题调研"], dependencies=[Depends(no_store)])

GRADES = {f"{number}年级" for number in ("一", "二", "三", "四", "五", "六", "七", "八", "九")} | {"高一", "高二", "高三"}
SUBJECTS = {"语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "政治"}


class ResearchTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: str = Field(min_length=2, max_length=12)
    subject: str = Field(min_length=2, max_length=12)
    keyword: str = Field(default="", max_length=80)
    period: Literal["day", "week", "half_year", "all"] = "week"
    sort_by: Literal["general", "popular", "latest"] = "popular"
    note_limit: int = Field(default=30, ge=10, le=100)

    @field_validator("grade")
    @classmethod
    def valid_grade(cls, value: str) -> str:
        if value not in GRADES:
            raise ValueError("请选择受支持的年级")
        return value

    @field_validator("subject")
    @classmethod
    def valid_subject(cls, value: str) -> str:
        if value not in SUBJECTS:
            raise ValueError("请选择受支持的科目")
        return value


class ResearchNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_id: str = Field(default="", max_length=80)
    title: str = Field(default="", max_length=300)
    author: str = Field(default="", max_length=120)
    published_text: str = Field(default="", max_length=80)
    likes_text: str = Field(default="", max_length=40)
    likes_count: int | None = Field(default=None, ge=0, le=10_000_000_000)
    url: str = Field(max_length=2000)
    sort_rank: int = Field(default=0, ge=0, le=1000)
    captured_at: str = Field(default="", max_length=40)

    @field_validator("url")
    @classmethod
    def valid_note_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parts = urlsplit(value)
        if parts.scheme != "https" or parts.hostname != "www.xiaohongshu.com":
            raise ValueError("笔记链接必须来自小红书")
        if not parts.path.startswith(("/search_result/", "/explore/")):
            raise ValueError("笔记链接格式不正确")
        return value


class ResearchResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ResearchNote] = Field(max_length=100)


class ResearchFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str = Field(min_length=1, max_length=500)


class ResearchBatchCreate(ResearchTaskCreate):
    keywords: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=1, max_length=20)

    @field_validator('keywords')
    @classmethod
    def nonempty_keywords(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError('每行请输入一个关键词')
        return list(dict.fromkeys(value.strip() for value in values))


class NoteFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id: str = Field(default='', max_length=80)
    q: str = Field(default='', max_length=120)
    author: str = Field(default='', max_length=120)
    exclude: str = Field(default='', max_length=500)
    min_likes: int | None = Field(default=None, ge=0, le=10_000_000_000)
    favorite_only: bool = False
    status: Literal['all', '', 'reference', 'planned', 'done', 'irrelevant'] = 'all'
    hide_seen: bool = False
    sort: Literal['likes_desc', 'likes_asc', 'latest', 'earliest'] = 'likes_desc'
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class NoteMark(BaseModel):
    model_config = ConfigDict(extra='forbid')
    favorite: bool
    status: Literal['', 'reference', 'planned', 'done', 'irrelevant']
    remark: str = Field(default='', max_length=2000)
    revision: int = Field(ge=0)


class NoteExport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filters: NoteFilters
    note_ids: list[Annotated[str, Field(min_length=8, max_length=80)]] | None = Field(default=None, max_length=1000)


@router.post('/batches', status_code=201, summary='创建多关键词采集队列', response_model=XhsResearchCreateBatchResponse, response_model_exclude_unset=True)
def create_batch(body: ResearchBatchCreate, admin: CurrentUser = Depends(require_admin)):
    return xhs_research.create_batch(admin.id, body.model_dump(exclude={'keywords', 'keyword'}), body.keywords)


@router.get('/batches', summary='读取我的采集队列', response_model=XhsResearchListBatchesResponse, response_model_exclude_unset=True)
def list_batches(admin: CurrentUser = Depends(require_admin)):
    return {'items': xhs_research.list_batches(admin.id)}


@router.get('/batches/{batch_id}', summary='读取队列中的任务', response_model=XhsResearchGetBatchResponse, response_model_exclude_unset=True)
def get_batch(batch_id: str, admin: CurrentUser = Depends(require_admin)):
    return xhs_research.get_batch(admin.id, batch_id)


@router.get('/notes', summary='筛选去重后的笔记与我的标记', response_model=XhsResearchListNotesResponse, response_model_exclude_unset=True)
def list_notes(filters: Annotated[NoteFilters, Query()], admin: CurrentUser = Depends(require_admin)):
    return xhs_research.list_notes(admin.id, **filters.model_dump())


@router.put('/notes/{note_id}/mark', summary='保存我的收藏、选题状态和备注', response_model=XhsResearchSaveMarkResponse, response_model_exclude_unset=True)
def save_mark(note_id: str, body: NoteMark, admin: CurrentUser = Depends(require_admin)):
    return xhs_research.save_mark(admin.id, note_id, **body.model_dump())


@router.get('/notes/{note_id}', summary='读取公开参考笔记与我的标记', response_model=XhsResearchGetNoteResponse, response_model_exclude_unset=True)
def get_note(note_id: str, admin: CurrentUser = Depends(require_admin)):
    return xhs_research.get_note(admin.id, note_id)


@router.get('/notes/{note_id}/history', summary='查看历次采集时的点赞快照', response_model=XhsResearchNoteHistoryResponse, response_model_exclude_unset=True)
def note_history(note_id: str, page: int = Query(1, ge=1), admin: CurrentUser = Depends(require_admin)):
    return xhs_research.note_history(note_id, page)


@router.post('/notes/export', summary='导出筛选或选中的笔记为 Excel', response_class=Response, responses=binary_responses('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))
def export_notes(body: NoteExport, admin: CurrentUser = Depends(require_admin)):
    from app.services.xhs_export import export_workbook

    filters = body.filters.model_dump(exclude={'page', 'page_size'})
    result = xhs_research.list_notes(admin.id, **filters, note_ids=body.note_ids, page_size=5000)
    if result['total'] > 5000:
        raise HTTPException(413, detail={'error': '一次最多导出 5000 条，请缩小筛选范围'})
    return Response(export_workbook(result['items']), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="xhs-notes.xlsx"'})


@router.post("/tasks", status_code=201, summary="创建采集任务", response_model=XhsResearchCreateTaskResponse, response_model_exclude_unset=True)
def create_task(body: ResearchTaskCreate, admin: CurrentUser = Depends(require_admin)):
    return xhs_research.create_task(
        admin.id, body.grade, body.subject, body.keyword.strip(), body.period, body.sort_by, body.note_limit
    )


@router.get("/tasks", summary="分页读取采集任务", response_model=XhsResearchListTasksResponse, response_model_exclude_unset=True)
def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    admin: CurrentUser = Depends(require_admin),
):
    total = xhs_research.count_tasks(admin.id)
    items = xhs_research.list_tasks(admin.id, page_size, (page - 1) * page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/tasks/{task_id}", summary="读取任务详情和采集笔记", response_model=XhsResearchGetTaskResponse, response_model_exclude_unset=True)
def get_task(task_id: str, admin: CurrentUser = Depends(require_admin)):
    return xhs_research.get_task(admin.id, task_id)


@router.post("/tasks/{task_id}/start", summary="启动任务", response_model=XhsResearchStartTaskResponse, response_model_exclude_unset=True)
def start_task(task_id: str, admin: CurrentUser = Depends(require_admin)):
    return xhs_research.start_task(admin.id, task_id)


@router.post("/tasks/{task_id}/results", summary="保存本机采集的公开笔记快照", response_model=XhsResearchSaveResultsResponse, response_model_exclude_unset=True)
def save_results(task_id: str, body: ResearchResults, admin: CurrentUser = Depends(require_admin)):
    return xhs_research.save_items(admin.id, task_id, [item.model_dump() for item in body.items])


@router.post("/tasks/{task_id}/failure", summary="记录采集失败", response_model=XhsResearchFailTaskResponse, response_model_exclude_unset=True)
def fail_task(task_id: str, body: ResearchFailure, admin: CurrentUser = Depends(require_admin)):
    return xhs_research.fail_task(admin.id, task_id, body.error.strip())


@router.delete("/tasks/{task_id}", status_code=204, summary="删除任务及笔记快照")
def delete_task(task_id: str, admin: CurrentUser = Depends(require_admin)) -> None:
    xhs_research.delete_task(admin.id, task_id)
