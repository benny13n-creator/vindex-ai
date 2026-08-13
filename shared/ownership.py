# -*- coding: utf-8 -*-
"""Kanonska provera vlasništva nad resursom.

BETA-DATA-CONFIDENTIALITY-002. Forenzika je našla deset ruta koje primaju ID
resursa iz tela zahteva i upisuju po njemu bez ijedne provere. Sve su
WRITE-side — klasa koju su raniji auditi potcenili, jer su tražili
`{predmet_id}` u PUTANJI, a devet od deset ga uzima iz TELA.

ZAŠTO OVO NIJE DUBINSKA ODBRANA NEGO JEDINA ODBRANA

Backend radi sa `service_role` ključem (`shared/deps.py:93`), pa je RLS
zaobiđen na svakoj API putanji. Onih 250 `CREATE POLICY` u repou štiti samo
pristup iz pregledača anon-ključem. Za API saobraćaj izostavljen
`.eq("user_id", ...)` nema ništa ispod sebe.

ZAŠTO JEDAN VLASNIK, A NE DESET KOPIJA

`docs/security/AUTHORIZATION_PATTERN_RECOMMENDATION.md` je 2026-07-23 predložio
tačno ovo i nije primenjen; deset nalaza je predviđena posledica. Deset ručnih
kopija znači deset prilika da se sledeća zaboravi.

404 A NE 403 — svuda i bez izuzetka. 403 kaže „postoji, ali nije tvoje", što
je proročište: napadač njime nabraja tuđe predmete i naloge.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

logger = logging.getLogger("vindex.ownership")


def poseduje(supa, tabela: str, resurs_id: str, user_id: str) -> bool:
    """Da li `resurs_id` u `tabela` pripada baš ovom korisniku.

    Fail-closed: greška u proveri znači NE.  Tiha `True` grana na izuzetak bi
    pretvorila prolazni ispad baze u otvorena vrata.
    """
    if not (resurs_id and user_id):
        return False
    try:
        r = (supa.table(tabela).select("id")
             .eq("id", resurs_id).eq("user_id", user_id).limit(1).execute())
        return bool(r.data)
    except Exception as e:
        logger.warning("[OWNERSHIP] provera %s/%s pala, odbijam: %s", tabela, resurs_id, e)
        return False


def zahtevaj(supa, tabela: str, resurs_id: str, user_id: str) -> None:
    """Kao `poseduje`, ali diže 404 umesto da vrati False.

    Prazan `resurs_id` NIJE greška — polje je opciono na više ruta; pozivalac
    prosleđuje ono što je dobio, a ovde se ne proverava ništa ako ničega nema.
    """
    if not resurs_id:
        return
    if not poseduje(supa, tabela, resurs_id, user_id):
        raise HTTPException(status_code=404, detail="Resurs nije pronađen.")
