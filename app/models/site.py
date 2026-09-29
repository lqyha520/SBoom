"""小程序运营内容的请求模型（分类 / Banner / 公告 / 协议文档 / 年级科目字典）。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CategoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    description: str = Field("", max_length=300)
    icon: str = Field("", max_length=40)
    sort_order: int = Field(0, ge=0, le=100000)
    is_visible: bool = True

    @model_validator(mode="after")
    def no_blank_name(self):
        if not self.name.strip():
            raise ValueError("分类名不能为空")
        return self


class CategoryUpdate(CategoryInput):
    revision: int = Field(ge=0)


class BannerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kicker: str = Field("", max_length=40)
    title: str = Field(min_length=1, max_length=40)
    subtitle: str = Field("", max_length=60)
    action_label: str = Field("", max_length=20)
    target_type: Literal["none", "keyword", "category", "subject", "paper"] = "none"
    target_value: str = Field("", max_length=64)
    image_fit: Literal["contain", "cover"] = "contain"
    sort_order: int = Field(0, ge=0, le=100000)
    is_visible: bool = True

    @model_validator(mode="after")
    def target_matches_type(self):
        if not self.title.strip():
            raise ValueError("Banner 标题不能为空")
        self.target_value = self.target_value.strip()
        if self.target_type == "none":
            self.target_value = ""
        elif not self.target_value:
            raise ValueError("选择了跳转方式就必须填写跳转目标")
        return self


class BannerUpdate(BannerInput):
    revision: int = Field(ge=0)


class NoticeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=60)
    body: str = Field("", max_length=2000)
    placement: Literal["popup", "banner"] = "popup"
    level: Literal["info", "warning"] = "info"
    starts_at: int = Field(0, ge=0, le=4102444800)
    ends_at: int = Field(0, ge=0, le=4102444800)
    is_visible: bool = True

    @model_validator(mode="after")
    def valid_window(self):
        if not self.title.strip():
            raise ValueError("公告标题不能为空")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class NoticeUpdate(NoticeInput):
    revision: int = Field(ge=0)


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=60)
    body: str = Field("", max_length=20000)


class DictionaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["grade", "subject", "knowledge_point"]
    value: str = Field(min_length=1, max_length=120)
    label: str = Field("", max_length=80)
    sort_order: int = Field(0, ge=0, le=100000)
    is_visible: bool = True
    parent: str = Field("", max_length=80)  # 知识点必填，格式「年级id|科目id」

    @model_validator(mode="after")
    def no_blank_value(self):
        if not self.value.strip():
            raise ValueError("取值不能为空")
        if self.kind == "knowledge_point":
            parts = self.parent.split("|")
            if len(parts) != 2 or not all(parts):
                raise ValueError("知识点必须挂在一个年级+科目组合下")
        elif self.parent:
            raise ValueError("只有知识点可以指定所属组合")
        return self


class DictionaryLinksUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_ids: list[str] = Field(default_factory=list, max_length=100)


class DictionaryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    value: str = Field(min_length=1, max_length=120)
    label: str = Field("", max_length=80)
    sort_order: int = Field(0, ge=0, le=100000)
    is_visible: bool = True


class ReorderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=500)


class DictionaryOrderItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=0)


class DictionaryReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["grade", "subject", "knowledge_point"]
    parent: str = Field("", max_length=80)
    items: list[DictionaryOrderItem] = Field(min_length=1, max_length=500)


class DictionaryAdopt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["grade", "subject"]
    values: list[str] = Field(min_length=1, max_length=200)
