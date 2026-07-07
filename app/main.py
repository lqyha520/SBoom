"""FastAPI 主入口"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.generate import router as generate_router
from app.services.llm_client import llm_client
from app.cache.question_cache import question_cache
from app.config import get_settings

settings = get_settings()

# ─── 日志 ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
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
    allow_origins=["*"],  # 开发阶段允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(generate_router)


# ─── 根路径 ───
@app.get("/", tags=["系统"])
async def root():
    return {
        "name": "Learning Coach API",
        "version": "0.1.0",
        "docs": "/docs",
    }


# ─── 健康检查 ───
@app.get("/health", tags=["系统"])
async def health():
    return {
        "status": "healthy",
        "model": settings.llm_model,
        "cache": question_cache.stats(),
    }
