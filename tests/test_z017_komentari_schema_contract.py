# -*- coding: utf-8 -*-
"""Z017 — `GET /predmeti/{id}/komentari` mora da procita ono sto je upisano.

PRE-STATE (dokazano uzivo na lokalnoj instanci produkcione baze, 2026-09-05):
    POST /predmeti/{id}/komentari  → 200, red u bazi, `kreirano` popunjeno
    GET  /predmeti/{id}/komentari  → 500  (svaki korisnik, svaki predmet)

  Uzrok je isti kvar kao B-U-001 i B-U-002: kod je gadjao kolonu koja u
  produkciji ne postoji. `get_komentari` je radio
      .order("created_at")
  nad tabelom `predmet_komentari` cije su kolone (sondirano nad produkcionom
  bazom 2026-09-05):
      id, predmet_id, user_id, tekst, kreirano, izmenjeno
  `created_at` ne postoji → PostgREST 42703 → 500.

ZASTO JE OVO GORE OD NEDOSTUPNE FUNKCIJE: upis je radio. Advokat koji unese
belesku „klijent doneo ugovor 12.08." dobija potvrdu da je zabelezeno, a
beleska se nikada ne moze procitati nazad. Funkcija koja ne postoji se vidi;
upis bez citanja se ne vidi dok ne zatreba.

INVARIJANTE:
  1. Citanje komentara sme da gadja samo kolone koje postoje u produkciji.
  2. Komentari se vracaju hronoloski (najstariji prvi) — to je tok razgovora
     o predmetu, ne obrnuti feed.
  3. Citanje je ograniceno na predmet u pitanju i na vlasnika.
  4. META: laznjak stvarno puca na lazno ime kolone — inace test ne meri nista.
"""
import asyncio

import pytest
from unittest.mock import patch

import routers.komentari as K
from tests._schema_fake import Drift42703, napravi_supa

UID = "00000000-0000-0000-0000-00000000000a"
PID = "00000000-0000-0000-0000-0000000000p1"

# ── Kanonska produkciona sema ────────────────────────────────────────────────
# Sondirano nad produkcionom bazom 2026-09-05. Namerno izostavljeni:
# `created_at`, `updated_at`, `azurirano` — ne postoje u `predmet_komentari`.
SEMA = {
    "predmet_komentari": {"id", "predmet_id", "user_id", "tekst",
                          "kreirano", "izmenjeno"},
    "predmeti": {"id", "naziv", "user_id", "status", "tip"},
}

def _lazni_request():
    """`@limiter.limit` zahteva pravi starlette Request (isti obrazac koji vec
    koristi tests/test_bu002_search_schema_contract.py)."""
    from starlette.requests import Request
    return Request({"type": "http", "method": "GET", "path": "/predmeti/x/komentari",
                    "headers": [], "query_string": b"",
                    "client": ("127.0.0.1", 0), "server": ("testserver", 80),
                    "scheme": "http", "root_path": "", "app": None})


PREDMET = {"id": PID, "user_id": UID, "naziv": "Radni spor"}

K1 = {"id": "k1", "predmet_id": PID, "user_id": UID, "tekst": "Prvi",
      "kreirano": "2026-09-01T10:00:00+00:00", "izmenjeno": None}
K2 = {"id": "k2", "predmet_id": PID, "user_id": UID, "tekst": "Drugi",
      "kreirano": "2026-09-02T10:00:00+00:00", "izmenjeno": None}


def _pozovi(redovi=None):
    supa = napravi_supa(SEMA, redovi if redovi is not None else {
        "predmeti": [PREDMET],
        "predmet_komentari": [K1, K2],
    })
    with patch.object(K, "_get_supa", return_value=supa):
        odgovor = asyncio.run(K.get_komentari(
            predmet_id=PID, request=_lazni_request(), user={"user_id": UID}))
    return odgovor, supa


# ── 1. Citanje ne sme da gadja nepostojecu kolonu ────────────────────────────
def test_citanje_komentara_ne_gadja_nepostojecu_kolonu():
    """Ovaj test je jedini razlog zasto je 500 uopste primecen."""
    odgovor, _ = _pozovi()
    assert "komentari" in odgovor


def test_sortira_se_po_kreirano_a_ne_po_created_at():
    _, supa = _pozovi()
    kolone = [k for (t, k) in supa._dnevnik["kolone"] if t == "predmet_komentari"]
    assert "kreirano" in kolone, kolone
    assert "created_at" not in kolone, "vracena je kolona koje nema u produkciji"


# ── 2. Sadrzaj ───────────────────────────────────────────────────────────────
def test_upisan_komentar_se_procita_nazad():
    odgovor, _ = _pozovi()
    tekstovi = [k["tekst"] for k in odgovor["komentari"]]
    assert tekstovi == ["Prvi", "Drugi"], tekstovi


def test_prazna_lista_nije_greska():
    odgovor, _ = _pozovi({"predmeti": [PREDMET], "predmet_komentari": []})
    assert odgovor == {"komentari": []}


# ── 3. Vlasnistvo ────────────────────────────────────────────────────────────
def test_tudji_predmet_daje_403_a_ne_praznu_listu():
    """Prazna lista bi bila tvrdnja da komentara nema — a ne da nemate pristup."""
    from fastapi import HTTPException
    supa = napravi_supa(SEMA, {"predmeti": [], "predmet_komentari": [K1]})
    with patch.object(K, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as ex:
            asyncio.run(K.get_komentari(
                predmet_id=PID, request=_lazni_request(), user={"user_id": UID}))
    assert ex.value.status_code == 403


# ── 4. META — laznjak stvarno puca ───────────────────────────────────────────
def test_meta_laznjak_puca_na_created_at():
    """Bez ovoga ceo fajl moze biti prazan: dokaz da bi PRE-STATE pao."""
    supa = napravi_supa(SEMA, {"predmet_komentari": [K1]})
    with pytest.raises(Drift42703):
        supa.table("predmet_komentari").select("*").order("created_at").execute()


def test_meta_laznjak_propusta_kreirano():
    supa = napravi_supa(SEMA, {"predmet_komentari": [K1]})
    r = supa.table("predmet_komentari").select("*").order("kreirano").execute()
    assert r.data == [K1]


# ═══════════════════════════════════════════════════════════════════════════
# BRISANJE BELESKE — „ok" ne sme da znaci „nista nije poklopljeno"
#
# PRE-STATE: `DELETE /api/predmeti/{pid}/beleske/{bid}` je odbacivao rezultat
# i bezuslovno vracao {"ok": True} — i za nepostojecu i za tudju belesku.
# Owner predikat je uvek drzao (nista tudje nije brisano); lazan je bio
# ODGOVOR. Ista klasa kvara je vec zatvorena za komentare (V31) i za rocista.
#
# Zasto je to vazno na ekranu: V2 posle uspeha kaze „Napomena je obrisana."
# Ako ruta tvrdi uspeh a red stoji, advokat dobija recenicu koja nije istina,
# a napomena se vraca pri sledecem osvezavanju.
# ═══════════════════════════════════════════════════════════════════════════
SEMA_BEL = {"predmet_beleske": {"id", "predmet_id", "user_id", "sadrzaj",
                                "created_at"}}
B1 = {"id": "b1", "predmet_id": PID, "user_id": UID, "sadrzaj": "Beleska",
      "created_at": "2026-09-01T10:00:00+00:00"}


def _obrisi_belesku(redovi):
    import api
    from starlette.requests import Request

    async def _auth(_a):
        class U:
            id = UID
        return U()

    req = Request({"type": "http", "method": "DELETE",
                   "path": "/api/predmeti/x/beleske/y", "headers": [],
                   "query_string": b"", "client": ("127.0.0.1", 0),
                   "server": ("testserver", 80), "scheme": "http",
                   "root_path": "", "app": None})
    supa = napravi_supa(SEMA_BEL, redovi)
    with patch.object(api, "_get_supa", return_value=supa), \
         patch.object(api, "_require_auth_async", _auth):
        return asyncio.run(api.obrisi_belesku(
            predmet_id=PID, beleska_id="b1", request=req, authorization="Bearer x"))


def test_brisanje_postojece_beleske_vraca_ok():
    assert _obrisi_belesku({"predmet_beleske": [B1]}) == {"ok": True}


def test_brisanje_nepostojece_beleske_ne_tvrdi_uspeh():
    """{"ok": True} nad nula pogodjenih redova je recenica koja nije istina."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ex:
        _obrisi_belesku({"predmet_beleske": []})
    assert ex.value.status_code == 404
