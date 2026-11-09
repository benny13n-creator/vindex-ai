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
