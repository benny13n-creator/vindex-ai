# NS2b follow-up round 2: BASELINE JPEG placed full-page on A4 inside a PDF (MuPDF decodes it at native size when
# halving would fall below the 300 dpi page raster). SYNTHETIC text only. Usage: gen_fx4.py <dir>
import json, math, os, sys

sys.path.insert(0, "/app")
import fitz
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None
OUT = sys.argv[1]
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


SPEC = [("rgb", mp) for mp in (16, 20, 22, 24, 28, 34.6)] + [("cmyk", mp) for mp in (14, 16, 20)]
for n, (kind, mp) in enumerate(SPEC):
    h = int(math.sqrt(mp * 1e6 * 842 / 595)); w = int(mp * 1e6 / h)
    l = lines(38, 30 + n); im = page_image(l, w, h)
    import io
    b = io.BytesIO()
    (im.convert("CMYK") if kind == "cmyk" else im).save(b, "JPEG", quality=85, **({} if kind == "cmyk" else {"subsampling": 2}))
    del im
    name = f"pdf_b_{kind}_{str(mp).replace('.', '_')}_a4.pdf"
    d = fitz.open(); pg = d.new_page(width=595, height=842); pg.insert_image(pg.rect, stream=b.getvalue())
    d.save(os.path.join(OUT, name)); d.close()
    TRUTH[name] = ["\n".join(l)]
    print(name, w, h, os.path.getsize(os.path.join(OUT, name)) // 1024, "KiB", flush=True)
json.dump(TRUTH, open(TP, "w", encoding="utf-8"), ensure_ascii=False)
