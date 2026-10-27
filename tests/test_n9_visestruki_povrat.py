# -*- coding: utf-8 -*-
"""N9 — višestruki povrat (KZ čl. 55a): istina iz LOKALNOG teksta zakonika, deterministički uslovi i raspon,
prepoznavanje činjenica iz pitanja i ožičenje u `ask_agent` (bez mreže; stvarni tok meri skripta izveštaja N9)."""
from datetime import date
from pathlib import Path
import re

import pytest

from shared import visestruki_povrat as V
from shared.visestruki_povrat import DA, NE, NEPOZNATO, RanijaOsuda, blok, izracunaj, iz_pitanja, je_pitanje_o_povratu

KZ = (Path(__file__).resolve().parent.parent / "data" / "laws" / "pdfs" / "krivicni_zakonik.pdf").read_text(encoding="utf-8")
GOD, MES = 360, 30


def _clan(oznaka):
    m = re.search(rf"^Član {oznaka}\s*$(.*?)(?=^Član \d+\w?\s*$)", KZ, re.M | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def test_citat_55a_je_doslovno_lokalni_tekst():
    assert V.CITAT_55A in _clan("55a")   # telo člana nosi i naslov sledećeg („Ublažavanje kazne“)
    assert "ne može biti kraća od trideset dana niti duža od dvadeset godina" in _clan(45)
    assert "izriče se na pune godine i mesece, a do šest meseci i na dane" in _clan(45)
    assert "osuđeni se smatra neosuđivanim" in _clan(97)
    assert _clan("55b") == ""


def _sve_da(mn, mx):
    return izracunaj(novo_delo_umisljaj=True, propisan_min_dana=mn, propisan_max_dana=mx,
                     ranije_osude=[RanijaOsuda(True, 24), RanijaOsuda(True, 12)], proteklo_od_otpusta_meseci=24)


@pytest.mark.parametrize("mn,mx,polovina,najniza", [
    (1 * GOD, 8 * GOD, 4 * GOD + 6 * MES, 4 * GOD + 7 * MES),      # 1–8 god: polovina 4g6m, „iznad“ na pune mesece 4g7m
    (6 * MES, 5 * GOD, 2 * GOD + 9 * MES, 2 * GOD + 10 * MES),     # 6 mes–5 god
    (2 * GOD, 10 * GOD, 6 * GOD, 6 * GOD + 1 * MES),               # 2–10 god
    (30, 6 * MES, 105, 106),                                       # ispod šest meseci se izriče i na dane
])
def test_raspon_iznad_polovine(mn, mx, polovina, najniza):
    r = _sve_da(mn, mx)
    assert r.primenjuje_se == DA
    assert r.raspon["polovina_raspona_dana"] == polovina and r.raspon["najniza_dozvoljena_dana"] == najniza
    assert r.raspon["najvisa_dana"] == mx          # maksimum se ne prekoračuje


def test_bez_propisanog_minimuma_vazi_opsti_minimum_30_dana():
    r = izracunaj(**{**iz_pitanja("Ranije je dva puta osuđen na zatvor od po dve godine za umišljajna dela, otpušten je pre "
                                  "dve godine, a sada je sa umišljajem učinio delo za koje je propisan zatvor do tri godine.")})
    assert r.primenjuje_se == DA and r.raspon["propisano_od_dana"] == 30
    assert r.raspon["polovina_raspona_dana"] == 30 + (3 * GOD - 30) / 2
    assert any("opšti minimum" in n for n in r.napomene) and any("30 dana" in n for n in r.napomene)


@pytest.mark.parametrize("osude,stanje", [
    ([RanijaOsuda(True, 24), RanijaOsuda(True, 12)], DA),
    ([RanijaOsuda(True, 6), RanijaOsuda(True, 6)], NE),            # V5: kazne kraće od godinu dana
    ([RanijaOsuda(True, 24), RanijaOsuda(False, 24)], NE),         # jedno delo iz nehata
    ([RanijaOsuda(True, 24)], NE),                                 # jedna osuda
    ([RanijaOsuda(True, 24), RanijaOsuda(None, 24)], NEPOZNATO),   # krivica nepoznata
    ([RanijaOsuda(True, 24), RanijaOsuda(True, None)], NEPOZNATO), # visina nepoznata
    ([RanijaOsuda(True, 24), RanijaOsuda(True, 6), RanijaOsuda(True, 18)], DA),
])
def test_uslov_1_dve_ranije_osude(osude, stanje):
    r = izracunaj(novo_delo_umisljaj=True, propisan_min_dana=GOD, propisan_max_dana=8 * GOD, ranije_osude=osude,
                  proteklo_od_otpusta_meseci=12)
    assert r.uslovi[2].stanje == stanje


@pytest.mark.parametrize("otpust,delo,stanje", [
    (date(2021, 3, 1), date(2026, 2, 28), DA),
    (date(2021, 3, 1), date(2026, 3, 1), NE),       # navršeno pet godina — „nije proteklo“ više ne važi
    (date(2020, 2, 29), date(2025, 2, 27), DA),     # prestupna godina
])
def test_uslov_2_tacni_datumi(otpust, delo, stanje):
    r = izracunaj(novo_delo_umisljaj=True, propisan_min_dana=GOD, propisan_max_dana=8 * GOD,
                  ranije_osude=[RanijaOsuda(True, 24)] * 2, otpust=otpust, novo_delo=delo)
    assert r.uslovi[3].stanje == stanje


@pytest.mark.parametrize("meseci,stanje", [(36, DA), (84, NE), (60, NEPOZNATO), (58, NEPOZNATO)])
def test_uslov_2_priblizan_navod_na_granici_se_ne_odlucuje(meseci, stanje):
    r = izracunaj(novo_delo_umisljaj=True, propisan_min_dana=GOD, propisan_max_dana=8 * GOD,
                  ranije_osude=[RanijaOsuda(True, 24)] * 2, proteklo_od_otpusta_meseci=meseci)
    assert r.uslovi[3].stanje == stanje
    if stanje == NEPOZNATO:
        assert r.primenjuje_se == NEPOZNATO and r.raspon is None


def test_novo_delo_iz_nehata_iskljucuje_55a():
    r = izracunaj(novo_delo_umisljaj=False, propisan_min_dana=GOD, propisan_max_dana=8 * GOD,
                  ranije_osude=[RanijaOsuda(True, 24)] * 2, proteklo_od_otpusta_meseci=12)
    assert r.primenjuje_se == NE and r.raspon is None


V2 = ("Okrivljeni je ranije dva puta osuđen na zatvor od po dve godine za krađe učinjene sa umišljajem, sa izdržavanja kazne je "
      "otpušten pre tri godine, a sada je sa umišljajem izvršio tešku krađu za koju je propisan zatvor od jedne do osam godina. "
      "U kom rasponu sud mora da izrekne kaznu?")
V5 = ("Okrivljeni je dva puta osuđen na zatvor od po šest meseci za umišljajna dela i otpušten je pre dve godine. Sada je sa "
      "umišljajem učinio delo za koje je propisan zatvor od šest meseci do pet godina. Da li se primenjuje višestruki povrat?")
V6 = ("Okrivljeni je dva puta osuđen na zatvor od po tri godine za umišljajna dela, otpušten je pre sedam godina, a sada je "
      "učinio umišljajno delo sa propisanim zatvorom od dve do deset godina. Da li se primenjuje član 55a KZ?")


@pytest.mark.parametrize("q,primena", [(V2, DA), (V5, NE), (V6, NE)])
def test_cinjenice_iz_pitanja_daju_izmeren_ishod(q, primena):
    assert izracunaj(**iz_pitanja(q)).primenjuje_se == primena


def test_v2_raspon_u_tekstu_bloka():
    t, r = blok(V2)
    assert "više od 4 godine i 6 meseci, najviše 8 godina zatvora" in t and "4 godine i 7 meseci" in t
    assert "NE predviđanje kazne" in t and "čl. 54" in t


def test_v6_propisan_zatvor_bez_reci_propisan_je():
    # „sa propisanim zatvorom od dve do deset godina“
    c = iz_pitanja(V6)
    assert (c["propisan_min_dana"], c["propisan_max_dana"]) == (2 * GOD, 10 * GOD)


def test_pojedinacne_ranije_kazne_i_datumi():
    q = ("Učinilac je ranije dva puta osuđen za umišljajna dela, na zatvor od dve godine i na zatvor od osam meseci. "
         "Otpušten je 01.03.2022, a novo delo sa umišljajem izvršio je 15.01.2025. Za delo je propisan zatvor od jedne do deset godina.")
    c = iz_pitanja(q)
    assert [o.zatvor_meseci for o in c["ranije_osude"]] == [24, 8]
    assert (c["otpust"], c["novo_delo"]) == (date(2022, 3, 1), date(2025, 1, 15))
    assert izracunaj(**c).primenjuje_se == NE      # druga kazna je kraća od godinu dana


@pytest.mark.parametrize("q", [
    "Za delo je propisan doživotni zatvor ili zatvor od deset do dvadeset godina; ranije dva puta osuđen na zatvor od po tri godine.",
    "Ranije dva puta osuđen na zatvor od po tri godine, za novo delo propisan zatvor od pet do četrdeset godina.",
])
def test_nepodrzan_raspon_se_ne_racuna(q):
    c = iz_pitanja(q)
    assert c["propisan_max_dana"] is None


@pytest.mark.parametrize("q,da", [
    ("Šta je višestruki povrat po Krivičnom zakoniku?", True), ("Kako se primenjuje čl. 55a KZ?", True), (V2, True),
    ("Povrat kao otežavajuća okolnost kod odmeravanja kazne?", True),
    ("Kako da tražim povrat novca od prodavca?", False), ("Rok za povrat poreza na dohodak?", False),
    ("Koji sud je mesno nadležan za tužbu protiv lica iz Čačka?", False),
])
def test_prepoznavanje_pitanja_o_povratu(q, da):
    assert je_pitanje_o_povratu(q) is da


def test_nepostojeci_clan_kz_se_imenuje_a_postojeci_ne():
    t, _ = blok("Prema članu 55b Krivičnog zakonika, koliko se povećava kazna za višestruki povrat?")
    assert "Član 55b ne postoji u Krivičnom zakoniku" in t
    t2, _ = blok("Da li po članu 55a KZ sud kod višestrukog povrata izriče kaznu iznad propisanog maksimuma?")
    assert "ne postoji" not in t2 and "raspon propisane kazne se ne prekoračuje" in t2


def test_blok_ne_tvrdi_stav_sudske_prakse():
    t, _ = blok(V2)
    assert "nije rešeno izvorom u bazi" in t
    assert not re.search(r"Vrhovn\w* (kasacion\w* )?sud\w* (je )?(zauzeo|stav)", t)


# ── ožičenje u ask_agent ───────────────────────────────────────────────────────────────────────────────────────────

def _odgovor(zakljucak, **dodatno):
    return {"status": "success", "data": f"--- PRAVNI ZAKLJUČAK\n{zakljucak}\n\n--- PRAVNI OSNOV\nKZ čl. 55a", **dodatno}


def test_pogresan_zakljucak_modela_se_zamenjuje_i_upozorava():
    import main as M
    ulaz = _odgovor("Pojam se primenjuje jer su ispunjeni uslovi iz člana 55a KZ.")
    izlaz = M._dodaj_proracun_povrata(V6, ulaz)
    assert "--- PRORAČUN: VIŠESTRUKI POVRAT" in izlaz["data"] and izlaz["proracun_povrata"] == NE
    zak = izlaz["data"].split("--- PRAVNI ZAKLJUČAK\n", 1)[1].split("\n\n", 1)[0]
    assert "ne primenjuje" in zak and "ispunjeni uslovi" not in zak
    assert ulaz["data"].startswith("--- PRAVNI ZAKLJUČAK")    # ulaz (moguće iz keša) se ne menja


def test_upozorenje_kad_drugi_deo_teksta_tvrdi_primenu():
    import main as M
    ulaz = {"status": "success", "data": "--- PRAVNI ZAKLJUČAK\nx\n\n--- BRZA PROCENA\nUslovi su ispunjeni za strožu kaznu."}
    assert "UPOZORENJE" in M._dodaj_proracun_povrata(V5, ulaz)["data"]
    assert "UPOZORENJE" not in M._dodaj_proracun_povrata(V5, _odgovor("Uslovi nisu ispunjeni."))["data"]


def test_blokiran_odgovor_dobija_proracun():
    import main as M
    izlaz = M._dodaj_proracun_povrata(V2, {"status": "success", "blocked": True, "data": "Odgovor je blokiran."})
    assert "više od 4 godine i 6 meseci" in izlaz["data"] and "ne zavisi od njega" in izlaz["data"]


def test_blokada_bez_zastavice_se_prepoznaje_po_tekstu():
    import main as M
    izlaz = M._dodaj_proracun_povrata("Šta je višestruki povrat?", {"status": "success", "data": "--- PRAVNI ZAKLJUČAK\nOdgovor je blokiran jer..."})
    assert "ne zavisi od njega" in izlaz["data"]


def test_ostala_pitanja_i_greske_se_ne_diraju():
    import main as M
    o = _odgovor("Nadležan je sud u Novom Sadu.")
    assert M._dodaj_proracun_povrata("Koji sud je mesno nadležan?", o) is o
    g = {"status": "error", "message": "Sistem je trenutno zauzet."}
    assert M._dodaj_proracun_povrata(V2, g) is g


def test_ask_agent_je_ozicen_i_na_grani_iz_kesa(monkeypatch):
    import main as M
    assert M.ask_agent.__wrapped__ is not None
    monkeypatch.setattr(M, "_cache_get", lambda q: _odgovor("Pojam se primenjuje jer su ispunjeni uslovi iz člana 55a KZ."))
    izlaz = M.ask_agent(V5)
    assert izlaz.get("from_cache") and "--- PRORAČUN: VIŠESTRUKI POVRAT" in izlaz["data"] and izlaz["proracun_povrata"] == NE



# ── nezavisna revizija N9: svaki reprodukovan nalaz kao regresioni test ────────────────────────────────────────────
P = "Okrivljeni je dva puta osuđen na zatvor od po dve godine za umišljajna dela, otpušten je pre tri godine, "
NOVO = "a sada je sa umišljajem učinio delo za koje je propisan zatvor od jedne do osam godina."


def _ishod(q):
    return izracunaj(**iz_pitanja(q)).primenjuje_se


@pytest.mark.parametrize("q,ocekivano", [
    (P + NOVO, DA),
    (P + "a sada je bez umišljaja učinio delo za koje je propisan zatvor od jedne do osam godina.", NE),
    (P + "a sada je učinio delo koje nije umišljajno, propisan zatvor od jedne do osam godina.", NE),
    ("Okrivljeni je dva puta osuđen na zatvor od po dve godine za neumišljajna dela, otpušten je pre tri godine, " + NOVO, NE),
    ("Okrivljeni je dva puta osuđen na zatvor od po dve godine, prvi put za umišljajno delo, a drugi put za delo iz nehata, "
     "otpušten je pre tri godine, " + NOVO, NEPOZNATO),                                         # mešovita krivica
    ("Saučesnik je dva puta osuđen na zatvor od po tri godine za umišljajna dela i otpušten pre dve godine, a okrivljeni nije "
     "ranije osuđivan. Sada je okrivljeni sa umišljajem učinio delo za koje je propisan zatvor od jedne do osam godina.", NEPOZNATO),
    ("Okrivljeni je dva puta osuđen uslovnom osudom na zatvor od po dve godine za umišljajna dela, " + NOVO, NEPOZNATO),
    ("Okrivljeni je dva puta osuđen na zatvor od po dve godine za umišljajna dela, uslovno je otpušten pre tri godine, " + NOVO, NEPOZNATO),
    ("Okrivljeni je osuđen dva puta na zatvor od po dve godine za umišljajna dela. Prvi put je otpušten pre osam godina, drugi put "
     "pre tri godine. Sada je sa umišljajem učinio delo za koje je propisan zatvor od jedne do osam godina.", NEPOZNATO),
    ("Okrivljeni je dva puta osuđen na zatvor od po dve godine za umišljajna dela, otpust je predložen 01.01.2018, a otpušten je "
     "10.10.2020. Novo delo sa umišljajem učinio je 05.05.2024, propisan zatvor od jedne do osam godina.", NEPOZNATO),
    ("Okrivljeni je dva puta osuđen na zatvor od po dve godine za umišljajna dela, otpušten je pre više od pet godina, " + NOVO, NE),
    ("Okrivljeni je dva puta osuđen na zatvor od po godinu dana za umišljajna dela, otpušten je pre godinu dana, " + NOVO, DA),
    ("Okrivljeni je dva puta osuđen na zatvor od po pola godine za umišljajna dela, otpušten je pre tri godine, " + NOVO, NE),
])
def test_revizija_parser_ne_pogadja(q, ocekivano):
    assert _ishod(q) == ocekivano


def test_revizija_godina_datuma_nije_broj_osuda_i_novo_delo_pre_otpusta_se_ne_racuna():
    c = iz_pitanja("Za delo koje je učinio 01.01.2010 osuđen je; ukupno je dva puta osuđen na zatvor od po dve godine za umišljajna "
                   "dela, otpušten je 10.10.2020. Novo delo sa umišljajem izvršeno je 05.05.2024. Propisan zatvor od jedne do osam godina.")
    assert c["broj_ranijih_osuda"] == 2 and c["otpust"] == date(2020, 10, 10) and c["novo_delo"] == date(2024, 5, 5)
    c2 = iz_pitanja("Dva puta osuđen na zatvor od po dve godine za umišljajna dela, otpušten je 10.10.2020. Sada je izvršio delo "
                    "sa umišljajem 05.05.2019, propisan zatvor od jedne do osam godina.")
    assert c2["otpust"] is None and c2["novo_delo"] is None


def test_revizija_raspon_ranijeg_dela_se_ne_koristi():
    c = iz_pitanja("Ranije je dva puta osuđen za krađu (za koju je propisan zatvor od šest meseci do pet godina) na zatvor od po dve "
                   "godine za umišljajna dela, otpušten je pre tri godine, a sada je sa umišljajem učinio tešku krađu za koju je "
                   "propisan zatvor od jedne do osam godina.")
    assert (c["propisan_min_dana"], c["propisan_max_dana"]) == (GOD, 8 * GOD)
    assert [o.zatvor_meseci for o in c["ranije_osude"]] == [24, 24]


@pytest.mark.parametrize("q,raspon", [
    (P + "a sada je sa umišljajem učinio delo; zakon predviđa zatvor od dve do deset godina.", (2 * GOD, 10 * GOD)),
    (P + "a sada je sa umišljajem učinio tešku krađu (zatvor od 2 do 10 godina).", (2 * GOD, 10 * GOD)),
    (P + "a sada je sa umišljajem učinio delo za koje je propisan zatvor i novčana kazna.", (None, None)),
    (P + "a sada je sa umišljajem učinio delo za koje je propisan zatvor od jedne do pet godina i novčana kazna.", (None, None)),
])
def test_revizija_formulacije_raspona(q, raspon):
    c = iz_pitanja(q)
    assert (c["propisan_min_dana"], c["propisan_max_dana"]) == raspon


@pytest.mark.parametrize("q,da", [
    ("Da li mogu tražiti povrat avansa i ugovornu kaznu od izvođača?", False),
    ("Kazna za kašnjenje sa povratom PDV-a?", False),
    ("Kako se traži povrat oduzetih predmeta u krivičnom postupku?", False),
    ("Povrat jemstva kad je okrivljeni oslobođen u krivičnom postupku?", False),
    ("Kada je povratak osuđenog u zatvor posle vikend izlaska?", False),
    ("Okrivljeni je 2 puta osuđen, kolika je kazna?", True),
    ("Okrivljeni ima tri ranije osude za krađu, koliku kaznu može dobiti?", True),
    ("Recidivista sa dve osude, kolika je kazna?", True),
    ("Da li se povratniku može ublažiti kazna?", True),
    ("Specijalni povrat kod krivičnih dela?", True),
])
def test_revizija_detektor(q, da):
    assert je_pitanje_o_povratu(q) is da


def test_revizija_bez_laznog_nepostojeceg_clana_i_tekst_bloka():
    t, _ = blok("Kako se po članu 54 i 55a KZ odmerava kazna povratniku?")
    assert "ne postoji" not in t
    t2, _ = blok("Okrivljeni je ranije dva puta osuđen na zatvor od po dve godine za umišljajna dela, otpušten je pre dve godine, "
                 "a sada je sa umišljajem učinio delo za koje je propisan zatvor do tri godine.")
    assert "Propisana kazna: 30 dana do 3 godine" in t2 and "više od 1 godine, 6 meseci i 15 dana" in t2
    t3, _ = blok(P + "a sada je iz nehata učinio delo za koje je propisan zatvor od jedne do osam godina.")
    assert "NE primenjuje" in t3 and "čl. 55 (povrat)" not in t3                  # čl. 55 traži umišljajno novo delo
    assert "Prepoznato iz pitanja:" in blok(P + NOVO)[0]


V_NE = P.replace("pre tri godine", "pre sedam godina") + NOVO


@pytest.mark.parametrize("q,ai,upozorenje", [
    (V_NE, "Nisu ispunjeni uslovi iz čl. 55a.", False),                      # AI se slaže sa NE
    (V_NE, "Ukoliko su ispunjeni uslovi, sud izriče strožu kaznu.", False),  # uslovna rečenica nije tvrdnja
    (V_NE, "Primenjuje se čl. 55a, sud mora izreći kaznu iznad polovine.", True),
    (P + NOVO, "Čl. 55a se ne primenjuje na ovaj slučaj.", True),             # DA, a AI kaže suprotno
    ("Okrivljeni je dva puta osuđen za umišljajna dela, " + NOVO, "Uslovi su ispunjeni.", True),   # NEPOZNATO, a AI tvrdi ishod
])
def test_revizija_upozorenje_u_oba_smera(q, ai, upozorenje):
    import main as M
    izlaz = M._dodaj_proracun_povrata(q, {"status": "success", "data": f"--- PRAVNI ZAKLJUČAK\nx\n\n--- OBRAZLOŽENJE\n{ai}"})
    assert ("UPOZORENJE" in izlaz["data"]) is upozorenje


def test_revizija_rezervni_oblik_zakljucka_se_zamenjuje():
    import main as M
    izlaz = M._dodaj_proracun_povrata(V_NE, {"status": "success", "data": "PRAVNI ZAKLJUČAK: Uslovi su ispunjeni.\n"
                                                                          "KRATAK ZAKLJUČAK (TL;DR): Primenjuje se čl. 55a."})
    assert "PRAVNI ZAKLJUČAK: Čl. 55a KZ se ne primenjuje" in izlaz["data"]
    assert "KRATAK ZAKLJUČAK (TL;DR): Čl. 55a KZ se ne primenjuje" in izlaz["data"]



def test_mutacije_dozivotni_posle_raspona_se_ne_racuna():
    c = iz_pitanja(P + "a sada je sa umišljajem učinio delo za koje je propisan zatvor od deset do dvadeset godina ili doživotni zatvor.")
    assert c["propisan_max_dana"] is None


def test_mutacije_uslovna_osuda_uslov_1_nepoznat():
    r = izracunaj(**iz_pitanja("Okrivljeni je dva puta osuđen uslovnom osudom na zatvor od po dve godine za umišljajna dela, " + NOVO))
    assert r.uslovi[2].stanje == NEPOZNATO


def test_mutacije_propisan_raspon_ranijih_dela_nije_izrecena_kazna():
    c = iz_pitanja("Okrivljeni je dva puta osuđen za krađe, za koje je propisan zatvor od šest meseci do pet godina, na zatvor od dve "
                   "godine i na zatvor od tri godine za umišljajna dela, otpušten je pre tri godine, " + NOVO)
    assert [o.zatvor_meseci for o in c["ranije_osude"]] == [24, 36]


def test_mutacije_godina_uz_osudu_nije_broj_osuda():
    c = iz_pitanja("Okrivljeni je 2015 osuđen na zatvor od dve godine za umišljajno delo, otpušten je pre tri godine, " + NOVO)
    assert c["broj_ranijih_osuda"] is None


def test_v4_nacin_racunanja_polovine_je_oznacen_kao_tumacenje():
    """V4: zakon kaže samo „iznad polovine raspona propisane kazne“; sredina min–max je tumačenje i to se kaže."""
    tekst, r = V.blok("Okrivljeni je ranije dva puta osuđen na zatvor od po dve godine za krađe učinjene sa umišljajem, sa "
                      "izdržavanja kazne je otpušten pre tri godine, a sada je sa umišljajem izvršio tešku krađu za koju je "
                      "propisan zatvor od jedne do osam godina. U kom rasponu sud mora da izrekne kaznu?")
    assert "više od 4 godine i 6 meseci, najviše 8 godina" in tekst and "4 godine i 7 meseci" in tekst
    assert "to je tumačenje" in tekst and "ne ublažava" in tekst
    nepoznato, _ = V.blok("Šta je višestruki povrat ako je za delo propisan zatvor od jedne do osam godina?")
    assert ("Ako se uslovi utvrde" in nepoznato) == ("to je tumačenje" in nepoznato)
    assert "Najniža kazna važi" not in nepoznato   # u toj grani najniža kazna se i ne navodi
    nije, _ = V.blok("Okrivljeni je dva puta osuđen na zatvor od po tri godine za umišljajna dela, otpušten je pre sedam godina, "
                     "a sada je učinio umišljajno delo sa propisanim zatvorom od dve do deset godina. Da li se primenjuje član 55a KZ?")
    assert "to je tumačenje" not in nije        # bez raspona nema ni napomene o računanju
