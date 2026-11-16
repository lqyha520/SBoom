"""发布前的可复现模型评测门禁；规则检查与人工正确率分别报告。"""
import argparse
import json
from pathlib import Path

from evaluate_generation import SUITE, digest, load_suite, questions, read_json, summarize

from app.services.question_qc import exact_question_key, question_issue


def evaluate(run: dict, suite: list[dict], build_id: str, ratings: dict | None = None, require_human: bool = False,
             *, required_rounds: int = 3) -> dict:
    if 'runs' in run:
        return evaluate_repeated(run, suite, build_id, ratings=ratings, require_human=require_human,
                                 required_rounds=required_rounds)
    failures = []
    if not build_id or run.get('build_id') != build_id:
        failures.append('评测不属于本次构建')
    if (run.get('suite_digest') != digest(suite)
            or [(c['id'], c['request']) for c in run['cases']] != [(c['id'], c['request']) for c in suite]):
        failures.append('固定评测集不一致或覆盖不完整')
    summary = summarize(run, ratings)
    for case in run['cases']:
        observation = case.get('observation') or {}
        values = questions(case)
        if observation.get('status') != 'succeeded' or observation.get('cache_expired') or case.get('collection_error'):
            failures.append(case['id'] + '：结果未完整确认')
        if len(values) != case['request']['question_count']:
            failures.append(case['id'] + '：题量不符')
        seen = set()
        for item in values:
            question = item['question']
            key = exact_question_key(question, item['passage'] or '')
            if key in seen:
                failures.append(case['id'] + '：完全重复题')
            seen.add(key)
            if question_issue(question) or not str(question.get('analysis') or '').strip():
                failures.append(case['id'] + '：本地校验失败或缺少解析')
            if question.get('quality_status') != 'passed':
                failures.append(case['id'] + '：模型复核未通过')
        trace = observation.get('trace') or {}
        if not trace.get('calls') or not any(c.get('stage') == 'generate' for c in trace['calls']):
            failures.append(case['id'] + '：缺少真实模型调用追踪')
    if require_human and (summary['human_coverage'] != 1 or (summary['human_correct_rate'] or 0) < 0.95):
        failures.append('人工评分覆盖不足或正确率低于95%')
    return {'passed': not failures, 'build_id': build_id, 'suite_digest': digest(suite), 'run_digest': digest(run),
            'checks': '结构、重复题、确定性校验、模型复核、调用追踪', 'human_required': require_human,
            'human_correct_rate': summary['human_correct_rate'], 'human_coverage': summary['human_coverage'],
            'failures': sorted(set(failures)), 'summary': summary}


def evaluate_repeated(bundle: dict, suite: list[dict], build_id: str, *, ratings=None, require_human=False,
                      required_rounds: int = 3) -> dict:
    import statistics
    runs = bundle['runs']
    failures = []
    if required_rounds not in (1, 3):
        raise ValueError('发布评测只支持一轮专项或完整三轮')
    if bundle.get('planned_rounds') != required_rounds or len(runs) != required_rounds:
        failures.append('固定三轮评测未全部完成' if required_rounds == 3 else '专项一轮评测未完整完成')
    if bundle.get('build_id') != build_id:
        failures.append('多轮评测不属于本次构建')
    if ratings and (ratings.get('run_digest') != digest(bundle) or len(ratings.get('rounds', [])) != len(runs)):
        raise ValueError('人工评分与多轮评测不匹配')
    checks = [evaluate(run, suite, build_id, ratings=ratings['rounds'][index] if ratings else None,
                       require_human=require_human) for index, run in enumerate(runs)]
    identifiers = [case.get('request_id') for run in runs for case in run['cases']]
    if any(not value for value in identifiers) or len(set(identifiers)) != len(identifiers):
        failures.append('多轮评测重复使用请求编号')
    for index, check in enumerate(checks, 1):
        failures.extend(f'第{index}轮：{reason}' for reason in check['failures'])
    regression = bundle.get('regressions') or {}
    if not regression.get('passed') or regression.get('build_id') != build_id or not regression.get('cases'):
        failures.append('历史失败回归未通过或不属于本次构建')
    times = sorted(case['request_elapsed_ms'] for run in runs for case in run['cases'] if case.get('request_elapsed_ms') is not None)
    count = sum(check['summary']['coverage']['returned_questions'] for check in checks)
    judged = sum(check['summary']['coverage']['human_judged'] for check in checks)
    correct = sum(row['correct'] for check in checks for row in check['summary']['cases'])
    return {'passed': not failures, 'build_id': build_id, 'suite_digest': digest(suite), 'run_digest': digest(bundle),
            'rounds': len(runs), 'human_required': require_human,
            'human_status': 'reviewed' if count and judged == count else 'pending_human_review',
            'human_coverage': judged / count if count else 0, 'human_correct_rate': correct / judged if judged else None,
            'failures': failures, 'round_checks': checks,
            'regressions': regression, 'latency_ms': {'median': statistics.median(times) if times else None,
            'p95': times[max(0, (len(times) * 95 + 99) // 100 - 1)] if times else None,
            'mean': round(statistics.mean(times)) if times else None},
            'questions': count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--suite', type=Path, default=SUITE)
    parser.add_argument('--ratings', type=Path)
    parser.add_argument('--require-human', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(read_json(args.run), load_suite(args.suite), args.build_id,
                      read_json(args.ratings) if args.ratings else None, args.require_human)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('passed', 'human_correct_rate', 'failures')}, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
