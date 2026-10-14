"""题型质检 —— 对 LLM 生成的题目做内容级校验，不合格的剔除或重生成

结构、选项及可确定计算答案检查；同卷避重由结果整理层负责。
不替代教师对语义、知识范围与开放题答案的审核。
"""

import ast
import json
import logging
import operator
import re
import unicodedata
from fractions import Fraction

from pydantic import ValidationError

from app.models import Question

logger = logging.getLogger(__name__)

_MATH_SYMBOLS: dict[int, int | str] = {code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)}
_MATH_SYMBOLS.update({ord(key): value for key, value in
                      {"×": "*", "÷": "/", "−": "-", "　": " ", "[": "(", "]": ")"}.items()})


def math_symbols(value: str) -> str:
    """只归一化全角 ASCII 与运算符，不把上标等其他数学记号改成数字。"""
    return value.translate(_MATH_SYMBOLS)


def calculation_expression(stem: str) -> str:
    text = math_symbols(stem)
    return re.sub(r"\s*=\s*(?:[_?\s]*|\(\s*[_?\s]*\))$", "", text).strip()


# 「同数连加」核心模式：a + a（两项即成，为 3 项检测打基础）
# 「加法转乘法」题：4 + 4 + 4 + 4 + 4 = 5 × ____（同数连加 ≥2 项 + 乘号）
_CHAIN_ADD_TO_MUL = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*\+\s*\1(?![\d.])(?:\s*\+\s*\1(?![\d.]))*\s*=\s*\d*\s*[×x*]"
)
# 同数连加 ≥ 3 项（无论是否配乘法）——乘法意义题，题目必然冗长
_SAME_NUM_CHAIN3 = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*\+\s*\1(?![\d.])\s*\+\s*\1(?![\d.])"
)


def reject_reason(stem: str | None) -> str | None:
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


def arithmetic_value(expression: str) -> Fraction | None:
    """Evaluate a bounded arithmetic AST only; never execute model-provided code."""
    text = math_symbols(expression).strip()
    text = re.sub(r"(\d+(?:\.\d+)?)%", r"(\1/100)", text)
    if not text or len(text) > 120 or not re.fullmatch(r"[0-9.\s+*/()\-]+", text):
        return None
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    try:
        tree = ast.parse(text, mode="eval")
        if len(list(ast.walk(tree))) > 80:
            return None

        def visit(node) -> Fraction:
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


def _number(value) -> Fraction | None:
    if type(value) not in (int, float, str) or len(str(value)) > 80:
        return None
    try:
        return Fraction(str(value).strip())
    except (ValueError, ZeroDivisionError):
        return None


def filled_math_stem(question: dict) -> str:
    """依空格顺序代入数字答案；不能明确对应时返回空字符串。"""
    stem = re.sub(r"\s+", "", math_symbols(str(question.get("stem", ""))))
    blank = re.compile(r"_+|[?？]+")
    if not blank.search(stem):
        return stem
    answers = re.split(r"[,，;；、\s]+", str(question.get("answer", "")).strip())
    if len(answers) != len(blank.findall(stem)) or any(_number(answer) is None for answer in answers):
        return ""
    # 分数和负数作为一个数代入，避免 3 / (1/2) 被误算成 3 / 1 / 2。
    values = iter(f"({answer})" if "/" in answer or answer.startswith("-") else answer for answer in answers)
    return blank.sub(lambda _: next(values), stem)


def arithmetic_statement(stem: str) -> tuple[str, str, str] | None:
    """只识别完整数值判断式，不对文字命题猜答案。"""
    text = re.sub(r"\(\)$", "", re.sub(r"\s+", "", math_symbols(stem))).rstrip("。.")
    match = re.fullmatch(r"([0-9.+*/()\-]+)([=<>≤≥≠])([0-9.+*/()\-]+)", text)
    if match and all(arithmetic_value(match[index]) is not None for index in (1, 3)):
        return match[1], match[2], match[3]
    return None


def question_issue(
    question, *, compact_fill_blank: bool = False, allow_fill_blank_steps: bool = False,
) -> str | None:
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
        expected = choice_value(stem or "")
        values = [arithmetic_value(value) for value in options]
        if expected is not None and all(value is not None for value in values):
            correct_indices = [i for i, value in enumerate(values) if value == expected]
            if len(correct_indices) != 1:
                return "选择题没有唯一正确选项"
            if int(index) != correct_indices[0]:
                return "选择题答案与算式不一致"
    if kind in ("oral_math", "vertical_calc", "recursive_calc", "smart_calc"):
        expression = calculation_expression(stem or "")
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
    if kind == "true_false" and (statement := arithmetic_statement(stem or "")):
        left_text, relation, right_text = statement
        a, b = arithmetic_value(left_text), arithmetic_value(right_text)
        operators = {"=": operator.eq, "<": operator.lt, ">": operator.gt,
                     "≤": operator.le, "≥": operator.ge, "≠": operator.ne}
        correct = str(answer).strip().casefold() in ("√", "正确", "对", "true")
        if a is not None and b is not None and operators[relation](a, b) != correct:
            return "判断题算式与正误答案不一致"
    if kind == "fill_blank":
        text = re.sub(r"\s+", "", math_symbols(stem or ""))
        numeric_fill = bool(re.fullmatch(r"[0-9.+*/()=_\-?]+", text) and re.search(r"[_?]", text) and "=" in text)
        process_fill = allow_fill_blank_steps and numeric_fill and "\n" in (stem or "") and text.count("=") > 1
        # 仅生成普通数学填空时限制题干长度；换行不能绕过限制。
        if compact_fill_blank and not process_fill and len(str(stem or "").strip()) > 24:
            return "填空题题干过长"
        if compact_fill_blank and re.match(r"在\s*_+\s*里填", str(stem or "").strip()):
            return "填空题含多余说明性前缀"
        if numeric_fill:
            filled_stem = filled_math_stem(question)
            values = [arithmetic_value(part) for part in filled_stem.split("=")] if filled_stem else []
            if not values or any(value is None for value in values) or len(set(values)) != 1:
                return "填空题答案与算式不一致或多空答案不完整"
    if kind == "number_split":
        if any(key not in question for key in ("top", "left", "right")):
            return "数的分成字段缺失"
        values = [_number(question.get(key)) for key in ("top", "left", "right")]
        target = _number(answer)
        if values.count(None) != 1 or target is None:
            return "数的分成需包含两个已知数和一个待填数"
        blank = question[("top", "left", "right")[values.index(None)]]
        if blank is not None and not re.fullmatch(r"[_?？\s]+", str(blank)):
            return "数的分成填空位置无效"
        # 用局部列表替代直接回写 values，让"待填位已填"这件事对类型检查可见
        filled = [target if value is None else value for value in values]
        if filled[0] != filled[1] + filled[2]:
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
        left_values = [arithmetic_value(value) for value in left]
        right_values = [arithmetic_value(value) for value in right]
        if all(value is not None for value in left_values + right_values):
            if any(left_values[a] != right_values[b] for a, b in answer):
                return "配对题计算结果与连线答案不一致"
            if len(set(right_values)) != len(right_values):
                return "配对题存在等值项目，无法唯一配对"
    if analysis_issue(str(question.get("analysis", ""))):
        return "解析包含不成立的计算等式"
    return None


def choice_value(stem: str) -> Fraction | None:
    """仅识别完整、直接求值的选择题；情境题和反向提问留给语义复核。"""
    text = math_symbols(stem).strip().rstrip("。.?？")
    text = re.sub(r"^(?:计算|算式)\s*", "", text)
    text = re.sub(r"(?:的结果是|的结果|等于多少|等于|是多少|=)\s*(?:多少|[_?？]|\(\s*\))*\s*$", "", text)
    return arithmetic_value(text)


def analysis_issue(analysis: str) -> bool:
    """只拦截独立的错误等式；引用错误示范或自然语言推理交给语义复核。"""
    if any(marker in analysis for marker in ("错", "误", "不能", "不是", "并非", "不等", "≠", "\"", "“", "‘")):
        return False
    for clause in re.split(r"[。；;，,\n]", analysis):
        text = math_symbols(clause).strip()
        for word, symbol in (("等于", "="), ("乘以", "*"), ("除以", "/"), ("加", "+"), ("减", "-")):
            text = text.replace(word, symbol)
        text = re.sub(r"\((?:支|个|朵|本|人|元|米|厘米|千米|千克|克|只|辆|颗|块)\)$", "", text)
        parts = text.split("=")
        if len(parts) < 2:
            continue
        values = [arithmetic_value(part) for part in parts]
        if all(value is not None for value in values) and len(set(values)) != 1:
            return True
    return False


def exact_question_key(question: dict, passage: str = "") -> str:
    """只去完全重复的题面；不合并换考法、换数字或不同文章的基础练习。"""
    fields = ("type", "stem", "options", "left_items", "right_items", "top", "left", "right", "left_expr", "right_expr")

    def normalize(value):
        if isinstance(value, list):
            return [normalize(item) for item in value]
        # 保留大小写、词间空格和上下标；它们可能改变语言题或数学题的含义。
        text = re.sub(r"\s+", " ", math_symbols(str(value))).strip() if value is not None else ""
        return re.sub(r"\s*([+*/=<>≤≥≠\-])\s*", r"\1", text)

    return json.dumps([normalize(passage), {key: normalize(question.get(key)) for key in fields}], ensure_ascii=False, sort_keys=True)


def make_ten_issue(question: dict) -> str | None:
    """仅校验明确的凑十法数值题边界，不生成题目，也不猜测自然语言题意。"""
    kind = question.get("type")
    expressions: list[str] = []
    allow_ten = kind in ("fill_blank", "true_false")
    if kind in ("oral_math", "vertical_calc", "fill_blank"):
        text = filled_math_stem(question)
        # 方法填空只检查起始原式，后续拆分步骤由算术一致性检查负责。
        first = text.split("=", 1)[0]
        if arithmetic_value(first) is not None:
            expressions = [first]
    elif kind == "compare":
        expressions = [str(question.get(key, "")) for key in ("left_expr", "right_expr")]
    elif kind == "true_false" and (statement := arithmetic_statement(question.get("stem", ""))):
        expressions = [statement[0], statement[2]]
    elif kind == "number_split":
        values = [_number(question.get(key)) for key in ("top", "left", "right")]
        answer = _number(question.get("answer"))
        filled = [answer if value is None else value for value in values]
        if any(value is None or value.denominator != 1 or not 1 <= value <= 10 for value in filled):
            return "凑十法的分成与组成应使用10以内的正整数"
    addition_found = False
    for expression in expressions:
        text = _text(expression)
        # 用 AST 识别原式，避免把括号或全角写法当成绕过边界的不同题型。
        try:
            tree = ast.parse(text, mode="eval").body
        except (SyntaxError, ValueError):
            return "凑十法算式格式不正确"
        if isinstance(tree, ast.Constant) and type(tree.value) is int and 0 <= tree.value <= 20:
            continue
        if (isinstance(tree, ast.BinOp) and isinstance(tree.op, ast.Add)
                and all(isinstance(node, ast.Constant) and type(node.value) is int and 1 <= node.value <= 9
                        for node in (tree.left, tree.right))):
            total = arithmetic_value(text)
            if total is not None and (total >= 10 if allow_ten else total > 10):
                addition_found = True
                continue
        return "凑十法原式应是一位数加一位数的进位加法，不能使用两位数加数或独立三项连加"
    if expressions and not addition_found and kind != "true_false":
        return "凑十法练习缺少两数加法原式"
    return None


def _text(value) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return re.sub(r"\s+", "", text).translate(str.maketrans("−×÷", "-*/"))


def _expression_key(value: str) -> str:
    """仅归一纯数字算式的写法与加乘交换；不按答案合并不同运算。"""
    text = _text(value)
    if arithmetic_value(text) is None:
        return text
    try:
        def key(node) -> str:
            if isinstance(node, ast.Constant):
                return str(Fraction(str(node.value)))
            if isinstance(node, ast.BinOp):
                left, right = key(node.left), key(node.right)
                if isinstance(node.op, (ast.Add, ast.Mult)):
                    left, right = sorted((left, right))
                return f"{type(node.op).__name__}({left},{right})"
            if isinstance(node, ast.UnaryOp):
                return f"{type(node.op).__name__}({key(node.operand)})"
            raise ValueError("非算术节点")
        return key(ast.parse(text, mode="eval").body)
    except (SyntaxError, ValueError):
        return text


def question_fingerprint(question: dict, namespace: str = "") -> str:
    kind = question.get("type", "")
    stem = re.sub(r"[_?]+", "_", _text(question.get("stem", "")))
    content: list
    expression = re.sub(r"=[_?]*$", "", stem)
    if kind in ("oral_math", "vertical_calc", "recursive_calc", "smart_calc") or (
        kind == "fill_blank" and expression != stem and arithmetic_value(expression) is not None
    ):
        content = ["calculation", _expression_key(calculation_expression(stem))]
    elif kind == "number_split":
        def part(value):
            return str(_number(value)) if _number(value) is not None else "_"
        content = [kind, part(question.get("top")), sorted(part(question.get(k)) for k in ("left", "right"))]
    elif kind == "compare":
        content = [kind, sorted(_expression_key(str(question.get(k, ""))) for k in ("left_expr", "right_expr"))]
    elif kind == "true_false" and (statement := arithmetic_statement(question.get("stem", ""))):
        left, relation, right = statement
        expressions = [_expression_key(left), _expression_key(right)]
        if relation in ("=", "≠"):
            expressions.sort()
        elif relation in (">", "≥"):
            expressions.reverse()
            relation = {">": "<", "≥": "≤"}[relation]
        content = [kind, relation, expressions]
    elif kind in ("multiple_choice", "quiz", "challenge"):
        content = ["multiple_choice", stem, sorted(_text(value) for value in question.get("options") or [])]
    elif kind == "match_pair":
        content = [kind, stem, sorted(_text(value) for value in question.get("left_items") or []),
                   sorted(_text(value) for value in question.get("right_items") or [])]
    else:
        content = [kind, stem]
    # 阅读题仍以原文分隔；不同文章里的同一句提问不能合并。
    return json.dumps([unicodedata.normalize("NFKC", namespace).strip(), content], ensure_ascii=False)


def filter_questions(questions: list, context: str = "") -> tuple:
    """拦截不合格题目。返回 (保留列表, 被拦截题目列表)。

    注意：被拦截的题【不删除】——由调用方决定替换重出或提示用户，
    保证试卷题数不被悄悄减少。
    """
    ok, blocked = [], []
    for q in (questions or []):
        reason = question_issue(q)
        if reason:
            blocked.append(q)
            logger.info("Question rejected (%s): %s", context, reason)
            continue
        ok.append(q)
    return ok, blocked
