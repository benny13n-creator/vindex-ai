# -*- coding: utf-8 -*-
"""
IMPLEMENTATION TASK 002A — NAČIN PRONALASKA.

Jedna semantika se menja: `lociraj_tvrdnju` sada prijavljuje KAKO je tvrdnja
pronađena, a `predmet_dokazi.nacin_pronalaska` to skladišti.

KRITIČNA INVARIJANTA koju svi testovi brane:

    nacin == "egzaktan"  =>  tekst[start_offset:end_offset] == proba   (DOSLOVNO)
    nacin == "nije_pronadjen"  =>  start_offset IS NULL i end_offset IS NULL

Za `normalizovan` se NE sme tvrditi da je span doslovno identičan.

Testovi takođe dokazuju IZOLOVANOST promene: `snaga`, `identitet` i grounding
kolone ostaju netaknuti.
"""
import io
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.evidence_write import (  # noqa: E402
    KOLONA_IDENTITET,
    KOLONA_NACIN,
    NACINI,
    NACIN_EGZAKTAN,
    NACIN_NIJE,
    NACIN_NORMALIZOVAN,
    _PROBE_MAX_LEN,
    izracunaj_identitet,
    lociraj_tvrdnju,
    snaga_iz_lokacije,
    upisi_dokaze,
)

from tests.test_impl001_unified_evidence_write import (  # noqa: E402
    DOKUMENT, KORISNIK, PREDMET, FakeSupa,
)


def _proba(t: str) -> str:
    """Ista transformacija koju `lociraj_tvrdnju` primenjuje na tvrdnju."""
    return re.sub(r"\.{2,}$|…$", "", t.strip()).rstrip()[:_PROBE_MAX_LEN]


DOK = "Clan 1. Ugovorna kazna iznosi 500.000 RSD.\n\nClan 2. Ostalo."
T   = "Ugovorna kazna iznosi 500.000 RSD."


# ═══════════════════════════════════════════════════════════════════════════
# A — EGZAKTAN
# ═══════════════════════════════════════════════════════════════════════════

def test_a_egzaktan_i_substring_invarijanta():
    L = lociraj_tvrdnju(DOK, T)
    assert L["nacin"] == NACIN_EGZAKTAN
    assert DOK[L["start_offset"]:L["end_offset"]] == _proba(T)


# ═══════════════════════════════════════════════════════════════════════════
# B — NORMALIZOVAN
# ═══════════════════════════════════════════════════════════════════════════

def test_b_visestruki_razmaci_daju_normalizovan():
    dok = "Clan 1. Ugovorna   kazna   iznosi   500.000   RSD.\n\nClan 2."
    L = lociraj_tvrdnju(dok, T)
    assert L["start_offset"] is not None, "postojeći normalizovani put mora naći span"
    assert L["nacin"] == NACIN_NORMALIZOVAN


def test_b2_razlika_u_velicini_slova_je_normalizovan_a_ne_egzaktan():
    """Pokušaj 1 je case-insensitive (`tekst.lower().find(probe.lower())`).
    Pogodak koji se razlikuje samo po veličini slova NIJE doslovan substring,
    pa po invarijanti mora biti `normalizovan`."""
    dok = "Clan 1. UGOVORNA KAZNA IZNOSI 500.000 RSD.\n\nClan 2."
    L = lociraj_tvrdnju(dok, T)
    assert L["start_offset"] is not None
    assert DOK[0:0] == ""  # sanity
    assert dok[L["start_offset"]:L["end_offset"]] != _proba(T)
    assert L["nacin"] == NACIN_NORMALIZOVAN


# ═══════════════════════════════════════════════════════════════════════════
# C — NIJE PRONAĐEN
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("dok,tv,opis", [
    (DOK, "Ova tvrdnja ne postoji nigde u ovom dokumentu.", "nema poklapanja"),
    ("", T, "prazan dokument"),
    (DOK, "", "prazna tvrdnja"),
    (DOK, "...", "tvrdnja svedena na prazno"),
])
def test_c_nije_pronadjen(dok, tv, opis):
    L = lociraj_tvrdnju(dok, tv)
    assert L["nacin"] == NACIN_NIJE, opis
    assert L["start_offset"] is None and L["end_offset"] is None, opis


# ═══════════════════════════════════════════════════════════════════════════
# D — EGZAKTAN MORA POBEDITI NORMALIZOVAN
# ═══════════════════════════════════════════════════════════════════════════

def test_d_egzaktan_pobedjuje_kad_oba_mogu_naci():
    """Dokument sadrži i doslovnu i razmaknutu varijantu; doslovna je PRVA po
    tekstu, ali test traži da rezultat bude `egzaktan` bez obzira na to."""
    dok = "Uvod. " + T + "\n\nPonavljanje: Ugovorna   kazna   iznosi   500.000   RSD."
    L = lociraj_tvrdnju(dok, T)
    assert L["nacin"] == NACIN_EGZAKTAN
    assert dok[L["start_offset"]:L["end_offset"]] == _proba(T)


# ═══════════════════════════════════════════════════════════════════════════
# E — MUTACIJA IZVORA RUŠI EGZAKTAN
# ═══════════════════════════════════════════════════════════════════════════

def test_e_promena_jednog_karaktera_rusi_egzaktan():
    dok = DOK.replace("500.000", "500.001")
    L = lociraj_tvrdnju(dok, T)
    assert L["nacin"] != NACIN_EGZAKTAN
    if L["start_offset"] is not None:
        assert dok[L["start_offset"]:L["end_offset"]] != _proba(T)


# ═══════════════════════════════════════════════════════════════════════════
# F — NORMALIZOVAN NIJE EGZAKTAN
# ═══════════════════════════════════════════════════════════════════════════

def test_f_normalizovan_nikad_ne_tvrdi_doslovan_span():
    """Za SVAKI slučaj u kome je `nacin == normalizovan`, doslovna jednakost
    NE SME važiti — inače bi klasifikacija bila pogrešna u drugom smeru."""
    varijante = [
        "Clan 1. Ugovorna   kazna   iznosi   500.000   RSD.",
        "Clan 1. UGOVORNA KAZNA IZNOSI 500.000 RSD.",
        "Clan 1. Ugovorna\nkazna iznosi 500.000 RSD.",
    ]
    bar_jedan = False
    for dok in varijante:
        L = lociraj_tvrdnju(dok, T)
        if L["nacin"] == NACIN_NORMALIZOVAN:
            bar_jedan = True
            assert dok[L["start_offset"]:L["end_offset"]] != _proba(T)
    assert bar_jedan, "nijedna varijanta nije dala normalizovan — test ne meri ništa"


# ═══════════════════════════════════════════════════════════════════════════
# G — DETERMINIZAM
# ═══════════════════════════════════════════════════════════════════════════

def test_g_determinizam_25_ponavljanja():
    r = [lociraj_tvrdnju(DOK, T) for _ in range(25)]
    assert len({(x["nacin"], x["start_offset"], x["end_offset"]) for x in r}) == 1


# ═══════════════════════════════════════════════════════════════════════════
# SKUP VREDNOSTI — nema četvrte, nema None
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("dok,tv", [
    (DOK, T),
    ("Clan 1. Ugovorna   kazna   iznosi   500.000   RSD.", T),
    (DOK, "Nepostojeca tvrdnja."),
    ("", ""),
    (DOK, "   "),
])
def test_nacin_je_uvek_jedna_od_tri_vrednosti(dok, tv):
    L = lociraj_tvrdnju(dok, tv)
    assert L["nacin"] in NACINI
    assert L["nacin"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# UPIS — kolona se puni i ne remeti ostala polja
# ═══════════════════════════════════════════════════════════════════════════

def test_upis_skladisti_nacin():
    supa = FakeSupa()
    upisi_dokaze(supa, predmet_id=PREDMET, user_id=KORISNIK,
                 stavke=[{"tvrdnja": T, "dokument_id": DOKUMENT}],
                 izvor_tekst=DOK, proveri_vlasnistvo=False)
    red = supa.dokazi[0]
    assert red[KOLONA_NACIN] == NACIN_EGZAKTAN
    assert red["start_offset"] == DOK.find(_proba(T))


def test_upis_bez_izvora_daje_nije_pronadjen():
    supa = FakeSupa()
    upisi_dokaze(supa, predmet_id=PREDMET, user_id=KORISNIK,
                 stavke=[{"tvrdnja": T}], proveri_vlasnistvo=False)
    red = supa.dokazi[0]
    assert red[KOLONA_NACIN] == NACIN_NIJE
    assert red["start_offset"] is None


def test_nacin_ne_ide_kroz_grounding_kljuc():
    """Ime ključa u rezultatu (`nacin`) i ime kolone (`nacin_pronalaska`) se
    razlikuju — sirovi ključ NE SME završiti u redu."""
    supa = FakeSupa()
    upisi_dokaze(supa, predmet_id=PREDMET, user_id=KORISNIK,
                 stavke=[{"tvrdnja": T, "dokument_id": DOKUMENT}],
                 izvor_tekst=DOK, proveri_vlasnistvo=False)
    assert "nacin" not in supa.dokazi[0]
    assert KOLONA_NACIN in supa.dokazi[0]


# ═══════════════════════════════════════════════════════════════════════════
# IZOLOVANOST — ništa drugo se nije promenilo
# ═══════════════════════════════════════════════════════════════════════════

def test_snaga_nije_promenjena_ni_za_jedan_nacin():
    """Isti primer koji je pre TASK-a 002A davao `jaka` mora i dalje davati
    `jaka` — i za egzaktan i za normalizovan."""
    for dok, ocek in [(DOK, NACIN_EGZAKTAN),
                      ("Clan 1. Ugovorna   kazna   iznosi   500.000   RSD.", NACIN_NORMALIZOVAN)]:
        L = lociraj_tvrdnju(dok, T)
        assert L["nacin"] == ocek
        assert snaga_iz_lokacije(T, L) == "jaka", "TASK 002A ne sme menjati snagu"


def test_snaga_iz_lokacije_ne_cita_nacin():
    import inspect
    izvor = inspect.getsource(snaga_iz_lokacije)
    telo = izvor.split('"""')[-1]
    assert "nacin" not in telo, "DC-005 ne sme zavisiti od načina pronalaska"


def test_identitet_nepromenjen_uvodjenjem_nacina():
    supa = FakeSupa()
    upisi_dokaze(supa, predmet_id=PREDMET, user_id=KORISNIK,
                 stavke=[{"tvrdnja": T, "dokument_id": DOKUMENT}],
                 izvor_tekst=DOK, proveri_vlasnistvo=False)
    assert supa.dokazi[0][KOLONA_IDENTITET] == izracunaj_identitet(PREDMET, T)


def test_grounding_kolone_ostaju_tacno_cetiri():
    from shared.evidence_write import KOLONE_GROUNDING
    assert KOLONE_GROUNDING == ("stranica", "paragraf", "start_offset", "end_offset")


# ═══════════════════════════════════════════════════════════════════════════
# DEGRADACIJA — okruženje bez migracije 117
# ═══════════════════════════════════════════════════════════════════════════

def _fake_bez(kolona):
    class _F(FakeSupa):
        def table(self, naziv):
            t = super().table(naziv)
            if naziv == "predmet_dokazi":
                orig = t.insert
                def insert(redovi):
                    if any(kolona in r for r in redovi):
                        raise RuntimeError('column "%s" does not exist' % kolona)
                    return orig(redovi)
                t.insert = insert
            return t
    return _F()


def test_bez_migracije_117_upis_ne_propada_i_identitet_prezivi():
    """Ključno: ako nedostaje SAMO `nacin_pronalaska`, `identitet` (migracija 116)
    NE SME biti odbačen — degradacija ide kolona po kolona, najnovija prva."""
    supa = _fake_bez(KOLONA_NACIN)
    upisi_dokaze(supa, predmet_id=PREDMET, user_id=KORISNIK,
                 stavke=[{"tvrdnja": T, "dokument_id": DOKUMENT}],
                 izvor_tekst=DOK, proveri_vlasnistvo=False)
    red = supa.dokazi[0]
    assert KOLONA_NACIN not in red
    assert KOLONA_IDENTITET in red, "identitet je odbačen bez potrebe"
    assert red["start_offset"] is not None, "utemeljenje je odbačeno bez potrebe"


def test_migracija_117_postoji_i_ne_radi_backfill():
    put = os.path.join(os.path.dirname(__file__), "..", "migrations",
                       "117_predmet_dokazi_nacin_pronalaska.sql")
    assert os.path.exists(put)
    sirovo = io.open(put, encoding="utf-8").read()
    # Provera se radi nad SAMIM DDL-om, ne nad prozom: zaglavlje migracije
    # nabraja šta NE radi ("ne uvodi UNIQUE, FK, NOT NULL...") pa bi provera nad
    # celim fajlom padala na sopstvenoj dokumentaciji.
    ddl = " ".join(
        red for red in sirovo.splitlines() if red.strip() and not red.strip().startswith("--")
    ).lower()
    assert "add column if not exists nacin_pronalaska" in ddl
    for zabranjeno in ("update public.predmet_dokazi", "delete from", "insert into",
                       "generated always", "not null", "default ", "unique", "references",
                       "create trigger", "create function"):
        assert zabranjeno not in ddl, f"migracija sme samo da doda kolonu, našao: {zabranjeno}"
