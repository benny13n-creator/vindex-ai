# -*- coding: utf-8 -*-
"""N03 — DATUM IZ DOKUMENTA NIJE PROCESNI ROK.

Adversarijalni dokaz da Vindex ne pretvara nesigurnu informaciju iz dokumenta
u autoritativan procesni rok bez izvora, pravne kvalifikacije i ljudske odluke.

Osam scenarija (nalog N03). Sinteticke cinjenice: 17.03.2025, 25.03.2025,
26.03.2025 — samo kao test podaci, bez ikakve pravne tvrdnje o trajanju roka.
Nijedan test ne ugradjuje zakonsko trajanje roka.

Testovi oznaceni `xfail(strict=True)` su DOKUMENTOVANE praznine koje traze
odluku osnivaca (vidi izvestaj N03) — ne popravljaju se ovde jer bi popravka
bila nova pravno-produktna odluka. `strict` znaci: ako neko promeni ponasanje,
test pada i praznina se mora svesno zatvoriti.

N03-FD ugovor (Workstream A, 2026-10-14): FD1, FD3, FD4, FD5 su ISPRAVLJENI
(xfail uklonjen). FD2 i FD6 ostaju BLOCKED u delu koji trazi identitet tvrdnje
(xfail zadrzan); dokaziv deo je pokriven testovima u sekciji „N03-FD" ispod.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared import rokovi as rokovi_domen
from shared.intake_extract import extract_deadline
from shared.rok_potvrda import (STANJE_NEPOTVRDJEN, STANJE_ODBIJEN,
                                STANJE_POTVRDJEN)

D_17 = "17.03.2025"   # sinteticki: datum donosenja / prijema
D_25 = "25.03.2025"   # sinteticki: datum iz dokumenta A
D_26 = "26.03.2025"   # sinteticki: datum iz dokumenta B
ISO_17, ISO_25, ISO_26 = "2025-03-17", "2025-03-25", "2025-03-26"


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# Smart Intake finalize — harness (isti obrazac kao test_blk1_deadline_safety)
# ═══════════════════════════════════════════════════════════════════════════

def _req():
    from starlette.requests import Request as StarletteRequest
    return StarletteRequest(scope={
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/smart-intake/jobs/job-1/finalize", "app": MagicMock(), "state": MagicMock(),
    })


_UID = "00000000-0000-0000-0000-0000000000a1"


def _supa(hronologija_postoji=False, insert_puca=None):
    """Belezi svaki INSERT u predmet_hronologija u `supa.upisi`."""
    supa = MagicMock()
    supa.upisi = []
    supa.predmeti = []

    def _table(name):
        t = MagicMock()
        if name == "intake_jobs":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "job-1", "status": "completed", "storage_path": "session/xyz",
                "original_filename": "presuda.pdf", "mime_type": "application/pdf",
                "predmet_id": None, "completed_at": None,
            }
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "predmeti":
            def _ins_pred(red):
                supa.predmeti.append(red)
                m = MagicMock()
                m.execute.return_value.data = [{"id": "pred-001"}]
                return m
            t.insert.side_effect = _ins_pred
        elif name == "predmet_dokumenti":
            t.insert.return_value.execute.return_value.data = [{"id": "dok-001"}]
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        elif name == "klijenti":
            t.select.return_value.eq.return_value.ilike.return_value.neq.return_value.limit.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [{"id": "kl-001"}]
        elif name == "predmet_klijenti":
            t.insert.return_value.execute.return_value.data = [{}]
        elif name == "predmet_hronologija":
            def _insert(red):
                if insert_puca is not None:
                    raise insert_puca
                supa.upisi.append(red)
                m = MagicMock()
                m.execute.return_value.data = [{}]
                return m
            t.insert.side_effect = _insert
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = (
                [{"id": "hron-odbijen"}] if hronologija_postoji else []
            )
        elif name == "intake_job_segments":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        return t

    supa.table.side_effect = _table
    return supa


def _ent(entity_type, value, confidence, reviewed=False, corrected=None):
    return {"id": "e-" + entity_type, "entity_type": entity_type, "value": value,
            "confidence": confidence, "reviewed": reviewed, "corrected_value": corrected,
            "extraction_method": "regex"}


def _dok(entities, dok_id="dok-001", tip="judgment"):
    return {"document": {"id": dok_id, "document_type": tip}, "entities": entities, "review": None}


async def _finalize(supa, documents, body=None):
    from routers.smart_intake import FinalizeReq, finalize_intake_job
    patches = (
        patch("routers.smart_intake._get_supa", return_value=supa),
        patch("shared.intake_segments._get_supa", return_value=supa),
        patch("shared.intake_documents.get_job_documents", new=AsyncMock(return_value=documents)),
        patch("shared.intake_worker.worker._download_and_decrypt", new=AsyncMock(return_value=b"raw")),
        patch("uploaded_doc.extractor.extract", return_value=("tekst", False, False, None, None)),
        patch("uploaded_doc.chunker.chunk_document", return_value={"chunks": []}),
        patch("uploaded_doc.ingest.ingest_session", return_value=None),
        patch("uploaded_doc.session.generate_session_id", return_value="sess-001"),
        patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)),
        patch("shared.vector_origin.now_iso", return_value="2025-03-27T00:00:00Z"),
        patch("routers.smart_intake.intake_queue.claim_finalize",
              new=AsyncMock(return_value={"id": "job-1", "finalizing_at": "2025-03-27T00:00:00+00:00"})),
        patch("services.event_bus.emit_durable", new=AsyncMock()),
        patch("shared.audit_immutable.log_action", new=AsyncMock(return_value=None)),
    )
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        return await finalize_intake_job("job-1", _req(), body or FinalizeReq(),
                                         {"user_id": _UID, "email": "advokat@primer.test"})


# ═══════════════════════════════════════════════════════════════════════════
# S1 — KONFLIKTNI DATUMI U DVA DOKUMENTA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_S1_konflikt_upisani_rok_je_samo_AI_kandidat_bez_odluke():
    """Dva dokumenta istog otpremanja tvrde razlicit rok (25. vs 26.03.2025).
    Sta god da se upise, upisuje se kao AI_AUTONOMOUS kandidat — nikad kao
    potvrdjena obaveza — i nijedan kanal ga ne sme pokrenuti."""
    supa = _supa()
    rez = await _finalize(supa, [
        _dok([_ent("deadline", D_25, 0.95)], "dok-A"),
        _dok([_ent("deadline", D_26, 0.95)], "dok-B"),
    ])
    # N03-FD1: svaki dokument daje SVOJ kandidat -- nijedan datum ne pobedjuje.
    assert len(supa.upisi) == 2
    for red in supa.upisi:
        assert red["izvor"] == rokovi_domen.IZVOR_AI_AUTONOMOUS
        assert "stanje" not in red or red["stanje"] != rokovi_domen.STANJE_POTVRDJEN
        # Nema odluke u lancu -> ACTION zabranjen.
        assert not rokovi_domen.sme_pokrenuti_obavezu({**red, "id": "novi"}, set())
    assert rez["rok_dodat"] in (True, False)


@pytest.mark.anyio
async def test_S1_konflikt_rokova_mora_ostati_vidljiv():
    """MUST-PASS 1 — INVARIJANTA: razlicit datum ostaje vidljiv. Ranije je
    finalize uzimao rok SAMO iz prvog dokumenta (`per_doc_meta_maps[0]`), a
    drugi datum je tiho nestajao (N03-FD1, ispravljeno)."""
    supa = _supa()
    rez = await _finalize(supa, [
        _dok([_ent("deadline", D_25, 0.95)], "dok-A"),
        _dok([_ent("deadline", D_26, 0.95)], "dok-B"),
    ])
    upisani = {r["datum_iso"] for r in supa.upisi}
    vidljivo = (upisani == {ISO_25, ISO_26}) or bool(rez.get("rok_preskocen_razlog"))
    assert vidljivo, f"konflikt nevidljiv: upisano={upisani}, razlog={rez.get('rok_preskocen_razlog')}"


# ═══════════════════════════════════════════════════════════════════════════
# S2 — PRIMALAC DOSTAVE PROTUMACEN KAO TUZILAC
# ═══════════════════════════════════════════════════════════════════════════

_DOSTAVNICA = (
    "DOSTAVNICA\nPosiljka: presuda P 123/2024\n"
    "Primalac: Marko Markovic, advokat\n"
    f"Primljeno dana {D_17}. godine, potpis primaoca.\n"
)


def _llm_tvrdi(**polja):
    out = {k: (None, 0.0) for k in ("judge", "plaintiff", "defendant", "court", "law_cited")}
    out.update(polja)
    return AsyncMock(return_value=out)


@pytest.mark.anyio
async def test_S2_primalac_dostave_nije_tuzilac():
    """Model tvrdi da je primalac tuzilac; tekst tu ulogu NIGDE ne dodeljuje.
    Dostava ne utvrdjuje procesnu ulogu -> vrednost se odbacuje."""
    from shared.intake_extract import extract_all_entities
    with patch("shared.intake_extract.extract_free_text_entities",
               new=_llm_tvrdi(plaintiff=("Marko Markovic", 0.93))):
        ent = {e["entity_type"]: e for e in await extract_all_entities(_DOSTAVNICA)}
    assert ent["plaintiff"]["value"] is None and ent["plaintiff"]["confidence"] == 0.0
    # Datum prijema nije rok.
    assert ent["deadline"]["value"] is None


@pytest.mark.anyio
async def test_S2_kontrola_izricito_navedena_uloga_prolazi():
    """Negativna kontrola: kad tekst uloga izricito dodeljuje, ostaje."""
    from shared.intake_extract import extract_all_entities
    tekst = "TUZBA\nTuzilac: Marko Markovic iz Beograda\nprotiv tuzenog Alfa DOO\n"
    with patch("shared.intake_extract.extract_free_text_entities",
               new=_llm_tvrdi(plaintiff=("Marko Markovic", 0.93))):
        ent = {e["entity_type"]: e for e in await extract_all_entities(tekst)}
    assert ent["plaintiff"]["value"] == "Marko Markovic"


@pytest.mark.anyio
async def test_S2_finalize_bez_uloge_ne_pravi_klijenta_iz_primaoca():
    """Bez tuzioca u izvodu, `klijent_strana=plaintiff` ne sme da izmisli
    klijenta iz primaoca dostave."""
    from routers.smart_intake import FinalizeReq
    supa = _supa()
    rez = await _finalize(supa, [_dok([_ent("plaintiff", None, 0.0), _ent("deadline", None, 0.0)], tip="other")],
                          body=FinalizeReq(klijent_strana="plaintiff"))
    assert rez["klijent_dodat"] is False
    assert supa.upisi == []


# ═══════════════════════════════════════════════════════════════════════════
# S3 — "ROK OD 7 DANA" BEZ PROVERENOG PRAVNOG OSNOVA
# ═══════════════════════════════════════════════════════════════════════════

_RESENJE_7 = (
    "RESENJE\nObavezuje se stranka da dostavi dokaz. "
    f"Rok od 7 dana.\nResenje je primljeno dana {D_17}. godine."
)


def test_S3_relativni_izraz_ostaje_izraz_ne_datum():
    vrednost, conf = extract_deadline(_RESENJE_7)
    assert vrednost == "7 dana"
    assert conf < 0.90
    from routers.smart_intake import _deadline_to_iso
    assert _deadline_to_iso(vrednost) is None


@pytest.mark.anyio
async def test_S3_finalize_ne_pravi_rok_iz_relativnog_izraza_i_to_KAZE():
    """Relativni izraz se ne racuna u datum (nema proverenog okidaca ni pravnog
    osnova), ali odsustvo upisa NE SME izgledati kao „dokument nema rok"."""
    supa = _supa()
    rez = await _finalize(supa, [_dok([_ent("deadline", "7 dana", 0.77)])])
    assert supa.upisi == []
    assert rez["rok_dodat"] is False
    assert rez["rok_preskocen_razlog"] == "bez_konkretnog_datuma"


def test_S3_kandidat_lista_ne_racuna_datum_iz_relativnog_izraza():
    """MUST-PASS 4. Legacy lista kandidata (`/api/dokument/rokovi`) je od
    relativnog izraza i AUTOMATSKI pogodjenog datuma dokumenta pravila konkretan
    datum i „Istice za N dana" (N03-FD3, ispravljeno: relativan rok ostaje
    relativan)."""
    from uploaded_doc.deadline_parser import ekstrahuj_rokove
    rel = [r for r in ekstrahuj_rokove(_RESENJE_7, D_17) if r["tip"] == "relativni"]
    assert rel and all(r["konkretan_datum"] is None for r in rel), rel


# ═══════════════════════════════════════════════════════════════════════════
# S4 — DATUM DOSTAVE ZAMENJEN ZA DATUM PRESUDE
# ═══════════════════════════════════════════════════════════════════════════

_PRESUDA = (
    f"Primljeno dana {D_25}.\n"
    "PRESUDA\nOsnovni sud u Beogradu, P 123/2024\n"
    f"Presuda je doneta dana {D_17}. godine.\n"
    f"Presuda je dostavljena punomocniku {D_25}. godine.\n"
)


def test_S4_ni_datum_presude_ni_datum_dostave_nisu_rok():
    assert extract_deadline(_PRESUDA) == (None, 0.0)


def test_S4_datum_dostave_ne_postaje_datum_dokumenta():
    """MUST-PASS 5. `_extract_datum_dokumenta` je uzimao prvo „dana DD.MM.YYYY"
    — ovde pecat prijema — kao datum dokumenta (N03-FD4, ispravljeno)."""
    from uploaded_doc.deadline_parser import _extract_datum_dokumenta
    assert _extract_datum_dokumenta(_PRESUDA) != D_25


# ═══════════════════════════════════════════════════════════════════════════
# S5 — NEPOZNAT / NEMOGUC DATUM
# ═══════════════════════════════════════════════════════════════════════════

def test_S5_nemoguc_kalendarski_datum_nije_ISO_datum():
    from routers.smart_intake import _deadline_to_iso
    assert _deadline_to_iso("31.02.2025") is None
    assert _deadline_to_iso("2025-02-31") is None
    assert _deadline_to_iso(D_25) == ISO_25


@pytest.mark.anyio
async def test_S5_nemoguc_datum_ne_ide_u_hronologiju_i_to_se_KAZE():
    supa = _supa()
    rez = await _finalize(supa, [_dok([_ent("deadline", "31.02.2025", 0.95)])])
    assert supa.upisi == []
    assert rez["rok_dodat"] is False
    assert rez["rok_preskocen_razlog"] == "bez_konkretnog_datuma"


@pytest.mark.anyio
async def test_S5_pad_upisa_roka_nije_odsustvo_roka():
    """Rok je pronadjen i prosao prag, ali upis je pao. Odgovor ne sme biti
    isti kao za dokument bez roka (`rok_preskocen_razlog=None`)."""
    supa = _supa(insert_puca=Exception("db down"))
    rez = await _finalize(supa, [_dok([_ent("deadline", D_25, 0.95)])])
    assert rez["rok_dodat"] is False
    assert rez["rok_preskocen_razlog"] == "upis_nije_uspeo"


@pytest.mark.anyio
async def test_S5_kontrola_dokument_bez_roka_ostaje_bez_razloga():
    """Negativna kontrola: stvarno odsustvo roka i dalje daje `None`."""
    supa = _supa()
    rez = await _finalize(supa, [_dok([_ent("deadline", None, 0.0)])])
    assert rez["rok_dodat"] is False and rez["rok_preskocen_razlog"] is None


# ═══════════════════════════════════════════════════════════════════════════
# S6 — NEPROVEREN CITAT ZAKONSKE ODREDBE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_S6_citat_odredbe_ne_postaje_pravni_osnov_roka():
    """Model izvlaci „clan 999 Zakona X" (neproveren citat) i relativni rok.
    Ni citat ni izraz ne smeju proizvesti rok niti se upisati kao osnov roka."""
    supa = _supa()
    await _finalize(supa, [_dok([
        _ent("law_cited", "clan 999 Zakona o primeru", 0.91),
        _ent("deadline", "15 dana", 0.77),
    ])])
    assert supa.upisi == []


@pytest.mark.anyio
async def test_S6_rok_ne_nosi_tvrdnju_o_vrsti_ni_osnovu():
    """Kad se apsolutni rok upise, naziv tvrdi samo „rok iz dokumenta tipa X" —
    ne vrstu roka i ne zakonski osnov, cak ni kad je citat izvucen."""
    supa = _supa()
    await _finalize(supa, [_dok([
        _ent("law_cited", "clan 999 Zakona o primeru", 0.91),
        _ent("deadline", D_26, 0.95),
    ])])
    assert len(supa.upisi) == 1
    red = supa.upisi[0]
    assert red["dogadjaj"].startswith("Rok iz dokumenta (")
    assert "999" not in red["dogadjaj"] and "Zakon" not in red["dogadjaj"]
    assert red["izvor"] == rokovi_domen.IZVOR_AI_AUTONOMOUS
    assert red["dokument_naziv"] == "presuda.pdf"


# ═══════════════════════════════════════════════════════════════════════════
# Kanonska kapija — AI kandidat != potvrdjena obaveza (S1/S7/S8)
# ═══════════════════════════════════════════════════════════════════════════

def _red(rid, datum=ISO_25, izvor=rokovi_domen.IZVOR_AI_AUTONOMOUS, vaznost="kritičan"):
    return {"id": rid, "predmet_id": "pred-001", "dogadjaj": "Rok iz dokumenta (presuda)",
            "datum_iso": datum, "izvor": izvor, "vaznost": vaznost, "vrsta": "rok"}


@pytest.mark.parametrize("stanje,akcija_sme", [
    (STANJE_NEPOTVRDJEN, False),
    (STANJE_ODBIJEN, False),
    (STANJE_POTVRDJEN, True),
])
@pytest.mark.parametrize("potrosac", [rokovi_domen.POTROSAC_AKCIJA, rokovi_domen.POTROSAC_KLIJENT,
                                      rokovi_domen.POTROSAC_IZVOZ_SPOLJA])
def test_kapija_spoljni_potrosaci_samo_potvrdjeno(stanje, akcija_sme, potrosac):
    mapa = {} if stanje == STANJE_NEPOTVRDJEN else {"r1": stanje}
    assert rokovi_domen.sme_pristupiti(_red("r1"), mapa, potrosac=potrosac) is akcija_sme


def test_kapija_kriticna_vaznost_i_ljudski_izvor_ne_ovlascuju():
    for izvor in rokovi_domen.IZVOR_DOZVOLJENI:
        assert not rokovi_domen.sme_pokrenuti_obavezu(_red("r1", izvor=izvor), set())


def test_kapija_odbijen_ne_ulazi_u_aktivni_danas():
    assert rokovi_domen.je_razresen(_red("r1"), {"r1": STANJE_ODBIJEN})
    assert not rokovi_domen.je_razresen(_red("r1"), {})


# ═══════════════════════════════════════════════════════════════════════════
# S7 — ODBIJEN KANDIDAT SE NE VRACA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_S7_ponovni_finalize_ne_vraca_odbijen_rok():
    """Odbijen rok ostaje u hronologiji (odbijen != obrisan). Ponovna obrada
    istog dokumenta nalazi ga i NE pravi nov, nepotvrdjen red."""
    supa = _supa(hronologija_postoji=True)
    rez = await _finalize(supa, [_dok([_ent("deadline", D_25, 0.95)])])
    assert supa.upisi == []
    assert rez["rok_preskocen_razlog"] == "vec_postoji"


class _HronUpit:
    def __init__(self, baza, tabela):
        self.b, self.t = baza, tabela

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self

    def insert(self, red):
        self.b.upisi.append(red)
        return self

    def execute(self):
        if self.t == "predmet_hronologija":
            return MagicMock(data=list(self.b.hron))
        return MagicMock(data=[])


class _HronBaza:
    def __init__(self, hron):
        self.hron, self.upisi = hron, []

    def table(self, ime):
        return _HronUpit(self, ime)


def test_S7_genome_ponovo_isti_rok_ne_pravi_nov_red():
    """Isti tekst roka i isti datum -> dedup drzi i odbijen red."""
    from routers.case_dna import _sync_rokovi_to_hronologija
    baza = _HronBaza([{"dogadjaj": "Rok za odgovor: na tuzbu", "datum_iso": ISO_26}])
    genome = {"rokovi_kriticni": [{"naziv": "Rok za odgovor", "opis": "na tuzbu",
                                   "datum": ISO_26, "status": "aktivan"}]}
    rokovi_domen._resetuj_sondu()
    try:
        assert asyncio.run(_sync_rokovi_to_hronologija(baza, "pred-001", _UID, genome)) == 0
    finally:
        rokovi_domen._resetuj_sondu()
    assert baza.upisi == []


@pytest.mark.xfail(strict=True, reason="N03-FD2 BLOCKED: automatsko gasenje preformulisanog roka trazi identitet tvrdnje koji ne postoji (resource_id = id reda); bez njega bi to bilo zakljucivanje ekvivalencije iz datuma/teksta — zabranjeno ugovorom")
def test_S7_genome_preformulisan_odbijen_rok_ne_vaskrsava():
    """Advokat je odbio rok 26.03.2025. Sledeci Genome refresh isti datum
    opise drugim recima -> nov red, nov nepotvrdjen kandidat. Odbijanje vazi
    za ID reda, ne za cinjenicu."""
    from routers.case_dna import _sync_rokovi_to_hronologija
    baza = _HronBaza([{"dogadjaj": "Rok za odgovor: na tuzbu", "datum_iso": ISO_26}])
    genome = {"rokovi_kriticni": [{"naziv": "Rok za odgovor", "opis": "na tuzbu tuzioca",
                                   "datum": ISO_26, "status": "aktivan"}]}
    rokovi_domen._resetuj_sondu()
    try:
        asyncio.run(_sync_rokovi_to_hronologija(baza, "pred-001", _UID, genome))
    finally:
        rokovi_domen._resetuj_sondu()
    assert baza.upisi == []


def test_S7_vaskrsli_kandidat_i_dalje_nije_izvrsiv():
    """Granica stete prazine iznad: nov red nema odluku -> ACTION zabranjen."""
    assert not rokovi_domen.sme_pokrenuti_obavezu(_red("novi-red", ISO_26), {"stari-red"})


# ═══════════════════════════════════════════════════════════════════════════
# HTTP rute nad memorijskom bazom (ns005 harness): odluka, Danas, kalendar
# ═══════════════════════════════════════════════════════════════════════════

from tests.ns005_harness import ocisti, pripremi, zaglavlje  # noqa: E402

PA, PB = "pred-A-n03", "pred-B-n03"


def _baza_http():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Predmet A", "status": "aktivan"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "status": "aktivan"}],
        "predmet_hronologija": [
            {"id": "r-kand", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Rok iz dokumenta (presuda)",
             "datum_iso": ISO_17, "vaznost": "važan", "izvor": "AI_AUTONOMOUS", "vrsta": "rok"},
            {"id": "r-odbijen", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Rok iz dokumenta (presuda)",
             "datum_iso": ISO_25, "vaznost": "kritičan", "izvor": "AI_AUTONOMOUS", "vrsta": "rok"},
            {"id": "r-potvrdjen", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Rok za odgovor",
             "datum_iso": ISO_26, "vaznost": "kritičan", "izvor": "AI_AUTONOMOUS", "vrsta": "rok"},
            {"id": "r-B", "user_id": "uid-B", "predmet_id": PB, "dogadjaj": "TAJNI rok B",
             "datum_iso": ISO_25, "vaznost": "kritičan", "izvor": "AI_AUTONOMOUS", "vrsta": "rok"},
        ],
        "rocista": [],
        "audit_immutable": [
            {"seq": 1, "action": "rok_odbijen", "resource_type": "rok", "resource_id": "r-odbijen", "user_id": "uid-A"},
            {"seq": 2, "action": "rok_potvrdjen", "resource_type": "rok", "resource_id": "r-potvrdjen", "user_id": "uid-A"},
        ],
    }


class _Danas2025(date):
    """Zamrznut „danas" — sinteticki datumi su u proslosti stvarnog kalendara,
    a `/api/rokovi/kandidati` ne dozvoljava raspon duzi od 365 dana."""

    @classmethod
    def today(cls):
        return cls(2025, 3, 20)


@pytest.fixture
def http(monkeypatch):
    rokovi_domen._resetuj_sondu()
    import shared.audit_immutable as audit
    pravi = audit.log_action
    k, b = pripremi(monkeypatch, _baza_http())
    monkeypatch.setattr(audit, "log_action", pravi)
    import routers.rok_odluka as ro
    monkeypatch.setattr(ro, "date", _Danas2025)
    yield k, b
    rokovi_domen._resetuj_sondu()
    ocisti()


def _kandidati(k, tok="A"):
    return k.get("/api/rokovi/kandidati", params={"od": "2025-03-01", "dana": 30}, headers=zaglavlje(tok))


def test_HTTP_kandidati_nose_stanje_odluke_i_samo_svoje(http):
    k, _ = http
    r = _kandidati(k)
    assert r.status_code == 200, r.text
    assert "TAJNI" not in r.text
    stanja = {x["id"]: x["stanje_odluke"] for x in r.json()["rokovi"]}
    assert stanja == {"r-kand": STANJE_NEPOTVRDJEN, "r-odbijen": STANJE_ODBIJEN,
                      "r-potvrdjen": STANJE_POTVRDJEN}


def test_HTTP_S5_S7_pad_lanca_odluka_nije_UNCONFIRMED(http):
    """Lanac odluka nije procitan. Ruta NE SME da javi „niko nije odlucio" —
    to bi odbijen rok vratilo u Danas kao nov predlog (vaskrsenje), a
    potvrdjen spustilo u predlog. Pad izvora mora biti pad, ne odsustvo."""
    k, b = http
    b.greske["audit_immutable"] = Exception("lanac nedostupan")
    r = _kandidati(k)
    assert r.status_code == 503, r.text
    assert "rokovi" not in r.json()


def test_HTTP_tudj_rok_ne_moze_biti_potvrdjen_ni_odbijen(http):
    k, b = http
    pre = list(b.tabele["audit_immutable"])
    for akcija in ("potvrdi", "odbij"):
        r = k.post(f"/api/rokovi/r-B/{akcija}", json={}, headers=zaglavlje("A"))
        assert r.status_code == 404 and "TAJNI" not in r.text
    assert b.tabele["audit_immutable"] == pre


def test_HTTP_potvrda_je_auditabilna_i_ne_menja_rok(http):
    k, b = http
    pre = [dict(x) for x in b.tabele["predmet_hronologija"]]
    r = k.post("/api/rokovi/r-kand/potvrdi", json={"napomena": "provereno u spisu"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    zap = [z for z in b.tabele["audit_immutable"] if z.get("resource_id") == "r-kand"]
    assert len(zap) == 1 and zap[0]["action"] == "rok_potvrdjen" and zap[0]["user_id"] == "uid-A"
    assert b.tabele["predmet_hronologija"] == pre


def _ics(k, tok="A"):
    return k.post("/api/kalendar/ics", params={"od": "2025-03-01", "do": "2025-03-31"}, headers=zaglavlje(tok))


def test_HTTP_ics_ne_izvozi_odbijen_rok(http):
    """Odbijen AI kandidat ne sme zavrsiti u spoljnom kalendaru advokata kao
    obaveza. `.ics` je upis u kalendar — isti efekat kao Google sinhronizacija,
    koja vec trazi potvrdu."""
    k, _ = http
    r = _ics(k)
    assert r.status_code == 200, r.text
    telo = r.text
    assert "20250326" in telo                       # potvrdjen: ostaje
    assert "20250325" not in telo                   # odbijen: ne izvozi se
    assert "TAJNI" not in telo


def test_HTTP_ics_pad_lanca_odluka_nije_izvoz_svega(http):
    k, b = http
    b.greske["audit_immutable"] = Exception("lanac nedostupan")
    r = _ics(k)
    assert r.status_code == 503


def test_HTTP_ics_ne_izvozi_nepotvrdjen_AI_kandidat(http):
    """MUST-PASS 6 — nepotvrdjen rok nije spoljna obaveza (N03-FD5, ispravljeno:
    `.ics` sada pita `sme_pristupiti(..., EXPORT_EXTERNAL)`)."""
    k, _ = http
    r = _ics(k)
    assert r.status_code == 200
    assert "20250317" not in r.text


# ═══════════════════════════════════════════════════════════════════════════
# S8 — POTVRDJEN ROK, PA SE IZVOR PROMENI
# ═══════════════════════════════════════════════════════════════════════════

def test_S8_novi_datum_iz_izmenjenog_izvora_je_nov_kandidat_i_oba_su_vidljiva(http):
    """Potvrdjen je 26.03.2025; ispravljen dokument daje 25.03.2025 (nov red).
    Nov red NE nasledjuje potvrdu, a oba ostaju vidljiva advokatu."""
    k, b = http
    b.tabele["predmet_hronologija"].append(
        {"id": "r-novi-izvor", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Rok za odgovor",
         "datum_iso": ISO_25, "vaznost": "kritičan", "izvor": "AI_AUTONOMOUS", "vrsta": "rok"})
    stanja = {x["id"]: x["stanje_odluke"] for x in _kandidati(k).json()["rokovi"]}
    assert stanja["r-novi-izvor"] == STANJE_NEPOTVRDJEN
    assert stanja["r-potvrdjen"] == STANJE_POTVRDJEN


@pytest.mark.xfail(strict=True, reason="N03-FD6 BLOCKED: automatska suspenzija potvrde trazi dokazanu vezu rok->dokument; Smart Intake rok nema dokument_id, Genome dokument_id je model-pripisan i FK ON DELETE SET NULL ga brise pri promeni. Dokaziv deo: upozorenje izvor_uklonjen_posle_potvrde")
def test_S8_potvrda_ne_prezivljava_promenu_izvora(http):
    """Nijedan mehanizam ne veze potvrdu za stanje izvornog dokumenta:
    hronologija je insert-only, invalidacija izvora (migracije 131/137) ne
    dira rokove. Stari potvrdjen rok i dalje pokrece podsetnike."""
    k, b = http
    b.tabele["predmet_hronologija"].append(
        {"id": "r-novi-izvor", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Rok za odgovor",
         "datum_iso": ISO_25, "vaznost": "kritičan", "izvor": "AI_AUTONOMOUS", "vrsta": "rok"})
    from shared.rok_potvrda import potvrdjeni_ids
    assert "r-potvrdjen" not in potvrdjeni_ids(["r-potvrdjen", "r-novi-izvor"])


# ═══════════════════════════════════════════════════════════════════════════
# N03-FD — UGOVOR OSNIVACA (Workstream A, 2026-10-14)
#
# Must-pass 1-10 iz ugovora -> imena testova (vidi i izvestaj):
#   1 test_S1_konflikt_rokova_mora_ostati_vidljiv, test_FD1_*
#   2 test_FD2_isti_datum_drugi_tekst_nije_zakljucena_ista_obaveza
#   3 test_FD2_odbijanje_ne_vaskrsava_kroz_preformulisan_red
#   4 test_S3_kandidat_lista_ne_racuna_datum_iz_relativnog_izraza, test_FD3_*
#   5 test_S4_datum_dostave_ne_postaje_datum_dokumenta, test_FD4_*
#   6 test_HTTP_ics_ne_izvozi_nepotvrdjen_AI_kandidat, test_FD5_*
#   7 test_FD6_istorijska_odluka_se_ne_brise_ni_ne_prepisuje
#   8 test_FD7_*
#   9 test_FD8_*
#  10 test_FD10_*
# ═══════════════════════════════════════════════════════════════════════════

import json as _json
import shutil as _shutil
import subprocess as _subprocess

_KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_NODE = _shutil.which("node")
_nodemark = pytest.mark.skipif(_NODE is None, reason="node nije dostupan")


@pytest.fixture
def sonda_129():
    rokovi_domen._resetuj_sondu()
    yield
    rokovi_domen._resetuj_sondu()


# ── FD1 — razliciti datumi u dokumentima istog otpremanja ───────────────────

@pytest.mark.anyio
async def test_FD1_svaki_dokument_daje_svoj_kandidat_i_signal_razlicitih_datuma(sonda_129):
    supa = _supa()
    rez = await _finalize(supa, [_dok([_ent("deadline", D_25, 0.95)], "dok-A"),
                                 _dok([_ent("deadline", D_26, 0.95)], "dok-B")])
    assert sorted(r["datum_iso"] for r in supa.upisi) == [ISO_25, ISO_26]
    assert rez["rok_dodat"] is True and rez["rokovi_razliciti_datumi"] is True
    assert [(x["dokument_id"], x["datum_iso"], x["dodat"]) for x in rez["rokovi_iz_dokumenata"]] == [
        ("dok-A", ISO_25, True), ("dok-B", ISO_26, True)]
    for red in supa.upisi:
        # Kandidat, ne obaveza: AI izvor, bez upisanog stanja, bez odluke -> nijedan kanal.
        assert red["izvor"] == rokovi_domen.IZVOR_AI_AUTONOMOUS and "stanje" not in red
        assert not rokovi_domen.sme_pokrenuti_obavezu({**red, "id": "x"}, set())


@pytest.mark.anyio
async def test_FD1_redosled_dokumenata_ne_bira_datum(sonda_129):
    a, b = _supa(), _supa()
    await _finalize(a, [_dok([_ent("deadline", D_25, 0.95)], "dok-A"), _dok([_ent("deadline", D_26, 0.95)], "dok-B")])
    await _finalize(b, [_dok([_ent("deadline", D_26, 0.95)], "dok-B"), _dok([_ent("deadline", D_25, 0.95)], "dok-A")])
    assert {r["datum_iso"] for r in a.upisi} == {r["datum_iso"] for r in b.upisi} == {ISO_25, ISO_26}


@pytest.mark.anyio
async def test_FD1_drugi_datum_ispod_praga_nije_upisan_ali_se_kaze(sonda_129):
    supa = _supa()
    rez = await _finalize(supa, [_dok([_ent("deadline", D_25, 0.95)], "dok-A"),
                                 _dok([_ent("deadline", D_26, 0.50)], "dok-B")])
    assert [r["datum_iso"] for r in supa.upisi] == [ISO_25]
    assert rez["rok_dodat"] is True
    assert rez["rok_preskocen_razlog"] == "niska_pouzdanost"          # drugi datum nije tiho odbacen
    assert rez["rokovi_razliciti_datumi"] is True
    assert rez["rokovi_iz_dokumenata"][1] == {"datum_iso": ISO_26, "dodat": False,
                                              "razlog": "niska_pouzdanost", "dokument_id": "dok-B"}


@pytest.mark.anyio
async def test_FD1_isti_datum_isti_tip_je_isti_red_ne_dva(sonda_129):
    """Kontrola: isti predmet + isti datum + isti naziv je POSTOJECE pravilo
    duplikata (BLK-1) — vazi i unutar jednog otpremanja. Ne uvodi se nova
    ekvivalencija; razliciti datumi nisu signalizirani jer ih nema."""
    supa = _supa()
    rez = await _finalize(supa, [_dok([_ent("deadline", D_25, 0.95)], "dok-A"),
                                 _dok([_ent("deadline", D_25, 0.95)], "dok-B")])
    assert [r["datum_iso"] for r in supa.upisi] == [ISO_25]
    assert rez["rokovi_razliciti_datumi"] is False
    assert rez["rokovi_iz_dokumenata"][1]["razlog"] == "vec_postoji"


@pytest.mark.anyio
async def test_FD1_isti_datum_razlicit_tip_dokumenta_su_dva_kandidata(sonda_129):
    """Isti datum u RAZLICITIM dokumentima nije dokaz iste obaveze -> dva reda."""
    supa = _supa()
    await _finalize(supa, [_dok([_ent("deadline", D_25, 0.95)], "dok-A", tip="judgment"),
                           _dok([_ent("deadline", D_25, 0.95)], "dok-B", tip="appeal")])
    assert sorted(r["dogadjaj"] for r in supa.upisi) == ["Rok iz dokumenta (presuda)", "Rok iz dokumenta (žalba)"]


@pytest.mark.anyio
async def test_FD1_jedan_dokument_odgovor_kao_ranije(sonda_129):
    supa = _supa()
    rez = await _finalize(supa, [_dok([_ent("deadline", D_25, 0.95)])])
    assert rez["rok_dodat"] is True and rez["rok_preskocen_razlog"] is None
    assert rez["rokovi_razliciti_datumi"] is False and len(rez["rokovi_iz_dokumenata"]) == 1


# ── FD2 — preformulisan rok posle odbijanja ─────────────────────────────────

def _dodaj(b, rid, datum, dogadjaj="Rok za odgovor", izvor="AI_AUTONOMOUS", korisnik="uid-A", predmet=PA, vrsta="rok"):
    b.tabele["predmet_hronologija"].append(
        {"id": rid, "user_id": korisnik, "predmet_id": predmet, "dogadjaj": dogadjaj,
         "datum_iso": datum, "vaznost": "kritičan", "izvor": izvor, "vrsta": vrsta})


def test_FD2_isti_datum_drugi_tekst_nije_zakljucena_ista_obaveza(http):
    """MUST-PASS 2: odbijen je r-odbijen (25.03.2025). Nov red istog datuma i
    drugog teksta NIJE ni sakriven (to bi bila ekvivalencija izvedena iz datuma)
    ni oznacen kao odbijen — ostaje zaseban, vidljiv, nepotvrdjen kandidat."""
    k, b = http
    _dodaj(b, "r-preformulisan", ISO_25, "Rok iz dokumenta (presuda): odgovor na tuzbu")
    stanja = {x["id"]: x["stanje_odluke"] for x in _kandidati(k).json()["rokovi"]}
    assert stanja["r-odbijen"] == STANJE_ODBIJEN
    assert stanja["r-preformulisan"] == STANJE_NEPOTVRDJEN


def test_FD2_odbijanje_ne_vaskrsava_kroz_preformulisan_red(http):
    """MUST-PASS 3: nijedan od dva reda ne dobija ovlascenje — ni odbijen (njegova
    odluka ostaje), ni nov (ne nasledjuje nista). Ni .ics ni akcija."""
    k, b = http
    _dodaj(b, "r-preformulisan", ISO_25, "Rok iz dokumenta (presuda): odgovor na tuzbu")
    assert "20250325" not in _ics(k).text
    from shared.rok_potvrda import odluke, potvrdjeni_ids
    assert odluke(["r-odbijen", "r-preformulisan"]) == {"r-odbijen": STANJE_ODBIJEN}
    assert potvrdjeni_ids(["r-odbijen", "r-preformulisan"]) == set()


def test_FD2_genome_preformulisan_je_nov_kandidat_bez_nasledjene_odluke():
    from routers.case_dna import _sync_rokovi_to_hronologija
    baza = _HronBaza([{"dogadjaj": "Rok za odgovor: na tuzbu", "datum_iso": ISO_26}])
    genome = {"rokovi_kriticni": [{"naziv": "Rok za odgovor", "opis": "na tuzbu tuzioca",
                                   "datum": ISO_26, "status": "aktivan"}]}
    rokovi_domen._resetuj_sondu()
    try:
        asyncio.run(_sync_rokovi_to_hronologija(baza, "pred-001", _UID, genome))
    finally:
        rokovi_domen._resetuj_sondu()
    assert len(baza.upisi) == 1
    nov = baza.upisi[0]
    assert nov["izvor"] == rokovi_domen.IZVOR_AI_AUTONOMOUS and "stanje" not in nov
    assert not rokovi_domen.sme_pokrenuti_obavezu({**nov, "id": "novi-red"}, {"stari-red"})


# ── FD3 — relativan rok ostaje relativan ────────────────────────────────────

def test_FD3_ni_korisnikov_datum_dokumenta_ne_pokrece_racun():
    from uploaded_doc.deadline_parser import RACUN_IZOSTAVLJEN_RELATIVNI, ekstrahuj_rokove
    tekst = ("Zalba se podnosi u roku od 15 dana. Obaveza se izvrsava u roku od 2 meseca. "
             "Placanje: rok od 1 mesec. Narednog radnog dana se dostavlja dokaz.")
    rel = [r for r in ekstrahuj_rokove(tekst, D_17) if r["tip"] == "relativni"]
    assert len(rel) >= 3
    for r in rel:
        assert r["konkretan_datum"] is None and r["dana_do_roka"] is None and r["istekao"] is False
        assert r["racun_izostavljen"] == RACUN_IZOSTAVLJEN_RELATIVNI


def test_FD3_nema_pravila_mesec_je_30_dana():
    import uploaded_doc.deadline_parser as dp
    assert not hasattr(dp, "_parse_trajanje_dana")


def test_FD3_kontrola_apsolutni_datum_i_dalje_ima_odbrojavanje():
    from uploaded_doc.deadline_parser import ekstrahuj_rokove
    aps = [r for r in ekstrahuj_rokove(f"Rok za zalbu istice {D_25}.") if r["tip"] == "apsolutni"]
    assert aps and aps[0]["konkretan_datum"] == D_25 and isinstance(aps[0]["dana_do_roka"], int)
    assert "racun_izostavljen" not in aps[0]


# ── FD4 — datum prijema/dostave nije datum dokumenta ────────────────────────

def test_FD4_jedini_datum_je_pecat_prijema_rezultat_nepoznat():
    from uploaded_doc.deadline_parser import _extract_datum_dokumenta
    assert _extract_datum_dokumenta(f"Primljeno dana {D_25}.\nRESENJE\nObavezuje se stranka.") is None
    assert _extract_datum_dokumenta(f"Dostavnica: uruceno {D_25}\nRESENJE") is None


def test_FD4_cirilicni_pecat_prijema_se_preskace():
    from uploaded_doc.deadline_parser import _extract_datum_dokumenta
    assert _extract_datum_dokumenta(f"Примљено {D_25}\nРЕШЕЊЕ\nБеоград, {D_17}") == D_17


def test_FD4_kontrola_datum_donosenja_i_mesto_datum():
    from uploaded_doc.deadline_parser import _extract_datum_dokumenta
    assert _extract_datum_dokumenta(f"Beograd, {D_17}\nPRESUDA") == D_17
    assert _extract_datum_dokumenta(f"Zapisnik sastavljen dana {D_17}.") == D_17


def test_FD4_datum_dostave_nije_rok_ni_u_smart_intake():
    """Datum dostave moze biti cinjenica, ali nikad rok iz dokumenta."""
    assert extract_deadline(f"RESENJE\nResenje je dostavljeno dana {D_25}.\n") == (None, 0.0)


# ── FD5 — spoljni izvoz samo uz ljudsku potvrdu ─────────────────────────────

def _potvrdi_u_lancu(b, rid, korisnik="uid-A", akcija="rok_potvrdjen", vreme=None):
    red = {"seq": 100 + len(b.tabele["audit_immutable"]), "action": akcija, "resource_type": "rok",
           "resource_id": rid, "user_id": korisnik}
    if vreme:
        red["created_at"] = vreme
    b.tabele["audit_immutable"].append(red)


def test_FD5_rucni_rok_bez_potvrde_ne_ide_u_ics(http):
    k, b = http
    _dodaj(b, "r-rucni", "2025-03-18", "Rok za uplatu takse", izvor="HUMAN_DIRECT")
    _dodaj(b, "r-nedeklarisan", "2025-03-19", "Rok bez vrste", izvor="HUMAN_DIRECT", vrsta=None)
    telo = _ics(k).text
    assert "20250318" not in telo and "20250319" not in telo


def test_FD5_rucni_rok_posle_potvrde_ide_u_ics(http):
    k, b = http
    _dodaj(b, "r-rucni", "2025-03-18", "Rok za uplatu takse", izvor="HUMAN_DIRECT")
    assert k.post("/api/rokovi/r-rucni/potvrdi", json={}, headers=zaglavlje("A")).status_code == 200
    assert "20250318" in _ics(k).text


def test_FD5_odbijanje_posle_potvrde_gasi_izvoz(http):
    k, b = http
    assert k.post("/api/rokovi/r-potvrdjen/odbij", json={}, headers=zaglavlje("A")).status_code == 200
    r = _ics(k)
    assert "20250326" not in r.text


def test_FD5_rociste_zadrzava_izvoz_i_nije_rok(http):
    k, b = http
    b.tabele["rocista"].append({"id": "roc-A", "user_id": "uid-A", "predmet_id": PA, "datum": "2025-03-21",
                                "status": "zakazano", "sud": "Osnovni sud u Beogradu"})
    b.tabele["rocista"].append({"id": "roc-B", "user_id": "uid-B", "predmet_id": PB, "datum": "2025-03-22",
                                "status": "zakazano", "sud": "TAJNI sud B"})
    telo = _ics(k).text
    assert "20250321" in telo and "20250322" not in telo and "TAJNI" not in telo
    ev = k.get("/api/kalendar/pregled", params={"od": "2025-03-01", "do": "2025-03-31"}, headers=zaglavlje("A")).json()
    roc = [e for e in ev["dogadjaji"] if e["tip"] == "rociste"]
    assert len(roc) == 1 and "stanje_odluke" not in roc[0]["detalji"]


def test_FD5_samo_rocista_bez_potvrdjenih_rokova_i_dalje_izvozi(http):
    k, b = http
    b.tabele["audit_immutable"] = []
    b.tabele["rocista"].append({"id": "roc-A", "user_id": "uid-A", "predmet_id": PA, "datum": "2025-03-21",
                                "status": "zakazano", "sud": "Osnovni sud"})
    r = _ics(k)
    assert r.status_code == 200 and "20250321" in r.text and "20250326" not in r.text


def test_FD5_bez_rocista_i_potvrdjenih_rokova_404_kaze_zasto(http):
    k, b = http
    b.tabele["audit_immutable"] = []
    r = _ics(k)
    assert r.status_code == 404 and "Nepotvrđeni rokovi se ne izvoze" in r.json()["detail"]


def test_FD5_pregled_je_interni_vidi_sve_sa_stanjem(http):
    k, _ = http
    r = k.get("/api/kalendar/pregled", params={"od": "2025-03-01", "do": "2025-03-31"}, headers=zaglavlje("A"))
    assert r.status_code == 200 and "TAJNI" not in r.text
    j = r.json()
    stanja = {e["detalji"]["id"]: e["detalji"]["stanje_odluke"] for e in j["dogadjaji"] if e["tip"] != "rociste"}
    assert stanja == {"r-kand": STANJE_NEPOTVRDJEN, "r-odbijen": STANJE_ODBIJEN, "r-potvrdjen": STANJE_POTVRDJEN}
    assert j["odluke_dostupne"] is True and j["degraded_sources"] == []


@pytest.mark.parametrize("izvor", list(rokovi_domen.IZVOR_DOZVOLJENI))
@pytest.mark.parametrize("vaznost", list(rokovi_domen.VAZNOST_DOZVOLJENE))
def test_FD5_nijedan_izvor_ni_vaznost_ne_izvozi_bez_potvrde(izvor, vaznost):
    red = _red("r1", izvor=izvor, vaznost=vaznost)
    for potrosac in (rokovi_domen.POTROSAC_IZVOZ_SPOLJA, rokovi_domen.POTROSAC_AKCIJA, rokovi_domen.POTROSAC_KLIJENT):
        assert not rokovi_domen.sme_pristupiti(red, {}, potrosac=potrosac)
        assert not rokovi_domen.sme_pristupiti(red, {"r1": "UNKNOWN"}, potrosac=potrosac)
    assert rokovi_domen.sme_pristupiti(red, {}, potrosac=rokovi_domen.POTROSAC_INTERNI)


def test_FD5_rok_bez_identiteta_ne_ide_napolje():
    assert not rokovi_domen.sme_pristupiti({"id": None}, {}, potrosac=rokovi_domen.POTROSAC_IZVOZ_SPOLJA)


# ── FD6 — promena izvora posle potvrde ──────────────────────────────────────

_T_POTVRDE, _T_PRE, _T_POSLE = "2025-03-20T10:00:00+00:00", "2025-03-19T10:00:00+00:00", "2025-03-21T10:00:00+00:00"


def _uklonjen_dokument(b, vreme, predmet=PA, tip="dokument"):
    b.tabele.setdefault("events", []).append(
        {"id": "ev-" + vreme + predmet + tip, "event_type": "SourceInvalidated", "user_id": "uid-A",
         "predmet_id": predmet, "created_at": vreme, "payload": {"source_type": tip, "source_id": "dok-1"}})


def _vremena_potvrde(b, vreme=_T_POTVRDE):
    for z in b.tabele["audit_immutable"]:
        z["created_at"] = vreme


def _upozorenja(k):
    j = _kandidati(k).json()
    return {x["id"]: x["izvor_uklonjen_posle_potvrde"] for x in j["rokovi"]}, j


def test_FD6_uklonjen_dokument_posle_potvrde_daje_upozorenje_bez_opoziva(http):
    k, b = http
    _vremena_potvrde(b)
    _uklonjen_dokument(b, _T_POSLE)
    upoz, j = _upozorenja(k)
    assert upoz["r-potvrdjen"] is True                         # samo potvrdjen rok
    assert upoz["r-kand"] is False and upoz["r-odbijen"] is False
    assert j["provera_izvora_dostupna"] is True
    # Upozorenje NIJE opoziv: odluka ostaje, politika je ista (BLOCKED deo).
    stanja = {x["id"]: x["stanje_odluke"] for x in j["rokovi"]}
    assert stanja["r-potvrdjen"] == STANJE_POTVRDJEN
    assert "20250326" in _ics(k).text


def test_FD6_ponovna_potvrda_gasi_upozorenje(http):
    k, b = http
    _vremena_potvrde(b)
    _uklonjen_dokument(b, _T_POSLE)
    _potvrdi_u_lancu(b, "r-potvrdjen", vreme="2025-03-22T10:00:00+00:00")
    upoz, _ = _upozorenja(k)
    assert upoz["r-potvrdjen"] is False


def test_FD6_uklanjanje_pre_potvrde_ili_drugog_izvora_ne_upozorava(http):
    k, b = http
    _vremena_potvrde(b)
    _uklonjen_dokument(b, _T_PRE)                               # pre potvrde: advokat je vec video stanje
    _uklonjen_dokument(b, _T_POSLE, tip="dokaz")                # dokaz nije dokument iz kog je rok
    _uklonjen_dokument(b, _T_POSLE, predmet=PB)                 # tudj predmet
    upoz, _ = _upozorenja(k)
    assert upoz["r-potvrdjen"] is False


def test_FD6_pad_provere_izvora_ne_obara_pregled_rokova(http):
    k, b = http
    b.greske["events"] = Exception("events nedostupan")
    r = _kandidati(k)
    assert r.status_code == 200
    assert r.json()["provera_izvora_dostupna"] is False
    assert {x["id"]: x["stanje_odluke"] for x in r.json()["rokovi"]}["r-potvrdjen"] == STANJE_POTVRDJEN


def test_FD6_istorijska_odluka_se_ne_brise_ni_ne_prepisuje(http):
    """MUST-PASS 7: nov kandidat iz izmenjenog izvora, uklanjanje dokumenta i nove
    odluke samo DODAJU zapise; nijedna ranija odluka nije obrisana ni izmenjena,
    a hronologija se ne menja (odbijen != obrisan)."""
    k, b = http
    pre = [dict(z) for z in b.tabele["audit_immutable"]]
    hron_pre = [dict(h) for h in b.tabele["predmet_hronologija"]]
    _dodaj(b, "r-novi-izvor", ISO_25)
    _uklonjen_dokument(b, _T_POSLE)
    for rid, akcija in (("r-novi-izvor", "odbij"), ("r-potvrdjen", "odbij"), ("r-potvrdjen", "potvrdi")):
        assert k.post(f"/api/rokovi/{rid}/{akcija}", json={}, headers=zaglavlje("A")).status_code == 200
    _kandidati(k)
    _ics(k)
    posle = b.tabele["audit_immutable"]
    assert posle[:len(pre)] == pre and len(posle) == len(pre) + 3
    assert b.tabele["predmet_hronologija"][:len(hron_pre)] == hron_pre
    assert not [z for z in b.dnevnik if z["tabela"] in ("audit_immutable", "predmet_hronologija")
                and z["radnja"] in ("update", "upsert", "delete")]


# ── FD7 — Smart Intake kandidat ulazi u ljudski pregled ─────────────────────

@pytest.mark.anyio
async def test_FD7_smart_intake_rok_izjavljuje_vrstu_bez_stanja(sonda_129):
    supa = _supa()
    await _finalize(supa, [_dok([_ent("deadline", D_25, 0.95)])])
    assert len(supa.upisi) == 1
    red = supa.upisi[0]
    assert red["vrsta"] == rokovi_domen.VRSTA_ROK                 # pre: kljuc nije postojao
    assert "stanje" not in red                                     # nema auto-potvrde
    assert red["izvor"] == rokovi_domen.IZVOR_AI_AUTONOMOUS and red["dokument_naziv"] == "presuda.pdf"


@pytest.mark.anyio
async def test_FD7_pre_migracije_129_upis_radi_bez_vrste(monkeypatch, sonda_129):
    monkeypatch.setattr(rokovi_domen, "_KOLONE_129", False)
    supa = _supa()
    rez = await _finalize(supa, [_dok([_ent("deadline", D_25, 0.95)])])
    assert rez["rok_dodat"] is True and len(supa.upisi) == 1 and "vrsta" not in supa.upisi[0]


def _danas_sastavi(kand, kal):
    skripta = (
        "const fs=require('fs'); globalThis.window=globalThis;"
        f"eval(fs.readFileSync({_json.dumps(os.path.join(_KOREN, 'frontend-v2-ng', 'src', 'danas.js'))},'utf8'));"
        f"const x=window.VxDanas._sastavi({_json.dumps(kand)},{_json.dumps(kal)},null);"
        "process.stdout.write(JSON.stringify(x));")
    p = _subprocess.run([_NODE, "-e", skripta], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return _json.loads(p.stdout)


@_nodemark
@pytest.mark.anyio
async def test_FD7_smart_intake_kandidat_je_predlog_u_V2_danas(sonda_129):
    """Red TACNO onakav kakav Smart Intake upisuje (uhvacen iz finalize-a) ->
    `/api/rokovi/kandidati` oblik -> V2 Danas: predlog sa „Potvrdi/Odbij", nikad
    obaveza. Pre ispravke je padao u `neizjavljeno` (nevidljiv)."""
    supa = _supa()
    danas = date.today().isoformat()
    await _finalize(supa, [_dok([_ent("deadline", danas, 0.95)])])
    red = {**supa.upisi[0], "id": "si-1", "stanje_odluke": STANJE_NEPOTVRDJEN}
    x = _danas_sastavi({"rokovi": [red]}, {"dogadjaji": []})
    assert [p["id"] for p in x["predlozi"]] == ["si-1"]
    assert x["grupe"] == [] and x["neizjavljeno"] == 0
    bez_vrste = {k2: v for k2, v in red.items() if k2 != "vrsta"}
    assert _danas_sastavi({"rokovi": [bez_vrste]}, {"dogadjaji": []})["neizjavljeno"] == 1   # stari kvar


@pytest.mark.anyio
async def test_FD7_smart_intake_kandidat_u_kandidatima_i_spisu(http, sonda_129):
    k, b = http
    supa = _supa()
    await _finalize(supa, [_dok([_ent("deadline", D_17, 0.95)])])
    b.tabele["predmet_hronologija"].append({**supa.upisi[0], "id": "si-1", "predmet_id": PA, "user_id": "uid-A"})
    stanja = {x["id"]: x["stanje_odluke"] for x in _kandidati(k).json()["rokovi"]}
    assert stanja["si-1"] == STANJE_NEPOTVRDJEN
    spis = k.get(f"/api/predmeti/{PA}", headers=zaglavlje("A")).json()
    h = next(x for x in spis["hronologija"] if x["id"] == "si-1")
    assert h["stanje_odluke"] == STANJE_NEPOTVRDJEN
    assert "20250317" not in _ics(k).text                          # i dalje nije spoljna obaveza


# ── FD8 — neprocitan lanac odluka nije UNCONFIRMED ──────────────────────────

def test_FD8_pregled_pad_lanca_daje_UNKNOWN_i_ne_gasi_kalendar(http):
    k, b = http
    b.tabele["rocista"].append({"id": "roc-A", "user_id": "uid-A", "predmet_id": PA, "datum": "2025-03-21",
                                "status": "zakazano", "sud": "Osnovni sud"})
    b.greske["audit_immutable"] = Exception("lanac nedostupan")
    r = k.get("/api/kalendar/pregled", params={"od": "2025-03-01", "do": "2025-03-31"}, headers=zaglavlje("A"))
    assert r.status_code == 200
    j = r.json()
    assert j["odluke_dostupne"] is False
    stanja = {e["detalji"]["stanje_odluke"] for e in j["dogadjaji"] if e["tip"] != "rociste"}
    assert stanja == {"UNKNOWN"}
    assert [e["detalji"]["id"] for e in j["dogadjaji"] if e["tip"] == "rociste"] == ["roc-A"]


def test_FD8_spis_predmeta_pad_lanca_daje_UNKNOWN_a_ostatak_ostaje(http):
    k, b = http
    ok = k.get(f"/api/predmeti/{PA}", headers=zaglavlje("A")).json()
    assert ok["odluke_o_rokovima_dostupne"] is True
    assert {h["id"]: h["stanje_odluke"] for h in ok["hronologija"]} == {
        "r-kand": STANJE_NEPOTVRDJEN, "r-odbijen": STANJE_ODBIJEN, "r-potvrdjen": STANJE_POTVRDJEN}
    b.greske["audit_immutable"] = Exception("lanac nedostupan")
    r = k.get(f"/api/predmeti/{PA}", headers=zaglavlje("A"))
    assert r.status_code == 200
    j = r.json()
    assert j["odluke_o_rokovima_dostupne"] is False
    assert {h["id"]: h["stanje_odluke"] for h in j["hronologija"]} == {
        "r-kand": "UNKNOWN", "r-odbijen": "UNKNOWN", "r-potvrdjen": "UNKNOWN"}
    assert j["predmet"]["id"] == PA and isinstance(j["dokumenti"], list)


def test_FD8_odgovor_posle_odluke_ne_izmislja_UNCONFIRMED(http, monkeypatch):
    k, b = http
    import routers.rok_odluka as ro
    pravi = ro.odluke

    def _pada(ids, strogo=False):
        if strogo:
            raise RuntimeError("lanac nedostupan")
        return pravi(ids, strogo)
    monkeypatch.setattr(ro, "odluke", _pada)
    for akcija in ("potvrdi", "odbij"):
        r = k.post(f"/api/rokovi/r-kand/{akcija}", json={}, headers=zaglavlje("A"))
        assert r.status_code == 200, r.text
        assert r.json()["stanje_odluke"] == "UNKNOWN" and r.json()["odluka_zabelezena"] is True
    assert [z["action"] for z in b.tabele["audit_immutable"] if z["resource_id"] == "r-kand"] == [
        "rok_potvrdjen", "rok_odbijen"]


def test_FD8_odgovor_posle_odluke_kontrola(http):
    k, _ = http
    r = k.post("/api/rokovi/r-kand/potvrdi", json={}, headers=zaglavlje("A"))
    assert r.json()["stanje_odluke"] == STANJE_POTVRDJEN


@_nodemark
def test_FD8_v2_dosije_nepoznato_nije_ni_obaveza_ni_prazno():
    v2 = os.path.join(_KOREN, "v2").replace("\\", "/")
    redovi = [{"id": "1", "dogadjaj": "Rok", "datum_iso": "2026-09-10", "vrsta": "rok", "stanje_odluke": "UNKNOWN"},
              {"id": "2", "dogadjaj": "Rok", "datum_iso": "2026-09-11", "vrsta": "rok", "stanje_odluke": "UNKNOWN",
               "stanje": "izvrsen"},
              # Kolona `kandidat` NE sme da pretvori nepoznato stanje odluke u „Za proveru".
              {"id": "3", "dogadjaj": "Rok", "datum_iso": "2026-09-12", "vrsta": "rok", "stanje_odluke": "UNKNOWN",
               "stanje": "kandidat"}]
    skripta = (f'import * as O from "file:///{v2}/domain/dosije.js";'
               f"const r=O.uRokove({_json.dumps(redovi)}, new Date(2026,8,5));"
               "process.stdout.write(JSON.stringify({o:r.obaveze.length,p:r.zaProveru.length,n:r.nepoznato.map(x=>x.id),z:r.razreseni}));")
    p = _subprocess.run([_NODE, "--input-type=module", "-e", skripta], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    assert _json.loads(p.stdout) == {"o": 0, "p": 0, "n": ["1", "3"], "z": 1}


# ── FD10 — izolacija kancelarija u svakoj dodirnutoj putanji ────────────────

def test_FD10_tudja_potvrda_ne_cini_moj_rok_izvrsivim(http):
    k, b = http
    pre = list(b.tabele["audit_immutable"])
    for akcija in ("potvrdi", "odbij"):
        r = k.post(f"/api/rokovi/r-kand/{akcija}", json={}, headers=zaglavlje("B"))
        assert r.status_code == 404 and "Rok iz dokumenta" not in r.text
    assert b.tabele["audit_immutable"] == pre
    assert "20250317" not in _ics(k).text


def test_FD10_pregled_ics_kandidati_spis_ne_otkrivaju_tudje(http):
    k, b = http
    _potvrdi_u_lancu(b, "r-B", korisnik="uid-B")
    _uklonjen_dokument(b, _T_POSLE, predmet=PB)
    for r in (k.get("/api/kalendar/pregled", params={"od": "2025-03-01", "do": "2025-03-31"}, headers=zaglavlje("A")),
              _ics(k), _kandidati(k), k.get(f"/api/predmeti/{PA}", headers=zaglavlje("A"))):
        assert "TAJNI" not in r.text and "r-B" not in r.text
    assert k.get(f"/api/predmeti/{PB}", headers=zaglavlje("A")).status_code == 404
    # B vidi SVOJ potvrdjen rok spolja; A-ovi rokovi tamo ne postoje.
    rb = _ics(k, "B")
    assert rb.status_code == 200 and "TAJNI" in rb.text and "20250326" not in rb.text and "20250317" not in rb.text


from tests.test_osb002_solo_tok import _do_kraja_dogadjaja, _novi_predmet, solo  # noqa: E402,F401


def _smart_intake_red(datum):
    """Red TACNO onakav kakav Smart Intake finalize upisuje (uhvacen, ne napisan rukom)."""
    supa = _supa()
    asyncio.run(_finalize(supa, [_dok([_ent("deadline", datum, 0.95)])]))
    rokovi_domen._resetuj_sondu()
    assert len(supa.upisi) == 1
    return dict(supa.upisi[0])


def test_FD7_smart_intake_kandidat_otvara_case_action_pregleda(solo, sonda_129):
    """Case Actions Rule 6 („Rok iz dokumenta čeka vašu potvrdu") vidi Smart
    Intake kandidat; isti red bez `vrsta` (stanje pre ispravke) ne vidi."""
    from datetime import timedelta
    from services.event_bus import EventType, emit_durable
    buduci = (date.today() + timedelta(days=12))
    si = _smart_intake_red(buduci.strftime("%d.%m.%Y"))
    k, b = solo
    _, pid = _novi_predmet(k, b)
    for rid, sa_vrstom in (("si-sa-vrstom", True), ("si-bez-vrste", False)):
        red = {**si, "id": rid, "predmet_id": pid, "user_id": "uid-A"}
        if not sa_vrstom:
            red.pop("vrsta", None)
        b.tabele["predmet_hronologija"].append(red)
    asyncio.run(emit_durable(EventType.MANUAL_CORRECTION_APPLIED, "uid-A", pid, {"trigger": "test"}))
    _do_kraja_dogadjaja(b)
    akc = [a for a in b.tabele["case_actions"] if a["predmet_id"] == pid and a["status"] == "open"
           and (a.get("dokaz") or {}).get("izvor") == "predmet_hronologija"]
    assert [a["dokaz"]["hronologija_id"] for a in akc] == ["si-sa-vrstom"]
    assert akc[0]["tip"] == "PLANIRATI_ROKOVE" and akc[0]["dokaz"]["stanje_odluke"] == STANJE_NEPOTVRDJEN
