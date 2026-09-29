"""列出旧版项目镜像；默认只预览，--apply 才删除。不运行全局 docker prune。"""
import argparse
import json
import subprocess
from pathlib import Path

from ops import compose


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=Path('/var/lib/learn-coach/releases/current.json'))
    parser.add_argument('--keep', type=int, default=5)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.keep < 2:
        parser.error('至少保留两个版本')
    state = json.loads(args.state.read_text(encoding='utf-8'))
    protected = {run('docker', 'image', 'inspect', '--format', '{{.Id}}', state[key]) for key in ('image', 'previous')}
    # 定时任务容器通常已 --rm；仍须保护配置中指定的运维镜像。
    for image in run(*compose(), '--profile', 'ops', '--profile', 'restore', 'config', '--images').splitlines():
        protected.add(run('docker', 'image', 'inspect', '--format', '{{.Id}}', image))
    containers = run('docker', 'ps', '-aq').splitlines()
    for container in containers:
        protected.add(run('docker', 'inspect', '--format', '{{.Image}}', container))
    for repository in ('learncoach-app', 'learncoach-ops'):
        tags = set(run('docker', 'image', 'ls', repository, '--format', '{{.Repository}}:{{.Tag}}').splitlines())
        candidates = []
        for tag in tags:
            # 只管理 prepare.py 生成的提交标签，其他镜像由操作者自行管理。
            suffix = tag.rsplit(':', 1)[-1]
            if len(suffix) != 12 or any(char not in '0123456789abcdef' for char in suffix):
                continue
            info = json.loads(run('docker', 'image', 'inspect', tag))[0]
            candidates.append((info['Created'], tag, info['Id']))
        for _, tag, identifier in sorted(candidates, reverse=True)[args.keep:]:
            if identifier in protected:
                continue
            print(('删除：' if args.apply else '可清理：') + tag)
            if args.apply:
                run('docker', 'image', 'rm', tag)


if __name__ == '__main__':
    main()
