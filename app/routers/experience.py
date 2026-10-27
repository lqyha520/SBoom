"""Consumer improvements and their administrator workflows."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from app.deps import require_admin
from app.library_deps import no_store, optional_mini_user, require_mini_user
from app.models.experience import (
    CatalogBatch,
    CatalogRevision,
    FavoriteBatch,
    FeedbackCreate,
    FeedbackUpdate,
    GroupAssignment,
    GroupInput,
    Renewal,
    SupportSettings,
    TopicInput,
    UsageEvent,
)
from app.services import catalog_ops as publishing
from app.services import mini_experience as experience
from app.services.mini_auth import MiniUser
from app.services.rate_limit import allow
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1", tags=["小程序服务与运营"], dependencies=[Depends(no_store)])


@router.get("/site/support")
def support():
    return experience.support()


@router.get("/site/topics")
def topics(user: MiniUser | None = Depends(optional_mini_user)):
    return publishing.topics()


@router.get("/mini/feedback")
def feedback(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: MiniUser = Depends(require_mini_user)):
    return experience.list_feedback(user.id, limit=limit, offset=offset)


@router.post("/mini/feedback", status_code=201)
def submit_feedback(body: FeedbackCreate, user: MiniUser = Depends(require_mini_user)):
    return experience.create_feedback(user.id, body)


@router.get("/mini/feedback/{identifier}")
def feedback_detail(identifier: str, user: MiniUser = Depends(require_mini_user)):
    return experience.feedback_detail(user.id, identifier)


@router.get("/mini/favorite-groups")
def groups(user: MiniUser = Depends(require_mini_user)):
    return experience.groups(user.id)


@router.post("/mini/favorites/batch")
def batch_favorites(body: FavoriteBatch, user: MiniUser = Depends(require_mini_user)):
    return experience.batch_favorites(user.id, body)


@router.post("/mini/favorite-groups", status_code=201)
def create_group(body: GroupInput, user: MiniUser = Depends(require_mini_user)):
    return experience.save_group(user.id, body)


@router.put("/mini/favorite-groups/{identifier}")
def update_group(identifier: str, body: GroupInput, user: MiniUser = Depends(require_mini_user)):
    return experience.save_group(user.id, body, identifier)


@router.delete("/mini/favorite-groups/{identifier}", status_code=204)
def delete_group(identifier: str, revision: int = Query(ge=1), user: MiniUser = Depends(require_mini_user)):
    experience.delete_group(user.id, identifier, revision)
    return Response(status_code=204)


@router.put("/mini/favorite-groups/papers/{catalog_id}")
def assign_group(catalog_id: str, body: GroupAssignment, user: MiniUser = Depends(require_mini_user)):
    return experience.assign_group(user.id, catalog_id, body.group_id)


@router.post("/mini/history/{catalog_id}", status_code=204)
def record_view(catalog_id: str, user: MiniUser = Depends(require_mini_user)):
    experience.record_view(user.id, catalog_id)
    return Response(status_code=204)


@router.delete("/mini/history", status_code=204)
def clear_history(user: MiniUser = Depends(require_mini_user)):
    experience.clear_history(user.id)
    return Response(status_code=204)


@router.post("/mini/events", status_code=204)
def record_event(body: UsageEvent, user: MiniUser = Depends(require_mini_user)):
    if not allow("mini-events:" + user.id, 60, 60):
        experience.fail("操作频繁，请稍后重试", 429)
    experience.record_event(user.id, body.kind, body.event_id, body.catalog_id)
    return Response(status_code=204)


@router.get("/admin/experience/support")
def admin_support(user: CurrentUser = Depends(require_admin)):
    return experience.support()


@router.put("/admin/experience/support")
def save_support(body: SupportSettings, user: CurrentUser = Depends(require_admin)):
    return experience.save_support(body)


@router.get("/admin/experience/feedback")
def admin_feedback(status: Literal["", "pending", "processing", "resolved", "closed"] = "",
                   limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: CurrentUser = Depends(require_admin)):
    return experience.list_feedback(status=status, limit=limit, offset=offset)


@router.get("/admin/experience/feedback/{identifier}")
def admin_feedback_detail(identifier: str, user: CurrentUser = Depends(require_admin)):
    return experience.admin_feedback_detail(identifier)


@router.put("/admin/experience/feedback/{identifier}")
def update_feedback(identifier: str, body: FeedbackUpdate, user: CurrentUser = Depends(require_admin)):
    return experience.update_feedback(user.id, identifier, body)


@router.get("/admin/experience/analytics")
def analytics(user: CurrentUser = Depends(require_admin)):
    return experience.usage_analytics()


@router.get("/admin/experience/topics")
def admin_topics(user: CurrentUser = Depends(require_admin)):
    return publishing.topics(admin=True)


@router.post("/admin/experience/topics", status_code=201)
def create_topic(body: TopicInput, user: CurrentUser = Depends(require_admin)):
    return publishing.save_topic(body)


@router.put("/admin/experience/topics/{identifier}")
def update_topic(identifier: str, body: TopicInput, user: CurrentUser = Depends(require_admin)):
    return publishing.save_topic(body, identifier)


@router.delete("/admin/experience/topics/{identifier}", status_code=204)
def delete_topic(identifier: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_admin)):
    publishing.delete_topic(identifier, revision)
    return Response(status_code=204)


@router.post("/admin/mini-users/{identifier}/renew")
def renew(identifier: str, body: Renewal, user: CurrentUser = Depends(require_admin)):
    return experience.renew_membership(user.id, identifier, body)


@router.get("/admin/mini-users/{identifier}/events")
def member_events(identifier: str, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000),
                  user: CurrentUser = Depends(require_admin)):
    return experience.membership_events(identifier, limit, offset)


@router.post("/admin/catalog/batch")
def batch(body: CatalogBatch, user: CurrentUser = Depends(require_admin)):
    return publishing.batch(body, user.id)


@router.get("/admin/catalog/papers/{identifier}/preview")
def preview(identifier: str, membership: Literal["regular", "vip"] = "regular", user: CurrentUser = Depends(require_admin)):
    return publishing.preview(user.id, identifier, membership)


@router.post("/admin/catalog/papers/{identifier}/revision")
def revise(identifier: str, body: CatalogRevision, user: CurrentUser = Depends(require_admin)):
    return publishing.revise(user.id, identifier, body)
