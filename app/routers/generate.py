"""生成路由 —— 题目/游戏生成 API 端点"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
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
from app.services import app_config
from app.services.user_store import CurrentUser
from app.config import get_settings
from app.deps import require_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["生成"])
settings = get_settings()


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
        return json.loads(text)
    except json.JSONDecodeError:
        # JSON 内部有杂质（如 "Extra data"）：用 JSONDecoder 逐段解析取第一个完整对象
        try:
            obj, _ = json.JSONDecoder().raw_decode(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
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
                    return json.loads(text[: i + 1])
        raise


def _merged_llm_params(base_url: str = None, model: str = None, api_key: str = None) -> dict:
    """合并 LLM 调用参数，优先级：请求显式传入 > 管理员在后台配置的全局模型 > .env 兜底。

    模型配置已收归后台管理（/admin 的「模型配置」），全体用户共用一份，密钥加密存于服务端。
    """
    g = app_config.get_llm(with_key=True)
    return {
        "base_url": base_url or g["baseUrl"] or settings.llm_base_url,
        "model": model or g["model"] or settings.llm_model,
        "api_key": api_key or g["api_key"] or settings.llm_api_key,
        "timeout": g["timeout"] or 60,
    }


async def _call_llm_and_parse(
    system_prompt: str, user_message: str,
    base_url: str = None, model: str = None, api_key: str = None,
) -> dict:
    """调用 LLM 并解析返回的 JSON。配置合并优先级：请求显式 > 后台全局配置 > .env 兜底。"""
    p = _merged_llm_params(base_url, model, api_key)
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
    except httpx.TransportError as e:
        logger.error(f"LLM 服务无法连接: {e}")
        raise HTTPException(
            status_code=502,
            detail={"error": "无法连接模型服务", "detail": f"{e}（请管理员检查后台「模型配置」的接口地址）"},
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.exception(f"LLM 调用未知错误")
        raise HTTPException(status_code=500, detail={"error": "内部错误", "detail": str(e)})


def _enrich_result(raw: dict, request: GenerateRequest) -> GameResult:
    """填充 GameResult 中服务端已知的字段"""
    raw.setdefault("game_type", request.game_type.value)
    raw.setdefault("topic", request.keyword)
    raw.setdefault("difficulty", request.difficulty.value)
    raw.setdefault("total_score", 100)
    raw.setdefault("pass_score", 60)

    raw["grade"] = request.grade.value
    raw["subject"] = request.subject.value

    return GameResult(**raw)


# ─── API 端点 ───

@router.post(
    "/generate-batch",
    response_model=BatchGenerateResponse,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="批量生成整张试卷（一次 LLM 调用出多个题型）",
    description="接收多个题型任务，一次 LLM 调用生成整张试卷的所有大题，避免限流。",
)
async def generate_batch(request: BatchGenerateRequest, user: CurrentUser = Depends(require_user)):
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

    # 4. 调用 LLM（一次，配置合并：请求 > 后台全局 > .env）
    try:
        raw = await _call_llm_and_parse(
            system_prompt, user_message,
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
            # 题型质检：源头已在 prompt 卡死；万一漏出（模型偶发违规），
            # 被拦截的题不删除卷子也不悄悄缺数——逐道单独重生成补齐
            from app.services.question_qc import filter_questions
            kept, blocked = filter_questions(
                sec_raw.get("questions") or [], context=f"{request.grade.value}/{it.game_type}"
            )
            if blocked:
                logger.warning(
                    f"题型质检拦截 {len(blocked)} 道违禁题（{it.game_type}），正在单独补生成同数量合规题"
                )
                for _ in range(len(blocked)):
                    try:
                        retry_prompt = prompt_builder.build_system_prompt(request, scope)
                        retry_msg = (
                            f"请围绕知识点\"{request.keyword}\"出 1 道{it.game_type}题型的新题。"
                            "注意：禁止同数连加 3 项及以上、禁止加法转乘法等式，题干一行以内。"
                            "直接返回 JSON。"
                        )
                        patch = await _call_llm_and_parse(retry_prompt, retry_msg,
                            base_url=request.llm_base_url,
                            model=request.llm_model,
                            api_key=request.llm_api_key)
                        patch_qs = patch.get("questions") or [] if isinstance(patch, dict) else []
                        patch_ok, _ = filter_questions(patch_qs, context="补生成")
                        if patch_ok:
                            kept.append(patch_ok[0])
                    except Exception:
                        logger.exception("补生成失败（试卷该大题将缺少此题）")
            sec_raw["questions"] = kept
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
async def generate_questions(request: GenerateRequest, user: CurrentUser = Depends(require_user)):
    """生成题目（非流式）。每次都真实调用 LLM，保证每次生成的试卷都是新的。"""
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

    # 2. 组装 Prompt
    system_prompt = prompt_builder.build_system_prompt(request, scope)
    user_message = prompt_builder.build_user_message(request.keyword)

    # 3. 调用 LLM
    raw_result = await _call_llm_and_parse(system_prompt, user_message,
        base_url=request.llm_base_url,
        model=request.llm_model,
        api_key=request.llm_api_key)

    # 3.5 题型质检：源头 prompt 已卡死；万一漏出，被拦截题单独补生成（不删除不缺数）
    from app.services.question_qc import filter_questions
    if isinstance(raw_result, dict) and isinstance(raw_result.get("questions"), list):
        kept, blocked = filter_questions(
            raw_result["questions"], context=f"single/{request.game_type.value}"
        )
        for _ in range(len(blocked)):
            try:
                patch = await _call_llm_and_parse(system_prompt, user_message,
                    base_url=request.llm_base_url,
                    model=request.llm_model,
                    api_key=request.llm_api_key)
                patch_qs = patch.get("questions") or [] if isinstance(patch, dict) else []
                patch_ok, _ = filter_questions(patch_qs, context="single补生成")
                if patch_ok:
                    kept.append(patch_ok[0])
            except Exception:
                logger.exception("单题补生成失败")
        raw_result["questions"] = kept

    # 4. 组装响应
    return _enrich_result(raw_result, request)


@router.post(
    "/generate/stream",
    summary="生成题目/游戏（流式）",
    description="流式返回生成结果，降低首字延迟感知。SSE 格式。",
)
async def generate_questions_stream(request: GenerateRequest, user: CurrentUser = Depends(require_user)):
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
    p = _merged_llm_params(request.llm_base_url, request.llm_model, request.llm_api_key)

    async def event_generator():
        """SSE 事件流"""
        try:
            async for token in llm_client.chat_stream(
                messages, base_url=p["base_url"], model=p["model"],
                api_key=p["api_key"], timeout=p["timeout"],
            ):
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
async def get_knowledge_scope(grade: str, subject: str, user: CurrentUser = Depends(require_user)):
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
async def get_available_scopes(user: CurrentUser = Depends(require_user)):
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
async def validate_oob(request: ValidateRequest, user: CurrentUser = Depends(require_user)):
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
        p = _merged_llm_params()
        raw = await llm_client.chat(
            messages, base_url=p["base_url"], model=p["model"],
            api_key=p["api_key"], timeout=p["timeout"],
        )
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
async def submit_feedback(request: FeedbackRequest, user: CurrentUser = Depends(require_user)):
    """接收用户反馈"""
    logger.info(
        f"Feedback received - user: {user.username}, game_id: {request.game_id}, "
        f"is_oob: {request.is_oob}, comment: {request.comment}"
    )
    return {"status": "ok", "message": "反馈已记录，感谢您的帮助！"}

