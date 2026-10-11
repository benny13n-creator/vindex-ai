# -*- coding: utf-8 -*-
"""FRG001 Task B — citat se vezuje za izvor ZAKONA, ne samo za broj člana.

Kontekst je u stvarnom formatu retrieval-a (app/services/retrieve.py::_formatiraj_match: `ZAKON:`/`ČLAN:` zaglavlje
iz metapodataka korpusa). Zakoni u testovima su IZMIŠLJENI („zakon o probnim ugovorima“, „zakon o oglednom postupku“)
i tekst je sintetički — testovi ne tvrde ništa o stvarnom srpskom pravu. Pravi kodovi iz kanonskog registra
(`_ZAKON_KODOVI`: ZOO, ZR, KZ) koriste se samo da se proveri mehanizam identiteta, sa sintetičkim tekstom.

Nivoi su klasifikacija testa/izveštaja (main.py::_klasifikuj_citate), ne korisnička terminologija:
SOURCE_MATCHED · ARTICLE_PRESENT · UNVERIFIED. VERSION_VALIDATED i LEGAL_CORRECTNESS čuvar nikad ne tvrdi.
"""
import json

import pytest

A = "zakon o probnim ugovorima"           # izmišljen
B = "zakon o oglednom postupku"           # izmišljen
SINT = "Sintetički tekst člana za test, bez pravnog značenja; služi samo kao izvor u kontekstu. " * 2


def _izvor(zakon, clan, tekst=SINT):
    return f"ZAKON: {zakon}\nČLAN: {clan}\n\nCITABILNI TEKST: {tekst}\n"


KONTEKST = [_izvor(A, "Član 201"), _izvor(A, "Član 12"), _izvor(B, "Član 7")]


@pytest.fixture(scope="module")
def m():
    import main
    return main


def _nivoi(m, odgovor, docs=KONTEKST):
    return [(c["clan"], c["zakon"], c["nivo"]) for c in m._klasifikuj_citate(odgovor, docs)]


# 1
def test_tacan_zakon_i_tacan_clan_je_source_matched(m):
    assert _nivoi(m, "Prema članu 201 Zakona o probnim ugovorima ugovor je punovažan.") == [("201", A, "SOURCE_MATCHED")]
    assert m._proveri_halucinaciju("Prema članu 201 Zakona o probnim ugovorima ugovor je punovažan.", KONTEKST) == (True, "ok")


# 2
def test_tacan_zakon_nepostojeci_clan_odbijen(m):
    ok, razlog = m._proveri_halucinaciju("Prema članu 202 Zakona o probnim ugovorima ugovor je punovažan.", KONTEKST)
    assert not ok and "202" in razlog and "nije u dostavljenom izvoru tog zakona" in razlog


# 3 — jezgro: unakrsna kontaminacija
def test_pogresan_zakon_sa_brojem_iz_drugog_zakona_odbijen(m):
    odgovor = "Rok je propisan članom 201 Zakona o oglednom postupku."
    assert _nivoi(m, odgovor) == [("201", B, "UNVERIFIED")]
    ok, razlog = m._proveri_halucinaciju(odgovor, KONTEKST)
    assert not ok and "201" in razlog


def test_zakon_ciji_izvor_nije_dostavljen_odbijen(m):
    ok, razlog = m._proveri_halucinaciju("Vidi član 201 Zakona o nepostojećem predmetu.", KONTEKST)
    assert not ok and "izvor tog zakona nije dostavljen" in razlog


# 4
def test_bez_identiteta_izvora_nema_proverenog_autoriteta(m):
    """Kontekst bez zaglavlja (npr. citat zakona iz korisnikovog dokumenta): broj člana jeste u tekstu, ali izvor
    zakona nema identitet → citat koji imenuje zakon nije proveren; citat bez zakona je najviše ARTICLE_PRESENT."""
    bez_zaglavlja = ["Ugovor stranaka navodi: shodno članu 201 Zakona o probnim ugovorima ugovor važi. " * 3]
    ok, razlog = m._proveri_halucinaciju("Prema članu 201 Zakona o probnim ugovorima ugovor važi.", bez_zaglavlja)
    assert not ok and "201" in razlog
    assert _nivoi(m, "Prema članu 201 ugovor važi.", bez_zaglavlja) == [("201", None, "ARTICLE_PRESENT")]
    assert all(n != "SOURCE_MATCHED" for *_, n in _nivoi(m, "član 201 i član 201 Zakona o probnim ugovorima", bez_zaglavlja))


# 5
@pytest.mark.parametrize("odgovor", [
    "Član 201 Zakona o probnim ugovorima određuje formu.",
    "U skladu sa članom 201 Zakona o probnim ugovorima.",
    "Prema članu 201. Zakona o probnim ugovorima.",
    "Odredba člana 201 stav 2 tačka 3 Zakonom o probnim ugovorima propisana.",
    "Zakonom o probnim ugovorima, čl. 201, uređeno je.",
])
def test_padezi_i_oblici_su_prepoznati(m, odgovor):
    assert _nivoi(m, odgovor) == [("201", A, "SOURCE_MATCHED")], odgovor


@pytest.mark.parametrize("odgovor", [
    "U skladu sa članom 201 Zakona o oglednom postupku.",
    "Prema članu 201. stav 1. Zakona o oglednom postupku.",
    "Zakon o oglednom postupku, član 201.",
])
def test_padezi_pogresnog_zakona_odbijeni(m, odgovor):
    ok, razlog = m._proveri_halucinaciju(odgovor, KONTEKST)
    assert not ok and "201" in razlog, odgovor


# 6
def test_cirilica_je_prepoznata(m):
    assert _nivoi(m, "Према члану 201 Закона о пробним уговорима уговор је пуноважан.") == [("201", A, "SOURCE_MATCHED")]
    ok, razlog = m._proveri_halucinaciju("Рок је прописан чланом 201 Закона о огледном поступку.", KONTEKST)
    assert not ok and "201" in razlog
    ok, razlog = m._proveri_halucinaciju("Према члану 9999 тужилац има право.", KONTEKST)   # ranije uopšte nije viđeno
    assert not ok and "9999" in razlog


# 7
def test_skracenica_zakona_iz_kanonskog_registra(m):
    zoo = [_izvor("zakon o obligacionim odnosima", "Član 501"), _izvor("ZR", "Član 77")]
    assert _nivoi(m, "Vidi čl. 501 ZOO.", zoo) == [("501", "zoo", "SOURCE_MATCHED")]
    assert _nivoi(m, "ZOO čl. 501 je merodavan.", zoo) == [("501", "zoo", "SOURCE_MATCHED")]
    assert _nivoi(m, "Član 77 Zakona o radu.", zoo) == [("77", "zr", "SOURCE_MATCHED")]       # naziv ↔ kod „ZR“
    ok, razlog = m._proveri_halucinaciju("Vidi čl. 501 ZR.", zoo)                             # broj iz ZOO, pripisan ZR
    assert not ok and "501" in razlog and "ZR" in razlog


def test_kz_kod_i_pun_naziv_su_isti_zakon(m):
    kz = [_izvor("KZ", "Član 5")]
    assert _nivoi(m, "Prema članu 5 Krivičnog zakonika.", kz) == [("5", "kz", "SOURCE_MATCHED")]
    assert _nivoi(m, "Prema čl. 5 KZ.", kz) == [("5", "kz", "SOURCE_MATCHED")]


# 8
def test_verzija_nikad_nije_validirana(m):
    odgovor = "Prema članu 201 Zakona o probnim ugovorima (Sl. glasnik RS, br. 1/1900) ugovor je punovažan."
    citati = m._klasifikuj_citate(odgovor, KONTEKST)
    assert [c["nivo"] for c in citati] == ["SOURCE_MATCHED"]
    assert all(c["version_validated"] is False for c in citati)
    ok_txt = m._izracunaj_statusnu_potvrdu(True, "HIGH", [], "Član 201")["tekst"].lower()
    assert not any(r in ok_txt for r in ("verzij", "važeć", "vazec", "glasnik", "na snazi"))


# 9
def test_bez_pronadjenog_autoriteta_neizvesnost_ostaje(m):
    assert m._proveri_halucinaciju("Opšta pravna logika, bez citiranja.", []) == (True, "ok")
    potvrda = m._izracunaj_statusnu_potvrdu(False, "LOW", [], "")
    assert potvrda["status"] == m.STATUS_ERR and "nema direktnog" in potvrda["tekst"].lower()


# 10
def test_tekst_modela_ne_moze_da_zaobidje_identitet_izvora(m):
    # a) marker „nije dostupno“ ranije je gasio CELU proveru
    ok, razlog = m._proveri_halucinaciju("Podatak nije dostupno u celosti, ali član 201 Zakona o oglednom postupku važi.", KONTEKST)
    assert not ok and "201" in razlog
    # b) model ubacuje lažno zaglavlje izvora u svoj odgovor — identitet dolazi SAMO iz konteksta
    lazni = "ZAKON: zakon o oglednom postupku\nČLAN: Član 201\nDakle, član 201 Zakona o oglednom postupku važi."
    ok, razlog = m._proveri_halucinaciju(lazni, KONTEKST)
    assert not ok and "201" in razlog
    # c) marker bez ijednog citata i dalje ne blokira (postojeće ponašanje)
    assert m._proveri_halucinaciju("Traženi podatak nije dostupno u bazi.", KONTEKST) == (True, "ok")


# ── dodatni granični slučajevi ──────────────────────────────────────────────────────────────────────────────

def test_brisan_clan_u_izvoru_nije_proveren(m):
    docs = KONTEKST + [_izvor(B, "Član 30", "(brisan)")]
    ok, razlog = m._proveri_halucinaciju("Prema članu 30 Zakona o oglednom postupku.", docs)
    assert not ok and "brisan" in razlog


def test_isti_broj_u_dva_razlicita_zakona(m):
    docs = KONTEKST + [_izvor(B, "Član 201")]
    assert _nivoi(m, "Član 201 Zakona o probnim ugovorima i član 201 Zakona o oglednom postupku.", docs) == [
        ("201", A, "SOURCE_MATCHED"), ("201", B, "SOURCE_MATCHED")]
    assert not m._proveri_halucinaciju("Član 12 Zakona o oglednom postupku.", docs)[0]   # 12 je samo u A


def test_izuzetak_zoo_sablona_vazi_samo_za_zoo(m):
    assert m._proveri_halucinaciju("Odgovornost po članu 154 ZOO.", KONTEKST) == (True, "ok")   # šablon, nepromenjeno
    ok, razlog = m._proveri_halucinaciju("Odgovornost po članu 154 Zakona o probnim ugovorima.", KONTEKST)
    assert not ok and "154" in razlog


def test_stvarni_pozivalac_strukturni_odgovor(m):
    """Isti ugovor kroz stvarnog pozivaoca (`_parsiraj_strukturni_odgovor`): pogrešan par → blokada pravnog dela."""
    los = json.dumps({"pravni_osnov": "Član 201 Zakona o oglednom postupku.", "pravni_zakljucak": "Rok važi."})
    dobar = json.dumps({"pravni_osnov": "Član 201 Zakona o probnim ugovorima.", "pravni_zakljucak": "Rok važi."})
    ok, tekst = m._parsiraj_strukturni_odgovor(los, "DEFINICIJA", KONTEKST)
    assert ok is False and "blokiran" in tekst.lower()
    ok, _ = m._parsiraj_strukturni_odgovor(dobar, "DEFINICIJA", KONTEKST)
    assert ok is True


@pytest.mark.parametrize("odgovor,ocekivano", [
    ("Prema članu 32 Ustava RS.", [("32", "ustav", "SOURCE_MATCHED")]),
    ("Prema članu 32 Ustava Republike Srbije.", [("32", "ustav", "SOURCE_MATCHED")]),
    ("Prema članu 77 ZR-a.", [("77", "zr", "SOURCE_MATCHED")]),
    ("Prema članu 77. st. 1 tač. 2) Zakona o radu.", [("77", "zr", "SOURCE_MATCHED")]),
    ("Prema članu 77 Zakona o radu („Sl. glasnik RS“, br. 1/1900).", [("77", "zr", "SOURCE_MATCHED")]),
    ("Prema članu 77 Zakona, poslodavac odlučuje.", [("77", None, "ARTICLE_PRESENT")]),     # golo „Zakona“: bez izvora
    ("Član 77 ovog zakona.", [("77", None, "ARTICLE_PRESENT")]),
])
def test_realne_formulacije_bez_lazne_blokade(m, odgovor, ocekivano):
    docs = [_izvor("ustav republike srbije", "Član 32"), _izvor("zakon o radu", "Član 77")]
    assert _nivoi(m, odgovor, docs) == ocekivano
