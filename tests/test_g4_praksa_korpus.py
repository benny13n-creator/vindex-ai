# -*- coding: utf-8 -*-
"""G4 — ograničen adversarijalni korpus (sažetak odluke ↔ stav koji mu model pripisuje).

Oznaka svakog para je određena KONSTRUKCIJOM (stav je ili preformulacija ili inverzija/proširenje ISTOG sažetka), ne
tumačenjem modela. Dva nivoa ugovora:
  1. Provera (`_proveri_stavove_prakse`) je heuristika (preklop reči + smer klauzule). Meri se: koliko podržanih ostaje,
     koliko nepodržanih se uklanja; parovi koje heuristika NE razlikuje su popisani kao poznata granica.
  2. Invarijanta prikaza (G4): ZADRŽANA odluka se nikad ne prikazuje samo AI parafrazom — uz nju ide DOSLOVAN sažetak
     iz baze, a parafraza je izričito označena kao „AI sažetak — nije potvrđen kao stav suda“. Tako ni par koji provera
     propusti ne dobija status potvrđenog stava suda: advokat vidi izvorni tekst."""
import pytest

import main

S_TRUDNOCA = "Poslodavac ne može da otkaže ugovor o radu zaposlenoj za vreme trudnoće i porodiljskog odsustva."
S_ZASTARELOST = "Rok zastarelosti potraživanja naknade štete teče od dana saznanja za štetu, a ne od dana nastanka štete."
S_REVIZIJA = "Revizija je nedopuštena kada vrednost predmeta spora ne prelazi propisani iznos."
S_IZUZETAK = "Zakupodavac može otkazati ugovor o zakupu pre isteka roka samo ako zakupac ne plati zakupninu ni posle opomene."
S_OBJEKTIVNA = "Poslodavac odgovara za štetu koju zaposleni pretrpi na radu ne samo kada je kriv, već i po principu objektivne odgovornosti."
S_SVEDOK = "Sud ne može odbiti da sasluša svedoka kojeg je stranka blagovremeno predložila."
S_USKO = "Ugovor o zajmu između fizičkih lica zaključen usmeno je punovažan."
S_UPRAVNI = "U upravnom sporu tužba ne odlaže izvršenje osporenog rešenja."
S_CIR = "Послодавац не може да откаже уговор о раду запосленој за време трудноће."
S_IZDVOJENO = "Veće je odbilo žalbu; u izdvojenom mišljenju jedan sudija navodi da je tužba trebalo da bude usvojena."

# (sažetak, pripisan stav, treba_da_ostane, kategorija)
KORPUS = [
    (S_TRUDNOCA, "Poslodavac ne može da otkaže ugovor o radu zaposlenoj za vreme trudnoće.", True, "podrška"),
    (S_TRUDNOCA, "Poslodavac može da otkaže ugovor o radu zaposlenoj za vreme trudnoće.", False, "izričita negacija"),
    (S_CIR, "Poslodavac može da otkaže ugovor o radu zaposlenoj za vreme trudnoće.", False, "ćirilica, negacija"),
    (S_CIR, "Poslodavac ne može da otkaže ugovor o radu zaposlenoj za vreme trudnoće.", True, "ćirilica, podrška"),
    (S_ZASTARELOST, "Rok zastarelosti potraživanja naknade štete teče od dana saznanja za štetu.", True, "kontrast — podržana grana"),
    (S_ZASTARELOST, "Rok zastarelosti potraživanja naknade štete teče od dana nastanka štete.", False, "kontrast — isključena grana"),
    (S_REVIZIJA, "Revizija je dopuštena kada vrednost predmeta spora ne prelazi propisani iznos.", False, "prefiks ne-"),
    (S_REVIZIJA, "Revizija je nedopuštena kada vrednost predmeta spora ne prelazi propisani iznos.", True, "prefiks ne-, podrška"),
    (S_OBJEKTIVNA, "Poslodavac odgovara za štetu koju zaposleni pretrpi na radu po principu objektivne odgovornosti.", True, "ne samo … već"),
    (S_UPRAVNI, "Tužba u upravnom sporu odlaže izvršenje osporenog rešenja.", False, "negacija, drugi red reči"),
    (S_UPRAVNI, "Ugovor o zakupu stana mora biti overen kod javnog beležnika.", False, "nepovezan stav"),
    (S_ZASTARELOST, "Rok zastarelosti potraživanja naknade štete ne teče od dana saznanja za štetu.", False, "negacija podržane grane"),
    (S_IZUZETAK, "Zakupodavac može otkazati ugovor o zakupu pre isteka roka.", False, "izuzetak izostavljen (preširoko)"),
]

# Parovi koje heuristika NE razlikuje (poznata granica, merena — ne skrivena). Invarijanta prikaza ih pokriva.
GRANICA = [
    (S_SVEDOK, "Sud mora da sasluša svedoka kojeg je stranka blagovremeno predložila.", "dvostruka negacija = podrška, a uklanja se"),
    (S_USKO, "Svaki ugovor zaključen usmeno je punovažan.", "preopšte proširenje"),
    (S_USKO, "Ugovor o zajmu zaključen usmeno je punovažan.", "izostavljeno „između fizičkih lica“ (šire)"),
    (S_IZDVOJENO, "Tužba je trebalo da bude usvojena.", "izdvojeno mišljenje, ne stav veća"),
]


def _kontekst(sazetak):
    return f"SUDSKA PRAKSA:\n1. Vrhovni sud, Rev 77/2021, 01.01.2021\n   Sažetak: {sazetak}\n"


def _proveri(sazetak, stav):
    data = {"pravni_zakljucak": "x", "sudska_praksa": [{"sud": "Vrhovni sud", "broj_odluke": "Rev 77/2021",
                                                          "pravni_princip": stav}]}
    return main._proveri_stavove_prakse(data, _kontekst(sazetak))


@pytest.mark.parametrize("sazetak,stav,ostaje,kategorija", KORPUS, ids=[k[3] for k in KORPUS])
def test_korpus_provera(sazetak, stav, ostaje, kategorija):
    assert bool(_proveri(sazetak, stav)["sudska_praksa"]) is ostaje


def test_granica_heuristike_je_izmerena():
    """Ako se heuristika promeni, ovaj popis se mora svesno ažurirati (test pada na svaku promenu ishoda)."""
    ishod = {opis: bool(_proveri(s, st)["sudska_praksa"]) for s, st, opis in GRANICA}
    assert ishod == {"dvostruka negacija = podrška, a uklanja se": False,
                     "preopšte proširenje": True, "izdvojeno mišljenje, ne stav veća": True,
                     "izostavljeno „između fizičkih lica“ (šire)": True}


@pytest.mark.parametrize("sazetak,stav", [(s, st) for s, st, o, _ in KORPUS if o] + [(s, st) for s, st, _ in GRANICA])
def test_zadrzan_stav_nikad_bez_doslovnog_sazetka_i_oznake(sazetak, stav):
    data = _proveri(sazetak, stav)
    if data["sudska_praksa"]:
        data["sudska_praksa"][0].update(primena_na_predmet="Odluka potvrđuje stav.", sazetak_relevantnosti="Relevantno.")
    if not data["sudska_praksa"]:
        return                                                   # uklonjen — ništa se ne prikazuje kao stav suda
    tekst = main._json_ka_tekst(data, "PARNICA")
    deo = tekst[tekst.index("--- SUDSKA PRAKSA"):]
    assert "Izvod iz teksta odluke u bazi Vindex (doslovno, skraćeno — izvod ne mora biti stav suda)" in deo
    assert f"„{sazetak} …“" in deo
    assert "AI sažetak — nije potvrđen kao stav suda" in deo
    assert "   Pravni princip: " not in deo                     # neoznačena AI formulacija se ne prikazuje
    assert "   Primena (AI): Odluka potvrđuje stav." in deo and "   AI: Relevantno." in deo


def test_odluka_van_konteksta_se_ne_prikazuje():
    data = {"sudska_praksa": [{"sud": "Vrhovni sud", "broj_odluke": "Rev 9999/2022", "pravni_princip": S_USKO}]}
    assert main._proveri_stavove_prakse(data, _kontekst(S_USKO))["sudska_praksa"] == []


def test_mera_korpusa():
    podrzani = [(s, st) for s, st, o, _ in KORPUS if o]
    nepodrzani = [(s, st) for s, st, o, _ in KORPUS if not o]
    zadrzano = sum(bool(_proveri(s, st)["sudska_praksa"]) for s, st in podrzani)
    uklonjeno = sum(not _proveri(s, st)["sudska_praksa"] for s, st in nepodrzani)
    assert (zadrzano, len(podrzani), uklonjeno, len(nepodrzani)) == (5, 5, 8, 8)


# ── revizija G4: stvaran put (`_parsiraj_strukturni_odgovor`), ne samo pomoćne funkcije ──

import json  # noqa: E402

_CTX = ("SUDSKA PRAKSA (relevantne odluke iz baze):\n1. Vrhovni sud, Rev 77/2021, 01.01.2021\n"
        "   Sažetak: Rok zastarelosti teče od dana saznanja za štetu, a ne od dana nastanka štete.")


def _parsiraj(data):
    ok, txt = main._parsiraj_strukturni_odgovor(json.dumps(data), "PARNICA", ["Član 376 ZOO tekst"], praksa_context=_CTX)
    assert ok
    return txt


@pytest.mark.parametrize("broj", ["", "Re", None])
def test_F1_stavka_bez_upotrebljivog_broja_se_uklanja(broj):
    txt = _parsiraj({"pravni_zakljucak": "Zaključak.", "sudska_praksa": [
        {"sud": "Vrhovni sud", "broj_odluke": broj, "pravni_princip": "Rok zastarelosti teče od dana nastanka štete."}]})
    assert "--- SUDSKA PRAKSA" not in txt and "od dana nastanka štete" not in txt


def test_F4_navod_zadrzane_odluke_u_drugoj_sekciji_je_oznacen():
    txt = _parsiraj({"pravni_zakljucak": "Prema stavu Vrhovnog suda u Rev 77/2021, rok teče od nastanka štete.",
                     "sudska_praksa": [{"sud": "Vrhovni sud", "broj_odluke": "Rev 77/2021",
                                        "pravni_princip": "Rok zastarelosti teče od dana saznanja za štetu."}]})
    zak = txt[txt.index("--- PRAVNI ZAKLJUČAK"):txt.index("--- SUDSKA PRAKSA")]
    assert "Rev 77/2021" in zak and "[AI navod o ovoj odluci — nije potvrđen kao stav suda]" in zak
    assert "„Rok zastarelosti teče od dana saznanja za štetu, a ne od dana nastanka štete. …“" in txt


def test_F2_verzija_oblika_je_u_kljucu_kesa(monkeypatch):
    k1 = main._cache_kljuc("Koliki je rok za žalbu?")
    monkeypatch.setattr(main, "_CACHE_VERZIJA", "starija")
    assert main._cache_kljuc("Koliki je rok za žalbu?") != k1


_CTX2 = _CTX + "\n2. Apelacioni sud u Beogradu, Gž 5/2020, 01.01.2020\n   Sažetak: Ugovor o zakupu stana mora biti pisan."
_OZN = "[AI navod o ovoj odluci — nije potvrđen kao stav suda]"


def _parsiraj2(data):
    ok, txt = main._parsiraj_strukturni_odgovor(json.dumps(data), "PARNICA", ["Član 376 ZOO tekst"], praksa_context=_CTX2)
    assert ok
    return txt


def _dve(zakljucak):
    return {"pravni_zakljucak": zakljucak, "sudska_praksa": [
        {"sud": "Vrhovni sud", "broj_odluke": "Rev 77/2021", "pravni_princip": "Rok zastarelosti teče od dana saznanja za štetu."},
        {"sud": "Apelacioni sud u Beogradu", "broj_odluke": "Gž 5/2020", "pravni_princip": "Poslodavac odgovara objektivno."}]}


@pytest.mark.parametrize("zakljucak,ostaje", [
    ("Prema Rev 77/2021 rok teče od nastanka. Tužba je neblagovremena.", "Tužba je neblagovremena."),
    ("Prema Rev 77/2021 rok teče od nastanka", "rok teče od nastanka"),
])
def test_mesovit_odgovor_navod_oznacen_a_ostali_tekst_ostaje(zakljucak, ostaje):
    txt = _parsiraj2(_dve(zakljucak))
    zak = txt[txt.index("--- PRAVNI ZAKLJUČAK"):txt.index("--- SUDSKA PRAKSA")]
    assert _OZN in zak and ostaje in zak and "Gž 5/2020" not in txt


def test_prelomi_redova_ostaju_kad_je_odluka_zadrzana():
    data = {"pravni_zakljucak": "Zaključak.", "procesni_koraci": "1. Podneti tužbu.\n2. Predložiti dokaze.",
            "sudska_praksa": [{"sud": "Vrhovni sud", "broj_odluke": "Rev 77/2021",
                               "pravni_princip": "Rok zastarelosti teče od dana saznanja za štetu."}]}
    out = main._proveri_stavove_prakse(data, _CTX)
    assert out["procesni_koraci"] == "1. Podneti tužbu.\n2. Predložiti dokaze."


def test_deo_broja_druge_odluke_se_ne_oznacava_i_ponovni_prolaz_ne_dodaje():
    zadrzane = [{"broj_odluke": "Rev 7/2021"}]
    data = {"a": "Prema Prev 7/2021 važi X. Prema Rev 7/20211 važi Y. Prema Rev 7/2021 važi Z."}
    jednom = main._oznaci_navode_zadrzane_prakse(data, zadrzane)
    assert jednom["a"] == "Prema Prev 7/2021 važi X. Prema Rev 7/20211 važi Y. Prema Rev 7/2021 važi Z " + _OZN + "."
    assert main._oznaci_navode_zadrzane_prakse(jednom, zadrzane) == jednom


# ── S1-C5 (revizija H4): skraćenice („Rev.“, „str.“) i broj odluke sa tačkom ──

def _h4_ctx():
    return main._format_praksa_context([{"court": "Vrhovni kasacioni sud", "decision_number": "Rev 5/2020", "date": "2020",
                                         "text": "Poslodavac ne može da otkaže ugovor o radu zaposlenoj za vreme trudnoće, osim u "
                                                 "slučajevima propisanim članom 187 Zakona o radu."}])


_H4_PROZA = ("Vrhovni kasacioni sud je u odluci Rev. 5/2020 zauzeo stav da zaposlena ima pravo na dvostruku naknadu štete. "
             "Prema stavu VKS (Rev 5/2020, str. 3) otkaz je ništav i bez tužbe. Tužbu treba podneti u roku.")


def test_H4_zadrzana_odluka_navod_sa_tackom_i_skracenicom_oznacen_bez_lomljenja():
    st = {"sud": "Vrhovni kasacioni sud", "broj_odluke": "Rev 5/2020", "sazetak_relevantnosti": "x",
          "pravni_princip": "Poslodavac ne može da otkaže ugovor o radu zaposlenoj za vreme trudnoće, član 187 Zakona o radu."}
    out = main._proveri_stavove_prakse({"pravni_zakljucak": _H4_PROZA, "sudska_praksa": [st]}, _h4_ctx())
    z = out["pravni_zakljucak"]
    assert out["sudska_praksa"] and z.count(_OZN) == 2, z
    assert "u odluci Rev. 5/2020 zauzeo stav da zaposlena ima pravo na dvostruku naknadu štete " + _OZN + "." in z
    assert "(Rev 5/2020, str. 3) otkaz je ništav i bez tužbe " + _OZN + "." in z
    assert z.endswith("Tužbu treba podneti u roku.")


def test_H4_uklonjena_odluka_navod_sa_tackom_i_skracenicom_uklonjen_ceo():
    st = {"sud": "Vrhovni kasacioni sud", "broj_odluke": "Rev 5/2020", "sazetak_relevantnosti": "x",
          "pravni_princip": "Otkaz zaposlenoj za vreme trudnoće je dopušten ako poslodavac prestane da postoji."}
    out = main._proveri_stavove_prakse({"pravni_zakljucak": _H4_PROZA, "sudska_praksa": [st]}, _h4_ctx())
    assert out["sudska_praksa"] == [] and out["pravni_zakljucak"] == "Tužbu treba podneti u roku."


def test_H4_obrazac_broja():
    o = main._obrazac_odluke("Rev 5/2020")
    assert main._sadrzi_odluku("u odluci Rev. 5/2020", [o]) and main._sadrzi_odluku("Рев 5/2020", [o])
    assert not main._sadrzi_odluku("Prev 5/2020", [o]) and not main._sadrzi_odluku("Rev 5/20201", [o])
    assert main._obrazac_odluke("154") is None


def test_M2_isti_broj_iz_dva_suda_nije_potvrdjen():
    """S1-C5 (revizija M2): „Gž 100/2020“ apelacionih sudova u Nišu i Beogradu — ne zna se čiji je sažetak."""
    ctx = main._format_praksa_context([
        {"court": "Apelacioni sud u Nišu", "decision_number": "Gž 100/2020", "date": "2020",
         "text": "Rok zastarelosti potraživanja naknade štete teče od dana saznanja za štetu."},
        {"court": "Apelacioni sud u Beogradu", "decision_number": "Gž 100/2020", "date": "2020",
         "text": "Ugovor o zakupu stana mora biti zaključen u pisanoj formi."}])
    st = {"sud": "Apelacioni sud u Nišu", "broj_odluke": "Gž 100/2020",
          "pravni_princip": "Rok zastarelosti potraživanja naknade štete teče od dana saznanja za štetu."}
    assert main._sazeci_iz_konteksta(ctx) == {}
    assert main._proveri_stavove_prakse({"pravni_zakljucak": "x", "sudska_praksa": [st]}, ctx)["sudska_praksa"] == []


def test_S1E_opsta_skracenica_na_kraju_recenice_i_lista_ne_spajaju_recenice():
    """Revizija S1-E: „… kamati itd. U Rev 5/2020 …“ — uklanjanje je brisalo i legitimnu prvu rečenicu; broj stavke
    liste („3.“) se lepio za prethodnu rečenicu."""
    st = {"sud": "Vrhovni kasacioni sud", "broj_odluke": "Rev 5/2020", "sazetak_relevantnosti": "x",
          "pravni_princip": "Otkaz zaposlenoj za vreme trudnoće je dopušten ako poslodavac prestane da postoji."}
    proza = "Sud primenjuje pravila o naknadi štete, kamati itd. U Rev 5/2020 VKS je zauzeo stav X."
    out = main._proveri_stavove_prakse({"pravni_zakljucak": proza, "sudska_praksa": [st]}, _h4_ctx())
    assert out["sudska_praksa"] == [] and out["pravni_zakljucak"] == "Sud primenjuje pravila o naknadi štete, kamati itd."
    assert main._recenice_sa_razmacima("Prvo. 3. Treće.")[0::2] == ["Prvo.", "3.", "Treće."]


def test_3k_skracenice_sredine_recenice_ne_lome_navod():
    """3. krug revizije: „…, tj. da rok teče …“ i „(Sl. glasnik RS …)“ su lomili rečenicu, pa je ostajao fragment."""
    assert main._recenice_sa_razmacima("Sud je zauzeo stav, tj. da rok teče od dostave. Dalje.")[0::2] == [
        "Sud je zauzeo stav, tj. da rok teče od dostave.", "Dalje."]
    assert main._recenice_sa_razmacima("Rok je propisan Zakonom (Sl. glasnik RS, br. 72/2011). Dalje.")[0::2] == [
        "Rok je propisan Zakonom (Sl. glasnik RS, br. 72/2011).", "Dalje."]
