"""重复评测不能靠复用成功样本过关，人工未评分保持待审。"""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from evaluate_generation import digest, ratings_template
from evaluation_gate import evaluate
from evaluation_regressions import evaluate as regressions


def sample():
    suite = [{'id': 'add', 'request': {'grade': '小学一年级', 'subject': '数学', 'game_type': 'oral_math', 'difficulty': 'easy', 'question_count': 1}}]
    run = {'build_id': 'candidate', 'suite_digest': digest(suite), 'cases': [{**suite[0], 'submitted': True,
           'request_elapsed_ms': 100, 'observation': {'status': 'succeeded', 'trace': {'calls': [{'stage': 'generate'}]},
           'result': {'questions': [{'type': 'oral_math', 'stem': '2+3=', 'answer': 5, 'analysis': '2+3=5', 'quality_status': 'passed'}]}}}]}
    runs = [copy.deepcopy(run) for _ in range(3)]
    for i, item in enumerate(runs):
        item['cases'][0]['request_id'] = f'eval-{i}'
    bundle = {'build_id': 'candidate', 'planned_rounds': 3, 'runs': runs,
              'regressions': {'passed': True, 'build_id': 'candidate', 'cases': [{'id': 'fixed', 'passed': True}]}}
    return suite, bundle


def test_repeated_gate_rejects_failed_round_reused_request_and_missing_round():
    suite, bundle = sample()
    assert evaluate(bundle, suite, 'candidate')['passed']
    for mutate in (lambda b: b['runs'].pop(),
                   lambda b: b['runs'][1]['cases'][0].update(request_id='eval-0'),
                   lambda b: b['runs'][1]['cases'][0]['observation'].update(status='failed')):
        invalid = copy.deepcopy(bundle)
        mutate(invalid)
        assert not evaluate(invalid, suite, 'candidate')['passed']


def test_human_pending_template_and_exact_run_binding():
    suite, bundle = sample()
    ratings = ratings_template(bundle)
    assert all(q['correct'] is None and 'quality_status' not in q['question'] for r in ratings['rounds'] for q in r['questions'])
    result = evaluate(bundle, suite, 'candidate', ratings)
    assert result['human_status'] == 'pending_human_review' and result['human_coverage'] == 0
    assert not evaluate(bundle, suite, 'candidate', ratings, require_human=True)['passed']
    for r in ratings['rounds']:
        r['questions'][0]['correct'] = True
    result = evaluate(bundle, suite, 'candidate', ratings, require_human=True)
    assert result['passed'] and result['human_status'] == 'reviewed'
    ratings['run_digest'] = 'stale'
    with pytest.raises(ValueError):
        evaluate(bundle, suite, 'candidate', ratings)


def test_fixed_historical_regressions():
    path = Path(__file__).parent / 'fixtures/generation-regressions.json'
    cases = json.loads(path.read_text(encoding='utf-8'))['cases']
    result = regressions(cases)
    assert result['passed'] and [case['id'] for case in result['cases']] == [case['id'] for case in cases]
    assert {'split-analysis-other-question', 'split-analysis-repaired'} <= {case['id'] for case in cases}
