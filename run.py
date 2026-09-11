"""启动入口

- DEBUG=true（开发）时启用热重载，workers 配置被忽略（reload 与多 worker 互斥）。
- 生产：WORKERS=1（默认）或 >1 开多进程；多 worker 建议配合 PostgreSQL 使用。
"""
import uvicorn
from app.config import get_settings

settings = get_settings()

if __name__ == "__main__":
    kwargs = dict(
        app="app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
    if not settings.debug and settings.workers > 1:
        kwargs["workers"] = settings.workers
    uvicorn.run(**kwargs)
