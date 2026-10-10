from enum import Enum
from typing import Annotated, Dict, List, Optional, Union

from pydantic import BaseModel, Field, model_validator


# 年级/科目不再用枚举：三端共用后台字典（site_dictionary 表）为唯一数据源，
# 请求侧为自由字符串，由 knowledge_scope（能力校验）拦截不支持的组合。


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
    grade: str = Field(..., min_length=1, max_length=20, description="年级（来自后台字典）")
    subject: str = Field(..., min_length=1, max_length=20, description="科目（来自后台字典）")
    keyword: str = Field(..., description="知识点关键词", min_length=1, max_length=100)
    game_type: GameType = Field(GameType.QUIZ, description="交互类型")
    difficulty: Difficulty = Field(Difficulty.MEDIUM, description="难度")
    question_count: int = Field(5, ge=1, le=30, description="生成题目数（1-30，单次 LLM 调用过大题量质量难保证）")
    stream: bool = Field(False, description="是否流式返回")
    # 注：不提供客户端可控的 llm_base_url/llm_model/llm_api_key——
    # 模型服务统一由管理员在后台配置，避免 SSRF（服务器被指任意地址）与越权绕过。


class ValidateRequest(BaseModel):
    """超纲校验请求"""
    grade: str = Field(..., min_length=1, max_length=20)
    subject: str = Field(..., min_length=1, max_length=20)
    question_content: str = Field(..., max_length=5000, description="待校验的题目内容")


class BatchItem(BaseModel):
    """批量生成里的单个题型任务"""
    game_type: str = Field(min_length=1, max_length=80)
    section_id: Optional[str] = Field(None, min_length=1, max_length=80)
    question_count: int = Field(5, ge=1, le=30)


class BatchGenerateRequest(BaseModel):
    """批量生成整张试卷的请求（一次 LLM 调用出多个题型）"""
    grade: str = Field(..., min_length=1, max_length=20)
    subject: str = Field(..., min_length=1, max_length=20)
    keyword: str = Field(..., min_length=1, max_length=100)
    difficulty: Difficulty = Field(Difficulty.MEDIUM)
    items: List[BatchItem] = Field(..., min_length=1, max_length=10)
    previous_request_ids: list[Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")]] = Field(
        default_factory=list, max_length=60, description="本卷前序已完成请求；仅从当前账号的保存结果读取避重上下文")

    @model_validator(mode="after")
    def unique_section_ids(self):
        ids = [item.section_id or f"section-{i + 1}" for i, item in enumerate(self.items)]
        if len(ids) != len(set(ids)):
            raise ValueError("section_id must be unique within a batch")
        return self


class FeedbackRequest(BaseModel):
    """用户反馈请求"""
    game_id: str = Field(..., max_length=200, description="游戏/题目 ID")
    is_oob: bool = Field(False, description="是否超纲")
    comment: Optional[str] = Field(None, max_length=2000, description="反馈备注")


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
    acceptable_answers: Optional[List[str]] = None
    analysis: str = ""                        # 解析
    tags: List[str] = []                      # 知识点标签
    difficulty_level: Optional[int] = None    # 闯关题的关卡
    expected_time_seconds: Optional[int] = None  # 口算题的建议用时（秒）


class GameResult(BaseModel):
    """LLM 生成结果"""
    game_type: str
    section_id: Optional[str] = None
    request_id: Optional[str] = None
    topic: str
    passage: Optional[str] = None
    difficulty: str
    grade: str
    subject: str
    questions: List[Question]
    total_score: int = 100
    pass_score: int = 60
    missing_count: int = 0  # 质检拦截后补生成仍缺的题数（>0 时前端应提示重试）
    quality_warnings: List[str] = Field(default_factory=list)


class BatchGenerateResponse(BaseModel):
    """批量生成结果：每项对应一个题型的一套题"""
    sections: List[GameResult] = []
    request_id: Optional[str] = None


class ValidateResult(BaseModel):
    """超纲校验结果"""
    is_oob: bool                               # 是否超纲
    oob_points: List[str] = []                 # 超纲的知识点
    suggestion: Optional[str] = None           # 修改建议
    request_id: Optional[str] = None


class TextbookUnit(BaseModel):
    title: str
    page: int
    topics: list[str] = Field(default_factory=list)


class TextbookBook(BaseModel):
    id: str
    semester: str
    series: str
    source_url: str
    verified_on: str
    units: list[TextbookUnit]


class KnowledgeScope(BaseModel):
    """知识范围信息"""
    grade: str
    subject: str
    allowed: List[str]
    forbidden: List[str]
    semesters: Optional[Dict[str, List[str]]] = None  # 按学期划分的知识点（上册/下册）
    catalog_revision: str = ""
    books: list[TextbookBook] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None
