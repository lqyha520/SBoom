from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

# .env 路径固定为 config.py 所在目录的上级（即 backend/.env）
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # LLM（必须通过 .env 或环境变量提供）
    llm_api_key: str  # 无默认值，缺失时启动即报错
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-pro"
    llm_temperature: float = 0.4
    llm_max_tokens: int = 4096
    llm_top_p: float = 0.9

    # 题目生成
    default_question_count: int = 5
    max_question_count: int = 10

    # 缓存
    cache_enabled: bool = True
    cache_max_size: int = 500
    cache_ttl_seconds: int = 86400

    # 服务
    host: str = "127.0.0.1"
    port: int = 8000

    class Config:
        env_file = str(_ENV_PATH)
        env_file_encoding = "utf-8"
        env_prefix = ""  # 环境变量无需前缀


@lru_cache()
def get_settings() -> Settings:
    return Settings()
