#!/usr/bin/env python3
"""After a test upload: show what Immich recorded for each uploaded asset (date, time zone, GPS, description, tags,
people/faces, live photo link, stack, albums), using the state database and the same API key."""
import argparse, os, sqlite3
from immich_client import ImmichClient

ap = argparse.ArgumentParser()
ap.add_argument("--state", required=True)
ap.add_argument("--api-key-file", required=True)
ap.add_argument("--server", default=os.environ.get("IMMICH_SERVER", "http://localhost:2283"))
ap.add_argument("--limit", type=int, default=50)
a = ap.parse_args()
c = ImmichClient(a.server, open(os.path.expanduser(a.api_key_file)).read().strip())
con = sqlite3.connect(a.state)
rows = con.execute("select key, role, immich_id, status from uploads order by ts limit ?", (a.limit,)).fetchall()
albums = {}
for al in c.albums():
    info = c.request("GET", f"/albums/{al['id']}")
    for asset in info.get("assets", []):
        albums.setdefault(asset["id"], []).append(al["albumName"])
for key, role, aid, status in rows:
    asset = c.get_asset(aid)
    ex = asset.get("exifInfo") or {}
    people = [(p.get("name") or "?") for p in asset.get("people") or []]
    tags = [t.get("value") or t.get("name") for t in asset.get("tags") or []]
    print(f"{role:17} {status:9} {asset.get('originalFileName')}")
    print(f"    taken {asset.get('localDateTime')} tz {ex.get('timeZone')}  gps {ex.get('latitude')},{ex.get('longitude')}  "
          f"{ex.get('city') or ''} {ex.get('country') or ''}")
    print(f"    type {asset.get('type')} favorite {asset.get('isFavorite')} visibility {asset.get('visibility')} "
          f"live-video {bool(asset.get('livePhotoVideoId'))} stack {'yes' if asset.get('stack') else 'no'}")
    if ex.get("description"): print(f"    description: {ex['description'][:80]!r}")
    if tags: print(f"    tags: {tags}")
    if people: print(f"    people: {people}")
    if albums.get(aid): print(f"    albums: {albums[aid]}")
