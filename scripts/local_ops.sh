#!/bin/sh
# 本地 systemd 备份入口：只读取业务容器，只删除本次创建的恢复容器。
set -eu
umask 077
: "${OPS_IMAGE:?}" "${OPS_STATE_ROOT:?}" "${OPS_DEPLOY_ROOT:?}" "${OPS_APP:?}" "${OPS_NETWORK:?}" "${OPS_VOLUME:?}" "${OPS_RESTORE_IMAGE:?}"
action=${1:?}
case "$action" in backup|restore-check) ;; *) exit 2 ;; esac
exec 9>/run/lock/learn-coach-local-ops.lock
flock -n 9 || { echo '另一项备份或恢复正在执行。'; exit 1; }
if [ "$action" = backup ] && [ -n "${OPS_OPERATION_STATUS:-}" ]; then
  python3 /usr/local/lib/learn-coach/ops_state.py "$OPS_OPERATION_STATUS" running source_backup
  trap 'result=$?; if [ "$result" -ne 0 ]; then python3 /usr/local/lib/learn-coach/ops_state.py "$OPS_OPERATION_STATUS" failed source_backup; fi' EXIT
  trap 'exit 1' HUP INT TERM
fi
docker inspect "$OPS_APP" | docker run --rm --pull never --network none --user 0 --read-only --cap-drop ALL --cap-add CHOWN --cap-add FOWNER --cap-add DAC_OVERRIDE --security-opt no-new-privileges -i \
  -v "$OPS_STATE_ROOT:/state" --entrypoint python "$OPS_IMAGE" scripts/local_backup_config.py

if [ "$action" = backup ] && [ "${OPS_BACKUP_IMAGES:-false}" = true ]; then
  python3 /usr/local/lib/learn-coach/recovery_images.py
fi

run_backup() {
  set -- "$1"
  if [ "${OPS_BACKUP_IMAGES:-false}" = true ]; then
    set -- "$1" -e BACKUP_IMAGES_ROOT=/run/images -v "$OPS_STATE_ROOT/images:/run/images:ro"
  fi
  backup_action=$1
  shift
  docker run --rm --pull never --network "$OPS_NETWORK" --read-only --cap-drop ALL --security-opt no-new-privileges --memory "${OPS_BACKUP_MEMORY:-2g}" --pids-limit 256 \
    --tmpfs "/tmp:size=${OPS_BACKUP_TMPFS_SIZE:-1g},mode=1777" --env-file "$OPS_STATE_ROOT/runtime.env" \
    -e RESTIC_REPOSITORY=/repository -e RESTIC_PASSWORD_FILE=/run/secrets/restic-password -e RESTIC_CACHE_DIR=/tmp/restic-cache \
    -e ARCHIVE_LOCAL_DIR=/app/data/paper-files -e BACKUP_CONFIG_ROOT=/run/deployment -e BACKUP_STATUS_FILE=/run/ops-status/backup.json \
    -v "$OPS_VOLUME:/app/data:ro" -v "$OPS_STATE_ROOT/repository:/repository" -v "$OPS_STATE_ROOT/status:/run/ops-status" \
    -v "$OPS_STATE_ROOT/restic-password:/run/secrets/restic-password:ro" -v "$OPS_STATE_ROOT/runtime.env:/run/secrets/service.env:ro" \
    -v "$OPS_DEPLOY_ROOT:/run/deployment:ro" "$@" "$OPS_IMAGE" "$backup_action"
}

if [ "$action" = backup ]; then
  if [ ! -f "$OPS_STATE_ROOT/repository/config" ]; then run_backup init; fi
  run_backup backup
  if [ -n "${OPS_OPERATION_STATUS:-}" ]; then
    python3 /usr/local/lib/learn-coach/ops_state.py "$OPS_OPERATION_STATUS" succeeded source_backup
  fi
else
  [ -f "$OPS_STATE_ROOT/repository/config" ] || { echo '请先成功执行一次备份。'; exit 1; }
  restore_name="lc-local-restore-$$"
  created=0
  cleanup() { if [ "$created" = 1 ]; then docker rm -f "$restore_name" >/dev/null; fi; }
  trap cleanup EXIT
  trap 'exit 1' HUP INT TERM
  docker run -d --pull never --name "$restore_name" --network none --memory 3g --pids-limit 256 --shm-size 256m \
    --tmpfs /var/lib/postgresql/data:size=2g -e POSTGRES_USER=restore -e POSTGRES_PASSWORD=isolated-restore-only -e POSTGRES_DB=lc_restore_probe \
    --health-cmd='pg_isready -U restore -d lc_restore_probe' --health-interval=2s --health-retries=30 "$OPS_RESTORE_IMAGE" >/dev/null
  created=1
  attempt=0
  while [ "$(docker inspect -f '{{.State.Health.Status}}' "$restore_name")" != healthy ]; do
    attempt=$((attempt + 1)); [ "$attempt" -lt 30 ] || { echo '独立恢复数据库未就绪。'; exit 1; }
    sleep 2
  done
  docker run --rm --pull never --network "container:$restore_name" --read-only --cap-drop ALL --security-opt no-new-privileges --memory 2g --pids-limit 256 \
    --tmpfs /tmp:size=2g,mode=1777 -e RESTIC_REPOSITORY=/repository -e RESTIC_PASSWORD_FILE=/run/secrets/restic-password -e RESTIC_CACHE_DIR=/tmp/restic-cache -e RESTIC_READ_ONLY=true \
    -e LC_RESTORE_DATABASE_URL=postgresql://restore:isolated-restore-only@127.0.0.1:5432/lc_restore_probe -e RESTORE_STATUS_FILE=/run/ops-status/restore.json \
    -v "$OPS_STATE_ROOT/repository:/repository:ro" -v "$OPS_STATE_ROOT/status:/run/ops-status" \
    -v "$OPS_STATE_ROOT/restic-password:/run/secrets/restic-password:ro" "$OPS_IMAGE" restore-check
fi
