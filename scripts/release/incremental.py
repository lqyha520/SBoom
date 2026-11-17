"""从运行镜像增量构建；原文件指纹不匹配时停止，保留兼容 schema 的回滚镜像。"""
import argparse
import hashlib
import io
import json
import subprocess
import tarfile
import time
from pathlib import Path

from existing_host import Host, save
from image_checks import SMOKE_CHECK

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_CODE = """import ast
from pathlib import Path
module=ast.parse(Path('/app/app/db.py').read_text())
print(next(ast.literal_eval(n.value) for n in module.body if isinstance(n,ast.Assign)
 and any(isinstance(t,ast.Name) and t.id=='SCHEMA_VERSION' for t in n.targets)))
"""
HASH_CODE = """import hashlib,json
from pathlib import Path
print(json.dumps({str(p.relative_to('/app')): hashlib.sha256(p.read_bytes()).hexdigest()
 for root in ('app','web/dist','admin/dist') for p in (Path('/app')/root).rglob('*')
 if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}))
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bundle(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.mode, member.size = 0o644, len(data)
            # 避免同大小、归零 mtime 的入口文件被文件同步层视为未变更。
            member.mtime = int(time.time())
            archive.addfile(member, io.BytesIO(data))
    return stream.getvalue()


def rollback_image(host, original: str, schema: int, explicit: str | None = None) -> str:
    """仅接受真实支持新 schema 的回滚程序，禁止改版本号伪装兼容。"""
    image = host.inspect(explicit)['Id'] if explicit else original
    version = int(host.run('docker', 'run', '--rm', '--pull', 'never', '--network', 'none', '--read-only',
                           '--entrypoint', 'python', image, '-c', SCHEMA_CODE))
    if version != schema:
        raise RuntimeError('回滚镜像不支持候选 schema；请先构建并验收兼容读写的回滚镜像，通过 --rollback-image 指定，禁止仅提升版本号')
    return image


def prepare(args):
    host = Host(args.target)
    old = host.inspect(host.app)
    if old['State'].get('Health', {}).get('Status') != 'healthy':
        raise RuntimeError('现有应用不健康')
    before = json.loads(host.run('docker', 'exec', host.app, 'python', '-c', HASH_CODE, read_only=True))
    files = {}
    for name in args.file:
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT / 'app') or path.suffix != '.py':
            raise ValueError('后端增量必须是 app 内的 Python 文件')
        baseline = args.baseline / name
        if name in before and (not baseline.is_file() or digest(baseline.read_bytes().replace(b'\r\n', b'\n')) != before[name]):
            raise RuntimeError('运行版本与修改前文件不一致：' + name)
        files[name] = path.read_bytes().replace(b'\r\n', b'\n')
    code_hashes = {name: digest(data) for name, data in files.items()}
    if 'app/db.py' in files:
        import ast
        module = ast.parse(files['app/db.py'])
        schema = next(ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'SCHEMA_VERSION' for t in node.targets))
    else:
        schema = int(host.run('docker', 'run', '--rm', '--pull', 'never', '--network', 'none', '--read-only',
                              '--entrypoint', 'python', old['Image'], '-c', SCHEMA_CODE))
    rollback = rollback_image(host, old['Image'], schema, getattr(args, 'rollback_image', None))
    if not getattr(args, 'backend_only', False):
        for frontend in ('web', 'admin'):
            for path in (ROOT / frontend / 'dist').rglob('*'):
                if path.is_file():
                    files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    payload_hashes = {name: digest(data) for name, data in sorted(files.items())}
    if not payload_hashes:
        raise RuntimeError('未找到发布文件，请指定后端文件或先构建前端')
    build_id = digest(json.dumps(payload_hashes, sort_keys=True).encode())
    base_tag = f'learncoach-app:base-{args.release}-{args.target}'
    tag = f'learncoach-app:{args.release}-{args.target}'
    directory = host.root + '/' + args.release
    host.run('mkdir', '-p', directory + '/context')
    host.run('chmod', '700', directory)
    host.run('docker', 'tag', old['Image'], base_tag)
    copies = ''.join(f'COPY {root} /app/{root}\n' for root in ('app', 'web/dist', 'admin/dist')
                     if any(name.startswith(root + '/') for name in files))
    files['Dockerfile'] = (f'FROM {base_tag}\nUSER root\n{copies}'
                           f'LABEL io.learncoach.release="{args.release}"\nUSER app\n').encode()
    host.run('tar', '-xzf', '-', '-C', directory + '/context', data=bundle(files))
    host.run('docker', 'build', '--pull=false', '--network=none', '-t', tag, directory + '/context')
    candidate = host.inspect(tag)
    after = json.loads(host.run('docker', 'run', '--rm', '--pull', 'never', '--network', 'none', '--read-only', '--entrypoint', 'python', tag, '-c', HASH_CODE))
    if after != {**before, **payload_hashes}:
        raise RuntimeError('镜像内容与预期增量不符')
    verify_payload(host, tag, payload_hashes)
    host.run('docker', 'run', '--rm', '--pull', 'never', '--network', 'none', '--read-only', '--tmpfs', '/tmp',
             '--entrypoint', 'python', tag, '-c', SMOKE_CHECK)
    config = json.loads(host.run(*host.compose(old), 'config', '--format', 'json', read_only=True))
    config['services']['app']['image'] = candidate['Id']
    config['services']['app'].setdefault('environment', {}).update(METRICS_ENABLED='true', METRICS_HOST='0.0.0.0')
    disable_failure_limit = bool(getattr(args, 'disable_daily_failure_limit', False))
    if disable_failure_limit:
        config['services']['app']['environment']['GENERATION_DAILY_FAILURE_LIMIT'] = '0'
    for service in config['services'].values():
        service.pop('build', None)
    host.write(directory + '/candidate.json', json.dumps(config).encode())
    state = {'release': args.release, 'image': candidate['Id'], 'previous': rollback, 'original': old['Image'],
             'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
             'dirty_worktree': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
             'build_id': build_id, 'old_app': old['Id'], 'old_hashes': before, 'candidate_hashes': after, 'files': code_hashes,
             'payload_hashes': payload_hashes,
             'compose': host.compose(old, [directory + '/candidate.json']), 'app': host.app,
             'containers': {name: host.inspect(name)['Id'] for name in host.run('docker', 'ps', '--format', '{{.Names}}').decode().split() if name != host.app},
             'mounts': old['Mounts'], 'ports': old['NetworkSettings']['Ports'], 'status': 'prepared'}
    if disable_failure_limit:
        state['disable_daily_failure_limit'] = True
    save(args.output / args.target / 'deployment.json', state)
    host.write(directory + '/deployment.json', json.dumps(state).encode())
    print(json.dumps({'target': args.target, 'status': 'prepared', 'build_id': build_id, 'image': candidate['Id']}), flush=True)


def verify_payload(host, image, expected):
    """核对镜像内每个发布文件，包括 HTML 入口和全部前端资源。"""
    code = '''import hashlib,json,sys
from pathlib import Path
expected=json.load(sys.stdin)
different=[name for name,value in expected.items() if not (Path('/app')/name).is_file() or hashlib.sha256((Path('/app')/name).read_bytes()).hexdigest()!=value]
print(json.dumps(different))
'''
    different = json.loads(host.run('docker', 'run', '--rm', '--pull', 'never', '--network', 'none',
                                   '--read-only', '-i', '--entrypoint', 'python', image, '-c', code,
                                   data=json.dumps(expected).encode()))
    if different:
        raise RuntimeError('发布文件与镜像不一致：' + ', '.join(different[:10]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=['wsl', 'production'], required=True)
    parser.add_argument('--release', required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--file', action='append', default=[], help='需复制的后端文件；纯前端发布可省略')
    parser.add_argument('--backend-only', action='store_true', help='仅复制指定后端文件，保留运行镜像内的前端资源')
    parser.add_argument('--rollback-image', help='已验收支持候选 schema 和文件格式的回滚镜像')
    parser.add_argument('--disable-daily-failure-limit', action='store_true', help='显式关闭全天失败次数封锁，保留并发、预算与模型冷却')
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'[a-z0-9-]{1,80}', args.release):
        parser.error('发布名无效')
    prepare(args)


if __name__ == '__main__':
    main()
