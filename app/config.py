from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

APP_VERSION = "0.5.0"  # 唯一版本号来源（main.py / admin stats 都引用这里）

# .env 路径固定为 config.py 所在目录的上级（即 backend/.env）
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # LLM —— 配置来源：管理员后台「模型配置」（app_config 表）优先，.env 作兜底。
    # 生成请求不再接受客户端传入的接口地址/密钥（防 SSRF 与越权）。
    llm_api_key: str = ""  # 允许为空：仅后台已配置时使用
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.4
    llm_max_tokens: int = 4096
    llm_top_p: float = 0.9

    # 题目生成
    default_question_count: int = 5
    max_question_count: int = 10  # 单题型题目数上限（models 的 Field(le=) 与此保持一致）

    # 服务
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False  # 仅开发时设 true：启用热重载。生产必须为 false
    workers: int = 1  # worker 进程数；>1 时建议配合 PostgreSQL 使用

    # 数据库：空 = SQLite（data/users.db）；填 PostgreSQL 连接串则切到 PG，例如
    #   postgresql://learncoach:learncoach@127.0.0.1:5432/learncoach
    database_url: str = ""

    # 注册开关
    registration_enabled: bool = True  # 关闭后 /auth/register 返回 403

    # 多用户
    secret_key: str = ""  # 会话签名/加密密钥；空则自动生成并持久化到 data/secret_key.txt
    cors_origins: str = ""  # 逗号分隔的跨域白名单；空 = 仅同源（默认，最安全）
    force_https: bool = False  # HTTPS 部署时设 true：会话 Cookie 加 Secure 标志

    # 后台管理
    admin_username: str = ""  # 种子管理员用户名（可选；设置后启动时自动创建/对齐）
    admin_password: str = ""  # 种子管理员密码（需与 ADMIN_USERNAME 同时设置）

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        env_prefix="",  # 环境变量无需前缀
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
