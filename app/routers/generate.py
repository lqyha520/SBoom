"""生成路由 —— 题目/游戏生成 API 端点"""

import asyncio
import json
import logging
from functools import partial

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.blocking import run_sync
from app.config import get_settings
from app.deps import require_user
from app.library_deps import no_store
from app.metrics import generation_stage
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
from app.models.generate_api_responses import (
    GenerateGetAvailableScopesResponse,
    GenerateSubmitFeedbackResponse,
)
from app.models.responses import GenerationPolicyResponse
from app.services.generation_control import metered
from app.services.generation_policy import QUALITY_REVIEW_TIMEOUT, load_policy, runtime_config
from app.services.generation_results import completed_sections, match_sections, normalize_result
from app.services.knowledge_scope import knowledge_scope_service
from app.services.llm_client import OutputTruncated, llm_client
from app.services.model_json import ModelFormatError
from app.services.model_json import extract_json as _extract_json
from app.services.prompt_builder import prompt_builder
from app.services.provider_failover import run_with_failover, stream_with_health
from app.services.question_review import previous_question_keys, review_results
from app.services.rate_limit import allow
from app.services.review_refill import refill_reviewed
from app.services.user_store import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["生成"])
settings = get_settings()


def _format_failure(error: Exception, text: str, expected_key: str | None, candidate: dict) -> HTTPException:
    reason = error.reason if isinstance(error, ModelFormatError) else "invalid_json"
    logger.warning("模型题目数据解析失败", extra={
        "format_reason": reason, "expected_container": expected_key, "response_chars": len(text),
        "json_line": error.line if isinstance(error, ModelFormatError) else None,
        "json_column": error.column if isinstance(error, ModelFormatError) else None,
        "candidate_id": candidate.get("id"),
    })
    messages = {
        "no_json": "模型未返回可识别的题目数据",
        "invalid_json": "模型返回的题目数据格式有误",
        "incomplete_json": "模型返回的题目数据未完整结束，请减少单次题量后重新生成",
        "missing_container": "模型返回的内容缺少本次任务所需的数据字段",
        "container_type": "模型返回的数据字段类型不符合要求",
        "invalid_root": "模型返回的数据结构不符合要求",
        "error_object": "模型返回了错误信息，未生成有效题目",
        "duplicate_key": "模型返回的数据字段重复，无法可靠解析",
        "ambiguous_json": "模型返回了多份结果，无法确定有效内容",
        "too_deep": "模型返回的数据嵌套过深，无法解析",
    }
    return HTTPException(502, detail={
        "code": "generation_invalid_format", "reason": reason,
        "error": messages.get(reason, messages["invalid_json"]),
        "detail": "查询原请求不会再次调用模型；重新生成会发起新的模型调用。若持续出现，请联系管理员查看解析日志。",
    })


def _merged_llm_params() -> dict:
    """合并 LLM 调用参数，来源：管理员在后台配置的全局模型 > .env 兜底。

    模型配置收归后台管理（/admin 的「模型配置」），全体用户共用，密钥加密存于服务端；
    客户端不可指定接口地址/密钥（防 SSRF 与越权绕过）。
    """
    g = runtime_config("text")
    if "models" in g:
        return {"models": [
            {"base_url": profile["baseUrl"], "model": profile["model"], "api_key": profile["api_key"],
             "timeout": profile["timeout"], "max_tokens": profile["maxTokens"],
             "sampling_mode": profile.get("samplingMode", "configured"),
             "token_parameter": profile.get("tokenParameter", "max_tokens"),
             "thinking_mode": profile.get("thinkingMode", "default"),
             "id": profile["id"], "_health_kind": "text", "_revision": g["revision"]}
            for profile in g["models"] if profile["enabled"]
        ]}
    t = float(g["timeout"] or 0)
    return {
        "base_url": g["baseUrl"] or settings.llm_base_url,
        "model": g["model"] or settings.llm_model,
        "api_key": g["api_key"] or settings.llm_api_key,
        "timeout": t or 120.0,
        "max_tokens": int(g.get("maxTokens") or settings.llm_max_tokens),
        "sampling_mode": g.get("samplingMode", "configured"),
        "token_parameter": g.get("tokenParameter", "max_tokens"),
        "thinking_mode": g.get("thinkingMode", "default"),
        "id": "legacy", "_health_kind": "text", "_revision": g["revision"],
    }


async def _call_llm_and_parse(system_prompt: str, user_message: str, question_count: int = 30,
                            *, temperature: float | None = None, expected_key: str | None = None,
                            time_budget: float | None = None) -> dict:
    """调用 LLM 并解析返回的 JSON。配置来源：后台全局配置 > .env 兜底。"""
    p = await run_sync(_merged_llm_params)
    candidates = p.get("models", [p])
    if not candidates or any(not candidate["api_key"] for candidate in candidates):
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

    async def invoke(candidate):
        # 多候选复核为后备项预留时间；仍服从管理员配置的更短超时。
        timeout = candidate["timeout"]
        if time_budget is not None:
            timeout = min(timeout, time_budget / min(len(candidates), 2))
        async with asyncio.timeout(timeout):
            raw_response = ''
            async def call(payload, *, thinking_mode=None):
                nonlocal raw_response
                raw_response = await llm_client.chat(
                    payload, base_url=candidate["base_url"], model=candidate["model"],
                    api_key=candidate["api_key"], timeout=timeout,
                    # 单模型没有备用候选，仅对请求尚未发出的连接错误重连一次；
                    # llm_client 不重试读写超时，外层原有总时限仍覆盖重连与等待。
                    max_tokens=candidate["max_tokens"], max_attempts=2 if len(candidates) == 1 else 1,
                    temperature=temperature,
                    sampling_mode=candidate.get("sampling_mode", "configured"),
                    token_parameter=candidate.get("token_parameter", "max_tokens"),
                    thinking_mode=thinking_mode or candidate.get("thinking_mode", "default"),
                )
                return raw_response
            try:
                # 只校验任务容器，题目仍交给后续逐题校验，保留部分有效内容。
                from app.services.generation_format import parse_response
                # 已验证 Qwen3 的关闭思考协议；仅出题空正文恢复使用，独立复核保留原设置。
                can_recover = (expected_key in ('sections', 'questions')
                               and candidate.get('thinking_mode', 'default') == 'default'
                               and candidate['model'].lower().rsplit('/', 1)[-1].startswith('qwen3'))
                return await parse_response(call, messages, expected_key,
                                            empty_reasoning_call=partial(call, thinking_mode='disabled') if can_recover else None)
            except (ValueError, TypeError, RecursionError) as exc:
                raise _format_failure(exc, raw_response, expected_key, candidate) from exc

    try:
        async with asyncio.timeout(time_budget):
            return await run_with_failover(candidates, invoke)
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        logger.error("模型 API 错误: HTTP %s", e.response.status_code)
        raise HTTPException(
            status_code=502,
            detail={"error": f"模型服务请求失败 ({e.response.status_code})", "detail": "已尝试全部可用候选，请先查询原请求状态"},
        ) from e
    except httpx.PoolTimeout as e:
        raise HTTPException(429, detail={"error": "模型连接池繁忙，请稍后重试"}) from e
    except (httpx.TimeoutException, TimeoutError) as e:
        logger.error("LLM 响应超时: %s", type(e).__name__)
        raise HTTPException(
            status_code=504,
            detail={
                "error": "生成超时",
                "detail": "模型响应未在时限内完成，上游可能已处理并计费。请先查询原请求状态，重新生成会发起新的模型调用。",
            },
        ) from e
    except httpx.DecodingError as e:
        logger.error("模型响应解压失败: %s", type(e).__name__)
        raise HTTPException(
            status_code=502,
            detail={"error": "模型返回的数据无法解压；请查询原请求状态",
                    "code": "provider_decoding_error"},
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

def _require_complete(sections: list[GameResult]) -> None:
    missing = sum(section.missing_count for section in sections)
    if missing:
        raise HTTPException(422, detail={
            "code": "generation_incomplete",
            "error": f"生成未完成，缺少 {missing} 道题；有效题目已保留，可手动补齐",
            "partial_sections": [section.model_dump(mode="json") for section in sections],
        })


async def _call_quality_review(system_prompt: str, user_message: str, question_count: int) -> dict:
    # 每批解析与复核仍由同一计量、限流和 token 预算约束，不循环重出。
    return await _call_llm_and_parse(system_prompt, user_message, question_count, temperature=0.1,
                                     expected_key="reviews", time_budget=QUALITY_REVIEW_TIMEOUT)

@router.get("/generation/options", response_model=GenerationPolicyResponse, summary="读取由后台模型配置计算的任务等待时限", dependencies=[Depends(no_store)])
def generation_options(kind: str = "text", user: CurrentUser = Depends(require_user)):
    if kind not in ("text", "image"):
        raise HTTPException(422, detail={"error": "不支持的模型类型"})
    return load_policy(kind).public()


class RetryAnalysisRequest(BaseModel):
    source_request_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/retry-analysis", response_model=BatchGenerateResponse, dependencies=[Depends(no_store)],
             summary="仅补全原请求未完成的解析与复核")
@metered("analysis")
async def retry_analysis(request: RetryAnalysisRequest, http_request: Request, user: CurrentUser = Depends(require_user)):
    from app.services.generation_control import request_status
    source = await run_sync(request_status, user.id, request.source_request_id)
    if source["status"] not in ("succeeded", "failed") or source["cache_expired"]:
        raise HTTPException(409, detail={"error": "原请求尚未结束或已过期，请先查询原请求"})
    if source["kind"] not in ("batch", "single", "analysis"):
        raise HTTPException(400, detail={"error": "该请求不支持补全解析"})
    result = source["result"] or {}
    values = ([result] if "questions" in result else result.get("sections")) or (source["error"] or {}).get("partial_sections", [])
    sections = [GameResult.model_validate(value) for value in values]
    if not sections or sum(len(section.questions) for section in sections) > 30:
        raise HTTPException(400, detail={"error": "原请求没有可补全的题目或题量超限"})
    # 题目与年级只能从当前账号的服务端原结果读取，不能注入他人的试卷或改写题干。
    context = GenerateRequest(grade=sections[0].grade, subject=sections[0].subject, keyword=sections[0].topic,
                              difficulty=sections[0].difficulty)
    await review_results(sections, context, _call_quality_review, generate_analysis=True, only_incomplete=True)
    return BatchGenerateResponse(sections=sections)


@router.post(
    "/generate-batch",
    response_model=BatchGenerateResponse,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="批量生成整张试卷（一次 LLM 调用出多个题型）",
    description="接收多个题型任务，一次 LLM 调用生成整张试卷的所有大题，避免限流。",
)
@metered("batch")
async def generate_batch(request: BatchGenerateRequest, http_request: Request, user: CurrentUser = Depends(require_user)):
    """先生成整卷题目与答案，再分批补解析并独立复核。"""
    if sum(item.question_count for item in request.items) > 30:
        raise HTTPException(422, detail={"code": "generation_batch_too_large", "error": "每次最多生成 30 道题，请拆分请求"})
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

    resolved_items = [item.model_copy(update={"section_id": item.section_id or f"section-{index + 1}"})
                      for index, item in enumerate(request.items)]
    # 所有题型统一由模型出题，本地只做结果校验与整理。
    system_prompt = prompt_builder.build_batch_prompt(
        grade=request.grade,
        subject=request.subject,
        keyword=request.keyword,
        difficulty=request.difficulty.value,
        items=resolved_items,
        scope=scope,
    )
    user_message = prompt_builder.build_batch_user_message(request.keyword)

    # 4. 调用 LLM（一次，配置：后台全局 > .env）
    truncated = None
    try:
        async with generation_stage("generate"):
            raw = await _call_llm_and_parse(system_prompt, user_message, sum(item.question_count for item in resolved_items),
                                            expected_key="sections")
    except OutputTruncated as error:
        truncated = error
        raw = {"sections": completed_sections(error.partial_text)}
    except HTTPException:
        raise
    except (RuntimeError, ValueError, TypeError) as e:
        logger.exception("批量生成失败: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail={"error": "批量生成失败", "detail": "生成链路异常，请重试；若持续失败请联系管理员"}) from e

    matched = match_sections(raw, resolved_items)
    sections = []
    seen = await run_sync(previous_question_keys, user.id, request)
    for item, section in zip(resolved_items, matched, strict=True):
        if truncated:
            # 残片只接受可唯一对应的大题，且不为挽救残片再发付费补题请求。
            if not section or section.get("section_id") != item.section_id or section.get("game_type") != item.game_type:
                continue
            candidate_seen = seen.copy()
            result = await normalize_result(section, request, item, scope, _call_llm_and_parse, allow_repairs=False, seen=candidate_seen)
            if result.missing_count:
                continue
            seen = candidate_seen
        else:
            result = await normalize_result(section, request, item, scope, _call_llm_and_parse, seen=seen)
        sections.append(result)
    if truncated:
        detail = dict(truncated.detail) if isinstance(truncated.detail, dict) else {}
        detail["partial_sections"] = [section.model_dump(mode="json") for section in sections]
        raise HTTPException(truncated.status_code, detail=detail) from truncated
    await review_results(sections, request, _call_quality_review, generate_analysis=True)
    await refill_reviewed(sections, request, scope, _call_llm_and_parse, _call_quality_review)
    _require_complete(sections)
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
    """生成题目（非流式）；原请求重放由计量层处理。"""
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
    item = BatchItem(game_type=request.game_type.value, question_count=request.question_count)
    async with generation_stage("generate"):
        raw_result = await _call_llm_and_parse(system_prompt, user_message, request.question_count, expected_key="questions")

    result = await normalize_result(
        raw_result, request,
        item,
        scope, _call_llm_and_parse,
    )
    await review_results([result], request, _call_quality_review, generate_analysis=True)
    await refill_reviewed([result], request, scope, _call_llm_and_parse, _call_quality_review)
    _require_complete([result])
    return result


@router.post(
    "/generate/stream",
    summary="生成题目/游戏（流式，实验性）",
    description="流式返回生成结果，降低首字延迟感知。SSE 格式。注意：为保持流式体验，"
                "质检无法像非流式那样事后剔除违禁题，仅在流结束时追加 qc_warning 事件告警。",
    response_class=Response, responses={200: {'content': {'text/event-stream': {'schema': {'type': 'string'}}}}},
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

    system_prompt = prompt_builder.build_system_prompt(request, scope, include_analysis=True)
    user_message = prompt_builder.build_user_message(request.keyword)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    p = await run_sync(_merged_llm_params)

    candidates = p.get("models", [p])
    if not candidates or any(not candidate["api_key"] for candidate in candidates):
        raise HTTPException(400, detail={"error": "尚未配置模型，请联系管理员"})

    async def candidate_tokens(candidate):
        async with asyncio.timeout(candidate["timeout"]):
            async for token in llm_client.chat_stream(
                messages, base_url=candidate["base_url"], model=candidate["model"],
                api_key=candidate["api_key"], timeout=candidate["timeout"],
                max_tokens=candidate["max_tokens"],
                sampling_mode=candidate.get("sampling_mode", "configured"),
                token_parameter=candidate.get("token_parameter", "max_tokens"),
                thinking_mode=candidate.get("thinking_mode", "default"),
            ):
                yield token

    async def tokens():
        if len(candidates) == 1:
            async for token in stream_with_health(candidates[0], candidate_tokens):
                yield token
            return

        async def collect(candidate):
            # 多候选先缓存完整一轮，失败残片不下发，避免不同模型的 JSON 拼接。
            async with asyncio.timeout(candidate["timeout"]):
                chunks = [token async for token in candidate_tokens(candidate)]
                try:
                    await run_sync(_extract_json, "".join(chunks), expected_key="questions")
                except (ValueError, TypeError, RecursionError) as exc:
                    raise _format_failure(exc, "".join(chunks), "questions", candidate) from exc
                return chunks

        for token in await run_with_failover(candidates, collect):
            yield token

    async def event_generator():
        """SSE 事件流（结束时做质检，违禁题无法撤回已流出的内容，只追加告警事件）"""
        buffered = []
        try:
            async for token in tokens():
                buffered.append(token)
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            # 流结束：解析并质检，违禁题只告警（流式无法事后剔除）
            try:
                data = await run_sync(_extract_json, "".join(buffered))
                if isinstance(data, dict) and isinstance(data.get("questions"), list):
                    result = await normalize_result(data, request, BatchItem(
                        game_type=request.game_type.value, question_count=request.question_count,
                    ), scope, _call_llm_and_parse, allow_repairs=False)
                    for warning in result.quality_warnings:
                        yield f"data: {json.dumps({'qc_warning': warning}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'qc_warning': '流式结果尚未独立复核，请核对答案、解析与教学范围'}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'qc_warning': '模型结果结构不完整，请人工核对'}, ensure_ascii=False)}\n\n"
                if request.game_type.value == "reading" and not data.get("passage"):
                    yield f"data: {json.dumps({'qc_warning': '阅读正文缺失'}, ensure_ascii=False)}\n\n"
            except (json.JSONDecodeError, ValueError, TypeError):
                yield f"data: {json.dumps({'qc_warning': '模型结果无法解析，请人工核对'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except HTTPException as exc:
            yield f"data: {json.dumps(exc.detail, ensure_ascii=False)}\n\n"
        except (httpx.HTTPError, TimeoutError, json.JSONDecodeError, RuntimeError, ValueError) as e:
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
    description="返回后台启用且已有核实的人教版教材目录的年级科目组合",
 response_model=GenerateGetAvailableScopesResponse, response_model_exclude_unset=True)
def get_available_scopes(user: CurrentUser = Depends(require_user)):
    """可用年级/科目：字典决定展示什么，年级-科目关联决定组合（后台可编辑）"""
    from app.db import db

    with db() as conn:
        rows = conn.execute(
            "SELECT id, kind, value FROM site_dictionary WHERE is_visible = 1 ORDER BY kind, sort_order"
        ).fetchall()
        links = conn.execute("SELECT parent_id, child_id FROM site_dict_links").fetchall()
    grades = [row for row in rows if row["kind"] == "grade"]
    linked_by_grade: dict[str, set[str]] = {}
    for row in links:
        linked_by_grade.setdefault(row["parent_id"], set()).add(row["child_id"])
    result = {}
    for grade in grades:
        subject_ids = linked_by_grade.get(grade["id"], set())
        pairs = [row["value"] for row in rows if row["kind"] == "subject" and row["id"] in subject_ids
                 and knowledge_scope_service.is_supported(grade["value"], row["value"])]
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

    try:
        data = await _call_llm_and_parse(system_prompt, f"请分析以下题目：\n{request.question_content}", 5)
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
 response_model=GenerateSubmitFeedbackResponse, response_model_exclude_unset=True)
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
    logger.info("Feedback saved user_id=%s is_oob=%s", user.id, request.is_oob)
    return {"status": "ok", "message": "反馈已记录，感谢您的帮助！"}

