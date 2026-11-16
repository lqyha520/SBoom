
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from app.blocking import run_sync
from app.config import get_settings
from app.deps import require_admin, require_recent_admin, require_user
from app.http_contracts import binary_responses
from app.library_deps import no_store
from app.models.image_generation import (
    MAX_IMAGE_CONCURRENCY,
    ImageGenerationOptions,
    ImageModelConfig,
    ImageWorksheetRequest,
)
from app.models.image_generation_api_responses import (
    ImageGenerationClearConfigResponse,
    ImageGenerationGenerateResponse,
    ImageGenerationGetConfigResponse,
    ImageGenerationPreviewPromptResponse,
    ImageGenerationSaveConfigResponse,
)
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


@router.get("/admin/image-config", response_model=ImageGenerationGetConfigResponse, response_model_exclude_unset=True)
def get_config(admin: CurrentUser = Depends(require_admin)):
    return image_config.get_admin_config()


@router.put("/admin/image-config", response_model=ImageGenerationSaveConfigResponse, response_model_exclude_unset=True)
def save_config(request: ImageModelProfiles | ImageModelConfig, admin: CurrentUser = Depends(require_recent_admin)):
    from app.provider_policy import validate_endpoint
    if isinstance(request, ImageModelProfiles):
        for profile in request.models:
            validate_endpoint(profile.baseUrl, resolve=profile.enabled)
        return image_config.save_models(request.models, expected_revision=request.revision, require_revision=True)
    validate_endpoint(request.baseUrl)
    image_config.save_config(request)
    return image_config.get_config()


@router.delete("/admin/image-config", response_model=ImageGenerationClearConfigResponse, response_model_exclude_unset=True)
def clear_config(admin: CurrentUser = Depends(require_recent_admin), if_match: str | None = Header(None)):
    saved = image_config.clear_config(expected_revision=if_match, check_current=True)
    return {**saved, "status": "ok"}


@router.get("/image-generation/options", response_model=ImageGenerationOptions)
def options(user: CurrentUser = Depends(require_user)):
    config = image_config.get_config()
    settings = get_settings()
    concurrency = min(MAX_IMAGE_CONCURRENCY, settings.generation_user_concurrency, settings.generation_global_concurrency)
    return {"configured": bool(config["hasKey"] and config["baseUrl"] and config["model"]),
            "max_concurrency": concurrency, "default_concurrency": min(2, concurrency)}


@router.post("/image-generation/prompt", response_model=ImageGenerationPreviewPromptResponse, response_model_exclude_unset=True)
def preview_prompt(request: ImageWorksheetRequest, user: CurrentUser = Depends(require_user)):
    return {"prompt": build_prompt(request)}


@router.post("/generate-image", response_model=ImageGenerationGenerateResponse, response_model_exclude_unset=True)
@metered("image")
async def generate(request: ImageWorksheetRequest, http_request: Request, user: CurrentUser = Depends(require_user)):
    prompt = await run_sync(build_prompt, request)
    config = runtime_config("image")
    if not config["api_key"] or not config["baseUrl"] or not config["model"]:
        raise HTTPException(400, detail={"error": "尚未配置生图服务，请在后台「模型配置 → 图片生成服务」中设置"})
    candidates = [{**profile, "_health_kind": "image", "_revision": config["revision"]}
                  for profile in entries(config) if profile["enabled"]]
    image = await run_with_failover(candidates, lambda profile: generate_image(profile, prompt), summarize_failures=True)
    from app.services.image_assets import persist
    from app.services.image_recovery import checkpoint_saved, current_request
    from app.services.image_review import pending, review_image
    owner = current_request.get()
    if owner is None:
        raise RuntimeError("图片生成缺少请求身份")
    result = await run_sync(persist, *owner, {**image, "quality_review": pending("图片已保存，内容检查尚未完成")})
    await run_sync(checkpoint_saved, result)
    result["quality_review"] = await review_image(image, request)
    await run_sync(checkpoint_saved, result)
    return result


@router.get("/image-generation/assets/{asset_id}", response_class=Response, responses=binary_responses('image/jpeg', 'image/png', 'image/webp', partial=True))
def image_asset(asset_id: str, user: CurrentUser = Depends(require_user)):
    from app.library_files import asset_response
    from app.services.image_assets import owned
    return asset_response(owned(user.id, asset_id))
