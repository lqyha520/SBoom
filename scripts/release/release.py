"""备份后发布固定镜像；仅在数据库兼容且健康检查通过时确认回滚成功。"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen

from image_checks import verify_image
from ops import compose


def run(args, env=None):
    return subprocess.run(args, check=True, env=env, capture_output=True, text=True).stdout.strip()


def atomic_write(path, data):
    """Create private files before writing secrets, preserving existing ownership."""
    previous = path.stat() if path.exists() else None
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            if previous is not None and hasattr(os, 'fchown'):
                current = os.fstat(stream.fileno())
                if (current.st_uid, current.st_gid) != (previous.st_uid, previous.st_gid):
                    os.fchown(stream.fileno(), previous.st_uid, previous.st_gid)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def image_environment(original, image):
    lines = [line for line in original.splitlines() if not line.startswith('APP_IMAGE=')]
    return ('\n'.join([*lines, 'APP_IMAGE=' + image]) + '\n').encode('utf-8')


def health_check(url):
    with urlopen(url, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError('readyz 未通过')


def start_app(command, image):
    run([*command, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never',
         '--wait', '--wait-timeout', '120', 'app'], {**os.environ, 'APP_IMAGE': image})


def record_recovery(args, env_file, original_env, image, previous, reason):
    atomic_write(env_file, image_environment(original_env, image))
    atomic_write(args.state_dir / 'current.json', json.dumps({
        'image': image, 'previous': previous, 'status': 'recovery_required', 'reason': reason,
    }).encode('utf-8'))


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
    parser.add_argument('--manifest', type=Path, help='包含 image/build_id 的候选清单')
    parser.add_argument('--run', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--ratings', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    validate_evaluation(args)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    with release_lock(args.state_dir / 'release.lock'):
        publish(args)


def publish(args):
    metadata = validate_evaluation(args)
    command = compose()
    image = run(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image])
    if metadata.get('image') != image:
        raise RuntimeError('待发布镜像与登记的候选镜像不一致')
    verify_image(image)
    container = run([*command, 'ps', '-q', 'app'])
    if not container:
        raise RuntimeError('需要现有 app 容器以确定可回滚镜像；首次安装请按操作手册执行')
    previous = run(['docker', 'inspect', '--format', '{{.Image}}', container])
    if 'candidate_hashes' in metadata and metadata.get('original') != previous:
        raise RuntimeError('范围判定的基线镜像与当前运行镜像不一致，请重新准备候选')
    env_file = Path(os.environ.get('RELEASE_ENV_FILE', '/etc/learn-coach/release.env'))
    original_env = env_file.read_text(encoding='utf-8')
    state_file = args.state_dir / 'current.json'
    original_state = state_file.read_bytes() if state_file.exists() else None
    # 一致性快照工具持锁导出数据库及文件；备份失败时不进入发布。
    subprocess.run([sys.executable, 'scripts/release/ops.py', 'backup'], check=True)
    env = {**os.environ, 'APP_IMAGE': image}
    try:
        # Do not let the old application keep writing while its schema changes.
        run([*command, 'stop', '--timeout', '40', 'app'])
        run([*command, 'run', '--rm', '--no-deps', '--pull', 'never', '-T',
             'app', 'python', '-m', 'app.migrations'], env)
        start_app(command, image)
        health_check(args.health_url)
        atomic_write(env_file, image_environment(original_env, image))
        atomic_write(state_file, json.dumps({'image': image, 'previous': previous}).encode('utf-8'))
    except (Exception, KeyboardInterrupt):
        try:
            # --check is read-only; a connection failure also means compatibility is unknown.
            run([*command, 'run', '--rm', '--no-deps', '--pull', 'never', '-T',
                 'app', 'python', '-m', 'app.migrations', '--check'],
                {**os.environ, 'APP_IMAGE': previous})
        except Exception:
            record_recovery(args, env_file, original_env, image, previous, 'compatibility_unverified')
            try:
                start_app(command, image)
            except Exception:
                pass
            raise RuntimeError('发布失败，旧镜像与当前数据库的兼容性未通过检查；保留新镜像配置，需人工恢复。未回滚或覆盖数据库。') from None
        try:
            start_app(command, previous)
            health_check(args.health_url)
        except Exception:
            record_recovery(args, env_file, original_env, previous, image, 'rollback_unhealthy')
            raise RuntimeError('发布失败，旧镜像恢复也未通过健康检查；已记录待恢复状态，需人工处理。未覆盖数据库。') from None
        atomic_write(env_file, original_env.encode('utf-8'))
        if original_state is not None:
            atomic_write(state_file, original_state)
        else:
            state_file.unlink(missing_ok=True)
        raise RuntimeError('发布失败，已恢复旧 app 镜像并通过健康检查') from None
    print('发布完成；当前与回滚镜像已登记。数据库及数据卷未替换。')


def validate_evaluation(args):
    if not getattr(args, 'manifest', None):
        raise RuntimeError('发布必须提供 --manifest 候选清单')
    from quality_policy import evaluate_release

    metadata = json.loads(args.manifest.read_text(encoding='utf-8'))
    evaluate_release(metadata, None, None, 'production')
    return metadata


if __name__ == '__main__':
    main()
