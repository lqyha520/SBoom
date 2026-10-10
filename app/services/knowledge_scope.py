"""人教版教材目录范围服务。

生成范围只来自 app/data/pep_catalog.json。历史数据库字典和旧范围文件不再
参与出题，避免把旧版或自由录入的知识点混入模型提示词。
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from app.models import KnowledgeScope, TextbookBook, TextbookUnit


class KnowledgeScopeService:
    """提供已核对教材册次的知识范围。"""

    _instance: Optional["KnowledgeScopeService"] = None
    _catalog: dict = {}

    def __new__(cls) -> "KnowledgeScopeService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        path = Path(__file__).parent.parent / "data" / "pep_catalog.json"
        with path.open(encoding="utf-8") as handle:
            self._catalog = json.load(handle)

    def _books(self, grade: str, subject: str) -> list[dict]:
        return [
            book for book in self._catalog.get("books", [])
            if book.get("grade") == grade and book.get("subject") == subject
            and book.get("status") == "verified"
        ]

    @staticmethod
    def _book_points(book: dict) -> list[str]:
        points: list[str] = []
        for unit in book.get("units", []):
            title = str(unit.get("title", "")).strip()
            if title:
                points.append(title)
            for topic in unit.get("topics", []):
                topic = str(topic).strip()
                if topic:
                    points.append(topic)
        return points

    def get_scope(self, grade: str, subject: str) -> KnowledgeScope:
        """返回指定年级、科目已由官方教材目录核对的知识点。"""
        books = self._books(grade, subject)
        semesters: dict[str, list[str]] = {}
        allowed: list[str] = []
        for book in books:
            points = self._book_points(book)
            semester = str(book.get("semester", "")).strip()
            semesters[semester] = list(dict.fromkeys(semesters.get(semester, []) + points))
            allowed.extend(points)
        allowed = list(dict.fromkeys(allowed))
        return KnowledgeScope(
            grade=grade,
            subject=subject,
            allowed=allowed,
            forbidden=[],
            semesters=semesters or None,
            catalog_revision=self._catalog["revision"],
            books=[TextbookBook(
                id=book["id"], semester=book["semester"],
                series=self._catalog["series"][subject],
                source_url=f"https://book.pep.com.cn/{book['id']}/",
                verified_on=book["verified_on"],
                units=[TextbookUnit(**unit) for unit in book["units"]],
            ) for book in books],
        )

    def is_supported(self, grade: str, subject: str) -> bool:
        return bool(self._books(grade, subject))

    def available_pairs(self) -> set[tuple[str, str]]:
        return {
            (book["grade"], book["subject"])
            for book in self._catalog.get("books", [])
            if book.get("status") == "verified"
        }

    @staticmethod
    def require_selected_semesters(scope: KnowledgeScope, keyword: str) -> None:
        semesters = {book.semester for book in scope.books}
        for semester in ("上册", "下册"):
            if semester in keyword and semester not in semesters:
                raise HTTPException(400, detail={
                    "code": "textbook_not_verified",
                    "error": f"{scope.grade}{scope.subject}{semester}教材目录尚未核实，暂不能据此出题",
                })

    def format_scope_for_prompt(self, scope: KnowledgeScope) -> str:
        """将已核对的教材范围格式化为内部提示文本。"""
        allowed_text = "、".join(scope.allowed) if scope.allowed else "（当前册次尚未核对）"
        result = (
            f"当前学生年级：{scope.grade}\n"
            f"科目：{scope.subject}\n"
            f"人教版教材知识点：{allowed_text}"
        )
        if scope.semesters:
            for semester, points in scope.semesters.items():
                result += f"\n{semester}：{'、'.join(points)}"
        return result


knowledge_scope_service = KnowledgeScopeService()
