#!/usr/bin/env python3
"""Read an Apple Photos library catalog (Photos.sqlite) read-only and write a migration manifest.

Usage:
  python3 photos_catalog.py --library "/Volumes/<disk>/<name>.photoslibrary" --out work/<user> --fallback-tz Europe/Berlin [--db PATH] [--limit N]

Outputs in --out: manifest.jsonl (one own asset per line), summary.json, albums.json, people.json, skipped.jsonl.
The library itself is never written to; the catalog is read from a copy (made into <out>/db unless --db is given).
"""
import argparse, collections, datetime, json, os, shutil, sqlite3, sys
from zoneinfo import ZoneInfo

APPLE_EPOCH = 978307200
RENDER_IMAGE = ("_1_201_a.jpeg", "_1_201_a.heic")
RENDER_VIDEO = "_2_0_a.mov"
RENDER_LIVE_VIDEO = "_2_100_a.mov"
RAW_ALT_EXTS = ("cr2", "dng", "arw", "nef", "raf", "orf", "rw2", "jpeg", "heic")
FALLBACK_TZ = ZoneInfo("UTC")   # overridden by --fallback-tz
ALBUM_KIND, FOLDER_KIND, ROOT_FOLDER_KIND = 2, 4000, 3999


def copy_db(library, out):
    src, dst = os.path.join(library, "database"), os.path.join(out, "db")
    os.makedirs(dst, exist_ok=True)
    for f in ("Photos.sqlite", "Photos.sqlite-wal", "Photos.sqlite-shm"):
        p = os.path.join(src, f)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(dst, f))
    return os.path.join(dst, "Photos.sqlite")


def apple_date(v):
    """Core Data timestamp -> aware UTC datetime; None for missing or corrupt values (year 0 etc.)."""
    if v is None:
        return None
    try:
        d = datetime.datetime.fromtimestamp(v + APPLE_EPOCH, datetime.UTC)
    except (ValueError, OverflowError, OSError):
        return None
    return d if 1970 <= d.year <= 2100 else None


def face_region(cx, cy, size, orientation, disp_w, disp_h):
    """Apple face center (displayed frame, origin bottom-left) -> MWG region in the stored frame (origin top-left).

    The orientation cases and the size scaling are adapted from the FaceInfo class of osxphotos
    (https://github.com/RhetTbull/osxphotos, MIT License, Copyright (c) Rhet Turnbull). See THIRD-PARTY-NOTICES.md.
    Returns (x, y, w, h, stored_w, stored_h) or None for mirrored orientations."""
    o = orientation or 1
    if o == 1:
        x, y = cx, 1.0 - cy
    elif o == 3:
        x, y = 1.0 - cx, cy
    elif o == 6:
        x, y = 1.0 - cy, 1.0 - cx
    elif o == 8:
        x, y = cy, cx
    else:
        return None
    if not disp_w or not disp_h or not size or size <= 0:
        return None
    size_px = size * max(disp_w, disp_h)
    stored_w, stored_h = (disp_h, disp_w) if o in (5, 6, 7, 8) else (disp_w, disp_h)
    w, h = size_px / stored_w, size_px / stored_h
    clamp = lambda v: max(0.0, min(1.0, v))
    return (clamp(x), clamp(y), clamp(w), clamp(h), int(stored_w), int(stored_h))


class Catalog:
    def __init__(self, db):
        self.con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        self.con.row_factory = sqlite3.Row
        self.tables = {r[0] for r in self.con.execute("select name from sqlite_master where type='table'")}
        self.cols = {t: [r[1] for r in self.con.execute(f'pragma table_info("{t}")')] for t in self.tables}

    def has(self, t, c):
        return t in self.tables and c in self.cols[t]

    def table_like(self, pattern_start, pattern_end):
        return [t for t in self.tables if t.startswith(pattern_start) and t.endswith(pattern_end) and t[len(pattern_start):-len(pattern_end)].isdigit()]

    # ---- lookups -------------------------------------------------------
    def people(self):
        """person pk -> final display name (merge chains followed)."""
        rows = {r["Z_PK"]: r for r in self.con.execute("select Z_PK, ZFULLNAME, ZDISPLAYNAME, ZMERGETARGETPERSON from ZPERSON")}
        names = {}
        for pk, r in rows.items():
            cur, seen = r, 0
            while cur["ZMERGETARGETPERSON"] is not None and cur["ZMERGETARGETPERSON"] in rows and seen < 20:
                cur, seen = rows[cur["ZMERGETARGETPERSON"]], seen + 1
            name = (cur["ZFULLNAME"] or "").strip() or (cur["ZDISPLAYNAME"] or "").strip()
            if name:
                names[pk] = name
        return names

    def faces_by_asset(self, names):
        out = collections.defaultdict(list)
        trash = "and (ZISINTRASH=0 or ZISINTRASH is null)" if self.has("ZDETECTEDFACE", "ZISINTRASH") else ""
        hidden = "and ZHIDDEN=0" if self.has("ZDETECTEDFACE", "ZHIDDEN") else ""
        for r in self.con.execute(f"select ZASSETFORFACE a, ZPERSONFORFACE p, ZCENTERX, ZCENTERY, ZSIZE, ZQUALITY from ZDETECTEDFACE where ZPERSONFORFACE is not null {hidden} {trash}"):
            name = names.get(r["p"])
            if name:
                out[r["a"]].append((name, r["ZCENTERX"], r["ZCENTERY"], r["ZSIZE"], r["ZQUALITY"] or 0))
        return out

    def albums(self):
        """album pk -> 'Folder / Album' path for user albums; plus memberships asset pk -> [album pk]."""
        rows = {r["Z_PK"]: r for r in self.con.execute("select Z_PK, ZTITLE, ZKIND, ZPARENTFOLDER, ZTRASHEDSTATE from ZGENERICALBUM")}
        paths = {}
        for pk, r in rows.items():
            if r["ZKIND"] != ALBUM_KIND or r["ZTRASHEDSTATE"]:
                continue
            parts, cur, seen = [(r["ZTITLE"] or "Untitled").strip()], r, 0
            while cur["ZPARENTFOLDER"] in rows and seen < 20:
                cur, seen = rows[cur["ZPARENTFOLDER"]], seen + 1
                if cur["ZKIND"] == FOLDER_KIND and cur["ZTITLE"]:
                    parts.insert(0, cur["ZTITLE"].strip())
            paths[pk] = " / ".join(parts)
        members = collections.defaultdict(list)
        for jt in self.table_like("Z_", "ASSETS"):
            cols = self.cols[jt]
            acol = next((c for c in cols if c.endswith("ALBUMS")), None)
            scol = next((c for c in cols if c.endswith("ASSETS") and not c.startswith("Z_FOK")), None)
            if not acol or not scol:
                continue
            for r in self.con.execute(f"select {acol} album, {scol} asset from {jt}"):
                if r["album"] in paths:
                    members[r["asset"]].append(r["album"])
        return paths, members

    def keywords(self):
        """attributes pk -> [keyword titles]."""
        out = collections.defaultdict(list)
        if "ZKEYWORD" not in self.tables:
            return out
        titles = {r["Z_PK"]: (r["ZTITLE"] or "").strip() for r in self.con.execute("select Z_PK, ZTITLE from ZKEYWORD")}
        for jt in self.table_like("Z_", "KEYWORDS"):
            cols = self.cols[jt]
            acol = next((c for c in cols if "ASSETATTRIBUTES" in c), None)
            kcol = next((c for c in cols if c.endswith("KEYWORDS") and not c.startswith("Z_FOK")), None)
            if not acol or not kcol:
                continue
            for r in self.con.execute(f"select {acol} attr, {kcol} kw from {jt}"):
                t = titles.get(r["kw"])
                if t:
                    out[r["attr"]].append(t)
        return out

    def captions(self):
        if "ZASSETDESCRIPTION" not in self.tables:
            return {}
        return {r["Z_PK"]: (r["ZLONGDESCRIPTION"] or "").strip() for r in self.con.execute("select Z_PK, ZLONGDESCRIPTION from ZASSETDESCRIPTION")}


def build(library, db, out, limit=None):
    global FALLBACK_TZ
    cat = Catalog(db)
    names = cat.people()
    faces = cat.faces_by_asset(names)
    album_paths, album_members = cat.albums()
    kws = cat.keywords()
    captions = cat.captions()
    rating_col = ", a.ZRATING" if cat.has("ZASSET", "ZRATING") else ", NULL as ZRATING"
    sql = f"""select a.Z_PK, a.ZUUID, a.ZDIRECTORY, a.ZFILENAME, a.ZKIND, a.ZKINDSUBTYPE, a.ZSAVEDASSETTYPE, a.ZDATECREATED,
        a.ZMODIFICATIONDATE, a.ZADDEDDATE, a.ZLATITUDE, a.ZLONGITUDE, a.ZFAVORITE, a.ZHIDDEN, a.ZWIDTH, a.ZHEIGHT, a.ZORIENTATION,
        a.ZDURATION, a.ZAVALANCHEUUID, a.ZAVALANCHEPICKTYPE, a.ZADJUSTMENTSSTATE, a.ZUNIFORMTYPEIDENTIFIER, a.ZTRASHEDSTATE{rating_col},
        aa.Z_PK attr_pk, aa.ZORIGINALFILENAME, aa.ZTITLE, aa.ZTIMEZONEOFFSET, aa.ZTIMEZONENAME, aa.ZINFERREDTIMEZONEOFFSET,
        aa.ZASSETDESCRIPTION, aa.ZORIGINALORIENTATION, aa.ZORIGINALWIDTH, aa.ZORIGINALHEIGHT, aa.ZORIGINALFILESIZE
        from ZASSET a left join ZADDITIONALASSETATTRIBUTES aa on aa.ZASSET = a.Z_PK
        where a.ZTRASHEDSTATE = 0 order by a.ZDATECREATED"""
    os.makedirs(out, exist_ok=True)
    stats = collections.Counter()
    bursts = collections.defaultdict(list)
    n = 0
    with open(os.path.join(out, "manifest.jsonl"), "w") as mf, open(os.path.join(out, "skipped.jsonl"), "w") as sf:
        for r in cat.con.execute(sql):
            stats["catalog_rows"] += 1
            d, fn = r["ZDIRECTORY"] or "", r["ZFILENAME"] or ""
            if r["ZSAVEDASSETTYPE"] == 4 or "/" in d or d.startswith("/"):
                stats["skipped_shared_album_copy"] += 1
                sf.write(json.dumps({"uuid": r["ZUUID"], "reason": "shared-album copy", "file": fn}) + "\n")
                continue
            orig = os.path.join(library, "originals", d, fn)
            if not os.path.isfile(orig):
                stats["skipped_missing_original"] += 1
                sf.write(json.dumps({"uuid": r["ZUUID"], "reason": "original missing", "file": os.path.join(d, fn)}) + "\n")
                continue
            stem = os.path.splitext(fn)[0]
            odir, rdir = os.path.join(library, "originals", d), os.path.join(library, "resources", "renders", d)
            live_video = os.path.join(odir, stem + "_3.mov")
            is_live = r["ZKINDSUBTYPE"] == 2 and os.path.isfile(live_video)
            raw_alt = next((os.path.join(odir, f"{stem}_4.{e}") for e in RAW_ALT_EXTS if os.path.isfile(os.path.join(odir, f"{stem}_4.{e}"))), None)
            # Edited assets keep the untouched original plus a flattened, correctly oriented full-size render.
            edited = None
            img = next((os.path.join(rdir, stem + s) for s in RENDER_IMAGE if os.path.isfile(os.path.join(rdir, stem + s))), None)
            vid = os.path.join(rdir, stem + RENDER_VIDEO) if os.path.isfile(os.path.join(rdir, stem + RENDER_VIDEO)) else None
            lvid = os.path.join(rdir, stem + RENDER_LIVE_VIDEO) if os.path.isfile(os.path.join(rdir, stem + RENDER_LIVE_VIDEO)) else None
            if r["ZKIND"] == 1:
                img, lvid = None, None  # a video's image render is only its poster frame
            if img or vid or lvid:
                edited = {"image": img, "video": vid, "live_video": lvid}
            created = apple_date(r["ZDATECREATED"])
            if created is None:
                created = apple_date(r["ZADDEDDATE"]) or datetime.datetime.fromtimestamp(os.path.getmtime(orig), datetime.UTC)
                stats["date_fallback"] += 1
            off = r["ZTIMEZONEOFFSET"]
            tz_source = "catalog"
            if off is None and r["ZINFERREDTIMEZONEOFFSET"] is not None:
                off, tz_source = r["ZINFERREDTIMEZONEOFFSET"], "inferred"
            if off is None and created is not None:
                off, tz_source = int(created.astimezone(FALLBACK_TZ).utcoffset().total_seconds()), "fallback"
            local = created.astimezone(datetime.timezone(datetime.timedelta(seconds=off))) if created is not None else None
            stats[f"tz_{tz_source}"] += 1
            lat, lon = r["ZLATITUDE"], r["ZLONGITUDE"]
            gps = [lat, lon] if lat is not None and lon is not None and lat > -180 and not (lat == 0 and lon == 0) else None
            # Face centers refer to the current (displayed) version. With an edited image render that render is the
            # current version, so the regions belong on it; otherwise they belong on the original, which is only safe
            # when the original's orientation is the current one (no rotation applied as an edit).
            regions, applied, faces_target = [], None, None
            if r["Z_PK"] in faces:
                if edited and edited.get("image"):
                    faces_target = "edited"
                elif r["ZORIGINALORIENTATION"] in (None, 0, r["ZORIENTATION"]):
                    faces_target = "original"
                if faces_target:
                    for name, cx, cy, size, q in faces[r["Z_PK"]]:
                        reg = face_region(cx, cy, size, r["ZORIENTATION"], r["ZWIDTH"], r["ZHEIGHT"])
                        if reg:
                            regions.append({"name": name, "x": round(reg[0], 5), "y": round(reg[1], 5), "w": round(reg[2], 5), "h": round(reg[3], 5)})
                            applied = [reg[4], reg[5]]
                        else:
                            stats["faces_skipped_no_face_box_or_mirrored"] += 1
                else:
                    stats["faces_skipped_rotated_original"] += len(faces[r["Z_PK"]])
                if regions:
                    stats[f"faces_on_{faces_target}"] += len(regions)
                else:
                    faces_target = None
            rec = {
                "uuid": r["ZUUID"], "kind": "video" if r["ZKIND"] == 1 else "photo", "subtype": r["ZKINDSUBTYPE"],
                "original": orig, "original_name": r["ZORIGINALFILENAME"] or fn, "original_size": r["ZORIGINALFILESIZE"],
                "uti": r["ZUNIFORMTYPEIDENTIFIER"], "width": r["ZWIDTH"], "height": r["ZHEIGHT"], "orientation": r["ZORIENTATION"],
                "live_video": live_video if is_live else None, "raw_alt": raw_alt, "edited": edited,
                "created_utc": created.isoformat() if created else None, "created_local": local.isoformat() if local else None,
                "tz_offset": off, "tz_name": r["ZTIMEZONENAME"], "tz_source": tz_source,
                "modified_utc": (apple_date(r["ZMODIFICATIONDATE"]) or created).isoformat() if created else None,
                "duration": r["ZDURATION"], "gps": gps, "title": (r["ZTITLE"] or "").strip() or None,
                "caption": captions.get(r["ZASSETDESCRIPTION"]) or None, "keywords": sorted(set(kws.get(r["attr_pk"], []))),
                "favorite": bool(r["ZFAVORITE"]), "hidden": bool(r["ZHIDDEN"]), "rating": r["ZRATING"] or None,
                "albums": sorted({album_paths[a] for a in album_members.get(r["Z_PK"], [])}),
                "faces": regions, "applied_dims": applied, "faces_target": faces_target,
                "burst": {"id": r["ZAVALANCHEUUID"], "pick": r["ZAVALANCHEPICKTYPE"]} if r["ZAVALANCHEUUID"] else None,
            }
            if rec["burst"]:
                bursts[r["ZAVALANCHEUUID"]].append((r["ZAVALANCHEPICKTYPE"] or 0, r["ZUUID"]))
            mf.write(json.dumps(rec) + "\n")
            n += 1
            stats["assets"] += 1
            stats["videos" if rec["kind"] == "video" else "photos"] += 1
            stats["live_photos"] += is_live
            stats["raw_pairs"] += bool(raw_alt)
            stats["edited"] += bool(edited)
            stats["favorites"] += rec["favorite"]
            stats["with_gps"] += bool(gps)
            stats["with_caption"] += bool(rec["caption"])
            stats["with_keywords"] += bool(rec["keywords"])
            stats["with_albums"] += bool(rec["albums"])
            stats["with_faces"] += bool(regions)
            stats["faces"] += len(regions)
            stats["bytes"] += r["ZORIGINALFILESIZE"] or 0
            if limit and n >= limit:
                break
    # burst primaries: prefer key (16), then default pick (4), then user pick (8), else first
    primaries = {}
    for bid, members in bursts.items():
        def score(m):
            p = m[0]
            return (bool(p & 16), bool(p & 4), bool(p & 8))
        primaries[bid] = max(members, key=score)[1]
    stats["burst_groups"] = len(bursts)
    with open(os.path.join(out, "bursts.json"), "w") as f:
        json.dump({bid: {"primary": primaries[bid], "members": [m[1] for m in sorted(members)]} for bid, members in bursts.items()}, f, indent=1)
    with open(os.path.join(out, "albums.json"), "w") as f:
        json.dump(sorted(set(album_paths.values())), f, indent=1, ensure_ascii=False)
    with open(os.path.join(out, "people.json"), "w") as f:
        json.dump(sorted(set(names.values())), f, indent=1, ensure_ascii=False)
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump(dict(stats), f, indent=1)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--db", help="existing read-only copy of Photos.sqlite (default: copy into <out>/db)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--fallback-tz", default="UTC", help="time zone for assets whose zone Photos never recorded, e.g. Europe/Berlin")
    a = ap.parse_args()
    FALLBACK_TZ = ZoneInfo(a.fallback_tz)
    db = a.db or copy_db(a.library, a.out)
    st = build(a.library, db, a.out, a.limit)
    print(json.dumps(dict(st), indent=1))
