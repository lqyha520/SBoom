"""Linux-only role test. Run as root in a disposable, network-disabled container."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != "linux" or os.geteuid() != 0:
        raise SystemExit("Requires root inside a disposable Linux container")
    with tempfile.TemporaryDirectory(prefix="lc-receipt-roles-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        status = root / "status"
        status.mkdir()
        os.chown(status, 10001, 10002)
        status.chmod(0o2750)
        receipt = status / "backup.json"
        writer = """
import sys, types
sys.path.insert(0, sys.argv[1])
sys.modules['backup_restore'] = types.SimpleNamespace(backup=lambda _: None)
import ops_backup
ops_backup.run = lambda *args: b''
ops_backup.time.time = lambda: int(sys.argv[2])
ops_backup.execute('backup')
"""
        reader = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import ops_check
target = Path(sys.argv[2])
assert ops_check.backup_age(target, 200, 1)['ok']
assert not ops_check.backup_age(target, 8000, 1)['ok']
try:
    ops_check.backup_age(target.with_name('missing.json'), 200, 1)
except FileNotFoundError:
    pass
else:
    raise AssertionError('Missing receipt accepted')
"""
        env = {**os.environ, "BACKUP_STATUS_FILE": str(receipt), "RESTIC_REPOSITORY": "s3:fixture/only"}
        for timestamp in (100, 200):
            subprocess.run([sys.executable, "-c", writer, str(ROOT / "scripts"), str(timestamp)],
                           user=10001, group=10001, extra_groups=[10002], env=env, check=True)
            stat = receipt.stat()
            assert (stat.st_uid, stat.st_gid, stat.st_mode & 0o777) == (10001, 10002, 0o640)
            subprocess.run([sys.executable, "-c", reader, str(ROOT / "scripts"), str(receipt)],
                           user=10003, group=10002, extra_groups=[], check=True)
        outsider = subprocess.run([sys.executable, "-c", "from pathlib import Path; import sys; Path(sys.argv[1]).read_text()", str(receipt)],
                                  user=10004, group=10004, extra_groups=[], capture_output=True)
        assert outsider.returncode != 0
        print(json.dumps({"replacement_rounds": 2, "owner": 10001, "group": 10002, "mode": "0640",
                          "monitor_read": True, "outsider_denied": True, "stale_and_missing_rejected": True}))


if __name__ == "__main__":
    main()
