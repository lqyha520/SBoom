"""站点内容模块冒烟测试：建表 → 分类/Banner/公告/字典 CRUD → 公开视图 → 看板。

用独立临时库运行，不触碰 data/users.db。
    python scripts/smoke_site.py        # SQLite（默认）
    python scripts/smoke_site.py --pg   # 另建一次性 PostgreSQL 库，验 PG 方言兼容性
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_USE_PG = "--pg" in sys.argv


def _env_database_url() -> str:
    """.env 里的 DATABASE_URL（PG 直连串），用于派生一次性测试库。"""
    from dotenv import dotenv_values

    return str(dotenv_values(ROOT / ".env").get("DATABASE_URL") or "")


def _create_temp_pg(url: str) -> tuple[str, str]:
    """在同一个 PG 实例上建一个临时库；返回 (测试库连接串, 库名)。"""
    import psycopg
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    temp_name = "lc_site_smoke_" + next(tempfile._get_candidate_names())
    admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{temp_name}"')
    return urlunsplit((parts.scheme, parts.netloc, "/" + temp_name, "", "")), temp_name


def _drop_temp_pg(url: str, name: str) -> None:
    import psycopg
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


_tmp = Path(tempfile.mkdtemp(prefix="lc-site-smoke-"))
os.environ["LC_DB_PATH"] = str(_tmp / "smoke.db")
os.environ["ARCHIVE_LOCAL_DIR"] = str(_tmp / "files")
# .env 里配置了 DATABASE_URL 时会连到真实库：默认强制回落 SQLite 临时库，
# --pg 时改连一次性测试库，绝不使用业务库。
_pg_temp = ("", "")
if _USE_PG:
    _pg_temp = _create_temp_pg(_env_database_url())
    os.environ["DATABASE_URL"] = _pg_temp[0]
    print(f"使用一次性 PostgreSQL 测试库：{_pg_temp[1]}")
else:
    os.environ["DATABASE_URL"] = ""

from app.db import init_db  # noqa: E402
from app.models.site import (  # noqa: E402
    BannerInput, BannerUpdate, CategoryInput, CategoryUpdate,
    DictionaryInput, DocumentUpdate, NoticeInput, NoticeUpdate,
)
from app.services import site_content as site  # noqa: E402

failures = []


def check(label, condition, extra=""):
    print(("  ok   " if condition else "  FAIL ") + label + (f"  {extra}" if extra else ""))
    if not condition:
        failures.append(label)


print("1. 建表与种子")
init_db()
docs = {item["key"] for item in site.list_documents()["items"]}
check("协议与隐私文档已初始化", docs == {"agreement", "privacy"}, str(docs))
grades = site.list_dictionary("grade")["items"]
check("年级字典已初始化 12 条", len(grades) == 12, f"实际 {len(grades)}")
check("科目字典已初始化 3 条", len(site.list_dictionary("subject")["items"]) == 3)

print("2. 分类 CRUD")
created = site.create_category(CategoryInput(name="单元测试分类", description="冒烟测试", icon="edit", is_visible=True))
check("创建分类返回 revision=1", created["revision"] == 1)
check("创建分类 paper_count=0", created["paper_count"] == 0)
updated = site.update_category(created["id"], CategoryUpdate(revision=1, name="单元测试分类改名", description="", icon="copy", sort_order=50, is_visible=False))
check("更新分类后 revision+1", updated["revision"] == 2 and updated["name"] == "单元测试分类改名")
try:
    site.update_category(created["id"], CategoryUpdate(revision=1, name="冲突", description="", icon="", sort_order=0, is_visible=True))
    check("过期 revision 应报 409", False)
except Exception as exc:
    check("过期 revision 被拒绝", getattr(exc, "status_code", None) == 409, str(getattr(exc, "detail", exc)))
try:
    site.create_category(CategoryInput(name="单元测试分类改名"))
    check("同名分类应报 409", False)
except Exception as exc:
    check("同名分类被拒绝", getattr(exc, "status_code", None) == 409)
site.reorder_categories([created["id"]])
check("排序接口可用", site.list_categories()["items"][0]["id"] == created["id"])

print("3. Banner CRUD 与图片校验")
banner = site.create_banner(BannerInput(title="冒烟标题", subtitle="副标题", kicker="提示", action_label="去看看",
                                        target_type="keyword", target_value="阅读"))
check("创建 Banner 成功", banner["revision"] == 1 and banner["image_url"] is None)
check("target_value 已保存", banner["target_value"] == "阅读")
try:
    site.create_banner(BannerInput(title="缺少目标", target_type="category"))
    check("缺跳转目标应被拒", False)
except Exception:
    check("缺跳转目标被 pydantic 拒绝", True)
try:
    site.save_banner_image(banner["id"], "image/jpeg", b"not-an-image")
    check("坏图片应被拒", False)
except Exception as exc:
    check("坏图片被拒绝", getattr(exc, "status_code", None) in (413, 422), str(getattr(exc, "detail", exc)))
try:
    site.save_banner_image(banner["id"], "text/plain", b"x")
    check("非图片类型应被拒", False)
except Exception as exc:
    check("非图片 MIME 被拒绝", getattr(exc, "status_code", None) == 415)
try:
    site.banner_asset(banner["id"])
    check("无图 Banner 取资产应 404", False)
except Exception as exc:
    check("无图 Banner 取资产报 404", getattr(exc, "status_code", None) == 404)
hidden = site.update_banner(banner["id"], BannerUpdate(revision=1, title="冒烟标题", subtitle="", kicker="", action_label="",
                                                       target_type="none", target_value="", sort_order=10, is_visible=False))
check("Banner 下线成功", hidden["is_visible"] is False and hidden["revision"] == 2)

print("4. 公告 CRUD 与状态机")
notice = site.create_notice(NoticeInput(title="维护公告", body="今晚维护", placement="banner", level="warning"))
check("公告状态 hidden→active", notice["state"] == "active")
scheduled = site.create_notice(NoticeInput(title="未来公告", placement="popup", starts_at=4102444800))
check("未到开始时间为 scheduled", scheduled["state"] == "scheduled")
expired = site.create_notice(NoticeInput(title="过期公告", placement="popup", ends_at=1000000))
check("已过结束时间为 expired", expired["state"] == "expired")
try:
    site.create_notice(NoticeInput(title="时间倒挂", starts_at=2000, ends_at=1000))
    check("时间倒挂应被拒", False)
except Exception:
    check("时间倒挂被 pydantic 拒绝", True)
site.update_notice(notice["id"], NoticeUpdate(revision=1, title="维护公告", body="改期", placement="banner", level="info", is_visible=True))
check("公告更新成功", next(item for item in site.list_notices()["items"] if item["id"] == notice["id"])["title"] == "维护公告")

print("5. 文档更新")
doc = site.get_document("privacy")
try:
    site.update_document("privacy", DocumentUpdate(revision=doc["revision"] + 5, title="x", body="y"))
    check("过期 revision 应被拒", False)
except Exception as exc:
    check("文档并发冲突被拒绝", getattr(exc, "status_code", None) == 409)
saved = site.update_document("privacy", DocumentUpdate(revision=doc["revision"], title="隐私政策", body="## 标题\n正文内容"))
check("文档保存成功", saved["revision"] == doc["revision"] + 1 and "正文内容" in saved["body"])
try:
    site.get_document("terms")
    check("未知文档应 404", False)
except Exception as exc:
    check("未知文档 key 报 404", getattr(exc, "status_code", None) == 404)

print("6. 字典与未收录值扫描")
added = site.create_dictionary(DictionaryInput(kind="grade", value="幼儿园大班"))
check("新增字典条目成功", added["value"] == "幼儿园大班")
unlisted = site.unlisted_dictionary()
check("未收录扫描返回两个维度", set(unlisted) == {"grade", "subject"})
adopted = site.adopt_dictionary("subject", ["科学", "道德与法治"])
check("一键收录计数正确", adopted["added"] == 2, str(adopted.get("added")))
check("重复收录不叠加", site.adopt_dictionary("subject", ["科学"])["added"] == 0)

print("7. 公开视图")
payload = site.home_payload()
check("home 返回四段结构", set(payload) == {"banners", "notices", "categories", "dictionaries"})
check("下线的 Banner 不出现在首页", all(item["id"] != banner["id"] for item in payload["banners"]))
check("banner 位公告出现在首页", any(item["title"] == "维护公告" for item in payload["notices"]["banner"]))
check("scheduled 公告不出现在首页", all(item["title"] != "未来公告" for item in payload["notices"]["popup"]))
check("字典顺序可读", payload["dictionaries"]["grades"][0] == "小学一年级")
check("科目包含新收录值", "科学" in payload["dictionaries"]["subjects"])

print("8. 内容数据看板")
analytics = site.admin_analytics()
check("看板结构完整", {"papers", "engagement", "by_category", "users", "new_users_timeline"} <= set(analytics))
check("新增用户走势 14 天", len(analytics["new_users_timeline"]) == 14)
check("无分类试卷计数存在", "papers_without_category" in analytics)

print()
if _pg_temp[1]:
    from app.db import close_pg_pool

    close_pg_pool()
    try:
        _drop_temp_pg(_env_database_url(), _pg_temp[1])
        print(f"已清理一次性 PostgreSQL 测试库：{_pg_temp[1]}")
    except Exception as exc:  # 清理失败不影响测试结论，仅提示手工回收
        print(f"⚠️  测试库 {_pg_temp[1]} 自动清理失败，请手工 DROP：{exc}")

if failures:
    print(f"❌ {len(failures)} 项失败：" + "、".join(failures))
    sys.exit(1)
print("✅ 站点内容模块冒烟测试全部通过")
