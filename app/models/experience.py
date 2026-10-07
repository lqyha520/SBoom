"""Validated inputs shared by consumer and editorial endpoints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FeedbackCreate(Input):
    catalog_id: str | None = Field(None, max_length=64)
    kind: Literal["correction", "download", "membership", "other"]
    body: str = Field(min_length=5, max_length=2000)


class FeedbackUpdate(Input):
    revision: int = Field(ge=1)
    status: Literal["pending", "processing", "resolved", "closed"]
    reply: str = Field("", max_length=2000)
    internal_note: str = Field("", max_length=2000)

    @model_validator(mode="after")
    def resolved_reply(self):
        if self.status in ("resolved", "closed") and not self.reply:
            raise ValueError("处理完成时请填写给用户的回复")
        return self


class GroupInput(Input):
    name: str = Field(min_length=1, max_length=40)
    revision: int = Field(0, ge=0)


class GroupAssignment(Input):
    group_id: str | None = Field(None, max_length=64)


class FavoriteBatch(Input):
    ids: list[str] = Field(min_length=1, max_length=200)
    action: Literal["remove", "assign"]
    group_id: str | None = Field(None, min_length=1, max_length=64)

    @field_validator("ids")
    @classmethod
    def unique_ids(cls, value):
        if len(set(value)) != len(value) or any(not item or len(item) > 64 for item in value):
            raise ValueError("请选择不重复的有效收藏资料")
        return value

    @model_validator(mode="after")
    def valid_action(self):
        if self.action == "remove" and self.group_id is not None:
            raise ValueError("取消收藏时不能指定分组")
        return self


class UsageEvent(Input):
    event_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    kind: Literal["active", "download_ok", "download_failed"]
    catalog_id: str | None = Field(None, max_length=64)


class Renewal(Input):
    revision: int = Field(ge=1)
    days: int = Field(ge=1, le=3660)
    note: str = Field("", max_length=300)


class SupportSettings(Input):
    revision: int = Field(0, ge=0)
    wechat: str = Field("", max_length=80)
    phone: str = Field("", max_length=40, pattern=r"^[0-9+() -]*$")
    email: str = Field("", max_length=120)
    hours: str = Field("", max_length=120)
    benefits: str = Field("VIP 可按资料权限查看完整原稿与下载 PDF，具体范围以资料详情为准。", max_length=2000)
    qr_url: str = Field("", max_length=500)


class TopicInput(Input):
    revision: int = Field(0, ge=0)
    title: str = Field(min_length=1, max_length=80)
    description: str = Field("", max_length=500)
    is_visible: bool = False
    sort_order: int = Field(0, ge=0, le=100000)
    paper_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("paper_ids")
    @classmethod
    def unique_ids(cls, value):
        if len(set(value)) != len(value) or any(not item or len(item) > 64 for item in value):
            raise ValueError("专题资料不能重复，且必须使用有效条目")
        return value


class RevisionItem(Input):
    id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1)


class CatalogBatch(Input):
    items: list[RevisionItem] = Field(min_length=1, max_length=50)
    action: Literal["category", "published", "withdrawn", "access", "tags"]
    category_id: str = Field("", max_length=64)
    view_access: Literal["inherit", "free", "vip"] = "inherit"
    download_access: Literal["inherit", "free", "vip"] = "inherit"
    confirm_publication: bool = False
    tag_ids: list[str] = Field(default_factory=list, max_length=25)

    @model_validator(mode="after")
    def valid_action(self):
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("批量操作中不能重复选择资料")
        if self.action == "category" and not self.category_id:
            raise ValueError("请选择分类")
        if self.action == "published" and not self.confirm_publication:
            raise ValueError("发布前请确认所选资料内容及访问权限")
        if self.action == "tags":
            if not self.tag_ids:
                raise ValueError("请至少选择一个标签")
            if len(set(self.tag_ids)) != len(self.tag_ids) or any(not item or len(item) > 64 for item in self.tag_ids):
                raise ValueError("标签选择无效或重复")
        if self.view_access == "vip" and self.download_access == "free":
            raise ValueError("VIP 内容不能免费提供 PDF")
        return self


class CatalogRevision(Input):
    revision: int = Field(ge=1)
    paper_id: str = Field(min_length=1, max_length=64)
    note: str = Field(min_length=2, max_length=1000)
    confirm_publication: bool = False
