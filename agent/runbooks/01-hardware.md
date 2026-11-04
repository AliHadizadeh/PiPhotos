# Runbook 01: hardware check

Chapter: `docs/01-hardware.md`. Mostly the person's job. The agent verifies what arrived.

## Needs
- SSH access to the Pi.

## Steps
1. Confirm the model and memory:
   `cat /proc/device-tree/model; free -h | head -2`
   Expect: Raspberry Pi 5, 8 GB or more.
2. Confirm the boot disk is the NVMe:
   `lsblk -o NAME,SIZE,TYPE,TRAN,MOUNTPOINT`
   Expect: `/` on `nvme0n1p2`, not on `mmcblk0`.
3. List the USB disks with their by-id names. Record them:
   `ls -l /dev/disk/by-id/ | grep -v part`
4. Confirm each USB disk is on USB 3:
   `lsusb -t`
   Expect: `5000M` next to the mass-storage device. `480M` means a USB 2 port or cable.
5. Confirm cooling and power:
   `vcgencmd measure_temp; vcgencmd get_throttled`
   Expect: `throttled=0x0`. Any other value means under-voltage or heat; stop and tell the person.
6. For a used disk, run the health report, read-only:
   `sudo scripts/checks/disk_health.sh /dev/sdX`
   Note whether the enclosure passes SMART through. Record the counters.

## Checks
- Pi 5, 8 GB or more, NVMe root, USB disks at 5000M, throttled 0x0.

## Stop conditions
- Throttling flags set. A USB disk on a 480M link. SMART reallocated or pending sectors above 0 on a disk meant for photos.

## Record
Model, memory, disks with by-id names and sizes, SMART summary, date.
