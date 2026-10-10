"""新目录的来源与完整性检查，不访问数据库或教材网站。"""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_pep_catalog", ROOT / "scripts" / "check_pep_catalog.py")
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.fixture
def catalog():
    return json.loads((ROOT / "app" / "data" / "pep_catalog.json").read_text(encoding="utf-8"))


def test_catalog_has_all_current_series_book_slots(catalog):
    result = checker.check_catalog(catalog)
    assert result["books"] == 32
    assert result["verified"] == 32
    assert result["pending"] == 0
    assert "三年级起点" in catalog["series"]["英语"]


def test_incomplete_catalog_cannot_be_marked_ready(catalog):
    pending = catalog["books"][-1]
    pending.pop("units")
    pending.pop("toc_image_pages")
    pending.pop("verified_on")
    pending.update(status="pending")
    catalog["status"] = "in_progress"
    with pytest.raises(ValueError, match="不能替换"):
        checker.check_catalog(catalog, require_complete=True)
    pending["units"] = [{"title": "旧知识点", "page": 1}]
    with pytest.raises(ValueError, match="不能混入"):
        checker.check_catalog(catalog)


def test_duplicate_missing_and_unsupported_books_are_rejected(catalog):
    for mutate in (
        lambda data: data["books"].append(deepcopy(data["books"][0])),
        lambda data: data["books"].pop(),
        lambda data: data["books"][-1].update(grade="小学一年级"),
    ):
        invalid = deepcopy(catalog)
        mutate(invalid)
        with pytest.raises(ValueError):
            checker.check_catalog(invalid)


def test_topic_details_require_body_page_evidence(catalog):
    unit = catalog["books"][0]["units"][0]
    unit["topics"] = ["未经正文核对的细分知识点"]
    with pytest.raises(ValueError, match="正文来源"):
        checker.check_catalog(catalog)


def test_verified_new_math_toc_does_not_reuse_old_placement(catalog):
    books = {book["id"]: book for book in catalog["books"]}
    upper = {unit["title"] for unit in books["1221001101241"]["units"]}
    lower = {unit["title"] for unit in books["1221001102241"]["units"]}
    second = {unit["title"] for unit in books["1221001201251"]["units"]}
    assert "认识钟表" not in upper
    assert "100以内的笔算加、减法" in lower
    assert "1～6的表内除法" in second
    assert "7～9的表内乘、除法" in second


def test_scope_is_official_only_and_carries_book_evidence():
    from app.services.knowledge_scope import knowledge_scope_service

    scope = knowledge_scope_service.get_scope("小学一年级", "数学")
    assert len(scope.books) == 2
    assert scope.catalog_revision.startswith("pep-")
    assert "认识钟表（整时和半时）" not in scope.allowed
    assert "100以内的笔算加、减法" in scope.semesters["下册"]
    assert scope.books[0].source_url == "https://book.pep.com.cn/1221001101241/"
    assert not knowledge_scope_service.get_scope("小学一年级", "英语").allowed


def test_prompt_uses_selected_book_and_chinese_question_names():
    from app.models import BatchItem, GenerateRequest
    from app.services.knowledge_scope import knowledge_scope_service
    from app.services.prompt_builder import prompt_builder

    scope = knowledge_scope_service.get_scope("小学一年级", "数学")
    keyword = "下册·认识平面图形·长方形"
    request = GenerateRequest(grade=scope.grade, subject=scope.subject, keyword=keyword, game_type="fill_blank")
    single = prompt_builder.build_system_prompt(request, scope)
    batch = prompt_builder.build_batch_prompt(scope.grade, scope.subject, keyword, "medium",
                                             [BatchItem(game_type="fill_blank", question_count=5)], scope)
    for prompt in (single, batch):
        assert "1221001102241" in prompt
        assert "1221001101241" not in prompt
        assert "填空题" in prompt
        assert "题干简洁" in prompt
        assert "知识点：" + keyword in prompt
        assert "随机" not in prompt


def test_missing_selected_semester_cannot_silently_use_other_book():
    from fastapi import HTTPException

    from app.services.knowledge_scope import knowledge_scope_service

    scope = knowledge_scope_service.get_scope("小学一年级", "数学")
    partial = scope.model_copy(update={"books": [scope.books[0]]})
    with pytest.raises(HTTPException) as error:
        knowledge_scope_service.require_selected_semesters(partial, "下册·认识平面图形")
    assert error.value.detail["code"] == "textbook_not_verified"
