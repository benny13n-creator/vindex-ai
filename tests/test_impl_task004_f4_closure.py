"""IMPL TASK 004 — F4 CLOSURE: assessed-only strength + eksplicitna coverage osa.

Do sada je `calculate_procesni_rizik` čitao `d.get("snaga", "srednja")` nad SVIM
redovima. Pošto je `predmet_dokazi.snaga` `NOT NULL DEFAULT 'srednja'`, svaka
NEPROCENJENA tvrdnja je ulazila u imenilac kao procenjena tvrdnja srednje snage:
10 neprocenjenih je obaralo advokatovo „Jaka" na „Srednja", a predmet sa 3
neprocenjene tvrdnje je tvrdio „Srednja, 100%".

Tri ose koje ovi testovi drže razdvojenima:
    A) postojanje tvrdnji      -> broj_tvrdnji
    B) pokrivenost procene     -> pokrivenost_procene / broj_procenjenih
    C) snaga PROCENJENIH       -> snaga_dokaza / snaga_pct / snaga_detalji
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.risk_engine import (  # noqa: E402
    SNAGA_NEPROCENJENO, calculate_procesni_rizik, identify_case_problems,
)
from shared.constants import EXPECTED_DOCS  # noqa: E402
from shared.evidence_write import KOLONA_IZVOR_SNAGE as K  # noqa: E402

# DB-veran red: `snaga` je NOT NULL, pa i neprocenjen red nosi vrednost.
UN = {"snaga": "srednja", K: "podrazumevano"}      # neprocenjeno
UL = {"snaga": "jaka", K: None}                    # legacy, fail-closed
AJ = {"snaga": "jaka", K: "covek"}
AS = {"snaga": "srednja", K: "covek"}
AL = {"snaga": "slaba", K: "covek"}
DJ = {"snaga": "jaka", K: "dc005"}


def R(dokazi, dokumenti=None, rocista=None):
    return calculate_procesni_rizik(
        dokazi=dokazi, dokumenti=dokumenti or [], rocista=rocista or [],
        tip_predmeta="ostalo", expected_docs=EXPECTED_DOCS,
    )


def SLIKA(x):
    """(label, pct, detalji, status, procenjenih, tvrdnji) — sve sem rokova."""
    return (x["snaga_dokaza"], x["snaga_pct"], x["snaga_detalji"],
            x["pokrivenost_procene"], x["broj_procenjenih"], x["broj_tvrdnji"])


# ═══════════════════════════════════════════════════════════════════════════
# §11 — OBAVEZNA TEST MATRICA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("dokazi,status,label,proc,tvrd", [
    ([],                       "NO_CLAIMS",           "Nema dokaza",       0, 0),
    ([UN],                     "EVIDENCE_UNASSESSED", SNAGA_NEPROCENJENO,  0, 1),
    ([UN] * 3,                 "EVIDENCE_UNASSESSED", SNAGA_NEPROCENJENO,  0, 3),
    ([UN] * 100,               "EVIDENCE_UNASSESSED", SNAGA_NEPROCENJENO,  0, 100),
    ([AJ],                     "EVIDENCE_ASSESSED",   "Jaka",              1, 1),
    ([AJ, UN, UN],             "EVIDENCE_PARTIAL",    "Jaka",              1, 3),
    ([AJ] + [UN] * 99,         "EVIDENCE_PARTIAL",    "Jaka",              1, 100),
    ([AJ] * 3,                 "EVIDENCE_ASSESSED",   "Jaka",              3, 3),
    ([AS] * 3,                 "EVIDENCE_ASSESSED",   "Srednja",           3, 3),
    ([AL] * 3,                 "EVIDENCE_ASSESSED",   "Slaba",             3, 3),
    ([AL] + [UN] * 99,         "EVIDENCE_PARTIAL",    "Slaba",             1, 100),
])
def test_matrica(dokazi, status, label, proc, tvrd):
    x = R(dokazi)
    assert x["pokrivenost_procene"] == status
    assert x["snaga_dokaza"] == label
    assert x["broj_procenjenih"] == proc
    assert x["broj_tvrdnji"] == tvrd


# ═══════════════════════════════════════════════════════════════════════════
# METAMORFNE INVARIJANTE M1–M10
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("baza", [AJ, AS, AL, DJ])
@pytest.mark.parametrize("n", [1, 10, 100])
def test_m1_unknown_ne_menja_snagu_procenjenih(baza, n):
    """Dodavanje neprocenjenih tvrdnji ne sme dirati strength procenjenih."""
    sam = R([baza])
    sa_unknown = R([baza] + [UN] * n)
    for k in ("snaga_dokaza", "snaga_pct", "snaga_detalji", "health_score", "nivo"):
        assert sam[k] == sa_unknown[k], k


def test_m2_99_unknown_ne_pretvara_jaka_u_srednja():
    assert R([AJ])["snaga_dokaza"] == "Jaka"
    assert R([AJ] + [UN] * 99)["snaga_dokaza"] == "Jaka"


def test_m3_unknown_ne_ulazi_u_denominator():
    x = R([AJ] + [UN] * 99)
    assert sum(x["snaga_detalji"].values()) == 1
    assert x["snaga_detalji"] == {"jaka": 1, "srednja": 0, "slaba": 0}


def test_m4_jedna_procenjena_od_sto_nije_potpuna_pokrivenost():
    x = R([AJ] + [UN] * 99)
    assert x["pokrivenost_procene"] == "EVIDENCE_PARTIAL"
    assert x["pokrivenost_procene"] != "EVIDENCE_ASSESSED"
    assert (x["broj_procenjenih"], x["broj_tvrdnji"]) == (1, 100)


def test_m5_nema_tvrdnji_nije_isto_sto_i_neprocenjeno():
    a, b = R([]), R([UN] * 3)
    assert a["snaga_dokaza"] == "Nema dokaza"
    assert b["snaga_dokaza"] == SNAGA_NEPROCENJENO
    assert a["pokrivenost_procene"] != b["pokrivenost_procene"]
    assert (a["broj_tvrdnji"], b["broj_tvrdnji"]) == (0, 3)


def test_m6_covek_ostaje_covek_samo_uz_eksplicitan_unos():
    """Provenance se ne izvodi ovde -- samo se čita. Ugovor iz TASK 003A/003B."""
    from shared.evidence_write import izvor_snage_iz_odluke
    assert izvor_snage_iz_odluke("covek", "srednja") == "covek"
    assert izvor_snage_iz_odluke("podrazumevano", "srednja") == "podrazumevano"


def test_m7_dc005_ne_postaje_covek():
    from shared.evidence_write import izvor_snage_iz_odluke
    assert izvor_snage_iz_odluke("dc005", "jaka") == "dc005"
    assert izvor_snage_iz_odluke("dc005", "srednja") == "podrazumevano"
    assert R([DJ])["snaga_dokaza"] == "Jaka"
    assert R([DJ])["pokrivenost_procene"] == "EVIDENCE_ASSESSED"


def test_m8_legacy_null_je_fail_closed():
    """Legacy red ima `snaga='jaka'` ali NEMA provenance -> ne broji se."""
    x = R([UL] * 3)
    assert x["broj_procenjenih"] == 0
    assert x["broj_tvrdnji"] == 3
    assert x["pokrivenost_procene"] == "EVIDENCE_UNASSESSED"
    assert x["snaga_dokaza"] == SNAGA_NEPROCENJENO
    assert x["snaga_detalji"] == {"jaka": 0, "srednja": 0, "slaba": 0}


def test_m9_neprocenjena_ne_dobija_implicitnu_srednju():
    """UN fizički JESTE `snaga='srednja'` -- ne sme se prebrojati kao srednja."""
    x = R([UN] * 5)
    assert x["snaga_detalji"]["srednja"] == 0
    assert x["snaga_dokaza"] != "Srednja"
    assert x["snaga_pct"] == 0


@pytest.mark.parametrize("dokazi,label,pct,health", [
    ([AJ] * 3, "Jaka", 100, 70),
    ([AS] * 3, "Srednja", 100, 50),
    ([AL] * 3, "Slaba", 10, 35),
])
def test_m10_postojeca_procenjena_snaga_ostaje_stabilna(dokazi, label, pct, health):
    """Predmet u kome je SVE procenjeno mora dati iste brojeve kao pre TASK 004."""
    x = R(dokazi)
    assert (x["snaga_dokaza"], x["snaga_pct"], x["health_score"]) == (label, pct, health)


# ═══════════════════════════════════════════════════════════════════════════
# POTROŠAČI — problemi, LLM ugovor, aditivnost
# ═══════════════════════════════════════════════════════════════════════════

def test_prazan_predmet_i_dalje_javlja_nema_dokaza():
    pr = identify_case_problems(R([]), "ostalo")
    assert any(p["ozbiljnost"] == "kritican" and "Nema uploadovanih dokaza" in p["problem"]
               for p in pr)


def test_neprocenjen_predmet_NE_javlja_nema_dokaza():
    """Najvažniji potrošački test: 3 tvrdnje postoje, tvrdnja o njihovom
    odsustvu je činjenično netačna."""
    pr = identify_case_problems(R([UN] * 3), "ostalo")
    assert not any("Nema uploadovanih dokaza" in p["problem"] for p in pr)
    assert any("nije procenjeno" in p["problem"] for p in pr)


def test_delimicna_procena_javlja_pokrivenost():
    pr = identify_case_problems(R([AJ] + [UN] * 99), "ostalo")
    assert any("1 od 100" in p["problem"] for p in pr)


def test_izlaz_je_aditivan_stari_kljucevi_netaknuti():
    x = R([AJ, UN])
    for k in ("nivo", "boja", "health_score", "snaga_dokaza", "snaga_pct",
              "snaga_detalji", "nedostajuci_dokazi", "nedostajuci_count",
              "predstojeći_rokovi", "kriticni_rokovi", "zakasneli_rokovi",
              "kriticni_rocista"):
        assert k in x, k
    for k in ("broj_tvrdnji", "broj_procenjenih", "pokrivenost_procene"):
        assert k in x, k


def test_sentinel_nije_strength_klasa():
    """`Nije procenjeno` ne sme ući ni u jedan brojač ni u risk bonus/kaznu."""
    x = R([UN] * 3)
    assert SNAGA_NEPROCENJENO not in x["snaga_detalji"]
    assert x["snaga_detalji"] == {"jaka": 0, "srednja": 0, "slaba": 0}
    # health je isti kao za prazan predmet: kaznu pokreće denominator, ne label
    assert x["health_score"] == R([])["health_score"]


def test_svi_potrosaci_dobijaju_isti_izvor():
    """Jedan derivation layer: `pokrivenost_procene` iz evidence_write je jedini
    vlasnik pojma, risk_engine ga ne kopira."""
    import inspect
    from services import risk_engine
    src = inspect.getsource(risk_engine)
    assert "pokrivenost_procene(dokazi)" in src
    # nema druge kopije brojanja provenance-a u risk_engine
    assert src.count("IZVORI_PROCENJENO") == 2  # import + jedan filter
