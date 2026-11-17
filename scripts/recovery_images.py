"""备份前导出实际应用、数据库和运维镜像；镜像仅在变更时重建归档。"""
import gzip
import hashlib
import json
import os
import subprocess
from pathlib import Path

from ops_state import write_json


def capture(root: Path, app: str, database: str, ops_image: str):
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    os.chown(root, 10001, 10001)
    def inspect(name):
        return json.loads(subprocess.check_output(['docker', 'inspect', name], stderr=subprocess.PIPE))[0]
    images = {'app': inspect(app)['Image'], 'database': inspect(database)['Image'], 'operations': inspect(ops_image)['Id']}
    metadata = root / 'runtime.json'
    archive = root / 'runtime.tar.gz'
    if metadata.exists() and archive.exists() and json.loads(metadata.read_text()).get('images') == images:
        return
    temporary = root / 'runtime.tar.gz.tmp'
    process = None
    try:
        with temporary.open('wb') as stream:
            temporary.chmod(0o600)
            process = subprocess.Popen(['docker', 'save', *dict.fromkeys(images.values())], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert process.stdout is not None
            with gzip.GzipFile(fileobj=stream, mode='wb', compresslevel=1, mtime=0) as compressed:
                while chunk := process.stdout.read(1024 * 1024):
                    compressed.write(chunk)
            if process.wait(timeout=1800):
                raise RuntimeError('恢复镜像归档失败')
        with temporary.open('rb') as reader:
            checksum = hashlib.file_digest(reader, 'sha256').hexdigest()
        os.chown(temporary, 10001, 10001)
        temporary.replace(archive)
        write_json(metadata, {'images': images, 'archive': 'runtime.tar.gz', 'sha256': checksum}, 0o600)
        os.chown(metadata, 10001, 10001)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=30)
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    capture(Path(os.environ['OPS_STATE_ROOT']) / 'images', os.environ['OPS_APP'], os.environ['OPS_DATABASE'], os.environ['OPS_IMAGE'])
