"""Shared access decisions for lists, snapshots, preview images and PDF assets."""

import time

from fastapi import HTTPException

from app.db import db
from app.models import GameType


TYPE_LABELS = {
    "quiz": "选择题", "fill_blank": "填空题", "match_pair": "连线配对", "challenge": "闯关练习",
    "oral_math": "口算", "reading": "阅读理解", "vertical_calc": "竖式计算", "recursive_calc": "脱式计算",
    "smart_calc": "简便计算", "number_split": "数的分成", "compare": "比大小", "true_false": "判断题", "word_problem": "应用题",
}


def access_map(conn, ids, user=None, admin=False):
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    policies = {row["catalog_id"]: dict(row) for row in conn.execute(
        f"SELECT * FROM catalog_access WHERE catalog_id IN ({placeholders})", ids)}
    kinds = {catalog_id: [] for catalog_id in ids}
    for row in conn.execute("SELECT t.catalog_id, t.question_type, r.view_access, r.download_access "
                            "FROM catalog_question_types t LEFT JOIN catalog_type_rules r ON r.question_type = t.question_type "
                            f"WHERE t.catalog_id IN ({placeholders}) ORDER BY t.question_type", ids):
        kinds[row["catalog_id"]].append(dict(row))
    result = {}
    vip = admin or bool(user and user.is_vip)
    for catalog_id in ids:
        policy = policies.get(catalog_id, {"view_access": "inherit", "download_access": "inherit"})
        types = kinds[catalog_id]
        view = policy["view_access"]
        download = policy["download_access"]
        if view == "inherit":
            view = "vip" if any(kind["view_access"] == "vip" for kind in types) else "free"
        if download == "inherit":
            download = "vip" if any(kind["download_access"] == "vip" for kind in types) else "free"
        # A PDF contains the complete exercise, so download never bypasses view restrictions.
        if view == "vip":
            download = "vip"
        result[catalog_id] = {"view_access": policy["view_access"], "download_access": policy["download_access"],
                              "required_view": view, "required_download": download,
                              "can_view": view == "free" or vip,
                              "can_download": bool(admin or user) and (download == "free" or vip),
                              "question_types": [kind["question_type"] for kind in types]}
    return result


def require_access(access, action):
    if not access["can_" + action]:
        verb = "观看" if action == "view" else "下载"
        raise HTTPException(403, detail={"error": "该习题仅限有效 VIP 会员" + verb, "code": "vip_required", "action": action})


def save_policy(conn, catalog_id, body, preserve_missing=False):
    policy = {"view_access": body.view_access, "download_access": body.download_access}
    if preserve_missing:
        previous = conn.execute("SELECT view_access, download_access FROM catalog_access WHERE catalog_id = ?", (catalog_id,)).fetchone()
        for key in policy:
            if key not in body.model_fields_set:
                policy[key] = previous[key] if previous else "inherit"
    if policy["view_access"] == "vip" and policy["download_access"] == "free":
        raise HTTPException(422, detail={"error": "VIP 观看的习题不能向普通用户开放下载"})
    conn.execute("INSERT INTO catalog_access(catalog_id, view_access, download_access) VALUES (?, ?, ?) "
                 "ON CONFLICT(catalog_id) DO UPDATE SET view_access = excluded.view_access, download_access = excluded.download_access",
                 (catalog_id, policy["view_access"], policy["download_access"]))


def list_type_rules():
    with db() as conn:
        configured = {row["question_type"]: dict(row) for row in conn.execute("SELECT * FROM catalog_type_rules")}
        counts = {row["question_type"]: row["total"] for row in conn.execute(
            "SELECT question_type, COUNT(*) AS total FROM catalog_question_types GROUP BY question_type")}
    types = {kind.value for kind in GameType} | set(configured) | set(counts)
    return {"items": [{"question_type": kind, "label": TYPE_LABELS.get(kind, kind), "paper_count": counts.get(kind, 0),
                       **configured.get(kind, {"view_access": "free", "download_access": "free", "revision": 0, "updated_at": 0})}
                      for kind in sorted(types)]}


def update_type_rule(kind, body):
    with db(serialized=True) as conn:
        row = conn.execute("SELECT revision FROM catalog_type_rules WHERE question_type = ?", (kind,)).fetchone()
        if (row["revision"] if row else 0) != body.revision:
            raise HTTPException(409, detail={"error": "题型权限已更新，请刷新后重试"})
        if kind not in {item.value for item in GameType} and not conn.execute(
                "SELECT 1 FROM catalog_question_types WHERE question_type = ?", (kind,)).fetchone():
            raise HTTPException(404, detail={"error": "题型不存在"})
        conn.execute("INSERT INTO catalog_type_rules(question_type, view_access, download_access, revision, updated_at) VALUES (?, ?, ?, 1, ?) "
                     "ON CONFLICT(question_type) DO UPDATE SET view_access = excluded.view_access, download_access = excluded.download_access, "
                     "revision = catalog_type_rules.revision + 1, updated_at = excluded.updated_at",
                     (kind, body.view_access, body.download_access, int(time.time())))
    return next(item for item in list_type_rules()["items"] if item["question_type"] == kind)
