#!/bin/bash
# install.sh - install the backup tools on the Pi. Run with sudo from this folder.
# Copies the scripts to TOOLS_DIR, creates the Python venv with tinytuya, the config and state folders,
# and installs the systemd units and timers. It never starts a backup.
set -eu
SRC=$(cd "$(dirname "$0")" && pwd)
CONF=/etc/immich-tools/backup.conf
[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }
mkdir -p /etc/immich-tools && chmod 700 /etc/immich-tools
if [ ! -f "$CONF" ]; then cp "$SRC/backup.conf.example" "$CONF"; echo "created $CONF from the example: edit it before the first run"; fi
. "$CONF"
D=${TOOLS_DIR:-/opt/immich-tools/backup}; STATE_ROOT=${STATE_ROOT:-/var/lib/immich-tools}
mkdir -p "$D" "$STATE_ROOT/logs" "$STATE_ROOT/state"
install -m 700 "$SRC"/*.sh "$SRC"/*.py "$D/"
cp "$SRC/backup.conf.example" "$SRC/README.md" "$D/"
[ -f "$SRC/../../docs/09-recovery.md" ] && cp "$SRC/../../docs/09-recovery.md" "$D/RECOVERY.md"   # travels onto the backup disk with the scripts
if [ ! -x "$D/venv/bin/python" ]; then
  echo "creating the Python venv and installing tinytuya (the only package)"
  python3 -m venv "$D/venv" && "$D/venv/bin/pip" install --quiet --upgrade pip && "$D/venv/bin/pip" install --quiet "tinytuya==1.20.0"   # pinned; raise it on purpose, not by accident
fi
install -m 644 "$SRC"/immich-backup.service "$SRC"/immich-backup-failed.service "$SRC"/immich-backup-watch.service "$SRC"/immich-backup.timer "$SRC"/immich-backup-watch.timer /etc/systemd/system/
systemctl daemon-reload
# touch the timer stamps so that Persistent=true does not trigger a catch-up run at the first enable
mkdir -p /var/lib/systemd/timers && touch /var/lib/systemd/timers/stamp-immich-backup.timer /var/lib/systemd/timers/stamp-immich-backup-watch.timer
systemctl enable --now immich-backup.timer immich-backup-watch.timer >/dev/null
[ -f "$STATE_ROOT/LAST-RUN.txt" ] || echo "$(date '+%Y-%m-%d %H:%M') NONE (no run yet)" > "$STATE_ROOT/LAST-RUN.txt"
echo "installed in $D; config $CONF; state $STATE_ROOT"
systemctl list-timers 'immich-backup*' --no-pager | head -4
echo "next: put the admin key in ${ADMIN_KEY_FILE:-/etc/immich-tools/admin.key} (mode 600), smtp.json and the plug key; then plug_test.sh, surface_read.sh, initial_copy.sh"
