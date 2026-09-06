"""FastAPI 主入口"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers.generate import router as generate_router
from app.services.llm_client import llm_client
from app.cache.question_cache import question_cache
from app.config import get_settings
from pydantic import BaseModel

settings = get_settings()


class LlmConfigRequest(BaseModel):
    baseUrl: str = ""
    model: str = ""
    apiKey: str = ""
    timeout: int = 60

# ─── 日志 ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler("server.log", encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ─── 生命周期 ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的管理"""
    logger.info("🚀 Learning Coach API 启动")
    logger.info(f"   LLM 模型: {settings.llm_model}")
    logger.info(f"   缓存状态: {'启用' if settings.cache_enabled else '关闭'}")
    yield
    logger.info("🛑 应用关闭，清理资源...")
    await llm_client.close()


# ─── 创建应用 ───
app = FastAPI(
    title="Learning Coach API",
    description="AI+教育 课堂互动系统 —— 趣味题目/知识游戏生成服务",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发阶段允许所有来源（与 allow_credentials 互斥，故不启用 credentials）
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(generate_router)

# 出题工作台页面（Vue 构建产物；开发时可用 `pnpm dev` 起 Vite 代理）
_web_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
app.mount("/static", StaticFiles(directory=_web_dir), name="web")

# Vite 构建产物以绝对路径 /assets/... 引用，挂在根路径兜底
# （API 路由已先注册，不会被遮蔽；必须在最后挂载）
app.mount("/", StaticFiles(directory=_web_dir, html=True), name="web_root")


@app.get("/", tags=["系统"], include_in_schema=False)
async def home():
    return FileResponse(_web_dir / "index.html")


# ─── 健康检查 ───
@app.get("/health", tags=["系统"])
async def health():
    return {
        "status": "healthy",
        "model": settings.llm_model,
        "cache": question_cache.stats(),
    }


# ─── LLM 配置 ───
@app.put("/api/v1/config/llm", tags=["系统"])
async def update_llm_config(req: LlmConfigRequest):
    """前端更新 LLM 配置（内存中生效，重启后恢复 .env）"""
    if req.baseUrl:
        settings.llm_base_url = req.baseUrl.rstrip("/")
    if req.model:
        settings.llm_model = req.model
    if req.apiKey:
        settings.llm_api_key = req.apiKey
    # 更新 httpx 超时——重建 client
    await llm_client.close()
    from app.services.llm_client import LLMClient
    new_client = LLMClient()
    new_client._timeout = req.timeout or 60
    # 替换模块级单例
    import app.services.llm_client as llm_mod
    llm_mod.llm_client = new_client
    logger.info(f"LLM 配置已更新: {settings.llm_base_url} / {settings.llm_model} / timeout={req.timeout}s")
    return {"status": "ok", "message": f"LLM 配置已更新：{settings.llm_model} @ {settings.llm_base_url}"}


@app.get("/api/v1/config/llm", tags=["系统"])
async def get_llm_config():
    """获取当前 LLM 配置"""
    return {
        "baseUrl": settings.llm_base_url,
        "model": settings.llm_model,
        "timeout": getattr(llm_client, '_timeout', 60)
    }
