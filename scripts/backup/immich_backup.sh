#!/bin/bash
# immich_backup.sh - weekly mirror of the Immich data onto the backup disk, which is powered through a smart plug.
# Every site-specific value comes from /etc/immich-tools/backup.conf (see backup.conf.example).
# Runs as root from immich-backup.service (Sunday 03:30 timer, or `sudo systemctl start immich-backup.service`).
# Steps: guards -> plug on, wait for the drive -> mount -> read sample -> capacity check -> fresh database dump
#        -> copy of the Immich config -> rsync of the configured folders (deleted/changed files kept in removed/<date>)
#        -> count the photos and videos on their way out (Immich's trash, removed/) -> purge old removed/ folders
#        -> verify against Immich's checksums -> unmount, detach, plug off
#        -> status line + email.  Any failure stops the run and leaves the drive mounted and powered.
set -u
export PATH=$PATH:/usr/sbin:/sbin:/usr/local/sbin
export PLUG_NOTIFY=0    # this job emails its own result; backup_plug.py must not send a second mail
CONF=${IMMICH_TOOLS_CONF:-/etc/immich-tools/backup.conf}; . "$CONF"
D=${TOOLS_DIR:-/opt/immich-tools/backup}; STATE_ROOT=${STATE_ROOT:-/var/lib/immich-tools}
LOGD=$STATE_ROOT/logs; STATED=$STATE_ROOT/state; mkdir -p "$LOGD" "$STATED"
PY=$D/venv/bin/python; HELP=$D/backup_helpers.py
BYID=$BACKUP_DISK_BYID
MNT=${BACKUP_MNT:-/mnt/immich-backup}; SRC=${IMMICH_DATA:-/mnt/immich}
THRESH=${CAPACITY_PCT:-90}; KEEP_DAYS=${KEEP_REMOVED_DAYS:-84}; FULL_EVERY=${FULL_VERIFY_EVERY:-13}; SAMPLE_PCT=${SAMPLE_PCT:-2}
KEEP_TXT=$( [ $(( KEEP_DAYS % 7 )) -eq 0 ] && echo "$(( KEEP_DAYS / 7 )) weeks" || echo "$KEEP_DAYS days" )
TS=$(date +%Y-%m-%d_%H%M); DATE=$(date +%Y-%m-%d); START_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
LOG=$LOGD/backup-$TS.log; RLOG=$LOGD/backup-$TS.rsync; REPORT=$LOGD/backup-$TS.verify.txt; COPIED=$LOGD/backup-$TS.copied
SUMMARY=$LOGD/backup-$TS.summary; : > "$SUMMARY"; T0=$(date +%s); WARN=""
ln -sfn "$LOG" "$LOGD/backup-latest.log"; ln -sfn "$REPORT" "$LOGD/backup-latest.verify.txt"
STATUS=$STATE_ROOT/LAST-RUN.txt
exec 9>"$D/.lock"; flock -n 9 || { echo "another backup run holds the lock"; exit 1; }
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
summ() { printf '%s=%s\n' "$1" "$2" >> "$SUMMARY"; }          # facts shown as the table in the report mail
warn() { log "WARNING: $*"; WARN="${WARN:+$WARN; }$*"; }
plug() { "$PY" "$D/backup_plug.py" "$@"; }
seagate_dev() { [ -e "$BYID" ] && readlink -e "$BYID"; }
RESULT=FAIL; STEP=start; SUMMARY_LINE=""
finish() {
  local secs=$(( $(date +%s) - T0 )) day; day=$(date '+%a %-d %b')
  echo "$(date '+%Y-%m-%d %H:%M') $RESULT step=$STEP $SUMMARY_LINE" > "$STATUS"
  log "RESULT: $RESULT (step $STEP) $SUMMARY_LINE"
  summ finished "$(date '+%a %-d %b %Y %H:%M')"; summ duration "$(( secs / 3600 )) h $(( secs % 3600 / 60 )) min"
  [ -n "$WARN" ] && summ warnings "$WARN"
  if [ "$RESULT" = PASS ]; then summ result "PASS"; subj="\u2705 Immich backup PASS \u00b7 $day \u00b7 run #$run_no"; title="Immich backup PASS, run #$run_no"; kind=pass
  else summ result "FAIL"; summ step "$STEP"; subj="\u274c Immich backup FAIL at step $STEP \u00b7 $day \u00b7 run #$run_no"; title="Immich backup FAIL at step $STEP, run #$run_no"; kind=fail; fi
  "$PY" "$HELP" email --subject "$(printf "%b" "$subj")" --title "$title" --kind $kind --summary "$SUMMARY" --body-file "$LOG" >>"$LOG" 2>&1 || log "email failed"
}
trap finish EXIT
fail() { log "FAIL at step $STEP: $*"; exit 1; }
run_no=$(( $(cat "$STATED/run-count" 2>/dev/null || echo 0) + 1 ))
log "=== immich backup run #$run_no ==="
summ run "#$run_no"; summ started "$(date '+%a %-d %b %Y %H:%M')"

STEP=guards
"$PY" "$HELP" email --flush >>"$LOG" 2>&1 || true     # deliver mail queued by earlier failures
pgrep -f "[s]urface_read.sh|[i]nitial_copy.sh" >/dev/null && fail "surface read or initial copy is still running"

STEP=power-on
if [ -z "$(seagate_dev)" ]; then
  plug on >>"$LOG" 2>&1 || fail "plug did not switch on"
  for i in $(seq 1 90); do [ -n "$(seagate_dev)" ] && break; sleep 2; done
fi
dev=$(seagate_dev); [ -n "$dev" ] || fail "drive did not appear within 3 min (plug left on)"
sleep 3; log "drive $dev"; summ drive "${BACKUP_DISK_NAME:-backup disk}, $dev"

STEP=mount
for m in $(lsblk -no MOUNTPOINTS "$dev" | grep -v "^$"); do      # anything mounted elsewhere (desktop, manual) comes off first
  [ "$m" = "$MNT" ] || { log "unmounting stray mount $m"; umount "$m" || fail "could not unmount $m"; }
done
findmnt "$MNT" >/dev/null || mount "$MNT" || fail "mount $MNT"
log "mounted $(findmnt -no SOURCE,OPTIONS "$MNT")"

STEP=drive-check
SZ=$(blockdev --getsize64 "$dev"); off=$(( (RANDOM * 32768 + RANDOM) % (SZ / 4194304 - 64) ))
rs=$(dd if="$dev" of=/dev/null bs=4M count=64 skip=$off iflag=direct 2>&1 | tail -1); log "read sample: $rs"; summ read_sample "256 MiB at a random offset: ${rs##*, }"

STEP=capacity
src_used=$(df -B1 --output=used "$SRC" | tail -1); bk_size=$(df -B1 --output=size "$MNT" | tail -1); bk_used=$(df -B1 --output=used "$MNT" | tail -1)
log "source used $((src_used/1000000000)) GB; backup $((bk_used/1000000000)) GB used of $((bk_size/1000000000)) GB"
summ source_used "$((src_used/1000000000)) GB"
[ $(( src_used * 100 / bk_size )) -le $THRESH ] || fail "source ($((src_used/1000000000)) GB) exceeds ${THRESH}% of the backup drive; drop regenerable folders"

STEP=db-dump
dump=$("$PY" "$HELP" dump 2>>"$LOG") || fail "database dump"
log "database dump: $dump"; summ dump "$dump"

STEP=config
mkdir -p "$MNT/config/scripts"
cp -p "${IMMICH_DIR:-/opt/immich}/docker-compose.yml" "${IMMICH_DIR:-/opt/immich}/.env" "$MNT/config/" 2>>"$LOG" || warn "compose or .env not copied"
"$PY" "$HELP" export-config "$MNT/config/immich-system-config.json" >>"$LOG" 2>&1 || warn "system-config export failed"
summ config "docker-compose.yml, .env, Immich settings, fstab, scripts"
cp -p "$D"/*.sh "$D"/*.py "$D"/*.md "$CONF" /etc/systemd/system/immich-backup*.service /etc/systemd/system/immich-backup*.timer "$MNT/config/scripts/" 2>/dev/null   # *.md includes RECOVERY.md
cp -p /etc/fstab "$MNT/config/fstab.pi"
chmod -R go-rwx "$MNT/config"

STEP=rsync
REMOVED="$MNT/removed/$DATE"; RSYNC_RC=0; : > "$COPIED"
EXCL=(); for e in ${EXCLUDE:-}; do EXCL+=(--exclude "$e"); done
for name in ${SYNC_DIRS:-media}; do
  mkdir -p "$MNT/$name"
  log "rsync $SRC/$name/ -> $MNT/$name/"
  rsync -aHAX --numeric-ids --delete --backup --backup-dir="$REMOVED/$name" --partial --info=stats2 "${EXCL[@]}" \
        --log-file="$RLOG.$name.log" --log-file-format='%o %n' "$SRC/$name/" "$MNT/$name/" >>"$LOG" 2>&1 \
    || { rc=$?; log "rsync exit $rc for $name"; RSYNC_RC=$rc; }
  [ "$name" = media ] && sed -nE 's/^[^ ]+ [^ ]+ \[[0-9]+\] (send|recv) //p' "$RLOG.$name.log" >> "$COPIED"
done
sync
[ $RSYNC_RC -eq 0 ] || fail "rsync exit $RSYNC_RC (nothing purged, run not counted)"
copied=$(grep -c '[^/]$' "$COPIED" || true)     # files only: rsync's log also lists every folder it touched
parked=$(find "$REMOVED" -type f 2>/dev/null | wc -l)   # deleted at the source, or the older copy of a changed file
log "media files copied this run: $copied; files deleted or replaced, moved to $REMOVED: $parked"
summ copied "$copied"; summ removed "$parked$( [ "$parked" -gt 0 ] && echo " (kept $KEEP_TXT in removed/$DATE)")"

STEP=purge
# Photos and videos on their way out: Immich's trash, and deleted originals that now exist only in removed/.
# Counted before the purge; a failure here only adds a warning.
stats=$("$PY" "$HELP" deletion-stats --removed-root "$MNT/removed" --keep-days $KEEP_DAYS 2>>"$LOG") || { warn "deletion stats failed"; stats=""; }
[ -n "$stats" ] && log "deletion stats: $(printf '%s' "$stats" | tr '\n' '|')"
printf '%s\n' "$stats" | grep -E '^(trash|backup_only)=' >> "$SUMMARY" || true
purge_now=$(printf '%s\n' "$stats" | sed -n 's/^purge_now=//p')
purged=$(find "$MNT/removed" -mindepth 1 -maxdepth 1 -type d -mtime +$KEEP_DAYS -print -exec rm -rf {} + 2>>"$LOG" | tee -a "$LOG" | wc -l)
if [ "$purged" -gt 0 ]; then summ purged "$purged removed/ folder$( [ "$purged" -gt 1 ] && echo s) older than $KEEP_TXT${purge_now:+: $purge_now}"
else summ purged "none"; fi

STEP=verify
full=""; [ $(( run_no % FULL_EVERY )) -eq 1 ] && full="--full"
"$PY" "$HELP" verify --copied "$COPIED" --sample-pct $SAMPLE_PCT $full --before "$START_ISO" --report "$REPORT" >>"$LOG" 2>&1 \
  || fail "verification found problems, see $REPORT"
SUMMARY_LINE="copied=$copied; $(tail -1 "$REPORT")"; summ verify "$(tail -1 "$REPORT")"
bk_used=$(df -B1 --output=used "$MNT" | tail -1)
summ backup_used "$((bk_used/1000000000)) GB of $((bk_size/1000000000)) GB ($(( bk_used * 100 / bk_size ))%)"
[ $(( bk_used * 100 / bk_size )) -le $THRESH ] || warn "backup drive is $(( bk_used * 100 / bk_size ))% full"

STEP=unmount
sync; umount "$MNT" || fail "unmount (drive left mounted and powered)"
[ -z "$(lsblk -no MOUNTPOINTS "$dev" | grep -v "^$")" ] || fail "something from $dev is still mounted (plug left on)"
udisksctl power-off -b "$dev" || fail "detach (plug left on)"          # flush, SCSI stop (heads parked, spindle stopped), USB removal
sleep 10; [ -z "$(seagate_dev)" ] || fail "drive still present after detach (plug left on)"
plug off >>"$LOG" 2>&1 || fail "plug off"
echo "$run_no" > "$STATED/run-count"
STEP=done; RESULT=PASS
