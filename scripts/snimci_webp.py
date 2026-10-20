"""Website V2: PNG snimci stvarnih V2 ekrana (site/snimci-izvor/, van git-a) -> optimizovan WebP u site/snimci/.

Snimke pravi `node frontend-v2-ng/tests/diagnostics/site-snimci.mjs` (izmišljeni podaci, lokalni fixture).
"""
from pathlib import Path

from PIL import Image

KOREN = Path(__file__).resolve().parent.parent
IZVOR, CILJ = KOREN / "site" / "snimci-izvor", KOREN / "site" / "snimci"
SIRINA = {"registar-mobilni": 780}
VISINA = {"registar-mobilni": 1240}  # gornji deo: zaglavlje, naslov i prvih pet predmeta

CILJ.mkdir(exist_ok=True)
for png in sorted(IZVOR.glob("*.png")):
    slika = Image.open(png).convert("RGB")
    w = SIRINA.get(png.stem, 1600)
    if slika.width > w:
        slika = slika.resize((w, round(slika.height * w / slika.width)), Image.LANCZOS)
    if png.stem in VISINA:
        slika = slika.crop((0, 0, slika.width, VISINA[png.stem]))
    izlaz = CILJ / (png.stem + ".webp")
    slika.save(izlaz, "WEBP", quality=82, method=6)
    print(f"{izlaz.name}: {slika.width}x{slika.height}, {izlaz.stat().st_size // 1024} KB")
