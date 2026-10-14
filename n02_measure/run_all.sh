#!/usr/bin/env bash
# Host side: one fresh 512 MiB container per case; records exit code and Docker's OOMKilled flag.
set -u
IMG=${IMG:-vx}
CASES=${1:-n02_measure/cases.txt}
mkdir -p n02_measure/out n02_measure/logs
# importing api requires a valid field key: a throwaway random one per job (never a literal in the repo)
FEK=$(python3 -c "import secrets; print(secrets.token_hex(32))")
while read -r id variant mode spec cpus mem; do
  [ -z "${id:-}" ] && continue
  case "$id" in \#*) continue;; esac
  extra=""
  [ -n "${cpus:-}" ] && [ "$cpus" != "-" ] && extra="--cpus=$cpus"
  lim="--memory=512m --memory-swap=512m"
  [ "${mem:-}" = "none" ] && lim=""
  start=$(date +%s.%N)
  docker run --name "c_$id" $lim $extra --env-file n02_measure/env.list -e FIELD_ENCRYPTION_KEY="$FEK" \
    -v "$PWD/n02_measure:/m" -e OUT=/m/out -e FX=/m/fx "$IMG" \
    python /m/case.py "$id" "$variant" "$mode" "$spec" > "n02_measure/logs/$id.log" 2>&1 < /dev/null
  ec=$?
  end=$(date +%s.%N)
  oom=$(docker inspect -f '{{.State.OOMKilled}}' "c_$id")
  docker rm "c_$id" > /dev/null
  echo "{\"case\":\"$id\",\"exit\":$ec,\"oomkilled\":$oom,\"cpus\":\"${cpus:-}\",\"mem\":\"${mem:-512m}\",\"container_s\":$(python3 -c "print(round($end-$start,1))")}" > "n02_measure/out/$id.exit.json"
  echo "N02EXIT $id variant=$variant mode=$mode spec=$spec exit=$ec oomkilled=$oom"
  if [ "$ec" != "0" ]; then grep -v "deprecated" "n02_measure/logs/$id.log" | tail -n 12 | cut -c1-300 | sed 's/^/   /'; fi
done < "$CASES"
