#!/usr/bin/env python3
"""Merge unnamed machine-learning people into the named people imported from Apple Photos.

Immich only attached an ML detection to an imported (exif) face when the boxes overlapped by IoU > 0.5, which
Apple's region boxes rarely do, so most named people also exist as separate unnamed ML clusters. Here an ML face
matches an imported face when their centres (normalised to the image) are within max(6 %, half the ML box size).
An unnamed cluster is merged into the named person that most of its matched faces belong to, when the evidence is
unambiguous. Dry run by default; --apply merges through POST /api/people/{named}/merge with the owner's API key.
"""
import argparse, collections, json, math, os
from common import api, load_owners, psql, read_key

OWN = load_owners()
OWNERS = {o["id"]: name for name, o in OWN.items()}   # user id -> short name

ap = argparse.ArgumentParser()
ap.add_argument("--min-matches", type=int, default=3, help="matched faces needed to merge a cluster")
ap.add_argument("--purity", type=float, default=0.8, help="share of a cluster's matched faces that must point at one person")
ap.add_argument("--apply", action="store_true")
ap.add_argument("--out", default="work/reconcile_plan.json")
args = ap.parse_args()

people = {}   # personGroupId -> (ownerId, name)
for gid, owner, name in psql('select "personGroupId", "ownerId", name from person'):
    people[gid] = (owner, name)
named = {gid for gid, (o, n) in people.items() if n}

faces = collections.defaultdict(lambda: {"exif": [], "ml": []})
rows = psql('''select f."assetId", f."sourceType", f."personGroupId", f."imageWidth", f."imageHeight",
                      f."boundingBoxX1", f."boundingBoxY1", f."boundingBoxX2", f."boundingBoxY2"
               from asset_face f where f."deletedAt" is null and f."personGroupId" is not null''')
cluster_size = collections.Counter()
for aid, st, gid, w, h, x1, y1, x2, y2 in rows:
    w, h = float(w), float(h); x1, y1, x2, y2 = map(float, (x1, y1, x2, y2))
    item = (gid, (x1 + x2) / 2 / w, (y1 + y2) / 2 / h, max((x2 - x1) / w, (y2 - y1) / h))
    if st == "exif":
        faces[aid]["exif"].append(item)
    else:
        faces[aid]["ml"].append(item); cluster_size[gid] += 1

votes = collections.defaultdict(collections.Counter)   # unnamed gid -> Counter(named gid)
for aid, d in faces.items():
    if not d["exif"] or not d["ml"]:
        continue
    for gid, mx, my, msize in d["ml"]:
        if gid in named:
            continue
        best, bestd = None, 1e9
        for egid, ex, ey, _ in d["exif"]:
            dist = math.hypot(ex - mx, ey - my)
            if dist < bestd:
                best, bestd = egid, dist
        if best is not None and bestd < max(0.06, 0.5 * msize) and best in named:
            votes[gid][best] += 1

plan = collections.defaultdict(list)   # named gid -> [unnamed gids]
skipped = collections.Counter(); merged_faces = 0
for gid, counter in votes.items():
    total = sum(counter.values()); (top, n), *rest = counter.most_common()
    owner = people[gid][0]
    if people[top][0] != owner:
        skipped["other owner"] += 1; continue
    if n < args.min_matches:
        skipped["too few matches"] += 1; continue
    if n / total < args.purity:
        skipped["mixed cluster"] += 1; continue
    plan[top].append(gid); merged_faces += cluster_size[gid]

print(f"people: {len(people)} ({len(named)} named); unnamed clusters with any match: {len(votes)}")
print(f"merges planned: {sum(len(v) for v in plan.values())} clusters ({merged_faces} ML faces) into {len(plan)} named people; skipped: {dict(skipped)}")
for top, gids in sorted(plan.items(), key=lambda kv: -sum(cluster_size[g] for g in kv[1]))[:25]:
    print(f"  {people[top][1]:<28} <- {len(gids):3d} clusters, {sum(cluster_size[g] for g in gids):6d} ML faces (largest {max(cluster_size[g] for g in gids)})")
os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
json.dump({top: gids for top, gids in plan.items()}, open(args.out, "w"), indent=1)
print("plan written to", args.out)

if args.apply:
    keys = {name: read_key(OWN[name]["key_file"]) for name in OWNERS.values()}
    done = 0
    for top, gids in plan.items():
        key = keys[OWNERS[people[top][0]]]
        for i in range(0, len(gids), 50):
            res = api("POST", f"/people/{top}/merge", key, {"ids": gids[i:i + 50]})
            ok = sum(1 for r in res if r.get("success"))
            bad = [r for r in res if not r.get("success")]
            done += ok
            if bad:
                print("  failed:", people[top][1], bad[:3])
    print(f"applied: {done} clusters merged")
