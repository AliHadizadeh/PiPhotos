#!/bin/bash
# End-to-end test of the backup plug: status -> on -> drive appears -> safe detach -> off -> drive gone.
# Never cuts power while the backup disk is present or mounted.
CONF=${IMMICH_TOOLS_CONF:-/etc/immich-tools/backup.conf}; . "$CONF"
D=${TOOLS_DIR:-/opt/immich-tools/backup}; P=$D/backup_plug.py
BYID=$BACKUP_DISK_BYID
seagate_dev() { [ -e "$BYID" ] && readlink -e "$BYID"; }
echo "=== $(date '+%H:%M:%S') LAN status of the plug ==="
st=$($P status) || { echo "status failed: $st"; exit 1; }
echo "plug: $st"
dev=$(seagate_dev); echo "seagate device now: ${dev:-absent}"
if [ -n "$dev" ]; then
  echo "drive already present: not touching power. mounts:"; lsblk -no MOUNTPOINTS "$dev" | grep -v "^$" || echo "(not mounted)"; exit 0
fi
if [ "$st" = "on" ]; then echo "plug on but no drive: stopping here"; exit 1; fi

echo "=== switching on ==="
$P on || exit 1
t0=$(date +%s)
for i in $(seq 1 60); do dev=$(seagate_dev); [ -n "$dev" ] && break; sleep 2; done
if [ -z "$dev" ]; then echo "drive did not appear within 120 s; leaving the plug ON"; exit 1; fi
echo "drive appeared as $dev after $(( $(date +%s)-t0 )) s"
sleep 3
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT "$dev"
journalctl -k --since "-3min" --no-pager -o short-iso 2>/dev/null | grep -iE "$(basename $dev)|usb 2-1" | tail -5

echo "=== safe detach (unmounted; spin down and remove) ==="
if [ -n "$(lsblk -no MOUNTPOINTS "$dev" | grep -v "^$")" ]; then echo "something on $dev is mounted: not detaching, leaving the plug ON"; exit 1; fi
sync
if sudo udisksctl power-off -b "$dev"; then echo "power-off issued (sync, spin-down, detach)"; else echo "detach FAILED: leaving the plug ON"; exit 1; fi
sleep 10
if [ -n "$(seagate_dev)" ]; then echo "device still present after detach: leaving the plug ON"; exit 1; fi
echo "seagate device now: absent"

echo "=== switching off ==="
$P off || exit 1
sleep 3
echo "plug: $($P status)"
echo "seagate device now: $(seagate_dev || echo absent)"
echo "=== $(date '+%H:%M:%S') done ==="
