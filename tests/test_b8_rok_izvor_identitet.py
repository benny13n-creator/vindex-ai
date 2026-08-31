# -*- coding: utf-8 -*-
"""B8 — KANONSKI IZVOR ROKA U GENOME-u I HRONOLOGIJI.

Rok je do sada završavao u `predmet_hronologija` bez ijedne reference na dokument
iz kog potiče — advokat je video „Rok za žalbu: 15 dana" i nije mogao da dođe do
rešenja koje ga je pokrenulo.

Živi dokaz (stvarni Supabase, lažiran samo GPT odgovor) zapisan je u
`SPRINT-B2 — BOJAN WORKFLOW CLOSURE REPORT.md`: 7/7. Ovde je regresiona brava
nad odlukama koje se mogu tiho pokvariti.

Ne uvodi se NOV identitet: koristi se isti `_DOK_PATTERN` i ista `redni_broj`
rezolucija koju A002 već gradi za kontradikcije.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

IZVOR = os.path.join(os.path.dirname(__file__), "..", "routers", "case_dna.py")


def _izvor() -> str:
    with open(IZVOR, encoding="utf-8") as fh:
        return fh.read()


def _telo(ime: str) -> str:
    s = _izvor()
    poc = s.index(f"async def {ime}(")
    ost = s[poc + 10:]
    kraj = len(s)
    for m in ("\nasync def ", "\ndef ", "\n@router"):
        k = ost.find(m)
        if k != -1:
            kraj = min(kraj, poc + 10 + k)
    return s[poc:kraj]


# ═══════════════════════════════════════════════════════════════════════════
# 1. UGOVOR PROIZVOĐAČA — rok mora moći da kaže odakle je
# ═══════════════════════════════════════════════════════════════════════════

def test_shema_rokova_trazi_lokaciju():
    s = _izvor()
    i = s.index('"rokovi_kriticni"')
    odsecak = s[i:i + 400]
    assert '"lokacija"' in odsecak, \
        "rok više ne traži lokaciju — izvor se ne može razrešiti"
    assert "DOK-" in odsecak, "lokacija ne koristi kanonsku DOK-NN konvenciju"


def test_rezolucija_koristi_postojeci_mehanizam_a_ne_nov():
    """Jedan koncept = jedan vlasnik: isti `_DOK_PATTERN` i isti `_po_rednom`
    koje A002 već gradi za kontradikcije."""
    telo = _telo("_extract_genome")
    i = telo.index('result.get("rokovi_kriticni")')
    odsecak = telo[i:i + 500]
    assert "_DOK_PATTERN" in odsecak, "uveden je nov način prepoznavanja DOK-NN"
    assert "_po_rednom" in odsecak, "uvedena je paralelna mapa dokumenata"


def test_rezolucija_je_fail_closed():
    """Bez oznake, nepoznat broj ili više kandidata → `None`. Nikad `_kand[0]`."""
    telo = _telo("_extract_genome")
    i = telo.index('result.get("rokovi_kriticni")')
    odsecak = telo[i:i + 500]
    assert '_r["dokument_id"] = _kand[0] if len(_kand) == 1 else None' in odsecak, \
        "rezolucija roka više nije fail-closed — može pogoditi pogrešan dokument"


def test_lokacija_se_ne_dira():
    """`lokacija` ostaje i prikaz i ulaz — dodaje se SAMO referenca."""
    telo = _telo("_extract_genome")
    i = telo.index('result.get("rokovi_kriticni")')
    odsecak = telo[i:i + 500]
    assert '_r["lokacija"] =' not in odsecak, "rezolucija prepisuje `lokacija`"


# ═══════════════════════════════════════════════════════════════════════════
# 2. HRONOLOGIJA — ime dokumenta se IZVODI, ne prepisuje iz LLM teksta
# ═══════════════════════════════════════════════════════════════════════════

def test_hronologija_izvodi_naziv_iz_razresenog_id_a():
    telo = _telo("_sync_rokovi_to_hronologija")
    assert "_dok_nazivi" in telo, "hronologija ne izvodi naziv iz dokumenta"
    assert '"dokument_naziv": dn' in telo, "hronologija ne upisuje naziv dokumenta"
    assert '_dok_nazivi.get(r.get("dokument_id"))' in telo, \
        "naziv se ne izvodi iz `dokument_id` nego iz nečeg drugog"


def test_hronologija_ne_izmislja_naziv_kad_izvor_nije_razresen():
    telo = _telo("_sync_rokovi_to_hronologija")
    i = telo.index("_dok_naziv =")
    red = telo[i:telo.index("\n", i)]
    assert 'if r.get("dokument_id")' in red, \
        "naziv se dodeljuje i kad `dokument_id` nije razrešen — izmišljena veza"


def test_citanje_dokumenata_je_opsegom_predmeta():
    """Cross-case naziv bi bio tiho curenje između predmeta."""
    telo = _telo("_sync_rokovi_to_hronologija")
    i = telo.index("_dok_nazivi")
    odsecak = telo[i:i + 400]
    assert '.eq("predmet_id", predmet_id)' in odsecak, \
        "dokumenti se čitaju bez opsega predmeta"


def test_pad_citanja_dokumenata_ne_obara_upis_roka():
    """Naziv je prikaz; rok mora ući u hronologiju i bez njega."""
    telo = _telo("_sync_rokovi_to_hronologija")
    i = telo.index("_dok_nazivi")
    odsecak = telo[i:i + 600]
    assert "except Exception" in odsecak, "pad čitanja dokumenata obara ceo sync"


def test_dedup_kljuc_nepromenjen():
    """Dedup po (dogadjaj, datum) ostaje — dodavanje naziva ne sme praviti
    duplikate pri ponovljenom refresh-u."""
    telo = _telo("_sync_rokovi_to_hronologija")
    assert '(dogadjaj, datum) in postojeci' in telo


# ═══════════════════════════════════════════════════════════════════════════
# 3. GRANICA — bez migracije nema `dokument_id` u hronologiji
# ═══════════════════════════════════════════════════════════════════════════

def test_hronologija_ne_upisuje_dokument_id_pre_migracije():
    """`predmet_hronologija.dokument_id` ne postoji u živoj šemi. Upis bi
    obarao svaki sync. Kolona čeka migraciju 126."""
    telo = _telo("_sync_rokovi_to_hronologija")
    i = telo.index('supa.table("predmet_hronologija").insert({')
    odsecak = telo[i:i + 500]
    assert '"dokument_id"' not in odsecak, \
        "upisuje se kolona koja u živoj šemi ne postoji — svaki sync bi pao"
