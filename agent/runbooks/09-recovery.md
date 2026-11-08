# Runbook 09: recovery

Chapter: `docs/09-recovery.md`. Slow down. Nothing here is urgent enough to skip a check. The first question decides everything: **is the database intact?** It is whenever the NVMe works. Never restore a dump over a working database.

## Needs
- What failed, in the person's words. The backup disk. For a lost database, the newest dump.

## A. The photo disk died, the NVMe works
1. `cd /opt/immich && sudo docker compose down`.
2. `sudo systemctl disable --now immich-backup.timer immich-backup-watch.timer`. The job must not back the backup disk up onto itself.
3. Mount the backup disk at `/mnt/immich` (change the fstab line to its label), or copy the backup onto a new disk labelled `immich` first. Check `ls /mnt/immich/media` shows Immich's folders.
4. `sudo docker compose up -d`. Check the web app: an old album, a person, a search. Tell the person that photos uploaded after the last backup run are missing and that the phone app re-sends them.
5. On the new disk, after the copy back: `backup_helpers.py verify --backup-root /mnt/immich/media --full --report <file>` with the tools' venv Python. About 2 hours per terabyte. Expect 0 mismatched, 0 missing.
6. Return the backup disk to its role and enable the timers. Say clearly that there was no backup in between.

## B. The NVMe died, the photo disk works
1. Operating system and Docker as in runbook 02. Restore `docker-compose.yml` and `.env` from the backup disk's `config/`, same `DB_PASSWORD`.
2. Mount the photo disk at `/mnt/immich`.
3. Restore the newest dump from `/mnt/immich/media/backups` with the commands in chapter 9.3, which follow the Immich documentation for the installed version. Read that documentation first. Keep any old database directory until the check in step 5.
4. `sudo docker compose up -d`.
5. Check: ping, an old album, a person, a search, asset counts per user against the last report mail. Then "Generate Thumbnails" in missing mode if previews are missing.
6. Reinstall the tools and the timers.

## C. Deleted photos
- Within 30 days: the trash in the web app.
- After Immich deleted them: the backup disk holds the files under `media/library/` until the next weekly run, then under `removed/<date>/` for about 13 weeks. Fetch them and re-upload them through the web app, the phone app or the CLI. Never copy files into the library folder by hand: Immich does not see files without a database row.

## Checks
- `curl -s http://localhost:2283/api/server/ping` returns pong.
- Asset counts per user match the last report mail, minus what was uploaded after the last run in scenario A.
- Integrity check queued and clean.

## Stop conditions
- Scenario A and someone proposes a database restore: refuse, explain the rollback.
- Scenario B and the dump is older than the last successful backup run: say so before you restore.
- The person wants to delete the old database directory before the check in B step 5: refuse until then.

## Record
What failed, which scenario, which dump if any, every command, the counts after, and the time the backup was out of service.
