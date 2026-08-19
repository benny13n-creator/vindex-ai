# -*- coding: utf-8 -*-
"""
N4-COI-001 — provera sukoba interesa u Intake toku mora biti fail-closed.

PRE-STATE (dokazano izvrsenjem 2026-08-18):
  `routers/intake.py::_run_conflict_check` je pretvarao pad upita u prazan
  rezultat na CETIRI nezavisna mesta — spoljni `except` (:700) i tri
  `return_exceptions=True` gutaca (klijenti, predmeti, predmet_klijenti).
  Svaki pad je zavrsavao kao `len([]) > 0 == False` ->
  "Nije detektovan sukob interesa. Mozete otvoriti predmet."
  Odgovor pri padu bio je BAJT-IDENTICAN odgovoru pri istinski cistoj proveri;
  u odgovoru nije postojalo nijedno polje o statusu provere.

  Tri ranija COI gate-a (BETA-P0-COI, BETA-P1 column drift) gadjala su druge
  dve implementacije (`klijenti/router.py`, `routers/conflict_check.py`);
  intake jezgro nikad nije bilo podvrgnuto fail-closed reviziji.

INVARIJANTA: CHECK_FAILED se NIKAD ne sme preslikati u NO_CONFLICT.
"""
import ast
import asyncio
import io
import sys

import pytest
from unittest.mock import MagicMock, patch

# `event_bus` mora biti ucitan PRE `case_evolution` (medjusobni import).
from services.event_bus import Event, EventType  # noqa: F401

import routers.intake as intake

COI_NO_CONFLICT = intake.COI_NO_CONFLICT
COI_CONFLICT_FOUND = intake.COI_CONFLICT_FOUND
COI_CHECK_FAILED = intake.COI_CHECK_FAILED

UID = "00000000-0000-0000-0000-000000000001"

# Realni PostgREST/mrezni kvarovi, doslovno onako kako stizu iz produkcije.
KVAROVI = {
    "42703_kolona": Exception("column klijenti.firma does not exist (code 42703)"),
    "PGRST205_tabela": Exception("Could not find the table 'public.predmet_klijenti' (PGRST205)"),
    "42501_rls": Exception("new row violates row-level security policy (code 42501)"),
    "timeout": TimeoutError("connection timeout expired"),
    "neocekivani": ValueError("neocekivano stanje drajvera"),
}

KLIJENT_PETAR = {
    "id": "c-1", "ime": "Petar", "prezime": "Petrović",
    "firma": "", "pib_encrypted": None,
}
PREDMET_1 = {"id": "p-1", "naziv": "Spor 1/2026", "tuzilac": "", "tuzeni": ""}


def _supa(clients=None, predmeti=None, pk_by_client=None, puca=None):
    """Supabase dvojnik sa SELEKTIVNIM padom po tabeli.

    `puca` = {ime_tabele: Exception}. Fake koji uvek vraca iste redove ne bi
    mogao da reprodukuje nijedan od cetiri kvara — pad mora biti adresibilan.
    """
    clients = clients if clients is not None else []
    predmeti = predmeti if predmeti is not None else []
    pk_by_client = pk_by_client or {}
    puca = puca or {}

    mock = MagicMock()

    def _table(name):
        t = MagicMock()
        greska = puca.get(name)

        if name == "klijenti":
            izvrsi = t.select.return_value.eq.return_value.neq.return_value.execute
            if greska is not None:
                izvrsi.side_effect = greska
            else:
                izvrsi.return_value.data = clients

        elif name == "predmeti":
            izvrsi = t.select.return_value.eq.return_value.execute
            if greska is not None:
                izvrsi.side_effect = greska
            else:
                izvrsi.return_value.data = predmeti

        elif name == "predmet_klijenti":
            def _eq(kolona, vrednost):
                unutra = MagicMock()
                if greska is not None:
                    unutra.execute.side_effect = greska
                else:
                    unutra.execute.return_value.data = pk_by_client.get(vrednost, [])
                return unutra
            t.select.return_value.eq.side_effect = _eq

        return t

    mock.table.side_effect = _table
    return mock


def _pokreni(supa, ime="Marko Marković", protivna="Petar Petrović"):
    with patch.object(intake, "_get_supa", return_value=supa), \
         patch.object(intake, "_sentry_capture", lambda *a, **k: None):
        return asyncio.run(intake._run_conflict_check(UID, ime, "", protivna, ""))


# ---------------------------------------------------------------------------
# A. PRIHVATNA MATRICA — pet redova iz mandata
# ---------------------------------------------------------------------------

def test_a1_stvarno_nema_konflikta__NO_CONFLICT():
    r = _pokreni(_supa(clients=[], predmeti=[]))
    assert r["status_provere"] == COI_NO_CONFLICT
    assert r["conflict_detected"] is False
    assert r["izvori_neuspeh"] == []
    assert "Nije detektovan sukob" in r["preporuka"]


def test_a2_konflikt_postoji__CONFLICT_FOUND():
    r = _pokreni(_supa(
        clients=[KLIJENT_PETAR],
        predmeti=[PREDMET_1],
        pk_by_client={"c-1": [{"predmet_id": "p-1", "uloga_klijenta": "stranka"}]},
    ))
    assert r["status_provere"] == COI_CONFLICT_FOUND
    assert r["conflict_detected"] is True
    assert r["has_blocker"] is True
    assert r["izvori_neuspeh"] == []


@pytest.mark.parametrize("ime_kvara", sorted(KVAROVI))
def test_a3_svaki_kvar_klijenata__CHECK_FAILED(ime_kvara):
    r = _pokreni(_supa(puca={"klijenti": KVAROVI[ime_kvara]}))
    assert r["status_provere"] == COI_CHECK_FAILED, ime_kvara
    assert "klijenti" in r["izvori_neuspeh"]
    assert "Nije detektovan sukob" not in r["preporuka"]
    assert "NIJE izvršena" in r["preporuka"]


@pytest.mark.parametrize("ime_kvara", sorted(KVAROVI))
def test_a4_svaki_kvar_predmeta__CHECK_FAILED(ime_kvara):
    r = _pokreni(_supa(puca={"predmeti": KVAROVI[ime_kvara]}))
    assert r["status_provere"] == COI_CHECK_FAILED, ime_kvara
    assert "predmeti" in r["izvori_neuspeh"]


@pytest.mark.parametrize("ime_kvara", sorted(KVAROVI))
def test_a5_kvar_uloga_pogodjenog_klijenta__CHECK_FAILED(ime_kvara):
    """Najpodmukliji sloj: klijenti i predmeti se procitaju, a bas uloge
    pogodjenog klijenta — sloj u kome se blokirajuci sukob prepoznaje — ne."""
    r = _pokreni(_supa(
        clients=[KLIJENT_PETAR],
        predmeti=[PREDMET_1],
        puca={"predmet_klijenti": KVAROVI[ime_kvara]},
    ))
    assert r["status_provere"] == COI_CHECK_FAILED, ime_kvara
    assert "predmet_klijenti" in r["izvori_neuspeh"]
    assert r["conflicts"] == []


# ---------------------------------------------------------------------------
# B. INVARIJANTA — FAILED nikad ne postaje NO_CONFLICT
# ---------------------------------------------------------------------------

def test_b1_neuspeh_ima_prednost_nad_pronadjenim_konfliktom():
    """Jedan sloj nadje sukob, drugi padne. Provera i dalje NIJE potpuna."""
    r = _pokreni(_supa(
        clients=[KLIJENT_PETAR],
        predmeti=[PREDMET_1],
        pk_by_client={"c-1": [{"predmet_id": "p-1", "uloga_klijenta": "stranka"}]},
        puca={"predmeti": KVAROVI["timeout"]},
    ))
    assert r["status_provere"] == COI_CHECK_FAILED
    assert r["conflict_detected"] is True, "pronadjeni sukob se ne sme sakriti"


def test_b2_neuspeh_svih_izvora():
    r = _pokreni(_supa(puca={
        "klijenti": KVAROVI["42501_rls"],
        "predmeti": KVAROVI["42501_rls"],
    }))
    assert r["status_provere"] == COI_CHECK_FAILED
    assert set(r["izvori_neuspeh"]) == {"klijenti", "predmeti"}


def test_b3_odgovor_pri_padu_NIJE_isti_kao_pri_cistoj_proveri():
    """Tacan pre-state defekt: ova dva odgovora su bila bajt-identicna."""
    pad = _pokreni(_supa(puca={"klijenti": KVAROVI["42703_kolona"]}))
    cist = _pokreni(_supa(clients=[], predmeti=[]))
    assert pad != cist
    assert pad["status_provere"] != cist["status_provere"]
    assert pad["preporuka"] != cist["preporuka"]


def test_b4_status_je_masinski_proverljiv():
    """Mandat: ne prihvata se `conflict_detected=False` + pomocna poruka."""
    for r in (_pokreni(_supa(puca={"klijenti": KVAROVI["timeout"]})),
              _pokreni(_supa(clients=[], predmeti=[]))):
        assert isinstance(r.get("status_provere"), str)
        assert r["status_provere"] in (COI_NO_CONFLICT, COI_CONFLICT_FOUND, COI_CHECK_FAILED)


def test_b5_spoljni_except_takodje_daje_FAILED():
    """Pad van `gather`-a (npr. `supa.table` sam po sebi puca)."""
    # Redovi se procitaju, ali su neispravnog oblika -> petlja poredjenja
    # puca IZVAN `gather`-a, tamo gde `return_exceptions` ne dopire.
    r = _pokreni(_supa(clients=[None], predmeti=[PREDMET_1]))
    assert r["status_provere"] == COI_CHECK_FAILED
    assert "provera" in r["izvori_neuspeh"]


# ---------------------------------------------------------------------------
# C. POTROSACI — fail-closed mora prezivati do kraja lanca
# ---------------------------------------------------------------------------

def _lazni_korisnik():
    return {"user_id": UID, "email": "advokat@vindex.rs", "role": "advokat"}


class _Telo:
    novi_klijent_ime = "Marko Marković"
    novi_klijent_firma = ""
    protivna_strana = "Petar Petrović"
    pib = ""


def test_c1_http_ruta_vraca_503_pri_neuspehu():
    """`r.ok` na frontendu mora da uhvati neuspeh, ne samo semanticki status."""
    from fastapi import HTTPException
    with patch.object(intake, "_get_supa", return_value=_supa(puca={"klijenti": KVAROVI["timeout"]})), \
         patch.object(intake, "_sentry_capture", lambda *a, **k: None):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(intake.intake_conflict_check.__wrapped__(
                body=_Telo(), request=MagicMock(), user=_lazni_korisnik()))
    assert exc.value.status_code == 503
    assert exc.value.detail["status_provere"] == COI_CHECK_FAILED


def test_c2_http_ruta_vraca_200_pri_cistoj_proveri():
    """Kontrola: bez ovoga bi c1 prolazio i da ruta uvek puca."""
    with patch.object(intake, "_get_supa", return_value=_supa(clients=[], predmeti=[])):
        r = asyncio.run(intake.intake_conflict_check.__wrapped__(
            body=_Telo(), request=MagicMock(), user=_lazni_korisnik()))
    assert r["status_provere"] == COI_NO_CONFLICT


def test_c3_event_bus_potrosac_ne_sme_reci_no_conflict():
    """`services/case_evolution.py` je pri padu vracao "no_conflict" i
    proaktivni alarm se nikad ne bi kreirao — tiho i trajno."""
    import services.case_evolution as ce

    dogadjaj = Event(
        type=EventType.NEW_CLIENT_LINKED, user_id=UID, predmet_id="p-1",
        payload={"klijent_ime": "Marko Marković", "protivna_strana": "Petar Petrović"},
    )

    with patch.object(intake, "_get_supa", return_value=_supa(puca={"klijenti": KVAROVI["42501_rls"]})), \
         patch.object(intake, "_sentry_capture", lambda *a, **k: None):
        with pytest.raises(RuntimeError) as exc:
            asyncio.run(ce._consequence_conflict_check(dogadjaj))
    assert "nije izvršena" in str(exc.value).lower()


def test_c4_event_bus_potrosac_kontrola_cist_slucaj():
    import services.case_evolution as ce

    dogadjaj = Event(
        type=EventType.NEW_CLIENT_LINKED, user_id=UID, predmet_id="p-1",
        payload={"klijent_ime": "Marko Marković", "protivna_strana": "Petar Petrović"},
    )

    with patch.object(intake, "_get_supa", return_value=_supa(clients=[], predmeti=[])):
        ishod = asyncio.run(ce._consequence_conflict_check(dogadjaj))
    assert ishod == "no_conflict"


# ---------------------------------------------------------------------------
# D. UGOVOR — isti pojam, isto ime, ista istina kao kanonska implementacija
# ---------------------------------------------------------------------------

def test_d1_konstante_su_identicne_kanonskim():
    import klijenti.router as kr
    assert intake.COI_NO_CONFLICT == kr.COI_NO_CONFLICT
    assert intake.COI_CONFLICT_FOUND == kr.COI_CONFLICT_FOUND
    assert intake.COI_CHECK_FAILED == kr.COI_CHECK_FAILED


def test_d2_ime_polja_je_isto_kao_kanonsko():
    r = _pokreni(_supa(clients=[], predmeti=[]))
    assert "status_provere" in r, "kanonsko ime polja iz klijenti/router.py"


def test_d3_nijedna_grana_ne_preslikava_FAILED_u_NO_CONFLICT():
    src = io.open("routers/intake.py", encoding="utf-8").read()
    t = ast.parse(src)
    fn = next(n for n in ast.walk(t)
              if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
              and n.name == "_run_conflict_check")
    telo = ast.get_source_segment(src, fn)
    # Jedina dodela COI_NO_CONFLICT sme biti u `else` grani posle provere
    # `izvori_neuspeh` — dakle nikad uz pomen neuspeha u istoj naredbi.
    for red in telo.split("\n"):
        if "COI_NO_CONFLICT" in red and "=" in red:
            assert "izvori_neuspeh" not in red, red


def test_d4_sva_cetiri_mesta_pada_su_pokrivena():
    """Regresiona brana: ako neko doda peti `return_exceptions`, ovaj test
    ne moze da ga vidi — ali moze da vidi da nijedan postojeci nije ostao nem."""
    src = io.open("routers/intake.py", encoding="utf-8").read()
    t = ast.parse(src)
    fn = next(n for n in ast.walk(t)
              if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
              and n.name == "_run_conflict_check")
    telo = ast.get_source_segment(src, fn)
    assert telo.count("izvori_neuspeh.append") >= 4, (
        "cetiri nezavisna mesta pada moraju upisati neuspeh")
