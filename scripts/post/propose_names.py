#!/usr/bin/env python3
"""Propose names for unnamed face clusters by comparing cluster centroids with the centroids of named people.

Both libraries use the same face model, so the centroid of one user's unnamed cluster can be compared with the
centroids of the other user's named people and vice versa. Same-owner candidates would be merges (geometry step missed them);
other-owner candidates are name proposals (the person is renamed, libraries stay separate). Dry run by default.
--apply renames/merges only candidates within --max-distance and with a margin of --margin to the runner-up.
"""
import argparse, collections, json, os
from common import api, load_owners, psql, read_key

OWN = load_owners()
OWNERS = {o["id"]: name for name, o in OWN.items()}   # user id -> short name

ap = argparse.ArgumentParser()
ap.add_argument("--min-faces", type=int, default=20, help="only clusters/people with at least this many embedded faces")
ap.add_argument("--max-distance", type=float, default=0.45, help="cosine distance between centroids to accept")
ap.add_argument("--margin", type=float, default=0.08, help="required gap to the second-best candidate")
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()

rows = psql(f'''
with c as (
  select p."ownerId", p."personGroupId" as gid, p.name, count(*) as n, avg(s.embedding) as centroid,
         (select count(distinct f2."assetId") from asset_face f2 where f2."personGroupId"=p."personGroupId" and f2."deletedAt" is null) as photos
  from person p
  join asset_face f on f."personGroupId"=p."personGroupId" and f."ownerId"=p."ownerId" and f."deletedAt" is null
  join face_search s on s."faceId"=f.id
  group by p."ownerId", p."personGroupId", p.name
  having count(*) >= {args.min_faces}),
u as (select * from c where name = ''), nm as (select * from c where name <> '')
select u."ownerId", u.gid, u.n, u.photos, nm."ownerId", nm.gid, nm.name, nm.n, round((u.centroid <=> nm.centroid)::numeric, 3)
from u cross join nm order by u.gid, 9''')

cands = collections.defaultdict(list)
for uo, ugid, un, uphotos, no, ngid, nname, nn, dist in rows:
    cands[(uo, ugid, int(un), int(uphotos))].append((float(dist), no, ngid, nname, int(nn)))

accepted, rejected = [], []
for (uo, ugid, un, uphotos), lst in sorted(cands.items(), key=lambda kv: -kv[0][3]):
    lst.sort(); best = lst[0]; second = lst[1][0] if len(lst) > 1 else 9
    ok = best[0] <= args.max_distance and (second - best[0]) >= args.margin
    kind = "merge" if best[1] == uo else "rename"
    rec = {"owner": OWNERS[uo], "cluster": ugid, "faces": un, "photos": uphotos, "kind": kind, "name": best[3],
           "named_owner": OWNERS[best[1]], "named_gid": best[2], "distance": best[0], "runner_up": lst[1][3] if len(lst) > 1 else "", "runner_up_distance": second}
    (accepted if ok else rejected).append(rec)

print(f"unnamed clusters with >= {args.min_faces} faces: {len(cands)}; accepted {len(accepted)}, rejected {len(rejected)}")
print("ACCEPTED (owner | cluster photos | kind | name | distance | runner-up):")
for r in accepted:
    print(f"  {r['owner']:5} | {r['photos']:6d} photos | {r['kind']:6} | {r['name']:<28} | {r['distance']:.3f} | {r['runner_up']} {r['runner_up_distance']:.3f}")
print("REJECTED, closest guess (owner | photos | name | distance | runner-up distance):")
for r in rejected[:40]:
    print(f"  {r['owner']:5} | {r['photos']:6d} photos | {r['name']:<28} | {r['distance']:.3f} | {r['runner_up_distance']:.3f}")
os.makedirs("work", exist_ok=True)
json.dump({"accepted": accepted, "rejected": rejected}, open("work/name_proposals.json", "w"), indent=1)

if args.apply:
    keys = {name: read_key(OWN[name]["key_file"]) for name in OWNERS.values()}
    owner_id = {v: k for k, v in OWNERS.items()}
    # existing named people per owner, so a proposed name that already exists becomes a merge instead of a duplicate
    existing = {}
    for oid, gid, name in psql("select \"ownerId\", \"personGroupId\", name from person where name <> ''"):
        existing[(OWNERS[oid], name)] = gid
    for r in sorted(accepted, key=lambda r: -r["photos"]):          # largest cluster of a name goes first
        key = keys[r["owner"]]
        target = existing.get((r["owner"], r["name"])) if r["kind"] == "rename" else r["named_gid"]
        if target and target != r["cluster"]:
            res = api("POST", f"/people/{target}/merge", key, {"ids": [r["cluster"]]})
            ok = bool(res) and res[0].get("success")
            print(f"merged  {r['owner']:5} {r['photos']:6d} photos -> {r['name']}" + ("" if ok else f"  FAILED {res}"))
        else:
            res = api("PUT", f"/people/{r['cluster']}", key, {"name": r["name"]})
            ok = bool(res) and res.get("name") == r["name"]
            print(f"renamed {r['owner']:5} {r['photos']:6d} photos -> {r['name']}" + ("" if ok else f"  FAILED {res}"))
            if ok:
                existing[(r["owner"], r["name"])] = r["cluster"]
