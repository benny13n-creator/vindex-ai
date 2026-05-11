# -*- coding: utf-8 -*-
"""
Phase 4.1 unit tests — drafting module.
Tests: templates registry, compliance rules, router (mocked LLM), API endpoint.
"""
import sys
import os
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

from drafting.templates import TEMPLATES, get_types_list, SABLON_UGOVOR_NEODREDJENO
from drafting.compliance import (
    proveri_uskladjenost,
    formatiraj_violations,
    _parse_mesece,
    _parse_dane,
    ZR_PROBNI_RAD_MAX_MESECI,
    ZR_OTKAZNI_ROK_MIN_DANA,
    ZR_KONKURENTSKA_MAX_GODINA,
    ZR_GODISNJI_ODMOR_MIN_DANA,
    ZR_ODREDJENO_MAX_MESECI,
    MIN_ZARADA_BRUTO_RSD,
)
from drafting.router import (
    _ekstraktuj_json,
    _popuni_sablon,
    _pripremi_ugovor_fields,
    _pripremi_sporazum_fields,
    _pripremi_punomocje_fields,
    generate_draft,
)


# ─────────────────────────────────────────────────────────────────────────────
# SEKCIJA 1: TEMPLATES REGISTRY (15 testova)
# ─────────────────────────────────────────────────────────────────────────────

def test_templates_has_all_five_types():
    assert set(TEMPLATES.keys()) == {
        "ugovor_neodredjeno",
        "ugovor_odredjeno",
        "aneks",
        "sporazumni_raskid",
        "punomocje",
    }


def test_each_template_has_required_keys():
    for vrsta, tpl in TEMPLATES.items():
        assert "label" in tpl, f"{vrsta} nema label"
        assert "opis_hint" in tpl, f"{vrsta} nema opis_hint"
        assert "ekstrakcioni_prompt" in tpl, f"{vrsta} nema ekstrakcioni_prompt"
        assert "sablon" in tpl, f"{vrsta} nema sablon"
        assert "compliance_tip" in tpl, f"{vrsta} nema compliance_tip"


def test_ugovor_neodredjeno_label():
    assert "neodređeno" in TEMPLATES["ugovor_neodredjeno"]["label"].lower()


def test_ugovor_odredjeno_label():
    assert "određeno" in TEMPLATES["ugovor_odredjeno"]["label"].lower()


def test_aneks_label():
    assert "aneks" in TEMPLATES["aneks"]["label"].lower()


def test_sporazumni_raskid_label():
    assert "raskid" in TEMPLATES["sporazumni_raskid"]["label"].lower()


def test_punomocje_label():
    assert "punomoćje" in TEMPLATES["punomocje"]["label"].lower()


def test_ugovor_templates_have_compliance_tip():
    assert TEMPLATES["ugovor_neodredjeno"]["compliance_tip"] == "ugovor_o_radu"
    assert TEMPLATES["ugovor_odredjeno"]["compliance_tip"] == "ugovor_o_radu"


def test_non_ugovor_templates_have_no_compliance():
    assert TEMPLATES["aneks"]["compliance_tip"] is None
    assert TEMPLATES["sporazumni_raskid"]["compliance_tip"] is None
    assert TEMPLATES["punomocje"]["compliance_tip"] is None


def test_ugovor_neodredjeno_sablon_contains_key_placeholders():
    sablon = TEMPLATES["ugovor_neodredjeno"]["sablon"]
    for p in ["{POSLODAVAC_IME}", "{ZAPOSLENI_IME}", "{DATUM_POCETKA}", "{OSNOVNA_ZARADA}"]:
        assert p in sablon, f"Nedostaje {p} u šablonu ugovor_neodredjeno"


def test_ugovor_odredjeno_sablon_contains_trajanje():
    sablon = TEMPLATES["ugovor_odredjeno"]["sablon"]
    assert "{TRAJANJE_ODREDJENO}" in sablon
    assert "{RAZLOG_ODREDJENOG}" in sablon


def test_aneks_sablon_contains_izmene():
    sablon = TEMPLATES["aneks"]["sablon"]
    assert "{IZMENE_OPIS}" in sablon
    assert "{DATUM_PRIMENE}" in sablon


def test_sporazumni_raskid_sablon_contains_datum_prestanka():
    sablon = TEMPLATES["sporazumni_raskid"]["sablon"]
    assert "{DATUM_PRESTANKA}" in sablon


def test_punomocje_sablon_contains_predmet():
    sablon = TEMPLATES["punomocje"]["sablon"]
    assert "{PREDMET_PUNOMOCJA}" in sablon
    assert "{VLASTODAVAC_IME}" in sablon


def test_get_types_list_returns_five():
    tipovi = get_types_list()
    assert len(tipovi) == 5


def test_get_types_list_structure():
    tipovi = get_types_list()
    for t in tipovi:
        assert "vrsta" in t
        assert "label" in t
        assert "opis_hint" in t


# ─────────────────────────────────────────────────────────────────────────────
# SEKCIJA 2: COMPLIANCE HELPERS (6 testova)
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_mesece_broj():
    assert _parse_mesece("3") == 3.0


def test_parse_mesece_meseci():
    assert _parse_mesece("6 meseci") == 6.0


def test_parse_mesece_godina():
    assert _parse_mesece("2 godine") == 24.0


def test_parse_mesece_prazno():
    assert _parse_mesece("") is None


def test_parse_dane_broj():
    assert _parse_dane("15 radnih dana") == 15.0


def test_parse_dane_prazno():
    assert _parse_dane("") is None


# ─────────────────────────────────────────────────────────────────────────────
# SEKCIJA 3: COMPLIANCE RULES — pass/fail (16 testova)
# ─────────────────────────────────────────────────────────────────────────────

def test_probni_rad_ok():
    violations = proveri_uskladjenost({"probni_rad": "3 meseca"}, "ugovor_neodredjeno")
    probni = next((v for v in violations if v["pravilo"] == "probni_rad"), None)
    assert probni is not None
    assert probni["status"] == "ok"


def test_probni_rad_krsi():
    violations = proveri_uskladjenost({"probni_rad": "9 meseci"}, "ugovor_neodredjeno")
    probni = next((v for v in violations if v["pravilo"] == "probni_rad"), None)
    assert probni is not None
    assert probni["status"] == "krsi"
    assert "ZR čl. 36" in probni["zakon"]


def test_otkazni_rok_zaposleni_ok():
    violations = proveri_uskladjenost(
        {"otkazni_rok_zaposleni": "15 radnih dana"}, "ugovor_neodredjeno"
    )
    r = next((v for v in violations if "otkazni_rok_zaposleni" in v["pravilo"]), None)
    assert r is not None
    assert r["status"] == "ok"


def test_otkazni_rok_zaposleni_krsi():
    violations = proveri_uskladjenost(
        {"otkazni_rok_zaposleni": "5 dana"}, "ugovor_neodredjeno"
    )
    r = next((v for v in violations if "otkazni_rok_zaposleni" in v["pravilo"]), None)
    assert r is not None
    assert r["status"] == "krsi"


def test_otkazni_rok_poslodavac_ok():
    violations = proveri_uskladjenost(
        {"otkazni_rok_poslodavac": "8 dana"}, "ugovor_neodredjeno"
    )
    r = next((v for v in violations if "otkazni_rok_poslodavac" in v["pravilo"]), None)
    assert r is not None
    assert r["status"] == "ok"


def test_otkazni_rok_poslodavac_krsi():
    violations = proveri_uskladjenost(
        {"otkazni_rok_poslodavac": "3 dana"}, "ugovor_neodredjeno"
    )
    r = next((v for v in violations if "otkazni_rok_poslodavac" in v["pravilo"]), None)
    assert r is not None
    assert r["status"] == "krsi"
    assert "ZR čl. 189" in r["zakon"]


def test_konkurentska_ok():
    violations = proveri_uskladjenost(
        {"ima_konkurentsku": True, "konkurentska_trajanje": "1 godina"},
        "ugovor_neodredjeno",
    )
    r = next((v for v in violations if v["pravilo"] == "konkurentska_klauzula"), None)
    assert r is not None
    assert r["status"] == "ok"


def test_konkurentska_krsi():
    violations = proveri_uskladjenost(
        {"ima_konkurentsku": True, "konkurentska_trajanje": "3 godine"},
        "ugovor_neodredjeno",
    )
    r = next((v for v in violations if v["pravilo"] == "konkurentska_klauzula"), None)
    assert r is not None
    assert r["status"] == "krsi"
    assert "ZR čl. 162" in r["zakon"]


def test_konkurentska_absent_skipped():
    violations = proveri_uskladjenost({"ima_konkurentsku": False}, "ugovor_neodredjeno")
    r = next((v for v in violations if v["pravilo"] == "konkurentska_klauzula"), None)
    assert r is None


def test_godisnji_odmor_ok():
    violations = proveri_uskladjenost({"godisnji_odmor_dani": "20"}, "ugovor_neodredjeno")
    r = next((v for v in violations if v["pravilo"] == "godisnji_odmor"), None)
    assert r is not None
    assert r["status"] == "ok"


def test_godisnji_odmor_krsi():
    violations = proveri_uskladjenost({"godisnji_odmor_dani": "10"}, "ugovor_neodredjeno")
    r = next((v for v in violations if v["pravilo"] == "godisnji_odmor"), None)
    assert r is not None
    assert r["status"] == "krsi"
    assert "ZR čl. 69" in r["zakon"]


def test_minimalna_zarada_ok():
    violations = proveri_uskladjenost({"osnovna_zarada": "150000"}, "ugovor_neodredjeno")
    r = next((v for v in violations if v["pravilo"] == "minimalna_zarada"), None)
    assert r is not None
    assert r["status"] == "ok"


def test_minimalna_zarada_krsi():
    violations = proveri_uskladjenost({"osnovna_zarada": "30000"}, "ugovor_neodredjeno")
    r = next((v for v in violations if v["pravilo"] == "minimalna_zarada"), None)
    assert r is not None
    assert r["status"] == "krsi"
    assert "ZR čl. 111" in r["zakon"]


def test_odredjeno_trajanje_ok():
    violations = proveri_uskladjenost({"trajanje_odredjeno": "12 meseci"}, "ugovor_odredjeno")
    r = next((v for v in violations if v["pravilo"] == "odredjeno_trajanje"), None)
    assert r is not None
    assert r["status"] == "ok"


def test_odredjeno_trajanje_krsi():
    violations = proveri_uskladjenost({"trajanje_odredjeno": "3 godine"}, "ugovor_odredjeno")
    r = next((v for v in violations if v["pravilo"] == "odredjeno_trajanje"), None)
    assert r is not None
    assert r["status"] == "krsi"
    assert "ZR čl. 37" in r["zakon"]


def test_compliance_empty_fields_returns_empty():
    violations = proveri_uskladjenost({}, "ugovor_neodredjeno")
    assert violations == []


# ─────────────────────────────────────────────────────────────────────────────
# SEKCIJA 4: ROUTER — popunjavanje šablona (8 testova)
# ─────────────────────────────────────────────────────────────────────────────

def test_ekstraktuj_json_clean():
    raw = '{"ime": "Petar", "zarada": "100000"}'
    result = _ekstraktuj_json(raw)
    assert result == {"ime": "Petar", "zarada": "100000"}


def test_ekstraktuj_json_with_fences():
    raw = '```json\n{"key": "val"}\n```'
    result = _ekstraktuj_json(raw)
    assert result == {"key": "val"}


def test_ekstraktuj_json_invalid_returns_empty():
    result = _ekstraktuj_json("nije validan JSON")
    assert result == {}


def test_popuni_sablon_fills_known():
    sablon = "Ime: {IME}, Zarada: {ZARADA}"
    filled = _popuni_sablon(sablon, {"ime": "Petar", "zarada": "100000"})
    assert "Petar" in filled
    assert "100000" in filled


def test_popuni_sablon_fills_missing_with_popuniti():
    sablon = "Sud: {SUD_NAZIV}"
    filled = _popuni_sablon(sablon, {})
    assert "POPUNITI" in filled


def test_pripremi_ugovor_fields_probni_rad():
    fields = {"probni_rad": "3 meseca"}
    out = _pripremi_ugovor_fields(fields, "ugovor_neodredjeno")
    assert "3 meseca" in out["probni_rad_clan"]
    assert "čl. 36" in out["probni_rad_clan"]


def test_pripremi_ugovor_fields_no_probni_rad():
    fields = {}
    out = _pripremi_ugovor_fields(fields, "ugovor_neodredjeno")
    assert "nije ugovoren" in out["probni_rad_clan"].lower()


def test_pripremi_ugovor_fields_konkurentska():
    fields = {
        "ima_konkurentsku": True,
        "konkurentska_trajanje": "2 godine",
        "konkurentska_naknada_procenat": "30",
    }
    out = _pripremi_ugovor_fields(fields, "ugovor_neodredjeno")
    assert "2 godine" in out["konkurentska_clan"]
    assert "30%" in out["konkurentska_clan"]


# ─────────────────────────────────────────────────────────────────────────────
# SEKCIJA 5: generate_draft (mocked LLM) (5 testova)
# ─────────────────────────────────────────────────────────────────────────────

_FAKE_FIELDS_NEODREDJENO = json.dumps({
    "poslodavac_ime": "TechCorp d.o.o.",
    "poslodavac_adresa": "Beograd",
    "zaposleni_ime": "Ana Anić",
    "zaposleni_jmbg": "1234567890123",
    "zaposleni_adresa": "Novi Sad",
    "radno_mesto": "Software Developer",
    "opis_posla": "Razvoj softvera",
    "mesto_rada": "Beograd",
    "osnovna_zarada": "150000",
    "rok_isplate": "10",
    "datum_pocetka": "01.06.2026.",
    "radno_vreme": "40",
    "otkazni_rok_zaposleni": "15 radnih dana",
    "otkazni_rok_poslodavac": "15 radnih dana",
    "probni_rad": "3 meseca",
    "godisnji_odmor_dani": "20",
    "ima_tajnost": "true",
    "tajnost_rok": "2 godine",
    "ima_konkurentsku": "false",
    "datum": "11.05.2026.",
    "mesto": "Beograd",
})


def test_generate_draft_neodredjeno_success():
    with patch("drafting.router._call_openai", return_value=_FAKE_FIELDS_NEODREDJENO):
        result = generate_draft("ugovor_neodredjeno", "TechCorp zapošljava Anu Anić")
    assert result["status"] == "success"
    assert "TechCorp" in result["data"]
    assert "Ana Anić" in result["data"]
    assert "NAPOMENA SISTEMA" in result["data"]


def test_generate_draft_includes_compliance():
    with patch("drafting.router._call_openai", return_value=_FAKE_FIELDS_NEODREDJENO):
        result = generate_draft("ugovor_neodredjeno", "TechCorp zapošljava Anu Anić")
    assert result["status"] == "success"
    assert "VINDEX COMPLIANCE" in result["data"]


def test_generate_draft_unknown_vrsta():
    result = generate_draft("nepostojeci_tip", "neki opis")
    assert result["status"] == "error"
    assert "nepostojeci_tip" in result["message"]


def test_generate_draft_sporazumni_raskid():
    fake = json.dumps({
        "poslodavac_ime": "LogiTech",
        "zaposleni_ime": "Petar Petrović",
        "datum_prestanka": "31.05.2026.",
        "ima_otpremninu": "true",
        "otpremnina_iznos": "150000",
        "datum": "11.05.2026.",
        "mesto": "Beograd",
    })
    with patch("drafting.router._call_openai", return_value=fake):
        result = generate_draft("sporazumni_raskid", "Raskid sa Petrom")
    assert result["status"] == "success"
    assert "LogiTech" in result["data"]
    assert "150000" in result["data"]


def test_generate_draft_punomocje():
    fake = json.dumps({
        "vlastodavac_ime": "Jovana Marković",
        "vlastodavac_jmbg": "9876543210987",
        "vlastodavac_adresa": "Beograd",
        "punomocnik_ime": "Milan Petrović",
        "punomocnik_adresa": "Beograd",
        "predmet_punomocja": "zastupa pred svim sudovima",
        "rok_vazenja": "do opoziva",
        "ima_supstituciju": "false",
        "datum": "11.05.2026.",
        "mesto": "Beograd",
    })
    with patch("drafting.router._call_openai", return_value=fake):
        result = generate_draft("punomocje", "Jovana ovlašćuje Milana")
    assert result["status"] == "success"
    assert "Jovana Marković" in result["data"]
    assert "do opoziva" in result["data"]


# ─────────────────────────────────────────────────────────────────────────────
# SEKCIJA 6: formatiraj_violations (4 testa)
# ─────────────────────────────────────────────────────────────────────────────

def test_formatiraj_prazna_lista():
    assert formatiraj_violations([]) == ""


def test_formatiraj_krsi_sadrzaj():
    v = [{"pravilo": "probni_rad", "zakon": "ZR čl. 36", "status": "krsi",
          "poruka": "Prelazi max."}]
    tekst = formatiraj_violations(v)
    assert "KRŠENJA" in tekst
    assert "ZR čl. 36" in tekst


def test_formatiraj_ok_sadrzaj():
    v = [{"pravilo": "godisnji_odmor", "zakon": "ZR čl. 69", "status": "ok",
          "poruka": "U skladu."}]
    tekst = formatiraj_violations(v)
    assert "PROVERENE ODREDBE" in tekst


def test_formatiraj_sadrzi_disclaimer():
    v = [{"pravilo": "x", "zakon": "ZR", "status": "ok", "poruka": "ok"}]
    tekst = formatiraj_violations(v)
    assert "isključivo informativna" in tekst
