#!/usr/bin/env python3
"""Tag duplicates across two Immich accounts. Tags only: no file is moved, linked or deleted.

Three classes, the strongest one wins per asset:
  identical  same bytes (Immich checksum) in both libraries
  same_shot  same capture second, camera model and pixel size but a different file;
             images must also be visually close (CLIP distance < --same-shot-distance), videos must have the same duration
  visual     CLIP distance < --max-distance (0.01 is Immich's own duplicate threshold); images only
Each user's copies get the tag "Also in <other user>'s library/<class>". The two users are the first two entries
of owners.json (see common.py), or --owners a,b.
Sync semantics: adds the tag where it is missing and removes it from assets whose counterpart no longer exists,
so the script can be re-run after phone backups add new shared photos.

  ./cross_dup_tags.py            dry run: compute pairs, write work/cross_dups.tsv, print what would change
  ./cross_dup_tags.py --apply    the same, then write the tags through the API with each owner's key
  ./cross_dup_tags.py --reuse    skip the 10-minute pair computation and reuse work/cross_dups.tsv
Reads the database through docker exec (read-only queries); all writes go through the Immich API.
"""
import argparse
import os
import sys
import time
from collections import defaultdict

from common import api as _api, load_owners, psql, read_key

OWN = {}          # set in main() from owners.json
A = B = None      # the two user names
USERS = {}        # name -> user id
PARENT = {}       # name -> parent tag
LEAF = {"identical": "Identical file", "same_shot": "Same shot", "visual": "Looks identical"}
RANK = {"identical": 3, "same_shot": 2, "visual": 1}
WORK = os.environ.get("WORK_DIR", "work")
CACHE = os.path.join(WORK, "cross_dups.tsv")
BATCH = 500

PAIRS_SQL = """
with
n as (select a.id, a.type, a.checksum, a.duration from asset a
      where a."ownerId" = '%(a)s' and a."deletedAt" is null and a.visibility in ('timeline', 'archive')),
al as (select a.id, a.type, a.checksum, a.duration from asset a
       where a."ownerId" = '%(b)s' and a."deletedAt" is null and a.visibility in ('timeline', 'archive')),
ident as (
  select n.id as nid, al.id as aid, 'identical' as kind from n join al on al.checksum = n.checksum),
same_shot as (
  select n.id as nid, al.id as aid, 'same_shot' as kind
  from n
  join asset_exif ne on ne."assetId" = n.id
  join asset_exif ae on ae."dateTimeOriginal" = ne."dateTimeOriginal"
                    and ae."exifImageWidth" = ne."exifImageWidth" and ae."exifImageHeight" = ne."exifImageHeight"
                    and coalesce(ae.model, '') = coalesce(ne.model, '')
  join al on al.id = ae."assetId" and al.type = n.type and al.checksum <> n.checksum
  where ne."dateTimeOriginal" is not null and ne."exifImageWidth" is not null and ne."exifImageHeight" is not null
    and ((n.type = 'VIDEO' and n.duration is not null and n.duration = al.duration)
      or (n.type = 'IMAGE' and exists (select 1 from smart_search sn join smart_search sa on sa."assetId" = al.id
                                       where sn."assetId" = n.id and sn.embedding <=> sa.embedding < %(same)s)))),
visual as (
  select n.id as nid, k."assetId" as aid, 'visual' as kind
  from n
  join smart_search sn on sn."assetId" = n.id
  cross join lateral (select s."assetId", s.embedding <=> sn.embedding as d
                      from smart_search s order by s.embedding <=> sn.embedding limit %(k)d) k
  join al on al.id = k."assetId" and al.type = 'IMAGE'
  where n.type = 'IMAGE' and k.d < %(vis)s),
pairs as (select * from ident union all select * from same_shot union all select * from visual)
select p.nid, p.aid, p.kind, coalesce(e."fileSizeInByte", 0)
from pairs p left join asset_exif e on e."assetId" = p.nid;
"""

CURRENT_SQL = """
select u.id, t.value, ta."assetId"
from tag t join "user" u on u.id = t."userId" join tag_asset ta on ta."tagId" = t.id
where t.value like 'Also in %%''s library/%%';
"""


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def key(user):
    return read_key(OWN[user]["key_file"])


def api(method, path, user, body=None):
    return _api(method, path, key(user), body)


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def compute_pairs(args):
    log("computing pairs (the visual pass takes about 10 minutes)")
    rows = psql(PAIRS_SQL % dict(a=USERS[A], b=USERS[B], same=args.same_shot_distance,
                                 vis=args.max_distance, k=args.knn))
    os.makedirs(WORK, exist_ok=True)
    with open(CACHE, "w") as f:
        f.write(f"{A}_asset\t{B}_asset\tkind\t{A}_bytes\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    log(f"{len(rows)} pairs written to {CACHE}")
    return rows


def load_pairs():
    with open(CACHE) as f:
        next(f)
        return [line.rstrip("\n").split("\t") for line in f if line.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the tags (default: dry run)")
    ap.add_argument("--reuse", action="store_true", help="reuse work/cross_dups.tsv instead of recomputing")
    ap.add_argument("--max-distance", type=float, default=0.01, help="CLIP distance for 'Looks identical' (default 0.01)")
    ap.add_argument("--same-shot-distance", type=float, default=0.05, help="CLIP guard for 'Same shot' images (default 0.05)")
    ap.add_argument("--knn", type=int, default=20, help="nearest neighbours examined per photo (default 20)")
    ap.add_argument("--owners", help="the two user names from owners.json, comma separated (default: the first two)")
    args = ap.parse_args()
    global OWN, A, B, USERS, PARENT
    OWN = load_owners()
    A, B = (args.owners.split(",") if args.owners else list(OWN)[:2])
    USERS = {A: OWN[A]["id"], B: OWN[B]["id"]}
    PARENT = {A: f"Also in {OWN[B]['display']}'s library", B: f"Also in {OWN[A]['display']}'s library"}
    id_to_name = {v: k for k, v in USERS.items()}

    pairs = load_pairs() if args.reuse and os.path.exists(CACHE) else compute_pairs(args)

    # strongest class per asset, on both sides
    cls = {}
    per_kind = defaultdict(int)
    a_bytes = defaultdict(int)
    seen_n = set()
    for nid, aid, kind, nbytes in pairs:
        per_kind[kind] += 1
        for owner, asset_id in ((A, nid), (B, aid)):
            cur = cls.get(asset_id)
            if cur is None or RANK[kind] > RANK[cur[1]]:
                cls[asset_id] = (owner, kind)
    for nid, aid, kind, nbytes in pairs:
        if nid not in seen_n:
            seen_n.add(nid)
            a_bytes[cls[nid][1]] += int(nbytes)
    desired = defaultdict(set)
    for asset_id, (owner, kind) in cls.items():
        desired[(owner, kind)].add(asset_id)

    current = defaultdict(set)
    for owner_id, value, asset_id in psql(CURRENT_SQL):
        owner = id_to_name.get(owner_id)
        if not owner:
            continue
        leaf = value.split("/", 1)[1] if "/" in value else ""
        kind = next((k for k, v in LEAF.items() if v == leaf), None)
        if kind:
            current[(owner, kind)].add(asset_id)

    print(f"pairs: " + ", ".join(f"{k} {per_kind[k]:,}" for k in RANK) + f"  (total {len(pairs):,})")
    print(f"{OWN[A]['display']}'s copies by class: " + ", ".join(
        f"{LEAF[k]} {len(desired[(A, k)]):,} ({a_bytes[k] / 2 ** 30:.1f} GB)" for k in RANK))
    print(f"{OWN[B]['display']}'s copies by class: " + ", ".join(f"{LEAF[k]} {len(desired[(B, k)]):,}" for k in RANK))
    plan = {}
    for owner in USERS:
        for kind in RANK:
            add = sorted(desired[(owner, kind)] - current[(owner, kind)])
            rem = sorted(current[(owner, kind)] - desired[(owner, kind)])
            plan[(owner, kind)] = (add, rem)
            print(f"{owner:>5} / {PARENT[owner]}/{LEAF[kind]}: have {len(current[(owner, kind)]):,}, add {len(add):,}, remove {len(rem):,}")

    if not args.apply:
        print("dry run; nothing written (use --apply)")
        return

    for owner in USERS:
        values = [f"{PARENT[owner]}/{LEAF[k]}" for k in RANK]
        created = api("PUT", "/tags", owner, {"tags": values})
        tag_id = {t["value"]: t["id"] for t in created}
        missing = [v for v in values if v not in tag_id]
        if missing:  # upsert may only return part of the hierarchy; fall back to the full list
            tag_id.update({t["value"]: t["id"] for t in api("GET", "/tags", owner) if t["value"] in values})
        for kind in RANK:
            value = f"{PARENT[owner]}/{LEAF[kind]}"
            add, rem = plan[(owner, kind)]
            ok = dup = err = 0
            for batch in chunks(add, BATCH):
                for r in api("PUT", f"/tags/{tag_id[value]}/assets", owner, {"ids": batch}):
                    if r.get("success"):
                        ok += 1
                    elif r.get("error") == "duplicate":
                        dup += 1
                    else:
                        err += 1
            removed = 0
            for batch in chunks(rem, BATCH):
                for r in api("DELETE", f"/tags/{tag_id[value]}/assets", owner, {"ids": batch}):
                    removed += bool(r.get("success"))
            log(f"{owner} / {value}: tagged {ok:,} (already {dup:,}, errors {err:,}), untagged {removed:,}")

    print("--- tag counts now:")
    for owner_name, value, n in psql("""select u.name, t.value, count(ta."assetId") from tag t join "user" u on u.id = t."userId"
                                        left join tag_asset ta on ta."tagId" = t.id
                                        where t.value like 'Also in %''s library%' group by 1, 2 order by 1, 2"""):
        print(f"  {owner_name:>5}  {value:<45} {int(n):>7,}")


if __name__ == "__main__":
    main()
