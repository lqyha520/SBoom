"""Only the server determines payment amounts and membership grants."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PlanInput(Input):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field("", max_length=1000)
    days: int = Field(ge=1, le=3660)
    price_fen: int = Field(ge=1, le=10000000)
    is_active: bool = False
    sort_order: int = Field(0, ge=0, le=10000)
    #: 0 表示不限购；按账号统计该套餐的已付款与未完成订单
    purchase_limit: int = Field(0, ge=0, le=100)
    virtual_product_id: str = Field("", max_length=64, pattern=r"^[A-Za-z0-9_-]*$")
    revision: int = Field(0, ge=0)


class OrderInput(Input):
    plan_id: str = Field(min_length=1, max_length=64)
    plan_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class RefundInput(Input):
    reason: str = Field(min_length=5, max_length=500)


class RefundReview(Input):
    revision: int = Field(ge=1)
    action: Literal["approve", "reject"]
    reply: str = Field(min_length=2, max_length=500)
    confirm_refund: bool = False


class BillInput(Input):
    bill_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("bill_date")
    @classmethod
    def valid_date(cls, value):
        from datetime import date
        date.fromisoformat(value)
        return value
