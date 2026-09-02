# -*- coding: utf-8 -*-
"""FAZA 6.5 — POTVRDA I GRANICA OTKRIVANJA: implementacija.

STA JE ZATVORENO
================
FAZA 6.4.2 je zatvorila ACTION (nista ne izlazi bez potvrde). FAZA 6.4.3 je
izmerila da DISCLOSURE nije ni bio definisan: klijentski portal (token BEZ
logina, dakle trece lice) prikazivao je nepotvrdjen AI rok, a `potvrdi_rok` nije
imao nijednog pozivaoca — advokat nije mogao nista da potvrdi.

Ovde su obe strane zatvorene JEDNOM politikom sa cetiri potrosaca:

    stanje         INTERNAL   CLIENT   EXPORT_EXTERNAL   ACTION
    UNCONFIRMED    vidi       NE       NE                NE
    CONFIRMED      vidi       vidi     vidi              sme
    REJECTED       vidi       NE       NE                NE

`INTERNAL` vidi sve namerno: advokat mora videti kandidata da bi ga potvrdio, a
odbijen rok mora ostati u istoriji. ODBIJEN NIJE OBRISAN.
"""
import asyncio
import io
import os
import re
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.rok_potvrda import (  # noqa: E402
    STANJE_NEPOTVRDJEN, STANJE_ODBIJEN, STANJE_POTVRDJEN, stanje_roka,
)
from shared.rokovi import (  # noqa: E402
    POTROSAC_AKCIJA, POTROSAC_IZVOZ_SPOLJA, POTROSAC_KLIJENT, POTROSAC_INTERNI,
    filtriraj_za, sme_pokrenuti_obavezu, sme_pristupiti,
)

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _izv(rel):
    return io.open(os.path.join(KOREN, rel), encoding="utf-8").read()


def _r(rid="r-1", izvor="AI_AUTONOMOUS", vaznost="kritičan", akter="DOO Alfa Trejd"):
    return {"id": rid, "izvor": izvor, "vaznost": vaznost, "akter": akter,
            "predmet_id": "p-1", "dogadjaj": "Rok", "datum_iso": "2026-03-15"}


POTVRDJEN = {"r-1": STANJE_POTVRDJEN}
ODBIJEN = {"r-1": STANJE_ODBIJEN}
NEPOTVRDJEN: dict = {}


# ═══════════════════════════════════════════════════════════════════════════
# PART XIV — AUTHORIZATION + DISCLOSURE (matrica 3 x 4)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("stanje,mapa,ocekivano", [
    ("UNCONFIRMED", NEPOTVRDJEN, {"INTERNAL": True,  "CLIENT": False, "EXPORT": False, "ACTION": False}),
    ("CONFIRMED",   POTVRDJEN,   {"INTERNAL": True,  "CLIENT": True,  "EXPORT": True,  "ACTION": True}),
    ("REJECTED",    ODBIJEN,     {"INTERNAL": True,  "CLIENT": False, "EXPORT": False, "ACTION": False}),
])
def test_matrica_stanje_x_potrosac(stanje, mapa, ocekivano):
    assert sme_pristupiti(_r(), mapa, potrosac=POTROSAC_INTERNI) is ocekivano["INTERNAL"], stanje
    assert sme_pristupiti(_r(), mapa, potrosac=POTROSAC_KLIJENT) is ocekivano["CLIENT"], stanje
    assert sme_pristupiti(_r(), mapa, potrosac=POTROSAC_IZVOZ_SPOLJA) is ocekivano["EXPORT"], stanje
    assert sme_pristupiti(_r(), mapa, potrosac=POTROSAC_AKCIJA) is ocekivano["ACTION"], stanje


def test_nepoznat_potrosac_je_fail_closed():
    assert sme_pristupiti(_r(), POTVRDJEN, potrosac="NOVI_KANAL") is False


@pytest.mark.parametrize("izvor", [
    "AI_AUTONOMOUS", "AI_ASSISTED", "HUMAN_DIRECT",
    "DETERMINISTIC", "SYSTEM", "LEGACY_UNKNOWN", None, "FUTURE_AGENT"])
@pytest.mark.parametrize("potrosac", [POTROSAC_KLIJENT, POTROSAC_IZVOZ_SPOLJA, POTROSAC_AKCIJA])
def test_18_19_20_poreklo_ne_ovlascuje_nijednog_potrosaca(izvor, potrosac):
    """Klijentski portal (i svaki drugi potrosac) ne moze sam sebe ovlastiti
    preko `izvor`, `akter` ni `vaznost`."""
    assert sme_pristupiti(_r(izvor=izvor), NEPOTVRDJEN, potrosac=potrosac) is False
    assert sme_pristupiti(_r(izvor=izvor), POTVRDJEN, potrosac=potrosac) is True


@pytest.mark.parametrize("akter", ["Advokat", "Genome (AI)", "Sud", "", None])
@pytest.mark.parametrize("vaznost", ["kritičan", "važan", "informativan"])
def test_akter_i_vaznost_ne_menjaju_ishod(akter, vaznost):
    red = _r(akter=akter, vaznost=vaznost)
    assert sme_pristupiti(red, NEPOTVRDJEN, potrosac=POTROSAC_KLIJENT) is False
    assert sme_pristupiti(red, POTVRDJEN, potrosac=POTROSAC_KLIJENT) is True


# ═══════════════════════════════════════════════════════════════════════════
# PART XI 1–2 — EXACT-ID: potvrda/odbijanje jednog ne prelazi na drugi
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("opis,a,b", [
    ("isti predmet/datum/naziv/vaznost, drugi ID",
     {"id": "rok-1", "predmet_id": "p", "datum_iso": "2026-03-15",
      "dogadjaj": "Rok za žalbu", "vaznost": "kritičan"},
     {"id": "rok-2", "predmet_id": "p", "datum_iso": "2026-03-15",
      "dogadjaj": "Rok za žalbu", "vaznost": "kritičan"}),
])
@pytest.mark.parametrize("potrosac", [POTROSAC_KLIJENT, POTROSAC_AKCIJA, POTROSAC_IZVOZ_SPOLJA])
def test_1_potvrda_A_nije_potvrda_B(opis, a, b, potrosac):
    mapa = {"rok-1": STANJE_POTVRDJEN}
    assert sme_pristupiti(a, mapa, potrosac=potrosac) is True, opis
    assert sme_pristupiti(b, mapa, potrosac=potrosac) is False, opis


def test_2_odbijanje_A_nije_odbijanje_B():
    a, b = _r("rok-1"), _r("rok-2")
    mapa = {"rok-1": STANJE_ODBIJEN, "rok-2": STANJE_POTVRDJEN}
    assert sme_pristupiti(a, mapa, potrosac=POTROSAC_KLIJENT) is False
    assert sme_pristupiti(b, mapa, potrosac=POTROSAC_KLIJENT) is True


def test_17_nov_ID_trazi_novu_odluku():
    """Novi observation sa NOVIM ID-em nije pokriven prethodnom odlukom —
    ni potvrdom ni odbijanjem. To je poznata praznina zivotnog ciklusa i
    NAMERNO se ne premoscava heuristikom."""
    stara = {"rok-stari": STANJE_ODBIJEN}
    assert stanje_roka("rok-novi", stara) == STANJE_NEPOTVRDJEN
    assert sme_pristupiti(_r("rok-novi"), stara, potrosac=POTROSAC_AKCIJA) is False


def test_16_odbijanje_ne_brise_rok():
    """ODBIJEN NIJE OBRISAN: ostaje vidljiv advokatu."""
    assert sme_pristupiti(_r(), ODBIJEN, potrosac=POTROSAC_INTERNI) is True


# ═══════════════════════════════════════════════════════════════════════════
# PART IX — POTVRDA NE MENJA IZVORNI ZAPIS
# ═══════════════════════════════════════════════════════════════════════════

def test_13_14_15_odluka_ne_menja_poreklo_aktera_ni_prioritet():
    red = _r(izvor="AI_AUTONOMOUS", akter="Sud u Beogradu", vaznost="važan")
    kopija = dict(red)
    for mapa in (NEPOTVRDJEN, POTVRDJEN, ODBIJEN):
        for p in (POTROSAC_INTERNI, POTROSAC_KLIJENT, POTROSAC_AKCIJA):
            sme_pristupiti(red, mapa, potrosac=p)
    assert red == kopija, "politika je izmenila red koji joj je prosledjen"


def test_modul_odluke_ne_pise_u_hronologiju():
    s = _izv("shared/rok_potvrda.py")
    assert 'table("predmet_hronologija")' not in s
    assert s.count('table("audit_immutable")') == 1


def test_ruta_odluke_ne_menja_rok():
    """`rok_odluka.py` sme SAMO da cita hronologiju (vlasnistvo + prikaz)."""
    s = _izv("routers/rok_odluka.py")
    for zabranjeno in (".insert(", ".update(", ".delete(", ".upsert("):
        assert zabranjeno not in s, f"ruta odluke poziva `{zabranjeno}` nad rokom"


# ═══════════════════════════════════════════════════════════════════════════
# PART XI 7–12 — NEMA IMPLICITNE POTVRDE
# ═══════════════════════════════════════════════════════════════════════════

#: Jedini fajl koji sme da poziva `potvrdi_rok`/`odbij_rok`.
DOZVOLJEN_POZIVALAC = "routers/rok_odluka.py"


def test_7_do_12_samo_jedna_povrsina_potvrdjuje():
    """Pregled, upload, kreiranje predmeta, Copilot, izvoz i kalendar NE
    potvrdjuju. Dokaz: jedini pozivalac odluke je namenska ruta."""
    nadjeni = []
    for k, _d, fs in os.walk(KOREN):
        if any(x in k for x in ("tests", ".git", "node_modules", "data", "__pycache__")):
            continue
        for ime in fs:
            if not ime.endswith((".py", ".js")):
                continue
            rel = os.path.relpath(os.path.join(k, ime), KOREN).replace(os.sep, "/")
            if rel in ("shared/rok_potvrda.py", DOZVOLJEN_POZIVALAC):
                continue
            s = io.open(os.path.join(k, ime), encoding="utf-8", errors="replace").read()
            if re.search(r"\b(potvrdi_rok|odbij_rok)\b", s):
                nadjeni.append(rel)
    assert nadjeni == [], f"potvrdu poziva jos neko: {nadjeni}"


def test_pregled_kandidata_ne_potvrdjuje():
    """`GET /api/rokovi/kandidati` samo cita — nema upisa ni odluke."""
    s = _izv("routers/rok_odluka.py")
    telo = s[s.index("async def kandidati("):s.index("async def potvrdi(")]
    assert "potvrdi_rok" not in telo and "odbij_rok" not in telo
    assert ".insert(" not in telo


@pytest.mark.parametrize("modul", [
    "api.py", "routers/case_dna.py", "routers/smart_intake.py",
    "routers/copilot.py", "routers/intake.py", "routers/export.py",
    "routers/integrations.py", "routers/client_portal.py",
])
def test_pisci_i_potrosaci_ne_potvrdjuju(modul):
    s = _izv(modul)
    assert "potvrdi_rok" not in s and "rok_potvrdjen" not in s, \
        f"{modul} potvrdjuje rok"


# ═══════════════════════════════════════════════════════════════════════════
# PART XI 4–5 — KLIJENTSKI PORTAL
# ═══════════════════════════════════════════════════════════════════════════

def test_4_5_portal_koristi_kanonsku_politiku():
    s = _izv("routers/client_portal.py")
    assert "from shared.rokovi import filtriraj_za" in s
    assert "POTROSAC_KLIJENT" in s
    assert s.count("_filtriraj_za(") == 2, "oba klijentska skupa moraju biti filtrirana"
    # poziv ide kroz `asyncio.to_thread(_odluke, ...)` -- bez zagrade uz ime
    assert "_odluke" in s, "portal ne cita stanje odluka"


def test_portal_upiti_dovlace_id():
    s = _izv("routers/client_portal.py")
    for deo in s.split('table("predmet_hronologija")')[1:]:
        sel = deo[deo.index(".select("):deo.index(")", deo.index(".select("))]
        assert '"id' in sel or "id," in sel, f"portal upit bez `id`: {sel}"


def test_portal_ne_koristi_izvor_akter_vaznost_kao_dozvolu():
    """Stari filter (`[INTERNI]`, `vaznost`) sme da OSTANE kao skrivanje internih
    beleski, ali NE SME biti jedina granica — kanonska politika ide PRE njega."""
    s = _izv("routers/client_portal.py")
    i_pol = s.index("_filtriraj_za(hron_raw")
    i_star = s.index('startswith("[INTERNI]")')
    assert i_pol < i_star, "tekstualni filter se primenjuje pre kanonske politike"
    assert "izvor" not in s[i_pol:i_star], "politika portala gleda poreklo"


def test_4_5_klijent_ne_vidi_nepotvrdjen_ni_odbijen():
    redovi = [_r("a"), _r("b"), _r("c")]
    mapa = {"a": STANJE_POTVRDJEN, "b": STANJE_ODBIJEN}   # "c" nepotvrdjen
    vidljivo = filtriraj_za(redovi, mapa, potrosac=POTROSAC_KLIJENT)
    assert [x["id"] for x in vidljivo] == ["a"]


# ═══════════════════════════════════════════════════════════════════════════
# PART V — IZVOZ
# ═══════════════════════════════════════════════════════════════════════════

def test_pdf_izvoz_oznacava_nepotvrdjen_rok():
    """PDF je advokatov radni spis (INTERNAL): nepotvrdjen rok OSTAJE, ali je
    vidljivo oznacen. Tiho izostavljanje bi bilo gore od prikaza kandidata."""
    s = _izv("predmet_pdf.py")
    assert '[NEPOTVRĐENO]' in s and '[ODBIJENO]' in s
    e = _izv("routers/export.py")
    assert "_stanje_roka(" in e and "stanje_odluke" in e


# ═══════════════════════════════════════════════════════════════════════════
# PART VII — JEDNA POLITIKA, NE VISE NJIH
# ═══════════════════════════════════════════════════════════════════════════

def test_akcija_delegira_centralnoj_politici():
    s = _izv("shared/rokovi.py")
    telo = s[s.index("def sme_pokrenuti_obavezu("):s.index("def filtriraj_izvrsive(")]
    assert "sme_pristupiti(" in telo, "ACTION ima svoju kopiju odluke"


def test_6_4_2_granica_ostaje_zatvorena():
    """Regresija: 7 izlaznih modula i dalje zovu kapiju."""
    for modul, n in (("routers/email_notif.py", 3), ("routers/sms.py", 2),
                     ("routers/notifications.py", 2), ("routers/viber.py", 1),
                     ("routers/morning_briefing.py", 2),
                     ("routers/whatsapp_notif.py", 2), ("routers/integrations.py", 1)):
        s = _izv(modul)
        assert s.count("_filtriraj_izvrsive(") == n, f"{modul} izgubio kapiju"


@pytest.mark.parametrize("izvor", ["AI_AUTONOMOUS", "HUMAN_DIRECT", "SYSTEM"])
def test_3_unconfirmed_ne_moze_action(izvor):
    assert sme_pokrenuti_obavezu(_r(izvor=izvor), set()) is False
    assert sme_pokrenuti_obavezu(_r(izvor=izvor), {"r-1"}) is True


# ═══════════════════════════════════════════════════════════════════════════
# PART VIII — AUDIT
# ═══════════════════════════════════════════════════════════════════════════

def test_odluka_pise_immutable_audit_i_prijavljuje_neuspeh():
    from shared import rok_potvrda as rp

    async def _none(*a, **k):
        return None

    with patch("shared.audit_immutable.log_action", _none):
        assert asyncio.run(rp.potvrdi_rok("r1", "u1")) is False
        assert asyncio.run(rp.odbij_rok("r1", "u1")) is False


def test_ruta_ne_tvrdi_uspeh_ako_audit_padne():
    """Obe rute odluke moraju prijaviti neuspeh upisa. Treci 503 u fajlu je
    citanje kandidata i meri se odvojeno, pa se ne broji ukupno nego po telu."""
    s = _izv("routers/rok_odluka.py")
    telo_potvrdi = s[s.index("async def potvrdi("):s.index("async def odbij(")]
    telo_odbij = s[s.index("async def odbij("):]
    for ime, telo in (("potvrdi", telo_potvrdi), ("odbij", telo_odbij)):
        assert "status_code=503" in telo, f"`{ime}` ne prijavljuje neuspeh upisa"
        assert "if not await" in telo, f"`{ime}` ne proverava ishod upisa"


# ═══════════════════════════════════════════════════════════════════════════
# VLASNISTVO
# ═══════════════════════════════════════════════════════════════════════════

def test_odluka_je_ogranicena_na_vlasnika():
    s = _izv("routers/rok_odluka.py")
    telo = s[s.index("async def _rok_u_vlasnistvu("):s.index("@router.get")]
    assert '.eq("user_id", uid)' in telo
    assert "404" in telo, "tudji rok mora dati 404, ne 403 (ne otkriva postojanje)"


# ═══════════════════════════════════════════════════════════════════════════
# `odluke()` — JEDINI CITAC ODLUKA, testiran nad laznim Supabase-om
#
# Dodato posle mutacionog prolaza u kome su M4 (fail-OPEN na pad upita) i M5
# (odbijanje procitano kao potvrda) PREZIVELE: cela logika citanja bila je
# pokrivena samo posredno, kroz kanale koji joj prosledjuju gotov skup.
# ═══════════════════════════════════════════════════════════════════════════

class _AuditUpit:
    def __init__(self, redovi):
        self._r = list(redovi)

    def select(self, *a, **k):
        return self

    def eq(self, k, v):
        return _AuditUpit([r for r in self._r if r.get(k) == v])

    def in_(self, k, vs):
        return _AuditUpit([r for r in self._r if r.get(k) in set(vs)])

    def order(self, k, **kw):
        return _AuditUpit(sorted(self._r, key=lambda r: r.get(k, 0)))

    def execute(self):
        class R:
            pass
        r = R()
        r.data = self._r
        return r


def _supa(redovi):
    class S:
        def table(self, t):
            assert t == "audit_immutable"
            return _AuditUpit(redovi)
    return S()


def _zapis(rid, akcija, seq):
    return {"resource_type": "rok", "resource_id": rid, "action": akcija, "seq": seq}


def test_odluke_potvrda_daje_CONFIRMED():
    from shared import rok_potvrda as rp
    with patch("shared.deps._get_supa", lambda: _supa([_zapis("r1", "rok_potvrdjen", 1)])):
        assert rp.odluke(["r1"]) == {"r1": STANJE_POTVRDJEN}


def test_odluke_odbijanje_daje_REJECTED_a_ne_CONFIRMED():
    """M5: ako se odbijanje procita kao potvrda, odbijen rok postaje izvrsiv."""
    from shared import rok_potvrda as rp
    with patch("shared.deps._get_supa", lambda: _supa([_zapis("r1", "rok_odbijen", 1)])):
        m = rp.odluke(["r1"])
    assert m == {"r1": STANJE_ODBIJEN}
    assert sme_pristupiti({"id": "r1"}, m, potrosac=POTROSAC_AKCIJA) is False
    assert sme_pristupiti({"id": "r1"}, m, potrosac=POTROSAC_KLIJENT) is False


def test_odluke_poslednja_pobedjuje_u_oba_smera():
    from shared import rok_potvrda as rp
    with patch("shared.deps._get_supa",
               lambda: _supa([_zapis("r1", "rok_potvrdjen", 1), _zapis("r1", "rok_odbijen", 2)])):
        assert rp.odluke(["r1"]) == {"r1": STANJE_ODBIJEN}
    with patch("shared.deps._get_supa",
               lambda: _supa([_zapis("r1", "rok_odbijen", 1), _zapis("r1", "rok_potvrdjen", 2)])):
        assert rp.odluke(["r1"]) == {"r1": STANJE_POTVRDJEN}


def test_odluke_pad_upita_je_FAIL_CLOSED():
    """M4: fail-open bi svaki rok proglasio potvrdjenim cim baza zakasli."""
    from shared import rok_potvrda as rp

    def _puca():
        raise RuntimeError("audit nedostupan")

    with patch("shared.deps._get_supa", _puca):
        m = rp.odluke(["r1", "r2"])
    assert m == {}
    assert sme_pristupiti({"id": "r1"}, m, potrosac=POTROSAC_KLIJENT) is False
    assert sme_pristupiti({"id": "r1"}, m, potrosac=POTROSAC_AKCIJA) is False


def test_odluke_prazan_ulaz_ne_zove_bazu():
    """Meri se BROJACEM, ne bacanjem izuzetka.

    Prva verzija je dizala `AssertionError` iz laznog `_get_supa` — ali
    `odluke` hvata `Exception` i vraca `{}`, pa je test prolazio i kad je
    zastita uklonjena (mutacija je PREZIVELA). Brojac to vidi."""
    from shared import rok_potvrda as rp
    pozivi = []

    def _broji():
        pozivi.append(1)
        return _supa([])

    with patch("shared.deps._get_supa", _broji):
        assert rp.odluke([]) == {}
        assert rp.odluke(None) == {}
        assert rp.odluke(["", None]) == {}
    assert pozivi == [], "baza je pozvana za prazan ulaz"


def test_potvrdjeni_ids_ne_ukljucuje_odbijene():
    from shared import rok_potvrda as rp
    zapisi = [_zapis("r1", "rok_potvrdjen", 1), _zapis("r2", "rok_odbijen", 2)]
    with patch("shared.deps._get_supa", lambda: _supa(zapisi)):
        assert rp.potvrdjeni_ids(["r1", "r2"]) == {"r1"}
