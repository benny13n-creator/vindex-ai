#!/usr/bin/env bash
# Host side: one fresh 512 MiB container per case; records exit code and Docker's OOMKilled flag.
set -u
IMG=${IMG:-vx}
CASES=${1:-n02_measure/cases.txt}
mkdir -p n02_measure/out n02_measure/logs
while read -r id variant mode spec cpus; do
  [ -z "${id:-}" ] && continue
  case "$id" in \#*) continue;; esac
  extra=""
  [ -n "${cpus:-}" ] && extra="--cpus=$cpus"
  start=$(date +%s.%N)
  docker run --name "c_$id" --memory=512m --memory-swap=512m $extra --env-file n02_measure/env.list \
    -v "$PWD/n02_measure:/m" -e OUT=/m/out -e FX=/m/fx "$IMG" \
    python /m/case.py "$id" "$variant" "$mode" "$spec" > "n02_measure/logs/$id.log" 2>&1
  ec=$?
  end=$(date +%s.%N)
  oom=$(docker inspect -f '{{.State.OOMKilled}}' "c_$id")
  docker rm "c_$id" > /dev/null
  echo "{\"case\":\"$id\",\"exit\":$ec,\"oomkilled\":$oom,\"cpus\":\"${cpus:-}\",\"container_s\":$(python3 -c "print(round($end-$start,1))")}" > "n02_measure/out/$id.exit.json"
  echo "N02EXIT $id variant=$variant mode=$mode spec=$spec exit=$ec oomkilled=$oom"
  if [ "$ec" != "0" ]; then grep -v "deprecated" "n02_measure/logs/$id.log" | tail -n 12 | cut -c1-300 | sed 's/^/   /'; fi
done < "$CASES"
