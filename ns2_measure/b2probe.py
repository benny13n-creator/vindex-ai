# B2 probe: extract() on short synthetic scans + what each downstream caller would do with the result.
# Usage: b2probe.py <fx dir> [files...]   (prints one JSON line per file; synthetic text only)
import json, logging, sys, time, unicodedata
from pathlib import Path

sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)
from uploaded_doc import extractor as ex  # noqa: E402

fx = Path(sys.argv[1]); truth = json.load(open(fx / "truth_b2.json", encoding="utf-8"))
files = sys.argv[2:] or sorted(truth)


def n(t):
    t = "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c)); return " ".join(t.lower().split())


def lev(a, b):
    if len(a) < len(b):
        a, b = b, a
    p = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        c = [i]
        for j, cb in enumerate(b, 1):
            c.append(min(p[j] + 1, c[j - 1] + 1, p[j - 1] + (ca != cb)))
        p = c
    return p[-1]


for name in files:
    path = fx / name; tr = truth[name]
    t0 = time.time()
    try:
        text, sc, ou, pages, conf = ex.extract(path)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"file": name, "exc": type(e).__name__})); continue
    trj = "\n".join(tr)
    r = {"file": name, "truth_chars": len(trj.strip()), "out_chars": len(text.strip()), "s": round(time.time() - t0, 1),
         "cer": round(lev(n(trj), n(text)) / max(len(n(trj)), 1), 3) if trj.strip() else None,
         "alnum_out": sum(ch.isalnum() for ch in text),
         "pages": None if pages is None else [len((p or "").strip()) for p in pages], "truth_pages": len(tr),
         "scanned": sc, "ocr_used": ou, "conf": None if conf is None else round(conf, 3)}
    # downstream decisions (read from the callers' code, no network):
    r["upload_routes"] = "422 nečitljivo" if sc else ("422 prazan" if not text.strip() else "prihvaćen")
    if sc:
        r["worker"] = "review ocr_failed (tekst odbačen iz klasifikacije)"
    else:
        try:
            from shared.intake_worker import IntakeWorker
            r["worker"] = "klasifikacija; flags=" + json.dumps(IntakeWorker._nepotpuno_procitano(path, pages, ou, conf), ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            r["worker"] = "klasifikacija; flags=? " + type(e).__name__
    if "--show" in sys.argv[0:1]:
        pass
    print(json.dumps(r, ensure_ascii=False))
