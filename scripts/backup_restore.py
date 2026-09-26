"""Consistent PostgreSQL + private files + encryption configuration backup.
Restore is restricted to an EMPTY local lc_restore_* / lc_test_* database and a
new file directory. DATABASE_URL selects backup; LC_RESTORE_DATABASE_URL restore.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.storage_registry import REFERENCES

LOCKS = [70634195, 70634191, 70634192, 70634193, 70634194]

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def safe(root, key):
    path = (root / key).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError('Path escapes backup root')
    return path

def pg_tool(args, dsn, program, file, snapshot=None):
    config = {key: str(value) for key, value in conninfo_to_dict(dsn).items() if value is not None}
    env = dict(os.environ)
    for key, variable in [('host','PGHOST'),('port','PGPORT'),('user','PGUSER'),('password','PGPASSWORD'),('dbname','PGDATABASE')]:
        env[variable] = config.get(key, '')
    if args.pg_container:
        env['PGHOST'], env['PGPORT'] = '127.0.0.1', '5432'
        command = ['docker', 'exec', '-i']
        if sys.platform == 'win32' and not shutil.which('docker'):
            command = ['wsl', '--exec', 'docker', 'exec', '-i']
            env['WSLENV'] = env.get('WSLENV', '') + ':PGHOST:PGPORT:PGUSER:PGPASSWORD:PGDATABASE'
        for variable in ('PGHOST','PGPORT','PGUSER','PGPASSWORD','PGDATABASE'):
            command += ['-e', variable]
        command += [args.pg_container, program]
    else:
        command = [program]
    if program == 'pg_dump':
        command += ['--format=custom', '--no-owner', '--no-privileges', '--snapshot=' + snapshot]
        with file.open('xb') as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE, env=env)
    else:
        command += ['--exit-on-error', '--no-owner', '--no-privileges', '--dbname=' + config['dbname']]
        with file.open('rb') as source:
            result = subprocess.run(command, stdin=source, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
    if result.returncode:
        # Never print command arguments or environment: these may contain credentials.
        raise RuntimeError(program + ' failed; backup/restore remains incomplete')

def private_files(conn):
    """备份要复制的私有文件：与孤儿回收共用 app/storage_registry.py 的登记表，漏登记的表不会进备份。"""
    selects = []
    for ref in REFERENCES:
        exists = conn.execute('SELECT to_regclass(%s)', (ref.table,)).fetchone()
        if exists and exists[0]:
            # 空后端名等同本地磁盘（Banner 的 image_storage 默认为空串）；没有文件的行不进清单
            selects.append(f"SELECT CASE WHEN {ref.storage_column} = '' THEN 'local' ELSE {ref.storage_column} END, {ref.key_column} "
                           f"FROM {ref.table} WHERE {ref.key_column} <> ''")
    return conn.execute(' UNION '.join(selects)).fetchall() if selects else []

def backup(args):
    root = args.destination.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    files_root = args.files_root.resolve()
    dsn = os.environ['DATABASE_URL']
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        # Session locks first, then take the snapshot. Waiting must not make a
        # repeatable-read snapshot older than the protected filesystem manifest.
        conn.execute("SET statement_timeout = '120s'")
        for key in LOCKS:
            conn.execute('SELECT pg_advisory_lock(%s)', (key,))
        conn.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        snapshot_row = conn.execute('SELECT pg_export_snapshot()').fetchone()
        if snapshot_row is None:
            raise RuntimeError('Database snapshot was not returned')
        snapshot = snapshot_row[0]
        pg_tool(args, dsn, 'pg_dump', root / 'database.dump', snapshot)
        records = private_files(conn)
        for backend, key in records:
            if backend != 'local':
                raise ValueError('Unsupported storage backend')
            source = safe(files_root, key)
            target = safe(root / 'files', key)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        shutil.copyfile(args.env_file, root / 'service.env')
        if args.secret_file:
            shutil.copyfile(args.secret_file, root / 'secret_key.txt')
        manifest = {str(path.relative_to(root)).replace('\\','/'): digest(path) for path in root.rglob('*') if path.is_file()}
        (root / 'manifest.json').write_text(json.dumps({'version': 1, 'created_at': int(time.time()), 'sha256': manifest}, indent=2), encoding='utf-8')
        for path in root.rglob('*'):
            if path.is_file():
                path.chmod(0o600)
        print('Backup complete:', len(records), 'private files; verified manifest written')
    finally:
        conn.close()  # rollback snapshot and release all session locks

def restore(args):
    dsn = os.environ['LC_RESTORE_DATABASE_URL']
    config = {key: str(value) for key, value in conninfo_to_dict(dsn).items() if value is not None}
    if config.get('host') not in ('127.0.0.1','localhost') or not config.get('dbname','').startswith(('lc_restore_','lc_test_')):
        raise ValueError('Restore requires a local disposable lc_restore_* / lc_test_* database')
    manifest = json.loads((args.source / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version') != 1 or not {'database.dump', 'service.env'}.issubset(manifest.get('sha256', {})):
        raise ValueError('Unknown backup version')
    for key, expected in manifest['sha256'].items():
        if digest(safe(args.source, key)) != expected:
            raise ValueError('Backup checksum mismatch: ' + key)
    with psycopg.connect(dsn) as conn:
        tables_row = conn.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')").fetchone()
        if tables_row is None:
            raise RuntimeError('Unable to inspect restore target')
        tables = tables_row[0]
        if tables:
            raise ValueError('Restore target must be empty')
    args.destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    pg_tool(args, dsn, 'pg_restore', args.source / 'database.dump')
    shutil.copytree(args.source / 'files', args.destination / 'files') if (args.source / 'files').exists() else (args.destination / 'files').mkdir()
    shutil.copyfile(args.source / 'service.env', args.destination / 'service.env')
    if (args.source / 'secret_key.txt').exists():
        shutil.copyfile(args.source / 'secret_key.txt', args.destination / 'secret_key.txt')
    for path in args.destination.rglob('*'):
        if path.is_file():
            path.chmod(0o600)
    print('Restore complete. Use the isolated database and files directory for verification; do not load service.env against production.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pg-container', help='Run PostgreSQL tools in this local Docker container (same PostgreSQL instance)')
    sub = parser.add_subparsers(dest='action', required=True)
    b = sub.add_parser('backup')
    b.add_argument('--destination', type=Path, required=True)
    b.add_argument('--files-root', type=Path, required=True)
    b.add_argument('--env-file', type=Path, required=True)
    b.add_argument('--secret-file', type=Path)
    r = sub.add_parser('restore')
    r.add_argument('--source', type=Path, required=True)
    r.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    backup(args) if args.action == 'backup' else restore(args)

if __name__ == '__main__':
    main()
