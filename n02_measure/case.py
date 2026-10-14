# One measurement case inside a fresh `docker run --memory=512m --memory-swap=512m` container.
# Usage: case.py <case_id> <variant> <mode> <spec>
#   variant: "pr24" (/m/variants/extractor_pr24.py) | "image" (the extractor baked into the image = candidate)
#   mode:    worker   -> extract() + necitljive_strane_pdf() like shared/intake_worker.py
#            finalize -> extract() like routers/smart_intake.py finalize
#            threads  -> spec "a|b": worker(a) and finalize(b) in two threads of ONE process (asyncio.to_thread)
#            retries  -> spec "file:n": n sequential attempts in one process (in-process retry)
# Never prints document text: only lengths, hashes, CER against synthetic ground truth.
import hashlib, importlib.util, json, os, subprocess, sys, threading, time, unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

case_id, variant, mode, spec = sys.argv[1:5]
OUT = Path(os.environ.get("OUT", "/m/out")); OUT.mkdir(parents=True, exist_ok=True)
FX = Path(os.environ.get("FX", "/m/fx"))
sam = subprocess.Popen([sys.executable, "/m/sampler.py", str(OUT / f"{case_id}.sampler.json")])
time.sleep(0.3)


def rss_self():
    for line in open("/proc/self/status"):
        if line.startswith("VmRSS:"):
            return round(int(line.split()[1]) / 1024, 1)


sys.path.insert(0, "/app")
os.chdir("/app")
import logging
t = time.perf_counter()
import api  # noqa: F401 — production baseline: the web process has the whole app imported
logging.disable(logging.CRITICAL)
base = {"rss_after_import_api_mib": rss_self(), "import_s": round(time.perf_counter() - t, 1)}

if os.path.exists(f"/m/variants/extractor_{variant}.py"):
    sp = importlib.util.spec_from_file_location("uploaded_doc.extractor", f"/m/variants/extractor_{variant}.py")
    ex = importlib.util.module_from_spec(sp); sys.modules["uploaded_doc.extractor"] = ex; sp.loader.exec_module(ex)
else:
    from uploaded_doc import extractor as ex
import fitz
truth = json.load(open(FX / "truth.json", encoding="utf-8"))


def _norm(t):
    t = "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c))
    return " ".join(t.lower().split())


def _lev(a, b):
    if len(a) < len(b):
        a, b = b, a
    pret = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        tek = [i]
        for j, cb in enumerate(b, 1):
            tek.append(min(pret[j] + 1, tek[j - 1] + 1, pret[j - 1] + (ca != cb)))
        pret = tek
    return pret[-1]


def cer(ist, pro):
    i = _norm(ist)
    return round(_lev(i, _norm(pro)) / max(len(i), 1), 4)


def word_recall(ist, pro):
    """Order-insensitive: share of ground-truth words (multiset) found. CER alone over-penalises a changed
    Tesseract reading order (e.g. a page segmented into two columns) that loses no characters."""
    import collections
    a = collections.Counter(_norm(ist).split()); b = collections.Counter(_norm(pro).split())
    return round(sum((a & b).values()) / max(sum(a.values()), 1), 4)


def run_one(name, worker):
    p = FX / name
    t0 = time.perf_counter(); r = {"file": name, "role": "worker" if worker else "finalize"}
    try:
        text, scanned, ocr_used, pages, conf = ex.extract(p)
        r.update(outcome="ok", scanned=scanned, ocr_used=ocr_used, chars=len(text),
                 sha=hashlib.sha256(text.encode()).hexdigest()[:12], pages=None if pages is None else len(pages),
                 conf=None if conf is None else round(conf, 3))
        if worker and pages and p.suffix == ".pdf" and not scanned:
            r["necitljive"] = ex.necitljive_strane_pdf(p, pages)
        r["secs"] = round(time.perf_counter() - t0, 2)
        tr = truth.get(name)
        if tr:
            if pages and len(pages) == len(tr):
                r["cer_pages"] = [cer(a, b) for a, b in zip(tr, pages)]
            r["cer"] = cer("\n".join(tr), text)
            r["wr"] = word_recall("\n".join(tr), text)
    except Exception as e:
        r.update(outcome="exception", exc=type(e).__name__, msg=str(e)[:160], secs=round(time.perf_counter() - t0, 2))
    return r


t0 = time.perf_counter()
if mode == "idle":
    results = []
elif mode in ("worker", "finalize"):
    results = [run_one(spec, mode == "worker")]
elif mode == "threads":
    a, b = spec.split("|")
    with ThreadPoolExecutor(2) as pool:
        fa = pool.submit(run_one, a, True); fb = pool.submit(run_one, b, False)
        results = [fa.result(), fb.result()]
elif mode == "retries":
    name, n = spec.split(":")
    results = []
    for k in range(int(n)):
        r = run_one(name, True); r["attempt"] = k + 1; r["rss_after_mib"] = rss_self(); results.append(r)
else:
    raise SystemExit("unknown mode")
wall = round(time.perf_counter() - t0, 2)
time.sleep(0.3)
sam.terminate(); sam.wait()


def rd(p):
    try:
        return open(p).read().strip()
    except OSError:
        return ""


res = {"case": case_id, "variant": variant, "mode": mode, "spec": spec, "wall_s": wall, **base,
       "pymupdf": fitz.VersionBind, "results": results,
       "cg_memory_peak_mib": round(int(rd("/sys/fs/cgroup/memory.peak") or 0) / 2**20, 1),
       "cg_memory_events": dict(l.split() for l in rd("/sys/fs/cgroup/memory.events").splitlines() if l)}
json.dump(res, open(OUT / f"{case_id}.json", "w"), ensure_ascii=False)
print("N02CASE " + json.dumps(res, ensure_ascii=False))
