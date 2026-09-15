"""个人数据路由 —— 每用户模板 CRUD

所有端点均要求登录；数据天然按 user_id 隔离，无跨用户访问可能。
（模型配置已收归后台管理：/api/v1/admin/llm-config，全体用户共用。）
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps import require_user
from app.services import user_store
from app.services.user_store import CurrentUser
from app.services.generation_control import usage_summary, request_status
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/me", tags=["个人数据"])


@router.get("/usage", summary="最近 24 小时的生成用量")
async def generation_usage(user: CurrentUser = Depends(require_user)):
    return await asyncio.to_thread(usage_summary, user.id)


@router.get("/generations/{request_id}", summary="查询本人生成请求的状态及结果")
async def generation_status(request_id: str, user: CurrentUser = Depends(require_user)):
    return await asyncio.to_thread(request_status, user.id, request_id)


# ─── 每用户模板 ───

class TemplateIn(BaseModel):
    template: dict  # 前端 MyTemplate 完整结构，以 name 为唯一键
    expected_revision: int | None = Field(None, ge=0)


class BulkTemplatesIn(BaseModel):
    templates: list[dict] = Field(..., max_length=50)  # 单次批量导入上限


# 单条模板序列化后体积上限（防 MB 级 payload 膨胀 DB）
_TEMPLATE_MAX_BYTES = 512 * 1024


def _check_template_size(template: dict) -> None:
    import json as _json
    if len(_json.dumps(template, ensure_ascii=False).encode("utf-8")) > _TEMPLATE_MAX_BYTES:
        raise HTTPException(status_code=413, detail={"error": "模板内容过大（上限 512KB）"})


@router.get("/templates", summary="列出当前用户的模板")
async def list_templates(user: CurrentUser = Depends(require_user)):
    return {"templates": await asyncio.to_thread(user_store.list_templates, user.id)}


@router.put("/templates", summary="保存/覆盖模板（按 name upsert）")
async def upsert_template(req: TemplateIn, user: CurrentUser = Depends(require_user)):
    name = (req.template or {}).get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise HTTPException(status_code=400, detail={"error": "模板名称需为 1 至 120 个字符"})
    _check_template_size(req.template)
    try:
        revision = await asyncio.to_thread(user_store.upsert_template, user.id, name, req.template, req.expected_revision)
    except user_store.TemplateConflict as exc:
        raise HTTPException(409, detail={"error": str(exc), "code": "template_conflict"}) from exc
    return {"status": "ok", "revision": revision}


@router.delete("/templates", summary="删除模板")
async def delete_template(name: str, expected_revision: int | None = Query(None, ge=0), user: CurrentUser = Depends(require_user)):
    try:
        ok = await asyncio.to_thread(user_store.delete_template, user.id, name, expected_revision)
    except user_store.TemplateConflict as exc:
        raise HTTPException(409, detail={"error": str(exc), "code": "template_conflict"}) from exc
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "模板不存在"})
    return {"status": "ok"}


@router.post("/templates/bulk", summary="批量导入模板（本地数据迁移到服务端）")
async def bulk_upload(req: BulkTemplatesIn, user: CurrentUser = Depends(require_user)):
    templates = [t for t in (req.templates or []) if isinstance(t, dict) and t.get("name")]
    for t in templates:
        if not isinstance(t["name"], str) or not t["name"].strip() or len(t["name"]) > 120:
            raise HTTPException(400, detail={"error": "模板名称需为 1 至 120 个字符"})
        _check_template_size(t)
    n = await asyncio.to_thread(user_store.bulk_upsert_templates, user.id, templates)
    return {"status": "ok", "imported": n}
