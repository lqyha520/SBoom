"""已有宿主发布的预检失败不得触发备份、停机或配置修改。"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/release'))
import publish_existing as release
from drain_existing import drain
from existing_host import Host
from quality_policy import evaluate_release


def test_retired_human_review_record_never_reaches_host(tmp_path, monkeypatch):
    metadata = {"build_id": "candidate"}
    gate = {**evaluate_release(metadata, None, None, "production"), "rounds": 3, "human_required": True}
    (tmp_path / "deployment.json").write_text(json.dumps(metadata))
    (tmp_path / "gate.json").write_text(json.dumps(gate))
    command = Mock()
    monkeypatch.setattr(release, "run", command)
    with pytest.raises(RuntimeError, match="已取消部署前"):
        release.publish(tmp_path, "production", tmp_path / "state")
    command.assert_not_called()
    assert not (tmp_path / "state").exists()


def test_rollback_never_patches_old_schema_version():
    from incremental import rollback_image
    host = Mock()
    host.run.return_value = b'2026111001'
    with pytest.raises(RuntimeError, match='兼容读写'):
        rollback_image(host, 'sha256:old', 2026111002)
    assert all(call.args[1] == 'run' for call in host.run.call_args_list)
    host.inspect.return_value = {'Id': 'sha256:compatible'}
    host.run.return_value = b'2026111002'
    assert rollback_image(host, 'sha256:old', 2026111002, 'app:compatible') == 'sha256:compatible'
    assert rollback_image(host, 'sha256:old', 2026111002) == 'sha256:old'


def test_ssh_read_retry_never_repeats_mutation(monkeypatch):
    import subprocess
    retry = Mock(side_effect=[subprocess.CompletedProcess([], 255, b'', b'reset'),
                              subprocess.CompletedProcess([], 0, b'[]', b'')])
    monkeypatch.setattr('existing_host.subprocess.run', retry)
    monkeypatch.setattr('existing_host.time.sleep', lambda _: None)
    assert Host('production').run('docker', 'inspect', 'app') == b'[]'
    assert retry.call_count == 2
    mutation = Mock(return_value=subprocess.CompletedProcess([], 255, b'', b'reset'))
    monkeypatch.setattr('existing_host.subprocess.run', mutation)
    with pytest.raises(RuntimeError):
        Host('production').run('docker', 'stop', 'app')
    assert mutation.call_count == 1


def test_drain_waits_for_active_work_and_releases_before_migration(monkeypatch):
    commands = []
    counts = iter([b'1', b'0'])
    monkeypatch.setattr('drain_existing.time.sleep', lambda _: None)
    def run(*args):
        commands.append(args)
        if args[:2] == ('docker', 'logs'):
            return b'admission-locked'
        if args[-1] == 'count':
            return next(counts)
        return b''
    with drain(['compose'], run) as release_admission:
        run('old-app', 'stop')
        release_admission()
        run('migrate')
    stopped = next(i for i, cmd in enumerate(commands) if cmd[:2] == ('docker', 'stop'))
    assert commands.index(('old-app', 'stop')) < stopped < commands.index(('migrate',))
    assert commands[-1][-2] == 'clear'
    assert sum(cmd[:2] == ('docker', 'stop') for cmd in commands) == 1


def test_drain_failure_clears_guard_and_does_not_switch(monkeypatch):
    commands = []
    def run(*args):
        commands.append(args)
        if args[:2] == ('docker', 'logs'):
            return b'admission-locked'
        if args[-1] == 'count':
            raise RuntimeError('database disconnected')
        return b''
    with pytest.raises(RuntimeError, match='disconnected'), drain(['compose'], run):
        pytest.fail('failed drain must not switch')
    assert any(cmd[:2] == ('docker', 'stop') for cmd in commands)
    assert commands[-1][-2] == 'clear'


def test_current_application_uses_flag_without_holding_replay_lock():
    commands = []
    def run(*args):
        commands.append(args)
        return b'0' if args[-1] == 'count' else b''
    with drain(['compose'], run, legacy=False) as release_admission:
        release_admission()
    assert not any(cmd[:1] == ('docker',) for cmd in commands)
    assert commands[0][-2] == 'set' and commands[-1][-2] == 'clear'


def test_failed_gate_never_runs_host_commands(tmp_path, monkeypatch):
    (tmp_path / 'deployment.json').write_text(json.dumps({'build_id': 'candidate'}))
    (tmp_path / 'gate.json').write_text(json.dumps({'passed': False, 'build_id': 'candidate'}))
    command = Mock()
    monkeypatch.setattr(release, 'run', command)
    with pytest.raises(RuntimeError, match='发布检查记录'):
        release.publish(tmp_path, 'wsl', tmp_path / 'state')
    command.assert_not_called()


def test_stale_container_never_enters_backup_or_stop(tmp_path, monkeypatch):
    metadata = {'build_id': 'candidate', 'app': 'app', 'original': 'old', 'old_app': 'id',
                'old_hashes': {'app/services/settlements.py': 'old'},
                'candidate_hashes': {'app/services/settlements.py': 'new'}}
    (tmp_path / 'deployment.json').write_text(json.dumps(metadata))
    (tmp_path / 'gate.json').write_text(json.dumps(evaluate_release(metadata, None, None, 'wsl')))
    monkeypatch.setattr(release, 'inspect', lambda _: {'Image': 'unexpected', 'Id': 'other'})
    command = Mock()
    monkeypatch.setattr(release, 'run', command)
    with pytest.raises(RuntimeError, match='版本已改变'):
        release.publish(tmp_path, 'wsl', tmp_path / 'state')
    command.assert_not_called()


def test_health_probe_does_not_assume_production_host_port(monkeypatch):
    ports = {'8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8000'}]}
    monkeypatch.setattr(release, 'inspect', lambda _: {'Image': 'new', 'State': {'Health': {'Status': 'healthy'}},
                                                    'Mounts': [], 'NetworkSettings': {'Ports': ports}})
    command = Mock(return_value=b'')
    monkeypatch.setattr(release, 'run', command)
    release.check_health({'app': 'deploy-app-1', 'mounts': [], 'ports': ports, 'containers': {}}, 'new')
    assert command.call_args_list[0].args[:4] == ('docker', 'exec', 'deploy-app-1', 'python')
    assert '127.0.0.1:8000/readyz' in command.call_args_list[0].args[-1]
    assert 'modulepreload' in command.call_args_list[1].args[-1]


def test_missing_frontend_asset_fails_health_check(monkeypatch):
    monkeypatch.setattr(release, 'inspect', lambda _: {'Image': 'new', 'State': {'Health': {'Status': 'healthy'}},
                                                    'Mounts': [], 'NetworkSettings': {'Ports': {}}})
    monkeypatch.setattr(release, 'run', Mock(side_effect=[b'', RuntimeError('HTTP Error 404')]))
    with pytest.raises(RuntimeError, match='404'):
        release.check_health({'app': 'app', 'mounts': [], 'ports': {}, 'containers': {}}, 'new')


@pytest.mark.parametrize('matching', [True, False])
def test_backup_configuration_tracks_live_image_and_preserves_other_files(tmp_path, monkeypatch, matching):
    existing = tmp_path / 'docker-compose.yml'
    existing.write_text('user configuration')
    candidate = tmp_path / 'candidate.json'
    candidate.write_text('{"previous":true}')
    monkeypatch.setattr(release, 'inspect', lambda _: {
        'Id': 'container-id', 'Image': 'sha256:live', 'Config': {'Labels': {
            'com.docker.compose.project.working_dir': '/deployment',
            'com.docker.compose.project': 'learncoach',
            'com.docker.compose.project.config_files': '/release/candidate.json',
        }},
    })
    config = {'services': {'app': {'image': 'release:current', 'build': '.', 'environment': {'SECRET': 'private'}},
                           'db': {'image': 'postgres:16'}}}
    def command(*args):
        if args[0] == 'sh':
            return str(tmp_path).encode()
        if args[:2] == ('docker', 'compose'):
            return json.dumps(config).encode()
        if args[:3] == ('docker', 'image', 'inspect'):
            return b'sha256:live\n' if matching else b'sha256:stale\n'
        raise AssertionError(args)
    monkeypatch.setattr(release, 'run', command)
    owner = Mock()
    monkeypatch.setattr(release.os, 'chown', owner, raising=False)
    if matching:
        release.refresh_backup_configuration('app', '/backup.env')
        saved = json.loads(candidate.read_text())
        assert saved['services']['app'] == {'image': 'sha256:live', 'environment': {'SECRET': 'private'}}
        assert saved['services']['db'] == config['services']['db']
        assert json.loads((tmp_path / 'current.json').read_text())['image'] == 'sha256:live'
        assert all(call.args[1:] == (10001, 10001) for call in owner.call_args_list)
    else:
        with pytest.raises(RuntimeError, match='运行镜像不一致'):
            release.refresh_backup_configuration('app', '/backup.env')
        assert candidate.read_text() == '{"previous":true}'
        owner.assert_not_called()
    assert existing.read_text() == 'user configuration'
