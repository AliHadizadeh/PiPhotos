# Backup tools

Read [chapter 8](../../docs/08-backup.md) first. Everything site-specific is in `/etc/immich-tools/backup.conf` (see `backup.conf.example`). Secrets are separate files, mode 600: the admin API key, `smtp.json`, the Tuya key file.

| File | Does |
|---|---|
| `install.sh` | installs the tools, the venv with tinytuya, the config skeleton, the systemd units and timers, and a copy of the recovery chapter as `RECOVERY.md` |
| `format_backup_disk.sh` | erases and formats the backup disk, adds the `noauto` fstab line |
| `surface_read.sh` | reads the whole disk once, read-only, mails the result, then starts `initial_copy.sh` on a clean result |
| `initial_copy.sh` | the first full copy, resumable, then schedules the first weekly run |
| `immich_backup.sh` | the weekly run: plug on, mount, read sample, capacity, fresh database dump, config copy, rsync with `removed/<date>`, purge, verify, unmount, detach, plug off, status, email |
| `backup_helpers.py` | `dump`, `export-config`, `verify` (against Immich's checksums), `email` (HTML and text, retries, queue) |
| `backup_plug.py` | `on`, `off`, `status`, `ratecheck` for the Tuya plug; logs power changes, limits power cycles, emails on failure |
| `tuya_cloud_key.py` | one-time fetch of the plug's local key through the Tuya developer platform |
| `plug_test.sh` | plug on, disk appears, clean detach, plug off, disk gone |
| `watchdog.sh` | daily check: standing failure, stale backup, timer disabled, disk powered outside a run, undelivered mail |
| `report_failure.sh` | systemd `OnFailure` hook: mails when the service died without a status |
| `monitor_backup.sh` | what is running right now |
| `immich_smtp.py` | optional: put the same mailbox into Immich's own notification settings |
| `immich-backup.service`, `.timer` | Sunday 03:30, persistent |
| `immich-backup-watch.service`, `.timer` | daily 09:00 |
| `immich-backup-failed.service` | the failure hook |

Rules the scripts follow: never cut the power while the disk is mounted or attached; any failure leaves the disk mounted and powered; no purge in a failed run; replace a running script by renaming a new file over it, never by writing into it.
