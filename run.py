"""启动入口

- DEBUG=true（开发）时启用热重载，workers 配置被忽略（reload 与多 worker 互斥）。
- 生产：WORKERS=1（默认）或 >1 开多进程；数据库必须配置 DATABASE_URL（PostgreSQL）。
"""
import socket

import uvicorn
from app.config import get_settings

settings = get_settings()

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


if __name__ == "__main__":
    ensure_port_available(settings.host, settings.port)
    kwargs = dict(
        app="app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
    if not settings.debug and settings.workers > 1:
        kwargs["workers"] = settings.workers
    uvicorn.run(**kwargs)
