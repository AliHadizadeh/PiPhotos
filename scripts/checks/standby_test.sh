#!/bin/bash
# standby_test.sh /dev/sdX - does the disk spin down by itself when idle? Waits for 15 minutes with no block I/O
# on the disk, then asks the drive for its power mode without waking it. Run with sudo; the disk must be idle.
set -u
export PATH=$PATH:/usr/sbin:/sbin
dev=${1:?usage: standby_test.sh /dev/sdX}; d=$(basename "$dev")
read -r r1 w1 < <(awk '{print $1, $5}' "/sys/block/$d/stat")
start=$(date +%s); idle=$start
echo "waiting for a 15-minute window without I/O on $dev (gives up after 45 min)"
while :; do
  sleep 30
  read -r r2 w2 < <(awk '{print $1, $5}' "/sys/block/$d/stat"); now=$(date +%s)
  if [ "$r2" != "$r1" ] || [ "$w2" != "$w1" ]; then idle=$now; echo "$(date +%H:%M:%S) I/O seen, timer reset"; fi
  r1=$r2; w1=$w2
  [ $((now - idle)) -ge 900 ] && break
  [ $((now - start)) -ge 2700 ] && { echo "no quiet window"; exit 1; }
done
echo "quiet for 15 min; power mode now:"; smartctl -n standby -i "$dev" | grep -iE 'power mode|STANDBY|SLEEP'
echo "(ACTIVE or IDLE = the disk never spins down on its own; STANDBY = it does)"
