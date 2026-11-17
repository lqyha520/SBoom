"""工作台扩展接口，素材下载同样要求管理员权限。"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from app.blocking import run_sync_in
from app.deps import require_admin
from app.http_limits import limited_body
from app.library_deps import no_store
from app.models.responses import AssetPageResponse, AssetResponse
from app.models.xhs_workflow import AssetMetadata, AssetUpdate, TemplateCreate
from app.models.xhs_workspace_api_responses import (
    XhsWorkspaceCalendarResponse,
    XhsWorkspaceCreateTutorialResponse,
    XhsWorkspaceIdeaPreviewResponse,
    XhsWorkspaceTodayResponse,
    XhsWorkspaceTutorialResponse,
)
from app.services import xhs_workspace as service
from app.services.user_store import CurrentUser
from app.upload_admission import bounded_upload

router = APIRouter(prefix='/api/v1/admin/xhs-workspace', tags=['小红书工作台'], dependencies=[Depends(no_store)])


@router.get('/assets', response_model=AssetPageResponse, response_model_exclude_unset=True)
def assets(q: str = Query('', max_length=120), kind: Literal['', 'image', 'video', 'template', 'media'] = '', archived: bool = False, page: int = Query(1, ge=1), admin: CurrentUser = Depends(require_admin)):
    return service.list_assets(admin.id, q, kind, archived, page)


@router.post('/assets/file', status_code=201, response_model=AssetResponse, response_model_exclude_unset=True)
@bounded_upload(2)
async def upload(request: Request, title: str = Query(min_length=1, max_length=120), admin: CurrentUser = Depends(require_admin)):
    media_type = request.headers.get('content-type', '').split(';')[0]
    if media_type not in ('image/png', 'image/jpeg', 'image/webp', 'video/mp4'):
        raise HTTPException(415, detail={'error': '仅支持 PNG、JPEG、WebP 和 MP4'})
    limit = (40 if media_type == 'video/mp4' else 10) * 1024 * 1024
    content = await limited_body(request, limit, error='图片最多 10 MB，视频最多 40 MB')
    if not content:
        raise HTTPException(422, detail={'error': '不能上传空文件'})
    return await run_sync_in('media', service.create_asset, admin.id, AssetMetadata(title=title).model_dump(), media_type, content)


@router.post('/assets/template', status_code=201, response_model=AssetResponse, response_model_exclude_unset=True)
def template(body: TemplateCreate, admin: CurrentUser = Depends(require_admin)):
    return service.create_asset(admin.id, body.data.model_dump(), 'application/x-xhs-template', template=body.template.model_dump())


@router.put('/assets/{identifier}', response_model=AssetResponse, response_model_exclude_unset=True)
def update(identifier: str, body: AssetUpdate, admin: CurrentUser = Depends(require_admin)):
    return service.update_asset(admin.id, identifier, body.revision, body.data.model_dump())


@router.get('/assets/{identifier}', response_model=AssetResponse, response_model_exclude_unset=True)
def asset(identifier: str, admin: CurrentUser = Depends(require_admin)):
    return service.get_asset(admin.id, identifier)


@router.get('/assets/{identifier}/file', response_class=FileResponse, responses={
    status: {'content': {media: {'schema': {'type': 'string', 'format': 'binary'}}
                         for media in ('image/png', 'image/jpeg', 'image/webp', 'video/mp4')}}
    for status in (200, 206)
})
def download(identifier: str, admin: CurrentUser = Depends(require_admin)):
    return _asset_file(admin.id, identifier, 'attachment')


@router.get('/assets/{identifier}/preview', response_class=FileResponse, responses={
    status: {'content': {media: {'schema': {'type': 'string', 'format': 'binary'}}
                         for media in ('image/png', 'image/jpeg', 'image/webp', 'video/mp4')}}
    for status in (200, 206)
})
def preview_asset(identifier: str, admin: CurrentUser = Depends(require_admin)):
    return _asset_file(admin.id, identifier, 'inline')


def _asset_file(admin_id: int, identifier: str, disposition: Literal['attachment', 'inline']):
    from app.services.xhs_asset_storage import owned_file
    path, media_type = owned_file(admin_id, identifier)
    extension = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'video/mp4': 'mp4'}[media_type]
    return FileResponse(path, media_type=media_type, filename=f'asset.{extension}', content_disposition_type=disposition,
                        headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store'})


@router.get('/assets/{identifier}/thumbnail', response_class=Response,
            responses={200: {'content': {'image/jpeg': {'schema': {'type': 'string', 'format': 'binary'}}}}})
async def thumbnail(identifier: str, admin: CurrentUser = Depends(require_admin)):
    content = await run_sync_in('media', service.asset_thumbnail, admin.id, identifier)
    return Response(content, media_type='image/jpeg', headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store'})


@router.delete('/assets/{identifier}', status_code=204)
def delete(identifier: str, revision: int = Query(ge=1), admin: CurrentUser = Depends(require_admin)):
    service.delete_asset(admin.id, identifier, revision)
    return Response(status_code=204)


@router.get('/calendar', response_model=XhsWorkspaceCalendarResponse, response_model_exclude_unset=True)
def calendar(start: datetime, end: datetime, account: str = Query('', max_length=120),
             unscheduled_page: int = Query(1, ge=1), admin: CurrentUser = Depends(require_admin)):
    return service.calendar(admin.id, start, end, account, unscheduled_page)


@router.get('/today', response_model=XhsWorkspaceTodayResponse, response_model_exclude_unset=True)
def today(start: datetime, end: datetime, category: Literal['review', 'publish', 'analytics'] = 'review', page: int = Query(1, ge=1), admin: CurrentUser = Depends(require_admin)):
    return service.today_tasks(admin.id, start, end, category, page)


@router.get('/analytics/{identifier}/idea-preview', response_model=XhsWorkspaceIdeaPreviewResponse, response_model_exclude_unset=True)
def idea_preview(identifier: str, checkpoint: int = Query(7, ge=1, le=7), admin: CurrentUser = Depends(require_admin)):
    if checkpoint not in (1, 3, 7):
        raise HTTPException(422, detail={'error': '请选择第 1、3 或 7 天'})
    return service.idea_preview(admin.id, identifier, checkpoint)


@router.get('/tutorial', response_model=XhsWorkspaceTutorialResponse, response_model_exclude_unset=True)
def tutorial(admin: CurrentUser = Depends(require_admin)):
    return service.tutorial(admin.id)


@router.post('/tutorial', response_model=XhsWorkspaceCreateTutorialResponse, response_model_exclude_unset=True)
def create_tutorial(admin: CurrentUser = Depends(require_admin)):
    return service.tutorial(admin.id, create=True)
