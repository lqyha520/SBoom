"""从独立加密快照恢复镜像、数据库和文件，并在无外网网络中启动整站。"""
import gzip
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from offsite_ops import Offsite, lock, run
from ops_state import operation, write_json

PROBE = '''import json,urllib.request,urllib.parse
from html.parser import HTMLParser
class Assets(HTMLParser):
 def __init__(self):super().__init__();self.urls=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='script' and a.get('src'):self.urls.append(a['src'])
  if tag=='link' and a.get('rel') in ('stylesheet','modulepreload'):self.urls.append(a['href'])
base='http://127.0.0.1:8000'
for path in ('/readyz','/','/admin/'):
 with urllib.request.urlopen(base+path,timeout=10) as r:
  assert r.status==200
  if path=='/readyz':continue
  parser=Assets();parser.feed(r.read().decode());assert parser.urls
 for asset in parser.urls:
  url=urllib.parse.urljoin(base+path,asset)
  assert urllib.parse.urlparse(url).netloc=='127.0.0.1:8000'
  with urllib.request.urlopen(url,timeout=10) as r:assert r.status==200 and r.read(1)
from app.services.app_config import get_llm
config=get_llm(with_key=True,fresh=True)
profiles=config.get('models') or [config]
assert all(p.get('api_key') for p in profiles if p.get('enabled',True))
print(json.dumps({'pages':True,'assets':True,'ready':True,'model_configuration_decrypted':True}))
'''


def state(target, status, stage):
    value = operation(target.root / 'status/restore-operation.json', status, stage)
    try:
        target.remote('restore-operation', json.dumps(value).encode())
    except Exception:
        pass


def restore(target):
    receipt = json.loads((target.root / 'status/backup.json').read_text())
    snapshot = receipt['vault_snapshot_id']
    state(target, 'running', 'restore_images')
    nodes = [json.loads(line) for line in target.restic('ls', snapshot, '--json', writable=False).splitlines()]
    def path(suffix):
        found = [item['path'] for item in nodes if item.get('path', '').endswith(suffix)]
        if len(found) != 1:
            raise RuntimeError('恢复文件不唯一或缺失：' + suffix)
        return found[0]
    runtime = json.loads(target.restic('dump', snapshot, path('/images/runtime.json'), writable=False))
    # 镜像不含业务数据；临时文件私有，校验后导入 Docker，退出即删除。
    with tempfile.TemporaryDirectory(prefix='learncoach-images-') as folder:
        archive = Path(folder) / 'runtime.tar.gz'
        with archive.open('wb') as output:
            archive.chmod(0o600)
            target.restic('dump', snapshot, path('/images/runtime.tar.gz'), writable=False, output=output)
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != runtime['sha256']:
                raise RuntimeError('恢复镜像归档校验失败')
        with gzip.open(archive, 'rb') as source, tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(['docker', 'load'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
            try:
                assert process.stdin is not None
                shutil.copyfileobj(source, process.stdin, 1024 * 1024)
                process.stdin.close()
                if process.wait(timeout=600):
                    raise RuntimeError('恢复镜像载入失败')
            finally:
                if process.poll() is None:
                    process.kill()
        for image in runtime['images'].values():
            run(['docker', 'image', 'inspect', image])
    source_env = target.restic('dump', snapshot, path('/bundle/service.env'), writable=False).decode()
    env = dict(line.split('=', 1) for line in source_env.splitlines() if line and not line.startswith('#'))
    token = secrets.token_hex(6)
    network, volume, database, app = ['lc-full-restore-' + token + '-' + suffix for suffix in ('net', 'data', 'db', 'app')]
    cleanup = []
    started = time.monotonic()
    try:
        run(['docker', 'network', 'create', '--internal', network])
        cleanup.append(['docker', 'network', 'rm', network])
        run(['docker', 'volume', 'create', '--driver', 'local', '--opt', 'type=tmpfs', '--opt', 'device=tmpfs',
             '--opt', 'o=size=2g,uid=10001,gid=10001,mode=700', volume])
        cleanup.append(['docker', 'volume', 'rm', volume])
        run(['docker', 'run', '-d', '--pull', 'never', '--name', database, '--network', network, '--network-alias', 'restore-db',
             '--tmpfs', '/var/lib/postgresql/data:size=2g', '--shm-size', '256m', '-e', 'POSTGRES_USER=restore',
             '-e', 'POSTGRES_PASSWORD=isolated-restore-only', '-e', 'POSTGRES_DB=lc_restore_probe', runtime['images']['database']])
        cleanup.append(['docker', 'rm', '-f', database])
        for attempt in range(30):
            try:
                run(['docker', 'exec', database, 'pg_isready', '-U', 'restore', '-d', 'lc_restore_probe'])
                break
            except RuntimeError:
                if attempt == 29:
                    raise
                time.sleep(2)
        state(target, 'running', 'restore_database_files')
        run(['docker', 'run', '--rm', '--pull', 'never', '--network', 'container:' + database,
             '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '3g',
             '--tmpfs', '/tmp:size=2g,mode=1777', '-e', 'RESTIC_REPOSITORY=/repository', '-e', 'RESTIC_PASSWORD_FILE=/password',
             '-e', 'RESTIC_CACHE_DIR=/tmp', '-e', 'RESTIC_READ_ONLY=true', '-e', 'RESTORE_SNAPSHOT=' + snapshot,
             '-e', 'LC_RESTORE_DATABASE_URL=postgresql://restore:isolated-restore-only@127.0.0.1:5432/lc_restore_probe',
             '-e', 'RESTORE_EXPORT_ROOT=/recovery', '-e', 'RESTORE_STATUS_FILE=/status/database-restore.json',
             '-v', f'{target.vault}:/repository:ro', '-v', f'{target.password}:/password:ro',
             '-v', f'{target.root}/status:/status', '-v', volume + ':/recovery', runtime['images']['operations'], 'restore-check'])
        restored = json.loads((target.root / 'status/database-restore.json').read_text())
        if (not restored.get('verified') or not restored.get('database_counts_checked')
                or restored.get('snapshot_id') != snapshot):
            raise RuntimeError('数据库与文件尚未验证')
        env.update(DATABASE_URL='postgresql://restore:isolated-restore-only@restore-db:5432/lc_restore_probe',
                   DB_AUTO_MIGRATE='false', MAINTENANCE_ENABLED='false', METRICS_ENABLED='false')
        env = {key: value for key, value in env.items() if not key.startswith(('BACKUP_', 'RESTORE_', 'RESTIC_'))}
        command = ['docker', 'run', '-d', '--pull', 'never', '--name', app, '--network', network, '--read-only',
                   '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--tmpfs', '/tmp:size=256m', '-v', volume + ':/app/data']
        for key in env:
            command += ['-e', key]
        command += [runtime['images']['app']]
        state(target, 'running', 'start_application')
        creation = subprocess.run(command, env={**os.environ, **env}, capture_output=True, timeout=60)
        if creation.returncode:
            raise RuntimeError('恢复应用容器创建失败')
        cleanup.append(['docker', 'rm', '-f', app])
        for attempt in range(45):
            try:
                run(['docker', 'exec', app, 'python', '-c', PROBE], timeout=60)
                break
            except RuntimeError:
                if attempt == 44:
                    raise
                time.sleep(2)
        result = {'verified': True, 'snapshot_id': snapshot, 'source_snapshot_id': receipt['snapshot_id'],
                  'completed_at': int(time.time()), 'app_started': True, 'database_counts_checked': True,
                  'pages_and_assets_checked': True, 'network_isolated': True, 'duration_seconds': round(time.monotonic() - started),
                  'model_configuration_decrypted': True,
                  'images': runtime['images']}
        write_json(target.root / 'status/restore.json', result)
        target.remote('restore-receipt', json.dumps(result).encode())
        state(target, 'succeeded', 'complete')
        print(json.dumps(result), flush=True)
    finally:
        failures = []
        for command in reversed(cleanup):
            try:
                run(command)
            except Exception:
                failures.append(command[1:3])
        if failures:
            raise RuntimeError('恢复临时资源清理未完成：' + str(failures))


if __name__ == '__main__':
    with lock():
        target = Offsite()
        try:
            restore(target)
        except BaseException:
            state(target, 'failed', 'restore_failed')
            raise
