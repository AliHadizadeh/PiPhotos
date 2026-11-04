#!/bin/bash
# usage: bench_ml.sh URL IMAGE SEQ PAR   (PAR=0 skips the parallel run)
URL=$1; IMG=$2; SEQ=${3:-20}; PAR=${4:-6}
[ -f "$IMG" ] || { echo "image not found: $IMG"; exit 1; }
now() { date +%s%3N; }
bench() {
  local name=$1 entries=$2
  local t0=$(now)
  local code=$(curl -s -o /tmp/bench_resp.json -w "%{http_code}" --max-time 1200 -F "entries=$entries" -F "image=@$IMG" "$URL/predict")
  local t1=$(now)
  printf "%-30s warm-up http %s in %d ms; reply: %s\n" "$name" "$code" $((t1-t0)) "$(head -c 90 /tmp/bench_resp.json | tr -d "\n")"
  [ "$code" = "200" ] || return
  t0=$(now)
  for i in $(seq $SEQ); do curl -s -o /dev/null --max-time 300 -F "entries=$entries" -F "image=@$IMG" "$URL/predict"; done
  t1=$(now)
  printf "   sequential: %d req, %d ms/req\n" $SEQ $(((t1-t0)/SEQ))
  if [ "$PAR" -gt 0 ]; then
    local N=$((SEQ*3))
    t0=$(now)
    seq $N | xargs -P $PAR -I{} curl -s -o /dev/null --max-time 300 -F "entries=$entries" -F "image=@$IMG" "$URL/predict"
    t1=$(now)
    printf "   parallel x%d: %d req in %d ms = %d req/s\n" $PAR $N $((t1-t0)) $((N*1000/(t1-t0)))
  fi
}
bench "CLIP ViT-B-32__openai (default)" "{\"clip\":{\"visual\":{\"modelName\":\"ViT-B-32__openai\"}}}"
bench "CLIP ViT-B-16-SigLIP2__webli" "{\"clip\":{\"visual\":{\"modelName\":\"ViT-B-16-SigLIP2__webli\"}}}"
bench "faces buffalo_l det+rec" "{\"facial-recognition\":{\"detection\":{\"modelName\":\"buffalo_l\",\"options\":{\"minScore\":0.7}},\"recognition\":{\"modelName\":\"buffalo_l\"}}}"
