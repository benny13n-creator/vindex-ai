# -*- coding: utf-8 -*-
"""
PRG-P1-NIGHT-001 / T2 — karakterizaciona matrica COI scoring-a.

Fiksira SEMANTIKU identiteta stranke, ne implementaciju. Svaki par nosi
očekivani opseg, jer `routers/conflict_check.py` ima tri opsega:

    score <  CONFLICT_WARN (70)   -> nema unosa u `konflikti`  -> status "clear"
    70 <= score < CONFLICT_HARD   -> unos, sever NIZAK/SREDNJI -> "conflict" ako je predmet aktivan
    score >= CONFLICT_HARD (85)   -> unos, sever VISOK         -> "conflict" + poruka OZBILJAN

Zato je jedini opseg koji stvarno oslobađa stranku `CLEAR`. Parovi označeni
CLEAR moraju pasti ispod 70 — ne 85 — inače advokat i dalje dobija blokirajuće
upozorenje.

Reference iz T1 forenzike (mereno, produkciona konfiguracija 3.11 + rapidfuzz):
  "Sasvim drugačija firma" vs "Firma doo" -> 100  (partial_ratio substring)
  "Milan Jovanović" vs "Milica Jovanović" ->  90  (token_sort_ratio, prisutno i u difflib grani)
"""
import os
import sys
import unicodedata

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CLEAR = "clear"        # < 70 — stranka se sme prihvatiti
REVIEW = "review"      # 70..84 — dvosmisleno, advokat odlučuje
CONFLICT = "conflict"  # >= 85 — isti subjekt


# ── A. Očigledno različita pravna lica ───────────────────────────────────────
RAZLICITA_PRAVNA_LICA = [
    ("Sasvim drugačija firma", "Firma doo",           CLEAR),
    ("Firma doo",              "Druga firma doo",     CLEAR),
    ("AB Komerc",              "XY Komerc",           CLEAR),
    ("Delta Inženjering doo",  "Alfa Trgovina doo",   CLEAR),
    ("Delta Inženjering doo",  "Delta Trgovina doo",  CLEAR),
    ("Alfa Komerc Beograd",    "Beta Komerc Beograd", CLEAR),
    # Ponovljen token: bez "trošenja" uparenog tokena, drugo "Delta" bi se
    # uparilo sa istim tokenom druge strane i proglasilo identitet.
    ("Delta Delta doo",        "Delta Alfa doo",      CLEAR),
    ("Alfa Alfa Komerc",       "Alfa Beta Komerc",    CLEAR),
]

# ── B. Isti subjekt, druga reprezentacija ───────────────────────────────────
ISTI_SUBJEKT = [
    ("Petar Petrović",        "Petar Petrović",             CONFLICT),
    ("Petar Petrović",        "PETAR  PETROVIĆ",            CONFLICT),
    ("Petrović Petar",        "Petar Petrović",             CONFLICT),
    ("Petar M. Petrović",     "Petar Petrović",             CONFLICT),
    ("Delta Inženjering doo", "Delta Inženjering d.o.o.",   CONFLICT),
    ("Delta Inženjering",     "Delta Inženjering Beograd",  CONFLICT),
    ("Delta Inženjering doo", "Delta Inžinjering doo",      CONFLICT),  # tipfeler
]

# ── C. Fizička lica — deljeno prezime NIJE isti čovek ───────────────────────
FIZICKA_LICA = [
    ("Milan Jovanović",  "Milica Jovanović",  CLEAR),
    ("Marko Marković",   "Marko Marić",       CLEAR),
    ("Ana Anić",         "Jovan Anić",        CLEAR),
    ("Petar Petrović",   "Petar Nikolić",     CLEAR),
    # ISPRAVKA MOG SOPSTVENOG OCEKIVANJA (T5). Prvobitno je ovde stajalo CLEAR.
    # Merenje ga obara: "nikola"/"nikolina" = 85, a "petrovic"/"petorvic"
    # (obican tipfeler istog coveka) = 87. Razlika je 2 poena, pa se ta dva
    # slucaja ne mogu razdvojiti slicnoscu znakova. Prag koji bi oslobodio
    # "Nikolinu" propusta 4.4% stvarnih tipfelera (33/758 mereno). Za COI je
    # propusten sukob teza greska od suvisne oznake, pa ovaj par ostaje oznacen.
    # Ovo je svesno prihvacen lazni pozitiv, ne previd.
    ("Nikola Nikolić",   "Nikolina Nikolić",  CONFLICT),
]

# ── D. Pravni nastavci — nastavak sam po sebi ne pravi identitet ────────────
PRAVNI_NASTAVCI = [
    ("Delta doo",   "Delta d.o.o.",  CONFLICT),
    ("Delta doo",   "Delta a.d.",    CONFLICT),   # isto jezgro, druga forma
    ("Delta doo",   "Omega doo",     CLEAR),      # isti nastavak, drugo jezgro
    ("Alfa a.d.",   "Beta a.d.",     CLEAR),
]

# ── E. Substring adversarial — jezgro T1 nalaza ─────────────────────────────
SUBSTRING_ADVERSARIAL = [
    ("AB",      "AB Komerc",    CLEAR),
    ("Komerc",  "Nova Komerc",  CLEAR),
    ("Nova",    "Nova Komerc",  CLEAR),
    ("Firma",   "Moja Firma",   CLEAR),
    ("A",       "A Komerc",     CLEAR),
]

# ── F. Unicode / ćirilica / interpunkcija / razmaci ─────────────────────────
UNICODE_I_FORMA = [
    # NAPOMENA: par ("Đorđe Šešelj", "Djordje Sheshelj") NIJE u matrici. On bi
    # tražio digrafsku transliteraciju (Š->sh, Ž->zh) latinice u latinicu, što
    # proizvod nikada nije tvrdio da radi; `_CYR_TO_LAT` prevodi samo ćirilicu.
    # Mereno: skor 72. Zabeleženo kao OUT-OF-SCOPE nalaz, ne kao ugovor.
    ("Петар Петровић",    "Petar Petrović",     CONFLICT),  # ćirilica -> latinica
    ("Petar   Petrović",  "Petar Petrović",     CONFLICT),  # višestruki razmak
    ("petar petrović",    "PETAR PETROVIĆ",     CONFLICT),  # veličina slova
    ("Čačak Komerc",      "Cacak Komerc",       CONFLICT),  # dijakritici
    ("Đorđe Šešelj",      "Đorđe Marković",     CLEAR),     # isto ime, drugo prezime
]

SVE = (RAZLICITA_PRAVNA_LICA + ISTI_SUBJEKT + FIZICKA_LICA
       + PRAVNI_NASTAVCI + SUBSTRING_ADVERSARIAL + UNICODE_I_FORMA)


def _opseg(score: int) -> str:
    from routers.conflict_check import CONFLICT_HARD, CONFLICT_WARN
    if score >= CONFLICT_HARD:
        return CONFLICT
    if score >= CONFLICT_WARN:
        return REVIEW
    return CLEAR


@pytest.mark.parametrize("a,b,ocekivano", SVE,
                         ids=[f"{a}|{b}" for a, b, _ in SVE])
def test_scoring_opseg(a, b, ocekivano):
    """Skor mora pasti u semantički ispravan opseg — u OBA smera (simetrija)."""
    from routers.conflict_check import _fuzzy_score
    sc_ab = _fuzzy_score(a, b)
    sc_ba = _fuzzy_score(b, a)
    assert sc_ab == sc_ba, (
        f"scoring nije simetričan: {a!r}->{b!r}={sc_ab}, obrnuto={sc_ba}. "
        f"COI ne sme zavisiti od toga koja je stranka upisana prva.")
    assert _opseg(sc_ab) == ocekivano, (
        f"{a!r} vs {b!r}: skor {sc_ab} pada u opseg {_opseg(sc_ab)!r}, "
        f"očekivano {ocekivano!r}.")


def test_identican_string_uvek_sto():
    from routers.conflict_check import _fuzzy_score
    for a, b, _ in SVE:
        assert _fuzzy_score(a, a) == 100, f"{a!r} vs sam sebe nije 100"
        assert _fuzzy_score(b, b) == 100, f"{b!r} vs sam sebe nije 100"


def test_prazan_ulaz_ne_pravi_konflikt():
    from routers.conflict_check import _fuzzy_score
    for prazno in ("", "   ", None, "doo", "d.o.o."):
        assert _fuzzy_score(prazno, "Petar Petrović") == 0, f"{prazno!r} dalo != 0"
        assert _fuzzy_score("Petar Petrović", prazno) == 0, f"{prazno!r} dalo != 0"


def test_nijedan_par_iz_t1_forenzike_ne_ostaje_lazan():
    """Doslovni parovi iz PRG-002 izveštaja. Ovo je regresioni katanac."""
    from routers.conflict_check import _fuzzy_score, CONFLICT_WARN
    dokazani_lazni = [
        ("Sasvim drugačija firma", "Firma doo"),
        ("Firma doo",              "Druga firma doo"),
        ("Milan Jovanović",        "Milica Jovanović"),
        ("AB Komerc",              "XY Komerc"),
    ]
    lose = [(a, b, _fuzzy_score(a, b)) for a, b in dokazani_lazni
            if _fuzzy_score(a, b) >= CONFLICT_WARN]
    assert not lose, f"lažni konflikti i dalje prelaze prag {CONFLICT_WARN}: {lose}"


# ── G. Katanci za kalibraciju — bez njih je prag slobodan da odluta ──────────

def _mutacije(baza: str):
    """Jedna izmena znaka: izostavljanje, transpozicija susednih, udvajanje."""
    out = []
    for i in range(len(baza)):
        if baza[i] == " ":
            continue
        out.append(baza[:i] + baza[i + 1:])
        if i < len(baza) - 1 and baza[i + 1] != " ":
            out.append(baza[:i] + baza[i + 1] + baza[i] + baza[i + 2:])
        out.append(baza[:i] + baza[i] + baza[i:])
    return [m for m in out if m != baza]


BAZNA_IMENA = [
    "Petar Petrović", "Delta Inženjering doo", "Marija Nikolić Stanković",
    "Alfa Komerc Beograd", "Jovan Simić", "Milan Obradović", "Zoran Ilić",
]


def test_tipfeler_ne_sme_da_sakrije_sukob():
    """Propušten sukob je teža greška od suvišne oznake.

    Ovo je katanac na `_TOKEN_JAK`. Mereno pri kalibraciji: prag >= 86 propušta
    4.4% ovih parova, prag 90 propušta 19.7%. Test pada ako neko podigne prag.
    """
    from routers.conflict_check import _fuzzy_score, CONFLICT_WARN
    propusteni = []
    ukupno = 0
    for baza in BAZNA_IMENA:
        for var in _mutacije(baza):
            ukupno += 1
            sc = _fuzzy_score(baza, var)
            if sc < CONFLICT_WARN:
                propusteni.append((baza, var, sc))
    assert ukupno == 294, f"korpus vise nije onaj na kome je prag kalibrisan: {ukupno}"
    assert not propusteni, (
        f"{len(propusteni)}/{ukupno} tipfelera sakriva sukob (prag prenizak/previsok): "
        f"{propusteni[:5]}")


def test_transpozicija_ne_sme_da_upari_razlicita_prezimena():
    """Pravilo transpozicije mora ostati usko — ne sme da postane anagram."""
    from routers.conflict_check import _transponovano
    assert _transponovano("ilic", "iilc") is True
    assert _transponovano("alfa", "afla") is True
    assert _transponovano("maric", "ramic") is False, "nesusedna zamena — različita prezimena"
    assert _transponovano("ilic", "clii") is False, "anagram nije tipfeler"
    assert _transponovano("ilic", "ilic") is False


def test_kriticni_put_ne_sme_zavisiti_od_opcione_zavisnosti():
    """PRG-P1-002 katanac.

    `rapidfuzz` je bio uvezen kroz `try/except ImportError`, pa je isti ulaz
    davao "conflict" tamo gde je paket instaliran i "clear" tamo gde nije.
    Verdikt o sukobu interesa ne sme zavisiti od toga šta je zateknuto u
    okruženju, pa modul više ne sme da referencira taj paket.
    """
    import io as _io
    import os as _os
    izvor = _io.open(_os.path.join(_os.path.dirname(__file__), "..", "routers",
                                   "conflict_check.py"), encoding="utf-8").read()
    assert "rapidfuzz" not in izvor.replace(
        "# PRG-P1-NIGHT-001: `rapidfuzz` je uklonjen iz ovog puta. Bio je uvezen kroz", ""), \
        "COI scoring ponovo zavisi od opcione zavisnosti"

    from routers.conflict_check import _FUZZY_ENGINE
    assert _FUZZY_ENGINE == "token-difflib"


def test_zlatna_tabela_skorova():
    """Fiksne vrednosti — isti brojevi u svakom okruženju i svakoj verziji Pythona."""
    from routers.conflict_check import _fuzzy_score
    zlatno = {
        ("Sasvim drugačija firma", "Firma doo"):          33,
        ("Firma doo", "Druga firma doo"):                 50,
        ("Milan Jovanović", "Milica Jovanović"):          50,
        ("AB Komerc", "XY Komerc"):                       50,
        ("Delta Inženjering doo", "Alfa Trgovina doo"):    0,
        ("Petrović Petar", "Petar Petrović"):            100,
        ("Delta Inženjering", "Delta Inženjering Beograd"): 100,
    }
    dobijeno = {k: _fuzzy_score(*k) for k in zlatno}
    assert dobijeno == zlatno, f"odstupanje: {dict(set(dobijeno.items()) - set(zlatno.items()))}"


def test_skor_je_simetrican_nad_sirokim_korpusom():
    """Redosled upisa stranaka ne sme da menja verdikt.

    Poholepno uparivanje tokena nije samo po sebi simetrično. Pretragom je
    nađeno da razlika ume da PREĐE granicu opsega — sintetički par
    ['bcacc','bcc'] / ['bcac','bcacc'] daje 92 u jednom smeru i 44 u drugom,
    dakle "conflict" naspram "clear" zavisno od toga ko je prvi upisan. Zato
    `_fuzzy_score` računa oba smera; ovaj test je katanac na to.
    """
    import itertools
    import random
    from routers.conflict_check import _fuzzy_score

    r = random.Random(20260819)
    tokeni = ["".join(p) for n in (3, 4, 5) for p in itertools.product("abc", repeat=n)]
    korpus = []
    for _ in range(4000):
        n = r.choice([2, 2, 2, 3])
        korpus.append((" ".join(r.sample(tokeni, n)), " ".join(r.sample(tokeni, n))))
    korpus += [(a, b) for a, b, _ in SVE]
    korpus += [("bcacc bcc", "bcac bcacc"), ("aac abaca", "abac abca")]

    asimetricni = [(a, b, _fuzzy_score(a, b), _fuzzy_score(b, a))
                   for a, b in korpus if _fuzzy_score(a, b) != _fuzzy_score(b, a)]
    assert not asimetricni, (
        f"{len(asimetricni)}/{len(korpus)} parova daje različit skor po smeru: "
        f"{asimetricni[:5]}")
