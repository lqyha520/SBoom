"""generate 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class GenerateGetAvailableScopesAvailable(ApiResponseModel):
    小学一年级: list[str]
    小学三年级: list[str]
    小学二年级: list[str]
    小学五年级: list[str]
    小学六年级: list[str]
    小学四年级: list[str]


class GenerateGetAvailableScopesResponse(ApiResponseModel):
    available: GenerateGetAvailableScopesAvailable


class GenerateSubmitFeedbackResponse(ApiResponseModel):
    message: str
    status: str
