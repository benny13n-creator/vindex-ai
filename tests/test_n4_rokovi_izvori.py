# -*- coding: utf-8 -*-
"""N4 — kalkulator rokova: svaka stavka kataloga mora biti potvrđena LOKALNIM tekstom zakona (data/laws/pdfs),
a poslednji dan na neradni dan se pomera po pravilu o računanju rokova. Izvor istine je tekst zakona, ne model."""
import re
from datetime import date
from pathlib import Path

import pytest

from shared.neradni_dani import drzavni_praznici, je_neradan, pravoslavni_vaskrs, prvi_radni_od
from zastarelost import ROKOVI_ZASTARELOSTI, kalkulisi_zastarelost

ZAKONI = Path(__file__).resolve().parent.parent / "data" / "laws" / "pdfs"
FAJL = {"ZOO": "zakon_o_obligacionim_odnosima.pdf", "ZPP": "zakon_o_parnicnom_postupku.pdf", "ZKP": "zakon_o_krivicnom_postupku.pdf",
        "ZUP": "zakon_o_opstem_upravnom_postupku.pdf", "ZUS": "zakon_o_upravnim_sporovima.pdf", "ZIO": "zakon_o_izvrsenju_i_obezbedjenju.pdf",
        "ZR": "zakon_o_radu.pdf"}
RECI = {1: ["jednu godinu"], 3: ["tri godine"], 5: ["pet godina"], 10: ["deset godina"],
        8: ["osam dana"], 15: ["15 dana"], 30: ["30 dana"], 60: ["60 dana"]}


def _clan(zakon: str, broj: int) -> str:
    tekst = (ZAKONI / FAJL[zakon]).read_text(encoding="utf-8")
    m = re.search(rf"^Član {broj}\s*$(.*?)(?=^Član \d+\w?\s*$)", tekst, re.M | re.S)
    assert m, f"{zakon} čl. {broj} nije u lokalnom tekstu"
    return re.sub(r"\s+", " ", m.group(1))


@pytest.mark.parametrize("kljuc", sorted(ROKOVI_ZASTARELOSTI))
def test_stavka_kataloga_potvrdjena_lokalnim_tekstom(kljuc):
    st = ROKOVI_ZASTARELOSTI[kljuc]
    m = re.match(r"^(ZOO|ZPP|ZKP|ZUP|ZUS|ZIO|ZR) čl\. (\d+)", st["osnov"])
    assert m, f"{kljuc}: osnov {st['osnov']!r} nije iz lokalno dostupnog zakona"
    tekst = _clan(m.group(1), int(m.group(2)))
    n = st.get("dani") or st.get("godine")
    assert n in RECI and any(r in tekst for r in RECI[n]), f"{kljuc}: rok {n} nije u tekstu {st['osnov']}: {tekst[:300]}"
    assert st.get("racunanje"), f"{kljuc}: nema pravila za poslednji dan"


@pytest.mark.parametrize("zakon,clan,deo", [
    ("ZPP", 103, "rok ističe protekom prvog narednog radnog dana"), ("ZPP", 103, "rok zastarelosti potraživanja"),
    ("ZUP", 80, "rok ističe kad protekne prvi naredni radni dan"), ("ZKP", 224, "u subotu ili u nedelju"),
    ("ZOO", 77, "kao poslednji dan roka računa se sledeći radni dan"), ("ZIO", 39, "zakon kojim se uređuje parnični postupak"),
    ("ZUS", 74, "zakona kojim se uređuje parnični postupak"),
])
def test_pravila_racunanja_postoje_u_lokalnom_tekstu(zakon, clan, deo):
    assert deo in _clan(zakon, clan)


@pytest.mark.parametrize("uklonjen", ["potroskac", "nasledna_potrazivanja", "izvrsenje", "zahtev_vanredno_preispitivanje",
                                      "saobracan_udes", "naknada_stete_krivicni", "menjacki", "cek", "poreski"])
def test_neproverljive_ili_pogresne_stavke_uklonjene(uklonjen):
    assert uklonjen not in ROKOVI_ZASTARELOSTI


def test_komunalne_jedna_godina_za_domacinstvo():
    st = ROKOVI_ZASTARELOSTI["komunalne"]
    assert st["godine"] == 1 and "378" in st["osnov"] and "DOMAĆINSTVA" in st["opis"]


# ── poslednji dan ─────────────────────────────────────────────────────────────

def test_vaskrs_racunat_za_svaku_godinu():
    assert [pravoslavni_vaskrs(g) for g in (2024, 2025, 2026, 2027, 2028, 2030)] == [
        date(2024, 5, 5), date(2025, 4, 20), date(2026, 4, 12), date(2027, 5, 2), date(2028, 4, 16), date(2030, 4, 28)]
    assert {date(2030, 4, 26), date(2030, 4, 27), date(2030, 4, 28), date(2030, 4, 29)} <= drzavni_praznici(2030)


def test_praznik_u_nedelju_pomera_na_ponedeljak():
    assert date(2023, 1, 3) in drzavni_praznici(2023)          # 1.1.2023. nedelja
    assert date(2029, 11, 12) in drzavni_praznici(2029)        # 11.11.2029. nedelja


@pytest.mark.parametrize("tip,dogadjaj,kalendarski,istice,razlog", [
    ("zalba_parnicna", date(2026, 10, 30), date(2026, 11, 14), date(2026, 11, 16), "subotu"),
    ("prigovor_platni_nalog", date(2026, 11, 1), date(2026, 11, 9), date(2026, 11, 9), ""),
    ("zalbeni_upravni", date(2026, 10, 27), date(2026, 11, 11), date(2026, 11, 12), "državni praznik"),
    ("zalbeni_krivicni", date(2026, 12, 18), date(2027, 1, 2), date(2027, 1, 4), "državni praznik"),   # prelaz godine, 1–2.1.
    ("revizija", date(2030, 3, 27), date(2030, 4, 26), date(2030, 4, 30), "državni praznik"),          # Veliki petak 2030.
    ("presudjeno", date(2020, 2, 29), date(2030, 2, 28), date(2030, 2, 28), ""),                       # prestupna → 28.2.
    ("opsti", date(2016, 11, 11), date(2026, 11, 11), date(2026, 11, 12), "državni praznik"),
])
def test_poslednji_dan_po_pravilu_racunanja(tip, dogadjaj, kalendarski, istice, razlog):
    r = kalkulisi_zastarelost(tip, dogadjaj)
    assert (r.kalendarski_poslednji_dan, r.datum_zastarelosti, r.pomereno_razlog) == (kalendarski, istice, razlog)
    assert not je_neradan(r.datum_zastarelosti) and r.izvor_neradnih_dana


def test_prvi_radni_od_ne_pomera_radni_dan():
    assert prvi_radni_od(date(2026, 11, 10)) == date(2026, 11, 10)


def test_ruta_vraca_pomeranje_i_izvor():
    from fastapi.testclient import TestClient
    import api
    r = TestClient(api.app).post("/zastarelost/kalkulisi", json={"tip": "zalba_parnicna", "datum_pocetka": "2026-10-30"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["datum_zastarelosti"] == "16.11.2026" and d["kalendarski_poslednji_dan"] == "14.11.2026" and d["pomereno_razlog"] == "subotu"
    assert d["vrsta"] == "procesni" and "ZPP čl. 103" in d["pravilo_racunanja"] and "nije u lokalnoj bazi" in d["izvor_neradnih_dana"]


def test_prvi_maj_u_nedelju_na_vaskrs_2027():
    """Nalaz pregleda N4: 2.5.2027. je nedelja i Vaskrs; 3.5. je drugi dan Vaskrsa, pa je neradan i 4.5."""
    assert {date(2027, 5, 1), date(2027, 5, 2), date(2027, 5, 3), date(2027, 5, 4)} <= drzavni_praznici(2027)
    assert prvi_radni_od(date(2027, 5, 1)) == date(2027, 5, 5)


def test_komunalne_napomena_telefon_bez_uslova_domacinstva():
    assert "za telefon i poštu (tač. 3) tog uslova nema" in ROKOVI_ZASTARELOSTI["komunalne"]["napomena"]
