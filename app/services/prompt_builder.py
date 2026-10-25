"""教材条件、教学要求与独立的 JSON 输出契约。"""

import json
from types import SimpleNamespace

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
        question.update(type="multiple_choice", options=["选项内容甲", "选项内容乙", "选项内容丙"], answer=0)
    elif kind == "number_split":
        question = {"type": kind, "top": 5, "left": 2, "right": "____",
                    "answer": 3, "analysis": "解析"}
    elif kind == "compare":
        question = {"type": kind, "left_expr": "左侧表达式", "right_expr": "右侧表达式",
                    "answer": ">、<或=", "analysis": "解析"}
    elif kind == "match_pair":
        question = {"type": kind, "left_items": ["左侧内容甲", "左侧内容乙"], "right_items": ["右侧内容甲", "右侧内容乙"],
                    "answer": [[0, 1], [1, 0]], "analysis": "解析"}
    elif kind == "true_false":
        question["answer"] = "√或×"
        question["stem"] = "待判断的简短命题，解析放analysis"
    elif kind == "fill_blank":
        question["stem"] = "简短题干，空缺处用___（三个下划线）表示；方法填空可展示待补步骤，完整解析放analysis"
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


DIFFICULTY_RULES = {
    "easy": "基础：直接运用本课知识，条件明确，提供必要提示，不叠加无关计算或生词。",
    "medium": "标准：在本课范围内独立运用知识，适度变化情境，步骤符合该年级已学内容。",
    "hard": "提升：在本课范围内考查方法选择、解释或迁移，减少提示；不得靠超纲、大数或冗长题干提高难度。",
}

SUBJECT_RULES = {
    "数学": "数学：核对运算顺序、数值和单位；条件与问题的数量关系一致，解析给出可复算的关键算式。",
    "语文": "语文：字音、字形、词义与语境相符；多音字、近义词和句意题提供足够语境。"
            "引用需准确，未提供的课文原文不得自行补写；原创阅读材料不冒称教材原文。",
    "英语": "英语：词汇和句式符合年级，拼写、大小写、标点及语法正确；"
            "补全或选择题提供足够上下文，避免多个选项在语法和语义上同时成立。",
}


def teaching_requirements(grade: str, subject: str, keyword: str, difficulty: str, kinds: set[str]) -> str:
    from app.services.knowledge_topics import is_make_ten_practice
    from app.services.question_planning import planning_prompt

    rules = [
        f"难度：{DIFFICULTY_RULES.get(difficulty, DIFFICULTY_RULES['medium'])}",
        "教学要求：每题必须对应所选知识点；保留用户明确指定的专项、数值范围和附加限制。"
        "词汇、数值范围和解题步骤符合年级及所选册次。",
        "多个知识点在本次生成范围内自然覆盖即可，不强行混入每道题，也不构成大题内的子考法名额；"
        "大题只固定题数，加法与减法这类子考法的数量不预设配比，不照搬模板或上一卷的题面分布，"
        "题目顺序也不按子考法分块排列。",
        "题意完整、条件充分、问法明确。先独立求解，再核对答案和解析；解析说明依据和关键步骤，不只重复答案。",
        "同一大题和同卷同题型不照抄完全相同的题；基础练习允许同一计算关系在不同题型中合理重复。",
        "不要把答案或提示答案的解析泄露到题干。不能完成指定范围时不要编造事实、引用或教材内容。",
    ]
    if subject in SUBJECT_RULES:
        rules.append(SUBJECT_RULES[subject])
    if subject == "语文" and any(word in keyword for word in ("近义词", "反义词")):
        rules.append("近义词、反义词辨析须在题干中明确目标词、比较要求和具体语境，不能只在解析中引入目标词或改成无关的选词填空。")
    if kinds & {"quiz", "challenge", "reading"}:
        rules.append("选择题只有一个正确选项，干扰项对应常见错误且互不等价；答案用从0开始的索引，正确选项位置适度分散。")
    if "word_problem" in kinds:
        rules.append("应用题保留完整条件、数量关系、单位和问句；答案包含必要单位，解析列出与题意对应的算式。")
    if "reading" in kinds:
        rules.append("阅读正文长度和词汇适合年级，问题只依据所给正文，解析指出原文依据；不依赖未提供的图片或课文。"
                     "引用原句须与正文逐字一致，转述应标明是概括，不能加引号冒充原句。")
    if "fill_blank" in kinds:
        rules.append("多个空的答案按空位顺序返回；开放填空给出合理参考答案，可接受的其他答案放acceptable_answers。")
    if "true_false" in kinds:
        rules.append("判断题正误合理搭配，不以修改正确答案来平衡分布，避免含混或缺条件的断言。")
    if "match_pair" in kinds:
        rules.append("配对题两侧项目一一对应，不存在歧义；answer为[[左索引,右索引],...]，每个索引恰好使用一次。")
    if "number_split" in kinds:
        rules.append("数的分成满足top=left+right，三个位置只留一个____，其余填整数；answer为该空的整数值。")
    if is_make_ten_practice(grade, subject, keyword):
        rules.append(planning_prompt(subject, keyword, [SimpleNamespace(game_type=kind) for kind in sorted(kinds)], grade))
    return "\n" + "\n".join(rules)


def _conditions(grade: str, subject: str, keyword: str, count: int) -> str:
    return f"年级：{grade}\n科目：{subject}\n题数：{count}\n知识点：{keyword}"


def _textbook_context(scope: KnowledgeScope | None, keyword: str) -> str:
    if not scope or not scope.books:
        return ""
    from app.services.knowledge_scope import knowledge_scope_service

    knowledge_scope_service.require_selected_semesters(scope, keyword)
    selected_semesters = [semester for semester in ("上册", "下册") if semester in keyword]
    books = [book for book in scope.books if not selected_semesters or book.semester in selected_semesters]
    context = "\n教材：" + "；".join(
        f"{book.series} {scope.grade}{book.semester}（官方资源号{book.id}）" for book in books
    )
    units = [f"{book.semester}·{unit.title}：{'、'.join(unit.topics)}" for book in books for unit in book.units
             if unit.title in keyword or any(topic in keyword for topic in unit.topics)]
    return context + ("\n相关教材目录：" + "；".join(units)[:2000] if units else "") + "\n教材信息仅为目录，不代表已提供课文正文。"


def _format_contract(value: dict) -> str:
    return (
        "\n\n接口格式：只返回一个合法JSON对象，不加代码块或额外文字；字符串中的换行和引号须按JSON转义。"
        "下面是字段与类型示例，说明文字及示例数值须替换成实际题目内容；"
        "game_type、type和section_id保留指定值，questions按指定题数返回数组。"
        "选择题answer用整数索引，配对题用二维整数数组，不把数组或整数写成说明文字。\n"
        + json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )


def allows_process_fill(grade: str, subject: str, keyword: str) -> bool:
    from app.services.knowledge_topics import is_make_ten_practice

    return subject == "数学" and (any(marker in keyword for marker in ("过程填空", "凑十法"))
                               or is_make_ten_practice(grade, subject, keyword))


def _format_rules(kinds: set[str], subject: str, keyword: str, grade: str) -> str:
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
            "完整解答写在analysis。"
        )
        if subject == "数学":
            lines.append("普通数学填空题题干一行控制在24个字符以内，通常只设置1个空，最多2个空。")
            if allows_process_fill(grade, subject, keyword):
                lines.append("本课可安排方法填空，待补过程可换行，保留作答空格；完整答案与解析单独返回。")
            else:
                lines.append("未要求过程填空时，不写解题步骤。")
    return ("\n题面格式要求：" + "\n".join(lines)) if lines else ""


class PromptBuilder:
    @staticmethod
    def build_system_prompt(request: GenerateRequest, scope: KnowledgeScope) -> str:
        return (
            _conditions(request.grade, request.subject, request.keyword, request.question_count)
            + _textbook_context(scope, request.keyword)
            + f"\n题型：{TYPE_NAMES.get(request.game_type.value, request.game_type.value)}"
            + teaching_requirements(request.grade, request.subject, request.keyword, request.difficulty.value,
                                    {request.game_type.value})
            + _format_rules({request.game_type.value}, request.subject, request.keyword, request.grade)
            + "\n题干简洁，答案和完整解析单独返回，方法填空只展示待补步骤。"
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
            + teaching_requirements(grade, subject, keyword, difficulty, {item.game_type for item in items})
            + _format_rules({item.game_type for item in items}, subject, keyword, grade)
            + "\n题干简洁，答案和完整解析单独返回，方法填空只展示待补步骤。"
            + _format_contract({"sections": sections})
        )

    @staticmethod
    def build_user_message(keyword: str) -> str:
        return "请生成题目。"

    @staticmethod
    def build_batch_user_message(keyword: str) -> str:
        return "请生成题目。"


prompt_builder = PromptBuilder()
