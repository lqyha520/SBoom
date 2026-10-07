"""Docker 运维入口：加密异地备份、保留策略、隔离恢复验证。见 docs/deploy.md。"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request, urlopen

import backup_restore


def run(*args):
    result = subprocess.run(args, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} 执行失败（退出码 {result.returncode}）；请检查仓库访问、容量和凭据")
    return result.stdout


def notify(success, action="backup"):
    heartbeat = os.environ.get('RESTORE_HEARTBEAT_URL' if action == 'restore-check' else 'BACKUP_HEARTBEAT_URL', '')
    alert = os.environ.get('BACKUP_ALERT_WEBHOOK', '')
    feishu = os.environ.get('BACKUP_FEISHU_WEBHOOK', '')
    failed = False
    if heartbeat:
        try:
            with urlopen(heartbeat if success else heartbeat.rstrip('/') + '/fail', timeout=15) as response:
                response.read()
        except Exception:
            failed = True
    if not success:
        label = '恢复演练' if action == 'restore-check' else '备份'
        message = f'learn-coach {label}失败，请检查服务器运维日志。'
        # 两个渠道独立尝试，任一渠道失败也不阻止另一个渠道通知。
        channels = []
        if alert:
            channels.append((alert, {'msgtype': 'text', 'text': {'content': message}}, 'errcode'))
        if feishu:
            payload = {'msg_type': 'text', 'content': {'text': message}}
            secret = os.environ.get('BACKUP_FEISHU_SECRET', '')
            if secret:
                timestamp = str(int(time.time()))
                # 飞书机器人签名：timestamp + 换行 + secret 作 HMAC 密钥，消息为空。
                signature = base64.b64encode(hmac.new(f'{timestamp}\n{secret}'.encode(), b'', hashlib.sha256).digest()).decode()
                payload.update(timestamp=timestamp, sign=signature)
            channels.append((feishu, payload, 'code'))
        for webhook, payload, code_key in channels:
            try:
                body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                with urlopen(Request(webhook, data=body, headers={'Content-Type': 'application/json'}), timeout=15) as response:
                    result = json.loads(response.read())
                    # 兼容飞书旧版成功回包；缺失状态码不视为成功。
                    code = result.get(code_key, result.get('StatusCode') if code_key == 'code' else None)
                    if code != 0:
                        raise RuntimeError('告警渠道拒绝消息')
            except Exception:
                failed = True
    if failed:
        raise RuntimeError('告警发送失败')


def execute(action):
    if action == 'init':
        run('restic', 'init')
        return
    # 明文只出现在容器 tmpfs 内，不落持久卷；restic 上传前自动加密。
    with tempfile.TemporaryDirectory(prefix='lc-backup-') as folder:
        root = Path(folder)
        if action == 'backup':
            bundle = root / 'bundle'
            backup_restore.backup(SimpleNamespace(destination=bundle,
                files_root=Path(os.environ.get('ARCHIVE_LOCAL_DIR', '/app/data/paper-files')),
                env_file=Path('/run/secrets/service.env'),
                secret_file=Path('/app/data/secret_key.txt') if Path('/app/data/secret_key.txt').is_file() else None,
                extra_files_root=Path('/app/data/wechat'),
                pg_container=None))
            run('restic', 'backup', '--host', 'learn-coach', '--tag', 'learn-coach', str(bundle))
            run('restic', 'forget', '--host', 'learn-coach', '--tag', 'learn-coach', '--group-by', 'host,tags',
                '--keep-daily', '7', '--keep-weekly', '4', '--keep-monthly', '6', '--prune')
            run('restic', 'check')
            status_file = os.environ.get('BACKUP_STATUS_FILE')
            if status_file:
                target = Path(status_file)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix('.tmp')
                repository = os.environ.get('RESTIC_REPOSITORY', '')
                remote = repository.startswith(('s3:', 'b2:', 'azure:', 'gs:', 'rclone:', 'rest:https://', 'sftp:'))
                temporary.write_text(json.dumps({'completed_at': int(time.time()), 'verified': True, 'offsite': remote}), encoding='utf-8')
                # The setgid receipt directory assigns the dedicated monitoring
                # group; no credentials are included in this status document.
                temporary.chmod(0o640)
                temporary.replace(target)
        else:
            # 只能在独立 restore-db 容器里运行；backup_restore 二次验证 localhost 和库名前缀。
            run('restic', 'restore', 'latest', '--host', 'learn-coach', '--tag', 'learn-coach', '--target', str(root / 'download'))
            bundles = list((root / 'download').rglob('manifest.json'))
            if len(bundles) != 1:
                raise RuntimeError('恢复快照必须恰好包含一个备份清单')
            backup_restore.restore(SimpleNamespace(source=bundles[0].parent, destination=root / 'verified', pg_container=None))
            import psycopg
            with psycopg.connect(os.environ['LC_RESTORE_DATABASE_URL']) as conn:
                conn.execute('SELECT COUNT(*) FROM users').fetchone()
                conn.execute('SELECT COUNT(*) FROM site_banners').fetchone()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'backup', 'restore-check'])
    args = parser.parse_args()
    for required in ('RESTIC_REPOSITORY', 'RESTIC_PASSWORD_FILE'):
        if not os.environ.get(required):
            parser.error(required + ' 未配置')
    try:
        execute(args.action)
        if args.action != 'init':
            notify(True, args.action)
    except Exception as exc:
        try:
            notify(False, args.action)
        finally:
            # 不打印 restic stderr 或 DSN，避免把存储访问密钥写进日志。
            raise SystemExit(f'{args.action} 失败：{type(exc).__name__}，请检查配置和服务状态') from None
    print(args.action + ' 完成：异地备份/隔离恢复检查通过')


if __name__ == '__main__':
    main()
