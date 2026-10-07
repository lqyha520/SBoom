"""统一应用、Uvicorn 与请求日志；初始化可由父进程和应用重复调用。"""
import logging
import logging.handlers
import sys
from pathlib import Path

from app.config import get_settings
from app.request_context import RequestIdFilter

_configured = False

def configure_logging() -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    fallback = False
    formatter: logging.Formatter
    try:
        if settings.log_format == "text":
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s [%(request_id)s]: %(message)s")
        else:
            from pythonjsonlogger.json import JsonFormatter
            formatter = JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s %(request_id)s")
    except ImportError:
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        fallback = True
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if settings.log_to_file:
        if settings.workers > 1:
            raise RuntimeError("LOG_TO_FILE requires WORKERS=1")
        path = Path(__file__).resolve().parent.parent / "data" / "logs" / "application.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(path, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(RequestIdFilter())
        root.addHandler(handler)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    # 访问日志由 app.access 记录路由模板，避免重复及原始查询参数泄露。
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.disabled = True
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    _configured = True
    if fallback:
        logging.getLogger(__name__).warning("JSON 日志依赖不可用，已退回文本日志")
