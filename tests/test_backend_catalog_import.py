"""手动导入外部 PDF 成为公共习题的契约。"""

import hashlib
import io
import json
import os
import unittest

os.environ.setdefault("DATABASE_URL", "")  # 防御：下面 install_module_database 会覆盖为一次性测试库

import pg_support  # noqa: E402  建一次性测试库，必须在 import app 之前

pg_support.install_module_database({"SECRET_KEY": "import-tests-disposable-secret-no-production",
                                    "LLM_API_KEY": "", "ADMIN_USERNAME": "", "ADMIN_PASSWORD": ""})

import test_backend_catalog as fixtures  # noqa: E402

from app import db as database  # noqa: E402
from app.routers import engagement  # noqa: E402


def tiny_pdf(label: str = "Hello Import") -> bytes:
    """单页最小 PDF（无 xref 表，pdfium 可自行重建）。"""
    return b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R >> endobj
4 0 obj << /Length 44 >>
stream
BT /F1 24 Tf 72 720 Td (LABEL) Tj ET
endstream
endobj
trailer << /Root 1 0 R /Size 5 >>
%%EOF
""".replace(b"LABEL", label.encode("ascii", "replace")).replace(b"\n", b"\r\n")


class CatalogImportContracts(fixtures.PublicCatalogContracts):
    def setUp(self):
        fixtures.PublicCatalogContracts.setUp(self)
        self.client.app.include_router(engagement.router)  # 打印版本关联接口在 engagement 路由

    def import_paper(self, **overrides):
        query = {"title": "外部导入练习", "grade": "三年级", "subject": "数学", **overrides}
        params = "&".join(f"{key}={value}" for key, value in query.items())
        # PDF 内容按标题哈希差异化：不同标题 = 不同字节，避免误触发同内容归档复用
        label = hashlib.md5(query["title"].encode()).hexdigest()[:16]
        return self.client.post("/api/v1/admin/catalog/import?" + params,
                                content=tiny_pdf(label), headers={"Content-Type": "application/pdf"})

    def test_import_creates_ready_draft_with_rendered_assets(self):
        result = self.import_paper()
        self.assertEqual(result.status_code, 201, result.text)
        paper = result.json()
        self.assertEqual(paper["status"], "draft")
        self.assertEqual(paper["file_status"], "ready")
        self.assertEqual(paper["question_count"], 0)
        self.assertEqual((paper["grade"], paper["subject"]), ("三年级", "数学"))
        kinds = {asset["kind"] for asset in paper["assets"]}
        self.assertEqual(kinds, {"pdf", "page"})
        for asset in paper["assets"]:
            self.assertEqual(self.client.get(asset["url"]).status_code, 200)
        # 发布后对读者可见，且搜索能按标题命中
        response = self.client.put(f"/api/v1/admin/catalog/papers/{paper['id']}",
                                   json={"revision": paper["revision"], "title": paper["title"], "description": "",
                                         "category": "", "category_id": "", "status": "published", "featured": False,
                                         "confirm_publication": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.sign_in(self.viewer)
        listing = self.client.get("/api/v1/catalog/papers", params={"q": "外部导入"}).json()
        self.assertEqual(listing["total"], 1)

    def test_pdf_import_can_deliver_a_link_while_retaining_page_previews(self):
        params = {'title': '网盘交付卷', 'grade': '三年级', 'subject': '数学', 'download_mode': 'external',
                  'external_url': 'https://pan.example.com/s/abc?pwd=1234&from=school', 'external_code': '1234'}
        response = self.client.post('/api/v1/admin/catalog/import', params=params,
                                    content=tiny_pdf('external-delivery'), headers={'Content-Type': 'application/pdf'})
        self.assertEqual(response.status_code, 201, response.text)
        item = self.publish(response.json())
        self.sign_in(self.viewer)
        detail = self.client.get(f"/api/v1/catalog/papers/{item['id']}").json()
        self.assertEqual([asset['kind'] for asset in detail['assets']], ['page'])
        delivery = self.client.post(f"/api/v1/catalog/papers/{item['id']}/download").json()
        self.assertEqual(delivery['url'], params['external_url'])
        self.assertEqual(delivery['extraction_code'], '1234')

    def test_landscape_and_large_pages_fit_preview_bounds_without_changing_pdf(self):
        from PIL import Image
        for width, height in ((842, 595), (2000, 3000)):
            with self.subTest(width=width, height=height):
                content = tiny_pdf(f"page-{width}").replace(b"595 842", f"{width} {height}".encode())
                response = self.client.post("/api/v1/admin/catalog/import", params={
                    "title": f"尺寸验收 {width}", "grade": "三年级", "subject": "数学",
                }, content=content, headers={"Content-Type": "application/pdf"})
                self.assertEqual(response.status_code, 201, response.text)
                assets = response.json()["assets"]
                preview = self.client.get(next(asset["url"] for asset in assets if asset["kind"] == "page"))
                with Image.open(io.BytesIO(preview.content)) as image:
                    self.assertLessEqual(image.width, 1200)
                    self.assertLessEqual(image.height, 1800)
                    self.assertAlmostEqual(image.width / image.height, width / height, delta=0.01)
                original = self.client.get(next(asset["url"] for asset in assets if asset["kind"] == "pdf"))
                self.assertEqual(original.content, content)

    def test_reimporting_the_same_pdf_reuses_the_archive(self):
        first = self.import_paper().json()
        second = self.import_paper()
        # 同一份 PDF 已在公共库：复用归档并拒绝重复创建
        self.assertEqual(second.status_code, 409, second.text)
        self.assertEqual(second.json()["detail"]["error"], "该版本已加入公共库，请编辑已有条目")
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM paper_archives WHERE source_id LIKE 'import-%'").fetchone()[0], 1)
        # 删除公共条目后可以重新导入并复用同一个归档
        self.assertEqual(self.client.delete(f"/api/v1/admin/catalog/papers/{first['id']}?revision={first['revision']}").status_code, 204)
        again = self.import_paper()
        self.assertEqual(again.status_code, 201, again.text)
        with database.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM paper_archives WHERE source_id LIKE 'import-%'").fetchone()[0], 1)

    def test_import_validates_metadata_and_content(self):
        self.assertEqual(self.import_paper(grade="").status_code, 422)
        self.assertEqual(self.import_paper(subject="").status_code, 422)
        self.assertEqual(self.client.post("/api/v1/admin/catalog/import?title=x&grade=三年级&subject=数学",
                                          content=b"not a pdf", headers={"Content-Type": "application/pdf"}).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/admin/catalog/import?title=x&grade=三年级&subject=数学",
                                          content=tiny_pdf(), headers={"Content-Type": "text/plain"}).status_code, 415)
        # 非管理员不可导入
        self.sign_in(self.author)
        self.assertEqual(self.import_paper().status_code, 403)

    def test_imported_paper_keeps_access_policy(self):
        result = self.import_paper(view_access="vip", download_access="vip")
        self.assertEqual(result.status_code, 201, result.text)
        paper = result.json()
        self.assertEqual((paper["view_access"], paper["required_view"]), ("vip", "vip"))

    def test_import_mode_selects_print_edition_kind(self):
        # 导出模式落入快照，决定之后能挂成哪种打印版本
        for mode in ("student", "answersOnly", "withAnswers"):
            result = self.import_paper(title=f"模式-{mode}", mode=mode)
            self.assertEqual(result.status_code, 201, result.text)
            with database.db() as conn:
                snapshot = json.loads(conn.execute(
                    "SELECT snapshot_json FROM paper_archives WHERE title = ?", (f"模式-{mode}",)).fetchone()[0])
            self.assertEqual(snapshot["export_options"]["mode"], mode)
        # 非法模式被 FastAPI 校验拒绝
        self.assertEqual(self.import_paper(mode="bogus").status_code, 422)

    def test_imported_editions_skip_content_validation(self):
        """导入的 PDF 不做题目一致性校验：内容、年级、导出模式都不同也能关联打印版本。"""
        target = self.import_paper(title="导入原稿").json()  # 默认 withAnswers，三年级
        second = self.import_paper(title="导入答案", grade="五年级", mode="answersOnly")  # 跨年级 + 模式不匹配
        self.assertEqual(second.status_code, 201, second.text)
        second = second.json()
        # 导入的答案已自动单独建条目；先删除该条目（归档保留），再关联为打印版本
        self.assertEqual(self.client.delete(f"/api/v1/admin/catalog/papers/{second['id']}?revision={second['revision']}").status_code, 204)
        with database.db() as conn:
            archive_id = conn.execute("SELECT id FROM paper_archives WHERE title = ?", ("导入答案",)).fetchone()[0]
        response = self.client.put(f"/api/v1/admin/catalog/papers/{target['id']}/editions",
                                   json={"revision": target["revision"], "kind": "student", "paper_id": archive_id})
        self.assertEqual(response.status_code, 200, response.text)
        kinds = {item["kind"] for item in response.json()["editions"]}
        self.assertIn("student", kinds)

    def test_edition_sources_lists_imported_archives(self):
        """打开导入条目的「打印版本」不应 500：LIKE 'import-%' 里的字面量 % 曾被当成非法占位符。"""
        paper = self.import_paper(title="打印版本来源卷").json()
        path = f"/api/v1/admin/catalog/papers/{paper['id']}/edition-sources"
        listing = self.client.get(path)
        self.assertEqual(listing.status_code, 200, listing.text)
        body = listing.json()
        self.assertTrue(body["loose"])  # 导入来源不限年级科目题量
        self.assertIn("打印版本来源卷", {item["title"] for item in body["items"]})
        searched = self.client.get(path, params={"q": "来源"})
        self.assertEqual(searched.status_code, 200, searched.text)
        self.assertEqual([item["title"] for item in searched.json()["items"]], ["打印版本来源卷"])

    def test_import_answer_edition_together_in_one_step(self):
        """导入卷子后可直接上传答案 PDF 挂为「答案解析版」，无需单独建条目再关联。"""
        paper = self.import_paper(title="随卷答案卷").json()
        with database.db() as conn:
            before = conn.execute("SELECT COUNT(*) FROM catalog_papers").fetchone()[0]
        response = self.client.post(f"/api/v1/admin/catalog/papers/{paper['id']}/editions/import?kind=answers",
                                    content=tiny_pdf("answer-key"), headers={"Content-Type": "application/pdf"})
        self.assertEqual(response.status_code, 200, response.text)
        kinds = {item["kind"]: item for item in response.json()["editions"]}
        self.assertIn("answers", kinds)
        self.assertEqual(kinds["answers"]["label"], "答案解析版")
        # 答案归档直接归属该条目，不再单独创建公共条目
        with database.db() as conn:
            after = conn.execute("SELECT COUNT(*) FROM catalog_papers").fetchone()[0]
            archive = conn.execute("SELECT title, source_id FROM paper_archives WHERE source_id LIKE 'import-%' AND title LIKE '%答案'").fetchone()
        self.assertEqual(after, before)
        self.assertEqual(archive["title"], "随卷答案卷·答案")
        # 详情页的版本列表里读者可下载答案
        detail = self.client.get(f"/api/v1/admin/catalog/papers/{paper['id']}").json()
        self.assertIn("answers", {item["kind"] for item in detail["editions"]})


class PlaceholderTranslationContracts(unittest.TestCase):
    """业务 SQL 一律写 ? 占位符；被引号包住的字面量 % 必须转义成 %%，psycopg 才不当占位符解析。"""

    def test_question_marks_become_placeholders_and_literals_escape(self):
        translate = database._to_pg_sql
        self.assertEqual(translate("SELECT 1 FROM t WHERE id = ? AND label = 'a?b'"),
                         "SELECT 1 FROM t WHERE id = %s AND label = 'a?b'")
        self.assertEqual(translate("SELECT 1 FROM t WHERE source_id LIKE 'import-%' AND id = ?"),
                         "SELECT 1 FROM t WHERE source_id LIKE 'import-%%' AND id = %s")


if __name__ == "__main__":
    unittest.main()
