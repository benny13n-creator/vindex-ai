# -*- coding: utf-8 -*-
"""
Integration/regression tests — Faza 4, AKCIJA 2: Strukturna unifikacija i
napredna obrada spisa od 100+ strana (2026-07-24).

1. main.py — Map-Reduce pipeline za dokumente >12000 znakova
   (_batch_segments_za_map, _ask_analiza_v2_map_reduce, ask_analiza_v2 dispatch).
2. routers/evidence.py — lokacijsko utemeljenje (_lociraj_tvrdnju).
3. routers/cross_doc.py — pametno uzorkovanje (_uzorkuj_dokument) i
   programska provera citata (_validate_konflikti_citati).
4. analiza/validator.py — run_post_parse_validation refaktor.
"""
import sys
import os
import json
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_TOKEN", "test-admin-token-12345")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _build_long_ugovor(broj_clanova: int = 40, rizicna_klauzula: str = "") -> str:
    tekst = "UGOVORNE STRANE zaključuju sledeći ugovor. Kupac i prodavac su saglasni.\n\n"
    for i in range(1, broj_clanova):
        tekst += (
            f"Član {i}. Ovo je tekst člana {i} koji opisuje obavezu strana u ugovoru o kupoprodaji. " * 10
            + "\n\n"
        )
    if rizicna_klauzula:
        tekst += f"Član {broj_clanova}. {rizicna_klauzula}\n\n"
    return tekst


# ─── 1a. _batch_segments_za_map ────────────────────────────────────────────

def test_batch_segments_postuje_budzet():
    from main import _batch_segments_za_map
    from analiza.segmenter import Segment

    segs = [
        Segment(id=f"s{i}", type="klauzula", naslov=None, tekst="X" * 2000, start_offset=i, end_offset=i + 1)
        for i in range(10)
    ]
    batches = _batch_segments_za_map(segs, budget=6000)
    assert len(batches) == 4
    for b in batches[:-1]:
        assert sum(len(s.tekst) for s in b) <= 6000


def test_batch_segments_predugacak_segment_dobija_sopstveni_batch():
    from main import _batch_segments_za_map
    from analiza.segmenter import Segment

    segs = [Segment(id="big", type="klauzula", naslov=None, tekst="Y" * 9000, start_offset=0, end_offset=1)]
    batches = _batch_segments_za_map(segs, budget=6000)
    assert len(batches) == 1
    assert len(batches[0]) == 1
    assert batches[0][0].id == "big"  # nije izostavljen zbog dužine


def test_batch_segments_prazna_lista():
    from main import _batch_segments_za_map
    assert _batch_segments_za_map([]) == []


# ─── 1b. Map-Reduce end-to-end (mocked OpenAI) ────────────────────────────

def test_ask_analiza_v2_map_reduce_ne_gubi_rizicnu_klauzulu_na_kraju():
    """Ključni regresioni test: pre AKCIJE 2, svaki segment je bio skraćen
    na 1800 znakova u JEDNOM pozivu -- rizična klauzula pri kraju dugačkog
    ugovora je mogla biti odsečena. Sada mora preživeti Map-Reduce."""
    import main
    from analiza.segmenter import segment_document

    rizicna = "Ugovorna kazna za kašnjenje iznosi 5.000.000 RSD po danu kašnjenja, izuzetno rizična klauzula."
    tekst = _build_long_ugovor(broj_clanova=40, rizicna_klauzula=rizicna)
    seg = segment_document(tekst)
    assert seg.char_count > 12000, "test dokument mora preći Map-Reduce prag"

    zadnji_id = seg.segments[-1].id

    def fake_pozovi_openai(system_prompt, user_content, model="gpt-4o", max_tokens=1000, response_format=None):
        if system_prompt == main._SYSTEM_PROMPT_ANALIZA_MAP:
            if f"[{zadnji_id}]" in user_content:
                return json.dumps({
                    "findings": [{
                        "id": "f1", "category": "finansijski", "severity": "kritican",
                        "clause_ref": zadnji_id, "clause_excerpt": rizicna,
                        "law_ref": None, "finding": "Izuzetno visoka ugovorna kazna",
                        "suggested_fix": None, "confidence": 90,
                    }],
                    "financial_exposure_items": [{
                        "type": "ugovorna_kazna", "clause_ref": zadnji_id,
                        "amount_or_formula": "5.000.000 RSD/dan", "notes": "",
                    }],
                    "litigation_readiness": {"evidence_gaps": [], "procedural_defects": [], "deadline_risks": []},
                    "attack_surface": [],
                })
            return json.dumps({"findings": [], "financial_exposure_items": [], "litigation_readiness": {}, "attack_surface": []})
        elif system_prompt == main._SYSTEM_PROMPT_ANALIZA_REDUCE:
            return json.dumps({
                "missing_clauses": [],
                "legacy_text": "PRAVNI OSNOV: ... IDENTIFIKOVANI RIZICI: visoka ugovorna kazna. POUZDANOST: visoka",
                "max_total_exposure_rsd": 5000000,
            })
        raise AssertionError(f"neočekivan system prompt: {system_prompt[:50]}")

    with patch("main._pozovi_openai", side_effect=fake_pozovi_openai):
        result = main.ask_analiza_v2(seg, "")

    assert result["status"] == "success"
    data = result["data"]
    assert len(data["findings"]) == 1
    assert data["findings"][0]["clause_ref"] == zadnji_id
    assert data["findings"][0]["severity"] == "kritican"
    assert data["executive_summary"]["overall_risk_score"] == 100
    assert data["financial_exposure"]["max_total_exposure_rsd"] == 5000000


def test_ask_analiza_v2_map_reduce_odbacuje_nevalidan_clause_ref():
    """Grounding provera (validate_clause_refs) mora ostati aktivna i za
    Map-Reduce rezultate -- izmišljen clause_ref se odbacuje."""
    import main
    from analiza.segmenter import segment_document

    tekst = _build_long_ugovor(broj_clanova=40, rizicna_klauzula="Standardna odredba bez posebnog rizika.")
    seg = segment_document(tekst)
    assert seg.char_count > 12000

    def fake_pozovi_openai(system_prompt, user_content, model="gpt-4o", max_tokens=1000, response_format=None):
        if system_prompt == main._SYSTEM_PROMPT_ANALIZA_MAP:
            return json.dumps({
                "findings": [{
                    "id": "f1", "category": "pravni_rizik", "severity": "visok",
                    "clause_ref": "clause_ne_postoji_9999", "clause_excerpt": "izmišljen citat koji nije u dokumentu",
                    "law_ref": None, "finding": "lažan nalaz", "suggested_fix": None, "confidence": 80,
                }],
                "financial_exposure_items": [], "litigation_readiness": {}, "attack_surface": [],
            })
        elif system_prompt == main._SYSTEM_PROMPT_ANALIZA_REDUCE:
            return json.dumps({"missing_clauses": [], "legacy_text": "test", "max_total_exposure_rsd": None})
        raise AssertionError("neočekivan prompt")

    with patch("main._pozovi_openai", side_effect=fake_pozovi_openai):
        result = main.ask_analiza_v2(seg, "")

    data = result["data"]
    assert data["findings"] == [], "finding sa izmišljenim clause_ref ne sme preživeti validaciju"
    assert len(data["low_confidence_findings"]) >= 1


def test_ask_analiza_v2_kratak_dokument_ne_ide_kroz_map_reduce():
    """Dokumenti ≤12000 znakova zadržavaju stari, jednostavniji jedan-poziv
    put -- Map-Reduce se NE aktivira nepotrebno za kratke dokumente."""
    import main
    from analiza.segmenter import segment_document

    tekst = "UGOVORNE STRANE zaključuju ugovor. Član 1. Kratka odredba.\n\n" * 20
    seg = segment_document(tekst)
    assert seg.char_count <= 12000

    calls = {"map_reduce": False, "single": False}

    def fake_pozovi_openai(system_prompt, user_content, model="gpt-4o", max_tokens=1000, response_format=None):
        if system_prompt == main._SYSTEM_PROMPT_ANALIZA_MAP:
            calls["map_reduce"] = True
            return json.dumps({"findings": [], "financial_exposure_items": [], "litigation_readiness": {}, "attack_surface": []})
        elif system_prompt == main.SYSTEM_PROMPT_ANALIZA_V2:
            calls["single"] = True
            return json.dumps({
                "document_type": "ugovor", "findings": [], "missing_clauses": [],
                "financial_exposure": {"max_total_exposure_rsd": None, "items": []},
                "litigation_readiness": {"applicable": False, "evidence_gaps": [], "procedural_defects": [], "deadline_risks": []},
                "attack_surface": [], "low_confidence_findings": [], "legacy_text": "test",
            })
        raise AssertionError(f"neočekivan prompt za kratak dokument: {system_prompt[:50]}")

    with patch("main._pozovi_openai", side_effect=fake_pozovi_openai):
        result = main.ask_analiza_v2(seg, "")

    assert result["status"] == "success"
    assert calls["single"] is True
    assert calls["map_reduce"] is False


def test_map_batch_neuspesan_ne_obara_celu_analizu():
    """Ako JEDAN map batch pukne (mrežna greška), ostali batch-evi i dalje
    moraju dati rezultat -- delimičan neuspeh ne blokira sve."""
    import main
    from analiza.segmenter import segment_document

    tekst = _build_long_ugovor(broj_clanova=40, rizicna_klauzula="Rizik u poslednjem članu.")
    seg = segment_document(tekst)

    call_count = {"n": 0}

    def flaky_pozovi_openai(system_prompt, user_content, model="gpt-4o", max_tokens=1000, response_format=None):
        if system_prompt == main._SYSTEM_PROMPT_ANALIZA_MAP:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("simulirana mrežna greška")
            return json.dumps({"findings": [], "financial_exposure_items": [], "litigation_readiness": {}, "attack_surface": []})
        elif system_prompt == main._SYSTEM_PROMPT_ANALIZA_REDUCE:
            return json.dumps({"missing_clauses": [], "legacy_text": "test", "max_total_exposure_rsd": None})
        raise AssertionError("neočekivan prompt")

    with patch("main._pozovi_openai", side_effect=flaky_pozovi_openai):
        result = main.ask_analiza_v2(seg, "")

    assert result["status"] == "success", "pad jednog batch-a ne sme oboriti celu analizu"


# ─── 2. evidence.py::_lociraj_tvrdnju ──────────────────────────────────────

def test_lociraj_tvrdnju_pronalazi_tacan_citat():
    from routers.evidence import _lociraj_tvrdnju

    tekst = "A" * 3000 + "Ugovorna kazna iznosi 500.000 RSD po danu kašnjenja." + "B" * 3000
    loc = _lociraj_tvrdnju(tekst, "Ugovorna kazna iznosi 500.000 RSD po danu kašnjenja.")
    assert loc["start_offset"] == tekst.find("Ugovorna kazna")
    assert loc["stranica"] is not None
    assert loc["paragraf"] is not None


def test_lociraj_tvrdnju_nepostojeca_tvrdnja_vraca_none():
    from routers.evidence import _lociraj_tvrdnju

    tekst = "Neki potpuno drugačiji tekst dokumenta."
    loc = _lociraj_tvrdnju(tekst, "ovo se nikad ne pojavljuje u dokumentu bas nikako")
    assert loc == {"stranica": None, "paragraf": None, "start_offset": None, "end_offset": None}


def test_lociraj_tvrdnju_prazan_ulaz():
    from routers.evidence import _lociraj_tvrdnju
    assert _lociraj_tvrdnju("", "nešto")["stranica"] is None
    assert _lociraj_tvrdnju("nešto", "")["stranica"] is None


def test_klasifikuj_i_sacuvaj_salje_lokaciju_u_insert():
    """Integracioni test: klasifikuj_i_sacuvaj mora pozvati _lociraj_tvrdnju
    za svaku ključnu činjenicu i uključiti rezultat u insert red."""
    from routers import evidence as ev

    supa = MagicMock()
    dokumenti_table = MagicMock()
    dokazi_table = MagicMock()

    def _table(name):
        return dokumenti_table if name == "predmet_dokumenti" else dokazi_table
    supa.table = MagicMock(side_effect=_table)

    tekst_dokumenta = "A" * 100 + "Tužilac je pretrpeo štetu usled saobraćajne nezgode." + "B" * 100

    def _fake_rezultat(naziv, tekst):
        return {
            "tip_dokaza": "podnesak",
            "pravni_elementi": ["uzročna veza"],
            "ai_tags": {},
            "kljucne_cinjenice": ["Tužilac je pretrpeo štetu usled saobraćajne nezgode."],
        }

    with patch("routers.evidence.get_supa", return_value=supa), \
         patch("routers.evidence._klasifikuj_dokument", side_effect=_fake_rezultat):
        ev.klasifikuj_i_sacuvaj("predmet-1", "dok-1", "tuzba.pdf", tekst_dokumenta, "user-1")

    dokazi_table.insert.assert_called_once()
    row = dokazi_table.insert.call_args[0][0][0]
    assert "start_offset" in row
    assert row["start_offset"] == tekst_dokumenta.find("Tužilac je pretrpeo")


def test_klasifikuj_i_sacuvaj_degradira_na_legacy_insert_ako_kolone_ne_postoje():
    """Ako migracija 080 još nije pokrenuta u produkciji, prvi insert (sa
    grounding kolonama) puca -- mora retry-ovati BEZ tih kolona umesto da
    izgubi ceo upis."""
    from routers import evidence as ev

    supa = MagicMock()
    dokumenti_table = MagicMock()
    dokazi_table = MagicMock()

    call_log = []

    def _insert(rows):
        call_log.append(rows)
        m = MagicMock()
        if len(call_log) == 1:
            m.execute.side_effect = Exception('column "stranica" does not exist')
        else:
            m.execute.return_value = MagicMock(data=[{"id": "row-1"}])
        return m

    dokazi_table.insert = MagicMock(side_effect=_insert)

    def _table(name):
        return dokumenti_table if name == "predmet_dokumenti" else dokazi_table
    supa.table = MagicMock(side_effect=_table)

    def _fake_rezultat(naziv, tekst):
        return {"tip_dokaza": "ostalo", "pravni_elementi": [], "ai_tags": {}, "kljucne_cinjenice": ["Neka činjenica."]}

    with patch("routers.evidence.get_supa", return_value=supa), \
         patch("routers.evidence._klasifikuj_dokument", side_effect=_fake_rezultat):
        ev.klasifikuj_i_sacuvaj("predmet-1", "dok-1", "test.pdf", "tekst sa Neka činjenica. u sebi", "user-1")

    assert len(call_log) == 2, "mora pokušati insert dva puta (sa pa bez grounding kolona)"
    assert "stranica" in call_log[0][0]
    assert "stranica" not in call_log[1][0]


# ─── 3a. cross_doc.py::_uzorkuj_dokument ───────────────────────────────────

def test_uzorkuj_dokument_kratak_tekst_neizmenjen():
    from routers.cross_doc import _uzorkuj_dokument
    kratak = "Kratak tekst dokumenta."
    uzorak, uzorkovano = _uzorkuj_dokument(kratak)
    assert uzorak == kratak
    assert uzorkovano is False


def test_uzorkuj_dokument_dugacak_tekst_pokriva_i_kraj():
    """Ključni regresioni test: stari [:4000]/[:5000] pristup je garantovano
    gubio sve posle par prvih strana. Novi uzorak mora sadržati segmente sa
    KRAJA dokumenta, ne samo sa početka."""
    from routers.cross_doc import _uzorkuj_dokument

    tekst = _build_long_ugovor(broj_clanova=60)
    uzorak, uzorkovano = _uzorkuj_dokument(tekst)
    assert uzorkovano is True
    assert "Član 1." in uzorak or "[clause_1]" in uzorak
    assert any(f"[clause_{i}]" in uzorak for i in range(50, 60)), (
        "uzorak mora sadržati segmente iz poslednje trećine dokumenta"
    )


def test_uzorkuj_dokument_nestrukturiran_tekst_uzima_pocetak_i_kraj():
    from routers.cross_doc import _uzorkuj_dokument
    tekst = "POČETAK " * 2000 + "KRAJ_MARKER " * 2000  # bez prepoznatljive strukture za segmentaciju
    uzorak, uzorkovano = _uzorkuj_dokument(tekst)
    assert uzorkovano is True
    assert "POČETAK" in uzorak
    assert "KRAJ_MARKER" in uzorak


# ─── 3b. cross_doc.py::_validate_konflikti_citati ─────────────────────────

def test_validate_konflikti_citati_potvrdjuje_tacan_citat():
    from routers.cross_doc import DokumentUnos, _validate_konflikti_citati

    docs = [
        DokumentUnos(naziv="Ugovor A", tekst="Zaposleni ima pravo na otkazni rok od 30 dana."),
        DokumentUnos(naziv="Pravilnik B", tekst="Otkazni rok iznosi 15 dana za sve zaposlene."),
    ]
    konflikti = [{
        "dokument_a": "Ugovor A", "dokument_b": "Pravilnik B", "opis": "test",
        "citat_a": "otkazni rok od 30 dana", "citat_b": "Otkazni rok iznosi 15 dana",
    }]
    out = _validate_konflikti_citati(konflikti, docs)
    assert out[0]["citat_a_potvrdjen"] is True
    assert out[0]["citat_b_potvrdjen"] is True


def test_validate_konflikti_citati_otkriva_nepotvrdjen_citat():
    from routers.cross_doc import DokumentUnos, _validate_konflikti_citati

    docs = [
        DokumentUnos(naziv="Ugovor A", tekst="Zaposleni ima pravo na otkazni rok od 30 dana."),
        DokumentUnos(naziv="Pravilnik B", tekst="Otkazni rok iznosi 15 dana za sve zaposlene."),
    ]
    konflikti = [{
        "dokument_a": "Ugovor A", "dokument_b": "Pravilnik B", "opis": "halucinacija",
        "citat_a": "ovo uopšte ne postoji u dokumentu A", "citat_b": None,
    }]
    out = _validate_konflikti_citati(konflikti, docs)
    assert out[0]["citat_a_potvrdjen"] is False
    assert out[0]["citat_b_potvrdjen"] is None  # citat_b nije dostavljen -- nema šta da se proverava


def test_cross_doc_sync_prosledjuje_upozorenje_kad_je_dokument_uzorkovan():
    from routers.cross_doc import DokumentUnos, _cross_doc_sync

    dugacak = _build_long_ugovor(broj_clanova=60)
    kratak = "Kratak drugi dokument radi poređenja."
    docs = [DokumentUnos(naziv="Dugačak ugovor", tekst=dugacak), DokumentUnos(naziv="Kratak dokument", tekst=kratak)]

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "rezime": "test", "konflikti": [], "slicnosti": [], "preporuke": [], "pravni_zakljucak": "test",
    })))]

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.return_value = fake_resp
        result = _cross_doc_sync(docs, "Da li postoji konflikt?", None)

    assert result["upozorenje_skracenja"] is not None
    assert "Dugačak ugovor" in result["upozorenje_skracenja"]
    assert "Kratak dokument" not in result["upozorenje_skracenja"]


# ─── 4. analiza/validator.py::run_post_parse_validation refaktor ──────────

def test_run_post_parse_validation_isti_rezultat_kao_run_validation_pipeline():
    from analiza.validator import run_post_parse_validation, run_validation_pipeline
    from analiza.segmenter import segment_document

    tekst = "Član 1. Prva odredba ugovora o zakupu.\n\nČlan 2. Druga odredba ugovora."
    seg = segment_document(tekst)

    raw = json.dumps({
        "document_type": "ugovor",
        "findings": [{
            "id": "f1", "category": "pravni_rizik", "severity": "visok",
            "clause_ref": "clause_1", "clause_excerpt": "Prva odredba ugovora o zakupu",
            "law_ref": None, "finding": "test nalaz", "suggested_fix": None, "confidence": 85,
        }],
        "missing_clauses": [], "financial_exposure": {"max_total_exposure_rsd": None, "items": []},
        "litigation_readiness": {"applicable": False, "evidence_gaps": [], "procedural_defects": [], "deadline_risks": []},
        "attack_surface": [], "low_confidence_findings": [], "legacy_text": "test",
    })

    via_pipeline = run_validation_pipeline(raw, seg)

    parsed_dict = json.loads(raw)
    via_direct = run_post_parse_validation(parsed_dict, seg)

    assert via_pipeline["findings"] == via_direct["findings"]
    assert via_pipeline["executive_summary"] == via_direct["executive_summary"]
