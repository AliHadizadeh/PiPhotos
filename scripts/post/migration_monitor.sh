#!/bin/bash
# migration_monitor.sh USER... - one-screen status of running migrations and of Immich on the Pi.
# Reads work/<user>.run.log and work/<user>/state.sqlite in the migration tool's folder (MIGRATE_DIR), the systemd
# services immich-migrate@<user>, Docker, the job queues (KEY_FILE = admin key) and the Pi's temperature.
set -u
MIGRATE_DIR=${MIGRATE_DIR:-$(cd "$(dirname "$0")/../migrate" && pwd)}
KEY_FILE=${KEY_FILE:-$HOME/.config/immich-tools/admin.key}; SERVER=${IMMICH_SERVER:-http://localhost:2283}
export PATH=$PATH:/usr/sbin:/sbin
echo "time: $(date '+%a %H:%M')  up: $(uptime -p | sed 's/up //')  load: $(cut -d' ' -f1-3 /proc/loadavg)  $(vcgencmd measure_temp 2>/dev/null)  throttled=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)"
echo "mem: $(free -h | awk 'NR==2{print $3" used, "$7" avail"}')  root: $(df -h / | awk 'NR==2{print $4" free"}')  data: $(df -h ${IMMICH_DATA:-/mnt/immich} | awk 'NR==2{print $3" used, "$4" free"}')"
for lib in "$@"; do
  st=$(systemctl is-active "immich-migrate@$lib.service" 2>/dev/null); nr=$(systemctl show -p NRestarts --value "immich-migrate@$lib.service" 2>/dev/null)
  log=$MIGRATE_DIR/work/$lib.run.log
  last=$(grep -E '^\[' "$log" 2>/dev/null | tail -1); errs=$(grep -cE '^ERROR|Traceback' "$log" 2>/dev/null)
  cnt=$(python3 -c "import sqlite3; c=sqlite3.connect('$MIGRATE_DIR/work/$lib/state.sqlite'); print(c.execute(\"select count(*) from uploads where role='original'\").fetchone()[0], c.execute('select count(*) from errors').fetchone()[0])" 2>/dev/null)
  echo "$lib: service=$st restarts=$nr originals/errors=$cnt log-errors=$errs"; echo "   $last"
done
echo "docker: $(docker ps --format '{{.Names}}={{.Status}}' | grep immich | sed 's/Up //; s/ (healthy)/ ok/' | tr '\n' ' ')"
if [ -f "$KEY_FILE" ]; then
  curl -s -H "x-api-key: $(cat "$KEY_FILE")" "$SERVER/api/jobs" | python3 -c '
import json,sys; j=json.load(sys.stdin); out=[]
for n,v in j.items():
    c=v.get("jobCounts",{}); q=v.get("queueStatus",{})
    if c.get("failed") or c.get("active") or c.get("waiting") or q.get("isPaused"):
        out.append("%s a%s w%s f%s%s" % (n[:14], c.get("active"), c.get("waiting"), c.get("failed"), " PAUSED" if q.get("isPaused") else ""))
print("jobs:", "; ".join(out) or "all idle")'
fi
echo "server log errors, last hour: $(docker logs immich_server --since 60m 2>&1 | grep -ci error)"
