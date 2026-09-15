"""Versioned archive wire contract. Rich text remains data, never executable HTML."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SnapshotSection(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str = Field(min_length=1, max_length=120)
    name: str | None = Field(None, max_length=120)
    data: dict
    layout: dict

    @field_validator("data")
    @classmethod
    def validate_questions(cls, data):
        questions = data.get("questions")
        if not isinstance(questions, list) or len(questions) > 500:
            raise ValueError("A section must contain at most 500 questions")
        if any(not isinstance(question, dict) for question in questions):
            raise ValueError("Questions must be objects")
        return data


class SnapshotPaper(BaseModel):
    model_config = ConfigDict(extra="allow")
    grade: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=80)
    title: str = Field(max_length=240)
    keyword: str = Field(max_length=2000)
    difficulty: str = Field(max_length=40)
    sections: list[SnapshotSection] = Field(min_length=1, max_length=60)


class ExportOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["student", "withAnswers", "answersOnly"] = "student"
    addDay: bool
    renderer_version: Literal["web-v1"] = "web-v1"


class PaperSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    paper: SnapshotPaper
    template: dict
    style: dict
    export_options: ExportOptions

    @model_validator(mode="after")
    def complete_snapshot(self):
        template_fields = {"id", "name", "tag", "showInfoRow", "showNotice", "showScore",
                           "titlePrefix", "titleSuffix", "footer", "headerExtra"}
        style_fields = {"bg", "bgOpacity", "banner", "secColor", "frame", "encourage", "reward",
                        "kidFont", "exportBg", "titleScale", "titleOffsetY"}
        if not template_fields.issubset(self.template) or not style_fields.issubset(self.style):
            raise ValueError("The full template and paper style are required")
        count = sum(len(section.data["questions"]) for section in self.paper.sections)
        if not 1 <= count <= 1500:
            raise ValueError("A paper must contain 1 to 1500 questions")
        return self


class ArchiveCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    source_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    folder_id: str | None = Field(None, max_length=64)
    group_name: str = Field("", max_length=120)
    group_id: str = Field("", max_length=100, pattern=r"^[a-zA-Z0-9_-]*$")
    snapshot: PaperSnapshot


class ArchiveUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, min_length=1, max_length=240)
    folder_id: str | None = Field(None, max_length=64)
    favorite: bool | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        if value is not None and not value.strip():
            raise ValueError("The title cannot be blank")
        return value.strip() if value else value


class FolderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("The folder name cannot be blank")
        return value
