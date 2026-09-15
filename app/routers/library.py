"""Private paper archives belonging exclusively to workbench users."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError

from app.config import get_settings
from app.deps import require_user
from app.library_deps import no_store, require_library_user
from app.library_files import asset_response
from app.models.library import ArchiveCreate, ArchiveUpdate, FolderInput
from app.services import paper_library as library
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1/library", tags=["试卷库"], dependencies=[Depends(no_store)])


async def _limited_body(request: Request, limit: int, content_type: str):
    if request.headers.get("content-type", "").split(";")[0].strip() != content_type:
        raise HTTPException(415, detail={"error": "文件或请求格式不正确"})
    try:
        declared = int(request.headers.get("content-length", "0"))
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "无效的请求长度"}) from exc
    if declared < 0 or declared > limit:
        raise HTTPException(413, detail={"error": "请求过大，请减少页数后重试"})
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > limit:
            raise HTTPException(413, detail={"error": "请求过大，请减少页数后重试"})
        content.extend(chunk)
    return bytes(content)


@router.get("/summary")
def summary(user: CurrentUser = Depends(require_library_user)):
    return library.library_summary(user.id)


@router.get("/papers")
def list_papers(q: str = Query("", max_length=120), grade: str = Query("", max_length=80),
                subject: str = Query("", max_length=80), folder_id: str | None = Query(None, max_length=64),
                favorite: bool = False, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000),
                user: CurrentUser = Depends(require_library_user)):
    return library.list_papers(user.id, q, grade, subject, folder_id, favorite, limit, offset)


@router.post("/papers", status_code=201)
async def create_paper(request: Request, user: CurrentUser = Depends(require_user)):
    raw = await _limited_body(request, 2 * 1024 * 1024 + 4096, "application/json")
    try:
        body = ArchiveCreate.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422, detail={"error": "试卷快照不完整或格式不正确，请刷新后重试"}) from exc
    return await asyncio.to_thread(library.create_paper, user.id, body)


@router.get("/papers/{paper_id}")
def get_paper(paper_id: str, user: CurrentUser = Depends(require_library_user)):
    return library.get_paper(user.id, paper_id)


@router.patch("/papers/{paper_id}")
@router.put("/papers/{paper_id}")
def update_paper(paper_id: str, body: ArchiveUpdate, user: CurrentUser = Depends(require_library_user)):
    return library.update_paper(user.id, paper_id, body)


@router.delete("/papers/{paper_id}", status_code=204)
def delete_paper(paper_id: str, user: CurrentUser = Depends(require_library_user)):
    library.delete_paper(user.id, paper_id)
    return Response(status_code=204)


@router.put("/papers/{paper_id}/files")
async def upload_files(paper_id: str, request: Request, user: CurrentUser = Depends(require_user)):
    await asyncio.to_thread(library.get_paper, user.id, paper_id)
    content = await _limited_body(request, get_settings().archive_max_bundle_mb * 1024 * 1024, "application/zip")
    return await asyncio.to_thread(library.publish_bundle, user.id, paper_id, content)


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str, user: CurrentUser = Depends(require_library_user)):
    return asset_response(library.owned_asset(user.id, asset_id))


@router.get("/folders")
def folders(user: CurrentUser = Depends(require_library_user)):
    return library.list_folders(user.id)


@router.post("/folders", status_code=201)
def create_folder(body: FolderInput, user: CurrentUser = Depends(require_library_user)):
    return library.save_folder(user.id, body.name)


@router.patch("/folders/{folder_id}")
@router.put("/folders/{folder_id}")
def rename_folder(folder_id: str, body: FolderInput, user: CurrentUser = Depends(require_library_user)):
    return library.save_folder(user.id, body.name, folder_id)


@router.delete("/folders/{folder_id}", status_code=204)
def delete_folder(folder_id: str, user: CurrentUser = Depends(require_library_user)):
    library.delete_folder(user.id, folder_id)
    return Response(status_code=204)
