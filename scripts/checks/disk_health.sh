#!/bin/bash
# disk_health.sh /dev/sdX - read-only health report for a USB disk on the Pi: identity, SMART, file system state,
# kernel messages, read speed at the start and the end of the disk. Needs smartmontools. Run with sudo.
set -u
export PATH=$PATH:/usr/sbin:/sbin
dev=${1:?usage: disk_health.sh /dev/sdX}
echo "=== identity ==="; lsblk -o NAME,SIZE,MODEL,SERIAL,TRAN,FSTYPE,MOUNTPOINT "$dev"
echo "=== SMART (ATA pass-through; falls back to the bridge's own health status) ==="
if smartctl -i "$dev" >/dev/null 2>&1; then
  smartctl -H "$dev" | grep -i result
  smartctl -A "$dev" | awk '$1==5||$1==9||$1==187||$1==188||$1==194||$1==196||$1==197||$1==198||$1==199 {printf "%-4s %-28s raw=%s\n",$1,$2,$10}'
  smartctl -l error "$dev" | grep -E 'No Errors|Error Count'
  smartctl -l selftest "$dev" | grep -E '^# ' | head -3
else
  echo "no ATA pass-through through this enclosure"; smartctl -d scsi -H "$dev" | grep -i health
fi
echo "=== file systems ==="
for p in "$dev"?*; do
  fs=$(lsblk -no FSTYPE "$p"); [ "$fs" = ext4 ] || { echo "$p: $fs"; continue; }
  echo "$p:"; tune2fs -l "$p" | grep -iE 'state|error count|last checked|mount count|lifetime writes'
done
echo "=== kernel messages about this disk, this boot ==="
journalctl -k --no-pager | grep -iE "$(basename "$dev")" | grep -iE 'error|reset|fail|I/O error' | tail -5 || true
echo "=== read speed, 256 MiB at the start and at the end (read-only) ==="
SZ=$(blockdev --getsize64 "$dev")
dd if="$dev" of=/dev/null bs=4M count=64 iflag=direct 2>&1 | tail -1 | sed 's/^/start: /'
dd if="$dev" of=/dev/null bs=4M count=64 skip=$(( SZ / 4194304 - 70 )) iflag=direct 2>&1 | tail -1 | sed 's/^/end:   /'
echo "=== Pi ==="; echo "temp $(vcgencmd measure_temp 2>/dev/null)  throttled $(vcgencmd get_throttled 2>/dev/null)"
