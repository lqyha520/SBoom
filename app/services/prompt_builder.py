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
1. 语言生动有趣，符合{grade}学生的认知水平和生活经验
2. 题目场景尽量贴近学生的日常生活（校园、家庭、游戏等）
3. 题目必须严格在允许的知识范围内，绝不超纲
4. 难度级别：{difficulty}
5. 生成{question_count}道题目
6. 每题必须附带：正确答案、详细解析（用学生能理解的方式写）、知识点标签
7. 题干要有趣味性，可加入角色对话、趣味场景等元素

## 输出格式要求
严格按以下 JSON 格式返回，不要输出任何额外文字、markdown标记或代码块包裹。直接输出纯 JSON：

{output_schema}

## 重要提醒
- 只输出 JSON，不要有 ```json``` 包裹
- 答案如果是选择题，answer 字段填选项索引（从0开始）
- 解析要写得像个亲切的老师在讲解，不要生硬
"""

# ─── 各类型中文描述 ───

GAME_TYPE_DESC = {
    "quiz": "选择题（每题4个选项，只有一个正确答案）",
    "fill_blank": "填空题（题干中留空，让学生填写关键词语、数字或公式）",
    "match_pair": "连线配对题（给出左右两组内容，让学生连线配对，如概念-定义）",
    "challenge": "闯关模式（由易到难排列的多道题目，每道题通关后才能进入下一题）",
    "oral_math": "口算挑战（限时心算题目，以四则运算为主）",
    "reading": "阅读理解（给出一段短文，后面跟理解性问题）",
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
      "options": ["A选项", "B选项", "C选项", "D选项"],
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
      "options": ["A", "B", "C", "D"],
      "answer": 0,
      "analysis": "解析",
      "tags": ["标签"]
    },
    {
      "id": 2,
      "type": "multiple_choice",
      "difficulty_level": 2,
      "stem": "中等题题干",
      "options": ["A", "B", "C", "D"],
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
      "stem": "计算：25 + 38 = ？",
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
      "options": ["A", "B", "C", "D"],
      "answer": 0,
      "analysis": "在短文中的依据",
      "tags": ["阅读理解"]
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

        return SYSTEM_PROMPT_TEMPLATE.format(
            subject=request.subject.value,
            grade=request.grade.value,
            scope_text=scope_text,
            game_type_desc=game_type_desc,
            difficulty=request.difficulty.value,
            question_count=request.question_count,
            output_schema=output_schema,
        )

    @staticmethod
    def build_user_message(keyword: str) -> str:
        """构建用户消息"""
        return f'请围绕知识点"{keyword}"出题。直接返回 JSON，不要加任何额外说明。'


# 全局单例
prompt_builder = PromptBuilder()
