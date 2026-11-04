#!/bin/bash
# report_failure.sh - runs when immich-backup.service fails. The job normally emails its own result; this only
# reports the case where it died without writing a status (crash, missing script, killed).
CONF=${IMMICH_TOOLS_CONF:-/etc/immich-tools/backup.conf}; . "$CONF"
D=${TOOLS_DIR:-/opt/immich-tools/backup}; STATE_ROOT=${STATE_ROOT:-/var/lib/immich-tools}; PY=$D/venv/bin/python; H=$D/backup_helpers.py
if [ -f "$STATE_ROOT/LAST-RUN.txt" ] && [ $(( $(date +%s) - $(stat -c %Y "$STATE_ROOT/LAST-RUN.txt") )) -lt 600 ]; then
  echo "the run reported itself $(( ($(date +%s) - $(stat -c %Y "$STATE_ROOT/LAST-RUN.txt")) / 60 )) min ago; no extra mail"; exit 0
fi
{ echo "immich-backup.service failed without writing a status line."; echo; systemctl status immich-backup.service --no-pager 2>&1 | head -20;
  echo; echo "--- latest log ---"; tail -30 "$STATE_ROOT/logs/backup-latest.log" 2>/dev/null; } > /tmp/backup-failure.txt
"$PY" "$H" email ${DRY:+--dry} --subject "$(printf "\u274c") Immich backup: the service failed without a report" --kind fail --body-file /tmp/backup-failure.txt
