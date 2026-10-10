"""简短的教材出题条件与独立的 JSON 输出契约。"""

import json

from app.models import GenerateRequest, KnowledgeScope

# 保留现有入口的题型适配检查，不将其转换为模型出题指导。
MIN_GRADE_FOR_TYPE = {"vertical_calc": 1, "recursive_calc": 3, "smart_calc": 4, "word_problem": 1}
TYPE_NAMES = {
    "quiz": "选择题", "fill_blank": "填空题", "match_pair": "连线配对", "challenge": "闯关选择题",
    "oral_math": "口算题", "reading": "阅读理解", "vertical_calc": "竖式计算",
    "recursive_calc": "脱式计算", "smart_calc": "简便计算", "number_split": "数的分成",
    "compare": "比大小", "true_false": "判断题", "word_problem": "应用题",
}


def _grade_num(grade: str) -> int:
    for ch in grade:
        if ch in "一二三四五六":
            return "一二三四五六".index(ch) + 1
    return 9


def _question_fields(kind: str) -> dict:
    question: dict = {"type": kind, "stem": "题干", "answer": "答案", "analysis": "解析"}
    if kind in ("quiz", "challenge", "reading"):
        question.update(type="multiple_choice", options=["选项内容"], answer="正确选项的从0开始的索引")
    elif kind == "number_split":
        question = {"type": kind, "top": "数字或____", "left": "数字或____", "right": "数字或____",
                    "answer": "空缺的数字", "analysis": "解析"}
    elif kind == "compare":
        question = {"type": kind, "left_expr": "左侧表达式", "right_expr": "右侧表达式",
                    "answer": ">、<或=", "analysis": "解析"}
    elif kind == "match_pair":
        question = {"type": kind, "left_items": ["左侧内容"], "right_items": ["右侧内容"],
                    "answer": "从0开始的配对索引数组", "analysis": "解析"}
    elif kind == "true_false":
        question["answer"] = "√或×"
        question["stem"] = "待判断的简短命题，解析放analysis"
    elif kind == "fill_blank":
        question["stem"] = "简短题干，空缺处用___（三个下划线）表示，解题步骤放analysis"
    elif kind in ("oral_math", "vertical_calc", "recursive_calc", "smart_calc"):
        question["stem"] = "待计算的算式，末尾保留等号，不含结果或解题步骤"
        question["answer"] = "计算结果"
    return question


def _section_fields(kind: str, section_id: str | None = None) -> dict:
    section = {"game_type": kind, "questions": [_question_fields(kind)]}
    if section_id:
        section["section_id"] = section_id
    if kind == "reading":
        section["passage"] = "阅读正文"
    return section


def _conditions(grade: str, subject: str, keyword: str, count: int) -> str:
    return f"年级：{grade}\n科目：{subject}\n题数：{count}\n知识点：{keyword}"


def _textbook_context(scope: KnowledgeScope | None, keyword: str) -> str:
    if not scope or not scope.books:
        return ""
    from app.services.knowledge_scope import knowledge_scope_service

    knowledge_scope_service.require_selected_semesters(scope, keyword)
    selected_semesters = [semester for semester in ("上册", "下册") if semester in keyword]
    books = [book for book in scope.books if not selected_semesters or book.semester in selected_semesters]
    return "\n教材：" + "；".join(
        f"{book.series} {scope.grade}{book.semester}（官方资源号{book.id}）" for book in books
    )


def _format_contract(value: dict) -> str:
    return (
        "\n\n接口格式：只返回JSON。下面是字段说明，字段说明文字需替换成生成内容；"
        "game_type、type和section_id保留指定值，questions按指定题数返回数组。\n"
        + json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )


def _format_rules(kinds: set[str], subject: str, keyword: str) -> str:
    """给模型最少但明确的题面格式约束，避免题型字段正确而卷面难看。"""
    lines: list[str] = ["本次生成的题目不要重复。"]
    if kinds & {"oral_math", "vertical_calc", "recursive_calc", "smart_calc"}:
        lines.append(
            "计算题题干必须是简短纯算式，末尾必须保留等号（例如‘9＋2 =’），"
            "不要省略等号，不写‘计算’‘结果是’等说明，不把答案或解题过程写进stem。"
        )
    if "fill_blank" in kinds:
        lines.append(
            "填空题只保留学生需要作答的简短内容，不写‘在___里填’等说明性前缀；"
            "未要求过程填空时，不写解题步骤。"
        )
        if subject == "数学":
            lines.append("普通数学填空题题干一行控制在24个字符以内，通常只设置1个空，最多2个空。")
            if any(marker in keyword for marker in ("过程填空", "凑十法")):
                lines.append("知识点明确要求过程填空时，过程可换行，但每一行仍只保留必要内容。")
    return ("\n题面格式要求：" + "\n".join(lines)) if lines else ""


class PromptBuilder:
    @staticmethod
    def build_system_prompt(request: GenerateRequest, scope: KnowledgeScope) -> str:
        return (
            _conditions(request.grade, request.subject, request.keyword, request.question_count)
            + _textbook_context(scope, request.keyword)
            + f"\n题型：{TYPE_NAMES.get(request.game_type.value, request.game_type.value)}"
            + _format_rules({request.game_type.value}, request.subject, request.keyword)
            + "\n题干简洁，答案和解析单独返回；未要求过程填空时，不把解题步骤写进题干。"
            + _format_contract(_section_fields(request.game_type.value))
        )

    @staticmethod
    def build_batch_prompt(grade: str, subject: str, keyword: str, difficulty: str, items, scope=None) -> str:
        sections = [_section_fields(item.game_type, item.section_id or f"section-{index + 1}")
                    for index, item in enumerate(items)]
        counts = {section["section_id"]: item.question_count for section, item in zip(sections, items, strict=True)}
        return (
            _conditions(grade, subject, keyword, sum(item.question_count for item in items))
            + _textbook_context(scope, keyword)
            + "\n题型：" + "；".join(
                f"{section['section_id']}：{TYPE_NAMES.get(item.game_type, item.game_type)} {item.question_count}道"
                for section, item in zip(sections, items, strict=True)
            )
            + "\n各大题题数：" + json.dumps(counts, ensure_ascii=False)
            + _format_rules({item.game_type for item in items}, subject, keyword)
            + "\n题干简洁，答案和解析单独返回；未要求过程填空时，不把解题步骤写进题干。"
            + _format_contract({"sections": sections})
        )

    @staticmethod
    def build_user_message(keyword: str) -> str:
        return "请生成题目。"

    @staticmethod
    def build_batch_user_message(keyword: str) -> str:
        return "请生成题目。"


prompt_builder = PromptBuilder()
