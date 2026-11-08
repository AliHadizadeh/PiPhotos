#!/opt/immich-tools/backup/venv/bin/python
"""Helpers for the weekly Immich backup (standard library only).

  dump                         ask Immich for a fresh database dump, wait for it, print the file name
  export-config OUT            write Immich's system configuration (GET /api/system-config) to OUT
  verify [options]             compare files on the backup drive with Immich's SHA-1 checksums
  email --subject S --body-file F   send a report (3 tries; queued in state/pending-mail on failure)
  email --flush                     send queued mail;   email --dry ...  print instead of sending
  deletion-stats [options]     photos and videos in Immich's trash and only in removed/, and what the purges delete

Site values come from /etc/immich-tools/backup.conf. Secrets (mode 600): ADMIN_KEY_FILE (Immich admin API key) and
SMTP_FILE, a JSON file {"host","port" (465 = SSL, 587 = STARTTLS),"user","password","from","to":[...]}, plus an
optional "from_name", the sender name shown in the inbox (default "Immich on Pi"). Keep "from" a bare address.
"""
import argparse, datetime, email.message, email.utils, glob, hashlib, json, os, random, smtplib, ssl, subprocess, sys, time, urllib.request


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
API = C.get('IMMICH_URL', 'http://localhost:2283').rstrip('/') + '/api'
KEY_FILE = C.get('ADMIN_KEY_FILE', '/etc/immich-tools/admin.key')
SMTP_FILE = C.get('SMTP_FILE', '/etc/immich-tools/smtp.json')
IMMICH_DATA = C.get('IMMICH_DATA', '/mnt/immich')
BACKUP_MNT = C.get('BACKUP_MNT', '/mnt/immich-backup')
DUMP_DIR = os.path.join(IMMICH_DATA, 'media', 'backups')
DB_CONTAINER = C.get('DB_CONTAINER', 'immich_postgres')
DB_USER = C.get('DB_USER', 'postgres')
DB_NAME = C.get('DB_NAME', 'immich')


def api(method, path, body=None, timeout=60):
    key = open(KEY_FILE).read().strip()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={'x-api-key': key, 'Content-Type': 'application/json', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        txt = r.read().decode()
        return json.loads(txt) if txt else None


def newest_dump():
    files = sorted(glob.glob(os.path.join(DUMP_DIR, 'immich-db-backup-*.sql.gz')), key=os.path.getmtime)
    return files[-1] if files else None


def cmd_dump(_args):
    before = newest_dump()
    t0 = time.time()
    api('PUT', '/jobs/backupDatabase', {'command': 'start', 'force': False})
    deadline = t0 + 30 * 60
    while time.time() < deadline:
        time.sleep(10)
        q = api('GET', '/jobs')['backupDatabase']['jobCounts']
        busy = q.get('active', 0) + q.get('waiting', 0) + q.get('delayed', 0)
        new = newest_dump()
        if busy == 0 and new and new != before and os.path.getmtime(new) >= t0 - 5:
            size = os.path.getsize(new)
            if size > 0 and time.time() - os.path.getmtime(new) > 5:
                print(f'{os.path.basename(new)} ({size/1e6:.0f} MB, {time.time()-t0:.0f} s)')
                return 0
        if busy == 0 and q.get('failed', 0):
            print('database dump job failed', file=sys.stderr)
            return 1
    print('timed out waiting for the database dump', file=sys.stderr)
    return 1


def cmd_export_config(args):
    cfg = api('GET', '/system-config')
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(cfg, f, indent=2)
    print(f'system config written to {args.out}')
    return 0


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def db_assets(before):
    """{relative path under the media root: sha1 hex} for assets created before `before` (ISO timestamp)."""
    sql = ('select "originalPath", encode(checksum, \'hex\') from asset '
           f'where "originalPath" like \'/data/%\' and "createdAt" < \'{before}\'')
    out = subprocess.run(['docker', 'exec', DB_CONTAINER, 'psql', '-U', DB_USER, '-d', DB_NAME,
                          '-At', '-F', '\t', '-c', sql], capture_output=True, text=True, check=True).stdout
    assets = {}
    for line in out.splitlines():
        p, c = line.split('\t')
        assets[p[len('/data/'):]] = c
    return assets


def cmd_verify(args):
    t0 = time.time()
    before = args.before or datetime.datetime.now(datetime.timezone.utc).isoformat()
    assets = db_assets(before)
    copied = [l.rstrip('\n') for l in open(args.copied)] if args.copied and os.path.exists(args.copied) else []
    copied = [c for c in copied if c and not c.endswith('/')]
    ok = mism = missing = gone = 0
    problems = []

    def check(rel, expected=None):
        nonlocal ok, mism, missing, gone
        bpath = os.path.join(args.backup_root, rel)
        spath = os.path.join(args.source_root, rel)
        if not os.path.isfile(bpath):
            if os.path.isfile(spath):
                missing += 1; problems.append(f'MISSING on backup: {rel}')
            else:
                gone += 1
            return
        if expected is None:
            if not os.path.isfile(spath):
                gone += 1; return
            expected = sha1(spath)
        if sha1(bpath) == expected:
            ok += 1
        else:
            mism += 1; problems.append(f'MISMATCH: {rel}')

    # 1. everything copied in this run
    copied_set = set(copied)
    for rel in copied:
        check(rel, assets.get(rel))
    n_copied = len(copied)
    # 2. originals: all of them (full) or a random sample
    rest = [r for r in assets if r not in copied_set]
    if args.full:
        chosen = rest
    else:
        k = max(1, round(len(rest) * args.sample_pct / 100)) if rest else 0
        chosen = random.sample(rest, k)
    for rel in chosen:
        check(rel, assets[rel])
    # 3. in full mode, non-original files (thumbs, transcodes, dumps): size+mtime for all, hash a 2 % sample
    meta_bad = 0; sample_bad = 0; n_other = 0
    if args.full:
        others = []
        for dirpath, _dirs, files in os.walk(args.source_root):
            for fn in files:
                sp = os.path.join(dirpath, fn); rel = os.path.relpath(sp, args.source_root)
                if rel in assets:
                    continue
                others.append(rel)
        n_other = len(others)
        for rel in others:
            sp = os.path.join(args.source_root, rel); bp = os.path.join(args.backup_root, rel)
            try:
                ss, bs = os.stat(sp), os.stat(bp)
            except FileNotFoundError:
                meta_bad += 1; problems.append(f'MISSING on backup (non-original): {rel}'); continue
            if ss.st_size != bs.st_size:
                meta_bad += 1; problems.append(f'SIZE DIFFERS (non-original): {rel}')
        for rel in random.sample(others, max(1, round(len(others) * 0.02))) if others else []:
            sp = os.path.join(args.source_root, rel); bp = os.path.join(args.backup_root, rel)
            if os.path.isfile(sp) and os.path.isfile(bp) and sha1(sp) != sha1(bp):
                sample_bad += 1; problems.append(f'MISMATCH (non-original): {rel}')
    mode = 'full' if args.full else f'sample {args.sample_pct}%'
    summary = (f'verify({mode}): copied-this-run {n_copied}, originals checked {len(chosen)}, ok {ok}, '
               f'mismatched {mism}, missing {missing}, gone-from-source {gone}'
               + (f', non-originals {n_other} size-checked with {meta_bad} problems, 2% hashed with {sample_bad} mismatches' if args.full else '')
               + f', {(time.time()-t0)/60:.0f} min')
    with open(args.report, 'w') as f:
        f.write(f'DB assets considered: {len(assets)} (created before {before})\n')
        for p in problems[:500]:
            f.write(p + '\n')
        if len(problems) > 500:
            f.write(f'... {len(problems)-500} more\n')
        f.write(summary + '\n')
    print(summary)
    return 1 if (mism or missing or meta_bad or sample_bad) else 0


IMAGE_EXT = {'.jpg', '.jpeg', '.jpe', '.heic', '.heif', '.hif', '.png', '.gif', '.webp', '.avif', '.jxl', '.bmp', '.tif',
             '.tiff', '.dng', '.cr2', '.cr3', '.crw', '.nef', '.nrw', '.arw', '.srf', '.sr2', '.raf', '.orf', '.rw2',
             '.pef', '.srw', '.x3f', '.3fr', '.erf', '.kdc', '.mrw', '.raw', '.rwl', '.iiq', '.psd', '.insp'}
VIDEO_EXT = {'.mov', '.mp4', '.m4v', '.3gp', '.3g2', '.avi', '.mkv', '.mts', '.m2ts', '.mpg', '.mpeg', '.wmv', '.webm',
             '.flv', '.vob', '.ogv', '.insv', '.mxf', '.qt', '.asf', '.divx'}


def psql(sql):
    return subprocess.run(['docker', 'exec', DB_CONTAINER, 'psql', '-U', DB_USER, '-d', DB_NAME,
                           '-At', '-F', '\t', '-c', sql], capture_output=True, text=True, check=True).stdout


def count_text(photos, videos):
    return f'{photos} photo{"" if photos == 1 else "s"}, {videos} video{"" if videos == 1 else "s"}'


def removed_originals(folder):
    """[(path, 'photo' | 'video')] for the originals under one removed/<date> folder (media/library, media/upload).
    Thumbnails, transcodes, sidecars and other synced folders are left out. A video next to a photo of the same name
    is the motion part of a Live Photo and is not counted on its own, as Immich shows the pair as one item."""
    out = []
    for top in ('library', 'upload'):
        for root, _dirs, files in os.walk(os.path.join(folder, 'media', top)):
            stems = {os.path.splitext(f)[0].lower() for f in files if os.path.splitext(f)[1].lower() in IMAGE_EXT}
            for f in files:
                stem, ext = os.path.splitext(f)
                if ext.lower() in IMAGE_EXT:
                    out.append((os.path.join(root, f), 'photo'))
                elif ext.lower() in VIDEO_EXT and stem.lower() not in stems:
                    out.append((os.path.join(root, f), 'video'))
    return out


def cmd_deletion_stats(args):
    """key=value rows for the report. A deleted photo or video goes through two holds before it is gone for good:
    Immich's trash (trash.days, 30 by default; a nightly job then deletes the file) and removed/<date> on the backup
    (keep_days, purged by the weekly run). Prints `trash` and `backup_only` (what sits in each hold, and what leaves it
    before the next run) and `purge_now` (what this run's purge deletes for good). Run before the purge."""
    nxt = datetime.datetime.now() + datetime.timedelta(days=args.next_run_days)
    when = f'{nxt:%a} {nxt.day} {nxt:%b}'
    try:
        days = int((api('GET', '/system-config').get('trash') or {}).get('days', 30))
    except Exception:
        days = 30
    tp = tv = dp = dv = 0      # in the trash; of those, deleted by Immich before the next run. Live Photo motion parts are hidden.
    for line in psql('select type, ("deletedAt" < now() + interval \'%d days\' - interval \'%d days\')::int, count(*) '
                     'from asset where status = \'trashed\' and visibility <> \'hidden\' group by 1, 2'
                     % (args.next_run_days, days)).splitlines():
        typ, due, n = line.split('\t')
        if typ == 'IMAGE':
            tp += int(n); dp += int(n) if due == '1' else 0
        elif typ == 'VIDEO':
            tv += int(n); dv += int(n) if due == '1' else 0
    in_immich = set(psql('select encode(checksum, \'hex\') from asset').split())
    groups = {'now': [0, 0], 'next': [0, 0], 'later': [0, 0]}
    still = 0
    t0 = time.time()
    if os.path.isdir(args.removed_root):
        for name in sorted(os.listdir(args.removed_root)):
            folder = os.path.join(args.removed_root, name)
            if not os.path.isdir(folder):
                continue
            age = int((t0 - os.stat(folder).st_mtime) // 86400)        # whole days, the way find -mtime counts them
            g = 'now' if age > args.keep_days else 'next' if age > args.keep_days - args.next_run_days else 'later'
            for path, kind in removed_originals(folder):
                if sha1(path) in in_immich:      # the same file is still in Immich: moved by the storage template, or a duplicate
                    still += 1
                    continue
                groups[g][0 if kind == 'photo' else 1] += 1
    none = lambda p, v: 'none' if p == v == 0 else count_text(p, v)
    held = (groups['next'][0] + groups['later'][0], groups['next'][1] + groups['later'][1])
    print('trash=' + ('empty' if tp == tv == 0 else
                      f'{count_text(tp, tv)}; Immich deletes {none(dp, dv)} of them before {when}'))
    print('backup_only=' + ('none' if held == (0, 0) else
                            f'{count_text(*held)}; {none(*groups["next"])} of them deleted for good at the {when} run')
          + (f'; not counted: {still} older cop{"y of a file" if still == 1 else "ies of files"} still in Immich'
             if still else ''))
    print('purge_now=' + ('no photos or videos' if groups['now'] == [0, 0] else count_text(*groups['now'])))
    print(f'deletion stats took {time.time() - t0:.0f} s', file=sys.stderr)
    return 0


PENDING_DIR =os.path.join(STATE_ROOT, 'state', 'pending-mail')


LABELS = [('result', 'Result'), ('run', 'Run'), ('started', 'Started'), ('finished', 'Finished'),
          ('duration', 'Duration'), ('step', 'Stopped at step'), ('drive', 'Backup drive'), ('read_sample', 'Drive read sample'),
          ('source_used', 'Immich data'), ('backup_used', 'Backup drive used'), ('dump', 'Database dump'),
          ('config', 'Configuration copy'), ('copied', 'Files copied'), ('removed', 'Deleted or replaced files'),
          ('trash', "In Immich's trash"), ('backup_only', 'Only on the backup'), ('purged', 'Deleted for good this run'),
          ('verify', 'Verification'), ('warnings', 'Warnings')]
COLORS = {'pass': '#15803d', 'fail': '#b91c1c', 'warn': '#b45309', 'info': '#1d4ed8'}
ICONS = {'pass': '✅', 'fail': '❌', 'warn': '⚠️', 'info': 'ℹ️'}


def guess_kind(subject):
    """Colour from the subject when the caller gives no --kind. The verdict word wins: 'FAIL' beats
    everything, then 'PASS' (so a PASS subject mentioning '0 problems' stays green), then alert words."""
    u = subject.upper()
    if 'FAIL' in u:
        return 'fail'
    if 'PASS' in u:
        return 'pass'
    if 'PROBLEM' in u or 'ERROR' in u or 'WITHOUT RESULT' in u:
        return 'fail'
    if 'ATTENTION' in u or 'WARN' in u:
        return 'warn'
    if 'DONE' in u or 'COMPLETE' in u:
        return 'pass'
    return 'info'


def read_summary(path):
    rows = []
    if path and os.path.exists(path):
        for line in open(path, errors='replace'):
            if '=' in line:
                k, _, v = line.rstrip('\n').partition('=')
                rows.append((k.strip(), v.strip()))
    return rows


def html_escape(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def render(subject, body, summary_rows, kind, title=None):
    """Returns (text, html). Tables and inline styles only, so Outlook and Gmail render it alike."""
    color = COLORS[kind]
    icon = ICONS[kind]
    title = title or subject
    order = {k: i for i, (k, _) in enumerate(LABELS)}
    labels = dict(LABELS)
    rows = sorted(summary_rows, key=lambda kv: order.get(kv[0], 99))
    rows = [(labels.get(k, k.replace('_', ' ').capitalize()), v) for k, v in rows if v]
    lines = body.splitlines()
    tail_txt = lines[-60:]
    tail_html = lines[-80:]
    when = time.strftime('%A %-d %B %Y, %H:%M')
    text = [title, '=' * len(title), '']
    if rows:
        w = max(len(l) for l, _ in rows)
        text += [f'{l.ljust(w)}  {v}' for l, v in rows] + ['']
    if lines:
        text += [f'Log (last {len(tail_txt)} of {len(lines)} lines):', '-' * 40] + tail_txt
    text += ['', f'Sent by the Immich backup job on the Pi, {when}.']
    tr = ''.join(
        '<tr><td style="padding:7px 14px 7px 0;color:#6b7280;font-size:13px;vertical-align:top;white-space:nowrap">'
        + html_escape(l) + '</td><td style="padding:7px 0;font-size:14px;vertical-align:top">' + html_escape(v) + '</td></tr>'
        for l, v in rows)
    table = '<table cellpadding="0" cellspacing="0" style="border-collapse:collapse">' + tr + '</table>' if rows else ''
    log_block = ''
    if lines:
        log_block = ('<div style="font-size:12px;color:#6b7280;margin:18px 0 6px">Log, last ' + str(len(tail_html)) + ' of ' + str(len(lines)) + ' lines</div>'
                     '<pre style="margin:0;background:#f3f4f6;border-radius:6px;padding:12px;font-size:12px;line-height:1.45;'
                     'white-space:pre-wrap;word-break:break-word;font-family:Menlo,Consolas,monospace">' + html_escape('\n'.join(tail_html)) + '</pre>')
    html = ('<!doctype html><html><body style="margin:0;padding:0;background:#f4f5f7;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#111827">'
            '<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7"><tr><td align="center" style="padding:24px 12px">'
            '<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:#ffffff;border-radius:8px">'
            '<tr><td style="background:' + color + ';color:#ffffff;padding:18px 28px;font-size:19px;font-weight:600;border-radius:8px 8px 0 0">'
            + icon + '&nbsp; ' + html_escape(title) + '</td></tr>'
            '<tr><td style="padding:18px 28px 6px 28px">' + table + log_block + '</td></tr>'
            '<tr><td style="padding:14px 28px 22px 28px;color:#9ca3af;font-size:11px">Sent by the Immich backup job on the Pi, ' + when + '.</td></tr>'
            '</table></td></tr></table></body></html>')
    return '\n'.join(text), html


def build_message(cfg, subject, body, summary_rows=(), kind=None, title=None):
    kind = kind or guess_kind(subject)
    if len(body) > 300000:
        body = body[-300000:]
    text, html = render(subject, body, list(summary_rows), kind, title)
    msg = email.message.EmailMessage()
    msg['Subject'] = subject
    # "from" stays a bare address (immich_smtp.py builds Immich's own sender from it); the inbox shows "from_name".
    name, addr = email.utils.parseaddr(cfg['from'])
    msg['From'] = email.utils.formataddr((cfg.get('from_name') or name or 'Immich on Pi', addr))
    msg['To'] = ', '.join(cfg['to'])
    # Every mail carries its own Date and Message-ID; they are not left to a mail relay.
    msg['Date'] = email.utils.formatdate(localtime=True)
    msg['Message-ID'] = email.utils.make_msgid(domain=addr.rpartition('@')[2] or None)
    msg.set_content(text)
    msg.add_alternative(html, subtype='html')
    return msg


def smtp_send(cfg, msg, tries=3):
    port = int(cfg.get('port', 587))
    ctx = ssl.create_default_context()          # verifies the server certificate
    last = None
    for attempt in range(tries):
        try:
            if port == 465:                      # implicit TLS (cPanel default)
                with smtplib.SMTP_SSL(cfg['host'], port, timeout=60, context=ctx) as s:
                    s.login(cfg['user'], cfg['password'])
                    s.send_message(msg)
            else:                                # STARTTLS on 587
                with smtplib.SMTP(cfg['host'], port, timeout=60) as s:
                    s.starttls(context=ctx)
                    s.login(cfg['user'], cfg['password'])
                    s.send_message(msg)
            return
        except Exception as e:
            last = e
            if attempt < tries - 1:
                time.sleep(60)
    raise last


def queue_mail(subject, body):
    os.makedirs(PENDING_DIR, exist_ok=True)
    path = os.path.join(PENDING_DIR, f'{int(time.time())}-{os.getpid()}.txt')
    with open(path, 'w') as f:
        f.write(subject + '\n' + body)
    return path


def cmd_email(args):
    if not os.path.exists(SMTP_FILE):
        print('email not configured (no smtp.json); skipped')
        return 0
    cfg = json.load(open(SMTP_FILE))
    if args.flush:
        files = sorted(glob.glob(os.path.join(PENDING_DIR, '*.txt')))
        if not files:
            print('no pending mail')
            return 0
        sent = 0
        for path in files:
            subject, _, body = open(path, errors='replace').read().partition('\n')
            try:
                smtp_send(cfg, build_message(cfg, '(delayed) ' + subject, body), tries=1)
                os.unlink(path); sent += 1
            except Exception as e:
                print(f'still cannot send {os.path.basename(path)}: {e}')
                break
        print(f'pending mail: {sent} sent, {len(files) - sent} left')
        return 0 if sent == len(files) else 1
    body = open(args.body_file, errors='replace').read() if args.body_file else ''
    rows = read_summary(args.summary)
    if args.dry:
        print(f'DRY email to {cfg["to"]}: subject "{args.subject}", {len(body)} bytes, {len(rows)} summary rows, kind {args.kind or guess_kind(args.subject)}')
        return 0
    try:
        smtp_send(cfg, build_message(cfg, args.subject, body, rows, args.kind, args.title))
        print(f'email sent to {", ".join(cfg["to"])}')
        return 0
    except Exception as e:
        path = queue_mail(args.subject, body)
        print(f'email failed ({e}); queued as {path}')
        return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('dump')
    p = sub.add_parser('export-config'); p.add_argument('out')
    p = sub.add_parser('verify')
    p.add_argument('--backup-root', default=os.path.join(BACKUP_MNT, 'media'))
    p.add_argument('--source-root', default=os.path.join(IMMICH_DATA, 'media'))
    p.add_argument('--copied', help='file with relative paths copied in this run, one per line')
    p.add_argument('--sample-pct', type=float, default=2.0)
    p.add_argument('--full', action='store_true')
    p.add_argument('--before', help='ISO timestamp; only assets created before it are expected on the backup')
    p.add_argument('--report', required=True)
    p = sub.add_parser('email'); p.add_argument('--subject', default='(no subject)'); p.add_argument('--body-file')
    p.add_argument('--flush', action='store_true', help='send queued mail'); p.add_argument('--dry', action='store_true')
    p.add_argument('--summary', help='key=value lines shown as the facts table'); p.add_argument('--kind', choices=['pass', 'fail', 'warn', 'info'])
    p.add_argument('--title', help='header line (default: the subject)')
    p = sub.add_parser('deletion-stats'); p.add_argument('--removed-root', default=os.path.join(BACKUP_MNT, 'removed'))
    p.add_argument('--keep-days', type=int, default=int(C.get('KEEP_REMOVED_DAYS', '84') or 84))
    p.add_argument('--next-run-days', type=int, default=7)
    args = ap.parse_args()
    return {'dump': cmd_dump, 'export-config': cmd_export_config, 'verify': cmd_verify, 'email': cmd_email,
            'deletion-stats': cmd_deletion_stats}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
