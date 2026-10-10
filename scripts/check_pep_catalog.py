"""核对人教版目录数据；--require-complete 阻止未核实目录进入替换流程。"""

import argparse
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "app" / "data" / "pep_catalog.json"


def check_catalog(data: dict, *, require_complete: bool = False) -> dict:
    if data.get("directory_url") != "https://jc.pep.com.cn/":
        raise ValueError("目录必须来自人教社官方电子教材站")
    date.fromisoformat(data["directory_checked_on"])
    expected = {
        (f"小学{grade}年级", subject, semester)
        for index, grade in enumerate("一二三四五六", 1)
        for subject in ("语文", "数学", "英语")
        for semester in ("上册", "下册")
        if subject != "英语" or index >= 3
    }
    seen: set[tuple[str, str, str]] = set()
    ids: set[str] = set()
    verified = 0
    unit_count = 0
    for book in data["books"]:
        pair = (book["grade"], book["subject"], book["semester"])
        if pair not in expected or pair in seen:
            raise ValueError(f"册次缺失、重复或不属于当前系列：{pair}")
        seen.add(pair)
        book_id = book["id"]
        if not isinstance(book_id, str) or len(book_id) != 13 or not book_id.isascii() or not book_id.isdecimal() or book_id in ids:
            raise ValueError(f"教材资源编号无效或重复：{book_id}")
        ids.add(book_id)
        if book["subject"] not in data["series"]:
            raise ValueError(f"缺少教材系列：{pair}")
        if book["status"] == "pending":
            if book.get("units") or book.get("verified_on"):
                raise ValueError(f"未核实册次不能混入知识点或核对日期：{pair}")
            continue
        if book["status"] != "verified":
            raise ValueError(f"未知核对状态：{pair}")
        date.fromisoformat(book["verified_on"])
        if not book.get("toc_image_pages") or not book.get("units"):
            raise ValueError(f"已核实册次必须有目录页来源和单元：{pair}")
        previous_page = 0
        titles: set[str] = set()
        for unit in book["units"]:
            if not unit["title"].strip() or unit["title"] in titles or unit["page"] <= previous_page:
                raise ValueError(f"单元名称或教材页码异常：{pair}")
            titles.add(unit["title"])
            previous_page = unit["page"]
            if unit.get("topics") and not unit.get("topic_image_pages"):
                raise ValueError(f"细分知识点缺少正文来源：{pair} / {unit['title']}")
            topics = unit.get("topics", [])
            if len(topics) != len(set(topics)) or any(not topic.strip() for topic in topics):
                raise ValueError(f"细分知识点存在重复或空值：{pair}")
        verified += 1
        unit_count += len(book["units"])
    if seen != expected:
        raise ValueError(f"缺少册次：{sorted(expected - seen)}")
    pending = len(expected) - verified
    if data.get("status") != ("in_progress" if pending else "complete"):
        raise ValueError("目录整体状态与逐册核对状态不一致")
    if require_complete and pending:
        raise ValueError(f"还有 {pending} 册未核实，不能替换当前目录")
    return {"books": len(seen), "verified": verified, "pending": pending, "units": unit_count}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        result = check_catalog(json.loads(CATALOG.read_text(encoding="utf-8")), require_complete=args.require_complete)
    except (ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
