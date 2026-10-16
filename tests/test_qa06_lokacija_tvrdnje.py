# -*- coding: utf-8 -*-
"""QA-06 — šta aplikacija SME da tvrdi o izvoru tvrdnje.

Četiri nivoa (Beta Reliability Closure):
  1 DOCUMENT_DELIVERED        dokument je bio dostupan
  2 CLAIM_SOURCE_LINKED       tvrdnja je vezana za dokument (`dokument_id`)
  3 QUOTE_EXACT_MATCH         tekst tvrdnje postoji u dokumentu (lokator)
  4 CLAIM_SEMANTICALLY_SUPPORTED   NE POSTOJI u aplikaciji

Ispravka: lokator je tražio samo prvih 100 znakova tvrdnje, pa je duža tvrdnja
sa izmišljenim nastavkom dobijala `egzaktan` i u V2 „pronađeno u dokumentu“.
Sintetički tekstovi; bez modela, bez baze.
"""
import pytest

from shared.evidence_graph import POTPORA_DOKUMENT, POTPORA_LOCIRANA, sastavi_graf
from shared.evidence_write import (GreskaDokaza, NACIN_EGZAKTAN, NACIN_NIJE, lociraj_tvrdnju,
                                   odredi_snagu, upisi_dokaze)

DOK = ("Zapisnik o primopredaji. Dana 15.08.2026. predato je devet monitora Kupcu u prostorijama "
       "Prodavca u Beogradu, bez primedbi na kvalitet isporucene robe i bez ikakve rezerve. "
       "Kupac je potpisao zapisnik.")
TACNO_DUGO = ("Dana 15.08.2026. predato je devet monitora Kupcu u prostorijama Prodavca u Beogradu, "
              "bez primedbi na kvalitet isporucene robe i bez ikakve rezerve.")
IZMISLJEN_REP = ("Dana 15.08.2026. predato je devet monitora Kupcu u prostorijama Prodavca u Beogradu, "
                 "bez primedbi na kvalitet, ali je Kupac istog dana raskinuo ugovor.")


def _potpora(tvrdnja, tekst=DOK, dokument_id="d1"):
    lok = lociraj_tvrdnju(tekst, tvrdnja) if tekst else lociraj_tvrdnju("", tvrdnja)
    snaga, izvor = odredi_snagu(tvrdnja, dict(lok), izvor_dostupan=bool(tekst))
    red = {"id": "t1", "predmet_id": "p", "dokument_id": dokument_id, "tvrdnja": tvrdnja, "kategorija": "cinjenica",
           "snaga": snaga, "deleted_at": None, "stranica": lok["stranica"], "paragraf": lok["paragraf"],
           "start_offset": lok["start_offset"], "end_offset": lok["end_offset"],
           "nacin_pronalaska": lok["nacin"], "izvor_tvrdnje": "AI"}
    g = sastavi_graf(dokazi=[red], dokumenti=[{"id": "d1", "naziv_fajla": "zapisnik.pdf"}], v2_kontradikcije=[])
    return lok, g["tvrdnje"][0], snaga, izvor


def test_izmisljen_nastavak_duge_tvrdnje_nije_pronadjen():
    assert IZMISLJEN_REP[:100] in DOK and IZMISLJEN_REP not in DOK
    lok, t, snaga, _ = _potpora(IZMISLJEN_REP)
    assert lok["nacin"] == NACIN_NIJE and lok["start_offset"] is None
    assert t["potpora"] == POTPORA_DOKUMENT                  # nivo 2, ne nivo 3
    assert snaga == "srednja"


def test_tacna_duga_tvrdnja_je_pronadjena_cela():
    lok, t, snaga, _ = _potpora(TACNO_DUGO)
    assert lok["nacin"] == NACIN_EGZAKTAN
    assert DOK[lok["start_offset"]:lok["end_offset"]] == TACNO_DUGO   # pokriven CEO citat, ne prefiks
    assert t["potpora"] == POTPORA_LOCIRANA
    assert snaga == "srednja"                                # > 100 znakova: „jaka“ i dalje nije dozvoljena


def test_citat_sa_zavrsnim_tri_tacke_je_namerno_skracen():
    assert TACNO_DUGO[:110] in DOK
    lok, t, _, _ = _potpora(TACNO_DUGO[:110] + "…")
    assert t["potpora"] == POTPORA_LOCIRANA
    assert lok["end_offset"] - lok["start_offset"] == len(TACNO_DUGO[:110].rstrip())


def test_kratka_tacna_tvrdnja_i_dalje_jaka():
    lok, t, snaga, izvor = _potpora("predato je devet monitora Kupcu")
    assert (t["potpora"], snaga, izvor) == (POTPORA_LOCIRANA, "jaka", "dc005")


# ── 12 sintetičkih slučajeva: šta aplikacija dokazuje NA NIVOU TVRDNJE ─────

def test_tacan_dokument_izmisljen_sadrzaj():
    _, t, _, _ = _potpora("Kupac je odbio prijem svih monitora zbog ostecenja.")
    assert t["potpora"] == POTPORA_DOKUMENT


def test_tacan_citat_pogresan_zakljucak_aplikacija_dokazuje_samo_citat():
    """„predato je devet monitora Kupcu“ JESTE u dokumentu; zaključak „pa je ugovor ispunjen u celosti“
    aplikacija ne proverava. Nivo 3 postoji, nivo 4 ne postoji ni kao polje."""
    _, t, _, _ = _potpora("predato je devet monitora Kupcu")
    assert t["potpora"] == POTPORA_LOCIRANA
    assert not ({"verifikovano", "podrzano", "semanticki"} & set(t))


def test_nedostaje_tekst_dokumenta_nema_lokacije_ni_dc005():
    lok, t, snaga, izvor = _potpora("predato je devet monitora Kupcu", tekst="")
    assert lok["start_offset"] is None and t["potpora"] == POTPORA_DOKUMENT
    assert izvor != "dc005"


def test_tvrdnja_bez_dokumenta():
    _, t, _, _ = _potpora("Prodavac je kasnio sa isporukom.", tekst="", dokument_id=None)
    assert t["potpora"] == "BEZ_POTPORE"


def test_tudji_dokument_javna_putanja():
    class _Prazno:
        def __getattr__(self, _):
            return lambda *a, **k: self

        def execute(self):
            class R:
                data = []
            return R()

    class _Supa:
        def __init__(self):
            self.n = 0

        def table(self, ime):
            if ime == "predmeti":
                class Da(_Prazno):
                    def execute(self):
                        class R:
                            data = [{"id": "p-A"}]
                        return R()
                return Da()
            return _Prazno()

    with pytest.raises(GreskaDokaza) as e:
        upisi_dokaze(_Supa(), predmet_id="p-A", user_id="u-A",
                     stavke=[{"tvrdnja": "x" * 30, "dokument_id": "dok-iz-predmeta-B"}])
    assert "ne pripada" in e.value.poruka


def test_isti_naziv_fajla_razresava_se_po_id_ne_po_nazivu():
    red = {"id": "t1", "predmet_id": "p", "dokument_id": "d2", "tvrdnja": "x" * 30, "kategorija": "cinjenica",
           "snaga": "srednja", "deleted_at": None, "izvor_tvrdnje": "AI"}
    g = sastavi_graf(dokazi=[red], dokumenti=[{"id": "d1", "naziv_fajla": "ugovor.pdf"},
                                              {"id": "d2", "naziv_fajla": "ugovor.pdf"}], v2_kontradikcije=[])
    assert g["tvrdnje"][0]["dokument_id"] == "d2"
