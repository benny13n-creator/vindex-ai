# -*- coding: utf-8 -*-
"""MIR001 TASK-01 — samoprovera Golden Case korpusa: da li fixture zaista može da falsifikuje tvrdnju
„sistem razume ceo spis“. Ne meri sistem, meri korpus (determinizam, konflikti, hronologija, stare činjenice,
skeniran dokument, nedostupna informacija, kasnija promena, izolacija korisnika B)."""
import io
import re
from datetime import date, timedelta

import pytest

from tests import mir001_golden_case as gc

VRSTE = {"tuzba", "odgovor_na_tuzbu", "podnesak", "nalaz_vestaka", "zapisnik"}


def _izvuci(pdf: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join((s.extract_text() or "") for s in PdfReader(io.BytesIO(pdf)).pages)


def _ceo_tekst():
    return {d["oznaka"]: gc.tekst(d) for d in gc.DOKUMENTI}


def _dmy(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d.%m.%Y")


def test_sedam_razlicitih_procesnih_dokumenata_stabilnih_identiteta():
    assert len(gc.DOKUMENTI) == 7
    assert [d["oznaka"] for d in gc.DOKUMENTI] == [f"DOK-0{i}" for i in range(1, 8)]
    assert len({d["ime"] for d in gc.DOKUMENTI}) == 7
    assert VRSTE <= {d["vrsta"] for d in gc.DOKUMENTI}
    assert {"tuzilac", "tuzeni", "vestak", "sud"} <= {d["strana"] for d in gc.DOKUMENTI}
    # tužba, odgovor, podnesak tužioca, podnesak tuženog, nalaz, izjašnjenje na nalaz, zapisnik
    oblik = [(d["vrsta"], d["strana"]) for d in gc.DOKUMENTI]
    assert ("podnesak", "tuzilac") in oblik and ("podnesak", "tuzeni") in oblik
    assert sum(1 for d in gc.DOKUMENTI if "IZJASNJENJE" in gc.tekst(d) and "NALAZ" in gc.tekst(d)) == 1


_HES = ("import hashlib,sys; sys.path.insert(0, '.'); from tests import mir001_golden_case as gc; "
        "print(' '.join(hashlib.sha256(gc.bajtovi(d)).hexdigest() for d in gc.DOKUMENTI + [gc.KASNIJI, gc.B_DOKUMENT]))")


def test_korpus_je_deterministicki_isti_bajtovi_u_dva_procesa():
    """Dva ODVOJENA procesa sa različitim PYTHONHASHSEED → isti sha256 za svih 9 PDF-ova."""
    import os
    import subprocess
    import sys
    koren = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    izlazi = [subprocess.run([sys.executable, "-c", _HES], cwd=koren, capture_output=True, text=True, check=True,
                             env={**os.environ, "PYTHONHASHSEED": seme}).stdout.strip().splitlines()[-1] for seme in ("1", "4242")]
    assert izlazi[0] == izlazi[1] and len(izlazi[0].split()) == 9


def test_bar_jedan_skeniran_bez_tekstualnog_sloja_sa_poznatim_tekstom():
    skenirani = [d for d in gc.DOKUMENTI if d["skeniran"]]
    assert skenirani, "bar jedan dokument mora biti skeniran"
    for d in skenirani:
        assert _izvuci(gc.bajtovi(d)).strip() == ""          # bez OCR-a nema teksta → OCR je stvarno potreban
        assert len(d["redovi"]) >= 5                          # poznat očekivan sadržaj za poređenje


@pytest.mark.parametrize("dok", [d for d in gc.DOKUMENTI + [gc.KASNIJI] if not d["skeniran"]], ids=lambda d: d["oznaka"])
def test_digitalni_dokument_daje_tacno_svoj_tekst(dok):
    izvuceno = " ".join(_izvuci(gc.bajtovi(dok)).split())
    for red in dok["redovi"]:
        assert " ".join(red.split()) in izvuceno, red


def test_svaki_navod_postoji_samo_u_svom_dokumentu():
    t = _ceo_tekst()
    for nid, n in gc.NAVODI.items():
        u = [oz for oz, tx in t.items() if n["tekst"] in tx]
        assert u == [n["dok"]], (nid, u)
        strana = gc.po_oznaci(n["dok"])["strana"]
        ocekivano = {"tuzilac": "NAVOD_TUZIOCA", "tuzeni": "NAVOD_TUZENOG", "vestak": "NALAZ_VESTAKA", "sud": "SUD"}[strana]
        assert n["status"] == ocekivano, nid


def test_protivrecnosti_su_izmedju_dve_strane_i_vrednosti_se_razlikuju():
    t = _ceo_tekst()
    for k in gc.PROTIVRECNOSTI:
        a, b = (gc.NAVODI[x] for x in k["strane"])
        assert {gc.po_oznaci(a["dok"])["strana"], gc.po_oznaci(b["dok"])["strana"]} == {"tuzilac", "tuzeni"}, k["id"]
        va, vb = k["vrednosti"]
        assert va != vb
        assert va in t[a["dok"]] and vb not in t[a["dok"]]
        assert vb in t[b["dok"]] and va not in t[b["dok"]]


def test_hronologija_je_uredjena_i_svaki_dogadjaj_ima_izvor():
    datumi = [h[0] for h in gc.HRONOLOGIJA]
    assert datumi == sorted(datumi)
    t = _ceo_tekst()
    for iso, opis, oz in gc.HRONOLOGIJA:
        assert _dmy(iso) in t[oz], (iso, opis, oz)
    # Redosled čitanja (dokument, red) NIJE hronologija: događaj pomenut tek u DOK-07 prethodi svemu ostalom.
    def _citanje(h):
        dok = gc.po_oznaci(h[2])
        red = next(i for i, r in enumerate(dok["redovi"]) if _dmy(h[0]) in r)
        return (gc.DOKUMENTI.index(dok), red)
    assert sorted(gc.HRONOLOGIJA, key=_citanje) != gc.HRONOLOGIJA
    assert gc.HRONOLOGIJA[0][2] == "DOK-07"


def test_dve_relevantne_cinjenice_su_van_pet_najnovijih_dokumenata():
    najnovijih_pet = {d["oznaka"] for d in gc.DOKUMENTI[-5:]}
    assert len(gc.STARE_CINJENICE) >= 2
    for nid in gc.STARE_CINJENICE:
        assert gc.NAVODI[nid]["dok"] not in najnovijih_pet, nid


def test_prelomna_cinjenica_menja_procenu_i_dolazi_iz_skena():
    n = gc.NAVODI[gc.PRELOMNA["navod"]]
    assert gc.po_oznaci(n["dok"])["skeniran"] is True       # razumevanje zavisi od stvarnog OCR-a
    t = _ceo_tekst()
    assert "solarnih panela nisu ostetili" in t["DOK-05"]    # obara tezu tuženog N-05
    assert gc.NAVODI[gc.PRELOMNA["iznos"]]["tekst"] in t["DOK-05"]


def test_nedostupna_informacija_zaista_nije_u_spisu():
    pre = "\n".join(_ceo_tekst().values()).lower()
    posle = pre + "\n" + gc.tekst(gc.KASNIJI).lower()
    for ceo in (pre, posle):
        assert "jun 2025" not in ceo                          # nijedan upis dnevnika za jun 2025
        assert [r for r in ceo.splitlines() if "06.2025" in r] == ["tuzeni je zavrsio radove na krovu hale dana 15.06.2025. godine."]
        # jedina imenovana osoba je veštak; izvođač/odgovorno lice tuženog nikad nije imenovano
        assert "odgovorni" not in ceo and "rukovodilac" not in ceo
        assert [r for r in ceo.splitlines() if "izmisljeni" in r] == ["vestak gradjevinske struke petar izmisljeni."]
        assert [r for r in ceo.splitlines() if "izvodjac" in r] == ([] if ceo is pre else
                                                                    ["vestak ostaje pri nalazu da je uzrok prokisnjavanja izvodjacka greska."])
    # dnevnik se POMINJE (tražen je); pre DOK-08 o sadržaju nema ničeg, posle — samo veštakov negativan nalaz
    assert "gradjevinski dnevnik" in pre and "dnevnik ne sadrzi" not in pre
    assert "dnevnik ne sadrzi upis o probi vodonepropusnosti" in posle
    assert all("posle_DOK_08" in n for n in gc.NEDOSTUPNO)


def test_povucen_navod_i_brisanje_izvora():
    t = _ceo_tekst()
    pov = gc.POVUCENO["sadrzinski"]
    assert gc.NAVODI[pov["navod"]]["dok"] == "DOK-03" and gc.NAVODI[pov["povlaci"]]["dok"] == "DOK-07"
    assert "povlaci" in t["DOK-07"] and "robi" in t["DOK-07"]
    obrisan = gc.POVUCENO["brisanje_izvora"]
    assert [nid for nid, n in gc.NAVODI.items() if n["dok"] == obrisan] == ["N-06", "N-07"]


def test_aktuelni_tuzbeni_zahtev_zamenjuje_iznos_iz_tuzbe():
    t = _ceo_tekst()
    z = gc.AKTUELNI_ZAHTEV
    assert gc.NAVODI[z["zamenjen"]]["dok"] == "DOK-01" and gc.NAVODI[z["aktuelan"]]["dok"] == "DOK-07"
    assert z["iznos"] in gc.NAVODI[z["aktuelan"]]["tekst"] and z["iznos"] not in t["DOK-01"]


def test_kasnija_promena_nosi_nov_rok_koji_nije_u_spisu():
    k = gc.KASNIJA_PROMENA
    assert date.fromisoformat(k["od"]) + timedelta(days=k["rok_dana"]) == date.fromisoformat(k["rok"])
    tk = gc.tekst(gc.KASNIJI)
    assert f"rok od {k['rok_dana']} dana od dana dopune" in tk and k["navod"] in tk
    assert _dmy(k["od"]) in tk and date.fromisoformat(gc.SADA) <= date.fromisoformat(k["rok"])
    assert k["navod"] not in "\n".join(_ceo_tekst().values())


def test_korisnik_b_ima_jedinstven_marker_koga_nema_u_spisu_a():
    ceo = "\n".join(_ceo_tekst().values()) + gc.tekst(gc.KASNIJI)
    assert gc.B_MARKER not in ceo
    assert gc.B_MARKER in "\n".join(gc.B_DOKUMENT["redovi"])


def test_sve_je_oznaceno_kao_sinteticko():
    for d in gc.DOKUMENTI + [gc.KASNIJI]:
        assert "SINTETICKI" in gc.tekst(d), d["oznaka"]
    assert re.search(r"SINTETICKI", gc.B_PREDMET["naziv"])


try:
    import pytesseract
    _OCR = str(pytesseract.get_tesseract_version())
except Exception:
    _OCR = None


@pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — OCR provera skena preskočena")
def test_sken_je_ocr_citljiv_kroz_stvarni_extractor(tmp_path):
    """Sken nije namerno nečitljiv: stvaran `uploaded_doc.extractor` izvlači prelomne navode (N-09, N-10)."""
    from uploaded_doc import extractor as ex
    d = gc.po_oznaci(gc.NAVODI[gc.PRELOMNA["navod"]]["dok"])
    p = tmp_path / d["ime"]
    p.write_bytes(gc.bajtovi(d))
    tekst, je_skeniran, ocr_koriscen, strane, pouzdanost = ex.extract(p)
    assert ocr_koriscen is True and je_skeniran is False and pouzdanost and pouzdanost > 0.6
    norm = " ".join(tekst.split())
    for nid in ("N-09", "N-10"):
        assert gc.NAVODI[nid]["tekst"] in norm, nid
    tacnih = sum(1 for r in d["redovi"] if " ".join(r.split()) in norm)
    assert tacnih >= len(d["redovi"]) - 1, tacnih
