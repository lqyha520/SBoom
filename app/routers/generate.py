"""生成路由 —— 题目/游戏生成 API 端点"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import httpx

from app.models import (
    GenerateRequest,
    GameResult,
    ValidateRequest,
    ValidateResult,
    FeedbackRequest,
    ErrorResponse,
    KnowledgeScope,
    BatchGenerateRequest,
    BatchGenerateResponse,
)
from app.services.knowledge_scope import knowledge_scope_service
from app.services.prompt_builder import prompt_builder
from app.services.llm_client import llm_client
from app.cache.question_cache import question_cache
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["生成"])
settings = get_settings()


def _extract_json(text: str) -> dict:
    """从 LLM 返回的文本中提取 JSON，处理可能的 markdown 包裹"""
    text = text.strip()

    # 去掉可能的 ```json ... ``` 包裹
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉首尾 ```
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

    return json.loads(text)


async def _call_llm_and_parse(
    system_prompt: str, user_message: str,
    base_url: str = None, model: str = None, api_key: str = None,
) -> dict:
    """调用 LLM 并解析返回的 JSON"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    try:
        raw_response = await llm_client.chat(messages, base_url=base_url, model=model, api_key=api_key)
        logger.debug(f"LLM raw response: {raw_response[:200]}...")
        return _extract_json(raw_response)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}, raw: {raw_response[:500]}")
        raise HTTPException(
            status_code=502,
            detail={"error": "LLM 返回格式异常，请重试", "detail": str(e)},
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"LLM API 错误: {e.response.status_code} - {e.response.text[:300]}")
        raise HTTPException(
            status_code=502,
            detail={"error": f"LLM 服务请求失败 ({e.response.status_code})", "detail": str(e)},
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.exception(f"LLM 调用未知错误")
        raise HTTPException(status_code=500, detail={"error": "内部错误", "detail": str(e)})


def _enrich_result(raw: dict, request: GenerateRequest, from_cache: bool, cache_key: Optional[str]) -> GameResult:
    """填充 GameResult 中服务端已知的字段"""
    raw.setdefault("game_type", request.game_type.value)
    raw.setdefault("topic", request.keyword)
    raw.setdefault("difficulty", request.difficulty.value)
    raw.setdefault("total_score", 100)
    raw.setdefault("pass_score", 60)

    raw["grade"] = request.grade.value
    raw["subject"] = request.subject.value
    raw["from_cache"] = from_cache
    raw["cache_key"] = cache_key

    return GameResult(**raw)


# ─── API 端点 ───

@router.post(
    "/generate-batch",
    response_model=BatchGenerateResponse,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="批量生成整张试卷（一次 LLM 调用出多个题型）",
    description="接收多个题型任务，一次 LLM 调用生成整张试卷的所有大题，避免限流。",
)
async def generate_batch(request: BatchGenerateRequest):
    """一次 LLM 调用生成整卷的多个题型"""
    # 1. 知识范围
    scope = knowledge_scope_service.get_scope(request.grade, request.subject)
    if not scope.allowed and not scope.forbidden:
        raise HTTPException(
            status_code=400,
            detail={"error": f"暂不支持 {request.grade.value} 的 {request.subject.value} 科目"},
        )

    # 2. 题型-年级适配校验
    from app.services.prompt_builder import MIN_GRADE_FOR_TYPE, _grade_num
    g_num = _grade_num(request.grade.value)
    for it in request.items:
        min_g = MIN_GRADE_FOR_TYPE.get(it.game_type, 0)
        if min_g and g_num < min_g:
            raise HTTPException(
                status_code=400,
                detail={"error": f"{request.grade.value}还没有学过{it.game_type}哦"},
            )

    # 3. 组装批量 Prompt
    system_prompt = prompt_builder.build_batch_prompt(
        grade=request.grade.value,
        subject=request.subject.value,
        keyword=request.keyword,
        difficulty=request.difficulty.value,
        items=request.items,
        scope=scope,
    )
    user_message = prompt_builder.build_batch_user_message(request.keyword)

    # 4. 调用 LLM（一次，使用前端传入的配置）
    try:
        raw = await _call_llm_and_parse(system_prompt, user_message,
            base_url=request.llm_base_url,
            model=request.llm_model,
            api_key=request.llm_api_key)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("批量生成失败")
        raise HTTPException(status_code=502, detail={"error": "批量生成失败", "detail": str(e)})

    # 5. 按顺序映射回 GameResult
    sections_raw = raw.get("sections", []) if isinstance(raw, dict) else []
    sections = []
    for i, it in enumerate(request.items):
        sec_raw = sections_raw[i] if i < len(sections_raw) else {}
        if isinstance(sec_raw, dict):
            sec_raw = dict(sec_raw)
            sec_raw.setdefault("game_type", it.game_type)
            sec_raw.setdefault("topic", request.keyword)
            sec_raw.setdefault("difficulty", request.difficulty.value)
            sec_raw["grade"] = request.grade.value
            sec_raw["subject"] = request.subject.value
            sec_raw.setdefault("from_cache", False)
            sec_raw.setdefault("cache_key", None)
            # 兜底修正：LLM 可能漏掉 type 字段，按字段特征自动识别
            for q in (sec_raw.get("questions") or []):
                if not q.get("type"):
                    if "top" in q:
                        q["type"] = "number_split"
                    elif "left_expr" in q:
                        q["type"] = "compare"
                    elif "options" in q:
                        q["type"] = "multiple_choice"
                    else:
                        q["type"] = it.game_type
                # 兜底：口算/填空等题型若 LLM 没给 stem，用 answer 生成默认题干
                if not q.get("stem") and not q.get("top") and not q.get("left_expr"):
                    ans = q.get("answer", "")
                    if ans:
                        q["stem"] = f"____ = {ans}" if "fill_blank" in (q.get("type","") or it.game_type) else f"{ans} = ？"
                    else:
                        q["stem"] = "请作答"
            try:
                sections.append(GameResult(**sec_raw))
            except Exception:
                # 题型数据不合规时给空题兜底，避免整卷失败
                sections.append(GameResult(
                    game_type=it.game_type, topic=request.keyword,
                    difficulty=request.difficulty.value, grade=request.grade.value,
                    subject=request.subject.value, questions=[],
                    total_score=100, pass_score=60,
                ))
        else:
            sections.append(GameResult(
                game_type=it.game_type, topic=request.keyword,
                difficulty=request.difficulty.value, grade=request.grade.value,
                subject=request.subject.value, questions=[],
                total_score=100, pass_score=60,
            ))

    return BatchGenerateResponse(sections=sections)


@router.post(
    "/generate",
    response_model=GameResult,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="生成题目/游戏",
    description="根据年级、科目、知识点关键词和交互类型，生成一套趣味题目。支持缓存。",
)
async def generate_questions(request: GenerateRequest):
    """生成题目（非流式）"""
    # 0. 题型-年级适配校验（低年级拦截超纲计算题型）
    from app.services.prompt_builder import MIN_GRADE_FOR_TYPE, _grade_num
    g_num = _grade_num(request.grade.value)
    min_g = MIN_GRADE_FOR_TYPE.get(request.game_type.value, 0)
    if min_g and g_num < min_g:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{request.grade.value}还没有学过{request.game_type.value}哦",
                "detail": f"该题型建议 {min_g} 年级及以上使用，请换一个题型",
            },
        )

    # 1. 获取知识范围
    scope = knowledge_scope_service.get_scope(request.grade, request.subject)

    if not scope.allowed and not scope.forbidden:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"暂不支持 {request.grade.value} 的 {request.subject.value} 科目",
                "detail": "知识范围库中未定义该年级和科目的内容",
            },
        )

    # 2. 检查缓存
    result_from_cache = None
    cache_key = None
    if request.use_cache and settings.cache_enabled:
        cache_key = question_cache.generate_key(
            grade=request.grade.value,
            subject=request.subject.value,
            keyword=request.keyword,
            game_type=request.game_type.value,
            difficulty=request.difficulty.value,
            count=request.question_count,
        )
        result_from_cache = question_cache.get(cache_key)

    if result_from_cache:
        result_from_cache["from_cache"] = True
        result_from_cache["cache_key"] = cache_key
        return GameResult(**result_from_cache)

    # 3. 组装 Prompt
    system_prompt = prompt_builder.build_system_prompt(request, scope)
    user_message = prompt_builder.build_user_message(request.keyword)

    # 4. 调用 LLM
    raw_result = await _call_llm_and_parse(system_prompt, user_message,
        base_url=request.llm_base_url,
        model=request.llm_model,
        api_key=request.llm_api_key)

    # 5. 写入缓存
    if cache_key and settings.cache_enabled:
        question_cache.set(cache_key, raw_result)

    # 6. 组装响应
    return _enrich_result(raw_result, request, from_cache=False, cache_key=cache_key)


@router.post(
    "/generate/stream",
    summary="生成题目/游戏（流式）",
    description="流式返回生成结果，降低首字延迟感知。SSE 格式。",
)
async def generate_questions_stream(request: GenerateRequest):
    """流式生成题目"""
    scope = knowledge_scope_service.get_scope(request.grade, request.subject)
    if not scope.allowed and not scope.forbidden:
        raise HTTPException(
            status_code=400,
            detail={"error": f"暂不支持 {request.grade.value} 的 {request.subject.value} 科目"},
        )

    system_prompt = prompt_builder.build_system_prompt(request, scope)
    user_message = prompt_builder.build_user_message(request.keyword)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    async def event_generator():
        """SSE 事件流"""
        try:
            async for token in llm_client.chat_stream(messages):
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

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
async def get_knowledge_scope(grade: str, subject: str):
    """获取知识范围"""
    from app.models import Grade, Subject

    try:
        grade_enum = Grade(grade)
        subject_enum = Subject(subject)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    scope = knowledge_scope_service.get_scope(grade_enum, subject_enum)
    return scope


@router.get(
    "/scope/available",
    summary="获取可用年级/科目列表",
    description="返回系统已定义的年级列表和每个年级下的科目",
)
async def get_available_scopes():
    """获取所有可用年级和科目"""
    grades = knowledge_scope_service.get_available_grades()
    result = {}
    for g in grades:
        result[g] = knowledge_scope_service.get_available_subjects(g)
    return {"available": result}


# ─── 超纲校验 ───

@router.post(
    "/validate",
    response_model=ValidateResult,
    summary="超纲校验",
    description="校验指定题目内容是否超出年级知识范围",
)
async def validate_oob(request: ValidateRequest):
    """校验题目是否超纲"""
    scope = knowledge_scope_service.get_scope(request.grade, request.subject)

    system_prompt = (
        f"你是一位教育内容审查专家。请判断以下题目是否超出了{request.grade.value}学生的知识范围。\n\n"
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
        raw = await llm_client.chat(messages)
        data = _extract_json(raw)
        return ValidateResult(**data)
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "校验请求失败", "detail": str(e)})


# ─── 反馈收集 ───

@router.post(
    "/feedback",
    summary="用户反馈",
    description="收集用户对题目超纲等问题的反馈",
)
async def submit_feedback(request: FeedbackRequest):
    """接收用户反馈"""
    logger.info(
        f"Feedback received - game_id: {request.game_id}, "
        f"is_oob: {request.is_oob}, comment: {request.comment}"
    )
    return {"status": "ok", "message": "反馈已记录，感谢您的帮助！"}


# ─── LLM 连接测试 ───

@router.post(
    "/test-llm",
    summary="测试 LLM 连接",
    description="发送一条短消息给 LLM，验证配置是否有效",
)
async def test_llm():
    """用极简消息测试 LLM 能否连通"""
    try:
        resp = await llm_client.chat(
            [{"role": "user", "content": "回复：ok"}],
            max_tokens=5,
        )
        return {"status": "ok", "reply": resp.strip()}
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "LLM 连接失败", "detail": str(e)})
