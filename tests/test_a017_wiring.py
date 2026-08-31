# -*- coding: utf-8 -*-
"""A017 — V2 KANONSKI WIRING.

ŠTA OVAJ FAJL JESTE, A ŠTA NIJE
================================
Živi dokaz wiring-a izveden je nad stvarnim Supabase RPC-om i zapisan u
`A017 — V2 CANONICAL WIRING REPORT.md` (T1–T6 33/33, failure semantics 23/23,
replay+concurrency+legacy 19/19). Mandat §14 izričito zabranjuje da mock zameni
živi dokaz za paketni RPC, `observation_version`, stale rejection, lifecycle,
C-1 i C-2 — pa se to ovde i ne pokušava.

Ovo JESTE brava nad wiring odlukama koje se mogu tiho pokvariti a da živi RPC i
dalje odgovara uredno:
  - da li V2 opažanje ide PRE upisa `case_dna` (redosled je ceo invariant);
  - da li postoji tačno JEDAN kanonski ulaz u V2 persistence;
  - da li neki put zaobilazi paket i zove pojedinačni RPC;
  - da li se neuspeh V2 upisa može predstaviti kao uspešan refresh;
  - da li kompletnost opažanja može biti tvrđena uprkos odbijenim kandidatima.
"""
import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

IZVOR_DIR = os.path.join(os.path.dirname(__file__), "..")


def _izvor(rel: str) -> str:
    """Čita se IZ FAJLA: `routers.case_dna` i `services.case_evolution` ulaze u
    kružni import kada se uveze izolovano (izmereno u A016.7)."""
    with open(os.path.join(IZVOR_DIR, rel), encoding="utf-8") as fh:
        return fh.read()


def _bez_dokumentacije(izvor: str) -> str:
    """Uklanja modulski docstring i `#` komentare.

    Bez ovoga test meri TEKST umesto KODA: `services/v2_observation.py` u svom
    docstring-u izričito piše da NE zove `v2_persist_contradiction` — pa bi
    naivna pretraga tu rečenicu pročitala kao poziv."""
    import re
    # Redosled je bitan: fajl počinje `# -*- coding -*-` linijom, pa `^"""`
    # ne bi pogodio docstring dok se komentari ne uklone.
    bez_kom = "\n".join(l.split("#")[0] for l in izvor.splitlines())
    return re.sub(r'^"""[\s\S]*?"""', "", bez_kom.lstrip(), count=1)


def _telo(izvor: str, ime: str) -> str:
    """Telo funkcije od `async def <ime>` do sledeće definicije na nultoj koloni."""
    poc = izvor.index(f"async def {ime}(")
    ostatak = izvor[poc + 10:]
    kraj = len(izvor)
    for marker in ("\nasync def ", "\ndef ", "\n@router"):
        k = ostatak.find(marker)
        if k != -1:
            kraj = min(kraj, poc + 10 + k)
    return izvor[poc:kraj]


# ═══════════════════════════════════════════════════════════════════════════
# 1. JEDAN KANONSKI ULAZ (§3)
# ═══════════════════════════════════════════════════════════════════════════

def test_postoji_tacno_jedan_kanonski_ulaz_u_v2_persistence():
    """`services/v2_observation.py::upisi_v2_opazanje` je jedini most iz Genome
    putanje u V2. Dva proizvođača opažanja smeju da ga zovu — ali nijedan ne sme
    da razgovara sa adapterom mimo njega."""
    cd = _bez_dokumentacije(_izvor("routers/case_dna.py"))
    assert "from services.v2_observation import upisi_v2_opazanje" in cd
    assert cd.count("upisi_v2_opazanje(") == 2, \
        "očekivana TAČNO 2 poziva — pozadinski i ručni refresh"
    assert "persist_observation_package" not in cd, \
        "case_dna.py zove adapter direktno, mimo kanonskog ulaza"
    assert "persist_paket" not in cd, \
        "case_dna.py zove predlog-po-predlog put, mimo paketa"


def test_kanonski_ulaz_zove_iskljucivo_paketni_adapter():
    obs = _bez_dokumentacije(_izvor("services/v2_observation.py"))
    assert "persist_observation_package" in obs
    assert "persist_paket(" not in obs, "kanonski ulaz zaobilazi paket"
    assert "v2_persist_contradiction" not in obs, "kanonski ulaz zove pojedinačni RPC"
    assert ".rpc(" not in obs, "kanonski ulaz zove bazu direktno umesto kroz adapter"
    assert ".table(" not in obs, "kanonski ulaz piše u bazu mimo adaptera"


def test_oba_proizvodjaca_opazanja_su_uvezana():
    """Genome opažanje nastaje na dva mesta (mapirano u §1). Ako je uvezano samo
    jedno, drugi put proizvodi `case_dna` bez V2 slike."""
    cd = _izvor("routers/case_dna.py")
    for ime in ("_do_genome_refresh", "_refresh_case_dna_body"):
        assert "upisi_v2_opazanje(" in _telo(cd, ime), f"{ime} nije uvezan u V2"


# ═══════════════════════════════════════════════════════════════════════════
# 2. REDOSLED (§2) — V2 PRE case_dna
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("funkcija", ["_do_genome_refresh", "_refresh_case_dna_body"])
def test_v2_opazanje_ide_pre_upisa_case_dna(funkcija):
    """Ceo invariant je u redosledu. Kad bi V2 išao POSLE, neuspeh paketa bi
    ostavio `case_dna` upisan a V2 sliku praznu — stanje koje §2 zabranjuje."""
    telo = _telo(_izvor("routers/case_dna.py"), funkcija)
    i_v2 = telo.index("upisi_v2_opazanje(")
    i_cd = telo.index('update({"case_dna": genome})')
    assert i_v2 < i_cd, f"{funkcija}: case_dna se upisuje PRE V2 opažanja"


@pytest.mark.parametrize("funkcija", ["_do_genome_refresh", "_refresh_case_dna_body"])
def test_v2_opazanje_ide_pre_svakog_pisca(funkcija):
    """`_sync_rokovi_to_hronologija` i `_save_genome_history` takođe PIŠU."""
    telo = _telo(_izvor("routers/case_dna.py"), funkcija)
    i_v2 = telo.index("upisi_v2_opazanje(")
    for pisac in ("_sync_rokovi_to_hronologija(", "_save_genome_history("):
        assert i_v2 < telo.index(pisac), f"{funkcija}: {pisac} piše pre V2 opažanja"


@pytest.mark.parametrize("funkcija", ["_do_genome_refresh", "_refresh_case_dna_body"])
def test_v2_opazanje_ide_pre_emitovanja_posledica(funkcija):
    telo = _telo(_izvor("routers/case_dna.py"), funkcija)
    assert telo.index("upisi_v2_opazanje(") < telo.index("_emit_genome_event(")


# ═══════════════════════════════════════════════════════════════════════════
# 3. NEUSPEH SE NE SME PREDSTAVITI KAO USPEH (§6)
# ═══════════════════════════════════════════════════════════════════════════

def test_pozadinski_put_ne_hvata_v2_izuzetak_lokalno():
    """Izuzetak mora doći do spoljnog `except`, koji se vraća BEZ ijednog upisa.
    Lokalni `try/except` oko V2 poziva bi značio nastavak sa upisom `case_dna`."""
    telo = _telo(_izvor("routers/case_dna.py"), "_do_genome_refresh")
    poc = telo.index("upisi_v2_opazanje(")
    kraj = telo.index('update({"case_dna": genome})')
    assert "except" not in telo[poc:kraj], \
        "V2 neuspeh se hvata pre upisa case_dna — refresh bi nastavio kao uspešan"


def test_rucni_put_vraca_posten_odgovor_na_v2_neuspeh():
    """Ponovo se koristi POSTOJEĆI `case_dna_persisted: False` obrazac
    (Singular Intelligence, 2026-08-07) — bez četvrtog stanja."""
    telo = _telo(_izvor("routers/case_dna.py"), "_refresh_case_dna_body")
    assert "_v2_ok = False" in telo
    i_ne = telo.index("if not _v2_ok:")
    i_cd = telo.index('update({"case_dna": genome})')
    assert i_ne < i_cd, "provera V2 neuspeha dolazi posle upisa case_dna"
    odsecak = telo[i_ne:i_cd]
    assert '"case_dna_persisted": False' in odsecak
    assert '"case_dna": stari_genome' in odsecak, \
        "vraća se NOVI genome iako nije sačuvan — odgovor bi lagao"


def test_kanonski_ulaz_ne_guta_izuzetke():
    obs = _bez_dokumentacije(_izvor("services/v2_observation.py"))
    telo = obs[obs.index("async def upisi_v2_opazanje("):]
    assert "except" not in telo, "kanonski ulaz guta izuzetak umesto da ga prosledi"


# ═══════════════════════════════════════════════════════════════════════════
# 4. KOMPLETNOST OPAŽANJA (§6 / G6)
# ═══════════════════════════════════════════════════════════════════════════

def test_odbijen_kandidat_skida_tvrdnju_o_kompletnosti():
    """Genome je kontradikciju VIDEO, a mi je nismo mogli izraziti. Tvrditi
    kompletnost tada znači zatvoriti spornu tačku na koju se odbijeni odnosio."""
    obs = _izvor("services/v2_observation.py")
    assert "kompletno = not odbijeni" in obs
    assert "kompletno_opazanje=kompletno" in obs


def test_adapter_kombinuje_kompletnost_konjunkcijom():
    """`and`, ne `or`: kompletnost mora potvrditi SVAKI sloj koji je mogao
    nešto da izgubi."""
    vcp = _izvor("services/v2_contradiction_persistence.py")
    assert "kompletno = bool(kompletno_opazanje) and not pregled" in vcp


def test_kompletnost_se_prenosi_do_baze():
    import services.v2_contradiction_persistence as mod
    assert "kompletno_opazanje" in inspect.signature(
        mod.persist_observation_package).parameters


# ═══════════════════════════════════════════════════════════════════════════
# 5. IDENTITET I LEGACY IZOLACIJA (§8, §9)
# ═══════════════════════════════════════════════════════════════════════════

def test_kanonski_ulaz_ne_izvodi_identitet_iz_lokacija():
    obs = _bez_dokumentacije(_izvor("services/v2_observation.py"))
    for zabranjeno in ("lokacija_1", "lokacija_2", "dedupe_key", "contradiction_identity"):
        assert zabranjeno not in obs, f"kanonski ulaz koristi legacy identitet: {zabranjeno}"


def test_materializer_ostaje_jedini_proizvodjac_kandidata():
    obs = _bez_dokumentacije(_izvor("services/v2_observation.py"))
    assert "materializuj(" in obs
    assert "napravi_katalog(" in obs
    assert "claim_refs" not in obs.split("def upisi_v2_opazanje")[1], \
        "kanonski ulaz sam gradi claim_refs umesto da ih uzme od materializer-a"


def test_delta_ne_bira_kontradikcije_po_poziciji():
    """C-2: `[-N:]` je pretpostavljao da GPT nove dopisuje na kraj."""
    ce = _izvor("services/case_evolution.py")
    assert "kontradikcije_posle[-nove_kontradikcije:]" not in ce
    assert "nove_kontradikcije_za_briefing(" in ce


def test_event_id_stize_do_kanonskog_ulaza():
    telo = _telo(_izvor("routers/case_dna.py"), "_do_genome_refresh")
    poc = telo.index("upisi_v2_opazanje(")
    assert "event_id=event_id" in telo[poc:poc + 300], \
        "event_id se gubi između Genome refresh-a i V2 sloja"


# ═══════════════════════════════════════════════════════════════════════════
# A017.1 — G5: ODBIJENO OPAŽANJE SE NE SME PREDSTAVITI KAO USPEH
#
# Izmereno pre popravke: u 4 od 6 stvarnih kolizija gubitnik trke dobije `55000`,
# ne upiše ništa — a njegova posledica ipak vrati USPEH, jer poredi verziju pre i
# posle, a pobednik ju je u međuvremenu pomerio.
# ═══════════════════════════════════════════════════════════════════════════

def test_odbijeno_opazanje_se_propagira_a_ne_guta():
    telo = _telo(_izvor("routers/case_dna.py"), "_do_genome_refresh")
    assert "except (V2StaleObservation, V2PackageRejected)" in telo, \
        "odbijeno opažanje opet pada u široki `except Exception` i postaje tiho"
    i_odb = telo.index("except (V2StaleObservation, V2PackageRejected)")
    i_sve = telo.index("except Exception as exc:")
    assert i_odb < i_sve, \
        "široki `except` je PRE specifičnog — Python bi uhvatio njime i progutao"
    odsecak = telo[i_odb:i_sve]
    assert "raise" in odsecak, "grana hvata odbijanje ali ga ne prosleđuje dalje"


def test_odbijena_grana_ne_upisuje_nista():
    """Grana sme samo da loguje i podigne — nijedan upis, nikakav `return`."""
    telo = _telo(_izvor("routers/case_dna.py"), "_do_genome_refresh")
    i = telo.index("except (V2StaleObservation, V2PackageRejected)")
    odsecak = _bez_dokumentacije(telo[i:telo.index("except Exception as exc:")])
    for zabranjeno in (".update(", ".insert(", ".upsert(", "_emit_genome_event",
                       "_save_genome_history", "create_proactive_alert", "return"):
        assert zabranjeno not in odsecak, \
            f"grana odbijenog opažanja radi nešto više od podizanja: {zabranjeno}"


def test_genericki_kvarovi_ostaju_na_starom_ugovoru():
    """§11: `RuntimeError`/DB kvar zadržavaju postojeću semantiku (`verzija
    unchanged`). Ovaj sprint ih namerno ne dira."""
    telo = _telo(_izvor("routers/case_dna.py"), "_do_genome_refresh")
    i = telo.index("except Exception as exc:")
    odsecak = telo[i:i + 200]
    assert "raise" not in odsecak, \
        "generički kvarovi sada propagiraju — to menja semantiku van opsega A017.1"


def test_izuzeci_odbijanja_su_uvezeni():
    cd = _bez_dokumentacije(_izvor("routers/case_dna.py"))
    assert "V2StaleObservation" in cd and "V2PackageRejected" in cd


def test_posledica_i_dalje_proverava_verziju():
    """§5: ponovo se koristi POSTOJEĆI mehanizam, ne novi status."""
    ce = _izvor("services/case_evolution.py")
    # Poruka nije provera. Mutacija koja uslov zameni sa `if False:` ostavlja
    # poruku netaknutu — pa se mora meriti SAM USLOV.
    assert "if after_verzija is None or after_verzija == before_verzija:" in ce, \
        "postojeća provera verzije je uklonjena — generički kvarovi bi ostali bez mreže"
    assert "verzija unchanged" in ce


def test_stale_izuzetak_stize_do_pozivaoca():
    """Ponašanje, ne izvor: `_do_genome_refresh` mora PODIĆI, ne vratiti."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    import routers.case_dna as cd
    from services.v2_contradiction_persistence import V2StaleObservation

    supa = MagicMock()

    def _table(ime):
        t = MagicMock()
        if ime == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value \
                .execute.return_value = MagicMock(data={"case_dna": {"verzija": 3}})
        elif ime == "predmet_dokumenti":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=1)
            t.select.return_value.eq.return_value.order.return_value.limit.return_value \
                .execute.return_value = MagicMock(
                    data=[{"id": "d1", "naziv_fajla": "a.pdf", "redni_broj": 1,
                           "tekst_sadrzaj": "tekst", "velicina_kb": 1, "pravni_elementi": None}])
        return t

    supa.table.side_effect = _table

    async def _fake_extract(docs, dokazi=None, ukupno_u_predmetu=None, predmet_id=None):
        return {"snaga_predmeta_procent": 50, "kontradikcije": []}

    with patch("routers.case_dna._get_supa", return_value=supa), \
         patch("routers.case_dna._extract_genome", new=_fake_extract), \
         patch("routers.case_dna._fetch_dokazi_kontekst", new=AsyncMock(return_value=[])), \
         patch("routers.case_dna._compute_analiza_osnov", new=AsyncMock(return_value={})), \
         patch("routers.case_dna.verify_genome", return_value={}), \
         patch("routers.case_dna.upisi_v2_opazanje",
               new=AsyncMock(side_effect=V2StaleObservation("55000 ustajalo opazanje"))), \
         patch("routers.case_dna._sync_rokovi_to_hronologija", new=AsyncMock()) as m_hron, \
         patch("routers.case_dna._save_genome_history", new=AsyncMock()) as m_hist, \
         patch("routers.case_dna._emit_genome_event", new=AsyncMock()) as m_emit:
        with pytest.raises(V2StaleObservation):
            asyncio.run(cd._do_genome_refresh("p1", "u1", None, "upload_trigger"))

    m_hron.assert_not_called()
    m_hist.assert_not_called()
    m_emit.assert_not_called()
