"""本地备份配置与恢复验证的故障回归，不读取真实凭据。"""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts import backup_restore, local_backup_config


class LocalBackupContracts(unittest.TestCase):
    def inspection(self, **environment):
        values = {'DATABASE_URL': 'postgresql://fixture:fixture@db/fixture', 'SECRET_KEY': 'fixture-only', **environment}
        return {'State': {'Running': True}, 'Config': {'Env': [f'{key}={value}' for key, value in values.items()]}}

    def test_reinstall_preserves_password_and_does_not_inherit_notifications(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(os, 'chown', create=True), patch.object(Path, 'chmod'):
            root = Path(folder)
            local_backup_config.prepare(root, self.inspection(BACKUP_ALERT_WEBHOOK='https://fixture.invalid'))
            original = (root / 'restic-password').read_bytes()
            local_backup_config.prepare(root, self.inspection())
            self.assertEqual((root / 'restic-password').read_bytes(), original)
            self.assertNotIn('BACKUP_ALERT_WEBHOOK', (root / 'runtime.env').read_text())
            self.assertTrue((root / 'repository').is_dir())
            self.assertTrue((root / 'status').is_dir())

    def test_missing_password_for_existing_repository_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(os, 'chown', create=True):
            root = Path(folder)
            (root / 'repository').mkdir()
            (root / 'repository/config').write_text('existing-repository')
            with self.assertRaisesRegex(ValueError, '不能生成新密码'):
                local_backup_config.prepare(root, self.inspection())
            self.assertFalse((root / 'restic-password').exists())

    def test_multiline_configuration_fails_before_writing_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, '多行变量'):
                local_backup_config.prepare(root, self.inspection(SECRET_KEY='first\nsecond'))
            self.assertFalse((root / 'runtime.env').exists())
            self.assertFalse((root / 'restic-password').exists())

    def test_restore_row_count_mismatch_prevents_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            source.mkdir()
            for name, content in {'database.dump': b'fixture-dump', 'service.env': b'fixture=true', 'database_counts.json': b'{"users":2}'}.items():
                (source / name).write_bytes(content)
            manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source.iterdir()}
            (source / 'manifest.json').write_text(json.dumps({'version': 1, 'sha256': manifest}))
            connection = MagicMock()
            connection.__enter__.return_value.execute.return_value.fetchone.return_value = (0,)
            with patch.dict(os.environ, {'LC_RESTORE_DATABASE_URL': 'postgresql://fixture:fixture@127.0.0.1:55432/lc_test_restore'}), \
                    patch.object(backup_restore.psycopg, 'connect', return_value=connection), \
                    patch.object(backup_restore, 'pg_tool'), patch.object(backup_restore, 'database_counts', return_value={'users': 1}):
                with self.assertRaisesRegex(ValueError, 'row counts'):
                    backup_restore.restore(SimpleNamespace(source=source, destination=root / 'restored', pg_container=None))
            self.assertFalse((root / 'restored/service.env').exists())
