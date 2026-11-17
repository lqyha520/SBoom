"""按镜像 ID 保留版本；支持日期、base、rollback 标签，默认只预览。"""
import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path

from ops import compose
from release import release_lock

OPS_CONFIG_FILES = (Path('/etc/learn-coach/backup.env'), Path('/etc/learn-coach-local-ops/operations.env'),
                    Path('/etc/learn-coach-production-offsite.env'))


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def local_image_references() -> dict[str, str]:
    """未启用的 Compose 服务可以引用尚未拉取的镜像，只保护实际存在的可选引用。"""
    result = {}
    for line in run('docker', 'image', 'ls', '--digests', '--no-trunc', '--format', '{{json .}}').splitlines():
        item = json.loads(line)
        identifier, repository = item['ID'], item['Repository']
        result[identifier] = identifier
        if repository == '<none>':
            continue
        if item['Tag'] != '<none>':
            result[repository + ':' + item['Tag']] = identifier
        if item['Digest'] != '<none>':
            result[repository + '@' + item['Digest']] = identifier
    return result


def protected_images(state: dict) -> set[str]:
    references = [state[key] for key in ('image', 'previous')]
    references.extend(state.get('protected_images', []))
    # 独立运维定时器使用的镜像不一定出现在业务 Compose 中。
    for path in OPS_CONFIG_FILES:
        if path.is_file():
            for line in path.read_text().splitlines():
                key, separator, value = line.partition('=')
                if separator and key in ('OPS_IMAGE', 'OPS_RESTORE_IMAGE', 'OFFSITE_IMAGE'):
                    parsed = shlex.split(value)
                    if len(parsed) == 1:
                        references.append(parsed[0])
    command = state.get('compose') or compose()
    optional = run(*command, '--profile', 'ops', '--profile', 'restore', 'config', '--images').splitlines()
    # 当前、回滚和已配置运维镜像必须存在，缺失时仍中止清理。
    protected = {run('docker', 'image', 'inspect', '--format', '{{.Id}}', reference) for reference in set(references)}
    available = local_image_references()
    for reference in optional:
        if '@' in reference:
            repository, digest = reference.rsplit('@', 1)
            if ':' in repository.rsplit('/', 1)[-1]:
                repository = repository.rsplit(':', 1)[0]
            reference = repository + '@' + digest
        if reference in available:
            protected.add(available[reference])
    for container in run('docker', 'ps', '-aq').splitlines():
        protected.add(run('docker', 'inspect', '--format', '{{.Image}}', container))
    return protected


def candidates(images: list[dict], protected: set[str], keep: int) -> list[tuple[str, list[str]]]:
    groups: dict[str, dict] = {}
    for info in images:
        tags = [tag for tag in info.get('RepoTags') or [] if tag.split(':')[0] in ('learncoach-app', 'learncoach-ops')
                and (re.fullmatch(r'[a-f0-9]{12}', tag.rsplit(':', 1)[-1])
                     or re.search(r'20[0-9]{6}', tag.rsplit(':', 1)[-1])
                     or info.get('Config', {}).get('Labels', {}).get('io.learncoach.release'))]
        if tags:
            groups[info['Id']] = {'created': info['Created'], 'tags': tags}
    preserved = set(protected)
    # 每个仓库按实际镜像数量保留；同一镜像的三个别名只算一个版本。
    for repository in ('learncoach-app', 'learncoach-ops'):
        ordered = sorted(((item['created'], identifier) for identifier, item in groups.items()
                          if any(tag.startswith(repository + ':') for tag in item['tags'])), reverse=True)
        preserved.update(identifier for _, identifier in ordered[:keep])
    return [(identifier, sorted(item['tags'])) for identifier, item in groups.items() if identifier not in preserved]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=Path('/var/lib/learn-coach/releases/current.json'))
    parser.add_argument('--keep', type=int, default=5)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.keep < 2:
        parser.error('至少保留两个版本')
    with release_lock(args.state.parent / 'release.lock'):
        state = json.loads(args.state.read_text(encoding='utf-8'))
        if state.get('status') == 'recovery_required':
            raise RuntimeError('当前发布等待恢复，禁止清理')
        protected = protected_images(state)
        ids = set()
        for repository in ('learncoach-app', 'learncoach-ops'):
            ids.update(run('docker', 'image', 'ls', repository, '--quiet', '--no-trunc').splitlines())
        images = json.loads(run('docker', 'image', 'inspect', *sorted(ids))) if ids else []
        for identifier, tags in candidates(images, protected, args.keep):
            print(json.dumps({'image': identifier, 'tags': tags, 'apply': args.apply}, ensure_ascii=False))
            if args.apply:
                # 再检查容器、定时任务配置、当前/回滚版本与标签归属，避免预览后状态改变。
                for tag in tags:
                    latest = json.loads(args.state.read_text(encoding='utf-8'))
                    if latest != state or identifier in protected_images(latest):
                        raise RuntimeError('保护集合发生变化，停止清理')
                    if run('docker', 'image', 'inspect', '--format', '{{.Id}}', tag) != identifier:
                        raise RuntimeError('镜像标签已改变，停止清理')
                    run('docker', 'image', 'rm', '--no-prune', tag)


if __name__ == '__main__':
    main()
