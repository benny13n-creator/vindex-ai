#!/usr/bin/env bash
# One fresh container per case, started with the PRODUCTION start command shape:
#   gunicorn <app>:app -c gunicorn.conf.py   (gunicorn.conf.py unchanged: UvicornWorker, timeout 120, max_requests 1000)
# under --memory=512m --memory-swap=512m. Memory is sampled from the HOST (cgroup v2 scope of the container), so the
# sampler itself is not inside the measured cgroup. Usage: run_b1.sh <cases file> <run tag>
set -u
IMG=${IMG:-vx}
CASES=$1; TAG=$2
mkdir -p ns2_measure/out ns2_measure/logs
FEK=$(python3 -c "import secrets; print(secrets.token_hex(32))")
while read -r id workers cpus scenario envs; do
  [ -z "${id:-}" ] && continue
  case "$id" in \#*) continue;; esac
  cid_name="c_${id}_${TAG}"; case_id="${id}_${TAG}"
  extra=""; [ "$cpus" != "-" ] && extra="--cpus=$cpus"
  for kv in $(echo "${envs:-}" | tr "," " "); do [ "$kv" != "-" ] && extra="$extra -e $kv"; done
  rm -f "ns2_measure/out/$case_id.stop"
  docker run -d --name "$cid_name" --memory=512m --memory-swap=512m $extra -p 10000:10000 \
    --env-file ns2_measure/env.list -e FIELD_ENCRYPTION_KEY="$FEK" -e WEB_CONCURRENCY="$workers" -e PORT=10000 \
    -e PYTHONPATH=/m -e FX=/m/fx -v "$PWD/ns2_measure:/m" -w /app "$IMG" \
    gunicorn gapp:app -c gunicorn.conf.py > /dev/null
  full=$(docker inspect -f '{{.Id}}' "$cid_name")
  cg=/sys/fs/cgroup/system.slice/docker-$full.scope
  [ -d "$cg" ] || cg=$(find /sys/fs/cgroup -maxdepth 4 -type d -name "*$full*" | head -n 1)
  sudo python3 ns2_measure/hsampler.py "$cg" "ns2_measure/out/$case_id.sampler.json" "ns2_measure/out/$case_id.stop" &
  sp=$!
  start=$(date +%s)
  timeout 2400 python3 ns2_measure/drive.py "$case_id" "$scenario" "$cg"
  touch "ns2_measure/out/$case_id.stop"; wait $sp
  docker logs "$cid_name" > "ns2_measure/logs/$case_id.log" 2>&1
  oomk=$(docker inspect -f '{{.State.OOMKilled}}' "$cid_name"); st=$(docker inspect -f '{{.State.Status}}' "$cid_name")
  boots=$(grep -c "Booting worker" "ns2_measure/logs/$case_id.log"); kills=$(grep -c "SIGKILL" "ns2_measure/logs/$case_id.log")
  docker rm -f "$cid_name" > /dev/null
  echo "{\"case\":\"$case_id\",\"id\":\"$id\",\"run\":\"$TAG\",\"workers\":\"$workers\",\"cpus\":\"$cpus\",\"scenario\":\"$scenario\",\"envs\":\"${envs:-}\",\"container_oomkilled\":$oomk,\"state\":\"$st\",\"worker_boots\":$boots,\"worker_sigkills\":$kills,\"secs\":$(( $(date +%s) - start ))}" > "ns2_measure/out/$case_id.exit.json"
  echo "NS2EXIT $case_id workers=$workers cpus=$cpus envs=${envs:-} $scenario oomkilled=$oomk boots=$boots sigkills=$kills"
  grep -E "SIGKILL|out of memory|Worker exiting|Traceback" "ns2_measure/logs/$case_id.log" | head -n 5 | cut -c1-200 | sed 's/^/   /'
done < "$CASES"
