# 9. Recovery

Read this before you need it. Every scenario assumes the backup from [chapter 8](08-backup.md). The backup job also copies this chapter onto the backup disk, under `config/scripts/`, so the instructions travel with the data.

## 9.1 Know what you have

- Originals: on the photo disk under `media/library`, and on the backup disk.
- Database: on the NVMe, alive as long as the NVMe is. Its dumps are under `media/backups` on both disks. The newest dump is from the last backup run or from 02:00 last night.
- Configuration: `config/` on the backup disk, with `docker-compose.yml`, `.env`, the exported settings, the fstab and the scripts.
- Everything derived can be rebuilt by Immich: thumbnails, previews, transcodes, metadata, faces, search, duplicates.

The first question in every scenario: is the database intact? If the NVMe works, it is. Do not restore a dump over a working database. The dump is older than the database, and a restore loses every album, name and date edit made since.

## 9.2 The photo disk died

The database is intact. Only the files are gone.

1. Stop Immich: `cd /opt/immich && sudo docker compose down`.
2. Stop the backup job, so it cannot try to back the backup disk up onto itself:
   `sudo systemctl disable --now immich-backup.timer immich-backup-watch.timer`
3. Mount the backup disk at the library path, in place of the dead disk. Its root already holds `media/` and `migration/`, so Immich's paths are unchanged. Change the fstab line for `/mnt/immich` to the backup disk's label, or copy the backup onto a new disk labelled `immich` first.
4. Start Immich. Open the web app. Everything up to the last backup run is there. Photos uploaded after that run are missing. The phone app sends them again on its next backup.
5. When a new disk arrives, copy `media/` back onto it, then check every original against the database with the job's own tool, about 2 hours per terabyte:

```bash
sudo /opt/immich-tools/backup/venv/bin/python /opt/immich-tools/backup/backup_helpers.py verify --backup-root /mnt/immich/media --full --report /var/lib/immich-tools/logs/restore-verify.txt
```

6. Put the backup disk back into its role and enable the timers again. Until then you have no backup.

## 9.3 The NVMe died

The database is gone with it. The photos and the dumps are on the photo disk.

1. Install the operating system and Docker as in [chapter 2](02-install.md).
2. Restore `/opt/immich/docker-compose.yml` and `.env` from the backup disk's `config/` folder, or from your notes. Use the same `DB_PASSWORD`.
3. Mount the photo disk at `/mnt/immich`.
4. Restore the database from the newest dump, following the Immich documentation for your version. For Immich 3 the documented way is: with the stack stopped, remove the old database directory named in `DB_DATA_LOCATION` if one exists, then

```bash
cd /opt/immich
sudo docker compose create
sudo docker start immich_postgres
sleep 10
gunzip --stdout /mnt/immich/media/backups/<newest>.sql.gz \
  | sed "s/SELECT pg_catalog.set_config('search_path', '', false);/SELECT pg_catalog.set_config('search_path', 'public, pg_catalog', true);/g" \
  | sudo docker exec -i immich_postgres psql --dbname=immich --username=postgres --single-transaction --set ON_ERROR_STOP=on
sudo docker compose up -d
```

   Immich 3 also offers a restore of a `.sql.gz` in the web app under Administration, Maintenance. The documentation's variant with `docker compose down -v` removes the named volumes too, including the machine-learning model cache, which is then downloaded again on the next start.

5. Open the web app. Check an old album, a person, a search. Run "Generate Thumbnails" in missing mode if previews are missing.
6. Reinstall the tools from this handbook and the timers.

## 9.4 The Pi died

Any Linux machine with Docker and USB 3 can take over. Follow 9.3 on that machine. The disks carry everything.

## 9.5 Someone deleted the wrong photos

- Within 30 days: Immich's trash restores them, with their albums and names.
- After Immich deleted them: until the next weekly run, the backup disk still holds the files under `media/library/`. After that run, they are under `removed/<date>/` for about 13 weeks, [chapter 8.7](08-backup.md). The report's "Only on the backup" row counts them. Fetch them from there and upload them again, through the web app, the phone app or the Immich CLI. Do not copy them into the library folder by hand: a file without a database row is invisible to Immich, and the integrity check only reports it as untracked. Album membership and names come back only with a database restore, which is rarely worth it for a few photos.
- Later: gone, unless an older full backup exists elsewhere.

## 9.6 A file is corrupt

The weekly verification mails the path. Compare the checksum on the photo disk and on the backup disk with the one in the database. Copy the good one over the bad one. Then run Immich's integrity check.

## 9.7 Off-site copy

The backup disk covers one failure at a time. For fire or theft you need a copy in another building. Two ways: a second backup disk that you swap monthly and keep elsewhere, or a copy of the dumps and originals to a remote machine over Tailscale. The weekly job's `rsync` works unchanged against a remote path.

## 9.8 Practice

Do a restore drill before you need it: restore the newest dump into a throwaway Postgres container and count the assets, or restore everything onto a spare disk and start a second Immich from it. Write down what it took.
