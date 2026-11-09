"""N9 live beta regression (2026-11-08): do not erase explicit synthetic case facts.

The production legal Q&A reported two earlier two-year convictions and a
three-year release interval as UNKNOWN although all were explicitly supplied.
Tests cover this natural phrasing and fail-closed negative controls.
No real LLM, HTTP, Supabase or criminal case data.
"""

from datetime import date

import pytest

from shared.visestruki_povrat import analiza, blok, DA, NE, NEPOZNATO, izracunaj


SCENARIO = (
    "Lice je dva puta pravnosnažno osuđeno za ranija umišljajna krivična "
    "dela, u oba slučaja na po 2 godine zatvora, kazne je izdržalo; od "
    "dana poslednjeg otpuštanja iz zavoda do novog umišljajnog krivičnog "
    "dela prošle su 3 godine. Za novo delo propisan je zatvor od 1 do "
    "8 godina."
)


def test_live_n9_explicit_prior_sentences_and_interval_are_recognized():
    a, _ = analiza(SCENARIO)
    assert a["broj_ranijih_osuda"] == 2
    assert len(a["ranije_osude"]) == 2
    assert all(o.umisljaj is True and o.zatvor_meseci == 24 for o in a["ranije_osude"])
    assert a["novo_delo_umisljaj"] is True
    assert a["proteklo_od_otpusta_meseci"] == 36


def test_live_n9_missing_same_kind_remains_unknown_after_extraction():
    a, _ = analiza(SCENARIO)
    assert a["istovrsna"] is None
    # The 2026 same-kind condition must NOT be inferred just because duration
    # and count are now recognized.
    result = izracunaj(**a)
    assert result.primenjuje_se == NEPOZNATO


def test_negated_release_interval_is_not_accepted_as_affirmative():
    q = SCENARIO.replace("prošle su 3 godine", "nije prošlo 3 godine")
    a, _ = analiza(q)
    assert a["proteklo_od_otpusta_meseci"] is None


def test_conflicting_release_intervals_remain_unknown():
    q = SCENARIO.replace(
        "prošle su 3 godine",
        "prošle su 3 godine, ali od otpuštanja do novog dela prošle su 7 godina"
    )
    a, _ = analiza(q)
    assert a["proteklo_od_otpusta_meseci"] is None


def test_short_prison_terms_cannot_meet_prior_conviction_requirement():
    q = SCENARIO.replace("po 2 godine zatvora", "po 6 meseci zatvora")
    a, _ = analiza(q)
    assert all(o.zatvor_meseci == 6 for o in a["ranije_osude"])
    result = izracunaj(**a)
    assert result.primenjuje_se != "DA"


def test_old_unambiguous_prior_conviction_form_remains_supported():
    q = (
        "Dva puta je ranije osuđen za dela sa umišljajem na zatvor od "
        "po 2 godine. Sada je novo delo učinio sa umišljajem, a propisan "
        "je zatvor od 1 godine do 8 godina."
    )
    a, _ = analiza(q)
    assert a["broj_ranijih_osuda"] == 2
    assert [o.zatvor_meseci for o in a["ranije_osude"]] == [24, 24]


def test_quoted_new_offence_question_is_not_accepted_as_fact():
    q = "Da li bi se član 55a primenio ako bi postojalo novo umišljajno krivično delo?"
    a, _ = analiza(q)
    assert a["novo_delo_umisljaj"] is None


def test_duration_of_nonprison_sanction_is_not_a_prison_sentence():
    q = SCENARIO.replace("na po 2 godine zatvora, kazne je izdržalo", "na po 2 godine zabrane upravljanja")
    a, _ = analiza(q)
    assert all(o.zatvor_meseci is None for o in a["ranije_osude"])


def test_alternative_durations_are_not_an_affirmative_interval():
    a, _ = analiza(SCENARIO.replace("prošle su 3 godine", "prošle su 3 godine ili 7 godina"))
    assert a["proteklo_od_otpusta_meseci"] is None


def test_hypothetical_release_interval_does_not_establish_intent_or_time():
    a, _ = analiza(SCENARIO.replace("od dana", "pretpostavimo da su od dana"))
    assert a["novo_delo_umisljaj"] is None
    assert a["proteklo_od_otpusta_meseci"] is None


_DATIRANI_SCENARIO = (
    "Okrivljeni je dva puta pravnosnažno osuđen za ranije umišljajne krađe na zatvor od po dve godine, "
    "otpušten je 01.11.2023. godine, a novo delo izvršio je 01.11.2026. godine sa umišljajem, "
    "za koje je propisan zatvor od jedne do osam godina."
)


@pytest.mark.parametrize("navod,istovrsna,ishod", [
    ("Ranija dela su istovrsna sa novim delom.", True, DA),
    ("Pretpostavimo da su ranija dela istovrsna sa novim delom.", None, NEPOZNATO),
    ("Ako su ranija dela istovrsna sa novim delom, to bi promenilo pravni zaključak.", None, NEPOZNATO),
    ("U udžbeniku je primer: „Ranija dela su istovrsna sa novim delom.“", None, NEPOZNATO),
    ('U udžbeniku je primer: "Najpre je došlo do otpusta. Ranija dela su istovrsna."', None, NEPOZNATO),
])
def test_hipoteza_ili_citat_ne_utvrdjuju_istovrsnost(navod, istovrsna, ishod):
    pitanje = f"{_DATIRANI_SCENARIO} {navod}"
    cinjenice, _ = analiza(pitanje)
    tekst, rezultat = blok(pitanje)
    assert cinjenice["istovrsna"] is istovrsna
    assert rezultat.primenjuje_se == ishod
    assert ("sud MORA" in tekst) is (ishod == DA)


@pytest.mark.parametrize("negacija", [
    "nije dva puta pravnosnažno osuđen",
    "nije ranije dva puta pravnosnažno osuđen",
    "nije bio pravnosnažno osuđen dva puta",
])
def test_negiran_broj_osuda_ne_daje_dve_pravnosnazne_osude(negacija):
    pitanje = _DATIRANI_SCENARIO.replace("je dva puta pravnosnažno osuđen", negacija)
    pitanje += " Ranija dela su istovrsna sa novim delom."
    cinjenice, _ = analiza(pitanje)
    tekst, rezultat = blok(pitanje)
    assert cinjenice["broj_ranijih_osuda"] is None
    assert cinjenice["pravnosnaznost"] != DA
    assert rezultat.primenjuje_se == NEPOZNATO
    assert "sud MORA" not in tekst


@pytest.mark.parametrize("pitanje", [
    SCENARIO + " Novo delo učinjeno je 01.08.2026. Ranija dela jesu istovrsna kao novo delo. Da li se primenjuje član 55a KZ?",
    "Лице је два пута правноснажно осуђено за ранија умишљајна кривична дела, у оба случаја на по 2 године затвора, "
    "казне је издржало. Од последњег отпуштања до новог умишљајног кривичног дела прошле су 3 године. "
    "За ново дело прописан је затвор од 1 до 8 година. Дела су истоврсна. "
    "Ново дело учињено је 01.08.2026. Да ли се примењује члан 55а КЗ?",
])
def test_izricit_datum_novog_dela_sa_intervalom_utvrdjuje_verziju_zakona(pitanje):
    cinjenice, _ = analiza(pitanje)
    assert cinjenice["novo_delo"] == date(2026, 8, 1)
    assert cinjenice["otpust"] is None
    assert cinjenice["proteklo_od_otpusta_meseci"] == 36
    rezultat = izracunaj(**cinjenice)
    assert rezultat.primenjuje_se == DA
    assert rezultat.raspon["polovina_raspona_dana"] == 54 * 30
    assert rezultat.raspon["najniza_dozvoljena_dana"] == 55 * 30
    assert rezultat.raspon["najvisa_dana"] == 96 * 30


@pytest.mark.parametrize("dodatak", [
    " Presuda je doneta 01.08.2026. Žalba je izjavljena 03.08.2026.",
    " Novo delo učinjeno je 01.08.2026. Novo delo učinjeno je 30.07.2026.",
    " Novo delo učinjeno je 31.08.2026. U spisu se pominje i 01.08.2026.",
    " Novo delo učinjeno je 31.02.2026.",
])
def test_nepouzdan_datum_dela_ostaje_nepoznat_uz_interval(dodatak):
    cinjenice, _ = analiza(SCENARIO + dodatak)
    assert cinjenice["novo_delo"] is None
    assert cinjenice["proteklo_od_otpusta_meseci"] == 36


@pytest.mark.parametrize("navod", [
    "Pretpostavimo da je novo delo učinjeno 01.08.2026.",
    "Nije utvrđeno da li je novo delo učinjeno 01.08.2026.",
    "Nije tačno da je novo delo učinjeno 01.08.2026.",
    'U optužnici navod glasi: "Novo delo učinjeno je 01.08.2026." Datum u spisu nije utvrđen.',
    'U optužnici navod glasi: "To je tvrdnja tužilaštva. Novo delo učinjeno je 01.08.2026. Postupak je u toku."',
    "Da li je novo delo učinjeno 01.08.2026?",
    "Novo delo učinjeno je 01.08.2026. Datum dela nije utvrđen.",
])
def test_neizjavna_ili_sporna_tvrdnja_ne_utvrdjuje_datum_dela(navod):
    pitanje = SCENARIO + " Dela su istovrsna. " + navod + " Da li se primenjuje član 55a KZ?"
    cinjenice, _ = analiza(pitanje)
    tekst, rezultat = blok(pitanje)
    assert cinjenice["novo_delo"] is None
    assert cinjenice["proteklo_od_otpusta_meseci"] == 36
    assert rezultat.primenjuje_se == NEPOZNATO
    assert rezultat.raspon is None and "sud MORA" not in tekst


def test_samostalni_datum_dela_sa_godinom_ostaje_potvrdjen():
    pitanje = SCENARIO + " Dela su istovrsna. Novo delo je učinjeno 01.08.2026. godine. Da li se primenjuje član 55a KZ?"
    cinjenice, _ = analiza(pitanje)
    assert cinjenice["novo_delo"] == date(2026, 8, 1)
    assert blok(pitanje)[1].primenjuje_se == DA


@pytest.mark.parametrize("otpust_kao_datum", [True, False])
@pytest.mark.parametrize("navod,datum_dela", [
    ("Novo delo učinjeno je 01.08.2026.", date(2026, 8, 1)),
    ("Pretpostavimo da je novo delo učinjeno 01.08.2026.", None),
    ("Nije utvrđeno da li je novo delo učinjeno 01.08.2026.", None),
    ("Tužilac tvrdi da je novo delo učinjeno 01.08.2026.", None),
    ("Novo delo učinjeno je 01.08.2026. Datum dela nije utvrđen.", None),
    ('U optužnici navod glasi: "Novo delo učinjeno je 01.08.2026. To se osporava."', None),
])
def test_datum_dela_proverava_celu_recenicu_pre_sidra(otpust_kao_datum, navod, datum_dela):
    uvod, raspon = SCENARIO.split("Za novo delo")
    if otpust_kao_datum:
        uvod = uvod.split("; od dana poslednjeg otpuštanja")[0] + ". Poslednji put otpušten je 01.08.2023. "
    pitanje = (
        uvod + navod + " Učinjeno je s umišljajem. Dela su istovrsna. Za novo delo" + raspon
        + " Da li se primenjuje član 55a KZ?"
    )
    cinjenice, _ = analiza(pitanje)
    assert cinjenice["novo_delo"] == datum_dela
    assert cinjenice["otpust"] == (date(2023, 8, 1) if otpust_kao_datum and datum_dela else None)
    assert blok(pitanje)[1].primenjuje_se == (DA if datum_dela else NEPOZNATO)


@pytest.mark.parametrize("navod", [
    "",
    " Novo delo nije učinjeno s umišljajem.",
    " Novo delo nije izvršeno sa umišljajem.",
])
def test_nehat_i_negiran_umisljaj_novog_dela(navod):
    pitanje = SCENARIO.replace("novog umišljajnog", "novog nehatnog") + navod
    pitanje += " Novo delo je od 01.08.2026. Dela su istovrsna. Da li se primenjuje član 55a KZ?"
    cinjenice, _ = analiza(pitanje)
    assert cinjenice["novo_delo_umisljaj"] is False
    assert cinjenice["proteklo_od_otpusta_meseci"] == 36
    assert all(o.umisljaj is True for o in cinjenice["ranije_osude"])
    assert blok(pitanje)[1].primenjuje_se == NE


def test_protivrecni_navodi_ne_utvrdjuju_krivicu_novog_dela():
    pitanje = SCENARIO + " Novo delo nije učinjeno s umišljajem."
    cinjenice, _ = analiza(pitanje)
    assert cinjenice["novo_delo_umisljaj"] is None


@pytest.mark.parametrize("otvaranje,zatvaranje", [('"', '"'), ("„", "“")])
def test_hipoteticki_citat_ne_utvrdjuje_osude_ili_pravnosnaznost(otvaranje, zatvaranje):
    pitanje = (
        f"U objašnjenju sam citirao hipotetički primer: {otvaranje}"
        f"Lice je dva puta pravnosnažno osuđeno za ranija umišljajna dela na po 2 godine zatvora{zatvaranje}. "
        "Za mog okrivljenog o tim činjenicama nema podataka. Da li se na njega primenjuje član 55a KZ?"
    )
    cinjenice, _ = analiza(pitanje)
    assert cinjenice["broj_ranijih_osuda"] is None
    assert cinjenice["ranije_osude"] is None
    assert cinjenice["pravnosnaznost"] != DA
    assert blok(pitanje)[1].primenjuje_se == NEPOZNATO


def test_negacija_umisljaja_ne_iznosi_nehat_kao_utvrdjenu_cinjenicu():
    pitanje = SCENARIO.replace("novog umišljajnog", "novog")
    pitanje += " Novo delo nije učinjeno s umišljajem. Da li se primenjuje član 55a KZ?"
    tekst, rezultat = blok(pitanje)
    assert rezultat.primenjuje_se == NE
    assert "novo delo: bez umišljaja" in tekst
    assert "učinjeno iz nehata" not in tekst


def test_model_okvir_zadrzava_neizvesnost_bez_korisnickog_teksta():
    from main import _okvir_povrata_za_model

    okvir = _okvir_povrata_za_model(SCENARIO + " Sintetički jedinstveni tekst XYZ.")
    assert "Proračun sistema za navedene činjenice: NEPOZNATO" in okvir
    assert "ista ili istovrsna" in okvir
    assert "vremenski merodavan zakon = NEPOZNATO" in okvir
    assert "XYZ" not in okvir
    assert _okvir_povrata_za_model("Koji sud je mesno nadležan po ZPP?") == ""


def test_model_okvir_ne_dozvoljava_potvrdan_zakljucak_za_kratke_osude():
    from main import _okvir_povrata_za_model

    okvir = _okvir_povrata_za_model(SCENARIO.replace("po 2 godine", "po 6 meseci"))
    assert "Proračun sistema za navedene činjenice: NE." in okvir
    assert "Za NE napiši da nema primene" in okvir


def _pitanje_sa_osudama_saucesnika(navod):
    return (
        "Saučesnik je dva puta pravnosnažno osuđen za ranija umišljajna dela na po 2 godine zatvora. "
        + navod + " Novo umišljajno delo je od 01.08.2026. Da li se za okrivljenog primenjuje čl. 55a KZ?"
    )


def test_izricito_neosudjivan_okrivljeni_ne_nasledjuje_osude_saucesnika():
    pitanje = _pitanje_sa_osudama_saucesnika("Okrivljeni nije ranije osuđivan.")
    cinjenice, _ = analiza(pitanje)
    assert cinjenice["broj_ranijih_osuda"] == 0
    assert cinjenice["ranije_osude"] is None
    assert cinjenice["pravnosnaznost"] != DA
    assert blok(pitanje)[1].primenjuje_se == NE


@pytest.mark.parametrize("navod", [
    "",
    "Nije potvrđeno da okrivljeni nije ranije osuđivan.",
    "Da li je tačno da okrivljeni nije ranije osuđivan?",
    'U spisu se navodi: "Okrivljeni nije ranije osuđivan."',
    "Okrivljeni nije ranije osuđivan. Okrivljeni je dva puta pravnosnažno osuđen.",
    "Okrivljeni nije ranije osuđivan, ali ima dve pravnosnažne presude.",
    "Okrivljeni nije ranije osuđivan. Prvi okrivljeni i drugi okrivljeni su različita lica.",
])
def test_neutvrdjen_ili_protivurecan_navod_ne_utvrdjuje_osude_okrivljenog(navod):
    pitanje = _pitanje_sa_osudama_saucesnika(navod)
    cinjenice, _ = analiza(pitanje)
    assert cinjenice["broj_ranijih_osuda"] is None
    assert cinjenice["ranije_osude"] is None
    assert cinjenice["pravnosnaznost"] != DA
    assert blok(pitanje)[1].primenjuje_se == NEPOZNATO


@pytest.mark.parametrize("pitanje", [
    "Да ли се примењује члан 55а КЗ?",
    "КЗ члан 55а",
    "члан 55а Кривичног законика",
    "čl. 55а КЗ",
])
def test_izricit_clan_kz_na_cirilici_trazi_tacnu_odredbu(pitanje):
    from app.services.retrieve import ekstrakcija_clana

    assert ekstrakcija_clana(pitanje) == ("Član 55a", "KZ")


_DATUMI_OTPUSTA = (
    "Za prvo izvršenje otpust je bio 2018, za poslednje izvršenje otpust je bio 01.08.2023, "
    "a novo istovrsno delo je učinjeno 01.08.2026."
)


@pytest.mark.parametrize("trajanje,godina,stanje", [("3 godine", 2026, DA), ("5 godina", 2028, NE)])
def test_izricito_oznacen_poslednji_otpust_i_potvrdjen_interval(trajanje, godina, stanje):
    pitanje = SCENARIO.replace("3 godine", trajanje) + " " + _DATUMI_OTPUSTA.replace("2026", str(godina)) + " Član 55a KZ?"
    cinjenice, _ = analiza(pitanje)
    assert cinjenice["otpust"] == date(2023, 8, 1)
    assert cinjenice["novo_delo"] == date(godina, 8, 1)
    assert cinjenice["novo_delo_umisljaj"] is True
    assert cinjenice["proteklo_od_otpusta_meseci"] == (godina - 2023) * 12
    rezultat = blok(pitanje)[1]
    assert rezultat.primenjuje_se == stanje
    if stanje == DA:
        assert rezultat.raspon["polovina_raspona_dana"] == 54 * 30


@pytest.mark.parametrize("navod", [
    _DATUMI_OTPUSTA.replace("poslednje izvršenje", "drugo izvršenje"),
    "Pretpostavimo: " + _DATUMI_OTPUSTA,
    _DATUMI_OTPUSTA.replace("bio 01.08.2023", "navodno bio 01.08.2023"),
    _DATUMI_OTPUSTA.replace("2018", "2024"),
    _DATUMI_OTPUSTA.replace("01.08.2023", "01.08.2022"),
    _DATUMI_OTPUSTA.replace("01.08.2023", "31.02.2023"),
    _DATUMI_OTPUSTA.replace("je učinjeno", "nije učinjeno"),
    "U optužnici navode: \"" + _DATUMI_OTPUSTA + "\"",
    _DATUMI_OTPUSTA + " Datum izvršenja nije utvrđen.",
    _DATUMI_OTPUSTA + " Postoji i otpust iz 2021.",
    _DATUMI_OTPUSTA + " Novo delo učinjeno je 02.08.2026.",
    _DATUMI_OTPUSTA + " Reč je o uslovnom otpustu.",
    _DATUMI_OTPUSTA + " Pominje se i saučesnik.",
])
def test_oznacen_poslednji_otpust_ne_resava_sporne_ili_protivrecne_navode(navod):
    pitanje = SCENARIO + " " + navod + " Član 55a KZ?"
    cinjenice, _ = analiza(pitanje)
    assert cinjenice["otpust"] is None
    assert cinjenice["novo_delo"] is None
    assert blok(pitanje)[1].primenjuje_se != DA


def test_oznacen_poslednji_otpust_ne_preuzima_potvrdu_intervala_iz_citata():
    uvod = SCENARIO.replace("; od dana", '. U spisu se navodi: "Navod odbrane. Od dana')
    uvod = uvod.replace("3 godine. Za novo", '3 godine. Navod nije potvrđen." Za novo')
    cinjenice, _ = analiza(uvod + " " + _DATUMI_OTPUSTA + " Član 55a KZ?")
    assert cinjenice["otpust"] is None
    assert cinjenice["novo_delo"] is None
