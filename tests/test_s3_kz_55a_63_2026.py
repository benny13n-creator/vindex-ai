# -*- coding: utf-8 -*-
"""S3 — čl. 55a posle izmene KZ 63/2026 (objavljen 10.07.2026, primena od 18.07.2026).

Izvor (proveren 27.10.2026): prečišćen tekst Krivičnog zakonika na pravno-informacioni-sistem.rs
(eli/rep/sgrs/skupstina/zakon/2024/94/30 → „85/2005-30 … 94/2024-390, 63/2026-28“). Doslovni ćirilični tekst čl. 55a ispod je
kopiran sa te stranice; napomena izdavača: zakon 63/2026 stupa na snagu 18.07.2026, a samo njegovi čl. 2–3 (čl. 348–348g)
primenjuju se posle devet meseci. Lokalni tekst zakona (data/laws/pdfs/krivicni_zakonik.pdf) i baza Vindex su zaključno
sa 94/2024."""
from datetime import date

import pytest

from shared import visestruki_povrat as V

CL_55A_PIS = ("(1) За кривично дело учињено са умишљајем, за које је прописана казна затвора, суд ће изрећи казну изнад "
              "половине распона прописане казне полазећи од најмање мере те казне, под следећим условима: 1) ако је учинилац "
              "раније два пута осуђен за иста или истоврсна кривична дела учињена са умишљајем на затвор од најмање једну "
              "годину; 2) ако од дана отпуштања учиниоца са издржавања изречене казне до извршења новог кривичног дела није "
              "протекло пет година. (2) Под ранијом осудом подразумева се осуда за кривично дело која је утврђена "
              "правноснажном пресудом домаћег суда, односно суда стране државе.")

_LAT = dict(zip("абвгдђежзијклљмнњопрстћуфхцчџшАБВГДЂЕЖЗИЈКЛЉМНЊОПРСТЋУФХЦЧЏШ",
                ["a", "b", "v", "g", "d", "đ", "e", "ž", "z", "i", "j", "k", "l", "lj", "m", "n", "nj", "o", "p", "r", "s",
                 "t", "ć", "u", "f", "h", "c", "č", "dž", "š", "A", "B", "V", "G", "D", "Đ", "E", "Ž", "Z", "I", "J", "K",
                 "L", "Lj", "M", "N", "Nj", "O", "P", "R", "S", "T", "Ć", "U", "F", "H", "C", "Č", "Dž", "Š"]))

NOVO = ("Okrivljeni je ranije dva puta osuđen na zatvor od po dve godine za umišljajna dela, otpušten je pre tri godine, a sada "
        "je sa umišljajem izvršio delo za koje je propisan zatvor od jedne do osam godina.")


def _ishod(q):
    return V.izracunaj(**V.iz_pitanja(q)).primenjuje_se


def test_citat_je_doslovna_transliteracija_zvanicnog_teksta():
    assert "".join(_LAT.get(z, z) for z in CL_55A_PIS) == V.CITAT_55A
    assert "63/2026" in V.IZVOR_55A and "18.07.2026" in V.IZVOR_55A
    assert V.POCETAK_PRIMENE_63_2026 == date(2026, 7, 18)


def test_bez_navoda_o_istovrsnosti_uslov_je_nepoznat_a_uslovni_raspon_se_daje():
    t, r = V.blok(NOVO)
    assert r.primenjuje_se == V.NEPOZNATO
    assert "[NEPOZNATO] 1b) ranija dela su ista ili istovrsna kao novo delo" in t
    assert "Ako se uslovi utvrde: kazna bi morala biti veća od 4 godine i 6 meseci, najviše 8 godina" in t
    assert "baza zakona Vindex sadrži tekst Krivičnog zakonika zaključno sa izmenom 94/2024" in t


@pytest.mark.parametrize("dodatak,ocekivano", [
    (" Ranija dela su istovrsna sa novim delom.", V.DA),
    (" Ranija dela su ista krivična dela kao novo.", V.DA),
    (" Ranija dela nisu istovrsna sa novim.", V.NE),
    (" Ranija dela su različita krivična dela od novog.", V.NE),
    (" Ranija dela nisu ista, ali jesu istovrsna.", V.NEPOZNATO),            # oba smera → bez zaključka
])
def test_izricit_navod_istovrsnosti(dodatak, ocekivano):
    assert _ishod(NOVO + dodatak) == ocekivano


@pytest.mark.parametrize("q,ocekivano", [
    ("Okrivljeni je dva puta osuđen na zatvor od po dve godine za krađe učinjene sa umišljajem, otpušten je pre tri godine, a "
     "sada je sa umišljajem izvršio krađu, propisan zatvor od jedne do osam godina.", V.DA),          # isti naziv dela
    ("Okrivljeni je dva puta osuđen na zatvor od po dve godine za krađe učinjene sa umišljajem, otpušten je pre tri godine, a "
     "sada je sa umišljajem izvršio tešku krađu, propisan zatvor od jedne do osam godina.", V.NEPOZNATO),   # drugo delo
    ("Okrivljeni je dva puta osuđen na zatvor od po dve godine za prevare učinjene sa umišljajem, otpušten je pre tri godine, "
     "a sada je sa umišljajem izvršio krađu, propisan zatvor od jedne do osam godina.", V.NEPOZNATO),   # istovrsnost: sud
])
def test_isti_naziv_dela_je_isto_delo_drugi_naziv_ostaje_sudu(q, ocekivano):
    assert _ishod(q) == ocekivano


def test_vremensko_vazenje_i_strana_osuda_se_navode():
    q = ("Okrivljeni je dva puta osuđen za umišljajna dela na zatvor od po dve godine, jednom od strane suda u inostranstvu. "
         "Otpušten je 01.03.2022, a novo delo sa umišljajem izvršio je 15.01.2025. Propisan zatvor od jedne do osam godina.")
    t, r = V.blok(q)
    assert "čl. 5 st. 2" in t and "pre 18.07.2026" in t and "stranog suda" in t
    c = V.iz_pitanja(q.replace("15.01.2025", "15.09.2026"))
    assert c["novo_delo"] == date(2026, 9, 15)
    assert not any(n.startswith("Vremensko važenje") for n in V.izracunaj(**c).napomene)   # delo posle 18.07.2026


@pytest.mark.parametrize("mn_g,mx_g,polovina,najniza", [
    (1, 8, (4, 6), (4, 7)),            # 1–8: polovina 4 g. 6 m.; najniža iznad polovine na pune mesece 4 g. 7 m.
    (3, 12, (7, 6), (7, 7)),           # VKS Kzz 602/2022: 3–12 → 7 g. 6 m.; 7 g. 7 m. pravilno
])
def test_aritmetika_polovine_deterministicki(mn_g, mx_g, polovina, najniza):
    G, M = 360, 30
    r = V.izracunaj(novo_delo_umisljaj=True, propisan_min_dana=mn_g * G, propisan_max_dana=mx_g * G,
                    ranije_osude=[V.RanijaOsuda(True, 24)] * 2, proteklo_od_otpusta_meseci=24, istovrsna=True)
    assert r.primenjuje_se == V.DA
    assert r.raspon["polovina_raspona_dana"] == polovina[0] * G + polovina[1] * M
    assert r.raspon["najniza_dozvoljena_dana"] == najniza[0] * G + najniza[1] * M
