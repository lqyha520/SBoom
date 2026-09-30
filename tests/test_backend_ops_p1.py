"""运维故障路径只模拟子进程与通知；与后端 CI 一起执行。"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


with patch.dict(sys.modules, {"backup_restore": load("backup_restore", "scripts/backup_restore.py")}):
    backup = load("ops_backup_test", "scripts/ops_backup.py")
ops = load("release_ops_test", "scripts/release/ops.py")
with patch.dict(sys.modules, {"ops": ops}):
    release = load("release_test", "scripts/release/release.py")


class OpsContracts(unittest.TestCase):
    def test_backup_replacement_keeps_receipt_readable_by_its_group(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "backup.json"
            chmod = Path.chmod
            modes = []
            def record_mode(path, mode, **kwargs):
                modes.append(mode)
                return chmod(path, mode, **kwargs)
            with patch.dict(os.environ, {"BACKUP_STATUS_FILE": str(target), "RESTIC_REPOSITORY": "s3:fixture/bucket"}, clear=True), \
                    patch.object(backup.backup_restore, "backup"), patch.object(backup, "run"), \
                    patch.object(Path, "chmod", record_mode):
                for timestamp in (100, 200):
                    with patch.object(backup.time, "time", return_value=timestamp):
                        backup.execute("backup")
                    self.assertEqual(json.loads(target.read_text()), {"completed_at": timestamp, "verified": True, "offsite": True})
                    if os.name == "posix":
                        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
                        self.assertEqual(target.stat().st_gid, target.parent.stat().st_gid)
            self.assertEqual(modes, [0o640, 0o640])
            self.assertFalse(target.with_suffix(".tmp").exists())

    def test_feishu_signed_restore_alert(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"code":0}'
        with patch.dict(os.environ, {'BACKUP_FEISHU_WEBHOOK': 'https://feishu.invalid/hook', 'BACKUP_FEISHU_SECRET': 'fixture-secret'}, clear=True), \
                patch.object(backup.time, 'time', return_value=1700000000), patch.object(backup, 'urlopen', return_value=response) as send:
            backup.notify(False, 'restore-check')
        request = send.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, 'https://feishu.invalid/hook')
        self.assertEqual(payload['msg_type'], 'text')
        self.assertIn('恢复演练失败', payload['content']['text'])
        self.assertEqual(payload['timestamp'], '1700000000')
        # 固定向量独立核对 timestamp/secret 的签名，避免误用常见的 webhook 签法。
        self.assertEqual(payload['sign'], 'eSSBpPPdWfBl7avPl9BWSBfQOnLGZ91Xn8G5oZis0sc=')
        self.assertNotIn('fixture-secret', request.data.decode())

    def test_feishu_unsigned_legacy_response(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"StatusCode":0}'
        with patch.dict(os.environ, {'BACKUP_FEISHU_WEBHOOK': 'https://feishu.invalid/hook'}, clear=True), \
                patch.object(backup, 'urlopen', return_value=response) as send:
            backup.notify(False)
        payload = json.loads(send.call_args.args[0].data)
        self.assertIn('备份失败', payload['content']['text'])
        self.assertNotIn('sign', payload)

    def test_feishu_rejection_or_invalid_response_is_failure(self):
        for body in (b'{"code":19021}', b'{}', b'not-json'):
            with self.subTest(body=body):
                response = MagicMock()
                response.__enter__.return_value.read.return_value = body
                with patch.dict(os.environ, {'BACKUP_FEISHU_WEBHOOK': 'https://feishu.invalid/hook'}, clear=True), \
                        patch.object(backup, 'urlopen', return_value=response), self.assertRaisesRegex(RuntimeError, '告警发送失败'):
                    backup.notify(False)

    def test_failed_heartbeat_and_wecom_do_not_skip_feishu(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"code":0}'
        with patch.dict(os.environ, {'BACKUP_HEARTBEAT_URL': 'https://heartbeat.invalid/id',
                                    'BACKUP_ALERT_WEBHOOK': 'https://wecom.invalid/hook',
                                    'BACKUP_FEISHU_WEBHOOK': 'https://feishu.invalid/hook'}, clear=True), \
                patch.object(backup, 'urlopen', side_effect=[OSError('offline'), OSError('offline'), response]) as send:
            with self.assertRaises(RuntimeError):
                backup.notify(False)
        self.assertEqual(send.call_count, 3)
        self.assertEqual(send.call_args.args[0].full_url, 'https://feishu.invalid/hook')

    def test_success_only_sends_heartbeat(self):
        with patch.dict(os.environ, {'BACKUP_HEARTBEAT_URL': 'https://heartbeat.invalid/id',
                                    'BACKUP_ALERT_WEBHOOK': 'https://wecom.invalid/hook',
                                    'BACKUP_FEISHU_WEBHOOK': 'https://feishu.invalid/hook'}, clear=True), \
                patch.object(backup, 'urlopen') as send:
            backup.notify(True)
        send.assert_called_once_with('https://heartbeat.invalid/id', timeout=15)

    def test_heartbeat_failure_does_not_skip_alert(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"errcode":0}'
        with patch.dict(os.environ, {"BACKUP_HEARTBEAT_URL": "https://heartbeat.invalid/id", "BACKUP_ALERT_WEBHOOK": "https://alert.invalid/key"}, clear=True), \
                patch.object(backup, "urlopen", side_effect=[OSError("offline"), response]) as send:
            with self.assertRaises(RuntimeError):
                backup.notify(False)
        self.assertEqual(send.call_count, 2)

    def test_restore_uses_separate_heartbeat(self):
        with patch.dict(os.environ, {"RESTORE_HEARTBEAT_URL": "https://restore.invalid/id", "BACKUP_HEARTBEAT_URL": "https://daily.invalid/id"}, clear=True), \
                patch.object(backup, "urlopen") as send:
            backup.notify(True, "restore-check")
            self.assertEqual(send.call_args.args[0], "https://restore.invalid/id")

    def test_restore_failure_removes_only_restore_container(self):
        with patch.object(sys, "argv", ["ops.py", "restore-check"]), \
                patch.object(ops.subprocess, "run", side_effect=[None, RuntimeError("failed"), None]) as execute:
            with self.assertRaises(RuntimeError):
                ops.main()
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertEqual(commands[-1][-3:], ["rm", "-sf", "restore-db"])
        self.assertFalse(any("down" in command for command in commands))

    def test_unhealthy_release_rolls_back_exact_image_and_preserves_configuration(self):
        with tempfile.TemporaryDirectory() as root:
            env = Path(root) / "release.env"
            original = "APP_IMAGE=app:old\nCOMPOSE_PROJECT_NAME=existing\n"
            env.write_text(original)
            def run(command, environment=None):
                if command[-3:] == ["ps", "-q", "app"]:
                    return "app-container"
                if command[:2] == ["docker", "inspect"]:
                    return "sha256:old-image"
                return ""
            with patch.dict(os.environ, {"RELEASE_ENV_FILE": str(env)}), \
                    patch.object(sys, "argv", ["release.py", "--image", "app:new", "--state-dir", root]), \
                    patch.object(release, "run", side_effect=run) as execute, \
                    patch.object(release.subprocess, "run"), \
                    patch.object(release, "urlopen", side_effect=OSError("unhealthy")):
                with self.assertRaisesRegex(RuntimeError, "已恢复"):
                    release.main()
            updates = [call for call in execute.call_args_list if "up" in call.args[0]]
            self.assertEqual(len(updates), 2)
            self.assertEqual(updates[-1].args[1]["APP_IMAGE"], "sha256:old-image")
            self.assertTrue(all(call.args[0][-1] == "app" and "--no-deps" in call.args[0] for call in updates))
            self.assertEqual(env.read_text(), original)
