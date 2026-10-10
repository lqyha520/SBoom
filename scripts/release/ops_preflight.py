"""Read-only configuration checks; never print credentials or contact storage."""

import ipaddress
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def configured(value):
    return isinstance(value, str) and bool(value.strip()) and not any(
        marker in value.upper() for marker in ('REPLACE', 'ACCOUNT_ID', 'YOUR_', ':RELEASE')
    )


def https_endpoint(value):
    if not configured(value):
        return False
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            return False
        if parsed.hostname == 'localhost' or parsed.hostname.endswith(('.invalid', '.example')):
            return False
        try:
            return ipaddress.ip_address(parsed.hostname).is_global
        except ValueError:
            return True
    except ValueError:
        return False


def mount(service, target):
    return next((item for item in service.get('volumes', []) if item.get('target') == target), {})


def secret_file(service, target):
    item = mount(service, target)
    if item.get('type') != 'bind' or item.get('read_only') is not True:
        return False
    path = Path(item.get('source', ''))
    try:
        stat = path.stat()
        if not path.is_absolute() or not path.is_file() or stat.st_size == 0:
            return False
        if os.name != 'posix':
            return False  # Container uid/gid permissions must be checked on its Linux host.
        groups = {10001, *(int(group) for group in service.get('group_add', []))}
        readable = stat.st_mode & 0o400 if stat.st_uid == 10001 else stat.st_gid in groups and stat.st_mode & 0o040
        return bool(readable and not stat.st_mode & 0o027)
    except (OSError, ValueError, TypeError):
        return False


def receipt_directory(service):
    item = mount(service, '/run/ops-status')
    if item.get('type') != 'bind' or item.get('read_only'):
        return False
    path = Path(item.get('source', ''))
    try:
        stat = path.stat()
        groups = {int(group) for group in service.get('group_add', [])}
        return (os.name == 'posix' and path.is_absolute() and path.is_dir()
                and stat.st_uid == 10001 and stat.st_gid in groups and stat.st_gid != 10001
                and stat.st_mode & 0o7777 == 0o2750)
    except (OSError, ValueError, TypeError):
        return False


def check_configuration(command):
    checks: dict[str, bool] = {}
    report: dict[str, Any] = {'ok': False, 'scope': 'configuration_only', 'checks': checks}
    try:
        result = subprocess.run([*command, '--profile', 'ops', '--profile', 'restore',
                                 'config', '--format', 'json'],
                                check=True, capture_output=True, text=True)
        config = json.loads(result.stdout)
        backup = config['services']['backup']
        restore = config['services']['restore-check']
        database = config['services']['restore-db']
        env = {key: value if isinstance(value, str) else '' for key, value in backup.get('environment', {}).items()}
        restore_env = {key: value if isinstance(value, str) else '' for key, value in restore.get('environment', {}).items()}
        if not isinstance(database, dict):
            raise TypeError('Invalid restore service')
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError, AttributeError):
        checks['compose'] = False
        return report
    checks['compose'] = True
    repository = env.get('RESTIC_REPOSITORY', '')
    checks['offsite_repository'] = configured(repository) and repository.startswith(
        ('s3:', 'b2:', 'azure:', 'gs:', 'rclone:', 'rest:https://', 'sftp:'))
    if repository.startswith('s3:'):
        checks['s3_https'] = https_endpoint(repository[3:])
        for name, settings in (('backup', env), ('restore', restore_env)):
            checks[name + '_s3_credentials'] = all(configured(settings.get(key)) for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'))
    checks['matching_repository'] = bool(repository) and repository == restore_env.get('RESTIC_REPOSITORY')
    checks['ops_image'] = (configured(backup.get('image')) and backup['image'] != 'learncoach-ops:local'
                           and backup['image'] == restore.get('image'))
    checks['database'] = configured(env.get('DATABASE_URL')) and env['DATABASE_URL'].startswith(('postgresql://', 'postgres://'))
    for name, service in (('backup', backup), ('restore', restore)):
        checks[name + '_password_file'] = (service.get('environment', {}).get('RESTIC_PASSWORD_FILE') == '/run/secrets/restic-password'
                                          and secret_file(service, '/run/secrets/restic-password'))
    checks['matching_password_file'] = (mount(backup, '/run/secrets/restic-password').get('source')
                                        == mount(restore, '/run/secrets/restic-password').get('source'))
    checks['service_env_file'] = secret_file(backup, '/run/secrets/service.env')
    checks['receipt_directory'] = receipt_directory(backup)
    checks['receipt_path'] = env.get('BACKUP_STATUS_FILE') == '/run/ops-status/backup.json'
    checks['readonly_appdata'] = mount(backup, '/app/data').get('read_only') is True
    heartbeat, restore_heartbeat = env.get('BACKUP_HEARTBEAT_URL', ''), restore_env.get('RESTORE_HEARTBEAT_URL', '')
    checks['backup_heartbeat'] = https_endpoint(heartbeat)
    checks['restore_heartbeat'] = https_endpoint(restore_heartbeat)
    checks['distinct_heartbeats'] = bool(heartbeat) and heartbeat.rstrip('/') != restore_heartbeat.rstrip('/')
    for name, settings in (('backup', env), ('restore', restore_env)):
        checks[name + '_alert_channel'] = any(https_endpoint(settings.get(key, ''))
                                              for key in ('BACKUP_ALERT_WEBHOOK', 'BACKUP_FEISHU_WEBHOOK'))
        checks[name + '_feishu_signing'] = not settings.get('BACKUP_FEISHU_SECRET') or https_endpoint(settings.get('BACKUP_FEISHU_WEBHOOK', ''))
    try:
        target = urlsplit(restore_env.get('LC_RESTORE_DATABASE_URL', ''))
        checks['isolated_restore'] = (restore.get('network_mode') == 'service:restore-db'
                                     and target.scheme in ('postgresql', 'postgres')
                                     and target.hostname in ('127.0.0.1', 'localhost', '::1')
                                     and target.path.startswith('/lc_restore_')
                                     and any(item.split(':', 1)[0] == '/var/lib/postgresql/data' for item in database.get('tmpfs', []))
                                     and not database.get('volumes')
                                     and not database.get('ports'))
    except ValueError:
        checks['isolated_restore'] = False
    report['ok'] = all(checks.values())
    return report
