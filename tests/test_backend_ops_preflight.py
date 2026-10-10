"""Readiness reports expose check names only and never start backup jobs."""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preflight = load('ops_preflight_checks', 'scripts/release/ops_preflight.py')
with patch.dict(sys.modules, {'ops_preflight': preflight}):
    ops = load('ops_preflight_entry', 'scripts/release/ops.py')


@pytest.fixture
def configuration(monkeypatch):
    environment = {
        'RESTIC_REPOSITORY': 's3:https://account.r2.cloudflarestorage.com/private-bucket',
        'AWS_ACCESS_KEY_ID': 'fixture-key-id', 'AWS_SECRET_ACCESS_KEY': 'fixture-secret',
        'RESTIC_PASSWORD_FILE': '/run/secrets/restic-password',
        'DATABASE_URL': 'postgresql://learncoach:private-db-password@db/learncoach',
        'BACKUP_STATUS_FILE': '/run/ops-status/backup.json',
        'BACKUP_HEARTBEAT_URL': 'https://hc-ping.com/fixture-daily-token',
        'RESTORE_HEARTBEAT_URL': 'https://hc-ping.com/fixture-monthly-token',
        'BACKUP_FEISHU_WEBHOOK': 'https://open.feishu.cn/open-apis/bot/v2/hook/private-token',
    }
    password = {'type': 'bind', 'source': '/etc/learn-coach/restic-password',
                'target': '/run/secrets/restic-password', 'read_only': True}
    services = {
        'backup': {'image': 'learncoach-ops:abcdef123456', 'environment': environment,
                   'volumes': [password, {'target': '/app/data', 'read_only': True}]},
        'restore-check': {'image': 'learncoach-ops:abcdef123456', 'network_mode': 'service:restore-db',
                          'environment': {**environment, 'LC_RESTORE_DATABASE_URL': 'postgresql://restore:fixture@127.0.0.1/lc_restore_probe'},
                          'volumes': [dict(password)]},
        'restore-db': {'tmpfs': ['/var/lib/postgresql/data:size=2g']},
    }
    execute = Mock(side_effect=lambda *_args, **_kwargs: argparse.Namespace(stdout=json.dumps({'services': services})))
    monkeypatch.setattr(preflight.subprocess, 'run', execute)
    monkeypatch.setattr(preflight, 'secret_file', lambda *_: True)
    monkeypatch.setattr(preflight, 'receipt_directory', lambda *_: True)
    return services, execute


def test_preflight_is_read_only_and_redacts_all_configuration(configuration):
    _, execute = configuration
    report = preflight.check_configuration(['docker', 'compose'])
    assert report['ok'] and report['scope'] == 'configuration_only'
    execute.assert_called_once()
    command = execute.call_args.args[0]
    assert command[-3:] == ['config', '--format', 'json']
    assert 'run' not in command and 'up' not in command
    assert execute.call_args.kwargs['capture_output'] is True
    text = json.dumps(report)
    for value in ('fixture-secret', 'private-db-password', 'private-token', 'private-bucket', 'fixture-daily-token'):
        assert value not in text


@pytest.mark.parametrize(('service', 'key', 'value', 'check'), [
    ('backup', 'RESTIC_REPOSITORY', '/local/backup', 'offsite_repository'),
    ('backup', 'RESTIC_REPOSITORY', 's3:https://ACCOUNT_ID.r2.cloudflarestorage.com/bucket', 'offsite_repository'),
    ('backup', 'RESTIC_REPOSITORY', None, 'offsite_repository'),
    ('backup', 'RESTIC_REPOSITORY', 's3:http://storage.example.net/bucket', 's3_https'),
    ('backup', 'AWS_ACCESS_KEY_ID', '', 'backup_s3_credentials'),
    ('restore-check', 'AWS_SECRET_ACCESS_KEY', '', 'restore_s3_credentials'),
    ('backup', 'DATABASE_URL', 'postgresql://learncoach:REPLACE@db/learncoach', 'database'),
    ('backup', 'BACKUP_HEARTBEAT_URL', '', 'backup_heartbeat'),
    ('backup', 'BACKUP_HEARTBEAT_URL', 'https://127.0.0.1/token', 'backup_heartbeat'),
    ('restore-check', 'RESTORE_HEARTBEAT_URL', '', 'restore_heartbeat'),
    ('restore-check', 'RESTORE_HEARTBEAT_URL', 'https://hc-ping.com/fixture-daily-token/', 'distinct_heartbeats'),
    ('backup', 'BACKUP_FEISHU_WEBHOOK', '', 'backup_alert_channel'),
    ('restore-check', 'BACKUP_FEISHU_WEBHOOK', '', 'restore_alert_channel'),
    ('restore-check', 'LC_RESTORE_DATABASE_URL', 'postgresql://u:p@production/learncoach', 'isolated_restore'),
])
def test_missing_or_unsafe_settings_fail_closed(configuration, service, key, value, check):
    services, _ = configuration
    services[service]['environment'][key] = value
    report = preflight.check_configuration(['docker', 'compose'])
    assert not report['ok'] and report['checks'][check] is False


@pytest.mark.parametrize('change', ['repository', 'password', 'image', 'ports', 'volume', 'tmpfs', 'readonly', 'receipt'])
def test_backup_and_restore_must_share_safe_configuration(configuration, change):
    services, _ = configuration
    if change == 'repository':
        services['restore-check']['environment']['RESTIC_REPOSITORY'] += '-other'
    elif change == 'password':
        services['restore-check']['volumes'][0]['source'] += '-other'
    elif change == 'image':
        services['restore-check']['image'] = 'learncoach-ops:other'
    elif change == 'ports':
        services['restore-db']['ports'] = ['5432:5432']
    elif change == 'volume':
        services['restore-db']['volumes'] = [{'source': 'live-pgdata'}]
    elif change == 'tmpfs':
        services['restore-db']['tmpfs'] = ['/tmp']
    elif change == 'readonly':
        services['backup']['volumes'][1]['read_only'] = False
    else:
        services['backup']['environment']['BACKUP_STATUS_FILE'] = '/tmp/backup.json'
    assert not preflight.check_configuration(['docker', 'compose'])['ok']


@pytest.mark.parametrize('failure', [OSError('private-key'), subprocess.CalledProcessError(1, 'docker', stderr='private-key')])
def test_compose_errors_do_not_leak_credentials(monkeypatch, failure):
    monkeypatch.setattr(preflight.subprocess, 'run', Mock(side_effect=failure))
    report = preflight.check_configuration(['docker', 'compose'])
    assert report == {'ok': False, 'scope': 'configuration_only', 'checks': {'compose': False}}


@pytest.mark.parametrize('body', ['not json', '{}', '{"services":{"backup":null}}'])
def test_invalid_compose_json_fails_closed(monkeypatch, body):
    monkeypatch.setattr(preflight.subprocess, 'run', Mock(return_value=argparse.Namespace(stdout=body)))
    assert not preflight.check_configuration(['docker', 'compose'])['ok']


@pytest.mark.parametrize('ok', [True, False])
def test_check_command_returns_status_without_starting_services(monkeypatch, capsys, ok):
    monkeypatch.setattr(sys, 'argv', ['ops.py', 'check'])
    monkeypatch.setattr(ops, 'check_configuration', lambda _: {'ok': ok, 'scope': 'configuration_only'})
    execute = Mock()
    monkeypatch.setattr(ops.subprocess, 'run', execute)
    assert ops.main() == (0 if ok else 1)
    execute.assert_not_called()
    assert json.loads(capsys.readouterr().out)['ok'] is ok


def test_nonexistent_secret_and_receipt_paths_are_rejected(tmp_path):
    service = {'volumes': [{'type': 'bind', 'source': str(tmp_path / 'missing'),
                            'target': '/run/secrets/restic-password', 'read_only': True}]}
    assert not preflight.secret_file(service, '/run/secrets/restic-password')
    assert not preflight.receipt_directory(service)


@pytest.mark.skipif(os.name != 'posix', reason='Linux ownership/mode checks')
def test_world_readable_secrets_are_rejected(tmp_path):
    secret = tmp_path / 'password'
    secret.write_text('fixture-only')
    secret.chmod(0o644)
    service = {'volumes': [{'type': 'bind', 'source': str(secret), 'target': '/secret', 'read_only': True}]}
    assert not preflight.secret_file(service, '/secret')


def test_timers_require_preflight_before_scheduled_jobs():
    root = Path(__file__).resolve().parents[1]
    for name in ('backup', 'restore'):
        unit = (root / f'deploy/learn-coach-{name}.service').read_text()
        assert 'ExecStartPre=/usr/bin/python3 scripts/release/ops.py check' in unit
        assert 'UMask=0077' in unit
