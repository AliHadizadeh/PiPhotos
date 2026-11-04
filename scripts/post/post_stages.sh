#!/bin/bash
# post_stages.sh - run the machine-learning stages after a migration, in order, through the jobs API.
# Immich chains search, faces, OCR and duplicates only after an upload's thumbnail job. Re-queued jobs do not
# chain, so each stage is queued with its own "missing" command once the previous one has drained.
# Stages: 0 wait for thumbnails; 1 smart search + face detection; 2 OCR + duplicate detection;
#         3 face clustering (concurrency 1); 4 person thumbnails; 5 final machine-learning address order.
# Video conversion is NOT queued here on purpose: see chapter 6 (probe_videos.py, queue_transcodes.py).
#
# Environment: KEY_FILE (admin API key, default ~/.config/immich-tools/admin.key), IMMICH_SERVER (default
# http://localhost:2283), GPU_URL and CPU_URL (optional machine-learning addresses on another machine),
# PI_URL (the Pi's own container, default http://immich-machine-learning:3003).
# Run it detached:  nohup setsid ./post_stages.sh > post_stages.log 2>&1 &
set -u
KEY_FILE=${KEY_FILE:-$HOME/.config/immich-tools/admin.key}; KEY=$(cat "$KEY_FILE")
SERVER=${IMMICH_SERVER:-http://localhost:2283}; API=$SERVER/api
GPU_URL=${GPU_URL:-}; CPU_URL=${CPU_URL:-}; PI_URL=${PI_URL:-http://immich-machine-learning:3003}
SET_ML="python3 $(dirname "$0")/../ml/set_remote_ml.py --server $SERVER --api-key-file $KEY_FILE"
log() { echo "$(date '+%F %T') $*"; }
jobs_json() { curl -s -H "x-api-key: $KEY" "$API/jobs"; }
pending() { jobs_json | python3 -c '
import sys,json; d=json.load(sys.stdin); qs=sys.argv[1:]
print(sum(d[q]["jobCounts"]["active"]+d[q]["jobCounts"]["waiting"]+d[q]["jobCounts"]["paused"]+d[q]["jobCounts"]["delayed"] for q in qs))' "$@"; }
snap() { jobs_json | python3 -c '
import sys,json,time; d=json.load(sys.stdin); out=[]
for k in ("thumbnailGeneration","smartSearch","faceDetection","ocr","duplicateDetection","facialRecognition","videoConversion"):
    c=d[k]["jobCounts"]; out.append("%s=%da/%dq/%df" % (k, c["active"], c["waiting"]+c["paused"], c["failed"]))
print(time.strftime("%F %T"), " ".join(out))'; }
cmd() { curl -s -o /dev/null -w "%{http_code}" -X PUT -H "x-api-key: $KEY" -H "Content-Type: application/json" -d "{\"command\":\"$2\",\"force\":false}" "$API/jobs/$1"; }
start_missing() {  # Immich answers 400 "Job is already running" while the queue is active: retry
  for i in $(seq 1 180); do c=$(cmd "$1" start); if [ "$c" = 200 ]; then log "$1: queued missing (attempt $i)"; return 0; fi; sleep 10; done
  log "$1: could not queue missing (last http $c)"; return 1; }
wait_drain() {  # until the given queues are empty on two consecutive checks
  local zero=0; while true; do n=$(pending "$@"); if [ "$n" -eq 0 ]; then zero=$((zero+1)); [ $zero -ge 2 ] && return 0; else zero=0; fi; sleep 60; done; }
urls() { [ -n "$GPU_URL" ] || return 0; $SET_ML "$@" | tail -1; }

log "stage 0: waiting for thumbnails ($(pending thumbnailGeneration) pending)"
i=0; while [ "$(pending thumbnailGeneration)" -gt 0 ]; do sleep 120; i=$((i+1)); [ $((i%30)) -eq 0 ] && log "thumbnails pending: $(pending thumbnailGeneration)"; done
log "thumbnails done"; snap

log "stage 1: smart search + face detection"
[ -n "$GPU_URL" ] && urls --add-url "$GPU_URL"
start_missing smartSearch; start_missing faceDetection
sleep 120; snap; wait_drain smartSearch faceDetection; log "search + faces done"; snap

log "stage 2: OCR + duplicate detection"
[ -n "$CPU_URL" ] && urls --add-url "$CPU_URL"
start_missing ocr; start_missing duplicateDetection
sleep 120; snap; wait_drain ocr duplicateDetection; log "ocr + duplicates done"; snap

log "stage 3: face clustering"
cmd facialRecognition empty >/dev/null; sleep 5
start_missing facialRecognition; log "facialRecognition resume -> $(cmd facialRecognition resume)"
sleep 180; snap; wait_drain facialRecognition; log "clustering done"; snap

log "stage 4: person thumbnails"
start_missing thumbnailGeneration; sleep 120; wait_drain thumbnailGeneration; log "person thumbnails done"

if [ -n "$GPU_URL" ]; then
  log "stage 5: final machine-learning order: CPU container, GPU container, the Pi's own container"
  urls --add-url "$PI_URL" >/dev/null; urls --add-url "$GPU_URL" >/dev/null; [ -n "$CPU_URL" ] && urls --add-url "$CPU_URL"
fi
snap; log "all stages done. Next: reconcile_faces.py, then propose_names.py and link_people.py if you have two users"
