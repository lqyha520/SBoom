"""从 Git 提交快照构建应用与运维镜像，保存校验包；可选上传到已有 SSH 目录。

在 WSL/Linux 仓库内执行：
python3 scripts/release/prepare.py --ref HEAD --output /secure/releases
上传需显式指定 --host user@server --remote-dir /secure/incoming。
"""
import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host')
    parser.add_argument('--remote-dir')
    args = parser.parse_args()
    if bool(args.host) != bool(args.remote_dir):
        parser.error('上传需要同时指定 host 和 remote-dir')
    if args.host and (not re.fullmatch(r'[\w.@-]+', args.host) or args.host.startswith('-')
                      or not re.fullmatch(r'/[\w/.-]+', args.remote_dir)):
        parser.error('请使用简单 SSH 主机别名和绝对目录（不含空格或 shell 字符）')
    commit = run('git', 'rev-parse', '--verify', args.ref + '^{commit}')
    output = args.output.resolve() / commit[:12]
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='lc-release-') as folder:
        root = Path(folder)
        archive = root / 'source.tar'
        run('git', 'archive', '--format=tar', '--output=' + str(archive), commit)
        source = root / 'source'
        source.mkdir()
        with tarfile.open(archive) as snapshot:
            snapshot.extractall(source, filter='data')
        images = [f'learncoach-app:{commit[:12]}', f'learncoach-ops:{commit[:12]}']
        for target, image in zip(('runtime', 'ops'), images, strict=True):
            subprocess.run(['docker', 'build', '--target', target, '-t', image, str(source)], check=True)
        bundle = output / 'images.tar'
        run('docker', 'save', '-o', str(bundle), *images)
        with bundle.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        (output / 'images.tar.sha256').write_text(digest + '  images.tar\n', encoding='utf-8')
        (output / 'release.json').write_text(json.dumps({'commit': commit, 'images': images,
            'image_ids': [run('docker', 'image', 'inspect', '--format', '{{.Id}}', image) for image in images],
            'sha256': digest}, indent=2), encoding='utf-8')
    if args.host:
        subprocess.run(['scp', str(bundle), str(output / 'images.tar.sha256'), str(output / 'release.json'),
                        args.host + ':' + args.remote_dir.rstrip('/') + '/'], check=True)
    print('构建完成：', output)


if __name__ == '__main__':
    main()
