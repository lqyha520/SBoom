"""Validated wire contracts for discovery and consumer service."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TagKind = Literal["textbook", "term", "unit", "knowledge"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TagInput(Input):
    kind: TagKind
    name: str = Field(min_length=1, max_length=80)
    is_visible: bool = True
    sort_order: int = Field(0, ge=0, le=10000)
    revision: int = Field(0, ge=0)


class PaperLabels(Input):
    revision: int = Field(ge=1)
    tag_ids: list[str] = Field(default_factory=list, max_length=24)

    @field_validator("tag_ids")
    @classmethod
    def identifiers(cls, values):
        if any(not value or len(value) > 64 for value in values) or len(set(values)) != len(values):
            raise ValueError("标签标识无效或重复")
        return values


class EditionInput(Input):
    revision: int = Field(ge=1)
    kind: Literal["student", "answers"]
    paper_id: str | None = Field(None, min_length=1, max_length=64)
    confirm_publication: bool = False


class ContentRequest(Input):
    title: str = Field(min_length=2, max_length=120)
    grade: str = Field("", max_length=80)
    subject: str = Field("", max_length=80)
    details: str = Field("", max_length=1000)


class RequestResolution(Input):
    revision: int = Field(ge=1)
    status: Literal["pending", "planned", "fulfilled", "closed"]
    reply: str = Field("", max_length=1000)
    catalog_id: str | None = Field(None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def linked_result(self):
        if self.status == "fulfilled" and not self.catalog_id:
            raise ValueError("已补齐的需求必须关联已发布资料")
        return self


class ClosureInput(Input):
    reason: str = Field("", max_length=500)
    acknowledge: Literal[True]


class ClosureReview(Input):
    revision: int = Field(ge=1)
    action: Literal["approve", "reject"]
    reply: str = Field(min_length=2, max_length=500)
    confirm_deletion: bool = False


class SubscriptionGrant(Input):
    template_id: str = Field(min_length=1, max_length=150)
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
