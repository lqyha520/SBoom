"""health 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class HealthHealthResponse(ApiResponseModel):
    status: str


class HealthHealthDetailChecks(ApiResponseModel):
    database: bool
    provider_connectivity: str


class HealthHealthDetailResponse(ApiResponseModel):
    checks: HealthHealthDetailChecks
    status: str


HealthReadinessResponse = HealthHealthResponse
