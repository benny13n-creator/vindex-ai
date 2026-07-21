# Vindex AI — Integration Master Plan ("Ustav" Vindex 2.1)

**2026-07-19.** Ovaj dokument je peti u nizu (posle
`OPERATING_SYSTEM_CONNECTIVITY_AUDIT.md`, `..._V2.md`,
`OPERATING_SYSTEM_ROADMAP.md`, `VINDEX_2_1_ARCHITECTURE_ROADMAP.md`) —
i poslednji koji menja SAM NAČIN RADA, ne samo sadržaj analize.

**Odnos prema `VINDEX_2_1_ARCHITECTURE_ROADMAP.md`:** taj dokument je
REGISTAR ODLUKA (D1-D20, statusi). Ovaj dokument je USTAV PROCESA — kako
se rad organizuje, meri, i kad se smatra završenim. Ne dupliraju se:
kad ovaj dokument pominje D-broj, znači "videti taj status u ADR-u".

**Novi princip rada, zamenjuje modul-po-modul pristup:** ne radi se
"Rokovi", "Genome", "Strategy" kao odvojeni zadaci. Radi se **TOK**
(npr. "Upload presude") koji prolazi kroz ceo sistem od početka do
kraja. Tok nije završen kad nema TODO-a — završen je kad se može
nacrtati dijagram bez prekinute strelice.

**Nova disciplina za svaki budući predlog, bez izuzetka:** ne pitati
"da li radi?" — pitati **"šta se POSLE ovoga automatski pokreće?"**
Ako odgovor je "ništa", predlog nije završen, bez obzira koliko je
funkcija sama po sebi dobra.

---

## Deo A — Kompletan operativni lanac, danas (kod-verifikovano)

Ovo NIJE aspiracioni dijagram — ovo je stvarno stanje `main` grane,
svaka strelica označena kao **ŽIVA** (postoji u kodu, automatski) ili
**PREKINUTA** (ne postoji, ili zahteva ručnu akciju koju dijagram ne
pokazuje).

```
Klijent ──(ručno)──► Predmet ──(ručno)──► Upload dokumenta
                                                │
                                          ŽIVA  ▼
                                              OCR (auto fallback,
                                              uploaded_doc/extractor.py)
                                                │
                                          ŽIVA  ▼
                                    Klasifikacija + Entity extraction
                                    (JEDAN GPT poziv, routers/evidence.py
                                    — ova dva "koraka" iz primera su
                                    tehnički isti poziv, ne dva)
                                                │
                                          ŽIVA  ▼
                                          Evidence Vault
                                    (predmet_dokazi upisano)
                                                │
                                    PREKINUTA (namerno, D17) ✗
                                                │
                                          ŽIVA  ▼ (nezavisan trigger,
                                                    ne kroz Evidence)
                                          Case Genome
                                    (uključuje Kontradikcije KAO POLJE
                                    unutar sopstvene šeme — nije
                                    odvojen modul, primer dijagrama
                                    ovo pogrešno prikazuje kao korak)
                                                │
                                    PREKINUTA (D-nema, Rejected/D20) ✗
                                                │
                                          Strategija
                                    (isključivo ručan klik; auto-KONTEKST
                                    radi kad se ručno otvori, auto-TRIGER
                                    namerno ne postoji — D20)
                                                │
                            Genome.rokovi_kriticni[] ostaje u JSON-u
                                    PREKINUTA (D7) ✗
                                                │
                                          ZPP događaji
                                    (rokovi_lanac.py — RUČAN, piše u
                                    predmet_hronologija)
                                                │
                            PREKINUTA — različite tabele (D-nalaz nov) ✗
                                                │
                                          Deadline Guardian
                                    (zastarelost.py — čita `rokovi`
                                    tabelu, KOJU NIŠTA NE PIŠE; nema UI, D8)
                                                │
                                    PREKINUTA (D-nema veze) ✗
                                                │
                                          Task Engine (zadaci.py)
                                    (sopstveni `rok_datum`, TREĆI
                                    nezavisan deadline-koncept —
                                    nov nalaz ove sesije, videti Deo C)
                                                │
                            DELIMIČNO (samo ručno dodeljen task) ⚠
                                                │
                                          Obaveštenja
                                    (email/whatsapp/briefing — cron
                                    isporuka neizvesna, D10)
                                                │
                                    PREKINUTA — 0 log_action poziva
                                    u notifikacionim routerima (nov
                                    nalaz ove sesije) ✗
                                                │
                                          Audit Trail
                                    (upisuje se za samo 3/24 akcije;
                                    NIŠTA GA NIKAD NE ČITA nazad —
                                    potvrđeno grep-om ove sesije, 0
                                    poziva van log_action definicije)
                                                │
                                    PREKINUTA — 0 čitalaca ✗
                                                │
                                          Analytics/Dashboard
                                    (postoji, ali NE čita audit_immutable
                                    niti bilo šta iz gornjeg lanca
                                    dosledno — van obima ovog audita da
                                    se svaki dashboard extra proveri)
```

**Brojčani rezime:** od 13 strelica u lancu, **6 su žive, 7 su
prekinute ili delimične.** Ovo NIJE isto što i "46% gotovo" — lanac je
onoliko dobar koliko njegova prva prekinuta karika (Evidence↔Genome, ✗
na poziciji 4 od 13) dozvoljava da PROĐE do kraja bez ljudske
intervencije. Efektivno: **0 od 13 koraka se dešava bez bar jedne
ručne akcije negde u lancu**, iako svaki pojedinačni korak (posmatran
izolovano) najčešće radi dobro.

---

## Deo B — Kompletan inventar eventova

(Registar, kompletna analiza u `OPERATING_SYSTEM_CONNECTIVITY_AUDIT.md`
Faza 1 — ovde samo sažet inventar radi kompletnosti "ustava".)

| Event | Postoji definicija | Emituje se | Handler postoji | Aktivan end-to-end |
|---|---|---|---|---|
| `GenomeUpdated` | DA | DA | DA | **JEDINI potpuno živ** |
| `PredmetKreiran` | DA | NE | DA (`on_predmet_kreiran`) | NE (D3) |
| `RokKritican` | DA | NE | DA (`on_rok_kritican`) | NE (D5) |
| `HealthScorePromenjen` | DA | NE | DA | NE (D5) |
| `DocumentJobEnqueued/Completed/Failed` | DA | DA (SQL RPC) | NE | NE (no-op) |
| `DokumentUploadovan` | DA | NE | DA | NE |
| `RokDodan` | DA | NE | NE | NE |
| `RociscteZakazano` | DA | NE | NE | NE |
| `StrategijaGenerisana` | DA | NE | NE | NE |
| `AnalizaZahtevana` | DA | NE | NE | NE |
| **"Dokument klasifikovan"** | **NE POSTOJI** | — | — | Nedostaje iz enum-a potpuno (D4) |
| **"Task kreiran"** | **NE POSTOJI** | — | — | Nedostaje — nov nalaz, potreban za Deo C spajanje |
| **"Notifikacija poslata"** | **NE POSTOJI** | — | — | Nedostaje — nov nalaz, objašnjava zašto Obaveštenja→Audit strelica ne postoji |

---

## Deo C — Nov nalaz ove sesije: tri paralelna "rok" koncepta

Reorganizacija po TOKOVIMA (ne modulima) otkrila je nešto što
modul-po-modul audit nije eksplicitno imenovao kao JEDAN problem:
**sistem ima TRI odvojena mesta gde "rok/deadline" živi, bez
sinhronizacije:**

1. **`predmet_hronologija`** — piše ZPP lanac (`rokovi_lanac.py`),
   follow-up ročišta forma, i GPT ekstrakcija prošlih datuma iz teksta.
2. **`rokovi` tabela** — čita je Deadline Guardian i 6+ drugih modula;
   **nijedan pisac nađen u kodu** (potvrđeno u prethodnom audit-u).
3. **`zadaci.rok_datum`** — sopstveni, nezavisan rok POJEDINAČNOG
   zadatka, nepovezan sa prva dva.

**Posledica:** čak i kad bi se D6/D7 (ZPP↔klasifikacija veza) i D8
(Deadline Guardian UI) implementirali nezavisno, oni bi i dalje gledali
u RAZLIČITE izvore istine za "koji su rokovi u ovom predmetu". Ovo je
**nov, četvrti preduslov** koji nijedan raniji audit nije eksplicitno
imenovao kao jedinstven problem — dodaje se u ADR kao:

### D21 (novo). Jedinstven izvor istine za rokove

- **Kontekst:** tri nezavisna mesta za "rok" podatak, bez sinhronizacije.
- **Status: Blocked (zavisi od D2, prethodi D6/D7/D8).** Pre nego što
  se ijedna veza iz Faze 3 ADR-a (D6-D9) implementira, mora se odlučiti
  da li `rokovi` tabela postaje jedini izvor (i `predmet_hronologija`
  rok-tipa unosi se sinhronizuju u nju), ili obrnuto. Ovo je
  arhitektonska odluka, ne detalj — utiče na redosled cele Faze 3.

---

## Deo D — Definicija četiri kanonska toka

Rad se od sada organizuje po ovim tokovima, ne po modulima. Svaki tok
ima Definition of Done (DoD) — nijedna stavka u DoD nije opciona.

### Tok 1 — Upload tužbe (prvi dokument u novom predmetu)

```
Upload → OCR → Klasifikacija+Ekstrakcija → Evidence Vault → Case Genome
   → [PredmetKreiran event, D3] → [run_case_pipeline, D9] → Audit → Dashboard
```

**DoD:**
- [x] Klasifikacija automatska (već ✅ živo)
- [x] Evidence Vault upis automatski (već ✅ živo)
- [x] Case Genome regeneracija automatska (već ✅ živo)
- [x] `PREDMET_KREIRAN` emitovan pri kreiranju predmeta (D3 — **zatvoreno i
  VERIFIKOVANO produkcijski**, commit `8f54f54`/`5bcc226`, 2026-07-21 —
  videti `CONTRACT_01_PRODUCTION_VERIFICATION.md`)
- [x] `run_case_pipeline()` pokrenut automatski (D9 — **zatvoreno i
  VERIFIKOVANO produkcijski**, ista verifikacija kao D3, posledica istog fix-a)
- [x] Audit red upisan za `predmet_create` i `dokument_upload` (D22 v1 —
  **zatvoreno i VERIFIKOVANO produkcijski**, commit `b84fd4b`/`bb4388b`,
  2026-07-21 — 7. stavka, formalizovana posle originalnog 4/6 brojanja.
  SAMO ova dva dogadjaja — tamper-evidence provera/retention/user
  attribution kroz ostale ~19-21 od 24 `AUDITABLE_ACTIONS`/export/
  compliance format i dalje van obima, NE tvrditi da je D22 "gotov" u
  širem smislu)
- [x] Korisnik vidi rezultat (Genome panel) bez ručnog osvežavanja (već ✅ živo)

**Status toka: 6/6 živo za originalnih 6 DoD stavki (100%), PLUS 7.
stavka (D22 v1, Audit) sada takođe zatvorena i verifikovana
produkcijski 2026-07-21 — Tok 1 danas RADI end-to-end za predmet→
pipeline→audit lanac. D22 v1 pokriva samo predmet/document creation;
šira audit zrelost (integritet/retention/ostali tokovi/export/
compliance) ostaje van obima, videti `VINDEX_OPERATIONAL_GAP_
REGISTER.md` G-003 Update 2026-07-21.**

### Tok 2 — Upload presude (klasifikovan procesni dokument → rok)

```
Upload → Klasifikacija("sudska_odluka") → [PRECIZNIJA klasifikacija, D1]
   → [datum dostave, D2] → [predlog ZPP događaja, D4+D6] → potvrda advokata
   → [rok izračunat, D6] → [D21 jedinstven izvor] → [Guardian registruje, D8]
   → [Task kreiran, D12] → [notifikacija raspoređena, D10] → Audit
```

**DoD:**
- [ ] Sistem prepoznaje da JE presuda, ne generičko "sudska_odluka"
  (D1 — **nedostaje**)
- [ ] Datum prijema/dostave izvučen ili eksplicitno zatražen (D2 —
  **nedostaje, najveći pojedinačni blok**)
- [ ] Predložen ZPP događaj sa tačnim tipom (D4+D6 — **nedostaje**)
- [ ] Advokat vidi zahtev za potvrdu, ne tih upis (D6 dizajn — **nedostaje**)
- [ ] Rok izračunat determinstički POSLE potvrde (`rokovi_lanac.py`
  katalog već ✅ postoji, samo nepovezan)
- [ ] Rok upisan u JEDINSTVEN izvor istine (D21 — **nedostaje, preduslov**)
- [ ] Guardian registruje novi rok za praćenje (D8 — **nedostaje**)
- [ ] Task kreiran kao predlog, ne automatski izvršen (D12 — **nedostaje**)
- [ ] Notifikacija raspoređena kad se rok približi (D10 — **nedostaje,
  I cron isporuka neizvesna**)
- [ ] Audit trag za ceo lanac (D22 — **nedostaje**)

**Status toka: 1/10 živo (sam ZPP katalog postoji, nepovezan), 9
nedostaje — OVO JE NAJDALJE OD ZAVRŠETKA OD SVA ČETIRI TOKA**, i tačno
onaj tok koji najdirektnije testira "operativni sistem" obećanje.

### Tok 3 — Dodavanje ročišta

```
Ročište uneto → predmet_hronologija upis (već ✅ živo) → [D21 sinhronizacija
   sa rokovi tabelom] → [Guardian registruje] → [notifikacija] →
   [dashboard prikaz] → [audit]
```

**DoD:**
- [ ] Ročište se upisuje u hronologiju (već ✅ živo, `rocista.py`)
- [ ] Genome refresh trigerovan (već ✅ živo, `trigger="rociste_trigger"`)
- [ ] Sinhronizovano sa jedinstvenim rok-izvorom (D21 — **nedostaje**)
- [ ] Guardian zna za ovaj datum (D8+D21 — **nedostaje**)
- [ ] Podsetnik pre ročišta raspoređen (D10 — **nedostaje**)
- [ ] Vidljivo na dashboard-u bez otvaranja predmeta (neprovereno — **treba proveriti**)
- [ ] Audit trag (D22 — **nedostaje**)

**Status toka: 2/7 živo.**

### Tok 4 — Zatvaranje predmeta

```
Zatvori predmet (routers/predmeti_close.py, već ✅ živo, strukturisan
   ishod) → benchmark upis (već ✅ živo, potvrđeno u prethodnom audit-u)
   → [learning/style profile update?] → [statistika?] → [firm metrics?]
   → [audit]
```

**DoD:**
- [ ] Strukturisan ishod upisan (već ✅ živo)
- [ ] Anonimni benchmark doprinos (već ✅ živo, potvrđeno)
- [ ] Da li se style profile (`_update_style_profile`, `corrections.py`)
  ikad trigeruje ovim eventom, ili samo posle 10+ korekcija nezavisno?
  **NEPROVERENO u ovoj sesiji — treba proveriti pre nego što se ovaj
  tok proglasi gotovim.**
- [ ] Firm-nivo statistika ažurirana (**neprovereno**)
- [ ] Audit trag za `predmet_close`/`predmet_delete` tip akcije —
  proveriti da li je uopšte u `AUDITABLE_ACTIONS` allowlist-i (D22)

**Status toka: 2/5 potvrđeno živo, 3 neprovereno (ne "nedostaje" —
ISKRENO nepoznato, treba provera pre suda).** Ovaj tok je najbliži
završetku od sva četiri, ali "najbliži" ovde znači "2 od 5 potvrđeno",
ne "skoro gotov".

---

## Deo E — Redosled integracije, uz reconciliaciju sa korisnikovim P0-P3

Korisnikov predlog ranga (P0 osnovni lanac, P1 semantička preciznost,
P2 trust, P3 UX) je ispravan kao PRIORITET VREDNOSTI. Zahteva jednu
preciznu dopunu radi TAČNOSTI (ne menja rang, samo redosled UNUTAR P0):

**P0 stavke koje NE zavise od semantičke preciznosti (D1/D2) — mogu
ići odmah:** D3 (PredmetKreiran emit), D5 (RokKritican/HealthScore
handleri), D9 (case pipeline aktivacija), D10 (cron provera), D22
(core audit akcije). Nijedna od ovih ne dodiruje SADRŽAJ roka — samo
strukturu/isporuku.

**P0 stavke koje TEHNIČKI spadaju u "osnovni lanac" ali SADRŽAJNO
zavise od P1 (semantička preciznost) da bi bile tačne, ne samo
prisutne:** "upload→rokovi" i "upload→Guardian" (D6, D7, D8 sa stvarnim
sadržajem). Ovde se korisnikov P0/P1 redosled mora ČITATI kao: **P0
infrastruktura ide prva (event postoji, UI postoji), P1 semantika mora
biti rešena PRE nego što se ta infrastruktura puni STVARNIM rok-
predlozima.** Redosled ostaje P0→P1 kako je predloženo — samo
"P0 gotovo" za rok-specifične stavke znači "žica postoji", ne "žica
nosi tačan signal" dok P1 ne prođe.

Konkretno, ažurirani redosled:

1. **P0-A (odmah, nezavisno):** D3, D5, D9, D10, D22.
2. **P0-B (infrastruktura za rokove, ALI ne puštati sadržaj dok P1 ne
   prođe):** D8 (Guardian UI — može se pustiti PRAZAN/sa postojećim
   ručno-unetim rokovima, korisno samo od sebe), D21 (jedinstven izvor
   istine — arhitektonska odluka, mora pasti pre D6/D7).
3. **P1 (semantička preciznost, blokira sadržaj P0-B stavki):** D1, D2.
4. **P0-B nastavak (sada sa sadržajem):** D4, D6, D7 — sada bezbedno
   jer P1 je rešen.
5. **P2 (Trust):** D15-D19 (već razrađeno u ADR-u), plus D11 (unlock
   modal provera — takođe hitna, ali kategorija Trust ne osnovni lanac).
6. **P3 (UX):** sve što nije gore — poslednje, tek kad se sva 4 toka
   provere end-to-end.

---

## Deo F — Obavezno end-to-end testiranje pre prelaska na sledeći tok

Pravilo, bez izuzetka: **nijedan tok se ne proglašava gotovim na
osnovu toga da li pojedinačni koraci rade izolovano.** Test mora
simulirati CEO tok, od prvog koraka do poslednjeg, i proveriti SVAKU
stavku u DoD listi tog toka (Deo D) kao jedan test, ne 10 odvojenih
testova.

Redosled testiranja tokova (ne redosled implementacije stavki iz Dela
E — ovo je REDOSLED VALIDACIJE celog toka posle implementacije):
1. Tok 1 (Upload tužbe) — najbliži završetku, testirati prvi.
2. Tok 3 (Dodavanje ročišta) — srednja složenost.
3. Tok 4 (Zatvaranje predmeta) — proveriti 3 neproverene stavke PRE
   testa, ne tokom.
4. Tok 2 (Upload presude) — najsloženiji, najviše zavisnosti (D1+D2+D4+
   D6+D8+D21+D12+D10+D22), testirati poslednji, tek kad su 1/3/4
   potvrđeno prošli.

Isti regresioni-skup obrazac kao Genome Verification Layer (Faza 1.3,
ranije ove sesije) — sintetički predmeti sa poznatim očekivanim
ishodom, pre/posle merenje, Rule C disciplina.

---

## Deo G — Kako se ovaj dokument koristi ubuduće

Svaka buduća izmena koda (posle Beta Freeze-a) se proverava protiv OVOG
dokumenta pre nego što se smatra "gotovom":
1. Kom TOKU pripada (ne kom modulu)?
2. Koju stavku u DoD listi tog toka zatvara?
3. Šta se POSLE ove izmene automatski pokreće — ako odgovor je
   "ništa", izmena nije integraciona, samo izolovana popravka, i mora
   biti jasno označena kao takva (nije loše da postoji, ali se ne
   računa kao napredak ka "operativni sistem" cilju).
4. Da li je testirana END-TO-END u kontekstu celog toka, ne izolovano?

Kad su sva četiri toka 100% DoD i prošla end-to-end test bez
prekinute strelice — TEK TADA se Vindex AI može opisati kao jedinstven
operativni sistem, ne kolekcija modula. Do tada, ovaj dokument je
merilo napretka — status svakog toka (Deo D) se ažurira posle svake
implementacione runde, isto kao statusi u `VINDEX_2_1_ARCHITECTURE_
ROADMAP.md`.

**Trenutni sažetak (2026-07-19):** Tok 1: 4/6. Tok 2: 1/10. Tok 3: 2/7.
Tok 4: 2/5 potvrđeno + 3 neprovereno. **Nijedan tok nije gotov. Sistem
je danas kolekcija modula sa jednim potpuno živim end-to-end lancem
(Genome regeneracija) i nula potpuno živih operativnih tokova.**

**Update 2026-07-21:** Tok 1: **6/6** originalnih DoD stavki (D3+D9
zatvoreni i produkcijski verifikovani, `CONTRACT_01_PRODUCTION_
VERIFICATION.md`). **Update isti dan, kasnije:** 7. stavka (Audit, D22
v1) takođe zatvorena i verifikovana produkcijski — Tok 1 je sada prvi
tok koji funkcioniše end-to-end za predmet→pipeline→audit lanac, na
originalnih 6 + formalizovanu 7. stavku. D22 v1 je namerno uzan (samo
predmet_create/dokument_upload) — šira audit zrelost ostaje van obima.
Preostala tri toka nepromenjena.
