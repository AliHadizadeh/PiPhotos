#!/bin/bash
# initial_copy.sh - first full copy of the Immich data onto the backup drive. rsync, so a rerun resumes.
# Copies the folders listed in SYNC_DIRS from IMMICH_DATA to the backup mount (backup.conf).
# Leaves the drive mounted and powered at the end (the weekly job, once installed, handles unmount and power).
set -u
export PATH=$PATH:/usr/sbin:/sbin
CONF=${IMMICH_TOOLS_CONF:-/etc/immich-tools/backup.conf}; . "$CONF"
D=${TOOLS_DIR:-/opt/immich-tools/backup}; STATE_ROOT=${STATE_ROOT:-/var/lib/immich-tools}; LOGD=$STATE_ROOT/logs; mkdir -p "$LOGD"
PY=$D/venv/bin/python; SRC=${IMMICH_DATA:-/mnt/immich}
BYID=$BACKUP_DISK_BYID
MNT=${BACKUP_MNT:-/mnt/immich-backup}
TS=$(date +%Y-%m-%d_%H%M)
LOG=$LOGD/initial-copy-$TS.log; RLOG=$LOGD/initial-copy-$TS.rsync.log
ln -sfn "$LOG" "$LOGD/initial-copy-latest.log"; ln -sfn "$RLOG" "$LOGD/initial-copy-latest.rsync.log"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
log "start: initial copy to the backup drive"
[ -e "$BYID" ] || { log "RESULT: FAIL (backup drive not present)"; "$PY" "$D/backup_helpers.py" email --subject "[immich-backup] initial copy FAIL: drive not present" --body-file "$LOG"; exit 1; }
findmnt "$MNT" >/dev/null || sudo mount "$MNT" || { log "RESULT: FAIL (could not mount $MNT)"; exit 1; }
log "mounted: $(findmnt -no SOURCE,OPTIONS "$MNT")"
df -h "$MNT" | tail -1 | tee -a "$LOG"
sudo mkdir -p "$MNT/removed"
EXCL=(); for e in ${EXCLUDE:-}; do EXCL+=(--exclude "$e"); done
RC=0; t0=$(date +%s)
for name in ${SYNC_DIRS:-media}; do
  src=$SRC/$name/; dst=$MNT/$name/; sudo mkdir -p "$dst"
  log "rsync $src -> $dst"
  sudo rsync -aHAX --numeric-ids --partial --info=stats2 "${EXCL[@]}" --log-file="$RLOG" --log-file-format='%o %l %n' "$src" "$dst" >>"$LOG" 2>&1
  rc=$?; log "rsync exit=$rc for $src"; [ $rc -eq 0 ] || RC=$rc
done
sync
t1=$(date +%s)
log "copy took $(( (t1-t0)/60 )) min"
df -h "$MNT" | tail -1 | tee -a "$LOG"
log "file count: backup media $(sudo find "$MNT/media" -type f | wc -l), source media $(sudo find "$SRC/media" -type f | wc -l)"
MAIL() { "$PY" "$D/backup_helpers.py" email --subject "$1" --body-file "$LOG" >>"$LOG" 2>&1; }
if [ "$RC" -eq 0 ]; then
  log "RESULT: PASS (initial copy complete; drive left mounted and powered)"
  MAIL "[immich-backup] initial copy PASS ($(( (t1-t0)/60 )) min); weekly run #1 with full verification starts in 60 s"
  log "scheduling the first weekly run in 60 s (fresh dump, config, full verification, then unmount and power off)"
  sudo systemd-run --on-active=60 --unit=immich-backup-first --description="first Immich backup run" systemctl start immich-backup.service >>"$LOG" 2>&1
else
  log "RESULT: FAIL (rsync exit $RC); drive left mounted and powered; weekly run NOT scheduled"
  MAIL "[immich-backup] initial copy FAIL (rsync exit $RC)"
fi
