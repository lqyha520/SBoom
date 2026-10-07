"""Guest catalog browsing and authenticated personal / administrator actions."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError

from app.blocking import run_sync
from app.deps import require_admin
from app.http_limits import limited_body
from app.library_deps import no_store, optional_mini_user, require_mini_user
from app.library_files import asset_response
from app.models.catalog import CatalogCreate, CatalogFavorite, CatalogUpdate, CatalogWindow, TypeAccessUpdate
from app.services import catalog_access, catalog_import
from app.services import public_catalog as catalog
from app.services.mini_auth import MiniUser
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1/catalog", tags=["公共试卷库"], dependencies=[Depends(no_store)])
admin_router = APIRouter(prefix="/api/v1/admin/catalog", tags=["公共试卷管理"], dependencies=[Depends(no_store)])


@router.post("/window")
def catalog_window(body: CatalogWindow, user: MiniUser | None = Depends(optional_mini_user)):
    return catalog.revalidate_window(user.id if user else None, body.ids)


@router.get("/summary")
def summary(user: MiniUser | None = Depends(optional_mini_user)):
    return catalog.summary(user.id if user else None)


@router.get("/papers")
def papers(q: str = Query("", max_length=120), grade: str = Query("", max_length=80),
           subject: str = Query("", max_length=80), category: str = Query("", max_length=60),
           favorite: bool = False, downloaded: bool = False, limit: int = Query(20, ge=1, le=50),
           offset: int = Query(0, ge=0, le=100000), sort: Literal["featured", "latest", "popular"] = "featured",
           only_free: bool = False, recent: bool = False, favorite_group: str = Query("", max_length=64), ungrouped: bool = False, topic: str = Query("", max_length=64),
           textbook: str = Query("", max_length=64), term: str = Query("", max_length=64), unit: str = Query("", max_length=64), knowledge: str = Query("", max_length=64),
           pagination: Literal["offset", "cursor"] = "offset", cursor: str = Query("", max_length=2048),
           record: bool = True, user: MiniUser | None = Depends(optional_mini_user)):
    result = catalog.list_papers(user.id if user else None, q, grade, subject, category, favorite, downloaded, limit, offset,
                                 sort=sort, only_free=only_free, recent=recent, favorite_group=favorite_group, ungrouped=ungrouped, topic=topic, textbook=textbook, term=term, unit=unit, knowledge=knowledge, pagination=pagination, cursor=cursor)
    if record and user and q.strip() and offset == 0 and not result["total"]:
        from app.services.mini_experience import record_event
        from app.services.rate_limit import allow
        if allow("search-miss:" + user.id, 20, 60):
            record_event(user.id, "search_miss", detail=q.strip())
    return result


@router.get("/papers/{catalog_id}")
def paper(catalog_id: str, user: MiniUser | None = Depends(optional_mini_user)):
    return catalog.get_paper(user.id if user else None, catalog_id)


@router.put("/papers/{catalog_id}/favorite")
def favorite(catalog_id: str, body: CatalogFavorite, user: MiniUser = Depends(require_mini_user)):
    return catalog.favorite_paper(user.id, catalog_id, body.favorite)


@router.post("/papers/{catalog_id}/download")
def download(catalog_id: str, edition: Literal["original", "student", "answers"] = "original", user: MiniUser = Depends(require_mini_user)):
    return catalog.request_download(user.id, catalog_id, edition)


@router.get("/papers/{catalog_id}/assets/{asset_id}")
def asset(catalog_id: str, asset_id: str, user: MiniUser | None = Depends(optional_mini_user)):
    item = catalog.get_asset(catalog_id, asset_id, user_id=user.id if user else None)
    if item.get("limited_preview"):
        from app.library_files import limited_preview
        return limited_preview(item)
    cache = "private, max-age=86400" if item.get("cache_public_preview") and item["kind"] != "pdf" else None
    return asset_response(item, cache_control=cache)


@admin_router.get("/type-rules")
def type_rules(user: CurrentUser = Depends(require_admin)):
    return catalog_access.list_type_rules()


@admin_router.put("/type-rules/{question_type}")
def update_type_rule(question_type: str, body: TypeAccessUpdate, user: CurrentUser = Depends(require_admin)):
    return catalog_access.update_type_rule(question_type, body)


@admin_router.get("/summary")
def admin_summary(user: CurrentUser = Depends(require_admin)):
    return catalog.admin_summary()


@admin_router.get("/sources")
def sources(q: str = Query("", max_length=120), limit: int = Query(20, ge=1, le=50),
            offset: int = Query(0, ge=0, le=100000), user: CurrentUser = Depends(require_admin)):
    return catalog.list_sources(user.id, q, limit, offset)


@admin_router.get("/papers")
def admin_papers(q: str = Query("", max_length=120), status: Literal["", "draft", "published", "withdrawn"] = "",
                 limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000),
                 user: CurrentUser = Depends(require_admin)):
    return catalog.list_papers(user.id, q=q, limit=limit, offset=offset, admin=True, status=status)


@admin_router.post("/papers", status_code=201)
def create(body: CatalogCreate, user: CurrentUser = Depends(require_admin)):
    return catalog.create_paper(user.id, body)


async def _pdf_body(request: Request, limit: int):
    """读取原始 PDF 上传体（与 library 的 ZIP 上传同款流式限额读取）。"""
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(415, detail={"error": "请上传 PDF 文件"})
    return await limited_body(request, limit, error="PDF 不能超过 32 MB")


@admin_router.post("/import", status_code=201)
@catalog_import.admitted_import
async def import_paper(request: Request,
                       title: str = Query("", max_length=240), grade: str = Query("", max_length=80),
                       subject: str = Query("", max_length=80), description: str = Query("", max_length=2000),
                       category_id: str = Query("", max_length=64),
                       keyword: str = Query("", max_length=500), question_types: str = Query("", max_length=500),
                       question_count: int = Query(0, ge=0, le=10000),
                       mode: Literal["student", "answersOnly", "withAnswers"] = Query("withAnswers"),
                       view_access: Literal["inherit", "free", "vip"] = "inherit",
                       download_access: Literal["inherit", "free", "vip"] = "inherit",
                       download_mode: Literal["pdf", "external"] = "pdf",
                       external_url: str = Query("", max_length=2000), external_code: str = Query("", max_length=100),
                       user: CurrentUser = Depends(require_admin)):
    """手动导入外部 PDF：渲染预览页 → 建归档 → 直接创建公共习题草稿。"""
    try:
        body = CatalogCreate(paper_id="pending-import", title=title, description=description.strip(),
                             category_id=category_id, view_access=view_access, download_access=download_access,
                             download_mode=download_mode, external_url=external_url, external_code=external_code)
    except ValidationError as exc:
        raise HTTPException(422, detail={"error": "下载配置无效，请检查网盘链接、提取码与访问权限"}) from exc
    from app.models import GameType
    types = list(dict.fromkeys(value.strip() for value in question_types.split(",") if value.strip()))
    if any(value not in {kind.value for kind in GameType} for value in types):
        raise HTTPException(422, detail={"error": "未知的题型"})
    content = await _pdf_body(request, catalog_import.MAX_IMPORT_BYTES)
    archive = await run_sync(catalog_import.import_paper, user.id, title, grade, subject, content, mode,
                                      keyword=keyword, question_types=types, question_count=question_count)
    body = body.model_copy(update={"paper_id": archive["id"], "title": archive["title"]})
    return await run_sync(catalog.create_paper, user.id, body)


@admin_router.post("/papers/{catalog_id}/editions/import")
@catalog_import.admitted_import
async def import_edition(catalog_id: str, request: Request,
                         kind: Literal["student", "answers"] = Query("answers"),
                         revision: int | None = Query(None, ge=1), confirm_publication: bool = False,
                         user: CurrentUser = Depends(require_admin)):
    """导入一份外部 PDF 直接挂为该资料的打印版本（默认答案解析版），不单独创建公共条目。"""
    from app.models.engagement import EditionInput
    from app.services import catalog_editions

    detail = await run_sync(catalog.get_paper, user.id, catalog_id, admin=True)
    if revision is not None and revision != detail["revision"]:
        raise HTTPException(409, detail={"error": "资料已更新，请刷新后重试"})
    if detail["status"] == "published" and (revision is None or not confirm_publication):
        raise HTTPException(422, detail={"error": "请核对当前版本及会员权限，确认发布后再上传"})
    content = await _pdf_body(request, catalog_import.MAX_IMPORT_BYTES)
    mode, suffix = ("answersOnly", "答案") if kind == "answers" else ("student", "练习版")
    archive = await run_sync(catalog_import.import_paper, user.id,
                                      f"{detail['title']}·{suffix}", detail["grade"], detail["subject"], content, mode)
    body = EditionInput(revision=detail["revision"], kind=kind, paper_id=archive["id"], confirm_publication=confirm_publication)
    return await run_sync(catalog_editions.assign, user.id, catalog_id, body)


@admin_router.get("/papers/{catalog_id}")
def admin_paper(catalog_id: str, user: CurrentUser = Depends(require_admin)):
    return catalog.get_paper(user.id, catalog_id, admin=True)


@admin_router.put("/papers/{catalog_id}")
def update(catalog_id: str, body: CatalogUpdate, user: CurrentUser = Depends(require_admin)):
    return catalog.update_paper(user.id, catalog_id, body)


@admin_router.delete("/papers/{catalog_id}", status_code=204)
def delete(catalog_id: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_admin)):
    catalog.delete_paper(catalog_id, revision)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@admin_router.get("/papers/{catalog_id}/assets/{asset_id}")
def admin_asset(catalog_id: str, asset_id: str, user: CurrentUser = Depends(require_admin)):
    return asset_response(catalog.get_asset(catalog_id, asset_id, admin=True))
