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


@pytest.mark.parametrize("pitanje,clan,zakon", [
    ("Šta propisuje član 27 Zakona o uređenju sudova?", "27", "zakon o uredjenju sudova"),
    ("Koji sud je stvarno nadležan za spor dva privredna društva prema članu 27 Zakona o uređenju sudova?",
     "27", "zakon o uredjenju sudova"),
    ("Prema članu 27. st. 1. tač. 1) Zakona o uređenju sudova, koji sud sudi?", "27", "zakon o uredjenju sudova"),
    ("Prema Zakonu o uređenju sudova, čl. 24, koji sud sudi?", "24", "zakon o uredjenju sudova"),
    ("Šta propisuje član 27 ZUS u upravnom sporu?", "27", "zakon o upravnim sporovima"),
    ("Da li je član 27 ZPP usklađen sa Zakonom o uređenju sudova, član 27?", "27", "zakon o parnicnom postupku"),
])
def test_tacan_clan_zakona_o_uredjenju_sudova(pitanje, clan, zakon):
    from app.services.retrieve import ekstrakcija_clana
    assert ekstrakcija_clana(pitanje) == (f"Član {clan}", zakon)


def test_tacan_statiski_izvod_zus_ulazi_u_prompt_bez_pripisivanja_bazi(monkeypatch):
    import json
    from unittest.mock import Mock
    import main as M

    def ne_sme():
        raise AssertionError("Static court-law excerpt must not use corpus exact lookup")

    monkeypatch.setattr(M, "_cache_get", Mock(return_value=None))
    monkeypatch.setattr(M, "_cache_set", Mock())
    monkeypatch.setattr(M, "retrieve_sudska_praksa", Mock(return_value=[]))
    monkeypatch.setattr(M, "retrieve_misljenja", Mock(return_value=[]))
    monkeypatch.setattr(M, "retrieve_documents", Mock(return_value=([], {
        "confidence": "LOW", "top_score": 0.0, "top_article": "", "top_law": "",
    })))
    exact = Mock(side_effect=lambda *args, **kwargs: ne_sme())
    monkeypatch.setattr(M, "_direktan_fetch_clana", exact)
    model = Mock(return_value=json.dumps({
        "pravni_zakljucak": "Za spor dva privredna društva nadležan je privredni sud.",
        "obrazlozenje": "Merodavan je član 27 Zakona o uređenju sudova.",
    }, ensure_ascii=False))
    monkeypatch.setattr(M, "_pozovi_openai", model)

    result = M.ask_agent(
        "Koji sud je stvarno nadležan za spor dva privredna društva prema članu 27 Zakona o uređenju sudova?"
    )

    exact.assert_not_called()
    model.assert_called_once()
    prompt = model.call_args.args[1]
    assert prompt.count("ČLAN: Član 27") == 1
    assert "ČLAN: Član 24" not in prompt and "ČLAN: Član 25" not in prompt
    assert "statički izvod proveren" in prompt and "https://ob.pk.sud.rs/" in prompt
    assert result["status"] == "success" and not result.get("blocked")
    assert result["top_law"] == "zakon o uredjenju sudova" and result["top_article"] == "Član 27"
    assert "direktno pronadjen u bazi" not in result["data"]

    model.reset_mock()
    missing = M.ask_agent("Šta propisuje član 26 Zakona o uređenju sudova?")
    assert missing["status"] == "error" and missing["retrieval_unavailable"]
    assert not missing["blocked"] and "ne postoji" in missing["data"]
    exact.assert_not_called()
    model.assert_not_called()


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


# ── S1-C5 (revizija M1): krivična, upravna i pitanja o odluci ne idu u tok građanske nadležnosti ──

@pytest.mark.parametrize("q", [
    "Koji sud sudi za ubistvo?",
    "Koji sud odlučuje o pritvoru okrivljenog?",
    "Koji sud je nadležan za ekstradiciju?",
    "Koji sud je nadležan za izdavanje evropskog naloga za hapšenje?",
    "Kom sudu se podnosi tužba protiv rešenja Poreske uprave?",
    "Koji je sud zauzeo stav o zastarelosti potraživanja iz ugovora o zajmu?",
    "Koji sud je doneo presudu Rev 1234/2020 o otkazu?",
    "Pred kojim sudom se vodi postupak za lišenje poslovne sposobnosti?",
    "Koji sud je nadležan za vraćanje deteta po Haškoj konvenciji?",
    # 3. krug revizije: krivična pitanja sa rečima „šteta“ / „tužilac“
    "Koji sud je nadležan za ubistvo ako je javni tužilac podigao optužnicu u Nišu?",
    "Koji sud je nadležan da sudi okrivljenom za prevaru kojom je pričinjena šteta od pet miliona dinara?",
    "Koji sud odlučuje o produženju pritvora kada je tužilaštvo predložilo produženje?",
    "Koji sud je nadležan za poresku utaju kojom je budžetu naneta šteta?",
    "Koji sud je nadležan za suđenje osumnjičenom za pranje novca, gde je šteta veća od milion?",
    "Koji sud je nadležan za privatnu tužbu za uvredu protiv okrivljenog?",
    "Koji sud je nadležan za tužbu kao privatni tužilac za uvredu?",
])
def test_s1_nije_gradjanska_nadleznost(q):
    from app.services.retrieve import je_pitanje_gradjanske_nadleznosti
    assert not je_pitanje_gradjanske_nadleznosti(q)


@pytest.mark.parametrize("q", [
    "Moj klijent iz Beograda želi da tuži fizičko lice koje ima prebivalište u Novom Sadu radi vraćanja duga. Koji sud je mesno nadležan?",
    "Gde da podnesem tužbu za uznemiravanje na radu?",
    "Kom sudu podnosimo tužbu protiv dva solidarna dužnika?",
    # revizija S1-E: građanske tužbe sa rečima krivičnog/poreskog konteksta
    "Kom sudu se podnosi tužba za naknadu štete zbog neosnovanog pritvora?",
    "Koji sud je nadležan za tužbu za nematerijalnu štetu od ubistva člana porodice?",
    "Koji sud je mesno nadležan za tužbu za naknadu štete koju je okrivljeni prouzrokovao u saobraćajnoj nezgodi?",
    "Kom sudu podnosim tužbu protiv poreskog savetnika zbog pogrešnog saveta?",
    "Koji sud je nadležan ako je tuženi direktor osumnjičen u drugom postupku?",
    "Koji sud je mesno nadležan za tužbu radi duga ako poslovna sposobnost tuženog nije sporna?",
    "Koji sud je nadležan za zahtev za štetu zbog neosnovanog pritvora?",
    "Koji sud je nadležan za regresni zahtev osiguravača zbog štete koju je okrivljeni prouzrokovao?",
    "Koji sud je nadležan kada tražim štetu od osumnjičenog koji mi je razbio auto?",
])
def test_s1_gradjanska_nadleznost_i_dalje(q):
    from app.services.retrieve import je_pitanje_gradjanske_nadleznosti
    assert je_pitanje_gradjanske_nadleznosti(q)


@pytest.mark.parametrize("odgovor,ok", [
    ("Prema članu 39 ZPP. Član 39 ZPP uređuje opšte pravilo. Prema članu 40 ZPP sedište je merodavno. "
     "Za stvarnu nadležnost primenjuje se član 27 Zakona o uređenju sudova.", True),
    ("Stvarno je nadležan privredni sud po čl. 27 ZUS, a sedište tuženog je merodavno po čl. 40 ZPP.", True),
    ("ЗУС члан 27 и члан 40 ЗПП уређују стварну и месну надлежност.", True),
    ("Prema čl. 40 ZUS sedište tuženog je merodavno.", False),
    ("Prema članu 40 ZOO sedište određuje sud.", False),
    ("Prema članu 999 ZPP sedište određuje sud.", False),
    ("Prema članu 40 ZPP. Takođe član 999 ZPP.", False),
])
def test_n8_tema_nadleznosti_proverava_zakon_i_clan(odgovor, ok):
    from main import _ZUS_KONTEKST, _proveri_tematsku_relevantnost
    docs = [
        "ZAKON: Zakon o parničnom postupku\nČLAN: Član 39\nOpšta mesna nadležnost prema prebivalištu tuženog.",
        "ZAKON: Zakon o parničnom postupku\nČLAN: Član 40\nMesna nadležnost prema sedištu pravnog lica.",
        "ZAKON: Zakon o obligacionim odnosima\nČLAN: Član 40\nUgovor se može zaključiti na drugi način.",
    ] + _ZUS_KONTEKST
    pitanje = "Koji je mesno i stvarno nadležan sud za spor dva privredna društva zbog isporuke po ugovoru?"
    assert _proveri_tematsku_relevantnost(pitanje, odgovor, docs)[0] is ok


_N8_TEST_COMPANY = (
    "Dva privredna društva se spore zbog isporuke opreme. Tuženi DOO ima sedište u Nišu. "
    "Koja je stvarna i opšta mesna nadležnost?"
)
_N8_TEST_NATURAL = (
    "Tuženi je fizičko lice sa prebivalištem u Novom Sadu i boravištem u Beogradu. "
    "Koja je opšta mesna nadležnost?"
)


@pytest.mark.parametrize("pitanje,odgovor,dozvoljen", [
    (_N8_TEST_COMPANY, "Zastarelost: Nije primenljivo jer se radi o ugovornom sporu.", False),
    (_N8_TEST_COMPANY, "Рокови застарелости: не примењују се на уговорна потраживања.", False),
    (_N8_TEST_COMPANY, "Član nije pronađen u bazi. Zastarelost nije primenljiva na ugovorna potraživanja.", False),
    (_N8_TEST_COMPANY, "Zastarelost: nije primenljiva na pitanje nadležnosti u ugovornom sporu.", True),
    (_N8_TEST_COMPANY, "Rokovi zastarelosti nisu predmet pitanja. Za ugovorna potraživanja mogu važiti posebni rokovi.", True),
    (_N8_TEST_NATURAL, "Oba suda su mesno nadležna prema prebivalištu i boravištu tuženog.", False),
    (_N8_TEST_NATURAL, "Oba suda su mesno nadležna ako okolnosti upućuju na duži boravak.", True),
    (_N8_TEST_NATURAL, "Sud boravišta može biti nadležan kod dužeg boravka, ali to nije slučaj ovde jer nema informacija o dužem boravku u Beogradu.", False),
    (_N8_TEST_NATURAL, "Sud boravišta može biti nadležan kod dužeg boravka, ali to nije slučaj ovde jer prebivalište ima prednost.", False),
    (_N8_TEST_NATURAL + " Poznato je da će tuženi u Beogradu boraviti duže vreme.",
     "Oba suda su mesno nadležna.", True),
    (_N8_TEST_NATURAL + " Nije poznato da li će tu boraviti duže vreme.", "Oba suda su mesno nadležna.", False),
    (_N8_TEST_NATURAL, "Ako tužilac to želi, oba suda su mesno nadležna.", False),
    ("Gde podneti jednu tužbu protiv dva materijalna suparničara?", "Oba suda su mesno nadležna.", True),
    ("Tuženi je DOO i ne znamo sedište. Koja je opšta mesna nadležnost?",
     "Nadležnost se određuje prema ZPP čl. 39. Proveriti sedište iz APR-a.", False),
    ("Tuženi je DOO i ne znamo sedište. Koja je opšta mesna nadležnost?",
     "Za fizička lica važi čl. 39 ZPP. Za DOO je merodavan čl. 40 ZPP. Potreban je izveštaj APR-a.", True),
])
def test_n8_dokazana_pravna_greska_ne_dospeva_u_odgovor(pitanje, odgovor, dozvoljen):
    import main as M
    assert M._verifikuj_pravne_greske(odgovor, pitanje=pitanje)[0] is dozvoljen


def test_n8_cache_samo_za_pitanja_o_nadleznosti_menja_verziju():
    import hashlib
    import main as M

    pitanje_drugo = "Koliki je opšti rok zastarelosti po ZOO?"
    def prethodni_kljuc(q):
        return hashlib.md5(
            f"{M._CACHE_VERZIJA}|{M._normalizuj_za_cache(q)}".encode(), usedforsecurity=False,
        ).hexdigest()

    assert M._cache_kljuc(_N8_TEST_COMPANY) != prethodni_kljuc(_N8_TEST_COMPANY)
    assert M._cache_kljuc(pitanje_drugo) == prethodni_kljuc(pitanje_drugo)


@pytest.mark.parametrize("pitanje,preskoci_stari", [
    ("Šta propisuje član 27 Zakona o uređenju sudova?", True),
    ("Šta propisuje čl. 27, st. 1, tač. 1 Zakona o uređenju sudova?", True),
    ("Шта прописује члан 27 Закона о уређењу судова?", True),
    ("Šta propisuje član 27 ZUS u upravnom sporu?", False),
    ("Koliki je opšti rok zastarelosti po ZOO?", False),
])
def test_n8_cache_izricitog_zakona_ne_preuzima_stari_odgovor(pitanje, preskoci_stari, monkeypatch):
    import hashlib
    from unittest.mock import Mock
    import main as M

    stari_kljuc = hashlib.md5(
        f"{M._CACHE_VERZIJA}|{M._normalizuj_za_cache(pitanje)}".encode(), usedforsecurity=False,
    ).hexdigest()
    odgovor = {"status": "success", "data": "Prethodno sačuvani odgovor."}
    monkeypatch.delenv("VINDEX_CACHE_BYPASS", raising=False)
    monkeypatch.setattr(M, "_CACHE", {stari_kljuc: (odgovor, M.datetime.now())})
    l2 = Mock(side_effect={stari_kljuc: odgovor}.get)
    monkeypatch.setattr(M, "_supa_cache_get", l2)

    if preskoci_stari:
        assert M._cache_get(pitanje) is None
        l2.assert_called_once_with(M._cache_kljuc(pitanje))
        assert l2.call_args.args[0] != stari_kljuc
    else:
        assert M._cache_get(pitanje) == odgovor
        l2.assert_not_called()


@pytest.mark.parametrize("confidence", ["HIGH", "MEDIUM"])
def test_n8_stvarni_tok_blokira_izmereni_pogresan_zakljucak_pre_kesa(monkeypatch, confidence):
    import json
    from unittest.mock import Mock

    import main as M

    article = "ZAKON: Zakon o parničnom postupku\nČLAN: Član 40\n" + _clan(40)
    metadata = {
        "confidence": confidence, "top_score": 0.8, "top_article": "Član 40",
        "top_law": "Zakon o parničnom postupku",
    }
    monkeypatch.setattr(M, "retrieve_documents", lambda *a, **k: ([article], metadata))
    monkeypatch.setattr(M, "retrieve_sudska_praksa", lambda *a, **k: [])
    monkeypatch.setattr(M, "retrieve_misljenja", lambda *a, **k: [])
    monkeypatch.setattr(M, "_cache_get", lambda *a: None)
    monkeypatch.setattr(M, "klasifikuj_pitanje", lambda *a: "PARNICA")
    cache = Mock()
    monkeypatch.setattr(M, "_cache_set", cache)
    provider = Mock(return_value=json.dumps({
        "pravni_zakljucak": "Za tuženog je mesno merodavno sedište.",
        "kada_ne_vazi": "Zastarelost: Nije primenljivo jer se radi o ugovornom sporu.",
    }))
    monkeypatch.setattr(M, "_pozovi_openai", provider)

    rezultat = M.ask_agent(_N8_TEST_COMPANY)

    assert rezultat["status"] == "success"
    assert rezultat.get("blocked") is True
    assert "potraživanje može zastareti" in rezultat["data"].lower()
    assert "nije primenljivo jer" not in rezultat["data"].lower()
    provider.assert_called_once()
    assert "Nije predmet pitanja" in provider.call_args.args[0]
    assert "čl. 39 st. 3" in provider.call_args.args[0]
    cache.assert_not_called()


@pytest.mark.parametrize("pitanje", [
    "Šta propisuje čl. 27, st. 1, tač. 1 Zakona o uređenju sudova?",
    "Шта прописује члан 27 Закона о уређењу судова?",
])
def test_n8_izricit_naziv_sudskog_zakona_sa_interpunkcijom_i_cirilicom(pitanje):
    from app.services.retrieve import ekstrakcija_clana

    assert ekstrakcija_clana(pitanje) == ("Član 27", "zakon o uredjenju sudova")
