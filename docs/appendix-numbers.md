# Appendix: performance numbers

Rates we measured, for planning. Setup: Pi 5 with 16 GB, NVMe for the system and the database, USB 3 disks with their own power supplies, wired gigabit network, a GPU machine with two Pascal-era 12 GB cards. Your numbers will differ with other hardware. The ratios between the columns are what to take away.

## Upload into Immich

| What | Rate |
|---|---|
| Migration tool, one library, two workers, Pi also making thumbnails | 15 to 25 MB/s |
| Two libraries at once | about 40 MB/s combined |
| Phone backup through the app over Wi-Fi | about 160 items per minute |
| Database dump | about 10 KB per asset, written at about 4 MB/s |

## Machine learning

| Task | GPU machine | Pi 5 under load |
|---|---|---|
| Smart search embedding, ViT-B-32 | 34 images per second | 2.6 images per second |
| Smart search embedding, SigLIP2 | 38 images per second | 0.9 images per second |
| Face detection and recognition | 25 images per second | 0.5 images per second |
| Search text encoding, one query | 70 to 90 ms | 375 to 560 ms |
| OCR, CPU container on the GPU machine | about 8 images per second | |
| Face clustering, on the Pi, concurrency 1 | about 15 faces per second | |
| Thumbnails, on the Pi, concurrency 3 | 45 to 75 images per minute | |

Rule of thumb: the first machine-learning pass over a library takes one night with the GPU machine and about two weeks on the Pi alone.

## Video

| What | Rate |
|---|---|
| Transcoding on the Pi, x264, 1080p | 0.5 times real time |
| Transcoding on the Pi, x264, 4K | 0.15 times real time |
| Share of jobs the "required" policy creates that selective transcoding avoids, in a mixed iPhone and camera library | about 90 % |

## API operations

| What | Rate |
|---|---|
| Date change through the API, one asset per request | about 20 assets per second |
| Sidecar rewrite after a tag change, on the Pi | about 13 assets per second |
| Queue drain after a bulk date change, sidecar plus metadata plus storage template | about 5 minutes per 3,500 assets |

## Disks on the Pi

| What | Rate |
|---|---|
| 5400 rpm 4 TB USB 3 disk, sequential read | 200 MB/s at the start, 100 MB/s at the end |
| 4 TB USB 3 backup disk, full-surface read | 150 MB/s average, 190 MB/s at the start, 60 MB/s at the end |
| rsync copy USB 3 disk to USB 3 disk, large files | 90 to 150 MB/s |
| Checksum verification of a backup, read plus SHA-1 | 110 to 160 MB/s |
| Spinning idle disk | about 5 W, about 45 kWh per year |

## Pi under load

| What | Value |
|---|---|
| Temperature with the active cooler at load 12 | 47 to 68 °C, no throttling |
| Temperature idle | about 48 °C |
