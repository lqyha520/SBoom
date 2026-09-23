"""后台管理路由 —— 数据概览 / 用户管理 / 缓存 / 日志

所有端点要求管理员角色（router 级依赖）。内置安全护栏：
- 管理员不能删除/禁用/降级自己（防止把自己锁在门外）
- 被禁用用户的现有会话立即失效（require_user 每次校验 is_active）
"""

import asyncio
import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.errors import UniqueViolation
from pydantic import BaseModel

from app.config import APP_VERSION, get_settings
from app.deps import require_admin
from app.security import encryption_backend, security_warnings
from app.services import app_config, user_store
from app.services.generation_control import usage_summary
from app.services.user_store import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["后台管理"])

settings = get_settings()
# app/routers/admin.py → 上三级 = 项目根目录
_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "server.log"


# ─── 数据概览 ───

@router.get("/stats", summary="后台概览数据")
def stats(admin: CurrentUser = Depends(require_admin)):
    from app.db import db

    s = user_store.admin_stats()
    g = app_config.get_llm()
    with db() as conn:
        fb_total = conn.execute("SELECT COUNT(*) c FROM feedbacks").fetchone()["c"]
        fb_oob = conn.execute("SELECT COUNT(*) c FROM feedbacks WHERE is_oob = 1").fetchone()["c"]
    return {
        **s,
        "llmConfigured": g["hasKey"] or bool(settings.llm_api_key),
        "feedbacks": fb_total,
        "feedbacksOob": fb_oob,
        "generationUsage": usage_summary(),
        "securityWarnings": security_warnings(),
        "server": {
            "model": g["model"] or settings.llm_model or "（未配置）",
            "encryption": encryption_backend(),
            "version": APP_VERSION,
        },
    }


# ─── 用户反馈查看 ───

@router.get("/feedbacks", summary="用户反馈列表（最新在前）")
def list_feedbacks(
    limit: int = 100,
    oob_only: bool = False,
    admin: CurrentUser = Depends(require_admin),
):
    from app.db import db

    limit = max(1, min(500, limit))
    sql = "SELECT id, user_id, username, game_id, is_oob, comment, created_at FROM feedbacks"
    if oob_only:
        sql += " WHERE is_oob = 1"
    sql += " ORDER BY id DESC LIMIT ?"
    with db() as conn:
        rows = [dict(r) for r in conn.execute(sql, (limit,))]
    return {"feedbacks": rows}


# ─── 用户管理 ───

@router.get("/users", summary="用户列表（可按用户名搜索、按角色筛选）")
def list_users(query: str = "", role: str = "", limit: int = Query(20, ge=1, le=100),
               offset: int = Query(0, ge=0), admin: CurrentUser = Depends(require_admin)):
    if role and role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail={"error": "role 只能是 user 或 admin"})
    return user_store.list_users(query.strip(), role, limit, offset)


class AdminCreateUser(BaseModel):
    username: str
    password: str
    role: str = "user"


@router.post("/users", summary="创建用户")
def create_user(req: AdminCreateUser, admin: CurrentUser = Depends(require_admin)):
    import re
    if not re.match(r"^[\w\u4e00-\u9fa5-]{2,32}$", req.username):
        raise HTTPException(status_code=400, detail={"error": "用户名需为 2-32 位字母、数字、下划线、中文"})
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail={"error": "密码至少 6 位"})
    if req.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail={"error": "role 只能是 user 或 admin"})
    if user_store.get_user_by_username(req.username):
        raise HTTPException(status_code=409, detail={"error": "用户名已被占用"})
    try:
        user = user_store.create_user(req.username, req.password, role=req.role)
    except UniqueViolation as exc:
        raise HTTPException(409, detail={"error": "用户名已被占用"}) from exc
    logger.info(f"管理员 {admin.username} 创建了用户 {user.username} (role={req.role})")
    return {"id": user.id, "username": user.username, "role": user.role}


class AdminUpdateUser(BaseModel):
    password: str | None = None
    role: str | None = None
    is_active: bool | None = None


@router.put("/users/{user_id}", summary="更新用户（重置密码 / 改角色 / 启用禁用）")
def update_user(user_id: int, req: AdminUpdateUser, admin: CurrentUser = Depends(require_admin)):
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
def delete_user(user_id: int, admin: CurrentUser = Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail={"error": "不能删除自己的账号"})
    try:
        ok = user_store.delete_user(user_id)
    except user_store.UserHasCatalogPapers as exc:
        raise HTTPException(409, detail={"error": str(exc)}) from exc
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "用户不存在"})
    logger.info(f"管理员 {admin.username} 删除了用户 id={user_id}")
    return {"status": "ok"}


# ─── 管理端查看用户模板 ───

@router.get("/users/{user_id}/templates", summary="列出指定用户的模板（元信息）")
def list_user_templates(user_id: int, admin: CurrentUser = Depends(require_admin)):
    if not user_store.get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail={"error": "用户不存在"})
    templates = user_store.list_templates_for_admin(user_id)
    return {"templates": templates}


@router.get("/users/{user_id}/templates/{tpl_id}", summary="查看指定模板的完整内容")
def get_user_template(user_id: int, tpl_id: int, admin: CurrentUser = Depends(require_admin)):
    """管理端查看模板内容（只读，用于排查/协助；内容含题目文字与配置）"""
    if not user_store.get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail={"error": "用户不存在"})
    # 单查询同时校验模板归属（tpl_id 与 user_id 不匹配时报 404）
    tpl = user_store.get_template_for_admin(tpl_id, user_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail={"error": "模板不存在"})
    with_title = tpl.get("name") or tpl.get("title") or ""
    logger.info(f"管理员 {admin.username} 查看了用户 id={user_id} 的模板「{with_title}」")
    return {"template": tpl}


# ─── 日志查看 ───

@router.get("/logs", summary="查看服务日志（尾部 N 行）")
def tail_logs(lines: int = 200, admin: CurrentUser = Depends(require_admin)):
    if not get_settings().log_to_file:
        return {"logs": "日志输出到标准输出，请查看启动终端或 docker compose logs app。单进程本地运行可设置 LOG_TO_FILE=true。"}
    lines = max(10, min(1000, lines))
    try:
        # deque 只保留尾部 N 行，日志文件再大也只读一遍流，不整文件进内存
        from collections import deque
        with open(_LOG_PATH, encoding="utf-8", errors="replace") as f:
            tail = deque(f, maxlen=lines)
        return {"logs": "".join(tail)}
    except FileNotFoundError:
        return {"logs": "（暂无日志文件）"}


# ─── 全局模型配置（所有用户共用的 LLM 服务） ───

class AdminLlmConfigIn(BaseModel):
    baseUrl: str = ""
    model: str = ""
    apiKey: str = ""   # 空串 = 保留已保存的密钥不变
    timeout: int = 60


@router.get("/llm-config", summary="获取全局模型配置（不含密钥明文）")
def get_llm_config(admin: CurrentUser = Depends(require_admin)):
    g = app_config.get_llm()
    return {
        "baseUrl": g["baseUrl"],
        "model": g["model"],
        "timeout": g["timeout"],
        "hasKey": g["hasKey"],
    }


@router.put("/llm-config", summary="保存全局模型配置（密钥服务端加密存储，全体用户生效）")
def save_llm_config(req: AdminLlmConfigIn, admin: CurrentUser = Depends(require_admin)):
    app_config.save_llm(
        base_url=req.baseUrl.rstrip("/"),
        model=req.model,
        api_key=req.apiKey,
        timeout=max(10, min(600, req.timeout or 60)),
    )
    has_key = app_config.get_llm()["hasKey"]
    logger.info(f"管理员 {admin.username} 更新了全局模型配置: {req.baseUrl} / {req.model}")
    return {"status": "ok", "message": "模型配置已保存，全体用户生效", "hasKey": has_key}


@router.delete("/llm-config", summary="清除全局模型配置（含已存密钥）")
def clear_llm_config(admin: CurrentUser = Depends(require_admin)):
    """整行删除全局 LLM 配置。用于部署纠错/安全清理（如密钥泄露后重置）。"""
    app_config.clear_llm()
    logger.info(f"管理员 {admin.username} 清除了全局模型配置")
    return {"status": "ok", "message": "模型配置已清除"}


def _resolve_public_ip(hostname: str, port: int) -> str:
    """把主机名解析为公网 IP（同步 DNS，调用方放线程池）。

    任何一条解析记录落在回环/内网/链路本地（169.254.x 云元数据）/保留段都拒绝，
    与 image_generation._public_image 的公网 IP 钉死策略一致。
    """
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"无法解析主机名 {hostname}") from exc
    ips = [str(entry[4][0]).split("%")[0] for entry in addresses]
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError("接口地址不能指向本机、内网或云元数据地址")
    return ips[0]


def _pin_public_url(url: str) -> tuple[str, str]:
    """校验未保存的接口地址并把连接钉到公网 IP，返回 (主机替换成 IP 的 URL, 原始 Host 头)。

    只按主机名解析一次、随后直接连该 IP，避免 DNS 重绑定把探测请求引到内网。
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("接口地址须为 http(s)://主机[:端口]/路径 形式，且不能包含账号密码")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    ip = _resolve_public_ip(parts.hostname, port)
    host = parts.hostname.encode("idna").decode("ascii")
    host_header = host if parts.port is None else f"{host}:{parts.port}"
    import httpx as _httpx
    return str(_httpx.URL(url).copy_with(host=ip)), host_header


@router.post("/test-llm", summary="测试模型连通性（流式探测：拿到首个响应即判定成功）")
async def test_llm(req: AdminLlmConfigIn | None = None, admin: CurrentUser = Depends(require_admin)):
    """连通性测试用流式请求：服务端开始吐第一个 token 就证明链路+鉴权都通。
    超时耐心 = 配置的 timeout（中转站拥堵时首 token 可能 20-60s，不宜截断）。

    防 SSRF：只有「已保存的全局配置地址」可以原样探测；表单里填的其他地址必须解析到公网 IP，
    否则管理员账号（或被盗的管理员会话）可以拿这个接口扫内网 / 读云元数据。
    """
    import httpx as _httpx

    g = await asyncio.to_thread(app_config.get_llm, with_key=True)
    saved_base = (g["baseUrl"] or settings.llm_base_url).rstrip("/")
    requested = req.baseUrl.strip().rstrip("/") if req and req.baseUrl else ""
    base_url = requested or saved_base
    model = (req.model if req and req.model else g["model"]) or settings.llm_model
    api_key = (req.apiKey if req and req.apiKey else g["api_key"]) or settings.llm_api_key
    timeout = (req.timeout if req and req.timeout else g["timeout"]) or 60
    request_headers: dict[str, str] = {}
    extensions: dict = {}
    if requested and requested != saved_base:
        try:
            base_url, host_header = await asyncio.to_thread(_pin_public_url, requested)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": "接口地址不允许", "detail": str(exc)}) from exc
        request_headers["Host"] = host_header
        extensions["sni_hostname"] = host_header.split(":")[0]  # TLS 证书仍按原始域名校验
    try:
        async with _httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            # 整体耐心按配置放宽，但握手 10s 不通就该报错，别让不可达地址挂满整个窗口
            timeout=_httpx.Timeout(max(float(timeout), 90.0), connect=10.0, pool=10.0),
            trust_env=False,
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
                headers=request_headers,
                extensions=extensions,
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
    except _httpx.TimeoutException:
        # 注意：必须放在 TransportError 之前（Timeout 是 TransportError 的子类，
        # 顺序反了会把超时误报成"无法连接"——请求其实已到达服务端并计费）
        raise HTTPException(
            status_code=502,
            detail={"error": "模型服务响应超时", "detail": f"等待 {max(timeout, 90)}s 未见任何输出（服务端可能极度拥堵）"},
        ) from None
    except _httpx.TransportError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "无法连接模型服务", "detail": f"{e}（检查接口地址/网络）"},
        ) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "模型连接失败", "detail": str(e)}) from e
