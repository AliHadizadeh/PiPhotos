#!/usr/bin/env python3
"""Find migrated assets whose metadata job failed (no time zone recorded although every migrated file carries a
sidecar with an offset) and queue a metadata refresh for them. Run after the migration when the Pi is idle.

  python3 fix_metadata.py --api-key-file ~/.config/immich-tools/<user>.key --server http://<pi>:2283 [--dry-run]
"""
import argparse, os
from immich_client import ImmichClient

ap = argparse.ArgumentParser()
ap.add_argument("--api-key-file", required=True)
ap.add_argument("--server", default=os.environ.get("IMMICH_SERVER", "http://localhost:2283"))
ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()
c = ImmichClient(a.server, open(os.path.expanduser(a.api_key_file)).read().strip())
me = c.me()
missing, total, page = [], 0, 1
while True:
    res = c.request("POST", "/search/metadata", json_body={"page": page, "size": 1000, "withExif": True})
    items = res.get("assets", {}).get("items", [])
    for asset in items:
        total += 1
        ex = asset.get("exifInfo") or {}
        if asset.get("ownerId") == me["id"] and not ex.get("timeZone"):
            missing.append((asset["id"], asset.get("originalFileName")))
    nxt = res.get("assets", {}).get("nextPage")
    if not nxt:
        break
    page = int(nxt)
print(f"{me['name']}: {total} assets scanned, {len(missing)} without a time zone (metadata not applied)")
for aid, name in missing[:15]:
    print("  ", name)
if missing and not a.dry_run:
    ids = [m[0] for m in missing]
    for i in range(0, len(ids), 500):
        c.request("POST", "/assets/jobs", json_body={"assetIds": ids[i:i + 500], "name": "refresh-metadata"})
    print(f"queued refresh-metadata for {len(ids)} assets")
