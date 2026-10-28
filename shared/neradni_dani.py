# -*- coding: utf-8 -*-
"""
Vindex AI — shared/neradni_dani.py

N4 (2026-10-27): neradni dani za pomeranje POSLEDNJEG dana roka (ZPP čl. 103 st. 4–5, ZUP čl. 80 st. 5,
ZKP čl. 224, ZOO čl. 77 st. 3 — tekstovi su u data/laws/pdfs i provereni).

Neradni dan = subota, nedelja ili državni praznik koji se praznuje neradno (Zakon o državnim i drugim
praznicima u Republici Srbiji): 1. i 2. januar, 7. januar, 15. i 16. februar, 1. i 2. maj, 11. novembar i
pravoslavni Vaskrs od Velikog petka do drugog dana Vaskrsa. Kad 1/2. januar, 15/16. februar, 1/2. maj ili
11. novembar padne u nedelju, neradan je i prvi naredni ponedeljak.

GRANICA: tekst Zakona o državnim i drugim praznicima NIJE u lokalnim izvorima (data/laws/pdfs), pa pozivalac
to mora da kaže uz rezultat. Verski praznici pojedinih zajednica (npr. katolički Božić za vernike) i lokalni
neradni dani nisu uračunati. Ranije tabele (routers/zastarelost.py, routers/rokovi_lanac.py) imaju Vaskrs
samo za 2025–2027; ovde se računa za svaku godinu 1900–2099.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

IZVOR_PRAZNIKA = ("Zakon o državnim i drugim praznicima u Republici Srbiji (tekst nije u lokalnoj bazi Vindexa); "
                  "verski praznici pojedinih zajednica i lokalni neradni dani nisu uračunati")
_NERADNI_SA_PONEDELJKOM = ((1, 1), (1, 2), (2, 15), (2, 16), (5, 1), (5, 2), (11, 11))


def pravoslavni_vaskrs(godina: int) -> date:
    """Julijanski Vaskrs (Meeus) preveden u gregorijanski kalendar (+13 dana važi za 1900–2099)."""
    if not 1900 <= godina <= 2099:
        raise ValueError("godina van opsega 1900–2099")
    a, b, c = godina % 4, godina % 7, godina % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    mesec, dan = divmod(d + e + 114, 31)
    return date(godina, mesec, dan + 1) + timedelta(days=13)


@lru_cache(maxsize=256)
def drzavni_praznici(godina: int) -> frozenset:
    dani = {date(godina, m, d) for m, d in _NERADNI_SA_PONEDELJKOM} | {date(godina, 1, 7)}
    v = pravoslavni_vaskrs(godina)
    vaskrs = {v - timedelta(days=2), v - timedelta(days=1), v, v + timedelta(days=1)}
    dani |= vaskrs
    for m, d in _NERADNI_SA_PONEDELJKOM:
        x = date(godina, m, d)
        if x.weekday() == 6:
            # Praznik u nedelju → neradan je prvi naredni dan koji već nije praznik (1.1. nedelja → 3.1.;
            # 2.5. nedelja = Vaskrs 2027 → 3.5. je drugi dan Vaskrsa, pa je neradan i 4.5.).
            y = x + timedelta(days=1)
            while y in dani:
                y += timedelta(days=1)
            dani.add(y)
    return frozenset(dani)


def je_neradan(d: date) -> bool:
    return d.weekday() >= 5 or d in drzavni_praznici(d.year)


def razlog(d: date) -> str:
    if d in drzavni_praznici(d.year):
        return "državni praznik"
    return "subotu" if d.weekday() == 5 else "nedelju" if d.weekday() == 6 else ""


def prvi_radni_od(d: date) -> date:
    """Isti dan ako je radni, inače prvi naredni radni dan."""
    while je_neradan(d):
        d += timedelta(days=1)
    return d
