"""Create printable demo PDF/JPEG bundles, without importing the application.

Optional dev dependencies: reportlab, pypdfium2, Pillow.
This is a test-asset renderer, not the production web exporter.
"""

import argparse
import hashlib
import json
import os
import zipfile
from html import escape
from pathlib import Path

from library_demo import DATASET, catalog, catalog_digest


def readable_stem(value):
    if "left_expr" in value:
        return f"{value['left_expr']} ____ {value['right_expr']}"
    return str(value.get("stem", ""))


def readable_answer(value):
    answer = value.get("answer", "")
    if isinstance(answer, int) and value.get("options"):
        return f"{chr(65 + answer)}. {value['options'][answer]}"
    if isinstance(answer, list) and value.get("left_items"):
        return "；".join(f"{value['left_items'][left]} - {value['right_items'][right]}" for left, right in answer)
    return str(answer)


def render_pdf(entry, path):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        HRFlowable,
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    paper = entry["request"]["snapshot"]["paper"]
    accent = colors.HexColor({"数学": "#176D5A", "语文": "#A34142", "英语": "#266C96"}[paper["subject"]])
    width = A4[0] - 96
    styles = {
        "meta": ParagraphStyle("meta", fontName="DemoCN", fontSize=9, leading=15, textColor=accent, spaceAfter=8),
        "title": ParagraphStyle("title", fontName="DemoCN", fontSize=19, leading=28, alignment=TA_CENTER, spaceAfter=16, wordWrap="CJK"),
        "section": ParagraphStyle("section", fontName="DemoCN", fontSize=12, leading=19, textColor=accent, spaceBefore=14, spaceAfter=8, keepWithNext=True),
        "body": ParagraphStyle("body", fontName="DemoCN", fontSize=11, leading=20, spaceAfter=8, wordWrap="CJK"),
        "answer": ParagraphStyle("answer", fontName="DemoCN", fontSize=10.5, leading=18, spaceAfter=8, wordWrap="CJK"),
        "muted": ParagraphStyle("muted", fontName="DemoCN", fontSize=9, leading=15, textColor=colors.HexColor("#62676D"), spaceAfter=8, wordWrap="CJK"),
    }

    def para(text, kind="body"):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[kind])

    def two_columns(cells):
        rows = [cells[i:i + 2] + ([""] if i + 1 == len(cells) else []) for i in range(0, len(cells), 2)]
        table = Table(rows, colWidths=[width / 2] * 2, hAlign="LEFT")
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 14), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        return table

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D9DFDC"))
        canvas.line(48, 42, A4[0] - 48, 42)
        canvas.setFont("DemoCN", 8)
        canvas.setFillColor(colors.HexColor("#62676D"))
        canvas.drawString(48, 28, "Learning Coach | 演示试卷 | 不含真实学生信息")
        canvas.drawRightString(A4[0] - 48, 28, f"第 {doc.page} 页")
        canvas.restoreState()

    story = [para(f"{paper['grade']} / {paper['subject']} / 开学巩固 · 演示数据", "meta"),
             para(paper["title"], "title"),
             para("姓名：____________    班级：____________    日期：____________", "muted"),
             HRFlowable(width="100%", thickness=1.2, color=accent), Spacer(1, 8)]
    for index, part in enumerate(paper["sections"], 1):
        story.append(para(f"{index}. {part['name']}", "section"))
        if part["data"].get("passage"):
            story.append(para(part["data"]["passage"]))
        questions = part["data"]["questions"]
        if part["type"] == "fill_blank" and all(len(readable_stem(q)) < 38 for q in questions):
            cells = [para(f"{i}. {readable_stem(q)}") for i, q in enumerate(questions, 1)]
            story.append(two_columns(cells))
            continue
        for number, value in enumerate(questions, 1):
            block = [para(f"{number}. {readable_stem(value)}")]
            if value.get("options"):
                block.append(para("    ".join(f"{chr(65 + i)}. {option}" for i, option in enumerate(value["options"]))))
            if value.get("left_items"):
                pairs = [[para(f"{i + 1}. {left}"), para(f"{chr(65 + i)}. {right}")]
                         for i, (left, right) in enumerate(zip(value["left_items"], value["right_items"], strict=False))]
                block.append(Table(pairs, colWidths=[width / 2] * 2, hAlign="LEFT"))
            if not value.get("options") and not value.get("left_items") and "____" not in readable_stem(value):
                block.append(Spacer(1, 18 if part["type"] == "word_problem" else 10))
            story.append(KeepTogether(block))

    story.extend([PageBreak(), para(paper["title"], "meta"), para("参考答案", "title"),
                  HRFlowable(width="100%", thickness=1.2, color=accent)])
    for index, part in enumerate(paper["sections"], 1):
        story.append(para(f"{index}. {part['name']}", "section"))
        answers = []
        for number, value in enumerate(part["data"]["questions"], 1):
            text = f"{number}. {readable_answer(value)}"
            if value.get("analysis"):
                text += "\n" + value["analysis"]
            answers.append(text)
        if part["type"] in ("fill_blank", "compare", "true_false") and all(len(text) < 80 for text in answers):
            story.append(two_columns([para(text, "answer") for text in answers]))
        else:
            story.extend(para(text, "answer") for text in answers)
    SimpleDocTemplate(str(path), pagesize=A4, topMargin=42, bottomMargin=58, leftMargin=48, rightMargin=48,
                      title=paper["title"], author="Learning Coach Demo").build(story, onFirstPage=footer, onLaterPages=footer)


def build_assets(output, font):
    import pypdfium2 as pdfium
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont("DemoCN", str(font), subfontIndex=0))
    entries = catalog()
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"dataset": DATASET, "renderer": "demo-reportlab-v1", "catalog_sha256": catalog_digest(entries), "bundles": {}}
    for entry in entries:
        if entry["file_status"] != "ready":
            continue
        directory = output / entry["key"]
        directory.mkdir(parents=True, exist_ok=True)
        pdf_path = directory / "paper.pdf"
        render_pdf(entry, pdf_path)
        pages = []
        with pdfium.PdfDocument(str(pdf_path)) as document:
            for i in range(len(document)):
                page = document[i]
                try:
                    bitmap = page.render(scale=1080 / page.get_width())
                    try:
                        pixels = bitmap.to_pil().convert("RGB")
                        if pixels.width > 1200 or pixels.height > 1800:
                            raise ValueError("Demo preview exceeds library image limits")
                        path = directory / f"page-{i + 1}.jpg"
                        pixels.save(path, "JPEG", quality=84, optimize=True)
                        pages.append(path)
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        bundle_path = directory / "bundle.zip"
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in [pdf_path, *pages]:
                bundle.write(path, path.name)
        manifest["bundles"][entry["key"]] = {"sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(), "pages": len(pages)}
        print(f"{entry['key']}: {len(pages)} pages", flush=True)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {len(manifest['bundles'])} PDF bundles in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "artifacts/miniprogram/demo")
    parser.add_argument("--font", type=Path, default=Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/simsun.ttc")
    args = parser.parse_args()
    if not args.font.is_file():
        parser.error("Pass --font with a CJK TrueType font path (SimSun or Noto Sans SC)")
    build_assets(args.output.resolve(), args.font.resolve())
