# NS2 B2 fixtures: SHORT scanned documents (synthetic text only). Writes <out>/b2_*.pdf|jpg and <out>/truth_b2.json
# = {file: [ground-truth text per page]} ("" for a page that carries no text).
import io, json, os, random, sys
import fitz
from PIL import Image, ImageDraw, ImageFilter

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
random.seed(11)
TRUTH = {}
LONG = ["OSNOVNI SUD U BEOGRADU", "Tužilac: Marko Petrović iz Beograda, ulica Kneza Miloša 12",
        "Tuženi: Jovan Jovanović iz Novog Sada, Bulevar oslobođenja 5",
        "Predmet: naknada štete u iznosu od 250.000 dinara sa kamatom"]


def render(lines, dpi=300, size=11, y0=60, w=595, h=842, extra=None):
    d = fitz.open(); p = d.new_page(width=w, height=h)
    tw = fitz.TextWriter(p.rect); font = fitz.Font("helv")
    for i, l in enumerate(lines):
        tw.append((50, y0 + i * 19), l, font=font, fontsize=size)
    tw.write_text(p)
    pix = p.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples); d.close()
    if extra:
        img = extra(img)
    return img.rotate(0.4, fillcolor="white", resample=Image.BICUBIC).filter(ImageFilter.GaussianBlur(0.6))


def jpeg(img, q=80):
    b = io.BytesIO(); img.save(b, "JPEG", quality=q); return b.getvalue()


def pdf(name, imgs, truth, digital=None):
    d = fitz.open()
    for k, img in enumerate(imgs):
        p = d.new_page(width=595, height=842)
        if img is not None:
            p.insert_image(p.rect, stream=jpeg(img))
        if digital and digital.get(k):
            p.insert_text((50, 800), digital[k], fontname="helv", fontsize=11)
    d.save(os.path.join(OUT, name), garbage=3, deflate=True); d.close()
    TRUTH[name] = truth


def letter_noise(img, n=900, seed=3):
    """Glyph-like clutter: random short strokes/arcs/dots (no real words), like a stamp/handwriting/smudge texture."""
    rnd = random.Random(seed); dr = ImageDraw.Draw(img)
    W, H = img.size
    for _ in range(n):
        x, y = rnd.randint(0, W - 40), rnd.randint(0, H - 40)
        k = rnd.random()
        if k < 0.4:
            dr.line([(x, y), (x + rnd.randint(-30, 30), y + rnd.randint(-30, 30))], fill=(20, 20, 20), width=rnd.randint(2, 5))
        elif k < 0.8:
            r = rnd.randint(6, 18); dr.arc([x, y, x + r * 2, y + r * 2], rnd.randint(0, 360), rnd.randint(0, 360), fill=(30, 30, 30), width=3)
        else:
            dr.ellipse([x, y, x + 5, y + 5], fill=(10, 10, 10))
    return img


def speckle(img, n=4000, seed=5):
    rnd = random.Random(seed); dr = ImageDraw.Draw(img)
    W, H = img.size
    for _ in range(n):
        x, y = rnd.randint(0, W - 3), rnd.randint(0, H - 3); dr.point([(x, y), (x + 1, y), (x, y + 1)], fill=(40, 40, 40))
    return img


S25 = "Rešenje broj P 123/2026"                                             # 23 chars
S45 = "Dostavnica: primljeno 12.10.2026. Potpis"                              # 40 chars
S45C = "Решење број П 456/2026 правноснажно"                                  # 35 chars Cyrillic
S80 = ["Poziv za ročište P 789/2026", "Ročište 15.11.2026. u 10 časova, sudnica 4"]   # ~70 chars
S95 = ["Opomena pred utuženje broj 55/2026", "Dug 120.000 dinara dospeo 01.09.2026. godine"]  # ~80 chars
pdf("b2_short25.pdf", [render([S25])], [S25])
pdf("b2_short40.pdf", [render([S45])], [S45])
pdf("b2_short35_cyr.pdf", [render([S45C])], [S45C])
pdf("b2_short70.pdf", [render(S80)], ["\n".join(S80)])
pdf("b2_short80.pdf", [render(S95)], ["\n".join(S95)])
pdf("b2_long150.pdf", [render(LONG[:3])], ["\n".join(LONG[:3])])
pdf("b2_blank.pdf", [render([], extra=lambda im: speckle(im, 300))], [""])
pdf("b2_noise.pdf", [render([], extra=letter_noise)], [""])
pdf("b2_noise_heavy.pdf", [render([], extra=lambda im: letter_noise(im, 3000, 9))], [""])
pdf("b2_speckle.pdf", [render([], extra=speckle)], [""])
pdf("b2_partial_line.pdf", [render([S45], extra=lambda im: letter_noise(im, 600, 4))], [S45])
pdf("b2_multi_one_short.pdf", [render(LONG), render([S25]), render(LONG[1:])], ["\n".join(LONG), S25, "\n".join(LONG[1:])])
pdf("b2_multi_all_short.pdf", [render([S25]), render([S45])], [S25, S45])
pdf("b2_multi_short_blank.pdf", [render([S45]), render([])], [S45, ""])
# digital-text preservation controls (OCR001 path): short digital text with/without a short scanned page
d = fitz.open(); p = d.new_page(width=595, height=842); p.insert_text((50, 80), S45, fontname="helv", fontsize=11)
d.save(os.path.join(OUT, "b2_digital_short.pdf")); d.close(); TRUTH["b2_digital_short.pdf"] = [S45]
pdf("b2_digital_plus_scan.pdf", [None, render([S25])], [S45, S25], digital={0: S45})
# standalone photos (extract_image has the same > 100 character rule)
render([S45]).save(os.path.join(OUT, "b2_short40.jpg"), "JPEG", quality=85); TRUTH["b2_short40.jpg"] = [S45]
render([], extra=letter_noise).save(os.path.join(OUT, "b2_noise.jpg"), "JPEG", quality=85); TRUTH["b2_noise.jpg"] = [""]
render([], extra=lambda im: speckle(im, 300)).save(os.path.join(OUT, "b2_blank.jpg"), "JPEG", quality=85); TRUTH["b2_blank.jpg"] = [""]
render(LONG[:3]).save(os.path.join(OUT, "b2_long150.jpg"), "JPEG", quality=85); TRUTH["b2_long150.jpg"] = ["\n".join(LONG[:3])]
json.dump(TRUTH, open(os.path.join(OUT, "truth_b2.json"), "w", encoding="utf-8"), ensure_ascii=False)
print({k: [len(x) for x in v] for k, v in TRUTH.items()})
