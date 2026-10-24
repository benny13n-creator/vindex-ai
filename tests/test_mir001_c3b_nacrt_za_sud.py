# -*- coding: utf-8 -*-
"""MIR001 C3b STRUCTURAL TASK-02 — zaštićen nacrt iz spisa: kapija teksta za sud, razdvajanje od internih napomena, DOCX.

Čiste provere kapije (`shared/nacrt_za_sud.zastiti`) nad procesnim stanjem Golden Case-a (scenariji A, C1, C2, H2 i
B bez odluke), pa stvarna ruta `POST /api/agents/run` (agent `drafting`, spis kroz OCR) i DOCX sa pregleda.
"""
import json
import types
from unittest.mock import patch

import pytest

from shared import nacrt_za_sud as NZ
from shared import procesno_stanje as PS
from tests.test_mir001_c3b_procesno_stanje_ugovor import BEZ_ZAPISNIKA, DOK06, ODUSTANAK, PREDUJAM, ZAPISNIK, _d
from tests.test_mir001_t06_nacrt_iz_spisa import _nacrti, _pisi, nacrt, treba_ocr  # noqa: F401
from tests.test_mir001_t04_savetnik_spis import savetnik  # noqa: F401
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401

P, U = "pred-1", "user-A"


def _st(*dok):
    return PS.utvrdi(list(dok), predmet_id=P, user_id=U)


NALAZ = ("NALAZ | MISLJENJE VESTAKA\nBroj predmeta: P 9901/2026\nVestak gradjevinske struke Petar Izmisljeni.\n"
         "Uzrok prokisnjavanja je neodgovarajuce izvedena hidroizolacija na spoju atike.\nDatum nalaza: 15.06.2026. godine.")
A_ST = _st(_d("DOK-05", NALAZ), _d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK))
C1_ST = _st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK), _d("DOK-08", ODUSTANAK))
C2_ST = _st(_d("DOK-06", DOK06), _d("DOK-07", BEZ_ZAPISNIKA))
H2_ST = _st(_d("DOK-07", PREDUJAM))
B_ST = _st(_d("DOK-06", DOK06))
PS_PRIHVATA = next(x["id"] for x in A_ST["dogadjaji"] if x["vrsta"] == "SUD_PRIHVATA")


def _ostaje(tekst, stanje):
    k = NZ.zastiti(tekst, stanje)
    return not k["izostavljeno"], k


@pytest.mark.parametrize("rec,stanje", [
    ("Tužilac je u međuvremenu izvršio uplatu predujma u skladu sa nalogom suda.", H2_ST),        # H2 #5
    ("Tužilac je uplatio predujam od 60.000 dinara.", H2_ST),
    ("Tužilac je spreman da uplati predujam za dopunu veštačenja, kako je naloženo od strane suda (DOK-07).", H2_ST),
    ("Tužilac će uplatiti predujam u roku od 8 dana od prijema zapisnika.", H2_ST),
    ("Rok za dostavu dnevnika je istekao.", A_ST),
    ("Tužilac očekuje da će tuženi dostaviti građevinski dnevnik u roku od 15 dana, kako je sud naložio.", A_ST),
    ("Smatramo da je nalaz veštaka potpun, te da dopuna veštačenja nije potrebna.", A_ST),         # A #3
    ("Nije potrebno dodatno veštačenje.", A_ST),                                                    # A #10
    ("Ukoliko sud smatra drugačije, tužilac će se povinovati odluci suda o dopuni veštačenja (DOK-07).", A_ST),
    ("Dodatni uvid u građevinski dnevnik ne bi promenio suštinu nalaza.", A_ST),
    ("Tužilac predlaže da sud razmotri dopunu veštačenja ukoliko tuženi dostavi dnevnik.", A_ST),   # A #6
    ("Sud je prihvatio nalaz veštaka (DOK-07).", A_ST),                                             # pogrešna parafraza
    ("Veštak je utvrdio da je uzrok neodgovarajuće izvedena hidroizolacija.", A_ST),
    ("Tuženi je u podnesku (DOK-08) odustao od predloga, te smatramo da je pitanje veštačenja time rešeno.", C1_ST),
    ("Tužilac se protivi predlogu tuženog za dopunu veštačenja, s obzirom da je tuženi u međuvremenu odustao.", C1_ST),
    ("Tužilac se protivi predlogu tuženog za dopunu veštačenja.", C2_ST),                          # C2: ishod nepoznat
    ("Predlažemo sudu da odbije predlog tuženog za dopunu veštačenja.", C2_ST),
    ("Sud je već odbio predlog, te je pitanje pravosnažno rešeno.", A_ST),
    # GATE-02 (1. prolaz) — prirodne parafraze koje je spisak reči propuštao (pravilo predmeta)
    ("Uplata predujma je izvršena.", H2_ST),
    ("Tužilac je izmirio predujam.", H2_ST),
    ("Tužilac je izmirio obavezu plaćanja predujma.", H2_ST),
    ("Tužilac je izvršio plaćanje predujma.", H2_ST),
    ("Tužilac je predujam položio na račun suda.", H2_ST),
    ("Predujam je uredno deponovan.", H2_ST),
    ("Tužilac je postupio po [[PS-02]].", H2_ST),
    ("Tuženi je [[PS-09]], pa se dopuna neće održati.", C1_ST),
    ("Tuženi više ne traži dopunu veštačenja, te je ista izgubila svrhu.", C1_ST),
    ("Predlog tuženog za dopunu veštačenja treba odbiti kao neosnovan.", C2_ST),
    ("Predlog tuženog za dopunu veštačenja je neosnovan.", C2_ST),
    ("Ne postoje razlozi za dopunu veštačenja.", C2_ST),
    ("Dopuna veštačenja ne doprinosi razjašnjenju stvari.", A_ST),
    ("Dopuna veštačenja bi samo odugovlačila postupak.", A_ST),
    ("Za dopunom veštačenja nema mesta.", A_ST),
    ("Dopuna veštačenja se neće sprovoditi.", A_ST),
    ("Sud je naknadno opozvao odluku o dopuni veštačenja.", A_ST),
    ("Nalog za dostavu građevinskog dnevnika je stavljen van snage.", A_ST),
    ("Rok od 15 dana za dnevnik je prošao.", A_ST),
    ("Tuženi je zakasnio sa dnevnikom.", A_ST),
    ("Tuženi je podneo građevinski dnevnik.", A_ST),
    ("Tuženi je priložio građevinski dnevnik.", A_ST),
    ("Sud je prihvatio predlog za dopunu veštačenja i tužbeni zahtev (DOK-07).", A_ST),
    ("Na ročištu je sud potvrdio da je tužbeni zahtev osnovan (DOK-07).", A_ST),
    ("Sud je [[PS-04]] i time potvrdio da je nalaz veštaka nepotpun.", A_ST),
    ("Dopuna veštačenja nije\npotrebna.", A_ST),
    ("Допуна вештачења није потребна.", A_ST),
    ("Tužilac osporava tvrdnje tuženog da je potrebno dopuniti veštačenje.", C2_ST),            # C2: ishod nepoznat
    ("Tužilac osporava tvrdnje tuženog, jer je sud naložio dostavu dnevnika (DOK-07), što tuženi nije učinio.", A_ST),
    # GATE-02 2. prolaz B1: navod bez izvora koji ga potvrđuje (oznaka suda, nepostojeći ili nemi dokument)
    ("Tužilac u podnesku (DOK-08) navodi da je uplatio predujam.", H2_ST),                  # DOK-08 ne postoji u H2
    ("Tužilac ističe da je predujam uplatio [[PS-02]].", H2_ST),
    ("Tužilac u podnesku (DOK-99) navodi da je uplatio predujam.", H2_ST),
    ("Kako tužilac ističe, predujam je uplaćen [[PS-02]].", H2_ST),
    ("Tužilac navodi da je predujam uplaćen u ostavljenom roku (DOK-07).", H2_ST),
    ("Tužilac ističe da je rok za dostavu dnevnika istekao [[PS-05]].", A_ST),
    ("Tužilac ističe da tuženi nije postupio po nalogu [[PS-05]].", A_ST),
    ("Tuženi tvrdi da je dnevnik dostavio (DOK-06).", A_ST),                                   # DOK-06 to ne kaže
    ("Tuženi je odustao [[PS-09]], kako navodi tužilac, pa dopuna neće biti sprovedena.", C1_ST),
    (f"Iako je sud [[{PS_PRIHVATA}]], tužilac smatra da je dopuna već sprovedena.", A_ST),
    ("Iako je sud [[PS-05]], tužilac ističe da je tuženi dnevnik već dostavio.", A_ST),
    ("Iako je sud [[PS-05]], tužilac ističe da je rok istekao.", A_ST),
    # GATE-02 2. prolaz N-b: parafraza uz oznaku koja dodaje predmet ili ulogu
    (f"Sud je [[{PS_PRIHVATA}]] prihvatio predlog tužioca.", A_ST),
    (f"Sud je prihvatio [[{PS_PRIHVATA}]] i tužbeni zahtev.", A_ST),
    ("Prema zapisniku (DOK-07), sud prihvata predlog i odbija primedbe tužioca.", A_ST),
    # samo jedan sloj odlučuje (mutacije Y13, Z2)
    ("Tužilac smatra da je ona nepotrebna (DOK-07).", A_ST),                  # bez predmeta, DOK nije izričito priznanje
    ("Tuženi u podnesku (DOK-99) navodi da je dopuna veštačenja bitna.", A_ST),  # izvor ne postoji
    # GATE-02 2. prolaz (probe 4/5): jedna rečenica — uplata drugim rečima, sinonimi, dejstvo uz stav, parafraza
    ("Novac za veštaka je obezbeđen.", H2_ST),
    ("Tuženi je ostao pasivan.", A_ST),
    ("Knjiga gradilišta je predata sudu.", A_ST),
    ("Dodatna ekspertiza ne bi ništa promenila.", A_ST),
    (f"Iako je sud [[{PS_PRIHVATA}]], tužilac smatra da je ta odluka prestala da važi.", A_ST),
    (f"Iako je sud [[{PS_PRIHVATA}]], tužilac smatra da je odustankom tuženog [[PS-09]] odluka bez dejstva.", C1_ST),
    (f"Iako je sud [[{PS_PRIHVATA}]], tužilac smatra da se dopuna neće sprovesti jer je tuženi odustao [[PS-09]].", C1_ST),
    ("Sud je naložio tuženom da dostavi dnevnik (DOK-07), a tuženi je to i uradio.", A_ST),
    ("Sud je naložio tuženom da dostavi dnevnik (DOK-07), što je tuženi i uradio.", A_ST),
    ("Sud je zakazao ročište za 18.11.2026. godine radi izvođenja dopune (DOK-07).", A_ST),
    ("Tužilac ističe da je dopuna veštačenja nepotrebna (DOK-07).", A_ST),
    # sloj detektora po rečima bez reči predmeta naloga (pravilo predmeta tu ne okida; mutacije Y7–Y28)
    ("Tužilac je uplatio troškove postupka.", A_ST),
    ("Тужилац је уплатио трошкове поступка.", A_ST),
    ("Rok za izjašnjenje je istekao.", A_ST),
    ("Presuda je pravosnažna.", A_ST),
    ("Tuženi će postupiti po nalogu.", A_ST),
    ("Ukoliko sud smatra drugačije, tužilac će se izjasniti.", A_ST),
    ("Veštak je utvrdio uzrok štete.", B_ST),
    ("Tuženi je odustao.", C1_ST),
    ("Uplatnica je predata sudu.", H2_ST),
    # samo jedno pravilo po primeru (mutacije X7, X8, X15)
    ("Odluka o dopuni veštačenja je pravosnažna.", A_ST),
    ("Tužilac će uplatiti predujam za dopunu veštačenja.", H2_ST),
    ("Tuženi će dostaviti građevinski dnevnik.", A_ST),
    ("Tuženi je odustao od predloga za dopunu veštačenja (DOK-08).", C1_ST),
])
def test_nepotvrdjena_procesna_tvrdnja_ne_ostaje_u_tekstu_za_sud(rec, stanje):
    ok, k = _ostaje(rec, stanje)
    assert not ok, rec
    assert k["tekst"].startswith("[IZOSTAVLJENO I-1: ") and k["izostavljeno"][0]["recenica"].split()[:2] == rec.split()[:2]
    assert "[[" not in k["tekst"]


@pytest.mark.parametrize("rec,stanje", [
    (f"Iako je sud prihvatio dopunu [[{PS_PRIHVATA}]], tužilac smatra da dopuna nije potrebna, jer je nalaz potpun.", A_ST),
    (f"Iako je sud [[{PS_PRIHVATA}]], tužilac predlaže da sud tu odluku preispita i odustane od dopune.", A_ST),
    ("Sud je prihvatio predlog za dopunu veštačenja (DOK-07).", A_ST),                              # tačna parafraza
    ("Tužilac se ne protivi dopuni veštačenja.", A_ST),
    ("Tužilac se protivi tvrdnjama tuženog da veštak nije izvršio uvid u građevinski dnevnik.", A_ST),
    ("Veštak u nalazu navodi da je uzrok neodgovarajuće izvedena hidroizolacija (DOK-05).", A_ST),
    ("Tuženi u podnesku (DOK-08) navodi da građevinski dnevnik nije sačuvan.", C1_ST),
    ("Ukoliko sud na ročištu 15.07.2026. nije odlučio o predlogu, tužilac se protivi dopuni veštačenja.", C2_ST),
    ("Tužilac smatra da dopuna veštačenja nije potrebna, jer je nalaz potpun.", B_ST),            # B: nema odluke suda
    ("Tužilac predlaže da sud odbije predlog tuženog za dopunu veštačenja.", B_ST),
    ("Tužilac je uz podnesak dostavio povratnicu PK-4471.", A_ST),                                   # činjenica, ne nalog
    ("Tužilac ostaje pri tužbenom zahtevu od 3.150.000 dinara.", A_ST),
    (f"Iako je tuženi odustao od predloga (DOK-08), sud je [[{PS_PRIHVATA}]], pa tužilac predlaže da sud odluči o tome.", C1_ST),
    ("Tužilac će se izjasniti na ročištu zakazanom za 18.11.2026.", A_ST),
    ("Tuženi je podneskom [[PS-09]] naveo da odustaje od predloga za dopunu veštačenja.", C1_ST),         # N5
    ("Tužilac predlaže da sud, imajući u vidu odluku (DOK-07), preispita potrebu za dopunom.", A_ST),
    ("Tužilac je precizirao tužbeni zahtev na iznos od 3.150.000 dinara (DOK-07).", A_ST),
    ("Tužilac moli sud da, s obzirom na [[PS-05]], produži rok za dostavu.", A_ST),
    (f"Iako je sud [[{PS_PRIHVATA}]], tužilac\nsmatra da dopuna nije potrebna, jer je nalaz potpun.", A_ST),   # prelom reda
    # GATE-02 2. prolaz N-c: legitimno, a bilo izostavljeno
    ("Tužilac moli sud da mu produži rok za uplatu predujma [[PS-02]].", H2_ST),
    ("Tužilac moli sud da veštaku [[PS-04]] odredi primeren rok.", A_ST),
    ("Iako je sud prihvatio dopunu (DOK-07), tužilac smatra da nije potrebna, jer je nalaz potpun.", A_ST),
    ("Tuženi u podnesku [[PS-10]] navodi da građevinski dnevnik nije sačuvan.", C1_ST),     # izvor to kaže
])


def test_legitiman_tekst_i_stav_stranke_uz_odluku_ostaju(rec, stanje):
    ok, k = _ostaje(rec, stanje)
    assert ok, (rec, k["izostavljeno"])


@pytest.mark.parametrize("tekst,stanje", [
    ("Sud nalaže tuženom da dostavi građevinski dnevnik [[PS-05]]. Isti je dostavljen.", A_ST),
    ("Sud nalaže tuženom da dostavi građevinski dnevnik [[PS-05]]. To je urađeno.", A_ST),
    ("Sud nalaže tuženom da dostavi građevinski dnevnik [[PS-05]]. Tuženi je to uradio.", A_ST),
    (f"Sud prihvata dopunu [[{PS_PRIHVATA}]]. Ista je izvršena.", A_ST),
    (f"Sud prihvata dopunu [[{PS_PRIHVATA}]]. Ona više nema svrhu.", A_ST),
    (f"Sud prihvata dopunu [[{PS_PRIHVATA}]]. Takva radnja nema smisla.", A_ST),
    ("Tuženi je imao 15 dana. Ništa nije dostavio.", A_ST),
    ("Tuženi je imao 15 dana. Tih 15 dana je prošlo.", A_ST),
    ("Tuženi nije postupio.", A_ST),
    ("Sud nalaže tuženom da dostavi građevinski dnevnik [[PS-05]]. Tuženi je isti dostavio u kartonskoj kutiji.", A_ST),  # Z5
    # GATE-02 2. prolaz (probe 4/5): glagoli stanja, uplata drugim rečima, sinonimi, dejstvo uz stav
    (f"Sud prihvata dopunu [[{PS_PRIHVATA}]]. Veštak je to već obavio.", A_ST),
    (f"Sud prihvata dopunu [[{PS_PRIHVATA}]]. Veštak je završio posao.", A_ST),
    ("Sud nalaže uplatu [[PS-02]]. Tužilac je to učinio.", H2_ST),
    ("Sud nalaže uplatu [[PS-02]]. Novac je prenet na račun suda.", H2_ST),
    ("Sud nalaže uplatu [[PS-02]]. Tužilac je obavezu namirio.", H2_ST),
    # GATE-02 3. prolaz B3: predaja/prijem i „tražena isprava“
    ("Sud nalaže tuženom da dostavi građevinski dnevnik [[PS-05]]. Tuženi je dokument predao.", A_ST),
    ("Sud nalaže tuženom da dostavi građevinski dnevnik [[PS-05]]. Tražena isprava je stigla u sud.", A_ST),
    ("Sud nalaže tuženom da dostavi građevinski dnevnik [[PS-05]]. Sud je dokument primio.", A_ST),
])
def test_zamenica_ili_recenica_bez_predmeta_posle_naloga_ne_nosi_stanje(tekst, stanje):
    k = NZ.zastiti(tekst, stanje)
    poslednja = tekst.rsplit(". ", 1)[-1]
    assert k["izostavljeno"] and k["izostavljeno"][-1]["recenica"] == poslednja, k["izostavljeno"]


def _podnesak(naslov, red):
    from tests.test_mir001_c3b_procesno_stanje_ugovor import _ZAGLAVLJE
    return _ZAGLAVLJE + naslov + " (SINTETICKI PREDMET)\n" + red + "\nDatum podneska: 20.08.2026. godine."


_H2 = lambda red: _st(_d("DOK-07", PREDUJAM), _d("DOK-08", _podnesak("PODNESAK TUZIOCA", red)))
_A8 = lambda red: _st(_d("DOK-06", DOK06), _d("DOK-07", ZAPISNIK), _d("DOK-08", _podnesak("PODNESAK TUZENOG", red)))


@pytest.mark.parametrize("izvor,rec,ostaje", [
    # GATE-02 3. prolaz B1: izvod sa „nije“ ili nameri ne potvrđuje završenu radnju
    (_H2("Tuzilac navodi da nije uplatio predujam za dopunu vestacenja."),
     "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam za dopunu veštačenja.", False),
    (_H2("Tuzilac navodi da ce uplatiti predujam za dopunu vestacenja."),
     "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam za dopunu veštačenja.", False),
    (_A8("Tuzeni navodi da gradjevinski dnevnik nije dostavio jer nije sacuvan."),
     "Tuženi u podnesku (DOK-08) navodi da je građevinski dnevnik dostavio.", False),
    (_A8("Tuzeni navodi da gradjevinski dnevnik nije sacuvan."),
     "Tuženi u podnesku (DOK-08) navodi da je građevinski dnevnik dostavio sudu.", False),
    # izvor bez tvrdnje (Z3: „propustio“ nije glagol stanja) i izvor druge grupe radnje (Z4: uvid ≠ dostava)
    (_A8("Tuzeni navodi da gradjevinski dnevnik nije sacuvan."),
     "Tuženi u podnesku (DOK-08) navodi da je propustio da postupi po nalogu o dnevniku.", False),
    (_A8("Tuzeni navodi da je vestak izvrsio uvid u gradjevinski dnevnik."),
     "Tuženi u podnesku (DOK-08) navodi da je građevinski dnevnik dostavio.", False),
    # GATE-02 4. prolaz N1: daleka negacija, nestvarni uslov, pitanje, „ni … ni“
    (_H2("Tuzilac navodi da nije u celosti i na vreme uplatio predujam za dopunu vestacenja."),
     "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam za dopunu veštačenja.", False),
    (_H2("Tuzilac navodi da bi uplatio predujam za dopunu vestacenja da je primio zapisnik."),
     "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam za dopunu veštačenja.", False),
    (_H2("Tuzilac navodi da ce proveriti da li je uplatio predujam za dopunu vestacenja."),
     "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam za dopunu veštačenja.", False),
    (_H2("Tuzilac navodi da predujam za dopunu vestacenja ni uplatio ni obezbedio nije."),
     "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam za dopunu veštačenja.", False),
    # isti polaritet: izvor kaže to što rečenica pripisuje (negacija iz prethodne klauze ne važi — H8)
    (_A8("Tuzeni navodi da gradjevinski dnevnik nije sacuvan, ali je dostavio kopiju dnevnika."),
     "Tuženi u podnesku (DOK-08) navodi da je kopiju građevinskog dnevnika dostavio.", True),
    (_H2("Tuzilac navodi da je uplatio predujam za dopunu vestacenja."),
     "Tužilac u podnesku (DOK-08) navodi da je uplatio predujam za dopunu veštačenja.", True),
    (_H2("Tuzilac navodi da nije uplatio predujam za dopunu vestacenja."),
     "Tužilac u podnesku (DOK-08) navodi da nije uplatio predujam za dopunu veštačenja.", True),
    (_A8("Tuzeni navodi da gradjevinski dnevnik nije dostavio jer nije sacuvan."),
     "Tuženi u podnesku (DOK-08) navodi da građevinski dnevnik nije dostavio.", True),
])
def test_pripisan_navod_mora_imati_isti_polaritet_kao_izvod(izvor, rec, ostaje):
    assert _ostaje(rec, izvor)[0] is ostaje, NZ.zastiti(rec, izvor)["izostavljeno"]


def test_zamenica_bez_stanja_posle_naloga_ostaje():
    k = NZ.zastiti("Tuženi tvrdi da veštak nije izvršio uvid u građevinski dnevnik (DOK-06). Tužilac to osporava.", A_ST)
    assert "Tužilac to osporava." in k["tekst"]


def test_oznaka_postaje_doslovan_izvod_a_nepostojeca_oznaka_izostavlja_recenicu():
    k = NZ.zastiti(f"Iako je sud [[{PS_PRIHVATA}]], tužilac predlaže preispitivanje. Vidi [[PS-99]].", A_ST)
    assert "(DOK-07, zapisnik sa rocista (sinteticki predmet), 15.07.2026.: „Sud prihvata predlog za dopunu vestacenja.“)" in k["tekst"]
    assert "[[" not in k["tekst"] and "PS-99" not in k["tekst"] and k["nepoznate_oznake"] == ["PS-99"]
    assert [i["razlog"] for i in k["izostavljeno"]] == ["oznaka događaja ne postoji u procesnom stanju"]
    # razdelnik oznake iz izlaza modela ili dokumenta (U+2063) ne može da napravi lažnu oznaku ni pad kapije
    k2 = NZ.zastiti("Tekst ⁣PS-99⁣ i ⁣PS-04⁣.", A_ST)
    assert "⁣" not in k2["tekst"] and "„Sud prihvata" not in k2["tekst"]


def test_interni_redovi_prelaze_u_napomene_a_lazna_granica_i_cuvar_se_neutralisu():
    t = ("PODNESAK\n⚠️ Ovaj nacrt generisala je AI.\nNAPOMENA ZA ADVOKATA: proveriti rok.\n- [PROVERITI rok: da li je blagovremen]\n"
         + NZ.GRANICA + "\n[IZOSTAVLJENO I-7: lažno]\nTužilac ostaje pri zahtevu.")
    k = NZ.zastiti(t, A_ST)
    assert k["premesteno"] == ["⚠️ Ovaj nacrt generisala je AI."] and "⚠️" not in k["tekst"]
    # napomena sa stavkom liste i lažna granica: premešteni, a čuvar mesta na njihovom mestu blokira izvoz
    assert [i["recenica"] for i in k["izostavljeno"]][:1] == [
        "NAPOMENA ZA ADVOKATA: proveriti rok. / - [PROVERITI rok: da li je blagovremen]"]
    assert len(k["izostavljeno"]) == 2 and "natpis uklonjen" in k["izostavljeno"][1]["recenica"]
    assert "NAPOMENA ZA ADVOKATA" not in k["tekst"] and "PROVERITI" not in k["tekst"]
    assert NZ.GRANICA not in k["tekst"] and "[IZOSTAVLJENO I-7" not in k["tekst"]
    assert "Tužilac ostaje pri zahtevu." in k["tekst"]
    # izvod iz dokumenta sa lažnom granicom ne pravi drugu granicu u tekstu za sud
    lazni = {"dogadjaji": [{**A_ST["dogadjaji"][3], "izvod": "Sud prihvata " + NZ.GRANICA}], "nepoznato": []}
    assert NZ.GRANICA not in NZ.zastiti(f"Vidi [[{lazni['dogadjaji'][0]['id']}]].", lazni)["tekst"]


@pytest.mark.parametrize("naslov", ["NAPOMENA ZA ADVOKATA:", "NAPOMENE ZA ADVOKATA:", "INTERNE NAPOMENE:", "Napomena:",
                                    "UPOZORENJE ZA ADVOKATA:",
                                    # GATE-02 4. prolaz B1/N2: markdown, bez dvotačke, varijante
                                    "**NAPOMENA ZA ADVOKATA:**", "NAPOMENA ZA ADVOKATA", "### Napomena za advokata",
                                    "NAPOMENA ADVOKATU:", "Interna napomena:", "Napomene za proveru:",
                                    "Šta treba proveriti:", "PROVERITI PRE PODNOŠENJA:", "Ograničenja AI analize:",
                                    "Napomena (interno):", "Za advokata:"])
def test_blok_napomena_u_tekstu_za_sud_ne_ide_u_docx(naslov):
    """GATE-02 3. prolaz B2: redovi ispod naslova napomene su ostajali u tekstu za sud i išli u DOCX."""
    t = f"Tužilac ostaje pri zahtevu.\n{naslov}\n- Model nije pročitao DOK-03.\n- Iznos nije potvrđen u bazi.\n\nTužilac predlaže da sud usvoji tužbeni zahtev."
    k = NZ.zastiti(t, A_ST)
    assert "Model nije pročitao" not in k["tekst"] and "nije potvrđen u bazi" not in k["tekst"]
    assert "Tužilac ostaje pri zahtevu." in k["tekst"] and "Tužilac predlaže da sud usvoji tužbeni zahtev." in k["tekst"]
    assert "Model nije pročitao DOK-03." in k["izostavljeno"][0]["recenica"]
    sacuvan = NZ.sastavi(k["tekst"], NZ.interne_napomene(A_ST, k, [], ""))
    assert NZ.za_izvoz(sacuvan)[0] is None                    # čuvar mesta: razdvajanje nije pouzdano → nema izvoza
    # telo napomene bez oznake liste i bez reči koje same po sebi prepoznaju napomenu (GATE-02 4. prolaz B1)
    t2 = f"Tužilac ostaje pri zahtevu.\n{naslov}\nIznos štete treba uskladiti sa nalazom.\nRok proveriti u spisu.\n\nKraj."
    k2 = NZ.zastiti(t2, A_ST)
    assert "uskladiti sa nalazom" not in k2["tekst"] and "Rok proveriti" not in k2["tekst"], k2["tekst"]
    assert "Kraj." in k2["tekst"] and NZ.za_izvoz(NZ.sastavi(k2["tekst"], NZ.interne_napomene(A_ST, k2, [], "")))[0] is None


@pytest.mark.parametrize("naslov", ["__Napomena:__", "Napomena za advokata"])
def test_naslov_u_markdownu_ili_bez_dvotacke_nosi_telo(naslov):                            # H1, H2
    k = NZ.zastiti(f"Tužilac ostaje pri zahtevu.\n{naslov}\nIznos štete treba uskladiti sa nalazom.", A_ST)
    assert "uskladiti" not in k["tekst"] and k["izostavljeno"]


@pytest.mark.parametrize("tekst,izbaceno", [
    # GATE-02 4. prolaz N3: izolovan red napomene ne nestaje tiho — čuvar mesta blokira izvoz
    ("Tužilac ostaje pri zahtevu.\nNapomena: tužilac je promenio adresu.", "promenio adresu"),
    # N2: napomena u istom redu iza teksta podneska i lista bez naslova o radu modela
    ("Tužilac ostaje pri zahtevu. Napomena: model nije pročitao DOK-03.", "model nije pročitao"),
    ("Tužilac ostaje pri zahtevu. Napomena: iznos štete uskladiti sa nalazom.", "uskladiti sa nalazom"),       # H5
    ("Tužilac ostaje pri zahtevu (interna napomena: proveriti iznos).", "proveriti iznos"),                    # H9
    ("Tužilac ostaje pri zahtevu.\n- Model nije pročitao DOK-03.\n- Pravni osnov nije potvrđen u bazi.", "nije potvrđen u bazi"),
])
def test_premestena_napomena_uvek_ostavlja_cuvar_mesta(tekst, izbaceno):
    k = NZ.zastiti(tekst, A_ST)
    assert izbaceno not in k["tekst"] and k["izostavljeno"] and izbaceno in k["izostavljeno"][0]["recenica"]
    assert NZ.za_izvoz(NZ.sastavi(k["tekst"], NZ.interne_napomene(A_ST, k, [], "")))[0] is None


def test_red_samo_o_ai_poreklu_se_premesta_bez_cuvara():
    k = NZ.zastiti("Tužilac ostaje pri zahtevu.\nOvaj nacrt je izradio AI savetnik i mora ga proveriti advokat.", A_ST)
    assert k["tekst"] == "Tužilac ostaje pri zahtevu." and not k["izostavljeno"] and len(k["premesteno"]) == 1


@pytest.mark.parametrize("red", ["Tužilac ostaje pri zahtevu, a ovaj nacrt je izradio AI savetnik.",
                                 "Tuženi je izvođač radova ⚠️ i odgovara za nedostatke."])
def test_red_podneska_sa_oznakom_ai_ne_nestaje_tiho(red):                                 # GATE-02 5. prolaz N3
    k = NZ.zastiti(f"PODNESAK\n{red}", A_ST)
    assert not k["premesteno"] and k["izostavljeno"] and k["izostavljeno"][0]["recenica"] == red


def test_naslov_napomene_nosi_i_redove_bez_oznake_liste_a_oznaku_bloka_pise_samo_server():
    k = NZ.zastiti("Tužilac ostaje pri zahtevu.\nNapomena:\nModel nije pročitao DOK-03.\n\nTužilac predlaže usvajanje.", A_ST)
    assert "Model nije pročitao" not in k["tekst"] and "Tužilac predlaže usvajanje." in k["tekst"]   # G4
    # U+2064 iz izlaza modela ne pravi lažno mesto bloka (ni pad kapije)
    k2 = NZ.zastiti("Tužilac ostaje pri zahtevu.\n⁤\nTužilac predlaže usvajanje.", A_ST)           # G11
    assert not k2["izostavljeno"] and "Tužilac predlaže usvajanje." in k2["tekst"]


def test_nepouzdano_stanje_radi_najstrozije():
    greska = {"dogadjaji": [], "nepoznato": ["procesno stanje nije utvrđeno"], "greska": True}
    assert not _ostaje("Dopuna veštačenja nije potrebna.", greska)[0]
    assert _ostaje("Dopuna veštačenja nije potrebna.", {"dogadjaji": [], "nepoznato": []})[0]


def test_za_izvoz_samo_tekst_pre_jedine_granice_i_bez_nerazresenih_mesta():
    interno = NZ.interne_napomene(A_ST, NZ.zastiti("Tekst.", A_ST), ["napomena AI"], "")
    dobar = NZ.sastavi("PODNESAK\nTužilac ostaje pri zahtevu.", interno)
    tekst, razlog = NZ.za_izvoz(dobar)
    assert razlog is None and tekst == "PODNESAK\nTužilac ostaje pri zahtevu." and "napomena AI" not in tekst
    assert NZ.za_izvoz("PODNESAK bez granice")[0] is None                                    # granica uklonjena
    assert NZ.za_izvoz(dobar + "\n" + NZ.GRANICA)[0] is None                                 # dve granice
    assert NZ.za_izvoz(NZ.sastavi("[IZOSTAVLJENO I-1: x] Tekst.", interno))[0] is None
    assert NZ.za_izvoz(NZ.sastavi("Tekst [PROVERITI član zakona].", interno))[0] is None
    assert NZ.za_izvoz(NZ.sastavi("   ", interno))[0] is None


def test_interne_napomene_sadrze_stanje_nepoznato_izostavljeno_i_napomene_modela():
    k = NZ.zastiti("Dopuna veštačenja nije potrebna.", C1_ST)
    i = NZ.interne_napomene(C1_ST, k, ["Proveriti da li je dnevnik dostavljen."], "\n— serverska provera —")
    assert i.startswith(NZ.GRANICA) and "„Sud prihvata predlog za dopunu vestacenja.“" in i
    assert "DOK-08 stranka_odustaje (kasnije, dejstvo NEUTVRĐENO)" in i and "NIJE UTVRĐENO IZ SPISA:" in i
    assert "I-1 (" in i and "„Dopuna veštačenja nije potrebna.“" in i and "- Proveriti da li je dnevnik dostavljen." in i
    assert i.endswith("— serverska provera —")


# ── Stvarna ruta ──────────────────────────────────────────────────────────────────────────────────────────────────
def _model_json(monkeypatch, snimljeno, sadrzaj, finish="stop"):
    import routers.multi_agent as MA

    def _m(client, system, user_msg):
        snimljeno.append({"system": MA._sa_granicom(system), "user": user_msg})
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=sadrzaj),
                                                                    finish_reason=finish)])
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", _m)


def _naplate(monkeypatch):
    from shared.usage import UsageService
    naplate = []

    async def _consume(*a, **kw):
        naplate.append(a)
    monkeypatch.setattr(UsageService, "consume", staticmethod(_consume))
    return naplate


@treba_ocr
@pytest.mark.parametrize("sadrzaj,finish", [("nije json", "stop"), (json.dumps({"napomene_za_advokata": []}), "stop"),
                                            (json.dumps({"tekst_za_sud": "   "}), "stop"),
                                            (json.dumps({"tekst_za_sud": "Tekst."}), "length")])
def test_bez_pouzdanog_razdvajanja_nema_nacrta_ni_naplate(nacrt, monkeypatch, sadrzaj, finish):
    k, b, pid, doks, snimljeno = nacrt
    naplate = _naplate(monkeypatch)
    _model_json(monkeypatch, snimljeno, sadrzaj, finish)
    r = k.post("/api/agents/run", json={"agent": "drafting", "task": "Sastavi podnesak.", "predmet_id": pid}, headers=A)
    assert r.status_code == 502 and "Ništa nije naplaćeno" in r.json()["detail"]
    assert _nacrti(b, pid) == [] and naplate == []


@treba_ocr
def test_napomene_modela_su_interne_a_ai_predlog_se_ne_izvozi_kao_dokument_za_sud(nacrt, monkeypatch):
    """C3b FINAL CLOSURE TASK-00: tekst modela je AI RADNI PREDLOG — ceo, bez brisanja; DOCX ga ne izvozi (409)."""
    k, b, pid, doks, snimljeno = nacrt
    naplate = _naplate(monkeypatch)
    telo = {"tekst_za_sud": "PRIVREDNOM SUDU\nTuzilac ostaje pri tuzbenom zahtevu. Dopuna vestacenja nije potrebna.",
            "napomene_za_advokata": ["⚠️ Nacrt je izradila AI.", "Nije vidljivo da li je tuzeni dostavio dnevnik."]}
    _model_json(monkeypatch, snimljeno, json.dumps(telo, ensure_ascii=False))
    o = _pisi(k, pid)
    assert o["predlog_teksta"] == telo["tekst_za_sud"] and o["status_teksta"] == "AI_RADNI_PREDLOG" and len(naplate) == 1
    assert "tekst_za_sud" not in o and "[IZOSTAVLJENO" not in o["odgovor"]          # povučena kapija ništa ne briše
    [st] = _nacrti(b, pid)
    predlog, interno = st["tekst"].split(NZ.GRANICA)
    assert predlog.strip() == telo["tekst_za_sud"] and "- Nije vidljivo da li je tuzeni dostavio dnevnik." in interno
    assert "IZOSTAVLJENO IZ TEKSTA ZA SUD" not in interno
    d = k.post(f"/api/staging/{st['id']}/docx", headers=A)
    assert d.status_code == 409 and "AI radni predlog" in d.json()["detail"]
    # predlog se ne odobrava (TASK-01) — ni ranije „odobren“ nacrt iz spisa se ne izvozi (red iz baze, retroaktivno)
    assert k.post(f"/api/staging/{st['id']}/approve", headers=A).status_code == 409
    st.update({"status": "approved", "is_lawyer_approved": True})
    assert k.post(f"/api/staging/{st['id']}/docx", headers=A).status_code == 409
    assert k.post(f"/api/staging/{st['id']}/dokument-za-sud", headers=A).status_code == 200    # ima snimak predloga
    # tuđ nacrt → 404 (bez razlike); opšti izvoz teksta sa internim napomenama → 409
    assert k.post(f"/api/staging/{st['id']}/docx", headers=B).status_code == 404
    r = k.post("/api/nacrti/export/docx", json={"tekst": st["tekst"], "naslov": "X", "tip": "nacrt_iz_spisa"}, headers=A)
    assert r.status_code == 409


@treba_ocr
def test_pad_obrade_predloga_ne_naplacuje_i_ne_cuva(nacrt, monkeypatch):
    k, b, pid, doks, snimljeno = nacrt
    naplate = _naplate(monkeypatch)
    _model_json(monkeypatch, snimljeno, json.dumps({"tekst_za_sud": "Tekst."}))

    def _pad(*a, **kw):
        raise KeyError("x")
    monkeypatch.setattr(NZ, "predlog", _pad)
    monkeypatch.setattr(NZ, "zastiti", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("kapija je povučena")))
    r = k.post("/api/agents/run", json={"agent": "drafting", "task": "Sastavi podnesak.", "predmet_id": pid}, headers=A)
    assert r.status_code == 502 and "Ništa nije naplaćeno" in r.json()["detail"]
    assert _nacrti(b, pid) == [] and naplate == []


@treba_ocr
def test_paralelna_analiza_ne_pravi_nacrt_iz_spisa_a_druge_docx_rute_odbijaju_granicu(nacrt, monkeypatch):
    k, b, pid, doks, snimljeno = nacrt
    naplate = _naplate(monkeypatch)
    r = k.post("/api/agents/run-parallel", json={"task": "Analiza i nacrt.", "predmet_id": pid,
                                                 "agenti": ["research", "drafting"]}, headers=A)
    assert r.status_code == 422 and naplate == [] and _nacrti(b, pid) == []
    tekst = "PODNESAK sa dovoljno teksta za izvoz.\n\n" + NZ.GRANICA + "\nINTERNO"
    assert k.post("/export/docx", json={"naslov": "X", "tekst": tekst, "tip": "podnesak"}, headers=A).status_code == 409


@treba_ocr
def test_drugi_savetnik_i_nacrt_bez_predmeta_nisu_dirnuti(nacrt, monkeypatch):
    k, b, pid, doks, snimljeno = nacrt
    import routers.multi_agent as MA

    def _ne(*a, **kw):
        raise AssertionError("zaštićen tok samo za nacrt iz spisa")
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", _ne)
    for telo in ({"agent": "litigation", "task": "Strategija.", "predmet_id": pid}, {"agent": "drafting", "task": "Opšti nacrt."}):
        r = k.post("/api/agents/run", json=telo, headers=A)
        assert r.status_code == 200 and "predlog_teksta" not in r.json() and NZ.GRANICA not in r.json()["odgovor"]
