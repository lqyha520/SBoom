"""后台管理路由 —— 数据概览 / 用户管理 / 缓存 / 日志

所有端点要求管理员角色（router 级依赖）。内置安全护栏：
- 管理员不能删除/禁用/降级自己（防止把自己锁在门外）
- 被禁用用户的现有会话立即失效（require_user 每次校验 is_active）
"""

import asyncio
import ipaddress
import json
import logging
import socket
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, ConfigDict, Field

from app.blocking import run_sync
from app.config import APP_VERSION, get_settings
from app.deps import require_admin, require_recent_admin
from app.http_limits import limited_lines
from app.models.model_profiles import TextModelProfiles
from app.security import encryption_backend, security_warnings
from app.sensitive_config import SensitiveConfigRoute
from app.services import app_config, image_config, user_store
from app.services.generation_control import usage_summary
from app.services.llm_client import parse_stream_chunk
from app.services.model_profiles import entries
from app.services.user_store import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["后台管理"], route_class=SensitiveConfigRoute)

settings = get_settings()
# app/routers/admin.py → 上三级 = 项目根目录
_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "logs" / "application.log"


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
        "llmConfigured": g["hasKey"] or ("models" not in g and bool(settings.llm_api_key)),
        "feedbacks": fb_total,
        "feedbacksOob": fb_oob,
        "generationUsage": usage_summary(),
        "securityWarnings": security_warnings(),
        "server": {
            "model": g["model"] or (settings.llm_model if "models" not in g else "") or "（未配置）",
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
def create_user(req: AdminCreateUser, admin: CurrentUser = Depends(require_recent_admin)):
    import re
    if not re.match(r"^[\w\u4e00-\u9fa5-]{2,32}$", req.username):
        raise HTTPException(status_code=400, detail={"error": "用户名需为 2-32 位字母、数字、下划线、中文"})
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail={"error": "密码至少 8 位"})
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
def update_user(user_id: int, req: AdminUpdateUser, admin: CurrentUser = Depends(require_recent_admin)):
    if req.role is not None and req.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail={"error": "role 只能是 user 或 admin"})
    if req.password is not None and len(req.password) < 8:
        raise HTTPException(status_code=400, detail={"error": "密码至少 8 位"})

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
    model_config = ConfigDict(extra="forbid")
    id: str | None = Field(None, max_length=64)
    baseUrl: str = Field("", max_length=500)
    model: str = Field("", max_length=120)
    apiKey: str = Field("", max_length=4000, repr=False)   # 空串 = 保留已保存的密钥不变
    timeout: int = Field(60, ge=10, le=600)
    maxTokens: int = Field(default=16384, ge=1024, le=131072)


class AdminLlmModelsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = Field(None, max_length=64)
    baseUrl: str = Field("", max_length=500)
    apiKey: str = Field("", max_length=4000, repr=False)
    timeout: int = Field(60, ge=10, le=600)
    # 图片候选的密钥存在图片配置里，按来源取已保存的密钥，避免要求管理员重复输入。
    kind: Literal["text", "image"] = "text"


@router.get("/llm-config", summary="获取全局模型配置（不含密钥明文）")
def get_llm_config(admin: CurrentUser = Depends(require_admin)):
    return app_config.get_admin_config()


@router.put("/llm-config", summary="保存全局模型配置（密钥服务端加密存储，全体用户生效）")
def save_llm_config(req: TextModelProfiles | AdminLlmConfigIn, admin: CurrentUser = Depends(require_recent_admin)):
    from app.provider_policy import validate_endpoint
    if isinstance(req, TextModelProfiles):
        for profile in req.models:
            validate_endpoint(profile.baseUrl, resolve=profile.enabled)
        saved = app_config.save_llm_models(req.models, expected_revision=req.revision, require_revision=True)
        return {**saved, "status": "ok", "message": "模型配置已保存，全体用户生效"}
    validate_endpoint(req.baseUrl)
    app_config.save_llm(
        base_url=req.baseUrl.rstrip("/"),
        model=req.model,
        api_key=req.apiKey,
        timeout=max(10, min(600, req.timeout or 60)),
        max_tokens=req.maxTokens,
    )
    has_key = app_config.get_llm()["hasKey"]
    logger.info("管理员 id=%s 更新了全局模型配置", admin.id)
    return {"status": "ok", "message": "模型配置已保存，全体用户生效", "hasKey": has_key}


@router.delete("/llm-config", summary="清除全局模型配置（含已存密钥）")
def clear_llm_config(admin: CurrentUser = Depends(require_recent_admin), if_match: str | None = Header(None)):
    """删除全部候选与密钥，保留空列表以阻止环境配置重新启用服务。"""
    saved = app_config.save_llm_models([], expected_revision=if_match, require_revision=True)
    logger.info(f"管理员 {admin.username} 清除了全局模型配置")
    return {**saved, "status": "ok", "message": "模型配置已清除"}


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
    from app.provider_policy import reachable_ip
    return reachable_ip(ips, port)


def _pin_public_url(url: str) -> tuple[str, str]:
    """校验未保存的接口地址并把连接钉到公网 IP，返回 (主机替换成 IP 的 URL, 原始 Host 头)。

    只按主机名解析一次、随后直接连该 IP，避免 DNS 重绑定把探测请求引到内网。
    """
    from app.provider_policy import validate_endpoint
    validate_endpoint(url, resolve=False)
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("接口地址须为 http(s)://主机[:端口]/路径 形式，且不能包含账号密码")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    ip = _resolve_public_ip(parts.hostname, port)
    host = parts.hostname.encode("idna").decode("ascii")
    host_header = host if parts.port is None else f"{host}:{parts.port}"
    import httpx as _httpx
    return str(_httpx.URL(url).copy_with(host=ip)), host_header


def _model_ids(data) -> list[str]:
    """兼容 OpenAI 的 {"data": [...]}、部分中转站的 {"models": [...]} 与裸数组。"""
    if isinstance(data, dict):
        items = data.get("data") if "data" in data else data.get("models")
    else:
        items = data
    if not isinstance(items, list):
        raise ValueError("模型列表格式错误")
    identifiers: set[str] = set()
    for item in items:
        value = item.get("id") if isinstance(item, dict) else item
        if not isinstance(value, str):
            continue
        value = value.strip()
        if value and len(value) <= 120:
            identifiers.add(value)
    return sorted(identifiers, key=str.casefold)


def _stream_reasoning(event: str) -> str:
    """推理模型会先吐 reasoning_content，同样能证明链路与鉴权已通。"""
    try:
        delta = json.loads(event)["choices"][0]["delta"]
        value = delta.get("reasoning_content")
        return value if isinstance(value, str) else ""
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return ""


@router.post("/llm-models", summary="拉取模型服务支持的模型列表（文本与图片候选共用）")
async def list_llm_models(req: AdminLlmModelsIn | None = None, admin: CurrentUser = Depends(require_admin)):
    """用当前表单或已保存的地址与密钥请求 OpenAI 兼容的 GET /models。

    kind=image 时从图片候选配置里取已保存的密钥；防 SSRF 与密钥借用规则和 test-llm 一致：
    未保存的地址必须解析到公网 IP；指定了未知 id 时不会借用其他模型（含另一类配置）的密钥。
    """
    import httpx as _httpx

    is_image = bool(req and req.kind == "image")
    if is_image:
        g = await run_sync(image_config.get_config, with_key=True)
    else:
        g = await run_sync(app_config.get_admin_config, with_key=True)
    managed = is_image or g.get("managed", "models" in g) or bool(req and req.id)
    if req and req.id:
        g = next((profile for profile in entries(g) if profile["id"] == req.id), {})
        if not g and not req.apiKey:
            raise HTTPException(400, detail={"error": "此模型尚未保存密钥，请填写密钥后拉取模型"})
    elif "models" in g:
        g = next((profile for profile in g["models"] if profile["enabled"]), {})
    saved_base = (g.get("baseUrl") or ("" if managed else settings.llm_base_url)).rstrip("/")
    requested = req.baseUrl.strip().rstrip("/") if req and req.baseUrl else ""
    base_url = requested or saved_base
    api_key = (req.apiKey if req and req.apiKey else g.get("api_key")) or ("" if managed else settings.llm_api_key)
    timeout = (req.timeout if req and req.timeout else g.get("timeout")) or 60
    if not base_url:
        raise HTTPException(400, detail={"error": "请先填写接口地址"})
    if not api_key:
        raise HTTPException(400, detail={"error": "请先填写此模型的 API 密钥"})
    request_headers: dict[str, str] = {}
    extensions: dict = {}
    from app.provider_policy import require_new_key, validate_endpoint
    if saved_base:
        require_new_key(saved_base, base_url, req.apiKey if req else "")
    if not settings.provider_allow_private:
        try:
            base_url, host_header = await run_sync(_pin_public_url, base_url)
        except (ValueError, HTTPException) as exc:
            raise HTTPException(status_code=400, detail={"error": "接口地址不允许"}) from exc
        request_headers["Host"] = host_header
        extensions["sni_hostname"] = host_header.split(":")[0]
    else:
        validate_endpoint(base_url, resolve=False)
    try:
        # 模型列表应当很快返回；不跟随表单里可能配置的 300-600s 长超时。
        wait = min(float(timeout), 60.0)
        async with asyncio.timeout(wait), _httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=_httpx.Timeout(wait, connect=10.0, pool=10.0),
            trust_env=False,
        ) as client:
            async with client.stream(
                "GET",
                "/models",
                headers=request_headers,
                extensions=extensions,
            ) as resp:
                if resp.status_code != 200:
                    raise HTTPException(
                        status_code=502,
                        detail={"error": f"模型服务返回 {resp.status_code}"},
                    )
                raw = bytearray()
                async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                    if len(raw) + len(chunk) > settings.provider_max_response_bytes:
                        raise HTTPException(502, detail={"code": "provider_response_too_large", "error": "模型列表响应超过安全上限"})
                    raw.extend(chunk)
        models = _model_ids(json.loads(raw))
        if not models:
            raise HTTPException(502, detail={"error": "模型服务未返回可选的模型，请手动填写模型名称"})
        return {"status": "ok", "models": models, "count": len(models)}
    except HTTPException:
        raise
    except (TimeoutError, _httpx.TimeoutException):
        raise HTTPException(status_code=502, detail={"error": "模型列表响应超时，请稍后重试"}) from None
    except _httpx.TransportError as e:
        raise HTTPException(status_code=502, detail={"error": "无法连接模型服务，请检查接口地址与网络"}) from e
    except (ValueError, TypeError):
        raise HTTPException(status_code=502, detail={"error": "模型列表响应格式异常，请手动填写模型名称"}) from None
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "模型列表拉取失败"}) from e


@router.post("/test-llm", summary="测试模型连通性（流式探测：拿到首个响应即判定成功）")
async def test_llm(req: AdminLlmConfigIn | None = None, admin: CurrentUser = Depends(require_admin)):
    """连通性测试用流式请求：服务端开始吐第一个 token 就证明链路+鉴权都通。
    超时耐心 = 配置的 timeout（中转站拥堵时首 token 可能 20-60s，不宜截断）。

    防 SSRF：只有「已保存的全局配置地址」可以原样探测；表单里填的其他地址必须解析到公网 IP，
    否则管理员账号（或被盗的管理员会话）可以拿这个接口扫内网 / 读云元数据。
    """
    import httpx as _httpx

    g = await run_sync(app_config.get_admin_config, with_key=True)
    managed = g.get("managed", "models" in g) or bool(req and req.id)
    if req and req.id:
        g = next((profile for profile in entries(g) if profile["id"] == req.id), {})
        if not g and not req.apiKey:
            raise HTTPException(400, detail={"error": "此模型尚未保存密钥，请填写密钥后测试"})
    elif "models" in g:
        g = next((profile for profile in g["models"] if profile["enabled"]), {})
    saved_base = (g.get("baseUrl") or ("" if managed else settings.llm_base_url)).rstrip("/")
    requested = req.baseUrl.strip().rstrip("/") if req and req.baseUrl else ""
    base_url = requested or saved_base
    model = (req.model if req and req.model else g.get("model")) or ("" if managed else settings.llm_model)
    api_key = (req.apiKey if req and req.apiKey else g.get("api_key")) or ("" if managed else settings.llm_api_key)
    timeout = (req.timeout if req and req.timeout else g.get("timeout")) or 60
    if not api_key:
        raise HTTPException(400, detail={"error": "请先配置此模型的 API 密钥"})
    request_headers: dict[str, str] = {}
    extensions: dict = {}
    from app.provider_policy import require_new_key, validate_endpoint
    if saved_base:
        require_new_key(saved_base, base_url, req.apiKey if req else "")
    if not settings.provider_allow_private:
        try:
            base_url, host_header = await run_sync(_pin_public_url, base_url)
        except (ValueError, HTTPException) as exc:
            raise HTTPException(status_code=400, detail={"error": "接口地址不允许"}) from exc
        request_headers["Host"] = host_header
        extensions["sni_hostname"] = host_header.split(":")[0]  # TLS 证书仍按原始域名校验
    else:
        validate_endpoint(base_url, resolve=False)
    try:
        async with asyncio.timeout(float(timeout)), _httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            # 整体耐心按配置放宽，但握手 10s 不通就该报错，别让不可达地址挂满整个窗口
            timeout=_httpx.Timeout(float(timeout), connect=10.0, pool=10.0),
            trust_env=False,
        ) as client:
            async with client.stream(
                "POST",
                "/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "回复：ok"}],
                    "max_tokens": 64,
                    "stream": True,
                },
                headers=request_headers,
                extensions=extensions,
            ) as resp:
                if resp.status_code != 200:
                    raise HTTPException(
                        status_code=502,
                        detail={"error": f"模型服务返回 {resp.status_code}"},
                    )
                async for line in limited_lines(resp, get_settings().provider_max_response_bytes):
                    if not line.startswith("data:"):
                        continue
                    event = line[5:].strip()
                    if event == "[DONE]":
                        break
                    content, reason, _ = parse_stream_chunk(event)
                    if reason == "content_filter":
                        raise HTTPException(502, detail={"error": "模型拒绝了连接测试请求"})
                    # 推理模型可能把探测预算全花在 reasoning_content 上，正文为空但链路已通。
                    if content.strip() or _stream_reasoning(event).strip():
                        return {"status": "ok", "reply": "已连通（流式响应正常）"}
                raise HTTPException(502, detail={"error": "模型未返回有效的流式文本，请检查接口与模型名称"})
    except HTTPException:
        raise
    except (TimeoutError, _httpx.TimeoutException):
        # 注意：必须放在 TransportError 之前（Timeout 是 TransportError 的子类，
        # 顺序反了会把超时误报成"无法连接"——请求其实已到达服务端并计费）
        raise HTTPException(
            status_code=502,
            detail={"error": "模型服务响应超时", "detail": f"等待 {timeout}s 未见任何输出（服务端可能极度拥堵）"},
        ) from None
    except _httpx.TransportError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "无法连接模型服务，请检查接口地址与网络"},
        ) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "模型连接失败"}) from e
