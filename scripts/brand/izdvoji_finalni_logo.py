"""Izdvaja finalni logo (znak V + VINDEX, boja kosti) iz slike osnivača 1:1 — isti pikseli, bez ponovnog crtanja.

Pokretanje: python scripts/brand/izdvoji_finalni_logo.py <izvorna-slika.png> <izlazni-folder>
Izvor: 766x515 PNG osnivača (tamnoplavi preliv, logo u boji kosti); nije u repozitorijumu.
       sha256 7c7307e59bc06807d00af9af0142d10759babfb48e9519a97ead9dc0109eebf3. Donjih 5 redova (beli rub snimka) se ne koristi.

Pozadina (preliv) se procenjuje glatkom površinom van logoa; providnost svakog piksela je udeo logoa u odnosu na tu
pozadinu, a boja se vraća deljenjem (un-premultiply). Složen nazad na istu pozadinu, izlaz daje izvornu sliku.

Izlaz:
  vindex-logo-final-tamna.png  — logo na providnoj pozadini (za tamne površine), izvorne boje i sjaj
  vindex-logo-final-svetla.png — isti kadar sa izvornom tamnoplavom pozadinom (za svetle površine; logo u boji kosti
                                 bez podloge na beloj se ne bi video, a boje se ne menjaju)
  vindex-znak-final.png        — samo znak V na izvornom prelivu, kvadrat 512 (izvor za ikone)
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

IZVOR, D = Path(sys.argv[1]), Path(sys.argv[2])
D.mkdir(parents=True, exist_ok=True)
im = np.asarray(Image.open(IZVOR).convert("RGB")).astype(np.float64)[:509]      # bez belog ruba (redovi 510+)
H, W, _ = im.shape
L = im.mean(axis=2)

# 1. Maska logoa sa sjajem: sve što je primetno svetlije od lokalne pozadine, široko prošireno.
jezgro = L > 45                                                                # preliv je svuda L <= 32
maska = np.asarray(Image.fromarray((jezgro * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(41))) > 0

# 2. Pozadina: polinom 4. stepena po kanalu, uklopljen samo van maske.
yy, xx = np.mgrid[0:H, 0:W]
xn, yn = xx / W, yy / H
cl = [xn ** i * yn ** j for i in range(5) for j in range(5 - i)]
A = np.stack([c[~maska] for c in cl], axis=1)
BG = np.empty_like(im)
for k in range(3):
    koef, *_ = np.linalg.lstsq(A, im[..., k][~maska], rcond=None)
    BG[..., k] = sum(c * q for c, q in zip(cl, koef))
print("greska pozadine van logoa (max/srednja):", np.abs(im - BG)[~maska].max().round(2), np.abs(im - BG)[~maska].mean().round(2))

# 3. Providnost i boja (un-premultiply prema boji jezgra logoa).
F = np.median(im[L > 215], axis=0)
smer = F - BG
alfa = np.clip(((im - BG) * smer).sum(axis=2) / (smer ** 2).sum(axis=2), 0, 1)
alfa[~maska] = 0
alfa[alfa < 0.035] = 0                                                         # šum preliva, ne logo
boja = np.where(alfa[..., None] > 0, BG + (im - BG) / np.maximum(alfa[..., None], 1e-6), F)
boja = np.clip(boja, 0, 255)
print("boja jezgra logoa:", F.round(1))

# 4. Kadar: ceo logo + 6 px (kao izdvoji_logo.py).
ys, xs = np.where(alfa > 0.5)
y0, y1, x0, x1 = ys.min() - 6, ys.max() + 7, xs.min() - 6, xs.max() + 7
ysg, xsg = np.where(alfa > 0)
y0, y1, x0, x1 = min(y0, ysg.min()), max(y1, ysg.max() + 1), min(x0, xsg.min()), max(x1, xsg.max() + 1)
print("kadar logoa: y", y0, y1, "x", x0, x1, "->", x1 - x0, "x", y1 - y0)

rgba = np.dstack([boja, alfa * 255]).round().astype(np.uint8)
Image.fromarray(rgba[y0:y1, x0:x1], "RGBA").save(D / "vindex-logo-final-tamna.png", optimize=True)
Image.fromarray(im[y0:y1, x0:x1].round().astype(np.uint8), "RGB").save(D / "vindex-logo-final-svetla.png", optimize=True)

# 5. Dokaz 1:1: tamna verzija složena nazad na pozadinu = izvor.
a = rgba[..., 3:4] / 255.0
nazad = rgba[..., :3] * a + BG * (1 - a)
print("rekonstrukcija izvora (max/srednja abs, 0-255):", np.abs(nazad - im).max().round(2), np.abs(nazad - im).mean().round(3))

# 6. Znak V (bez natpisa): redovi iznad praznine između znaka i slova.
red = (alfa > 0.5).any(axis=1)
redovi = np.where(red)[0]
praznine = np.where(np.diff(redovi) > 8)[0]
kraj_znaka = redovi[praznine[0]] + 1
zy, zx = np.where(alfa[:kraj_znaka] > 0.5)
cy, cx = (zy.min() + zy.max()) / 2, (zx.min() + zx.max()) / 2
vel = max(np.ptp(zy), np.ptp(zx)) / 0.62                                           # znak = 62 % stranice (maskable)
s = int(round(vel))
y_a, x_a = int(round(cy - s / 2)), int(round(cx - s / 2))
print("znak: redovi do", kraj_znaka, "kvadrat", s, "od", (y_a, x_a))
alfa_z = alfa.copy()
alfa_z[kraj_znaka + 4:] = 0                                                     # bez slova (i njihovog sjaja)


def isecak(arr, fill):
    out = np.empty((s, s) + arr.shape[2:], dtype=np.float64)
    out[...] = fill
    sy0, sx0 = max(y_a, 0), max(x_a, 0)
    sy1, sx1 = min(y_a + s, H), min(x_a + s, W)
    out[sy0 - y_a:sy1 - y_a, sx0 - x_a:sx1 - x_a] = arr[sy0:sy1, sx0:sx1]
    return out


BGz = isecak(BG, BG[int(cy), int(cx)])
Az = isecak(alfa_z, 0)[..., None]
Cz = isecak(boja, F)
znak = Cz * Az + BGz * (1 - Az)
Image.fromarray(znak.round().astype(np.uint8), "RGB").resize((512, 512), Image.LANCZOS).save(D / "vindex-znak-final.png", optimize=True)
print("gotovo:", sorted(p.name for p in D.glob("*final*")))
