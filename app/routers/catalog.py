"""Guest catalog browsing and authenticated personal / administrator actions."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from app.deps import require_admin
from app.library_deps import no_store, optional_mini_user, require_mini_user
from app.library_files import asset_response
from app.models.catalog import CatalogCreate, CatalogFavorite, CatalogUpdate, TypeAccessUpdate
from app.services import catalog_access
from app.services.mini_auth import MiniUser
from app.services import public_catalog as catalog
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1/catalog", tags=["公共试卷库"], dependencies=[Depends(no_store)])
admin_router = APIRouter(prefix="/api/v1/admin/catalog", tags=["公共试卷管理"], dependencies=[Depends(no_store)])


@router.get("/summary")
def summary(user: MiniUser | None = Depends(optional_mini_user)):
    return catalog.summary(user.id if user else None)


@router.get("/papers")
def papers(q: str = Query("", max_length=120), grade: str = Query("", max_length=80),
           subject: str = Query("", max_length=80), category: str = Query("", max_length=60),
           favorite: bool = False, downloaded: bool = False, limit: int = Query(20, ge=1, le=50),
           offset: int = Query(0, ge=0, le=100000), sort: Literal["featured", "latest", "popular"] = "featured",
           only_free: bool = False, recent: bool = False, favorite_group: str = Query("", max_length=64), topic: str = Query("", max_length=64),
           textbook: str = Query("", max_length=64), term: str = Query("", max_length=64), unit: str = Query("", max_length=64), knowledge: str = Query("", max_length=64),
           user: MiniUser | None = Depends(optional_mini_user)):
    result = catalog.list_papers(user.id if user else None, q, grade, subject, category, favorite, downloaded, limit, offset,
                                 sort=sort, only_free=only_free, recent=recent, favorite_group=favorite_group, topic=topic, textbook=textbook, term=term, unit=unit, knowledge=knowledge)
    if user and q.strip() and offset == 0 and not result["total"]:
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
    return asset_response(catalog.get_asset(catalog_id, asset_id, user_id=user.id if user else None))


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
