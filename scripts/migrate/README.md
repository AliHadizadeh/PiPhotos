# Migration tool

Standard-library Python 3. Nothing to install. Read [chapter 5](../../docs/05-migrate-apple-photos.md) first.

| File | Does |
|---|---|
| `photos_catalog.py` | reads a copy of `Photos.sqlite` and the library's files into `manifest.jsonl` plus albums, people, bursts, summary and skipped lists |
| `xmp_sidecar.py` | builds the XMP sidecar for one asset: date with offset, GPS, description, keywords, named face regions |
| `immich_client.py` | small Immich API client with streaming uploads and retries |
| `migrate.py` | uploads, links Live Photos, stacks, sets favorites, builds albums; resumable through `work/<user>/state.sqlite` |
| `pick_test_set.py` | picks 15 assets that cover the tricky cases |
| `verify_assets.py` | prints what Immich recorded for the test set |
| `fix_metadata.py` | queues a metadata refresh for assets whose metadata job timed out |
| `immich-migrate@.service` | systemd template to run a migration unattended on the Pi |

Order: catalog, dry run, test set, verify, full run, fix_metadata. The chapter has the commands.

Set `IMMICH_SERVER` or pass `--server`. Keys live in files under `~/.config/immich-tools/`, mode 600. Never pass a key on the command line.
