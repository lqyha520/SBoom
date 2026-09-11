"""后台管理路由 —— 数据概览 / 用户管理 / 缓存 / 日志

所有端点要求管理员角色（router 级依赖）。内置安全护栏：
- 管理员不能删除/禁用/降级自己（防止把自己锁在门外）
- 被禁用用户的现有会话立即失效（require_user 每次校验 is_active）
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.deps import require_admin, require_user
from app.security import encryption_backend
from app.services import app_config, user_store
from app.services.llm_client import llm_client
from app.services.user_store import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["后台管理"])

settings = get_settings()
# app/routers/admin.py → 上三级 = 项目根目录
_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "server.log"


# ─── 数据概览 ───

@router.get("/stats", summary="后台概览数据")
async def stats(admin: CurrentUser = Depends(require_admin)):
    s = user_store.admin_stats()
    g = app_config.get_llm()
    return {
        **s,
        "llmConfigured": g["hasKey"] or bool(g["baseUrl"]),
        "server": {
            "model": g["model"] or settings.llm_model or "（未配置）",
            "encryption": encryption_backend(),
            "version": "0.4.0",
        },
    }


# ─── 用户管理 ───

@router.get("/users", summary="用户列表（可按用户名搜索）")
async def list_users(query: str = "", admin: CurrentUser = Depends(require_admin)):
    return {"users": user_store.list_users(query.strip())}


class AdminCreateUser(BaseModel):
    username: str
    password: str
    role: str = "user"


@router.post("/users", summary="创建用户")
async def create_user(req: AdminCreateUser, admin: CurrentUser = Depends(require_admin)):
    import re
    if not re.match(r"^[\w\u4e00-\u9fa5-]{2,32}$", req.username):
        raise HTTPException(status_code=400, detail={"error": "用户名需为 2-32 位字母、数字、下划线、中文"})
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail={"error": "密码至少 6 位"})
    if req.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail={"error": "role 只能是 user 或 admin"})
    if user_store.get_user_by_username(req.username):
        raise HTTPException(status_code=409, detail={"error": "用户名已被占用"})
    user = user_store.create_user(req.username, req.password, role=req.role)
    logger.info(f"管理员 {admin.username} 创建了用户 {user.username} (role={req.role})")
    return {"id": user.id, "username": user.username, "role": user.role}


class AdminUpdateUser(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


@router.put("/users/{user_id}", summary="更新用户（重置密码 / 改角色 / 启用禁用）")
async def update_user(user_id: int, req: AdminUpdateUser, admin: CurrentUser = Depends(require_admin)):
    if req.role is not None and req.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail={"error": "role 只能是 user 或 admin"})
    if req.password is not None and len(req.password) < 6:
        raise HTTPException(status_code=400, detail={"error": "密码至少 6 位"})

    # 护栏：不能对自己降级 / 禁用（删除见下方 delete）
    if user_id == admin.id:
        if req.role == "user":
            raise HTTPException(status_code=400, detail={"error": "不能取消自己的管理员角色"})
        if req.is_active is False:
            raise HTTPException(status_code=400, detail={"error": "不能禁用自己的账号"})

    ok = user_store.update_user(
        user_id, password=req.password, role=req.role, is_active=req.is_active
    )
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "用户不存在"})
    logger.info(
        f"管理员 {admin.username} 更新了用户 id={user_id}: "
        f"password={'***' if req.password else '-'} role={req.role or '-'} is_active={req.is_active if req.is_active is not None else '-'}"
    )
    return {"status": "ok"}


@router.delete("/users/{user_id}", summary="删除用户（模板与配置级联删除）")
async def delete_user(user_id: int, admin: CurrentUser = Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail={"error": "不能删除自己的账号"})
    ok = user_store.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "用户不存在"})
    logger.info(f"管理员 {admin.username} 删除了用户 id={user_id}")
    return {"status": "ok"}


# ─── 管理端查看用户模板 ───

@router.get("/users/{user_id}/templates", summary="列出指定用户的模板（元信息）")
async def list_user_templates(user_id: int, admin: CurrentUser = Depends(require_admin)):
    if not user_store.get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail={"error": "用户不存在"})
    templates = user_store.list_templates_for_admin(user_id)
    return {"templates": templates}


@router.get("/users/{user_id}/templates/{tpl_id}", summary="查看指定模板的完整内容")
async def get_user_template(user_id: int, tpl_id: int, admin: CurrentUser = Depends(require_admin)):
    """管理端查看模板内容（只读，用于排查/协助；内容含题目文字与配置）"""
    if not user_store.get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail={"error": "用户不存在"})
    tpl = user_store.get_template_for_admin(tpl_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail={"error": "模板不存在"})
    # 防御：模板必须属于目标用户（tpl_id 与 user_id 不匹配时报 404）
    with_title = tpl.get("name") or tpl.get("title") or ""
    belongs = any(
        row["id"] == tpl_id
        for row in user_store.list_templates_for_admin(user_id)
    )
    if not belongs:
        raise HTTPException(status_code=404, detail={"error": "模板不存在"})
    logger.info(f"管理员 {admin.username} 查看了用户 id={user_id} 的模板「{with_title}」")
    return {"template": tpl}


# ─── 日志查看 ───

@router.get("/logs", summary="查看服务日志（尾部 N 行）")
async def tail_logs(lines: int = 200, admin: CurrentUser = Depends(require_admin)):
    lines = max(10, min(1000, lines))
    try:
        text = _LOG_PATH.read_text(encoding="utf-8", errors="replace")
        return {"logs": "\n".join(text.splitlines()[-lines:])}
    except FileNotFoundError:
        return {"logs": "（暂无日志文件）"}


# ─── 全局模型配置（所有用户共用的 LLM 服务） ───

class AdminLlmConfigIn(BaseModel):
    baseUrl: str = ""
    model: str = ""
    apiKey: str = ""   # 空串 = 保留已保存的密钥不变
    timeout: int = 60


@router.get("/llm-config", summary="获取全局模型配置（不含密钥明文）")
async def get_llm_config(admin: CurrentUser = Depends(require_admin)):
    g = app_config.get_llm()
    return {
        "baseUrl": g["baseUrl"],
        "model": g["model"],
        "timeout": g["timeout"],
        "hasKey": g["hasKey"],
    }


@router.put("/llm-config", summary="保存全局模型配置（密钥服务端加密存储，全体用户生效）")
async def save_llm_config(req: AdminLlmConfigIn, admin: CurrentUser = Depends(require_admin)):
    app_config.save_llm(
        base_url=req.baseUrl.rstrip("/"),
        model=req.model,
        api_key=req.apiKey,
        timeout=max(10, min(600, req.timeout or 60)),
    )
    has_key = app_config.get_llm()["hasKey"]
    logger.info(f"管理员 {admin.username} 更新了全局模型配置: {req.baseUrl} / {req.model}")
    return {"status": "ok", "message": "模型配置已保存，全体用户生效", "hasKey": has_key}


@router.post("/test-llm", summary="测试模型连通性（流式探测：拿到首个响应即判定成功）")
async def test_llm(req: Optional[AdminLlmConfigIn] = None, admin: CurrentUser = Depends(require_admin)):
    """连通性测试用流式请求：服务端开始吐第一个 token 就证明链路+鉴权都通。
    超时耐心 = 配置的 timeout（中转站拥堵时首 token 可能 20-60s，不宜截断）。"""
    import httpx as _httpx

    g = app_config.get_llm(with_key=True)
    base_url = (req.baseUrl if req and req.baseUrl else g["baseUrl"]) or settings.llm_base_url
    model = (req.model if req and req.model else g["model"]) or settings.llm_model
    api_key = (req.apiKey if req and req.apiKey else g["api_key"]) or settings.llm_api_key
    timeout = (req.timeout if req and req.timeout else g["timeout"]) or 60
    try:
        async with _httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=_httpx.Timeout(max(float(timeout), 90.0)),
        ) as client:
            async with client.stream(
                "POST",
                "/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "回复：ok"}],
                    "max_tokens": 5,
                    "stream": True,
                },
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", errors="replace")[:200]
                    raise HTTPException(
                        status_code=502,
                        detail={"error": f"模型服务返回 {resp.status_code}", "detail": body},
                    )
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and '"content"' in line:
                        return {"status": "ok", "reply": "已连通（流式响应正常）"}
                # 流结束但没收到 content（如空回复）——链路已通，也算成功
                return {"status": "ok", "reply": "已连通"}
    except HTTPException:
        raise
    except _httpx.TimeoutException as e:
        # 注意：必须放在 TransportError 之前（Timeout 是 TransportError 的子类，
        # 顺序反了会把超时误报成"无法连接"——请求其实已到达服务端并计费）
        raise HTTPException(
            status_code=502,
            detail={"error": "模型服务响应超时", "detail": f"等待 {max(timeout, 90)}s 未见任何输出（服务端可能极度拥堵）"},
        )
    except _httpx.TransportError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "无法连接模型服务", "detail": f"{e}（检查接口地址/网络）"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "模型连接失败", "detail": str(e)})
