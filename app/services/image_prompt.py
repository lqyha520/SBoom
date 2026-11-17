"""图片习题的教学约束；保持整页直接生图，明确题量和图示语义。"""
from fastapi import HTTPException

from app.models.image_generation import ImageWorksheetRequest
from app.services.knowledge_scope import knowledge_scope_service
from app.services.prompt_builder import DIFFICULTY_RULES, MIN_GRADE_FOR_TYPE, _grade_num, _textbook_context

PROMPT_VERSION = "image-worksheet-v5"
TYPE_NAMES = {
    "quiz": "选择题", "fill_blank": "填空题", "match_pair": "连线配对", "challenge": "闯关挑战",
    "oral_math": "口算题", "reading": "阅读理解", "vertical_calc": "竖式计算",
    "recursive_calc": "脱式计算", "smart_calc": "简便计算", "number_split": "数的分成",
    "compare": "比大小", "true_false": "判断题", "word_problem": "应用题",
}
STYLES = {"playful": "清新彩色，搭配少量童趣插画，装饰不能抢占答题空间",
          "clean": "简洁清爽，浅色点缀，文字与图示层次分明",
          "black_white": "纯白背景、黑色文字与线条，适合黑白打印，不使用大面积底色；题意不能依赖颜色辨别"}
TYPE_RULES = {
    "quiz": "选择题：每题一个问题、3至4个完整选项；只有一个正确选项，其他选项有明确错误原因。",
    "challenge": "闯关挑战：每关一个独立问题、3至4个选项；只有一个正确选项，关卡数就是题数。",
    "fill_blank": "填空题：每题一个完整语境和一个待填空，不把一组互不相关的小题算成一道。方法填空可保留同一算式的待补步骤。",
    "oral_math": "口算题：一道题就是一个待计算的算式和一个答案空格，末尾仅保留等号和空格；不擅自改成看图列式或增加附属算式。",
    "vertical_calc": "竖式计算：一道题一个算式，数位对齐并保留竖式书写区，不预填计算结果。",
    "recursive_calc": "脱式计算：一道题一个完整算式，运算顺序明确，留足分步计算空间。",
    "smart_calc": "简便计算：一道题一个算式，确实可以运用已学运算规律简算，留出计算空间。",
    "number_split": "数的分成：每题一个总数与两个部分，只空缺一个部分，两个部分之和等于总数。",
    "compare": "比大小：每题两个完整数值或算式，中间仅留一个比较符号空格。",
    "true_false": "判断题：每题一个完整、可判断真假的命题，留空让学生判断，不预画对错标记。",
    "word_problem": "应用题：每题一个完整情境和一个问题；条件充分、数量关系和单位一致，保留列式及作答区。",
    "reading": "阅读理解：题数指阅读后的独立问题数，不是文章篇数或板块数；同一篇短文可配多题。正文必须完整可读，问题都能从正文找到依据，不虚构教材原文。引用某句话时在题干中完整引用，避免依赖画线、圈字或颜色等可能漏画的标记。",
    "match_pair": "连线配对：一组配对算一道题，每组3对；左右项目一一对应、右侧打乱顺序，不能预画答案连线，组与组清楚分隔。",
}
SUBJECT_RULES = {
    "数学": "核对运算顺序、数值范围、单位及数量关系；先算出每题答案并代回验证，检查过程和答案不画在学生页。",
    "语文": "简体中文，字形、拼音声调与词义准确；多音字和词义题给足语境。原创材料不能冒称课文原文，未提供的课文正文不得自行补写。",
    "英语": "使用适龄英语，拼写、大小写、标点和语法准确；选择与补全题有足够上下文，避免多个答案同时成立。必要说明可用简体中文。",
}


def allowed_types(grade: str, subject: str) -> list[str]:
    """与工作台题型选择保持相同的学科和年级边界。"""
    number = _grade_num(grade)
    if subject == "数学":
        kinds = set(TYPE_NAMES)
        if number < 3:
            kinds.discard("reading")
        else:
            kinds -= {"number_split", "compare"}
        if number < 2:
            kinds.discard("challenge")
    elif subject in ("语文", "英语"):
        kinds = {"quiz", "fill_blank", "match_pair"}
        if number >= 3:
            kinds.add("reading")
        if number >= (3 if subject == "语文" else 5):
            kinds.add("challenge")
    else:
        kinds = set()
    return [kind for kind in TYPE_NAMES if kind in kinds and number >= MIN_GRADE_FOR_TYPE.get(kind, 0)]


def build_prompt(request: ImageWorksheetRequest) -> str:
    scope = knowledge_scope_service.get_scope(request.grade, request.subject)
    if not scope.allowed:
        raise HTTPException(400, detail={"error": "暂不支持所选年级与科目"})
    allowed = allowed_types(request.grade, request.subject)
    for item in request.items:
        if item.game_type.value not in allowed:
            raise HTTPException(400, detail={"error": f"{request.grade}{request.subject}暂不适合{TYPE_NAMES[item.game_type.value]}"})
    kinds = [item.game_type.value for item in request.items] or allowed
    pure_calculation = bool(request.items) and set(kinds) <= {"oral_math", "vertical_calc", "recursive_calc", "smart_calc", "compare"}
    visual_request = any(word in request.keyword + request.requirements for word in ("看图", "图示", "数量图", "数一数"))
    text_only = pure_calculation and not visual_request
    phonetic = request.subject == "语文" and any(word in request.keyword for word in ("多音字", "读音", "拼音", "字音"))
    rules = [TYPE_RULES[kind] for kind in kinds]
    if phonetic:
        rules = [rule.replace("3至4个", "2个") for rule in rules]
        rules.append("字音选择题：在完整词语或句子中标出待辨读的汉字，选项只列该字的两个候选读音，"
                     "不附加其他汉字或词语来提示答案。多音字专项只使用确有多个读音的汉字，"
                     "不能拿单音字或不同汉字的拼音冒充多音字；声调、声母和韵母均需核对。")
    items = "；".join(f"{TYPE_NAMES[item.game_type.value]} {item.question_count} 道" if item.question_count is not None
                     else f"{TYPE_NAMES[item.game_type.value]}（题量自动安排）" for item in request.items)
    items = items or f"自动安排：从适龄题型（{'、'.join(TYPE_NAMES[kind] for kind in allowed)}）中选择 1 至 5 种"
    automatic = not request.items or any(item.question_count is None for item in request.items)
    quantity = ("已指定的题量必须准确落实；未指定题量的题型每种至少1道、最多20道，整张合计不超过 24 道。"
                "自动题量优先安排4至8个作答任务；阅读、应用、连线和竖式题按书写空间减少数量，不用缩小字号凑数。"
                if automatic else "每种题量都必须准确落实。")
    total = sum(item.question_count or 0 for item in request.items)
    if not automatic:
        quantity += f"整页恰好{total}道题，逐题编号1至{total}；大标题、板块标题和装饰不计题数，不附加练习或例题。"
    page = request.image_index - 1
    contexts = ("校园与文具", "家庭与生活用品", "自然与植物", "运动与游戏", "阅读与图书", "出行与日常安排")
    angle = ("直接运用", "更换已知条件", "辨别易混情况", "迁移到新情境")
    variation = ("本页通过更换算式数值和顺序增加变化，保持纯计算题。" if text_only else
                 f"本页可选情境：{contexts[page % len(contexts)]}；变化方向：{angle[(page // len(contexts)) % len(angle)]}。")
    series = (f"【本组图片】\n共 {request.image_count} 张，这是第 {request.image_index} 张。"
              "本次只生成这一张完整习题图，不要把多张图拼在一起。题型及题量都是每张的要求。"
              f"{variation}"
              "仅在适合知识点和题型时采用，纯计算题保持算式；改变数值和表述，不能因变化而超纲或改题量。\n\n"
              if request.image_count > 1 else "")
    keyword = request.keyword or "自动安排：从允许范围中选择1至3个本年级核心知识点，优先基础巩固"
    graphics = ("本页是纯计算练习。每道题的区域只放题号、算式和空白作答区；算式周围保持空白。"
                "装饰仅放在页眉或页脚，与题目隔开。装饰不能被误当成计数对象。" if text_only else
                "只有题目需要看图解答时才画教学图示。逐个清点对象，图示数量、分组与题干和算式完全一致；"
                "加法清楚分出两组，减法画出原有总数并明确划掉或标出拿走的对象。几何图形、钟表与刻度必须准确。"
                "装饰与解题区域分开，装饰不能被误当成计数对象。")
    return (
        "请直接生成一张完整、清晰、可打印的小学生习题图片。输出成品图片。\n\n"
        "【必须遵守的出题条件】\n"
        f"年级：{request.grade}\n科目：{request.subject}\n知识点：{keyword}\n"
        f"{_textbook_context(scope, request.keyword)}\n题型及题量：{items}\n"
        f"难度：{DIFFICULTY_RULES[request.difficulty.value]}\n\n{series}"
        "【内容与题量】\n题目符合年级、科目和知识点，每种选定题型都必须出现；已指定条件不得擅自替换。"
        f"{quantity}每个独立作答任务计一道题，不能把多个独立问题放在同一编号下以凑题数。\n"
        + "\n".join(rules)
        + f"\n{SUBJECT_RULES[request.subject]}\n允许的知识范围：{'、'.join(scope.allowed)}\n"
        f"禁止的超纲内容：{'、'.join(scope.forbidden) or '不得超出以上已核对范围'}\n\n"
        f"【图示与文字】\n{graphics}"
        "简体中文、数字、符号及英文清晰完整，不使用伪文字、乱码和模糊小字。\n\n"
        "【学生作答页】\n不显示答案或解析，不使用勾选、着色、加粗或预先连线提示正确答案。"
        "为书写、计算、连线预留空间；内容较多时优先删减装饰和缩短非必要说明，不能减少指定题数或挤压文字。\n\n"
        f"【画面要求】\n视觉风格：{STYLES[request.style]}。\n"
        "自主设计标题和布局，不使用工作台的试卷模板或排版参数。标题自然体现主题，题号连续，"
        "对比充分、内容不裁切、四周留白；不要设备外框、拍照场景、水印或无关标识。\n\n"
        f"【用户补充偏好】\n{request.requirements or '无'}\n"
        "补充偏好不能改变年级、科目、知识点、题型、题量、视觉风格和学生页不泄露答案的约束。\n\n"
        "【出图前核对】\n逐题检查实际题数、文字与符号、可解性、图文对应、答案遮蔽、重复题和书写空间。"
        "检查不通过先改正再出图；检查记录和教材资源号不要画进成品。"
        + ("最后确认：题目区域只有题号、算式与作答空格，所有装饰集中在页眉页脚。" if text_only else "")
    )
