"""核对候选后在已有宿主部署增量版本；不要求出题评测或人工评分。"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from evaluate_generation import read_json
from existing_host import Host, save
from quality_policy import evaluate_release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--run', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--ratings', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--human-review-waiver', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--target', choices=['wsl', 'production'], required=True)
    parser.add_argument('--keep', type=int, default=2, help='至少保留当前与上一版本')
    args = parser.parse_args()
    if args.keep < 2:
        parser.error('--keep 至少为2')
    metadata = read_json(args.manifest)
    gate = evaluate_release(metadata, None, None, args.target)
    host = Host(args.target)
    directory = host.root + '/' + metadata['release']
    if json.loads(host.read(directory + '/deployment.json')) != metadata:
        raise RuntimeError('本地与宿主部署记录不一致')
    for name in ('publish_existing.py', 'quality_policy.py', 'drain_existing.py', 'release.py', 'image_checks.py', 'ops.py', 'ops_preflight.py', 'prune.py'):
        host.write(directory + '/' + name, (ROOT / 'scripts/release' / name).read_bytes().replace(b'\r\n', b'\n'))
    host.write(directory + '/gate.json', json.dumps(gate).encode())
    # systemd 保持发布事务独立于桌面连接；日志不包含环境或密钥。
    host.run('systemd-run', '--unit=learn-coach-release-' + metadata['release'], '--collect', '--wait',
             '--property=WorkingDirectory=' + directory, '--property=UMask=0077',
             '/usr/bin/python3', directory + '/publish_existing.py', '--directory', directory, '--target', args.target,
             timeout=1800)
    result = json.loads(host.read(directory + '/deployment.json'))
    save(args.manifest, result)
    host.run('/usr/bin/python3', directory + '/prune.py', '--keep', str(args.keep), '--apply', timeout=600)
    print(json.dumps({key: result[key] for key in ('status', 'image', 'build_id')}))


if __name__ == '__main__':
    main()
