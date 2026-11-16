"""Private paper archives belonging exclusively to workbench users."""


import tempfile

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError

from app.blocking import run_sync
from app.config import get_settings
from app.deps import require_user
from app.http_contracts import binary_responses
from app.http_limits import limited_body
from app.library_deps import no_store, require_library_user
from app.library_files import asset_response
from app.models.library import (
    ArchiveBatchDelete,
    ArchiveCreate,
    ArchiveDeletePreview,
    ArchiveDeleteResult,
    ArchiveDeleteSelection,
    ArchiveUpdate,
    FolderInput,
)
from app.models.library_api_responses import (
    LibraryCreateFolderResponse,
    LibraryFoldersResponse,
    LibraryRenameFolderResponse,
    LibrarySummaryResponse,
)
from app.models.responses import ArchiveDetailResponse, ArchivePageResponse
from app.services import catalog_import
from app.services import paper_library as library
from app.services.paper_storage import MAX_PAGES
from app.services.resource_admission import admitted_media
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1/library", tags=["试卷库"], dependencies=[Depends(no_store)])


async def _limited_body(request: Request, limit: int, content_type: str):
    if request.headers.get("content-type", "").split(";")[0].strip() != content_type:
        raise HTTPException(415, detail={"error": "文件或请求格式不正确"})
    return await limited_body(request, limit, error="请求过大，请减少页数后重试")


@router.get("/summary", response_model=LibrarySummaryResponse, response_model_exclude_unset=True)
def summary(user: CurrentUser = Depends(require_library_user)):
    return library.library_summary(user.id)


@router.get("/papers", response_model=ArchivePageResponse, response_model_exclude_unset=True)
def list_papers(q: str = Query("", max_length=120), grade: str = Query("", max_length=80),
                subject: str = Query("", max_length=80), folder_id: str | None = Query(None, max_length=64),
                favorite: bool = False, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000),
                user: CurrentUser = Depends(require_library_user)):
    return library.list_papers(user.id, q, grade, subject, folder_id, favorite, limit, offset)


@router.post("/papers", status_code=201, response_model=ArchiveDetailResponse, response_model_exclude_unset=True)
async def create_paper(request: Request, user: CurrentUser = Depends(require_user)):
    raw = await _limited_body(request, 2 * 1024 * 1024 + 4096, "application/json")
    try:
        body = ArchiveCreate.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422, detail={"error": "试卷快照不完整或格式不正确，请刷新后重试"}) from exc
    return await run_sync(library.create_paper, user.id, body)


@router.post("/papers/batch-delete/preview", response_model=ArchiveDeletePreview)
def preview_delete(body: ArchiveDeleteSelection, user: CurrentUser = Depends(require_library_user)):
    return library.preview_delete(user.id, body.ids)


@router.post("/papers/batch-delete", response_model=ArchiveDeleteResult)
def batch_delete(body: ArchiveBatchDelete, user: CurrentUser = Depends(require_library_user)):
    return library.batch_delete(user.id, body.ids)


@router.get("/papers/{paper_id}", response_model=ArchiveDetailResponse, response_model_exclude_unset=True)
def get_paper(paper_id: str, user: CurrentUser = Depends(require_library_user)):
    return library.get_paper(user.id, paper_id)


@router.post("/import", status_code=201, response_model=ArchiveDetailResponse, response_model_exclude_unset=True)
@catalog_import.admitted_import
async def import_image_paper(request: Request,
                             request_id: str = Query(..., pattern=r"^[a-f0-9]{64}$"),
                             title: str = Query(..., min_length=1, max_length=240),
                             grade: str = Query(..., min_length=1, max_length=80),
                             subject: str = Query(..., min_length=1, max_length=80),
                             keyword: str = Query("", max_length=500),
                             question_types: str = Query("", max_length=500),
                             question_count: int = Query(0, ge=0, le=24 * MAX_PAGES),
                             folder_id: str | None = Query(None, max_length=64),
                             user: CurrentUser = Depends(require_library_user)):
    """保存图片出题的 PDF 到私人云端库；创建公共草稿和发布仍是独立操作。"""
    from app.models import GameType
    types = list(dict.fromkeys(value.strip() for value in question_types.split(",") if value.strip()))
    if any(value not in {kind.value for kind in GameType} for value in types):
        raise HTTPException(422, detail={"error": "未知的题型"})
    content = await _limited_body(request, catalog_import.MAX_IMPORT_BYTES, "application/pdf")
    return await run_sync(catalog_import.import_paper, user.id, title, grade, subject, content, "student",
                          keyword=keyword, question_types=types, question_count=question_count,
                          request_id=request_id, folder_id=folder_id)


@router.patch("/papers/{paper_id}", response_model=ArchiveDetailResponse, response_model_exclude_unset=True)
@router.put("/papers/{paper_id}", response_model=ArchiveDetailResponse, response_model_exclude_unset=True)
def update_paper(paper_id: str, body: ArchiveUpdate, user: CurrentUser = Depends(require_library_user)):
    return library.update_paper(user.id, paper_id, body)


@router.delete("/papers/{paper_id}", status_code=204)
def delete_paper(paper_id: str, user: CurrentUser = Depends(require_library_user)):
    library.delete_paper(user.id, paper_id)
    return Response(status_code=204)


@router.put("/papers/{paper_id}/files", response_model=ArchiveDetailResponse, response_model_exclude_unset=True)
async def upload_files(paper_id: str, request: Request, user: CurrentUser = Depends(require_user)):
    await run_sync(library.get_paper, user.id, paper_id)
    with admitted_media(), tempfile.TemporaryFile() as content:
        if request.headers.get("content-type", "").split(";")[0] != "application/zip":
            raise HTTPException(415, detail={"error": "请选择 ZIP 文件包"})
        limit = get_settings().archive_max_bundle_mb * 1024 * 1024
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, detail={"error": "文件包过大"})
            await run_sync(content.write, chunk)
        content.seek(0)
        return await run_sync(library.publish_bundle, user.id, paper_id, content)


@router.get("/assets/{asset_id}", response_class=Response, responses=binary_responses('application/pdf', 'image/jpeg', 'image/png', 'image/webp', partial=True))
def get_asset(asset_id: str, user: CurrentUser = Depends(require_library_user)):
    return asset_response(library.owned_asset(user.id, asset_id))


@router.get("/folders", response_model=LibraryFoldersResponse, response_model_exclude_unset=True)
def folders(user: CurrentUser = Depends(require_library_user)):
    return library.list_folders(user.id)


@router.post("/folders", status_code=201, response_model=LibraryCreateFolderResponse, response_model_exclude_unset=True)
def create_folder(body: FolderInput, user: CurrentUser = Depends(require_library_user)):
    return library.save_folder(user.id, body.name)


@router.patch("/folders/{folder_id}", response_model=LibraryRenameFolderResponse, response_model_exclude_unset=True)
@router.put("/folders/{folder_id}", response_model=LibraryRenameFolderResponse, response_model_exclude_unset=True)
def rename_folder(folder_id: str, body: FolderInput, user: CurrentUser = Depends(require_library_user)):
    return library.save_folder(user.id, body.name, folder_id)


@router.delete("/folders/{folder_id}", status_code=204)
def delete_folder(folder_id: str, user: CurrentUser = Depends(require_library_user)):
    library.delete_folder(user.id, folder_id)
    return Response(status_code=204)
