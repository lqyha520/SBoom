"""提取模型结果，只兼容不改变内容的格式瑕疵，不补全截断数据。"""

import json
import logging
from collections.abc import Iterator

logger = logging.getLogger(__name__)


class ModelFormatError(ValueError):
    """错误信息只含固定分类和位置，不包含模型正文。"""

    def __init__(self, reason: str, *, line: int | None = None, column: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.line = line
        self.column = column


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ModelFormatError("duplicate_key")
        result[key] = value
    return result


def _reject_constant(_value: str):
    raise ModelFormatError("invalid_json")


def _syntax_only(text: str) -> str:
    """只转义字符串内的换行/制表符、移除值后多余的末尾逗号。"""
    out: list[str] = []
    quoted = escaped = False
    previous = ""
    for index, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            elif char in "\n\r\t":
                char = json.dumps(char)[1:-1]
        elif char == '"':
            quoted = True
        elif char == "," and previous and previous not in "[{,:":
            following = index + 1
            while following < len(text) and text[following].isspace():
                following += 1
            if following < len(text) and text[following] in "]}":
                continue
        out.append(char)
        if not char.isspace():
            previous = char
    return "".join(out)


def _decode(text: str) -> tuple[object, bool]:
    try:
        return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant), False
    except json.JSONDecodeError as original:
        normalized = _syntax_only(text)
        if normalized != text:
            try:
                return json.loads(normalized, object_pairs_hook=_unique_object, parse_constant=_reject_constant), True
            except json.JSONDecodeError:
                pass
            except RecursionError:
                raise ModelFormatError("too_deep") from None
        raise ModelFormatError("invalid_json", line=original.lineno, column=original.colno) from None
    except RecursionError:
        raise ModelFormatError("too_deep") from None


def _containers(text: str) -> Iterator[str]:
    """按层级扫描完整容器，不把题目内嵌对象误当成顶层结果。"""
    position = count = 0
    lower = text.lower()
    while position < len(text):
        if lower.startswith("<think>", position):
            end = lower.find("</think>", position + 7)
            if end < 0:
                raise ModelFormatError("incomplete_json")
            position = end + 8
            continue
        if text[position] not in "[{":
            position += 1
            continue
        start = position
        stack: list[str] = []
        quoted = escaped = False
        while position < len(text):
            char = text[position]
            position += 1
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
                continue
            if char == '"':
                quoted = True
            elif char in "[{":
                stack.append(char)
                if len(stack) > 128:
                    raise ModelFormatError("too_deep")
            elif char in "]}":
                if not stack or stack.pop() != ("[" if char == "]" else "{"):
                    raise ModelFormatError("invalid_json")
                if not stack:
                    count += 1
                    if count > 16:
                        raise ModelFormatError("ambiguous_json")
                    yield text[start:position]
                    break
        else:
            raise ModelFormatError("incomplete_json")


def _result(value: object, expected_key: str | None) -> dict:
    if not isinstance(value, dict):
        raise ModelFormatError("invalid_root")
    if "error" in value:
        raise ModelFormatError("error_object")
    if expected_key is not None:
        if expected_key not in value:
            raise ModelFormatError("missing_container")
        if not isinstance(value[expected_key], list):
            raise ModelFormatError("container_type")
    return value


def extract_json(text: str, *, expected_key: str | None = None) -> dict:
    """优先原样解析；有包裹时只接受唯一、完整且符合任务容器的对象。"""
    text = text.strip().lstrip("\ufeff")
    try:
        value, repaired = _decode(text)
    except ModelFormatError as error:
        if error.reason != "invalid_json":
            raise
    else:
        result = _result(value, expected_key)
        if repaired:
            logger.info("模型 JSON 已兼容换行或末尾逗号", extra={"response_chars": len(text)})
        return result

    matches: list[tuple[dict, bool]] = []
    failure = ModelFormatError("no_json")
    for fragment in _containers(text):
        try:
            value, repaired = _decode(fragment)
            matches.append((_result(value, expected_key), repaired))
        except ModelFormatError as error:
            failure = error
    if len(matches) > 1:
        raise ModelFormatError("ambiguous_json")
    if not matches:
        raise failure
    result, repaired = matches[0]
    if repaired:
        logger.info("模型 JSON 已兼容换行或末尾逗号", extra={"response_chars": len(text)})
    return result
