"""HTTP boundaries for curriculum discovery, inbox and account requests."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from app.deps import require_admin
from app.library_deps import no_store, optional_mini_user, require_mini_user
from app.models.engagement import (
    ClosureInput,
    ClosureReview,
    ContentRequest,
    EditionInput,
    PaperLabels,
    RequestResolution,
    SubscriptionGrant,
    TagInput,
)
from app.models.engagement_api_responses import (
    EngagementAdminRequestsResponse,
    EngagementAdminTagsResponse,
    EngagementCancelClosureResponse,
    EngagementClosureResponse,
    EngagementClosuresResponse,
    EngagementCreateRequestResponse,
    EngagementCreateTagResponse,
    EngagementDeliveryStatusResponse,
    EngagementEditionSourcesResponse,
    EngagementEditionsResponse,
    EngagementInboxResponse,
    EngagementLabelsResponse,
    EngagementReadAllResponse,
    EngagementReadMessageResponse,
    EngagementRequestClosureResponse,
    EngagementRequestDetailResponse,
    EngagementRequestsResponse,
    EngagementResolveRequestResponse,
    EngagementReviewClosureResponse,
    EngagementSubscribeResponse,
    EngagementSubscriptionResponse,
    EngagementTagsResponse,
    EngagementUpdateTagResponse,
)
from app.services import (
    account_closures,
    catalog_discovery,
    catalog_editions,
    content_requests,
    mini_messages,
    wechat_notices,
)
from app.services.mini_auth import MiniUser
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1", tags=["资料发现与消息服务"], dependencies=[Depends(no_store)])


@router.get("/site/catalog-tags", response_model=EngagementTagsResponse, response_model_exclude_unset=True)
def tags(user: MiniUser | None = Depends(optional_mini_user)):
    return catalog_discovery.tags()


@router.get("/admin/catalog/tags", response_model=EngagementAdminTagsResponse, response_model_exclude_unset=True)
def admin_tags(user: CurrentUser = Depends(require_admin)):
    return catalog_discovery.tags(True)


@router.post("/admin/catalog/tags", status_code=201, response_model=EngagementCreateTagResponse, response_model_exclude_unset=True)
def create_tag(body: TagInput, user: CurrentUser = Depends(require_admin)):
    return catalog_discovery.save(body)


@router.put("/admin/catalog/tags/{identifier}", response_model=EngagementUpdateTagResponse, response_model_exclude_unset=True)
def update_tag(identifier: str, body: TagInput, user: CurrentUser = Depends(require_admin)):
    return catalog_discovery.save(body, identifier)


@router.delete("/admin/catalog/tags/{identifier}", status_code=204)
def remove_tag(identifier: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_admin)):
    catalog_discovery.remove(identifier, revision)
    return Response(status_code=204)


@router.put("/admin/catalog/papers/{identifier}/labels", response_model=EngagementLabelsResponse, response_model_exclude_unset=True)
def labels(identifier: str, body: PaperLabels, user: CurrentUser = Depends(require_admin)):
    return catalog_discovery.assign(identifier, body, admin_id=user.id)


@router.get("/admin/catalog/papers/{identifier}/edition-sources", response_model=EngagementEditionSourcesResponse, response_model_exclude_unset=True)
def edition_sources(identifier: str, q: str = Query("", max_length=120), user: CurrentUser = Depends(require_admin)):
    return catalog_editions.sources(user.id, identifier, q)


@router.put("/admin/catalog/papers/{identifier}/editions", response_model=EngagementEditionsResponse, response_model_exclude_unset=True)
def editions(identifier: str, body: EditionInput, user: CurrentUser = Depends(require_admin)):
    from app.admin_permissions import require
    if body.confirm_publication:
        require(user, 'papers', 'publish')
    return catalog_editions.assign(user.id, identifier, body)


@router.get("/mini/messages", response_model=EngagementInboxResponse, response_model_exclude_unset=True)
def inbox(unread: bool = False, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: MiniUser = Depends(require_mini_user)):
    return mini_messages.inbox(user.id, unread, limit, offset)


@router.post("/mini/messages/read-all", response_model=EngagementReadAllResponse, response_model_exclude_unset=True)
def read_all(user: MiniUser = Depends(require_mini_user)):
    return mini_messages.read(user.id)


@router.post("/mini/messages/{identifier}/read", response_model=EngagementReadMessageResponse, response_model_exclude_unset=True)
def read_message(identifier: str, user: MiniUser = Depends(require_mini_user)):
    return mini_messages.read(user.id, identifier)


@router.get("/mini/message-subscription", response_model=EngagementSubscriptionResponse, response_model_exclude_unset=True)
def subscription(user: MiniUser = Depends(require_mini_user)):
    return wechat_notices.configuration()


@router.post("/mini/message-subscription", response_model=EngagementSubscribeResponse, response_model_exclude_unset=True)
def subscribe(body: SubscriptionGrant, user: MiniUser = Depends(require_mini_user)):
    return wechat_notices.grant(user.id, body)


@router.get("/admin/engagement/delivery-status", response_model=EngagementDeliveryStatusResponse, response_model_exclude_unset=True)
def delivery_status(user: CurrentUser = Depends(require_admin)):
    return wechat_notices.status()


@router.get("/mini/requests", response_model=EngagementRequestsResponse, response_model_exclude_unset=True)
def requests(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: MiniUser = Depends(require_mini_user)):
    return content_requests.listing(user.id, limit=limit, offset=offset)


@router.post("/mini/requests", status_code=201, response_model=EngagementCreateRequestResponse, response_model_exclude_unset=True)
def create_request(body: ContentRequest, user: MiniUser = Depends(require_mini_user)):
    return content_requests.create(user.id, body)


@router.get("/mini/requests/{identifier}", response_model=EngagementRequestDetailResponse, response_model_exclude_unset=True)
def request_detail(identifier: str, user: MiniUser = Depends(require_mini_user)):
    return content_requests.detail(user.id, identifier)


@router.get("/admin/engagement/requests", response_model=EngagementAdminRequestsResponse, response_model_exclude_unset=True)
def admin_requests(status: Literal["", "pending", "planned", "fulfilled", "closed"] = "", fingerprint: str = Query("", max_length=64), limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: CurrentUser = Depends(require_admin)):
    return content_requests.listing(status=status, fingerprint=fingerprint, limit=limit, offset=offset)


@router.put("/admin/engagement/requests/{identifier}", response_model=EngagementResolveRequestResponse, response_model_exclude_unset=True)
def resolve_request(identifier: str, body: RequestResolution, user: CurrentUser = Depends(require_admin)):
    return content_requests.resolve(identifier, body)


@router.get("/mini/closure", response_model=EngagementClosureResponse, response_model_exclude_unset=True)
def closure(user: MiniUser = Depends(require_mini_user)):
    return account_closures.current(user.id)


@router.post("/mini/closure", response_model=EngagementRequestClosureResponse, response_model_exclude_unset=True)
def request_closure(body: ClosureInput, user: MiniUser = Depends(require_mini_user)):
    return account_closures.request(user.id, body)


@router.delete("/mini/closure", response_model=EngagementCancelClosureResponse, response_model_exclude_unset=True)
def cancel_closure(revision: int = Query(ge=1), user: MiniUser = Depends(require_mini_user)):
    return account_closures.cancel(user.id, revision)


@router.get("/admin/engagement/closures", response_model=EngagementClosuresResponse, response_model_exclude_unset=True)
def closures(status: Literal["", "pending", "cancelled", "rejected", "completed"] = "", limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: CurrentUser = Depends(require_admin)):
    return account_closures.listing(status, limit, offset)


@router.put("/admin/engagement/closures/{identifier}", response_model=EngagementReviewClosureResponse, response_model_exclude_unset=True)
def review_closure(identifier: str, body: ClosureReview, user: CurrentUser = Depends(require_admin)):
    return account_closures.review(user.id, identifier, body)
