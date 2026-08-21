# B4-M2 — FORENZIČKI IZVEŠTAJ: INTEGRITET ČINJENICE IZ DOKUMENTA

**Datum:** 2026-08-21 · **Baseline HEAD:** `84fb7f96` · **Prethodni gate:** `a3d0aed9` (B1–B5)

---

## VERDIKT

🔴 **RED.**

Jedan kvar je dokazan i **zatvoren** (NALAZ 1). Ali B4-M2 kao celina **nije
zatvoren**: kanal `cinjenice_iz_dokumenta` dokazano **ne postoji na blokiranim
izlazima** iz `ask_agent` (NALAZ 2) — dakle tačno u situaciji zbog koje je B4 i
otvoren: pravni deo padne, a činjenica iz advokatovog dokumenta nestane s njim.

`a3d0aed9` je tvrdio da je M2 zatvoren. Ta tvrdnja **nije tačna za blokirane
puteve**.

---

## 1. ŠTA JE ZATEČENO

`a3d0aed9` je uveo kanal `cinjenice_iz_dokumenta` — strukturisane činjenice iz
korisnikovog dokumenta, sa `source_type=USER_DOCUMENT` i
`verification_state=READ_OK`, koje gradi **backend** iz `docs`, bez učešća
modela. Provenance je namerno izvan JSON šema da model ne bi mogao da dodeljuje
epistemološki status izvoru. Taj deo dizajna je zdrav.

Lanac iz mandata, verifikovan po koracima:

| Korak | Nalaz |
|---|---|
| DOCUMENT EXTRACTION | 🟢 pasusi se **dodaju** (`docs.append`) posle zakonskih, ne takmiče se za `k` mesta → zakonski korpus ih ne istiskuje |
| FACT REPRESENTATION | 🟢 parsira se **samo** header koji je sistem sam napisao (`format_doc_passage`) → sadržaj dokumenta ne može sebi dodeliti autoritet |
| FACT REPRESENTATION | 🔴 **NALAZ 1** — vrednost se sekla usred broja i potpisivala kao `READ_OK` (zatvoreno) |
| LEGAL CONTEXT ENRICHMENT | 🟡 **NALAZ 4** — hijerarhija izvora demotira i dokument tekućeg predmeta (NOT PROVEN) |
| LLM / REASONING | 🟢 kanal **zaobilazi model u celosti** — model ga ne može izmeniti |
| FINAL ANSWER | 🔴 **NALAZ 2** — kanal nedostaje na blokiranim/odbijenim izlazima |
| FINAL ANSWER | 🟡 **NALAZ 5** — SSE ruta ne prenosi kanal (latentno) |

---

## 2. NALAZ 1 — DOKAZAN I ZATVOREN 🟢

### Root cause

`main.py::_dokumentarne_cinjenice` poštovao je budžet `_DOK_CITAT_MAX = 1200`
tako što je telo pasusa **sekao na proizvoljnom znaku**:

```python
if ukupno + len(telo) > _DOK_CITAT_MAX:
    telo = telo[: max(0, _DOK_CITAT_MAX - ukupno)].rstrip()
```

Fragment je zatim dobijao **iste oznake kao ceo navod** i stizao u UI pod
naslovom „Doslovan navod iz dokumenta koji ste dostavili"
(`static/vindex.js:970-992`). Nijedno polje ne razlikuje ceo navod od odsečenog
— ključevi su `navod, dokument, chunk, source_type, verification_state`.

### Reprodukcija (mereno, `_DOK_CITAT_MAX = 1200`)

| Dokument kaže | Advokat je video | `verification_state` |
|---|---|---|
| `Kazna je 500.000,00 dinara.` | `Kazna je 500.0` | `READ_OK` |
| `Kazna je 500.000,00 dinara.` | `Kazna je 500.000` | `READ_OK` |
| `Zakljucen 14.03.2026. godine.` | `Zakljucen 14.03.2026.` | `READ_OK` |
| `Ugovorna kazna iznosi 500.000,00 dinara.` | `U` | `READ_OK` |

Pola miliona dinara prikazano kao **500,0**. To nije izgubljena činjenica nego
**IZMENJENA**, potpisana kao pročitana iz dokumenta.

Uz to: od 8 pasusa dokumenta na ulazu, 6 je tiho ispalo bez ijednog signala.

### Popravka — `main.py:2531`

```python
if ukupno + len(telo) > _DOK_CITAT_MAX:
    continue
```

**Cela činjenica ili nijedna.** `continue`, ne `break` — kraća činjenica iza
preskočene i dalje ulazi, pa se gubi strogo manje nego ranije (dokazano
testom `test_kraca_cinjenica_iza_preskocene_i_dalje_ulazi`). Kad sve staje u
budžet — uobičajen slučaj — ponašanje je bajt-identično ranijem.

Nije dodato nijedno polje: marker o skraćivanju bio bi izmena API ugovora (§7).

### Dokaz

- 400 nasumičnih (seed `20260821`) kombinacija dužina → **0 odsečenih navoda**
- Adversarial matrica §5 — datum, rok, iznos, subjekt, broj predmeta, činjenična
  tvrdnja — svaka uz 6 zakonskih pasusa dužih od nje: sve prežive doslovno
- Obrnut smer: nijedna vrednost iz zakona (`9,50`, `01.01.1978`, `P-9999/99`)
  ne može da uđe u kanal dokumenta
- Količina pravnog konteksta ne menja sadržaj kanala (bogato == oskudno)

### Mutacije — 5/5 ubijeno

| Mutacija | Ishod |
|---|---|
| vraćanje sečenja (originalni kod) | **8 failed** |
| `continue` → `break` | 1 failed |
| budžet uklonjen | 1 failed |
| `VERIF_READ_OK` promenjen | 1 failed |
| pad izvora više ne gasi kanal | 1 failed |

`main.py` posle svake mutacije vraćen bajt-identično (`sha256` 3dd398c4…).

---

## 3. NALAZ 2 — DOKAZAN, **NIJE POPRAVLJEN** 🔴 (jezgro B4-M2)

### Root cause

AST popis svih izlaza iz `ask_agent`: **24 izlaza nose odgovor korisniku, 13 od
njih nema `cinjenice_iz_dokumenta`.**

Potvrđeno **izvršavanjem** (ne čitanjem koda), kroz postojeći harness
`tests/test_b4_source_authority.py::_ask`, sa isključenim L1+L2 kešom:

| Put | `blocked` | kanal |
|---|---|---|
| HIGH normalan | — | ✅ |
| LOW (`r3714`) | — | ✅ |
| `filtrirani == []` (`r3751`) | — | ❌ |
| pravna greška (`r4022`) | `True` | ❌ |
| guard block (`r4011`) | `True` | ❌ |

`r3751` i `r3714` su **sestrinski LOW izlazi** iz iste funkcije — ista
situacija, dva različita ugovora prema korisniku.

Na putu `r4022` (`_odgovor_pravna_greska`) činjenica nestaje **potpuno**: nema
ni kanala ni doslovnog citata u tekstu. Na `r4011` je `_format_halucination_block`
(NS001-P0-001B) sposoban da priloži citat u tekst, pa činjenica nije nužno
nevidljiva — ali strukturisanog, mašinski čitljivog kanala nema.

### Zašto NIJE popravljeno u ovom sprintu

Dva od tri pogođena izlaza su izlazi **anti-halucinacijskog guard-a**. NS002 je
izmereno dokazao da izmene na toj granici traže živo E2E merenje: naizgled
ispravna izmena je scenario J oborila sa **4/5 na 1/10** i morala je biti
**vraćena**. Ovaj sprint to merenje ne može da izvede.

Popravka je zato **zaključana karakterizacionim testovima**, ne nagađana.
Četiri testa u sekciji 4 novog paketa tvrde današnje (pogrešno) ponašanje i
nose izričitu uputu: **kad se blokator zatvori, MORAJU pasti i tada se
ZAMENJUJU dokazom pokrivenosti — ne brišu se.**

---

## 4. NALAZ 3 — DOKAZAN, NIJE POPRAVLJEN 🟡 (van opsega)

`main.py::_dokumentarni_citat` (`:2565-2566`) ima **identičan** obrazac sečenja.

Mereno: pasus koji se završava sa `Ugovorna kazna iznosi 500.000,00 dinara.`
isporučen je odsečen na ` … U` — iznos ne postoji u izlazu. Blok koji ga
okružuje glasi **„IZ VAŠEG DOKUMENTA (doslovan citat, potvrđen izvor)"**.

**Zašto nije dirano:** funkcija pripada tracked stavci **NS001-P0-001B**, ne
B4-M2; mandat §8 zabranjuje širenje opsega. Razlika u težini je realna — tamo je
izlaz prozni blok koji se vidno prekida, ovde je bio *fact-shaped* podatak — ali
korenski uzrok je isti.

---

## 5. NALAZ 4 — **NOT PROVEN** 🟡 (STOP: prompt governance)

`app/services/doc_formatter.py::ORIGIN_HIERARCHY_INSTRUCTIONS` ubacuje se na
`docs[0]` kad god postoje kancelarijski pasusi (`retrieve.py`, `if _kanc_dodato:`):

> PRIMAT 1 — Zvaničan zakon/Ustav: **jedini neoboriv izvor**…
> PRIMAT 3 — … pasusi označeni **'KORISNIKOV DOKUMENT'**: koristi **ISKLJUČIVO**
> kao stilski/stručni orijentir … **NIKAD kao neoborivu činjenicu**…

Niska `'KORISNIKOV DOKUMENT'` je **prefiks sve tri labele**, uključujući
`KORISNIKOV DOKUMENT (OVAJ PREDMET)` — dokument **tekućeg** predmeta — i goli
`KORISNIKOV DOKUMENT` za tek otpremljen dokument (`tmp_*`).

Namera iz komentara je uža od teksta: sprečiti da **raniji** predmet bude pravni
osnov za **novi**. Kako je napisano, uputstvo poručuje modelu da ni dokument
tekućeg predmeta ne tretira kao činjenicu.

**NOT PROVEN:** da model zbog toga stvarno protivreči dokumentu. Za to je
potrebno merenje sa živim LLM-om. Strukturisani kanal (NALAZ 1) je nezavisan i
nepogođen — ne prolazi kroz model — pa je izloženost ograničena na **narativni**
deo odgovora.

**Zašto nije dirano:** izmena teksta hijerarhije izvora je promena prompt
governance arhitekture → §7 STOP.

---

## 6. NALAZ 5 — DOKAZAN, LATENTAN 🟡 (STOP: API ugovor)

`POST /api/pitanje/stream` (`api.py:3520`) zove `ask_agent` i dobija pun
rezultat, ali u SSE tok emituje **samo tekst odgovora**, `[DONE]` i
`[CREDITS:N]`. `cinjenice_iz_dokumenta` i `izvori_neuspeh` ne prelaze granicu.

Sestrinski `/api/pitanje` ih prenosi kroz `normalizuj_rezultat`
(`api.py:1524-1525`).

**Latentno:** nijedan klijent u repou ne poziva `/api/pitanje/stream`
(`static/vindex.js` zove isključivo `/api/pitanje`, linije 7746 i 10873).
Rizik je za spoljnog potrošača dokumentovanog endpointa.

**Zašto nije dirano:** dodavanje polja u SSE tok je promena javnog API ugovora
→ §7 STOP.

---

## 7. TESTOVI

```
tests/test_b4m2_fact_integrity.py            34 passed   (novo)
  sekcije 1-3  regresija NALAZA 1            30
  sekcija 4    karakterizacija NALAZA 2       4
povezani paketi (b4m2 + b4 + ns002 + ns002b) 111 passed
```

Nijedan postojeći test nije menjan, oslabljen, preskočen ni obrisan.

---

## 8. METODOLOŠKA NAPOMENA — DVE GREŠKE HARNESSA U OVOJ SESIJI

1. **Prvi AST popis izlaza bio je pogrešan.** Tražio je ključ `odgovor`, a
   dict-ovi u `ask_agent` koriste `data`/`message` — pa je prijavio „3 izlaza,
   svi nose kanal" umesto stvarnih „24 izlaza, 13 bez kanala". Bez ispravke bi
   ovaj izveštaj završio kao 🟡 umesto 🔴.
2. **Prvi probe je merio keš, ne kod.** `ask_agent` kešira po tekstu pitanja;
   scenariji 2–6 su vraćali keširan rezultat prvog (`Cache HIT L1`) i svi su
   izgledali kao da nose kanal. Uz to je jedan red upisan u **produkcionu**
   `ai_cache` tabelu; identifikovan po `cache_key`
   `83e7f5cf7bae9fe681391ff9367bdd79`, obrisan, provereno 0 preostalih redova.
   Merenje je ponovljeno sa isključenim L1+L2 kešom.

Oba slučaja potvrđuju pravilo iz `feedback_mutacije_i_harness_forenzika`:
zelen ili crven rezultat ništa ne znači dok se ne dokaže da harness meri ono
što tvrdi da meri.

---

## 9. UTICAJ NA BEZBEDNOST / INTEGRITET PODATAKA

Bez migracija, bez izmene šeme, bez dodira sa auth/RLS/enkripcijom/audit-om.
Popravka NALAZA 1 **sužava** ono što sistem tvrdi o korisnikovom dokumentu —
nikad ne proširuje. Fail-closed smer.

---

## 10. PREOSTALI RIZIK

1. **NALAZ 2** — činjenica iz dokumenta nestaje na blokiranim izlazima. Glavni
   otvoreni deo B4-M2.
2. **NALAZ 3** — `_dokumentarni_citat`, isti korenski uzrok kao NALAZ 1.
3. **NALAZ 4** — narativni deo odgovora nije mereno zaštićen od potiskivanja.
4. **NALAZ 5** — SSE ruta bez provenance.
5. Činjenica koja ne stane u budžet i dalje **tiho izostaje**; signalizacija
   zahteva novo polje → API ugovor.
6. `NS002B-OPEN-001` (treći mehanizam gubitka, u sintezi) nije dirala ni ova
   sesija.

---

## 11. SLEDEĆA AKCIJA

**Zatvoriti NALAZ 2** — dodati `cinjenice_iz_dokumenta` na blokirane izlaze iz
`ask_agent`, uz **živo E2E merenje pre i posle** (scenario A i scenario J iz
NS002), jer se izmena dodiruje sa anti-halucinacijskim guard-om. Četiri
karakterizaciona testa već postoje i moraju pasti kad se to uradi.
