from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional, Union
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
    QUIZ = "quiz"                # 选择题
    FILL_BLANK = "fill_blank"    # 填空题
    MATCH_PAIR = "match_pair"    # 连线配对
    CHALLENGE = "challenge"      # 闯关模式
    ORAL_MATH = "oral_math"      # 口算挑战
    READING = "reading"          # 阅读理解
    VERTICAL_CALC = "vertical_calc"   # 竖式计算
    RECURSIVE_CALC = "recursive_calc" # 脱式计算
    SMART_CALC = "smart_calc"         # 简便计算
    NUMBER_SPLIT = "number_split"     # 数的分成
    COMPARE = "compare"             # 比大小
    TRUE_FALSE = "true_false"        # 判断题
    WORD_PROBLEM = "word_problem"    # 应用题（解决问题）


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
    question_count: int = Field(5, ge=1, le=30, description="生成题目数（1-30，单次 LLM 调用过大题量质量难保证）")
    stream: bool = Field(False, description="是否流式返回")
    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None


class ValidateRequest(BaseModel):
    """超纲校验请求"""
    grade: Grade
    subject: Subject
    question_content: str = Field(..., description="待校验的题目内容")


class BatchItem(BaseModel):
    """批量生成里的单个题型任务"""
    game_type: str  # 自定义题型名可能是任意字符串，不用枚举约束
    question_count: int = Field(5, ge=1, le=30)


class BatchGenerateRequest(BaseModel):
    """批量生成整张试卷的请求（一次 LLM 调用出多个题型）"""
    grade: Grade
    subject: Subject
    keyword: str = Field(..., min_length=1, max_length=100)
    difficulty: Difficulty = Field(Difficulty.MEDIUM)
    items: List[BatchItem] = Field(..., min_items=1, max_items=10)
    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None


class FeedbackRequest(BaseModel):
    """用户反馈请求"""
    game_id: str = Field(..., description="游戏/题目 ID")
    is_oob: bool = Field(False, description="是否超纲")
    comment: Optional[str] = Field(None, description="反馈备注")


# ─── 响应模型 ───

class Question(BaseModel):
    """单道题目"""
    id: Optional[int] = None
    type: str = ""
    stem: str = ""  # 题干（数的分成/比大小等特殊题型可能无题干）
    options: Optional[List[str]] = None       # 选择题的选项
    left_items: Optional[List[str]] = None    # 连线配对题左栏
    right_items: Optional[List[str]] = None   # 连线配对题右栏
    top: Optional[Union[int, str]] = None     # 数的分成：顶部数字（__ 表示填空）
    left: Optional[Union[int, str]] = None    # 数的分成：左下数字（__ 表示填空）
    right: Optional[Union[int, str]] = None   # 数的分成：右下数字（__ 表示填空）
    left_expr: Optional[str] = None           # 比大小：左边表达式
    right_expr: Optional[str] = None          # 比大小：右边表达式
    answer: Union[str, int, float, List[List[int]]]  # 正确答案（口算题可能是小数；配对题为索引数组）
    analysis: str = ""                        # 解析
    tags: List[str] = []                      # 知识点标签
    difficulty_level: Optional[int] = None    # 闯关题的关卡
    expected_time_seconds: Optional[int] = None  # 口算题的建议用时（秒）


class GameResult(BaseModel):
    """LLM 生成结果"""
    game_type: str
    topic: str
    difficulty: str
    grade: str
    subject: str
    questions: List[Question]
    total_score: int = 100
    pass_score: int = 60
    missing_count: int = 0  # 质检拦截后补生成仍缺的题数（>0 时前端应提示重试）


class BatchGenerateResponse(BaseModel):
    """批量生成结果：每项对应一个题型的一套题"""
    sections: List[GameResult] = []


class ValidateResult(BaseModel):
    """超纲校验结果"""
    is_oob: bool                               # 是否超纲
    oob_points: List[str] = []                 # 超纲的知识点
    suggestion: Optional[str] = None           # 修改建议


class KnowledgeScope(BaseModel):
    """知识范围信息"""
    grade: str
    subject: str
    allowed: List[str]
    forbidden: List[str]
    semesters: Optional[Dict[str, List[str]]] = None  # 按学期划分的知识点（上册/下册）


class SubjectGrades(BaseModel):
    """某科目的所有年级知识范围"""
    subject: str
    grades: Dict[str, KnowledgeScope]


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None
