"""小红书创作流程中各模块的独立数据契约。"""
import re
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Kind = Literal['ideas', 'materials', 'drafts', 'publications']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Idea(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    status: Literal['inbox', 'planned', 'creating', 'done', 'archived'] = 'inbox'
    grade: str = Field(default='一年级', min_length=1, max_length=20)
    subject: str = Field(default='数学', min_length=1, max_length=20)
    keyword: str = Field(default='', max_length=100)
    audience: str = Field(default='', max_length=200)
    problem: str = Field(default='', max_length=2000)
    angle: str = Field(default='', max_length=2000)
    format: str = Field(default='分层练习', max_length=80)
    priority: Literal['high', 'normal', 'low'] = 'normal'
    due_date: date | None = None
    source_note_id: str = Field(default='', max_length=80)
    source_publication_id: str = Field(default='', max_length=80)
    notes: str = Field(default='', max_length=4000)


class Exercise(StrictModel):
    stem: str = Field(default='', max_length=3000)
    options: list[str] = Field(default_factory=list, max_length=8)
    answer: str = Field(default='', max_length=2000)
    analysis: str = Field(default='', max_length=4000)
    quality_issues: list[str] = Field(default_factory=list, max_length=20)


class Material(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    status: Literal['draft', 'review', 'ready', 'archived'] = 'draft'
    grade: str = Field(default='一年级', min_length=1, max_length=20)
    subject: str = Field(default='数学', min_length=1, max_length=20)
    keyword: str = Field(default='', max_length=100)
    game_type: Literal['fill_blank', 'quiz', 'oral_math', 'word_problem', 'true_false'] = 'fill_blank'
    difficulty: Literal['easy', 'medium', 'hard'] = 'medium'
    question_count: int = Field(default=10, ge=1, le=30)
    instructions: str = Field(default='', max_length=2000)
    questions: list[Exercise] = Field(default_factory=list, max_length=100)
    accuracy_checked: bool = False
    scope_checked: bool = False
    layout_checked: bool = False
    review_notes: str = Field(default='', max_length=4000)
    generation_request_id: str = Field(default='', max_length=100)

    @model_validator(mode='after')
    def checked_ready(self):
        if self.status == 'ready' and (not self.questions or not all(
                q.stem and q.answer and q.analysis for q in self.questions) or not all(
                (self.accuracy_checked, self.scope_checked, self.layout_checked))):
            raise ValueError('请补全题目、答案、讲解，并完成三项复核后再标为可用')
        return self


class Card(StrictModel):
    heading: str = Field(default='', max_length=80)
    body: str = Field(default='', max_length=800)


class AccountProfile(StrictModel):
    audience: str = Field(default='', max_length=200)
    direction: str = Field(default='', max_length=1000)
    style: str = Field(default='', max_length=1000)
    topics: str = Field(default='', max_length=300)


class AccountSnapshot(AccountProfile):
    id: str = Field(default='', max_length=80)
    name: str = Field(default='', max_length=60)


class Draft(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    audience: str = Field(default='家长', max_length=200)
    angle: str = Field(default='', max_length=2000)
    status: Literal['draft', 'review', 'ready', 'archived'] = 'draft'
    headline: str = Field(default='', max_length=20)
    title_options: list[str] = Field(default_factory=list, max_length=6)
    body: str = Field(default='', max_length=2000)
    hashtags: str = Field(default='', max_length=300)
    cover_title: str = Field(default='', max_length=40)
    cover_subtitle: str = Field(default='', max_length=120)
    theme: Literal['green', 'orange', 'blue'] = 'green'
    cards: list[Card] = Field(default_factory=list, max_length=8)
    notes: str = Field(default='', max_length=4000)
    generation_request_id: str = Field(default='', max_length=100)
    source_material_revision: int = Field(default=0, ge=0)
    account_profile: AccountSnapshot = Field(default_factory=AccountSnapshot)

    @model_validator(mode='after')
    def ready_content(self):
        if self.status == 'ready' and not (self.headline and self.body and self.cover_title):
            raise ValueError('待发布笔记需要填写标题、正文和封面标题')
        return self


class PublicationContent(StrictModel):
    headline: str = Field(default='', max_length=20)
    body: str = Field(default='', max_length=2000)
    hashtags: str = Field(default='', max_length=300)
    media_notes: str = Field(default='', max_length=2000)


class PublicationMedia(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    asset_id: str = Field(default='', max_length=80)
    name: str = Field(min_length=1, max_length=255)
    media_type: Literal['image/png', 'image/jpeg', 'image/webp', 'video/mp4']
    size_bytes: int = Field(ge=1, le=40 * 1024 * 1024)
    last_modified: int = Field(default=0, ge=0)


class Publication(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    status: Literal['planned', 'ready', 'published', 'archived'] = 'planned'
    source: Literal['linked', 'custom'] = 'linked'
    custom_content: PublicationContent = Field(default_factory=PublicationContent)
    media: list[PublicationMedia] = Field(default_factory=list, max_length=9)
    account: str = Field(default='', max_length=120)
    account_id: str = Field(default='', max_length=80)
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    url: str = Field(default='', max_length=2000)
    notes: str = Field(default='', max_length=4000)
    conclusion: str = Field(default='', max_length=4000)
    next_action: str = Field(default='', max_length=2000)
    rights_checked: bool = False
    truth_checked: bool = False
    privacy_checked: bool = False
    media_checked: bool = False
    platform_checked: bool = False
    review_notes: str = Field(default='', max_length=4000)

    @field_validator('media')
    @classmethod
    def valid_media(cls, value):
        if len({item.id for item in value}) != len(value):
            raise ValueError('发布配图不能包含重复编号')
        video = any(item.media_type == 'video/mp4' for item in value)
        if video and len(value) != 1:
            raise ValueError('视频必须单独发布，不能与图片混用')
        if not video and (any(item.size_bytes > 10 * 1024 * 1024 for item in value)
                          or sum(item.size_bytes for item in value) > 30 * 1024 * 1024):
            raise ValueError('每张图片最多 10 MB，合计最多 30 MB')
        return value

    @field_validator('url')
    @classmethod
    def xhs_url(cls, value):
        if value:
            parts = urlsplit(value)
            if parts.scheme != 'https' or parts.hostname not in ('www.xiaohongshu.com', 'xiaohongshu.com', 'xhslink.com') or parts.username or parts.password or parts.port not in (None, 443):
                raise ValueError('请填写小红书 HTTPS 发布链接')
            if not parts.path.strip('/') or any(c.isspace() for c in value):
                raise ValueError('请粘贴具体笔记的链接，不是小红书首页或整段分享文案')
            if parts.hostname != 'xhslink.com' and not re.fullmatch(r'/(?:explore|discovery/item)/[a-fA-F0-9]{24}/?', parts.path):
                raise ValueError('请填写具体笔记的详情链接，或小红书分享短链接')
        return value

    @field_validator('scheduled_at', 'published_at')
    @classmethod
    def aware_time(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError('发布时间需要包含时区')
        return value

    @model_validator(mode='after')
    def published_details(self):
        if self.status == 'published' and not (self.url and self.published_at):
            raise ValueError('标记已发布前请填写发布链接和实际发布时间')
        if self.published_at and self.published_at > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError('实际发布时间不能是未来时间，请把排期填写在计划发布时间中')
        return self


MODELS: dict[str, type[BaseModel]] = {'ideas': Idea, 'materials': Material, 'drafts': Draft, 'publications': Publication}


class RecordCreate(StrictModel):
    id: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    parent_id: str | None = Field(default=None, max_length=80)
    data: dict


class RecordUpdate(StrictModel):
    revision: int = Field(ge=1)
    data: dict


class PublicationCheck(StrictModel):
    record_id: str | None = Field(default=None, max_length=80)
    parent_id: str | None = Field(default=None, max_length=80)
    data: dict


class PublicationRefresh(StrictModel):
    revision: int = Field(ge=1)


class Metric(StrictModel):
    checkpoint: Literal[1, 3, 7]
    revision: int = Field(default=0, ge=0)
    measured_at: datetime
    views: int = Field(ge=0, le=10_000_000_000)
    likes: int = Field(ge=0, le=10_000_000_000)
    saves: int = Field(ge=0, le=10_000_000_000)
    comments: int = Field(ge=0, le=10_000_000_000)
    follows: int | None = Field(default=None, ge=0, le=10_000_000_000)
    downloads: int | None = Field(default=None, ge=0, le=10_000_000_000)
    notes: str = Field(default='', max_length=2000)

    @field_validator('measured_at')
    @classmethod
    def measured_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError('统计时间需要包含时区')
        return value


class ReviewSave(StrictModel):
    revision: int = Field(ge=1)
    metric: Metric
    conclusion: str = Field(default='', max_length=4000)
    next_action: str = Field(default='', max_length=2000)


class CopyRequest(StrictModel):
    material_id: str = Field(min_length=8, max_length=80)
    material_revision: int = Field(ge=1)
    audience: str = Field(default='家长', max_length=200)
    angle: str = Field(default='', max_length=2000)
    account_profile: AccountSnapshot = Field(default_factory=AccountSnapshot)


class CoverTemplate(StrictModel):
    theme: Literal['green', 'orange', 'blue'] = 'green'
    cover_title: str = Field(default='', max_length=40)
    cover_subtitle: str = Field(default='', max_length=120)
    cards: list[Card] = Field(default_factory=list, max_length=8)


class AssetMetadata(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=20)
    rights: Literal['unknown', 'original', 'licensed'] = 'unknown'
    source: str = Field(default='', max_length=2000)
    notes: str = Field(default='', max_length=2000)
    archived: bool = False

    @field_validator('tags')
    @classmethod
    def valid_tags(cls, value):
        if any(not tag.strip() or len(tag.strip()) > 30 for tag in value):
            raise ValueError('标签应为 1–30 字，最多 20 个')
        return list(dict.fromkeys(tag.strip() for tag in value))

    @model_validator(mode='after')
    def licensed_source(self):
        if self.rights == 'licensed' and not self.source:
            raise ValueError('授权素材需要记录来源与授权依据')
        return self


class AssetUpdate(StrictModel):
    revision: int = Field(ge=1)
    data: AssetMetadata


class TemplateCreate(StrictModel):
    data: AssetMetadata
    template: CoverTemplate
