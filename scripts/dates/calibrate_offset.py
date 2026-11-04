#!/usr/bin/env python3
"""Find how far a camera's clock was off, from a trip photographed by that camera and by a second camera with a correct clock.

For every whole-day shift in a range, the script shifts the suspect camera's capture times and measures how close each
reference photo is to the nearest shifted photo. The shift with the smallest median distance is the clock error.
Both cameras must have photographed the same days. Give a date window around the trip as Immich shows it for the
reference camera, and a window around the same trip as the suspect camera shows it.

  python3 calibrate_offset.py --api-key-file ~/.config/immich-tools/<user>.key \
      --suspect "DSC-T200" --suspect-after 2008-01-01 --suspect-before 2008-03-01 \
      --reference "DSC-H50" --reference-after 2009-02-01 --reference-before 2009-04-01 --min-days 400 --max-days 480
"""
import argparse, datetime, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shift_dates import Api, search


def times(api, model, after, before):
    out = []
    for a in search(api, model, after, before):
        out.append(datetime.datetime.fromisoformat(a['localDateTime'][:19]))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--server', default=os.environ.get('IMMICH_SERVER', 'http://localhost:2283'))
    ap.add_argument('--api-key-file', required=True)
    ap.add_argument('--suspect', required=True); ap.add_argument('--suspect-after'); ap.add_argument('--suspect-before')
    ap.add_argument('--reference', required=True); ap.add_argument('--reference-after'); ap.add_argument('--reference-before')
    ap.add_argument('--min-days', type=int, default=-30); ap.add_argument('--max-days', type=int, default=30)
    a = ap.parse_args()
    api = Api(a.server, open(os.path.expanduser(a.api_key_file)).read().strip())
    s = times(api, a.suspect, a.suspect_after, a.suspect_before)
    r = times(api, a.reference, a.reference_after, a.reference_before)
    if not s or not r:
        sys.exit(f'no photos: suspect {len(s)}, reference {len(r)}')
    print(f'suspect {a.suspect}: {len(s)} photos {s[0]:%Y-%m-%d} .. {s[-1]:%Y-%m-%d}; reference {a.reference}: {len(r)} photos {r[0]:%Y-%m-%d} .. {r[-1]:%Y-%m-%d}')
    results = []
    for n in range(a.min_days, a.max_days + 1):
        shift = datetime.timedelta(days=n)
        d = sorted(min(abs((t + shift - x).total_seconds()) for t in s) / 60 for x in r)
        results.append((d[len(d) // 2], d[len(d) // 4], n))
    results.sort()
    print('best shifts: (median minutes to the nearest shifted photo, lower quartile, days)')
    for med, q1, n in results[:5]:
        print(f'  {n:+5d} days   median {med:7.1f} min   quartile {q1:7.1f} min')
    print(f'answer: the {a.suspect} clock is off by {results[0][2]:+d} days (use --days {results[0][2]} in shift_dates.py)')


if __name__ == '__main__':
    main()
