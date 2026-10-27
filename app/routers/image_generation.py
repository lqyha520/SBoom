
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.blocking import run_sync
from app.deps import require_admin, require_recent_admin, require_user
from app.library_deps import no_store
from app.models.image_generation import ImageModelConfig, ImageWorksheetRequest
from app.models.model_profiles import ImageModelProfiles
from app.sensitive_config import SensitiveConfigRoute
from app.services import image_config
from app.services.generation_control import metered
from app.services.generation_policy import runtime_config
from app.services.image_generation import build_prompt, generate_image
from app.services.model_profiles import entries
from app.services.provider_failover import run_with_failover
from app.services.user_store import CurrentUser

router = APIRouter(prefix="/api/v1", tags=["图片出题"], dependencies=[Depends(no_store)], route_class=SensitiveConfigRoute)


@router.get("/admin/image-config")
def get_config(admin: CurrentUser = Depends(require_admin)):
    return image_config.get_admin_config()


@router.put("/admin/image-config")
def save_config(request: ImageModelProfiles | ImageModelConfig, admin: CurrentUser = Depends(require_recent_admin)):
    from app.provider_policy import validate_endpoint
    if isinstance(request, ImageModelProfiles):
        for profile in request.models:
            validate_endpoint(profile.baseUrl, resolve=profile.enabled)
        return image_config.save_models(request.models, expected_revision=request.revision, require_revision=True)
    validate_endpoint(request.baseUrl)
    image_config.save_config(request)
    return image_config.get_config()


@router.delete("/admin/image-config")
def clear_config(admin: CurrentUser = Depends(require_recent_admin), if_match: str | None = Header(None)):
    saved = image_config.clear_config(expected_revision=if_match, check_current=True)
    return {**saved, "status": "ok"}


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
    prompt = await run_sync(build_prompt, request)
    config = runtime_config("image")
    if not config["api_key"] or not config["baseUrl"] or not config["model"]:
        raise HTTPException(400, detail={"error": "尚未配置生图服务，请在后台「模型配置 → 图片生成服务」中设置"})
    candidates = [{**profile, "_health_kind": "image", "_revision": config["revision"]}
                  for profile in entries(config) if profile["enabled"]]
    return await run_with_failover(candidates, lambda profile: generate_image(profile, prompt), summarize_failures=True)


@router.get("/image-generation/assets/{asset_id}")
def image_asset(asset_id: str, user: CurrentUser = Depends(require_user)):
    from app.library_files import asset_response
    from app.services.image_assets import owned
    return asset_response(owned(user.id, asset_id))
