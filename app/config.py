import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    llm_max_tokens: int = Field(16384, ge=1024, le=131072)
    llm_top_p: float = 0.9
    provider_allow_private: bool = False  # 内网自建模型需显式启用；默认只允许公网 HTTPS
    provider_max_response_bytes: int = Field(8 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024)
    provider_failure_threshold: int = Field(2, ge=1, le=1000)
    provider_cooldown_seconds: int = Field(30, ge=1, le=300)
    # CDN 边缘兜底地址（逗号分隔的公网 IP）：某主机的 DNS 全部落在被丢包的网段时，改用这些地址建连。
    # Host 与 sni_hostname 仍是原主机，TLS 证书校验不变，所以只能拿到该主机自己的内容。
    provider_edge_fallback_ips: str = ""

    # 题目生成
    default_question_count: int = 5
    max_question_count: int = 30
    generation_daily_limit: int = Field(20, ge=0, le=100000)  # 0 关闭每用户每日成功生成额度（失败与结果未知不再占用）
    generation_daily_failure_limit: int = Field(30, ge=0, le=100000)  # 0 关闭失败次数上限；失败仍消耗全站预算，所以要有独立闸
    generation_user_concurrency: int = Field(2, ge=1, le=100)
    generation_global_concurrency: int = Field(6, ge=1, le=1000)
    generation_repair_limit: int = Field(3, ge=0, le=10)
    generation_lease_seconds: int = Field(3600, ge=60, le=86400)
    generation_heartbeat_seconds: int = Field(90, ge=30, le=300)
    generation_global_daily_tokens: int = Field(2_000_000, ge=10000)
    generation_global_daily_images: int = Field(100, ge=1)
    generation_result_days: int = Field(7, ge=1, le=365)

    # 服务
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False  # 仅开发时设 true：启用热重载。生产必须为 false
    workers: int = 1  # worker 进程数；>1 时建议配合 PostgreSQL 使用
    log_to_file: bool = False
    # 日志格式：auto/json 使用 JSON；text 供本机阅读
    log_format: Literal["auto", "json", "text"] = "auto"
    # 非上传接口的请求体上限（按 Content-Length 在中间件层直接 413）；上传接口自带流式限额
    max_request_body_bytes: int = Field(4 * 1024 * 1024, ge=1024, le=1024 * 1024 * 1024)
    metrics_enabled: bool = False
    metrics_host: str = "127.0.0.1"
    metrics_port: int = Field(9090, ge=1, le=65535)
    maintenance_enabled: bool = True
    import_default_view_access: Literal["free", "vip"] = "free"
    import_default_download_access: Literal["free", "vip"] = "free"
    image_storage_mb: int = Field(512, ge=16, le=102400)

    # 数据库：PostgreSQL 连接串（必填；本服务仅支持 PG），例如
    #   postgresql://learncoach:learncoach@127.0.0.1:5432/learncoach
    database_url: str = ""
    # 连接池：每个 worker 进程各自一池；DB_POOL_MAX 应 >= 预期并发（线程池上限会按它放大）
    db_pool_min: int = Field(1, ge=1, le=100)
    db_pool_max: int = Field(10, ge=1, le=500)
    db_pool_timeout: float = Field(30.0, ge=1.0, le=600.0)  # 池耗尽时最多等多久（秒）
    # 服务端超时（毫秒，0 = 不限）：单条语句 / 等锁（含 db(serialized=...) 的事务级咨询锁）/ 事务内空闲
    db_statement_timeout_ms: int = Field(30000, ge=0, le=3_600_000)
    db_lock_timeout_ms: int = Field(2500, ge=0, le=3_600_000)
    db_idle_in_transaction_timeout_ms: int = Field(60000, ge=0, le=3_600_000)

    # 注册开关
    registration_enabled: bool = True  # 关闭后 /auth/register 返回 403
    mini_registration_enabled: bool = True

    # 多用户
    secret_key: str = ""  # 会话签名/加密密钥；空则自动生成并持久化到 data/secret_key.txt
    encryption_keys: dict[str, str] = {}  # JSON 密钥环，保留旧编号直到重新加密完成
    encryption_active_key: str = ""
    session_idle_seconds: int = Field(86400, ge=300, le=30 * 86400)
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
    # 小程序虚拟支付（XPay）：启用后会员订单改走 wx.requestVirtualPayment。
    # env=0 使用现网 AppKey，env=1 使用沙箱 AppKey；两者在微信公众平台「虚拟支付」中分别生成。
    wechat_virtual_pay_enabled: bool = False
    wechat_virtual_offer_id: str = ""
    wechat_virtual_app_key: str = ""
    wechat_virtual_sandbox_app_key: str = ""
    wechat_virtual_env: int = Field(0, ge=0, le=1)
    wechat_virtual_ios_enabled: bool = False
    wechat_virtual_push_token: str = ""
    wechat_virtual_push_aes_key: str = ""
    wechat_subscribe_template_id: str = ""
    wechat_subscribe_title_field: str = ""
    wechat_subscribe_body_field: str = ""
    wechat_subscribe_time_field: str = ""

    # 后台管理
    admin_username: str = ""  # 种子管理员用户名（可选；设置后启动时自动创建/对齐）
    admin_password: str = ""  # 种子管理员密码（需与 ADMIN_USERNAME 同时设置）
    admin_reset_on_start: bool = False  # 应急重置开关；使用后关闭，同时吊销旧会话
    api_docs_enabled: bool | None = None  # 未指定时 HTTPS 生产环境关闭
    db_auto_migrate: bool = True  # 生产发布先执行 python -m app.migrations，再设为 false

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        env_prefix="",  # 环境变量无需前缀
    )

    def validate_startup(self) -> None:
        """启动时验证必填配置项，避免运行时才发现错误。

        刻意不叫 ``validate``：那是 ``pydantic.BaseModel`` 的类方法，同名定义会把
        父类的 ``Settings.validate(value)`` 覆盖成实例方法。
        """
        errors = []

        # 必填项
        if not self.database_url:
            errors.append("DATABASE_URL 必须配置（PostgreSQL 连接串，如 postgresql://user:pass@host:5432/db）")

        # 相关性检查
        if self.log_to_file and self.workers > 1:
            errors.append("LOG_TO_FILE=true 与 WORKERS>1 不兼容，多进程部署应使用容器日志")

        if self.encryption_active_key and self.encryption_active_key not in self.encryption_keys:
            errors.append("ENCRYPTION_ACTIVE_KEY 必须存在于 ENCRYPTION_KEYS")
        if any(not key or ":" in key or len(value.encode()) < 32 for key, value in self.encryption_keys.items()):
            errors.append("加密密钥编号不能为空或含冒号，每把密钥至少 32 字节")

        # 支付配置相关性检查
        if self.wechat_pay_enabled:
            required_pay_fields = [
                ("wechat_pay_mchid", "商户号"),
                ("wechat_pay_serial_no", "商户证书序列号"),
                ("wechat_pay_private_key_path", "商户私钥路径"),
                ("wechat_pay_api_v3_key", "API v3 密钥"),
                ("wechat_pay_notify_origin", "支付回调域名"),
            ]
            for field, name in required_pay_fields:
                if not getattr(self, field):
                    errors.append(f"启用微信支付时必须配置 {name}（{field}）")

        # 虚拟支付相关性检查：AppID/AppSecret 用于 code2session 与 access_token。
        if self.wechat_virtual_pay_enabled:
            if not re.fullmatch(r"wx[a-zA-Z0-9]{16}", self.wechat_app_id):
                errors.append("启用虚拟支付时必须配置正确的小程序 AppID（WECHAT_APP_ID）")
            if not self.wechat_app_secret:
                errors.append("启用虚拟支付时必须配置小程序 AppSecret（WECHAT_APP_SECRET）")
            if not re.fullmatch(r"\d{1,20}", self.wechat_virtual_offer_id):
                errors.append("启用虚拟支付时必须配置数字 OfferID（WECHAT_VIRTUAL_OFFER_ID）")
            app_key = self.wechat_virtual_sandbox_app_key if self.wechat_virtual_env == 1 else self.wechat_virtual_app_key
            if not app_key:
                errors.append("虚拟支付缺少对应环境的 AppKey（WECHAT_VIRTUAL_APP_KEY / WECHAT_VIRTUAL_SANDBOX_APP_KEY）")
            if self.wechat_virtual_push_token and len(self.wechat_virtual_push_aes_key) != 43:
                errors.append("配置虚拟支付消息推送 Token 时必须同时配置 43 位 EncodingAESKey（WECHAT_VIRTUAL_PUSH_AES_KEY）")

        # 种子管理员相关性检查
        has_username = bool(self.admin_username)
        has_password = bool(self.admin_password)
        if has_username != has_password:
            errors.append("ADMIN_USERNAME 和 ADMIN_PASSWORD 必须同时设置或同时留空")

        if errors:
            raise ValueError(
                "配置验证失败：\n" + "\n".join(f"  - {e}" for e in errors) +
                "\n请在 .env 文件中修正配置"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
