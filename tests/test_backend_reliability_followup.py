"""发布准入、备份重试和失败状态的故障回归；不使用真实业务数据库。"""
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

import pytest
import test_backend_generation_stages as fixtures

from app.services.generation_drain import clear_drain, set_drain

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import backup_gateway
import offsite_ops
import ops_state
import production_monitor
import public_monitor
from install_reliability_ops import service


class DeploymentDrainTests(unittest.TestCase):
    setUp = fixtures.StageAPI.setUp

    def test_drain_rejects_new_paid_calls_but_preserves_replay_and_ownership(self):
        first = self.client.post('/api/v1/generate-batch', json=self.body, headers={'X-Request-ID': 'before-drain'})
        self.assertEqual(first.status_code, 200)
        calls = len(self.calls)
        set_drain('release-one')
        try:
            replay = self.client.post('/api/v1/generate-batch', json=self.body, headers={'X-Request-ID': 'before-drain'})
            self.assertEqual(replay.status_code, 200)
            with self.assertRaises(RuntimeError):
                set_drain('release-two')
            clear_drain('release-two')
            denied = self.client.post('/api/v1/generate-batch', json=self.body, headers={'X-Request-ID': 'during-drain'})
            self.assertEqual(denied.status_code, 503)
            self.assertEqual(denied.json()['detail']['code'], 'generation_deploying')
            self.assertEqual(len(self.calls), calls)
        finally:
            clear_drain('release-one')
        self.calls.clear()
        self.assertEqual(self.client.post('/api/v1/generate-batch', json=self.body,
                                         headers={'X-Request-ID': 'after-drain'}).status_code, 200)


def test_expired_and_failed_operations_are_unhealthy(tmp_path):
    path = tmp_path / 'operation.json'
    for state, stamp, expected in (('failed', time.time(), False), ('running', time.time() - 1300, False),
                                    ('running', time.time(), True), ('succeeded', time.time(), True)):
        ops_state.write_json(path, {'state': state, 'checked_at': stamp, 'stage': 'transfer'})
        assert ops_state.operation_check(path)['ok'] is expected


def test_gateway_never_allows_unrestricted_shell_or_other_directories():
    assert backup_gateway.allowed_command('operation') == ['operation']
    assert backup_gateway.allowed_command('rsync --server --sender -logDtpre.iLsfxCIvu --timeout=90 . /data/data1/learn-coach-ops/repository/')
    for command in ('sh', 'cat /etc/passwd', 'rsync --server --sender -a . /root/', 'backup; id'):
        with pytest.raises(ValueError):
            backup_gateway.allowed_command(command)


def test_offsite_exhaustion_preserves_last_good_receipt_and_retries(tmp_path, monkeypatch):
    monkeypatch.setenv('OFFSITE_ROOT', str(tmp_path))
    monkeypatch.setenv('OFFSITE_IMAGE', 'fixture-image')
    monkeypatch.setenv('OFFSITE_HOST', 'fixture.invalid')
    target = offsite_ops.Offsite()
    previous = {'verified': True, 'snapshot_id': 'old-good'}
    ops_state.write_json(tmp_path / 'status/backup.json', previous)
    monkeypatch.setattr(target, 'initialize', lambda: None)
    monkeypatch.setattr(target, 'restic', lambda *a, **k: b'[{"id":"independent-old"}]')
    remote = Mock(side_effect=RuntimeError('ssh exit=255'))
    monkeypatch.setattr(target, 'remote', remote)
    monkeypatch.setattr(offsite_ops.time, 'sleep', lambda _: None)
    monkeypatch.setattr(target, 'state', lambda state, stage, attempt=1, error=None:
                        ops_state.operation(tmp_path / 'status/operation.json', state, stage, attempt=attempt))
    with pytest.raises(RuntimeError, match='三次'):
        target.sync()
    assert remote.call_count == 3
    assert json.loads((tmp_path / 'status/backup.json').read_text()) == previous
    assert json.loads((tmp_path / 'status/operation.json').read_text())['state'] == 'failed'


def test_monitor_container_discovery_failure_replaces_old_green_state(tmp_path, monkeypatch):
    output = tmp_path / 'latest.json'
    output.write_text('{"ok":true,"checked_at":1}')
    monkeypatch.setattr(sys, 'argv', ['monitor', '--output', str(output), '--backup-status', str(tmp_path / 'backup.json')])
    monkeypatch.setattr(production_monitor.subprocess, 'check_output', Mock(side_effect=RuntimeError('docker unavailable')))
    monkeypatch.setattr(production_monitor, 'check', lambda _: {'checked_at': 200, 'checks': {'readyz': {'ok': False}}})
    assert production_monitor.main() == 1
    value = json.loads(output.read_text())
    assert not value['ok'] and value['checked_at'] == 200 and not value['checks']['container']['ok']


def test_public_probe_checks_assets_and_certificate(monkeypatch):
    monkeypatch.setattr(public_monitor, 'fetch', lambda url, **kwargs: b'<script src="/missing.js"></script>' if url.endswith('/') else (_ for _ in ()).throw(ValueError('missing')))
    monkeypatch.setattr(public_monitor, 'tls_days', lambda *args: 10)
    result = public_monitor.check_public('https://fixture.invalid')
    assert not result['ok']
    assert all(not value['ok'] for value in result['checks'].values())


def test_public_probe_rejects_spa_fallback_for_missing_scripts(monkeypatch):
    monkeypatch.setattr(public_monitor, 'fetch', lambda *args, **kwargs: b'<!doctype html><script src="/missing.js"></script>')
    monkeypatch.setattr(public_monitor, 'tls_days', lambda *args: 30)
    result = public_monitor.check_public('https://fixture.invalid')
    assert not result['ok'] and result['checks']['tls']['ok']


def test_five_minute_monitor_is_not_limited_to_three_starts_per_two_hours():
    host = Mock()
    service(host, 'learn-coach-public-monitor', '/monitor', '/settings')
    text = host.write.call_args.args[1].decode()
    assert 'StartLimitIntervalSec=0' in text and 'StartLimitBurst=3' not in text
    service(host, 'learn-coach-production-offsite', '/backup', '/settings', retry=True)
    text = host.write.call_args.args[1].decode()
    assert 'StartLimitBurst=3' in text and 'Restart=on-failure' in text
