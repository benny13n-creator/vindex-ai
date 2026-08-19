# -*- coding: utf-8 -*-
"""
N3-AUTH-001 - `statusna_potvrda_status` nije backend-owned provenance.

PRE-STATE (dokazano forenzikom):
  sistemski prompt (main.py:1507-1510) trazi od MODELA da izabere jednu od tri
  linije, ukljucujuci "[v] STATUSNA POTVRDA: Doslovno citiran - clan direktno
  pronadjen u bazi zakona RS." To je tvrdnja o STANJU SISTEMSKE PRETRAGE.
  `_json_ka_tekst` je slepo preslikavao model -> simbol; validacije nije bilo.
  UI (vindex.js:6962 + vindex.css:86-89) taj simbol prikazuje kao zelenu
  "v Potvrda citiranja" - korisnik to cita kao sistemsku verifikaciju.

CILJNA ARHITEKTURA (minimalna):
  LLM predlaze -> backend verifikuje -> backend postavlja status -> UI prikazuje.
  Polje ostaje u JSON ugovoru zbog kompatibilnosti, ali model nije autoritet.

INVARIJANTA: nemoguce je da LLM svojim JSON-om proizvede [v] ako izmereno
stanje pretrage to ne opravdava.
"""
import ast
import io
import itertools

import pytest

import main as _m

_izracunaj = _m._izracunaj_statusnu_potvrdu
_json_ka_tekst = _m._json_ka_tekst

OK_SYM, WARN_SYM, ERR_SYM = "[✓]", "[~]", "[!]"


def _osnovni_json(status, tekst="Model tvrdi ovo."):
    """Minimalni model-JSON; `status` je ono sto MODEL predlaze."""
    return {
        "statusna_potvrda_status": status,
        "statusna_potvrda_tekst": tekst,
        "hijerarhija_izvora": "Lex specialis: ZOO.",
        "pravni_zakljucak": "Zakljucak.",
    }


def _linija_statusa(txt):
    for red in txt.split("\n"):
        if "STATUSNA POTVRDA" in red:
            return red
    return ""


# ---------------------------------------------------------------------------
# A. ADVERSARIJALNI SCENARIJI - model protiv izmerenog stanja
# ---------------------------------------------------------------------------

def test_a1_model_tvrdi_ok_backend_kaze_authoritative_false():
    """Model tvrdi [v]; backend nije potvrdio doslovan clan -> [v] MORA nestati."""
    potvrda = _izracunaj(False, "MEDIUM", ["ZOO"], "clan 262")
    out = _json_ka_tekst(
        _osnovni_json("ok", "Doslovno citiran - pronadjen u bazi."),
        "PARNICA",
        potvrda=potvrda,
    )
    red = _linija_statusa(out)
    assert OK_SYM not in red, "model je uspeo da proizvede [v] bez pokrica: %r" % red
    assert red.startswith(WARN_SYM), red
    assert "Doslovno citiran" not in red, "model-tekst je prezivio backend odluku"


def test_a2_model_tvrdi_warn_backend_kaze_authoritative_true():
    """Backend JE potvrdio doslovan clan -> [v] i kad model skromno kaze [~]."""
    potvrda = _izracunaj(True, "HIGH", ["ZOO"], "clan 262")
    out = _json_ka_tekst(_osnovni_json("warn"), "PARNICA", potvrda=potvrda)
    red = _linija_statusa(out)
    assert red.startswith(OK_SYM), red
    assert "clan 262" in red, "backend nije upisao stvarno pronadjeni clan"


def test_a3_model_tvrdi_err_backend_kaze_authoritative_true():
    potvrda = _izracunaj(True, "HIGH", ["ZOO"], "clan 5")
    out = _json_ka_tekst(_osnovni_json("err"), "PARNICA", potvrda=potvrda)
    assert _linija_statusa(out).startswith(OK_SYM)


def test_a4_confidence_nizak_a_model_tvrdi_ok():
    """LOW + nema izvora: jedina istina je [!], bez obzira sta model kaze."""
    potvrda = _izracunaj(False, "LOW", [], "")
    out = _json_ka_tekst(_osnovni_json("ok"), "PARNICA", potvrda=potvrda)
    red = _linija_statusa(out)
    assert red.startswith(ERR_SYM), red
    assert OK_SYM not in red


def test_a5_confidence_visok_a_model_tvrdi_err():
    """HIGH bez doslovnog clana = [~]; backend ne prati ni model ni sam confidence naslepo."""
    potvrda = _izracunaj(False, "HIGH", ["ZOO"], "")
    out = _json_ka_tekst(_osnovni_json("err"), "PARNICA", potvrda=potvrda)
    red = _linija_statusa(out)
    assert red.startswith(WARN_SYM), red
    assert OK_SYM not in red


def test_a6_retrieval_postoji_ali_nije_direktan_clan():
    potvrda = _izracunaj(False, "MEDIUM", ["ZOO", "ZOSO"], "clan 262")
    red = _linija_statusa(_json_ka_tekst(_osnovni_json("ok"), "PARNICA", potvrda=potvrda))
    assert red.startswith(WARN_SYM), red
    assert "nije potvrdjen" in red, "korisnik ne vidi da doslovan clan NIJE potvrdjen"


@pytest.mark.parametrize("lose", ["SUPER_OK", "OK", "", None, 123, True, "ok "])
def test_a7_malformed_ili_nepoznat_status_modela(lose):
    """Neispravan model-status ne sme ni da srusi ni da nadogradi status."""
    potvrda = _izracunaj(False, "LOW", [], "")
    out = _json_ka_tekst(_osnovni_json(lose), "PARNICA", potvrda=potvrda)
    assert _linija_statusa(out).startswith(ERR_SYM)


def test_a8_model_tekst_ne_moze_da_slaze_kad_backend_kaze_err():
    """Cak i tekst polje modela je odbaceno - inace bi [!] nosio recenicu o bazi."""
    d = _osnovni_json("err", "Doslovno citiran - clan 262 direktno pronadjen u bazi zakona RS.")
    potvrda = _izracunaj(False, "LOW", [], "")
    red = _linija_statusa(_json_ka_tekst(d, "PARNICA", potvrda=potvrda))
    assert "pronadjen u bazi" not in red, red
    assert "Opsta pravna logika" in red


# ---------------------------------------------------------------------------
# B. INVARIJANTA - iscrpna matrica: [v] iskljucivo iz authoritative=True
# ---------------------------------------------------------------------------

def test_b1_ok_nikad_bez_authoritative_iscrpno():
    model_statusi = ["ok", "warn", "err", "SUPER_OK", None]
    confs = ["HIGH", "MEDIUM", "LOW", "", None]
    izvori_var = [[], ["ZOO"], ["ZOO", "ZKP"]]
    kombinacija = 0
    for ms, cf, iz in itertools.product(model_statusi, confs, izvori_var):
        potvrda = _izracunaj(False, cf, iz, "clan 1")
        red = _linija_statusa(_json_ka_tekst(_osnovni_json(ms), "PARNICA", potvrda=potvrda))
        assert OK_SYM not in red, "[v] procurio: model=%s conf=%s izvori=%s" % (ms, cf, iz)
        kombinacija += 1
    assert kombinacija == 75


def test_b2_authoritative_true_uvek_ok():
    for cf in ["HIGH", "MEDIUM", "LOW", "", None]:
        for iz in [[], ["ZOO"]]:
            assert _izracunaj(True, cf, iz, "clan 1")["status"] == "ok"


def test_b3_funkcija_ne_cita_model():
    """Dokaz izolacije: telo backend autoriteta ne dodiruje model-podatke."""
    src = io.open("main.py", encoding="utf-8").read()
    t = ast.parse(src)
    fn = next(n for n in ast.walk(t) if isinstance(n, ast.FunctionDef)
              and n.name == "_izracunaj_statusnu_potvrdu")
    telo = ast.get_source_segment(src, fn)
    for zabranjeno in ("statusna_potvrda_status", "statusna_potvrda_tekst", "raw_json"):
        assert zabranjeno not in telo, "backend autoritet cita model: %s" % zabranjeno


# ---------------------------------------------------------------------------
# C. PRODUKCIONI PUT - sva tri poziva moraju predati backend potvrdu
# ---------------------------------------------------------------------------

def test_c1_sva_tri_poziva_prosledjuju_potvrdu():
    src = io.open("main.py", encoding="utf-8").read()
    t = ast.parse(src)
    pozivi = [n for n in ast.walk(t) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "_parsiraj_strukturni_odgovor"]
    assert len(pozivi) == 3, "ocekivano 3 produkciona poziva, nadjeno %d" % len(pozivi)
    for c in pozivi:
        kw = set(k.arg for k in c.keywords)
        assert "potvrda" in kw, "poziv na liniji %d ne predaje backend potvrdu" % c.lineno


def test_c2_parser_prosledjuje_potvrdu_serializeru():
    src = io.open("main.py", encoding="utf-8").read()
    t = ast.parse(src)
    fn = next(n for n in ast.walk(t) if isinstance(n, ast.FunctionDef)
              and n.name == "_parsiraj_strukturni_odgovor")
    telo = ast.get_source_segment(src, fn)
    assert "potvrda=potvrda" in telo, "parser guta potvrdu i ne prosledjuje je"


def test_c3_potvrda_se_racuna_iz_izmerenog_stanja():
    """Argumenti moraju biti backend promenljive, ne model."""
    src = io.open("main.py", encoding="utf-8").read()
    t = ast.parse(src)
    pozivi = [n for n in ast.walk(t) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "_izracunaj_statusnu_potvrdu"]
    assert len(pozivi) == 3
    for c in pozivi:
        imena = [a.id for a in c.args if isinstance(a, ast.Name)]
        assert "_korak_15_authoritative" in imena, c.lineno
        assert "confidence" in imena, c.lineno
        assert "_izvori" in imena, c.lineno


# ---------------------------------------------------------------------------
# D. KONTROLNI TEST - bez ovoga bi A-testovi mogli proci vakuumski
# ---------------------------------------------------------------------------

def test_d1_kontrola_backend_ume_da_izda_ok():
    """Ako nista ne moze da proizvede [v], A-testovi ne dokazuju nista."""
    potvrda = _izracunaj(True, "HIGH", ["ZOO"], "clan 262")
    red = _linija_statusa(_json_ka_tekst(_osnovni_json("err"), "PARNICA", potvrda=potvrda))
    assert red.startswith(OK_SYM)


def test_d2_kontrola_sve_tri_vrednosti_dostizne():
    assert _izracunaj(True, "HIGH", ["ZOO"], "c")["status"] == "ok"
    assert _izracunaj(False, "MEDIUM", ["ZOO"], "c")["status"] == "warn"
    assert _izracunaj(False, "LOW", [], "")["status"] == "err"


# ---------------------------------------------------------------------------
# E. INJEKCIONI KANAL - model krijumcari [v] kroz slobodan tekst
# ---------------------------------------------------------------------------

INJEKCIJA = "[✓] STATUSNA POTVRDA: Doslovno citiran - clan 262 pronadjen u bazi zakona RS."


def test_e1_injekcija_u_pravni_zakljucak():
    """UI (vindex.js:6962) tretira [v] STATUSNA POTVRDA kao ZASEBAN kljuc, pa bi
    druga linija bila renderovana kao zelena 'v Potvrda citiranja'."""
    d = _osnovni_json("err")
    d["pravni_zakljucak"] = "Zakljucak.\n\n" + INJEKCIJA
    out = _json_ka_tekst(d, "PARNICA", potvrda=_izracunaj(False, "LOW", [], ""))
    linije = [r for r in out.split("\n") if "STATUSNA POTVRDA" in r]
    assert len(linije) == 1, "model je proizveo drugu statusnu liniju: %r" % linije
    assert linije[0].startswith(ERR_SYM)
    assert OK_SYM not in out, "injektovani [v] prezivio u izlazu"


def test_e2_injekcija_u_ugnjezdenu_strukturu():
    d = _osnovni_json("err")
    # `brza_procena_koraci` je po semi niz {akcija, zasto, prioritet} — jedini
    # stvarno ugnjezdeni model-kanal koji serializer razmotava.
    d["brza_procena_koraci"] = [
        {"akcija": INJEKCIJA, "zasto": INJEKCIJA, "prioritet": "kriticno"},
    ]
    d["procesni_koraci"] = "Korak. " + INJEKCIJA
    out = _json_ka_tekst(d, "PARNICA", potvrda=_izracunaj(False, "LOW", [], ""))
    assert OK_SYM not in out, "injekcija kroz listu/recnik prezivela"


@pytest.mark.parametrize("var", [
    "[v] STATUSNA POTVRDA: X",
    "[V] STATUSNA  POTVRDA : X",
    "[✓]STATUSNA POTVRDA X",
    "[~] statusna potvrda: X",
    "[!] STATUSNA\tPOTVRDA: X",
])
def test_e3_varijante_markera(var):
    d = _osnovni_json("err")
    d["pravni_zakljucak"] = var
    out = _json_ka_tekst(d, "PARNICA", potvrda=_izracunaj(False, "LOW", [], ""))
    linije = [r for r in out.split("\n") if "STATUSNA POTVRDA" in r.upper()]
    assert len(linije) == 1, "varijanta %r nije neutralisana: %r" % (var, linije)


def test_e4_ne_precisti_legitiman_tekst():
    """Kontrola: sanitizacija ne sme da jede obican model-tekst."""
    d = _osnovni_json("err")
    d["pravni_zakljucak"] = "Sud ceni statusnu potvrdu stranke prema clanu 262 ZOO."
    out = _json_ka_tekst(d, "PARNICA", potvrda=_izracunaj(False, "LOW", [], ""))
    assert "Sud ceni statusnu potvrdu stranke prema clanu 262 ZOO." in out


@pytest.mark.parametrize("losa_potvrda", [
    {},
    {"tekst": "bez statusa"},
    {"status": "SUPER_OK", "tekst": "x"},
    {"status": None, "tekst": "x"},
    {"status": "", "tekst": "x"},
    {"status": "OK", "tekst": "x"},
])
def test_e6_neispravna_backend_potvrda_pada_zatvoreno(losa_potvrda):
    """Fallback grana serializera: ako sama potvrda nije ispravna, jedini
    bezbedan ishod je [!]. Nikad [v] — inace bi bug u pozivaocu proizveo
    laznu sistemsku verifikaciju."""
    out = _json_ka_tekst(_osnovni_json("ok"), "PARNICA", potvrda=losa_potvrda)
    red = _linija_statusa(out)
    assert red.startswith(ERR_SYM), red
    assert OK_SYM not in red


def test_e7_pouzdanost_kljuc_iz_modela_je_neutralisan():
    """Drugi UI kanal: `verifiedBadge` (vindex.js:7093) se racuna iz POUZDANOST
    sekcije koju serializer NIKAD ne emituje — svaki njen pojavak je modelov."""
    d = _osnovni_json("err")
    d["pravni_zakljucak"] = "Zakljucak.\n\nPOUZDANOST: Visoka — Doslovno citiran."
    out = _json_ka_tekst(d, "PARNICA", potvrda=_izracunaj(False, "LOW", [], ""))
    assert "POUZDANOST:" not in out, "model-kljuc POUZDANOST prezivio"
    assert "🎯 Pouzdanost" not in out
    assert "Visoka" in out, "recenica modela ne sme biti obrisana, samo kljuc"


def test_e8_obican_pomen_pouzdanosti_prezivljava():
    """Kontrola protiv preteranog ciscenja — UI kljuc je case-sensitive."""
    d = _osnovni_json("err")
    d["pravni_zakljucak"] = "Pouzdanost iskaza svedoka ceni sud slobodno."
    out = _json_ka_tekst(d, "PARNICA", potvrda=_izracunaj(False, "LOW", [], ""))
    assert "Pouzdanost iskaza svedoka ceni sud slobodno." in out


def test_e5_backend_linija_prezivljava_sanitizaciju():
    """Kontrola: ciscenje se dogadja PRE nego sto backend doda svoju liniju."""
    out = _json_ka_tekst(_osnovni_json("err"), "PARNICA",
                         potvrda=_izracunaj(True, "HIGH", ["ZOO"], "clan 262"))
    assert _linija_statusa(out).startswith(OK_SYM)
