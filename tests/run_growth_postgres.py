"""Own one ephemeral PostgreSQL container, run contracts, then remove that container."""

import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    docker = ['wsl', '-d', 'Debian', '--exec', 'docker'] if os.name == 'nt' else ['docker']
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    name = 'lc_verify_growth_' + uuid.uuid4().hex[:10]
    password = uuid.uuid4().hex
    container = None
    try:
        container = subprocess.check_output([*docker, 'run', '--rm', '-d', '--name', name, '-p', f'127.0.0.1:{port}:5432', '-e', 'POSTGRES_DB=lc_verify_growth', '-e', 'POSTGRES_USER=lc_fixture', '-e', 'POSTGRES_PASSWORD=' + password, 'postgres:16-alpine'], text=True).strip()
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            probe = subprocess.run([*docker, 'exec', container, 'pg_isready', '-U', 'lc_fixture', '-d', 'lc_verify_growth'], capture_output=True)
            if probe.returncode == 0:
                break
            time.sleep(0.3)
        else:
            raise TimeoutError('Disposable PostgreSQL did not become ready')
        env = {**os.environ, 'LC_TEST_PG_DSN': f'postgresql://lc_fixture:{password}@127.0.0.1:{port}/lc_verify_growth', 'PYTHONIOENCODING': 'utf-8'}
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'postgres_experience.py', '-v'], cwd=ROOT, env=env)
        return result.returncode
    finally:
        if container:
            subprocess.run([*docker, 'rm', '-f', container], check=True, capture_output=True)
            print('Disposable PostgreSQL removed; existing containers were not changed.', flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
