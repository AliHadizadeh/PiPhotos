#!/usr/bin/env python3
"""Configure Immich's own email from the same smtp.json the backup uses: test first through Immich's admin
endpoint (POST /api/admin/notifications/test-email, which needs transport.secure in v3.3), save only on success."""
import json, os, sys, urllib.request, urllib.error

_C = {}
for _l in open(os.environ.get('IMMICH_TOOLS_CONF', '/etc/immich-tools/backup.conf')):
    _l = _l.split('#', 1)[0].strip()
    if '=' in _l:
        _k, _, _v = _l.partition('='); _C[_k.strip()] = _v.strip().strip('"').strip("'")
API = _C.get('IMMICH_URL', 'http://localhost:2283').rstrip('/') + '/api'
KEY = open(_C.get('ADMIN_KEY_FILE', '/etc/immich-tools/admin.key')).read().strip()
cfg = json.load(open(_C.get('SMTP_FILE', '/etc/immich-tools/smtp.json')))


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={'x-api-key': KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            t = r.read().decode()
            return r.status, (json.loads(t) if t else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


me = api('GET', '/users/me')[1]
print('admin account email in Immich:', me.get('email'))
smtp = {'enabled': True, 'from': f'Immich <{cfg["from"]}>', 'replyTo': '',
        'transport': {'host': cfg['host'], 'port': int(cfg['port']), 'username': cfg['user'],
                      'password': cfg['password'], 'ignoreCert': False, 'secure': int(cfg['port']) == 465}}
for port in (int(cfg['port']), 587):
    smtp['transport']['port'] = port
    smtp['transport']['secure'] = (port == 465)   # implicit TLS on 465, STARTTLS otherwise
    st, res = api('POST', '/admin/notifications/test-email', smtp)
    print(f'test-email on port {port}: HTTP {st} {res if st != 200 else "sent, messageId " + str(res.get("messageId", ""))[:40]}')
    if st == 200:
        break
else:
    sys.exit('Immich could not send through either port; nothing saved')

st, full = api('GET', '/system-config')
full['notifications']['smtp'] = smtp
st, res = api('PUT', '/system-config', full)
print('save:', 'HTTP', st, '' if st == 200 else res)
st, now = api('GET', '/system-config')
n = now['notifications']['smtp']
print('saved config: enabled', n['enabled'], '| from', n['from'], '| host', n['transport']['host'], 'port', n['transport']['port'],
      '| user', n['transport']['username'], '| secure', n['transport'].get('secure'), '| ignoreCert', n['transport']['ignoreCert'])
