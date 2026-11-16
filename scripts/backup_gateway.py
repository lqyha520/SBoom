"""专用 SSH 密钥只可触发备份、读取加密仓库与提交校验回执。"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from ops_state import write_json

ROOT = Path('/data/data1/learn-coach-ops')


def allowed_command(command: str) -> list[str]:
    parts = shlex.split(command)
    if parts in (['backup'], ['status'], ['receipt'], ['operation'], ['restore-operation'], ['restore-receipt'], ['external']):
        return parts
    if (len(parts) >= 5 and parts[:3] == ['rsync', '--server', '--sender']
            and parts[-2:] == ['.', (ROOT / 'repository').as_posix() + '/']
            and all(re.fullmatch(r'-[a-zA-Z.]+', value) or value == '--timeout=90' for value in parts[3:-2])):
        return parts
    raise ValueError('该密钥只可访问 Learn Coach 的加密备份')


def main():
    import fcntl
    parts = allowed_command(os.environ.get('SSH_ORIGINAL_COMMAND') or ' '.join(sys.argv[1:]))
    if parts == ['backup']:
        # 写端由 production_ops.sh 获取同一独占锁，避免嵌套锁死锁。
        subprocess.run(['/bin/sh', '-c', 'set -a; . /etc/learn-coach/backup.env; exec /usr/local/lib/learn-coach/production_ops.sh backup'], check=True)
        return
    with open('/run/lock/learn-coach-production-ops.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        if parts == ['status']:
            print((ROOT / 'status/backup.json').read_text())
        elif parts == ['receipt']:
            receipt = json.loads(sys.stdin.read(4097))
            source = json.loads((ROOT / 'status/backup.json').read_text())
            if (receipt.get('verified') is not True or receipt.get('offsite') is not True
                    or receipt.get('snapshot_id') != source.get('snapshot_id') or not source.get('snapshot_id')
                    or abs(time.time() - receipt.get('completed_at', 0)) > 300):
                raise ValueError('异地校验回执与当前备份不符')
            target = Path('/var/lib/learn-coach/ops-status/backup.json')
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps({key: receipt[key] for key in ('verified', 'offsite', 'snapshot_id', 'completed_at', 'independent', 'vault_snapshot_id') if key in receipt}))
            temporary.chmod(0o640)
            temporary.replace(target)
        elif parts in (['operation'], ['restore-operation'], ['restore-receipt'], ['external']):
            value = json.loads(sys.stdin.read(8193))
            stamp = value.get('checked_at', value.get('completed_at', 0))
            if not isinstance(stamp, (int, float)) or abs(time.time() - stamp) > 300:
                raise ValueError('回执时间无效')
            if parts in (['operation'], ['restore-operation']):
                if value.get('state') not in ('running', 'failed', 'succeeded') or not isinstance(value.get('stage'), str):
                    raise ValueError('运行状态无效')
                value = {key: value[key] for key in ('state', 'stage', 'checked_at', 'attempt', 'error') if key in value}
                name = 'offsite-operation.json' if parts == ['operation'] else 'restore-operation.json'
            elif parts == ['restore-receipt']:
                if value.get('verified') is not True or not re.fullmatch(r'[0-9a-f]{64}', value.get('snapshot_id', '')):
                    raise ValueError('恢复回执无效')
                value = {key: value[key] for key in ('verified', 'snapshot_id', 'completed_at', 'app_started', 'database_counts_checked') if key in value}
                name = 'restore.json'
            else:
                if type(value.get('ok')) is not bool or not isinstance(value.get('checks'), dict):
                    raise ValueError('外部检查回执无效')
                name = 'external.json'
            write_json(Path('/var/lib/learn-coach/ops-status') / name, value)
        else:
            subprocess.run(parts, check=True)


if __name__ == '__main__':
    main()
