"""同一归档的学生卷与答案独立下载，沿用发布、权限及原稿保护。"""
import copy
import io
import unittest
from unittest.mock import patch

import pypdfium2 as pdfium
import test_backend_catalog as fixtures
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError
from test_backend_catalog_import import tiny_pdf
from test_backend_library import snapshot

from app.models.library import PaperSnapshot
from app.models.mini import MembershipUpdate
from app.routers import engagement
from app.services import catalog_import, paper_library
from app.services.paper_storage import LocalStorage, unpack_bundle


def split_bundle(count=1, **overrides):
    if count == 1:
        student, answers = tiny_pdf("Student"), tiny_pdf("Answers")
    else:
        document = pdfium.PdfDocument.new()
        try:
            for _ in range(count):
                document.new_page(595, 842).close()
            output = io.BytesIO()
            document.save(output)
            student = answers = output.getvalue()
        finally:
            document.close()
    image = io.BytesIO()
    Image.new("RGB", (1040, 1471), "white").save(image, "JPEG")
    values = {"paper.pdf": student, "answers.pdf": answers, **{f"page-{i}.jpg": image.getvalue() for i in range(1, count + 1)}}
    values.update(overrides)
    return fixtures.bundle(values), student, answers


class SplitPdfContracts(unittest.TestCase):
    sign_in = fixtures.PublicCatalogContracts.sign_in
    draft = fixtures.PublicCatalogContracts.draft
    update = fixtures.PublicCatalogContracts.update
    publish = fixtures.PublicCatalogContracts.publish

    def setUp(self):
        fixtures.PublicCatalogContracts.setUp(self)
        self.client.app.include_router(engagement.router)

    def create_split(self, count=1):
        value = snapshot()
        value["export_options"].update(mode="withAnswers", separate_answers=True)
        if count > 1:
            value.update(schema_version=2, collection_title=value["paper"]["title"], additional_papers=[copy.deepcopy(value["paper"]) for _ in range(count - 1)])
        response = self.client.post("/api/v1/library/papers", json={"request_id": "split-request", "source_id": "split-source", "snapshot": value})
        self.assertEqual(response.status_code, 201, response.text)
        record = response.json()
        bundle, student, answers = split_bundle(count)
        response = self.client.put(f"/api/v1/library/papers/{record['id']}/files", content=bundle, headers={"Content-Type": "application/zip"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), bundle, student, answers, value

    def test_twenty_papers_remain_one_archive_with_two_immutable_pdfs(self):
        record, bundle, student, answers, value = self.create_split(20)
        self.assertEqual(record["title"], value["paper"]["title"])
        self.assertEqual(record["snapshot"], value)
        self.assertEqual(record["page_count"], 20)
        self.assertEqual(self.client.get("/api/v1/library/papers").json()["total"], 1)
        pdfs = [asset for asset in record["assets"] if asset["kind"] == "pdf"]
        self.assertEqual(len(pdfs), 2)
        self.assertIsNone(pdfs[0].get("edition"))
        self.assertEqual(pdfs[1]["edition"], "answers")
        for asset, raw in zip(pdfs, (student, answers), strict=True):
            response = self.client.get(asset["url"])
            self.assertEqual(response.content, raw)
            self.assertEqual(response.headers["content-type"], "application/pdf")
            self.assertIn("attachment", response.headers["content-disposition"])
        with patch.object(LocalStorage, "put", side_effect=AssertionError("就绪文件不应重写")):
            replay = self.client.put(f"/api/v1/library/papers/{record['id']}/files", content=bundle, headers={"Content-Type": "application/zip"})
        self.assertEqual(replay.json()["assets"], record["assets"])

    def test_publication_has_two_choices_with_shared_download_and_view_permissions(self):
        record, _, student, answers, _ = self.create_split()
        published = self.publish(self.draft(record))
        self.assertEqual(published["answer_readiness"], "separate")
        self.assertEqual([item["mode"] for item in published["editions"]], ["student", "answersOnly"])
        self.assertEqual([item["kind"] for item in published["editions"]], ["original", "answers"])
        self.sign_in(self.viewer)
        prefix = f"/api/v1/catalog/papers/{published['id']}"
        self.assertEqual(self.client.get("/api/v1/catalog/papers").json()["total"], 1)
        urls = []
        for kind, raw in (("original", student), ("answers", answers)):
            result = self.client.post(prefix + "/download?edition=" + kind)
            self.assertEqual(result.status_code, 200, result.text)
            asset = result.json()
            self.assertEqual(asset["kind"], "pdf")
            urls.append(asset["url"])
            self.assertEqual(self.client.get(asset["url"]).content, raw)
        self.assertNotEqual(urls[0], urls[1])
        self.sign_in(self.admin)
        published = self.update(published, view_access="free", download_access="vip").json()
        self.sign_in(self.viewer)
        detail = self.client.get(prefix).json()
        self.assertTrue(all("url" not in item for item in detail["editions"]))
        self.assertTrue(all(asset["kind"] == "page" for asset in detail["assets"]))
        page_url = detail["assets"][0]["url"]
        self.assertEqual(self.client.get(page_url).status_code, 200)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(prefix + "/download?edition=answers").status_code, 403)
        self.client.headers.pop("Authorization", None)
        self.assertEqual(self.client.get(urls[1]).status_code, 401)
        mini_auth = fixtures.mini_auth
        mini_auth.update_membership(self.admin.id, self.viewer.id, MembershipUpdate(revision=1, membership="vip", is_active=True))
        self.sign_in(self.viewer)
        self.assertEqual(self.client.get(urls[1]).content, answers)
        self.sign_in(self.admin)
        self.update(published, status="withdrawn")
        self.sign_in(self.viewer)
        for url in (*urls, page_url):
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_split_package_requires_both_pdfs_and_bounds_total_pages(self):
        bundle, _, _ = split_bundle()
        self.assertEqual([kind for kind, _, _, _ in unpack_bundle(bundle, separate_answers=True)], ["pdf", "answers_pdf", "page"])
        for raw, separate, limit in ((bundle, False, 40), (fixtures.bundle(), True, 40), (split_bundle(**{"answers.pdf": b"bad"})[0], True, 40), (bundle, True, 1)):
            with self.subTest(separate=separate, limit=limit):
                with self.assertRaises(HTTPException) as error:
                    unpack_bundle(raw, separate_answers=separate, max_pages=limit)
                self.assertEqual(error.exception.status_code, 422)
        catalog_import._import_gate.acquire()
        try:
            with self.assertRaises(HTTPException) as error:
                unpack_bundle(bundle, separate_answers=True)
            self.assertEqual(error.exception.status_code, 429)
        finally:
            catalog_import._import_gate.release()
        value = snapshot()
        value["export_options"]["separate_answers"] = True
        with self.assertRaises(ValidationError):
            PaperSnapshot.model_validate(value)

    def test_extra_answer_edition_can_override_and_restore_embedded_answers(self):
        record, _, _, answers, value = self.create_split()
        published = self.publish(self.draft(record))
        value["export_options"].update(mode="answersOnly", separate_answers=False)
        other = self.client.post("/api/v1/library/papers", json={"request_id": "extra-answer-request", "source_id": "extra-answer-source", "snapshot": value}).json()
        replacement = tiny_pdf("Replacement")
        image = io.BytesIO()
        Image.new("RGB", (210, 297), "white").save(image, "JPEG")
        paper_library.publish_bundle(self.admin.id, other["id"], fixtures.bundle({"paper.pdf": replacement, "page-1.jpg": image.getvalue()}))
        endpoint = f"/api/v1/admin/catalog/papers/{published['id']}/editions"
        result = self.client.put(endpoint, json={"revision": published["revision"], "kind": "answers", "paper_id": other["id"], "confirm_publication": True})
        self.assertEqual(result.status_code, 200, result.text)
        edition = next(item for item in result.json()["editions"] if item["kind"] == "answers")
        self.assertEqual(self.client.get(edition["url"]).content, replacement)
        restored = self.client.put(endpoint, json={"revision": result.json()["revision"], "kind": "answers", "paper_id": None, "confirm_publication": True})
        self.assertEqual(restored.status_code, 200, restored.text)
        edition = next(item for item in restored.json()["editions"] if item["kind"] == "answers")
        self.assertNotIn("paper_id", edition)
        self.assertEqual(self.client.get(edition["url"]).content, answers)

    def test_failed_second_pdf_upload_can_retry_without_extra_archive_or_partial_assets(self):
        value = snapshot()
        value["export_options"].update(mode="withAnswers", separate_answers=True)
        record = self.client.post("/api/v1/library/papers", json={"request_id": "split-retry", "source_id": "split-source", "snapshot": value}).json()
        bundle, _, _ = split_bundle()
        original = LocalStorage.put

        def fail_answer(storage, key, data, mime):
            if key.endswith("/answers.pdf"):
                raise OSError("模拟答案文件写入失败")
            return original(storage, key, data, mime)

        with patch.object(LocalStorage, "put", fail_answer):
            with self.assertRaises(HTTPException):
                paper_library.publish_bundle(self.admin.id, record["id"], bundle)
        failed = paper_library.get_paper(self.admin.id, record["id"])
        self.assertEqual(failed["file_status"], "failed")
        self.assertEqual(failed["assets"], [])
        ready = paper_library.publish_bundle(self.admin.id, record["id"], bundle)
        self.assertEqual(ready["file_status"], "ready")
        self.assertEqual(len([asset for asset in ready["assets"] if asset["kind"] == "pdf"]), 2)
        self.assertEqual(paper_library.list_papers(self.admin.id)["total"], 1)
