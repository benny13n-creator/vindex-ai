# -*- coding: utf-8 -*-
"""TENFRONTS-M07 (BL-004) — pozadinski Genome refresh ne sme da nastavi posle neuspele provere vlasnika.

Dokaz POSTOJEĆEG ponašanja (bez izmene koda): `_do_genome_refresh` čita predmet sa
`.eq("id").eq("user_id").single()`; postgrest 2.28.3 `single()` diže `APIError` za svaki ne-2xx odgovor
(PostgREST vraća 406/PGRST116 za 0 redova), a spoljni `except Exception` funkcije samo loguje i izlazi.
Lažna baza ovde modeluje tačno to: 0 ili >1 red za `single()` → izuzetak."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import routers.case_dna as cd

P, VLASNIK, NAPADAC = "pred-1", "u-vlasnik", "u-drugi"


class _APIError(Exception):
    pass


class _Upit:
    def __init__(self, baza, t):
        self.b, self.t, self.redovi, self.single_ = baza, t, list(baza.tabele.get(t, [])), False

    def select(self, *a, **k):
        self.b.citanja.append(self.t)
        if self.t == "predmeti" and self.b.timeout:
            raise TimeoutError("db timeout")
        return self

    def eq(self, k, v):
        self.redovi = [r for r in self.redovi if r.get(k) == v]
        return self

    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def lt(self, *a, **k): return self

    def single(self):
        self.single_ = True
        return self

    def maybe_single(self): return self

    def _pise(self, *a, **k):
        self.b.upisi.append(self.t)
        return self
    update = insert = upsert = delete = _pise

    def execute(self):
        class R: pass
        r = R(); r.count = len(self.redovi)
        if self.single_:
            if len(self.redovi) != 1:
                raise _APIError('{"code":"PGRST116","message":"JSON object requested, multiple (or no) rows returned"}')
            r.data = self.redovi[0]
        else:
            r.data = self.redovi
        return r


class _Baza:
    def __init__(self, timeout=False):
        self.timeout, self.citanja, self.upisi = timeout, [], []
        self.tabele = {
            "predmeti": [{"id": P, "user_id": VLASNIK, "case_dna": {"verzija": 1}}],
            "predmet_dokumenti": [{"id": "d1", "predmet_id": P, "naziv_fajla": "t.pdf", "redni_broj": 1,
                                   "tekst_sadrzaj": "Tužba radi naknade štete.", "velicina_kb": 1}],
        }

    def table(self, t):
        return _Upit(self, t)


def _pokreni(uid, predmet=P, timeout=False):
    baza = _Baza(timeout)
    gpt = AsyncMock(return_value={"verzija": 2})
    emit = AsyncMock()
    with patch.object(cd, "_get_supa", return_value=baza), \
         patch.object(cd, "_extract_genome", gpt), \
         patch("services.event_bus.emit", emit, create=True), \
         patch("services.event_bus.emit_durable", emit, create=True), \
         patch("shared.audit_immutable.log_action", AsyncMock()):
        asyncio.run(cd._do_genome_refresh(predmet, uid))
    return baza, gpt, emit


@pytest.mark.parametrize("uid,predmet,timeout", [
    (NAPADAC, P, False),             # tuđi predmet
    (VLASNIK, "pred-nepostoji", False),
    ("", P, False),                  # prazan korisnik
    (VLASNIK, P, True),              # greška/timeout provere vlasnika
], ids=["tudji", "nepostojeci", "prazan_uid", "timeout"])
def test_odbijena_provera_nema_nikakvih_posledica(uid, predmet, timeout):
    baza, gpt, emit = _pokreni(uid, predmet, timeout)
    assert gpt.await_count == 0, "GPT pozvan posle neuspele provere vlasnika"
    assert baza.upisi == [], "upis posle neuspele provere vlasnika"
    assert emit.await_count == 0, "upozorenje/događaj posle neuspele provere vlasnika"
    assert "predmet_dokumenti" not in baza.citanja, "čitani dokumenti posle neuspele provere vlasnika"


def test_kontrola_vlasnik_prolazi_do_ekstrakcije():
    _, gpt, _ = _pokreni(VLASNIK)
    assert gpt.await_count == 1
