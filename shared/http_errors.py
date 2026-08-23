# -*- coding: utf-8 -*-
"""Namerni 5xx ugovor prema korisniku.

KONTEKST — dokazano curenje na produkciji `657818a5`
(WRITE-ERROR-DB-VALUE-DISCLOSURE-REPORT.md):

    POST /api/firma-memorija/klijent/sacuvaj  {"rizik_profil": "NEPOSTOJECI_PROFIL"}
    → CHECK violation (SQLSTATE 23514)
    → ruta: `raise HTTPException(500, str(e))`
    → HTTP 500 telo je sadržalo `Failing row contains (…, KANARINAC-…, …)`

Zato `api.py::_http_exception_boundary` po pravilu NE emituje `detail` ni za
jedan status ≥ 500 — korisnik dobija kanonsku poruku, original ide u log.

ALI: neki 5xx odgovori NISU greške sistema nego **poslovna poruka koju korisnik
mora da vidi**. Primer koji je paušalna sanitizacija oborila (9 testova iz B2
gate-a): kad padne izvor za finansijski izveštaj, korisnik mora saznati da
iznos NIJE izračunat — inače bi tišina bila neodvojiva od „nula dinara", što je
tačno kvar koji je B2 gate zatvorio.

Runtime ne može da dokaže da je neka niska bezbedna. Zato se bezbednost NE
pogađa iz sadržaja (to bi bila crna lista koju napadač ispituje), nego se
**deklariše na mestu dizanja**: autor koji podiže ovaj izuzetak tvrdi da je
poruka napisana ručno i da ne sadrži nijedan interni podatak.

PRAVILO: `detail` ovde sme biti ISKLJUČIVO tekst koji je autor napisao.
Nikada `str(e)`, `repr(e)`, `exc.details`, `exc.hint`, SQL, naziv tabele ili
kolone, niti bilo šta izvedeno iz uhvaćenog izuzetka.
"""
from fastapi import HTTPException


class NamerniHTTPException(HTTPException):
    """5xx čiji `detail` JESTE deo korisničkog ugovora i sme se prikazati.

    Sve ostale 5xx putanje ostaju sanitizovane (v. `api.py`).
    """
