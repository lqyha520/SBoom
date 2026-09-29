"""Normalize model output against the requested sections, never invented questions."""

import json
import re
from collections import Counter
from collections.abc import Awaitable, Callable

from app.models import BatchItem, GameResult, GameType, GenerateRequest, Question
from app.services.generation_control import reserve_repairs
from app.services.prompt_builder import prompt_builder
from app.services.question_qc import filter_questions


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
    # IDs are server-owned; a malformed model ID must not discard a good question.
    question.pop("id", None)
    return question


def _take_questions(raw, game_type: str, count: int, seen: set, namespace: str) -> tuple[list, int]:
    questions = raw.get("questions", []) if isinstance(raw, dict) else []
    if not isinstance(questions, list):
        return [], 1
    kept: list[dict] = []
    rejected = 0
    for value in questions[:300]:
        if len(kept) >= count:
            break
        question = _normalize_question(value, game_type)
        ok, blocked = filter_questions([question], context=game_type, seen=seen, namespace=namespace)
        rejected += len(blocked)
        kept.extend(ok)
    return kept, rejected


async def normalize_result(
    raw, request, item: BatchItem, scope,
    call_model: Callable[..., Awaitable[dict]],
    seen: set | None = None,
    *, allow_repairs: bool = True,
) -> GameResult:
    seen = seen if seen is not None else set()
    warnings = []
    if not isinstance(raw, dict) or raw.get("game_type", item.game_type) != item.game_type:
        raw = {}
        warnings.append("模型未返回可对应的大题")
    passage = raw.get("passage")
    passage = passage.strip() if isinstance(passage, str) else None
    namespace = passage or ""
    if item.game_type == "reading" and not passage:
        kept: list[dict] = []
        rejected = 0
        warnings.append("阅读正文缺失，未采用无法核对的问题")
    else:
        kept, rejected = _take_questions(raw, item.game_type, item.question_count, seen, namespace)
    if rejected:
        warnings.append(f"剔除 {rejected} 道格式、答案或重复检查未通过的题目")

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
                    fixed, _ = _take_questions(patch, item.game_type, missing, seen, namespace)
                    kept.extend(fixed)
                except Exception:
                    continue
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
