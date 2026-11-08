# Runbook 08: backup

Chapter: `docs/08-backup.md`. The destructive step is 3. Confirm it with the person in their words.

## Needs
- The backup disk attached to the Pi, its by-id name, model and size.
- A Tuya-based smart plug, paired in its app, with the device id. The person does the Tuya developer platform steps; the agent cannot create accounts.
- An email account for reports: host, port, user, password, from, to, and optionally from_name, the sender name. Stored in `/etc/immich-tools/smtp.json`, mode 600.
- The admin API key in `/etc/immich-tools/admin.key`, mode 600.

## Steps
1. Install: `sudo scripts/backup/install.sh`. Edit `/etc/immich-tools/backup.conf`: by-id, model glob, size range, plug id, folders to sync.
2. Health of the backup disk: `sudo scripts/checks/disk_health.sh /dev/sdX`. Note if SMART is hidden by the enclosure.
3. Format: `sudo /opt/immich-tools/backup/format_backup_disk.sh`. It asks for the word ERASE. **Ask the person before you type it.** It refuses the photo disk, a wrong model or size.
4. Plug key: the person creates the Tuya project and gives you the project's client id and secret for `/etc/immich-tools/tuya-cloud.json` (mode 600). `sudo /opt/immich-tools/backup/venv/bin/python /opt/immich-tools/backup/tuya_cloud_key.py`. On "data center is suspended", the person removes and re-adds the data centre in the project. Run again.
5. Plug test: `sudo /opt/immich-tools/backup/plug_test.sh`. Expect on, disk appears, detach, off, gone. The plug may be unreachable for a minute after a re-plug; the command retries.
6. Email test: `sudo /opt/immich-tools/backup/venv/bin/python /opt/immich-tools/backup/backup_helpers.py email --subject test --body-file /etc/hostname`.
7. Surface read, detached: `cd /opt/immich-tools/backup && sudo nohup setsid ./surface_read.sh > /var/lib/immich-tools/logs/surface-read.out 2>&1 &`. Hours. It mails the result and starts `initial_copy.sh` on PASS, which schedules the first weekly run with a full verification. Check progress with `monitor_backup.sh`.
8. Next morning: `cat /var/lib/immich-tools/LAST-RUN.txt` says PASS. The report mail arrived.

## Checks
- `systemctl list-timers 'immich-backup*'` shows Sunday 03:30 and daily 09:00.
- The plug is off and the disk absent between runs: `monitor_backup.sh`.
- `backup_plug.py ratecheck` passes.
- `sudo /opt/immich-tools/backup/venv/bin/python /opt/immich-tools/backup/backup_helpers.py deletion-stats` prints the trash, backup-only and purge rows. With the disk unmounted, the backup-only row says none.

## Stop conditions
- The format guard refuses. Do not override it.
- The surface read reports bad blocks: the disk goes back. Do not copy onto it.
- Any step leaves the disk mounted and the plug on: read the log, fix, do not cut the power.

## Record
Disk identity, format parameters, the plug id, the test results, the surface read result, the first run's numbers.
