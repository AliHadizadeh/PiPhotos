#!/usr/bin/env python3
"""Shift the capture date of a set of assets by a number of days, through the Immich API.

Use it for a camera whose clock was wrong. Immich does the rest: it writes the new date into the asset's
XMP sidecar, re-reads the metadata and moves the file into the new date folder on disk.

Select assets by camera model and an optional date window, or give a plan file (TSV: id, new_local).
Always dry-run first. The log makes a run resumable: assets already logged as done are skipped.

  python3 shift_dates.py --api-key-file ~/.config/immich-tools/<user>.key --model "DSC-T200" --days 440 --dry-run
  python3 shift_dates.py --api-key-file ~/.config/immich-tools/<user>.key --model "DSC-T200" --days 440 --apply
  python3 shift_dates.py --api-key-file ~/.config/immich-tools/<user>.key --plan plan.tsv --apply
  python3 shift_dates.py --api-key-file ~/.config/immich-tools/<user>.key --model "DSC-T200" --days 440 --verify

The log is shift-dates.log.tsv in the working directory: time, status, id, old local time, new local time.
"""
import argparse, csv, datetime, json, os, sys, time, urllib.request, urllib.error

LOG = 'shift-dates.log.tsv'


class Api:
    def __init__(self, server, key):
        self.server, self.key = server.rstrip('/'), key

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.server + '/api' + path, data=data, method=method,
                                     headers={'x-api-key': self.key, 'Content-Type': 'application/json', 'Accept': 'application/json'})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    t = r.read().decode()
                    return json.loads(t) if t else None
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                    time.sleep(2 ** attempt); continue
                raise SystemExit(f'HTTP {e.code} {path}: {e.read().decode()[:200]}')
            except OSError:
                if attempt < 4:
                    time.sleep(2 ** attempt); continue
                raise


def search(api, model, after, before):
    """All assets of the caller with the given camera model, taken in [after, before)."""
    body = {'size': 1000, 'withExif': True, 'model': model}
    if after:
        body['takenAfter'] = after
    if before:
        body['takenBefore'] = before
    page, out = 1, []
    while True:
        body['page'] = page
        res = api.call('POST', '/search/metadata', body)
        items = res.get('assets', {}).get('items', [])
        out += items
        nxt = res.get('assets', {}).get('nextPage')
        if not nxt:
            return out
        page = int(nxt)


def shifted(local_iso, days):
    """localDateTime from Immich (ISO, no offset) plus N days, as an ISO string with the asset's offset added later."""
    dt = datetime.datetime.fromisoformat(local_iso.replace('Z', ''))
    return (dt + datetime.timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%S')


def offset_of(asset):
    """The asset's UTC offset as +HH:MM, from exifInfo.timeZone ('UTC+3:30', 'Europe/Berlin', ...) or from dateTimeOriginal."""
    dto = (asset.get('exifInfo') or {}).get('dateTimeOriginal') or ''
    if len(dto) >= 6 and dto[-6] in '+-' and dto[-3] == ':':
        return dto[-6:]
    tz = (asset.get('exifInfo') or {}).get('timeZone') or ''
    if tz.startswith('UTC') and len(tz) > 3:
        sign, rest = tz[3], tz[4:]
        h, _, m = rest.partition(':')
        return f'{sign}{int(h):02d}:{int(m or 0):02d}'
    return '+00:00'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--server', default=os.environ.get('IMMICH_SERVER', 'http://localhost:2283'))
    ap.add_argument('--api-key-file', required=True)
    ap.add_argument('--model', help='camera model as Immich shows it, e.g. "DSC-T200"')
    ap.add_argument('--after', help='only assets taken after this ISO date')
    ap.add_argument('--before', help='only assets taken before this ISO date')
    ap.add_argument('--days', type=int, help='shift by this many days (negative to go back)')
    ap.add_argument('--plan', help='TSV with columns id and new_local (YYYY-MM-DDTHH:MM:SS) instead of --model/--days')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--dry-run', action='store_true')
    g.add_argument('--apply', action='store_true')
    g.add_argument('--verify', action='store_true', help='read the assets back and compare with the plan or the shift')
    a = ap.parse_args()
    if not (a.plan or (a.model and a.days is not None)):
        ap.error('give --plan, or --model and --days')
    api = Api(a.server, open(os.path.expanduser(a.api_key_file)).read().strip())
    me = api.call('GET', '/users/me')
    print(f'user {me["name"]} on {a.server}')
    # build the plan: [(id, name, old_local, new_local_with_offset)]
    plan = []
    if a.plan:
        rows = list(csv.DictReader(open(a.plan, encoding='utf-8'), delimiter='\t'))
        for r in rows:
            asset = api.call('GET', f'/assets/{r["id"]}')
            plan.append((r['id'], asset.get('originalFileName'), asset.get('localDateTime', '')[:19], r['new_local'][:19] + offset_of(asset)))
    else:
        for asset in search(api, a.model, a.after, a.before):
            old = asset.get('localDateTime', '')[:19]
            plan.append((asset['id'], asset.get('originalFileName'), old, shifted(old, a.days) + offset_of(asset)))
    print(f'{len(plan)} assets selected')
    for aid, name, old, new in plan[:10]:
        print(f'  {name:30s} {old} -> {new}')
    if len(plan) > 10:
        print('  ...')
    if a.verify:
        bad = 0
        for aid, name, old, new in plan:
            now = api.call('GET', f'/assets/{aid}').get('localDateTime', '')[:19]
            if now != new[:19]:
                bad += 1; print(f'  NOT APPLIED {name}: {now} != {new[:19]}')
        print(f'verify: {len(plan) - bad} as planned, {bad} not')
        return
    if not a.apply:
        print('dry run, nothing changed (add --apply)')
        return
    done = set()
    if os.path.exists(LOG):
        for r in csv.reader(open(LOG, encoding='utf-8'), delimiter='\t'):
            if len(r) > 2 and r[1] in ('updated', 'already'):
                done.add(r[2])
    log = open(LOG, 'a', encoding='utf-8', buffering=1)
    n = {'updated': 0, 'already': 0, 'error': 0}
    for i, (aid, name, old, new) in enumerate(plan, 1):
        if aid in done:
            continue
        try:
            if old == new[:19]:
                status = 'already'
            else:
                api.call('PUT', f'/assets/{aid}', {'dateTimeOriginal': new}); status = 'updated'
        except SystemExit as e:
            status = 'error'; print(f'ERROR {name}: {e}')
        n[status] += 1
        log.write('\t'.join([time.strftime('%Y-%m-%dT%H:%M:%S'), status, aid, old, new]) + '\n')
        if i % 200 == 0:
            print(f'{i}/{len(plan)} {n}')
    print('done', n, '- Immich now rewrites the sidecars and moves the files; check the jobs page until the sidecar, metadata and storage-template queues are empty')


if __name__ == '__main__':
    main()
