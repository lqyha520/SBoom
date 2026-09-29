"""FastAPI 主入口"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg.errors import LockNotAvailable
from psycopg_pool import PoolTimeout, TooManyRequests

from app.body_limit import BodySizeLimit
from app.cache_policy import CachePolicy
from app.config import APP_VERSION, get_settings
from app.db import close_pg_pool, init_db
from app.db_admission import DatabaseBusy
from app.logging_config import configure_logging
from app.metrics import RequestMetrics
from app.request_context import RequestContext
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.catalog import admin_router as catalog_admin_router
from app.routers.catalog import router as catalog_router
from app.routers.commerce import router as commerce_router
from app.routers.engagement import router as engagement_router
from app.routers.experience import router as experience_router
from app.routers.generate import router as generate_router
from app.routers.health import router as health_router
from app.routers.image_generation import router as image_generation_router
from app.routers.library import router as library_router
from app.routers.me import router as me_router
from app.routers.mini import router as mini_router
from app.routers.site import admin_router as site_admin_router
from app.routers.site import router as site_router
from app.security import security_warnings
from app.services import user_store
from app.services.llm_client import llm_client

settings = get_settings()



configure_logging()
logger = logging.getLogger(__name__)

# 保留导出，方便现有测试和外部集成使用同一中间件。


# ─── 生命周期 ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的管理"""
    # 启动时验证配置
    try:
        settings.validate_startup()
    except ValueError as e:
        logger.error("配置验证失败: %s", e)
        raise

    # 初始化监控指标
    from app.metrics import init_metrics, start_metrics_server
    init_metrics(APP_VERSION)

    # FastAPI 同步路由与异步入口的阻塞工作共用同一个线程容量。
    from app.blocking import configure_threads
    configure_threads(settings.db_pool_max)

    exporter = None
    maintenance_stop = None
    maintenance_task = None
    sampler_task = None
    try:
        init_db()
        from app.services.generation_control import reclaim_expired
        reclaim_expired()  # 用户库建表 + 迁移（幂等）
        for warning in security_warnings():
            logger.warning("Security configuration: %s", warning)
        # 环境变量种子管理员（可选）：确保存在并对齐角色/状态/密码
        if settings.admin_username and settings.admin_password:
            user_store.ensure_admin(settings.admin_username, settings.admin_password, reset=settings.admin_reset_on_start)
            logger.info(f"已确保种子管理员账号存在: {settings.admin_username}")
        # 模型配置收归后台：老部署里用户自配的 LLM 一次性迁移为全局配置
        from app.services.app_config import seed_llm_from_user_configs
        seed_llm_from_user_configs()
        logger.info("🚀 Learning Coach API 启动（多用户模式）")
        logger.info(f"   LLM 模型（全局兜底）: {settings.llm_model}")
        from app.services.mini_jobs import start
        maintenance_stop, maintenance_task = start()
        if settings.metrics_enabled and not os.environ.get("LC_METRICS_MANAGED"):
            if settings.workers > 1:
                raise RuntimeError("Multi-worker metrics require the run.py launcher")
            exporter = start_metrics_server(settings.metrics_port, settings.metrics_host)
        from app.blocking import sample_limiters
        sampler_task = asyncio.create_task(sample_limiters())
        yield
    finally:
        if sampler_task:
            sampler_task.cancel()
            with suppress(asyncio.CancelledError):
                await sampler_task
        if maintenance_stop:
            maintenance_stop.set()
        try:
            if maintenance_task:
                await maintenance_task
        finally:
            if exporter:
                exporter[0].shutdown()
                exporter[0].server_close()
                exporter[1].join(timeout=3)
            if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
                from prometheus_client import multiprocess
                multiprocess.mark_process_dead(os.getpid())
            from app.services.generation_control import shutdown_generation
            await shutdown_generation()
            await llm_client.close()
            from app.services.provider_http import close_clients
            await close_clients()
            close_pg_pool()


# ─── 创建应用 ───
app = FastAPI(
    title="Learning Coach API",
    description="AI+教育 课堂互动系统 —— 趣味题目/知识游戏生成服务（多用户 + 后台管理）",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if (settings.api_docs_enabled if settings.api_docs_enabled is not None else not settings.force_https) else None,
    redoc_url=None,
    openapi_url="/openapi.json" if (settings.api_docs_enabled if settings.api_docs_enabled is not None else not settings.force_https) else None,
)

# 请求体上限最先注册（最内层）：CORS/指标中间件在外层，413 响应同样带 CORS 头并计入指标
app.add_middleware(BodySizeLimit, limit=settings.max_request_body_bytes)

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


# Metrics cover the complete ASGI response, including streams.

app.add_middleware(RequestMetrics)
app.add_middleware(CachePolicy)
app.add_middleware(RequestContext)


async def database_busy(request, exc):
    from app.metrics import database_busy_total
    database_busy_total.inc()
    return JSONResponse({"detail": {"error": "服务繁忙，请稍后重试", "code": "database_busy"}}, status_code=503,
                        headers={"Retry-After": "2", "Cache-Control": "no-store"})



for busy_error in (DatabaseBusy, PoolTimeout, TooManyRequests, LockNotAvailable):
    app.add_exception_handler(busy_error, database_busy)


@app.exception_handler(Exception)
async def unhandled_error(request, exc):
    # ServerErrorMiddleware 位于用户中间件之外，500 也必须声明缓存边界。
    return JSONResponse({"error": "服务暂时不可用，请稍后重试"}, status_code=500,
                        headers={"Cache-Control": "no-store", "Vary": "Cookie, Authorization"})


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
app.include_router(image_generation_router)
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
