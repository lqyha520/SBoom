"""推广管理：所有查询、导出都在服务端应用管理员范围。"""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.blocking import run_sync
from app.deps import require_admin, require_recent_admin
from app.http_contracts import binary_responses
from app.library_deps import no_store
from app.models.promotion_finance import CampaignExpense, CampaignExpenseUpdate
from app.models.referral_operations import (
    CampaignInput,
    CampaignUpdate,
    ConversionFilters,
    ConversionResponse,
    ReferralPosterRequest,
)
from app.models.referrals_api_responses import (
    ReferralsAcquisitionResponse,
    ReferralsAddExpenseResponse,
    ReferralsAdminsResponse,
    ReferralsAuditResponse,
    ReferralsBudgetResponse,
    ReferralsCampaignsResponse,
    ReferralsCodeResponse,
    ReferralsComparisonResponse,
    ReferralsCreateCampaignResponse,
    ReferralsExpensesResponse,
    ReferralsOrdersResponse,
    ReferralsPerformanceResponse,
    ReferralsPosterResponse,
    ReferralsQualityResponse,
    ReferralsRulesResponse,
    ReferralsSaveBudgetResponse,
    ReferralsSummaryResponse,
    ReferralsSupplementResponse,
    ReferralsUpdateCampaignResponse,
    ReferralsUpdateExpenseResponse,
    ReferralsUsersResponse,
)
from app.models.settlements import BudgetInput
from app.services import (
    payment_bills,
    referral_conversion,
    referral_growth,
    referral_operations,
    referral_poster,
    referrals,
    settlements,
)
from app.services.generation_control import metered
from app.services.mini_errors import fail
from app.services.rate_limit import allow
from app.services.user_store import CurrentUser

router = APIRouter(prefix='/api/v1/admin/referrals', tags=['推广管理'], dependencies=[Depends(no_store)])


async def poster_access(request: ReferralPosterRequest, user: CurrentUser = Depends(require_admin)):
    # 在计量与缓存重放之前校验活动范围，停用或越权时不调用模型。
    await run_sync(referral_operations.campaign_code, user.id, request.campaign_id)
    return user


@router.post('/poster', summary='使用已配置的图片模型生成推广海报原画', response_model=ReferralsPosterResponse, response_model_exclude_unset=True)
@metered('image')
async def poster(request: ReferralPosterRequest, http_request: Request, user: CurrentUser = Depends(poster_access)):
    return await referral_poster.generate(request)


class Filters(BaseModel):
    admin_id: int | None = Field(default=None, ge=0)
    q: str = Field(default='', max_length=120)
    start_date: str = Field(default='', max_length=10)
    end_date: str = Field(default='', max_length=10)
    campaign_id: str = Field(default='', max_length=80)
    date_basis: Literal['created', 'paid'] = 'created'


class UserFilters(Filters):
    stage: Literal['all', 'ordered', 'paid', 'not_ordered', 'unpaid'] = 'all'
    as_of: int | None = Field(default=None, ge=1)


class CodeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    admin_id: int | None = Field(default=None, gt=0)
    env_version: Literal['release', 'trial', 'develop'] = 'release'
    campaign_id: str = Field(default='', max_length=80)


class SupplementInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    admin_id: int = Field(gt=0)
    reason: str = Field(min_length=2, max_length=500)


@router.get('/admins', response_model=ReferralsAdminsResponse, response_model_exclude_unset=True)
def admins(user: CurrentUser = Depends(require_admin)):
    return referrals.admins(user.id)


@router.post('/code', response_model=ReferralsCodeResponse, response_model_exclude_unset=True)
def code(body: CodeInput, user: CurrentUser = Depends(require_admin)):
    return referrals.admin_code(user.id, body.admin_id)


@router.post('/qrcode', response_class=Response, responses=binary_responses('image/png', 'image/jpeg'))
def qrcode(body: CodeInput, user: CurrentUser = Depends(require_admin)):
    if not allow(f'referral-qr:{user.id}', 10, 300):
        fail('生成过于频繁，请稍后再试', 429)
    content, media_type = referrals.qrcode(user.id, body.admin_id, body.env_version, body.campaign_id)
    return Response(content, media_type=media_type, headers={'Content-Disposition': 'attachment; filename="referral-code.' + ('png' if media_type == 'image/png' else 'jpg') + '"'})


@router.get('/summary', response_model=ReferralsSummaryResponse, response_model_exclude_unset=True)
def summary(filters: Filters = Depends(), user: CurrentUser = Depends(require_admin)):
    return referral_operations.analytics(user.id, **filters.model_dump())


@router.get('/conversion', response_model=ConversionResponse)
def conversion(filters: ConversionFilters = Depends(), page: int = Query(1, ge=1, le=5000), user: CurrentUser = Depends(require_admin)):
    return referral_conversion.conversion(user.id, **filters.model_dump(), page=page)


@router.get('/rules', response_model=ReferralsRulesResponse, response_model_exclude_unset=True)
def rules(user: CurrentUser = Depends(require_admin)):
    return settlements.public_rules(user.id)


@router.get('/users', response_model=ReferralsUsersResponse, response_model_exclude_unset=True)
def users(filters: UserFilters = Depends(), limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: CurrentUser = Depends(require_admin)):
    return referrals.users(user.id, **filters.model_dump(), limit=limit, offset=offset)


@router.get('/orders', response_model=ReferralsOrdersResponse, response_model_exclude_unset=True)
def orders(filters: Filters = Depends(), limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: CurrentUser = Depends(require_admin)):
    return referrals.orders(user.id, **filters.model_dump(), limit=limit, offset=offset)


@router.get('/export/{kind}', response_class=Response, responses=binary_responses('text/csv'))
def export(kind: Literal['users', 'orders'], filters: UserFilters = Depends(), user: CurrentUser = Depends(require_admin)):
    if kind == 'users':
        content = referrals.export_users(user.id, **filters.model_dump())
    else:
        content = payment_bills.export_orders(q=filters.q, start_date=filters.start_date, end_date=filters.end_date,
                                             admin_actor_id=user.id, referral_admin_id=filters.admin_id, campaign_id=filters.campaign_id, date_basis=filters.date_basis, real_only=True)
    return Response(content, media_type='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="referral-{kind}.csv"'})


@router.put('/users/{identifier}', response_model=ReferralsSupplementResponse, response_model_exclude_unset=True)
def supplement(identifier: str, body: SupplementInput, user: CurrentUser = Depends(require_recent_admin)):
    return referrals.supplement(user.id, identifier, body.admin_id, body.reason)


@router.get('/users/{identifier}/audit', response_model=ReferralsAuditResponse, response_model_exclude_unset=True)
def audit(identifier: str, user: CurrentUser = Depends(require_admin)):
    return referrals.audit(user.id, identifier)


@router.get('/campaigns', response_model=ReferralsCampaignsResponse, response_model_exclude_unset=True)
def campaigns(admin_id: int | None = Query(None, gt=0), q: str = Query('', max_length=80),
              state: Literal['all', 'active', 'inactive'] = 'all', source: str = Query('', max_length=80),
              page: int = Query(1, ge=1, le=5000), user: CurrentUser = Depends(require_admin)):
    return referral_operations.campaigns(user.id, admin_id, q, state, source, page)


@router.get('/campaigns/{identifier}/performance', response_model=ReferralsPerformanceResponse, response_model_exclude_unset=True)
def performance(identifier: str, user: CurrentUser = Depends(require_admin)):
    return referral_operations.performance(user.id, identifier)


@router.get('/acquisition', response_model=ReferralsAcquisitionResponse, response_model_exclude_unset=True)
def acquisition(filters: ConversionFilters = Depends(), user: CurrentUser = Depends(require_admin)):
    return referral_growth.acquisition(user.id, **filters.model_dump())


@router.post('/campaigns', response_model=ReferralsCreateCampaignResponse, response_model_exclude_unset=True)
def create_campaign(body: CampaignInput, user: CurrentUser = Depends(require_recent_admin)):
    return referral_operations.save_campaign(user.id, body)


@router.put('/campaigns/{identifier}', response_model=ReferralsUpdateCampaignResponse, response_model_exclude_unset=True)
def update_campaign(identifier: str, body: CampaignUpdate, user: CurrentUser = Depends(require_recent_admin)):
    return referral_operations.save_campaign(user.id, body, identifier)


@router.get('/budget/{admin_id}', response_model=ReferralsBudgetResponse, response_model_exclude_unset=True)
def budget(admin_id: int, user: CurrentUser = Depends(require_admin)):
    return referral_operations.budget(user.id, admin_id)


@router.put('/budget/{admin_id}', response_model=ReferralsSaveBudgetResponse, response_model_exclude_unset=True)
def save_budget(admin_id: int, body: BudgetInput, user: CurrentUser = Depends(require_recent_admin)):
    return referral_operations.budget(user.id, admin_id, body)


@router.get('/quality', response_model=ReferralsQualityResponse, response_model_exclude_unset=True)
def quality(filters: ConversionFilters = Depends(), page: int = Query(1, ge=1, le=5000), user: CurrentUser = Depends(require_admin)):
    from app.services.referral_quality import quality
    return quality(user.id, **filters.model_dump(), page=page)


@router.get('/comparison', response_model=ReferralsComparisonResponse, response_model_exclude_unset=True)
def comparison(start_date: str = Query(max_length=10), end_date: str = Query(max_length=10), admin_id: int | None = Query(None, ge=0), campaign_id: str = Query('', max_length=80),
               sort: Literal['paying_users', 'spend', 'cost_per_payer', 'refund_rate', 'net'] = 'paying_users', direction: Literal['asc', 'desc'] = 'desc', page: int = Query(1, ge=1, le=5000), user: CurrentUser = Depends(require_admin)):
    from app.services.referral_comparison import comparison
    return comparison(user.id, start_date, end_date, admin_id, campaign_id, sort, direction, page)


@router.get('/campaigns/{identifier}/expenses', response_model=ReferralsExpensesResponse, response_model_exclude_unset=True)
def expenses(identifier: str, start_date: str = Query('', max_length=10), end_date: str = Query('', max_length=10), page: int = Query(1, ge=1, le=5000), user: CurrentUser = Depends(require_admin)):
    from app.services.referral_expenses import listing
    return listing(user.id, identifier, start_date, end_date, page)


@router.post('/campaigns/{identifier}/expenses', response_model=ReferralsAddExpenseResponse, response_model_exclude_unset=True)
def add_expense(identifier: str, body: CampaignExpense, user: CurrentUser = Depends(require_recent_admin)):
    from app.services.referral_expenses import save
    return save(user.id, identifier, body)


@router.put('/campaigns/{identifier}/expenses/{expense_id}', response_model=ReferralsUpdateExpenseResponse, response_model_exclude_unset=True)
def update_expense(identifier: str, expense_id: str, body: CampaignExpenseUpdate, user: CurrentUser = Depends(require_recent_admin)):
    from app.services.referral_expenses import save
    return save(user.id, identifier, body, expense_id)
