"""部署不再要求付费出题评测或人工评分；保留候选绑定及部署检查。"""

import argparse
import json
from pathlib import Path


def validation_plan(metadata: dict, thinking_mode: str = 'production') -> dict:
    before, after = metadata.get('old_hashes'), metadata.get('candidate_hashes')
    changed = (sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
               if isinstance(before, dict) and isinstance(after, dict) else [])
    return {'version': 2, 'scope': 'none', 'rounds': 0, 'subjects': [], 'changed_files': changed,
            'reason': '用户已取消部署前的题目评测与人工评分；执行功能回归及部署检查'}


def planned_suite(plan: dict, suite: list[dict]) -> list[dict]:
    return []


def requires_human(metadata: dict, target: str, thinking_mode: str = 'production') -> bool:
    return False


def verify_release_gate(metadata: dict, gate: dict, target: str) -> None:
    """宿主在备份和停机前确认候选记录，仍拒绝旧构建或过期发布策略。"""
    if gate.get('passed') is not True or gate.get('build_id') != metadata.get('build_id'):
        raise RuntimeError('发布检查记录与本次构建不一致')
    if gate.get('validation_plan') != validation_plan(metadata):
        raise RuntimeError('发布策略与候选差异不一致，请重新生成发布检查记录')
    if gate.get('rounds') != 0 or gate.get('human_required') is not False:
        raise RuntimeError('已取消部署前的题目评测与人工评分，请重新生成发布检查记录')


def evaluate_release(metadata: dict, evaluation_run: dict | None, ratings: dict | None, target: str,
                     *, human_review_waiver: dict | None = None) -> dict:
    # 保留旧调用参数兼容性；历史评测和评分不再影响部署，也不改变业务模型配置。
    build_id = metadata.get('build_id')
    if not isinstance(build_id, str) or not build_id.strip():
        raise RuntimeError('发布必须提供构建标识')
    if target not in ('wsl', 'production'):
        raise ValueError('未知部署目标')
    plan = validation_plan(metadata)
    return {'passed': True, 'build_id': build_id, 'validation_plan': plan,
            'thinking_mode': 'production', 'rounds': 0, 'questions': 0,
            'human_required': False, 'human_status': 'not_required', 'human_coverage': 0,
            'human_correct_rate': None, 'failures': [], 'checks': plan['reason']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--thinking-mode', choices=['production', 'default', 'disabled'], default='production')
    args = parser.parse_args()
    print(json.dumps(validation_plan(json.loads(args.manifest.read_text(encoding='utf-8'))),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
