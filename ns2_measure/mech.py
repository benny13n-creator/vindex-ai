# NS2b mechanism probe: ONE fixture per fresh process. Prints one JSON line:
#   header-computed coefficient bytes (extractor._jpeg_okvir, header only) vs measured process peak for
#   (a) Image.open + .size (no load), (b) the extractor's real decode path (_u_granici_ocr / convert("L")),
#   (c) for PDFs: the extractor's real rasterization (_rasterizuj_stranu) of page 1.
# Linux: VmHWM reset through /proc/self/clear_refs ("5") before each phase, delta = VmHWM - VmRSS(before).
# Usage: mech.py <file>     (cwd = repo root so `uploaded_doc` imports)
import io, json, os, sys, time

sys.path.insert(0, os.getcwd())
p = sys.argv[1]
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


def reset():
    if LINUX:
        try:
            open("/proc/self/clear_refs", "w").write("5")
            return True
        except OSError:
            return False
    return False


def phase(fn):
    reset()
    r0, _ = st()
    t = time.perf_counter()
    out = fn()
    r1, hwm = st()
    return out, round((hwm - r0) / 2**20, 1), round((r1 - r0) / 2**20, 1), round(time.perf_counter() - t, 2)


from PIL import Image  # noqa: E402
from uploaded_doc import extractor as X  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
res = {"file": os.path.basename(p), "size_kib": os.path.getsize(p) // 1024, "hwm_reset": reset()}

if p.endswith(".pdf"):
    import fitz
    doc = fitz.open(p)
    imgs = []
    for xref, *_rest in doc[0].get_images(full=True):
        raw = doc.xref_stream_raw(xref)
        ok = X._jpeg_okvir(io.BytesIO(raw))
        imgs.append({"xref": xref, "filter": doc.xref_get_key(xref, "Filter")[1], "okvir": ok})
    res["images"] = imgs
    res["coef_bytes"] = sum((i["okvir"] or {}).get("koeficijenti", 0) for i in imgs)
    _, res["rss_peak_mib"], res["rss_after_mib"], res["secs"] = phase(lambda: X._rasterizuj_stranu(doc[0]))
    doc.close()
else:
    def hdr():
        with open(p, "rb") as f:
            return X._jpeg_okvir(f)
    okvir, res["hdr_peak_mib"], _, res["hdr_secs"] = phase(hdr)
    res["okvir"] = okvir
    res["coef_bytes"] = (okvir or {}).get("koeficijenti", 0)
    full = X._jpeg_bajtova_koeficijenata(okvir["sirina"], okvir["visina"], okvir["komponente"]) if okvir else 0
    res["coef_full_if_buffered"] = full

    def opn():
        im = Image.open(p); s = im.size; m = im.mode; info = {k: v for k, v in im.info.items() if k in ("progressive", "progression")}
        lay = getattr(im, "layer", None); im.close(); return s, m, info, lay
    (res["pil_size"], res["pil_mode"], res["pil_info"], res["pil_layer"]), res["open_peak_mib"], _, _ = phase(opn)

    def dec():
        with Image.open(p) as izvor:
            img = X._u_granici_ocr(izvor)
            if img is izvor:
                img = izvor.convert("L")
            return img.size
    res["decoded_size"], res["rss_peak_mib"], res["rss_after_mib"], res["secs"] = phase(dec)

res["coef_mib"] = round(res["coef_bytes"] / 2**20, 1)
print("MECH " + json.dumps(res), flush=True)
