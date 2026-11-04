# 5. Migrate from Apple Photos

Time: a few hours of your attention, then one day per terabyte unattended. Result: every photo and video from the Photos library is in Immich, with its date, time zone, GPS, albums, keywords, named faces, Live Photo clip, edits, RAW pair and burst group. The Photos library is not changed.

The tool is in `scripts/migrate/`. It is standard-library Python 3. It needs nothing installed.

## 5.1 Rules

1. Never open the source library in Photos.app while you migrate. Photos rewrites its database when it opens.
2. Mount the source disk read-only. On the Pi, also lock the block device read-only (step 5.5).
3. Work from a copy of the catalog. The tool copies `Photos.sqlite` before it reads it.
4. Upload originals byte for byte. Metadata goes in an XMP sidecar next to each upload. Immich reads the sidecar and keeps it.
5. Test with 15 photos before you upload 50,000.

## 5.2 What is carried over

| In Photos | In Immich | How |
|---|---|---|
| Originals: HEIC, JPEG, RAW, MOV, MP4 | the same bytes | upload |
| Live Photo clip (`<uuid>_3.mov`) | linked to the still | clip uploaded first, then linked |
| RAW + JPEG pair (`<uuid>_4.cr2`) | a stack, JPEG on top | both uploaded, stacked |
| Edits (full-size renders) | a stack, edit on top of the untouched original | render uploaded, stacked |
| Date with time zone, GPS, title, caption | the same | XMP sidecar |
| Keywords | tags | sidecar `dc:subject` and `digiKam:TagsList` |
| Named faces | named people | sidecar MWG regions, with "face import" on |
| Favorites, hidden | favorite, archived | upload flags |
| Albums and folders | albums named `Folder / Album` | API |
| Bursts | a stack, key photo on top | API |
| iCloud shared-album copies, Recently Deleted | skipped, listed | `skipped.jsonl` |

Edited videos are stacked too. A video's image render is only its poster frame and is not uploaded.

## 5.3 Build the manifest

Run this on the Mac with the library's disk attached. Or run it on the Pi with the disk mounted read-only.

```bash
cd scripts/migrate
python3 photos_catalog.py --library "/Volumes/<disk>/<name>.photoslibrary" --out work/<user> --fallback-tz <Your/Timezone>
```

Output in `work/<user>/`: `manifest.jsonl` (one line per asset), `albums.json`, `people.json`, `bursts.json`, `summary.json`, `skipped.jsonl`. Read `summary.json`. Compare the asset count with what Photos shows.

`--fallback-tz` is the time zone used for photos whose time zone Photos never recorded. Use the zone you lived in when you took most of them.

## 5.4 Test, then run

1. Dry run. Nothing is uploaded:

```bash
python3 migrate.py --manifest work/<user>/manifest.jsonl --server http://<pi>:2283 --dry-run
```

2. Upload a test set of 15 photos that covers rotated, edited, RAW, burst, Live, favorite, album and face cases. Then look at what Immich recorded:

```bash
python3 pick_test_set.py work/<user>/manifest.jsonl work/<user>/test-uuids.txt
python3 migrate.py --manifest work/<user>/manifest.jsonl --server http://<pi>:2283 --api-key-file ~/.config/immich-tools/<user>.key --uuids work/<user>/test-uuids.txt
python3 verify_assets.py --state work/<user>/state.sqlite --server http://<pi>:2283 --api-key-file ~/.config/immich-tools/<user>.key
```

Check each line: date and time zone, GPS with place names, description, tags, favorite, Live link, stack, albums, people. Open the photos in the web app. Fix what is wrong before you go on.

3. Full run:

```bash
python3 migrate.py --manifest work/<user>/manifest.jsonl --server http://<pi>:2283 --api-key-file ~/.config/immich-tools/<user>.key --workers 2 --newest-first
```

The run is resumable. Stop it and start the same command again at any time. `--report` prints the state. Errors are retried on the next run. Immich skips files it already has, by checksum.

## 5.5 Run it on the Pi, unattended

An SSH session dies. A systemd service does not.

1. Mount the source disk read-only and lock it:

```bash
echo 'UUID=<source-disk-uuid>  /mnt/photos  hfsplus  ro,noatime,nofail,uid=1000,gid=1000,x-systemd.device-timeout=20  0  0' | sudo tee -a /etc/fstab
echo 'ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_UUID}=="<source-disk-uuid>", RUN+="/usr/sbin/blockdev --setro /dev/%k"' | sudo tee /etc/udev/rules.d/99-photos-drive-readonly.rules
sudo udevadm control --reload && sudo mount /mnt/photos
findmnt -no OPTIONS /mnt/photos | cut -d, -f1     # ro
```

2. Copy `scripts/migrate/` and `work/<user>/` to the Pi. Install the service from `scripts/migrate/immich-migrate@.service`. Edit the paths in it. The service adds `--path-prefix "/Volumes/<disk>=/mnt/photos"` so the manifest's Mac paths resolve on the Pi.

```bash
sudo systemctl enable --now immich-migrate@<user>
grep '^\[' work/<user>.run.log | tail -1        # progress
```

3. Before the run, pause the queues that would fight the upload for the CPU: smart search, face detection, facial recognition, OCR, video conversion. Set thumbnail concurrency to 1. Resume after the run ([chapter 6](06-cleanup.md)).

Our run: two libraries at once, two workers each, about one day per terabyte, zero errors, Pi at 47 to 68 °C.

## 5.6 After the run

1. `python3 fix_metadata.py` finds assets whose metadata job timed out and queues a refresh. Multi-gigabyte videos time out under load.
2. Restore thumbnail concurrency to 3 and metadata to 5.
3. Run the machine-learning stages in order. Immich chains jobs only after an upload's thumbnail job. Re-queued jobs do not chain. Drive the stages yourself with `scripts/post/post_stages.sh`. The order: thumbnails, then smart search and face detection, then OCR and duplicate detection, then facial recognition with concurrency 1, then "Generate Thumbnails" in missing mode for the person thumbnails.
4. Reconcile faces and names ([chapter 6](06-cleanup.md)).
5. Disable the migration services. Delete the migration API keys when no script needs them.

## 5.7 What goes wrong

- **Damaged originals.** A handful of files per 100,000 were truncated in the source library already. Immich cannot thumbnail them and logs three errors every night. Find them with the thumbnail failure lines in the server log. Decide to repair or delete.
- **Live Photo mislinks** in families of same-named files. After the run, compare each still's Live Photo link (`livePhotoVideoId` from the API) with the clip the tool uploaded for it (`state.sqlite`, role `live_video`). Expect a few wrong links per 10,000 Live Photos, and fix them through the API.
- **Rotated originals with edits.** Face regions belong to the edited render when one exists. The tool handles that. Mirrored orientations are skipped.
- **"Missing" button.** Pressing it on a job page while the queue has a backlog adds every asset again. Empty the queue and re-queue once.
- **Tag changes rewrite sidecars.** Every tag added or removed through the API or the web app rewrites the asset's XMP sidecar and re-reads the metadata. Originals are untouched. Plan tagging after the migration, not during it.

## 5.8 Apple catalog facts

For maintainers of the tool. In `Photos.sqlite`:

- `ZASSET` is the asset table. `ZSAVEDASSETTYPE` 3 and 6 are own assets with files. 4 is a shared-album copy under `scopes/cloudsharing/data/`.
- Album membership sits in a join table `Z_<n>ASSETS`. The number differs per library. The tool finds it by name.
- Keywords: `ZKEYWORD` and a join table `Z_<n>KEYWORDS`.
- Originals: `originals/<X>/<UUID>.<ext>`. Live clip `<UUID>_3.mov`. RAW pair `<UUID>_4.cr2`. iPhone edit recipe `<UUID>_5.aae`.
- Renders: `resources/renders/<X>/<UUID>_1_201_a.jpeg|heic` for edited images, `_2_0_a.mov` for edited videos, `_2_100_a.mov` for edited Live clips.
- Face boxes are in the displayed frame with a bottom-left origin. The conversion to the stored frame follows osxphotos' formulas.
- Dates are Core Data timestamps: seconds since 2001-01-01 UTC. Some are corrupt. The tool falls back to the added date, then the file time.
