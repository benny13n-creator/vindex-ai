# -*- coding: utf-8 -*-
"""
Kontaminacija Strategic Orchestrator promptova konkretnim propisima.

ODAKLE JE DOŠAO ZUP

Prvi stvarni PRO run (TEST-3F) vratio je „čl. 42 ZUP, Sl. gl. RS 18/2016" kao
formalni nedostatak u PRIVREDNOM SPORU dva d.o.o., gde se Zakon o opštem
upravnom postupku uopšte ne primenjuje. Navod se ponovio u tri modula.

Uzrok NIJE bila halucinacija modela. Prompt je doslovno sadržao propis kao
„primer formata", uz instrukciju da to nije halucinacija nego stručnost. Model
je prepisao primer i preneo ga u pogrešnu granu prava.

DVA STRUKTURNA UZROKA (zabeleženo, nije popravljeno ovim testom)

1. Orkestrator nema `tip_postupka` — za razliku od `_RED_TEAM_*` promptova koji
   se biraju po grani prava (`strategija.py:116-122`). Nema pojma o grani, pa
   nema šta da ga zaustavi da upravni propis primeni na privredni spor.
2. Nigde u repou ne postoji provera da citiran član stvarno postoji.
   `main.py::_proveri_halucinaciju` nije primenljiva: orkestrator nema
   `pinecone_context` (guard rano izlazi), a njen regex `[ČčCc]lan\\s+(\\d+)`
   ne hvata oblik `čl. 205` koji promptovi izričito nalažu.

ZAŠTO JE STARI DETEKTOR ZAMENJEN

Prethodna verzija je koristila listu skraćenica: `("ZUP", "Sl. gl. RS", "ZPP",
'ZR"')`. Dve dokazane rupe:

  - Token `'ZR"'` traži ZR + navodnik. `ZR čl. 195` (ZR + razmak) prolazi.
    Zbog toga je `test_e` LAŽNO PROLAZIO nad `_ORK_SYNTHESIS_SYSTEM`, koji je
    baš taj niz sadržao — regresioni pojas je propuštao ono što štiti.
  - `ZOO` je najčešća skraćenica u fajlu (6 pojava) i uopšte nije bila u listi.
    Ni `ZKP`, `ZUS`, `ZUSP`, `ZOSL`, `ZPD`, `KZ`.

Lista skraćenica je principijelno nedovršiva. Razlika između zaštite i
kontaminacije nije u IMENU zakona nego u KONKRETNOM BROJU: `čl. X ZOO
(proveriti st.)` je placeholder i sme da ostane; `čl. 454 ZOO` je primer koji
model prepisuje. Zato detektor traži cifru.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import strategija  # noqa: E402

# Konkretan propis = referenca sa BROJEM. Placeholder bez broja prolazi namerno.
KONKRETAN_PROPIS = re.compile(
    r"(?:"
    r"[čČ]l\.\s*\d+"                              # čl. 195 / Čl.195
    r"|[čČ]lan(?:a|u|om)?\s+\d+"                  # član 195 / članu 53
    r"|Sl\.\s*gl\.\s*RS\s*\d+/\d+"                # Sl. gl. RS 18/2016
    r"|Službenom?\s+glasnik\w*\s+RS\s*\d+/\d+"
    r")"
)

# Svih šest orkestratorskih promptova. Orkestrator NEMA `tip_postupka`, pa
# nijedan od njih ne sme nositi konkretan propis — svaki radi na svakoj grani.
ORK_PROMPTOVI = (
    "_ORK_REVIZOR_SYSTEM",
    "_ORK_DUE_DILIGENCE_SYSTEM",
    "_ORK_WITNESS_SYSTEM",
    "_ORK_RED_TEAM_SYSTEM",
    "_ORK_PRESUDA_SYSTEM",
    "_ORK_SYNTHESIS_SYSTEM",
)

# Promptovi koje orkestrator koristi ali nisu `_ORK_*` — lako se previde.
ORK_KORISTI_JOS = ("_JUDGE_V2_TUZILAC", "_JUDGE_V2_BRANILAC")

# Anti-halucinaciona zaštita mora preživeti čišćenje. Presuda je dobila
# `ANTI-HALUCINACIJA` blok tek sada — ranije ga uopšte nije imala (`:556` je
# glasilo samo „OBAVEZNA PRAVILA"), što je bila stvarna rupa, ne test-artefakt.
SA_ANTI_HALUCINACIJOM = (
    "_ORK_REVIZOR_SYSTEM",
    "_ORK_DUE_DILIGENCE_SYSTEM",
    "_ORK_RED_TEAM_SYSTEM",
    "_ORK_PRESUDA_SYSTEM",
)


def _prompt(name: str) -> str:
    p = getattr(strategija, name, None)
    assert isinstance(p, str) and p, f"{name} ne postoji ili nije string"
    return p


# ─── 1. NIJEDAN ORK PROMPT NE NOSI KONKRETAN PROPIS ─────────────────────────

@pytest.mark.parametrize("name", ORK_PROMPTOVI + ORK_KORISTI_JOS)
def test_a_nema_konkretnog_propisa_kao_primera(name):
    """Trajna invarijanta.

    Orkestrator radi na svakoj grani prava i ne zna na kojoj je. Svaki
    konkretan propis u njegovom promptu je kandidat da bude prepisan u pogrešnu
    granu — što se i dogodilo u TEST-3F.
    """
    p = _prompt(name)
    nadjeno = sorted(set(KONKRETAN_PROPIS.findall(p)))
    assert not nadjeno, (
        f"{name} sadrži konkretan propis {nadjeno} — model takav primer "
        f"prepisuje u izlaz, i to je proizvelo ZUP u privrednom sporu (TEST-3F)"
    )


@pytest.mark.parametrize("name", ORK_PROMPTOVI)
def test_b_nema_ohrabrivanja_citiranja_po_secanju(name):
    """Formulacija koja citiranje po sećanju proglašava stručnošću.

    Prethodna verzija je tražila tačan niz „nije halucinacija". Ali
    `_ORK_DUE_DILIGENCE_SYSTEM` je glasio „To je tvoja stručnost, NE
    halucinacija" — drugačiji red reči, isto značenje, test bi ga propustio.
    Zato se sada traži koren reči.
    """
    p = _prompt(name).lower()
    assert "halucinacij" not in p or "anti-halucinacij" in p or "zabranjeno" in p, (
        f"{name} pominje halucinaciju van zabranjujućeg konteksta"
    )
    assert not re.search(r"(ne|nije)\s+halucinacij", p), (
        f"{name} modelu poručuje da je citiranje po sećanju stručnost"
    )


# ─── 2. ZAŠTITA JE SAČUVANA ─────────────────────────────────────────────────

@pytest.mark.parametrize("name", SA_ANTI_HALUCINACIJOM)
def test_c_anti_halucinaciono_pravilo_ostaje(name):
    """Brisanje primera ne sme oslabiti zabranu izmišljanja.

    Ovo je test koji sprečava da se „očisti" prompt tako što se obriše i
    zaštita zajedno sa primerom.
    """
    p = _prompt(name)
    assert "ANTI-HALUCINACIJA" in p, f"{name} je izgubio anti-halucinacioni blok"
    assert re.search(r"ZABRANJENO je izmišljati", p), f"{name} više ne zabranjuje izmišljanje"
    assert "proveriti" in p.lower(), (
        f"{name} više ne traži da se nesigurna referenca označi kao 'proveriti'"
    )
    assert "relevantn" in p.lower(), (
        f"{name} više ne traži da propis bude relevantan za konkretan predmet"
    )


# ─── 3. GRANSKI RUTIRANI PROMPTOVI SU NAMERNO IZVAN OBIMA ───────────────────

@pytest.mark.parametrize("name", [
    "_RED_TEAM_PRIVREDNO_SYSTEM",
    "_RED_TEAM_RADNO_SYSTEM",
])
def test_d_granski_promptovi_smeju_imati_svoj_propis(name):
    """Zašto ovi NISU kontaminacija — i zašto ih ne treba „usput" očistiti.

    `_RED_TEAM_PROMPTS` (`strategija.py:116-122`) bira prompt po
    `tip_postupka`. `ZOO čl. 374` u privrednom promptu ne može procuriti u
    upravni spor, jer se taj prompt na upravni spor nikad ne primeni. To je
    grounding vezan za granu, ne ilustracija formata.

    Test je namerno POZITIVAN: tvrdi da propis JESTE tu. Ako ga neko obriše
    misleći da čisti kontaminaciju, ovo pada i tera ga da pročita razlog.
    Suprotno od `test_a` — i to je razlika između orkestratora (bez grane) i
    ovih (sa granom).
    """
    p = _prompt(name)
    assert KONKRETAN_PROPIS.search(p), (
        f"{name} je izgubio granski propis. Ovi promptovi se biraju po "
        f"`tip_postupka` (strategija.py:116-122), pa im konkretan propis JESTE "
        f"grounding, ne kontaminacija. Ako je uklanjanje bilo namerno, prepiši "
        f"i ovaj test uz obrazloženje."
    )


# ─── 4. NEGATIVNA KONTROLA DETEKTORA ────────────────────────────────────────

@pytest.mark.parametrize("tekst", [
    "čl. 195 ZR", "ZR čl. 195", "čl. 9 st. 1 ZUP", "Sl. gl. RS 18/2016",
    "čl. 454 ZOO", "čl. 18 st. 1 ZUSP", "npr. čl. 205 ZUP ili čl. 454 ZOO",
    "ZPP čl. 3, ZKP čl. 83", "ZR čl. 179-184", "član 195 Zakona o radu",
])
def test_ng_detektor_hvata_konkretan_propis(tekst):
    """Bez ovoga bi `test_a` prolazio i da regex ne hvata ništa."""
    assert KONKRETAN_PROPIS.search(tekst), f"detektor propušta: {tekst!r}"


@pytest.mark.parametrize("tekst", [
    "čl. X ZUP (proveriti st.)",
    "čl. X ZOO (proveriti st.)",
    "zakonski osnov",
    "relevantan propis",
    "konkretan član propisa relevantnog za ovaj predmet, ili prazno ako nije poznat",
    "Ako nisi siguran u tačan broj člana ili stava, jasno označi da referencu treba proveriti",
    "ZABRANJENO je izmišljati brojeve sudskih presuda",
    "koji zakoni i članovi se primenjuju",
    "(ZUP, ZUS, posebni zakoni)",
])
def test_ng_detektor_ne_hvata_opste_pravilo(tekst):
    """Detektor koji laže je gori od nikakvog.

    Ako ovo padne, regex je preširok i počeo bi da obara zaštitu umesto
    kontaminacije — a onda bi ga neko oslabio da bi CI bio zelen.
    """
    assert not KONKRETAN_PROPIS.search(tekst), f"detektor lažno optužuje: {tekst!r}"


def test_ng_stari_detektor_bi_propustio_synthesis():
    """Dokaz da zamena liste tokena regexom nije kozmetika.

    Reprodukuje se stara lista i pokazuje da bi `_ORK_SYNTHESIS_SYSTEM` sa
    `ZR čl. 195` prošao kao čist — što je i bio slučaj do ovog commita.
    """
    stari_tokeni = ("ZUP", "Sl. gl. RS", "ZPP", 'ZR"')
    kontaminiran = "3. Rok za tužbu (npr. 60 dana za radne sporove — ZR čl. 195) ide u hitno_crveno."

    assert not [t for t in stari_tokeni if t in kontaminiran], (
        "stara lista je trebalo da PROPUSTI ovaj niz — u tome je i bila rupa"
    )
    assert KONKRETAN_PROPIS.search(kontaminiran), "novi detektor mora da ga uhvati"
