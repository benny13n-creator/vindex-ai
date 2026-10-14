# MuPDF multithreading stress: N threads render pages of scanned PDFs concurrently while
# fitz.TOOLS.store_shrink(100) runs between renders (exactly the PR #24 pattern), compared to a serial reference.
# Prints only hashes/counts. Usage: mt_stress.py <pdf> [<pdf>...]  env THREADS, ROUNDS, DPI, LOCK=1 to serialize.
import hashlib, json, os, sys, threading, time
import fitz

files = sys.argv[1:]
THREADS = int(os.getenv("THREADS", "4")); ROUNDS = int(os.getenv("ROUNDS", "6")); DPI = int(os.getenv("DPI", "100"))
LOCK = threading.Lock() if os.getenv("LOCK") == "1" else None


def render_all(path):
    out = []
    doc = fitz.open(path)
    for p in doc:
        if LOCK:
            with LOCK:
                pix = p.get_pixmap(dpi=DPI); h = hashlib.sha256(pix.samples).hexdigest()[:16]; del pix
                fitz.TOOLS.store_shrink(100)
        else:
            pix = p.get_pixmap(dpi=DPI); h = hashlib.sha256(pix.samples).hexdigest()[:16]; del pix
            fitz.TOOLS.store_shrink(100)
        out.append(h)
    doc.close()
    return out


ref = {f: render_all(f) for f in files}
errors = []; mismatches = 0; renders = 0; lk = threading.Lock()


def worker(k):
    global mismatches, renders
    for r in range(ROUNDS):
        f = files[(k + r) % len(files)]
        try:
            got = render_all(f)
        except Exception as e:  # noqa
            with lk: errors.append(type(e).__name__ + ":" + str(e)[:80]); continue
        with lk:
            renders += len(got)
            mismatches += sum(1 for a, b in zip(got, ref[f]) if a != b) + abs(len(got) - len(ref[f]))


t0 = time.perf_counter(); c0 = time.process_time()
ts = [threading.Thread(target=worker, args=(k,)) for k in range(THREADS)]
[t.start() for t in ts]; [t.join() for t in ts]
wall = time.perf_counter() - t0; cpu = time.process_time() - c0
print(json.dumps({"pymupdf": fitz.VersionBind, "threads": THREADS, "rounds": ROUNDS, "dpi": DPI, "lock": bool(LOCK),
                  "renders": renders, "mismatches": mismatches, "errors": len(errors), "error_kinds": sorted(set(errors))[:5],
                  "wall_s": round(wall, 2), "cpu_s": round(cpu, 2), "cpu_over_wall": round(cpu / wall, 2)}))
