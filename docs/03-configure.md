# 3. Configure Immich

Time: 1 hour. Do this before the first upload. Some settings cannot be changed later without redoing work.

## 3.1 Settings we changed, and why

Open Administration, Settings. Change these:

| Setting | Default | Set to | Why |
|---|---|---|---|
| Storage Template: enabled | off | **on**, template `{{y}}/{{MM}}/{{dd}}/{{filename}}` | Files on disk sit in date folders. You can browse the disk without Immich. Set this before any upload, or Immich moves every file later. |
| Metadata: face import | off | **on** | Named faces from Apple Photos arrive as XMP regions. Without this, the names are lost. |
| Machine learning: smart search model | `ViT-B-32__openai` | `ViT-B-16-SigLIP2__webli` | Better recall and multilingual search. We measured 85 % against 70 %. Decide now: a later change re-embeds every photo. |
| Video transcoding: accepted video codecs | h264 | **h264, hevc** | iPhones record HEVC. Apple devices play it. Transcoding it wastes days of CPU. |
| Video transcoding: accepted containers | mov, ogg, webm | **plus mp4** | Same reason. |
| Video transcoding: policy | required | required (keep) | See the warning below. |
| Job concurrency: face detection, smart search | 2, 2 | 4, 4 with a GPU machine, 1, 1 on the Pi alone | The Pi's CPU cannot feed more. |
| Job concurrency: thumbnails, metadata | 3, 5 | 1, 1 during a migration, then back to 3, 5 | Thumbnails and metadata compete with the upload for the CPU. |
| Server: external domain | empty | your Tailscale address, see [chapter 7](07-remote-access.md) | Links in emails and shares use it. |
| Backup: database dump | 02:00, keep 14 | keep | The dumps are the only copy of albums, people, tags and stacks. [Chapter 8](08-backup.md) copies them off the disk. |
| Trash: days | 30 | keep | A deleted photo stays restorable for 30 days. The backup then keeps it about 13 more weeks, [chapter 8.7](08-backup.md). |

**Warning about the "required" transcode policy.** It also transcodes every video whose pixel format is not 8-bit 4:2:0. Modern iPhones record 10-bit HDR. On a Pi that is two days of CPU for 8 hours of footage, for no playback gain on Apple devices. Chapter 6 shows how to transcode only what needs it. Never press "Missing" or "All" on the Video Conversion job. It re-queues every HDR clip.

## 3.2 Per-user settings

Each user opens Account Settings, Features:

- **Tags: on**, with the sidebar entry. Keywords from Photos become tags.
- **Folders: on**, with the sidebar entry. Folders show the date layout on disk.
- **Ratings: on** if you used stars in Photos.
- **People: shown from 3 faces.** Fewer shows hundreds of strangers from group photos.
- **Email notifications** as you like. Immich emails album invitations and updates only.

## 3.3 Partner sharing

Two family members, two accounts, one library each. Each user shares with the other under Account Settings, Sharing. Keep "show in timeline" off, or every photo appears twice.

## 3.4 The phone app

Settings we use in the Immich app on each phone. Find them under Settings.

**Backup**

- Enable Backup: on.
- Backup albums: Recents (All). Excluded: Screenshots, Screen Recordings.
- Original quality. Over Wi-Fi only if your mobile plan is small.

**Asset Viewer**

- Load original image: **on**. The viewer loads the thumbnail, then the preview, then the full original. Full quality on the phone, at the cost of data and cache. Turn it off on a slow link.
- Tap to navigate: off.
- Auto play videos: on. Looping: on.
- Force original video: off. The transcode plays when one exists, the original otherwise.
- Repeat slideshow: on.

**Networking**: see [chapter 7](07-remote-access.md). The app switches between the home address and the Tailscale address by itself.

## 3.5 Settings by script

The admin UI writes the whole settings object at once. So does `scripts/ml/set_remote_ml.py`. Use it for machine-learning addresses, the search model and job concurrency:

```bash
python3 scripts/ml/set_remote_ml.py --server http://localhost:2283 --api-key-file ~/.config/immich-tools/admin.key \
  --clip-model ViT-B-16-SigLIP2__webli --concurrency faceDetection=4 --concurrency smartSearch=4 --dry-run
```

Drop `--dry-run` to save. The script prints every change before it saves.

## 3.6 Record your settings

Save the difference between your settings and the defaults. You will want it after a reinstall:

```bash
KEY=$(cat ~/.config/immich-tools/admin.key)
curl -s -H "x-api-key: $KEY" http://localhost:2283/api/system-config > my-settings.json
curl -s -H "x-api-key: $KEY" http://localhost:2283/api/system-config/defaults > defaults.json
```

Keep `my-settings.json` with your backup. It contains no passwords unless you configured email.

## 3.7 Things not to touch

- Do not press "Missing" or "All" on any job page while a queue has a backlog. It adds the whole library again.
- Do not press "Delete reports" on the integrity page while reports are stale. It can trash the assets behind missing-file reports.
- Do not run "Regenerate people" on a shared person group. It resets every machine-learning person.
