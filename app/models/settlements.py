"""金额一律用分；费率用万分比，税费录入实际核定金额。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Fee(Input):
    name: str = Field(min_length=1, max_length=80)
    amount_fen: int = Field(ge=0, le=100000000, strict=True)


class PercentageFee(Input):
    name: str = Field(min_length=1, max_length=80)
    source_ref: str | None = Field(default=None, min_length=2, max_length=120)
    mode: Literal['fixed', 'percent'] = 'fixed'
    amount_fen: int | None = Field(default=None, ge=0, le=100000000, strict=True)
    rate_bps: int | None = Field(default=None, ge=0, le=10000, strict=True)

    @model_validator(mode='after')
    def exclusive_value(self):
        if self.mode == 'fixed' and (self.amount_fen is None or self.rate_bps is not None):
            raise ValueError('固定费用必须填写金额，不能同时填写比例')
        if self.mode == 'percent' and (self.rate_bps is None or self.amount_fen is not None):
            raise ValueError('比例费用必须填写比例，金额由服务器计算')
        return self


class SharedFee(PercentageFee):
    basis: Literal['order_gross', 'after_channel'] = 'after_channel'


class PersonalFee(PercentageFee):
    basis: Literal['reward_gross', 'after_adjustment'] = 'reward_gross'


class Revision(Input):
    revision: int = Field(ge=1, strict=True)


class ChannelRates(Input):
    wechat: int = Field(ge=0, le=10000, strict=True)
    virtual_android: int = Field(ge=0, le=10000, strict=True)
    virtual_ios: int = Field(ge=0, le=10000, strict=True)


class PolicyInput(Revision):
    enabled: bool
    beneficiary: Literal['admin'] = 'admin'
    rate_bps: int = Field(ge=0, le=10000, strict=True)
    hold_days: int = Field(ge=0, le=365, strict=True)
    review_days: int | None = Field(default=None, ge=1, le=90, strict=True)
    payout_days: int | None = Field(default=None, ge=1, le=90, strict=True)
    max_reward_fen: int | None = Field(default=None, ge=0, le=100000000, strict=True)
    channel_rate_bps: int | None = Field(default=None, ge=0, le=10000, strict=True)
    channel_rates: ChannelRates | None = None
    shared_fees: list[SharedFee] = Field(default_factory=list, max_length=20)
    reason: str = Field(min_length=2, max_length=500)


class CostsInput(Revision):
    bill_row_id: int | None = Field(default=None, gt=0, strict=True)
    channel_rate_bps: int | None = Field(default=None, ge=0, le=10000, strict=True)
    channel_fee_fen: int | None = Field(default=None, ge=0, le=100000000, strict=True)
    shared_fees: list[SharedFee] = Field(max_length=20)
    evidence: str = Field(min_length=2, max_length=1000)
    confirmed: Literal[True]

    @model_validator(mode='after')
    def unique_names(self):
        if (self.channel_rate_bps is None) == (self.channel_fee_fen is None):
            raise ValueError('渠道手续费填写费率，金额由服务端计算；旧金额格式不能同时传入费率')
        names = [fee.name for fee in self.shared_fees]
        if len(set(names)) != len(names):
            raise ValueError('同一费用不能重复列入')
        return self


class StatementInput(Input):
    order_ids: list[str] = Field(default_factory=list, max_length=5000)
    beneficiary: str | None = Field(default=None, pattern=r'^admin:[0-9]+$', max_length=100)
    settlement_request_id: str | None = Field(default=None, max_length=80)


class SettlementPreviewInput(Input):
    order_ids: list[str] = Field(default_factory=list, max_length=5000)
    all_eligible: bool = Field(default=False, strict=True)

    @model_validator(mode='after')
    def select_scope(self):
        if bool(self.order_ids) == self.all_eligible:
            raise ValueError('请选择指定订单或全部可申请订单，不能同时指定')
        return self


class SettlementApplyInput(SettlementPreviewInput):
    request_key: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')
    quote_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    note: str = Field(default='', max_length=500)
    confirmed: Literal[True]


class ReviewInput(Revision):
    personal_fees: list[PersonalFee] = Field(max_length=20)
    tax_fen: int = Field(ge=0, le=100000000, strict=True)
    evidence: str = Field(min_length=2, max_length=1000)
    confirmed: Literal[True]
    difference_reason: str = Field(default='', max_length=1000)


class BatchCostItem(CostsInput):
    order_id: str = Field(min_length=1, max_length=200)


class BatchCostsInput(Revision):
    items: list[BatchCostItem] = Field(min_length=1, max_length=5000)

    @model_validator(mode='after')
    def unique_orders(self):
        if len({item.order_id for item in self.items}) != len(self.items):
            raise ValueError('批量核对不能重复包含同一订单')
        return self


class ReceiptInput(Revision):
    amount_fen: int = Field(ge=0, le=100000000000, strict=True)
    receipt: str = Field(min_length=2, max_length=500)
    transferred_at: int | None = Field(default=None, gt=0, strict=True)


class SettlementFilters(Input):
    admin_id: int | None = Field(default=None, gt=0)
    q: str = Field(default='', max_length=120)
    status: str = Field(default='', max_length=30)
    channel: Literal['', 'wechat', 'virtual_android', 'virtual_ios', 'unknown'] = ''
    start_date: str = Field(default='', max_length=10)
    end_date: str = Field(default='', max_length=10)
    date_basis: Literal['created', 'paid'] = 'created'
    timing: Literal['', 'stalled', 'review_overdue', 'payout_overdue'] = ''


class PayeeInput(Input):
    revision: int = Field(default=0, ge=0, strict=True)
    name: str = Field(min_length=2, max_length=80)
    method: Literal['bank', 'wechat', 'alipay']
    account: str = Field(min_length=4, max_length=120)
    bank: str = Field(default='', max_length=120)


class BillImportInput(Input):
    name: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=2, max_length=1000)
    content: str = Field(min_length=1, max_length=500000)


class RecoveryInput(Revision):
    reason: str = Field(min_length=2, max_length=500)
    confirmed: Literal[True]


class BudgetInput(Input):
    revision: int = Field(default=0, ge=0, strict=True)
    budget_fen: int | None = Field(default=None, ge=0, le=100000000000, strict=True)


class VoidInput(Revision):
    reason: str = Field(min_length=2, max_length=500)


class AdjustmentInput(Input):
    beneficiary: str = Field(pattern=r'^admin:[0-9]+$', max_length=100)
    amount_fen: int = Field(ge=-100000000, le=100000000, strict=True)
    request_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')
    reason: str = Field(min_length=2, max_length=500)
    evidence: str = Field(min_length=2, max_length=1000)
