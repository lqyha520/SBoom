"""发布门禁拒绝不完整评测，镜像保留按内容去重并保护运行版本。"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts/release'))

from evaluate_generation import digest
from evaluation_gate import evaluate

spec = importlib.util.spec_from_file_location('release_prune', ROOT / 'scripts/release/prune.py')
assert spec and spec.loader
prune = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prune)


def test_date_base_rollback_tags_do_not_consume_retention_slots():
    images = [{'Id': str(i), 'Created': str(i), 'RepoTags': [f'learncoach-app:{prefix}2026110{i}' for prefix in ('fix-', 'base-', 'rollback-')]} for i in range(1, 6)]
    images.append({'Id': 'unmanaged', 'Created': '0', 'RepoTags': ['other-app:20261101']})
    result = prune.candidates(images, {'1'}, 2)
    assert {identifier for identifier, _ in result} == {'2', '3'}
    assert all(len(tags) == 3 for _, tags in result)


def test_prune_protects_independently_scheduled_operations_images(tmp_path, monkeypatch):
    config = tmp_path / 'backup.env'
    config.write_text("OPS_IMAGE='learncoach-ops:new'\nOFFSITE_IMAGE='learncoach-ops:vault'\nPRIVATE_KEY=secret\n")
    monkeypatch.setattr(prune, 'OPS_CONFIG_FILES', (config,))
    def run(*args):
        if args[:3] == ('docker', 'image', 'inspect'):
            assert args[-1] != 'secret'
            return args[-1]
        return ''
    monkeypatch.setattr(prune, 'run', run)
    assert {'learncoach-ops:new', 'learncoach-ops:vault'} <= prune.protected_images({'image': 'app', 'previous': 'rollback', 'compose': ['compose']})


def test_prune_skips_unpulled_optional_tag_but_protects_digest_and_requires_rollback(monkeypatch):
    monkeypatch.setattr(prune, 'OPS_CONFIG_FILES', ())
    def run(*args):
        if args[0] == 'compose':
            return 'postgres:16-bookworm\nregistry:5000/postgres:16@sha256:manifest'
        if args[:3] == ('docker', 'image', 'ls'):
            return json.dumps({'Repository': 'registry:5000/postgres', 'Tag': '16', 'Digest': 'sha256:manifest', 'ID': 'sha256:database'})
        if args[:3] == ('docker', 'image', 'inspect'):
            if args[-1] == 'missing-rollback':
                raise RuntimeError('required image missing')
            assert args[-1] in ('app', 'rollback')
            return args[-1]
        return ''
    monkeypatch.setattr(prune, 'run', run)
    state = {'image': 'app', 'previous': 'rollback', 'compose': ['compose']}
    assert prune.protected_images(state) == {'app', 'rollback', 'sha256:database'}
    with pytest.raises(RuntimeError, match='required image missing'):
        prune.protected_images({**state, 'previous': 'missing-rollback'})


def test_gate_rejects_stale_build_incomplete_suite_and_missing_trace():
    suite = [{'id': 'test', 'request': {'grade': '小学一年级', 'subject': '数学', 'game_type': 'oral_math', 'difficulty': 'easy', 'question_count': 1}}]
    run = {'build_id': 'candidate', 'suite_digest': digest(suite), 'cases': [{**suite[0], 'submitted': True,
           'observation': {'status': 'succeeded', 'result': {'questions': [{'type': 'oral_math', 'stem': '2 + 3 =', 'answer': 5,
                            'analysis': '2加3等于5', 'quality_status': 'passed'}]}}}]}
    assert not evaluate(run, suite, 'old')['passed']
    assert not evaluate(run, suite, 'candidate')['passed']
    run['cases'][0]['observation']['trace'] = {'calls': [{'stage': 'generate'}]}
    assert evaluate(run, suite, 'candidate')['passed']
    assert not evaluate(run, suite, 'candidate', require_human=True)['passed']
    assert not evaluate(run, suite * 2, 'candidate')['passed']


def test_number_split_analysis_accepts_both_sentence_orders():
    from app.services.question_qc import question_issue
    question = {'type': 'number_split', 'top': 9, 'left': 7, 'right': '____', 'answer': 2}
    assert not question_issue({**question, 'analysis': '9分成7和2。'})
    assert not question_issue({**question, 'analysis': '7和2组成9。'})
    assert question_issue({**question, 'analysis': '7和3组成9。'})
    assert question_issue({**question, 'analysis': '7和2组成8。'})


def test_number_split_missing_total_is_checked_against_the_answer():
    from app.services.question_qc import question_issue
    question = {'type': 'number_split', 'top': '____', 'left': 3, 'right': 3, 'answer': 6}
    assert not question_issue({**question, 'analysis': '总数为6，3和3组成6。'})
    assert question_issue({**question, 'analysis': '总数为7，3和3组成7。'})
    assert not question_issue({**question, 'analysis': '总数为3+3=6，所以填6。'})
    assert not question_issue({**question, 'analysis': '总数为3加3等于6，所以填6。'})
    assert question_issue({**question, 'analysis': '总数为3+4=7，所以填7。'})


@pytest.mark.parametrize('analysis', [
    '数的分成中，总数等于两部分之和：6+2=8，所以空格填8。',
    '数的分成中总数为两部分之和，所以总数为6+2=8。',
    '总数等于两个数之和，6+2=8，所以填8。',
    '总数为两项之和，6+2=8，所以填8。',
    '总数为2部分之和，6+2=8，所以填8。',
])
def test_number_split_component_count_is_not_a_stated_total(analysis):
    from app.services.question_qc import question_issue
    question = {'type': 'number_split', 'top': '____', 'left': 6, 'right': 2, 'answer': 8}
    assert not question_issue({**question, 'analysis': analysis})


@pytest.mark.parametrize('analysis', [
    '总数为两，所以填2。',
    '总数为两个苹果，所以填2。',
    '总数为两部分之和，总数为9，所以填9。',
    '总数为两部分之和，6+2=9，所以填9。',
])
def test_number_split_component_phrase_keeps_incorrect_total_checks(analysis):
    from app.services.question_qc import question_issue
    question = {'type': 'number_split', 'top': '____', 'left': 6, 'right': 2, 'answer': 8}
    assert question_issue({**question, 'analysis': analysis})
