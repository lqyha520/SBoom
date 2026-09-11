"""FastAPI 主入口"""

import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.generate import router as generate_router
from app.routers.me import router as me_router
from app.services.llm_client import llm_client
from app.services import user_store
from app.config import get_settings, APP_VERSION
from app.db import init_db

settings = get_settings()


# ─── 日志（滚动：单文件 5MB，保留 3 份备份，无上限增长） ───
_LOG_FILE = Path(__file__).resolve().parent.parent / "server.log"
_log_file_handler = logging.handlers.RotatingFileHandler(
    _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[_log_file_handler, logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ─── 生命周期 ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的管理"""
    init_db()  # 用户库建表 + 迁移（幂等）
    # 环境变量种子管理员（可选）：确保存在并对齐角色/状态/密码
    if settings.admin_username and settings.admin_password:
        user_store.ensure_admin(settings.admin_username, settings.admin_password)
        logger.info(f"已确保种子管理员账号存在: {settings.admin_username}")
    # 模型配置收归后台：老部署里用户自配的 LLM 一次性迁移为全局配置
    from app.services.app_config import seed_llm_from_user_configs
    seed_llm_from_user_configs()
    logger.info("🚀 Learning Coach API 启动（多用户模式）")
    logger.info(f"   LLM 模型（全局兜底）: {settings.llm_model}")
    yield
    logger.info("🛑 应用关闭，清理资源...")
    await llm_client.close()


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,  # 跨域携带 Cookie 必须显式白名单 + credentials
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ─── 前端目录 ───
# 出题工作台（用户端）：web/dist，挂在 /
_web_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
# 后台管理（独立系统）：admin/dist，挂在 /admin
_admin_dir = Path(__file__).resolve().parent.parent / "admin" / "dist"

# ─── API 路由（必须在静态挂载之前注册，否则会被 StaticFiles 遮蔽） ───
app.include_router(auth_router)
app.include_router(me_router)
app.include_router(generate_router)
app.include_router(admin_router)


@app.get("/", tags=["系统"], include_in_schema=False)
async def home():
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


@app.get("/health", tags=["系统"])
async def health():
    return {
        "status": "healthy",
        "model": settings.llm_model,
    }


# ─── 静态挂载（必须放最后：根路径 mount 会吃掉后注册的路由） ───
app.mount("/static", StaticFiles(directory=_web_dir), name="web")
app.mount("/", StaticFiles(directory=_web_dir, html=True), name="web_root")
