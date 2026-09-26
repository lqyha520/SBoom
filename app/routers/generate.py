"""生成路由 —— 题目/游戏生成 API 端点"""

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.blocking import run_sync
from app.config import get_settings
from app.deps import require_user
from app.models import (
    BatchGenerateRequest,
    BatchGenerateResponse,
    BatchItem,
    ErrorResponse,
    FeedbackRequest,
    GameResult,
    GenerateRequest,
    KnowledgeScope,
    ValidateRequest,
    ValidateResult,
)
from app.services import app_config
from app.services.generation_control import metered
from app.services.generation_results import match_sections, normalize_result
from app.services.knowledge_scope import knowledge_scope_service
from app.services.llm_client import llm_client
from app.services.prompt_builder import prompt_builder
from app.services.rate_limit import allow
from app.services.user_store import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["生成"])
settings = get_settings()


def _object(value) -> dict:
    """模型返回的 JSON 必须是对象；合法 JSON 也可能是数组/标量，那种情况按生成失败处理。"""
    if not isinstance(value, dict):
        raise ValueError("模型返回的 JSON 不是对象")
    return value


def _extract_json(text: str) -> dict:
    """从 LLM 返回的文本中提取 JSON，处理思考标签/markdown 包裹等干扰"""
    text = text.strip()

    # 剥掉推理模型的 <think>...</think> 思考过程
    import re
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # 未闭合的 <think>（输出被截断）：取 </think> 之后 / 或最后一个 { 开始
    if "<think>" in text and "</think>" not in text:
        text = text.split("<think>")[0]

    # 去掉可能的 ```json ... ``` 包裹
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 尝试找到 JSON 开始和结束位置
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]

    try:
        return _object(json.loads(text))
    except json.JSONDecodeError:
        # JSON 内部有杂质（如 "Extra data"）：用 JSONDecoder 逐段解析取第一个完整对象
        try:
            obj, _ = json.JSONDecoder().raw_decode(text)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        # 括号配平修复：从第一个 { 起逐字符配平，截取完整对象
        depth = 0
        in_str = False
        esc = False
        for i, ch in enumerate(text):
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return _object(json.loads(text[: i + 1]))
        raise


def _merged_llm_params() -> dict:
    """合并 LLM 调用参数，来源：管理员在后台配置的全局模型 > .env 兜底。

    模型配置收归后台管理（/admin 的「模型配置」），全体用户共用，密钥加密存于服务端；
    客户端不可指定接口地址/密钥（防 SSRF 与越权绕过）。
    """
    g = app_config.get_llm(with_key=True)
    t = float(g["timeout"] or 0)
    return {
        "base_url": g["baseUrl"] or settings.llm_base_url,
        "model": g["model"] or settings.llm_model,
        "api_key": g["api_key"] or settings.llm_api_key,
        # 超时下限 120s：整卷生成 prompt 很长，部分模型需要 1-2 分钟；
        # 超时过短会让客户端先掐断，而服务端通常已开始生成并计费——白白扣钱
        "timeout": max(t, 120.0),
    }


async def _call_llm_and_parse(system_prompt: str, user_message: str) -> dict:
    """调用 LLM 并解析返回的 JSON。配置来源：后台全局配置 > .env 兜底。"""
    p = await run_sync(_merged_llm_params)
    if not p["api_key"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "尚未配置模型",
                "detail": "模型服务由管理员统一配置，请联系管理员在后台「模型配置」中填写接口地址和密钥",
            },
        )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    try:
        raw_response = await llm_client.chat(
            messages, base_url=p["base_url"], model=p["model"],
            api_key=p["api_key"], timeout=p["timeout"],
        )
        return _extract_json(raw_response)
    except json.JSONDecodeError as e:
        # raw_response 可能未绑定（llm_client 内部解析响应 JSON 就失败时），分别兜底
        logger.error("模型返回内容不是有效 JSON: %s", type(e).__name__)
        raise HTTPException(
            status_code=502,
            detail={"error": "LLM 返回格式异常，请重试", "detail": str(e)},
        ) from e
    except httpx.HTTPStatusError as e:
        logger.error("模型 API 错误: HTTP %s", e.response.status_code)
        raise HTTPException(
            status_code=502,
            detail={"error": f"模型服务请求失败 ({e.response.status_code})", "detail": "未自动重发，请先查询原请求状态"},
        ) from e
    except httpx.TimeoutException as e:
        # 注意：TimeoutException 是 TransportError 的子类，必须先于其捕获。
        # 超时意味着请求已到达服务端（很可能已被处理甚至计费），不能自动重试。
        logger.error(f"LLM 响应超时（timeout={p['timeout']}s）: {type(e).__name__}")
        raise HTTPException(
            status_code=504,
            detail={
                "error": f"生成超时（等待 {int(p['timeout'])} 秒无响应）",
                "detail": "请求已发送给模型服务，超时前未返回结果（服务端可能已处理并计费）。"
                          "未自动重发。请先查询原请求状态，重新生成会发起新的模型调用。",
            },
        ) from e
    except httpx.TransportError as e:
        logger.error("模型连接异常: %s", type(e).__name__)
        raise HTTPException(
            status_code=502,
            detail={"error": "模型连接中断", "detail": "请先查询原请求状态，再联系管理员检查模型配置"},
        ) from e
    except Exception:
        logger.exception("LLM 调用未知错误")
        raise HTTPException(status_code=500, detail={"error": "内部错误", "detail": "服务异常，请稍后重试；若持续出现请联系管理员查看服务日志"}) from None




# ─── API 端点 ───

@router.post(
    "/generate-batch",
    response_model=BatchGenerateResponse,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="批量生成整张试卷（一次 LLM 调用出多个题型）",
    description="接收多个题型任务，一次 LLM 调用生成整张试卷的所有大题，避免限流。",
)
@metered("batch")
async def generate_batch(request: BatchGenerateRequest, http_request: Request, user: CurrentUser = Depends(require_user)):
    """一次 LLM 调用生成整卷的多个题型"""
    # 1. 知识范围
    scope = await run_sync(knowledge_scope_service.get_scope, request.grade, request.subject)
    if not scope.allowed and not scope.forbidden:
        raise HTTPException(
            status_code=400,
            detail={"error": f"暂不支持 {request.grade} 的 {request.subject} 科目"},
        )

    # 2. 题型-年级适配校验
    from app.services.prompt_builder import MIN_GRADE_FOR_TYPE, _grade_num
    g_num = _grade_num(request.grade)
    for it in request.items:
        min_g = MIN_GRADE_FOR_TYPE.get(it.game_type, 0)
        if min_g and g_num < min_g:
            raise HTTPException(
                status_code=400,
                detail={"error": f"{request.grade}还没有学过{it.game_type}哦"},
            )

    # 3. 组装批量 Prompt
    system_prompt = prompt_builder.build_batch_prompt(
        grade=request.grade,
        subject=request.subject,
        keyword=request.keyword,
        difficulty=request.difficulty.value,
        items=request.items,
        scope=scope,
    )
    user_message = prompt_builder.build_batch_user_message(request.keyword)

    # 4. 调用 LLM（一次，配置：后台全局 > .env）
    try:
        raw = await _call_llm_and_parse(system_prompt, user_message)
    except HTTPException:
        raise
    except (RuntimeError, ValueError, TypeError) as e:
        logger.exception("批量生成失败: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail={"error": "批量生成失败", "detail": "生成链路异常，请重试；若持续失败请联系管理员"}) from e

    matched = match_sections(raw, request.items)
    seen: set[str] = set()
    sections = []
    for index, (item, section) in enumerate(zip(request.items, matched, strict=False)):
        resolved = item.model_copy(update={"section_id": item.section_id or f"section-{index + 1}"})
        sections.append(await normalize_result(section, request, resolved, scope, _call_llm_and_parse, seen))
    return BatchGenerateResponse(sections=sections)


@router.post(
    "/generate",
    response_model=GameResult,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="生成题目/游戏",
    description="根据年级、科目和知识点生成题目。同一 X-Request-ID 重放原结果，不重复调用模型。",
)
@metered("single")
async def generate_questions(request: GenerateRequest, http_request: Request, user: CurrentUser = Depends(require_user)):
    """生成题目（非流式）。每次都真实调用 LLM，保证每次生成的试卷都是新的。"""
    # 1. 题型-年级适配校验（低年级拦截超纲计算题型）
    from app.services.prompt_builder import MIN_GRADE_FOR_TYPE, _grade_num
    g_num = _grade_num(request.grade)
    min_g = MIN_GRADE_FOR_TYPE.get(request.game_type.value, 0)
    if min_g and g_num < min_g:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{request.grade}还没有学过{request.game_type.value}哦",
                "detail": f"该题型建议 {min_g} 年级及以上使用，请换一个题型",
            },
        )

    # 1. 获取知识范围
    scope = await run_sync(knowledge_scope_service.get_scope, request.grade, request.subject)

    if not scope.allowed and not scope.forbidden:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"暂不支持 {request.grade} 的 {request.subject} 科目",
                "detail": "知识范围库中未定义该年级和科目的内容",
            },
        )

    # 2. 组装 Prompt
    system_prompt = prompt_builder.build_system_prompt(request, scope)
    user_message = prompt_builder.build_user_message(request.keyword)

    # 3. 调用 LLM（配置：后台全局 > .env）
    raw_result = await _call_llm_and_parse(system_prompt, user_message)

    return await normalize_result(
        raw_result, request,
        BatchItem(game_type=request.game_type.value, question_count=request.question_count),
        scope, _call_llm_and_parse,
    )


@router.post(
    "/generate/stream",
    summary="生成题目/游戏（流式，实验性）",
    description="流式返回生成结果，降低首字延迟感知。SSE 格式。注意：为保持流式体验，"
                "质检无法像非流式那样事后剔除违禁题，仅在流结束时追加 qc_warning 事件告警。",
)
@metered("stream")
async def generate_questions_stream(request: GenerateRequest, http_request: Request, user: CurrentUser = Depends(require_user)):
    """流式生成题目"""
    # 1. 题型-年级适配校验（与非流式对齐）
    from app.services.prompt_builder import MIN_GRADE_FOR_TYPE, _grade_num
    g_num = _grade_num(request.grade)
    min_g = MIN_GRADE_FOR_TYPE.get(request.game_type.value, 0)
    if min_g and g_num < min_g:
        raise HTTPException(
            status_code=400,
            detail={"error": f"{request.grade}还没有学过{request.game_type.value}哦"},
        )

    # 2. 知识范围
    scope = await run_sync(knowledge_scope_service.get_scope, request.grade, request.subject)
    if not scope.allowed and not scope.forbidden:
        raise HTTPException(
            status_code=400,
            detail={"error": f"暂不支持 {request.grade} 的 {request.subject} 科目"},
        )

    system_prompt = prompt_builder.build_system_prompt(request, scope)
    user_message = prompt_builder.build_user_message(request.keyword)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    p = await run_sync(_merged_llm_params)

    if not p["api_key"]:
        raise HTTPException(400, detail={"error": "尚未配置模型，请联系管理员"})

    async def event_generator():
        """SSE 事件流（结束时做质检，违禁题无法撤回已流出的内容，只追加告警事件）"""
        buffered = []
        try:
            async for token in llm_client.chat_stream(
                messages, base_url=p["base_url"], model=p["model"],
                api_key=p["api_key"], timeout=p["timeout"],
            ):
                buffered.append(token)
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            # 流结束：解析并质检，违禁题只告警（流式无法事后剔除）
            try:
                data = _extract_json("".join(buffered))
                if isinstance(data, dict) and isinstance(data.get("questions"), list):
                    from app.services.question_qc import filter_questions
                    _, blocked = filter_questions(data["questions"], context="stream")
                    if blocked:
                        logger.warning(f"流式生成质检拦截 {len(blocked)} 道违禁题（仅告警）")
                        yield f"data: {json.dumps({'qc_warning': f'检测到 {len(blocked)} 道题目不符合该年级要求，建议重新生成'}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'qc_warning': '模型结果结构不完整，请人工核对'}, ensure_ascii=False)}\n\n"
                if request.game_type.value == "reading" and not data.get("passage"):
                    yield f"data: {json.dumps({'qc_warning': '阅读正文缺失'}, ensure_ascii=False)}\n\n"
            except (json.JSONDecodeError, ValueError, TypeError):
                yield f"data: {json.dumps({'qc_warning': '模型结果无法解析，请人工核对'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except (httpx.HTTPError, json.JSONDecodeError, RuntimeError, ValueError) as e:
            # 不向客户端泄漏内部异常细节（可能含内网 URL/密钥提示），详情留日志
            logger.exception("流式生成失败: %s", type(e).__name__)
            yield f"data: {json.dumps({'error': '生成失败，请重试；若持续失败请联系管理员'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── 知识范围查询 ───

@router.get(
    "/scope",
    response_model=KnowledgeScope,
    summary="查询知识范围",
    description="获取指定年级和科目的允许/禁止知识点范围",
)
def get_knowledge_scope(grade: str, subject: str, user: CurrentUser = Depends(require_user)):
    """获取知识范围"""
    return knowledge_scope_service.get_scope(grade, subject)


@router.get(
    "/scope/available",
    summary="获取可用年级/科目列表",
    description="以后台字典的显式关联（site_dict_links）为唯一数据源，返回每个已关联年级下的可见科目",
)
def get_available_scopes(user: CurrentUser = Depends(require_user)):
    """可用年级/科目：字典决定展示什么，年级-科目关联决定组合（后台可编辑）"""
    from app.db import db

    with db() as conn:
        rows = conn.execute(
            "SELECT id, kind, value FROM site_dictionary WHERE is_visible = 1 ORDER BY kind, sort_order"
        ).fetchall()
        links = conn.execute("SELECT parent_id, child_id FROM site_dict_links").fetchall()
    grades = [row for row in rows if row["kind"] == "grade"]
    _subject_value_by_id = {row["id"]: row["value"] for row in rows if row["kind"] == "subject"}
    linked_by_grade: dict[str, set[str]] = {}
    for row in links:
        linked_by_grade.setdefault(row["parent_id"], set()).add(row["child_id"])
    result = {}
    for grade in grades:
        subject_ids = linked_by_grade.get(grade["id"], set())
        pairs = [row["value"] for row in rows if row["kind"] == "subject" and row["id"] in subject_ids]
        if pairs:
            result[grade["value"]] = pairs
    return {"available": result}


# ─── 超纲校验 ───

@router.post(
    "/validate",
    response_model=ValidateResult,
    summary="超纲校验",
    description="校验指定题目内容是否超出年级知识范围",
)
@metered("validate")
async def validate_oob(request: ValidateRequest, http_request: Request, user: CurrentUser = Depends(require_user)):
    """校验题目是否超纲"""
    scope = await run_sync(knowledge_scope_service.get_scope, request.grade, request.subject)

    system_prompt = (
        f"你是一位教育内容审查专家。请判断以下题目是否超出了{request.grade}学生的知识范围。\n\n"
        f"【该年级允许的知识范围】\n{'、'.join(scope.allowed)}\n\n"
        f"【该年级严禁的知识点（超纲）】\n{'、'.join(scope.forbidden)}\n\n"
        "请分析题目内容，输出 JSON：\n"
        '{"is_oob": true/false, "oob_points": ["超纲知识点1"], "suggestion": "修改建议"}\n\n'
        "只输出 JSON，不要额外文字。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请分析以下题目：\n{request.question_content}"},
    ]

    try:
        p = await run_sync(_merged_llm_params)
        if not p["api_key"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "尚未配置模型",
                    "detail": "模型服务由管理员统一配置，请联系管理员在后台「模型配置」中填写接口地址和密钥",
                },
            )
        raw = await llm_client.chat(
            messages, base_url=p["base_url"], model=p["model"],
            api_key=p["api_key"], timeout=p["timeout"],
        )
        data = _extract_json(raw)
        return ValidateResult(**data)
    except HTTPException:
        raise
    except (RuntimeError, ValueError, TypeError, json.JSONDecodeError) as e:
        logger.exception("超纲校验失败: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail={"error": "校验请求失败", "detail": "校验链路异常，请重试；若持续失败请联系管理员"}) from e


# ─── 反馈收集 ───

@router.post(
    "/feedback",
    summary="用户反馈",
    description="收集用户对题目超纲等问题的反馈",
)
def submit_feedback(request: FeedbackRequest, user: CurrentUser = Depends(require_user)):
    """接收用户反馈并落库（后台可查看，重启不丢）"""
    from app.db import db

    if not allow(f"feedback:{user.id}", 20, 3600):
        raise HTTPException(status_code=429, detail={"error": "反馈提交过于频繁，请稍后再试"})

    with db() as conn:
        conn.execute(
            "INSERT INTO feedbacks (user_id, username, game_id, is_oob, comment) VALUES (?, ?, ?, ?, ?)",
            (user.id, user.username, request.game_id, int(request.is_oob), request.comment),
        )
    logger.info(
        f"Feedback saved - user: {user.username}, game_id: {request.game_id}, "
        f"is_oob: {request.is_oob}, comment: {request.comment}"
    )
    return {"status": "ok", "message": "反馈已记录，感谢您的帮助！"}

