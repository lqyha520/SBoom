"""UI/API regression checks. Refuses to run against a non-fixture service."""

import os
import io
import time
import unittest
import zipfile

import httpx
from PIL import Image

BASE = os.environ.get("LC_TEST_BASE", "http://127.0.0.1:8105")


class UiContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        health = httpx.get(BASE + "/health").json()
        if health.get("fixture") is not True:
            raise RuntimeError("Refusing to modify a non-fixture service")
        cls.admin = httpx.Client(base_url=BASE)
        cls.admin_id = cls.admin.post("/api/v1/auth/login", json={"username": "admin_console", "password": "admin-pass-123"}).json()["id"]
        username = "ui-contract-" + str(time.time_ns())[-10:]
        result = cls.admin.post("/api/v1/admin/users", json={"username": username, "password": "test-pass-123", "role": "user"})
        result.raise_for_status()
        cls.user_id = result.json()["id"]
        cls.user = httpx.Client(base_url=BASE)
        cls.user.post("/api/v1/auth/login", json={"username": username, "password": "test-pass-123"}).raise_for_status()
        # 公共试卷库只认小程序读者的 bearer 会话，与工作台 cookie 是两个互不相通的账号域
        # （见 app/library_deps.py 的 require_mini_user），所以可见性断言必须用真实读者身份；
        # 第二个读者用来验证「收藏是读者私有的」。
        cls.reader_id, cls.reader = cls._new_reader("ui-reader-")
        cls.other_reader_id, cls.other_reader = cls._new_reader("ui-reader-other-")

    @classmethod
    def _new_reader(cls, prefix):
        name = prefix + str(time.time_ns())[-10:]
        created = cls.admin.post("/api/v1/admin/mini-users", json={"username": name, "password": "test-pass-123"})
        created.raise_for_status()
        token = httpx.post(BASE + "/api/v1/mini/login-password",
                           json={"username": name, "password": "test-pass-123"})
        token.raise_for_status()
        return created.json()["id"], httpx.Client(base_url=BASE,
                                                  headers={"Authorization": "Bearer " + token.json()["token"]})

    @classmethod
    def tearDownClass(cls):
        cls.admin.delete(f"/api/v1/admin/users/{cls.user_id}").raise_for_status()
        for client, reader_id in ((cls.reader, cls.reader_id), (cls.other_reader, cls.other_reader_id)):
            client.close()
            cls.admin.delete(f"/api/v1/admin/mini-users/{reader_id}").raise_for_status()
        cls.admin.close()
        cls.user.close()

    def test_self_protection(self):
        path = f"/api/v1/admin/users/{self.admin_id}"
        self.assertEqual(self.admin.delete(path).status_code, 400)
        self.assertEqual(self.admin.put(path, json={"is_active": False}).status_code, 400)
        self.assertEqual(self.admin.put(path, json={"role": "user"}).status_code, 400)

    def test_normal_user_cannot_access_admin(self):
        for route in ["stats", "users", "feedbacks", "logs", "llm-config"]:
            self.assertEqual(self.user.get("/api/v1/admin/" + route).status_code, 403)

    def test_template_round_trip_and_admin_inspection(self):
        template = {"name": "UI contract", "grade": "小学三年级", "subject": "数学", "cards": [{"type": "fill_blank", "count": 2}]}
        self.user.put("/api/v1/me/templates", json={"template": template}).raise_for_status()
        saved = self.user.get("/api/v1/me/templates").json()["templates"]
        self.assertIn(template, [{key: value for key, value in item.items() if key != "_revision"} for item in saved])
        metas = self.admin.get(f"/api/v1/admin/users/{self.user_id}/templates").json()["templates"]
        meta = next(row for row in metas if row["name"] == template["name"])
        content = self.admin.get(f"/api/v1/admin/users/{self.user_id}/templates/{meta['id']}").json()["template"]
        self.assertEqual(content["cards"], template["cards"])
        self.user.delete("/api/v1/me/templates", params={"name": template["name"]}).raise_for_status()
        self.assertEqual(self.user.get("/api/v1/me/templates").json()["templates"], [])

    def test_admin_model_config_masks_key(self):
        value = self.admin.get("/api/v1/admin/llm-config").json()
        self.assertIn("hasKey", value)
        self.assertNotIn("apiKey", value)
        self.assertNotIn("api_key", value)
        self.assertNotIn("test-only-key", str(value))

    def test_generation_count_contract(self):
        body = {"grade": "小学三年级", "subject": "数学", "keyword": "加法", "difficulty": "medium", "items": [{"game_type": "fill_blank", "question_count": 30}]}
        result = self.user.post("/api/v1/generate-batch", json=body)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.json()["sections"][0]["questions"]), 30)
        body["items"][0]["question_count"] = 31
        self.assertEqual(self.user.post("/api/v1/generate-batch", json=body).status_code, 422)

    def test_built_frontends_are_available(self):
        self.assertIn('id="app"', self.admin.get("/").text)
        self.assertIn('/admin/assets/', self.admin.get("/admin/").text)

    def test_batch_archive_visible_to_another_client_and_private_downloads(self):
        group_id = "contract-group-" + str(time.time_ns())
        folder = self.user.post("/api/v1/library/folders", json={"name": group_id}).json()
        layout = {"qCols": 2, "optCols": 2, "showNo": True, "tableBorder": "none", "fontSize": ""}
        template = {"id": "exam", "name": "Test", "tag": "test", "showInfoRow": True, "showNotice": True,
                    "showScore": True, "titlePrefix": "", "titleSuffix": "", "footer": "", "headerExtra": ""}
        style = {"bg": "none", "bgOpacity": 70, "banner": False, "secColor": False, "frame": "none", "encourage": False,
                 "reward": False, "kidFont": "off", "exportBg": False, "titleScale": 1, "titleOffsetY": 0}
        image = io.BytesIO()
        Image.new("RGB", (210, 297), "white").save(image, "JPEG")
        files = io.BytesIO()
        with zipfile.ZipFile(files, "w") as archive:
            archive.writestr("paper.pdf", b"%PDF-1.4\ncontract-fixture-only\n%%EOF\n")
            archive.writestr("page-1.jpg", image.getvalue())
        papers = []
        for index in range(2):
            paper = {"grade": "小学三年级", "subject": "数学", "keyword": "加法", "difficulty": "medium", "title": f"归档契约 {index + 1}"}
            result = self.user.post("/api/v1/generate-batch", json={key: value for key, value in paper.items() if key != "title"} | {
                "items": [{"game_type": "fill_blank", "question_count": 2}],
            })
            result.raise_for_status()
            paper["sections"] = [{"type": "fill_blank", "layout": layout, "data": {"questions": result.json()["sections"][0]["questions"]}}]
            body = {"request_id": f"{group_id}-{index}", "source_id": f"{group_id}-source-{index}", "folder_id": folder["id"],
                    "group_id": group_id, "group_name": "跨端批量测试", "snapshot": {"schema_version": 1, "paper": paper,
                    "template": template, "style": style, "export_options": {"mode": "student", "addDay": True, "renderer_version": "web-v1"}}}
            saved = self.user.post("/api/v1/library/papers", json=body)
            self.assertEqual(saved.status_code, 201, saved.text)
            self.assertEqual(saved.json()["file_status"], "pending")
            self.assertEqual(self.user.post("/api/v1/library/papers", json=body).json()["id"], saved.json()["id"])
            uploaded = self.user.put(f"/api/v1/library/papers/{saved.json()['id']}/files", content=files.getvalue(),
                                     headers={"Content-Type": "application/zip"})
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            self.assertEqual(uploaded.json()["file_status"], "ready")
            papers.append(uploaded.json())

        with httpx.Client(base_url=BASE, cookies=self.user.cookies) as companion:
            listed = companion.get("/api/v1/library/papers", params={"folder_id": folder["id"]}).json()
            self.assertEqual(listed["total"], 2)
            self.assertEqual({item["id"] for item in listed["items"]}, {item["id"] for item in papers})
            for paper in papers:
                for asset in paper["assets"]:
                    downloaded = companion.get(asset["url"])
                    self.assertEqual(downloaded.status_code, 200)
                    self.assertEqual(len(downloaded.content), asset["byte_size"])
                    self.assertEqual(downloaded.headers["cache-control"], "private, no-store")
                    self.assertEqual(self.admin.get(asset["url"]).status_code, 404)
            changed = companion.put(f"/api/v1/library/papers/{papers[0]['id']}", json={"favorite": True, "title": "手机整理"})
            self.assertEqual(changed.status_code, 200)
            self.assertEqual(self.user.get(f"/api/v1/library/papers/{papers[0]['id']}").json()["title"], "手机整理")
        for paper in papers:
            self.user.delete(f"/api/v1/library/papers/{paper['id']}").raise_for_status()
        self.user.delete(f"/api/v1/library/folders/{folder['id']}").raise_for_status()

    def test_admin_publication_reader_access_and_withdrawal(self):
        from library_demo import catalog

        body = catalog()[1]["request"]
        body["request_id"] = body["source_id"] = "public-http-" + str(time.time_ns())
        body["group_name"] = "private-source-metadata"
        source = self.admin.post("/api/v1/library/papers", json=body)
        source.raise_for_status()
        source_id = source.json()["id"]
        self.assertEqual(self.user.get(f"/api/v1/library/papers/{source_id}").status_code, 404)
        self.assertEqual(self.user.post("/api/v1/admin/catalog/papers", json={"paper_id": source_id}).status_code, 403)
        draft = self.admin.post("/api/v1/admin/catalog/papers", json={"paper_id": source_id, "title": "Public HTTP contract", "category": "Contract"})
        draft.raise_for_status()
        publication_id = draft.json()["id"]
        path = f"/api/v1/catalog/papers/{publication_id}"
        admin_path = f"/api/v1/admin/catalog/papers/{publication_id}"
        update = {"revision": 1, "title": "Public HTTP contract", "category": "Contract", "status": "published", "confirm_publication": True}
        self.assertEqual(self.reader.get(path).status_code, 404)
        self.assertEqual(self.user.get(path).status_code, 404)  # 工作台 cookie 按游客处理，不能读取未发布资料。
        self.assertEqual(self.admin.put(admin_path, json=update).status_code, 409)

        image, files = io.BytesIO(), io.BytesIO()
        Image.new("RGB", (210, 297), "white").save(image, "JPEG")
        with zipfile.ZipFile(files, "w") as archive:
            archive.writestr("paper.pdf", b"%PDF-1.4\npublic-contract-fixture-only\n%%EOF\n")
            archive.writestr("page-1.jpg", image.getvalue())
        self.admin.put(f"/api/v1/library/papers/{source_id}/files", content=files.getvalue(),
                       headers={"Content-Type": "application/zip"}).raise_for_status()
        published = self.admin.put(admin_path, json=update)
        published.raise_for_status()
        guest_detail = self.user.get(path)
        self.assertEqual(guest_detail.status_code, 200)
        self.assertTrue(guest_detail.json()["can_view"])
        self.assertFalse(guest_detail.json()["can_download"])
        self.assertEqual(self.user.post(path + "/download").status_code, 401)
        detail = self.reader.get(path)
        detail.raise_for_status()
        self.assertNotIn("private-source-metadata", detail.text)
        for asset in detail.json()["assets"]:
            file = self.reader.get(asset["url"])
            self.assertEqual(file.status_code, 200)
            self.assertEqual(len(file.content), asset["byte_size"])
            self.assertEqual(file.headers["cache-control"], "private, no-store")
        self.reader.put(path + "/favorite", json={"favorite": True}).raise_for_status()
        pdf = self.reader.post(path + "/download").json()
        self.assertTrue(self.reader.get(pdf["url"]).content.startswith(b"%PDF-"))
        self.assertEqual(self.reader.get("/api/v1/catalog/papers?favorite=true").json()["total"], 1)
        self.assertEqual(self.reader.get("/api/v1/catalog/papers?downloaded=true").json()["total"], 1)
        self.assertFalse(self.other_reader.get(path).json()["favorite"])  # 收藏是读者私有的
        self.assertEqual(self.admin.delete(f"/api/v1/library/papers/{source_id}").status_code, 409)

        update.update(revision=published.json()["revision"], status="withdrawn", confirm_publication=False)
        withdrawn = self.admin.put(admin_path, json=update)
        withdrawn.raise_for_status()
        self.assertEqual(self.reader.get(path).status_code, 404)
        self.assertEqual(self.reader.get(pdf["url"]).status_code, 404)
        self.assertEqual(self.reader.post(path + "/download").status_code, 404)
        self.assertEqual(self.reader.get("/api/v1/catalog/papers?favorite=true").json()["total"], 0)
        self.admin.delete(admin_path, params={"revision": withdrawn.json()["revision"]}).raise_for_status()
        self.assertEqual(self.admin.get(f"/api/v1/library/papers/{source_id}").status_code, 200)
        self.admin.delete(f"/api/v1/library/papers/{source_id}").raise_for_status()


if __name__ == "__main__":
    unittest.main(verbosity=2)
