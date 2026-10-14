#!/usr/bin/env bash
# NS2 TASK B measurement (measurement branch only, never merged).
# One fresh container per case from the PRODUCTION Dockerfile image. Synthetic/fake env only.
# Case line: <id> <mem> <conf: old|new|none> <WEB_CONCURRENCY value or -> <cmd: gunicorn|dockercmd>
#   old = gunicorn.conf.py at dd619e9a (default 4), new = gunicorn.conf.py at 6e08073b (default 1)
# Per case: wait up to 120 s for /health, settle 45 s, then 30 GETs to /health (new TCP connection each, 1 s apart),
# read memory.current / memory.peak / memory.events from the HOST cgroup, list processes in the cgroup, count
# "Booting worker" lines and OOM kills.
set -u
IMG=${IMG:-vx}
mkdir -p ns2b_measure/out
FEK=$(python3 -c "import secrets; print(secrets.token_hex(32))")
while read -r id mem conf wc cmd; do
  [ -z "${id:-}" ] && continue
  case "$id" in \#*) continue;; esac
  name="c_$id"
  envwc=""; [ "$wc" != "-" ] && envwc="-e WEB_CONCURRENCY=$wc"
  memarg="--memory=$mem --memory-swap=$mem"
  if [ "$cmd" = "dockercmd" ]; then
    run_cmd=""
  else
    cfile=/app/gunicorn.conf.py; [ "$conf" = old ] && cfile=/m/gunicorn_old.conf.py
    run_cmd="gunicorn api:app -c $cfile"
  fi
  docker run -d --name "$name" $memarg $envwc -e PORT=10000 -p 10000:10000 \
    --env-file ns2b_measure/env.list -e FIELD_ENCRYPTION_KEY="$FEK" \
    -v "$PWD/ns2b_measure:/m:ro" "$IMG" $run_cmd > /dev/null
  full=$(docker inspect -f '{{.Id}}' "$name")
  cg=/sys/fs/cgroup/system.slice/docker-$full.scope
  [ -d "$cg" ] || cg=$(find /sys/fs/cgroup -maxdepth 4 -type d -name "*$full*" | head -n 1)
  up=0; t0=$(date +%s)
  for i in $(seq 1 120); do
    if curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:10000/health | grep -q 200; then up=1; break; fi
    sleep 1
  done
  boot_s=$(( $(date +%s) - t0 ))
  sleep 45
  pids=""; workers_field=""
  for i in $(seq 1 30); do
    r=$(curl -s -m 5 -H 'Connection: close' http://127.0.0.1:10000/health)
    p=$(echo "$r" | python3 -c "import sys,json
try:
  d=json.load(sys.stdin); print(d.get('pid'), d.get('workers'))
except Exception: print('ERR ERR')")
    pids="$pids ${p% *}"; workers_field="${p#* }"
    sleep 1
  done
  memcur=$(cat "$cg/memory.current" 2>/dev/null || echo NA)
  mempeak=$(cat "$cg/memory.peak" 2>/dev/null || echo NA)
  oomk=$(grep -E '^oom_kill ' "$cg/memory.events" 2>/dev/null | awk '{print $2}')
  plist=$(for p in $(cat "$cg/cgroup.procs" 2>/dev/null); do
            echo "$p:$(awk '/^Name:/{n=$2} /^PPid:/{pp=$2} /^VmRSS:/{r=$2} END{print n":"pp":"int(r/1024)"MiB"}' /proc/$p/status 2>/dev/null)"
          done | tr '\n' ' ')
  nproc_py=$(for p in $(cat "$cg/cgroup.procs" 2>/dev/null); do awk '/^Name:/{print $2}' /proc/$p/status 2>/dev/null; done | grep -c -E 'gunicorn|uvicorn|python')
  docker logs "$name" > "ns2b_measure/out/$id.log" 2>&1
  boots=$(grep -c "Booting worker" "ns2b_measure/out/$id.log")
  sigk=$(grep -c -E "SIGKILL|Perhaps out of memory" "ns2b_measure/out/$id.log")
  st=$(docker inspect -f '{{.State.Status}} oomkilled={{.State.OOMKilled}} restarts={{.RestartCount}}' "$name")
  ctr_pid1=$(docker exec "$name" sh -c 'cat /proc/1/cmdline | tr "\0" " "' 2>/dev/null)
  uniq_pids=$(echo $pids | tr ' ' '\n' | sort | uniq -c | tr '\n' ';' | tr -s ' ')
  docker rm -f "$name" > /dev/null
  echo "NS2B $id mem=$mem conf=$conf WEB_CONCURRENCY=$wc cmd=$cmd up=$up boot_s=$boot_s state=[$st] booting_worker_lines=$boots sigkill_lines=$sigk cg_oom_kill=${oomk:-NA} mem_current_mib=$(( ${memcur:-0} / 1048576 )) mem_peak_mib=$( [ "$mempeak" != NA ] && echo $(( mempeak / 1048576 )) || echo NA) py_procs=$nproc_py health_workers_field=$workers_field pid_dist=[$uniq_pids] pid1=[$ctr_pid1]"
  echo "NS2B_PROCS $id $plist"
done < "$1"
