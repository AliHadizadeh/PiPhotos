#!/opt/immich-tools/backup/venv/bin/python
"""backup_plug.py on|off|status|ratecheck

Switches the Tuya smart plug that powers the Immich backup drive, over the LAN only.
Site values come from /etc/immich-tools/backup.conf: PLUG_ID, PLUG_PROTOCOL, PLUG_FALLBACK_IP, TUYA_DEVICES (the key file
written by tuya_cloud_key.py). The plug is found by device id through Tuya's UDP discovery, with the last known address cached. Exit 0 only when the plug
confirms the requested state.

Safety: every real power change is appended to state/power-log. "on" when already on (or "off" when already off)
does nothing and is not counted. Before a real power-on the command waits until MIN_GAP_MIN minutes have passed
since the last power-off, and refuses (exit 3) when MAX_ON_PER_DAY power-ons already happened in the last 24 h,
unless PLUG_FORCE=1. Any failure sends an email through backup_helpers.py unless PLUG_NOTIFY=0 (the weekly job
sets that because it reports by itself).
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import tinytuya


CONF_FILE = os.environ.get('IMMICH_TOOLS_CONF', '/etc/immich-tools/backup.conf')


def load_conf(path=CONF_FILE):
    """KEY=VALUE lines, shell style; quotes and comments are stripped."""
    conf = {}
    try:
        for line in open(path):
            line = line.split('#', 1)[0].strip()
            if '=' in line:
                k, _, v = line.partition('=')
                conf[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return conf


C = load_conf()
STATE_ROOT = C.get('STATE_ROOT', '/var/lib/immich-tools')
PLUG_ID = C.get('PLUG_ID', '')
VERSION = float(C.get('PLUG_PROTOCOL', '3.3'))
SWITCH_DP = C.get('PLUG_SWITCH_DP', '1')         # single-outlet plugs expose the relay as DP 1
DEVICES = C.get('TUYA_DEVICES', '/etc/immich-tools/tuya-devices.json')
FALLBACK_IP = C.get('PLUG_FALLBACK_IP', '')
STATE_DIR = os.environ.get('PLUG_STATE_DIR', os.path.join(STATE_ROOT, 'state'))
IPCACHE = os.path.join(STATE_DIR, 'plug-ip')
POWER_LOG = os.path.join(STATE_DIR, 'power-log')
MIN_GAP_MIN = int(C.get('PLUG_MIN_GAP_MIN', 10))
MAX_ON_PER_DAY = int(C.get('PLUG_MAX_ON_PER_DAY', 6))
CONNECT_TRIES = 6                            # the plug drops off the LAN for a while after being re-plugged
PY = sys.executable
HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backup_helpers.py')


def notify(subject, body):
    if os.environ.get('PLUG_NOTIFY', '1') == '0':
        return
    try:
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.txt') as f:
            f.write(body)
            path = f.name
        subprocess.run([PY, HELPER, 'email', '--subject', subject, '--body-file', path], timeout=600)
        os.unlink(path)
    except Exception as e:
        print(f'backup_plug: could not send the email: {e}', file=sys.stderr)


def die(msg, code=1):
    print(f'backup_plug: {msg}', file=sys.stderr)
    notify(f'\u274c Immich backup: plug problem', f'{time.strftime("%Y-%m-%d %H:%M:%S")} backup_plug: {msg}\n')
    sys.exit(code)


def power_events():
    try:
        return [l.split() for l in open(POWER_LOG) if l.strip()]
    except FileNotFoundError:
        return []


def log_power(event):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        new = not os.path.exists(POWER_LOG)
        with open(POWER_LOG, 'a') as f:
            f.write(f'{int(time.time())} {time.strftime("%Y-%m-%d %H:%M:%S")} {event}\n')
        if new:
            os.chmod(POWER_LOG, 0o666)       # written by root (systemd) and by an interactive user alike
    except OSError as e:
        print(f'backup_plug: power log not written: {e}', file=sys.stderr)


def rate_check():
    """Before a real power-on: refuse too many power-ons, and wait out the minimum gap since the last power-off."""
    if os.environ.get('PLUG_FORCE') == '1':
        return
    now = time.time()
    ev = power_events()
    ons = [e for e in ev if e[3] == 'on' and now - int(e[0]) < 86400]
    if len(ons) >= MAX_ON_PER_DAY:
        die(f'refusing to power on: {len(ons)} power-ons in the last 24 h (limit {MAX_ON_PER_DAY}); PLUG_FORCE=1 overrides', 3)
    offs = [int(e[0]) for e in ev if e[3] == 'off']
    if offs:
        wait = MIN_GAP_MIN * 60 - (now - max(offs))
        if wait > 0:
            print(f'backup_plug: last power-off was {int((now - max(offs)) / 60)} min ago; waiting {int(wait)} s before powering on')
            time.sleep(wait)


def load_key():
    for d in json.load(open(DEVICES)):
        if d.get('id') == PLUG_ID and d.get('key'):
            return d['key']
    raise RuntimeError(f'no local key for {PLUG_ID} in {DEVICES}')


def find_ip():
    try:
        found = tinytuya.find_device(dev_id=PLUG_ID)
        if found and found.get('ip'):
            try:
                with open(IPCACHE, 'w') as f:
                    f.write(found['ip'])
            except OSError:
                pass
            return found['ip']
    except Exception:
        pass
    try:
        return open(IPCACHE).read().strip() or FALLBACK_IP
    except OSError:
        return FALLBACK_IP


def state(d):
    st = d.status()
    if not isinstance(st, dict) or 'dps' not in st:
        raise RuntimeError(f'plug did not answer: {st}')
    return bool(st['dps'].get(SWITCH_DP))


def connect():
    """Connect and read the state, retrying for about a minute (the plug is briefly unreachable after a re-plug)."""
    last = None
    for attempt in range(CONNECT_TRIES):
        try:
            d = tinytuya.OutletDevice(PLUG_ID, find_ip(), load_key(), version=VERSION)
            d.set_socketTimeout(5)
            d.set_socketRetryLimit(2)
            return d, state(d)
        except Exception as e:
            last = e
            if attempt < CONNECT_TRIES - 1:
                time.sleep(10)
    raise RuntimeError(f'plug unreachable after {CONNECT_TRIES} attempts: {last}')


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if not PLUG_ID:
        sys.exit('PLUG_ID is not set in ' + CONF_FILE)
    if cmd == 'ratecheck':
        rate_check()
        print('ratecheck ok')
        return
    if cmd not in ('on', 'off', 'status'):
        sys.exit('usage: backup_plug.py on|off|status|ratecheck')
    d, on = connect()
    if cmd == 'status':
        print('on' if on else 'off')
        return
    want = cmd == 'on'
    if on == want:
        print(f'{cmd} (already)')
        return
    if want:
        rate_check()
    for _ in range(3):
        d.turn_on() if want else d.turn_off()
        time.sleep(1.5)
        on = state(d)
        if on == want:
            log_power(cmd)
            print(cmd)
            return
    log_power(f'{cmd}-FAILED')
    raise RuntimeError(f'plug still {"on" if on else "off"} after 3 attempts (wanted {cmd})')


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        die(str(e))
