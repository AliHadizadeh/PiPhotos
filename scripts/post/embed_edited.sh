#!/bin/bash
# embed_edited.sh ML_URL MODEL MEDIA_ROOT ASSET_ID... - compute the search embedding for assets whose smart-search job
# fails because they carry an edited preview (Immich 3.3: the job wants exactly one preview file), and store it the way
# the job would. Check your version's release notes first; the bug may be fixed. Reads the database through docker.
#   embed_edited.sh http://<gpu-machine>:3003 ViT-B-16-SigLIP2__webli /mnt/immich/media <asset-id> [<asset-id> ...]
set -eu
ML=$1; MODEL=$2; ROOT=$3; shift 3
DB_CONTAINER=${DB_CONTAINER:-immich_postgres}; DB_USER=${DB_USER:-postgres}; DB_NAME=${DB_NAME:-immich}
psql() { docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -At "$@" < /dev/null; }
for id in "$@"; do
  p=$(psql -c "select path from asset_file where \"assetId\"='$id' and type='preview' and \"isEdited\"")
  f=$ROOT/${p#/data/}
  [ -f "$f" ] || { echo "missing $f"; exit 1; }
  vec=$(curl -sf -X POST "$ML/predict" -F "entries={\"clip\":{\"visual\":{\"modelName\":\"$MODEL\"}}}" -F "image=@$f" \
        | python3 -c 'import sys,json; v=json.loads(json.load(sys.stdin)["clip"]); print("[" + ",".join(repr(float(x)) for x in v) + "]")')
  psql -c "insert into smart_search (\"assetId\", embedding) values ('$id', '$vec') on conflict (\"assetId\") do update set embedding = excluded.embedding"
  echo "$id: embedding stored from $(basename "$f")"
done
psql -c "select 'visible assets still without embedding', count(*) from asset a where a.\"deletedAt\" is null and a.visibility='timeline' and not exists (select 1 from smart_search s where s.\"assetId\"=a.id)"
