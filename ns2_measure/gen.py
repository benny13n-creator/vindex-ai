# N02 Linux measurement fixtures. SYNTHETIC text only (no client documents). Writes <out>/*.pdf|jpg and
# <out>/truth.json = {file: [ground-truth text per page]} used for character-accuracy (CER) scoring.
import io, json, os, random, sys
import fitz
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None          # generator only (the extractor keeps its own guards)
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
random.seed(7)
TRUTH = {}

LAT = ["OSNOVNI SUD U BEOGRADU", "Tužilac: Marko Petrović iz Beograda, ulica Kneza Miloša 12",
       "Tuženi: Jovan Jovanović iz Novog Sada, Bulevar oslobođenja 5",
       "Predmet: naknada štete u iznosu od 250.000 dinara sa kamatom",
       "Ročište je zakazano za 15. novembar 2026. godine u sudnici broj 4.",
       "Sud je razmotrio dokaze i izjave svedoka, te utvrdio činjenično stanje."]
CYR = ["ОСНОВНИ СУД У БЕОГРАДУ", "Тужилац: Марко Петровић из Београда, улица Кнеза Милоша 12",
       "Тужени: Јован Јовановић из Новог Сада, Булевар ослобођења 5",
       "Предмет: накнада штете у износу од 250.000 динара са каматом",
       "Рочиште је заказано за 15. новембар 2026. године у судници број 4.",
       "Суд је размотрио доказе и изјаве сведока, те утврдио чињенично стање."]


def lines(kind, n):
    src = CYR if kind == "cyr" else LAT
    return [f"{i+1}. " + src[(i * 7 + random.randint(0, 5)) % len(src)] for i in range(n)]


def text_page(doc, ls, size=11):
    p = doc.new_page(width=595, height=842)
    tw = fitz.TextWriter(p.rect)
    font = fitz.Font("helv")
    for i, l in enumerate(ls):
        tw.append((50, 60 + i * 19), l, font=font, fontsize=size)
    tw.write_text(p)
    return p


def scan_image(ls, dpi=300):
    d = fitz.open(); text_page(d, ls)
    pix = d[0].get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    d.close()
    return img.rotate(0.4, fillcolor="white", resample=Image.BICUBIC).filter(ImageFilter.GaussianBlur(0.6))


def jpeg(img, q=80):
    b = io.BytesIO(); img.save(b, "JPEG", quality=q); return b.getvalue()


def add_scan(doc, ls, w=595, h=842):
    p = doc.new_page(width=w, height=h)
    p.insert_image(p.rect, stream=jpeg(scan_image(ls)))


def save(doc, name, truth):
    path = os.path.join(OUT, name); doc.save(path, garbage=3, deflate=True); doc.close()
    TRUTH[name] = truth
    print(name, os.path.getsize(path) // 1024, "KiB")


# 1. one-page Cyrillic scan
l = lines("cyr", 38); d = fitz.open(); add_scan(d, l); save(d, "scan_cyr_1p.pdf", ["\n".join(l)])
# 2. ten-page scan (Latin/Cyrillic alternating)
d = fitz.open(); tr = []
for i in range(10):
    l = lines("cyr" if i % 2 else "lat", 38); add_scan(d, l); tr.append("\n".join(l))
save(d, "scan_10p.pdf", tr)
# 3. multipage mixed digital + scan (D S D S D S)
d = fitz.open(); tr = []
for i in range(6):
    l = lines("cyr" if i % 2 else "lat", 35)
    (add_scan(d, l) if i % 2 else text_page(d, l)); tr.append("\n".join(l))
save(d, "mixed_6p.pdf", tr)
# 4. photo-based PDFs
l = lines("lat", 38)
ph = scan_image(l, dpi=360).resize((3024, 4032))
ph.save(os.path.join(OUT, "img_12mp.jpg"), "JPEG", quality=85); TRUTH["img_12mp.jpg"] = ["\n".join(l)]
#    4a. image->PDF converter default: page size in points == pixel size (Pillow, many phone apps)
ph.save(os.path.join(OUT, "photo_12mp_page72.pdf"), "PDF", resolution=72); TRUTH["photo_12mp_page72.pdf"] = ["\n".join(l)]
#    4b. same photo placed on an A4 page
d = fitz.open(); p = d.new_page(width=595, height=842); p.insert_image(p.rect, stream=jpeg(ph, 85))
save(d, "photo_12mp_a4.pdf", ["\n".join(l)])
#    4c. 48 MP photo on A4 (high-resolution phone mode)
l48 = lines("cyr", 38); big = scan_image(l48, dpi=700)            # ~5790 x 8186 = 47 MP
d = fitz.open(); p = d.new_page(width=595, height=842); p.insert_image(p.rect, stream=jpeg(big, 80))
save(d, "photo_48mp_a4.pdf", ["\n".join(l48)])
#    4d. standalone image just under the documented 40 MP image limit
l40 = lines("lat", 38); i40 = scan_image(l40, dpi=640)              # ~5292 x 7484 = 39.6 MP
i40.save(os.path.join(OUT, "img_40mp.jpg"), "JPEG", quality=80); TRUTH["img_40mp.jpg"] = ["\n".join(l40)]
i40.convert("L").save(os.path.join(OUT, "img_40mp.png"), "PNG"); TRUTH["img_40mp.png"] = ["\n".join(l40)]
i40.convert("CMYK").save(os.path.join(OUT, "img_40mp_cmyk.jpg"), "JPEG", quality=90); TRUTH["img_40mp_cmyk.jpg"] = ["\n".join(l40)]
i40.save(os.path.join(OUT, "img_40mp_prog444.jpg"), "JPEG", quality=90, progressive=True, subsampling=0)
TRUTH["img_40mp_prog444.jpg"] = ["\n".join(l40)]
#    4e. the same 40 MP image embedded losslessly (Flate) in an A4 PDF: MuPDF cannot subsample-decode it
b = io.BytesIO(); i40.save(b, "PNG")
d = fitz.open(); p = d.new_page(width=595, height=842); p.insert_image(p.rect, stream=b.getvalue())
save(d, "pdf_flate40_a4.pdf", ["\n".join(l40)])
#    4f. ~97 MP lossless (Flate) image in an A4 PDF: the embedded-image decode is NOT bounded by the output raster
l100 = lines("cyr", 38); i100 = scan_image(l100, dpi=1000).convert("L")       # ~8268 x 11693 = 96.7 MP
b = io.BytesIO(); i100.save(b, "PNG"); del i100
d = fitz.open(); p = d.new_page(width=595, height=842); p.insert_image(p.rect, stream=b.getvalue())
save(d, "pdf_flate100_a4.pdf", ["\n".join(l100)])
print("img_40mp", i40.size, i40.size[0] * i40.size[1])
# 5. raster-size probes: the SAME 300 dpi A4 scan stretched over larger page formats -> constant decode,
#    growing 300 dpi output raster (A3 17.4 MP, A2 34.8 MP, A1 69.6 MP, A0 139 MP)
for name, (w, h) in {"page_a3": (842, 1191), "page_a2": (1191, 1684), "page_a1": (1684, 2384), "page_a0": (2384, 3370)}.items():
    l = lines("lat", 38); d = fitz.open(); add_scan(d, l, w, h); save(d, name + ".pdf", ["\n".join(l)])

# 6. round 3 (appended last so earlier fixtures keep their random text): progressive with ordinary 4:2:0 chroma at 40 MP, and progressive 4:4:4 at ~20 MP (coefficient-buffer classes)
i40.save(os.path.join(OUT, "img_40mp_prog420.jpg"), "JPEG", quality=90, progressive=True, subsampling=2)
TRUTH["img_40mp_prog420.jpg"] = ["\n".join(l40)]
l20 = lines("cyr", 38); i20 = scan_image(l20, dpi=450)             # ~3720 x 5262 = 19.6 MP
i20.save(os.path.join(OUT, "img_20mp_prog444.jpg"), "JPEG", quality=90, progressive=True, subsampling=0)
TRUTH["img_20mp_prog444.jpg"] = ["\n".join(l20)]
del i20
json.dump(TRUTH, open(os.path.join(OUT, "truth.json"), "w", encoding="utf-8"), ensure_ascii=False)
