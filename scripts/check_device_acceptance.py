"""真机验收记录：缺少设备、重复测量、功能确认或证据时失败，不伪造真机结果。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

SCENARIOS = {
    "cold_start": ("home_cold", 5000),
    "reader_40_pages": ("reader_image", 1500),
    "pdf_open": ("pdf_open", 15000),
    "foreground_resume": ("home_warm", 3000),
}
PROFILES = ("android-low-weak", "ios-weak")


def template() -> dict:
    return {"version": 1, "build_commit": "", "records": [
        {"profile": profile, "scenario": scenario, "device": "", "os": "", "wechat": "", "network": "",
         "tested_at": "", "functional_pass": None, "evidence": [], "diagnostics": []}
        for profile in PROFILES for scenario in SCENARIOS
    ]}


def evidence_path(root: Path, value: str) -> Path:
    if not isinstance(value, str):
        raise ValueError("证据路径必须为字符串")
    candidate = (root / value).resolve()
    if not value or Path(value).is_absolute() or not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        raise ValueError("证据须为验收目录内的现有文件")
    return candidate


def file_digest(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def check(data: dict, root: Path) -> dict:
    errors, rows = [], []
    if not isinstance(data, dict):
        return {"passed": False, "errors": ["验收记录必须为对象"], "records": []}
    if data.get("version") != 1 or not isinstance(data.get("build_commit"), str) or not data["build_commit"].strip():
        errors.append("缺少构建版本")
    records = data.get("records", [])
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        return {"passed": False, "errors": [*errors, "records必须为数组"], "records": []}
    for profile in PROFILES:
        for scenario, (metric, limit) in SCENARIOS.items():
            matching = [record for record in records if record.get("profile") == profile and record.get("scenario") == scenario]
            label = profile + "/" + scenario
            if len(matching) != 1:
                errors.append(label + ": 缺少或重复记录")
                continue
            record = matching[0]
            try:
                if any(not isinstance(record.get(key), str) or not record[key].strip() for key in ("device", "os", "wechat", "network", "tested_at")):
                    raise ValueError("缺少设备、系统、微信、网络或验收时间")
                if record.get("functional_pass") is not True:
                    raise ValueError("尚未确认完整功能通过")
                if not isinstance(record.get("evidence"), list) or not record["evidence"]:
                    raise ValueError("缺少真机录像或性能trace")
                files = [evidence_path(root, value) for value in record["evidence"]]
                if not isinstance(record.get("diagnostics"), list) or not record["diagnostics"]:
                    raise ValueError("缺少复制的故障记录")
                count, p95 = 0, 0.0
                seen = set()
                for value in record["diagnostics"]:
                    path = evidence_path(root, value)
                    if path in seen:
                        raise ValueError("同一诊断文件不能重复计入样本")
                    seen.add(path)
                    if path.stat().st_size > 1024 * 1024:
                        raise ValueError("诊断文件过大")
                    diagnostic = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(diagnostic, dict) or diagnostic.get("version") != 2:
                        raise ValueError("诊断版本不支持")
                    if (not isinstance(diagnostic.get("performance"), list) or any(not isinstance(item, dict) for item in diagnostic["performance"])
                            or not isinstance(diagnostic.get("events", []), list) or any(not isinstance(item, dict) for item in diagnostic.get("events", []))):
                        raise ValueError("诊断结构无效")
                    values = [item for item in diagnostic.get("performance", []) if item.get("kind") == metric]
                    if len(values) != 1:
                        raise ValueError("缺少所需性能指标")
                    sample = values[0]
                    if (type(sample.get("count")) is not int or not 1 <= sample["count"] <= 60 or sample.get("unit") != "ms"
                            or any(type(sample.get(key)) not in (int, float) or not math.isfinite(sample[key]) or sample[key] < 0
                                   for key in ("p50", "p95", "max"))
                            or not sample["p50"] <= sample["p95"] <= sample["max"]):
                        raise ValueError("诊断样本无效")
                    if any(event.get("kind") in ("runtime", "promise", "memory") and event.get("count", 0) > 0
                           for event in diagnostic.get("events", [])):
                        raise ValueError("诊断含运行异常或内存告警，需要排查后复测")
                    count += sample["count"]
                    p95 = max(p95, sample["p95"])
                if count < 5 or p95 > limit:
                    raise ValueError(f"至少5次测量，单次会话p95最大值须不高于{limit}ms")
                rows.append({"profile": profile, "scenario": scenario, "samples": count, "max_session_p95_ms": p95,
                             "evidence_sha256": [file_digest(path) for path in files]})
            except (ValueError, TypeError, KeyError, OSError) as error:
                errors.append(label + ": " + str(error))
    return {"passed": not errors, "errors": errors, "records": rows,
            "note": "本工具校验操作者记录和证据完整性，不验证设备真实性；PDF打开成功不等于另存成功，须人工确认。"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("init", "check"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == "init":
            args.path.parent.mkdir(parents=True, exist_ok=True)
            with args.path.open("x", encoding="utf-8") as file:
                json.dump(template(), file, ensure_ascii=False, indent=2)
            return 0
        result = check(json.loads(args.path.read_text(encoding="utf-8")), args.path.parent)
    except (OSError, ValueError, TypeError) as error:
        result = {"passed": False, "errors": ["记录不可用: " + type(error).__name__]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
