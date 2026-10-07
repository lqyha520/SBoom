"""Inputs for consumer accounts and administrator membership changes."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: 登录账号保持固定格式；展示昵称单独接受微信昵称（含空格和表情）。
USERNAME_PATTERN = re.compile(r"[\w\u4e00-\u9fa5-]{2,32}")
NEW_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_-]{2,32}")
NICKNAME_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]")
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_BASE64 = 4 * ((MAX_AVATAR_BYTES + 2) // 3)


def normalize_nickname(value):
    if not isinstance(value, str):
        return value
    if NICKNAME_CONTROLS.search(value):
        raise ValueError("昵称不能包含换行或控制字符")
    value = value.strip()
    if not value:
        raise ValueError("昵称不能为空")
    if len(value) > 32:
        raise ValueError("昵称需为 1-32 个字符")
    return value


def _check_username(value, label):
    if not USERNAME_PATTERN.fullmatch(value):
        raise ValueError(f"{label}需为 2-32 位字母、数字、下划线或中文")
    return value


#: 预设头像键。前端按同一份键表渲染图案与配色；新增头像时两端一起改。
PROFILE_AVATARS = (
    "fox", "panda", "penguin", "deer", "rabbit", "koala", "owl", "dolphin",
    "tiger", "frog", "bee", "octopus", "cat", "whale", "turtle", "squirrel",
)


class MiniCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("username")
    @classmethod
    def username_format(cls, value):
        return _check_username(value, "用户名")


class MiniRegistration(MiniCredentials):
    password: str = Field(min_length=8, max_length=128)
    """New login identifiers are ASCII; existing Chinese accounts can still log in."""

    @field_validator("username")
    @classmethod
    def username_format(cls, value):
        if not NEW_USERNAME_PATTERN.fullmatch(value):
            raise ValueError("账号需为 2-32 位英文字母、数字、下划线或短横线，不能使用中文")
        return value


class MiniProfileUpdate(BaseModel):
    """用户自助改资料：只更新传上来的字段，至少传一个。"""

    model_config = ConfigDict(extra="forbid")
    username: str | None = Field(None, min_length=1, max_length=32)
    nickname: str | None = Field(None, min_length=1, max_length=32)
    avatar: str | None = Field(None, max_length=32)

    @field_validator("username", "nickname", mode="before")
    @classmethod
    def username_format(cls, value):
        return normalize_nickname(value)

    @field_validator("avatar")
    @classmethod
    def avatar_known(cls, value):
        """None = 不改动；空串 = 恢复默认形象；其余必须在预设键表里。"""
        if value is not None and value != "" and value not in PROFILE_AVATARS:
            raise ValueError("头像不在可选范围内")
        return value

    @model_validator(mode="after")
    def has_something_to_update(self):
        if self.username is None and self.nickname is None and self.avatar is None:
            raise ValueError("没有需要更新的内容")
        return self


class MiniPasswordUpdate(BaseModel):
    """改/设密码。账号已有密码时必须带 current_password 验证。"""

    model_config = ConfigDict(extra="forbid")
    current_password: str = Field("", max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class MiniAvatarUpdate(BaseModel):
    """The selected image and optional nickname are saved in one transaction."""

    model_config = ConfigDict(extra="forbid")
    image: str = Field(min_length=1, max_length=MAX_AVATAR_BASE64)
    nickname: str | None = Field(None, min_length=1, max_length=32)

    @field_validator("nickname", mode="before")
    @classmethod
    def nickname_format(cls, value):
        return normalize_nickname(value)


class AdminProfileUpdate(BaseModel):
    """管理员改小程序用户资料：昵称 / 头像 / 重置密码，至少传一个。

    与用户自助改资料的 ``MiniProfileUpdate`` 的区别：这里的 ``revision`` 是乐观锁，
    且可以重置密码（不需要原密码）——那是管理员代用户找回账号的场景。
    """

    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    username: str | None = Field(None, min_length=1, max_length=32)
    nickname: str | None = Field(None, min_length=1, max_length=32)
    avatar: str | None = Field(None, max_length=32)
    new_password: str | None = Field(None, min_length=8, max_length=128)

    @field_validator("username", "nickname", mode="before")
    @classmethod
    def username_format(cls, value):
        return normalize_nickname(value)

    @field_validator("avatar")
    @classmethod
    def avatar_known(cls, value):
        if value is not None and value != "" and value not in PROFILE_AVATARS:
            raise ValueError("头像不在可选范围内")
        return value

    @model_validator(mode="after")
    def has_something_to_update(self):
        if self.username is None and self.nickname is None and self.avatar is None and self.new_password is None:
            raise ValueError("没有需要更新的内容")
        return self


class MembershipUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    membership: Literal["regular", "vip"]
    vip_expires_at: int | None = Field(None, gt=0, le=253402300799)
    is_active: bool

    @model_validator(mode="after")
    def regular_has_no_expiry(self):
        if self.membership == "regular" and self.vip_expires_at is not None:
            raise ValueError("普通用户不应设置会员到期时间")
        return self
