#!/usr/bin/env python3
"""Upload a photos_catalog manifest into Immich.

For every own asset: the original (with its Live Photo video linked, favorites and hidden state applied, and an XMP
sidecar carrying date, time zone, GPS, caption, keywords and named faces), the RAW counterpart of a RAW+JPEG pair,
and the edited render when the photo was edited in Photos (stacked over the original with the edit on top).
Then albums (folder / album paths) and burst stacks. Everything is recorded in a state database so a run can be
stopped and resumed; Immich's own checksum check makes re-uploads harmless.

Usage:
  python3 migrate.py --manifest work/<user>/manifest.jsonl --api-key-file ~/.config/immich-tools/<user>.key --server http://<pi>:2283
                     [--state work/<user>/state.sqlite] [--dry-run] [--limit N] [--uuid UUID] [--album NAME] [--workers 2]
                     [--skip-albums] [--skip-stacks] [--hash] [--report]
"""
import argparse, collections, concurrent.futures as cf, json, os, sqlite3, sys, threading, time
from immich_client import ImmichClient, ApiError, sha1_file
from xmp_sidecar import build_xmp

MIME = {".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".heic": "image/heic", ".heif": "image/heif", ".png": "image/png",
        ".gif": "image/gif", ".tiff": "image/tiff", ".tif": "image/tiff", ".cr2": "image/x-canon-cr2", ".dng": "image/x-adobe-dng",
        ".arw": "image/x-sony-arw", ".webp": "image/webp", ".bmp": "image/bmp", ".mov": "video/quicktime", ".mp4": "video/mp4",
        ".m4v": "video/x-m4v", ".avi": "video/x-msvideo", ".mpg": "video/mpeg", ".mpeg": "video/mpeg", ".3gp": "video/3gpp"}


class State:
    def __init__(self, path):
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.con:
            self.con.executescript("""
            create table if not exists uploads(key text primary key, uuid text, role text, immich_id text, status text, ts real);
            create index if not exists uploads_uuid on uploads(uuid);
            create table if not exists albums(name text primary key, immich_id text);
            create table if not exists album_members(name text, immich_id text, primary key(name, immich_id));
            create table if not exists stacks(key text primary key, stack_id text);
            create table if not exists errors(key text, message text, ts real);""")

    def _q(self, sql, *a):
        with self.lock, self.con:
            return self.con.execute(sql, a).fetchall()

    def upload(self, key):
        r = self._q("select immich_id, status from uploads where key=?", key)
        return r[0] if r else None

    def put_upload(self, key, uuid, role, immich_id, status):
        self._q("insert or replace into uploads values(?,?,?,?,?,?)", key, uuid, role, immich_id, status, time.time())

    def uploads_for(self, uuid):
        return {r[0]: r[1] for r in self._q("select role, immich_id from uploads where uuid=?", uuid)}

    def album(self, name):
        r = self._q("select immich_id from albums where name=?", name)
        return r[0][0] if r else None

    def set_album(self, name, immich_id):
        self._q("insert or replace into albums values(?,?)", name, immich_id)

    def members(self, name):
        return {r[0] for r in self._q("select immich_id from album_members where name=?", name)}

    def add_members(self, name, ids):
        with self.lock, self.con:
            self.con.executemany("insert or ignore into album_members values(?,?)", [(name, i) for i in ids])

    def stack(self, key):
        r = self._q("select stack_id from stacks where key=?", key)
        return r[0][0] if r else None

    def set_stack(self, key, stack_id):
        self._q("insert or replace into stacks values(?,?)", key, stack_id)

    def error(self, key, message):
        self._q("insert into errors values(?,?,?)", key, message[:2000], time.time())

    def report(self):
        print("uploads by role/status:", self._q("select role, status, count(*) from uploads group by 1,2"))
        print("albums:", self._q("select count(*) from albums")[0][0], " memberships:", self._q("select count(*) from album_members")[0][0],
              " stacks:", self._q("select count(*) from stacks")[0][0], " errors:", self._q("select count(*) from errors")[0][0])
        for r in self._q("select key, message from errors order by ts desc limit 10"):
            print("  error:", r[0], "->", r[1][:200])


class Migrator:
    def __init__(self, args):
        self.a = args
        self.state = State(args.state)
        self.dry = args.dry_run
        self.client = None if self.dry else ImmichClient(args.server, open(os.path.expanduser(args.api_key_file)).read().strip(), verbose=True)
        self.lock = threading.Lock()
        self.done, self.bytes, self.errors, self.t0 = 0, 0, 0, time.time()
        self.plan = collections.Counter()

    # ---- helpers -------------------------------------------------------
    @staticmethod
    def names(rec):
        base = rec.get("original_name") or os.path.basename(rec["original"])
        stem, ext = os.path.splitext(base)
        return base, (stem or rec["uuid"]), (ext or os.path.splitext(rec["original"])[1])

    @staticmethod
    def minimal(rec):
        return build_xmp({"created_local": rec.get("created_local"), "gps": rec.get("gps")})

    def upload_file(self, rec, role, path, filename, sidecar, live_id=None, favorite=None, visibility=None, duration_ms=None):
        key = f"{rec['uuid']}:{role}"
        prev = self.state.upload(key)
        if prev and prev[0]:
            return prev[0]
        if not os.access(path, os.R_OK):
            raise PermissionError(f"not readable: {path}")
        size = os.path.getsize(path)
        self.plan[f"upload:{role}"] += 1
        self.plan["bytes"] += size
        if self.dry:
            return f"dry:{key}"
        res = self.client.upload(path, filename, device_asset_id=key, device_id=self.a.device_id, created_at=rec["created_utc"],
                                 modified_at=rec.get("modified_utc") or rec["created_utc"], is_favorite=favorite, visibility=visibility,
                                 live_photo_video_id=live_id, duration_ms=duration_ms, sidecar=sidecar,
                                 checksum_hex=sha1_file(path) if self.a.hash else None,
                                 content_type=MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream"))
        self.state.put_upload(key, rec["uuid"], role, res["id"], res["status"])
        if res.get("status") == "duplicate" and favorite:
            try:
                self.client.update_asset(res["id"], isFavorite=True)
            except ApiError:
                pass
        with self.lock:
            self.bytes += size
        return res["id"]

    # ---- one asset -------------------------------------------------------
    def process(self, rec):
        base, stem, ext = self.names(rec)
        ids = {}
        dur = int(rec["duration"] * 1000) if rec.get("kind") == "video" and rec.get("duration") else None
        visibility = "archive" if rec.get("hidden") else None
        faces_on = rec.get("faces_target")
        if rec.get("live_video"):
            ids["live_video"] = self.upload_file(rec, "live_video", rec["live_video"], f"{stem}.mov", self.minimal(rec))
        ids["original"] = self.upload_file(rec, "original", rec["original"], base,
                                           build_xmp(rec, faces=rec["faces"] if faces_on == "original" else []),
                                           live_id=ids.get("live_video"), favorite=rec.get("favorite"), visibility=visibility, duration_ms=dur)
        if rec.get("raw_alt"):
            rext = os.path.splitext(rec["raw_alt"])[1]
            ids["raw_alt"] = self.upload_file(rec, "raw_alt", rec["raw_alt"], f"{stem}{rext}", self.minimal(rec), visibility=visibility)
        ed = rec.get("edited") or {}
        if rec.get("kind") == "video":
            ed = {"video": ed.get("video")}  # a video's image render is only its poster frame
        if ed.get("live_video") and ed.get("image"):
            ids["edited_live_video"] = self.upload_file(rec, "edited_live_video", ed["live_video"], f"{stem}_edited.mov", self.minimal(rec))
        if ed.get("image"):
            eext = os.path.splitext(ed["image"])[1]
            ids["edited"] = self.upload_file(rec, "edited_image", ed["image"], f"{stem}_edited{eext}",
                                             build_xmp(rec, faces=rec["faces"] if faces_on == "edited" else []),
                                             live_id=ids.get("edited_live_video"), favorite=rec.get("favorite"), visibility=visibility)
        elif ed.get("video"):
            ids["edited"] = self.upload_file(rec, "edited_video", ed["video"], f"{stem}_edited.mov", build_xmp(rec, faces=[]),
                                             favorite=rec.get("favorite"), visibility=visibility, duration_ms=dur)
        return ids

    def visible_id(self, rec):
        u = self.state.uploads_for(rec["uuid"]) if not self.dry else {}
        return u.get("edited_image") or u.get("edited_video") or u.get("original")

    # ---- phases ----------------------------------------------------------
    def run_uploads(self, recs):
        total = len(recs)
        total_bytes = sum((r.get("original_size") or 0) for r in recs)

        def work(rec):
            try:
                self.process(rec)
            except Exception as e:  # keep going; the asset can be retried on the next run
                self.state.error(rec["uuid"], f"{type(e).__name__}: {e}")
                with self.lock:
                    self.errors += 1
                print(f"ERROR {rec['uuid']} {rec.get('original_name')}: {e}", file=sys.stderr)
            with self.lock:
                self.done += 1
                if self.done % 25 == 0 or self.done == total:
                    el = time.time() - self.t0
                    rate = self.bytes / el / 1e6 if el else 0
                    print(f"[{self.done}/{total}] {self.bytes / 1e9:.1f} GB sent, {rate:.1f} MB/s, {el / 60:.0f} min elapsed, errors {self.errors}", flush=True)

        with cf.ThreadPoolExecutor(max_workers=self.a.workers) as ex:
            list(ex.map(work, recs))
        print(f"uploads finished: {self.done} assets, {self.errors} errors, {self.bytes / 1e9:.1f} GB sent (manifest originals {total_bytes / 1e9:.1f} GB)")

    def run_stacks(self, recs, bursts):
        made, skipped = 0, 0
        stacked = set()
        for rec in recs:
            u = self.state.uploads_for(rec["uuid"]) if not self.dry else {}
            edited = u.get("edited_image") or u.get("edited_video")
            members = []
            if edited:
                members = [edited, u.get("original")] + ([u["raw_alt"]] if u.get("raw_alt") else [])
            elif u.get("raw_alt"):
                members = [u.get("original"), u["raw_alt"]]
            if self.dry and (rec.get("edited") or rec.get("raw_alt")):
                self.plan["stack:edit-or-raw"] += 1
                stacked.add(rec["uuid"])
                continue
            members = list(dict.fromkeys(m for m in members if m))  # byte-identical files share one Immich asset
            if len(members) < 2:
                continue
            stacked.add(rec["uuid"])
            if self.state.stack(rec["uuid"]):
                continue
            try:
                s = self.client.create_stack(members)
                self.state.set_stack(rec["uuid"], s["id"])
                made += 1
            except ApiError as e:
                self.state.error(f"stack:{rec['uuid']}", str(e))
                skipped += 1
        by_uuid = {r["uuid"]: r for r in recs}
        for bid, b in (bursts or {}).items():
            uuids = [b["primary"]] + [m for m in b["members"] if m != b["primary"]]
            uuids = [x for x in uuids if x in by_uuid and x not in stacked]
            if len(uuids) < 2:
                continue
            if self.dry:
                self.plan["stack:burst"] += 1
                continue
            if self.state.stack(f"burst:{bid}"):
                continue
            ids = list(dict.fromkeys(i for i in (self.visible_id(by_uuid[x]) for x in uuids) if i))
            if len(ids) < 2:
                continue
            try:
                s = self.client.create_stack(ids)
                self.state.set_stack(f"burst:{bid}", s["id"])
                made += 1
            except ApiError as e:
                self.state.error(f"stack:burst:{bid}", str(e))
                skipped += 1
        print(f"stacks: {made} created, {skipped} failed")

    def run_albums(self, recs):
        wanted = collections.defaultdict(list)
        for rec in recs:
            for name in rec.get("albums") or []:
                wanted[name].append(rec)
        if self.dry:
            self.plan["albums"] = len(wanted)
            self.plan["album memberships"] = sum(len(v) for v in wanted.values())
            return
        existing = {a["albumName"]: a["id"] for a in self.client.albums()}
        for name, members in sorted(wanted.items()):
            album_id = self.state.album(name) or existing.get(name)
            ids = [self.visible_id(r) for r in members]
            ids = [i for i in ids if i]
            if not album_id:
                if not ids:
                    continue
                album_id = self.client.create_album(name)["id"]
            self.state.set_album(name, album_id)
            new = [i for i in ids if i not in self.state.members(name)]
            if new:
                self.client.add_to_album(album_id, new)
                self.state.add_members(name, new)
            print(f"album {name!r}: {len(ids)} assets ({len(new)} added)")


def load(args):
    recs = [json.loads(l) for l in open(args.manifest)]
    if args.path_prefix:
        src, dst = args.path_prefix.split("=", 1)
        def remap(v):
            return dst + v[len(src):] if isinstance(v, str) and v.startswith(src) else v
        for r in recs:
            for k in ("original", "live_video", "raw_alt"):
                r[k] = remap(r.get(k))
            if r.get("edited"):
                r["edited"] = {k: remap(v) for k, v in r["edited"].items()}
    if args.uuid:
        recs = [r for r in recs if r["uuid"] == args.uuid]
    if args.uuids:
        wanted = {l.split("#")[0].strip() for l in open(args.uuids) if l.split("#")[0].strip()}
        recs = [r for r in recs if r["uuid"] in wanted]
    if args.album:
        recs = [r for r in recs if args.album in (r.get("albums") or [])]
    if args.newest_first:
        recs.sort(key=lambda r: r.get("created_utc") or "", reverse=True)
    if args.limit:
        recs = recs[:args.limit]
    bursts_path = args.bursts or os.path.join(os.path.dirname(args.manifest), "bursts.json")
    bursts = json.load(open(bursts_path)) if os.path.exists(bursts_path) else {}
    return recs, bursts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--bursts")
    ap.add_argument("--server", default=os.environ.get("IMMICH_SERVER", "http://localhost:2283"), help="Immich base URL (or set IMMICH_SERVER)")
    ap.add_argument("--api-key-file")
    ap.add_argument("--state")
    ap.add_argument("--device-id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--uuid")
    ap.add_argument("--uuids", help="file with one asset UUID per line (a test set)")
    ap.add_argument("--album")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--skip-albums", action="store_true")
    ap.add_argument("--skip-stacks", action="store_true")
    ap.add_argument("--hash", action="store_true", help="send a SHA-1 checksum so the server can skip files it already has before the upload")
    ap.add_argument("--report", action="store_true", help="print the state database summary and exit")
    ap.add_argument("--newest-first", action="store_true", help="upload the newest photos first so the library becomes useful sooner")
    ap.add_argument("--path-prefix", help="remap manifest paths, e.g. '/Volumes/<disk>=/mnt/photos' when running on another machine")
    args = ap.parse_args()
    work = os.path.dirname(os.path.abspath(args.manifest))
    args.state = args.state or os.path.join(work, "state.sqlite")
    args.device_id = args.device_id or f"apple-photos-{os.path.basename(work)}"
    if args.report:
        State(args.state).report()
        return
    if not args.dry_run and not args.api_key_file:
        ap.error("--api-key-file is required unless --dry-run")
    recs, bursts = load(args)
    m = Migrator(args)
    if not m.dry:
        me = m.client.me()
        print(f"server {args.server}: {m.client.version()} user {me.get('name')} <{me.get('email')}>")
    print(f"{len(recs)} assets selected from {args.manifest}")
    m.run_uploads(recs)
    if not args.skip_stacks:
        m.run_stacks(recs, bursts)
    if not args.skip_albums:
        m.run_albums(recs)
    if m.dry:
        print("dry-run plan:", json.dumps(dict(m.plan), indent=1))
    else:
        m.state.report()
        if m.errors:
            sys.exit(1)  # non-zero so a supervising service restarts and retries the failed assets


if __name__ == "__main__":
    main()
