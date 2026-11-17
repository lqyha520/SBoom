"""取消部署前出题验证后，仍核对候选、备份和恢复事务。"""
import io
import json
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'scripts/release'),
               str(Path(__file__).resolve().parents[1] / 'scripts')]
from quality_policy import evaluate_release, planned_suite, requires_human, validation_plan, verify_release_gate


def candidate(*paths):
    return {'build_id': 'candidate', 'old_hashes': {path: 'old' for path in paths},
            'candidate_hashes': {path: 'new' for path in paths}}


@pytest.mark.parametrize('path', [
    'app/services/settlements.py', 'admin/dist/index.html', 'web/dist/index.html',
    'app/services/question_bank.py', 'app/services/question_qc.py', 'app/config.py',
    'app/services/prompt_builder.py', 'app/services/llm_client.py',
    'app/services/generation_results.py', 'app/data/pep_catalog.json', 'requirements.lock',
])
@pytest.mark.parametrize('target', ['wsl', 'production'])
def test_release_never_loads_paid_suite_or_requires_human(monkeypatch, path, target):
    load = Mock(side_effect=AssertionError('部署不应装载出题评测'))
    monkeypatch.setattr('evaluate_generation.load_suite', load)
    metadata = candidate(path)
    gate = evaluate_release(metadata, None, None, target)
    assert gate['passed'] and gate['rounds'] == 0
    assert gate['validation_plan']['scope'] == 'none'
    assert not requires_human(metadata, target)
    assert gate['human_status'] == 'not_required' and gate['human_correct_rate'] is None
    verify_release_gate(metadata, gate, target)
    load.assert_not_called()


@pytest.mark.parametrize('mode', ['production', 'default', 'disabled'])
def test_model_configuration_and_missing_fingerprints_do_not_restart_validation(mode):
    for metadata in ({'build_id': 'candidate'},
                     {**candidate('app/config.py'), 'model_config_changed': True}):
        plan = validation_plan(metadata, mode)
        assert plan['scope'] == 'none' and plan['rounds'] == 0
        assert planned_suite(plan, [{'id': 'unused'}]) == []
        assert not requires_human(metadata, 'production', mode)


@pytest.mark.parametrize('build_id', [None, '', '  ', False])
def test_candidate_build_binding_remains_required(build_id):
    with pytest.raises(RuntimeError, match='构建标识'):
        evaluate_release({'build_id': build_id}, None, None, 'production')


def test_cancelled_failed_or_stale_evaluations_do_not_block_deploy_or_change_models():
    metadata = candidate('app/services/question_qc.py')
    gate = evaluate_release(metadata, {'passed': False, 'build_id': 'old', 'thinking_mode': 'disabled'},
                            {'status': 'pending_human_review'}, 'production', human_review_waiver={})
    assert gate['passed'] and gate['thinking_mode'] == 'production'
    assert gate['human_status'] == 'not_required'
    verify_release_gate(metadata, gate, 'production')


@pytest.mark.parametrize('mutation', [
    {'passed': False}, {'build_id': 'old'}, {'rounds': 3}, {'human_required': True},
    {'validation_plan': {'version': 1, 'scope': 'full'}},
])
def test_stale_publish_record_fails_before_any_host_action(tmp_path, monkeypatch, mutation):
    import publish_existing
    metadata = candidate('app/config.py')
    gate = {**evaluate_release(metadata, None, None, 'production'), **mutation}
    (tmp_path / 'deployment.json').write_text(json.dumps(metadata))
    (tmp_path / 'gate.json').write_text(json.dumps(gate))
    command = Mock()
    monkeypatch.setattr(publish_existing, 'run', command)
    with pytest.raises(RuntimeError):
        publish_existing.publish(tmp_path, 'production', tmp_path / 'state')
    command.assert_not_called()
    assert not (tmp_path / 'state').exists()


def test_generic_release_cli_ignores_retired_evaluation_arguments(tmp_path):
    from release import validate_evaluation
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(candidate('app/services/prompt_builder.py')))
    args = SimpleNamespace(manifest=path, run=tmp_path / 'missing-run.json', ratings=tmp_path / 'missing-ratings.json')
    assert validate_evaluation(args)['build_id'] == 'candidate'


@pytest.mark.parametrize('extra', [[], ['--case', 'g1-math-add'], ['--thinking-mode', 'disabled']])
def test_retired_evaluator_never_connects_hosts_or_creates_output(tmp_path, monkeypatch, extra):
    import evaluate_candidate
    import existing_host
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(candidate('app/services/question_qc.py')))
    output = tmp_path / 'no-paid-evaluation'
    monkeypatch.setattr(sys, 'argv', ['evaluate_candidate.py', '--manifest', str(path), '--directory', str(output), *extra])
    host = Mock(side_effect=AssertionError('取消后不应连接宿主'))
    load = Mock(side_effect=AssertionError('取消后不应读取付费样本'))
    monkeypatch.setattr(existing_host, 'Host', host)
    monkeypatch.setattr('evaluate_generation.load_suite', load)
    assert evaluate_candidate.main() == 0
    host.assert_not_called()
    load.assert_not_called()
    assert not output.exists()


def test_incremental_cli_ignores_retired_evaluation_files(tmp_path, monkeypatch):
    import deploy_existing
    metadata = {**candidate('app/config.py'), 'release': 'fixture', 'image': 'sha256:candidate', 'status': 'prepared'}
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(metadata))
    host = Mock(root='/releases')
    host.read.side_effect = [json.dumps(metadata).encode(), json.dumps({**metadata, 'status': 'deployed'}).encode()]
    monkeypatch.setattr(deploy_existing, 'Host', lambda _: host)
    monkeypatch.setattr(sys, 'argv', ['deploy_existing.py', '--target', 'production', '--manifest', str(path),
                                   '--run', str(tmp_path / 'missing-run'), '--ratings', str(tmp_path / 'missing-ratings'),
                                   '--human-review-waiver', str(tmp_path / 'missing-waiver')])
    deploy_existing.main()
    assert json.loads(path.read_text())['status'] == 'deployed'
    gate = json.loads(next(call.args[1] for call in host.write.call_args_list if call.args[0].endswith('/gate.json')))
    assert gate['rounds'] == 0 and gate['human_status'] == 'not_required'


@pytest.mark.parametrize('disable_failure_limit', [False, True])
def test_admin_only_candidate_captures_complete_baseline_and_inherits_generation(tmp_path, monkeypatch, disable_failure_limit):
    import incremental
    frontend = tmp_path / 'admin/dist/index.html'
    frontend.parent.mkdir(parents=True)
    frontend.write_bytes(b'new-admin')
    before = {'app/services/llm_client.py': 'unchanged', 'admin/dist/index.html': 'old-admin',
              'web/dist/index.html': 'unchanged-web'}
    after = {**before, 'admin/dist/index.html': incremental.digest(b'new-admin')}
    old = {'Image': 'sha256:old', 'Id': 'old-container', 'State': {'Health': {'Status': 'healthy'}},
           'Mounts': [], 'NetworkSettings': {'Ports': {}}}
    host = Mock(app='app', root='/releases')
    host.inspect.side_effect = lambda name: old if name == 'app' else {'Id': 'sha256:candidate'}
    host.compose.return_value = ['docker', 'compose']
    def command(*args, **kwargs):
        if args[-1] == incremental.HASH_CODE:
            return json.dumps(before if args[1] == 'exec' else after).encode()
        if args[-1] == incremental.SCHEMA_CODE:
            return b'2026111005'
        if args[-3:] == ('config', '--format', 'json'):
            return b'{"services":{"app":{}}}'
        if args[:2] == ('docker', 'ps'):
            return b'app'
        return b''
    host.run.side_effect = command
    monkeypatch.setattr(incremental, 'Host', lambda _: host)
    monkeypatch.setattr(incremental, 'ROOT', tmp_path)
    monkeypatch.setattr(incremental, 'verify_payload', Mock())
    monkeypatch.setattr(incremental.subprocess, 'check_output', Mock(return_value='fixture'))
    incremental.prepare(SimpleNamespace(target='production', file=[], baseline=tmp_path / 'unused',
                                        release='admin-only', output=tmp_path / 'output', rollback_image=None,
                                        disable_daily_failure_limit=disable_failure_limit))
    metadata = json.loads((tmp_path / 'output/production/deployment.json').read_text(encoding='utf-8'))
    assert metadata['old_hashes'] == before and metadata['candidate_hashes'] == after
    assert validation_plan(metadata)['scope'] == 'none'
    config = json.loads(next(call.args[1] for call in host.write.call_args_list if call.args[0].endswith('/candidate.json')))
    assert metadata.get('disable_daily_failure_limit', False) is disable_failure_limit
    assert config['services']['app']['environment'].get('GENERATION_DAILY_FAILURE_LIMIT') == ('0' if disable_failure_limit else None)
    payload = next(call.kwargs['data'] for call in host.run.call_args_list if call.args[0] == 'tar')
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
        dockerfile = archive.extractfile('Dockerfile').read().decode()
        assert 'FROM learncoach-app:base-admin-only-production' in dockerfile
        assert 'COPY admin/dist /app/admin/dist' in dockerfile
        assert 'COPY app ' not in dockerfile and 'COPY web/' not in dockerfile


def test_daily_failure_cap_change_is_explicit_and_preserves_other_settings():
    from publish_existing import verified_candidate_config
    original = {'services': {'app': {'image': 'old', 'build': '.', 'environment': {
        'GENERATION_DAILY_FAILURE_LIMIT': '30', 'GENERATION_GLOBAL_DAILY_IMAGES': '200',
        'GENERATION_USER_CONCURRENCY': '2'}}, 'db': {'image': 'database', 'volumes': ['data:/data']}}}
    plain = verified_candidate_config(original, {'image': 'new'})
    assert plain['services']['app']['environment']['GENERATION_DAILY_FAILURE_LIMIT'] == '30'
    changed = verified_candidate_config(original, {'image': 'new', 'disable_daily_failure_limit': True})
    assert changed['services']['app']['environment'] == {
        **plain['services']['app']['environment'], 'GENERATION_DAILY_FAILURE_LIMIT': '0'}
    assert changed['services']['db'] == original['services']['db']
    assert original['services']['app']['environment']['GENERATION_DAILY_FAILURE_LIMIT'] == '30'
    assert original['services']['app']['image'] == 'old'  # 原配置仍可用于完整回退
    with pytest.raises(RuntimeError, match='标识无效'):
        verified_candidate_config(original, {'image': 'new', 'disable_daily_failure_limit': 'false'})


def test_generic_publisher_rejects_stale_baseline_before_backup(monkeypatch):
    import release
    monkeypatch.setattr(release, 'validate_evaluation', lambda _: {
        **candidate('app/services/settlements.py'), 'image': 'sha256:new', 'original': 'sha256:stale',
    })
    monkeypatch.setattr(release, 'compose', lambda: ['compose'])
    monkeypatch.setattr(release, 'verify_image', Mock())
    run = Mock(side_effect=['sha256:new', 'container', 'sha256:current'])
    backup = Mock()
    monkeypatch.setattr(release, 'run', run)
    monkeypatch.setattr(release.subprocess, 'run', backup)
    with pytest.raises(RuntimeError, match='基线镜像'):
        release.publish(SimpleNamespace(image='candidate'))
    backup.assert_not_called()
