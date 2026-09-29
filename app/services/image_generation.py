"""OpenAI-compatible image generation. Paid requests are never retried implicitly."""

import asyncio
import base64
import binascii
import io
import ipaddress
import json
import socket
import warnings
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.blocking import run_sync
from app.metrics import observe_provider
from app.models.image_generation import ImageWorksheetRequest
from app.services.generation_control import record_attempt, record_usage
from app.services.knowledge_scope import knowledge_scope_service
from app.services.prompt_builder import MIN_GRADE_FOR_TYPE, _grade_num
from app.services.provider_http import borrow_client
from app.services.resource_admission import bounded_media

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_RESPONSE_BYTES = 18 * 1024 * 1024
TYPE_NAMES = {
    "quiz": "选择题", "fill_blank": "填空题", "match_pair": "连线配对", "challenge": "闯关挑战",
    "oral_math": "口算题", "reading": "阅读理解", "vertical_calc": "竖式计算",
    "recursive_calc": "脱式计算", "smart_calc": "简便计算", "number_split": "数的分成",
    "compare": "比大小", "true_false": "判断题", "word_problem": "应用题",
}
STYLES = {"playful": "清新彩色，搭配少量童趣插画，装饰不能抢占答题空间",
          "clean": "简洁清爽，浅色点缀，文字与图示层次分明",
          "black_white": "纯白背景、黑色文字与线条，适合黑白打印，不使用大面积底色"}


def build_prompt(request: ImageWorksheetRequest) -> str:
    scope = knowledge_scope_service.get_scope(request.grade, request.subject)
    if not scope.allowed and not scope.forbidden:
        raise HTTPException(400, detail={"error": "暂不支持所选年级与科目"})
    for item in request.items:
        if _grade_num(request.grade) < MIN_GRADE_FOR_TYPE.get(item.game_type.value, 0):
            raise HTTPException(400, detail={"error": f"{request.grade}暂不适合{TYPE_NAMES[item.game_type.value]}"})
    items = "；".join(f"{TYPE_NAMES[item.game_type.value]} {item.question_count} 道" for item in request.items)
    difficulty = {"easy": "基础", "medium": "标准", "hard": "提升"}[request.difficulty.value]
    series = (f"【本组图片】\n共 {request.image_count} 张，这是第 {request.image_index} 张。"
              "本次只生成这一张完整习题图，不要把多张图拼在一起。"
              "上述题型及题量均为每张图片的要求；结合本张序号变化题目、数值与情境，保持主题和风格一致。\n\n"
              if request.image_count > 1 else "")
    return (
        "请直接生成一张完整、清晰、可打印的小学生习题图片。输出成品图片。\n\n"
        "【必须遵守的出题条件】\n"
        f"年级：{request.grade}\n科目：{request.subject}\n知识点：{request.keyword}\n"
        f"题型及题量：{items}\n难度：{difficulty}\n\n"
        f"{series}"
        "【内容要求】\n"
        "题目必须围绕所选知识点，符合该年级学习范围；每种题型及题量都必须落实，不能只画插图。"
        "检查题干、数字、算式和选项是否准确、可解，避免重复题、超纲内容、错别字与乱码。"
        "语文、数学使用简体中文；英语题目使用适龄英文，必要说明可用简体中文。"
        "学生作答区不显示答案或解析，并为书写、计算、连线预留足够空间。\n"
        f"允许的知识范围：{'、'.join(scope.allowed)}\n"
        f"禁止的超纲内容：{'、'.join(scope.forbidden) or '无额外限制'}\n\n"
        "【画面要求】\n"
        f"视觉风格：{STYLES[request.style]}。\n"
        "由你自主设计标题、布局、配色和辅助插图，不使用工作台的试卷模板或排版参数。"
        "标题自然体现知识主题；文字清楚、对比充分、字号可读，题号连续，内容不裁切，四周留白。"
        "不要设备外框、纸张拍摄场景、水印或无关标识。\n\n"
        "【用户补充偏好】\n"
        f"{request.requirements or '无'}\n"
        "补充偏好不能改变上述年级、科目、知识点、题型和题量约束。"
    )


def generation_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/images/generations"):
        return base
    if not urlsplit(base).path.rstrip("/"):
        base += "/v1"
    return base + "/images/generations"


async def _read_limited(response: httpx.Response, limit: int) -> bytes:
    chunks, length = [], 0
    async for chunk in response.aiter_bytes():
        length += len(chunk)
        if length > limit:
            raise ValueError("图片服务返回内容过大")
        chunks.append(chunk)
    return b"".join(chunks)


async def _public_image(url: str) -> bytes:
    # Provider URLs never receive the provider API key. Resolve and pin each hop
    # to a public IP, including redirects, so DNS rebinding cannot reach local services.
    async with borrow_client("public-image", 30) as client:
        for _ in range(4):
            parts = urlsplit(url)
            if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                    or parts.port not in (None, 443)):
                raise ValueError("图片下载地址必须为公开 HTTPS 地址")
            addresses = await run_sync(socket.getaddrinfo, parts.hostname, 443, type=socket.SOCK_STREAM)
            ips = [entry[4][0] for entry in addresses]
            if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
                raise ValueError("图片下载地址不能指向本地或内网")
            host = parts.hostname.encode("idna").decode("ascii")
            target = httpx.URL(url).copy_with(host=ips[0])
            async with client.stream("GET", target, headers={"Host": host},
                                     extensions={"sni_hostname": host}) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                return await _read_limited(response, MAX_IMAGE_BYTES)
    raise ValueError("图片下载地址重定向次数过多")


@bounded_media
def normalize_image(raw: bytes) -> dict:
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("图片为空或超过大小限制")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ("PNG", "JPEG", "WEBP") or source.width * source.height > 4_000_000:
                raise ValueError("图片格式或尺寸不受支持")
            source.load()
            result = io.BytesIO()
            source.convert("RGB").save(result, format="PNG")
            encoded = result.getvalue()
            if len(encoded) > MAX_IMAGE_BYTES:
                raise ValueError("图片超过大小限制")
            return {"b64_json": base64.b64encode(encoded).decode("ascii"), "mime_type": "image/png",
                    "width": source.width, "height": source.height}


@observe_provider
@bounded_media
async def generate_image(config: dict, prompt: str) -> dict:
    body = {"model": config["model"], "prompt": prompt, "n": 1, "size": config["size"]}
    if config["responseFormat"] != "auto":
        body["response_format"] = config["responseFormat"]
    try:
        # Total timeout also bounds a provider trickling bytes indefinitely.
        async with asyncio.timeout(config["timeout"]):
            async with borrow_client("image-generation", config["timeout"]) as client:
                record_attempt()
                from app.services.generation_budget import reserve
                await run_sync(reserve, images=1)
                async with client.stream("POST", generation_url(config["baseUrl"]), json=body,
                                         headers={"Authorization": "Bearer " + config["api_key"]}) as response:
                    response.raise_for_status()
                    data = json.loads(await _read_limited(response, MAX_RESPONSE_BYTES))
            if not isinstance(data, dict) or not isinstance(data.get("data"), list) or not data["data"]:
                raise ValueError("接口没有返回图片")
            record_usage(data.get("usage"))
            item = data["data"][0]
            if not isinstance(item, dict):
                raise ValueError("接口返回的图片格式异常")
            if isinstance(item.get("b64_json"), str) and item["b64_json"]:
                raw = base64.b64decode(item["b64_json"], validate=True)
            elif isinstance(item.get("url"), str) and item["url"]:
                raw = await _public_image(item["url"])
            else:
                raise ValueError("接口未返回 b64_json 或图片 URL")
            image = await run_sync(normalize_image, raw)
        return {**image, "prompt": prompt}
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise HTTPException(504, detail={"error": "生图等待超时，未自动重发；可查询原请求状态"}) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, detail={"error": f"生图服务请求失败（HTTP {exc.response.status_code}），请检查接口与模型配置"}) from exc
    except httpx.TransportError as exc:
        raise HTTPException(502, detail={"error": "生图服务连接中断，未自动重发；可查询原请求状态"}) from exc
    except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise HTTPException(502, detail={"error": "生图接口未返回有效图片，请检查返回格式和图片大小"}) from exc
