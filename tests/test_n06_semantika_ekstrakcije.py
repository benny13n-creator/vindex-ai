# -*- coding: utf-8 -*-
"""N06 — semantička ekstrakcija Smart Intake-a kroz STVARAN kod (`classify`, `extract_all_entities`, worker, finalize)
sa namerno pogrešnim odgovorima modela. Svi dokumenti su sintetički (izmišljeni podaci); referentni dokument je
rekonstrukcija QA dostavnice `04_dostavnica_novi_ocr001_test.pdf` (oznaka OCR001-FRESH-2026-015).

Šta se dokazuje:
  * primalac / punomoćnik koji stoji ODMAH ISPOD stranke nikad ne postaje ta stranka (prozor uloge se ne preliva
    preko oznake druge, nezamenljive uloge);
  * ime koje model „ispravi“ (OCR pogrešno pročitano slovo, drugo prezime sa istim početkom) nije potvrđeno kao
    navedena stranka — ide na pregled, ne tiho u predmet;
  * dostavnica koja POMINJE dostavljeno pismeno („Писмено: пресуда“) nije heuristički proglašena tim pismenom;
  * datum uručenja nije rok, izmišljen rok iz modela se ne prima, nepoznat tip se prijavljuje pošteno.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

REF_04 = [
    "ДОСТАВНИЦА",
    "Прималац: Пример Инвест Тест д.о.о.",
    "Уручено дана 26.03.2025. године.",
    "Ознака: OCR001-FRESH-2026-015",
    "Достављач: Милан Измишљени",
]
DOSTAVNICA_SA_STRANKAMA_CIR = [
    "ДОСТАВНИЦА",
    "Пошиљалац: Основни суд у Београду",
    "Писмено: пресуда П 123/2025",
    "Тужилац: Марко Петровић",
    "Тужени: Јован Јовановић",
    "Прималац: Пример Инвест Тест д.о.о.",
    "Уручено дана 26.03.2025. године.",
]
DOSTAVNICA_SA_STRANKAMA_LAT = [
    "DOSTAVNICA",
    "Predmet: P 123/2025",
    "Tužilac: Marko Petrović",
    "Tuženi: Jovan Jovanović",
    "Primalac: Primer Invest Test doo",
    "Uručeno dana 26.03.2025. godine.",
]

_PET = ("judge", "plaintiff", "defendant", "court", "law_cited")


def _model_klijent(klasa: dict, entiteti: dict):
    """Lažni OpenAI klijent: STVARNI `classify_llm`/`extract_free_text_entities` parsiraju njegov JSON."""
    async def create(**kw):
        telo = klasa if "klasifikator" in kw["messages"][0]["content"] else entiteti
        r = MagicMock()
        r.choices = [MagicMock(message=MagicMock(content=json.dumps(telo, ensure_ascii=False)))]
        return r
    c = MagicMock()
    c.chat.completions.create = AsyncMock(side_effect=create)
    return c


def _obradi_tekst(tekst: str, klasa: dict, **uloge):
    from shared.intake_classify import classify
    from shared.intake_extract import extract_all_entities
    entiteti = {t: {"value": None, "confidence": 0.0} for t in _PET}
    for t, (v, c) in uloge.items():
        entiteti[t] = {"value": v, "confidence": c}

    async def _sve():
        with patch("openai.AsyncOpenAI", return_value=_model_klijent(klasa, entiteti)):
            return await classify(tekst), await extract_all_entities(tekst)
    k, e = asyncio.run(_sve())
    return k, {x["entity_type"]: x for x in e}


def _uloga(tekst: str, tip: str, vrednost: str):
    """Samo čuvar uloge, bez modela: da li bi vrednost modela bila zadržana."""
    from shared.intake_extract import uloga_navedena_u_tekstu
    return uloga_navedena_u_tekstu(tekst, tip, vrednost)


# ── 1. Primalac ispod stranke ne postaje stranka ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("redovi,tip,vrednost", [
    (DOSTAVNICA_SA_STRANKAMA_CIR, "defendant", "Пример Инвест Тест д.о.о."),
    (DOSTAVNICA_SA_STRANKAMA_LAT, "defendant", "Primer Invest Test doo"),
    (["Tužilac: Marko Petrović", "Primalac: Primer Invest Test doo"], "plaintiff", "Primer Invest Test doo"),
    (["Тужилац: Марко Петровић", "Адресат: Пример Инвест Тест д.о.о."], "plaintiff", "Пример Инвест Тест д.о.о."),
    (["Tuženi: Jovan Jovanović", "Punomoćnik: advokat Petar Petrović"], "defendant", "Petar Petrović"),
    (["Tuženi: Jovan Jovanović", "Pošiljalac: Primer Invest Test doo"], "defendant", "Primer Invest Test doo"),
])
def test_ime_iza_oznake_druge_uloge_nije_stranka(redovi, tip, vrednost):
    assert _uloga("\n".join(redovi), tip, vrednost) is False


def test_primalac_dostavnice_kroz_stvaran_tok_nije_tuzeni():
    k, e = _obradi_tekst("\n".join(DOSTAVNICA_SA_STRANKAMA_LAT), {"document_type": "other", "confidence": 0.2},
                         plaintiff=("Marko Petrović", 0.9), defendant=("Primer Invest Test doo", 0.95))
    assert e["defendant"]["value"] is None and e["defendant"]["confidence"] == 0.0
    assert e["plaintiff"]["value"] == "Marko Petrović"          # stvarno navedena stranka ostaje


# ── 2. Ime koje je model „ispravio“ nije potvrđena stranka ─────────────────────────────────────────────────────

@pytest.mark.parametrize("tekst,vrednost", [
    ("Tuženi: Jovan Petrovlć iz Niša", "Jovan Petrović"),                    # OCR: „l“ umesto „i“
    ("Tuženi: Jovan Petrovski iz Niša", "Jovan Petrović"),                   # drugo prezime, isti početak
    ("Tuženi: Primer Investlcije Test d.o.o.", "Primer Investicije Test d.o.o."),
])
def test_ispravljeno_ili_drugo_ime_nije_potvrdjeno(tekst, vrednost):
    assert _uloga(tekst, "defendant", vrednost) is False


@pytest.mark.parametrize("tekst,tip,vrednost", [
    ("Tuženi: Primer Invest Test doo iz Beograda", "defendant", "Primer Invest Test doo"),
    ("Tuženi:\nPrimer Invest Test doo", "defendant", "Primer Invest Test doo"),          # ime u sledećem redu
    ("Тужилац Марко Петровић из Београда поднео је тужбу против туженог Јована Јовановића", "defendant", "Jovan Jovanović"),
    ("u parnici tužioca Marka Petrovića protiv tuženog", "plaintiff", "Marko Petrović"),
    ("Tužilac: Marka Petrovića", "plaintiff", "Marko Petrović"),
    ("tuženog Primer Investa", "defendant", "Primer Invest"),
    ("Tuženi: Primer Invest Test doo, koga zastupa punomoćnik advokat Petar Petrović", "defendant", "Primer Invest Test doo"),
])
def test_stvarno_navedena_stranka_u_padezu_ostaje(tekst, tip, vrednost):
    assert _uloga(tekst, tip, vrednost) is True


# Recenzija N06: nepostojano „a“ u padežu (Aleksandar → Aleksandra) je bilo True na 020da293, a N06 ga je odbijao.
@pytest.mark.parametrize("tekst,tip,vrednost", [
    ("u parnici tužioca Aleksandra Jovanovića protiv tuženog", "plaintiff", "Aleksandar Jovanović"),
    ("u parnici tužioca Petra Petrovića protiv tuženog", "plaintiff", "Petar Petrović"),
    ("Тужилац Александар Јовановић, против туженог", "plaintiff", "Aleksandar Jovanović"),
    ("tuženom Aleksandru Jovanoviću", "defendant", "Aleksandar Jovanović"),
])
def test_nepostojano_a_u_padezu_ostaje(tekst, tip, vrednost):
    assert _uloga(tekst, tip, vrednost) is True


@pytest.mark.parametrize("tekst,tip,vrednost", [
    ("Tužilac: Aleksa Jovanović", "plaintiff", "Aleksandar Jovanović"),      # drugo ime, isti početak
    ("Tužilac: Petrović Jovan", "plaintiff", "Petar Petrović"),               # „petr“ ne sme da pogodi „Petrović“
    ("Tužilac: Aleksandrov Jovanović", "plaintiff", "Aleksandar Jovanović"),  # drugo ime, ista osnova
])
def test_nepostojano_a_ne_otvara_druga_imena(tekst, tip, vrednost):
    assert _uloga(tekst, tip, vrednost) is False


def test_ispravljeno_ime_kroz_stvaran_tok_ide_na_pregled():
    k, e = _obradi_tekst("TUŽBA\nTužilac: Marko Petrović\nTuženi: Jovan Petrovski iz Niša",
                         {"document_type": "lawsuit", "confidence": 0.9},
                         plaintiff=("Marko Petrović", 0.95), defendant=("Jovan Petrović", 0.95))
    assert e["defendant"]["value"] is None and e["defendant"]["confidence"] == 0.0
    assert e["plaintiff"]["value"] == "Marko Petrović"


# ── 3. Dostavnica nije pismeno koje pominje ───────────────────────────────────────────────────────────────────

def test_dostavnica_koja_pominje_presudu_nije_heuristicki_presuda():
    from shared.intake_classify import classify_heuristic
    assert classify_heuristic("\n".join(DOSTAVNICA_SA_STRANKAMA_CIR)) is None
    assert classify_heuristic("POŠTA SRBIJE — DOSTAVNICA\nPismeno: rešenje\nPrimalac: Marko Petrović") is None
    k, _ = _obradi_tekst("\n".join(DOSTAVNICA_SA_STRANKAMA_CIR), {"document_type": "other", "confidence": 0.2})
    assert k == {"document_type": "other", "confidence": 0.2, "method": "llm"}


@pytest.mark.parametrize("tekst,tip", [
    ("PRESUDA U IME NARODA\nOsnovni sud u Novom Sadu", "judgment"),
    ("ТУЖБА\nОсновном суду у Београду\nДоказ: доставница", "lawsuit"),       # dostavnica pomenuta POSLE naslova
    ("REŠENJE\nkojim se odbija predlog; dostavnica u prilogu", "court_decision"),
])
def test_naslov_ispred_pomena_dostavnice_ostaje_heuristika(tekst, tip):
    from shared.intake_classify import classify_heuristic
    assert classify_heuristic(tekst) == (tip, 0.85)


# ── 4. Referentna dostavnica (OCR001-FRESH-2026-015): ništa izmišljeno ────────────────────────────────────────

def test_referentna_dostavnica_model_tvrdi_stranke_rok_i_tip():
    tekst = "\n".join(REF_04)
    entiteti_modela = {"plaintiff": ("Пример Инвест Тест д.о.о.", 0.92), "defendant": ("Пример Инвест Тест д.о.о.", 0.92)}
    k, e = _obradi_tekst(tekst, {"document_type": "delivery_receipt", "confidence": 0.99}, **entiteti_modela)
    assert k == {"document_type": "other", "confidence": 0.3, "method": "llm"}      # nepoznat tip → pošteno „other“
    assert e["plaintiff"]["value"] is None and e["defendant"]["value"] is None
    assert e["deadline"] == {"entity_type": "deadline", "value": None, "confidence": 0.0, "extraction_method": "regex"}
    assert e["case_number"]["value"] is None                                         # interna oznaka nije broj predmeta


def test_izmisljen_rok_iz_modela_se_ne_prima():
    from shared.intake_extract import extract_all_entities
    tekst = "\n".join(REF_04)
    telo = {t: {"value": None, "confidence": 0.0} for t in _PET}
    telo["deadline"] = {"value": "10.04.2025", "confidence": 0.99}

    async def _sve():
        with patch("openai.AsyncOpenAI", return_value=_model_klijent({}, telo)):
            return await extract_all_entities(tekst)
    e = {x["entity_type"]: x for x in asyncio.run(_sve())}
    assert e["deadline"]["value"] is None and e["deadline"]["extraction_method"] == "regex"


# ── 5. Stvaran OCR → worker → pregled → predmet (preskače se bez Tesseract-a) ────────────────────────────────────

from tests.ns005_harness import zaglavlje  # noqa: E402
from tests.test_ns005_t14_smart_intake import PA, _OCR, _obradi, _otpremi, _skeniran_pdf, ok  # noqa: E402,F401

treba_ocr = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — stvaran OCR preskočen")


@treba_ocr
def test_ocr_dostavnice_ceo_tok_primalac_nije_stranka_i_original_ostaje(ok, monkeypatch):
    """Skenirane dostavnice (referentna 04 + latinična sa strankama) kroz stvaran OCR, worker, pregled i prikačivanje;
    model namerno tvrdi da je primalac tužilac/tuženi. Proverava se ono što ne zavisi od kvaliteta lokalnog OCR-a:
    latinična oznaka i datum su u tekstu predmeta, strana je jedna, uloga nije prihvaćena, rok nije nastao."""
    k, b = ok
    import shared.intake_extract as ex

    async def _model(t):
        return {"judge": (None, 0.0), "plaintiff": ("Пример Инвест Тест д.о.о.", 0.92),
                "defendant": ("Primer Invest Test doo", 0.95), "court": (None, 0.0), "law_cited": (None, 0.0)}
    monkeypatch.setattr(ex, "extract_free_text_entities", _model)
    uloge = {}
    for ime, redovi in (("04_dostavnica_novi_ocr001_test.pdf", REF_04),
                        ("05_dostavnica_sa_strankama.pdf", DOSTAVNICA_SA_STRANKAMA_LAT)):
        jid = _otpremi(k, "A", _skeniran_pdf(redovi), ime=ime).json()["rezultati"][0]["job_id"]
        assert _obradi() is True
        g = k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje("A")).json()
        uloge[ime] = {e["entity_type"]: e["value"] for e in g["entiteti"] if e["entity_type"] in ("plaintiff", "defendant", "deadline")}
        assert g["dokument"]["ocr_koriscen"] is True
        if g["job"]["status"] == "awaiting_review":
            assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=zaglavlje("A")).status_code == 200
        f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": PA}, headers=zaglavlje("A"))
        assert f.status_code == 200 and f.json()["prikacivanje"] == "POTPUNO", (ime, f.text)
    assert all(v is None for u in uloge.values() for v in u.values()), uloge
    docs = [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == PA]
    assert len(docs) == 2
    tekst = " ".join(d.get("tekst_sadrzaj") or "" for d in docs)
    assert "OCR001-FRESH-2026-015" in tekst and "26.03.2025" in tekst
    assert b.tabele["predmet_hronologija"] == [], "datum uručenja ne sme postati rok"

# Recenzija N06 (krug 2): oblik bez nepostojanog „a“ važi samo posle muške oznake u kosom padežu. Posle nominativa
# ili ženske oznake „Petra“ je žensko ime — „Tužilja: Petra Ilić“ ne potvrđuje model-vrednost „Petar Ilić“.
@pytest.mark.parametrize("tekst,tip,vrednost", [
    ("Tužilja: Petra Ilić", "plaintiff", "Petar Ilić"),
    ("Tužilac: Petra Ilić", "plaintiff", "Petar Ilić"),
    ("Tužena: Petra Ilić", "defendant", "Petar Ilić"),
    ("Тужиља: Петра Илић", "plaintiff", "Petar Ilić"),
    ("u parnici tužilje Petre Ilić", "plaintiff", "Petar Ilić"),
    ("Tužioci: Petra Ilić i Marko Ilić", "plaintiff", "Petar Ilić"),   # krug 3: množina nije kosi padež
])
def test_nepostojano_a_ne_vazi_posle_nominativa_ili_zenske_oznake(tekst, tip, vrednost):
    assert _uloga(tekst, tip, vrednost) is False


@pytest.mark.parametrize("tekst,tip,vrednost", [
    ("u parnici tužioca Petra Ilića protiv tuženog", "plaintiff", "Petar Ilić"),
    ("protiv tuženog Lazara Ilića", "defendant", "Lazar Ilić"),
    ("presuda tuženom Petru Iliću", "defendant", "Petar Ilić"),
    ("presuda tužiocu Petru Iliću", "plaintiff", "Petar Ilić"),
    ("sa tužiocem Petrom Ilićem", "plaintiff", "Petar Ilić"),
    ("u parnici tužilje Petre Ilić", "plaintiff", "Petra Ilić"),   # žensko ime u kosom padežu, ženska vrednost
    ("Tužilja: Petra Ilić", "plaintiff", "Petra Ilić"),
])
def test_nepostojano_a_posle_muskog_kosog_padeza_i_zenska_imena(tekst, tip, vrednost):
    assert _uloga(tekst, tip, vrednost) is True

