"""个人数据路由 —— 每用户模板 CRUD

所有端点均要求登录；数据天然按 user_id 隔离，无跨用户访问可能。
（模型配置已收归后台管理：/api/v1/admin/llm-config，全体用户共用。）
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import require_user
from app.services import user_store
from app.services.user_store import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/me", tags=["个人数据"])


# ─── 每用户模板 ───

class TemplateIn(BaseModel):
    template: dict  # 前端 MyTemplate 完整结构，以 name 为唯一键


class BulkTemplatesIn(BaseModel):
    templates: list[dict]


@router.get("/templates", summary="列出当前用户的模板")
async def list_templates(user: CurrentUser = Depends(require_user)):
    return {"templates": user_store.list_templates(user.id)}


@router.put("/templates", summary="保存/覆盖模板（按 name upsert）")
async def upsert_template(req: TemplateIn, user: CurrentUser = Depends(require_user)):
    name = (req.template or {}).get("name")
    if not name or not isinstance(name, str):
        raise HTTPException(status_code=400, detail={"error": "模板缺少 name 字段"})
    user_store.upsert_template(user.id, name, req.template)
    return {"status": "ok"}


@router.delete("/templates", summary="删除模板")
async def delete_template(name: str, user: CurrentUser = Depends(require_user)):
    ok = user_store.delete_template(user.id, name)
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "模板不存在"})
    return {"status": "ok"}


@router.post("/templates/bulk", summary="批量导入模板（本地数据迁移到服务端）")
async def bulk_upload(req: BulkTemplatesIn, user: CurrentUser = Depends(require_user)):
    n = user_store.bulk_upsert_templates(user.id, req.templates or [])
    return {"status": "ok", "imported": n}
