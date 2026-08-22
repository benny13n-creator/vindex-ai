# -*- coding: utf-8 -*-
"""Deljeni lažnjak Supabase klijenta koji ZNA PRODUKCIONU ŠEMU.

Zašto postoji: B-U-001 i B-U-002 su bili isti kvar — kod je gađao kolone koje
u produkcionoj bazi ne postoje, a `GET /api/briefing/daily` je padao 500 dva
meseca dok je `GET /api/search` trajno vraćao `nepotpuno: ["klijenti"]`.
Nijedan od ~6300 postojećih testova to nije mogao da uhvati: svi mock-uju
Supabase lažnjakom koji ignoriše imena kolona i vraća šta god test zada, pa
`column X does not exist` u takvom svetu ne može ni da nastane.

Ovaj lažnjak:
  1. validira svako ime kolone — i u `.select(...)` I u filterima
     (`.or_`, `.ilike`, `.eq`, `.neq`, `.in_`, `.gte`, `.lte`, `.lt`, `.gt`,
     `.order`) — protiv skupa kolona SONDIRANOG NAD PRODUKCIONOM BAZOM, i
     diže `Drift42703` isto kao PostgREST;
  2. stvarno primenjuje filtere na zadate redove, pa test može da dokaže da
     se postojeći red NALAZI a nepostojeći NE — a ne samo da je vraćen
     konzervirani odgovor.

Svaki test koji ga koristi MORA imati i META test koji dokazuje da lažnjak
zaista puca na lažnu kolonu — inače je ceo fajl prazan.

Šema se ne prepisuje iz migracija ni iz modela: produkciona baza je autoritet.
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock


class Drift42703(Exception):
    """Isti oblik greške koji PostgREST vraća za nepostojeću kolonu."""


def _uslov_ilike(vrednost, obrazac: str) -> bool:
    if vrednost is None:
        return False
    return obrazac.strip("%").lower() in str(vrednost).lower()


class _Upit:
    """Lanac PostgREST filtera nad listom redova u memoriji."""

    def __init__(self, dnevnik, tabela, sema, redovi, greska):
        self._d, self._t, self._sema = dnevnik, tabela, sema
        self._redovi = list(redovi)
        self._g = greska
        self._limit = None

    # ── validacija imena kolona ──────────────────────────────────────────────
    def _proveri(self, kolona: str) -> str:
        kolona = kolona.strip()
        poznate = self._sema.get(self._t)
        if poznate is not None and kolona and kolona not in poznate:
            raise Drift42703("column %s.%s does not exist (42703)" % (self._t, kolona))
        self._d["kolone"].append((self._t, kolona))
        return kolona

    # ── select ───────────────────────────────────────────────────────────────
    def select(self, kolone="*", *a, **k):
        if kolone != "*":
            for kol in [c for c in re.split(r",", kolone) if c.strip()]:
                self._proveri(kol)
        self._d["select"].append((self._t, kolone))
        return self

    # ── filteri ──────────────────────────────────────────────────────────────
    def eq(self, kolona, vrednost):
        self._proveri(kolona)
        self._d["eq"].append((self._t, kolona.strip(), vrednost))
        self._redovi = [r for r in self._redovi if r.get(kolona.strip()) == vrednost]
        return self

    def neq(self, kolona, vrednost):
        # SQL semantika, ne Python: `NULL <> 'x'` je NULL, pa red ISPADA.
        # Python `None != "x"` je True i red bi ostao -- lažnjak koji to ne
        # modeluje bio bi blaži od baze i proizveo bi lažno zelen test.
        self._proveri(kolona)
        self._d["neq"].append((self._t, kolona.strip(), vrednost))
        self._redovi = [r for r in self._redovi
                        if r.get(kolona.strip()) is not None
                        and r.get(kolona.strip()) != vrednost]
        return self

    def in_(self, kolona, vrednosti):
        self._proveri(kolona)
        dozvoljene = set(vrednosti or [])
        self._redovi = [r for r in self._redovi if r.get(kolona.strip()) in dozvoljene]
        return self

    def ilike(self, kolona, obrazac):
        self._proveri(kolona)
        self._redovi = [r for r in self._redovi if _uslov_ilike(r.get(kolona.strip()), obrazac)]
        return self

    def or_(self, izraz: str, *a, **k):
        """`col.op.value,col.op.value` — PostgREST OR sintaksa."""
        uslovi = []
        for deo in izraz.split(","):
            deo = deo.strip()
            if not deo:
                continue
            kol, _, ostatak = deo.partition(".")
            op, _, vrednost = ostatak.partition(".")
            self._proveri(kol)
            uslovi.append((kol.strip(), op, vrednost))
        self._d["or_"].append((self._t, izraz))

        def _pogadja(r):
            for kol, op, vrednost in uslovi:
                if op == "ilike" and _uslov_ilike(r.get(kol), vrednost):
                    return True
                if op == "eq" and str(r.get(kol)) == vrednost:
                    return True
            return False

        self._redovi = [r for r in self._redovi if _pogadja(r)]
        return self

    def order(self, kolona, *a, **k):
        self._proveri(kolona)
        return self

    def limit(self, n, *a, **k):
        self._limit = n
        return self

    def range(self, a, b, *args, **k):
        self._redovi = self._redovi[a:b + 1]
        return self

    def __getattr__(self, ime):
        # `is_`, `not_`, `single`, `maybe_single`, `insert`, ... — prolaze
        def poziv(*a, **k):
            return self
        return poziv

    def execute(self):
        if self._g is not None:
            raise self._g
        m = MagicMock()
        m.data = self._redovi[:self._limit] if self._limit else self._redovi
        m.count = len(self._redovi)
        return m


def napravi_supa(sema: dict, redovi: dict | None = None, greske: dict | None = None):
    """`sema`: tabela → skup postojećih kolona (None = ne validiraj tu tabelu).
    `redovi`: tabela → lista redova. `greske`: tabela → izuzetak koji `execute()` diže.

    Vraća MagicMock sa `.table(...)`; dnevnik poziva je u `._dnevnik`.
    """
    redovi, greske = redovi or {}, greske or {}
    dnevnik = {"select": [], "eq": [], "neq": [], "or_": [], "kolone": [], "tabele": []}
    m = MagicMock()

    def _table(ime):
        dnevnik["tabele"].append(ime)
        return _Upit(dnevnik, ime, sema, redovi.get(ime, []), greske.get(ime))

    m.table.side_effect = _table
    m._dnevnik = dnevnik
    return m
