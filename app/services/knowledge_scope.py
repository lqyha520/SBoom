"""知识范围约束服务 —— 加载并查询各年级/各科的知识范围"""

import json
from pathlib import Path
from typing import List, Optional

from app.models import Grade, Subject, KnowledgeScope, SubjectGrades


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

    def get_scope(self, grade: Grade, subject: Subject) -> KnowledgeScope:
        """获取指定年级和科目的知识范围"""
        grade_data = self._data.get(grade.value, {})
        subject_data = grade_data.get(subject.value, {})

        if not subject_data:
            return KnowledgeScope(
                grade=grade.value,
                subject=subject.value,
                allowed=[],
                forbidden=[],
            )

        return KnowledgeScope(
            grade=grade.value,
            subject=subject.value,
            allowed=subject_data.get("allowed", []),
            forbidden=subject_data.get("forbidden", []),
            semesters=subject_data.get("semesters") or None,
        )

    def get_all_grades_for_subject(self, subject: Subject) -> SubjectGrades:
        """获取某科目在所有年级的知识范围"""
        grades_map = {}
        for grade_value, subjects in self._data.items():
            if subject.value in subjects:
                scope = subjects[subject.value]
                grades_map[grade_value] = KnowledgeScope(
                    grade=grade_value,
                    subject=subject.value,
                    allowed=scope.get("allowed", []),
                    forbidden=scope.get("forbidden", []),
                    semesters=scope.get("semesters") or None,
                )

        return SubjectGrades(
            subject=subject.value,
            grades=grades_map,
        )

    def get_available_grades(self) -> List[str]:
        """获取所有已定义的年级"""
        return list(self._data.keys())

    def get_available_subjects(self, grade: str) -> List[str]:
        """获取某年级下已定义的科目"""
        grade_data = self._data.get(grade, {})
        return list(grade_data.keys())

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
