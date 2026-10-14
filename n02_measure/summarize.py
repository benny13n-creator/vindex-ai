# Builds the measurement table from n02_measure/out (no document text is ever stored there).
import glob, json, os
OUT = "n02_measure/out"
rows = []
for ex in sorted(glob.glob(f"{OUT}/*.exit.json")):
    e = json.load(open(ex)); cid = e["case"]
    c = json.load(open(f"{OUT}/{cid}.json")) if os.path.exists(f"{OUT}/{cid}.json") else {}
    s = json.load(open(f"{OUT}/{cid}.sampler.json")) if os.path.exists(f"{OUT}/{cid}.sampler.json") else {}
    m = lambda b: round(b / 2**20) if b else "-"
    res = c.get("results", [])
    def fmt(r):
        if r.get("outcome") == "exception":
            return f"{r['file']}:{r['exc']}"
        q = r.get("cer"); cp = r.get("cer_pages")
        return f"{r['file']}:{r.get('role','')[:1]} {r.get('secs')}s cer={q} conf={r.get('conf')} chars={r.get('chars')}" + (f" pages_cer_max={max(cp)}" if cp else "") + (f" att={r['attempt']} rss={r['rss_after_mib']}" if 'attempt' in r else "")
    rows.append({"case": cid, "variant": c.get("variant", "?"), "mode": c.get("mode", "?"), "cpus": e.get("cpus"),
                 "exit": e["exit"], "oomkilled": e["oomkilled"], "oom_kill_events": (c.get("cg_memory_events") or {}).get("oom_kill", "?"),
                 "cg_peak": c.get("cg_memory_peak_mib", "-"), "cg_peak_sampled": m(s.get("cg_current")), "cg_anon_peak": m(s.get("cg_anon")),
                 "rss_total": m(s.get("rss_total")), "rss_python": m(s.get("rss_python")), "rss_tess_each": m(s.get("rss_tesseract_each")),
                 "tess_conc": s.get("tesseract_concurrent"), "base_api": c.get("rss_after_import_api_mib"), "wall": c.get("wall_s"),
                 "container_s": e.get("container_s"), "results": " ; ".join(fmt(r) for r in res)})
hdr = ["case", "variant", "mode", "cpus", "exit", "oomkilled", "oom_kill_events", "cg_peak", "cg_peak_sampled", "cg_anon_peak", "rss_total",
       "rss_python", "rss_tess_each", "tess_conc", "base_api", "wall", "container_s", "results"]
lines = ["| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
for r in rows:
    lines.append("| " + " | ".join(str(r[h]) for h in hdr) + " |")
txt = "\n".join(lines)
print(txt)
json.dump(rows, open(f"{OUT}/summary.json", "w"), indent=1)
if os.environ.get("GITHUB_STEP_SUMMARY"):
    open(os.environ["GITHUB_STEP_SUMMARY"], "a").write("## N02 512 MiB measurements (MiB)\n\n" + txt + "\n")
