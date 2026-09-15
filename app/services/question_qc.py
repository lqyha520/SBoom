"""题型质检 —— 对 LLM 生成的题目做内容级校验，不合格的剔除或重生成

结构、选项、可确定计算答案及重复内容检查。
不替代教师对语义、知识范围与开放题答案的审核。
"""

import logging
import re
import ast
import json
import operator
from fractions import Fraction
from typing import Optional
from app.models import Question
from pydantic import ValidationError

logger = logging.getLogger(__name__)

# 「同数连加」核心模式：a + a（两项即成，为 3 项检测打基础）
# 「加法转乘法」题：4 + 4 + 4 + 4 + 4 = 5 × ____（同数连加 ≥2 项 + 乘号）
_CHAIN_ADD_TO_MUL = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*\+\s*\1(?![\d.])(?:\s*\+\s*\1(?![\d.]))*\s*=\s*\d*\s*[×x*]"
)
# 同数连加 ≥ 3 项（无论是否配乘法）——乘法意义题，题目必然冗长
_SAME_NUM_CHAIN3 = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*\+\s*\1(?![\d.])\s*\+\s*\1(?![\d.])"
)


def reject_reason(stem: Optional[str]) -> Optional[str]:
    """检查题干，返回拒绝原因；None = 合格。

    只检查算式类特征，纯文字题干（应用题等）不受影响。
    """
    if not stem or not isinstance(stem, str):
        return None
    s = stem.strip()
    if not s:
        return None

    # 1. 加法转乘法题：4+4+4+4+4 = 5 × ____（同数连加配乘号，两项以上即拦）
    if _CHAIN_ADD_TO_MUL.search(s):
        return "同数连加配乘法（加法转乘法题）"

    # 2. 同数连加 3 项及以上（不配乘法也算——乘法意义题型，题目必然冗长）
    if _SAME_NUM_CHAIN3.search(s):
        return "同数连加 3 项及以上"

    return None


def arithmetic_value(expression: str) -> Optional[Fraction]:
    """Evaluate a bounded arithmetic AST only; never execute model-provided code."""
    text = expression.translate(str.maketrans({"×": "*", "÷": "/", "−": "-", "（": "(", "）": ")", "[": "(", "]": ")"})).strip()
    text = re.sub(r"(\d+(?:\.\d+)?)%", r"(\1/100)", text)
    if not text or len(text) > 120 or not re.fullmatch(r"[0-9.\s+*/()\-]+", text):
        return None
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    try:
        tree = ast.parse(text, mode="eval")
        if len(list(ast.walk(tree))) > 80:
            return None

        def visit(node):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                value = Fraction(str(node.value))
            elif isinstance(node, ast.BinOp) and type(node.op) in ops:
                value = ops[type(node.op)](visit(node.left), visit(node.right))
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            else:
                raise ValueError("Unsupported arithmetic")
            if abs(value.numerator) > 10 ** 15 or value.denominator > 10 ** 12:
                raise ValueError("Arithmetic is too large")
            return value

        return visit(tree.body)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, RecursionError):
        return None


def _number(value) -> Optional[Fraction]:
    if type(value) not in (int, float, str) or len(str(value)) > 80:
        return None
    try:
        return Fraction(str(value).strip())
    except (ValueError, ZeroDivisionError):
        return None


def question_issue(question) -> Optional[str]:
    if not isinstance(question, dict):
        return "题目不是有效对象"
    try:
        Question.model_validate(question)
    except ValidationError:
        return "题目字段或答案格式不完整"
    kind, stem, answer = question.get("type"), question.get("stem"), question.get("answer")
    if not isinstance(kind, str) or not kind.strip():
        return "缺少题型"
    if kind not in ("number_split", "compare", "match_pair") and (not isinstance(stem, str) or not stem.strip()):
        return "缺少题干"
    reason = reject_reason(stem)
    if reason:
        return reason
    if answer is None or isinstance(answer, bool) or (isinstance(answer, str) and not answer.strip()):
        return "缺少答案"
    if isinstance(answer, list) and kind != "match_pair":
        return "该题型的答案不能是配对数组"
    if kind in ("multiple_choice", "quiz", "challenge"):
        options = question.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= 8 or any(not isinstance(x, str) or not x.strip() for x in options):
            return "选择题选项不完整"
        if len({x.strip().casefold() for x in options}) != len(options):
            return "选择题选项重复"
        index = _number(answer)
        if index is None or index.denominator != 1 or not 0 <= index < len(options):
            return "选择题答案索引越界"
    if kind in ("oral_math", "vertical_calc", "recursive_calc", "smart_calc"):
        expression = re.sub(r"\s*[=＝]\s*[_?？\s]*$", "", stem or "")
        expected, actual = arithmetic_value(expression), _number(answer)
        if expected is None:
            return "计算题算式格式不正确"
        remainder = re.fullmatch(r"\s*(\d+)\s*(?:余|…{1,2}|\.{3,6})\s*(\d+)\s*", str(answer))
        division = re.fullmatch(r"\s*(\d+)\s*[÷/]\s*(\d+)\s*", expression)
        if remainder and division and int(division[2]) > 0:
            if divmod(int(division[1]), int(division[2])) != (int(remainder[1]), int(remainder[2])):
                return "有余数除法答案不正确"
        elif actual is None or expected != actual:
            return "计算题答案不正确"
    if kind == "compare":
        left = arithmetic_value(str(question.get("left_expr", "")))
        right = arithmetic_value(str(question.get("right_expr", "")))
        if left is None or right is None:
            return "比大小题缺少有效算式"
        if answer != ("<" if left < right else ">" if left > right else "="):
            return "比大小题答案不正确"
    if kind == "true_false" and str(answer).strip().casefold() not in ("√", "×", "正确", "错误", "对", "错", "true", "false"):
        return "判断题答案格式不正确"
    if kind == "number_split":
        if any(key not in question for key in ("top", "left", "right")):
            return "数的分成字段缺失"
        values = [_number(question.get(key)) for key in ("top", "left", "right")]
        if values.count(None) != 1 or _number(answer) is None:
            return "数的分成需包含两个已知数和一个待填数"
        blank = question[("top", "left", "right")[values.index(None)]]
        if blank is not None and not re.fullmatch(r"[_?？\s]+", str(blank)):
            return "数的分成填空位置无效"
        values[values.index(None)] = _number(answer)
        if values[0] != values[1] + values[2]:
            return "数的分成答案不正确"
    if kind == "match_pair":
        left, right = question.get("left_items"), question.get("right_items")
        if not isinstance(left, list) or not isinstance(right, list) or not left or len(left) != len(right):
            return "配对题左右项目不完整"
        if any(not isinstance(item, str) or not item.strip() for item in left + right):
            return "配对题包含空项目"
        if not isinstance(answer, list) or len(answer) != len(left):
            return "配对题答案不完整"
        if any(not isinstance(pair, list) or len(pair) != 2 or any(type(i) is not int for i in pair) for pair in answer):
            return "配对题答案格式不正确"
        if {pair[0] for pair in answer} != set(range(len(left))) or {pair[1] for pair in answer} != set(range(len(right))):
            return "配对题索引越界或重复"
    return None


def question_fingerprint(question: dict, namespace: str = "") -> str:
    content = {key: question[key] for key in (
        "type", "stem", "options", "left_items", "right_items", "top", "left", "right", "left_expr", "right_expr",
    ) if question.get(key) is not None}
    return namespace + re.sub(r"\s+", "", json.dumps(content, sort_keys=True, ensure_ascii=False)).casefold()


def filter_questions(questions: list, context: str = "", seen: Optional[set] = None, namespace: str = "") -> tuple:
    """拦截不合格题目。返回 (保留列表, 被拦截题目列表)。

    注意：被拦截的题【不删除】——由调用方决定替换重出或提示用户，
    保证试卷题数不被悄悄减少。
    """
    ok, blocked = [], []
    seen = seen if seen is not None else set()
    for q in (questions or []):
        reason = question_issue(q)
        fingerprint = question_fingerprint(q, namespace) if isinstance(q, dict) else ""
        if not reason and fingerprint in seen:
            reason = "重复题目"
        if reason:
            blocked.append(q)
            logger.info("Question rejected (%s): %s", context, reason)
            continue
        seen.add(fingerprint)
        ok.append(q)
    return ok, blocked
