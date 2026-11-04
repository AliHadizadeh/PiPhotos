# 6. Clean up the library

Do this after the migration, with the Pi idle. Each section is independent. The tools are in `scripts/post/` and `scripts/dates/`.

## 6.1 Person thumbnails

Faces imported from sidecars exist before the photos have thumbnails. Some people show a broken picture at first. Administration, Jobs, "Generate Thumbnails", mode "missing" fills them in.

## 6.2 Merge Immich's faces into the named people

Immich runs its own face detection on every photo. It creates unnamed people next to the named ones from the import, because its box must overlap the imported region by more than half to merge on its own. In our libraries only 10 % did.

`scripts/post/reconcile_faces.py` matches each detected face to an imported named region on the same photo by box centre. When at least three faces of a cluster match the same person, it merges the cluster into that person. Dry run first:

```bash
python3 reconcile_faces.py --api-key-file ~/.config/immich-tools/<user>.key --dry-run
python3 reconcile_faces.py --api-key-file ~/.config/immich-tools/<user>.key --apply
```

Expect it to merge most of the large unnamed clusters into the named people in one pass.

## 6.3 Names across two users

The same people appear in both users' libraries. `scripts/post/propose_names.py` computes the average face embedding per person in each account. It proposes a name for an unnamed cluster when the cluster sits close to a named person in the other account. Read the proposal, then apply it. Then share the people between the accounts with `link_people.py`, so both users see one set of named people with their own display names.

Immich detail: a merge between two named persons of different users is skipped silently unless it runs with the key of the user whose person is merged away. The script does that.

## 6.4 Duplicates

**Inside one account**, Immich finds duplicates itself. Review them under Utilities, Duplicates. Stacked assets are skipped by design.

**Across two accounts**, Immich sees nothing. `scripts/post/cross_dup_tags.py` compares the database and tags three classes in both accounts, under a parent tag you choose:

- Identical file: same checksum.
- Same shot: same capture second, dimensions and camera, different bytes. Images must also be visually near-identical by Immich's own search embedding.
- Looks identical: embedding distance under 0.01, Immich's own duplicate threshold.

Our policy: tags only. No deletions, no hard links. The script is a sync. Run it again after phone backups add photos.

Remember that every tag change rewrites the asset's sidecar. The originals stay untouched.

## 6.5 Wrong camera clocks

A camera that was never set after a battery change puts years of photos on the wrong date. We had a compact camera 440 days behind for its whole life.

1. Find the offset. Pick a trip where that camera and a second camera with a correct clock both took photos. `scripts/dates/calibrate_offset.py` searches the whole-day shift that best aligns the two cameras' photo times.
2. Check in the web app that the affected photos still show the camera's time, so one uniform shift applies.
3. Shift them:

```bash
python3 shift_dates.py --api-key-file ~/.config/immich-tools/<user>.key --model "DSC-T200" --days 440 --dry-run
python3 shift_dates.py --api-key-file ~/.config/immich-tools/<user>.key --model "DSC-T200" --days 440 --apply
```

The script sets `dateTimeOriginal` through the API. Immich then writes the new date into the sidecar, re-reads the metadata and moves the file into the new date folder on disk. Nothing else to do. The log makes the run resumable. `--verify` reads the assets back.

## 6.6 Photos without a date

Scans, WhatsApp images and old clips carry no date. Photos used the file's creation time, often the day of a copy. Evidence that works, strongest first:

1. A date in the file name.
2. A recording stamp inside the container, such as `IDIT` in AVI files.
3. The capture times of numbered neighbours from the same camera.
4. The file's own modification time, if the folder is a camera dump. Write a plan as a table, review it, then apply it with `shift_dates.py --plan`.

## 6.7 Transcode only what needs it

The "required" policy also transcodes 10-bit HDR video. Instead:

1. Empty the video conversion queue.
2. `scripts/post/probe_videos.py` runs ffprobe over every video through the Immich container and writes a census: codec, pixel format, audio codec.
3. `scripts/post/queue_transcodes.py` queues per-asset transcode jobs only for what browsers cannot play: MPEG-1, MJPEG, MPEG-4 part 2, H.263, and clips with PCM audio.

In a mixed iPhone and camera library this cuts the queue to under a tenth of what the policy would create, and most videos stay as originals. New HDR clips from the phones still transcode one by one. Leave the policy at "required" and never press "Missing" or "All" on Video Conversion.

## 6.8 Edited photos without a search embedding

In Immich 3.3 the embedding job fails for assets that have an edited preview. `scripts/post/embed_edited.sh` computes the embedding against the machine-learning container and inserts it. Check the release notes of your version before you use it. The bug may be fixed.

## 6.9 Integrity reports

Immich checks for missing files, untracked files and checksum mismatches every night. The checks detect, they do not repair.

- The untracked-file scan lists the disk when queued but compares later. Files moved by the storage template in between show as untracked. Harmless.
- Never press "Delete reports" on stale rows. It can trash the assets behind missing-file reports.

## 6.10 Keep the API keys you still need

`cross_dup_tags.py`, the monitoring script and the backup job read keys. Delete the others in Account Settings.
