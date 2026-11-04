#!/usr/bin/env python3
"""Queue transcode-video jobs only for the assets probe_videos.py classed as 'transcode' (first) and 'remux' (last),
using each owner's API key. Immich's 'required' policy then decides the exact ffmpeg command per asset."""
import csv, sys, collections
from common import api_status, load_owners, read_key
OWN = load_owners()
OWNERS = {o["id"][:8]: name for name, o in OWN.items()}   # probe_videos.py stores the first 8 characters of the owner id
keys = {name: read_key(OWN[name]["key_file"]) for name in OWNERS.values()}
def api(method, path, key, body):
    return api_status(method, path, key, body, timeout=120)[0]
rows = list(csv.DictReader(open(sys.argv[1] if len(sys.argv) > 1 else "work/video_probe.tsv"), delimiter="\t"))
queued = collections.Counter()
for cls in ("transcode", "remux"):
    for owner8, name in OWNERS.items():
        ids = [r["id"] for r in rows if r["class"] == cls and r["owner"] == owner8]
        for i in range(0, len(ids), 200):
            st = api("POST", "/assets/jobs", keys[name], {"name": "transcode-video", "assetIds": ids[i:i + 200]})
            if st not in (200, 201, 204):
                sys.exit(f"queueing failed for {name} {cls}: http {st}")
        queued[(cls, name)] = len(ids)
print("queued:", dict(queued), "total", sum(queued.values()))
