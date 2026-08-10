# VINDEX AI — ZATVARANJE TEHNIČKIH NEPOZNANICA

Stanje: `4d9d1f59`. Verifikacija iz koda, bez izmena.

---

## 1. STREAMING — **NO**

`api.py:3128` sam dokumentuje svoj protokol:
```
data: <tekst chunk>\n\n
data: [DONE]\n\n        — signal kraju
data: [CREDITS:N]\n\n   — preostali krediti
```
Jedini `yield` u telu šalje **tekstualni komad**. **Nema `izvori`, nema `confidence`, nema
`confidence_detail`.**

**Dva endpointa imaju različite ugovore.** To je nalaz sam po sebi: ko god sutra prebaci
frontend na streaming radi boljeg osećaja brzine, **tiho gubi poreklo**.

## 2. KO PUNI `izvori`

| Proizvođač | Šta radi |
|---|---|
| `app/services/retrieve.py:2093` | `"izvori": _izvori` — glavni RAG put |
| `app/services/retrieve.py:1696` | **prazan slučaj**: `{"confidence": "LOW", "confidence_detail": {}, "izvori": []}` |
| `main.py:3504`, `main.py:3613` | dodatni putevi sa istim poljima |
| `api.py:1430` | prenos u odgovor (`normalizuj_rezultat`) |

**Status: CONDITIONALLY POPULATED.** Popunjeno kada pretraga nađe izvore; **prazna lista** kada
ne nađe. Struktura pojedinačnog elementa **nije verifikovana** — ne znam da li nosi naziv
dokumenta, identifikator odlomka i lokaciju.

## 3. SINTETIČKI TEST — **NIJE IZVRŠEN**

Nisam ga napisao. Ostao sam bez raspoloživog konteksta u ovoj sesiji.
**Ne prijavljujem ga kao urađen.**

Ono što bi test dokazao, a što sada ostaje otvoreno: **da li element u `izvori` sadrži dovoljno
da se izvor prikaže korisniku** (naziv dokumenta i lokacija u njemu). Bez toga se ne zna da li
je uključivanje prikaza pitanje jednog popodneva ili traži i izmenu retrieval sloja.

## 4–8. KLASIFIKACIJA — pet odvojenih kategorija

| Kategorija | Odgovor | Dokaz |
|---|---|---|
| **Sposobnost proizvoda** — zna li sistem izvor? | **DA** | `retrieve.py:2093` |
| **API** — izlaže li `/api/pitanje`? | **DA** | `normalizuj_rezultat`, `api.py:1430` |
| **Streaming** — izlaže li? | **NE** | protokol na `api.py:3128` |
| **UI** — prikazuje li? | **NE** | `index.html:4025` prazan `display:none`; jedine dve reference u `vindex.js` ga skrivaju |
| **Klik do izvora** | **NE** | nema šta da se klikne |

**Ključni dodatak:** frontend zove **`/api/pitanje`** (3 mesta), **nijednom `/stream`**. Dakle
klijent **već prima `izvori`** i jednostavno ih ne iscrtava. Time je potvrđeno
**API-AVAILABLE / UI-MISSING** — prekid je isključivo u prikazu.

## 9–10. JAVNE TVRDNJE — P0

Vidi `VINDEX_AI_CURRENT_PUBLIC_CLAIMS_AUDIT.md`. Četiri tvrdnje na **trenutno javnoj** strani
su **NEPODRŽANE**, ne u budućem sajtu nego danas.

## 11. POSLEDICE PO SAJT

**Strategija se ne menja.** Teza „Vindex zna odakle zna" je **potvrđena na nivou sistema i
API-ja**.

Ostaje jedno pitanje koje odlučuje **hero**: da li element u `izvori` sadrži dovoljno za
prikaz. Ako da — dijagram je privremen. Ako ne — trajan.
