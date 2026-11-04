#!/usr/bin/env python3
"""Edit Immich's machine-learning settings from the command line.

Reads the current system config with an admin API key, applies the requested
changes and writes the whole config back (the same thing the admin UI does).

  --add-url URL         put URL first in the machine-learning URL list; the
                        existing entries stay behind it as fallbacks
  --remove-url URL      drop URL from the list
  --clip-model NAME     set the smart-search (CLIP) model
  --concurrency Q=N     set a job queue's concurrency, repeatable
                        (e.g. --concurrency faceDetection=6 --concurrency smartSearch=6)
  --dry-run             print the changes and save nothing

Example (on the Pi):
  python3 set_remote_ml.py --api-key-file ~/.config/immich-tools/admin.key \
      --add-url http://<gpu-machine>:3003 --concurrency faceDetection=4 \
      --concurrency smartSearch=4 --dry-run
"""
import argparse
import json
import sys
import urllib.request


def api(server, key, method="GET", path="/api/system-config", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        server.rstrip("/") + path, data=data, method=method,
        headers={"x-api-key": key, "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def diff(old, new, path=""):
    out = []
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new)):
            out += diff(old.get(k), new.get(k), f"{path}.{k}" if path else k)
    elif old != new:
        out.append(f"{path}: {json.dumps(old)} -> {json.dumps(new)}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default="http://localhost:2283")
    ap.add_argument("--api-key-file", required=True)
    ap.add_argument("--add-url")
    ap.add_argument("--remove-url")
    ap.add_argument("--clip-model")
    ap.add_argument("--concurrency", action="append", default=[], metavar="QUEUE=N")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    key = open(a.api_key_file).read().strip()
    cfg = api(a.server, key)
    new = json.loads(json.dumps(cfg))
    ml = new["machineLearning"]

    norm = lambda u: u.rstrip("/")
    if a.remove_url:
        ml["urls"] = [u for u in ml["urls"] if norm(u) != norm(a.remove_url)]
    if a.add_url:
        ml["urls"] = [a.add_url] + [u for u in ml["urls"] if norm(u) != norm(a.add_url)]
    if not ml["urls"]:
        sys.exit("refusing to save an empty machine-learning URL list")
    if a.clip_model:
        ml["clip"]["modelName"] = a.clip_model
    for item in a.concurrency:
        queue, _, n = item.partition("=")
        if queue not in new["job"] or not n.isdigit():
            sys.exit(f"bad --concurrency {item!r}; queues: {', '.join(new['job'])}")
        new["job"][queue]["concurrency"] = int(n)

    changes = diff(cfg, new)
    if not changes:
        print("no changes")
        return
    print("\n".join(changes))
    if a.dry_run:
        print("(dry run, nothing saved)")
        return
    api(a.server, key, "PUT", body=new)
    saved = api(a.server, key)
    print("saved. urls:", saved["machineLearning"]["urls"], "clip:", saved["machineLearning"]["clip"]["modelName"],
          "faceDetection:", saved["job"]["faceDetection"]["concurrency"], "smartSearch:", saved["job"]["smartSearch"]["concurrency"])


if __name__ == "__main__":
    main()
