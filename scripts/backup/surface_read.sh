#!/bin/bash
# surface_read.sh - read-only full-surface read of the Immich backup drive (badblocks in read-only mode).
# Switches the plug on, waits for the drive, refuses to run if it is mounted, reads every 4 KiB block once,
# logs the outcome and leaves the drive powered and attached; on PASS it starts initial_copy.sh. Writes nothing to the drive.
set -u
export PATH=$PATH:/usr/sbin:/sbin
CONF=${IMMICH_TOOLS_CONF:-/etc/immich-tools/backup.conf}; . "$CONF"
D=${TOOLS_DIR:-/opt/immich-tools/backup}; STATE_ROOT=${STATE_ROOT:-/var/lib/immich-tools}; LOGD=$STATE_ROOT/logs; mkdir -p "$LOGD"
P=$D/backup_plug.py
BYID=$BACKUP_DISK_BYID
TS=$(date +%Y-%m-%d_%H%M)
LOG=$LOGD/surface-read-$TS.log; PROG=$LOGD/surface-read-$TS.progress; BAD=$LOGD/surface-read-$TS.badblocks
ln -sfn "$LOG" "$LOGD/surface-read-latest.log"; ln -sfn "$PROG" "$LOGD/surface-read-latest.progress"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
seagate_dev() { [ -e "$BYID" ] && readlink -e "$BYID"; }
log "start: full-surface read (read-only) of the backup drive"
dev=$(seagate_dev)
if [ -z "$dev" ]; then
  log "plug on"; $P on >>"$LOG" 2>&1 || { log "RESULT: FAIL (plug did not switch on)"; exit 1; }
  for i in $(seq 1 90); do dev=$(seagate_dev); [ -n "$dev" ] && break; sleep 2; done
  [ -z "$dev" ] && { log "RESULT: FAIL (drive did not appear within 3 min; plug left on)"; exit 1; }
  sleep 3
fi
log "drive: $dev"
if findmnt -no SOURCE | grep -q "^${dev}"; then log "RESULT: FAIL (drive is mounted; not running)"; exit 1; fi
SZ=$(sudo blockdev --getsize64 "$dev"); log "size: $SZ bytes, blocks of 4096: $((SZ/4096))"
t0=$(date +%s)
: > "$BAD"
# read-only mode: no -w and no -n, so badblocks never writes
sudo badblocks -b 4096 -c 4096 -s -v -o "$BAD" "$dev" 2>"$PROG"
rc=$?
t1=$(date +%s)
nbad=$(wc -l < "$BAD" | tr -d ' ')
log "badblocks exit=$rc after $(( (t1-t0)/60 )) min, bad blocks listed: $nbad"
tr '\b\r' '\n' < "$PROG" | grep -v '^$' | tail -2 | tee -a "$LOG"
nerr=$(journalctl -k --since "@$t0" --no-pager | grep -iE "$(basename "$dev")" | grep -icE 'error|I/O|reset|sense')
log "kernel error/reset lines for $(basename "$dev") during the run: $nerr"
journalctl -k --since "@$t0" --no-pager -o short-iso | grep -iE "$(basename "$dev")|usb 2-1" | grep -iE 'error|fail|reset|I/O|sense' | head -20 | tee -a "$LOG"
[ $((t1-t0)) -gt 0 ] && log "average speed: $(( SZ / (t1-t0) / 1000000 )) MB/s"
if [ "$rc" -eq 0 ] && [ "$nbad" -eq 0 ] && [ "$nerr" -eq 0 ]; then
  log "RESULT: PASS (0 bad blocks, 0 kernel errors); drive left powered; starting the initial copy"
  exec bash "$D/initial_copy.sh"
else
  log "RESULT: FAIL (badblocks rc=$rc, bad blocks=$nbad, kernel errors=$nerr); drive left powered for inspection; initial copy NOT started"
fi
