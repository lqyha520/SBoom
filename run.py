"""启动入口

- DEBUG=true（开发）时启用热重载，workers 配置被忽略（reload 与多 worker 互斥）。
- 生产：WORKERS=1（默认）或 >1 开多进程；数据库必须配置 DATABASE_URL（PostgreSQL）。
"""
import logging
import os
import socket
from tempfile import TemporaryDirectory

import uvicorn

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("run")


def start_server() -> None:
    uvicorn.run(
        "app.main:app", host=settings.host, port=settings.port, reload=settings.debug,
        workers=settings.workers if not settings.debug and settings.workers > 1 else None,
        timeout_graceful_shutdown=30, timeout_keep_alive=15,
        log_config=None, access_log=False,
    )


def ensure_port_available(host: str, port: int) -> None:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        # Uvicorn uses SO_REUSEADDR; Windows can otherwise accept duplicate listeners.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind((host, port))
        except OSError as exc:
            raise SystemExit(f"Cannot bind {host}:{port}. Stop the existing service or change PORT. ({exc})") from exc


def forwarded_ips_warning() -> str | None:
    """FORCE_HTTPS=true 意味着前面有反向代理；uvicorn 默认只信任 127.0.0.1 发来的 X-Forwarded-For。

    Docker bridge 部署时代理的源地址是网关 IP（172.x.x.x），不在信任名单里，
    于是每个请求的 client IP 都变成同一个网关地址——登录/注册按 IP 的限流会塌成一个桶，
    一个用户被限流等于全站被限流。需要把代理容器/网段填进 FORWARDED_ALLOW_IPS。
    不要填 *：任何直连的客户端都能伪造 X-Forwarded-For 绕过限流。
    """
    if not settings.force_https:
        return None
    allow = os.environ.get("FORWARDED_ALLOW_IPS", "").strip()
    if allow not in ("", "127.0.0.1"):
        return None
    return (
        "FORCE_HTTPS=true 但 FORWARDED_ALLOW_IPS 未设置（或仅 127.0.0.1）。"
        "若反向代理经 Docker bridge 访问本服务，其源地址是网关 IP，X-Forwarded-For 会被忽略，"
        "所有请求的客户端 IP 都变成同一个网关地址，按 IP 的登录/注册限流会塌成一个桶。"
        "请把代理的真实地址填入 FORWARDED_ALLOW_IPS（例如 172.18.0.1 或代理容器 IP），不要使用 *。"
    )


if __name__ == "__main__":
    from app.logging_config import configure_logging
    configure_logging()
    ensure_port_available(settings.host, settings.port)
    warning = forwarded_ips_warning()
    if warning:
        logger.warning(warning)
    if settings.metrics_enabled and (settings.workers > 1 or settings.debug):
        # The directory must be configured before importing prometheus_client.
        with TemporaryDirectory(prefix="learn-coach-metrics-") as directory:
            os.environ["PROMETHEUS_MULTIPROC_DIR"] = directory
            os.environ["LC_METRICS_MANAGED"] = "1"
            from app.metrics_exporter import start_metrics_server
            server, thread = start_metrics_server(settings.metrics_port, settings.metrics_host)
            try:
                start_server()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
                os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)
                os.environ.pop("LC_METRICS_MANAGED", None)
    else:
        start_server()
