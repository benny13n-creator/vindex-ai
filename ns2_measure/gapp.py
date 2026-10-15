# NS2 B1 measurement entry point (measurement branch only, never merged).
# Runs the UNCHANGED production app (`import api`) under the production start command shape
# `gunicorn <module>:app -c gunicorn.conf.py` and adds ONE measurement route that drives the same extraction
# calls the real callers make, the same way they make them:
#   role=worker   -> shared.intake_worker.IntakeWorker._extract_text + _nepotpuno_procitano via asyncio.to_thread
#   role=finalize -> uploaded_doc.extractor.extract via asyncio.to_thread (routers/smart_intake.py finalize,
#                    routers/dokument.py upload, api.py predmet upload)
# The fixture is copied to a NamedTemporaryFile first (as every caller does) and its hash is checked after
# extraction (the input file must stay byte-identical). Only synthetic fixtures are used.
import asyncio
import hashlib
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "/app")
os.chdir("/app")

import api  # noqa: E402  (production app, all startup hooks: warming, IntakeWorker loop, event bus loop)
from starlette.responses import JSONResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402

app = api.app
if os.environ.get("NS3_NOGUARD") == "1":     # measurement only: true peak of PDFs the NS3-A guard would reject
    import uploaded_doc.extractor as _X
    _X.MAX_PDF_RASTER_BAJTOVA = 1 << 40
if os.environ.get("NS2B_NOFILTER") == "1":     # measurement only: true decode peak of inputs the candidate would reject
    import uploaded_doc.extractor as _X
    for _k in ("MAX_JPEG_DEKODIRANJA_BAJTOVA", "MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA", "MAX_JPEG_KOEFICIJENATA_BAJTOVA"):
        if hasattr(_X, _k):
            setattr(_X, _k, 1 << 40)
FX = Path(os.environ.get("FX", "/m/fx"))


def _rss_mib() -> float:
    for line in open("/proc/self/status"):
        if line.startswith("VmRSS:"):
            return round(int(line.split()[1]) / 1024, 1)
    return -1.0


async def _ocr(request):
    q = request.query_params
    src = FX / q["f"]
    role = q.get("role", "finalize")
    with tempfile.NamedTemporaryFile(suffix=src.suffix, delete=False) as tmp:
        tmp.write(src.read_bytes())
        p = Path(tmp.name)
    h0 = hashlib.sha256(p.read_bytes()).hexdigest()
    t0 = time.perf_counter()
    out = {"file": q["f"], "role": role, "pid": os.getpid()}
    try:
        if role == "worker":
            from shared.intake_worker import IntakeWorker as W
            text, sc, ou, pages, conf = await asyncio.to_thread(W._extract_text, p)
            nec = None if sc else await asyncio.to_thread(W._nepotpuno_procitano, p, pages, ou, conf)
        else:
            from uploaded_doc.extractor import extract
            text, sc, ou, pages, conf = await asyncio.to_thread(extract, p)
            nec = None
        out.update(ok=True, scanned=sc, ocr_used=ou, chars=len(text or ""),
                   sha=hashlib.sha256((text or "").encode()).hexdigest()[:12],
                   pages=None if pages is None else len(pages),
                   page_chars=None if pages is None else [len(x or "") for x in pages],
                   conf=None if conf is None else round(conf, 3), review=nec)
        if q.get("text") == "1":      # synthetic fixtures only: the driver scores CER and never stores the text
            out["text"] = text
            out["pages_text"] = pages
    except Exception as e:  # noqa: BLE001
        out.update(ok=False, exc=type(e).__name__, msg=str(e)[:200], poruka=getattr(e, "poruka", None))
    finally:
        out["input_intact"] = hashlib.sha256(p.read_bytes()).hexdigest() == h0
        p.unlink()
    out["secs"] = round(time.perf_counter() - t0, 2)
    out["rss_after_mib"] = _rss_mib()
    return JSONResponse(out)


import ctypes  # noqa: E402


class _MI2(ctypes.Structure):
    _fields_ = [(n, ctypes.c_size_t) for n in ("arena", "ordblks", "smblks", "hblks", "hblkhd", "usmblks", "fsmblks", "uordblks", "fordblks", "keepcost")]


_libc = ctypes.CDLL("libc.so.6")
_libc.mallinfo2.restype = _MI2


async def _rss(request):
    m = _libc.mallinfo2(); M = lambda b: round(b / 2**20, 1)
    thr = next(int(l.split()[1]) for l in open("/proc/self/status") if l.startswith("Threads:"))
    return JSONResponse({"pid": os.getpid(), "rss_mib": _rss_mib(), "heap_total": M(m.arena), "heap_inuse": M(m.uordblks),
                         "heap_free": M(m.fordblks), "mmapped": M(m.hblkhd), "threads": thr})


app.router.routes.insert(0, Route("/__ns2m/ocr", _ocr, methods=["GET"]))
app.router.routes.insert(0, Route("/__ns2m/rss", _rss, methods=["GET"]))
