"""FastAPI 主入口"""

import logging
import logging.handlers
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.generate import router as generate_router
from app.routers.me import router as me_router
from app.routers.health import router as health_router
from app.routers.library import router as library_router
from app.routers.mini import router as mini_router
from app.routers.catalog import router as catalog_router, admin_router as catalog_admin_router
from app.routers.site import router as site_router, admin_router as site_admin_router
from app.routers.experience import router as experience_router
from app.routers.engagement import router as engagement_router
from app.routers.commerce import router as commerce_router
from app.services.llm_client import llm_client
from app.services import user_store
from app.config import get_settings, APP_VERSION
from app.db import init_db, close_pg_pool
from app.security import security_warnings

settings = get_settings()


_LOG_FILE = Path(__file__).resolve().parent.parent / "server.log"
_log_handlers = [logging.StreamHandler(sys.stdout)]
if settings.log_to_file:
    if settings.workers > 1:
        raise RuntimeError("LOG_TO_FILE requires WORKERS=1; use container logs for multiple workers")
    _log_handlers.append(logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"))

# 配置日志格式：生产环境（FORCE_HTTPS=true）使用 JSON 格式，开发环境使用文本格式
use_json_logging = settings.force_https
if use_json_logging:
    try:
        from pythonjsonlogger import jsonlogger
        formatter = jsonlogger.JsonFormatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    except ImportError:
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
else:
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')

for handler in _log_handlers:
    handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=_log_handlers,
)
logger = logging.getLogger(__name__)


# ─── 生命周期 ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的管理"""
    # 启动时验证配置
    try:
        settings.validate()
    except ValueError as e:
        logger.error("配置验证失败: %s", e)
        raise

    # 初始化监控指标
    from app.metrics import init_metrics, start_metrics_server
    init_metrics(APP_VERSION)
    # 仅在生产环境启动 metrics 服务器
    if settings.force_https:
        start_metrics_server(9090)

    init_db()  # 用户库建表 + 迁移（幂等）
    for warning in security_warnings():
        logger.warning("Security configuration: %s", warning)
    # 环境变量种子管理员（可选）：确保存在并对齐角色/状态/密码
    if settings.admin_username and settings.admin_password:
        user_store.ensure_admin(settings.admin_username, settings.admin_password)
        logger.info(f"已确保种子管理员账号存在: {settings.admin_username}")
    # 模型配置收归后台：老部署里用户自配的 LLM 一次性迁移为全局配置
    from app.services.app_config import seed_llm_from_user_configs
    seed_llm_from_user_configs()
    logger.info("🚀 Learning Coach API 启动（多用户模式）")
    logger.info(f"   LLM 模型（全局兜底）: {settings.llm_model}")
    from app.services.mini_jobs import start
    maintenance_stop, maintenance_task = start()
    try:
        yield
    finally:
        maintenance_stop.set()
        if maintenance_task:
            await maintenance_task
    logger.info("🛑 应用关闭，清理资源...")
    await llm_client.close()
    close_pg_pool()


# ─── 创建应用 ───
app = FastAPI(
    title="Learning Coach API",
    description="AI+教育 课堂互动系统 —— 趣味题目/知识游戏生成服务（多用户 + 后台管理）",
    version=APP_VERSION,
    lifespan=lifespan,
)

# CORS：默认仅同源（前端由本服务直接托管，或经 Vite 代理，同源携带 Cookie）。
# 需要跨域部署时，在 .env 设置 CORS_ORIGINS=https://a.com,https://b.com
if settings.cors_origins.strip():
    _origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if "*" in _origins:
        # 通配符 + 携带凭证的组合等于向任意站点开放登录态，直接拒绝启动以防误配
        raise RuntimeError(
            "CORS_ORIGINS 不能使用 *：会话 Cookie 会被任意跨站携带。"
            "请列出确切的来源域名，如 https://a.com,https://b.com"
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,  # 跨域携带 Cookie 必须显式白名单 + credentials
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ─── 监控中间件 ───
@app.middleware("http")
async def track_requests(request, call_next):
    """跟踪 API 请求的指标"""
    from app.metrics import api_requests_total, api_request_duration
    import time

    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    # 记录请求指标
    api_requests_total.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    api_request_duration.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)

    return response


# ─── 前端目录 ───
# 出题工作台（用户端）：web/dist，挂在 /
_web_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
# 后台管理（独立系统）：admin/dist，挂在 /admin
_admin_dir = Path(__file__).resolve().parent.parent / "admin" / "dist"
_web_built = _web_dir.is_dir()

# ─── API 路由（必须在静态挂载之前注册，否则会被 StaticFiles 遮蔽） ───
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(me_router)
app.include_router(library_router)
app.include_router(mini_router)
app.include_router(catalog_router)
app.include_router(catalog_admin_router)
app.include_router(site_router)
app.include_router(site_admin_router)
app.include_router(experience_router)
app.include_router(engagement_router)
app.include_router(commerce_router)
app.include_router(generate_router)
app.include_router(admin_router)


@app.get("/", tags=["系统"], include_in_schema=False)
async def home():
    if not _web_built:
        raise HTTPException(
            status_code=503,
            detail={"error": "前端未构建", "detail": "请先执行 cd web && pnpm install && pnpm build"},
        )
    return FileResponse(_web_dir / "index.html")


# ─── 后台管理前端（独立应用）。必须在根 mount 之前注册；未构建时告警但不阻塞主服务。 ───
_admin_console_built = _admin_dir.is_dir()
if _admin_console_built:
    from starlette.responses import RedirectResponse

    @app.get("/admin", tags=["系统"], include_in_schema=False)
    async def admin_console_redirect():
        """规范化到目录形式 /admin/（StaticFiles html 模式只响应目录路径）"""
        return RedirectResponse(url="/admin/", status_code=307)

    app.mount("/admin", StaticFiles(directory=_admin_dir, html=True), name="admin_console")
else:
    logger.warning(
        "未找到 admin/dist —— 后台管理前端未构建。执行：cd admin && pnpm install && pnpm build"
    )


# ─── 静态挂载（必须放最后：根路径 mount 会吃掉后注册的路由） ───
if _web_built:
    app.mount("/static", StaticFiles(directory=_web_dir), name="web")
    app.mount("/", StaticFiles(directory=_web_dir, html=True), name="web_root")
else:
    logger.warning(
        "未找到 web/dist —— 出题工作台前端未构建，API 正常服务但页面不可访问。"
        "执行：cd web && pnpm install && pnpm build"
    )
