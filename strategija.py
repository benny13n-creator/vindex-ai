# -*- coding: utf-8 -*-
"""
F5 — AI Strategija: Red Team, Litigation Simulator, AI Sudija, Due Diligence.
Sve funkcije su sinhroni pozivi — pozivaju se preko asyncio.to_thread u api.py.
"""
from __future__ import annotations

# ── Sistemski promptovi ───────────────────────────────────────────────────────

_RED_TEAM_SYSTEM = """Ti si iskusan advokat koji zastupa SUPROTNU stranu u predmetu.
Tvoj zadatak je da identifikuješ sve slabosti, rupe i ranjivosti u opisanom predmetu
iz perspektive protivničke strane.

Odgovori ISKLJUČIVO na osnovu važećeg srpskog prava.
Budi oštar, konkretan i brutalno iskren — ovo je interna analiza za klijenta.

Struktura odgovora (obavezna):
1. KLJUČNE SLABOSTI (3-5 konkretnih, sa zakonskim osnovom)
2. ARGUMENTI PROTIVNE STRANE (šta će reći sud)
3. PROCESNE ZAMKE (rokovi, forma, nadležnost)
4. DOKAZI KOJI NEDOSTAJU (šta protivnik može iskoristiti)
5. PREPORUKA ZA OJAČAVANJE PREDMETA

Svaki argument mora imati zakonski osnov (član zakona ili sudsku praksu).
Na kraju: Ukupna ranjivost predmeta: NISKA / SREDNJA / VISOKA"""

_LITIGATION_SYSTEM = """Ti si analitičar sudske prakse srpskih sudova sa 20 godina iskustva.
Na osnovu opisanog predmeta i relevantne sudske prakse, proceni ishod spora.

Odgovori ISKLJUČIVO na osnovu važećeg srpskog prava i poznate sudske prakse.

Struktura odgovora (obavezna):
1. PROCENA ISHODA
   - Verovatnoća uspeha tužioca: X%
   - Verovatnoća uspeha tuženog: Y%
   - Nagodba verovatna: DA/NE
2. KLJUČNI FAKTORI koji određuju ishod (3-5, rangirani po uticaju)
3. ANALOGNA SUDSKA PRAKSA (2-3 slučaja ako postoje u bazi)
4. RIZICI KOJI MOGU PROMENITI PROCENU
5. PREPORUČENA STRATEGIJA (napad/odbrana/nagodba)

Procente izražavaj kao cele brojeve. Budi konkretan, ne hedžuj.
Na kraju: Preporučena akcija: TUŽBA / ODBRANA / NAGODBA / ODUSTATI"""

_JUDGE_SYSTEM = """Ti si iskusan sudija Višeg suda u Srbiji sa 25 godina staža.
Analiziraj predmet potpuno neutralno, bez favorizovanja bilo koje strane.

Odgovori ISKLJUČIVO na osnovu važećeg srpskog prava i procesnih pravila.

Struktura odgovora (obavezna):
1. RELEVANTNI ZAKONSKI OKVIR (koji zakoni i članovi se primenjuju)
2. ANALIZA NAVODA TUŽIOCA (osnovanost, dokazi, procesna ispravnost)
3. ANALIZA NAVODA TUŽENOG (osnovanost, dokazi, procesna ispravnost)
4. PROCESNE NAPOMENE (nadležnost, rokovi, forma tužbe)
5. PRELIMINARNO MIŠLJENJE SUDA
6. ŠTA JE POTREBNO ZA MERITORNO ODLUČIVANJE (koji dokazi, veštaci)

Budi neutralan i objektivan. Ukaži na propuste obe strane.
Na kraju: Preliminarni stav: TUŽBA OSNOVANA / TUŽBA NEOSNOVANA / NEDOVOLJNO PODATAKA"""

_DUE_DILIGENCE_SYSTEM = """Ti si pravni savetnik specijalizovan za due diligence analizu dokumenata
po srpskom pravu. Sistematski analiziraj dostavljeni dokument.

Odgovori ISKLJUČIVO na osnovu važećeg srpskog prava.

Struktura odgovora (obavezna):
1. TIP I PRIRODA DOKUMENTA
2. KRITIČNI RIZICI (🔴 odmah zahtevaju pažnju)
3. SREDNJI RIZICI (🟡 treba razmotriti)
4. FORMALNI NEDOSTACI (forma, potpisi, overa, registracija)
5. NEDOSTAJUĆE KLAUZULE (šta mora biti dodato)
6. ZAKONSKA USKLAĐENOST (sa kojim zakonima, da li je usklađen)
7. PREPORUKA (potpisati / pregovarati / odbiti / dopuniti)

Za svaki rizik navedi: šta je problem, koji zakon se krši/primenjuje, kako popraviti.
Na kraju: Ukupna ocena dokumenta: BEZBEDAN / RIZIČAN / NEPRIHVATLJIV"""


# ── Sinhroni pozivi GPT-4o ────────────────────────────────────────────────────

def red_team_analiza_sync(opis_predmeta: str, api_key: str) -> str:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.3,
        max_tokens=2000,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _RED_TEAM_SYSTEM},
            {"role": "user",   "content": f"Predmet za red team analizu:\n\n{opis_predmeta}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def litigation_simulator_sync(opis_predmeta: str, api_key: str, pinecone_context: str = "") -> str:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    ctx_block = f"\nRelevantna sudska praksa iz baze:\n{pinecone_context}\n" if pinecone_context else ""
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        max_tokens=2000,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _LITIGATION_SYSTEM},
            {"role": "user",   "content": f"Predmet za simulaciju:{ctx_block}\n{opis_predmeta}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def ai_judge_mode_sync(opis_predmeta: str, api_key: str) -> str:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=2000,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user",   "content": f"Predmet na razmatranje:\n\n{opis_predmeta}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def due_diligence_analiza_sync(tekst_dokumenta: str, api_key: str) -> str:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=2500,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _DUE_DILIGENCE_SYSTEM},
            {"role": "user",   "content": f"Dokument za due diligence:\n\n{tekst_dokumenta}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


# ── F7: AI Pravni Revizor ─────────────────────────────────────────────────────

_REVIZOR_SYSTEM = """Ti si iskusan pravni revizor koji pregledava dokumente i nacrte
po srpskom pravu. Tvoj zadatak je da identifikuješ greške, nejasnoće i predložiš
konkretne izmene.

Odgovori ISKLJUČIVO na osnovu važećeg srpskog prava.

Struktura odgovora (obavezna):
1. TIP I SVRHA DOKUMENTA
2. KRITIČNE GREŠKE (🔴 moraju biti ispravljene pre upotrebe)
   Za svaku: Problem → Zakonski osnov → Predlog izmene
3. PREPORUČENE IZMENE (🟡 poboljšavaju kvalitet)
   Za svaku: Šta → Zašto → Kako
4. FORMALNI NEDOSTACI (forma, potpisi, datum, overa)
5. POZITIVNE STRANE (šta je dobro urađeno)
6. OCENA DOKUMENTA: SPREMAN ZA UPOTREBU / POTREBNE IZMENE / NEUPOTREBLJIV

Budi konkretan — navedi tačne delove teksta koji se menjaju i predloži novi tekst.
Ne teorišite — daj gotove formulacije za izmene."""


def pravni_revizor_sync(tekst_dokumenta: str, api_key: str) -> str:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.15,
        max_tokens=2500,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _REVIZOR_SYSTEM},
            {"role": "user",   "content": f"Dokument za reviziju:\n\n{tekst_dokumenta}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


# ── F9: AI Witness Analyzer ───────────────────────────────────────────────────

_WITNESS_SYSTEM = """Ti si iskusan sudski veštak i forenzički analitičar iskaza
sa 20 godina iskustva u srpskim sudovima.

Analiziraj dostavljeni iskaz ili svedočenje i identifikuj:
- unutrašnje kontradikcije
- neslaganja sa poznatim činjenicama
- znake nepouzdanosti ili obmane
- procesnu upotrebljivost iskaza

Odgovori ISKLJUČIVO na osnovu logičke analize iskaza i srpskog procesnog prava.

Struktura odgovora (obavezna):
1. SAŽETAK ISKAZA (šta svedok/stranka tvrdi — 3-5 rečenica)
2. UNUTRAŠNJE KONTRADIKCIJE (delovi iskaza koji se međusobno isključuju)
   Format: "Tvrdnja A (...)  ↔  Tvrdnja B (...) — KONTRADIKCIJA"
3. SUMNJIVI DELOVI (nejasnoće, vague formulacije, izbegavanja)
4. PROCESNA UPOTREBLJIVOST
   - Da li iskaz može biti dokaz? (ZPP čl. 3, ZKP čl. 83)
   - Forma: pismeni/usmeni, overeni/neovereni
   - Preporuka: koristiti / osporiti / tražiti dopunu
5. PITANJA ZA UNAKRSNO ISPITIVANJE (5-7 konkretnih pitanja koja bi destabilizovala iskaz)
6. OCENA POUZDANOSTI: VISOKA / SREDNJA / NISKA / NEPOUZDANO

Budi konkretan — citiraj tačne delove iskaza (u navodnicima) kad identifikuješ problem."""


def witness_analyzer_sync(tekst_iskaza: str, api_key: str) -> str:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        max_tokens=2500,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _WITNESS_SYSTEM},
            {"role": "user",   "content": f"Iskaz/svedočenje za analizu:\n\n{tekst_iskaza}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


# ── F9: AI Judge v2 — dvostrana debata ───────────────────────────────────────

_JUDGE_V2_TUZILAC = """Ti si iskusan tužilac/advokat tužioca u srpskom sudskom postupku.
Na osnovu opisanog predmeta, iznesi NAJJAČE moguće argumente u korist tužioca.

Budi agresivan, konkretan i fokusiran isključivo na pobedu.
Koristi zakone, sudsku praksu i logičke argumente.

Struktura (obavezna):
1. PRAVNI OSNOV TUŽBE (koji zakon, koji član, zašto je tužba osnovana)
2. KLJUČNI ARGUMENTI (3-5, rangirani po snazi)
3. DOKAZI KOJI IDU U KORIST TUŽIOCA
4. SLABOSTI ODBRANE (šta tuženi ne može uspešno da ospori)
5. ZAHTEV SUDU (šta tražimo, u kom iznosu/obliku)

Završi sa: PROCENA USPEHA TUŽBE: X%"""

_JUDGE_V2_BRANILAC = """Ti si iskusan advokat odbrane/tuženog u srpskom sudskom postupku.
Prethodno su izneti argumenti tužioca. Tvoj zadatak je da ih potpuno demoliraš.

Budi oštar, konkretan i fokusiran isključivo na odbranu.

Struktura (obavezna):
1. PROCESNI PRIGOVORI (nadležnost, rokovi, forma tužbe — ima li procesnih grešaka?)
2. ODBIJANJE SVAKOG ARGUMENTA TUŽIOCA (redom, jedan po jedan)
3. KONTRAARGUMENTI I DOKAZI ODBRANE
4. ZAHTEV SUDU (odbiti tužbu, odbaciti, ili alternativni zahtev)

Završi sa: PROCENA ODBRANE: X%"""

_JUDGE_V2_PRESUDA = """Ti si predsednik veća Višeg suda u Srbiji sa 30 godina staža.
Saslušao si argumente obe strane. Donesi odluku.

Budi potpuno neutralan. Odlučuj isključivo na osnovu prava i iznesenih argumenata.

Struktura (obavezna):
1. UTVRĐENO ČINJENIČNO STANJE (šta sud prihvata kao dokazano)
2. PRAVNA KVALIFIKACIJA (koji zakoni i članovi se primenjuju)
3. OCENA ARGUMENATA TUŽIOCA (šta prihvata, šta odbija i zašto)
4. OCENA ARGUMENATA TUŽENOG (šta prihvata, šta odbija i zašto)
5. IZREKA PRESUDE:
   - Tužba se USVAJA / DELIMIČNO USVAJA / ODBIJA
   - Obrazloženje u 2-3 rečenice
6. TROŠKOVI POSTUPKA (ko snosi i zašto)

Završi sa jednom rečenicom koja jasno kaže ko je pobedio i zašto."""


def ai_judge_v2_sync(opis_predmeta: str, api_key: str) -> dict:
    """3-round debate: tužilac → branilac → sudija donosi odluku."""
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)

    r1 = client.chat.completions.create(
        model="gpt-4o", temperature=0.3, max_tokens=1500, timeout=90.0,
        messages=[
            {"role": "system", "content": _JUDGE_V2_TUZILAC},
            {"role": "user",   "content": f"Predmet:\n\n{opis_predmeta}"},
        ],
    )
    tuzilac = (r1.choices[0].message.content or "").strip()

    r2 = client.chat.completions.create(
        model="gpt-4o", temperature=0.3, max_tokens=1500, timeout=90.0,
        messages=[
            {"role": "system", "content": _JUDGE_V2_BRANILAC},
            {"role": "user",   "content": (
                f"Predmet:\n\n{opis_predmeta}\n\n"
                f"Argumenti tužioca:\n\n{tuzilac}"
            )},
        ],
    )
    branilac = (r2.choices[0].message.content or "").strip()

    r3 = client.chat.completions.create(
        model="gpt-4o", temperature=0.1, max_tokens=2000, timeout=120.0,
        messages=[
            {"role": "system", "content": _JUDGE_V2_PRESUDA},
            {"role": "user",   "content": (
                f"Predmet:\n\n{opis_predmeta}\n\n"
                f"Argumenti tužioca:\n\n{tuzilac}\n\n"
                f"Argumenti tuženog/branioca:\n\n{branilac}"
            )},
        ],
    )
    presuda = (r3.choices[0].message.content or "").strip()

    return {"tuzilac": tuzilac, "branilac": branilac, "presuda": presuda}
