"""Deployment failure paths use mock processes, never live application containers."""

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


images = load('release_images', 'scripts/release/image_checks.py')
preflight = load('release_preflight', 'scripts/release/ops_preflight.py')
with patch.dict(sys.modules, {'ops_preflight': preflight}):
    ops = load('release_ops_safety', 'scripts/release/ops.py')
with patch.dict(sys.modules, {'ops': ops, 'image_checks': images}):
    release = load('release_safety', 'scripts/release/release.py')
    prepare = load('release_prepare_safety', 'scripts/release/prepare.py')


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    env_file = tmp_path / 'release.env'
    original_env = 'APP_IMAGE=app:old\nSECRET_KEY=fixture-secret\n'
    env_file.write_text(original_env)
    state = tmp_path / 'current.json'
    original_state = b'{"image":"app:old","previous":"app:older"}'
    state.write_bytes(original_state)
    monkeypatch.setenv('RELEASE_ENV_FILE', str(env_file))
    monkeypatch.setattr(release, 'compose', lambda: ['docker', 'compose'])
    failures = {}
    calls = []

    def run(command, env=None):
        calls.append((command, env))
        if command[:3] == ['docker', 'image', 'inspect']:
            return 'sha256:new-image'
        if command[:2] == ['docker', 'inspect']:
            return 'sha256:old-image'
        if command[-3:] == ['ps', '-q', 'app']:
            return 'app-container'
        if command[-1] == '--check' and 'compatibility' in failures:
            raise failures['compatibility']
        if command[-1] == 'app.migrations' and 'migration' in failures:
            raise failures['migration']
        if 'up' in command and env['APP_IMAGE'] == 'sha256:old-image' and 'rollback' in failures:
            raise failures['rollback']
        return ''

    monkeypatch.setattr(release, 'run', run)
    smoke = Mock()
    backup = Mock()
    health = Mock()
    monkeypatch.setattr(release, 'verify_image', smoke)
    monkeypatch.setattr(release.subprocess, 'run', backup)
    monkeypatch.setattr(release, 'health_check', health)
    return argparse.Namespace(args=argparse.Namespace(image='app:new', health_url='http://127.0.0.1/readyz', state_dir=tmp_path),
                              env_file=env_file, original_env=original_env, state=state, original_state=original_state,
                              failures=failures, calls=calls, smoke=smoke, backup=backup, health=health)


def test_success_pins_image_and_stops_only_app_before_migration(deployment):
    d = deployment
    release.publish(d.args)
    d.smoke.assert_called_once_with('sha256:new-image')
    assert 'APP_IMAGE=sha256:new-image' in d.env_file.read_text()
    assert 'SECRET_KEY=fixture-secret' in d.env_file.read_text()
    assert json.loads(d.state.read_text()) == {'image': 'sha256:new-image', 'previous': 'sha256:old-image'}
    commands = [command for command, _ in d.calls]
    stop = next(index for index, command in enumerate(commands) if 'stop' in command)
    migration = next(index for index, command in enumerate(commands) if command[-1] == 'app.migrations')
    assert stop < migration
    assert commands[stop][-1] == 'app'
    for command, env in d.calls:
        if env:
            assert env['APP_IMAGE'] == 'sha256:new-image'
        assert 'down' not in command


@pytest.mark.parametrize('stage', ['smoke', 'backup'])
def test_preflight_or_backup_failure_does_not_stop_live_app(deployment, stage):
    d = deployment
    getattr(d, stage).side_effect = RuntimeError('preparation failed')
    with pytest.raises(RuntimeError):
        release.publish(d.args)
    assert not any('stop' in command or 'up' in command for command, _ in d.calls)
    assert d.env_file.read_text() == d.original_env
    assert d.state.read_bytes() == d.original_state
    assert not list(d.args.state_dir.glob('*.tmp'))


@pytest.mark.parametrize('failure', [RuntimeError('older schema'), OSError('database unavailable')])
def test_schema_or_connection_failure_never_starts_old_image(deployment, failure):
    d = deployment
    d.health.side_effect = OSError('new health check failed')
    d.failures['compatibility'] = failure
    with pytest.raises(RuntimeError, match='兼容性未通过'):
        release.publish(d.args)
    starts = [(command, env) for command, env in d.calls if 'up' in command]
    assert starts and all(env['APP_IMAGE'] == 'sha256:new-image' for _, env in starts)
    assert 'APP_IMAGE=sha256:new-image' in d.env_file.read_text()
    assert json.loads(d.state.read_text())['status'] == 'recovery_required'
    assert json.loads(d.state.read_text())['previous'] == 'sha256:old-image'


def test_failed_migration_can_restore_verified_compatible_image(deployment):
    d = deployment
    d.failures['migration'] = RuntimeError('migration transaction failed')
    with pytest.raises(RuntimeError, match='已恢复'):
        release.publish(d.args)
    probe = next(i for i, (command, _) in enumerate(d.calls) if command[-1] == '--check')
    start = next(i for i, (command, _) in enumerate(d.calls) if 'up' in command)
    assert probe < start
    assert d.env_file.read_text() == d.original_env
    assert d.state.read_bytes() == d.original_state
    d.health.assert_called_once()


def test_interrupted_migration_restores_verified_compatible_image(deployment):
    d = deployment
    d.failures['migration'] = KeyboardInterrupt()
    with pytest.raises(RuntimeError, match='已恢复'):
        release.publish(d.args)
    assert d.env_file.read_text() == d.original_env
    assert d.state.read_bytes() == d.original_state


def test_failed_state_write_restores_original_metadata(deployment, monkeypatch):
    d = deployment
    original = release.atomic_write
    written = False

    def write(path, data):
        nonlocal written
        if path == d.state and not written:
            written = True
            raise OSError('one-time state write failure')
        original(path, data)

    monkeypatch.setattr(release, 'atomic_write', write)
    with pytest.raises(RuntimeError, match='已恢复'):
        release.publish(d.args)
    assert d.env_file.read_text() == d.original_env
    assert d.state.read_bytes() == d.original_state


def test_rollback_does_not_leave_new_success_record_when_no_previous_state(deployment):
    d = deployment
    d.state.unlink()
    d.health.side_effect = [OSError('new endpoint unavailable'), None]
    with pytest.raises(RuntimeError, match='已恢复'):
        release.publish(d.args)
    assert not d.state.exists()


@pytest.mark.parametrize('failure', ['start', 'health'])
def test_failed_rollback_never_claims_recovery(deployment, failure):
    d = deployment
    d.health.side_effect = OSError('endpoint unavailable')
    if failure == 'start':
        d.failures['rollback'] = RuntimeError('container unhealthy')
    with pytest.raises(RuntimeError, match='恢复也未通过'):
        release.publish(d.args)
    state = json.loads(d.state.read_text())
    assert state['status'] == 'recovery_required'
    assert state['reason'] == 'rollback_unhealthy'
    assert state['image'] == 'sha256:old-image'
    assert 'APP_IMAGE=sha256:old-image' in d.env_file.read_text()


def test_atomic_private_write_cleans_temporary_on_failure(tmp_path, monkeypatch):
    target = tmp_path / 'release.env'
    target.write_bytes(b'old-secret')
    monkeypatch.setattr(release.os, 'fsync', Mock(side_effect=OSError('disk error')))
    with pytest.raises(OSError):
        release.atomic_write(target, b'new-secret')
    assert target.read_bytes() == b'old-secret'
    assert not list(tmp_path.glob('*.tmp'))


def test_atomic_write_preserves_ownership_and_private_mode(tmp_path):
    target = tmp_path / 'release.env'
    target.write_bytes(b'old-secret')
    before = target.stat()
    release.atomic_write(target, b'new-secret')
    assert target.read_bytes() == b'new-secret'
    if os.name == 'posix':
        after = target.stat()
        assert (after.st_uid, after.st_gid) == (before.st_uid, before.st_gid)
        assert after.st_mode & 0o777 == 0o600


def test_image_smoke_has_no_network_or_production_mounts(monkeypatch):
    execute = Mock()
    monkeypatch.setattr(images.subprocess, 'run', execute)
    images.verify_image('sha256:candidate')
    command = execute.call_args.args[0]
    assert command[command.index('--network') + 1] == 'none'
    assert '--read-only' in command and '--entrypoint' in command
    assert '--volume' not in command and '-v' not in command and '--env-file' not in command
    assert 'getuid() == 10001' in command[-1]
    assert "stream.read(1)" in command[-1]


def test_prepare_refuses_existing_image_before_build(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['prepare.py', '--output', str(tmp_path)])
    monkeypatch.setattr(prepare, 'run', Mock(side_effect=['a' * 40, 'existing-image']))
    execute = Mock()
    monkeypatch.setattr(prepare.subprocess, 'run', execute)
    with pytest.raises(RuntimeError, match='拒绝覆盖'):
        prepare.main()
    execute.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_prepare_does_not_export_failed_smoke(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['prepare.py', '--output', str(tmp_path)])
    execute = Mock(return_value='')

    def run(*command, **kwargs):
        if command[:2] == ('git', 'rev-parse'):
            return 'a' * 40
        if command[:2] == ('git', 'archive'):
            import tarfile
            archive = next(value.split('=', 1)[1] for value in command if value.startswith('--output='))
            with tarfile.open(archive, 'w'):
                pass
        return execute(*command, **kwargs)

    monkeypatch.setattr(prepare, 'run', run)
    monkeypatch.setattr(prepare.subprocess, 'run', Mock())
    monkeypatch.setattr(prepare, 'verify_image', Mock(side_effect=subprocess.CalledProcessError(1, 'smoke')))
    with pytest.raises(subprocess.CalledProcessError):
        prepare.main()
    assert not any(call.args[:2] == ('docker', 'save') for call in execute.call_args_list)
    assert not list(tmp_path.rglob('release.json'))
