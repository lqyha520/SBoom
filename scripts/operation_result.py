"""systemd 收尾兜底：进程被终止或超时也必须留下失败状态。"""
import json
import os
import sys

from offsite_ops import Offsite
from ops_state import operation


def record(kind):
    target = Offsite()
    filename = 'operation.json' if kind == 'offsite' else 'restore-operation.json'
    path = target.root / 'status' / filename
    value = json.loads(path.read_text()) if path.exists() else {}
    if os.environ.get('SERVICE_RESULT') != 'success' or value.get('state') == 'running':
        value = operation(path, 'failed', 'service_terminated', error=os.environ.get('SERVICE_RESULT', 'unknown'))
        try:
            target.remote('operation' if kind == 'offsite' else 'restore-operation', json.dumps(value).encode())
        except Exception:
            pass


if __name__ == '__main__':
    if sys.argv[1] not in ('offsite', 'restore'):
        raise ValueError('未知运行类型')
    record(sys.argv[1])
