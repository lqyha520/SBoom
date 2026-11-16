from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FinanceLedgerInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    identifier: str = Field(default='', max_length=100)
    entry_date: str = Field(min_length=10, max_length=10, pattern=r'^\d{4}-\d{2}-\d{2}$')
    direction: Literal['income', 'expense']
    category: str = Field(min_length=1, max_length=80)
    amount_fen: int = Field(ge=1, le=10_000_000_000, strict=True)
    tax_fen: int = Field(default=0, ge=0, le=10_000_000_000, strict=True)
    counterparty: str = Field(default='', max_length=160)
    reference: str = Field(default='', max_length=160)
    note: str = Field(default='', max_length=2000)
    attachment: str = Field(default='', max_length=500)

    @field_validator('entry_date')
    @classmethod
    def valid_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @model_validator(mode='after')
    def tax_within_amount(self):
        if self.tax_fen > self.amount_fen:
            raise ValueError('税额不能超过含税金额')
        return self


class FinanceLedgerUpdate(FinanceLedgerInput):
    revision: int = Field(ge=1)


class FinanceLedgerEntry(FinanceLedgerInput):
    id: str
    status: Literal['active', 'void']
    revision: int
    created_by: int | None
    created_at: int
    updated_at: int


class FinanceLedgerSummary(BaseModel):
    income_fen: int
    expense_fen: int
    tax_fen: int
    net_fen: int


class FinanceLedgerPage(BaseModel):
    items: list[FinanceLedgerEntry]
    total: int
    page: int
    page_size: int
    summary: FinanceLedgerSummary
