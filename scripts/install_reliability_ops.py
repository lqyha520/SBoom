"""升级已有备份与监测，不重置仓库密码，不更换业务数据卷。"""
import argparse
import io
import json
import shlex
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/release'))
from existing_host import Host

IMAGE = 'learncoach-ops:reliability-20261110'
OFFSITE = '/home/lqyha/learn-coach-production-backup'
SOURCE_RETRY = ('[Unit]\nStartLimitIntervalSec=7200\nStartLimitBurst=3\n'
                '[Service]\nRestart=on-failure\nRestartSec=300\n')


def settings(host, path):
    return {key: shlex.split(value)[0] for key, value in
            (line.split('=', 1) for line in host.read(path).decode().splitlines() if line and not line.startswith('#'))}


def write_env(host, path, values):
    host.write(path, ''.join(f'{key}={shlex.quote(value)}\n' for key, value in values.items()).encode())


def service(host, name, command, env_file, calendar=None, retry=False):
    limit = 'StartLimitIntervalSec=0\n' if name == 'learn-coach-public-monitor' else 'StartLimitIntervalSec=7200\nStartLimitBurst=3\n'
    content = ('[Unit]\nDescription=Learn Coach verified operations\nAfter=network-online.target docker.service\n'
               f'Requires=docker.service\n{limit}\n[Service]\nType=oneshot\n'
               f'EnvironmentFile={env_file}\nExecStart={command}\nUMask=0077\nTimeoutStartSec=7200\n')
    if retry:
        content += 'Restart=on-failure\nRestartSec=300\n'
    if name in ('learn-coach-production-offsite', 'learn-coach-production-restore'):
        kind = 'offsite' if name.endswith('offsite') else 'restore'
        content += f'ExecStopPost=/usr/bin/python3 /usr/local/lib/learn-coach/operation_result.py {kind}\n'
    host.write('/etc/systemd/system/' + name + '.service', content.encode(), '644')
    if calendar:
        timer = ('[Unit]\nDescription=Learn Coach verified operations schedule\n[Timer]\n'
                 f'OnCalendar={calendar}\nPersistent=true\nRandomizedDelaySec=60\n[Install]\nWantedBy=timers.target\n')
        host.write('/etc/systemd/system/' + name + '.timer', timer.encode(), '644')
    host.run('systemd-analyze', 'verify', '/etc/systemd/system/' + name + '.service')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-url', required=True)
    args = parser.parse_args()
    from urllib.parse import urlsplit
    url = urlsplit(args.public_url)
    if url.scheme != 'https' or not url.hostname or url.query or url.username:
        raise ValueError('需要已核实的公网 HTTPS 入口')
    wsl, production = Host('wsl'), Host('production')
    old = settings(production, '/etc/learn-coach/backup.env')
    context = OFFSITE + '/reliability-build'
    wsl.run('mkdir', '-p', context)
    files = {name: (ROOT / name).read_bytes().replace(b'\r\n', b'\n') for name in
             ('scripts/ops_backup.py', 'scripts/backup_restore.py', 'scripts/local_backup_config.py')}
    files['Dockerfile'] = (b'FROM learncoach-ops:production-backup-20261110\nUSER root\nCOPY scripts /app/scripts\nUSER app\n')
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name, value in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(value), 0o644, int(time.time())
            archive.addfile(info, io.BytesIO(value))
    wsl.run('tar', '-xf', '-', '-C', context, data=stream.getvalue())
    wsl.run('docker', 'build', '--pull=false', '--network=none', '-t', IMAGE, context)
    image = wsl.inspect(IMAGE)['Id']
    try:
        installed = production.inspect(IMAGE)['Id']
    except RuntimeError:
        installed = None
    if installed != image:
        source = subprocess.Popen(wsl.command(['docker', 'save', IMAGE]), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            transferred = subprocess.run(production.command(['docker', 'load']), stdin=source.stdout,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=1800)
            if source.stdout:
                source.stdout.close()
            if source.wait(timeout=60) or transferred.returncode:
                raise RuntimeError('备份镜像传输失败')
        finally:
            if source.poll() is None:
                source.kill()
    assert production.inspect(IMAGE)['Id'] == image
    common = ('ops_state.py',)
    for host, names in ((production, (*common, 'backup_gateway.py', 'recovery_images.py', 'production_monitor.py', 'ops_check.py')),
                        (wsl, (*common, 'offsite_ops.py', 'full_restore.py', 'public_monitor.py', 'operation_result.py', 'ops_check.py'))):
        for name in names:
            host.write('/usr/local/lib/learn-coach/' + name, (ROOT / 'scripts' / name).read_bytes().replace(b'\r\n', b'\n'), '700')
    runner = (ROOT / 'scripts/local_ops.sh').read_text().replace('learn-coach-local-ops.lock', 'learn-coach-production-ops.lock')
    production.write('/usr/local/lib/learn-coach/production_ops.sh', runner.encode(), '700')
    old.update(OPS_IMAGE=IMAGE, OPS_DATABASE=production.database, OPS_RESTORE_IMAGE=production.inspect(production.database)['Image'], OPS_BACKUP_IMAGES='true',
               OPS_OPERATION_STATUS='/var/lib/learn-coach/ops-status/source-operation.json')
    write_env(production, '/etc/learn-coach/backup.env', old)
    external = settings(wsl, '/etc/learn-coach-production-offsite.env')
    external.update(OFFSITE_IMAGE=IMAGE, OPS_PUBLIC_URL=args.public_url.rstrip('/'))
    write_env(wsl, '/etc/learn-coach-production-offsite.env', external)
    service(wsl, 'learn-coach-production-offsite', '/usr/bin/python3 /usr/local/lib/learn-coach/offsite_ops.py sync',
            '/etc/learn-coach-production-offsite.env', '*-*-* 03:30:00 Asia/Shanghai', retry=True)
    service(wsl, 'learn-coach-production-restore', '/usr/bin/python3 /usr/local/lib/learn-coach/full_restore.py',
            '/etc/learn-coach-production-offsite.env', 'Sun *-*-* 05:00:00 Asia/Shanghai')
    service(wsl, 'learn-coach-public-monitor', '/usr/bin/python3 /usr/local/lib/learn-coach/public_monitor.py',
            '/etc/learn-coach-production-offsite.env', '*-*-* *:0/5:00 Asia/Shanghai')
    production.run('mkdir', '-p', '/etc/systemd/system/learn-coach-ops-check.service.d')
    production.write('/etc/systemd/system/learn-coach-ops-check.service.d/reliability.conf',
                     ('[Service]\nEnvironment=OPS_TLS_HOST=' + url.hostname + '\n').encode(), '644')
    production.run('mkdir', '-p', '/etc/systemd/system/learn-coach-production-backup.service.d')
    production.write('/etc/systemd/system/learn-coach-production-backup.service.d/retry.conf', SOURCE_RETRY.encode(), '644')
    for host in (wsl, production):
        host.run('systemctl', 'daemon-reload')
    wsl.run('systemctl', 'reset-failed', 'learn-coach-production-offsite.service')
    wsl.run('systemctl', 'enable', '--now', 'learn-coach-production-offsite.timer', 'learn-coach-production-restore.timer', 'learn-coach-public-monitor.timer')
    wsl.run('systemctl', 'start', '--no-block', 'learn-coach-production-offsite.service')
    print(json.dumps({'installed': True, 'image': image, 'public_url': args.public_url}), flush=True)


if __name__ == '__main__':
    main()
