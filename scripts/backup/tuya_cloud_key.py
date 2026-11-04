#!/usr/bin/env python3
"""Fetch a Tuya device's details and local key through the Tuya OpenAPI, standard library only.

Reads  /etc/immich-tools/tuya-cloud.json   {"client_id","secret","region","device_id","mac" (optional)}
Writes /etc/immich-tools/tuya-devices.json (tinytuya-compatible list) with the local key, mode 600.
Paths can be changed with TUYA_CLOUD and TUYA_DEVICES in /etc/immich-tools/backup.conf.
Prints device facts only; never prints the secret or the key.
"""
import hashlib, hmac, json, os, sys, time, urllib.error, urllib.request

def _conf():
    c = {}
    try:
        for line in open(os.environ.get('IMMICH_TOOLS_CONF', '/etc/immich-tools/backup.conf')):
            line = line.split('#', 1)[0].strip()
            if '=' in line:
                k, _, v = line.partition('='); c[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return c


_C = _conf()
CFG = _C.get('TUYA_CLOUD', '/etc/immich-tools/tuya-cloud.json')
OUT = _C.get('TUYA_DEVICES', '/etc/immich-tools/tuya-devices.json')
ENDPOINTS = {'us': 'https://openapi.tuyaus.com', 'us-e': 'https://openapi-ueaz.tuyaus.com',
             'eu': 'https://openapi.tuyaeu.com', 'eu-w': 'https://openapi-weaz.tuyaeu.com',
             'cn': 'https://openapi.tuyacn.com', 'in': 'https://openapi.tuyain.com'}
EMPTY_SHA = hashlib.sha256(b'').hexdigest()


def sign(secret, msg):
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest().upper()


def call(base, cfg, path, token=None):
    t = str(int(time.time() * 1000))
    str_to_sign = 'GET\n' + EMPTY_SHA + '\n\n' + path
    msg = cfg['client_id'] + (token or '') + t + str_to_sign
    headers = {'client_id': cfg['client_id'], 'sign': sign(cfg['secret'], msg), 't': t,
               'sign_method': 'HMAC-SHA256', 'Content-Type': 'application/json'}
    if token:
        headers['access_token'] = token
    req = urllib.request.Request(base + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {'success': False, 'code': e.code, 'msg': e.read().decode(errors='replace')[:200]}


def main():
    cfg = json.load(open(CFG))
    dev_id = cfg['device_id']
    regions = [cfg.get('region', 'us')] + [r for r in ('us-e', 'eu', 'eu-w') if r != cfg.get('region')]
    for region in regions:
        base = ENDPOINTS[region]
        tok = call(base, cfg, '/v1.0/token?grant_type=1')
        if not tok.get('success'):
            print(f'[{region}] token: code={tok.get("code")} msg={tok.get("msg")}')
            if tok.get('code') in (2007, 1106):
                continue
            sys.exit(1)
        token = tok['result']['access_token']
        dev = call(base, cfg, f'/v1.0/devices/{dev_id}', token)
        if not dev.get('success'):
            print(f'[{region}] device: code={dev.get("code")} msg={dev.get("msg")}')
            if dev.get('code') in (2007,):
                continue
            sys.exit(1)
        r = dev['result']
        key = r.get('local_key', '')
        print(f'[{region}] device found')
        for k in ('name', 'product_name', 'category', 'model', 'online', 'ip', 'time_zone', 'uuid', 'product_id'):
            print(f'  {k:13s} {r.get(k)}')
        print(f'  local_key     {"received, %d chars" % len(key) if key else "MISSING"}')
        fn = call(base, cfg, f'/v1.0/devices/{dev_id}/functions', token)
        if fn.get('success'):
            print('  functions     ' + ', '.join(f['code'] for f in fn['result'].get('functions', [])))
        st = call(base, cfg, f'/v1.0/devices/{dev_id}/status', token)
        if st.get('success'):
            print('  status        ' + ', '.join(f"{s['code']}={s['value']}" for s in st['result']))
        entry = {'name': r.get('name'), 'id': dev_id, 'key': key, 'uuid': r.get('uuid'),
                 'category': r.get('category'), 'product_name': r.get('product_name'),
                 'product_id': r.get('product_id'), 'model': r.get('model'), 'mac': cfg.get('mac', '')}
        fd = os.open(OUT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump([entry], f, indent=2)
        print(f'  saved         {OUT} (mode 600)')
        return
    sys.exit(1)


if __name__ == '__main__':
    main()
