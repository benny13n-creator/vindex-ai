# -*- coding: utf-8 -*-
"""
Z017.18 — UVOZ IZ DOKUMENTA (Smart Intake), A7.

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. „PROVERA JE ZAKAZANA" NIJE „NEMA SUKOBA".
     Finalizovanje uvoza pravi predmet i ZAKAZUJE proveru sukoba; rezultat
     stize kasnije, kroz dogadjaj. Nijedno od tri stanja NE ZNACI da sukoba
     nema. `COI_FAILED` znaci da provera nece biti izvrsena NIKADA — to je
     nalaz, ne fusnota. Odsustvo alarma nije dokaz o odsustvu sukoba (S6).
     `test_coi_stanja_su_razdvojena`, `test_nepoznat_coi_je_neprimenljiv`.

  2. ODSUTNA VREDNOST NIJE PRAZAN STRING.
     `value: null` znaci da izvlacenje NIJE naslo podatak.
     `test_odsutna_vrednost_nije_prazna`.

  3. PREGLED SE TRAZI FAIL-CLOSED U TRI SMERA.
     Server kaze `needs_review`, ILI je pouzdanost ispod praga, ILI podatak
     uopste nije nadjen. `test_pregled_iz_tri_razloga`.

  4. NESIGURAN KLIJENT SE NE POGADJA.
     Dva istoimena klijenta -> server izricito kaze `klijent_nesiguran`.
     `test_nesiguran_klijent_se_ne_gubi`.

  5. „ROK NIJE DODAT" NE RAZLIKUJE DVA SLUCAJA BEZ RAZLOGA.
     „dokument nema rok" i „rok nije dovoljno dokazan" nisu isto.
     `test_razlog_preskocenog_roka_se_cuva`.

  6. PREKINUT BATCH SE NE PRECUTKUJE.
     Fajlovi koji nisu ni zapoceti moraju biti imenovani.
     `test_prekinut_batch_imenuje_preostale`.
"""
import json
import os
import shutil
import subprocess
import textwrap

import pytest

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V2 = os.path.join(KOREN, "v2").replace("\\", "/")

node = shutil.which("node")
nodemark = pytest.mark.skipif(node is None, reason="node nije dostupan")


def _js(telo: str):
    skripta = textwrap.dedent(f"""
        import * as U from "file:///{V2}/domain/uvoz.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


ISHOD = {"ok": True, "predmet_id": "p1", "naziv": "P 4010/2026",
         "coi_status": "COI_PENDING", "coi_event_id": "e1",
         "klijent_dodat": True, "klijent_nesiguran": False,
         "klijent_kandidati": [], "rok_dodat": True,
         "rok_preskocen_razlog": None, "dokument_povezan": True}


def _i(o):
    return _js(f"return U.uIshodUvoza({_j(o)});")


# ── 1. COI ───────────────────────────────────────────────────────────────────
@nodemark
def test_coi_stanja_su_razdvojena():
    z = _i(ISHOD)
    assert (z["coiZakazana"], z["coiOtkazala"], z["coiNeprimenljiva"]) == (True, False, False)
    f = _i(dict(ISHOD, coi_status="COI_FAILED"))
    assert (f["coiZakazana"], f["coiOtkazala"], f["coiNeprimenljiva"]) == (False, True, False)
    n = _i(dict(ISHOD, coi_status="COI_NOT_APPLICABLE"))
    assert (n["coiZakazana"], n["coiOtkazala"], n["coiNeprimenljiva"]) == (False, False, True)


@nodemark
def test_nepoznat_coi_je_neprimenljiv():
    """Nepoznato stanje se NE proglasava zakazanom proverom — fail-closed."""
    for v in ('""', '"NESTO"', "null"):
        r = _js('return U.uIshodUvoza({ coi_status: ' + v + " });")
        assert r["coiZakazana"] is False, v


@nodemark
def test_odsutan_ishod_ne_tvrdi_zakazanu_proveru():
    r = _js("return U.uIshodUvoza(null);")
    assert r["coiZakazana"] is False
    assert r["uspeh"] is False


# ── 2. Odsutna vrednost ──────────────────────────────────────────────────────
@nodemark
def test_odsutna_vrednost_nije_prazna():
    r = _js('return U.uEntitet({ entity_id: "a", entity_type: "amount", '
            "value: null, confidence: 0 });")
    assert r["vrednost"] is None
    assert r["nadjen"] is False


@nodemark
def test_nadjena_vrednost_je_nadjena():
    r = _js('return U.uEntitet({ entity_id: "a", entity_type: "case_number", '
            'value: "P 1/2026", confidence: 0.95 });')
    assert r["vrednost"] == "P 1/2026"
    assert r["nadjen"] is True


# ── 3. Pregled fail-closed ───────────────────────────────────────────────────
@nodemark
def test_pregled_iz_tri_razloga():
    # 1) server kaze
    a = _js('return U.uEntitet({ entity_id: "a", value: "x", confidence: 0.99, '
            "needs_review: true }).trebaPregled;")
    # 2) pouzdanost ispod praga
    b = _js('return U.uEntitet({ entity_id: "b", value: "x", confidence: 0.3 })'
            ".trebaPregled;")
    # 3) podatak nije nadjen
    c = _js('return U.uEntitet({ entity_id: "c", value: null, confidence: 0.99 })'
            ".trebaPregled;")
    assert (a, b, c) == (True, True, True)


@nodemark
def test_pouzdan_i_nadjen_podatak_ne_trazi_pregled():
    r = _js('return U.uEntitet({ entity_id: "a", value: "x", confidence: 0.95, '
            "needs_review: false }).trebaPregled;")
    assert r is False


@nodemark
def test_string_true_needs_review_ne_prolazi_kao_false():
    """Labava provera bi `needs_review: "false"` procitala kao istinu."""
    r = _js('return U.uEntitet({ entity_id: "a", value: "x", confidence: 0.95, '
            'needs_review: "false" }).trebaPregled;')
    assert r is False


# ── 4. Klijent ───────────────────────────────────────────────────────────────
@nodemark
def test_nesiguran_klijent_se_ne_gubi():
    r = _i(dict(ISHOD, klijent_dodat=False, klijent_nesiguran=True,
                klijent_kandidati=["a", "b", "c"]))
    assert r["klijentNesiguran"] is True
    assert r["klijentKandidata"] == 3
    assert r["klijentDodat"] is False


@nodemark
def test_klijent_dodat_mora_biti_izricit():
    r = _i(dict(ISHOD, klijent_dodat="true"))
    assert r["klijentDodat"] is False


# ── 5. Rok ───────────────────────────────────────────────────────────────────
@nodemark
def test_razlog_preskocenog_roka_se_cuva():
    r = _i(dict(ISHOD, rok_dodat=False,
                rok_preskocen_razlog="pouzdanost ispod praga"))
    assert r["rokDodat"] is False
    assert r["rokRazlog"] == "pouzdanost ispod praga"


@nodemark
def test_bez_razloga_rok_nije_preskocen_nego_ga_nema():
    r = _i(dict(ISHOD, rok_dodat=False, rok_preskocen_razlog=None))
    assert r["rokDodat"] is False
    assert r["rokRazlog"] == ""


# ── 6. Batch ─────────────────────────────────────────────────────────────────
@nodemark
def test_prekinut_batch_imenuje_preostale():
    r = _js('return U.uPoslove({ rezultati: [{ job_id: "j1", filename: "a.pdf" }], '
            'ukupno: 3, nastavlja: true, preostali_fajlovi: ["b.pdf", "c.pdf"] });')
    assert r["nastavlja"] is True
    assert r["preostali"] == ["b.pdf", "c.pdf"]
    assert r["ukupno"] == 3
    assert len(r["poslovi"]) == 1


@nodemark
def test_potpun_batch_nema_preostalih():
    r = _js('return U.uPoslove({ rezultati: [{ job_id: "j1" }], ukupno: 1, '
            "nastavlja: false, preostali_fajlovi: [] });")
    assert r["nastavlja"] is False and r["preostali"] == []


# ── 7. Posao ─────────────────────────────────────────────────────────────────
POSAO = {"job": {"id": "j1", "status": "completed", "original_filename": "p.pdf",
                 "predmet_id": None, "attempts": 0, "last_error": None},
         "dokument": {"tip": "court_decision", "tip_pouzdanost": 0.85,
                      "ocr_koriscen": False},
         "entiteti": [
             {"entity_id": "e1", "entity_type": "plaintiff", "value": "Petar",
              "confidence": 0.9, "needs_review": False},
             {"entity_id": "e2", "entity_type": "defendant", "value": "DOO",
              "confidence": 0.9, "needs_review": False},
             {"entity_id": "e3", "entity_type": "amount", "value": None,
              "confidence": 0.0, "needs_review": True}]}


@nodemark
def test_stranke_se_izdvajaju_za_izbor_klijenta():
    r = _js(f"return U.uPosao({_j(POSAO)});")
    assert [x["tip"] for x in r["stranke"]] == ["plaintiff", "defendant"]
    assert len(r["zaPregled"]) == 1


@nodemark
def test_pao_posao_je_pao_i_nije_uspesan():
    r = _js(f"return U.uPosao({_j(dict(POSAO, job=dict(POSAO['job'], status='failed')))});")
    assert r["pao"] is True and r["uspesan"] is False and r["zavrsen"] is True


@nodemark
def test_posao_u_obradi_nije_zavrsen():
    r = _js(f"return U.uPosao({_j(dict(POSAO, job=dict(POSAO['job'], status='processing')))});")
    assert r["zavrsen"] is False
    assert r["stanjeTekst"] == "Obrada u toku"


@nodemark
def test_vrsta_dokumenta_je_na_srpskom():
    """Srpski advokat ne sme da čita „Court decision" u pravnom proizvodu."""
    r = _js(f"return U.uPosao({_j(POSAO)});")
    assert r["dokument"]["tipNaziv"] == "Sudska odluka"
    assert _js('return U.imeDokumenta("nepoznat_tip");') == "Nepoznat tip"


@nodemark
def test_prazan_posao_ne_ruši():
    r = _js("return U.uPosao(null);")
    assert r["entiteti"] == [] and r["zavrsen"] is False


# ── 8. Provera pre finalizovanja ─────────────────────────────────────────────
@nodemark
def test_strana_je_obavezna():
    g = _js("return U.nedostaciUvoza({});")
    assert g != []
    assert "klijent" in g[0].lower(), g


@nodemark
def test_neispravna_strana_se_odbija():
    assert _js('return U.nedostaciUvoza({ strana: "nesto" });') != []
    assert _js('return U.nedostaciUvoza({ strana: "plaintiff" });') == []
    assert _js('return U.nedostaciUvoza({ strana: "defendant" });') == []


@nodemark
def test_predugacak_naziv_se_odbija():
    g = _js('return U.nedostaciUvoza({ strana: "plaintiff", naziv: "x".repeat(201) });')
    assert g != []
