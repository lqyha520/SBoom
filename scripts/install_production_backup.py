"""为已有生产容器安装备份，WSL 拉取到独立加密仓库并执行恢复演练。"""
import io
import json
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/release'))
from existing_host import Host

OPS_ROOT = '/data/data1/learn-coach-ops'
OFFSITE_ROOT = '/home/lqyha/learn-coach-production-backup'
IMAGE = 'learncoach-ops:production-backup-20261110'


def write(host, path, value, mode='600'):
    host.write(path, value.encode() if isinstance(value, str) else value, mode)


def unit(host, name, command, environment, calendar):
    service = f'[Unit]\nDescription=Learn Coach {name}\nAfter=network-online.target docker.service\nRequires=docker.service\n\n[Service]\nType=oneshot\nEnvironmentFile={environment}\nExecStart={command}\nUMask=0077\nTimeoutStartSec=7200\n'
    timer = f'[Unit]\nDescription=Learn Coach {name} schedule\n\n[Timer]\nOnCalendar={calendar}\nPersistent=true\nRandomizedDelaySec=180\n\n[Install]\nWantedBy=timers.target\n'
    for suffix, content in (('service', service), ('timer', timer)):
        write(host, '/etc/systemd/system/' + name + '.' + suffix, content, '644')
    host.run('systemd-analyze', 'verify', '/etc/systemd/system/' + name + '.service', '/etc/systemd/system/' + name + '.timer')


def main():
    wsl, production = Host('wsl'), Host('production')
    wsl_config = dict(line.split('=', 1) for line in wsl.read('/etc/learn-coach-local-ops/operations.env').decode().splitlines())
    base = shlex.split(wsl_config['OPS_IMAGE'])[0]
    context = OFFSITE_ROOT + '/build'
    wsl.run('mkdir', '-p', '-m', '700', context, OFFSITE_ROOT + '/status', OFFSITE_ROOT + '/repository')
    files = {name: (ROOT / name).read_bytes().replace(b'\r\n', b'\n') for name in
             ('scripts/ops_backup.py', 'scripts/backup_restore.py', 'scripts/local_backup_config.py',
              'app/storage_registry.py', 'app/constants.py')}
    files['Dockerfile'] = f'FROM {base}\nUSER root\nCOPY scripts /app/scripts\nCOPY app /app/app\nUSER app\n'.encode()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(content), 0o644
            archive.addfile(member, io.BytesIO(content))
    wsl.run('tar', '-xf', '-', '-C', context, data=stream.getvalue())
    wsl.run('docker', 'build', '--pull=false', '--network=none', '-t', IMAGE, context)
    # 已有运维镜像复用依赖；管道传输镜像，不在服务器保留额外 tar 包。
    try:
        installed = production.inspect(IMAGE)['Id']
    except RuntimeError:
        installed = None
    if installed != wsl.inspect(IMAGE)['Id']:
        print('正在传输专用备份镜像。', flush=True)
        source = subprocess.Popen(wsl.command(['docker', 'save', IMAGE]), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            result = subprocess.run(production.command(['docker', 'load']), stdin=source.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=1800)
            if source.stdout:
                source.stdout.close()
            if source.wait(timeout=30) or result.returncode:
                raise RuntimeError('运维镜像传输失败')
        finally:
            if source.poll() is None:
                source.kill()
    app = production.inspect(production.app)
    database = production.inspect(production.database)
    networks = set(app['NetworkSettings']['Networks']) & set(database['NetworkSettings']['Networks'])
    if len(networks) != 1:
        raise RuntimeError('无法确定备份网络')
    volume = next(mount['Name'] for mount in app['Mounts'] if mount['Destination'] == '/app/data' and mount['Type'] == 'volume')
    production.run('mkdir', '-p', '-m', '700', OPS_ROOT + '/deployment', '/etc/learn-coach', '/usr/local/lib/learn-coach')
    production.run('chmod', '711', OPS_ROOT)
    configuration = production.run(*production.compose(app), 'config', '--format', 'json')
    write(production, OPS_ROOT + '/deployment/candidate.json', configuration)
    production.run('chown', '-R', '10001:10001', OPS_ROOT + '/deployment')
    settings = {'OPS_IMAGE': IMAGE, 'OPS_STATE_ROOT': OPS_ROOT, 'OPS_DEPLOY_ROOT': OPS_ROOT + '/deployment',
                'OPS_APP': production.app, 'OPS_NETWORK': next(iter(networks)), 'OPS_VOLUME': volume,
                'OPS_RESTORE_IMAGE': database['Image']}
    write(production, '/etc/learn-coach/backup.env', ''.join(f'{key}={shlex.quote(value)}\n' for key, value in settings.items()))
    runner = (ROOT / 'scripts/local_ops.sh').read_text(encoding='utf-8').replace('learn-coach-local-ops.lock', 'learn-coach-production-ops.lock')
    write(production, '/usr/local/lib/learn-coach/production_ops.sh', runner, '700')
    unit(production, 'learn-coach-production-backup', '/usr/local/lib/learn-coach/production_ops.sh backup',
         '/etc/learn-coach/backup.env', '*-*-* 03:10:00 Asia/Shanghai')
    production.run('systemctl', 'daemon-reload')
    production.run('systemctl', 'enable', '--now', 'learn-coach-production-backup.timer')
    write(production, '/usr/local/lib/learn-coach/backup_gateway.py', (ROOT / 'scripts/backup_gateway.py').read_bytes(), '700')
    production.run('sh', '-c', 'docker inspect learncoach-app-1 | docker run --rm --pull never --network none --user 0 -i -v /data/data1/learn-coach-ops:/state --entrypoint python ' + IMAGE + ' scripts/local_backup_config.py')
    # 密码只写私有文件，不出现在命令行、日志、Git 或镜像中。
    write(wsl, OFFSITE_ROOT + '/restic-password', production.read(OPS_ROOT + '/restic-password'), '400')
    wsl.run('chown', '10001:10001', OFFSITE_ROOT + '/restic-password', OFFSITE_ROOT + '/status', OFFSITE_ROOT + '/repository')
    wsl.run('chmod', '711', OFFSITE_ROOT)
    wsl.run('sh', '-c', 'test -f "$1" || ssh-keygen -q -t ed25519 -N "" -C learn-coach-offsite -f "$1"', 'sh', OFFSITE_ROOT + '/ssh-key')
    public_key = wsl.read(OFFSITE_ROOT + '/ssh-key.pub').decode().strip()
    authorized = 'restrict,command="python3 /usr/local/lib/learn-coach/backup_gateway.py" ' + public_key
    production.run('python3', '-c', 'from pathlib import Path; import sys; p=Path("/root/.ssh/authorized_keys"); s=p.read_text(); k=sys.stdin.read().strip(); p.write_text(s if k in s else s.rstrip()+chr(10)+k+chr(10)); p.chmod(0o600)', data=authorized.encode())
    remote = dict(line.split(' ', 1) for line in subprocess.check_output(['ssh', '-G', 'myserver'], text=True).splitlines() if ' ' in line)
    if remote['user'] != 'root' or not remote['port'].isdigit() or not 1 <= int(remote['port']) <= 65535:
        raise RuntimeError('当前安装器需要已验证的 root SSH 连接与有效端口')
    host = remote['hostname']
    # 通过现有已认证 SSH 通道取得主机公钥，不接受未核验的 ssh-keyscan 结果。
    host_key = production.read('/etc/ssh/ssh_host_ed25519_key.pub').decode().split()
    host_label = host if remote['port'] == '22' else f"[{host}]:{remote['port']}"
    write(wsl, OFFSITE_ROOT + '/known_hosts', host_label + ' ' + ' '.join(host_key[:2]) + '\n')
    write(wsl, '/usr/local/lib/learn-coach/offsite_pull.sh', (ROOT / 'scripts/offsite_pull.sh').read_bytes(), '700')
    write(wsl, '/etc/learn-coach-production-offsite.env', f"OFFSITE_ROOT={OFFSITE_ROOT}\nOFFSITE_HOST=root@{host}\nOFFSITE_PORT={remote['port']}\nOFFSITE_IMAGE={IMAGE}\n")
    unit(wsl, 'learn-coach-production-offsite', '/usr/local/lib/learn-coach/offsite_pull.sh', '/etc/learn-coach-production-offsite.env', '*-*-* 03:30:00 Asia/Shanghai')
    # 复用隔离恢复器，但删除读取本地业务容器/生成运行配置的步骤。
    restore_runner = runner[runner.index('#!'):]
    start, end = restore_runner.index('docker inspect "$OPS_APP"'), restore_runner.index('\nrun_backup()')
    restore_runner = restore_runner[:start] + restore_runner[end:]
    restore_runner = restore_runner.replace('learn-coach-production-ops.lock', 'learn-coach-offsite.lock')
    write(wsl, '/usr/local/lib/learn-coach/offsite_restore.sh', restore_runner, '700')
    restore_env = {**settings, 'OPS_STATE_ROOT': OFFSITE_ROOT, 'OPS_IMAGE': IMAGE}
    write(wsl, '/etc/learn-coach-production-restore.env', ''.join(f'{key}={shlex.quote(value)}\n' for key, value in restore_env.items()))
    unit(wsl, 'learn-coach-production-restore', '/usr/local/lib/learn-coach/offsite_restore.sh restore-check', '/etc/learn-coach-production-restore.env', 'Sun *-*-* 05:00:00 Asia/Shanghai')
    wsl.run('systemctl', 'daemon-reload')
    print('正在执行首次生产备份、WSL 密文校验与隔离恢复。', flush=True)
    wsl.run('systemctl', 'start', 'learn-coach-production-offsite.service', timeout=7200)
    wsl.run('systemctl', 'start', 'learn-coach-production-restore.service', timeout=7200)
    wsl.run('systemctl', 'enable', '--now', 'learn-coach-production-offsite.timer', 'learn-coach-production-restore.timer')
    print(json.dumps({'offsite': json.loads(wsl.read(OFFSITE_ROOT + '/status/backup.json')),
                      'restore': json.loads(wsl.read(OFFSITE_ROOT + '/status/restore.json'))}), flush=True)


if __name__ == '__main__':
    main()
