#!/bin/sh
# WSL 每日拉取生产密文；私钥被服务端强制命令限制，不能打开远程 shell。
set -eu
umask 077
: "${OFFSITE_ROOT:?}" "${OFFSITE_HOST:?}" "${OFFSITE_IMAGE:?}"
exec 9>/run/lock/learn-coach-offsite.lock
flock -n 9 || exit 1
remote() { ssh -p "${OFFSITE_PORT:-22}" -i "$OFFSITE_ROOT/ssh-key" -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$OFFSITE_ROOT/known_hosts" "$OFFSITE_HOST" "$@"; }
remote backup
remote status > "$OFFSITE_ROOT/source-status.json"
export RSYNC_RSH="ssh -p ${OFFSITE_PORT:-22} -i $OFFSITE_ROOT/ssh-key -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$OFFSITE_ROOT/known_hosts"
rsync -a --delete-delay "$OFFSITE_HOST:/data/data1/learn-coach-ops/repository/" "$OFFSITE_ROOT/repository/"
docker run --rm --pull never --network none --read-only --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:size=256m -e RESTIC_REPOSITORY=/repository -e RESTIC_PASSWORD_FILE=/password -e RESTIC_CACHE_DIR=/tmp \
  -v "$OFFSITE_ROOT/repository:/repository:ro" -v "$OFFSITE_ROOT/restic-password:/password:ro" --entrypoint restic "$OFFSITE_IMAGE" --no-lock check
docker run --rm --pull never --network none --read-only --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:size=256m -e RESTIC_REPOSITORY=/repository -e RESTIC_PASSWORD_FILE=/password -e RESTIC_CACHE_DIR=/tmp \
  -v "$OFFSITE_ROOT/repository:/repository:ro" -v "$OFFSITE_ROOT/restic-password:/password:ro" --entrypoint restic "$OFFSITE_IMAGE" --no-lock snapshots --json latest > "$OFFSITE_ROOT/snapshots.json"
python3 - "$OFFSITE_ROOT" <<'PY'
import json, sys, time
from pathlib import Path
root = Path(sys.argv[1])
source = json.loads((root / 'source-status.json').read_text())
snapshots = json.loads((root / 'snapshots.json').read_text())
assert len(snapshots) == 1 and snapshots[0]['id'] == source['snapshot_id']
receipt = {'verified': True, 'offsite': True, 'snapshot_id': source['snapshot_id'], 'completed_at': int(time.time())}
(root / 'status/backup.json').write_text(json.dumps(receipt))
PY
remote receipt < "$OFFSITE_ROOT/status/backup.json"
echo '生产异地加密备份与完整性检查完成。'
