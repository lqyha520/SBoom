"""发布已验证的增量候选；宿主执行，先备份并保留兼容回滚镜像。"""

import argparse
import copy
import json
import os
import subprocess
import time
from pathlib import Path

from drain_existing import drain
from release import atomic_write, release_lock


def run(*args):
    result = subprocess.run(args, capture_output=True, timeout=600)
    if result.returncode:
        raise RuntimeError(f'{args[0]} 执行失败（{result.returncode}）')
    return result.stdout


def inspect(name):
    return json.loads(run('docker', 'inspect', name))[0]


def verified_candidate_config(original, metadata):
    """部署配置只允许已登记的镜像、监控设置和显式关闭全天失败封锁。"""
    expected = copy.deepcopy(original)
    expected['services']['app']['image'] = metadata['image']
    environment = expected['services']['app'].setdefault('environment', {})
    environment.update(METRICS_ENABLED='true', METRICS_HOST='0.0.0.0')
    disable = metadata.get('disable_daily_failure_limit', False)
    if type(disable) is not bool:
        raise RuntimeError('失败次数配置变更标识无效')
    if disable:
        environment['GENERATION_DAILY_FAILURE_LIMIT'] = '0'
    for service in expected['services'].values():
        service.pop('build', None)
    return expected


def refresh_backup_configuration(app, backup_env):
    """备份实际运行的 Compose 配置，防止恢复仍引用安装时的旧镜像。"""
    root = Path(run('sh', '-c', '. "$1"; printf "%s" "$OPS_DEPLOY_ROOT"', 'sh', backup_env).decode())
    if not root.is_absolute() or not root.is_dir():
        raise RuntimeError('备份部署配置目录不存在')
    current = inspect(app)
    labels = current['Config']['Labels']
    command = ['docker', 'compose', '--project-directory', labels['com.docker.compose.project.working_dir'],
               '-p', labels['com.docker.compose.project']]
    if labels.get('com.docker.compose.project.environment_file'):
        command += ['--env-file', labels['com.docker.compose.project.environment_file']]
    for path in labels['com.docker.compose.project.config_files'].split(','):
        command += ['-f', path]
    config = json.loads(run(*command, 'config', '--format', 'json'))
    image = run('docker', 'image', 'inspect', '--format', '{{.Id}}', config['services']['app']['image']).decode().strip()
    if image != current['Image']:
        raise RuntimeError('备份配置与运行镜像不一致')
    config['services']['app']['image'] = image
    for service in config['services'].values():
        service.pop('build', None)
    receipt = {'image': image, 'app': app, 'container_id': current['Id'],
               'compose': command, 'captured_at': int(time.time())}
    for name, content in (('candidate.json', config), ('current.json', receipt)):
        path = root / name
        atomic_write(path, json.dumps(content).encode())
        # 运维镜像以 uid 10001 读取；新文件始终为 0600，不改变其他部署文件。
        os.chown(path, 10001, 10001)


def apply_model_mode(app, mode):
    """使用带版本检查的配置服务，保留模型、接口与原有加密密钥。"""
    if mode not in ('default', 'disabled'):
        return None
    code = '''import json,sys
from app.services.app_config import get_llm,save_llm_models
from app.models.model_profiles import TextModelProfile
c=get_llm(fresh=True)
profiles=c.get('models') or [{**c,'id':'legacy'}]
before=[{k:v for k,v in p.items() if k in TextModelProfile.model_fields and k!='apiKey'} for p in profiles]
mode=sys.argv[1]
new=save_llm_models([TextModelProfile.model_validate({**p,'thinkingMode':mode}) for p in before], expected_revision=c['revision'],require_revision=True)
print(json.dumps({'profiles':before,'revision':new['revision']}))
'''
    return json.loads(run('docker', 'exec', app, 'python', '-c', code, mode))


def restore_model_mode(app, before):
    if before is None:
        return
    code = '''import json,sys
from app.services.app_config import save_llm_models
from app.models.model_profiles import TextModelProfile
c=json.loads(sys.argv[1])
save_llm_models([TextModelProfile.model_validate(p) for p in c['profiles']],expected_revision=c['revision'],require_revision=True)
'''
    run('docker', 'exec', app, 'python', '-c', code, json.dumps(before))


def check_health(metadata, image):
    current = inspect(metadata['app'])
    if current['Image'] != image or current['State'].get('Health', {}).get('Status') != 'healthy':
        raise RuntimeError('应用镜像或健康检查不符')
    if current['Mounts'] != metadata['mounts'] or current['NetworkSettings']['Ports'] != metadata['ports']:
        raise RuntimeError('应用数据卷或端口发生变化')
    for name, identifier in metadata['containers'].items():
        if inspect(name)['Id'] != identifier:
            raise RuntimeError('其他容器被替换')
    # 本地 WSL 仅通过 Caddy 暴露应用，不能假定和生产使用相同宿主端口。
    run('docker', 'exec', metadata['app'], 'python', '-c',
        'import urllib.request; r=urllib.request.urlopen("http://127.0.0.1:8000/readyz",timeout=15); assert r.status==200')
    code = '''import urllib.request,urllib.parse
from html.parser import HTMLParser
class Assets(HTMLParser):
 def __init__(self): super().__init__(); self.urls=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='script' and a.get('src'): self.urls.append(a['src'])
  if tag=='link' and a.get('rel') in ('stylesheet','modulepreload'): self.urls.append(a['href'])
base='http://127.0.0.1:8000'
for path in ('/','/admin/'):
 url=base+path
 with urllib.request.urlopen(url,timeout=15) as response:
  assert response.status==200
  assets=Assets(); assets.feed(response.read().decode())
 assert assets.urls
 for asset in assets.urls:
  target=urllib.parse.urljoin(url,asset)
  if urllib.parse.urlparse(target).netloc!=urllib.parse.urlparse(base).netloc: continue
  with urllib.request.urlopen(target,timeout=15) as response:
   assert response.status==200 and response.read(1)
'''
    run('docker', 'exec', metadata['app'], 'python', '-c', code)


def publish(directory: Path, target: str, state_root: Path = Path('/var/lib/learn-coach/releases')):
    from quality_policy import verify_release_gate
    metadata = json.loads((directory / 'deployment.json').read_text())
    gate = json.loads((directory / 'gate.json').read_text())
    verify_release_gate(metadata, gate, target)
    state_root.mkdir(parents=True, exist_ok=True)
    with release_lock(state_root / 'release.lock'):
        old = inspect(metadata['app'])
        if old['Image'] != metadata['original'] or old['Id'] != metadata['old_app']:
            raise RuntimeError('准备后运行版本已改变')
        candidate = json.loads((directory / 'candidate.json').read_text())
        if candidate['services']['app']['image'] != metadata['image']:
            raise RuntimeError('候选配置与登记镜像不一致')
        labels = old['Config']['Labels']
        old_compose = ['docker', 'compose', '--project-directory', labels['com.docker.compose.project.working_dir'],
                       '-p', labels['com.docker.compose.project']]
        if labels.get('com.docker.compose.project.environment_file'):
            old_compose += ['--env-file', labels['com.docker.compose.project.environment_file']]
        for path in labels['com.docker.compose.project.config_files'].split(','):
            old_compose += ['-f', path]
        original_config = json.loads(run(*old_compose, 'config', '--format', 'json'))
        expected = verified_candidate_config(original_config, metadata)
        if expected != candidate:
            raise RuntimeError('存在未登记的部署配置变更')
        if target == 'production':
            backup_env, runner = '/etc/learn-coach/backup.env', '/usr/local/lib/learn-coach/production_ops.sh'
        else:
            backup_env, runner = '/etc/learn-coach-local-ops/operations.env', '/usr/local/lib/learn-coach/local_ops.sh'
        # 使用已验收的加密备份；失败时应用仍在运行。
        refresh_backup_configuration(metadata['app'], backup_env)
        run('sh', '-c', 'set -a; . "$1"; exec "$2" backup', 'sh', backup_env, runner)
        supports_drain = run('docker', 'exec', metadata['app'], 'python', '-c',
            "import importlib.util; print(int(importlib.util.find_spec('app.services.generation_drain') is not None))").strip() == b'1'
        with drain(metadata['compose'], run, legacy=not supports_drain) as release_admission:
            model_before = apply_model_mode(metadata['app'], gate.get('thinking_mode'))
            if model_before:
                atomic_write(directory / 'model-before.json', json.dumps(model_before).encode())
            rollback = {**candidate, 'services': {**candidate['services'],
                        'app': {**candidate['services']['app'], 'image': metadata['previous']}}}
            if metadata.get('disable_daily_failure_limit'):
                rollback['services']['app']['environment'] = original_config['services']['app'].get('environment', {})
            rollback_path = directory / 'rollback.json'
            atomic_write(rollback_path, json.dumps(rollback).encode())
            command = metadata['compose']
            previous_command = [str(rollback_path) if value == str(directory / 'candidate.json') else value for value in command]
            def start(compose):
                run(*compose, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '120', 'app')
            try:
                run(*command, 'stop', '--timeout', '45', 'app')
                release_admission()
                run(*command, 'run', '--rm', '--no-deps', '--pull', 'never', '-T', 'app', 'python', '-m', 'app.migrations')
                # 在切换前确认回滚镜像可读取已迁移 schema。
                run(*previous_command, 'run', '--rm', '--no-deps', '--pull', 'never', '-T', 'app', 'python', '-m', 'app.migrations', '--check')
                start(command)
                check_health(metadata, metadata['image'])
            except BaseException:
                release_admission()
                metadata.update(status='recovery_required')
                # 迁移事务未提交时可用原镜像；已升级时必须使用兼容读写的回滚镜像。
                for fallback_command, fallback_image in ((previous_command, metadata['previous']), (old_compose, metadata['original'])):
                    try:
                        run(*fallback_command, 'run', '--rm', '--no-deps', '--pull', 'never', '-T', 'app', 'python', '-m', 'app.migrations', '--check')
                        start(fallback_command)
                        check_health(metadata, fallback_image)
                        restore_model_mode(metadata['app'], model_before)
                        metadata.update(status='rolled_back', image=fallback_image, compose=fallback_command)
                        break
                    except Exception:
                        continue
                atomic_write(state_root / 'current.json', json.dumps(metadata).encode())
                if metadata['status'] == 'rolled_back':
                    refresh_backup_configuration(metadata['app'], backup_env)
                raise
            metadata.update(status='deployed', deployed_at=int(time.time()), evaluation=gate,
                            protected_images=[metadata['previous'], 'learncoach-ops:production-backup-20261110'] if target == 'production' else [metadata['previous']])
            atomic_write(state_root / 'current.json', json.dumps(metadata).encode())
            atomic_write(directory / 'deployment.json', json.dumps(metadata).encode())
            refresh_backup_configuration(metadata['app'], backup_env)
            print(json.dumps({'status': metadata['status'], 'image': metadata['image'], 'build_id': metadata['build_id']}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--target', choices=['production', 'wsl'], required=True)
    args = parser.parse_args()
    publish(args.directory, args.target)
