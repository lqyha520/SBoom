"""教学功能的请求与成功响应，三端使用同一份版本化契约。"""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Question


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class BankQuestion(Question):
    preview: bool = Field(False, alias='_preview', exclude=True)


class BankContent(Input):
    title: str = Field(min_length=1, max_length=240)
    grade: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=80)
    topic: str = Field('', max_length=200)
    difficulty: Literal['easy', 'medium', 'hard'] = 'medium'
    section_type: str = Field(min_length=1, max_length=80)
    passage: str = Field('', max_length=20000)
    questions: list[BankQuestion] = Field(min_length=1, max_length=30)

    @model_validator(mode='after')
    def validate_content(self):
        if any(q.preview or not str(q.answer).strip() for q in self.questions):
            raise ValueError('格式示例和缺少答案的题目不能存入题库')
        if self.section_type == 'reading' and not self.passage:
            raise ValueError('阅读题须连同完整文章保存')
        if self.section_type != 'reading' and (self.passage or len(self.questions) != 1):
            raise ValueError('普通题型每条保存一道题，阅读题保存整篇')
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > 65536:
            raise ValueError('题目内容不能超过 64 KB')
        return self


class BankItem(BaseModel):
    id: str
    title: str
    grade: str
    subject: str
    topic: str
    difficulty: Literal['easy', 'medium', 'hard']
    section_type: str
    passage: str
    questions: list[Question]
    revision: int
    created_at: int
    updated_at: int


class BankPage(BaseModel):
    items: list[BankItem]
    total: int
    has_more: bool
    bank_total: int = 0
    available: dict[str, list[str]] = Field(default_factory=dict)


class BankMetadata(Input):
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    topic: str = Field('', max_length=200)
    difficulty: Literal['easy', 'medium', 'hard']


class BankSelection(Input):
    ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator('ids')
    @classmethod
    def distinct_ids(cls, values):
        if any(not v or len(v) > 64 for v in values) or len(set(values)) != len(values):
            raise ValueError('题目编号无效或重复')
        return values


class ScheduleInput(Input):
    catalog_revision: int = Field(ge=1)
    schedule_revision: int = Field(0, ge=0)
    scheduled_at: int = Field(gt=0)
    confirm_publication: Literal[True]


class ScheduleItem(BaseModel):
    catalog_id: str
    title: str
    scheduled_at: int
    catalog_revision: int
    revision: int
    status: Literal['pending', 'published', 'failed', 'cancelled']
    message: str
    updated_at: int


class SchedulePage(BaseModel):
    items: list[ScheduleItem]
    total: int
    has_more: bool
    counts: dict[str, int] = Field(default_factory=dict)


class LinkCheck(BaseModel):
    catalog_id: str
    status: Literal['reachable', 'suspect', 'unverified', 'confirmed']
    message: str
    checked_at: int


class HealthIssue(BaseModel):
    code: str
    severity: Literal['error', 'warning', 'info']
    message: str


class HealthItem(BaseModel):
    catalog_id: str
    title: str
    revision: int
    status: str
    external: bool
    issues: list[HealthIssue]
    link_check: LinkCheck | None


class HealthPage(BaseModel):
    items: list[HealthItem]
    total: int
    has_more: bool
    checked_at: int
    counts: dict[str, int] = Field(default_factory=dict)
