"""为已有本地 WSL Docker 应用安装加密备份与独立恢复定时任务。"""
import argparse
import hashlib
import io
import json
import re
import shlex
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CONFIG = '/etc/learn-coach-local-ops'
RUNNER = '/usr/local/lib/learn-coach/local_ops.sh'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--distribution', default='Debian')
    parser.add_argument('--app', default='deploy-app-1')
    parser.add_argument('--database', default='deploy-db-1')
    parser.add_argument('--state-root', default='/home/lqyha/learn-coach-local-ops')
    parser.add_argument('--base-image', required=True, help='已有且包含 restic/PG16 客户端的 learncoach-ops 镜像')
    parser.add_argument('--verify', action='store_true', help='安装后立即备份并执行恢复演练')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_./:@-]+', args.base_image) or not PurePosixPath(args.state_root).is_absolute() or '..' in PurePosixPath(args.state_root).parts or len(PurePosixPath(args.state_root).parts) < 3:
        parser.error('镜像名或状态目录无效')
    prefix = ['wsl.exe', '-d', args.distribution, '-u', 'root', '--exec']

    def run(*command, data=None):
        result = subprocess.run([*prefix, *command], input=data, capture_output=True)
        if result.returncode:
            raise RuntimeError(f'{command[0]} 执行失败（{result.returncode}）；请查看本地运维服务日志')
        return result.stdout

    def write(path, content, mode='600'):
        run('sh', '-c', 'umask 077; cat > "$1"; chmod "$2" "$1"', 'sh', path, mode, data=content.encode('utf-8'))

    app, database = json.loads(run('docker', 'inspect', args.app, args.database))
    if not app['State']['Running'] or not database['State']['Running']:
        raise RuntimeError('业务容器未运行')
    networks = set(app['NetworkSettings']['Networks']) & set(database['NetworkSettings']['Networks'])
    if len(networks) != 1:
        raise RuntimeError('需要明确唯一的应用与数据库共有网络')
    mount = next(item for item in app['Mounts'] if item['Destination'] == '/app/data')
    if mount['Type'] != 'volume':
        raise RuntimeError('当前安装器要求具名 appdata 卷')
    deployment = app['Config']['Labels']['com.docker.compose.project.working_dir']
    if not PurePosixPath(deployment).is_absolute() or '\n' in deployment:
        raise RuntimeError('部署目录无效')
    run('test', '-f', deployment + '/.env.production')
    run('docker', 'image', 'inspect', args.base_image, 'postgres:16-bookworm')
    run('docker', 'run', '--rm', '--pull', 'never', '--network', 'none', '--entrypoint', 'sh', args.base_image, '-c', 'command -v restic >/dev/null; command -v pg_dump >/dev/null; command -v pg_restore >/dev/null')
    files = {path.relative_to(ROOT).as_posix(): path.read_bytes() for folder in ('app', 'scripts') for path in (ROOT / folder).rglob('*') if path.is_file() and '__pycache__' not in path.parts}
    fingerprint = hashlib.sha256(b''.join(name.encode() + data for name, data in sorted(files.items()))).hexdigest()[:12]
    image = 'learncoach-ops:local-backup-' + fingerprint
    files['Dockerfile'] = f'FROM {args.base_image}\nUSER root\nCOPY app /app/app\nCOPY scripts /app/scripts\nUSER app\n'.encode()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as tar:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            tar.addfile(member, io.BytesIO(data))
    build = args.state_root + '/build-' + fingerprint
    run('mkdir', '-p', '-m', '711', args.state_root)
    run('mkdir', '-p', '-m', '700', build, CONFIG, '/usr/local/lib/learn-coach')
    run('tar', '-xf', '-', '-C', build, data=archive.getvalue())
    print('正在准备本地备份镜像。', flush=True)
    run('docker', 'build', '--pull=false', '-t', image, build)
    write(RUNNER, (ROOT / 'scripts/local_ops.sh').read_text(encoding='utf-8'), '700')
    variables = {'OPS_IMAGE': image, 'OPS_STATE_ROOT': args.state_root, 'OPS_DEPLOY_ROOT': deployment,
                 'OPS_APP': args.app, 'OPS_NETWORK': next(iter(networks)), 'OPS_VOLUME': mount['Name'], 'OPS_RESTORE_IMAGE': 'postgres:16-bookworm'}
    write(CONFIG + '/operations.env', ''.join(f'{key}={shlex.quote(value)}\n' for key, value in variables.items()))
    for action, calendar in (('backup', '*-*-* 03:00:00 Asia/Shanghai'), ('restore', 'Sun *-*-* 04:00:00 Asia/Shanghai')):
        unit = f'learn-coach-local-{action}'
        command = 'backup' if action == 'backup' else 'restore-check'
        service = f'[Unit]\nDescription=Learning Coach local {action}\nAfter=docker.service\nRequires=docker.service\n\n[Service]\nType=oneshot\nEnvironmentFile={CONFIG}/operations.env\nExecStart={RUNNER} {command}\nUMask=0077\nTimeoutStartSec=3600\n'
        timer = f'[Unit]\nDescription=Learning Coach local {action} schedule\n\n[Timer]\nOnCalendar={calendar}\nPersistent=true\nRandomizedDelaySec=300\n\n[Install]\nWantedBy=timers.target\n'
        write('/etc/systemd/system/' + unit + '.service', service, '644')
        write('/etc/systemd/system/' + unit + '.timer', timer, '644')
    run('systemd-analyze', 'verify', '/etc/systemd/system/learn-coach-local-backup.service', '/etc/systemd/system/learn-coach-local-backup.timer', '/etc/systemd/system/learn-coach-local-restore.service', '/etc/systemd/system/learn-coach-local-restore.timer')
    run('systemctl', 'daemon-reload')
    if args.verify:
        print('正在备份并恢复到独立临时数据库。', flush=True)
        run('systemctl', 'start', 'learn-coach-local-backup.service')
        run('systemctl', 'start', 'learn-coach-local-restore.service')
    run('systemctl', 'enable', '--now', 'learn-coach-local-backup.timer', 'learn-coach-local-restore.timer')
    print(json.dumps({'installed': True, 'verified': args.verify, 'offsite': False, 'image': image,
                      'backup_schedule': '每天 03:00（北京时间，最多延迟 5 分钟）', 'restore_schedule': '每周日 04:00（北京时间，最多延迟 5 分钟）'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
