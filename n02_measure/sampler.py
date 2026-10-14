# Samples every process in the container (own PID namespace => everything is the case under test, incl. tesseract
# subprocesses) + the container cgroup, every ~10 ms. Writes the running peaks to <out> every ~100 ms, so the numbers
# survive even when the OOM killer ends the container. Usage: sampler.py <out.json>
import json, os, sys, time

out = sys.argv[1]
me = os.getpid()
CG = "/sys/fs/cgroup"


def rd(p):
    try:
        with open(p) as f:
            return f.read()
    except OSError:
        return ""


def anon():
    for line in rd(CG + "/memory.stat").splitlines():
        if line.startswith("anon "):
            return int(line.split()[1])
    return 0


peak = {"rss_total": 0, "rss_python": 0, "rss_tesseract_each": 0, "rss_tesseract_sum": 0, "tesseract_concurrent": 0,
        "cg_current": 0, "cg_anon": 0, "samples": 0}
t0 = time.time(); n = 0
while True:
    tot = py = tsum = tmax = tcnt = 0
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == me:
            continue
        st = rd(f"/proc/{pid}/status")
        name = rss = None
        for line in st.splitlines():
            if line.startswith("Name:"):
                name = line.split()[1]
            elif line.startswith("VmRSS:"):
                rss = int(line.split()[1]) * 1024
        if not rss:
            continue
        tot += rss
        if name and name.startswith("tesseract"):
            tsum += rss; tmax = max(tmax, rss); tcnt += 1
        elif name and name.startswith("python"):
            py = max(py, rss)
    cur = int(rd(CG + "/memory.current") or 0)
    peak["rss_total"] = max(peak["rss_total"], tot); peak["rss_python"] = max(peak["rss_python"], py)
    peak["rss_tesseract_each"] = max(peak["rss_tesseract_each"], tmax); peak["rss_tesseract_sum"] = max(peak["rss_tesseract_sum"], tsum)
    peak["tesseract_concurrent"] = max(peak["tesseract_concurrent"], tcnt)
    peak["cg_current"] = max(peak["cg_current"], cur); peak["cg_anon"] = max(peak["cg_anon"], anon())
    n += 1; peak["samples"] = n; peak["elapsed_s"] = round(time.time() - t0, 2)
    if n % 10 == 0:
        tmp = out + ".tmp"
        with open(tmp, "w") as f:
            json.dump(peak, f)
        os.replace(tmp, out)
    time.sleep(0.01)
