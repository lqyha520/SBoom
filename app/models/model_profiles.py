"""按列表顺序执行的模型配置，ID 用于绑定各自保存的密钥。"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.image_generation import ImageModelConfig


class ProfileIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field("", max_length=80)
    enabled: bool = True


class TextModelProfile(ProfileIdentity):
    baseUrl: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)
    apiKey: str = Field("", max_length=4000, repr=False)
    timeout: int = Field(120, ge=10, le=600)
    maxTokens: int = Field(16384, ge=1024, le=131072)


class ImageModelProfile(ImageModelConfig, ProfileIdentity):
    pass


class ProfilesBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    models: list
    revision: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({profile.id for profile in self.models}) != len(self.models):
            raise ValueError("模型配置 ID 不能重复")
        return self


class TextModelProfiles(ProfilesBase):
    models: list[TextModelProfile] = Field(max_length=8)


class ImageModelProfiles(ProfilesBase):
    models: list[ImageModelProfile] = Field(max_length=8)
