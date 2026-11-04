#!/bin/bash
# watchdog.sh - daily 09:00 check (immich-backup-watch.timer): emails when a failure is standing, when no backup has
# passed for 8 days, when the weekly timer is not enabled, or when the backup drive is powered outside a run.
CONF=${IMMICH_TOOLS_CONF:-/etc/immich-tools/backup.conf}; . "$CONF"
D=${TOOLS_DIR:-/opt/immich-tools/backup}; STATE_ROOT=${STATE_ROOT:-/var/lib/immich-tools}; PY=$D/venv/bin/python; H=$D/backup_helpers.py
BYID=$BACKUP_DISK_BYID
MAIL() { "$PY" "$H" email ${DRY:+--dry} --kind warn --subject "$1" --body-file "$2"; }
"$PY" "$H" email ${DRY:+--dry} --flush >/dev/null 2>&1 || true
status=$(cat "$STATE_ROOT/LAST-RUN.txt" 2>/dev/null || echo "none")
age_days=$(( ( $(date +%s) - $(stat -c %Y "$STATE_ROOT/LAST-RUN.txt" 2>/dev/null || echo 0) ) / 86400 ))
problems=""
case "$status" in
  *FAIL*) problems+="The last backup run FAILED and has not been followed by a successful one: $status\n";;
esac
if ! echo "$status" | grep -q PASS && [ "$age_days" -ge 8 ]; then problems+="No successful backup for $age_days days (status: $status)\n"; fi
if echo "$status" | grep -q PASS && [ "$age_days" -ge 8 ]; then problems+="The last successful backup is $age_days days old: $status\n"; fi
[ "$(systemctl is-enabled immich-backup.timer 2>/dev/null)" = enabled ] || problems+="immich-backup.timer is not enabled\n"
if [ -e "$BYID" ] && ! pgrep -f "[i]mmich_backup.sh|[s]urface_read.sh|[i]nitial_copy.sh" >/dev/null; then
  problems+="The backup drive is powered and attached while no backup job is running (plug: $(PLUG_NOTIFY=0 $PY $D/backup_plug.py status 2>&1))\n"
fi
pending=$(ls "$STATE_ROOT/state/pending-mail" 2>/dev/null | wc -l); [ "$pending" -gt 0 ] && problems+="$pending report mail(s) could not be delivered yet\n"
if [ -n "$problems" ]; then
  { printf "$problems"; echo; echo "next scheduled run: $(systemctl list-timers immich-backup.timer --no-pager 2>/dev/null | sed -n 2p)";
    echo; echo "--- latest log tail ---"; tail -15 "$STATE_ROOT/logs/backup-latest.log" 2>/dev/null; } > /tmp/backup-watch.txt
  MAIL "$(printf "\u26a0\ufe0f") Immich backup needs attention: $(printf "$problems" | head -1 | cut -c1-70)" /tmp/backup-watch.txt
else
  echo "watchdog: all fine ($status)"
fi
