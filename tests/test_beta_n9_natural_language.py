"""N9 live beta regression (2026-11-08): do not erase explicit synthetic case facts.

The production legal Q&A reported two earlier two-year convictions and a
three-year release interval as UNKNOWN although all were explicitly supplied.
Tests cover this natural phrasing and fail-closed negative controls.
No real LLM, HTTP, Supabase or criminal case data.
"""

from shared.visestruki_povrat import analiza, NEPOZNATO, izracunaj


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
