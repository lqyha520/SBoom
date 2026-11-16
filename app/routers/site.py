"""小程序运营内容接口：后台管理端（增删改查 / 排序 / 上下线）与小程序端（只读）。"""


from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.blocking import run_sync
from app.deps import require_admin
from app.http_contracts import binary_responses
from app.http_limits import limited_body
from app.library_deps import no_store, optional_mini_user
from app.library_files import asset_response
from app.models.site import (
    BannerInput,
    BannerUpdate,
    CategoryInput,
    CategoryUpdate,
    DictionaryAdopt,
    DictionaryInput,
    DictionaryLinksUpdate,
    DictionaryReorder,
    DictionaryUpdate,
    DocumentUpdate,
    HomeSettings,
    NoticeInput,
    NoticeUpdate,
    ReorderInput,
)
from app.models.site_api_responses import (
    SiteAdoptDictionaryResponse,
    SiteAnalyticsResponse,
    SiteBannersResponse,
    SiteCategoriesResponse,
    SiteClearBannerImageResponse,
    SiteCreateBannerResponse,
    SiteCreateCategoryResponse,
    SiteCreateDictionaryResponse,
    SiteCreateNoticeResponse,
    SiteDictionaryLinksResponse,
    SiteDictionaryResponse,
    SiteDocumentResponse,
    SiteDocumentsResponse,
    SiteHomeResponse,
    SiteNoticesResponse,
    SiteOrderCategoriesResponse,
    SiteReorderDictionaryResponse,
    SiteSetDictionaryLinksResponse,
    SiteUnlistedDictionaryResponse,
    SiteUpdateBannerResponse,
    SiteUpdateCategoryResponse,
    SiteUpdateDictionaryResponse,
    SiteUpdateDocumentResponse,
    SiteUpdateNoticeResponse,
    SiteUploadBannerImageResponse,
)
from app.services import site_content as site
from app.services.mini_auth import MiniUser
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1/site", tags=["小程序内容"], dependencies=[Depends(no_store)])
admin_router = APIRouter(prefix="/api/v1/admin/site", tags=["小程序内容管理"], dependencies=[Depends(no_store)])

_IMAGE_LIMIT = site.MAX_IMAGE_BYTES


async def _image_body(request: Request) -> tuple[str, bytes]:
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        raise HTTPException(415, detail={"error": "请上传图片文件"})
    return content_type, await limited_body(request, _IMAGE_LIMIT, error="Banner 图片不能超过 2 MB")


# ─── 小程序端 ───

@router.get("/home", response_model=SiteHomeResponse, response_model_exclude_unset=True)
def home(user: MiniUser | None = Depends(optional_mini_user)):
    """首页一次性拿全：Banner、公告、分类、年级科目字典。"""
    return {**site.home_payload(), "banner_mode": site.home_settings()["banner_mode"]}


@router.get("/banners/{banner_id}/image", response_class=Response, responses=binary_responses('image/jpeg', 'image/png', 'image/webp', partial=True))
def banner_image(banner_id: str, v: int | None = None, user: MiniUser | None = Depends(optional_mini_user)):
    asset = site.banner_asset(banner_id)
    # 仅当前版本可长期缓存；旧版本 URL 不能把新内容永久缓存到错误的键下。
    cache = "public, max-age=31536000, immutable" if v == asset["revision"] else "public, max-age=60"
    return asset_response(asset, cache_control=cache)


@router.get("/documents/{key}", response_model=SiteDocumentResponse, response_model_exclude_unset=True)
def document(key: str):
    row = site.get_document(key)
    return {"key": row["key"], "title": row["title"], "body": row["body"], "updated_at": row["updated_at"]}


# ─── 后台 · 分类 ───

@admin_router.get("/categories", response_model=SiteCategoriesResponse, response_model_exclude_unset=True)
def categories(user: CurrentUser = Depends(require_admin)):
    return site.list_categories()


@admin_router.post("/categories", status_code=201, response_model=SiteCreateCategoryResponse, response_model_exclude_unset=True)
def create_category(body: CategoryInput, user: CurrentUser = Depends(require_admin)):
    return site.create_category(body)


@admin_router.put("/categories/order", response_model=SiteOrderCategoriesResponse, response_model_exclude_unset=True)
def order_categories(body: ReorderInput, user: CurrentUser = Depends(require_admin)):
    """必须注册在 /categories/{category_id} 之前，否则 "order" 会被当成路径参数。"""
    return site.reorder_categories(body.ids)


@admin_router.put("/categories/{category_id}", response_model=SiteUpdateCategoryResponse, response_model_exclude_unset=True)
def update_category(category_id: str, body: CategoryUpdate, user: CurrentUser = Depends(require_admin)):
    return site.update_category(category_id, body)


@admin_router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_admin)):
    site.delete_category(category_id, revision)
    return Response(status_code=204, headers={"Cache-Control": "private, no-store"})


# ─── 后台 · Banner ───

@admin_router.get("/home-settings", response_model=HomeSettings)
def home_settings(user: CurrentUser = Depends(require_admin)):
    return site.home_settings()


@admin_router.put("/home-settings", response_model=HomeSettings)
def save_home_settings(body: HomeSettings, user: CurrentUser = Depends(require_admin)):
    return site.save_home_settings(body)

@admin_router.get("/banners", response_model=SiteBannersResponse, response_model_exclude_unset=True)
def banners(user: CurrentUser = Depends(require_admin)):
    return site.list_banners()


@admin_router.post("/banners", status_code=201, response_model=SiteCreateBannerResponse, response_model_exclude_unset=True)
def create_banner(body: BannerInput, user: CurrentUser = Depends(require_admin)):
    return site.create_banner(body)


@admin_router.put("/banners/{banner_id}", response_model=SiteUpdateBannerResponse, response_model_exclude_unset=True)
def update_banner(banner_id: str, body: BannerUpdate, user: CurrentUser = Depends(require_admin)):
    return site.update_banner(banner_id, body)


@admin_router.delete("/banners/{banner_id}", status_code=204)
def delete_banner(banner_id: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_admin)):
    site.delete_banner(banner_id, revision)
    return Response(status_code=204, headers={"Cache-Control": "private, no-store"})


@admin_router.put("/banners/{banner_id}/image", response_model=SiteUploadBannerImageResponse, response_model_exclude_unset=True)
async def upload_banner_image(banner_id: str, request: Request, revision: int | None = Query(default=None, ge=1), user: CurrentUser = Depends(require_admin)):
    content_type, content = await _image_body(request)
    return await run_sync(site.save_banner_image, banner_id, content_type, content, revision=revision)


@admin_router.delete("/banners/{banner_id}/image", response_model=SiteClearBannerImageResponse, response_model_exclude_unset=True)
def clear_banner_image(banner_id: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_admin)):
    return site.clear_banner_image(banner_id, revision)


@admin_router.get("/banners/{banner_id}/image", response_class=Response, responses=binary_responses('image/jpeg', 'image/png', 'image/webp', partial=True))
def admin_banner_image(banner_id: str, user: CurrentUser = Depends(require_admin)):
    """后台预览：未发布的 Banner 也能取图。"""
    return asset_response(site.banner_asset(banner_id, require_visible=False))


# ─── 后台 · 公告与弹窗 ───

@admin_router.get("/notices", response_model=SiteNoticesResponse, response_model_exclude_unset=True)
def notices(user: CurrentUser = Depends(require_admin)):
    return site.list_notices()


@admin_router.post("/notices", status_code=201, response_model=SiteCreateNoticeResponse, response_model_exclude_unset=True)
def create_notice(body: NoticeInput, user: CurrentUser = Depends(require_admin)):
    return site.create_notice(body)


@admin_router.put("/notices/{notice_id}", response_model=SiteUpdateNoticeResponse, response_model_exclude_unset=True)
def update_notice(notice_id: str, body: NoticeUpdate, user: CurrentUser = Depends(require_admin)):
    return site.update_notice(notice_id, body)


@admin_router.delete("/notices/{notice_id}", status_code=204)
def delete_notice(notice_id: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_admin)):
    site.delete_notice(notice_id, revision)
    return Response(status_code=204, headers={"Cache-Control": "private, no-store"})


# ─── 后台 · 协议与隐私页 ───

@admin_router.get("/documents", response_model=SiteDocumentsResponse, response_model_exclude_unset=True)
def documents(user: CurrentUser = Depends(require_admin)):
    return site.list_documents()


@admin_router.put("/documents/{key}", response_model=SiteUpdateDocumentResponse, response_model_exclude_unset=True)
def update_document(key: str, body: DocumentUpdate, user: CurrentUser = Depends(require_admin)):
    return site.update_document(key, body)


# ─── 后台 · 年级科目字典 ───

@admin_router.get("/dictionary", response_model=SiteDictionaryResponse, response_model_exclude_unset=True)
def dictionary(kind: str = Query("", max_length=20), parent: str = Query("", max_length=80),
               user: CurrentUser = Depends(require_admin)):
    if kind and kind not in ("grade", "subject", "knowledge_point"):
        raise HTTPException(422, detail={"error": "kind 只能是 grade、subject 或 knowledge_point"})
    return site.list_dictionary(kind, parent)


@admin_router.get("/dictionary/links", response_model=SiteDictionaryLinksResponse, response_model_exclude_unset=True)
def dictionary_links(user: CurrentUser = Depends(require_admin)):
    return site.list_dictionary_links()


@admin_router.put("/dictionary/links/{grade_id}", response_model=SiteSetDictionaryLinksResponse, response_model_exclude_unset=True)
def set_dictionary_links(grade_id: str, body: DictionaryLinksUpdate, user: CurrentUser = Depends(require_admin)):
    return site.set_dictionary_links(grade_id, body.subject_ids)


@admin_router.get("/dictionary/unlisted", response_model=SiteUnlistedDictionaryResponse, response_model_exclude_unset=True)
def unlisted_dictionary(user: CurrentUser = Depends(require_admin)):
    return site.unlisted_dictionary()


@admin_router.post("/dictionary/adopt", response_model=SiteAdoptDictionaryResponse, response_model_exclude_unset=True)
def adopt_dictionary(body: DictionaryAdopt, user: CurrentUser = Depends(require_admin)):
    return site.adopt_dictionary(body.kind, body.values)


@admin_router.post("/dictionary", status_code=201, response_model=SiteCreateDictionaryResponse, response_model_exclude_unset=True)
def create_dictionary(body: DictionaryInput, user: CurrentUser = Depends(require_admin)):
    return site.create_dictionary(body)


@admin_router.post("/dictionary/reorder", response_model=SiteReorderDictionaryResponse, response_model_exclude_unset=True)
def reorder_dictionary(body: DictionaryReorder, user: CurrentUser = Depends(require_admin)):
    return site.reorder_dictionary(body)


@admin_router.put("/dictionary/{item_id}", response_model=SiteUpdateDictionaryResponse, response_model_exclude_unset=True)
def update_dictionary(item_id: str, body: DictionaryUpdate, user: CurrentUser = Depends(require_admin)):
    return site.update_dictionary(item_id, body)


@admin_router.delete("/dictionary/{item_id}", status_code=204)
def delete_dictionary(item_id: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_admin)):
    site.delete_dictionary(item_id, revision)
    return Response(status_code=204, headers={"Cache-Control": "private, no-store"})


# ─── 后台 · 内容数据看板 ───

@admin_router.get("/analytics", response_model=SiteAnalyticsResponse, response_model_exclude_unset=True)
def analytics(user: CurrentUser = Depends(require_admin)):
    return site.admin_analytics()
