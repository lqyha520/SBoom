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
from app.models.experience_api_responses import (
    ExperienceAdminFeedbackDetailResponse,
    ExperienceAdminFeedbackResponse,
    ExperienceAdminSupportResponse,
    ExperienceAdminTopicsResponse,
    ExperienceAnalyticsResponse,
    ExperienceAssignGroupResponse,
    ExperienceBatchFavoritesResponse,
    ExperienceBatchResponse,
    ExperienceCreateGroupResponse,
    ExperienceCreateTopicResponse,
    ExperienceFeedbackDetailResponse,
    ExperienceFeedbackResponse,
    ExperienceGroupsResponse,
    ExperienceMemberEventsResponse,
    ExperiencePreviewResponse,
    ExperienceRenewResponse,
    ExperienceReviseResponse,
    ExperienceSaveSupportResponse,
    ExperienceSubmitFeedbackResponse,
    ExperienceSupportResponse,
    ExperienceTopicsResponse,
    ExperienceUpdateFeedbackResponse,
    ExperienceUpdateGroupResponse,
    ExperienceUpdateTopicResponse,
)
from app.services import catalog_ops as publishing
from app.services import mini_experience as experience
from app.services.mini_auth import MiniUser
from app.services.rate_limit import allow
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1", tags=["小程序服务与运营"], dependencies=[Depends(no_store)])


@router.get("/site/support", response_model=ExperienceSupportResponse, response_model_exclude_unset=True)
def support():
    return experience.support()


@router.get("/site/topics", response_model=ExperienceTopicsResponse, response_model_exclude_unset=True)
def topics(user: MiniUser | None = Depends(optional_mini_user)):
    return publishing.topics()


@router.get("/mini/feedback", response_model=ExperienceFeedbackResponse, response_model_exclude_unset=True)
def feedback(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: MiniUser = Depends(require_mini_user)):
    return experience.list_feedback(user.id, limit=limit, offset=offset)


@router.post("/mini/feedback", status_code=201, response_model=ExperienceSubmitFeedbackResponse, response_model_exclude_unset=True)
def submit_feedback(body: FeedbackCreate, user: MiniUser = Depends(require_mini_user)):
    return experience.create_feedback(user.id, body)


@router.get("/mini/feedback/{identifier}", response_model=ExperienceFeedbackDetailResponse, response_model_exclude_unset=True)
def feedback_detail(identifier: str, user: MiniUser = Depends(require_mini_user)):
    return experience.feedback_detail(user.id, identifier)


@router.get("/mini/favorite-groups", response_model=ExperienceGroupsResponse, response_model_exclude_unset=True)
def groups(user: MiniUser = Depends(require_mini_user)):
    return experience.groups(user.id)


@router.post("/mini/favorites/batch", response_model=ExperienceBatchFavoritesResponse, response_model_exclude_unset=True)
def batch_favorites(body: FavoriteBatch, user: MiniUser = Depends(require_mini_user)):
    return experience.batch_favorites(user.id, body)


@router.post("/mini/favorite-groups", status_code=201, response_model=ExperienceCreateGroupResponse, response_model_exclude_unset=True)
def create_group(body: GroupInput, user: MiniUser = Depends(require_mini_user)):
    return experience.save_group(user.id, body)


@router.put("/mini/favorite-groups/{identifier}", response_model=ExperienceUpdateGroupResponse, response_model_exclude_unset=True)
def update_group(identifier: str, body: GroupInput, user: MiniUser = Depends(require_mini_user)):
    return experience.save_group(user.id, body, identifier)


@router.delete("/mini/favorite-groups/{identifier}", status_code=204)
def delete_group(identifier: str, revision: int = Query(ge=1), user: MiniUser = Depends(require_mini_user)):
    experience.delete_group(user.id, identifier, revision)
    return Response(status_code=204)


@router.put("/mini/favorite-groups/papers/{catalog_id}", response_model=ExperienceAssignGroupResponse, response_model_exclude_unset=True)
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


@router.get("/admin/experience/support", response_model=ExperienceAdminSupportResponse, response_model_exclude_unset=True)
def admin_support(user: CurrentUser = Depends(require_admin)):
    return experience.support()


@router.put("/admin/experience/support", response_model=ExperienceSaveSupportResponse, response_model_exclude_unset=True)
def save_support(body: SupportSettings, user: CurrentUser = Depends(require_admin)):
    return experience.save_support(body)


@router.get("/admin/experience/feedback", response_model=ExperienceAdminFeedbackResponse, response_model_exclude_unset=True)
def admin_feedback(status: Literal["", "pending", "processing", "resolved", "closed"] = "",
                   limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: CurrentUser = Depends(require_admin)):
    return experience.list_feedback(status=status, limit=limit, offset=offset)


@router.get("/admin/experience/feedback/{identifier}", response_model=ExperienceAdminFeedbackDetailResponse, response_model_exclude_unset=True)
def admin_feedback_detail(identifier: str, user: CurrentUser = Depends(require_admin)):
    return experience.admin_feedback_detail(identifier)


@router.put("/admin/experience/feedback/{identifier}", response_model=ExperienceUpdateFeedbackResponse, response_model_exclude_unset=True)
def update_feedback(identifier: str, body: FeedbackUpdate, user: CurrentUser = Depends(require_admin)):
    return experience.update_feedback(user.id, identifier, body)


@router.get("/admin/experience/analytics", response_model=ExperienceAnalyticsResponse, response_model_exclude_unset=True)
def analytics(user: CurrentUser = Depends(require_admin)):
    return experience.usage_analytics()


@router.get("/admin/experience/topics", response_model=ExperienceAdminTopicsResponse, response_model_exclude_unset=True)
def admin_topics(user: CurrentUser = Depends(require_admin)):
    return publishing.topics(admin=True)


@router.post("/admin/experience/topics", status_code=201, response_model=ExperienceCreateTopicResponse, response_model_exclude_unset=True)
def create_topic(body: TopicInput, user: CurrentUser = Depends(require_admin)):
    return publishing.save_topic(body)


@router.put("/admin/experience/topics/{identifier}", response_model=ExperienceUpdateTopicResponse, response_model_exclude_unset=True)
def update_topic(identifier: str, body: TopicInput, user: CurrentUser = Depends(require_admin)):
    return publishing.save_topic(body, identifier)


@router.delete("/admin/experience/topics/{identifier}", status_code=204)
def delete_topic(identifier: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_admin)):
    publishing.delete_topic(identifier, revision)
    return Response(status_code=204)


@router.post("/admin/mini-users/{identifier}/renew", response_model=ExperienceRenewResponse, response_model_exclude_unset=True)
def renew(identifier: str, body: Renewal, user: CurrentUser = Depends(require_admin)):
    return experience.renew_membership(user.id, identifier, body)


@router.get("/admin/mini-users/{identifier}/events", response_model=ExperienceMemberEventsResponse, response_model_exclude_unset=True)
def member_events(identifier: str, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000),
                  user: CurrentUser = Depends(require_admin)):
    return experience.membership_events(identifier, limit, offset)


@router.post("/admin/catalog/batch", response_model=ExperienceBatchResponse, response_model_exclude_unset=True)
def batch(body: CatalogBatch, user: CurrentUser = Depends(require_admin)):
    from app.admin_permissions import require
    if body.action in ('published', 'withdrawn'):
        require(user, 'papers', 'publish')
    return publishing.batch(body, user.id)


@router.get("/admin/catalog/papers/{identifier}/preview", response_model=ExperiencePreviewResponse, response_model_exclude_unset=True)
def preview(identifier: str, membership: Literal["regular", "vip"] = "regular", user: CurrentUser = Depends(require_admin)):
    return publishing.preview(user.id, identifier, membership)


@router.post("/admin/catalog/papers/{identifier}/revision", response_model=ExperienceReviseResponse, response_model_exclude_unset=True)
def revise(identifier: str, body: CatalogRevision, user: CurrentUser = Depends(require_admin)):
    from app.admin_permissions import require
    if body.confirm_publication:
        require(user, 'papers', 'publish')
    return publishing.revise(user.id, identifier, body)
