# Per-run rows and per-case distribution (min/median/max) from ns2_measure/out (no document text stored there).
import glob, json, os, statistics, sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "ns2_measure/out"
M = lambda b: round(b / 2**20, 1) if b else None
rows = []
for ex in sorted(glob.glob(f"{OUT}/*.exit.json")):
    e = json.load(open(ex)); c = e["case"]
    d = json.load(open(f"{OUT}/{c}.drive.json")) if os.path.exists(f"{OUT}/{c}.drive.json") else {}
    s = json.load(open(f"{OUT}/{c}.sampler.json")) if os.path.exists(f"{OUT}/{c}.sampler.json") else {}
    res = d.get("results") or []
    bl = d.get("baselines") or []
    row = dict(case=c, id=e["id"], run=e["run"], workers=e["workers"], cpus=e["cpus"], scenario=e["scenario"],
               peak_kernel=M(s.get("memory_peak")), peak_sampled=M(s.get("cg_current")), oom_kill=s.get("oom_kill"),
               container_oomkilled=e["container_oomkilled"], boots=e["worker_boots"], sigkills=e["worker_sigkills"],
               master=M(s.get("rss_master")), worker_max=M(s.get("rss_worker_max")), workers_sum=M(s.get("rss_workers_sum")),
               tess_each=M(s.get("rss_tesseract_each")), tess_conc=s.get("tesseract_concurrent"), workers_alive_max=s.get("workers_alive_max"),
               worker_pids=len(s.get("worker_pids_seen") or []), ready_s=d.get("ready_s"),
               base_start=(d.get("baseline_start") or {}).get("cg_mib"), base_start_worker=(d.get("baseline_start") or {}).get("worker_rss_mib"),
               base_end=bl[-1]["cg_mib"] if bl else None, base_series=[b["cg_mib"] for b in bl] if len(bl) > 2 else None,
               load=d.get("load"), cancels=d.get("cancels"), error=d.get("error"),
               jobs=[{k: r.get(k) for k in ("file", "role", "http", "ok", "exc", "scanned", "ocr_used", "chars", "sha", "pages", "pages_match_truth",
                                            "cer", "wr", "cer_pages_max", "conf", "review", "input_intact", "secs", "wall_s", "pid", "seq", "pair")}
                     for r in res])
    rows.append(row)
json.dump(rows, open(f"{OUT}/summary_rows.json", "w"), indent=1, ensure_ascii=False)

agg = {}
for r in rows:
    agg.setdefault(r["id"], []).append(r)
lines = ["| case | W | cpus | scenario | runs | peak min/med/max MiB | margin to 512 (min) | base start med | base end med | master | worker max | tess each | OOM kills | jobs ok/total | max job s | load req (p95 s) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for i, rs in sorted(agg.items()):
    pk = [r["peak_kernel"] or r["peak_sampled"] for r in rs if (r["peak_kernel"] or r["peak_sampled"])]
    md = lambda xs: round(statistics.median(xs), 1) if xs else None
    jobs = [j for r in rs for j in r["jobs"]]
    ok = sum(1 for j in jobs if j.get("ok"))
    ld = [r["load"] for r in rs if r.get("load")]
    lines.append("| " + " | ".join(str(x) for x in [
        i, rs[0]["workers"], rs[0]["cpus"], rs[0]["scenario"][:60], len(rs),
        f"{min(pk)}/{md(pk)}/{max(pk)}" if pk else "-", round(512 - max(pk), 1) if pk else "-",
        md([r["base_start"] for r in rs if r["base_start"]]), md([r["base_end"] for r in rs if r["base_end"]]),
        max((r["master"] or 0) for r in rs), max((r["worker_max"] or 0) for r in rs), max((r["tess_each"] or 0) for r in rs),
        sum((r["oom_kill"] or 0) for r in rs), f"{ok}/{len(jobs)}", max([j.get("wall_s") or 0 for j in jobs] or [0]),
        ",".join(f"{l['requests']}({l['p95_s']})" for l in ld) or "-"]) + " |")
txt = "\n".join(lines)
print(txt)
print()
# job-level integrity: same file -> same text hash everywhere; per-file quality
byf = {}
for j in (j for r in rows for j in r["jobs"]):
    if j.get("ok"):
        byf.setdefault(j["file"], []).append(j)
ql = ["| file | jobs | distinct text sha | pages ok | CER min/max | word recall min | conf | input intact | scanned flags |", "|---|---|---|---|---|---|---|---|---|"]
for f, js in sorted(byf.items()):
    ce = [j["cer"] for j in js if j.get("cer") is not None]
    ql.append("| " + " | ".join(str(x) for x in [f, len(js), len({j['sha'] for j in js}), all(j.get("pages_match_truth") in (True, None) for j in js),
              f"{min(ce)}/{max(ce)}" if ce else "-", min([j['wr'] for j in js if j.get('wr') is not None] or [None]) if any(j.get('wr') is not None for j in js) else "-",
              sorted({j.get('conf') for j in js}, key=str)[:3], all(j.get("input_intact") for j in js), sorted({str(j.get('scanned')) for j in js})]) + " |")
print("\n".join(ql))
if os.environ.get("GITHUB_STEP_SUMMARY"):
    open(os.environ["GITHUB_STEP_SUMMARY"], "a").write("## NS2 B1 gunicorn 512 MiB (MiB)\n\n" + txt + "\n\n" + "\n".join(ql) + "\n")
