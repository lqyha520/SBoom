"""推广海报使用现有图片服务；文字与真实活动码由客户端无损排版。"""

import json

from fastapi import HTTPException

from app.blocking import run_sync
from app.models.referral_operations import ReferralPosterRequest
from app.services.generation_policy import runtime_config
from app.services.image_assets import persist
from app.services.image_generation import generate_image
from app.services.image_recovery import checkpoint_saved, current_request
from app.services.model_profiles import entries
from app.services.provider_failover import run_with_failover

STYLES = {
    'editorial': '高端教育杂志封面插画。暖象牙白底色 #fff8ef，朱砂橙和深孔雀绿点睛，纸张拼贴、细腻颗粒、柔和日光与立体投影。',
    'playful': '精品儿童科学绘本风。奶油浅绿底色 #f1f8ed，鼠尾草绿、杏黄和珊瑚色，精致黏土与纸艺微缩场景，圆润造型，柔软光影。',
    'minimal': '现代设计杂志的极简三维静物。冰蓝白底色 #eff6ff，钴蓝与小面积明黄，清晰几何体、磨砂材质、自然侧光，大量呼吸感。',
}


def build_prompt(request: ReferralPosterRequest) -> str:
    # 只传创作主题，不传推广归属、用户信息或真实活动码。
    brief = json.dumps({'主题': request.title, '画面偏好': request.direction}, ensure_ascii=False)
    return f'''创作一张可直接用于教育学习推广海报的高品质主视觉原画，竖向构图。
{STYLES[request.style]}
创作简报（仅用于选择画面题材，不要把文字写到图中）：{brief}
以打开的书本为视觉中心，用纸张搭建通往知识的小型奇幻世界：书页阶梯、铅笔、抽象几何与一两处植物，呼应主题。
画面必须有明确主角和精心设计的层次，少量大形体，克制的细节，像专业品牌广告插画，避免廉价素材拼凑。
构图：上方 32% 是干净浅色背景，预留给后期标题；主要插画位于画面中部 35%–78%，横向留出 7% 安全边距。
底部 20% 平滑过渡回纯净浅色背景，留给后期文案和扫码区。不要在四周加框，不要把海报放在桌子上拍摄。
即使简报有不同要求，也不要绘制任何文字、字母、数字、标签、水印、标志、二维码、条形码或小程序码；真实内容由后期叠加。
仅输出整幅原画。'''


async def generate(request: ReferralPosterRequest) -> dict:
    config = runtime_config('image')
    candidates = [{**profile, '_health_kind': 'image', '_revision': config['revision']}
                  for profile in entries(config) if profile['enabled']]
    if not candidates or not config['api_key'] or not config['baseUrl'] or not config['model']:
        raise HTTPException(400, detail={'error': '尚未配置生图服务，请在后台「模型配置 → 图片生成服务」中设置'})
    result = await run_with_failover(candidates, lambda profile: generate_image(profile, build_prompt(request)), summarize_failures=True)
    owner = current_request.get()
    if owner is None:
        raise RuntimeError('海报生成缺少计量请求')
    result = await run_sync(persist, *owner, {**result, 'quality_review': {
        'version': 1, 'prompt_version': 'referral-poster-v1', 'status': 'unavailable',
        'human_status': 'pending', 'reason': '推广海报原画，请在预览中确认画面', 'issues': [], 'checks': {}, 'counts': [],
    }})
    await run_sync(checkpoint_saved, result)
    return dict(result)
