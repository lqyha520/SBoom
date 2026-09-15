"""Explicit publication controls for the authenticated public paper catalog."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AccessPolicy(BaseModel):
    view_access: Literal["inherit", "free", "vip"] = "inherit"
    download_access: Literal["inherit", "free", "vip"] = "inherit"

    @model_validator(mode="after")
    def no_download_bypass(self):
        if self.view_access == "vip" and self.download_access == "free":
            raise ValueError("VIP 观看的习题不能向普通用户开放下载")
        return self


class CatalogCreate(AccessPolicy):
    model_config = ConfigDict(extra="forbid")
    paper_id: str = Field(min_length=1, max_length=64)
    title: str = Field("", max_length=240)
    description: str = Field("", max_length=2000)
    category_id: str = Field("", max_length=64)
    category: str = Field("", max_length=60)


class CatalogUpdate(AccessPolicy):
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
