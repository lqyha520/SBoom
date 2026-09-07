from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

# .env 路径固定为 config.py 所在目录的上级（即 backend/.env）
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # LLM —— 配置来源以前端为主：
    # 生成请求会带 llm_base_url/llm_model/llm_api_key（前端「模型配置」弹窗保存的值），
    # 后端仅在请求未携带时才回落到这里的值。可以把 .env 里的 LLM_* 删掉（llm_api_key 给空串即可）。
    llm_api_key: str = ""  # 允许为空：前端配置为主
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.4
    llm_max_tokens: int = 4096
    llm_top_p: float = 0.9

    # 题目生成
    default_question_count: int = 5
    max_question_count: int = 10

    # 缓存（默认关闭：用户要求每次生成都真实调用 LLM，保证试卷不重复）
    cache_enabled: bool = False
    cache_max_size: int = 500
    cache_ttl_seconds: int = 86400

    # 服务
    host: str = "127.0.0.1"
    port: int = 8000

    # 多用户
    secret_key: str = ""  # 会话签名/加密密钥；空则自动生成并持久化到 data/secret_key.txt
    cors_origins: str = ""  # 逗号分隔的跨域白名单；空 = 仅同源（默认，最安全）

    # 后台管理
    admin_username: str = ""  # 种子管理员用户名（可选；设置后启动时自动创建/对齐）
    admin_password: str = ""  # 种子管理员密码（需与 ADMIN_USERNAME 同时设置）

    class Config:
        env_file = str(_ENV_PATH)
        env_file_encoding = "utf-8"
        env_prefix = ""  # 环境变量无需前缀


@lru_cache()
def get_settings() -> Settings:
    return Settings()
