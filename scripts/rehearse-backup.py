"""Create, back up and restore ONLY disposable local test databases."""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / 'tests')]
from unittest.mock import patch

import pg_support

source_dsn, source_name = pg_support.create_test_db()
target_dsn, target_name = pg_support.create_test_db()
os.environ['DATABASE_URL'] = source_dsn
os.environ['SECRET_KEY'] = 'backup-rehearsal-only-not-a-real-secret'
from test_backend_library import bundle, snapshot

from app.config import get_settings
from app.db import close_pg_pool, db, init_db
from app.models.library import ArchiveCreate
from app.security import decrypt_secret, encrypt_secret
from app.services import paper_library, user_store

spec = importlib.util.spec_from_file_location('backup_restore', Path(__file__).with_name('backup_restore.py'))
if spec is None or spec.loader is None:
    raise RuntimeError('Cannot load the backup helper')
backup_restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_restore)
try:
    with tempfile.TemporaryDirectory(prefix='lc-backup-rehearsal-') as folder:
        root = Path(folder)
        with patch.object(get_settings(), 'archive_local_dir', str(root / 'source-files')):
            init_db()
            user = user_store.create_user('backup-fixture', 'disposable-password')
            paper = paper_library.create_paper(user.id, ArchiveCreate(request_id='backup-one', source_id='backup-one', snapshot=snapshot()))
            paper_library.publish_bundle(user.id, paper['id'], bundle())
            cipher = encrypt_secret('rehearsal-provider-secret')
            with db() as conn:
                conn.execute("INSERT INTO app_config(key,value) VALUES ('rehearsal_cipher',?)", (cipher,))
            (root / 'fixture.env').write_text('SECRET_KEY=' + os.environ['SECRET_KEY'], encoding='utf-8')
            args = SimpleNamespace(destination=root / 'backup', files_root=root / 'source-files', env_file=root / 'fixture.env', secret_file=None, pg_container='learncoach-db')
            backup_restore.backup(args)
            close_pg_pool()
            os.environ['LC_RESTORE_DATABASE_URL'] = target_dsn
            backup_restore.restore(SimpleNamespace(source=root / 'backup', destination=root / 'restored', pg_container='learncoach-db'))
            get_settings().database_url = target_dsn
            get_settings().archive_local_dir = str(root / 'restored' / 'files')
            from app.library_files import asset_response
            restored = paper_library.get_paper(user.id, paper['id'])
            assert len(restored['assets']) == 2
            for asset in restored['assets']:
                response = asset_response(paper_library.owned_asset(user.id, asset['id']))
                assert Path(response.path).is_file()
            with db() as conn:
                recovered = conn.execute("SELECT value FROM app_config WHERE key = 'rehearsal_cipher'").fetchone()[0]
            assert decrypt_secret(recovered) == 'rehearsal-provider-secret'
            print(json.dumps({'restored_files': len(restored['assets']) + 1, 'decryption': 'passed', 'download_paths': 'passed'}))
finally:
    close_pg_pool()
    pg_support.drop_test_db(source_name)
    pg_support.drop_test_db(target_name)
