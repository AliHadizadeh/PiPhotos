# 1. Hardware

## What you need

| Part | Minimum | What we used | Why |
|---|---|---|---|
| Computer | Raspberry Pi 5, 8 GB | Pi 5, 16 GB | 8 GB runs Immich. 16 GB keeps the Pi responsive when its own machine-learning container runs. |
| Boot and database disk | NVMe SSD, 128 GB, on an NVMe HAT | 256 GB NVMe | The database must be on a fast disk. An SD card is too slow and wears out. |
| Photo disk | USB 3 hard disk, 2 times your library size | 4 TB, in a powered enclosure | Immich stores originals, thumbnails, transcodes and database dumps here. |
| Power supply | Official 27 W Pi 5 supply | the official supply | A USB disk draws power through the Pi unless it has its own supply. |
| Cooling | Active cooler or a fan case | active cooler | Thumbnails and transcodes run the CPU at 100 % for days. |
| Network | Wired gigabit Ethernet | wired | Uploads of 2 TB over Wi-Fi take a week. |

## Optional

| Part | Use | Chapter |
|---|---|---|
| Second USB disk, at least your library size | Weekly backup | [8](08-backup.md) |
| Wi-Fi smart plug (Tuya based) | Powers the backup disk only during the backup | [8](08-backup.md) |
| A computer with an NVIDIA GPU, 8 GB VRAM or more | Face detection, search and OCR run 20 to 50 times faster | [4](04-ml-offload.md) |
| A second Pi or any always-on machine | Off-site copy of the database dumps | [9](09-recovery.md) |

## Disk advice

- Use a disk with its own power supply. Bus-powered 2.5 inch disks drop out under load.
- Prefer CMR disks for the photo disk. SMR disks are fine for the backup disk.
- Check a used disk before you trust it. Chapter 8 shows a full-surface read.
- Format the photo disk as ext4. macOS cannot write ext4, and that is fine. The Pi owns this disk.

## Layout we use

```
NVMe        /                 Raspberry Pi OS, Docker, Immich's database
USB disk 1  /mnt/immich       Immich media: originals, thumbnails, transcodes, database dumps
USB disk 2  /mnt/immich-backup  weekly backup, mounted only during the backup
```

## Before you buy

1. Count your photos and videos. Note the total size.
2. Multiply the size by 2. That is the photo disk size.
3. Decide if you want the GPU machine. Without it, the first machine-learning pass of 100,000 photos takes about two weeks on the Pi. With it, one night.
