"""Image worksheets use their own prompt, independent of paper layout models."""

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Difficulty, GameType


class ImageModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    baseUrl: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)
    apiKey: str = Field("", max_length=4000, repr=False)
    timeout: int = Field(300, ge=30, le=600)
    size: str = Field("1024x1536", max_length=30)
    responseFormat: Literal["auto", "b64_json", "url"] = "auto"

    @field_validator("baseUrl")
    @classmethod
    def valid_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (parts.scheme not in ("https", "http") or not parts.hostname
                or parts.username or parts.password or parts.query or parts.fragment):
            raise ValueError("接口地址必须是 HTTP(S) 地址，不能包含账号、查询参数或片段")
        _ = parts.port
        return value.rstrip("/")

    @field_validator("size")
    @classmethod
    def valid_size(cls, value: str) -> str:
        if value != "auto" and not re.fullmatch(r"[1-9]\d{2,3}x[1-9]\d{2,3}", value):
            raise ValueError("图片尺寸应为宽x高（例如 1024x1536），或 auto")
        return value


class ImageWorksheetItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    game_type: GameType
    question_count: int | None = Field(None, ge=1, le=20, strict=True)


class ImageWorksheetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    grade: str = Field(min_length=1, max_length=20)
    subject: str = Field(min_length=1, max_length=20)
    keyword: str = Field("", max_length=100)
    difficulty: Difficulty = Difficulty.MEDIUM
    items: list[ImageWorksheetItem] = Field(default_factory=list, max_length=5)
    style: Literal["playful", "clean", "black_white"] = "playful"
    requirements: str = Field("", max_length=600)
    image_count: int = Field(1, ge=1, le=10)
    image_index: int = Field(1, ge=1, le=10)

    @model_validator(mode="after")
    def validate_items(self):
        if self.image_index > self.image_count:
            raise ValueError("图片序号不能大于生成张数")
        if len({item.game_type for item in self.items}) != len(self.items):
            raise ValueError("同一题型只需选择一次")
        if sum(item.question_count or 1 for item in self.items) > 24:
            raise ValueError("一张图片最多安排 24 道题，自动题量的题型至少预留 1 道，请减少题量")
        return self
