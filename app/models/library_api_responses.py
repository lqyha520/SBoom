"""library 成功响应契约；历史快照与扩展字段兼容现存数据。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class LibraryCreateFolderResponse(ApiResponseModel):
    id: str
    name: str


class LibraryFoldersItemsItem(ApiResponseModel):
    created_at: int
    id: str
    name: str
    paper_count: int


class LibraryFoldersResponse(ApiResponseModel):
    items: list[LibraryFoldersItemsItem]


LibraryRenameFolderResponse = LibraryCreateFolderResponse


class LibrarySummaryResponse(ApiResponseModel):
    favorites: int
    grades: list[str]
    paper_limit: int
    papers: int
    storage_bytes: int
    storage_limit_bytes: int
    subjects: list[str]
    unfiled: int
