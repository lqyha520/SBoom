"""image_generation 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ImageGenerationClearConfigModelsItem(ApiResponseModel):
    baseUrl: str
    enabled: bool
    hasKey: bool
    id: str
    model: str
    name: str
    requestMode: str
    responseFormat: str
    size: str
    timeout: int


class ImageGenerationClearConfigResponse(ApiResponseModel):
    baseUrl: str
    hasKey: bool
    model: str
    models: list[ImageGenerationClearConfigModelsItem]
    requestMode: str
    responseFormat: str
    revision: str
    size: str
    status: str
    timeout: int


class ImageGenerationGenerateQualityReviewChecks(ApiResponseModel):
    answer_leak: str | None = None
    diagram: str | None = None
    duplicates: str | None = None
    layout: str | None = None
    quantity: str | None = None
    scope: str | None = None
    solvability: str | None = None
    text: str | None = None


class ImageGenerationGenerateQualityReviewCountsItem(ApiResponseModel):
    count: int
    game_type: str


class ImageGenerationGenerateQualityReviewIssue(ApiResponseModel):
    question: str
    message: str


class ImageGenerationGenerateQualityReview(ApiResponseModel):
    checked_at: int | None = None
    checks: ImageGenerationGenerateQualityReviewChecks
    counts: list[ImageGenerationGenerateQualityReviewCountsItem]
    human_status: str
    issues: list[ImageGenerationGenerateQualityReviewIssue]
    model: str | None = None
    prompt_version: str
    reason: str | None = None
    status: str
    version: int


class ImageGenerationGenerateResponse(ApiResponseModel):
    asset_id: str
    byte_size: int
    expires_at: int
    height: int
    mime_type: str
    prompt: str
    quality_review: ImageGenerationGenerateQualityReview
    request_id: str
    url: str
    width: int


class ImageGenerationGetConfigResponse(ApiResponseModel):
    baseUrl: str
    enabled: bool
    hasKey: bool
    id: str
    model: str
    models: list[ImageGenerationClearConfigModelsItem]
    name: str
    requestMode: str
    responseFormat: str
    revision: str
    size: str
    timeout: int


class ImageGenerationPreviewPromptResponse(ApiResponseModel):
    prompt: str


class ImageGenerationSaveConfigResponse(ApiResponseModel):
    baseUrl: str
    hasKey: bool
    model: str
    models: list[ImageGenerationClearConfigModelsItem] | None = None
    requestMode: str
    responseFormat: str
    revision: str
    size: str
    timeout: int
