"""HTTP boundaries for curriculum discovery, inbox and account requests."""

from typing import Literal
from fastapi import APIRouter, Depends, Query, Response
from app.deps import require_admin
from app.library_deps import no_store, optional_mini_user, require_mini_user
from app.models.engagement import TagInput, PaperLabels, EditionInput, ContentRequest, RequestResolution, ClosureInput, ClosureReview, SubscriptionGrant
from app.services import catalog_discovery, catalog_editions, content_requests, mini_messages, account_closures, wechat_notices
from app.services.mini_auth import MiniUser
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1", tags=["资料发现与消息服务"], dependencies=[Depends(no_store)])


@router.get("/site/catalog-tags")
def tags(user: MiniUser | None = Depends(optional_mini_user)):
    return catalog_discovery.tags()


@router.get("/admin/catalog/tags")
def admin_tags(user: CurrentUser = Depends(require_admin)):
    return catalog_discovery.tags(True)


@router.post("/admin/catalog/tags", status_code=201)
def create_tag(body: TagInput, user: CurrentUser = Depends(require_admin)):
    return catalog_discovery.save(body)


@router.put("/admin/catalog/tags/{identifier}")
def update_tag(identifier: str, body: TagInput, user: CurrentUser = Depends(require_admin)):
    return catalog_discovery.save(body, identifier)


@router.delete("/admin/catalog/tags/{identifier}", status_code=204)
def remove_tag(identifier: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_admin)):
    catalog_discovery.remove(identifier, revision)
    return Response(status_code=204)


@router.put("/admin/catalog/papers/{identifier}/labels")
def labels(identifier: str, body: PaperLabels, user: CurrentUser = Depends(require_admin)):
    return catalog_discovery.assign(identifier, body)


@router.get("/admin/catalog/papers/{identifier}/edition-sources")
def edition_sources(identifier: str, q: str = Query("", max_length=120), user: CurrentUser = Depends(require_admin)):
    return catalog_editions.sources(user.id, identifier, q)


@router.put("/admin/catalog/papers/{identifier}/editions")
def editions(identifier: str, body: EditionInput, user: CurrentUser = Depends(require_admin)):
    return catalog_editions.assign(user.id, identifier, body)


@router.get("/mini/messages")
def inbox(unread: bool = False, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: MiniUser = Depends(require_mini_user)):
    return mini_messages.inbox(user.id, unread, limit, offset)


@router.post("/mini/messages/read-all")
def read_all(user: MiniUser = Depends(require_mini_user)):
    return mini_messages.read(user.id)


@router.post("/mini/messages/{identifier}/read")
def read_message(identifier: str, user: MiniUser = Depends(require_mini_user)):
    return mini_messages.read(user.id, identifier)


@router.get("/mini/message-subscription")
def subscription(user: MiniUser = Depends(require_mini_user)):
    return wechat_notices.configuration()


@router.post("/mini/message-subscription")
def subscribe(body: SubscriptionGrant, user: MiniUser = Depends(require_mini_user)):
    return wechat_notices.grant(user.id, body)


@router.get("/admin/engagement/delivery-status")
def delivery_status(user: CurrentUser = Depends(require_admin)):
    return wechat_notices.status()


@router.get("/mini/requests")
def requests(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: MiniUser = Depends(require_mini_user)):
    return content_requests.listing(user.id, limit=limit, offset=offset)


@router.post("/mini/requests", status_code=201)
def create_request(body: ContentRequest, user: MiniUser = Depends(require_mini_user)):
    return content_requests.create(user.id, body)


@router.get("/mini/requests/{identifier}")
def request_detail(identifier: str, user: MiniUser = Depends(require_mini_user)):
    return content_requests.detail(user.id, identifier)


@router.get("/admin/engagement/requests")
def admin_requests(status: Literal["", "pending", "planned", "fulfilled", "closed"] = "", fingerprint: str = Query("", max_length=64), limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: CurrentUser = Depends(require_admin)):
    return content_requests.listing(status=status, fingerprint=fingerprint, limit=limit, offset=offset)


@router.put("/admin/engagement/requests/{identifier}")
def resolve_request(identifier: str, body: RequestResolution, user: CurrentUser = Depends(require_admin)):
    return content_requests.resolve(identifier, body)


@router.get("/mini/closure")
def closure(user: MiniUser = Depends(require_mini_user)):
    return account_closures.current(user.id)


@router.post("/mini/closure")
def request_closure(body: ClosureInput, user: MiniUser = Depends(require_mini_user)):
    return account_closures.request(user.id, body)


@router.delete("/mini/closure")
def cancel_closure(revision: int = Query(ge=1), user: MiniUser = Depends(require_mini_user)):
    return account_closures.cancel(user.id, revision)


@router.get("/admin/engagement/closures")
def closures(status: Literal["", "pending", "cancelled", "rejected", "completed"] = "", limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: CurrentUser = Depends(require_admin)):
    return account_closures.listing(status, limit, offset)


@router.put("/admin/engagement/closures/{identifier}")
def review_closure(identifier: str, body: ClosureReview, user: CurrentUser = Depends(require_admin)):
    return account_closures.review(user.id, identifier, body)
