# NS2b follow-up fixtures: BASELINE (single-scan) CMYK / RGB JPEGs around the draft boundary, and CMYK JPEG in PDF.
# SYNTHETIC text only. Run after gen.py/gen_fx2.py (appends to <dir>/truth.json if present). Usage: gen_fx3.py <dir>
import json, math, os, sys

sys.path.insert(0, "/app")
import fitz
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
TP = os.path.join(OUT, "truth.json")
TRUTH = json.load(open(TP, encoding="utf-8")) if os.path.exists(TP) else {}
LAT = ["OSNOVNI SUD U BEOGRADU", "Tužilac: Marko Petrović iz Beograda, ulica Kneza Miloša 12",
       "Tuženi: Jovan Jovanović iz Novog Sada, Bulevar oslobođenja 5",
       "Predmet: naknada štete u iznosu od 250.000 dinara sa kamatom",
       "Ročište je zakazano za 15. novembar 2026. godine u sudnici broj 4.",
       "Sud je razmotrio dokaze i izjave svedoka, te utvrdio činjenično stanje."]


def lines(n, off):
    return [f"{i+1}. " + LAT[(i * 5 + off) % len(LAT)] for i in range(n)]


def page_image(ls, w, h):
    d = fitz.open(); p = d.new_page(width=595, height=842)
    tw = fitz.TextWriter(p.rect); font = fitz.Font("helv")
    for i, l in enumerate(ls):
        tw.append((50, 60 + i * 19), l, font=font, fontsize=11)
    tw.write_text(p)
    pix = p.get_pixmap(matrix=fitz.Matrix(w / 595.0, h / 842.0))
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    d.close()
    return img.filter(ImageFilter.GaussianBlur(0.6))


def dims(mp):
    h = int(math.sqrt(mp * 1e6 * 842 / 595)); w = int(mp * 1e6 / h)
    return w, h


SPEC = [("cmyk", mp) for mp in (20, 25, 28, 30, 32, 34.6, 35, 40)] + [(k, mp) for k in ("444", "420") for mp in (30, 32, 34.6)]
for n, (kind, mp) in enumerate(SPEC):
    w, h = dims(mp)
    tag = str(mp).replace(".", "_")
    name = f"b_{kind}_{tag}.jpg"
    l = lines(38, 10 + n); im = page_image(l, w, h)
    p = os.path.join(OUT, name)
    if kind == "cmyk":
        im.convert("CMYK").save(p, "JPEG", quality=90)
    else:
        im.save(p, "JPEG", quality=90, subsampling={"444": 0, "420": 2}[kind])
    del im
    TRUTH[name] = ["\n".join(l)]
    print(name, w, h, os.path.getsize(p) // 1024, "KiB", flush=True)
    if kind == "cmyk" and mp in (30, 34.6, 40):
        pn = f"pdf_b_cmyk_{tag}.pdf"
        d = fitz.open(); pg = d.new_page(width=595, height=842); pg.insert_image(pg.rect, stream=open(p, "rb").read())
        d.save(os.path.join(OUT, pn)); d.close()
        TRUTH[pn] = TRUTH[name]
        print(pn, os.path.getsize(os.path.join(OUT, pn)) // 1024, "KiB", flush=True)
json.dump(TRUTH, open(TP, "w", encoding="utf-8"), ensure_ascii=False)
