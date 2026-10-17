"""评测工具在离线HTTP和临时文件中测试；不发付费请求或伪造设备验收。"""
import json

import httpx
import pytest

from scripts import check_device_acceptance as device
from scripts import evaluate_generation as evaluation


def fixture_run():
    return {"version": 1, "model_label": "offline", "cases": [{
        **evaluation.load_suite(evaluation.SUITE)[0], "request_id": "offline-one", "submitted": True,
        "observation": {"status": "succeeded", "result": {"questions": [
            {"stem": "2+3=?", "answer": 5, "analysis": "2+3=5", "quality_status": "passed"},
        ]}, "usage": {"model_calls": 2, "reported_calls": 2, "prompt_tokens": 100, "completion_tokens": 50}},
    }]}


def test_suite_is_valid_and_plan_or_unconfirmed_run_never_authenticates(monkeypatch, tmp_path, capsys):
    assert len(evaluation.load_suite(evaluation.SUITE)) == 8
    monkeypatch.setattr(evaluation, "authenticated", lambda _: pytest.fail("不得联网"))
    assert evaluation.main(["plan"]) == 0
    assert evaluation.main(["run", "--base-url", "http://localhost", "--directory", str(tmp_path / "run"), "--model-label", "offline"]) == 1
    assert not (tmp_path / "run").exists()


def test_timeout_retains_original_id_and_stops_next_request(tmp_path):
    directory = tmp_path / "run"
    posts, gets = [], []

    def transport(request):
        saved = evaluation.read_json(directory / "run.json")
        assert saved["cases"][0]["submitted"]
        if request.method == "POST":
            posts.append(request.headers["X-Request-ID"])
            assert posts[-1] == saved["cases"][0]["request_id"]
            raise httpx.ReadTimeout("SECRET upstream detail", request=request)
        gets.append(request.url.path)
        return httpx.Response(200, json={"status": "running"})

    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(transport)) as client:
        result = evaluation.run_cases(client, evaluation.load_suite(evaluation.SUITE)[:2], directory, {})
        evaluation.collect_case(client, result["cases"][0])
    assert len(posts) == 1 and len(gets) == 2
    assert result["cases"][1]["submitted"] is False
    assert "SECRET" not in (directory / "run.json").read_text(encoding="utf-8")
    assert result["cases"][0]["observation"]["status"] == "running"
    with pytest.raises(FileExistsError):
        evaluation.run_cases(None, [], directory, {})


def test_human_review_is_required_and_bound_to_exact_output():
    run = fixture_run()
    report = evaluation.summarize(run)
    assert report["human_correct_rate"] is None
    assert report["false_rejection_rate"] is None
    ratings = evaluation.ratings_template(run)
    assert "quality_status" not in ratings["questions"][0]["question"]
    ratings["questions"][0].update(correct=False, reason="离线错误样例")
    report = evaluation.summarize(run, ratings, (2, 4))
    assert report["human_correct_rate"] == 0
    assert report["missing_rate"] == 2 / 3
    assert report["human_coverage"] == 1
    assert report["cases"][0]["estimated_cost"] == 0.0004
    run["cases"][0]["observation"]["result"]["questions"][0]["answer"] = 6
    with pytest.raises(ValueError, match="不匹配"):
        evaluation.summarize(run, ratings)


def test_incomplete_usage_pending_results_and_invalid_ratings_never_look_complete():
    run = fixture_run()
    run["cases"][0]["observation"]["usage"]["reported_calls"] = 1
    assert evaluation.summarize(run, prices=(2, 4))["cases"][0]["estimated_cost"] is None
    run["cases"][0]["observation"]["status"] = "running"
    assert evaluation.summarize(run)["missing_rate"] is None
    with pytest.raises(ValueError):
        evaluation.summarize(run, prices=(float("nan"), 4))
    ratings = evaluation.ratings_template(run)
    ratings["questions"][0]["correct"] = "true"
    with pytest.raises(ValueError):
        evaluation.summarize(run, ratings)


@pytest.mark.parametrize("url", ["http://example.com", "https://user:secret@example.com", "https://example.com/path", "https://example.com/?token=secret"])
def test_unsafe_targets_rejected(url):
    with pytest.raises(ValueError):
        evaluation.validate_base(url)


def test_device_template_is_not_acceptance(tmp_path):
    result = device.check(device.template(), tmp_path)
    assert not result["passed"]
    assert len(result["errors"]) == 9


def device_fixture(tmp_path):
    data = device.template()
    data["build_commit"] = "offline-unit-test-only"
    (tmp_path / "evidence.txt").write_text("OFFLINE TEST, NOT DEVICE EVIDENCE", encoding="utf-8")
    for index, record in enumerate(data["records"]):
        metric = device.SCENARIOS[record["scenario"]][0]
        name = f"diagnostic-{index}.json"
        (tmp_path / name).write_text(json.dumps({"version": 2, "events": [], "performance": [
            {"kind": metric, "unit": "ms", "count": 5, "p50": 50, "p95": 100, "max": 120}
        ]}), encoding="utf-8")
        record.update(device="offline", os="offline", wechat="offline", network="offline", tested_at="offline",
                      functional_pass=True, evidence=["evidence.txt"], diagnostics=[name])
    return data


def test_device_record_validation_and_thresholds(tmp_path):
    data = device_fixture(tmp_path)
    assert device.check(data, tmp_path)["passed"]
    name = tmp_path / data["records"][0]["diagnostics"][0]
    saved = json.loads(name.read_text())
    for changes in ({"count": 1}, {"p95": 6000, "max": 7000}, {"p95": float("nan")}):
        value = json.loads(json.dumps(saved))
        value["performance"][0].update(changes)
        name.write_text(json.dumps(value))
        assert not device.check(data, tmp_path)["passed"]
    name.write_text(json.dumps(saved))
    data["records"][0]["diagnostics"] *= 2
    assert not device.check(data, tmp_path)["passed"]
    data["records"][0]["evidence"] = ["../outside.txt"]
    assert not device.check(data, tmp_path)["passed"]


def test_device_errors_and_missing_evidence_fail_closed(tmp_path):
    data = device_fixture(tmp_path)
    name = tmp_path / data["records"][0]["diagnostics"][0]
    saved = json.loads(name.read_text())
    saved["events"] = [{"kind": "memory", "count": 1}]
    name.write_text(json.dumps(saved))
    assert not device.check(data, tmp_path)["passed"]
    assert not device.check({"records": [None]}, tmp_path)["passed"]
