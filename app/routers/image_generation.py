import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from app.deps import require_admin, require_user
from app.library_deps import no_store
from app.models.image_generation import ImageModelConfig, ImageWorksheetRequest
from app.services import image_config
from app.services.generation_control import metered
from app.services.image_generation import build_prompt, generate_image
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1", tags=["图片出题"], dependencies=[Depends(no_store)])


@router.get("/admin/image-config")
def get_config(admin: CurrentUser = Depends(require_admin)):
    return image_config.get_config()


@router.put("/admin/image-config")
def save_config(request: ImageModelConfig, admin: CurrentUser = Depends(require_admin)):
    image_config.save_config(request)
    return image_config.get_config()


@router.delete("/admin/image-config")
def clear_config(admin: CurrentUser = Depends(require_admin)):
    image_config.clear_config()
    return {"status": "ok"}


@router.get("/image-generation/options")
def options(user: CurrentUser = Depends(require_user)):
    config = image_config.get_config()
    return {"configured": bool(config["hasKey"] and config["baseUrl"] and config["model"])}


@router.post("/image-generation/prompt")
def preview_prompt(request: ImageWorksheetRequest, user: CurrentUser = Depends(require_user)):
    return {"prompt": build_prompt(request)}


@router.post("/generate-image")
@metered("image")
async def generate(request: ImageWorksheetRequest, http_request: Request, user: CurrentUser = Depends(require_user)):
    prompt = await asyncio.to_thread(build_prompt, request)
    config = await asyncio.to_thread(image_config.get_config, with_key=True)
    if not config["api_key"] or not config["baseUrl"] or not config["model"]:
        raise HTTPException(400, detail={"error": "尚未配置生图服务，请在后台「模型配置 → 图片生成服务」中设置"})
    return await generate_image(config, prompt)


@router.get("/image-generation/assets/{asset_id}")
def image_asset(asset_id: str, user: CurrentUser = Depends(require_user)):
    from app.library_files import asset_response
    from app.services.image_assets import owned
    return asset_response(owned(user.id, asset_id))
