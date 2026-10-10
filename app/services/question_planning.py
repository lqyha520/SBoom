"""整卷计算关系、填空考法与答案顺序检查；不改写模型题目或答案。"""

import random
import re
from collections import Counter

from app.services.knowledge_topics import is_make_ten_practice
from app.services.question_qc import _expression_key, _number, _text, arithmetic_value, filled_math_stem

RELATION_LIMIT = 2
_BLANK = re.compile(r"_+|[?？]+")


def calculation_relations(question: dict) -> set[str]:
    """提取有把握的计算关系，跳过文章、情境题和不能解析的自然语言。"""
    kind = question.get("type")
    expressions: list[str] = []
    if kind == "number_split":
        values = [_number(question.get(key)) for key in ("top", "left", "right")]
        answer = _number(question.get("answer"))
        if values.count(None) == 1 and answer is not None:
            filled = [answer if value is None else value for value in values]
            expressions = [f"{filled[1]}+{filled[2]}"]
    elif kind == "compare":
        expressions = [str(question.get(key, "")) for key in ("left_expr", "right_expr")]
    elif kind in ("oral_math", "vertical_calc", "recursive_calc", "smart_calc", "fill_blank", "true_false"):
        stem = filled_math_stem(question)
        # 凑十过程只统计原算式，不能把每一步都算成一道独立练习。
        first = re.split(r"[=＝<>≤≥≠]", stem, maxsplit=1)[0]
        if arithmetic_value(first) is not None:
            expressions = [first]
        elif kind == "true_false":
            match = re.match(r"^(\d+)加(\d+)[,，]", stem)
            if match:
                expressions = [f"{match[1]}+{match[2]}"]
    return {key for expression in expressions if arithmetic_value(expression) is not None
            for key in [_expression_key(expression)] if key.startswith(("Add(", "Sub(", "Mult(", "Div("))}


def fill_pattern(question: dict) -> str:
    """限制数学填空的单一考法；普通求结果计算保留正常重复练习空间。"""
    if question.get("type") != "fill_blank":
        return ""
    stem = _text(question.get("stem", ""))
    if not re.search(r"\d", stem) or not _BLANK.search(stem):
        return ""
    if re.fullmatch(r"[0-9.+*/()\-]+=_+", stem):
        return ""
    if not calculation_relations(question) and not any(word in stem for word in ("凑", "分成", "组成")):
        return ""
    if len(_BLANK.findall(stem)) > 1:
        return "过程填空"
    if re.fullmatch(r"[0-9.+*/()\-]+=10\+_+", stem):
        return "凑十后填余数"
    # 保留运算符和空格位置的含义，只替换具体数值。
    return re.sub(r"\d+(?:\.\d+)?", "#", _BLANK.sub("_", stem))


def pattern_limit(count: int) -> int:
    return max(2, (count + 1) // 2)


def fill_plan_gaps(questions: list[dict], count: int, subject: str, keyword: str) -> tuple[int, list[str]]:
    """只评估能识别的数学填空；缺考法时交给原有补题预算，不自行编造题目。"""
    if subject != "数学" or count < 4 or not any(calculation_relations(q) for q in questions):
        return 0, []
    patterns = {fill_pattern(question) or "直接求结果或其他" for question in questions}
    gaps = max(0, 3 - len(patterns))
    warnings = ["填空考法少于3种，请核对是否需要增加变化"] if gaps else []
    if ("凑十" in keyword or "进位加法" in keyword) and "过程填空" not in patterns:
        gaps = max(gaps, 1)
        warnings.append("缺少让学生完成拆分、凑十和合成的过程填空，请核对")
    return gaps, warnings


def planning_prompt(subject: str, keyword: str, items, grade: str = "") -> str:
    if subject != "数学":
        return ""
    if is_make_ten_practice(grade, subject, keyword):
        goals = {
            "oral_math": "练习一位数加一位数的进位加法，题干只写原算式，拆数过程写在analysis。",
            "fill_blank": "围绕同一教学目标安排求和、凑十所需数、求未知加数或方法填空；"
                          "按题量适度搭配，不强制凑够考法种数。题量足够时可安排少量方法填空："
                          "从原来的两数加法开始，依次呈现拆分、凑十、合成；过程必须写在stem中，"
                          "可用JSON的\\n分行，多个空的answer按顺序用逗号分隔，不省略必要步骤。",
            "number_split": "为凑十做准备：将10以内的数分成两个正整数，或由两部分组成10以内的数。"
                            "只考数的分成与组成，题面没有给出的原算式不要在解析里凭空补设。",
            "compare": "比较一个两数进位加法算式与20以内的数，或比较两个这样的算式；"
                       "每侧至多一个加号，不用三项连加增加运算负担。",
            "true_false": "检查两数进位加法的结果或简单的拆数、凑十方法；"
                          "正误适度搭配，错误项对应常见错误，不使用独立三项连加。",
            "word_problem": "只安排两个一位数合并求总数的一步问题，和大于10；"
                            "保留完整条件、单位和明确问句，不为压缩字数写成词语拼接。",
        }
        lines = [
            "\n## 本课教学目标与题型分工",
            "核心是用凑十法理解并练习一位数加一位数的进位加法：两个加数均为1～9的整数，和大于10。",
            "口算原式不出18 + 2、17 + 3这类两位数加一位数，也不靠三项连加、减乘除提高难度。",
            "凑成10和10以内的数的分成可作为辅助练习；方法填空里的拆分步骤允许出现三个加数，"
            "但必须从原来的两数加法展开，不能整组变成三项连加。",
            "用户明确指定9加几、8加几等专项或附加限制时必须保留；未指定专项时适度覆盖不同加数。",
            "基础练习允许重复计算关系：同一算式可以在不同题型考查不同能力，近期练过也可以再练。"
            "同卷不照抄完全相同的题目，不以换运算结构、扩大数值范围或省略题意来追求新颖。",
            "难度通过提示多少和方法理解深浅调整，不改变上述运算与数值边界。",
        ]
        for item in items:
            if goal := goals.get(item.game_type):
                lines.append(f"- {item.game_type}：{goal}")
        return "\n".join(lines)
    lines = [
        "\n## 整卷考法安排",
        "按计算关系统筹所有大题：同一组数字与运算（含交换加数、换填空位置）原则上最多出现2次，"
        "第二次必须考查不同能力。不要将口算逐题复制到比大小或判断题。",
        "判断题的正误、比大小的符号应适度分散，不要按对错交替或固定符号循环排列；"
        "不得为了改变答案分布而标错答案。",
    ]
    for item in items:
        if item.game_type != "fill_blank" or item.question_count < 4:
            continue
        lines.append(f"填空大题 {getattr(item, 'section_id', None) or 'fill_blank'} 共{item.question_count}题："
                     f"至少安排3种适用考法，同一填空模板不超过{pattern_limit(item.question_count)}题；"
                     "在知识范围内轮换求结果、求未知数、补方法步骤，不要连续堆叠同一等式模板。")
        if "凑十" in keyword or "进位加法" in keyword:
            lines.append(
                "这组填空至少1题让学生完成拆分→凑十→合成，过程必须写在stem中，不能只写在analysis。"
                "过程题可用2～3行短算式（此处优先于一般的一行限制，每行约20字符以内），"
                "用JSON的\\n换行；每个空依次填写一个数字，answer用逗号分隔的数字字符串。"
                "格式示例仅展示结构，不得照抄数字："
                "'8 + 7 = 8 + ____ + 5\\n= 10 + ____ = ____'，answer为'2，5，15'。"
                "各行应连成相等的完整计算过程，其他题仍保持简短，不能增加题数或提高难度。"
            )
    return "\n".join(lines)


def _answer_key(question: dict) -> str:
    answer = str(question["answer"]).strip().casefold()
    if question.get("type") == "true_false":
        return "对" if answer in ("√", "正确", "对", "true") else "错"
    return answer


def _order_penalty(questions: list[dict]) -> int:
    keys = [_answer_key(question) for question in questions]
    repeats = sum(keys[i] == keys[i - 1] == keys[i - 2] for i in range(2, len(keys)))
    # 拦截两轮及以上的交替/三符号循环，优先消除整组可猜的周期。
    cycles = sum(all(keys[j] == keys[j - width] for j in range(i + width, i + 2 * width))
                 for width in (2, 3) for i in range(len(keys) - 2 * width + 1))
    return repeats + 4 * cycles


def arrange_answers(questions: list[dict], game_type: str) -> tuple[list[dict], list[str]]:
    """只调整独立判断/比较题的顺序，题干、答案、解析始终整体移动。"""
    if game_type not in ("true_false", "compare") or len(questions) < 4:
        return questions, []
    # 有承接关系的题不能重排；此类大题应由老师核对。
    if any(re.search(r"上[一道题述面]|前[一道题述面]|第[一二三四五六七八九十\d]+题|接着|据此|由此|同上",
                     str(question.get("stem", ""))) or question.get("difficulty_level") is not None
           for question in questions):
        return questions, ["题目含承接关系或关卡顺序，未自动调整答案排列，请核对"]
    counts = Counter(_answer_key(question) for question in questions)
    warnings = []
    if max(counts.values()) > (len(questions) + 1) // 2:
        warnings.append("答案分布偏集中，已保留正确答案，请核对题目搭配")
    best = questions
    score = _order_penalty(best)
    for _ in range(64):
        candidate = list(questions)
        random.shuffle(candidate)
        penalty = _order_penalty(candidate)
        if penalty < score:
            best, score = candidate, penalty
        if score == 0:
            break
    if score:
        warnings.append("答案顺序仍存在连续或循环规律，请核对题目搭配")
    return best, warnings
