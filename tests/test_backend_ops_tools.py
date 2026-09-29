"""运维工具只在临时目录和 mock 网络/进程中验证，不连接数据库。"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import dev, ops_check, prune_artifacts, secure_archives, serve_detached


def test_backup_requires_verified_offsite_receipt(tmp_path: Path):
    receipt = tmp_path / "backup.json"
    receipt.write_text(json.dumps({"completed_at": 1000, "verified": True, "offsite": True}))
    assert ops_check.backup_age(receipt, 4600, 2)["ok"]
    assert not ops_check.backup_age(receipt, 11800, 2)["ok"]
    receipt.write_text(json.dumps({"completed_at": 1000, "verified": True, "offsite": False}))
    with pytest.raises(ValueError):
        ops_check.backup_age(receipt, 4600, 2)
    receipt.write_text('{"completed_at": NaN, "verified": true, "offsite": true}')
    with pytest.raises(ValueError):
        ops_check.backup_age(receipt, 4600, 2)


def test_maintenance_labels_and_counter_reset():
    assert ops_check.maintenance_count(b'maintenance_failures_total{task="a"} 2\nmaintenance_failures_total{task="b"} 3\n') == 5
    assert ops_check.maintenance_delta(5, 4) == 1
    assert ops_check.maintenance_delta(2, 5) == 2
    assert ops_check.maintenance_delta(2, None) == 2
    with pytest.raises(ValueError):
        ops_check.maintenance_count(b"unrelated 1")


def test_ops_report_fails_closed_and_persists_increment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    receipt = tmp_path / "backup.json"
    receipt.write_text(json.dumps({"completed_at": 1000, "verified": True, "offsite": True}))
    count = [0]
    monkeypatch.setattr(ops_check.time, "time", lambda: 1100)
    monkeypatch.setattr(ops_check, "fetch", lambda url, **_: b"ok" if "ready" in url else f"maintenance_failures_total {count[0]}\n".encode())
    monkeypatch.setattr(ops_check.shutil, "disk_usage", lambda _: argparse.Namespace(total=100 * 1024**3, free=50 * 1024**3))
    args = argparse.Namespace(ready_url="http://127.0.0.1/readyz", metrics_url="http://127.0.0.1/metrics", disk_path=tmp_path,
                              min_free_gib=5, min_free_percent=15, backup_status=str(receipt), max_backup_hours=27,
                              tls_host=None, tls_port=443, min_tls_days=14, state_file=str(tmp_path / "state.json"))
    assert ops_check.check(args)["ok"]
    count[0] = 2
    report = ops_check.check(args)
    assert not report["ok"] and report["checks"]["maintenance"]["new_failures"] == 2
    assert ops_check.check(args)["ok"]
    args.backup_status = None
    assert not ops_check.check(args)["checks"]["backup"]["ok"]


def test_dev_only_targets_test_service(monkeypatch: pytest.MonkeyPatch):
    down = dev.commands("down", [])
    assert down[0][-2:] == ["stop", "test-db"]
    assert "down" not in down[0]
    monkeypatch.setattr(sys, "argv", ["dev.py", "test", "tests/test_backend_ops_tools.py"])
    monkeypatch.setenv("DATABASE_URL", "sensitive-daily-db")
    run = Mock(return_value=argparse.Namespace(returncode=0))
    monkeypatch.setattr(dev.subprocess, "run", run)
    assert dev.main() == 0
    assert len(run.call_args_list) == 2
    for call in run.call_args_list:
        assert "DATABASE_URL" not in call.kwargs["env"]
        assert call.kwargs["env"]["LC_TEST_PG_ADMIN"] == dev.TEST_DSN


def old_file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("diagnostic", encoding="utf-8")
    os.utime(path, (1000, 1000))
    return path


def test_prune_protects_backups_environment_and_review(tmp_path: Path):
    root = tmp_path / "artifacts"
    keep = [old_file(root / "database.dump"), old_file(root / ".env.production"),
            old_file(root / "venv" / "old.py"), old_file(root / "p2-p3-2026-09-28" / "test.log"),
            old_file(root / "backups" / "note.txt")]
    expired = old_file(root / "old.log")
    plan = prune_artifacts.inventory(root, 30, now=86400 * 60)
    assert expired.exists()  # inventory is always read-only
    assert [item["path"] for item in plan if item["action"] == "candidate"] == ["old.log"]
    assert prune_artifacts.apply_plan(root, plan, False) == ["old.log"]
    assert not expired.exists() and all(path.exists() for path in keep)


def test_prune_archives_without_overwrite_and_rejects_changed_file(tmp_path: Path):
    root = tmp_path / "artifacts"
    expired = old_file(root / "old.log")
    plan = prune_artifacts.inventory(root, 30, now=86400 * 60)
    expired.write_text("modified")
    with pytest.raises(ValueError, match="修改"):
        prune_artifacts.apply_plan(root, plan, False)
    expired = old_file(root / "old.log")
    plan = prune_artifacts.inventory(root, 30, now=86400 * 60)
    prune_artifacts.apply_plan(root, plan, True)
    assert not expired.exists()
    assert len(list(root.glob("loose-archive-*/old.log"))) == 1
    old_file(root / "old.log")
    with pytest.raises(ValueError, match="已存在"):
        prune_artifacts.apply_plan(root, plan, True)


def test_prune_rejects_plan_outside_root(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    external = old_file(tmp_path / "external.log")
    with pytest.raises(ValueError):
        prune_artifacts.apply_plan(root, [{"action": "candidate", "path": "../external.log"}], False)
    assert external.exists()


def test_launcher_refuses_legacy_or_unverified_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pidfile = tmp_path / "server.pid"
    monkeypatch.setattr(serve_detached, "PID_FILE", pidfile)
    pidfile.write_text("1234")
    assert serve_detached.read_state() is None
    run = Mock()
    monkeypatch.setattr(serve_detached.subprocess, "run", run)
    assert serve_detached.stop() == 1
    run.assert_not_called()
    assert serve_detached.LOG_FILE.name == "launcher.log"
    assert serve_detached.LOG_FILE.parent.name == "logs"


def test_launcher_requires_readyz_and_has_hidden_detached_supervisor(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(serve_detached, "health", lambda *_: False)
    monkeypatch.setattr(serve_detached, "read_state", lambda: None)
    popen = Mock(return_value=Mock(poll=Mock(return_value=1)))
    monkeypatch.setattr(serve_detached.subprocess, "Popen", popen)
    monkeypatch.setattr(serve_detached, "IS_WIN", True)
    assert serve_detached.start(0) == 1
    assert popen.call_args.args[0][-1] == "--supervise"
    assert popen.call_args.kwargs["creationflags"] & 0x00000008
    assert popen.call_args.kwargs["stdout"] == serve_detached.subprocess.DEVNULL


def test_secure_archive_roundtrip_and_authenticated_tamper(tmp_path: Path):
    from cryptography.exceptions import InvalidTag
    key = b"K" * 32
    source = tmp_path / "backup.dump"
    source.write_bytes(b"private-backup" * 100000)
    encrypted = tmp_path / "backup.lcenc"
    digest = secure_archives.encrypt_file(source, encrypted, "data/backups/backup.dump", key)
    assert secure_archives.decrypt_file(encrypted, key, expected_source="data/backups/backup.dump") == digest
    assert digest == secure_archives.digest_file(source)
    with pytest.raises(ValueError):
        secure_archives.decrypt_file(encrypted, key, expected_source="another/path")
    with pytest.raises(InvalidTag):
        secure_archives.decrypt_file(encrypted, b"X" * 32, expected_source="data/backups/backup.dump")
    raw = bytearray(encrypted.read_bytes())
    raw[-2] ^= 1
    encrypted.write_bytes(raw)
    with pytest.raises(InvalidTag):
        secure_archives.decrypt_file(encrypted, key, expected_source="data/backups/backup.dump")


def test_secure_archive_empty_and_truncated(tmp_path: Path):
    source, encrypted = tmp_path / "empty", tmp_path / "empty.lcenc"
    source.write_bytes(b"")
    key = b"K" * 32
    digest = secure_archives.encrypt_file(source, encrypted, "empty", key)
    assert secure_archives.decrypt_file(encrypted, key, expected_source="empty") == digest
    encrypted.write_bytes(encrypted.read_bytes()[:-1])
    with pytest.raises(ValueError, match="截断"):
        secure_archives.decrypt_file(encrypted, key, expected_source="empty")


def test_secure_archive_allowlist_migration_restore(tmp_path: Path):
    root, target = tmp_path / "repo", tmp_path / "encrypted"
    target.mkdir()
    selected = old_file(root / ".review/backups/example.dump")
    backup_key = old_file(root / "data/backups/old/secret_key.txt")
    live_key = old_file(root / "data/secret_key.txt")
    business = old_file(root / "data/paper-files/live.pdf")
    evidence = old_file(root / "artifacts/p2-p3-2026-09-28/evidence.log")
    assert set(secure_archives.sources(root)) == {selected, backup_key}
    manifest = secure_archives.migrate(root, target, b"K" * 32)
    assert not selected.exists() and not backup_key.exists()
    assert live_key.exists() and business.exists() and evidence.exists()
    destination = tmp_path / "restored"
    assert secure_archives.restore(manifest, destination, b"K" * 32) == 2
    assert (destination / "data/backups/old/secret_key.txt").read_text() == "diagnostic"
    with pytest.raises(ValueError, match="目标已存在"):
        secure_archives.restore(manifest, destination, b"K" * 32)


def test_secure_archive_verification_failure_preserves_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root, target = tmp_path / "repo", tmp_path / "encrypted"
    target.mkdir()
    source = old_file(root / ".review/backups/example.dump")
    monkeypatch.setattr(secure_archives, "decrypt_file", lambda *_args, **_kwargs: "wrong")
    with pytest.raises(ValueError, match="哈希"):
        secure_archives.migrate(root, target, b"K" * 32)
    assert source.exists()
    assert not (target / "manifest.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="DPAPI仅限Windows当前用户")
def test_current_user_dpapi_roundtrip():
    raw = b"test-key-material" * 2
    encrypted = secure_archives.dpapi(raw)
    assert encrypted != raw
    assert secure_archives.dpapi(encrypted, decrypt=True) == raw


def test_launcher_rotates_dummy_child_output_without_application(tmp_path: Path):
    # 只启动临时目录中的打印进程，不执行仓库run.py，不打开业务端口。
    (tmp_path / "run.py").write_text("for _ in range(700):\n    print('x' * 10000)\n", encoding="utf-8")
    module_root = str(Path(serve_detached.__file__).resolve().parents[1])
    code = ("import sys, os; from pathlib import Path; "
            f"sys.path.insert(0, {module_root!r}); from scripts import serve_detached as s; "
            f"s.ROOT=Path({str(tmp_path)!r}); s.PID_FILE=s.ROOT/'server.pid'; "
            "s.LOG_FILE=s.ROOT/'data/logs/launcher.log'; "
            "os.environ['LC_LAUNCHER_TOKEN']='test-only-token-material-with-32-bytes'; "
            "raise SystemExit(s.supervise())")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=15,
                            creationflags=0x08000000 if os.name == "nt" else 0)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert not (tmp_path / "server.pid").exists()
    assert not (tmp_path / "server.log").exists()
    assert (tmp_path / "data/logs/launcher.log.1").exists()
    assert (tmp_path / "data/logs/launcher.log").stat().st_size < 5 * 1024**2
