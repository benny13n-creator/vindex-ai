"""Izdvaja logo A2 („Heritage Crest“) iz originalne slike osnivača 1:1 (isti pikseli),
uklanja papirnu pozadinu.

Pokretanje: python scripts/brand/izdvoji_logo.py <izvorna-slika.png> <izlazni-folder>
Izvor: ploča koncepata 1536x1024 (ea3de69e-….png, kadar A2 dole levo); nije u repozitorijumu.
Izlaz: vindex-logo-svetla.png i vindex-logo-tamna.png (357x305, providna pozadina) i
vindex-znak-tamna.png (samo znak, za ikone).

Svetla verzija: originalne boje (crno V i slova, zlatni stub i lovor) na providnoj podlozi.
Tamna verzija: isti crtež; crni delovi (V i VINDEX) dobijaju zlatni ton kao u tamnoj
varijanti na istoj slici (gornji desni kadar A2), zlatni delovi ostaju isti.
"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image

IZVOR, D = Path(sys.argv[1]), Path(sys.argv[2])
D.mkdir(parents=True, exist_ok=True)
im = np.asarray(Image.open(IZVOR).convert("RGB")).astype(np.float64)
BG = np.array([237.0, 231.0, 222.0])

# Oblast logoa (znak + VINDEX), izmereno profilom redova i kolona.
p = im[515:1024, 0:533]
d = np.abs(p - BG).max(axis=2)
ys, xs = np.where(d[60:372] > 40)   # 575..887
y0, y1 = 60 + ys.min() - 6, 60 + ys.max() + 7
x0, x1 = xs.min() - 6, xs.max() + 7
c = p[y0:y1, x0:x1]
print("isecak", c.shape, "u izvoru: y", 515 + y0, 515 + y1, "x", x0, x1)

# Alfa iz udaljenosti od papira: šum papira je do ~18/255 (izmereno), mastilo i zlato
# su daleko iznad; između je meka ivica (anti-aliasing originala).
d = np.abs(c - BG).max(axis=2)
PRAG, PUNO = 20.0, 90.0
a = np.clip((d - PRAG) / (PUNO - PRAG), 0, 1)
fg = np.where(a[..., None] > 0, (c - (1 - a[..., None]) * BG) / np.maximum(a[..., None], 1e-6), 0)
fg = np.clip(fg, 0, 255)

def sacuvaj(boje, ime):
    out = np.dstack([boje, a * 255]).round().astype(np.uint8)
    Image.fromarray(out, "RGBA").save(D / ime, optimize=True)
    print(ime, out.shape[1], "x", out.shape[0])

sacuvaj(fg, "vindex-logo-svetla.png")

# Tamna: crni delovi (niska zasićenost i niska svetlina) → zlato. Zlato iz samog crteža:
# srednja boja zlatnih piksela (zasićenih), pa se senčenje crnog prenosi kao svetlina zlata.
sv = fg.mean(axis=2)
zas = fg.max(axis=2) - fg.min(axis=2)
zlatni = (a > 0.9) & (zas > 40)
zlato = np.median(fg[zlatni], axis=0)
print("zlato", zlato)
crno = (zas < 40) & (sv < 120)
t = np.clip(sv / 120.0, 0, 1)[..., None]           # 0 = najtamnije crno
svetlo_zlato = np.minimum(zlato * 1.18, 255)
tamno_zlato = zlato * 0.78
preslikano = tamno_zlato + (svetlo_zlato - tamno_zlato) * t
tamna = np.where(crno[..., None], preslikano, fg)
sacuvaj(tamna, "vindex-logo-tamna.png")
# Samo znak (redovi do praznog pojasa iznad slova), za favicon i ikonu aplikacije.
red = np.where((a > 0).any(axis=1))[0]
prazno = [y for y in range(red.min(), red.max()) if not (a[y] > 0).any()]
# najduži pojas praznih redova je razmak između znaka i slova
pojasi, start = [], prazno[0]
for i in range(1, len(prazno) + 1):
    if i == len(prazno) or prazno[i] != prazno[i - 1] + 1:
        pojasi.append((start, prazno[i - 1])); start = prazno[i] if i < len(prazno) else 0
granica = max(pojasi, key=lambda p: p[1] - p[0])[0] + 2
zn = np.dstack([tamna, a * 255])[:granica].round().astype(np.uint8)
Image.fromarray(zn, "RGBA").save(D / "vindex-znak-tamna.png", optimize=True)
print("vindex-znak-tamna.png", zn.shape[1], "x", zn.shape[0])
