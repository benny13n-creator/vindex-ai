# NS2b falsification fixtures, generated AFTER gen.py into the same dir (gen.py fixtures keep their round-3 text).
# SYNTHETIC text only. Usage (in the production image, cwd /app): gen_fx2.py <fxdir>
import io, json, math, os, sys, zlib

sys.path.insert(0, "/app")
import fitz
from PIL import Image, ImageFilter

from uploaded_doc.extractor import MAX_JPEG_KOEFICIJENATA_BAJTOVA, _jpeg_bajtova_koeficijenata, _jpeg_okvir

Image.MAX_IMAGE_PIXELS = None
OUT = sys.argv[1]
TRUTH = json.load(open(os.path.join(OUT, "truth.json"), encoding="utf-8"))
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


def dims_for_coef(target, comps):
    """Largest A4-ratio size whose header-computed coefficient bytes stay <= target."""
    lo, hi = 1.0, 60.0
    for _ in range(60):
        mp = (lo + hi) / 2
        h = int(math.sqrt(mp * 1e6 * 842 / 595)); w = int(mp * 1e6 / h)
        if _jpeg_bajtova_koeficijenata(w, h, comps) <= target:
            lo = mp
        else:
            hi = mp
    h = int(math.sqrt(lo * 1e6 * 842 / 595)); w = int(lo * 1e6 / h)
    return w, h


def pdf_with(name, jpeg_bytes, truth, flate=False):
    d = fitz.open(); p = d.new_page(width=595, height=842); p.insert_image(p.rect, stream=jpeg_bytes)
    if flate:
        x = p.get_images(full=True)[0][0]
        d.update_stream(x, zlib.compress(jpeg_bytes), compress=False)
        d.xref_set_key(x, "Filter", "[/FlateDecode /DCTDecode]")
    d.save(os.path.join(OUT, name)); d.close()
    TRUTH[name] = truth
    print(name, os.path.getsize(os.path.join(OUT, name)) // 1024, "KiB")


def info(name):
    with open(os.path.join(OUT, name), "rb") as f:
        o = _jpeg_okvir(f)
    print(name, o and {k: o[k] for k in ("sirina", "visina", "komponente", "progresivni", "koeficijenti")}, os.path.getsize(os.path.join(OUT, name)) // 1024, "KiB")


# 1. ordinary phone photo: 12 MP baseline 4:2:0 with EXIF
l = lines(38, 1); ph = page_image(l, 3000, 4000)
ex = Image.Exif(); ex[0x010F] = "SyntheticPhone"; ex[0x0110] = "SP-1"; ex[0x0112] = 1; ex[0x0132] = "2026:10:14 10:00:00"
ph.save(os.path.join(OUT, "img_12mp_exif.jpg"), "JPEG", quality=90, subsampling=2, exif=ex.tobytes())
TRUTH["img_12mp_exif.jpg"] = ["\n".join(l)]; info("img_12mp_exif.jpg"); del ph
# 2. high-quality progressive 4:4:4 just below the threshold (q95), and at ~96 MiB
from uploaded_doc.extractor import MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA
for name, target, off, comps, sub in (("img_prog444_below.jpg", MAX_JPEG_KOEFICIJENATA_BAJTOVA - (1 << 20), 2, [(1, 1)] * 3, 0),
                                      ("img_prog444_96.jpg", 95 << 20, 3, [(1, 1)] * 3, 0),
                                      ("img_prog444_64.jpg", MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA - (1 << 20), 6, [(1, 1)] * 3, 0),
                                      ("img_prog420_64.jpg", MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA - (1 << 20), 7, [(2, 2), (1, 1), (1, 1)], 2)):
    w, h = dims_for_coef(target, comps)
    l = lines(38, off); im = page_image(l, w, h)
    im.save(os.path.join(OUT, name), "JPEG", quality=95, progressive=True, subsampling=sub)
    TRUTH[name] = ["\n".join(l)]; info(name); del im
# 2b. baseline CMYK just below 4 x MIN_DEKODIRANIH_PIKSELA (draft cannot halve it -> full-size CMYK decode; not a coefficient-buffer case)
from uploaded_doc.extractor import MIN_DEKODIRANIH_PIKSELA
for name, mp, off in (("img_cmyk_34mp.jpg", 4 * MIN_DEKODIRANIH_PIKSELA / 1e6 * 0.995, 4), ("img_cmyk_30mp.jpg", 30.0, 5)):
    h = int(math.sqrt(mp * 1e6 * 842 / 595)); w = int(mp * 1e6 / h)
    l = lines(38, off); im = page_image(l, w, h).convert("CMYK")
    im.save(os.path.join(OUT, name), "JPEG", quality=90)
    TRUTH[name] = ["\n".join(l)]; info(name); del im
# 3. JPEG embedded in PDF
rd = lambda n: open(os.path.join(OUT, n), "rb").read()
pdf_with("pdf_prog444_40.pdf", rd("img_40mp_prog444.jpg"), TRUTH["img_40mp_prog444.jpg"])
pdf_with("pdf_flatedct_prog444_40.pdf", rd("img_40mp_prog444.jpg"), TRUTH["img_40mp_prog444.jpg"], flate=True)
pdf_with("pdf_prog420_40.pdf", rd("img_40mp_prog420.jpg"), TRUTH["img_40mp_prog420.jpg"])
pdf_with("pdf_base_40.pdf", rd("img_40mp.jpg"), TRUTH["img_40mp.jpg"])
pdf_with("pdf_prog444_below.pdf", rd("img_prog444_below.jpg"), TRUTH["img_prog444_below.jpg"])
pdf_with("pdf_prog444_96.pdf", rd("img_prog444_96.jpg"), TRUTH["img_prog444_96.jpg"])
pdf_with("pdf_prog444_64.pdf", rd("img_prog444_64.jpg"), TRUTH["img_prog444_64.jpg"])
pdf_with("pdf_prog420_64.pdf", rd("img_prog420_64.jpg"), TRUTH["img_prog420_64.jpg"])
for n in ("img_40mp_prog444.jpg", "img_40mp_prog420.jpg", "img_20mp_prog444.jpg", "img_40mp.jpg", "img_40mp_cmyk.jpg", "img_12mp.jpg"):
    info(n)
json.dump(TRUTH, open(os.path.join(OUT, "truth.json"), "w", encoding="utf-8"), ensure_ascii=False)
