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
