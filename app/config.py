from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
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
    max_question_count: int = 30
    generation_daily_limit: int = Field(100, ge=1, le=100000)
    generation_user_concurrency: int = Field(3, ge=1, le=100)
    generation_global_concurrency: int = Field(6, ge=1, le=1000)
    generation_repair_limit: int = Field(3, ge=0, le=10)
    generation_lease_seconds: int = Field(3600, ge=60, le=86400)
    generation_result_days: int = Field(7, ge=1, le=365)

    # 服务
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False  # 仅开发时设 true：启用热重载。生产必须为 false
    workers: int = 1  # worker 进程数；>1 时建议配合 PostgreSQL 使用

    # 数据库：PostgreSQL 连接串（必填；本服务仅支持 PG），例如
    #   postgresql://learncoach:learncoach@127.0.0.1:5432/learncoach
    database_url: str = ""

    # 注册开关
    registration_enabled: bool = True  # 关闭后 /auth/register 返回 403
    mini_registration_enabled: bool = True

    # 多用户
    secret_key: str = ""  # 会话签名/加密密钥；空则自动生成并持久化到 data/secret_key.txt
    cors_origins: str = ""  # 逗号分隔的跨域白名单；空 = 仅同源（默认，最安全）
    force_https: bool = False  # HTTPS 部署时设 true：会话 Cookie 加 Secure 标志

    # Paper library: private files live on the local disk (data/paper-files by default).
    archive_local_dir: str = ""
    archive_max_papers: int = Field(1000, ge=1, le=100000)
    archive_storage_mb: int = Field(512, ge=16, le=102400)
    archive_max_bundle_mb: int = Field(40, ge=1, le=64)

    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    mini_session_days: int = Field(7, ge=1, le=30)
    # Consumer commerce and subscription delivery remain opt-in until deployment is configured.
    wechat_pay_enabled: bool = False
    wechat_pay_mchid: str = ""
    wechat_pay_serial_no: str = ""
    wechat_pay_private_key_path: str = ""
    wechat_pay_platform_serial: str = ""
    wechat_pay_platform_key_path: str = ""
    wechat_pay_api_v3_key: str = ""
    wechat_pay_notify_origin: str = ""
    wechat_pay_ios_enabled: bool = False
    wechat_pay_auto_reconcile: bool = False
    wechat_subscribe_template_id: str = ""
    wechat_subscribe_title_field: str = ""
    wechat_subscribe_body_field: str = ""
    wechat_subscribe_time_field: str = ""

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
