"""访问现有 WSL/SSH 部署；凭据及完整 Docker 检查结果只在内存中处理。"""
import hashlib
import json
import shlex
import subprocess
import time
from pathlib import Path
from typing import cast


class Host:
    def __init__(self, target: str):
        if target not in ('wsl', 'production'):
            raise ValueError('未知部署目标')
        self.target = target
        self.app = 'deploy-app-1' if target == 'wsl' else 'learncoach-app-1'
        self.database = 'deploy-db-1' if target == 'wsl' else 'learncoach-db-1'
        self.root = '/home/lqyha/learn-coach/releases' if target == 'wsl' else '/opt/learn-coach/releases'

    def command(self, args):
        return (['wsl.exe', '-d', 'Debian', '-u', 'root', '--exec', *args] if self.target == 'wsl' else
                ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15',
                 '-o', 'ServerAliveCountMax=3', 'myserver', shlex.join(args)])

    def run(self, *args, data: bytes | None = None, timeout: int = 300, read_only: bool = False) -> bytes:
        readonly = (read_only or args[:2] in (('docker', 'inspect'), ('docker', 'ps'))
                    or args[:3] == ('docker', 'image', 'inspect') or args[:1] == ('cat',))
        attempts = 3 if self.target == 'production' and readonly and data is None else 1
        for attempt in range(attempts):
            result = subprocess.run(self.command(args), input=data, capture_output=True, timeout=timeout)
            if result.returncode != 255 or attempt == attempts - 1:
                break
            time.sleep(attempt + 1)
        if result.returncode:
            raise RuntimeError(f'{self.target}: {args[0]} 执行失败，退出码 {result.returncode}')
        return result.stdout

    def inspect(self, name: str) -> dict:
        return cast(dict, json.loads(self.run('docker', 'inspect', name))[0])

    def write(self, path: str, data: bytes, mode='600'):
        self.run('sh', '-c', 'set -eu; umask 077; trap \'rm -f -- "$1.tmp"\' EXIT; '
                 'cat > "$1.tmp"; actual=$(sha256sum "$1.tmp"); test "${actual%% *}" = "$3"; '
                 'chmod "$2" "$1.tmp"; mv -f -- "$1.tmp" "$1"',
                 'sh', path, mode, hashlib.sha256(data).hexdigest(), data=data)

    def read(self, path: str) -> bytes:
        return self.run('cat', path)

    def compose(self, inspected: dict, files=None) -> list[str]:
        labels = inspected['Config']['Labels']
        command = ['docker', 'compose', '--project-directory', labels['com.docker.compose.project.working_dir'],
                   '-p', labels['com.docker.compose.project']]
        if labels.get('com.docker.compose.project.environment_file'):
            command += ['--env-file', labels['com.docker.compose.project.environment_file']]
        for path in files or labels['com.docker.compose.project.config_files'].split(','):
            command += ['-f', path]
        return command


def save(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
