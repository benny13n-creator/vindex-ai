# HOST-side sampler for one container's cgroup v2 (nothing runs inside the measured cgroup).
# memory.current every ~10 ms; memory.stat anon/file/kernel every ~50 ms (NS2b); per-process RSS (gunicorn master / workers / tesseract / other) every ~50 ms.
# Writes running peaks + a 100 ms timeline to <out>.json every ~0.5 s and on exit (cgroup gone or <stop> file).
# Usage: hsampler.py <cgroup_dir> <out.json> <stopfile>
import json, os, sys, time

cg, out, stop = sys.argv[1:4]


def rd(p):
    try:
        with open(p) as f:
            return f.read()
    except OSError:
        return None


def procs():
    r = {}
    for pid in (rd(cg + "/cgroup.procs") or "").split():
        st = rd(f"/proc/{pid}/status")
        if not st:
            continue
        d = {}
        for line in st.splitlines():
            k, _, v = line.partition(":")
            if k in ("Name", "PPid", "VmRSS"):
                d[k] = v.strip()
        if "VmRSS" not in d:
            continue
        r[int(pid)] = (d.get("Name", "?"), int(d.get("PPid", 0)), int(d["VmRSS"].split()[0]) * 1024)
    return r


peak = {"cg_current": 0, "rss_total": 0, "rss_master": 0, "rss_workers_sum": 0, "rss_worker_max": 0, "workers_alive_max": 0,
        "rss_tesseract_sum": 0, "rss_tesseract_each": 0, "tesseract_concurrent": 0, "samples": 0,
        "anon": 0, "file_at_anon_peak": 0, "anon_at_cur_peak": 0, "file_at_cur_peak": 0, "kernel_at_cur_peak": 0, "stat_samples": 0}
timeline = []          # (t, cg_current_mib, workers_alive, tesseract_n)
worker_pids = set()
oom_kill = 0
mem_peak = None
t0 = time.time(); n = 0; last_w = 0; last_proc = 0; last_tl = 0
alive_w = tn = 0
while True:
    cur = rd(cg + "/memory.current")
    if cur is None or os.path.exists(stop):
        break
    cur = int(cur); now = time.time() - t0
    peak["cg_current"] = max(peak["cg_current"], cur)
    ev = rd(cg + "/memory.events") or ""
    for line in ev.splitlines():
        if line.startswith("oom_kill "):
            oom_kill = int(line.split()[1])
    mp = rd(cg + "/memory.peak")
    if mp:
        mem_peak = int(mp)
    if now - last_proc >= 0.05:
        last_proc = now
        ms = {}
        for line in (rd(cg + "/memory.stat") or "").splitlines():
            k, _, v = line.partition(" ")
            if k in ("anon", "file", "kernel"):
                ms[k] = int(v)
        if ms:
            peak["stat_samples"] += 1
            if ms.get("anon", 0) > peak["anon"]:
                peak["anon"] = ms["anon"]; peak["file_at_anon_peak"] = ms.get("file", 0)
            if cur >= peak["cg_current"]:
                peak["anon_at_cur_peak"] = ms.get("anon", 0); peak["file_at_cur_peak"] = ms.get("file", 0); peak["kernel_at_cur_peak"] = ms.get("kernel", 0)
        ps = procs()
        pids = set(ps)
        master = [p for p, (nm, pp, _) in ps.items() if pp not in pids and nm != "tesseract"]
        mpid = master[0] if master else None
        tot = sum(v[2] for v in ps.values())
        ws = [(p, v) for p, v in ps.items() if v[1] == mpid and v[0] != "tesseract"]
        ts = [v for v in ps.values() if v[0] == "tesseract"]
        for p, _ in ws:
            worker_pids.add(p)
        alive_w = len(ws); tn = len(ts)
        peak["rss_total"] = max(peak["rss_total"], tot)
        if mpid:
            peak["rss_master"] = max(peak["rss_master"], ps[mpid][2])
        peak["rss_workers_sum"] = max(peak["rss_workers_sum"], sum(v[2] for _, v in ws))
        peak["rss_worker_max"] = max([peak["rss_worker_max"]] + [v[2] for _, v in ws])
        peak["workers_alive_max"] = max(peak["workers_alive_max"], alive_w)
        peak["rss_tesseract_sum"] = max(peak["rss_tesseract_sum"], sum(v[2] for v in ts))
        peak["rss_tesseract_each"] = max([peak["rss_tesseract_each"]] + [v[2] for v in ts])
        peak["tesseract_concurrent"] = max(peak["tesseract_concurrent"], tn)
    if now - last_tl >= 0.1:
        last_tl = now
        timeline.append((round(now, 2), round(cur / 2**20, 1), alive_w, tn))
    n += 1; peak["samples"] = n
    if now - last_w >= 0.5:
        last_w = now
        res = dict(peak, oom_kill=oom_kill, memory_peak=mem_peak, worker_pids_seen=sorted(worker_pids), elapsed=round(now, 1), timeline=timeline)
        with open(out + ".tmp", "w") as f:
            json.dump(res, f)
        os.replace(out + ".tmp", out)
    time.sleep(0.01)
res = dict(peak, oom_kill=oom_kill, memory_peak=mem_peak, worker_pids_seen=sorted(worker_pids), elapsed=round(time.time() - t0, 1), timeline=timeline)
with open(out + ".tmp", "w") as f:
    json.dump(res, f)
os.replace(out + ".tmp", out)
