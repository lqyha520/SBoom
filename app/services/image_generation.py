"""单个图片模型调用；跨模型切换由路由统一编排。"""

import asyncio
import base64
import binascii
import io
import ipaddress
import json
import re
import socket
import warnings
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.blocking import run_sync, run_sync_in
from app.metrics import observe_provider
from app.models.image_generation import ImageWorksheetRequest
from app.provider_policy import origin, validate_endpoint
from app.services.generation_control import record_attempt, record_usage
from app.services.knowledge_scope import knowledge_scope_service
from app.services.prompt_builder import MIN_GRADE_FOR_TYPE, _grade_num, _textbook_context
from app.services.provider_http import borrow_client
from app.services.resource_admission import bounded_image_request, bounded_media

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_RESPONSE_BYTES = 18 * 1024 * 1024
TASK_POLL_INTERVAL = 2.0
MODEL_ERROR_CODES = {"model_not_found", "model_not_supported", "invalid_model", "unsupported_model"}
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
    if (not scope.allowed and not scope.forbidden) or (not request.keyword and not scope.allowed):
        raise HTTPException(400, detail={"error": "暂不支持所选年级与科目"})
    for item in request.items:
        if _grade_num(request.grade) < MIN_GRADE_FOR_TYPE.get(item.game_type.value, 0):
            raise HTTPException(400, detail={"error": f"{request.grade}暂不适合{TYPE_NAMES[item.game_type.value]}"})
    available_types = "、".join(name for kind, name in TYPE_NAMES.items()
                              if _grade_num(request.grade) >= MIN_GRADE_FOR_TYPE.get(kind, 0))
    items = "；".join(
        f"{TYPE_NAMES[item.game_type.value]} {item.question_count} 道"
        if item.question_count is not None else f"{TYPE_NAMES[item.game_type.value]}（题量自动安排）"
        for item in request.items
    ) or f"自动安排：根据所选科目和知识点，从适龄题型（{available_types}）中选择 1 至 5 种，不必全部使用"
    quantity_rule = (
        "已指定的题量必须准确落实；未指定题量的题型，由你根据内容难度、图片尺寸和答题空间安排合理数量，"
        "每种至少 1 道、最多 20 道，整张合计不超过 24 道。不要为了凑满题数挤压字号或作答区。"
        if not request.items or any(item.question_count is None for item in request.items) else "每种题量都必须准确落实。"
    )
    keyword = request.keyword or "自动安排：从所选科目的允许知识范围中选择 1 至 3 个本年级核心知识点，优先基础巩固"
    difficulty = {"easy": "基础", "medium": "标准", "hard": "提升"}[request.difficulty.value]
    series = (f"【本组图片】\n共 {request.image_count} 张，这是第 {request.image_index} 张。"
              "本次只生成这一张完整习题图，不要把多张图拼在一起。"
              "上述题型及题量均为每张图片的要求；结合本张序号变化题目、数值与情境，保持主题和风格一致。\n\n"
              if request.image_count > 1 else "")
    return (
        "请直接生成一张完整、清晰、可打印的小学生习题图片。输出成品图片。\n\n"
        "【必须遵守的出题条件】\n"
        f"年级：{request.grade}\n科目：{request.subject}\n知识点：{keyword}\n"
        f"{_textbook_context(scope, request.keyword)}\n"
        f"题型及题量：{items}\n难度：{difficulty}\n\n"
        f"{series}"
        "【内容要求】\n"
        "题目必须围绕已指定或自动选定的知识点，符合该年级学习范围；每种选定题型都必须出现，不能只画插图。"
        "自动安排的内容必须符合对应科目的知识范围，不得把其他科目的知识范围用于本学科；"
        "已指定的科目、知识点和题型不得擅自替换，自动题型必须适合科目与年级。"
        f"{quantity_rule}"
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
    content = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
        if len(content) + len(chunk) > limit:
            raise ValueError("图片服务返回内容过大")
        content.extend(chunk)
    return bytes(content)


def _provider_error(status: int, payload: bytes = b"") -> dict:
    # 只将上游错误归类成固定提示，不回显可能含密钥、提示词或内部地址的正文。
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeError):
        data = {}
    error = data.get("error", data) if isinstance(data, dict) else {}
    if isinstance(error, str):
        error = {"message": error}
    if not isinstance(error, dict):
        error = {}
    message = str(error.get("message", "")).lower()
    code = str(error.get("code", "")).lower()
    param = str(error.get("param", "")).lower()
    reason, hint = "request_rejected", "上游拒绝请求，请核对接口支持的参数与模型权限"
    if status in (401, 403):
        reason, hint = "authentication", "密钥无效或没有该模型的调用权限"
    elif status == 402 or code in ("insufficient_quota", "insufficient_balance", "quota_exceeded"):
        reason, hint = "quota", "上游额度不足或配额已用尽"
    elif status == 429:
        reason, hint = "rate_limit", "上游限流或配额已用尽"
    elif status >= 500:
        reason, hint = "unavailable", "上游服务暂不可用"
    elif code in ("content_policy_violation", "content_filter", "safety_violation"):
        reason, hint = "content_policy", "上游内容审核拒绝了请求"
    elif status == 400 and (code == "async_required" or message.startswith("图片 api 仅支持异步任务")):
        reason, hint = "async_required", "该接口要求通过异步任务生成图片"
    elif param == "size" or ("size" in message and any(word in message for word in ("invalid", "support", "must be"))):
        reason, hint = "size", "上游不接受当前图片尺寸，请核对该模型支持的尺寸"
    elif param == "response_format":
        reason, hint = "response_format", "上游不接受当前返回格式，请核对模型配置"
    elif param == "model" or code in MODEL_ERROR_CODES:
        reason, hint = "model", "模型不可用或当前密钥没有该模型的权限"
    elif param == "prompt" and any(word in message for word in ("long", "length", "limit")):
        reason, hint = "prompt_length", "上游提示词长度限制小于当前请求"
    return {"code": "image_provider_error", "upstream_status": status, "reason": reason,
            "error": f"生图服务请求失败（HTTP {status}）：{hint}"}


async def _provider_json(client: httpx.AsyncClient, method: str, url: str, headers: dict,
                         body: dict | None = None) -> dict:
    async with client.stream(method, url, headers=headers, json=body) as response:
        if response.is_error:
            payload = b""
            try:
                # 错误正文既限长又限时，不能拖住备用模型的切换。
                async with asyncio.timeout(1):
                    payload = await _read_limited(response, 8192)
            except (ValueError, TimeoutError, httpx.HTTPError):
                pass
            raise HTTPException(502, detail=_provider_error(response.status_code, payload))
        response.raise_for_status()
        payload = await _read_limited(response, MAX_RESPONSE_BYTES)
        # 成品 JSON 可含十余 MiB Base64；解析不应阻塞其他请求和任务心跳。
        data = await run_sync_in("media", json.loads, payload)
        if not isinstance(data, dict):
            raise ValueError("图片服务返回格式异常")
        return data


def _has_image_result(data: dict) -> bool:
    items = data.get("data")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return False
    return any(isinstance(items[0].get(key), str) and bool(items[0][key]) for key in ("b64_json", "url"))


def _task_poll_url(data: dict, endpoint: str) -> tuple[str, str]:
    task_id, poll_url = data.get("task_id", data.get("id")), data.get("poll_url")
    if (not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", task_id)
            or not isinstance(poll_url, str) or not poll_url or len(poll_url) > 2000
            or any(char.isspace() or ord(char) < 32 for char in poll_url)):
        raise ValueError("异步图片任务缺少有效编号或查询地址")
    target = urljoin(endpoint, poll_url)
    parts = urlsplit(target)
    # 轮询携带原服务商密钥，仅允许同协议、主机、端口；拒绝重定向与内网解析。
    if parts.username or parts.password or parts.fragment or origin(target) != origin(endpoint):
        raise ValueError("异步图片任务查询地址不属于当前服务商")
    validate_endpoint(parts._replace(query="").geturl(), resolve=False)
    return task_id, target


async def _poll_image_task(client: httpx.AsyncClient, data: dict, endpoint: str, headers: dict) -> dict:
    task_id, poll_url = _task_poll_url(data, endpoint)
    transient_errors = 0
    while True:
        # 只查询已提交任务，绝不在轮询阶段重复发送生成 POST。
        await asyncio.sleep(TASK_POLL_INTERVAL)
        try:
            response = await _provider_json(client, "GET", poll_url, headers)
        except (httpx.TransportError, HTTPException) as exc:
            detail: dict = exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) else {}
            status = detail.get("upstream_status", 0)
            retryable = isinstance(exc, httpx.TransportError) or status == 429 or status >= 500
            if not retryable or transient_errors >= 2:
                raise
            transient_errors += 1
            continue
        transient_errors = 0
        # 两种已验证协议：批量 items 列表，以及 image.task 单任务对象。
        items = response.get("items") if "items" in response else [response]
        if not isinstance(items, list):
            raise ValueError("异步图片任务查询格式异常")
        matches = [item for item in items if isinstance(item, dict) and item.get("id") == task_id]
        if len(matches) != 1:
            raise ValueError("未返回指定的异步图片任务")
        task = matches[0]
        status = task.get("status")
        if status in ("queued", "running") and task.get("terminal") is not True:
            continue
        if status in ("success", "partial_success", "succeeded", "completed"):
            results = task.get("results", task.get("data"))
            if results is None and isinstance(task.get("result"), dict):
                results = task["result"].get("data")
            if not isinstance(results, list) or not results:
                raise ValueError("异步图片任务未返回成品图片")
            return {"data": results, "usage": task.get("usage")}
        if status in ("failed", "cancelled", "text_review"):
            reason = "content_policy" if status == "text_review" else "generation_failed"
            hint = "上游内容审核拒绝了图片任务" if reason == "content_policy" else "上游图片任务执行失败，请稍后重试或更换服务商"
            error = task.get("error")
            code = task.get("error_code") or (error.get("code") if isinstance(error, dict) else None)
            # 服务商可能用笼统的 public_error 覆盖具体原因，保留标准模型错误码的分类。
            if status == "failed" and isinstance(code, str) and code.lower() in MODEL_ERROR_CODES:
                reason, hint = "model", "上游模型不可用或当前密钥没有该模型的权限，请更换可用型号或联系服务商"
            # 任务原始报错可能含提示词或内部地址，不能直接返回给工作台。
            raise HTTPException(502, detail={"code": "image_task_failed", "reason": reason, "error": hint})
        raise ValueError("异步图片任务状态异常")


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


async def _normalize_when_available(raw: bytes) -> dict:
    while True:
        try:
            return await run_sync_in("media", normalize_image, raw)
        except HTTPException as exc:
            if exc.status_code != 429:
                raise
            # 模型已出图，只等待本地处理槽位；沿用候选总超时，不重新请求上游。
            await asyncio.sleep(0.05)


@observe_provider
@bounded_image_request
async def generate_image(config: dict, prompt: str) -> dict:
    processing_image = False
    body = {"model": config["model"], "prompt": prompt, "n": 1, "size": config["size"]}
    mode = config.get("requestMode", "auto")
    if mode == "async":
        body["async"] = True
    if config["responseFormat"] != "auto":
        body["response_format"] = config["responseFormat"]
    try:
        # Total timeout also bounds a provider trickling bytes indefinitely.
        async with asyncio.timeout(config["timeout"]):
            endpoint = generation_url(config["baseUrl"])
            async with borrow_client("image-generation", config["timeout"], base_url=endpoint) as client:
                from app.services.generation_budget import reserve
                await run_sync(reserve, images=1)
                record_attempt()
                headers = {"Authorization": "Bearer " + config["api_key"]}
                try:
                    data = await _provider_json(client, "POST", endpoint, headers, body)
                except HTTPException as exc:
                    # 仅在服务明确拒绝同步协议时协商一次；超时、断线和其他 400 均不重发。
                    if mode != "auto" or not isinstance(exc.detail, dict) or exc.detail.get("reason") != "async_required":
                        raise
                    record_attempt()
                    data = await _provider_json(client, "POST", endpoint, headers, {**body, "async": True})
                # 同步成品也可能附带 task_id/poll_url；仅在尚无图片时进入异步轮询。
                if not _has_image_result(data) and (data.get("object") == "image_task" or "task_id" in data or "poll_url" in data):
                    data = await _poll_image_task(client, data, endpoint, headers)
            if not isinstance(data, dict) or not isinstance(data.get("data"), list) or not data["data"]:
                raise ValueError("接口没有返回图片")
            record_usage(data.get("usage"))
            item = data["data"][0]
            if not isinstance(item, dict):
                raise ValueError("接口返回的图片格式异常")
            if isinstance(item.get("b64_json"), str) and item["b64_json"]:
                raw = await run_sync_in("media", base64.b64decode, item["b64_json"], validate=True)
            elif isinstance(item.get("url"), str) and item["url"]:
                raw = await _public_image(item["url"])
            else:
                raise ValueError("接口未返回 b64_json 或图片 URL")
            # 归一化会产生新 PNG 和 Base64，提前释放供应商的大响应，减少峰值副本。
            del item, data
            processing_image = True
            image = await _normalize_when_available(raw)
        return {**image, "prompt": prompt}
    except httpx.PoolTimeout as exc:
        raise HTTPException(429, detail={"error": "生图连接池繁忙，请稍后重试"}) from exc
    except (TimeoutError, httpx.TimeoutException) as exc:
        if processing_image:
            raise HTTPException(429, detail={"code": "image_processing_busy",
                "error": "上游已返回图片，但本地处理超时；重新生成可能产生新的费用"}) from exc
        raise HTTPException(504, detail={"error": "生图等待超时，请查询原请求状态；上游可能已处理并计费"}) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, detail=_provider_error(exc.response.status_code)) from exc
    except (httpx.TransportError, httpx.DecodingError) as exc:
        raise HTTPException(502, detail={"error": "生图服务连接中断，请查询原请求状态；上游可能已处理并计费"}) from exc
    except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise HTTPException(502, detail={"error": "生图接口未返回有效图片，请检查返回格式和图片大小"}) from exc
