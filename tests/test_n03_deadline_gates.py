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
    assert len(supa.upisi) <= 1
    for red in supa.upisi:
        assert red["izvor"] == rokovi_domen.IZVOR_AI_AUTONOMOUS
        assert "stanje" not in red or red["stanje"] != rokovi_domen.STANJE_POTVRDJEN
        # Nema odluke u lancu -> ACTION zabranjen.
        assert not rokovi_domen.sme_pokrenuti_obavezu({**red, "id": "novi"}, set())
    assert rez["rok_dodat"] in (True, False)


@pytest.mark.xfail(strict=True, reason="N03-FD1: konflikt rokova izmedju dokumenata se ne prijavljuje — odluka osnivaca")
@pytest.mark.anyio
async def test_S1_konflikt_rokova_mora_ostati_vidljiv():
    """INVARIJANTA: kontradikcija ostaje vidljiva. Danas finalize uzima rok
    SAMO iz prvog dokumenta (`per_doc_meta_maps[0]`), drugi datum tiho nestaje
    iz predmeta, a odgovor ne nosi nikakav signal konflikta (za razliku od
    broja predmeta, gde konflikt daje 409)."""
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


@pytest.mark.xfail(strict=True, reason="N03-FD3: /api/dokument/rokovi racuna datum iz relativnog izraza (mesec=30 dana) bez pravnog osnova — odluka osnivaca")
def test_S3_kandidat_lista_ne_racuna_datum_iz_relativnog_izraza():
    """Legacy lista kandidata (`/api/dokument/rokovi`) od relativnog izraza i
    AUTOMATSKI pogodjenog datuma dokumenta pravi konkretan datum i
    „Istice za N dana". To je pravni racun bez izvora i bez kvalifikacije."""
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


@pytest.mark.xfail(strict=True, reason="N03-FD4: auto-detektovan 'datum dokumenta' uzima pecat prijema umesto datuma presude — odluka osnivaca")
def test_S4_datum_dostave_ne_postaje_datum_dokumenta():
    """`_extract_datum_dokumenta` (izvor za racun relativnih rokova u
    /api/dokument/rokovi) uzima prvo „dana DD.MM.YYYY" — ovde pecat prijema —
    i vraca ga kao datum dokumenta, uz `datum_dokumenta_izvor="auto"`."""
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


@pytest.mark.xfail(strict=True, reason="N03-FD2: preformulisan AI rok posle odbijanja postaje nov kandidat (FAZA 6.5 poznata praznina) — odluka osnivaca")
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


@pytest.mark.xfail(strict=True, reason="N03-FD5: .ics izvozi NEPOTVRDJEN AI kandidat kao obavezu — odluka osnivaca (kanonska kapija vs oznaka)")
def test_HTTP_ics_ne_izvozi_nepotvrdjen_AI_kandidat(http):
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


@pytest.mark.xfail(strict=True, reason="N03-FD6: promena/brisanje izvora ne ponistava potvrdu roka — odluka osnivaca")
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
