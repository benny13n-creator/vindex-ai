# B1 retention probe: WHAT stays in the process after each OCR job (one process, jobs run in a thread pool exactly like
# asyncio.to_thread). After each job: VmRSS/RssAnon, glibc mallinfo2 (in-use vs free-but-retained heap, mmapped),
# Python allocated blocks, thread count; then the same after gc.collect()+malloc_trim(0).
# Usage: ret.py <file1,file2,...>      env: VARIANT=<path to extractor variant> (optional)
import ctypes, gc, importlib.util, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, "/app"); os.chdir("/app")
import logging
import api  # noqa: F401
logging.disable(logging.CRITICAL)
if os.environ.get("VARIANT"):
    sp = importlib.util.spec_from_file_location("uploaded_doc.extractor", os.environ["VARIANT"])
    ex = importlib.util.module_from_spec(sp); sys.modules["uploaded_doc.extractor"] = ex; sp.loader.exec_module(ex)
from shared.intake_worker import IntakeWorker as W  # noqa: E402

libc = ctypes.CDLL("libc.so.6")


class MI2(ctypes.Structure):
    _fields_ = [(n, ctypes.c_size_t) for n in ("arena", "ordblks", "smblks", "hblks", "hblkhd", "usmblks", "fsmblks", "uordblks", "fordblks", "keepcost")]


libc.mallinfo2.restype = MI2


def st():
    d = {}
    for line in open("/proc/self/status"):
        k, _, v = line.partition(":")
        if k in ("VmRSS", "RssAnon", "RssFile", "Threads"):
            d[k] = int(v.split()[0]) // 1024 if k != "Threads" else int(v.split()[0])
    m = libc.mallinfo2()
    M = lambda b: round(b / 2**20, 1)
    d.update(heap_total=M(m.arena), heap_inuse=M(m.uordblks), heap_free=M(m.fordblks), mmapped=M(m.hblkhd), mmapped_n=m.hblks,
             py_blocks=sys.getallocatedblocks())
    return d


FX = Path("/m/fx")
pool = ThreadPoolExecutor(max_workers=int(os.environ.get("POOL", "8")))
out = {"start": st()}
seq = []
for i, f in enumerate(sys.argv[1].split(",")):
    p = FX / f
    def job():
        text, sc, ou, pages, conf = W._extract_text(p)
        if not sc:
            W._nepotpuno_procitano(p, pages, ou, conf)
        return len(text)
    t0 = time.perf_counter()
    n = pool.submit(job).result()
    time.sleep(1.0)
    a = st()
    gc.collect(); libc.malloc_trim(0); time.sleep(0.5)
    b = st()
    seq.append({"i": i + 1, "file": f, "chars": n, "s": round(time.perf_counter() - t0, 1), "after": a, "after_gc_trim": b})
    print("RET", json.dumps(seq[-1]), flush=True)
out["seq"] = seq
print("RETSUM", json.dumps({"start": out["start"]}))
