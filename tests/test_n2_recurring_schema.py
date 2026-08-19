# -*- coding: utf-8 -*-
"""
N2 (OOS-B2-1) — PONAVLJAJUĆA FAKTURA JE PISALA U ŠEST KOLONA KOJE NE POSTOJE.

ŠTA JE BILO — sonda ključ-po-ključ nad živom šemom (2026-08-18)

`routers/recurring.py::_build_faktura_row` je gradio `INSERT` u `fakture` sa:

    klijent_id · opis · iznos_rsd · pdv_procenat · bruto_rsd · datum_izdavanja
        -> svih šest: `42703: column fakture.<x> does not exist`

Nijedna nije preimenovana ni uklonjena — `migrations/003_billing.sql:7-25` je
jedina definicija tabele i nikad ih nije imala. `recurring_templates` ima SVE
izvorne vrednosti (13/13 kolona OK), pa je ovo **greška mapiranja**, ne
nedostajuća šema.

LANAC: INSERT -> 42703 -> izuzetak IZLAZI iz rute -> HTTP 500 ->
`sledeci_datum` se ne pomera. Nije bilo lažnog uspeha (padalo je glasno), ali
nijedna ponavljajuća faktura nikada nije mogla biti izdata.

DVA DODATNA NALAZA IZ ISTOG LANCA (zatvorena zajedno, jer bez njih „popravka"
6 kolona ostaje lažno zelena):

  * `fakture.broj_fakture` i `fakture.klijent_naziv` su **NOT NULL bez
    default-a**, a payload ih nikad nije postavljao -> INSERT bi pao i posle
    preimenovanja 6 kolona.
  * povratak rute je čitao `faktura["iznos_rsd"]`/`["bruto_rsd"]` -> `KeyError`
    i posle uspešnog upisa.

ZAŠTO POSTOJEĆI TESTOVI NISU UHVATILI KVAR

`tests/test_recurring.py` mokuje `tbl.insert.return_value.execute.return_value`
i **potpuno ignoriše payload**, pa nijedna nepostojeća kolona nije mogla biti
odbijena. Njegov `SAMPLE_FAKTURA` je izmišljen hibrid — sadrži i stvarne
(`broj_fakture`, `datum_fakture`) i nepostojeće kolone (`iznos_rsd`,
`bruto_rsd`, `klijent_id`) — red koji u pravoj bazi ne može postojati.

ZATO `_SemaSupa` OVDE VALIDIRA UPIS: svaki ključ se proverava protiv stvarnog
skupa kolona i diže 42703, isto kao PostgREST. Bez toga test ne bi merio ništa.
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "admin@vindex.ai")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import HTTPException  # noqa: E402
import routers.recurring as rec  # noqa: E402

UID = "uid-001"

# ─── STVARNA ŠEMA (PostgREST OpenAPI koren, 2026-08-18) ──────────────────────
# `fakture`: 17 kolona. Šest iz starog payload-a NAMERNO nije ovde.
SEMA_FAKTURE = {
    "id", "user_id", "predmet_id", "broj_fakture", "datum_fakture",
    "klijent_naziv", "klijent_adresa", "klijent_pib", "iznos_bez_pdv",
    "pdv_iznos", "iznos_sa_pdv", "status", "napomena", "created_at",
    "updated_at", "is_proforma", "datum_dospeca",
}
SEMA_KLIJENTI = {
    "id", "user_id", "ime", "prezime", "firma", "email", "telefon", "adresa",
    "status", "deleted_at", "kreirano",
}
# Šest kolona iz OOS-B2-1 — ovaj skup je predmet nalaza.
SEST_NEVALIDNIH = ["klijent_id", "opis", "iznos_rsd", "pdv_procenat",
                   "bruto_rsd", "datum_izdavanja"]

TPL = {
    "id": "tpl-001", "user_id": UID, "naziv": "Mesečno savetovanje",
    "opis": "Pravno savetovanje", "iznos_rsd": 50000.0, "pdv_procenat": 20.0,
    "klijent_id": "kl-001", "predmet_id": "pred-001",
    "ucestalost": "mesecno", "sledeci_datum": "2026-09-01", "aktivan": True,
}
KLIJENT = {"ime": "Nikola", "prezime": "Petrović", "firma": None}


class SemaGreska(RuntimeError):
    """42703 — isto što PostgREST vrati za nepostojeću kolonu."""


class _SemaSupa:
    """Lažni Supabase koji VALIDIRA i `select` i `insert` payload.

    `pada` je opsegovan po tabeli — failure injector nikad ne obara domen koji
    test ne meri (harness lekcija iz N1).
    """

    def __init__(self, tpl=TPL, klijent=KLIJENT, pada=None,
                 insert_prazan=False, klijent_data_none=False):
        self.tpl = tpl
        self.klijent = klijent
        self.pada = set(pada or ())
        self.insert_prazan = insert_prazan
        self.klijent_data_none = klijent_data_none
        self.upisano: list = []
        self.trazeno: list = []

    def table(self, ime):
        spolja = self

        class _Q:
            def __init__(self):
                self._red = None

            def select(self, kolone="*", *a, **k):
                spolja.trazeno.append((ime, kolone))
                if ime in spolja.pada:
                    raise RuntimeError(f"simuliran ispad tabele {ime}")
                sema = {"fakture": SEMA_FAKTURE, "klijenti": SEMA_KLIJENTI}.get(ime)
                if sema and kolone != "*":
                    for c in [x.strip() for x in kolone.split(",")]:
                        if c and c not in sema:
                            raise SemaGreska(f"42703: column {ime}.{c} does not exist")
                return self

            def insert(self, red, *a, **k):
                if ime in spolja.pada:
                    raise RuntimeError(f"simuliran ispad tabele {ime}")
                if ime == "fakture":
                    for c in red:
                        if c not in SEMA_FAKTURE:
                            raise SemaGreska(f"42703: column fakture.{c} does not exist")
                    for obavezna in ("broj_fakture", "klijent_naziv", "user_id"):
                        if red.get(obavezna) in (None, ""):
                            raise SemaGreska(
                                f'23502: null value in column "{obavezna}" '
                                f"violates not-null constraint")
                    # `insert_prazan` simulira „upit izvršen, 0 redova upisano" —
                    # tada red NIJE perzistiran, pa se ne beleži u `upisano`.
                    if not spolja.insert_prazan:
                        spolja.upisano.append(red)
                self._red = red
                return self

            def update(self, red, *a, **k):
                self._red = red
                return self

            def eq(self, *a, **k):    return self
            def like(self, *a, **k):  return self
            def order(self, *a, **k): return self
            def limit(self, *a, **k): return self
            def maybe_single(self):   return self

            def execute(self):
                if ime == "recurring_templates":
                    return MagicMock(data=spolja.tpl)
                if ime == "klijenti":
                    if spolja.klijent_data_none:
                        return MagicMock(data=None)
                    return MagicMock(data=spolja.klijent)
                if ime == "fakture":
                    if self._red is None:            # SELECT (broj fakture)
                        return MagicMock(data=[])
                    if spolja.insert_prazan:
                        return MagicMock(data=[])
                    return MagicMock(data=[dict(self._red, id="fak-001")])
                return MagicMock(data=[])

        return _Q()


def _request():
    """Pravi starlette Request — `slowapi` rate limiter odbija MagicMock."""
    from starlette.requests import Request as _SReq
    return _SReq({
        "type": "http", "method": "POST",
        "path": "/billing/recurring/tpl-001/generisi",
        "headers": [], "query_string": b"", "client": ("1.2.3.4", 1234),
        "scheme": "http", "server": ("test", 80), "root_path": "",
    })


def _generisi(supa):
    """Vozi PRAVI `generisi_iz_sablona`."""
    with patch.object(rec, "_get_supa", return_value=supa), \
         patch("routers.billing._get_supa", return_value=supa):
        return asyncio.run(rec.generisi_iz_sablona(
            template_id="tpl-001",
            request=_request(),
            user={"user_id": UID, "email": "a@b.rs"},
        ))


# ═══════════════════════════════════════════════════════════════════════════
# PRE-STATE — šest kolona
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("kolona", SEST_NEVALIDNIH)
def test_pre_svaka_od_sest_kolona_obara_insert(kolona):
    """Dokaz da je kvar bio ACTIVE: harness odbija svaku od šest."""
    supa = _SemaSupa()
    with pytest.raises(SemaGreska) as e:
        supa.table("fakture").insert({"user_id": UID, "broj_fakture": "2026/0001",
                                      "klijent_naziv": "X", kolona: "vrednost"})
    assert kolona in str(e.value)


def test_pre_nijedna_od_sest_nije_vise_u_payload_u():
    """Regresiona brava nad izvorom."""
    red = rec._build_faktura_row(TPL, UID, "2026/0001", "Nikola Petrović")
    for kolona in SEST_NEVALIDNIH:
        assert kolona not in red, f"`{kolona}` se i dalje upisuje u `fakture`"
    for kolona in red:
        assert kolona in SEMA_FAKTURE, f"`{kolona}` ne postoji u `fakture`"


# ═══════════════════════════════════════════════════════════════════════════
# A. VALID DATA
# ═══════════════════════════════════════════════════════════════════════════

def test_A_valid_data_faktura_se_stvarno_upisuje():
    supa = _SemaSupa()
    rez = _generisi(supa)

    assert len(supa.upisano) == 1, "nijedan red nije upisan u `fakture`"
    red = supa.upisano[0]
    assert red["iznos_bez_pdv"] == 50000.0
    assert red["pdv_iznos"] == 10000.0          # 20% od 50000
    assert red["iznos_sa_pdv"] == 60000.0
    assert red["klijent_naziv"] == "Nikola Petrović"
    assert red["broj_fakture"]
    assert rez["status"] == "generisano"
    assert rez["iznos_sa_pdv"] == 60000.0


def test_A2_pdv_nula_daje_ispravan_bruto():
    supa = _SemaSupa(tpl=dict(TPL, pdv_procenat=0.0))
    _generisi(supa)
    red = supa.upisano[0]
    assert red["pdv_iznos"] == 0.0
    assert red["iznos_sa_pdv"] == red["iznos_bez_pdv"] == 50000.0


def test_A3_opis_sablona_prezivljava_u_napomeni():
    """`fakture` nema `opis`; sadržaj ne sme nestati."""
    supa = _SemaSupa()
    _generisi(supa)
    assert "Pravno savetovanje" in supa.upisano[0]["napomena"]


# ═══════════════════════════════════════════════════════════════════════════
# B/E. EMPTY · MALFORMED
# ═══════════════════════════════════════════════════════════════════════════

def test_B_prazan_rezultat_upisa_je_neuspeh_ne_uspeh():
    """0 upisanih redova ≠ uspeh."""
    supa = _SemaSupa(insert_prazan=True)
    with pytest.raises(HTTPException) as e:
        _generisi(supa)
    assert e.value.status_code == 500


def test_E_klijent_data_None_daje_eksplicitnu_gresku():
    """`maybe_single()` vraća `None` kad reda nema — ne sme postati prazno ime."""
    supa = _SemaSupa(klijent_data_none=True)
    with pytest.raises(HTTPException) as e:
        _generisi(supa)
    assert e.value.status_code == 422
    assert supa.upisano == [], "faktura upisana bez klijenta"


def test_E2_sablon_bez_klijenta_ne_izmislja_ime():
    """Nema kanonskog izvora naziva -> eksplicitan neuspeh, bez izmišljanja."""
    supa = _SemaSupa(tpl=dict(TPL, klijent_id=None))
    with pytest.raises(HTTPException) as e:
        _generisi(supa)
    assert e.value.status_code == 422
    assert supa.upisano == []
    assert not any(t == "klijenti" for t, _ in supa.trazeno)


def test_E3_klijent_bez_ijednog_imena_ne_prolazi():
    supa = _SemaSupa(klijent={"ime": None, "prezime": None, "firma": None})
    with pytest.raises(HTTPException) as e:
        _generisi(supa)
    assert e.value.status_code == 422
    assert supa.upisano == []


# ═══════════════════════════════════════════════════════════════════════════
# C/D. FAILED · EXCEPTION — i dokaz FAILED ≠ EMPTY
# ═══════════════════════════════════════════════════════════════════════════

def test_C_pad_upisa_fakture_ne_postaje_prazno_ni_uspeh():
    """PAO upis i PRAZAN upis moraju ostati RAZLIČIVI ishodi.

    Ranija verzija ovog testa prihvatala je „sirov izuzetak ILI 500", pa je
    mutacija koja guta DB grešku i pretvara je u istu generičku 500 poruku kao
    „upis je vratio 0 redova" PREŽIVELA. To je ista `FAILED ≠ EMPTY`
    invarijanta jedan nivo dublje: ispad baze i prazan rezultat ne smeju se
    slити u jedan neraspoznatljiv odgovor, jer se tada stvarni uzrok gubi i iz
    odgovora i iz traga.
    """
    palo = _SemaSupa(pada={"fakture"})
    with pytest.raises(Exception) as e_palo:
        _generisi(palo)

    prazno = _SemaSupa(insert_prazan=True)
    with pytest.raises(HTTPException) as e_prazno:
        _generisi(prazno)

    assert palo.upisano == [] and prazno.upisano == []
    assert e_prazno.value.status_code == 500
    # Pad baze NE SME biti isporučen kao isti ishod kao prazan upis.
    assert not (isinstance(e_palo.value, HTTPException)
                and e_palo.value.status_code == e_prazno.value.status_code
                and str(e_palo.value.detail) == str(e_prazno.value.detail)), (
        "ispad baze je sveden na isti odgovor kao prazan rezultat — "
        "uzrok neuspeha je izgubljen")


def test_D_pad_citanja_klijenta_ne_postaje_prazno_ime():
    supa = _SemaSupa(pada={"klijenti"})
    with pytest.raises(Exception):
        _generisi(supa)
    assert supa.upisano == [], "faktura upisana uprkos palom čitanju klijenta"


def test_F_FAILED_nije_EMPTY():
    """Jezgro N2: prazan klijent i PAO klijent daju RAZLIČIT ishod."""
    prazan = _SemaSupa(klijent_data_none=True)
    with pytest.raises(HTTPException) as e1:
        _generisi(prazan)

    palo = _SemaSupa(pada={"klijenti"})
    with pytest.raises(Exception) as e2:
        _generisi(palo)

    assert e1.value.status_code == 422              # provereno: klijenta nema
    assert not isinstance(e2.value, HTTPException)  # provera NIJE izvršena
    assert prazan.upisano == palo.upisano == []


def test_F2_failure_ne_pomera_sledeci_datum():
    """Neuspeh ne sme ostaviti šablon kao da je faktura izdata."""
    supa = _SemaSupa(pada={"fakture"})
    with pytest.raises(Exception):
        _generisi(supa)
    assert supa.upisano == []


# ═══════════════════════════════════════════════════════════════════════════
# VLASNIŠTVO — mora ostati netaknuto
# ═══════════════════════════════════════════════════════════════════════════

def test_lookup_klijenta_je_opsegovan_na_vlasnika():
    """Šablon ne sme povući klijenta drugog korisnika."""
    import re
    src = open(os.path.join(os.path.dirname(__file__), "..", "routers",
                            "recurring.py"), encoding="utf-8").read()
    i = src.index('.table("klijenti")')
    blok = src[i:i + 400]
    assert '.eq("user_id", uid)' in blok, "lookup klijenta nije opsegovan na vlasnika"
    assert '.eq("id", tpl["klijent_id"])' in blok


def test_caller_ugovor_ocuvan():
    """Postojeća polja odgovora ostaju; dodata su samo stvarna."""
    supa = _SemaSupa()
    rez = _generisi(supa)
    for k in ("status", "faktura_id", "sledeci_datum"):
        assert k in rez, f"nedostaje postojeće polje `{k}`"
    for k in ("iznos_rsd", "bruto_rsd"):
        assert k not in rez, f"`{k}` ne postoji u `fakture` — ne sme se vraćati"
