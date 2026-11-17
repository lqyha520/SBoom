"""游戏存档只属于当前工作台账号，不用于排名或奖励核算。"""
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

GameId = Literal['little-shop', 'robot-maze', 'rocket-math', 'memory-match', 'fraction-pizza',
                 'poem-order', 'idiom-fill', 'word-spell', 'word-market', 'clock-town']


class GameSaveInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    mutation_id: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    progress: dict[str, Any]

    @field_validator('progress')
    @classmethod
    def bounded_progress(cls, value):
        if type(value.get('version')) is not int or value['version'] != 1:
            raise ValueError('游戏存档版本不支持')
        try:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (ValueError, RecursionError) as exc:
            raise ValueError('游戏存档格式无效') from exc
        if len(encoded.encode('utf-8')) > 128 * 1024:
            raise ValueError('单个游戏存档不得超过 128 KB')
        return value


class GameSave(BaseModel):
    game_id: GameId
    revision: int
    mutation_id: str
    progress: dict[str, Any]
    updated_at: int


class GameSaves(BaseModel):
    items: list[GameSave]
