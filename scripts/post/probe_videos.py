#!/usr/bin/env python3
"""ffprobe every video that is not yet converted and classify it with Immich's own rules minus the 8-bit rule:
   transcode  = codec not h264/hevc, or container not MOV/MP4 (unplayable on iPhone/iPad/Safari)
   remux      = codec fine but audio not aac/mp3/opus (e.g. Canon PCM: Chrome plays it silently)
   fine       = plays natively; 10-bit HDR HEVC lands here on purpose
Writes work/video_probe.tsv. Read-only."""
import subprocess, json, concurrent.futures, collections, argparse, os
from common import psql
ap = argparse.ArgumentParser(); ap.add_argument("--since", help="only assets uploaded after this local timestamp, e.g. 2026-11-01 07:00")
ap.add_argument("--tz", default=os.environ.get("TZ", "UTC"), help="time zone of --since (default $TZ or UTC)")
ap.add_argument("--out", default="work/video_probe.tsv"); ap.add_argument("--server-container", default="immich_server"); args = ap.parse_args()
since = f"""and a."createdAt" > '{args.since}'::timestamp at time zone '{args.tz}'""" if args.since else ""
os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
rows = psql('''select a.id, left(a."ownerId"::text,8), a."originalPath", coalesce(e.make,''), coalesce(a.duration,0), coalesce(e."fileSizeInByte",0), a.visibility
               from asset a left join asset_exif e on e."assetId"=a.id
               where a.type='VIDEO' and a."deletedAt" is null
                 and not exists (select 1 from asset_file f where f."assetId"=a.id and f.type='encoded_video') {since}'''.replace("{since}", since))
def probe(r):
    aid, owner, path, make, dur, size, vis = r
    if make == "Apple" and not args.since:   # h264/hevc + aac by construction; probe anyway for small --since runs to see the 10-bit share
        return (aid, owner, path, make, dur, size, vis, "apple-skip", "", "", "", "", "")
    p = subprocess.run(["docker","exec",args.server_container,"ffprobe","-v","error","-show_entries","format=format_name:stream=codec_type,codec_name,pix_fmt,width,height","-of","json",path],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    try:
        d = json.loads(p.stdout); fmt = d["format"]["format_name"]
        v = next((s for s in d["streams"] if s["codec_type"] == "video"), {}); a = next((s for s in d["streams"] if s["codec_type"] == "audio"), {})
        return (aid, owner, path, make, dur, size, vis, fmt, v.get("codec_name",""), v.get("pix_fmt",""), f'{v.get("width","")}x{v.get("height","")}', a.get("codec_name",""), "")
    except Exception as ex:
        return (aid, owner, path, make, dur, size, vis, "probe-failed", "", "", "", "", p.stderr.strip()[:80])
with concurrent.futures.ThreadPoolExecutor(4) as ex:
    results = list(ex.map(probe, rows))
def classify(x):
    fmt, vcodec, acodec = x[7], x[8], x[11]
    if fmt == "apple-skip": return "fine"
    if fmt == "probe-failed": return "probe-failed"
    container_ok = fmt.startswith("mov,mp4") or fmt == "mp4"
    if vcodec not in ("h264", "hevc") or not container_ok: return "transcode"
    if acodec and acodec not in ("aac", "mp3", "opus"): return "remux"
    return "fine"
with open(args.out, "w") as fh:
    fh.write("class\tid\towner\tpath\tmake\tduration_ms\tsize\tvisibility\tformat\tvcodec\tpix_fmt\tdims\tacodec\terr\n")
    for x in results: fh.write("\t".join([classify(x)] + [str(v) for v in x]) + "\n")
summary = collections.defaultdict(lambda: [0, 0.0])
tenbit = [x for x in results if x[9] and not x[9].endswith("420p")]
print(f"10-bit / HDR (would be transcoded by the 'required' policy): {len(tenbit)} videos, {sum(int(x[4]) for x in tenbit)/3600000:.1f} h, {sum(int(x[5]) for x in tenbit)/1073741824:.1f} GB")
for x in sorted(tenbit, key=lambda x: -int(x[5]))[:6]: print(f"   {int(x[5])/1048576:6.0f} MB {int(x[4])/60000:5.1f} min {x[10]:>9} {x[9]:12} {x[2].split('/')[-1]}")
for x in results:
    c = classify(x); summary[c][0] += 1; summary[c][1] += int(x[4]) / 3600000
print("class | videos | hours of footage")
for c, (n, h) in sorted(summary.items()): print(f"{c:13} | {n:6d} | {h:6.1f}")
det = collections.Counter((classify(x), x[8] or x[7], x[11]) for x in results if classify(x) in ("transcode", "remux"))
print("details (class, video codec/format, audio codec): count"); [print(f"  {k}: {v}") for k, v in det.most_common(15)]
