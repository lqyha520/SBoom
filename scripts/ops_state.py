"""运维状态原子落盘；成功回执与最近运行状态分别保留。"""
import json
import os
import tempfile
import time
from pathlib import Path


def write_json(path: Path, value: dict, mode=0o640):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def operation(path: Path, state: str, stage: str, **fields):
    value = {'state': state, 'stage': stage, 'checked_at': int(time.time()), **fields}
    write_json(path, value)
    return value


def operation_check(path: Path, max_running_seconds=1200) -> dict:
    value = json.loads(path.read_text())
    state, stamp = value.get('state'), value.get('checked_at', 0)
    age = time.time() - stamp
    return {'ok': state in ('succeeded', 'running') and -300 <= age and
                  (state != 'running' or age <= max_running_seconds),
            'state': state, 'stage': value.get('stage'), 'age_seconds': max(0, round(age))}


if __name__ == '__main__':
    import sys
    operation(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
