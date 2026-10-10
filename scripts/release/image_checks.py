"""Offline checks shared by image preparation and deployment."""

import subprocess

SMOKE_CHECK = """
import os
from pathlib import Path
import app.main

assert os.getuid() == 10001, 'Application must run as uid 10001'
assert Path('run.py').read_bytes(), 'Missing application entrypoint'
for root in (Path('app'), Path('web/dist'), Path('admin/dist')):
    list(root.iterdir())
    for path in root.rglob('*'):
        if path.is_dir():
            list(path.iterdir())
        elif path.is_file():
            with path.open('rb') as stream:
                stream.read(1)
for root in (Path('web/dist'), Path('admin/dist')):
    assert root.joinpath('index.html').read_bytes(), 'Missing frontend HTML'
    assert any(root.joinpath('assets').glob('*.js')), 'Missing frontend assets'
"""


def verify_image(image):
    subprocess.run([
        'docker', 'run', '--rm', '--pull', 'never', '--network', 'none',
        '--read-only', '--tmpfs', '/tmp', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--entrypoint', 'python',
        image, '-c', SMOKE_CHECK,
    ], check=True, capture_output=True, text=True)
