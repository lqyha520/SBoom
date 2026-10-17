"""固定样本真实模型评测：显式付费、持久化请求编号、只读恢复、人工盲评。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.models import GenerateRequest

SUITE = ROOT / "tests/fixtures/generation-evaluation.json"


def reject_constant(_: str):
    raise ValueError("非有限数字")


def read_json(path: Path):
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("评测文件超过16 MiB")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def save_json(path: Path, value) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_suite(path: Path) -> list[dict]:
    data = read_json(path)
    if data.get("version") != 1 or not isinstance(data.get("cases"), list) or not 1 <= len(data["cases"]) <= 100:
        raise ValueError("评测集格式错误")
    ids = set()
    for case in data["cases"]:
        if not re.fullmatch(r"[a-z0-9-]{1,80}", case["id"]) or case["id"] in ids:
            raise ValueError("评测编号无效或重复")
        ids.add(case["id"])
        request = GenerateRequest.model_validate(case["request"])
        if request.stream or set(case["request"]) - set(GenerateRequest.model_fields):
            raise ValueError("评测只支持非流式正式请求字段")
    return [dict(case) for case in data["cases"]]


def validate_base(base: str) -> str:
    parsed = urlsplit(base)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")
            or (parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"))):
        raise ValueError("目标必须是HTTPS源地址或本机HTTP，不得携带凭证、路径或查询参数")
    return base.rstrip("/")


@contextmanager
def authenticated(base: str):
    username, password = os.environ.get("LC_EVAL_USERNAME"), os.environ.get("LC_EVAL_PASSWORD")
    if not username or not password:
        raise ValueError("请通过LC_EVAL_USERNAME/LC_EVAL_PASSWORD提供专用评测账号")
    with httpx.Client(base_url=validate_base(base), timeout=600, follow_redirects=False, trust_env=False) as client:
        response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
        response.raise_for_status()
        client.headers["X-Workspace-User"] = str(response.json()["id"])
        try:
            yield client
        finally:
            try:
                client.post("/api/v1/auth/logout", timeout=10)
            except httpx.HTTPError:
                pass


def collect_case(client: httpx.Client, case: dict) -> None:
    try:
        response = client.get("/api/v1/me/generations/" + case["request_id"])
        response.raise_for_status()
        value = response.json()
        case["observation"] = {key: value.get(key) for key in ("status", "result", "error", "usage", "cache_expired")}
        case.pop("collection_error", None)
    except (httpx.HTTPError, ValueError) as error:
        # 不保存可能包含凭证或上游响应内容的异常消息，也不自动重发收费请求。
        case["collection_error"] = type(error).__name__


def run_cases(client: httpx.Client, cases: list[dict], directory: Path, identity: dict) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    run = {"version": 1, **identity, "cases": [
        {**case, "request_id": "eval-" + uuid.uuid4().hex, "submitted": False} for case in cases
    ]}
    save_json(directory / "run.json", run)
    for case in run["cases"]:
        case["submitted"] = True
        save_json(directory / "run.json", run)
        started = time.monotonic()
        try:
            response = client.post("/api/v1/generate", json=case["request"], headers={"X-Request-ID": case["request_id"]})
            case["http_status"] = response.status_code
        except httpx.HTTPError as error:
            case["transport_error"] = type(error).__name__
        finally:
            case["request_elapsed_ms"] = round((time.monotonic() - started) * 1000)
            save_json(directory / "run.json", run)
        collect_case(client, case)
        save_json(directory / "run.json", run)
        if case.get("observation", {}).get("status") not in ("succeeded", "failed"):
            break
    return run


def questions(case: dict) -> list[dict]:
    observation = case.get("observation") or {}
    result = observation.get("result")
    sections = ([result] if isinstance(result, dict) and "questions" in result else result.get("sections", [])) if isinstance(result, dict) else []
    if not sections:
        sections = (observation.get("error") or {}).get("partial_sections", [])
    return [{"key": digest({"case": case["id"], "section": si, "index": qi, "passage": section.get("passage"), "question": q}),
             "passage": section.get("passage", ""), "question": q}
            for si, section in enumerate(sections) for qi, q in enumerate(section.get("questions", []))]


def ratings_template(run: dict) -> dict:
    # 人工表不展示模型复核结论，避免把模型自评当作真值。
    return {"version": 1, "run_digest": digest(run), "questions": [
        {"key": item["key"], "case": case["id"], "passage": item["passage"],
         "question": {key: value for key, value in item["question"].items() if key not in ("quality_status", "quality_issues")},
         "correct": None, "reason": ""}
        for case in run["cases"] for item in questions(case)
    ]}


def summarize(run: dict, ratings: dict | None = None, prices: tuple[float, float] | None = None) -> dict:
    if ratings and ratings.get("run_digest") != digest(run):
        raise ValueError("人工评分与当前结果不匹配，请重新生成评分表")
    if prices and any(not math.isfinite(value) or value < 0 for value in prices):
        raise ValueError("价格必须是有限非负数")
    expected = {item["key"] for case in run["cases"] for item in questions(case)}
    labels = {}
    for item in (ratings or {}).get("questions", []):
        if item["key"] not in expected or item["key"] in labels or (item["correct"] is not None and type(item["correct"]) is not bool):
            raise ValueError("人工评分编号重复、未知或评分不是布尔值")
        if item["correct"] is False and not str(item.get("reason", "")).strip():
            raise ValueError("错误题必须填写核对依据")
        labels[item["key"]] = item["correct"]
    rows = []
    for case in run["cases"]:
        observation = case.get("observation") or {}
        items = questions(case)
        judged = [labels[item["key"]] is True for item in items if labels.get(item["key"]) is not None]
        usage = observation.get("usage") or {}
        usage_keys = ("model_calls", "reported_calls", "prompt_tokens", "completion_tokens")
        complete_usage = (all(type(usage.get(key)) is int and usage[key] >= 0 for key in usage_keys)
                          and usage["reported_calls"] == usage["model_calls"])
        terminal = observation.get("status") in ("succeeded", "failed") and not observation.get("cache_expired")
        cost = ((usage["prompt_tokens"] * prices[0] + usage["completion_tokens"] * prices[1]) / 1_000_000
                if complete_usage and prices and terminal else None)
        rows.append({"id": case["id"], **{key: case["request"][key] for key in ("grade", "subject", "game_type", "difficulty")},
                     "status": observation.get("status", "not_submitted" if not case["submitted"] else "unknown"),
                     "requested": case["request"]["question_count"], "returned": len(items),
                     "missing": max(0, case["request"]["question_count"] - len(items)) if terminal else None,
                     "judged": len(judged), "correct": sum(judged), "request_elapsed_ms": case.get("request_elapsed_ms"),
                     "estimated_cost": cost, "usage_complete": complete_usage, "usage": usage})
    terminal_rows = [row for row in rows if row["missing"] is not None]
    requested = sum(row["requested"] for row in terminal_rows)
    returned, judged = sum(row["returned"] for row in rows), sum(row["judged"] for row in rows)
    return {"version": 1, "model_label": run.get("model_label"), "cases": rows,
            "coverage": {"cases": len(rows), "terminal": len(terminal_rows), "returned_questions": returned, "human_judged": judged},
            "missing_rate": sum(row["missing"] for row in terminal_rows) / requested if requested else None,
            "human_correct_rate": sum(row["correct"] for row in rows) / judged if judged else None,
            "human_coverage": judged / returned if returned else None,
            "false_rejection_rate": None,
            "limitations": ["正确率仅针对人工已核对题，未评分不视为正确。",
                            "服务端不返回剔除题原文，不能据缺题数估算误剔除率。",
                            "费用按提供的每百万token价格估算；用量未完整上报时不输出费用。",
                            "request_elapsed_ms是首次HTTP请求耗时，断线后查询恢复不代表全程生成耗时。"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--suite", type=Path, default=SUITE)
    run = sub.add_parser("run")
    run.add_argument("--suite", type=Path, default=SUITE)
    run.add_argument("--limit", type=int, default=1)
    run.add_argument("--model-label", required=True)
    run.add_argument("--confirm-paid", action="store_true")
    for command in (run, sub.add_parser("collect")):
        command.add_argument("--base-url", required=True)
        command.add_argument("--directory", type=Path, required=True)
    for name in ("ratings", "report"):
        command = sub.add_parser(name)
        command.add_argument("--directory", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        if name == "report":
            command.add_argument("--ratings", type=Path)
            command.add_argument("--input-per-million", type=float)
            command.add_argument("--output-per-million", type=float)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            print(json.dumps({"cases": load_suite(args.suite), "paid": False}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "run":
            cases = load_suite(args.suite)
            if not args.confirm_paid or not 1 <= args.limit <= len(cases):
                raise ValueError("真实调用须显式--confirm-paid，limit须在评测集范围内")
            with authenticated(args.base_url) as client:
                data = run_cases(client, cases[:args.limit], args.directory, {
                    "target_digest": digest(validate_base(args.base_url)), "suite_digest": digest(cases), "model_label": args.model_label,
                    "account_digest": digest(client.headers["X-Workspace-User"]),
                })
                if any(case.get("observation", {}).get("status") not in ("succeeded", "failed") for case in data["cases"]):
                    return 1
        else:
            data = read_json(args.directory / "run.json")
            if args.command == "collect":
                if data["target_digest"] != digest(validate_base(args.base_url)):
                    raise ValueError("恢复查询必须使用原目标")
                with authenticated(args.base_url) as client:
                    if data["account_digest"] != digest(client.headers["X-Workspace-User"]):
                        raise ValueError("恢复查询必须使用原评测账号")
                    for case in data["cases"]:
                        if case["submitted"]:
                            collect_case(client, case)
                            save_json(args.directory / "run.json", data)
                if any(case["submitted"] and (case.get("collection_error") or case.get("observation", {}).get("status") not in ("succeeded", "failed"))
                       for case in data["cases"]):
                    return 1
            else:
                if args.output.exists():
                    raise ValueError("输出已存在，请指定新文件，避免覆盖人工评分")
                if args.command == "ratings":
                    value = ratings_template(data)
                else:
                    if (args.input_per_million is None) != (args.output_per_million is None):
                        raise ValueError("输入和输出token价格须同时提供")
                    prices = None if args.input_per_million is None else (args.input_per_million, args.output_per_million)
                    value = summarize(data, read_json(args.ratings) if args.ratings else None, prices)
                save_json(args.output, value)
        return 0
    except (ValueError, KeyError, TypeError, OSError, httpx.HTTPError) as error:
        print(f"评测未完成（{type(error).__name__}）；保留已有结果，核对参数后继续。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
