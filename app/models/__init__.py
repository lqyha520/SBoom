from pydantic import BaseModel, Field
from typing import Literal, Optional, Union
from enum import Enum


# ─── 枚举定义 ───

class Grade(str, Enum):
    """年级"""
    G1 = "小学一年级"
    G2 = "小学二年级"
    G3 = "小学三年级"
    G4 = "小学四年级"
    G5 = "小学五年级"
    G6 = "小学六年级"
    J7 = "初中一年级"
    J8 = "初中二年级"
    J9 = "初中三年级"


class Subject(str, Enum):
    """科目"""
    MATH = "数学"
    CHINESE = "语文"
    ENGLISH = "英语"
    SCIENCE = "科学"
    PHYSICS = "物理"
    CHEMISTRY = "化学"
    BIOLOGY = "生物"


class GameType(str, Enum):
    """交互类型"""
    QUIZ = "quiz"              # 选择题
    FILL_BLANK = "fill_blank"  # 填空题
    MATCH_PAIR = "match_pair"  # 连线配对
    CHALLENGE = "challenge"    # 闯关模式
    ORAL_MATH = "oral_math"    # 口算挑战
    READING = "reading"        # 阅读理解


class Difficulty(str, Enum):
    """难度"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# ─── 请求模型 ───

class GenerateRequest(BaseModel):
    """题目/游戏生成请求"""
    grade: Grade = Field(..., description="年级")
    subject: Subject = Field(..., description="科目")
    keyword: str = Field(..., description="知识点关键词", min_length=1, max_length=100)
    game_type: GameType = Field(GameType.QUIZ, description="交互类型")
    difficulty: Difficulty = Field(Difficulty.MEDIUM, description="难度")
    question_count: int = Field(5, ge=1, le=10, description="生成题目数（1-10）")
    use_cache: bool = Field(True, description="是否使用缓存")
    stream: bool = Field(False, description="是否流式返回")


class ValidateRequest(BaseModel):
    """超纲校验请求"""
    grade: Grade
    subject: Subject
    question_content: str = Field(..., description="待校验的题目内容")


class FeedbackRequest(BaseModel):
    """用户反馈请求"""
    game_id: str = Field(..., description="游戏/题目 ID")
    is_oob: bool = Field(False, description="是否超纲")
    comment: Optional[str] = Field(None, description="反馈备注")


# ─── 响应模型 ───

class Question(BaseModel):
    """单道题目"""
    id: int
    type: str
    stem: str
    options: Optional[list[str]] = None       # 选择题的选项
    answer: Union[str, int]                     # 正确答案
    analysis: str                              # 解析
    tags: list[str] = []                       # 知识点标签


class GameResult(BaseModel):
    """LLM 生成结果"""
    game_type: str
    topic: str
    difficulty: str
    grade: str
    subject: str
    questions: list[Question]
    total_score: int = 100
    pass_score: int = 60
    from_cache: bool = False
    cache_key: Optional[str] = None


class ValidateResult(BaseModel):
    """超纲校验结果"""
    is_oob: bool                               # 是否超纲
    oob_points: list[str] = []                 # 超纲的知识点
    suggestion: Optional[str] = None           # 修改建议


class KnowledgeScope(BaseModel):
    """知识范围信息"""
    grade: str
    subject: str
    allowed: list[str]
    forbidden: list[str]


class SubjectGrades(BaseModel):
    """某科目的所有年级知识范围"""
    subject: str
    grades: dict[str, KnowledgeScope]


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None
