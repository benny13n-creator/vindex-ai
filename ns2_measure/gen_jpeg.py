# NS2b JPEG coefficient-buffer matrix fixtures. SYNTHETIC text only (no client documents).
# Usage: gen_jpeg.py <outdir> [sizes_mp_csv] [--quick]
# Writes <out>/m_<prog|base>_<444|422|420|gray|cmyk>_<MP>.jpg, PDFs with an embedded JPEG, the falsification
# fixtures (f_*.jpg/png/pdf) and <out>/truth.json for the ones used for CER.
import io, json, math, os, sys
import fitz
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None
OUT = sys.argv[1]
SIZES = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "10,20,30,40,48").split(",")]
os.makedirs(OUT, exist_ok=True)
TRUTH = json.load(open(os.path.join(OUT, "truth.json"), encoding="utf-8")) if os.path.exists(os.path.join(OUT, "truth.json")) else {}

LAT = ["OSNOVNI SUD U BEOGRADU", "Tužilac: Marko Petrović iz Beograda, ulica Kneza Miloša 12",
       "Tuženi: Jovan Jovanović iz Novog Sada, Bulevar oslobođenja 5",
       "Predmet: naknada štete u iznosu od 250.000 dinara sa kamatom",
       "Ročište je zakazano za 15. novembar 2026. godine u sudnici broj 4.",
       "Sud je razmotrio dokaze i izjave svedoka, te utvrdio činjenično stanje."]


def lines(n, off=0):
    return [f"{i+1}. " + LAT[(i * 7 + off) % len(LAT)] for i in range(n)]


def page_image(ls, w, h):
    """A4-like page with text rendered directly at w x h pixels (no upscaling blur)."""
    d = fitz.open(); p = d.new_page(width=595, height=842)
    tw = fitz.TextWriter(p.rect); font = fitz.Font("helv")
    for i, l in enumerate(ls):
        tw.append((50, 60 + i * 19), l, font=font, fontsize=11)
    tw.write_text(p)
    zoom = w / 595.0
    pix = p.get_pixmap(matrix=fitz.Matrix(zoom, h / 842.0))
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    d.close()
    return img.filter(ImageFilter.GaussianBlur(0.6))


def dims(mp):
    h = int(math.sqrt(mp * 1e6 * 842 / 595)); w = int(mp * 1e6 / h)
    return w, h


SUB = {"444": 0, "422": 1, "420": 2}
L = lines(38)
for mp in SIZES:
    w, h = dims(mp)
    base = page_image(L, w, h)
    for prog in (True, False):
        for kind in ("444", "422", "420", "gray", "cmyk"):
            name = f"m_{'prog' if prog else 'base'}_{kind}_{mp}.jpg"
            p = os.path.join(OUT, name)
            if kind in SUB:
                base.save(p, "JPEG", quality=90, progressive=prog, subsampling=SUB[kind])
            elif kind == "gray":
                base.convert("L").save(p, "JPEG", quality=90, progressive=prog)
            else:
                base.convert("CMYK").save(p, "JPEG", quality=90, progressive=prog)
            TRUTH[name] = ["\n".join(L)]
            print(name, w, h, os.path.getsize(p) // 1024, "KiB", flush=True)
    del base
json.dump(TRUTH, open(os.path.join(OUT, "truth.json"), "w", encoding="utf-8"), ensure_ascii=False)
