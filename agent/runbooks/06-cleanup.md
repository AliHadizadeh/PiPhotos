# Runbook 06: clean up after the migration

Chapter: `docs/06-cleanup.md`. Every tool here is a dry run until `--apply`. Show the person the dry run before you apply.

## Needs
- `scripts/post/owners.json` filled in: user ids, key files, display names.
- The Pi idle: no migration, no stage running.

## Steps
1. Person thumbnails: queue "Generate Thumbnails" in missing mode. `PUT /api/jobs/thumbnailGeneration` with `{"command":"start","force":false}`. Wait until the queue drains.
2. Reconcile faces: `python3 reconcile_faces.py --dry-run`. Report clusters, faces and people. With the person's OK: `--apply`.
3. Two users: `python3 propose_names.py` and show the accepted list. With the OK: `--apply`. Then `python3 link_people.py --host <a> --guest <b>` dry, then `--apply`.
4. Duplicates across users: `python3 cross_dup_tags.py` dry run, report the counts per class, then `--apply`. Tags only.
5. Wrong camera clock: `python3 ../dates/calibrate_offset.py ...` to find the shift. Then `shift_dates.py --model ... --days N --dry-run`, show the first lines, `--apply`, then `--verify` after the sidecar, metadata and storage-template queues are empty.
6. Videos: `python3 probe_videos.py`, read the summary. Empty the video conversion queue (`PUT /api/jobs/videoConversion` with `{"command":"empty"}`) only if the person agrees to selective transcoding. Then `python3 queue_transcodes.py`.
7. Integrity: Administration, Repair. Explain stale rows. Never delete reports.

## Checks
- After 2: the number of unnamed people with many photos dropped. `GET /api/people?withHidden=true` total.
- After 5: `shift_dates.py --verify` reports 0 not applied.
- After 6: the video conversion queue holds only the queued count.

## Stop conditions
- A dry run proposes merges across owners, or thousands of renames: stop and show the person.
- Any step that would delete assets or files. None of these tools does. If the person asks for deletion, that is a separate, confirmed step.

## Record
Each tool's dry-run numbers and the applied numbers, with timestamps.
