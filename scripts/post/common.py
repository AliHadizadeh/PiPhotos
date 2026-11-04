"""Shared bits for the post-processing tools: owners file, database queries through docker, Immich API calls.

owners.json (copy owners.example.json) maps a short name to an Immich user:
  {"alice": {"id": "<user uuid>", "key_file": "~/.config/immich-tools/alice.key", "display": "Alice"}, ...}
The user id is in Administration, Users, or `GET /api/users/me` with that user's key.
Environment: IMMICH_SERVER (default http://localhost:2283), DB_CONTAINER (immich_postgres), DB_USER (postgres), DB_NAME (immich).
"""
import json, os, subprocess, sys, urllib.error, urllib.request

SERVER = os.environ.get('IMMICH_SERVER', 'http://localhost:2283').rstrip('/')
API = SERVER + '/api'
DB = (os.environ.get('DB_CONTAINER', 'immich_postgres'), os.environ.get('DB_USER', 'postgres'), os.environ.get('DB_NAME', 'immich'))


def load_owners(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'owners.json')
    if not os.path.exists(path):
        sys.exit(f'{path} not found: copy owners.example.json to owners.json and fill it in')
    owners = json.load(open(path))
    for name, o in owners.items():
        o.setdefault('display', name.capitalize())
        o['key_file'] = os.path.expanduser(o['key_file'])
    return owners


def read_key(path):
    return open(os.path.expanduser(path)).read().strip()


def psql(sql):
    """Read-only query through the database container. Never pass user input into sql without care."""
    container, user, db = DB
    out = subprocess.run(['docker', 'exec', container, 'psql', '-U', user, '-d', db, '-At', '-F', '\t', '-v', 'ON_ERROR_STOP=1', '-c', sql],
                         capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if out.returncode:
        sys.exit(f'psql failed: {out.stderr}')
    return [line.split('\t') for line in out.stdout.splitlines() if line]


def api(method, path, key, body=None, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, method=method, data=data,
                                 headers={'x-api-key': key, 'Content-Type': 'application/json', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def api_status(method, path, key, body=None, timeout=600):
    """Like api() but returns (status, payload) and never raises on HTTP errors."""
    try:
        return 200, api(method, path, key, body, timeout)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
