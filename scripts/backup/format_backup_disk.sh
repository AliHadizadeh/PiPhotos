#!/bin/bash
# format_backup_disk.sh - make the backup disk: GPT, one ext4 partition labelled immich-backup, fstab entry (noauto).
# THIS ERASES THE DISK. Guards: the disk must resolve from BACKUP_DISK_BYID, must not be the disk behind IMMICH_DATA,
# must match BACKUP_DISK_MODEL_MATCH and the size range in backup.conf, and nothing from it may stay mounted.
set -euo pipefail
export PATH=$PATH:/usr/sbin:/sbin
CONF=${IMMICH_TOOLS_CONF:-/etc/immich-tools/backup.conf}; . "$CONF"
MNT=${BACKUP_MNT:-/mnt/immich-backup}; SRC=${IMMICH_DATA:-/mnt/immich}
DEV=$(readlink -e "$BACKUP_DISK_BYID") || { echo "backup disk not present at $BACKUP_DISK_BYID"; exit 1; }
SRC_DISK="/dev/$(lsblk -no PKNAME "$(findmnt -no SOURCE "$SRC")")"
MODEL=$(lsblk -dno MODEL "$DEV" | sed 's/ *$//'); SIZE=$(blockdev --getsize64 "$DEV")
echo "target: $DEV  model='$MODEL'  size=$SIZE   (photo disk: $SRC_DISK)"
[ "$DEV" != "$SRC_DISK" ] || { echo "REFUSING: target is the photo disk"; exit 1; }
case "$MODEL" in ${BACKUP_DISK_MODEL_MATCH:-*}) ;; *) echo "REFUSING: model '$MODEL' does not match BACKUP_DISK_MODEL_MATCH"; exit 1;; esac
[ "$SIZE" -ge "${BACKUP_DISK_SIZE_MIN:-0}" ] && [ "$SIZE" -le "${BACKUP_DISK_SIZE_MAX:-999999999999999}" ] || { echo "REFUSING: size $SIZE outside the configured range"; exit 1; }
for m in $(lsblk -no MOUNTPOINTS "$DEV" | grep -v '^$'); do umount "$m" && echo "unmounted $m"; done
lsblk -o NAME,SIZE,FSTYPE,LABEL "$DEV"
read -r -p "Type ERASE to format $DEV ($MODEL): " ans; [ "$ans" = ERASE ] || { echo "aborted"; exit 1; }
for p in "$DEV"?* "$DEV"; do [ -e "$p" ] && blockdev --setrw "$p"; done      # macOS-formatted disks leave a stale read-only flag
wipefs -a "$DEV"?* "$DEV" 2>/dev/null || wipefs -a "$DEV"
printf 'label: gpt\nname="immich-backup", type=L\n' | sfdisk --wipe always --wipe-partitions always "$DEV"
udevadm settle; sleep 2
PART=$(lsblk -nro NAME,TYPE "$DEV" | awk '$2=="part"{print "/dev/"$1; exit}')
echo "mkfs.ext4 on $PART (no reserved blocks, 32 KiB per inode, tables initialized now; a few minutes)"
mkfs.ext4 -q -F -L immich-backup -m 0 -i 32768 -E lazy_itable_init=0,lazy_journal_init=0 "$PART"
tune2fs -e remount-ro "$PART" >/dev/null
udevadm settle; blkid "$PART"
mkdir -p "$MNT"
grep -q 'LABEL=immich-backup' /etc/fstab || echo "LABEL=immich-backup  $MNT  ext4  noauto,noatime,nofail,x-systemd.device-timeout=20  0  0" >> /etc/fstab
systemctl daemon-reload
mount "$MNT" && df -h "$MNT" | tail -1
printf 'immich-backup: %s, ext4 created %s. Weekly mirror of the Immich data; see the handbook, chapter 8.\n' "${BACKUP_DISK_NAME:-backup disk}" "$(date '+%Y-%m-%d %H:%M')" > "$MNT/README-DISK.txt"
sync; umount "$MNT"; echo "done; the disk is unmounted (noauto). Next: surface_read.sh"
