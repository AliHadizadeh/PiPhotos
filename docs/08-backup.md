# 8. Backup

Time: 2 hours of setup, one night for the first copy. Result: a second disk holds a verified copy of everything, refreshed weekly, powered only during the backup, with an email after every run and an email when anything is wrong.

The tools are in `scripts/backup/`. One config file, `backup.conf`, holds every value that is specific to your setup.

## 8.1 What is protected

| Folder on the photo disk | What it is | Can it be rebuilt? |
|---|---|---|
| `media/library` | the originals | no |
| `media/backups` | nightly database dumps | no, this is the database: albums, people, tags, stacks |
| `media/thumbs`, `media/encoded-video` | thumbnails, previews, transcodes | yes, days of CPU |
| `media/upload`, `media/profile` | uploads in flight, avatars | small |

Immich is originals plus database. Everything else is convenience. Copy everything while it fits. Drop the rebuildable folders when the backup disk fills up.

## 8.2 The design

- **A plain mirror with rsync.** Files on the backup are files. A restore is a copy. Any Linux machine reads the disk.
- **Deleted or changed files are kept** in `removed/<date>/` for 12 weeks, then purged. A mistake in Immich can be undone for three months.
- **Verification against Immich's own checksums.** Immich stores a SHA-1 for every original. Each run hashes every file it copied and a random 2 % of the older originals and compares them with the database. Every 13th run hashes all originals. Silent corruption on either disk shows up.
- **A fresh database dump at the start of each run**, so files and database match.
- **The Immich configuration is copied too**: compose file, `.env`, exported settings, fstab, the scripts, and the recovery chapter, so the instructions travel with the data.
- **Powered only during the run.** A Wi-Fi smart plug switches the disk on, the job mounts it, and at the end the job unmounts, detaches and switches it off. A surge, a wrong command or a bug cannot reach a disk that is off.
- **Any failure stops the run** and leaves the disk mounted and powered for inspection. No purge happens in a failed run. The plug goes off only after a clean unmount and detach.
- **Email after every run.** Email for every problem too: plug failures, a job that died without a report, a failure that stays unfixed, no backup for 8 days, a disk found powered outside a run.
- **Power-cycle limits.** The plug command waits 10 minutes after a power-off before a power-on, and refuses more than 6 power-ons a day.

Why not btrfs snapshots, restic or borg: the originals never change, so deduplication buys nothing, and a plain disk restores without tools. Why not exFAT: too fragile for a library of terabytes.

## 8.3 Set up the backup disk

1. If the disk is used, check it first. Chapter 1 explains why. `scripts/checks/disk_health.sh /dev/sdX` prints SMART data when the enclosure allows it.
2. Format it. **This erases the disk.** The script refuses to touch the photo disk. It checks the model and size you put in `backup.conf`. It clears the stale read-only flag that macOS-formatted disks leave behind. Then it asks you to type ERASE.

```bash
sudo scripts/backup/format_backup_disk.sh
```

It writes a GPT partition, ext4 with the label `immich-backup`, no reserved space, inode tables initialized at once, and errors set to remount read-only. It adds the fstab line `LABEL=immich-backup /mnt/immich-backup ext4 noauto,noatime,nofail,x-systemd.device-timeout=20 0 0`. `noauto` means only the backup job mounts it.

3. Read the whole surface once, unattended, before you trust the disk:

```bash
sudo scripts/backup/surface_read.sh
```

It reads every block with `badblocks` in read-only mode, about 8 hours for 4 TB, and emails the result. Zero bad blocks or the disk goes back to the shop.

## 8.4 The smart plug

Any Tuya-based Wi-Fi plug works. Many brands sell them under their own app names. The Pi needs the plug's device id and its local key, after which the plug obeys commands on the LAN with no cloud.

1. Pair the plug in its app. Note the device id under device information.
2. Get the local key through Tuya's developer platform. Create an account at iot.tuya.com. Create a cloud project of type Smart Home in your region's data centre. Link your app account by QR code from the app's scanner. Subscribe to the free IoT Core trial.
3. If the device query answers "the data center is suspended", open the project, remove the data centre from its settings, confirm, and add it again. The portal may show an error. Ignore it.
4. On the Pi: `scripts/backup/tuya_cloud_key.py` reads the project's id and secret from `/etc/immich-tools/tuya-cloud.json`, asks the platform once, and stores the key in `/etc/immich-tools/tuya-devices.json`, readable by root only. The cloud is never needed again unless the plug is reset.
5. `scripts/backup/backup_plug.py on|off|status` switches the plug. It finds the plug by id on the LAN, confirms the state, logs every real power change, and emails on failure.
6. `scripts/backup/plug_test.sh` runs the whole cycle: plug on, disk appears, clean detach, plug off, disk gone.

Rule that costs a disk if you break it: never cut the power while the disk is mounted. The scripts never do. If you switch the plug by hand, unmount and detach first:

```bash
sudo umount /mnt/immich-backup && sudo udisksctl power-off -b /dev/sdX
```

## 8.5 Install the job

1. Copy `scripts/backup/` to `/opt/immich-tools/backup/` and `scripts/backup/backup.conf.example` to `/etc/immich-tools/backup.conf`. Fill in the disk's by-id path, the plug id, the Immich paths, the thresholds and the email settings.
2. Put the admin API key in `/etc/immich-tools/admin.key`, mode 600.
3. For email, create a mailbox used for nothing else, at your mail provider or as a Gmail app password on a separate account, and put host, port, user, password, from and to into `/etc/immich-tools/smtp.json`, mode 600. Never put your main account's password on the Pi: a mailbox password gives full access to that mailbox. Port 465 means implicit TLS, 587 means STARTTLS. The certificate is checked.
4. Install the systemd units and the timer. The timer runs Sunday 03:30 and catches up after a missed week:

```bash
sudo scripts/backup/install.sh
systemctl list-timers 'immich-backup*'
```

5. First copy. Start it by hand and leave the Pi alone for a night:

```bash
sudo scripts/backup/initial_copy.sh
```

It mirrors the media folder and leaves the disk mounted. Sixty seconds later it starts the first scheduled-style run. That run does a full verification and then powers the disk off. Expect 6 hours for 2 TB over USB 3, and 4 more hours for the verification.

## 8.6 What the mail says

Subject first: `✅ Immich backup PASS · Sun 8 Nov · run #2` or `❌ Immich backup FAIL at step verify · ...`. Inside: a table with run, duration, disk read sample, data size, backup disk usage, database dump, files copied, files parked in removed, folders purged, verification result and warnings, then the last lines of the log. The full log stays on the Pi under `/var/lib/immich-tools/logs/`.

Other mails: `❌ Immich backup: plug problem`, `❌ Immich backup: the service failed without a report`, `⚠️ Immich backup needs attention: ...` from the daily 09:00 check.

## 8.7 By hand

```bash
sudo systemctl start immich-backup.service      # run now
cat /var/lib/immich-tools/LAST-RUN.txt           # last result, one line
/opt/immich-tools/backup/monitor_backup.sh       # what is running right now
```

## 8.8 Limits

- The backup sits next to the Pi. It covers disk failure and mistakes, not fire or theft. Chapter 9 lists what an off-site copy needs.
- Photos added through Immich exist only on the Pi until the next Sunday. Run the job by hand after a big import.
- The backup disk will one day be smaller than the library. The job warns at 90 %. Then the rebuildable folders leave the mirror: add them to `EXCLUDE` in `backup.conf`.
