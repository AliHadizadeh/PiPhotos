# Runbook 05: migrate an Apple Photos library

Chapter: `docs/05-migrate-apple-photos.md`. Read it first. Rule 1 of AGENTS.md applies: the library is read-only.

## Needs
- The library path on the Mac, or the source disk attached to the Pi.
- The Immich user and the key file for that user. The person's usual time zone.
- Free space on the photo disk: at least the library size.

## Steps
1. If the source disk goes on the Pi: mount it read-only and lock it at the block level (chapter 5.5). Check: `findmnt -no OPTIONS /mnt/photos | cut -d, -f1` prints `ro`; `sudo blockdev --getro /dev/sdX` prints `1`.
2. Build the manifest:
   `cd scripts/migrate && python3 photos_catalog.py --library "<path>.photoslibrary" --out work/<user> --fallback-tz <zone>`
   Read `work/<user>/summary.json`. Compare `assets` with the count Photos shows the person. Report `skipped_*` counts.
3. Dry run: `python3 migrate.py --manifest work/<user>/manifest.jsonl --server http://<pi>:2283 --dry-run`. Report the plan: uploads by role, bytes, albums, stacks.
4. Test set: `python3 pick_test_set.py work/<user>/manifest.jsonl work/<user>/test-uuids.txt`, upload it with `--uuids`, then `verify_assets.py`. Check every line: date and zone, GPS, description, tags, favorite, Live link, stack, albums, people. Ask the person to open the 15 assets in the web app. Fix before you continue.
5. Pause the queues that fight the upload: smartSearch, faceDetection, facialRecognition, ocr, videoConversion. Set thumbnail concurrency to 1. Through the jobs API: `PUT /api/jobs/<queue>` with `{"command":"pause","force":false}`.
6. Full run, on the Pi as a service: install `immich-migrate@.service` with the edited paths, `sudo systemctl enable --now immich-migrate@<user>`. Progress: `grep '^\[' work/<user>.run.log | tail -1`. Or on the Mac, detached, with `--workers 2 --newest-first`.
7. Monitor every hour with `scripts/post/migration_monitor.sh <user>`: errors, restarts, temperature, free space. Expect 15 to 25 MB/s per library when two run at once and the Pi also makes thumbnails.
8. When `uploads finished` appears with 0 errors: `python3 fix_metadata.py --api-key-file ... --dry-run`, then without. Restore thumbnail concurrency to 3 and metadata to 5. Disable the service.
9. Run the stages: `nohup setsid scripts/post/post_stages.sh > post_stages.log 2>&1 &` with `KEY_FILE`, and `GPU_URL`/`CPU_URL` if chapter 4 is done. It takes hours to days.
10. Continue with runbook 06.

## Checks
- `migrate.py --report` shows 0 errors, or errors you have explained.
- Immich's asset count for the user equals `assets` in the summary minus collapsed byte-identical burst frames. Explain any difference.
- Integrity reports (Administration, Repair) at 0 after the storage template settled.

## Stop conditions
- The source mount is read-write. Fix it before anything else.
- Errors repeat for the same assets across restarts: inspect them (damaged files are normal, a handful per 100,000).
- Free space on the photo disk under 10 %.

## Record
Counts from summary.json, the test set results, start and end times, speed, errors and their cause, the stages' timing.
