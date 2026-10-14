# B2 discriminator sweep: OCR output length / mean word confidence / letter share for
#   (a) genuine short text under degradations (dpi, blur, JPEG quality, Latin/Cyrillic)
#   (b) glyph-like clutter, speckle and blank pages at many densities
# through the production preprocessing + Tesseract call (uploaded_doc.extractor._ocr_image). Synthetic only.
import json, logging, random, sys
from PIL import Image, ImageFilter

sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)
sys.path.insert(0, sys.argv[1])
sys.argv = [sys.argv[0], sys.argv[2]]
from uploaded_doc import extractor as ex  # noqa: E402
import gen_b2 as g  # noqa: E402  (fixture helpers; importing it also (re)writes fixtures into argv[2])

lang = ex._detect_ocr_lang()
GEN = ["Rešenje broj P 123/2026", "Dostavnica: primljeno 12.10.2026. Potpis", "Решење број П 456/2026 правноснажно",
       "Poziv za ročište P 789/2026", "Opomena 55/2026", "Overeno 3.9.2026.", "Пресуда К 12/2025"]


def stats(img):
    t, c = ex._ocr_image(img, lang)
    t = t.strip()
    letters = sum(ch.isalpha() for ch in t)
    words = t.split()
    good = [w for w in words if sum(ch.isalnum() for ch in w) >= 3]
    return {"chars": len(t), "conf": None if c is None else round(c, 3), "letters": round(letters / max(len(t), 1), 2),
            "words": len(words), "w3": len(good)}


def degrade(img, dpi_scale, blur, q):
    if dpi_scale != 1:
        img = img.resize((int(img.width * dpi_scale), int(img.height * dpi_scale)), Image.BICUBIC)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    import io
    b = io.BytesIO(); img.save(b, "JPEG", quality=q); b.seek(0)
    return Image.open(b)


for s in GEN:
    for sc, bl, q in [(1, 0, 80), (0.5, 0, 60), (0.5, 0.8, 40), (1, 1.2, 50), (0.66, 0.6, 30)]:
        print(json.dumps({"kind": "genuine", "len": len(s), "deg": [sc, bl, q], **stats(degrade(g.render([s]), sc, bl, q))}, ensure_ascii=False), flush=True)
for n in (20, 40, 80, 150, 300, 600, 900, 1500, 3000):
    for seed in (1, 2, 3):
        print(json.dumps({"kind": "clutter", "n": n, "seed": seed, **stats(g.render([], extra=lambda im: g.letter_noise(im, n, seed)))}), flush=True)
for n in (100, 300, 1000):
    print(json.dumps({"kind": "speckle", "n": n, **stats(g.render([], extra=lambda im: g.speckle(im, n, n)))}), flush=True)
