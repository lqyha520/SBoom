"""Deterministic demo content and an explicitly disposable-only library seeder."""

import hashlib
import json
import tempfile
import time
from pathlib import Path

import pg_support

DATASET = "paper-library-demo-v1"
FOLDERS = ("三年级数学", "阅读与积累", "英语专项", "期末复习")
GRADES = ("一年级", "二年级", "三年级", "四年级", "五年级", "六年级")


def question(stem, answer, analysis="", **extra):
    return {"stem": stem, "answer": answer, "analysis": analysis, **extra}


def section(kind, name, questions, passage=None):
    data = {"questions": questions}
    if passage:
        data["passage"] = passage
    return {"type": kind, "name": name, "data": data,
            "layout": {"qCols": 2 if kind == "fill_blank" else 1, "optCols": 2,
                       "showNo": True, "tableBorder": "none", "fontSize": ""}}


def entry(key, title, grade, subject, keyword, sections, folder=None, favorite=False,
          age_hours=0, source=None, status="ready", day=None):
    paper = {"grade": "小学" + GRADES[grade - 1], "subject": subject, "title": title,
             "keyword": keyword, "difficulty": "medium", "sections": sections}
    if day is not None:
        paper["day"] = day
    return {
        "key": key, "folder": folder, "favorite": favorite,
        "age_hours": age_hours, "file_status": status,
        "request": {
            "request_id": DATASET + "-" + key, "source_id": source or "demo-" + key,
            "group_id": "demo-daily" if day is not None else "demo-autumn",
            "group_name": "每日口算" if day is not None else "开学巩固",
            "snapshot": {
                "schema_version": 1, "paper": paper,
                "template": {"id": "exam", "name": "标准试卷", "tag": "考试",
                             "showInfoRow": True, "showNotice": True, "showScore": True,
                             "titlePrefix": "", "titleSuffix": "", "footer": "演示试卷",
                             "headerExtra": "演示数据，不含真实学生信息"},
                "style": {"bg": "none", "bgOpacity": 70, "banner": False, "secColor": False,
                          "frame": "none", "encourage": False, "reward": False, "kidFont": "off",
                          "exportBg": False, "titleScale": 1, "titleOffsetY": 0},
                "export_options": {"mode": "withAnswers", "addDay": True, "renderer_version": "web-v1"},
            },
        },
    }


def math_unit(version):
    sums = [(118, 236), (287, 317), (345, 225), (248, 352 if version == 1 else 341)]
    return [
        section("fill_blank", "计算与填空", [
            question(f"{a} + {b} = ____", str(a + b), "先算个位，再算十位和百位。") for a, b in sums
        ] + [question("1 千米 = ____ 米", "1000"), question("3 分 = ____ 秒", "180", "1 分等于 60 秒。")]),
        section("compare", "比较大小", [
            question("在横线上填 >、< 或 =。", sign, left_expr=left, right_expr=right)
            for left, right, sign in [("398 + 102", "500", "="), ("607 - 298", "300", ">"),
                                     ("245 + 156", "410", "<"), ("1 千米", "900 米", ">")]
        ]),
        section("quiz", "选择题", [
            question("305 + 196 的结果是（ ）。", 1, "305 + 196 = 501。", type="multiple_choice", options=["491", "501", "511"]),
            question("下面哪个数最接近 600？", 1, "598 与 600 相差 2。", type="multiple_choice", options=["590", "598", "609"]),
        ]),
        section("word_problem", "解决问题", [
            question("图书角原有 238 本书，新添了 156 本，借出了 89 本。现在有多少本书？", "305 本", "238 + 156 - 89 = 305（本）。"),
            question("一根绳子长 1 米，剪去 35 厘米，还剩多少厘米？", "65 厘米", "1 米 = 100 厘米，100 - 35 = 65（厘米）。"),
            question("同学们 8:20 开始阅读，8:55 结束。这次阅读用了多长时间？", "35 分钟", "55 - 20 = 35（分钟）。"),
        ]),
    ]


def daily_sections(day, grade):
    values = []
    for i in range(20):
        if grade == 1:
            a, b = (day + i) % 11 + 2, (day * 2 + i) % 7 + 1
            stem, answer = (f"{a} + {b}", a + b) if i % 2 == 0 else (f"{a + b} - {b}", a)
        elif grade == 2:
            a, b = (day + i) % 8 + 2, i % 8 + 2
            stem, answer = (f"{a} × {b}", a * b) if i % 2 == 0 else (f"{a * b} ÷ {a}", b)
        else:
            a, b = day * 7 + i * 11 + 108, i * 3 + 17
            stem, answer = (f"{a} + {b}", a + b) if i % 2 == 0 else (f"{a} - {b}", a - b)
        values.append(question(stem + " = ____", str(answer)))
    count = 4 + day % 5
    problems = [question(f"书架上有 {count} 本故事书和 8 本绘本，一共有多少本书？", f"{count + 8} 本", f"{count} + 8 = {count + 8}（本）。")]
    if grade > 1:
        problems.append(question(f"每盒彩笔有 6 支，{count} 盒彩笔共有多少支？", f"{6 * count} 支", f"6 × {count} = {6 * count}（支）。"))
    return [section("fill_blank", "口算与计算", values), section("word_problem", "解决问题", problems)]


def catalog():
    reading = (
        "周五的午后，三年级的同学们来到校园的小花园。昨夜下过雨，叶片上还挂着水珠。"
        "林老师让大家选择一株植物，连续观察一周，并把变化记在本子上。\n"
        "小雨选了一株向日葵。第一天，她只写下‘叶子是绿色的’。第二天，她带来了直尺，"
        "量出最高的一片叶子长 12 厘米，又画下花盘的方向。过了几天，她发现同一时刻的影子有长有短。\n"
        "分享时，小雨说：‘观察不只是看一眼，还要多比较、多记录。’同学们纷纷举起自己的观察本，"
        "原来熟悉的小花园里，也藏着许多值得发现的变化。"
    )
    entries = [
        entry("math-unit-v1", "三年级数学 第一单元练习", 3, "数学", "万以内加减法 时间 长度单位", math_unit(1), FOLDERS[0], age_hours=240, source="demo-math-unit"),
        entry("math-unit-v2", "三年级数学 第一单元巩固练习", 3, "数学", "万以内加减法 时间 长度单位 修订版", math_unit(2), FOLDERS[0], True, source="demo-math-unit"),
        entry("chinese-observation", "三年级语文 小花园里的发现", 3, "语文", "阅读理解 观察日记 词语积累", [
            section("reading", "阅读短文，完成练习", [
                question("同学们在什么时候来到小花园？", 1, "短文第一句交代了时间。", type="multiple_choice", options=["周一早晨", "周五午后", "周日傍晚"]),
                question("小雨选择观察的植物是什么？", "向日葵", "第二段第一句写明了观察对象。"),
                question("第二天，小雨带来了什么工具？", "直尺", "她用直尺测量叶子的长度。"),
                question("小雨量出的那片叶子有多长？", "12 厘米"),
                question("文中哪句话最能说明小雨的收获？", "观察不只是看一眼，还要多比较、多记录。"),
                question("如果你来写观察日记，还会记录什么？", "示例：记录每天的天气、叶片数量和花盘方向。", "答案开放，写出具体、可观察的内容即可。"),
            ], reading),
            section("fill_blank", "词语与表达", [
                question("‘熟悉’的反义词是 ____。", "陌生"), question("‘连续观察一周’中的‘一周’是 ____ 天。", "7"),
                question("照样子填词：一株植物，一____直尺。", "把"),
                question("用‘发现’写一句完整的话。", "示例：我发现窗边的种子发芽了。", "句子完整，用词恰当即可。"),
            ]),
        ], FOLDERS[1], True, age_hours=1),
        entry("english-library", "四年级英语 A Day at the Library", 4, "英语", "阅读理解 时间表达 场所词汇", [
            section("reading", "Read and answer", [
                question("When does Lucy go to the library?", 1, "The passage says Saturday morning.", type="multiple_choice", options=["Friday evening", "Saturday morning", "Sunday afternoon"]),
                question("How many books does Lucy borrow?", "Two books."),
                question("What time does the library open?", "At nine o'clock."),
                question("Can Lucy eat in the library?", "No, she can't.", "The rule says: Do not eat here."),
            ], "Lucy goes to the library on Saturday morning. The library opens at nine o'clock. She borrows two books about plants. Her brother Tom reads a storybook there. A sign says, 'Please be quiet. Do not eat here.' They take the books home at ten o'clock."),
            section("match_pair", "Match the words", [question("把单词和正确的中文意思连起来。", [[0, 2], [1, 0], [2, 3], [3, 1]],
                left_items=["library", "quiet", "borrow", "plant"], right_items=["安静的", "植物", "图书馆", "借入"])]),
            section("fill_blank", "Complete the sentences", [
                question("I ____ a book every evening. (read / reads)", "read"),
                question("Tom ____ to school at eight. (go / goes)", "goes"),
                question("There ____ two books on the desk. (is / are)", "are"),
                question("Please ____ quiet in the library. (be / is)", "be"),
            ]),
        ], FOLDERS[2], True, age_hours=2),
        entry("math-decimals", "五年级数学 小数专项练习", 5, "数学", "小数加减法 小数乘法 实际应用", [
            section("fill_blank", "计算与填空", [question(stem, answer) for stem, answer in [
                ("3.6 + 2.45 = ____", "6.05"), ("8.2 - 3.75 = ____", "4.45"), ("0.6 × 4 = ____", "2.4"),
                ("2.5 × 8 = ____", "20"), ("4.08 × 10 = ____", "40.8"), ("6.3 ÷ 10 = ____", "0.63")]]),
            section("true_false", "判断题", [question("0.50 与 0.5 大小相等。", "正确"), question("小数乘整数，积一定大于这个整数。", "错误", "例如 0.5 × 2 = 1，小于 2。")]),
            section("word_problem", "解决问题", [
                question("每本练习本 2.5 元，买 6 本需要多少钱？", "15 元", "2.5 × 6 = 15（元）。"),
                question("一条步道长 3.8 千米，已经走了 1.65 千米，还剩多少千米？", "2.15 千米", "3.8 - 1.65 = 2.15（千米）。"),
            ]),
        ], FOLDERS[3], True, age_hours=24),
        entry("math-fractions", "六年级数学 分数整理与复习", 6, "数学", "分数加减法 分数乘法 应用题", [
            section("fill_blank", "计算与填空", [question(stem, answer) for stem, answer in [
                ("1/2 + 1/4 = ____", "3/4"), ("3/5 - 1/5 = ____", "2/5"), ("2/3 × 3/4 = ____", "1/2"),
                ("5/6 - 1/3 = ____", "1/2"), ("3/8 + 1/4 = ____", "5/8"), ("4/5 × 10 = ____", "8")]]),
            section("quiz", "选择题", [question("下面与 2/3 相等的分数是（ ）。", 2, "分子、分母同时乘 2。", type="multiple_choice", options=["2/6", "3/4", "4/6"])]),
            section("word_problem", "解决问题", [
                question("一本书共 120 页，已经读了全书的 3/5。还剩多少页？", "48 页", "120 × (1 - 3/5) = 48（页）。"),
                question("一根绳子长 8 米，用去它的 3/4。用去了多少米？", "6 米", "8 × 3/4 = 6（米）。"),
            ]),
        ], FOLDERS[3], age_hours=48),
        entry("chinese-sentences", "二年级语文 词句积累", 2, "语文", "量词 反义词 连词成句 标点", [
            section("fill_blank", "词语积累", [question(stem, answer) for stem, answer in [
                ("一____铅笔", "支"), ("一____白云", "朵"), ("一____小河", "条"), ("‘高’的反义词是 ____。", "矮"),
                ("‘远’的反义词是 ____。", "近"), ("‘早’的反义词是 ____。", "晚")]]),
            section("word_problem", "句子练习", [
                question("把词语排成一句通顺的话：在 / 同学们 / 操场上 / 跑步", "同学们在操场上跑步。"),
                question("把句子补充完整：春天来了，____。", "示例：春天来了，小草变绿了。"),
                question("给句子加上标点：你今天读书了吗", "你今天读书了吗？"),
            ]),
        ], FOLDERS[1], age_hours=72),
        entry("english-classroom", "三年级英语 My Classroom", 3, "英语", "颜色 文具 单复数", [
            section("quiz", "Choose the answer", [
                question("What colour is the sky on a clear day?", 0, type="multiple_choice", options=["Blue", "Green", "Black"]),
                question("I write with a ____.", 1, type="multiple_choice", options=["chair", "pencil", "door"]),
                question("Two ____ are on the desk.", 2, type="multiple_choice", options=["book", "a book", "books"]),
            ]),
            section("match_pair", "Match the words", [question("把文具和对应的英文单词连起来。", [[0, 1], [1, 2], [2, 0]],
                left_items=["尺子", "橡皮", "书包"], right_items=["schoolbag", "ruler", "eraser"])]),
            section("fill_blank", "Complete the sentences", [question("This is ____ apple. (a / an)", "an"), question("My bag is ____.（红色的）", "red")]),
        ], FOLDERS[2], True, age_hours=96),
    ]
    for day in range(1, 15):
        grade = (day - 1) % 3 + 1
        entries.append(entry(f"daily-{day:02d}", f"{GRADES[grade - 1]}数学 每日口算 {day:02d}", grade, "数学",
                             "每日口算 " + ("20 以内加减法" if grade == 1 else "表内乘除法" if grade == 2 else "三位数加减法"),
                             daily_sections(day, grade), FOLDERS[0] if grade == 3 else None,
                             favorite=day == 14, age_hours=120 + (14 - day) * 24, day=day))
    entries.extend([
        entry("pending-files", "一年级数学 加减法练习（待传文件）", 1, "数学", "演示 待上传", daily_sections(1, 1), age_hours=144, status="pending"),
        entry("failed-files", "三年级数学 单元复习（文件中断）", 3, "数学", "演示 上传失败 内容已保留", math_unit(1), FOLDERS[3], age_hours=168, status="failed"),
    ])
    return entries


def catalog_digest(entries):
    return hashlib.sha256(json.dumps(entries, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def load_bundles(directory, entries):
    root = Path(directory).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    ready = {item["key"] for item in entries if item["file_status"] == "ready"}
    if (manifest.get("dataset") != DATASET or manifest.get("catalog_sha256") != catalog_digest(entries)
            or set(manifest.get("bundles", {})) != ready):
        raise ValueError("Demo manifest is stale or incomplete; regenerate the demo assets")
    bundles = {}
    for key in sorted(ready):
        path = (root / key / "bundle.zip").resolve()
        if not path.is_relative_to(root):
            raise ValueError("Demo assets must stay inside the selected directory")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != manifest["bundles"][key]["sha256"]:
            raise ValueError(f"Demo bundle checksum mismatch: {key}")
        bundles[key] = content
    return bundles


def seed_library(user, disposable_root, assets_directory):
    from app import db as database
    from app.config import get_settings
    from app.models.library import ArchiveCreate, ArchiveUpdate
    from app.services import paper_library

    root, settings = Path(disposable_root).resolve(), get_settings()
    # This helper is deliberately unavailable to the real app and production DB.
    if (not root.is_relative_to(Path(tempfile.gettempdir()).resolve())
            or not root.name.startswith("learn-coach-ui-") or user.username != "ui_teacher"
            or not pg_support.is_disposable_db(settings.database_url)
            or Path(settings.archive_local_dir).resolve() != root / "private-papers"):
        raise ValueError("Demo seeding is allowed only for the disposable UI fixture")

    entries = catalog()
    bundles = load_bundles(assets_directory, entries)
    requests = {item["key"]: ArchiveCreate.model_validate(item["request"]) for item in entries}
    with database.db() as conn:
        existing = {row["request_id"]: row["id"] for row in conn.execute(
            "SELECT request_id, id FROM paper_archives WHERE user_id = ?", (user.id,))}
    folders = {item["name"]: item["id"] for item in paper_library.list_folders(user.id)["items"]}
    created, now = 0, int(time.time())
    for item in entries:
        request = requests[item["key"]]
        if request.request_id in existing:
            continue
        folder = item["folder"]
        if folder and folder not in folders:
            folders[folder] = paper_library.save_folder(user.id, folder)["id"]
        request.folder_id = folders.get(folder)
        paper = paper_library.create_paper(user.id, request)
        if item["favorite"]:
            paper_library.update_paper(user.id, paper["id"], ArchiveUpdate(favorite=True))
        if item["file_status"] == "ready":
            paper_library.publish_bundle(user.id, paper["id"], bundles[item["key"]])
        stamp = now - item["age_hours"] * 3600
        with database.db() as conn:
            conn.execute("UPDATE paper_archives SET created_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                         (stamp, stamp, paper["id"], user.id))
            if item["file_status"] == "failed":
                conn.execute("UPDATE paper_archives SET file_status = 'failed', file_error = ? WHERE id = ? AND user_id = ?",
                             ("演示：文件上传中断，试卷内容已保留", paper["id"], user.id))
        created += 1
    return {"created": created, **paper_library.library_summary(user.id)}


def seed_public_catalog(publisher, reader, disposable_root, assets_directory):
    from app import db as database
    from app.config import get_settings
    from app.models.catalog import CatalogCreate, CatalogUpdate, TypeAccessUpdate
    from app.models.library import ArchiveCreate
    from app.services import catalog_access, mini_auth, paper_library, public_catalog

    root, settings = Path(disposable_root).resolve(), get_settings()
    if (not root.is_relative_to(Path(tempfile.gettempdir()).resolve())
            or not root.name.startswith("learn-coach-ui-")
            or publisher.username != "admin_console" or publisher.role != "admin"
            or not isinstance(reader, mini_auth.MiniUser) or reader.username != "ui_vip"
            or not pg_support.is_disposable_db(settings.database_url)
            or Path(settings.archive_local_dir).resolve() != root / "private-papers"):
        raise ValueError("Public demo seeding is allowed only for the disposable UI fixture")

    entries = catalog()
    bundles = load_bundles(assets_directory, entries)
    reading_rule = next(rule for rule in catalog_access.list_type_rules()["items"] if rule["question_type"] == "reading")
    if reading_rule["revision"] == 0:
        catalog_access.update_type_rule("reading", TypeAccessUpdate(revision=0, view_access="vip", download_access="vip"))
    with database.db() as conn:
        existing = {row["request_id"] for row in conn.execute(
            "SELECT request_id FROM paper_archives WHERE user_id = ?", (publisher.id,))}
    created, now = 0, int(time.time())
    for item in entries:
        request = ArchiveCreate.model_validate(item["request"])
        request.request_id = "public-" + request.request_id
        if request.request_id in existing:
            continue
        source = paper_library.create_paper(publisher.id, request)
        if item["file_status"] == "ready":
            paper_library.publish_bundle(publisher.id, source["id"], bundles[item["key"]])
        elif item["file_status"] == "failed":
            with database.db() as conn:
                conn.execute("UPDATE paper_archives SET file_status = 'failed', file_error = ? WHERE id = ?",
                             ("演示：文件上传中断，试卷内容已保留", source["id"]))
        category = ("每日口算" if item["key"].startswith("daily-") else
                    "英语专项" if source["subject"] == "英语" else
                    "阅读与积累" if source["subject"] == "语文" else
                    "期末复习" if item["folder"] == FOLDERS[3] else "单元练习")
        policy = {"view_access": "free", "download_access": "vip"} if item["key"] == "math-decimals" else {}
        publication = public_catalog.create_paper(publisher.id, CatalogCreate(
            paper_id=source["id"], category=category,
            description=f"{source['grade']} · {source['subject']} · {source['keyword']}", **policy))
        if item["file_status"] == "ready":
            public_catalog.update_paper(publisher.id, publication["id"], CatalogUpdate(
                revision=publication["revision"], title=publication["title"], category=category,
                description=publication["description"], status="published", featured=item["favorite"],
                confirm_publication=True, **policy))
            if item["favorite"]:
                public_catalog.favorite_paper(reader.id, publication["id"], True)
            if item["key"] in ("math-unit-v2", "chinese-observation", "english-library"):
                public_catalog.request_download(reader.id, publication["id"])
        stamp = now - item["age_hours"] * 3600
        with database.db() as conn:
            conn.execute("UPDATE paper_archives SET created_at = ?, updated_at = ? WHERE id = ?", (stamp, stamp, source["id"]))
            conn.execute("UPDATE catalog_papers SET created_at = ?, updated_at = ?, published_at = ? WHERE id = ?",
                         (stamp, stamp, stamp if item["file_status"] == "ready" else 0, publication["id"]))
        created += 1

    # Keep one ready source outside the catalog for the administrator's publishing workflow.
    spare = ArchiveCreate.model_validate(entries[1]["request"])
    spare.request_id = DATASET + "-public-unlisted"
    spare.source_id = "public-demo-unlisted"
    if spare.request_id not in existing:
        source = paper_library.create_paper(publisher.id, spare)
        paper_library.publish_bundle(publisher.id, source["id"], bundles[entries[1]["key"]])
    return {"created": created, **public_catalog.admin_summary()}
