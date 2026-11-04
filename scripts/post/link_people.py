#!/usr/bin/env python3
"""Join two users into one cluster group, share every named person both ways, and link each of the guest's named
people to the host's matching person (by face-centroid similarity) so the same person is one entry in both libraries.
Usage: link_people.py --host alice --guest bob [--apply]   (names from owners.json; the guest joins the host's group)
Each user keeps their own display name for a linked person (Immich keeps one person row per user per group).
Dry run by default; --apply performs the changes through the API with each owner's key."""
import argparse
from common import api_status, load_owners, psql, read_key
ap = argparse.ArgumentParser(); ap.add_argument("--host", required=True); ap.add_argument("--guest", required=True)
ap.add_argument("--apply", action="store_true"); ap.add_argument("--role", default="write"); args = ap.parse_args()
OWN = load_owners()
HOST, GUEST = OWN[args.host]["id"], OWN[args.guest]["id"]          # host and guest user ids
HOSTN, GUESTN = OWN[args.host]["display"], OWN[args.guest]["display"]
KEYS = {HOST: read_key(OWN[args.host]["key_file"]), GUEST: read_key(OWN[args.guest]["key_file"])}

def api(method, path, user, body=None):
    return api_status(method, path, KEYS[user], body)

# 1. cluster group
users = {u["id"]: u for u in api("GET", "/admin/users", HOST)[1]}
host_cg, guest_cg = users[HOST]["clusterGroupId"], users[GUEST]["clusterGroupId"]
print(f"cluster groups: {HOSTN} {host_cg}  {GUESTN} {guest_cg}  -> {'already shared' if host_cg == guest_cg else 'different: the guest will join the host'}")
if args.apply and host_cg != guest_cg:
    st, req = api("PUT", f"/cluster-groups/{host_cg}/requests", HOST, {"userId": GUEST}); print("  invite:", st, req)
    pending = api("GET", "/cluster-groups/requests", GUEST)[1]
    for r in pending:
        if r["clusterGroupId"] == host_cg:
            st, _ = api("POST", f"/cluster-groups/requests/{r['id']}/accept", GUEST); print("  accept:", st)
    st, members = api("GET", f"/cluster-groups/{host_cg}/users", HOST); print("  members now:", [m["name"] for m in members] if st == 200 else members)

# 2. share named people both ways
named = {}
for user in (HOST, GUEST):
    people = []
    page = 1
    while True:
        st, d = api("GET", f"/people?size=1000&page={page}&withHidden=true", user)
        people += [p for p in d["people"] if p["name"]]
        if len(d["people"]) < 1000: break
        page += 1
    named[user] = {p["id"]: p["name"] for p in people}
print(f"named people: {HOSTN} {len(named[HOST])}, {GUESTN} {len(named[GUEST])}")
if args.apply:
    for user, other in ((HOST, GUEST), (GUEST, HOST)):
        st, d = api("PUT", "/people/users", user, {"personIds": list(named[user]), "sharedWithIds": [other], "role": args.role})
        print(f"  share {len(named[user])} people of {users[user]['name']} with {users[other]['name']} (role {args.role}): http {st}" + ("" if st in (200, 201, 204) else f" {d}"))

# 3. pairs by face-centroid similarity (the guest's named person -> closest host named person)
rows = psql(f'''with c as (select p."ownerId", p."personGroupId" gid, p.name, avg(s.embedding) centroid
  from person p join asset_face f on f."personGroupId"=p."personGroupId" and f."ownerId"=p."ownerId" and f."deletedAt" is null
  join face_search s on s."faceId"=f.id where p.name<>'' group by 1,2,3),
 a as (select * from c where "ownerId"='{HOST}'), n as (select * from c where "ownerId"='{GUEST}'),
 best as (select n.gid ngid, n.name nname, a.gid agid, a.name aname, (n.centroid <=> a.centroid) dist,
          row_number() over (partition by n.gid order by n.centroid <=> a.centroid) rn from n cross join a)
 select ngid, nname, agid, aname, round(dist::numeric,3),
   (select round(min(n2.centroid <=> a2.centroid)::numeric,3) from n n2 cross join a a2 where n2.gid=best.ngid and a2.gid<>best.agid) runner
 from best where rn=1 and ngid <> agid order by nname''')
pairs = [(ng, nn, ag, an, float(d), float(r)) for ng, nn, ag, an, d, r in rows if float(d) < 0.2 and float(r) - float(d) > 0.3]
print(f"link candidates: {len(pairs)} of {len(rows)} (distance < 0.2 and clear runner-up)")
for ng, nn, ag, an, d, r in pairs:
    print(f"  {GUESTN} '{nn}'  ->  {HOSTN} '{an}'   d={d:.3f} runner-up={r:.3f}")
if args.apply:
    done = 0
    for ng, nn, ag, an, d, r in pairs:
        st, res = api("POST", "/people/merge", HOST, {"ids": [ag, ng]})
        ok = st == 200 and all(x.get("success") for x in res)
        done += ok
        if not ok: print(f"  FAILED {nn} -> {an}: http {st} {res}")
    print(f"linked: {done}/{len(pairs)}")
    # 4. verify
    for user in (HOST, GUEST):
        st, d = api("GET", "/people?size=1&withHidden=true", user)
        st2, shares = api("GET", "/people/users", user)
        print(f"  {users[user]['name']}: people total {d['total']}, hidden {d['hidden']}; sharing records {len(shares) if st2 == 200 else shares}")
    print("  group rows per linked group (should be 2):", psql('''select count(*) from (select "personGroupId" from person group by 1 having count(*)=2) g''')[0][0])
