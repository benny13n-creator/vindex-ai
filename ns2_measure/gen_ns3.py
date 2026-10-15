# NS3-A fixtures (PDF OCR memory). SYNTHETIC text only. Run after gen.py/gen_fx2/3/4 into the same dir (cwd /app).
# Usage: gen_ns3.py <dir>
import io, json, math, os, sys, zlib

sys.path.insert(0, "/app")
import fitz
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None
OUT = sys.argv[1]
TP = os.path.join(OUT, "truth.json")
TRUTH = json.load(open(TP, encoding="utf-8"))
LAT = ["OSNOVNI SUD U BEOGRADU", "Tužilac: Marko Petrović iz Beograda, ulica Kneza Miloša 12",
       "Tuženi: Jovan Jovanović iz Novog Sada, Bulevar oslobođenja 5",
       "Predmet: naknada štete u iznosu od 250.000 dinara sa kamatom",
       "Ročište je zakazano za 15. novembar 2026. godine u sudnici broj 4.",
       "Sud je razmotrio dokaze i izjave svedoka, te utvrdio činjenično stanje."]
A4 = fitz.Rect(0, 0, 595, 842)


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


def jpg(img, **kw):
    b = io.BytesIO(); img.save(b, "JPEG", **kw); return b.getvalue()


def dims(mp):
    h = int(math.sqrt(mp * 1e6 * 842 / 595)); return int(mp * 1e6 / h), h


def rd(n):
    return open(os.path.join(OUT, n), "rb").read()


def save(d, name, truth=None):
    d.save(os.path.join(OUT, name)); d.close()
    if truth is not None:
        TRUTH[name] = truth
    print(name, os.path.getsize(os.path.join(OUT, name)) // 1024, "KiB", flush=True)


def scan_pages(d, n, off):
    tr = []
    for k in range(n):
        l = lines(38, off + k); p = d.new_page(width=595, height=842)
        p.insert_image(A4, stream=jpg(page_image(l, 2480, 3508), quality=80)); tr.append("\n".join(l))
    return tr


def raw_image(d, w, h, bpc, cs, data, extra=""):
    x = d.get_new_xref()
    d.update_object(x, f"<</Type/XObject/Subtype/Image/Width {w}/Height {h}/BitsPerComponent {bpc}{cs}/Filter/FlateDecode{extra}>>")
    d.update_stream(x, zlib.compress(data, 6), compress=False)
    return x


def page_with_xobjects(d, items, content):
    p = d.new_page(width=595, height=842)
    d.xref_set_key(p.xref, "Resources", "<</XObject<<" + "".join(f"/{k} {x} 0 R" for k, x in items) + ">>>>")
    c = d.get_new_xref(); d.update_object(c, "<<>>"); d.update_stream(c, content)
    d.xref_set_key(p.xref, "Contents", f"{c} 0 R")
    return p


# 7. multipage scan + one high-memory page (rejected), and the same with CMYK 40 MP (accepted)
for tag, src in (("cmyk30", "b_cmyk_30.jpg"), ("cmyk40", "b_cmyk_40.jpg")):
    d = fitz.open(); tr = scan_pages(d, 9, 40)
    p = d.new_page(width=595, height=842); p.insert_image(A4, stream=rd(src)); tr.append(TRUTH[src][0])
    save(d, f"ns3_scan9_{tag}.pdf", tr)
# 8. multiple image XObjects: 4 x 12 MP RGB quadrants (accepted); two CMYK 20 MP full-page overlapping (rejected)
d = fitz.open(); p = d.new_page(width=595, height=842); l = lines(38, 50)
q = jpg(page_image(l, 3000, 4000), quality=85)
for r in (fitz.Rect(0, 0, 297, 421), fitz.Rect(297, 0, 595, 421), fitz.Rect(0, 421, 297, 842), fitz.Rect(297, 421, 595, 842)):
    p.insert_image(r, stream=q)
save(d, "ns3_multi_xobj.pdf")
d = fitz.open(); p = d.new_page(width=595, height=842); c20 = rd("b_cmyk_20.jpg")
p.insert_image(A4, stream=c20); p.insert_image(A4, stream=jpg(Image.open(io.BytesIO(c20)).rotate(180), quality=90))
save(d, "ns3_multi_cmyk20.pdf", TRUTH["b_cmyk_20.jpg"])
# 9. masks: RGB 16 MP + 16 MP gray soft mask; 1-bit stencil (ImageMask) 600 dpi A4 full page
l = lines(38, 52); w, h = dims(16); im = page_image(l, w, h)
d = fitz.open(); p = d.new_page(width=595, height=842)
p.insert_image(A4, stream=jpg(im, quality=85), mask=jpg(Image.new("L", (w, h), 255), quality=85)); save(d, "ns3_smask.pdf", ["\n".join(l)])
l = lines(38, 53); im = page_image(l, 4960, 7016).convert("L").point(lambda v: 255 if v > 128 else 0).convert("1")
d = fitz.open(); x = raw_image(d, 4960, 7016, 1, "", im.tobytes(), "/ImageMask true/Decode[1 0]")
page_with_xobjects(d, [("S0", x)], b"0 g q 595 0 0 842 0 0 cm /S0 Do Q"); save(d, "ns3_stencil.pdf", ["\n".join(l)])
# 10. filter chains: ASCIIHex+DCT progressive 40 MP; Flate+DCT CMYK 30 / 40 MP; Flate raw CMYK 7000x5700 (review class)
d = fitz.open(); p = d.new_page(width=595, height=842); p.insert_image(A4, stream=rd("img_40mp_prog444.jpg"))
xi = p.get_images(full=True)[0][0]; d.update_stream(xi, rd("img_40mp_prog444.jpg").hex().encode() + b">", compress=False)
d.xref_set_key(xi, "Filter", "[/ASCIIHexDecode /DCTDecode]"); save(d, "ns3_ahx_prog444_40.pdf", TRUTH["img_40mp_prog444.jpg"])
for tag, src in (("cmyk30", "b_cmyk_30.jpg"), ("cmyk40", "b_cmyk_40.jpg")):
    d = fitz.open(); p = d.new_page(width=595, height=842); p.insert_image(A4, stream=rd(src))
    xi = p.get_images(full=True)[0][0]; d.update_stream(xi, zlib.compress(rd(src)), compress=False)
    d.xref_set_key(xi, "Filter", "[/FlateDecode /DCTDecode]"); save(d, f"ns3_fl_{tag}.pdf", TRUTH[src])
l = lines(38, 54); im = page_image(l, 5700, 7000).convert("CMYK")
d = fitz.open(); x = raw_image(d, 5700, 7000, 8, "/ColorSpace/DeviceCMYK", im.tobytes()); del im
page_with_xobjects(d, [("I0", x)], b"q 595 0 0 842 0 0 cm /I0 Do Q"); save(d, "ns3_flate_cmyk_40mp.pdf", ["\n".join(l)])
# 11. inline images: CMYK DCT 30 MP full page (rejected before the interpreter); small inline logo on a scan page
d = fitz.open(); p = d.new_page(width=595, height=842); src = rd("b_cmyk_30.jpg"); W, H = Image.open(io.BytesIO(src)).size
c = d.get_new_xref(); d.update_object(c, "<<>>")
d.update_stream(c, b"q 595 0 0 842 0 0 cm BI /W %d /H %d /CS /CMYK /BPC 8 /F /DCT ID\n" % (W, H) + src + b"\nEI Q")
d.xref_set_key(p.xref, "Contents", f"{c} 0 R"); save(d, "ns3_inline_cmyk30.pdf", TRUTH["b_cmyk_30.jpg"])
d = fitz.open(); tr = scan_pages(d, 1, 55); p = d[0]
logo = jpg(Image.new("RGB", (200, 100), (200, 30, 30)), quality=80)
c = d.get_new_xref(); d.update_object(c, "<<>>")
d.update_stream(c, b"q 100 0 0 50 470 770 cm BI /W 200 /H 100 /CS /RGB /BPC 8 /F /DCT ID\n" + logo + b"\nEI Q")
d.xref_set_key(p.xref, "Contents", "[" + " ".join(f"{x} 0 R" for x in p.get_contents() + [c]) + "]")
save(d, "ns3_inline_small.pdf", tr)
# annotation appearance stream with the CMYK 30 MP image (page itself empty -> OCR path)
d = fitz.open(); p = d.new_page(width=595, height=842); p.insert_image(A4, stream=rd("b_cmyk_30.jpg"))
xi = p.get_images(full=True)[0][0]
for cx in p.get_contents():
    d.update_stream(cx, b"")
a = p.add_rect_annot(fitz.Rect(10, 10, 100, 100)); ax = a.xref
f = d.get_new_xref(); d.update_object(f, f"<</Type/XObject/Subtype/Form/BBox[0 0 595 842]/Resources<</XObject<</Im0 {xi} 0 R>>>>>>")
d.update_stream(f, b"q 595 0 0 842 0 0 cm /Im0 Do Q")
d.xref_set_key(ax, "AP", f"<</N {f} 0 R>>"); d.xref_set_key(ax, "Rect", "[0 0 595 842]")
d.save(os.path.join(OUT, "ns3_annot_cmyk30.pdf"), garbage=0); d.close(); TRUTH["ns3_annot_cmyk30.pdf"] = TRUTH["b_cmyk_30.jpg"]
print("ns3_annot_cmyk30.pdf", flush=True)
# JPX (JPEG 2000) scans: RGB A4 300 dpi, gray A4 600 dpi
for name, mode, (w, h), off in (("ns3_jpx_rgb_300.pdf", "RGB", (2480, 3508), 56), ("ns3_jpx_gray_600.pdf", "L", (4960, 7016), 57)):
    l = lines(38, off); im = page_image(l, w, h).convert(mode); b = io.BytesIO(); im.save(b, "JPEG2000", quality_mode="rates", quality_layers=[40])
    d = fitz.open(); p = d.new_page(width=595, height=842); p.insert_image(A4, stream=b.getvalue()); save(d, name, ["\n".join(l)])
# 14. digital-text PDF (10 pages); page 3 carries a CMYK 30 MP image next to its text (never rasterized)
d = fitz.open(); tr = []
for k in range(10):
    l = lines(35, 60 + k); p = d.new_page(width=595, height=842)
    tw = fitz.TextWriter(p.rect); font = fitz.Font("helv")
    for i, t in enumerate(l):
        tw.append((50, 60 + i * 19), t, font=font, fontsize=11)
    tw.write_text(p); tr.append("\n".join(l))
    if k == 2:
        p.insert_image(fitz.Rect(350, 500, 550, 780), stream=rd("b_cmyk_30.jpg"))
save(d, "ns3_digital_10p.pdf", tr)
# review class: TIFF (CMYK 7000x5700) with a small PDF appended, named .pdf
b = io.BytesIO(); Image.new("CMYK", (7000, 5700)).save(b, "TIFF", compression="tiff_lzw")
d = fitz.open(); p = d.new_page(); p.insert_text((50, 72), "x"); pdf = d.tobytes(); d.close()
open(os.path.join(OUT, "ns3_poly_tiff.pdf"), "wb").write(b.getvalue() + pdf); print("ns3_poly_tiff.pdf", flush=True)
json.dump(TRUTH, open(TP, "w", encoding="utf-8"), ensure_ascii=False)
