# -*- coding: utf-8 -*-
"""
Testovi za analiza/segmenter.py (Sloj 1).

Smoke test kriterijumi:
  Test 1 — Ugovor o radu: prepoznaje "Član N", vraća klauzule, doc_type="ugovor"
  Test 2 — Presuda: prepoznaje sekcije (izreka, obrazlozenje), doc_type="presuda"
  Oba: segment_count > 0, full_text sačuvan, char_count tačan
"""

import pytest
from analiza.segmenter import detect_document_type, segment_document, SegmentedDocument

# ─── Test dokumenti ──────────────────────────────────────────────────────────

UGOVOR_O_RADU = """UGOVOR O RADU

Ugovorne strane:
Poslodavac: DOO "Primer", PIB 123456789
Zaposleni: Petar Petrović, JMBG redacted

zaključuju sledeći ugovor:

Član 1
PREDMET UGOVORA

Poslodavac zasniva radni odnos sa zaposlenim na neodređeno vreme, na radnom mestu Magacioner.

Član 2
TRAJANJE RADNOG ODNOSA

Radni odnos zasniva se na neodređeno vreme počev od 01.01.2024. godine.

Član 3
ZARADA

Osnovna mesečna bruto zarada zaposlenog iznosi 80.000 dinara.

Član 4
RASKID UGOVORA

Poslodavac može raskinuti ovaj ugovor bez otkaznog roka u slučaju krivice zaposlenog.

Član 5
UGOVORNA KAZNA

U slučaju prevremenog raskida od strane zaposlenog, zaposleni je dužan da plati ugovornu kaznu u iznosu od 10% godišnje zarade.
"""

PRESUDA_TEKST = """REPUBLIKA SRBIJA
VRHOVNI KASACIONI SUD

PRESUDA

U IME NARODA

Vrhovni kasacioni sud, u veću sastavljenom od sudija...

IZREKA

Odbija se kao neosnovana revizija tužioca.

Obavezuje se tužilac da tuženom naknadi troškove revizijskog postupka u iznosu od 30.000 dinara.

OBRAZLOŽENJE

Prvostepenom presudom Osnovnog suda u Beogradu P. 1234/2023 od 10.05.2024. odbijen je tužbeni zahtev tužioca.

Drugostepenom presudom Apelacionog suda u Beogradu Gž. 456/2024 od 15.08.2024. odbijena je žalba tužioca.

Tužilac je blagovremeno izjavio reviziju...

PRAVNI OSNOV

Na osnovu člana 416 Zakona o parničnom postupku, odlučeno je kao u izreci.

POUKA O PRAVNOM LEKU

Protiv ove presude nije dopuštena revizija.
"""

OSTALO_TEKST = "Ovo je neki tekst koji nije ni ugovor ni presuda. Sadrži razne informacije."


# ─── detect_document_type ─────────────────────────────────────────────────────

def test_detect_ugovor():
    assert detect_document_type(UGOVOR_O_RADU) == "ugovor"

def test_detect_presuda():
    assert detect_document_type(PRESUDA_TEKST) == "presuda"

def test_detect_ostalo():
    tip = detect_document_type(OSTALO_TEKST)
    assert tip in ("ostalo", "ugovor", "presuda", "resenje")  # ne sme da crasha

def test_detect_resenje():
    resenje = "REŠENJE\nIzvršni poverilac traži izvršenje. Nalaže se plenidba plate."
    assert detect_document_type(resenje) == "resenje"


# ─── segment_document — ugovor ───────────────────────────────────────────────

def test_ugovor_segment_count():
    doc = segment_document(UGOVOR_O_RADU)
    assert doc.doc_type == "ugovor"
    assert doc.segment_count >= 4  # 5 članova

def test_ugovor_clause_ids():
    doc = segment_document(UGOVOR_O_RADU)
    ids = [s.id for s in doc.segments]
    # Mora imati clause_1 kroz clause_5 (ili slično)
    assert any("1" in sid for sid in ids), f"Nema clause_1 u: {ids}"
    assert any("4" in sid for sid in ids), f"Nema clause_4 u: {ids}"

def test_ugovor_tekst_nije_prazan():
    doc = segment_document(UGOVOR_O_RADU)
    for seg in doc.segments:
        assert len(seg.tekst) > 0, f"Prazna klauzula: {seg.id}"

def test_ugovor_full_text_saeuvan():
    doc = segment_document(UGOVOR_O_RADU)
    assert doc.full_text == UGOVOR_O_RADU.strip()
    assert doc.char_count == len(UGOVOR_O_RADU.strip())

def test_ugovor_offsets():
    doc = segment_document(UGOVOR_O_RADU)
    for seg in doc.segments:
        assert seg.start_offset >= 0
        assert seg.end_offset > seg.start_offset


# ─── segment_document — presuda ──────────────────────────────────────────────

def test_presuda_doc_type():
    doc = segment_document(PRESUDA_TEKST)
    assert doc.doc_type == "presuda"

def test_presuda_ima_izreku():
    doc = segment_document(PRESUDA_TEKST)
    ids = [s.id for s in doc.segments]
    assert "izreka" in ids, f"Nedostaje 'izreka' u: {ids}"

def test_presuda_ima_obrazlozenje():
    doc = segment_document(PRESUDA_TEKST)
    ids = [s.id for s in doc.segments]
    assert "obrazlozenje" in ids, f"Nedostaje 'obrazlozenje' u: {ids}"

def test_presuda_null_za_nepronasene():
    doc = segment_document(PRESUDA_TEKST)
    # Svaka sekcija mora biti u listi (ili prazna = null)
    ids = {s.id for s in doc.segments}
    # Sve od ovih mora biti prisutno (ili prazno)
    expected_sections = {"izreka", "obrazlozenje", "pravni_osnov", "pouka_o_pravnom_leku"}
    for sec in expected_sections:
        assert sec in ids, f"Nedostaje sekcija '{sec}' — mora biti prisutna (može biti prazna)"

def test_presuda_segment_count():
    doc = segment_document(PRESUDA_TEKST)
    assert doc.segment_count >= 3

def test_presuda_izreka_tekst_sadrzi_odluku():
    doc = segment_document(PRESUDA_TEKST)
    izreka = next((s for s in doc.segments if s.id == "izreka" and s.start_offset >= 0), None)
    assert izreka is not None, "Izreka nije pronađena"
    assert len(izreka.tekst) > 0
    assert "odbija" in izreka.tekst.lower() or "odbija" in izreka.tekst.lower() or "nalaže" in izreka.tekst.lower()


# ─── SegmentedDocument.to_llm_context ────────────────────────────────────────

def test_to_llm_context_sadrzi_ids():
    doc = segment_document(UGOVOR_O_RADU)
    ctx = doc.to_llm_context()
    for seg in doc.segments[:3]:
        assert f"[{seg.id}]" in ctx, f"ID '{seg.id}' nije u LLM kontekstu"

def test_to_llm_context_posteuje_limit():
    doc = segment_document(UGOVOR_O_RADU)
    ctx = doc.to_llm_context(max_chars_per_segment=100)
    # Svaki segment mora biti skraćen — "skraćeno" mora biti u tekstu za duže segmente
    # (nema hard provere, samo ne sme da crasha)
    assert len(ctx) > 0

def test_segment_map():
    doc = segment_document(UGOVOR_O_RADU)
    smap = doc.segment_map()
    for seg in doc.segments:
        assert seg.id in smap
        assert smap[seg.id] is seg


# ─── Fallback za kratki tekst ─────────────────────────────────────────────────

def test_fallback_for_unstructured():
    tekst = "Ovo je dugačak nestrukturirani tekst. " * 200  # 7200 char
    doc = segment_document(tekst)
    assert doc.segment_count >= 1
    assert doc.doc_type in ("ostalo", "ugovor", "presuda", "resenje")
    assert doc.char_count == len(tekst.strip())
