"""知识范围约束服务 —— 查询各年级/各科的知识范围

数据来源分两层：
- 知识点字典（site_dictionary 里 kind='knowledge_point' 的行，parent=「年级id|科目id」）：
  后台可编辑，是「允许涉及」的权威来源；组合下有可见知识点时优先生效；
- knowledge_scope.json：兜底与补充（组合尚无知识点时的 allowed，以及 forbidden/semesters）。
"""

import json
from pathlib import Path
from typing import Optional

from app.models import KnowledgeScope


class KnowledgeScopeService:
    """提供知识范围查询能力"""

    _instance: Optional["KnowledgeScopeService"] = None
    _data: dict = {}

    def __new__(cls) -> "KnowledgeScopeService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        data_path = Path(__file__).parent.parent / "data" / "knowledge_scope.json"
        with open(data_path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    def _dictionary_points(self, grade: str, subject: str) -> list[str]:
        """后台知识点字典里该组合的可见知识点（按展示顺序）。"""
        from app.db import db

        with db() as conn:
            rows = conn.execute(
                "SELECT p.value FROM site_dictionary p "
                "JOIN site_dictionary g ON g.kind = 'grade' AND g.value = ? "
                "JOIN site_dictionary s ON s.kind = 'subject' AND s.value = ? "
                "WHERE p.kind = 'knowledge_point' AND p.is_visible = 1 AND p.parent = g.id || '|' || s.id "
                "ORDER BY p.sort_order, p.value", (grade, subject)).fetchall()
        return [row["value"] for row in rows]

    def get_scope(self, grade: str, subject: str) -> KnowledgeScope:
        """获取指定年级和科目的知识范围（grade/subject 为后台字典中的字符串值）"""
        grade_data = self._data.get(grade, {})
        subject_data = grade_data.get(subject, {})
        points = self._dictionary_points(grade, subject)

        if not subject_data and not points:
            return KnowledgeScope(grade=grade, subject=subject, allowed=[], forbidden=[])

        return KnowledgeScope(
            grade=grade,
            subject=subject,
            allowed=points or subject_data.get("allowed", []),
            forbidden=subject_data.get("forbidden", []),
            semesters=subject_data.get("semesters") or None,
        )

    def format_scope_for_prompt(self, scope: KnowledgeScope) -> str:
        """将知识范围格式化为 Prompt 可用的文本"""
        allowed_text = "、".join(scope.allowed) if scope.allowed else "（无特殊限制）"
        forbidden_text = "、".join(scope.forbidden) if scope.forbidden else "（无明确禁止项）"

        result = (
            f"当前学生年级：{scope.grade}\n"
            f"科目：{scope.subject}\n"
            f"允许涉及的知识点范围：{allowed_text}\n"
            f"严禁涉及（超纲）的知识点：{forbidden_text}"
        )

        # 按学期划分的知识点（如上册/下册），帮助 LLM 根据关键词判断学期范围
        if scope.semesters:
            for sem, points in scope.semesters.items():
                if points:
                    result += f"\n{sem}知识点：{'、'.join(points)}"
            result += "\n请根据知识点关键词判断用户要出上册还是下册的题，只出对应学期的内容；若无法判断，则严格限定在上面列出的总范围内。"

        return result


# 全局单例
knowledge_scope_service = KnowledgeScopeService()
