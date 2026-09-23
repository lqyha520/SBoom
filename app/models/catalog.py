"""Explicit publication controls for the authenticated public paper catalog."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AccessPolicy(BaseModel):
    view_access: Literal["inherit", "free", "vip"] = "inherit"
    download_access: Literal["inherit", "free", "vip"] = "inherit"

    @model_validator(mode="after")
    def no_download_bypass(self):
        if self.view_access == "vip" and self.download_access == "free":
            raise ValueError("VIP 观看的习题不能向普通用户开放下载")
        return self


class DownloadSettings(BaseModel):
    download_mode: Literal["pdf", "external"] = "pdf"
    external_url: str = Field("", max_length=2000)
    external_code: str = Field("", max_length=100)

    @field_validator("external_url")
    @classmethod
    def clean_external_url(cls, value):
        value = value.strip()
        if not value:
            return value
        try:
            url = urlsplit(value)
            valid = (url.scheme in ("http", "https") and url.hostname and not url.username
                     and not url.password and url.port != 0 and "\\" not in value
                     and not any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value))
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("请填写完整的 http:// 或 https:// 网盘链接，提取码请单独填写")
        return value

    @field_validator("external_code")
    @classmethod
    def clean_external_code(cls, value):
        value = value.strip()
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("提取码不能包含换行或控制字符")
        return value


class CatalogCreate(AccessPolicy, DownloadSettings):
    model_config = ConfigDict(extra="forbid")
    paper_id: str = Field("", max_length=64)
    grade: str = Field("", max_length=80)
    subject: str = Field("", max_length=80)
    title: str = Field("", max_length=240)
    description: str = Field("", max_length=2000)
    category_id: str = Field("", max_length=64)
    category: str = Field("", max_length=60)

    @model_validator(mode="after")
    def require_source(self):
        if self.download_mode == "external" and not self.external_url:
            raise ValueError("请填写网盘链接")
        if not self.paper_id and not (self.download_mode == "external" and self.title.strip()
                                      and self.grade.strip() and self.subject.strip()):
            raise ValueError("请选择习题原稿，或填写网盘习题的标题、年级和科目")
        return self


class CatalogUpdate(AccessPolicy, DownloadSettings):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field("", max_length=2000)
    category_id: str = Field("", max_length=64)
    category: str = Field("", max_length=60)
    status: Literal["draft", "published", "withdrawn"]
    featured: bool = False
    confirm_publication: bool = False

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        if not value.strip():
            raise ValueError("The title cannot be blank")
        return value.strip()


class CatalogFavorite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    favorite: bool


class TypeAccessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    view_access: Literal["free", "vip"]
    download_access: Literal["free", "vip"]

    @model_validator(mode="after")
    def no_download_bypass(self):
        if self.view_access == "vip" and self.download_access != "vip":
            raise ValueError("VIP 观看的题型必须同时限制 PDF 下载")
        return self


class CatalogWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(max_length=1000)

    @field_validator("ids")
    @classmethod
    def valid_ids(cls, values):
        if any(not value or len(value) > 64 for value in values):
            raise ValueError("无效的资料编号")
        return list(dict.fromkeys(values))
