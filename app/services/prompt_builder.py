"""Prompt 组装器 —— 根据用户输入 + 知识范围约束组装最终 System Prompt"""

from app.models import GenerateRequest, KnowledgeScope


# ─── System Prompt 模板 ───

SYSTEM_PROMPT_TEMPLATE = """你是一位专业的{subject}教育游戏设计师，面向{grade}学生。

## 你的任务
根据学生提供的知识点关键词，生成一套趣味互动题目。

## 知识范围约束
{scope_text}

## 目标互动类型：{game_type_desc}

## 出题要求
1. 题目必须严格在允许的知识范围内，绝不超纲
2. 难度级别：{difficulty}
3. 生成{question_count}道题目
4. 每题必须附带：正确答案、详细解析（用学生能理解的方式写）、知识点标签
{style_requirements}

## 输出格式要求
严格按以下 JSON 格式返回，不要输出任何额外文字、markdown标记或代码块包裹。直接输出纯 JSON：

{output_schema}

## 重要提醒
- 只输出 JSON，不要有 ```json``` 包裹
- 答案如果是选择题，answer 字段填选项索引（从0开始）
- 解析要写得像个亲切的老师在讲解，不要生硬
"""

# ─── 出题风格块：计算类 = 纯算式，其他 = 按年级控制语言复杂度 ───

# 低年级（一二年级）识字量有限，题干必须极简短
LOW_GRADE_LANG = """5. 【硬性要求·低年级识字量约束】{grade}学生识字量很少（约300字以内）：
   - 题干控制在 15 个字以内，一句话说清
   - 只用最常见的字词，禁止出现成语、书面语、复杂修饰
   - 选择题选项每项不超过 6 个字
   - 能用数字/算式表达的，绝不用文字描述
   - 严禁长段文字、严禁故事铺垫（如"小明今天去超市买了很多东西……"这种禁止）"""

# 中年级（三四年级）识字量中等
MID_GRADE_LANG = """5. 语言简洁明了，符合{grade}学生的阅读水平：
   - 题干控制在 30 个字以内
   - 场景贴近学生日常生活（校园、家庭、游戏）
   - 避免复杂长句和生僻字"""

# 高年级（五六年级）可以有适度的场景描述
HIGH_GRADE_LANG = """5. 语言生动有趣，符合{grade}学生的认知水平：
   - 题干控制在 50 个字以内
   - 场景贴近学生生活，可加入角色对话等趣味元素
   - 但不要为了趣味而加无关的冗长铺垫"""

STYLE_REQUIREMENTS = {
    "calc": """5. 【硬性要求】题目只能是纯算式，禁止出现任何中文文字！
   - 口算题干形如：25 + 38 =  （只要一个等式，不要"小兔子""胡萝卜"等任何场景或故事）
   - 竖式计算：345 + 278 =  、  62 ÷ 2 =
   - 脱式计算：128 + 72 × 3 =
   - 简便计算：25 × 44 =
   - 题干里绝对不能出现汉字（"计算：""用竖式计算："这类引导词也不要），只允许数字和运算符号
   - 小朋友识字量有限，看到中文就做不了题了，纯数字最友好""",
    "story": "{grade_lang}",  # 按年级动态替换
}

# 题型的最低年级限制（防止低年级出现超纲题型）
MIN_GRADE_FOR_TYPE = {
    "vertical_calc": 1,   # 竖式：一年级下册起（100以内加减法）
    "recursive_calc": 3,  # 脱式：三年级起
    "smart_calc": 4,      # 简便计算：四年级起（运算定律）
    "word_problem": 1,    # 应用题：一年级起（解决问题）
}

def _grade_num(grade: str) -> int:
    # 初中年级 → 7/8/9（不限制题型）
    if "初中" in grade or "初一" in grade or "初二" in grade or "初三" in grade:
        for ch in grade:
            if ch in "一二三":
                return 6 + {"一": 1, "二": 2, "三": 3}[ch]
        return 9
    for ch in grade:
        if ch in "一二三四五六":
            return {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6}[ch]
    return 9  # 未知默认不限制

# 年级 → 语言约束档次（1-2 低，3-4 中，5-6 高；初中按高年级处理）
def _lang_block_for_grade(grade: str) -> str:
    grade_num = 0
    for ch in grade:
        if ch in "一二三四五六":
            grade_num = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6}[ch]
            break
    if 1 <= grade_num <= 2:
        return LOW_GRADE_LANG
    elif 3 <= grade_num <= 4:
        return MID_GRADE_LANG
    else:
        return HIGH_GRADE_LANG

# 难度中文映射
DIFFICULTY_CN = {"easy": "简单（基础巩固）", "medium": "中等（课堂同步）", "hard": "困难（拓展冲刺）"}

CALC_TYPES = {"oral_math", "vertical_calc", "recursive_calc", "smart_calc"}


# ─── 各类型中文描述 ───

GAME_TYPE_DESC = {
    "quiz": "选择题（每题4个选项，只有一个正确答案）",
    "fill_blank": "填空题（题干中留空，让学生填写关键词语、数字或公式）",
    "match_pair": "连线配对题（给出左右两组内容，让学生连线配对，如概念-定义）",
    "challenge": "闯关模式（由易到难排列的多道题目，每道题通关后才能进入下一题）",
    "oral_math": "口算挑战（限时心算题目，以四则运算为主。题干必须是纯算式如 25 + 38 = ，禁止出现任何汉字）",
    "reading": "阅读理解（给出一段短文，后面跟理解性问题）",
    "vertical_calc": "竖式计算（列竖式计算，加、减、乘、除的笔算题，数字位数符合该年级要求。题干必须是纯算式如 345 + 278 = ，禁止出现任何汉字）",
    "recursive_calc": "脱式计算（递等式计算，四则混合运算，按运算顺序一步步写出过程。题干必须是纯算式如 128 + 72 × 3 = ，禁止出现任何汉字）",
    "smart_calc": "简便计算（运用运算定律，如加法交换律/结合律、乘法交换律/结合律/分配律、减法性质、除法性质等，使计算简便。题干必须是纯算式如 25 × 44 = ，禁止出现任何汉字）",
    "number_split": "数的分成/组成（一年级核心题型，给出一个数字拆成两个数，或给出部分求整体。格式为 top/left/right 三个字段，用____表示填空位置，如 top=9, left=5, right=____ 表示9可以分成5和几）",
    "compare": "比大小（在○里填 >、< 或 =，比较左右两个算式或数字的大小。left_expr 是左边表达式，right_expr 是右边表达式，answer 填 > / < / = 其中之一）",
    "true_false": "判断题（给出一个陈述句，学生判断对错。stem 不要以句号结尾，末尾带（　）括号供学生填写，如 '6 比 1 大（　）'。answer 填 '√'（对）或 '×'（错））",
    "word_problem": "应用题/解决问题（结合生活情境的文字题，需要列式计算并作答。stem 是完整题目描述，answer 是最终答案）",
}


# ─── 各类型的输出 JSON Schema ───

OUTPUT_SCHEMAS = {
    "quiz": """{
  "game_type": "quiz",
  "topic": "知识点主题",
  "questions": [
    {
      "id": 1,
      "type": "multiple_choice",
      "stem": "题干文字",
      "options": ["具体选项内容1", "具体选项内容2", "具体选项内容3", "具体选项内容4"],
      "answer": 0,
      "analysis": "详细解析",
      "tags": ["知识点标签1"]
    }
  ]
}""",
    "fill_blank": """{
  "game_type": "fill_blank",
  "topic": "知识点主题",
  "questions": [
    {
      "id": 1,
      "type": "fill_blank",
      "stem": "含有____的题干（用____表示填空位置）",
      "answer": "正确答案文字",
      "acceptable_answers": ["可接受的等价答案"],
      "analysis": "详细解析",
      "tags": ["知识点标签1"]
    }
  ]
}""",
    "match_pair": """{
  "game_type": "match_pair",
  "topic": "知识点主题",
  "questions": [
    {
      "id": 1,
      "type": "match_pair",
      "left_items": ["左1", "左2", "左3"],
      "right_items": ["右1", "右2", "右3"],
      "answer": [[0,1],[1,2],[2,0]],
      "analysis": "配对依据说明",
      "tags": ["知识点标签1"]
    }
  ]
}""",
    "challenge": """{
  "game_type": "challenge",
  "topic": "知识点主题",
  "questions": [
    {
      "id": 1,
      "type": "multiple_choice",
      "difficulty_level": 1,
      "stem": "简单题题干",
      "options": ["具体选项内容1", "具体选项内容2", "具体选项内容3", "具体选项内容4"],
      "answer": 0,
      "analysis": "解析",
      "tags": ["标签"]
    },
    {
      "id": 2,
      "type": "multiple_choice",
      "difficulty_level": 2,
      "stem": "中等题题干",
      "options": ["具体选项内容1", "具体选项内容2", "具体选项内容3", "具体选项内容4"],
      "answer": 1,
      "analysis": "解析",
      "tags": ["标签"]
    }
  ]
}""",
    "oral_math": """{
  "game_type": "oral_math",
  "topic": "知识点主题",
  "questions": [
    {
      "id": 1,
      "type": "oral_math",
      "stem": "25 + 38 =",
      "answer": 63,
      "expected_time_seconds": 10,
      "analysis": "口算技巧说明",
      "tags": ["两位数加法"]
    }
  ]
}""",
    "reading": """{
  "game_type": "reading",
  "topic": "知识点主题",
  "passage": "阅读短文内容",
  "questions": [
    {
      "id": 1,
      "type": "multiple_choice",
      "stem": "根据短文内容的问题",
      "options": ["具体选项内容1", "具体选项内容2", "具体选项内容3", "具体选项内容4"],
      "answer": 0,
      "analysis": "在短文中的依据",
      "tags": ["阅读理解"]
    }
  ]
}""",
    "vertical_calc": """{
  "game_type": "vertical_calc",
  "topic": "知识点主题",
  "questions": [
    {
      "id": 1,
      "type": "vertical_calc",
      "stem": "345 + 278 =",
      "answer": 623,
      "analysis": "竖式计算过程说明（相同数位对齐，从个位算起，满十进一）",
      "tags": ["三位数加法"]
    }
  ]
}""",
    "recursive_calc": """{
  "game_type": "recursive_calc",
  "topic": "知识点主题",
  "questions": [
    {
      "id": 1,
      "type": "recursive_calc",
      "stem": "128 + 72 × 3 =",
      "answer": 344,
      "analysis": "递等式过程：先算乘法 72×3=216，再算加法 128+216=344",
      "tags": ["四则混合运算"]
    }
  ]
}""",
    "smart_calc": """{
  "game_type": "smart_calc",
  "topic": "知识点主题",
  "questions": [
    {
      "id": 1,
      "type": "smart_calc",
      "stem": "25 × 44 =",
      "answer": 1100,
      "analysis": "简便方法：44 拆成 4×11，25×4=100，100×11=1100（乘法结合律）",
      "tags": ["乘法结合律"]
    }
  ]
}""",
    "number_split": """{
  "game_type": "number_split",
  "topic": "知识点主题",
  "questions": [
    {
      "id": 1,
      "type": "number_split",
      "top": 9,
      "left": 5,
      "right": "__",
      "answer": 4,
      "analysis": "9可以分成5和4"
    },
    {
      "id": 2,
      "type": "number_split",
      "top": "__",
      "left": 3,
      "right": 6,
      "answer": 9,
      "analysis": "3和6组成9"
    }
  ]
}""",
    "compare": """{
  "game_type": "compare",
  "topic": "知识点主题",
  "questions": [
    {
      "id": 1,
      "type": "compare",
      "left_expr": "5+2",
      "right_expr": "8",
      "answer": "<",
      "analysis": "5+2=7，7小于8"
    },
    {
      "id": 2,
      "type": "compare",
      "left_expr": "9-1",
      "right_expr": "7",
      "answer": ">",
      "analysis": "9-1=8，8大于7"
    }
  ]
}""",
}


class PromptBuilder:
    """Prompt 组装器"""

    @staticmethod
    def build_system_prompt(request: GenerateRequest, scope: KnowledgeScope) -> str:
        """根据请求组装完整的 System Prompt"""
        scope_text = (
            f"- 允许涉及的知识点：{'、'.join(scope.allowed)}\n"
            f"- **严禁涉及**（超纲）的知识点：{'、'.join(scope.forbidden)}"
        )

        game_type_desc = GAME_TYPE_DESC.get(request.game_type.value, "选择题")
        output_schema = OUTPUT_SCHEMAS.get(request.game_type.value, OUTPUT_SCHEMAS["quiz"])

        # 计算类 → 纯算式硬约束；其他 → 按年级控制语言复杂度
        if request.game_type.value in CALC_TYPES:
            style_requirements = STYLE_REQUIREMENTS["calc"]
        else:
            style_requirements = _lang_block_for_grade(request.grade.value).format(grade=request.grade.value)

        return SYSTEM_PROMPT_TEMPLATE.format(
            subject=request.subject.value,
            grade=request.grade.value,
            scope_text=scope_text,
            game_type_desc=game_type_desc,
            difficulty=DIFFICULTY_CN.get(request.difficulty.value, request.difficulty.value),
            question_count=request.question_count,
            output_schema=output_schema,
            style_requirements=style_requirements,
        )

    @staticmethod
    def build_user_message(keyword: str) -> str:
        """构建用户消息"""
        return f'请围绕知识点"{keyword}"出题。直接返回 JSON，不要加任何额外说明。'

    @staticmethod
    def build_batch_prompt(grade: str, subject: str, keyword: str, difficulty: str, items, scope=None) -> str:
        """构建批量生成整卷的 Prompt（一次 LLM 调用出多个题型）"""
        item_descs = []
        for i, it in enumerate(items):
            t = it.game_type
            desc = GAME_TYPE_DESC.get(t, "")
            item_descs.append(f"{i + 1}. {t}（{desc}）：{it.question_count} 道题")

        from app.models import GameType
        lang_block = _lang_block_for_grade(grade).format(grade=grade)
        calc_note = "计算类题型（oral_math/vertical_calc/recursive_calc/smart_calc）题干必须是纯算式，禁止汉字。"

        # 知识范围（含上下册学期划分）
        scope_text = ""
        if scope:
            from app.services.knowledge_scope import knowledge_scope_service
            scope_text = knowledge_scope_service.format_scope_for_prompt(scope) + "\n\n"

        # 按题型给出精确字段规范，防止模型输出错误结构
        FIELD_RULES = {
            "number_split": (
                "数的分成 number_split：每道题输出 { id（整数）, type: 'number_split', "
                "top（数字或'____'表示填空）, left（数字或'____'表示填空）, "
                "right（数字或'____'表示填空）, answer（填空对应的数字答案）, analysis（简短解析） }。"
                "示例：{id:1,type:'number_split',top:9,left:5,right:'____',answer:4,analysis:'9可以分成5和4'}。"
                "top 已知时 left/right 有一个是 ____；已知两个填 top 为 ____。"
            ),
            "compare": (
                "比大小 compare：每道题输出 { id（整数）, type: 'compare', "
                "left_expr（左边算式或数字）, right_expr（右边算式或数字）, "
                "answer（填 '>' 或 '<' 或 '='）, analysis（简短解析） }。"
                "示例：{id:1,type:'compare',left_expr:'5+2',right_expr:'8',answer:'<',analysis:'5+2=7，7小于8'}。"
            ),
        }
        field_rules_text = "\n".join(FIELD_RULES.get(it.game_type, "")
                                    for it in items if it.game_type in FIELD_RULES)

        system_prompt = (
            f"你是一位专业的{subject}教育老师，面向{grade}学生。\n"
            f"请围绕知识点「{keyword}」一次生成一张试卷的多个大题。\n\n"
            f"{scope_text}"
            f"## 知识点范围\n"
            f"严格在 {keyword} 相关范围内出题，绝不超纲。\n\n"
            f"## 难度\n{DIFFICULTY_CN.get(difficulty, difficulty)}\n\n"
            f"## 需要生成的大题\n" + "\n".join(item_descs) + "\n\n"
            f"## 出题要求\n"
            f"{lang_block}\n{calc_note}\n"
            f"每题都要带正确答案和解析。\n\n"
            f"## 字段规范（必须严格遵守）\n"
            f"{field_rules_text}\n"
            f"其他题型（quiz/fill_blank/match_pair/oral_math/vertical_calc/recursive_calc/smart_calc/challenge/reading）按各自标准字段结构输出。\n\n"
            f"## 输出格式\n"
            f"所有数学表达式在运算符前后加空格（如 '3 + 5 =' 而不是 '3+5='，'5 + ____ = 9' 而不是 '5+____=9'）。\n"
            f"直接返回纯 JSON，不要 markdown 包裹、不要任何额外文字：\n"
            f'{{"sections": ['
            f'{{"game_type": "对应题目1的英文名", "questions": [各题JSON]}},'
            f'{{"game_type": "对应题目2的英文名", "questions": [各题JSON]}}'
            f']}}\n\n'
            f"每个 section 的 game_type 必须是上面标注的**英文名**（如 number_split、compare），不要中文，不要写错拼写。\n"
            f"口算(oral_math)、填空(fill_blank)、竖式(vertical_calc)、脱式(recursive_calc)、简便(smart_calc)、闯关(challenge)、选择题(quiz)、阅读(reading)这些题型，每道题必须包含 stem（题干）、answer（答案）、analysis（解析）字段。\n"
            f"stem 是题目正文（如 '3+5='、'5+____=9'、'9×7='），不能为空。\n"
            f"questions 数组里的每道题必须严格包含上面对应的所有字段（type 字段也要正确写出英文）。"
        )
        return system_prompt

    @staticmethod
    def build_batch_user_message(keyword: str) -> str:
        return f'请围绕知识点"{keyword}"生成整张试卷。直接返回 JSON。'


# 全局单例
prompt_builder = PromptBuilder()
