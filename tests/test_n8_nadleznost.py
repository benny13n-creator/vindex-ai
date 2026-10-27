# -*- coding: utf-8 -*-
"""N8 — pravno rezonovanje o nadležnosti: deterministički delovi (bez mreže). Stvarni model + Pinecone se mere
posebnom skriptom (izveštaj N8); ovde se dokazuje usmeravanje pretrage, prepoznavanje citiranog člana u padežu,
uklanjanje neproverene prakse i stavova koji nisu podržani sažetkom odluke, i determinističke napomene."""
from pathlib import Path
import re

import pytest

from app.services.retrieve import _clan_nadleznosti_zpp, _izvuci_broj_clana, _prepoznaj_zakon, je_pitanje_gradjanske_nadleznosti

ZPP = (Path(__file__).resolve().parent.parent / "data" / "laws" / "pdfs" / "zakon_o_parnicnom_postupku.pdf").read_text(encoding="utf-8")


def _clan(n):
    m = re.search(rf"^Član {n}\s*$(.*?)(?=^Član \d+\w?\s*$)", ZPP, re.M | re.S)
    return re.sub(r"\s+", " ", m.group(1)) if m else ""


# Tačni odgovori iz LOKALNOG teksta ZPP-a (ne iz modela): pitanje → član i ključna rečenica člana.
ISTINA = [
    ("opšta mesna nadležnost fizičkog lica", 39, "sud na čijem području tuženi ima prebivalište"),
    ("pravno lice", 40, "nalazi njihovo sedište, prema izveštaju Agencije za privredne registre"),
    ("vanugovorna šteta / teška telesna povreda", 44, "sud na čijem području tužilac ima prebivalište"),
    ("nepokretnost — isključiva", 51, "isključivo je mesno nadležan sud na čijem području"),
    ("radni spor zaposlenog", 60, "sud na čijem se području rad obavlja ili se obavljao"),
    ("stvarna — upućuje na zakon", 27, "u granicama svoje stvarne nadležnosti propisane zakonom"),
]


@pytest.mark.parametrize("opis,clan,recenica", ISTINA)
def test_istina_je_u_lokalnom_tekstu_zpp(opis, clan, recenica):
    assert recenica in _clan(clan), (opis, clan)


@pytest.mark.parametrize("q,da", [
    ("Koji sud je mesno nadležan?", True), ("Pred kojim sudom oštećeni može da tuži?", True), ("Gde da podnesem tužbu?", True),
    ("Kom sudu se podnosi tužba za razvod?", True), ("Koji sud je nadležan za krivično delo prevare?", False),
    ("Nadležnost u upravnom sporu?", False), ("Koliki je rok zastarelosti za zajam?", False),
    # revizija N8 F2: nije pitanje o nadležnosti SUDA u parnici
    ("Koji je nadležni organ za izdavanje građevinske dozvole?", False), ("Nadležnost ministarstva finansija", False),
    ("Ko je nadležan za zaštitu podataka o ličnosti?", False), ("Gde da podnesem prijavu za krađu?", False),
    ("Kom sudu se podnosi ustavna žalba?", False), ("Kom sudu se izjavljuje žalba na presudu osnovnog suda?", False),
    ("Koji sud je mesno nadležan za izvršenje po članu 7 Zakona o izvršenju i obezbeđenju?", False),
    ("Koji sud vodi ostavinski postupak?", False), ("Komšija mi je poplavio stan. Koji sud je nadležan?", True),
    ("Koji je nadležni sud za spor oko zakupa?", True),
])
def test_prepoznavanje_pitanja_o_gradjanskoj_nadleznosti(q, da):
    assert je_pitanje_gradjanske_nadleznosti(q) is da
    if da:
        assert _prepoznaj_zakon(q) == "zakon o parnicnom postupku"


def test_pitanje_o_nadleznosti_sa_cinjenicom_zajma_ide_u_zpp_a_ne_zoo():
    q = "Klijent tuži fizičko lice iz Novog Sada radi vraćanja zajma. Koji sud je mesno nadležan?"
    assert _prepoznaj_zakon(q) == "zakon o parnicnom postupku"
    assert _prepoznaj_zakon("Koja je kamata kod ugovora o zajmu?") != "zakon o parnicnom postupku"


@pytest.mark.parametrize("q,broj", [("prema članu 999 Zakona", "999"), ("člana 39 ZPP", "39"), ("članom 5", "5"), ("čl. 55a KZ", "55a"), ("član 44", "44")])
def test_citirani_clan_u_padezu(q, broj):
    assert _izvuci_broj_clana(q) == broj


def test_clanovi_nadleznosti_zpp():
    z = "zakon o parnicnom postupku"
    assert _clan_nadleznosti_zpp({"law": z, "article": "Član 39"}) and _clan_nadleznosti_zpp({"law": z, "article": "Član 27"})
    assert not _clan_nadleznosti_zpp({"law": z, "article": "Član 367"}) and not _clan_nadleznosti_zpp({"law": "zakon o radu", "article": "Član 39"})


def test_bez_bloka_prakse_navedene_odluke_se_uklanjaju():
    import main as M
    data = {"pravni_zakljucak": "Nadležan je sud u Novom Sadu (čl. 39 ZPP). Sudska praksa: Vrhovni sud, Us 14/2023: sud u Kragujevcu je nadležan.",
            "obrazlozenje": "Sudska praksa potvrđuje nadležnost. Tuženi ima prebivalište u Novom Sadu.",
            "sudska_praksa": [{"sud": "Vrhovni sud", "broj_odluke": "Us 14/2023", "pravni_princip": "x"}]}
    out = M._ukloni_neproverenu_praksu(data)
    assert out["sudska_praksa"] == []
    tekst = " ".join(v for v in out.values() if isinstance(v, str))
    assert "14/2023" not in tekst and "Sudska praksa" not in tekst
    assert "čl. 39 ZPP" in tekst and "prebivalište u Novom Sadu" in tekst


def test_stav_nepodrzan_sazetkom_odluke_se_uklanja():
    import main as M
    kontekst = ("SUDSKA PRAKSA (relevantne odluke iz baze):\n1. Ustavni sud Srbije, Уж-12306/2019\n"
                "   Sažetak: поднео је тужбу Првом општинском суду у Београду ради накнаде нематеријалне штете\n\n"
                "2. AS Beograd, Gž1 100/2020\n   Sažetak: U sporu iz radnog odnosa nadležan je i sud na čijem se području rad obavljao.")
    data = {"pravni_zakljucak": "Opšta mesna nadležnost. Ustavni sud Srbije, Už-12306/2019, potvrđuje nadležnost prema prebivalištu tužioca.",
            "sudska_praksa": [
                {"sud": "Ustavni sud Srbije", "broj_odluke": "Уж-12306/2019", "pravni_princip": "Opšta mesna nadležnost suda prema prebivalištu tužioca."},
                {"sud": "AS Beograd", "broj_odluke": "Gž1 100/2020", "pravni_princip": "U sporu iz radnog odnosa nadležan je i sud na čijem se području rad obavljao."}]}
    out = M._proveri_stavove_prakse(data, kontekst)
    assert [x["broj_odluke"] for x in out["sudska_praksa"]] == ["Gž1 100/2020"]


def test_napomene_stvarna_nadleznost_i_premisa():
    import main as M
    t = M._napomene_nadleznosti("Koji sud je stvarno nadležan za spor dva privredna društva?", "ODGOVOR")
    assert "Zakon o uređenju sudova" in t and "nije u bazi" in t
    t2 = M._napomene_nadleznosti("Da li je po članu 39 Zakona o obligacionim odnosima nadležan sud prebivališta tuženog?", "ODGOVOR")
    assert "ISPRAVKA PREMISE" in t2
    assert M._napomene_nadleznosti("Koliki je rok zastarelosti?", "ODGOVOR") == "ODGOVOR"


@pytest.mark.parametrize("tekst,validan", [
    ("Opšta mesna nadležnost suda prema prebivalištu tužioca.", False),
    ("Opšta mesna nadležnost pripada sudu prebivališta tužioca.", False),
    ("Opšta mesna nadležnost se određuje po prebivalištu tužioca.", False),
    ("Opšta mesna nadležnost određuje se po prebivalištu tuženog, ne tužioca.", True),
    ("ZPP ne predviđa nadležnost po mestu izvršenja ugovora.", True),
    ("Kod teške telesne povrede nadležan je i sud prebivališta tužioca (čl. 44).", True),
    ("Opšte mesno nadležan je sud prebivališta tuženog.", True),
    # revizija N8 F3: tačni iskazi koje su ranija pravila blokirala
    ("Pored opšte mesne nadležnosti, kod izdržavanja nadležan je i sud prebivališta tužioca (čl. 43).", True),
    ("Pored suda opšte mesne nadležnosti nadležan je i sud prema prebivalištu tužioca kod povrede prava ličnosti.", True),
    ("Opšta mesna nadležnost se ne određuje po prebivalištu tužioca.", True),
    ("Opšta mesna nadležnost pripada sudu prebivališta tuženog; sud prebivališta tužioca nadležan je samo izuzetno.", True),
    ("Nadležnost zavisi od mesta ispunjenja ugovora u Srbiji (čl. 53 st. 3).", True),
    ("Treba utvrditi mesto izvršenja ugovora radi obračuna kamate.", True),
])
def test_poznate_greske_o_nadleznosti(tekst, validan):
    import main as M
    assert M._verifikuj_pravne_greske(tekst)[0] is validan


def test_pravila_nadleznosti_odgovaraju_lokalnom_tekstu():
    import main as M
    for clan, recenica in [(39, "tuženi ima prebivalište"), (40, "sedište, prema izveštaju Agencije"), (44, "teške telesne povrede"),
                           (51, "isključivo je mesno nadležan"), (60, "rad obavlja ili se obavljao"), (43, "zakonskom izdržavanju"),
                           (45, "zaštitu prava potrošača"), (46, "povrede prava ličnosti"), (48, "poslednje zajedničko"),
                           (42, "nadležan je sud koji je mesno nadležan za jednog od tuženih")]:
        assert recenica in _clan(clan) and f"čl. {clan}" in M.NADLEZNOST_ZPP_PRAVILA, clan
    assert "Prebivalište TUŽIOCA NIJE osnov opšte nadležnosti" in M.NADLEZNOST_ZPP_PRAVILA
    assert "NEMA opšte pravilo o nadležnosti po mestu izvršenja" in M.NADLEZNOST_ZPP_PRAVILA
    for clan, recenica in [(53, "obaveze koje treba da se ispune"), (55, "moraju da se ispune"), (59, "sud \nmesta plaćanja"),
                           (65, "stranke mogu da se sporazumeju"), (57, "ostavinski postupak"), (58, "izvršni, odnosno stečajni")]:
        assert re.sub(r"\s+", " ", recenica) in _clan(clan) and f"čl. {clan}" in M.NADLEZNOST_ZPP_PRAVILA, clan
    assert "mesto ispunjenja ugovora" not in ZPP.lower() and "mestu ispunjenja ugovora" not in ZPP.lower()


def test_stav_podrzan_istim_clanom_i_sadrzajem_ostaje_a_pogresno_pripisan_se_uklanja():
    """Izmereno R2/R4 (stvarni tok): sažetak je ćirilica i 300 znakova; isti član + sadržaj = podrška; stav suprotan
    sažetku (pristanak poslodavca isključuje zabranu ≠ „zabrana zahteva naknadu“) se uklanja."""
    import main as M
    kontekst = ("SUDSKA PRAKSA (relevantne odluke iz baze):\n"
                "1. Ministarstvo rada, zapošljavanja, boračkih i socijalnih pitanja, sp_misljenje_011-00-00066_2019-02\n"
                "   Sažetak: Prema članu 192 Zakona o radu, poslodavac ne može zaposlenom da otkaže za vreme bolovanja\n\n"
                "2. Apelacioni sud u Nisu, Гж1 3141/2019\n"
                "   Sažetak: Одредбом чл. 187 Закона о раду одређено је да за време трудноће, породиљског одсуства\n\n"
                "3. Apelacioni sud u Beogradu, Гж1 1900/20\n"
                "   Sažetak: Сагласношћу послодавца да се послови обухваћени клаузулом забране конкуренције могу обављати "
                "искључује се примена клаузуле забране конкуренције")
    assert M._kljuc_odluke("sp_misljenje_011-00-00066_2019-02") in M._sazeci_iz_konteksta(kontekst)
    data = {"pravni_zakljucak": "x", "sudska_praksa": [
        {"sud": "AS Niš", "broj_odluke": "Гж1 3141/2019", "pravni_princip": "Zabrana otkaza tokom trudnoće prema članu 187 Zakona o radu.",
         "sazetak_relevantnosti": "Zaposlena uživa posebnu zaštitu."},
        {"sud": "AS Beograd", "broj_odluke": "Гж1 1900/20", "pravni_princip": "Ugovaranje klauzule zabrane konkurencije zahteva isplatu naknade."}]}
    out = M._proveri_stavove_prakse(data, kontekst)
    assert [x["broj_odluke"] for x in out["sudska_praksa"]] == ["Гж1 3141/2019"]
    # isti član bez sadržaja nije dovoljan
    d2 = {"pravni_zakljucak": "x", "sudska_praksa": [
        {"sud": "AS Niš", "broj_odluke": "Гж1 3141/2019", "pravni_princip": "Član 187 propisuje naknadu za prekovremeni rad."}]}
    assert M._proveri_stavove_prakse(d2, kontekst)["sudska_praksa"] == []


def _parsiraj(praksa_context, pitanje, sudska_praksa):
    import json
    import main as M
    data = {"pravni_zakljucak": "Zaključak bez citata.", "obrazlozenje": "Obrazloženje bez citata.", "sudska_praksa": sudska_praksa}
    return M._parsiraj_strukturni_odgovor(json.dumps(data, ensure_ascii=False), "PARNICA", [], praksa_context=praksa_context, pitanje=pitanje)


def test_ozicenje_parsiranja_bez_konteksta_prakse_uklanja_odluke():
    ok, t = _parsiraj("", "Koliki je rok?", [{"sud": "Vrhovni sud", "broj_odluke": "Us 14/2023", "pravni_princip": "x"}])
    assert ok and "14/2023" not in t


def test_ozicenje_parsiranja_proverava_stav_prema_sazetku():
    kontekst = "SUDSKA PRAKSA (relevantne odluke iz baze):\n1. Apelacioni sud u Beogradu, Гж1 1900/20\n   Sažetak: Сагласношћу послодавца искључује се примена клаузуле забране конкуренције"
    ok, t = _parsiraj(kontekst, "Šta je zabrana konkurencije?",
                      [{"sud": "AS Beograd", "broj_odluke": "Гж1 1900/20", "pravni_princip": "Ugovaranje klauzule zabrane konkurencije zahteva isplatu naknade."}])
    assert ok and "1900/20" not in t


def test_ozicenje_parsiranja_dodaje_napomene_nadleznosti():
    ok, t = _parsiraj("", "Da li je po članu 39 Zakona o obligacionim odnosima nadležan sud prebivališta tuženog?", [])
    assert ok and "ISPRAVKA PREMISE" in t


@pytest.mark.parametrize("q,da", [
    ("Tužimo dva tužena iz istog zajma kao solidarne dužnike: jedan ima prebivalište u Somboru, drugi u Leskovcu. Kom sudu podnosimo tužbu?", True),
    ("Koji sud je nadležan kad tužimo više lica jednom tužbom?", True),
    ("Koji sud je mesno nadležan za tužbu protiv fizičkog lica iz Čačka?", False),
])
def test_napomena_vise_tuzenih_navodi_cl_42_doslovno(q, da):
    import main as M
    t = M._napomene_nadleznosti(q, "ODGOVOR")
    assert ("ZPP čl. 42" in t) is da
    if da:
        citat = re.search(r"„(.*?)“", t).group(1)
        assert re.sub(r"\s+", " ", citat) in _clan(42).replace("tuženo više", "tuženo više")


def test_imenovan_drugi_zakon_ostaje_taj_zakon():
    """Revizija N8 F1: „po članu 179 Zakona o radu“ se ranije tražilo kao ZPP čl. 179."""
    from app.services.retrieve import ekstrakcija_clana
    assert ekstrakcija_clana("Koji sud je nadležan za spor o otkazu po članu 179 Zakona o radu?") == ("Član 179", "zakon o radu")
    assert ekstrakcija_clana("Koji sud je nadležan po čl. 154 ZOO?") == ("Član 154", "zakon o obligacionim odnosima")
    assert _prepoznaj_zakon("Koji sud je mesno nadležan po ZPP?") == "zakon o parnicnom postupku"
    assert _prepoznaj_zakon("Koji sud je nadležan po čl. 154 ZOO?") != "zakon o parnicnom postupku"


def test_ispravka_premise_samo_kad_clan_ne_uredjuje_nadleznost():
    import main as M
    assert "ISPRAVKA PREMISE" in M._napomene_nadleznosti("Da li je po članu 39 ZOO nadležan sud prebivališta tuženog?", "")
    # ZPP čl. 39 i članovi bez citata — bez ispravke
    assert "ISPRAVKA PREMISE" not in M._napomene_nadleznosti("Koji sud je nadležan za radni spor po Zakonu o radu?", "")
    assert "ISPRAVKA PREMISE" not in M._napomene_nadleznosti("Da li je po članu 39 ZPP nadležan sud prebivališta tuženog?", "")
    # član drugog zakona koji JESTE pravilo o nadležnosti (lokalni tekst sadrži „nadlež“) — bez ispravke
    pz = M._lokalni_clan("porodicni zakon", "209")
    assert pz is not None and "mesno je nadležan" in pz
    assert "ISPRAVKA PREMISE" not in M._napomene_nadleznosti("Koji sud je mesno nadležan u bračnom sporu po članu 209 Porodičnog zakona?", "")
    # ZOO čl. 328 (polaganje kod stvarno nadležnog suda) jeste pravilo o sudu — bez ispravke; čl. 84 (zastupanje) nije
    assert "ISPRAVKA PREMISE" not in M._napomene_nadleznosti("Koji sud je nadležan po članu 328 ZOO?", "")
    assert "ISPRAVKA PREMISE" in M._napomene_nadleznosti("Koji sud je nadležan po članu 84 ZOO?", "")


def test_napomena_stvarne_samo_kad_se_pita_stvarna():
    import main as M
    assert "nije u bazi" not in M._napomene_nadleznosti("Koji osnovni sud je mesno nadležan za tužbu protiv lica iz Niša?", "")
    assert "nije u bazi" in M._napomene_nadleznosti("Da li je za spor nadležan osnovni ili privredni sud?", "")


def test_broj_odluke_se_poredi_tacno_ne_kao_podniz():
    import main as M
    kontekst = ("SUDSKA PRAKSA (relevantne odluke iz baze):\n1. VKS, Rev 1/2019\n   Sažetak: naknada štete zbog povrede na radu poslodavac odgovara\n\n"
                "2. VKS, Rev 1/20\n   Sažetak: otkaz ugovora o zakupu stana zakupodavac mora dostaviti pismeno")
    data = {"pravni_zakljucak": "x", "sudska_praksa": [
        {"sud": "VKS", "broj_odluke": "Rev 1/20", "pravni_princip": "Otkaz ugovora o zakupu stana zakupodavac mora dostaviti pismeno."},
        {"sud": "VKS", "broj_odluke": "Rev 1/2", "pravni_princip": "Naknada štete zbog povrede na radu, poslodavac odgovara."}]}
    out = M._proveri_stavove_prakse(data, kontekst)
    assert [x["broj_odluke"] for x in out["sudska_praksa"]] == ["Rev 1/20"]
    assert M._kljuc_odluke("Уж-12306/2019") == M._kljuc_odluke("Už 12306/2019")


def test_sazetak_u_jednom_redu_i_red_sa_brojem_nije_zaglavlje():
    import main as M
    ctx = M._format_praksa_context([{"court": "AS Beograd", "decision_number": "Gž 5/2021",
                                     "text": "Prvi red sažetka\n2. tačka obrazloženja: zakupac mora platiti zakupninu"}])
    sz = M._sazeci_iz_konteksta(ctx)
    assert list(sz) == [M._kljuc_odluke("Gž 5/2021")] and "zakupac mora platiti" in sz[M._kljuc_odluke("Gž 5/2021")]


def test_uklanjanje_prakse_ne_brise_zakonske_recenice():
    import main as M
    data = {"pravni_zakljucak": "Upravni sud odlučuje po Zakonu o upravnim sporovima (Službeni glasnik RS br 111/2009). Prema čl. 154 ZOO odgovara štetnik.",
            "sudska_praksa": [{"sud": "VKS", "broj_odluke": "154", "pravni_princip": "x"}]}
    out = M._ukloni_neproverenu_praksu(data)
    assert "111/2009" in out["pravni_zakljucak"] and "Prema čl. 154 ZOO odgovara štetnik." in out["pravni_zakljucak"]
