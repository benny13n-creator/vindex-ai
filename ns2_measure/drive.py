# HOST-side driver for one B1 case against `gunicorn gapp:app -c gunicorn.conf.py` in a 512 MiB container.
# Usage: drive.py <case_id> <scenario> <cgroup_dir>     (results -> ns2_measure/out/<case_id>.drive.json)
# Never stores document text (synthetic fixtures; only lengths, hashes, CER / word recall vs ground truth).
import collections, json, os, random, socket, sys, threading, time, unicodedata, urllib.error, urllib.request

case_id, scenario, cg = sys.argv[1:4]
BASE = os.environ.get("BASE", "http://127.0.0.1:10000")
OUT = "ns2_measure/out"
TRUTH = json.load(open("ns2_measure/fx/truth.json", encoding="utf-8"))
REF = json.load(open("ns2_measure/ref.json")) if os.path.exists("ns2_measure/ref.json") else {}
T0 = time.time()


def ip():
    return f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def get(path, timeout=600):
    req = urllib.request.Request(BASE + path, headers={"X-Forwarded-For": ip(), "Connection": "close"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read(), time.time() - t
    except Exception as e:  # noqa: BLE001
        return type(e).__name__, b"", time.time() - t


def cgcur():
    try:
        return round(int(open(cg + "/memory.current").read()) / 2**20, 1)
    except OSError:
        return None


def norm(t):
    t = "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c))
    return " ".join(t.lower().split())


def lev(a, b):
    if len(a) < len(b):
        a, b = b, a
    pr = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cu = [i]
        for j, cb in enumerate(b, 1):
            cu.append(min(pr[j] + 1, cu[j - 1] + 1, pr[j - 1] + (ca != cb)))
        pr = cu
    return pr[-1]


def cer(a, b):
    a = norm(a)
    return round(lev(a, norm(b)) / max(len(a), 1), 4)


def wr(a, b):
    x = collections.Counter(norm(a).split()); y = collections.Counter(norm(b).split())
    return round(sum((x & y).values()) / max(sum(x.values()), 1), 4)


def wait_ready(limit=240):
    t = time.time()
    while time.time() - t < limit:
        s, b, _ = get("/health", timeout=5)
        if s == 200:
            return round(time.time() - T0, 1)
        time.sleep(0.5)
    return None


def ocr(f, role, timeout=900):
    s, b, el = get(f"/__ns2m/ocr?f={f}&role={role}&text=1", timeout=timeout)
    r = {"file": f, "role": role, "http": s, "wall_s": round(el, 2), "t_end": round(time.time() - T0, 1)}
    if s != 200:
        r["body"] = b[:200].decode("utf-8", "replace"); return r
    d = json.loads(b)
    text, pages = d.pop("text", None), d.pop("pages_text", None)
    r.update(d)
    tr = TRUTH.get(f)
    if text is not None and tr:
        r["cer"] = cer("\n".join(tr), text); r["wr"] = wr("\n".join(tr), text)
        r["pages_match_truth"] = (pages is not None and len(pages) == len(tr)) if f.endswith(".pdf") else None
        if pages and len(pages) == len(tr):
            r["cer_pages_max"] = max(cer(a, b) for a, b in zip(tr, pages))
    if f in REF:
        r["sha_matches_ref"] = r.get("sha") == REF[f]
    return r


class Load:
    """Modest concurrent HTTP traffic on real lightweight routes while OCR runs (random X-Forwarded-For = many users)."""
    PATHS = ["/health", "/api/version", "/", "/api/predmeti", "/static/sw.js"]

    def __init__(self, threads=6, think=0.02):
        self.n, self.think, self.stop = threads, think, threading.Event()
        self.lat = collections.defaultdict(list); self.codes = collections.Counter(); self.lk = threading.Lock(); self.ts = []

    def _run(self):
        while not self.stop.is_set():
            p = random.choice(self.PATHS)
            s, _, el = get(p, timeout=60)
            with self.lk:
                self.lat[p].append(el); self.codes[f"{p}:{s}"] += 1
            time.sleep(self.think)

    def __enter__(self):
        self.ts = [threading.Thread(target=self._run, daemon=True) for _ in range(self.n)]
        [t.start() for t in self.ts]; return self

    def __exit__(self, *a):
        self.stop.set(); [t.join(70) for t in self.ts]

    def stats(self):
        allv = sorted(v for vs in self.lat.values() for v in vs)
        q = lambda p: round(allv[min(len(allv) - 1, int(p * len(allv)))], 3) if allv else None
        return {"threads": self.n, "requests": len(allv), "p50_s": q(0.5), "p95_s": q(0.95), "max_s": q(1.0), "codes": dict(self.codes)}


def par(jobs):
    res = [None] * len(jobs)
    def one(i, f, role, delay):
        time.sleep(delay); res[i] = ocr(f, role)
    ts = [threading.Thread(target=one, args=(i, *j)) for i, j in enumerate(jobs)]
    [t.start() for t in ts]; [t.join() for t in ts]
    return res


def baseline(tag):
    time.sleep(2.0)
    s, b, _ = get("/__ns2m/rss", timeout=30)
    w = json.loads(b) if s == 200 else {}
    return {"tag": tag, "t": round(time.time() - T0, 1), "cg_mib": cgcur(), "worker_rss_mib": w.get("rss_mib"), "pid": w.get("pid")}


R = {"case": case_id, "scenario": scenario}
R["ready_s"] = wait_ready()
if R["ready_s"] is None:
    R["error"] = "never ready"
else:
    time.sleep(8)       # startup hooks (warming, IntakeWorker, event bus) settle
    R["baseline_start"] = baseline("start")
    kind, _, arg = scenario.partition(":")
    if kind == "idle":
        time.sleep(float(arg or 20)); R["baselines"] = [baseline("idle_end")]
    elif kind == "idleload":
        with Load() as L:
            time.sleep(float(arg or 30))
        R["load"] = L.stats(); R["baselines"] = [baseline("after_load")]
    elif kind in ("single", "pair", "multi"):
        jobs = []
        for k, part in enumerate(arg.split("|")):
            f, role = part.split("@")
            jobs.append((f, role, 0.0 if k == 0 else 0.3))
        with Load() as L:
            R["results"] = par(jobs)
        R["load"] = L.stats(); R["baselines"] = [baseline("after")]
    elif kind == "noload":
        jobs = [(p.split("@")[0], p.split("@")[1], 0.0 if k == 0 else 0.3) for k, p in enumerate(arg.split("|"))]
        R["results"] = par(jobs); R["baselines"] = [baseline("after")]
    elif kind == "cancel":
        # client aborts the same upload n times (socket timeout), then retries and waits for the result
        f, role, n = arg.split("@")
        cancels = []
        with Load() as L:
            for _ in range(int(n)):
                s, _, el = get(f"/__ns2m/ocr?f={f}&role={role}", timeout=2.5)
                cancels.append({"status": s, "after_s": round(el, 1)})
            R["cancels"] = cancels
            R["results"] = [ocr(f, role)]
        R["load"] = L.stats()
        R["baselines"] = [baseline("after_retry")]
        time.sleep(25); R["baselines"].append(baseline("after_abandoned_threads"))
    elif kind == "sustained":
        rot = arg.split(",")
        R["results"] = []; R["baselines"] = []
        with Load(threads=3, think=0.05) as L:
            for i in range(20):
                f = rot[i % len(rot)]
                r = ocr(f, "worker"); r["seq"] = i + 1; R["results"].append(r)
                R["baselines"].append(baseline(f"seq{i + 1}"))
            for i in range(10):
                a, b = rot[(2 * i) % len(rot)], rot[(2 * i + 1) % len(rot)]
                for r in par([(a, "worker", 0.0), (b, "finalize", 0.3)]):
                    r["pair"] = i + 1; R["results"].append(r)
                R["baselines"].append(baseline(f"pair{i + 1}"))
        R["load"] = L.stats()
    else:
        R["error"] = "unknown scenario"
R["total_s"] = round(time.time() - T0, 1)
json.dump(R, open(f"{OUT}/{case_id}.drive.json", "w"), ensure_ascii=False)
print("NS2DRIVE", case_id, json.dumps({k: R.get(k) for k in ("ready_s", "total_s", "error")}))
