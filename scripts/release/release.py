"""在生产主机发布已校验镜像：备份、更新 app、健康检查，失败自动回滚 app。"""
import argparse
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen

from ops import compose


def run(args, env=None):
    return subprocess.run(args, check=True, env=env, capture_output=True, text=True).stdout.strip()


@contextmanager
def release_lock(path):
    with path.open('a') as lock:
        if sys.platform != 'win32':
            import fcntl
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('已有发布进程运行，请等该进程完成') from None
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='已构建并载入本机的版本镜像（发布/回滚均使用此参数）')
    parser.add_argument('--health-url', default='http://127.0.0.1:33403/readyz')
    parser.add_argument('--state-dir', type=Path, default=Path('/var/lib/learn-coach/releases'))
    args = parser.parse_args()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    with release_lock(args.state_dir / 'release.lock'):
        publish(args)


def publish(args):
    command = compose()
    run(['docker', 'image', 'inspect', args.image])
    container = run([*command, 'ps', '-q', 'app'])
    if not container:
        raise RuntimeError('需要现有 app 容器以确定可回滚镜像；首次安装请按操作手册执行')
    previous = run(['docker', 'inspect', '--format', '{{.Image}}', container])
    env_file = Path(os.environ.get('RELEASE_ENV_FILE', '/etc/learn-coach/release.env'))
    original_env = env_file.read_text()
    state_file = args.state_dir / 'current.json'
    original_state = state_file.read_bytes() if state_file.exists() else None
    temporary = env_file.with_suffix('.new')
    lines = [line for line in original_env.splitlines() if not line.startswith('APP_IMAGE=')]
    temporary.write_text('\n'.join([*lines, 'APP_IMAGE=' + args.image]) + '\n')
    temporary.chmod(0o600)
    # 一致性快照工具持锁导出数据库及文件；备份失败时不进入发布。
    subprocess.run([sys.executable, 'scripts/release/ops.py', 'backup'], check=True)
    env = {**os.environ, 'APP_IMAGE': args.image}
    try:
        run([*command, 'run', '--rm', '--no-deps', 'app', 'python', '-m', 'app.migrations'], env)
        run([*command, 'up', '-d', '--no-deps', '--no-build', '--wait', 'app'], env)
        with urlopen(args.health_url, timeout=15) as response:
            if response.status != 200:
                raise RuntimeError('readyz 未通过')
        state = args.state_dir / 'current.new'
        state.write_text(json.dumps({'image': args.image, 'previous': previous}), encoding='utf-8')
        temporary.replace(env_file)
        state.replace(state_file)
    except Exception:
        run([*command, 'up', '-d', '--no-deps', '--no-build', '--wait', 'app'], {**os.environ, 'APP_IMAGE': previous})
        temporary.write_text(original_env)
        temporary.chmod(0o600)
        temporary.replace(env_file)
        if original_state is not None:
            state_file.write_bytes(original_state)
        elif state_file.exists():
            state_file.unlink()
        raise RuntimeError('发布未通过健康检查，已恢复旧 app 镜像') from None
    print('发布完成；当前与回滚镜像已登记。数据库及数据卷未替换。')


if __name__ == '__main__':
    main()
