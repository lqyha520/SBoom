"""Loopback-only UI test service with disposable data and no external LLM calls.

Run: python tests/ui_fixture.py --port 8105
With demo papers: add --demo-library artifacts/miniprogram/demo after rendering the assets.
Accounts: admin_console / admin-pass-123; ui_teacher / teacher-pass-123.
The demo additionally creates ui_reader / reader-pass-123, with no private archives.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TEMP = tempfile.TemporaryDirectory(prefix="learn-coach-ui-")

import pg_support  # noqa: E402  一次性测试库，必须在 import app 之前

pg_support.install_module_database({
    "SECRET_KEY": "ui-fixture-disposable-secret-never-use-in-production",
    "PROVIDER_ALLOW_PRIVATE": "true", "LLM_API_KEY": "", "LLM_BASE_URL": "http://127.0.0.1:1", "LLM_MODEL": "ui-fixture",
    "ADMIN_USERNAME": "", "ADMIN_PASSWORD": "", "FORCE_HTTPS": "false",
    "REGISTRATION_ENABLED": "true", "MINI_REGISTRATION_ENABLED": "true", "CORS_ORIGINS": "",
    "ARCHIVE_LOCAL_DIR": str(Path(TEMP.name) / "private-papers"),
    "WECHAT_APP_ID": "", "WECHAT_APP_SECRET": "",
    "WECHAT_PAY_ENABLED": "false", "WECHAT_SUBSCRIBE_TEMPLATE_ID": "", "WECHAT_PAY_AUTO_RECONCILE": "false",
})

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.db import db, init_db
from app.deps import require_admin
from app.models.mini import MembershipUpdate
from app.routers import (
    admin,
    auth,
    catalog,
    commerce,
    engagement,
    experience,
    generate,
    image_generation,
    library,
    me,
    mini,
    site,
)
from app.services import app_config, mini_auth, user_store
from app.services.generation_control import record_attempt, record_usage
from app.services.llm_client import llm_client
from app.services.user_store import CurrentUser


async def fixture_image(config, prompt):
    """Deterministic local PNG for UI checks; never contacts an image provider."""
    import io

    from PIL import Image, ImageDraw

    from app.services.image_generation import normalize_image
    record_attempt()
    await asyncio.sleep(0.25)
    position = re.search(r"这是第 (\d+) 张", prompt)
    page_number = int(position[1]) if position else 1
    if "模拟生图超时" in prompt or ("模拟第2张超时" in prompt and page_number == 2):
        raise HTTPException(504, detail={"error": "模拟生图超时，未自动重发"})
    picture = Image.new("RGB", (768, 1024), "#ffffff")
    draw = ImageDraw.Draw(picture)
    draw.rectangle((30, 30, 738, 135), fill="#e5f1eb")
    draw.text((60, 65), "OFFLINE IMAGE FIXTURE - NOT AI OUTPUT", fill="#295542", font_size=24)
    draw.text((60, 145), f"PAGE {page_number}", fill="#295542", font_size=24)
    for index in range(6):
        draw.text((60, 190 + index * 110), f"{index + 1}.    {index + 12} + 8 = __________", fill="#26332c", font_size=28)
    stream = io.BytesIO()
    picture.save(stream, format="PNG")
    return {**normalize_image(stream.getvalue()), "prompt": prompt}


image_generation.generate_image = fixture_image


def question(kind, index, version=0):
    number = index + 1 + version
    value = {"type": kind, "stem": f"{number} + 8 = ____", "answer": str(number + 8), "analysis": "Add the two numbers."}
    if kind in ("quiz", "challenge", "reading"):
        value.update(type="multiple_choice", stem=f"{number} + 8 = ?", options=[str(number + 7), str(number + 8), str(number + 9), str(number + 10)], answer=1)
    elif kind == "word_problem":
        value.update(stem=f"小明有 {number + 8} 本书，借出 8 本，还剩多少本？", answer=str(number))
    elif kind == "true_false":
        value.update(stem=f"{number} + 8 = {number + 8}", answer="正确")
    elif kind == "compare":
        value.update(left_expr=str(number + 8), right_expr=str(number), answer=">")
    elif kind == "number_split":
        value.update(top=number + 8, left=number, right="__", answer=8)
    elif kind == "match_pair":
        value.update(left_items=["2+3", "3+4"], right_items=["5", "7"], answer=[[0, 0], [1, 1]])
    return value


@asynccontextmanager
async def lifespan(_app):
    init_db()
    publisher = user_store.create_user("admin_console", "admin-pass-123", role="admin")
    teacher = user_store.create_user("ui_teacher", "teacher-pass-123")
    mini_auth.register("ui_reader", "reader-pass-123")
    vip = mini_auth.register("ui_vip", "vip-pass-123")["user"]
    mini_auth.update_membership(publisher.id, vip["id"], MembershipUpdate(
        revision=1, membership="vip", vip_expires_at=int(time.time()) + 30 * 86400, is_active=True))
    layout = {"qCols": 2, "optCols": 2, "tableBorder": "none", "fontSize": "", "showNo": True}
    template = {
        "name": "三年级数学随堂练习", "grade": "小学三年级", "subject": "数学",
        "keyword": "两位数加减法", "title": "三年级数学随堂练习", "difficulty": "medium", "templateId": "exam",
        "cards": [{"type": "fill_blank", "count": 6, "layout": layout}],
        "sections": [{"type": "fill_blank", "count": 6, "layout": layout, "data": {"questions": [question("fill_blank", i) for i in range(6)]}}],
    }
    user_store.upsert_template(teacher.id, template["name"], template)
    demo_library = getattr(_app.state, "demo_library", None)
    if demo_library:
        from library_demo import seed_library, seed_public_catalog
        result = seed_library(teacher, TEMP.name, demo_library)
        print(f"Demo library ready: {result['papers']} papers, {result['favorites']} favorites", flush=True)
        public = seed_public_catalog(publisher, mini_auth.get_user(vip["id"]), TEMP.name, demo_library)
        print(f"Public catalog ready: {public['published']} published, {public['draft']} drafts", flush=True)
    if os.environ.get("LC_SEED_MINI_FIXTURE") == "1":
        from test_backend_library import bundle, snapshot

        from app.models.catalog import CatalogCreate, CatalogUpdate
        from app.models.library import ArchiveCreate
        from app.services import paper_library, public_catalog
        for index in range(4):
            value = snapshot()
            value["paper"]["title"] = f"首页浏览器用例 {index + 1}"
            source = paper_library.create_paper(publisher.id, ArchiveCreate(request_id=f"home-browser-{index}", source_id=f"home-browser-{index}", snapshot=value))
            paper_library.publish_bundle(publisher.id, source["id"], bundle())
            item = public_catalog.create_paper(publisher.id, CatalogCreate(paper_id=source["id"], title=value["paper"]["title"]))
            public_catalog.update_paper(publisher.id, item["id"], CatalogUpdate(revision=item["revision"], title=item["title"], description="", category="", status="published", featured=True, confirm_publication=True))
    app_config.save_llm("http://127.0.0.1:1", "ui-fixture", "test-only-key", 60)
    with db() as conn:
        conn.execute("INSERT INTO feedbacks (user_id, username, game_id, is_oob, comment) VALUES (?, ?, ?, ?, ?)", (teacher.id, teacher.username, "ui-paper-001", 1, "这道应用题的数值范围偏大。"))
        conn.execute("INSERT INTO feedbacks (user_id, username, game_id, is_oob, comment) VALUES (?, ?, ?, ?, ?)", (teacher.id, teacher.username, "ui-paper-002", 0, "建议增加一道填空题。"))
    yield
    TEMP.cleanup()


fixture = FastAPI(title="Learning Coach UI Fixture", lifespan=lifespan)
generation = 0


async def fixture_chat(messages, **_kwargs):
    global generation
    generation += 1
    record_attempt()
    system = messages[0]["content"]
    user = messages[-1]["content"]
    await asyncio.sleep(0.35)
    if "fixture-error" in system + user:
        import httpx
        raise httpx.ReadTimeout("Disposable fixture timeout")
    record_usage({"prompt_tokens": 120, "completion_tokens": 80})
    if '"is_oob"' in system:
        return json.dumps({"is_oob": False, "oob_points": []})
    items = re.findall(r"section_id=([^，\n]+)，([^（\n]+)（[^\n]*?）：(\d+) 道题", system)
    if items:
        sections = []
        for index, (section_id, kind, count) in enumerate(items):
            value = {"section_id": section_id, "game_type": kind,
                     "questions": [question(kind, i, generation * 100 + index * 40) for i in range(int(count))]}
            if kind == "reading":
                value["passage"] = "春天到了，小明和同学们去公园观察植物。大家记录花朵的颜色，比较树叶的形状。回到教室后，他们一起分享观察到的变化。"
            if "fixture-partial" in system + user:
                value["questions"] = value["questions"][:1]
            sections.append(value)
        return json.dumps({"sections": list(reversed(sections))}, ensure_ascii=False)
    kind = re.search(r'"game_type"\s*:\s*"([^"]+)"', system)
    count = re.search(r"生成(\d+)道题目", system)
    return json.dumps({"game_type": kind[1] if kind else "fill_blank", "questions": [
        question(kind[1] if kind else "fill_blank", i, generation * 100)
        for i in range(int(count[1]) if count else 1)
    ]}, ensure_ascii=False)


async def fixture_stream(messages, **kwargs):
    yield await fixture_chat(messages, **kwargs)


llm_client.chat = fixture_chat
llm_client.chat_stream = fixture_stream


@fixture.get("/health")
async def health():
    return {"status": "healthy", "fixture": True}


@fixture.post("/api/v1/admin/test-llm")
async def test_model(user: CurrentUser = Depends(require_admin)):
    return {"reply": "UI fixture connection OK; no external request was made."}


@fixture.get("/api/v1/admin/logs")
async def logs(user: CurrentUser = Depends(require_admin)):
    return {"logs": "[INFO] Disposable UI fixture ready\n[INFO] Authentication, templates and admin use the real API\n[INFO] External LLM traffic disabled"}


fixture.include_router(auth.router)
fixture.include_router(me.router)
fixture.include_router(library.router)
fixture.include_router(mini.router)
fixture.include_router(catalog.router)
fixture.include_router(catalog.admin_router)
fixture.include_router(generate.router)
fixture.include_router(image_generation.router)
fixture.include_router(admin.router)
fixture.include_router(site.router)
fixture.include_router(site.admin_router)
fixture.include_router(experience.router)
fixture.include_router(engagement.router)
fixture.include_router(commerce.router)


@fixture.get("/admin", include_in_schema=False)
async def admin_redirect():
    return RedirectResponse("/admin/")


fixture.mount("/admin", StaticFiles(directory=Path(os.environ.get("LC_ADMIN_DIST", ROOT / "admin" / "dist")), html=True), name="admin")
fixture.mount("/", StaticFiles(directory=Path(os.environ.get("LC_WEB_DIST", ROOT / "web" / "dist")), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8105)
    parser.add_argument("--demo-library", type=Path, help="Prebuilt demo bundle directory from tests/render_library_demo.py")
    args = parser.parse_args()
    fixture.state.demo_library = args.demo_library
    uvicorn.run(fixture, host="127.0.0.1", port=args.port)
