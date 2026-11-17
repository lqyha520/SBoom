"""从 Docker 检查结果准备本地备份配置；不输出环境或密钥。"""
import json
import os
import secrets
import sys
from pathlib import Path


def prepare(root: Path, inspection: dict):
    if not inspection['State']['Running']:
        raise ValueError('应用容器未运行')
    environment = dict(item.split('=', 1) for item in inspection['Config']['Env'])
    if not environment.get('DATABASE_URL'):
        raise ValueError('应用缺少数据库连接')
    # 本地任务只写 systemd 日志和回执，不继承应用中的通知渠道。
    environment = {key: value for key, value in environment.items() if not key.startswith(('BACKUP_', 'RESTORE_', 'RESTIC_', 'AWS_'))}
    if any('\n' in value or '\r' in value for value in environment.values()):
        raise ValueError('Docker 环境文件不支持多行变量，请使用挂载的密钥文件')
    root.mkdir(parents=True, exist_ok=True)
    for name in ('repository', 'status'):
        target = root / name
        target.mkdir(exist_ok=True)
        target.chmod(0o700)
        os.chown(target, 10001, 10001)
    password = root / 'restic-password'
    if not password.exists():
        if (root / 'repository/config').exists():
            raise ValueError('已有仓库缺少密码文件，请恢复原密码，不能生成新密码')
        with os.fdopen(os.open(password, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
            stream.write(secrets.token_urlsafe(64) + '\n')
    if not password.is_file() or not password.stat().st_size:
        raise ValueError('已有备份密码文件无效，不能覆盖')
    password.chmod(0o400)
    os.chown(password, 10001, 10001)
    target = root / 'runtime.env'
    temporary = root / 'runtime.env.tmp'
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8') as stream:
        stream.write(''.join(f'{key}={value}\n' for key, value in sorted(environment.items())))
    temporary.chmod(0o400)
    os.chown(temporary, 10001, 10001)
    temporary.replace(target)


if __name__ == '__main__':
    prepare(Path('/state'), json.load(sys.stdin)[0])
