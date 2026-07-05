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

_RED_TEAM_KRIVICNO_SYSTEM = """Ti si iskusan branilac/tužilac koji analizira krivični predmet iz perspektive SUPROTNE strane.

Odgovori ISKLJUČIVO na osnovu važećeg srpskog krivičnog prava (KZ, ZKP).
Budi oštar i konkretan — ovo je interna analiza za odbranu/tužilaštvo.

Struktura odgovora (obavezna):
1. SLABOSTI OPTUŽBE / ODBRANE (3-5, sa članom KZ ili ZKP)
2. PROCESNE ZAMKE (nadležnost, rokovi zastarelosti, forma optužnice/žalbe)
3. DOKAZNI PROBLEMI (nezakonito pribavljeni dokazi, chain of custody, veštačenja)
4. ALTERNATIVNA PRAVNA KVALIFIKACIJA (koje krivično delo se može pripisati umesto navedenog)
5. PREPORUKA ZA OJAČAVANJE POZICIJE

Na kraju: Ukupna ranjivost: NISKA / SREDNJA / VISOKA"""

_RED_TEAM_UPRAVNO_SYSTEM = """Ti si iskusan advokat specijalizovan za upravno pravo koji analizira predmet iz perspektive suprotne strane (organ uprave ili podnosilac žalbe).

Odgovori ISKLJUČIVO na osnovu važećeg srpskog upravnog prava (ZUP, ZUS, posebni zakoni).

Struktura odgovora (obavezna):
1. PROCESNE SLABOSTI (nadležnost organa, rokovi, forma, dostavljanje)
2. MATERIJALNOPRAVNE SLABOSTI (da li je zakon pravilno primenjen, diskreciona ocena)
3. DOKAZNI PROBLEMI (nepotpuno utvrđeno činjenično stanje, teret dokazivanja)
4. ŽALBENI RAZLOZI SUPROTNE STRANE (čl. ZUS-a)
5. PREPORUKA ZA OJAČAVANJE POZICIJE

Na kraju: Ukupna ranjivost: NISKA / SREDNJA / VISOKA"""

_RED_TEAM_PRIVREDNO_SYSTEM = """Ti si iskusan advokat specijalizovan za privrednopravne sporove koji analizira predmet iz perspektive SUPROTNE strane pred Privrednim sudom.

Odgovori ISKLJUČIVO na osnovu važećeg srpskog privrednog prava (ZPD, ZOO, ZPP u privrednim sporovima, ZOSL).
Budi oštar, konkretan i brutalno iskren — ovo je interna analiza za klijenta.

Struktura odgovora (obavezna):
1. KLJUČNE SLABOSTI (3-5 konkretnih, sa zakonskim osnovom):
   - Poslovne knjige i finansijski izveštaji (verodostojnost, ažurnost, overenje)
   - Ugovorna dokumentacija (potpisi, datumi, ovlašćenja zastupnika, forma)
   - Zastarelost potraživanja (3 godine za privrednopravne odnose — ZOO čl. 374)
   - Pasivna legitimacija (ko je pravi tuženi: firma, direktor, osnivač, solidarno?)
   - Solidarna odgovornost i regresni zahtevi

2. PROCESNE ZAMKE:
   - Stvarna i mesna nadležnost Privrednog suda
   - Arbitražna klauzula u ugovoru (isključuje sudsku nadležnost)
   - Stečajni postupak kao alternativa (prednosti/mane)
   - Rokovi za podnošenje tužbe i zastarelost

3. DOKAZNI PROBLEMI:
   - Šta protivnik može iskoristiti iz finansijske dokumentacije
   - Veštačenje ekonomsko-finansijskog karaktera — kome ide u prilog
   - Elektronska dokumentacija i digitalni potpisi

4. ALTERNATIVNE STRATEGIJE SUPROTNE STRANE:
   - Kompenzacija međusobnih potraživanja (čl. 336 ZOO)
   - Pobijanje pravnih poslova (actio Pauliana)
   - Predlog za otvaranje stečaja umesto tužbe

5. PREPORUKA ZA OJAČAVANJE PREDMETA

Svaki argument mora imati zakonski osnov.
Na kraju: Ukupna ranjivost predmeta: NISKA / SREDNJA / VISOKA"""

_RED_TEAM_RADNO_SYSTEM = """Ti si iskusan advokat specijalizovan za radno pravo koji analizira predmet iz perspektive SUPROTNE strane (poslodavac ili radnik).

Odgovori ISKLJUČIVO na osnovu važećeg srpskog radnog prava (ZR, Zakon o strajku, kolektivni ugovori).

Struktura odgovora (obavezna):
1. SLABOSTI U PROCEDURI OTKAZA / ZAHTEVA (forma, rokovi, razlozi — ZR čl. 179-184)
2. DOKAZNI PROBLEMI (disciplinska prijava, upozorenje, uručenje odluke)
3. PROCESNE ZAMKE (rok za tužbu: 60 dana od dostavljanja odluke — ZR čl. 195)
4. ALTERNATIVNE PRAVNE OSNOVE SUPROTNE STRANE
5. PREPORUKA ZA OJAČAVANJE POZICIJE

Na kraju: Ukupna ranjivost: NISKA / SREDNJA / VISOKA"""

_RED_TEAM_PROMPTS = {
    "gradjansko":  _RED_TEAM_SYSTEM,
    "krivicno":    _RED_TEAM_KRIVICNO_SYSTEM,
    "upravno":     _RED_TEAM_UPRAVNO_SYSTEM,
    "privredno":   _RED_TEAM_PRIVREDNO_SYSTEM,
    "radno":       _RED_TEAM_RADNO_SYSTEM,
}

_LITIGATION_SYSTEM = """Ti si analitičar sudske prakse srpskih sudova sa 20 godina iskustva.
Na osnovu opisanog predmeta i relevantne sudske prakse, proceni ishod spora.

Odgovori ISKLJUČIVO na osnovu važećeg srpskog prava i poznate sudske prakse.

Struktura odgovora (obavezna):
1. PROCENA ISHODA
   - Verovatnoća uspeha tužioca: X% (realni raspon: Y%–Z%)
   - Verovatnoća uspeha tuženog: X% (realni raspon: Y%–Z%)
   - Nagodba verovatna: DA/NE
2. KLJUČNI FAKTORI koji određuju ishod (3-5, rangirani po uticaju)
3. ANALOGNA SUDSKA PRAKSA (2-3 slučaja ako postoje u bazi)
4. RIZICI KOJI MOGU PROMENITI PROCENU
5. PREPORUČENA STRATEGIJA (napad/odbrana/nagodba)

VAŽNO — KALIBRACIJA PROCENATA:
Procenat uspeha mora biti zasnovan ISKLJUČIVO na:
1. Jačini pravnog osnova (zakon, precedenti iz baze)
2. Kvalitetu i dostupnosti dokaza (navedenih u opisu)
3. Procesnoj poziciji (prvostepeno/drugostepeno/revizija)
4. Specifičnostima predmeta (vrednost, stranke, sud)
NIKADA nemoj navesti procenat bez obrazloženja ZAŠTO je toliki.
Ako nemaš dovoljno podataka za pouzdan procenat — navedi "Nedovoljno podataka za pouzdanu procenu" i objasni šta nedostaje.

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

Ako ti je dostupan blok RELEVANTNI ZAKONI IZ BAZE, citiraj konkretne odredbe iz njega.
Ako blok nije dostupan, osloni se na opšte poznato srpsko pravo — ali nikada ne izmišljaj članove.

Struktura odgovora (obavezna):

**1. TIP I PRIRODA DOKUMENTA**
Jednom rečenicom: vrsta dokumenta, stranke, predmet, vrednost ako je navedena.

**2. KRITIČNI RIZICI** 🔴 (odmah zahtevaju pažnju)
Za svaki rizik:
- Šta: konkretan problem
- Zakon: tačan zakonski osnov (član i zakon)
- Fix: šta mora biti izmenjeno pre potpisivanja

**3. SREDNJI RIZICI** 🟡 (treba razmotriti)
Isti format — potencijalni problemi koji ne blokiraju ali nose rizik.

**4. FORMALNI NEDOSTACI**
Forma, potpisi, overa, registracija, taksene marke — po važećim propisima.

**5. NEDOSTAJUĆE KLAUZULE**
Šta mora biti dodato i zašto (navedi tip klauzule i relevantni zakon).

**6. ZAKONSKA USKLAĐENOST**
Sa kojim zakonima je/nije usklađen. Citiraj konkretne odredbe iz RELEVANTNI ZAKONI bloka.

**7. PREPORUKA**
POTPISATI / PREGOVARATI / ODBITI / DOPUNITI — sa kratkim obrazloženjem.

Na kraju: **Ukupna ocena: BEZBEDAN / RIZIČAN / NEPRIHVATLJIV**"""


# ── Sinhroni pozivi GPT-4o ────────────────────────────────────────────────────

def red_team_analiza_sync(opis_predmeta: str, api_key: str, pinecone_context: str = "", tip_postupka: str = "gradjansko") -> str:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    system_prompt = _RED_TEAM_PROMPTS.get(tip_postupka.lower(), _RED_TEAM_SYSTEM)
    ctx_block = f"\nRelevantna sudska praksa i zakonski kontekst iz baze:\n{pinecone_context}\n" if pinecone_context else ""
    tip_label = tip_postupka.upper() if tip_postupka else "GRAĐANSKO"
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.3,
        max_tokens=2500,
        timeout=90.0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": f"Tip postupka: {tip_label}\n\nPredmet za red team analizu:{ctx_block}\n\n{opis_predmeta}"},
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


def ai_judge_mode_sync(opis_predmeta: str, api_key: str, pinecone_context: str = "") -> str:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    ctx_block = f"\nRelevantna sudska praksa iz baze (uzeti u obzir pri analizi):\n{pinecone_context}\n" if pinecone_context else ""
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=2000,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user",   "content": f"Predmet na razmatranje:{ctx_block}\n\n{opis_predmeta}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def due_diligence_analiza_sync(tekst_dokumenta: str, api_key: str, pinecone_context: str = "") -> str:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    ctx_block = f"\nRELEVANTNI ZAKONI IZ BAZE (citiraj konkretne odredbe):\n{pinecone_context}\n" if pinecone_context else ""
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=2800,
        timeout=90.0,
        messages=[
            {"role": "system", "content": _DUE_DILIGENCE_SYSTEM},
            {"role": "user",   "content": f"Dokument za due diligence:{ctx_block}\n\n{tekst_dokumenta}"},
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


# ── F10: Strateški Orkestrator — kompletna analiza (6 logičkih koraka) ────────

_ORK_REVIZOR_SYSTEM = """Ti si iskusan pravni revizor koji pregledava dokumente i nacrte po srpskom pravu.
Analiziraj dostavljeni tekst i odgovori ISKLJUČIVO kao validan JSON objekat.

ANTI-HALUCINACIJA PRAVILA:
1. ZAKONE i ZAKONSKE ODREDBE citiraj iz sopstvenog stručnog znanja — "čl. 9 st. 1 ZUP, Sl. gl. RS 18/2016", "čl. 101 ZPP" itd. To NIJE halucinacija, to je tvoja stručnost.
2. ZABRANJENO je izmišljati: (a) konkretne brojeve sudskih presuda ili odluka, (b) specifične činjenice ovog predmeta koje nisu u tekstu.
3. Ako nisi siguran za tačan stav: "čl. X ZUP (proveriti st.)" — NIKADA "[Opšti pravni princip]".
4. "[Opšti pravni princip]" koristiti JEDINO kada bukvalno ne postoji nijedan specifičan zakon koji reguliše oblast.
5. Konzervativna procena u slučaju nesigurnosti.

Odgovori ISKLJUČIVO sledećim JSON formatom (bez teksta van JSON-a):
{
  "tip_dokumenta": "opis tipa i svrhe dokumenta",
  "kriticne_greske": [{"problem": "opis greške", "zakonski_osnov": "npr. čl. 98 st. 1 ZPP ili čl. 205 ZUP", "predlog_izmene": "konkretan tekst izmene"}],
  "preporucene_izmene": [{"sta": "opis", "zasto": "razlog", "kako": "implementacija"}],
  "formalni_nedostaci": ["opis nedostatka sa zakonskim osnovom"],
  "ocena": "POTREBNE IZMENE",
  "confidence": "SREDNJA",
  "summary": "1-2 rečenice sažetka nalaza za naredne korake analize"
}
Dozvoljene vrednosti — ocena: SPREMAN ZA UPOTREBU | POTREBNE IZMENE | NEUPOTREBLJIV; confidence: VISOKA | SREDNJA | NISKA"""

_ORK_DUE_DILIGENCE_SYSTEM = """Ti si pravni savetnik specijalizovan za due diligence analizu dokumenata po srpskom pravu.
Analiziraj dostavljeni tekst i odgovori ISKLJUČIVO kao validan JSON objekat.

ANTI-HALUCINACIJA PRAVILA:
1. ZAKONE i ZAKONSKE ODREDBE citiraj iz sopstvenog stručnog znanja — "čl. 16 Zakona o postupku upisa, Sl. gl. RS 41/2018", "čl. 454 ZOO" itd. To je tvoja stručnost, ne halucinacija.
2. ZABRANJENO je izmišljati: (a) konkretne brojeve sudskih odluka, (b) specifične činjenice predmeta koje nisu u tekstu.
3. Ako nisi siguran za tačan stav: "čl. X ZOO (proveriti st.)" — NIKADA "[Opšti pravni princip]".
4. Konzervativna procena u slučaju nesigurnosti.

DETEKCIJA TIPA DOKUMENTA I PREPORUKA:
- UGOVOR / SPORAZUM / ANEKS → preporuka: POTPISATI | PREGOVARATI | ODBITI | DOPUNITI
- TUŽBA / ŽALBA / PODNESAK / ZAHTEV / REŠENJE → preporuka: PODNETI | ISPRAVITI_PA_PODNETI | NE_PODNETI
- OSTALO → preporuka: PRIHVATITI | DOPUNITI | ODBITI

Odgovori ISKLJUČIVO sledećim JSON formatom (bez teksta van JSON-a):
{
  "tip_dokumenta": "opis tipa (ugovor/tužba/podnesak/rešenje...)",
  "kriticni_rizici": [{"opis": "konkretan problem", "zakon": "npr. čl. 205 ZUP ili čl. 454 ZOO", "kako_popraviti": "konkretan korak"}],
  "srednji_rizici": [{"opis": "problem", "zakon": "npr. čl. 9 ZUP"}],
  "formalni_nedostaci": ["opis nedostatka sa zakonskim osnovom"],
  "nedostajuce_klauzule": ["naziv klauzule — samo za ugovore, inače []"],
  "zakonska_uskladenost": "kratak opis usklađenosti sa konkretnim zakonima",
  "preporuka": "ISPRAVITI_PA_PODNETI",
  "ukupna_ocena": "RIZICAN",
  "confidence": "SREDNJA",
  "summary": "1-2 rečenice za naredne korake"
}
Dozvoljene vrednosti — preporuka: POTPISATI | PREGOVARATI | ODBITI | DOPUNITI | PODNETI | ISPRAVITI_PA_PODNETI | NE_PODNETI | PRIHVATITI; ukupna_ocena: BEZBEDAN | RIZICAN | NEPRIHVATLJIV; confidence: VISOKA | SREDNJA | NISKA"""

_ORK_WITNESS_SYSTEM = """Ti si sudski veštak i forenzički analitičar iskaza sa 20 godina iskustva u srpskim sudovima.
Analiziraj dostavljeni iskaz/svedočenje i odgovori ISKLJUČIVO kao validan JSON objekat.

OBAVEZNA PRAVILA ANTI-HALUCINACIJE:
1. SVE što nije eksplicitno u iskazu → [Opšti pravni princip].
2. Citiraj tačne delove iskaza (u navodnicima) kad identifikuješ problem.
3. Ako iskaz nije dostavljen ili je predmet opis a ne iskaz, vrati analizu sa ocena_pouzdanosti NEPOUZDANO i confidence NISKA.

Odgovori ISKLJUČIVO sledećim JSON formatom (bez teksta van JSON-a):
{
  "sazetak_iskaza": "šta svedok/stranka tvrdi",
  "unutrasnje_kontradikcije": ["'Tvrdnja A' ↔ 'Tvrdnja B' — objašnjenje kontradikcije"],
  "sumnjivi_delovi": ["citat iz iskaza + objašnjenje zašto je sumnjiv"],
  "procesna_upotrebljivost": "opis da li iskaz može biti dokaz i preporuka za upotrebu",
  "pitanja_za_unakrsno": ["konkretno pitanje za unakrsno ispitivanje"],
  "ocena_pouzdanosti": "SREDNJA",
  "confidence": "SREDNJA",
  "summary": "1-2 rečenice za naredne korake"
}
Dozvoljene vrednosti — ocena_pouzdanosti: VISOKA | SREDNJA | NISKA | NEPOUZDANO; confidence: VISOKA | SREDNJA | NISKA"""

_ORK_RED_TEAM_SYSTEM = """Ti si iskusan advokat koji zastupa SUPROTNU stranu u predmetu.
Identificiraj SVE slabosti i ranjivosti iz perspektive protivničke strane.
Imaš pristup analizama prethodnih koraka — koristi ih da pronađeš slabosti koje oni možda nisu pokrili ili koje oni direktno otvaraju.

ANTI-HALUCINACIJA PRAVILA:
1. ZAKONE citiraj iz sopstvenog stručnog znanja srpskog prava — "čl. 16 ZUP", "čl. 195 ZR", "čl. 373 ZPP" itd. To je tvoja stručnost.
2. ZABRANJENO je izmišljati: (a) brojeve sudskih presuda koje nisu u kontekstu, (b) specifične činjenice ovog predmeta kojih nema u tekstu.
3. Ako nisi siguran za tačan stav: "čl. X ZPP (proveriti st.)" — NIKADA "[Opšti pravni princip]".
4. Budi oštar i brutalno iskren — ovo je interna analiza za klijenta.
5. Konzervativna procena: ne umanjuj rizike.

Odgovori ISKLJUČIVO sledećim JSON formatom (bez teksta van JSON-a):
{
  "kljucne_slabosti": [{"opis": "opis slabosti", "zakonski_osnov": "konkretan zakon: čl. X st. Y ZUP ili slično"}],
  "argumenti_protivne_strane": ["konkretan argument koji će protivna strana koristiti na sudu"],
  "procesne_zamke": ["procesna zamka sa zakonskim osnovom: rok, forma, nadležnost, legitimacija"],
  "dokazi_koji_nedostaju": ["konkretan dokaz koji nedostaje — šta je to i gde se pribavlja"],
  "preporuka_za_ojacavanje": "konkretne preporuke sa zakonskim osnovom",
  "ukupna_ranjivost": "SREDNJA",
  "confidence": "VISOKA",
  "summary": "1-2 rečenice za naredne korake"
}
Dozvoljene vrednosti — ukupna_ranjivost: NISKA | SREDNJA | VISOKA; confidence: VISOKA | SREDNJA | NISKA"""

_ORK_PRESUDA_SYSTEM = """Ti si predsednik veća Višeg suda u Srbiji sa 30 godina staža.
Saslušao si argumente tužioca i tuženog. Donesi odluku i odgovori ISKLJUČIVO kao validan JSON objekat.

OBAVEZNA PRAVILA:
1. Budi potpuno neutralan — odlučuj isključivo na osnovu prava i iznesenih argumenata.
2. ZAKONE citiraj iz sopstvenog znanja — "čl. 18 st. 1 ZUSP", "čl. 9 ZUP" itd. Zabranjeno je izmišljati brojeve sudskih odluka.
3. Konzervativna procena: ne daj lažni optimizam ni jednoj strani.

Odgovori ISKLJUČIVO sledećim JSON formatom (bez teksta van JSON-a):
{
  "utvrdjeno_cinjenicno_stanje": "šta sud prihvata kao dokazano",
  "pravna_kvalifikacija": "koji zakoni i članovi se primenjuju",
  "ocena_tuzilac": "šta sud prihvata i šta odbija od argumenata tužioca i zašto",
  "ocena_tuzeni": "šta sud prihvata i šta odbija od argumenata tuženog i zašto",
  "izreka": "TUZBA ODBIJENA",
  "obrazlozenje": "2-3 rečenice obrazloženja izreke",
  "troskovi": "ko snosi troškove i zašto",
  "procena_uspeha_tuzilac": 50,
  "confidence": "SREDNJA",
  "summary": "1-2 rečenice za Synthesis Engine"
}
Dozvoljene vrednosti — izreka: TUZBA USVOJENA | TUZBA DELIMICNO USVOJENA | TUZBA ODBIJENA; confidence: VISOKA | SREDNJA | NISKA; procena_uspeha_tuzilac: ceo broj 0-100"""

_ORK_SYNTHESIS_SYSTEM = """Ti si vrhunski pravni strateg koji integriše analize svih prethodnih koraka u jedinstvenu stratešku preporuku.

Dobio si rezultate 5 analiza: Pravni Revizor, Due Diligence, Witness Analyzer, Red Team i AI Sudija v2.

OBAVEZNE DUŽNOSTI:
1. Integriši sve nalaze u koherentnu stratešku preporuku. NE ponavljaj iste nalaze iz više koraka — ako se isti problem pojavi u Revizoru I u Red Team-u, navedi ga JEDNOM u akcionom planu.
2. Identifikuj KONFLIKTE između koraka. Primeri: Revizor kaže SPREMAN ZA UPOTREBU ali Red Team identifikuje VISOKA ranjivost zbog iste klauzule; Due Diligence kaže NEPRIHVATLJIV ali Sudija pretpostavlja valjanost dokumenta.
3. Prioritizuj akcije: hitno_crveno (mora odmah — naročito rokovi i procesne zamke), vazno_zuto (u narednih 30 dana), preporuceno_zeleno (poboljšanje). Rok za tužbu (npr. 60 dana za radne sporove — ZR čl. 195) ide AUTOMATSKI u hitno_crveno ako je pomenut u analizama.
4. Ako su 2 ili više RELEVANTNIH koraka imali confidence = NISKA, postavi sistemsko_upozorenje. VAŽNO: Witness Analyzer sa ocena_pouzdanosti = NIJE_PRIMENLJIVO se NE broji u ovu računicu.
5. Konzervativna procena uvek — ne davaj lažni optimizam.
6. executive_summary mora biti AKCIONI, ne deskriptivni: "Advokat mora da uradi X, Y, Z" — ne "Analiza je pokazala da...". Konkretno i brutalno iskreno.

Odgovori ISKLJUČIVO sledećim JSON formatom (bez teksta van JSON-a):
{
  "executive_summary": "3-5 rečenica — konkretan sažetak za advokata, bez retorike",
  "strateski_stav": "OJACATI_ODBRANU",
  "prioritetni_akcioni_plan": {
    "hitno_crveno": ["akcija koja mora biti preduzeta odmah"],
    "vazno_zuto": ["akcija u narednih 30 dana"],
    "preporuceno_zeleno": ["poboljšanje koje nije hitno"]
  },
  "detektovani_konflikti": ["format: 'Korak X: nalaz A ↔ Korak Y: nalaz B — implikacija za strategiju'"],
  "sistemsko_upozorenje": null,
  "opsta_confidence": "SREDNJA"
}
Dozvoljene vrednosti — strateski_stav: NASTAVITI_TUZBU | PREGOVARATI_NAGODBU | OJACATI_ODBRANU | DOPUNITI_DOKUMENTACIJU | ODUSTATI; opsta_confidence: VISOKA | SREDNJA | NISKA; sistemsko_upozorenje: null ili string sa objašnjenjem"""


def orkestrator_kompletna_analiza_sync(
    opis_predmeta: str,
    api_key: str,
    dokumenti: list | None = None,
    iskazi_svedoka: list | None = None,
) -> dict:
    """
    F10 — Strateški Orkestrator: 6 logičkih koraka, 8 GPT-4o poziva ukupno.
    Svaki korak prima akumulirani kontekst svih prethodnih. Vraća kompletan strukturovani dict.
    """
    import json as _json
    from openai import OpenAI as _OAI

    client = _OAI(api_key=api_key)

    def _gpt_json(system: str, user: str, temperature: float = 0.2, max_tokens: int = 2000) -> dict:
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=120.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        if resp.usage:
            try:
                from shared.cost import record_cost as _rc
                _rc("gpt-4o", resp.usage.prompt_tokens, resp.usage.completion_tokens)
            except Exception:
                pass
        raw = (resp.choices[0].message.content or "{}").strip()
        try:
            return _json.loads(raw)
        except _json.JSONDecodeError:
            return {"error": "JSON decode failed", "raw": raw[:300], "confidence": "NISKA", "summary": "Korak nije vratio validan JSON."}

    def _gpt_text(system: str, user: str, temperature: float = 0.3, max_tokens: int = 1500) -> str:
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=90.0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        if resp.usage:
            try:
                from shared.cost import record_cost as _rc
                _rc("gpt-4o", resp.usage.prompt_tokens, resp.usage.completion_tokens)
            except Exception:
                pass
        return (resp.choices[0].message.content or "").strip()

    kontekst = ""

    # ── Korak 1: Pravni Revizor ───────────────────────────────────────────────
    tekst_za_revizor = "\n\n---\n\n".join(dokumenti) if dokumenti else opis_predmeta
    korak1 = _gpt_json(
        _ORK_REVIZOR_SYSTEM,
        f"Tekst za reviziju:\n\n{tekst_za_revizor}",
        temperature=0.15,
        max_tokens=2000,
    )
    kontekst += f"\n\n=== KORAK 1 — PRAVNI REVIZOR ===\n{_json.dumps(korak1, ensure_ascii=False)}"

    # ── Korak 2: Due Diligence ────────────────────────────────────────────────
    tekst_za_due = "\n\n---\n\n".join(dokumenti) if dokumenti else opis_predmeta
    korak2 = _gpt_json(
        _ORK_DUE_DILIGENCE_SYSTEM,
        f"Opis predmeta / Dokument za due diligence:\n\n{tekst_za_due}\n\nKontekst prethodnih analiza:{kontekst}",
        temperature=0.1,
        max_tokens=2000,
    )
    kontekst += f"\n\n=== KORAK 2 — DUE DILIGENCE ===\n{_json.dumps(korak2, ensure_ascii=False)}"

    # ── Korak 3: Witness Analyzer (samo ako su iskazi dostavljeni) ────────────
    if iskazi_svedoka:
        tekst_iskaza = "\n\n---\n\n".join(iskazi_svedoka)
        witness_user = (
            f"Iskazi svedoka:\n\n{tekst_iskaza}\n\n"
            f"Osnovni opis predmeta:\n\n{opis_predmeta}\n\n"
            f"Kontekst prethodnih analiza:{kontekst}"
        )
        korak3 = _gpt_json(
            _ORK_WITNESS_SYSTEM,
            witness_user,
            temperature=0.2,
            max_tokens=2000,
        )
    else:
        # Bez iskaza — ne pozivamo AI, vraćamo fiksni skip result
        korak3 = {
            "sazetak_iskaza": "Iskazi svedoka nisu dostavljeni.",
            "unutrasnje_kontradikcije": [],
            "sumnjivi_delovi": [],
            "procesna_upotrebljivost": "Witness Analyzer nije primenljiv — iskazi svedoka nisu dostavljeni za ovaj predmet.",
            "pitanja_za_unakrsno": [],
            "ocena_pouzdanosti": "NIJE_PRIMENLJIVO",
            "confidence": "NIJE_PRIMENLJIVO",
            "summary": "Modul preskočen — iskazi nisu dostavljeni. Ako postoje svedoci, dostavite iskaze za aktivaciju ovog modula.",
        }
    kontekst += f"\n\n=== KORAK 3 — WITNESS ANALYZER ===\n{_json.dumps(korak3, ensure_ascii=False)}"

    # ── Korak 4: Red Team ─────────────────────────────────────────────────────
    korak4 = _gpt_json(
        _ORK_RED_TEAM_SYSTEM,
        f"Opis predmeta:\n\n{opis_predmeta}\n\nAnalize prethodnih koraka:{kontekst}",
        temperature=0.3,
        max_tokens=2000,
    )
    kontekst += f"\n\n=== KORAK 4 — RED TEAM ===\n{_json.dumps(korak4, ensure_ascii=False)}"

    # ── Korak 5: AI Judge v2 (3 interna poziva: tužilac → branilac → presuda JSON)
    tuzilac_txt = _gpt_text(
        _JUDGE_V2_TUZILAC,
        f"Predmet:\n\n{opis_predmeta}\n\nKontekst svih prethodnih analiza:{kontekst}",
        temperature=0.3,
        max_tokens=1500,
    )
    branilac_txt = _gpt_text(
        _JUDGE_V2_BRANILAC,
        (
            f"Predmet:\n\n{opis_predmeta}\n\n"
            f"Argumenti tužioca:\n\n{tuzilac_txt}\n\n"
            f"Kontekst svih prethodnih analiza:{kontekst}"
        ),
        temperature=0.3,
        max_tokens=1500,
    )
    presuda_json = _gpt_json(
        _ORK_PRESUDA_SYSTEM,
        (
            f"Predmet:\n\n{opis_predmeta}\n\n"
            f"Argumenti tužioca:\n\n{tuzilac_txt}\n\n"
            f"Argumenti tuženog/branioca:\n\n{branilac_txt}\n\n"
            f"Kontekst svih prethodnih analiza:{kontekst}"
        ),
        temperature=0.1,
        max_tokens=2000,
    )
    korak5 = {
        "tuzilac": tuzilac_txt,
        "branilac": branilac_txt,
        "presuda": presuda_json,
        "confidence": presuda_json.get("confidence", "SREDNJA"),
        "summary": presuda_json.get("summary", ""),
    }
    kontekst += (
        f"\n\n=== KORAK 5 — AI SUDIJA V2 ===\n"
        f"Presuda (strukturovano):\n{_json.dumps(presuda_json, ensure_ascii=False)}"
    )

    # ── Korak 6: Synthesis Engine ─────────────────────────────────────────────
    sinteza = _gpt_json(
        _ORK_SYNTHESIS_SYSTEM,
        f"Opis predmeta:\n\n{opis_predmeta}\n\nSvi nalazi prethodnih koraka:{kontekst}",
        temperature=0.15,
        max_tokens=2500,
    )

    return {
        "koraci": {
            "korak_1_pravni_revizor":   korak1,
            "korak_2_due_diligence":    korak2,
            "korak_3_witness_analyzer": korak3,
            "korak_4_red_team":         korak4,
            "korak_5_sudska_procena":   korak5,
        },
        "sinteza": sinteza,
    }
