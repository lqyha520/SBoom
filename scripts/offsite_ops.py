"""生产密文缓存导入独立 WSL 仓库；中断不删除已验证的历史备份。"""
import argparse
import json
import os
import secrets
import shlex
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from ops_state import operation, write_json


def run(args, *, data=None, timeout=1800, output=None):
    result = subprocess.run(args, input=data, stdout=output or subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{Path(args[0]).name} exit={result.returncode}')
    return result.stdout


@contextmanager
def lock():
    import fcntl
    with open('/run/lock/learn-coach-offsite.lock', 'a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


class Offsite:
    def __init__(self):
        self.root = Path(os.environ['OFFSITE_ROOT'])
        self.image = os.environ['OFFSITE_IMAGE']
        self.host = os.environ['OFFSITE_HOST']
        self.vault = self.root / 'vault'
        self.password = self.root / 'vault-password'
        self.cache = self.root / 'source-cache'
        self.ssh = ['ssh', '-p', os.environ.get('OFFSITE_PORT', '22'), '-i', str(self.root / 'ssh-key'),
                    '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'ConnectionAttempts=2',
                    '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
                    '-o', 'ControlMaster=auto', '-o', 'ControlPersist=120', '-o', f'ControlPath={self.root}/ssh-control',
                    '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={self.root}/known_hosts']

    def remote(self, command, data=None):
        return run([*self.ssh, self.host, command], data=data)

    def state(self, status, stage, attempt=1, error=None):
        value = operation(self.root / 'status/operation.json', status, stage, attempt=attempt, error=error)
        print(json.dumps(value), flush=True)
        try:
            self.remote('operation', json.dumps(value).encode())
        except Exception:
            # 本地状态始终保留；服务器以运行心跳超时识别回执连接中断。
            pass

    def restic(self, *args, source=None, writable=True, output=None):
        command = ['docker', 'run', '--rm', '--pull', 'never', '--network', 'none', '--read-only',
                   '--user', '10001:10001', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                   '--tmpfs', '/tmp:size=512m', '-e', 'RESTIC_REPOSITORY=/vault', '-e', 'RESTIC_PASSWORD_FILE=/password',
                   '-e', 'RESTIC_CACHE_DIR=/tmp', '-v', f'{self.vault}:/vault' + ('' if writable else ':ro'),
                   '-v', f'{self.password}:/password:ro']
        if source:
            command += ['-v', f'{source}:/source:ro', '-v', f'{self.root}/restic-password:/source-password:ro']
        command += ['--entrypoint', 'restic', self.image]
        # copy 会尝试给源仓库加锁；源挂载只读且整个流程已有宿主独占锁。
        return run([*command, *(['--no-lock'] if not writable or source else []), *args], output=output)

    def initialize(self):
        self.vault.mkdir(mode=0o700, exist_ok=True)
        os.chown(self.vault, 10001, 10001)
        if not self.password.exists():
            if (self.vault / 'config').exists():
                raise RuntimeError('独立仓库存在但密码丢失，不能重置密码')
            fd = os.open(self.password, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
            with os.fdopen(fd, 'w') as stream:
                stream.write(secrets.token_urlsafe(64) + '\n')
            os.chown(self.password, 10001, 10001)
        if not (self.vault / 'config').exists():
            self.restic('init')

    def import_snapshot(self, source, snapshot):
        self.restic('copy', '--from-repo', '/source', '--from-password-file', '/source-password', snapshot, source=source)
        snapshots = json.loads(self.restic('snapshots', '--json'))
        matches = [item for item in snapshots if item.get('original') == snapshot or item['id'] == snapshot]
        if len(matches) != 1:
            raise RuntimeError('独立仓库快照无法对应源快照')
        self.restic('check', '--read-data')
        return matches[0]['id']

    def sync(self):
        self.initialize()
        # 首次先导入上一份已验证副本，远端失败时仍有独立、可恢复的历史。
        prior = self.root / 'status/backup.json'
        if prior.exists() and not json.loads(self.restic('snapshots', '--json')):
            old = json.loads(prior.read_text())
            self.import_snapshot(self.root / 'repository', old['snapshot_id'])
        if not self.cache.exists():
            self.cache.mkdir(mode=0o700)
            # 旧镜像仅作为本机种子，复制后仍由 rsync 校准；避免首次重传全部历史密文。
            if (self.root / 'repository/config').exists():
                run(['cp', '-a', str(self.root / 'repository') + '/.', str(self.cache) + '/'])
        last_error = None
        for attempt in range(1, 4):
            try:
                self.state('running', 'source_backup', attempt)
                self.remote('backup')
                source = json.loads(self.remote('status'))
                self.state('running', 'transfer', attempt)
                run(['rsync', '-a', '--delete-delay', '--timeout=90', '-e', shlex.join(self.ssh),
                     self.host + ':/data/data1/learn-coach-ops/repository/', str(self.cache) + '/'])
                self.state('running', 'independent_copy', attempt)
                snapshot = self.import_snapshot(self.cache, source['snapshot_id'])
                receipt = {'verified': True, 'offsite': True, 'independent': True, 'snapshot_id': source['snapshot_id'],
                           'vault_snapshot_id': snapshot, 'completed_at': int(time.time())}
                write_json(self.root / 'status/backup.json', receipt)
                self.remote('receipt', json.dumps(receipt).encode())
                # 独立保留；至少保留三次，防止同日新快照淘汰发布前版本。
                self.restic('forget', '--host', 'learn-coach', '--tag', 'learn-coach', '--group-by', 'host,tags',
                            '--keep-last', '3', '--keep-daily', '7', '--keep-weekly', '4', '--keep-monthly', '6', '--prune')
                self.state('succeeded', 'complete', attempt)
                return receipt
            except Exception as error:
                last_error = type(error).__name__
                self.state('failed', 'retry_pending' if attempt < 3 else 'exhausted', attempt, last_error)
                if attempt < 3:
                    time.sleep(10 * attempt)
        raise RuntimeError('异地同步三次尝试失败：' + str(last_error))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['sync', 'initialize'])
    args = parser.parse_args()
    with lock():
        target = Offsite()
        try:
            target.sync() if args.action == 'sync' else target.initialize()
        except BaseException as error:
            target.state('failed', 'operation_failed', error=type(error).__name__)
            raise
