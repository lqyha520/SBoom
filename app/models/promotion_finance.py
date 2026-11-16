from typing import Annotated, Literal

from pydantic import Field

from app.models.settlements import Input, Revision


class FinanceControls(Revision):
    separate_review: bool
    separate_payment: bool


class MonthlyArchive(Input):
    admin_id: int = Field(gt=0)
    month: str = Field(pattern=r'^\d{4}-\d{2}$')
    quote_digest: str = Field(pattern=r'^[a-f0-9]{64}$')


class PayoutBatchInput(Input):
    name: str = Field(min_length=2, max_length=80)
    statement_ids: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=1, max_length=200)
    request_key: str = Field(min_length=8, max_length=100)


class PayoutImportInput(Revision):
    content: str = Field(min_length=1, max_length=500000)
    confirmed: Literal[True]


class PayoutPreview(Input):
    content: str = Field(min_length=1, max_length=500000)


class PayoutSelection(Input):
    statement_ids: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=1, max_length=200)


class CostVoucherInput(Input):
    admin_id: int = Field(gt=0)
    reference: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=80)
    total_fen: int = Field(gt=0, le=10000000000, strict=True)
    evidence: str = Field(min_length=2, max_length=1000)
    revision: int = Field(default=0, ge=0, strict=True)


class DisputeInput(Input):
    target_kind: Literal['reward', 'statement']
    target_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=2, max_length=100)
    content: str = Field(min_length=2, max_length=2000)
    evidence: str = Field(default='', max_length=500)
    request_key: str = Field(min_length=8, max_length=100)


class DisputeReply(Revision):
    content: str = Field(min_length=2, max_length=2000)
    evidence: str = Field(default='', max_length=500)
    status: Literal['open', 'processing', 'resolved', 'rejected'] = 'open'


class CampaignExpenseFields(Input):
    expense_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    category: Literal['广告', '物料', '其他']
    amount_fen: int = Field(gt=0, le=100000000, strict=True)
    evidence: str = Field(min_length=2, max_length=500)
    note: str = Field(default='', max_length=500)
    source_ref: str = Field(default='', max_length=120)
    included_in_baseline: bool = Field(default=False, strict=True)


class CampaignExpense(CampaignExpenseFields):
    request_key: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')


class CampaignExpenseUpdate(CampaignExpenseFields, Revision):
    active: bool = True
