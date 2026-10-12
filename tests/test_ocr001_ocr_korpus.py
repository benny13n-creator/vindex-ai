# -*- coding: utf-8 -*-
"""OCR001 Faze B/C/E — tri sintetička QA dokumenta (izmišljeni podaci) kroz STVARAN ekstraktor, STVARAN intake worker
i STVARNE Smart Intake rute.

Dva sloja:
  * bez Tesseract-a (lokalno, uvek): kvar OCR-a se ubacuje na granici `extractor._ocr_image` (Tesseract) — tako se
    meri šta pipeline radi kad OCR ne pročita stranu, kad je kratak digitalni tekst, i kad nema srpskog paketa;
  * sa Tesseract-om (CI: produkciona Docker slika, VINDEX_REQUIRE_OCR=1): stvarno merenje CER/WER, pokrivenosti strana,
    kritičnih datuma i oznaka, plus okrenut i blед sken. `VINDEX_OCR001_REPORT=<putanja>` → JSON sa brojevima.

Nijedan rezultat nije opšta tačnost srpskih pravnih dokumenata: to su tri determinisana fajla + dva otežana slučaja.
"""
import asyncio
import io
import json
import os
import time
import unicodedata

import pytest

from tests.ns005_harness import zaglavlje
from tests.test_ns005_t14_smart_intake import PA, _OCR, _obradi, _otpremi, _skeniran_pdf, ok  # noqa: F401 — `ok` je fixture

treba_ocr = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — merenje stvarnim OCR-om preskočeno")
IZVESTAJ: dict = {}

# ── Ground truth tri QA dokumenta (izmišljeno) ─────────────────────────────────────────────────────────────────────
A_REDOVI = [
    "OSNOVNI SUD U BEOGRADU",
    "Interna oznaka: TEST-2026-014",
    "Tuzilac: Petar Primerovic iz Beograda",
    "Tuzeni: Primer Invest Test doo iz Beograda",
    "Tuzeni duguje iznos od 47.912,00 RSD.",
    "Tuzba je dostavljena tuzenom 17.03.2025. godine.",
]
B_REDOVI = [
    "ДОСТАВНИЦА",
    "Прималац: Пример Инвест Тест д.о.о.",
    "Уручено дана 25.03.2025. године.",
    "Достављач: Милан Измишљени",
]
C1_REDOVI = [
    "ZAPISNIK O PRIJEMU POSILJKE",
    "Oznaka: TEST-2026-014",
    "Marker digitalne strane: DIGITALNA STRANA JEDAN",
]
C2_REDOVI = [
    "МАРКЕР СКЕНИРАНЕ СТРАНЕ ДВА",
    "Датум доставе је споран: 17.03.2025. или 25.03.2025.",
    "Наводно је остављен рок за одговор, што није проверено.",
]


def _norm(t):
    t = "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c))
    return " ".join(t.lower().split())


def _lev(a, b):
    if len(a) < len(b):
        a, b = b, a
    pret = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        tek = [i]
        for j, cb in enumerate(b, 1):
            tek.append(min(pret[j] + 1, tek[j - 1] + 1, pret[j - 1] + (ca != cb)))
        pret = tek
    return pret[-1]


def _cer_wer(istina, procitano):
    """Stopa greške po znaku i po reči (Levenshtein / dužina istine), posle NFKD normalizacije i malih slova."""
    i, p = _norm(istina), _norm(procitano)
    ri, rp = i.split(), p.split()
    cer = _lev(i, p) / max(len(i), 1)
    # WER: poravnanje reči kao niza simbola
    mapa = {w: chr(0x4E00 + k) for k, w in enumerate(sorted(set(ri + rp)))}
    wer = _lev("".join(mapa[w] for w in ri), "".join(mapa[w] for w in rp)) / max(len(ri), 1)
    return round(cer, 4), round(wer, 4)


def _digitalni(*strane):
    import fitz
    d = fitz.open()
    for redovi in strane:
        s = d.new_page(width=595, height=842)
        for k, red in enumerate(redovi):
            s.insert_text((50, 80 + k * 30), red, fontsize=14)
    b = io.BytesIO()
    d.save(b)
    d.close()
    return b.getvalue()


def _spoji(*pdfovi):
    import fitz
    d = fitz.open()
    for x in pdfovi:
        s = fitz.open(stream=x, filetype="pdf")
        d.insert_pdf(s)
        s.close()
    b = io.BytesIO()
    d.save(b)
    d.close()
    return b.getvalue()


def _sken_varijanta(redovi, rotacija=0, kontrast=1.0):
    """Sken bez tekstualnog sloja; `rotacija` u stepenima, `kontrast` < 1 bledi tekst ka beloj."""
    import fitz
    from PIL import Image, ImageEnhance
    izvor = fitz.open(stream=_skeniran_pdf(redovi), filetype="pdf")
    pix = izvor[0].get_pixmap(dpi=200)
    izvor.close()
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    if kontrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(kontrast)
    if rotacija:
        img = img.rotate(rotacija, expand=True, fillcolor=255)
    b = io.BytesIO()
    img.save(b, format="PNG")
    d = fitz.open()
    s = d.new_page(width=595 if img.width < img.height else 842, height=842 if img.width < img.height else 595)
    s.insert_image(s.rect, stream=b.getvalue())
    out = io.BytesIO()
    d.save(out)
    d.close()
    return out.getvalue()


def A_pdf():
    return _digitalni(A_REDOVI)


def B_pdf():
    return _skeniran_pdf(B_REDOVI)


def C_pdf():
    return _spoji(_digitalni(C1_REDOVI), _skeniran_pdf(C2_REDOVI))


def _sloj_teksta(pdf):
    import pypdf
    return [len((p.extract_text() or "").strip()) for p in pypdf.PdfReader(io.BytesIO(pdf)).pages]


def _izvuci(tmp_path, ime, pdf):
    from uploaded_doc.extractor import extract
    p = tmp_path / ime
    p.write_bytes(pdf)
    t0 = time.perf_counter()
    r = extract(p)
    return r, round(time.perf_counter() - t0, 2), p


@pytest.fixture
def ocr_pada(monkeypatch):
    """Tesseract ne pročita nijednu stranu (timeout / pad / nema paketa) — granica OCR-a, ne logika pipeline-a."""
    import uploaded_doc.extractor as ex
    pozivi = []

    def _ocr(img, jezik):
        pozivi.append(jezik)
        return "", None
    monkeypatch.setattr(ex, "_ocr_image", _ocr)
    # Izbor jezika zamenjen samo da bi STVARNA petlja po stranama radila i bez instaliranog pytesseract-a.
    monkeypatch.setattr(ex, "_detect_ocr_lang", lambda: "srp+srp_latn+eng")
    return pozivi


# ── Fiksture su ono što tvrde (E2) ───────────────────────────────────────────────────────────────────────────────

def test_fiksture_imaju_tacno_deklarisan_tekstualni_sloj():
    assert all(n > 0 for n in _sloj_teksta(A_pdf()))
    assert _sloj_teksta(B_pdf()) == [0], "„sken“ ne sme imati digitalni tekstualni sloj"
    sloj = _sloj_teksta(C_pdf())
    assert len(sloj) == 2 and sloj[0] > 30 and sloj[1] == 0, sloj


# ── B1: kratak ispravan digitalni tekst se ne odbacuje ──────────────────────────────────────────────────────────

def test_kratak_digitalni_pdf_zadrzava_tekst_kad_ocr_ne_procita_nista(tmp_path, ocr_pada):
    kratak = _digitalni(["DOSTAVNICA", "Primalac: Primer Invest Test doo", "Uruceno 25.03.2025."])
    assert 0 < sum(_sloj_teksta(kratak)) < 80                      # ispod praga „skenirano“ (80 znakova)
    (text, is_scanned, ocr_used, pages, _c), _t, _p = _izvuci(tmp_path, "kratak.pdf", kratak)
    assert ocr_pada, "OCR petlja mora stvarno da se izvrši (inače test ništa ne meri)"
    assert is_scanned is True and ocr_used is False                  # i dalje označen kao nepročitan → pregled
    assert "Primalac: Primer Invest Test doo" in text and "25.03.2025" in text   # ali tekst nije obrisan
    assert pages and "25.03.2025" in pages[0]


def test_kratak_digitalni_pdf_kraci_ocr_ne_zamenjuje_digitalni_tekst(tmp_path, monkeypatch):
    import uploaded_doc.extractor as ex
    pozivi = []
    monkeypatch.setattr(ex, "_ocr_image", lambda img, jezik: pozivi.append(jezik) or ("DOSTAV", 0.4))
    monkeypatch.setattr(ex, "_detect_ocr_lang", lambda: "srp+srp_latn+eng")
    kratak = _digitalni(["DOSTAVNICA", "Primalac: Primer Invest Test doo", "Uruceno 25.03.2025."])
    (text, is_scanned, ocr_used, _pg, conf), _t, _p = _izvuci(tmp_path, "kratak.pdf", kratak)
    assert pozivi, "OCR petlja mora stvarno da se izvrši (inače test ništa ne meri)"
    assert "Primer Invest Test doo" in text and is_scanned is True and ocr_used is False and conf is None


def test_kratak_digitalni_pdf_zadrzava_tekst_kad_ocr_pukne(tmp_path, monkeypatch):
    """Tesseract pukne (proces, memorija, nedostajući paket) — digitalni sloj ostaje, ništa se ne izmišlja."""
    import uploaded_doc.extractor as ex

    def _pukne(img, jezik):
        raise RuntimeError("tesseract pao")
    monkeypatch.setattr(ex, "_ocr_image", _pukne)
    monkeypatch.setattr(ex, "_detect_ocr_lang", lambda: "srp+srp_latn+eng")
    kratak = _digitalni(["DOSTAVNICA", "Primalac: Primer Invest Test doo", "Uruceno 25.03.2025."])
    (text, is_scanned, ocr_used, pages, conf), _t, _p = _izvuci(tmp_path, "kratak.pdf", kratak)
    assert is_scanned is True and ocr_used is False and conf is None
    assert "Primer Invest Test doo" in text and pages and "25.03.2025" in pages[0]


def test_digitalni_A_bez_ocr_a(tmp_path, ocr_pada):
    (text, is_scanned, ocr_used, pages, conf), _t, _p = _izvuci(tmp_path, "A.pdf", A_pdf())
    assert ocr_pada == [] and ocr_used is False and conf is None and is_scanned is False
    for kriticno in ("47.912,00 RSD", "17.03.2025", "TEST-2026-014"):
        assert kriticno in text, kriticno


# ── B4: potpunost strana ───────────────────────────────────────────────────────────────────────────────────────

def test_nepročitana_skenirana_strana_je_prepoznata_a_prazna_nije(tmp_path, ocr_pada):
    from uploaded_doc.extractor import necitljive_strane_pdf
    prazna = _digitalni([])
    pdf = _spoji(_digitalni(C1_REDOVI), _skeniran_pdf(C2_REDOVI), prazna)
    (text, is_scanned, ocr_used, pages, conf), _t, p = _izvuci(tmp_path, "C3.pdf", pdf)
    assert ocr_pada and is_scanned is False and len(pages) == 3
    assert "DIGITALNA STRANA JEDAN" in text and pages[1] == "" and pages[2] == ""
    assert necitljive_strane_pdf(p, pages) == [2], "skenirana strana bez teksta mora biti prijavljena, prazna ne"


def test_nemerljivo_nije_tvrdnja_ni_u_jednom_smeru(tmp_path):
    from uploaded_doc.extractor import necitljive_strane_pdf
    p = tmp_path / "nije_pdf.pdf"
    p.write_bytes(b"nije pdf")
    assert necitljive_strane_pdf(p, ["", "tekst"]) is None


# ── B4 kroz STVARAN worker i rute: delimično pročitan dokument ide na pregled, nikad „potpuno obrađen“ ──────────

def _posao(b):
    return b.tabele["intake_jobs"][-1]


def test_worker_deo_dokumenta_nije_procitan_posao_ceka_pregled_sa_tacnom_stranom(ok, ocr_pada):
    k, b = ok
    r = _otpremi(k, "A", C_pdf(), ime="03_zapisnik_mesoviti_pdf.pdf")
    jid = r.json()["rezultati"][0]["job_id"]
    assert _obradi() is True
    assert _posao(b)["status"] == "awaiting_review", _posao(b)["status"]
    g = k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje("A")).json()
    provere = g["potrebne_provere"]
    ocr = [q for q in provere if q["razlog"] == "ocr_failed"]
    assert ocr and any(x.startswith("strana 2:") for x in ocr[0]["polja"]), provere
    assert not any(x.startswith("strana 1:") for x in ocr[0]["polja"])


def test_worker_ocr_bez_srpskog_paketa_je_oznacen(ok, monkeypatch):
    import uploaded_doc.extractor as ex
    monkeypatch.setattr(ex, "_detect_ocr_lang", lambda: "eng")
    monkeypatch.setattr(ex, "_ocr_image", lambda img, jezik: ("MAPKEP CKEHNPAHE CTPAHE ДВА " * 6, 0.91))
    k, b = ok
    r = _otpremi(k, "A", C_pdf(), ime="03.pdf")
    jid = r.json()["rezultati"][0]["job_id"]
    assert _obradi() is True
    g = k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje("A")).json()
    polja = [x for q in g["potrebne_provere"] if q["razlog"] == "ocr_failed" for x in q["polja"]]
    assert any("bez srpskog jezičkog paketa" in x for x in polja), g["potrebne_provere"]
    assert _posao(b)["status"] == "awaiting_review"


def test_worker_niska_ocr_pouzdanost_je_oznacena(ok, monkeypatch):
    """Okrenut/mutan sken daje ≥ 30 znakova besmislenog teksta niske pouzdanosti — to nije „pročitano“."""
    import uploaded_doc.extractor as ex
    monkeypatch.setattr(ex, "_detect_ocr_lang", lambda: "srp+srp_latn+eng")
    monkeypatch.setattr(ex, "_ocr_image", lambda img, jezik: ("ln: TLE SL Eo eT ee ri Wee 2 eS ee ae ae " * 3, 0.41))
    k, b = ok
    jid = _otpremi(k, "A", C_pdf(), ime="03.pdf").json()["rezultati"][0]["job_id"]
    assert _obradi() is True
    g = k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje("A")).json()
    polja = [x for q in g["potrebne_provere"] if q["razlog"] == "ocr_failed" for x in q["polja"]]
    assert any("OCR pouzdanost 41 %" in x for x in polja), g["potrebne_provere"]
    assert _posao(b)["status"] == "awaiting_review"


# ── C2: primalac nije tužilac ──────────────────────────────────────────────────────────────────────────────────

def _entiteti(tekst, monkeypatch, iz_modela):
    import shared.intake_extract as ex

    async def _model(t):
        base = {t2: (None, 0.0) for t2 in ("judge", "plaintiff", "defendant", "court", "law_cited")}
        base.update(iz_modela)
        return base
    monkeypatch.setattr(ex, "extract_free_text_entities", _model)
    return {e["entity_type"]: e for e in asyncio.run(ex.extract_all_entities(tekst))}


def test_primalac_sa_dostavnice_nikad_nije_tuzilac(monkeypatch):
    """Tačno QA nalaz: model je primaoca stavio u `plaintiff`. Uloga nije navedena u tekstu → ne tvrdi se."""
    e = _entiteti("\n".join(B_REDOVI), monkeypatch, {"plaintiff": ("Пример Инвест Тест д.о.о.", 0.86)})
    assert e["plaintiff"]["value"] is None and e["plaintiff"]["confidence"] == 0.0


def test_stranke_tuzbe_sa_navedenom_ulogom_ostaju(monkeypatch):
    e = _entiteti("\n".join(A_REDOVI), monkeypatch, {"plaintiff": ("Petar Primerović", 0.92), "defendant": ("Primer Invest Test doo", 0.9)})
    assert e["plaintiff"]["value"] == "Petar Primerović" and e["plaintiff"]["confidence"] == 0.92
    assert e["defendant"]["value"] == "Primer Invest Test doo"


def test_zamenjene_uloge_iz_modela_su_odbijene(monkeypatch):
    e = _entiteti("\n".join(A_REDOVI), monkeypatch, {"plaintiff": ("Primer Invest Test doo", 0.9), "defendant": ("Petar Primerović", 0.9)})
    assert e["plaintiff"]["value"] is None and e["defendant"]["value"] is None


def test_cirilicna_tuzba_u_padezu_ostaje(monkeypatch):
    t = "Тужилац Марко Петровић из Београда поднео је тужбу против туженог Јована Јовановића"
    e = _entiteti(t, monkeypatch, {"plaintiff": ("Marko Petrović", 0.9), "defendant": ("Jovan Jovanović", 0.9)})
    assert e["plaintiff"]["value"] == "Marko Petrović" and e["defendant"]["value"] == "Jovan Jovanović"


# ── C4: broj predmeta — stvarni srpski oblici prepoznati, sintetička interna oznaka nije sudski broj ───────────

@pytest.mark.parametrize("tekst,ocekivano", [
    ("Broj predmeta: P 4321/2026", "P 4321/2026"),
    ("Број предмета: П 4321/2026", "П 4321/2026"),
    ("posl. br. Gž 123/2025", "Gž 123/2025"),
    ("Rev 77/2024", "Rev 77/2024"),
    ("Interna oznaka: TEST-2026-014", None),
])
def test_broj_predmeta_srpski_oblici(tekst, ocekivano):
    from shared.intake_extract import extract_case_number
    assert extract_case_number(tekst)[0] == ocekivano


# ── C5: sporni datumi i „rok“ bez osnova ne postaju rok ────────────────────────────────────────────────────────

def test_sporni_datumi_i_neprovereni_rok_ne_postaju_rok():
    from shared.intake_extract import extract_deadline
    assert extract_deadline("\n".join(C1_REDOVI + C2_REDOVI)) == (None, 0.0)
    assert extract_deadline("\n".join(A_REDOVI)) == (None, 0.0)          # „dostavljena 17.03.2025“ je događaj, ne rok


def test_ai_rok_iz_dokumenta_ne_pokrece_podsetnik_bez_potvrde():
    from shared.rokovi import IZVOR_AI_AUTONOMOUS, filtriraj_izvrsive
    red = {"id": "r1", "izvor": IZVOR_AI_AUTONOMOUS, "dogadjaj": "Rok iz dokumenta (tužba)", "datum_iso": "2026-11-15"}
    assert filtriraj_izvrsive([red], set()) == []
    assert filtriraj_izvrsive([red], {"r1"}) == [red]


# ── Stvaran Tesseract (CI produkciona slika): merenje ─────────────────────────────────────────────────────────

def _zapisi_izvestaj():
    put = os.getenv("VINDEX_OCR001_REPORT")
    if put:
        with open(put, "w", encoding="utf-8") as f:
            json.dump(IZVESTAJ, f, ensure_ascii=False, indent=1)


@treba_ocr
def test_ocr_B_skenirana_cirilicna_dostavnica(tmp_path):
    from uploaded_doc.extractor import _detect_ocr_lang, necitljive_strane_pdf
    (text, is_scanned, ocr_used, pages, conf), t, p = _izvuci(tmp_path, "B.pdf", B_pdf())
    cer, wer = _cer_wer("\n".join(B_REDOVI), text)
    IZVESTAJ["B_sken_cirilica"] = {"jezik": _detect_ocr_lang(), "ocr_used": ocr_used, "strana": len(pages or []),
                                   "cer": cer, "wer": wer, "conf": round(conf, 3) if conf else None, "sekundi": t,
                                   "datum_25_03_2025": "25.03.2025" in text,
                                   "primalac": "пример инвест тест" in _norm(text)}
    _zapisi_izvestaj()
    assert ocr_used is True and is_scanned is False
    assert "25.03.2025" in text, "kritičan datum dostave mora biti pročitan (ili dokument označen kao nepročitan)"
    assert necitljive_strane_pdf(p, pages) == []


@treba_ocr
def test_ocr_C_mesoviti_obe_strane_pokrivene(tmp_path):
    from uploaded_doc.extractor import necitljive_strane_pdf
    (text, is_scanned, ocr_used, pages, conf), t, p = _izvuci(tmp_path, "C.pdf", C_pdf())
    cer2, wer2 = _cer_wer("\n".join(C2_REDOVI), pages[1] if pages and len(pages) > 1 else "")
    IZVESTAJ["C_mesoviti"] = {"strana": len(pages or []), "strana_1_digitalna": "DIGITALNA STRANA JEDAN" in (pages or [""])[0],
                              "strana_2_cer": cer2, "strana_2_wer": wer2, "conf": round(conf, 3) if conf else None,
                              "sekundi": t, "oba_datuma": "17.03.2025" in text and "25.03.2025" in text}
    _zapisi_izvestaj()
    assert len(pages) == 2 and "DIGITALNA STRANA JEDAN" in pages[0]
    assert necitljive_strane_pdf(p, pages) == [] and len(pages[1].strip()) >= 30
    from uploaded_doc.extractor import _detect_ocr_lang
    if "srp" in _detect_ocr_lang().split("+"):
        assert "маркер" in _norm(pages[1]), pages[1][:200]          # sa ćiriličnim paketom: tačan marker skenirane strane
    elif os.getenv("VINDEX_EXPECT_SRP") == "1":
        pytest.fail("produkciona slika bez ćiriličnog OCR paketa")


@treba_ocr
@pytest.mark.parametrize("naziv,pdf", [
    ("okrenut_90", lambda: _spoji(_digitalni(C1_REDOVI), _sken_varijanta(C2_REDOVI, rotacija=90))),
    ("bled_kontrast_0_25", lambda: _spoji(_digitalni(C1_REDOVI), _sken_varijanta(C2_REDOVI, kontrast=0.25))),
])
def test_ocr_otezan_sken_procitan_ili_prijavljen_nikad_tiho_izgubljen(tmp_path, naziv, pdf):
    from shared.intake_worker import IntakeWorker
    (text, _s, ocr_used, pages, conf), t, p = _izvuci(tmp_path, naziv + ".pdf", pdf())
    cer, wer = _cer_wer("\n".join(C2_REDOVI), pages[1] if len(pages) > 1 else "")
    tacno_procitana = cer < 0.2                    # „pročitano“ = tačno pročitano, ne samo ≥ 30 znakova
    signali = IntakeWorker._nepotpuno_procitano(p, pages, ocr_used, conf)
    IZVESTAJ["otezano_" + naziv] = {"tacno_procitana": tacno_procitana, "signali_za_pregled": signali,
                                    "cer": cer, "wer": wer, "conf": round(conf, 3) if conf else None, "sekundi": t}
    _zapisi_izvestaj()
    assert tacno_procitana or signali, (naziv, cer, conf, pages[1][:120] if len(pages) > 1 else None)


@treba_ocr
def test_ocr_ceo_tok_tri_qa_dokumenta_do_predmeta(ok, monkeypatch):
    """Stvaran OCR → worker → pregled → prikačivanje u predmet; model (stranke) namerno vraća primaoca kao tužioca."""
    k, b = ok
    import shared.intake_extract as ex

    async def _model(t):
        return {"judge": (None, 0.0), "plaintiff": ("Пример Инвест Тест д.о.о.", 0.86), "defendant": (None, 0.0),
                "court": (None, 0.0), "law_cited": (None, 0.0)}
    monkeypatch.setattr(ex, "extract_free_text_entities", _model)
    rez = {}
    for ime, pdf in (("01_tuzba_digital_lat.pdf", A_pdf()), ("02_dostavnica_sken_cirilica.pdf", B_pdf()),
                     ("03_zapisnik_mesoviti_pdf.pdf", C_pdf())):
        jid = _otpremi(k, "A", pdf, ime=ime).json()["rezultati"][0]["job_id"]
        assert _obradi() is True
        g = k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje("A")).json()
        tuzilac = next((e["value"] for e in g["entiteti"] if e["entity_type"] == "plaintiff"), None)
        if g["job"]["status"] == "awaiting_review":
            assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=zaglavlje("A")).status_code == 200
        f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": PA}, headers=zaglavlje("A"))
        assert f.status_code == 200 and f.json()["prikacivanje"] == "POTPUNO", (ime, f.text)
        rez[ime] = {"tip": g["dokument"]["tip"], "ocr": g["dokument"]["ocr_koriscen"], "tuzilac": tuzilac,
                    "provere": [q["razlog"] for q in g["potrebne_provere"]]}
    docs = [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == PA]
    tekst = " ".join(d.get("tekst_sadrzaj") or "" for d in docs)
    IZVESTAJ["ceo_tok"] = {"dokumenata_u_predmetu": len(docs), "po_dokumentu": rez,
                           "kriticno_u_predmetu": {s: (s in tekst) for s in ("47.912,00 RSD", "17.03.2025", "25.03.2025", "TEST-2026-014")}}
    _zapisi_izvestaj()
    assert len(docs) == 3
    assert rez["01_tuzba_digital_lat.pdf"]["tuzilac"] is None                 # model je pogrešio ulogu; nije prihvaćeno
    assert rez["02_dostavnica_sken_cirilica.pdf"]["tuzilac"] is None
    assert all(IZVESTAJ["ceo_tok"]["kriticno_u_predmetu"].values()), IZVESTAJ["ceo_tok"]
    assert b.tabele["predmet_hronologija"] == [], "nijedan rok ne sme nastati iz ova tri dokumenta"
