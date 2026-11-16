"""推广活动及运营查询输入。"""

from typing import Literal

from pydantic import Field

from app.models.settlements import Input


class ConversionFilters(Input):
    admin_id: int | None = Field(default=None, ge=0)
    start_date: str = Field(default='', max_length=10)
    end_date: str = Field(default='', max_length=10)
    campaign_id: str = Field(default='', max_length=80)


class ConversionCounts(Input):
    registrations: int
    ordered_users: int
    paying_users: int
    not_ordered_users: int
    unpaid_users: int
    order_rate_bps: int | None
    pay_rate_bps: int | None
    order_pay_rate_bps: int | None


class ConversionGroup(ConversionCounts):
    key: str
    admin_id: str
    admin_name: str
    campaign_id: str
    name: str
    source: str


class ConversionResponse(Input):
    summary: ConversionCounts
    items: list[ConversionGroup]
    total: int
    page: int
    as_of: int


class CampaignInput(Input):
    admin_id: int | None = Field(default=None, gt=0)
    name: str = Field(min_length=2, max_length=80)
    source: str = Field(min_length=2, max_length=80)
    budget_fen: int | None = Field(default=None, ge=0, le=100000000000, strict=True)
    spend_fen: int | None = Field(default=None, ge=0, le=100000000000, strict=True)
    landing_kind: Literal['home', 'topic', 'paper'] = 'home'
    landing_id: str = Field(default='', max_length=80, pattern=r'^[a-zA-Z0-9_-]*$')


class CampaignUpdate(CampaignInput):
    revision: int = Field(ge=1, strict=True)
    active: bool


class ReferralPosterRequest(Input):
    campaign_id: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    title: str = Field(min_length=1, max_length=80)
    style: Literal['editorial', 'playful', 'minimal'] = 'editorial'
    direction: str = Field(default='', max_length=500)
