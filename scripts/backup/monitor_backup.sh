#!/bin/bash
# monitor_backup.sh - compact status of tonight's chain (surface read -> initial copy -> weekly run #1) and the Pi.
export PATH=$PATH:/usr/sbin:/sbin
CONF=${IMMICH_TOOLS_CONF:-/etc/immich-tools/backup.conf}; . "$CONF"
D=${TOOLS_DIR:-/opt/immich-tools/backup}; STATE_ROOT=${STATE_ROOT:-/var/lib/immich-tools}; L=$STATE_ROOT/logs
MNT=${BACKUP_MNT:-$MNT}; SRC=${IMMICH_DATA:-/mnt/immich}
BYID=$BACKUP_DISK_BYID; dev=$( [ -e "$BYID" ] && readlink -e "$BYID" ); blk=$(basename "${dev:-none}")
echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="
echo "processes: surface_read=$(pgrep -fc '[s]urface_read.sh') badblocks=$(pgrep -c badblocks) initial_copy=$(pgrep -fc '[i]nitial_copy.sh') rsync=$(pgrep -c rsync) weekly=$(pgrep -fc '[i]mmich_backup.sh') verify=$(pgrep -fc 'backup_helpers.py verify') chain_watch=$(pgrep -fc '[c]hain_watch.sh')"
echo "drive: $([ -e "$BYID" ] && echo present || echo absent)  mounted: $(findmnt -no TARGET $MNT 2>/dev/null || echo no)  plug: $(PLUG_NOTIFY=0 $D/venv/bin/python $D/backup_plug.py status 2>&1 | tail -1)"
echo "--- surface read ---"
tail -2 "$L/surface-read-latest.log" 2>/dev/null
tr '\b\r' '\n' < "$L/surface-read-latest.progress" 2>/dev/null | grep -v '^$' | tail -1; echo
if [ -e "$L/initial-copy-latest.log" ]; then
  echo "--- initial copy ---"; grep -E 'start:|rsync |exit=|RESULT|took' "$L/initial-copy-latest.log" | tail -4
  echo "rsync log lines: $(wc -l < "$L/initial-copy-latest.rsync.log" 2>/dev/null)  backup used: $(df -h $MNT 2>/dev/null | awk 'NR==2 {print $3" of "$2}')"
fi
if [ -e "$L/backup-latest.log" ] && [ -e "$L/initial-copy-latest.log" ] && [ "$(stat -c %Y "$L/backup-latest.log")" -gt "$(stat -c %Y "$L/initial-copy-latest.log")" ]; then
  echo "--- weekly run ---"; grep -E '=== immich|FAIL|RESULT|rsync |database dump|verify|mounted|drive ' "$L/backup-latest.log" | tail -6
fi
echo "--- status file ---"; cat "$STATE_ROOT/LAST-RUN.txt" 2>/dev/null
echo "pending mail: $(ls "$STATE_ROOT/state/pending-mail" 2>/dev/null | wc -l)   power-log: $(tail -2 "$STATE_ROOT/state/power-log" 2>/dev/null | tr '\n' ';')"
echo "--- pi ---"; echo "temp $(vcgencmd measure_temp | cut -d= -f2)  throttled $(vcgencmd get_throttled | cut -d= -f2)  load $(cut -d' ' -f1-3 /proc/loadavg)  free $(free -h | awk '/Mem/ {print $7}')  immich disk $(df -h "$SRC" | awk 'NR==2 {print $4" free"}')"
echo "kernel errors on $blk this boot: $(journalctl -k -b --no-pager 2>/dev/null | grep -iE "$blk" | grep -icE 'error|reset|I/O error|fail')"
echo "read/write rate (5 s): $(r1=$(awk '{print $3, $7}' /sys/block/$blk/stat 2>/dev/null); sleep 5; r2=$(awk '{print $3, $7}' /sys/block/$blk/stat 2>/dev/null); echo "$r1 $r2" | awk '{printf "read %d MB/s write %d MB/s", ($3-$1)*512/5/1e6, ($4-$2)*512/5/1e6}')"
