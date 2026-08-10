# VINDEX AI — FINALNA SPREMNOST ZA IZRADU SAJTA

Stanje: `a171189f`. Verifikacija iz koda, bez izmena.

---

## 1–5. POZICIJA (nepromenjeno)

**Centralna ideja:** Vindex zna odakle zna.
**Kategorija:** operativni **sloj** za složen profesionalni rad *(ne „sistem" — vidi §10)*
**Prvo tržište:** advokatske kancelarije · **Dugoročno:** banke, notarijat, osiguranje, korporativna pravna služba

## 6. POREKLO — POTVRĐENO

`normalizuj_rezultat` u `api.py` dodaje `resp["izvori"]`, `resp["confidence"]`,
`resp["confidence_detail"]`, uz komentar „šalje se klijentu radi prikaza".
**Status: API-AVAILABLE / UI-MISSING.**

## 7. STREAMING — **UNVERIFIED**

`api.py:3128` nije pročitan. Ostao sam bez konteksta u ovoj sesiji.
**Ne rešavam nagađanjem.** Važno jer streaming otežava slanje metapodataka uz tok teksta.

## 8. SADRŽAJ `izvori` — **UNVERIFIED**

Nije praćeno šta popunjava polje, pod kojim uslovima, i da li objekat identifikuje dokument i
lokaciju u njemu. **Sva tri polja se dodaju uslovno** (`if rezultat.get(...)`), pa postojanje
polja nije dokaz da je popunjeno.

---

## 9. `landing.html` — ANALIZA

**Struktura** (1.297 linija, 2 skripte): `hero` → `kako` (tri koraka) → `funkcije` → `zasto` →
`cenovnik` → `cta`.

**Tehnički kvalitet je DOBAR:** CSS custom properties (`--font-brand`, `--font-mono`,
`--font-ui`), semantične sekcije sa id-evima, minimalan JS. Održivo.

**Strateški je POGREŠAN — na sva četiri pitanja:**

| Zatečeno | Sukob |
|---|---|
| **„Vindex AI — Pravni operativni sistem"** | oba problema odjednom: **„pravni"** zaključava u jednu delatnost i ruši beachhead strategiju; **„operativni sistem"** je tvrdnja koju smo utvrdili kao neodrživu (ništa se ne pokreće na Vindexu) |
| **„Počni besplatno — 15 upita bez kartice"** | samouslužna registracija. Proizvod je pre-beta, bez korisnika. Preporučeni CTA je zatvoreno testiranje. |
| **Sekcija `cenovnik`** | cena je objavljena, a u repozitorijumu postoji **više neusaglašenih varijanti** |
| **„Nikad više propuštenih rokova"** | garancija ishoda — **ZABRANJENO** po `PUBLIC_CLAIMS.md` |
| „Simulacija … verovatnoće ishoda" | tvrdnja o predviđanju ishoda — **NEPODRŽANO**, nikad mereno |

**Revizija tvrdnji:** ODOBRENO ~2 · USLOVNO ~4 · **NEPODRŽANO ~5** · NEPOZNATO ~3.

## 10. ODLUKA: **REPLACE**

Ne `ENHANCE` — struktura je izgrađena oko pogrešne pozicije.
Ne `REUSE` — pet nepodržanih tvrdnji.
Ne `REBUILD` — „rebuild" podrazumeva čuvanje temelja, a **temelj je upravo ono što je pogrešno**.

**Ključna distinkcija koju je misija tražila: kod je dobar, strategija nije.**

| | |
|---|---|
| **KEEP** | vizuelni sistem (CSS promenljive, tri fonta, paleta) · koncept sekcije „tri koraka" · čist HTML pristup bez okvira |
| **DISCARD** | naslov „Pravni operativni sistem" · „Počni besplatno" · ceo `cenovnik` · „Nikad više propuštenih rokova" · tvrdnje o verovatnoći ishoda |
| **REBUILD** | hero · poruka · redosled sekcija (poverenje pre funkcija) · CTA |
| **TRANSFORM** | `funkcije` → grupisane sposobnosti bez liste alata · `zasto` → „zašto verovati" sa poreklom i evidencijom |

## 11. HERO

**Dijagram, ne snimak** — `dokument → uređen kontekst → odgovor → nazad do dokumenta`.
Snimak sa vidljivim izvorom **ne postoji** dok se prikaz ne uključi.

## 12. TRI NAJJAČA DOKAZA
1. strukturisan prikaz predmeta *(uz sintetiku)* · 2. tok unosa dokumenta · 3. rok izvučen iz dokumenta.
Odgovor sa vidljivim izvorom — **nemoguć danas**.

## 13–14. TVRDNJE
**SMEMO:** sistem beleži poreklo i vraća ga klijentu · nepromenljiva evidencija · razdvajanje podataka · uloge.
**NE SMEMO:** da korisnik klikom stiže do izvora · cena · garancije rokova · verovatnoća ishoda · „operativni sistem" kao kategorija.

## 15. BLOKATORI
1. `landing.html` tvrdi suprotno od strategije — **do zamene ne sme ostati javan sa ovim tekstom**
2. Streaming poreklo — UNVERIFIED
3. Sadržaj `izvori` — UNVERIFIED
4. Prikaz izvora isključen u UI-ju
5. Sintetički demo predmet ne postoji
6. Kontakt i pravni podaci firme — UNKNOWN

## 16. PREPORUKA
Zameniti stranu, zadržati vizuelni sistem. **Pre pisanja finalnog prompta zatvoriti blokatore 2 i 3** —
oni odlučuju da li hero ide na dijagram trajno ili samo privremeno.
