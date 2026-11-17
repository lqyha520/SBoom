"""旧候选评测入口：用户已取消部署前出题验证，不创建测试库或调用模型。"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/release'))
from quality_policy import validation_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--thinking-mode', choices=['default', 'disabled'], help=argparse.SUPPRESS)
    parser.add_argument('--case', action='append', help=argparse.SUPPRESS)
    parser.add_argument('--plan-only', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    metadata = json.loads(args.manifest.read_text(encoding='utf-8'))
    print(json.dumps({'validation_plan': validation_plan(metadata), 'case_ids': [],
                      'rounds': 0, 'status': 'cancelled_by_user'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
