"""Normalize model output against the requested sections, never invented questions."""

import json
import logging
import re
from collections import Counter
from collections.abc import Awaitable, Callable

from app.models import BatchItem, GameResult, GameType, GenerateRequest, Question
from app.services.generation_control import reserve_repairs
from app.services.prompt_builder import prompt_builder
from app.services.question_qc import arithmetic_value, question_issue

logger = logging.getLogger(__name__)


def completed_sections(text: str) -> list[dict]:
    """只解码顶层 sections 数组中已闭合的对象，不补括号或猜测残缺内容。"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if "<think>" in text:
        text = text.split("<think>")[0]
    start = text.find("{")
    if start < 0:
        return []
    decoder = json.JSONDecoder()
    tail = text[start + 1:].lstrip()
    try:
        while tail:
            key, end = decoder.raw_decode(tail)
            tail = tail[end:].lstrip()
            if not isinstance(key, str) or not tail.startswith(":"):
                return []
            tail = tail[1:].lstrip()
            if key == "sections":
                if not tail.startswith("["):
                    return []
                tail = tail[1:].lstrip()
                sections: list[dict] = []
                while tail and not tail.startswith("]"):
                    try:
                        section, end = decoder.raw_decode(tail)
                    except json.JSONDecodeError:
                        break
                    if not isinstance(section, dict):
                        break
                    sections.append(section)
                    tail = tail[end:].lstrip()
                    if not tail.startswith(","):
                        break
                    tail = tail[1:].lstrip()
                return sections
            _, end = decoder.raw_decode(tail)
            tail = tail[end:].lstrip()
            if not tail.startswith(","):
                break
            tail = tail[1:].lstrip()
    except json.JSONDecodeError:
        pass
    return []


def match_sections(raw, items: list[BatchItem]) -> list[dict | None]:
    sections = raw.get("sections", []) if isinstance(raw, dict) else []
    if not isinstance(sections, list):
        sections = []
    candidates = [section for section in sections if isinstance(section, dict)]
    ids = Counter(str(section.get("section_id")) for section in candidates)
    requested_types = Counter(item.game_type for item in items)
    matched = []
    for index, item in enumerate(items):
        section_id = item.section_id or f"section-{index + 1}"
        exact = [section for section in candidates if section.get("section_id") == section_id]
        section = exact[0] if exact and ids[section_id] == 1 else None
        if not exact and requested_types[item.game_type] == 1:
            # Legacy responses without IDs are only safe when the type is unique.
            legacy = [section for section in candidates
                      if not section.get("section_id") and section.get("game_type") == item.game_type]
            if len(legacy) == 1:
                section = legacy[0]
        matched.append(section)
    return matched


def _normalize_question(value, game_type: str) -> dict | None:
    if not isinstance(value, dict):
        return None
    question = dict(value)
    expected = "multiple_choice" if game_type in ("quiz", "challenge") else game_type
    if game_type == "reading":
        expected = "multiple_choice" if question.get("options") else "reading"
    kind = question.get("type") or expected
    if kind in ("quiz", "challenge"):
        kind = "multiple_choice"
    allowed = {expected}
    if game_type == "reading":
        allowed = {"reading", "multiple_choice", "fill_blank", "word_problem", "true_false"}
    if kind not in allowed:
        return None
    question["type"] = kind
    # 模型偶尔返回不带等号的纯算式；统一成卷面需要的“算式 =”格式。
    if game_type in ("oral_math", "vertical_calc", "recursive_calc", "smart_calc"):
        stem = question.get("stem")
        if isinstance(stem, str) and "=" not in stem and arithmetic_value(stem) is not None:
            question["stem"] = stem.strip() + " ="
    # IDs are server-owned; a malformed model ID must not discard a good question.
    question.pop("id", None)
    return question


def _take_questions(
    raw, game_type: str, count: int, *, compact_fill_blank: bool = False,
    allow_fill_blank_steps: bool = False,
) -> tuple[list, Counter[str]]:
    questions = raw.get("questions", []) if isinstance(raw, dict) else []
    if not isinstance(questions, list):
        return [], Counter({"题目列表格式不正确": 1})
    kept: list[dict] = []
    rejected: Counter[str] = Counter()
    for value in questions[:300]:
        if len(kept) >= count:
            break
        question = _normalize_question(value, game_type)
        issue = "题型或题目对象不正确" if question is None else question_issue(
            question, compact_fill_blank=compact_fill_blank, allow_fill_blank_steps=allow_fill_blank_steps,
        )
        if issue:
            rejected[issue] += 1
            continue
        assert question is not None
        kept.append(question)
    return kept, rejected


def _rejection_warning(rejected: Counter[str], section_id: str | None, phase: str) -> str:
    details = "；".join(f"{reason} {count} 道" for reason, count in rejected.items())
    logger.info("生成质检 section=%s phase=%s rejected=%s", section_id, phase, dict(rejected))
    return f"{phase}剔除 {sum(rejected.values())} 道题（{details}）"


async def normalize_result(
    raw, request, item: BatchItem, scope,
    call_model: Callable[..., Awaitable[dict]],
    *, allow_repairs: bool = True,
) -> GameResult:
    warnings = []
    if not isinstance(raw, dict) or raw.get("game_type", item.game_type) != item.game_type:
        raw = {}
        warnings.append("模型未返回可对应的大题")
    passage = raw.get("passage")
    passage = passage.strip() if isinstance(passage, str) else None
    compact_fill_blank = item.game_type == "fill_blank" and request.subject == "数学"
    allow_fill_blank_steps = any(marker in request.keyword for marker in ("过程填空", "凑十法"))
    if item.game_type == "reading" and not passage:
        kept: list[dict] = []
        rejected: Counter[str] = Counter()
        warnings.append("阅读正文缺失，未采用无法核对的问题")
    else:
        kept, rejected = _take_questions(
            raw, item.game_type, item.question_count, compact_fill_blank=compact_fill_blank,
            allow_fill_blank_steps=allow_fill_blank_steps,
        )
    if rejected:
        warnings.append(_rejection_warning(rejected, item.section_id, "初次生成"))

    # Reading repairs could introduce questions about a different passage. Keep
    # the original passage and expose missing counts instead of mixing sources.
    missing = item.question_count - len(kept)
    if missing and allow_repairs and item.game_type != "reading":
        try:
            game_type = GameType(item.game_type)
        except ValueError:
            game_type = None
        if game_type is not None:
            single = GenerateRequest(grade=request.grade, subject=request.subject,
                                     keyword=request.keyword, difficulty=request.difficulty,
                                     game_type=game_type, question_count=missing)
            prompt = prompt_builder.build_system_prompt(single, scope)
            # Sequential repairs keep each admitted job at one active provider call.
            for _ in range(reserve_repairs(1)):
                try:
                    patch = await call_model(prompt, prompt_builder.build_user_message(request.keyword), missing)
                    fixed, rejected = _take_questions(
                        patch, item.game_type, missing, compact_fill_blank=compact_fill_blank,
                        allow_fill_blank_steps=allow_fill_blank_steps,
                    )
                    kept.extend(fixed)
                    if rejected:
                        warnings.append(_rejection_warning(rejected, item.section_id, "补题"))
                except Exception as error:
                    logger.warning("模型补题失败 section=%s error_type=%s", item.section_id, type(error).__name__)
                    warnings.append("模型补题失败，已保留有效题目，未继续重发")
    missing = item.question_count - len(kept)
    if missing:
        warnings.append(f"请求 {item.question_count} 道，保留 {len(kept)} 道，缺少 {missing} 道；补题有次数上限")
    return GameResult(
        game_type=item.game_type, section_id=item.section_id,
        topic=request.keyword, difficulty=request.difficulty.value,
        grade=request.grade, subject=request.subject,
        passage=passage, questions=[Question(**{**value, "id": i + 1}) for i, value in enumerate(kept)],
        missing_count=missing, quality_warnings=warnings,
    )
