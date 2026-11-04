#!/usr/bin/env python3
"""Pick a small, representative test set from a manifest: Live Photos, edited photos with faces, RAW pairs, a burst,
videos, captions, keywords, albums, different time zones. Writes one UUID per line (with a comment describing why)."""
import json, sys, collections

manifest, out = sys.argv[1], sys.argv[2]
recs = [json.loads(l) for l in open(manifest)]
bursts = collections.defaultdict(list)
for r in recs:
    if r.get("burst"):
        bursts[r["burst"]["id"]].append(r)
picked, reasons = [], []

def pick(label, pred, n=1):
    got = 0
    for r in recs:
        if r["uuid"] in picked:
            continue
        if pred(r):
            picked.append(r["uuid"]); reasons.append(f"{r['uuid']}  # {label}: {r.get('original_name')} {r.get('created_local')}")
            got += 1
            if got >= n:
                return

pick("live photo with faces, unedited", lambda r: r.get("live_video") and r["faces"] and not r.get("edited"))
pick("edited photo with faces on the render", lambda r: r.get("edited") and r["edited"].get("image") and r.get("faces_target") == "edited")
pick("edited live photo", lambda r: r.get("edited") and r["edited"].get("live_video"))
pick("edited video", lambda r: r.get("edited") and r["edited"].get("video"))
pick("raw+jpeg pair", lambda r: r.get("raw_alt"))
pick("raw original (cr2/dng)", lambda r: r["original"].lower().endswith((".cr2", ".dng")) and not r.get("edited"))
pick("plain video", lambda r: r["kind"] == "video" and not r.get("edited"))
pick("rotated original (orientation 6/8) with faces", lambda r: r.get("orientation") in (6, 8) and r.get("faces_target") == "original")
pick("caption + keywords", lambda r: r.get("caption") and r.get("keywords"))
pick("favorite", lambda r: r.get("favorite"))
common_tz = collections.Counter(r.get("tz_offset") for r in recs).most_common(1)[0][0]
pick("time zone different from the usual one", lambda r: r.get("tz_offset") is not None and r.get("tz_offset") != common_tz)
pick("fallback time zone", lambda r: r.get("tz_source") == "fallback")
pick("old scanned photo (pre-2005)", lambda r: (r.get("created_local") or "9") < "2005")
pick("png / screenshot", lambda r: r["original"].lower().endswith(".png"))
for bid, members in bursts.items():
    if 2 <= len(members) <= 6:
        for m in members:
            if m["uuid"] not in picked:
                picked.append(m["uuid"]); reasons.append(f"{m['uuid']}  # burst member {bid[:8]}: {m.get('original_name')}")
        break
with open(out, "w") as f:
    f.write("\n".join(reasons) + "\n")
print(f"{len(picked)} assets picked -> {out}")
print("\n".join(reasons))
