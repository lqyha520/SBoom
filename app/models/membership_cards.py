from pydantic import BaseModel, ConfigDict, Field


class CardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(ge=1, le=3660)
    quantity: int = Field(1, ge=1, le=1000)
    expires_at: int | None = Field(None, gt=0)

class CardRedeem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=8, max_length=64)
