# NS3-A mechanism probe, ONE fresh process per (file, mode). Prints one "MECH3 {json}" line.
#   mode=guard : NS3-A estimate for every page at the dpi the extractor would use + guard cost (time, peak delta)
#   mode=render: real rasterization (_rasterizuj_stranu) of the page with the largest estimate; peak delta
# Linux: VmHWM reset via /proc/self/clear_refs ("5"); Windows: peak working set (no reset, fresh process).
# Usage: mech3.py <pdf> <guard|render>     (cwd = repo root)
import json, os, sys, time

sys.path.insert(0, os.getcwd())
p, mode = sys.argv[1], sys.argv[2]
LINUX = os.path.exists("/proc/self/status")


def st():
    if LINUX:
        d = {}
        for line in open("/proc/self/status"):
            k, _, v = line.partition(":")
            if k in ("VmRSS", "VmHWM"):
                d[k] = int(v.split()[0]) * 1024
        return d["VmRSS"], d["VmHWM"]
    import psutil
    m = psutil.Process().memory_info()
    return m.rss, m.peak_wset


def phase(fn):
    if LINUX:
        open("/proc/self/clear_refs", "w").write("5")
    r0, h0 = st()
    t = time.perf_counter()
    out = fn()
    r1, hwm = st()
    return out, round((hwm - (r0 if LINUX else h0)) / 2**20, 1), round(time.perf_counter() - t, 3)


import fitz  # noqa: E402
from uploaded_doc import extractor as X  # noqa: E402

res = {"file": os.path.basename(p), "mode": mode, "kib": os.path.getsize(p) // 1024}
try:
    doc = fitz.open(p)
    res["is_pdf"], res["pages"] = doc.is_pdf, len(doc)

    def guard():
        out = []
        for i in range(len(doc)):
            s = doc[i]
            dpi = X._dpi_strane(float(s.rect.width), float(s.rect.height))
            try:
                b, o = X._procena_rastera_strane(doc, i, dpi)
                out.append((round(b / 2**20, 1), o, dpi))
            except X._NeproverljivPdf as e:
                out.append((None, "UNKNOWN " + str(e), dpi))
        return out

    est, res["guard_peak_mib"], res["guard_s"] = phase(guard)
    known = [e for e in est if e[0] is not None]
    top = max(range(len(est)), key=lambda i: est[i][0] or 1e9)
    res["est_max_mib"], res["est_top"], res["top_page"] = est[top][0], est[top][1], top + 1
    res["est_pages"] = [e[0] for e in est]
    if mode == "render":
        fitz.TOOLS.store_shrink(100)
        _, res["render_peak_mib"], res["render_s"] = phase(lambda: X._rasterizuj_stranu(doc[top]).size)
except Exception as e:  # noqa: BLE001
    res["exc"] = type(e).__name__ + ": " + str(e)[:160]
print("MECH3 " + json.dumps(res, ensure_ascii=False), flush=True)
