# Vindex — mapa tvrdnji na sajtu i sposobnosti

**Pravilo:** RICH CONTENT + PROVEN CLAIMS. Sajt sme biti bogat, ali svaka rečenica koja opisuje šta proizvod *radi* mora imati živ, dostupan i dokazan put u V2.
**Osnova:** stari sajt na `f1d29b32` (pre NS004) · novi sajt na `51164c92` · popis `VINDEX_CAPABILITY_CENSUS.csv`.
**Ovaj dokument ne menja sajt i nije marketinški tekst.**

## Statusi

| Status tvrdnje danas | Značenje |
|---|---|
| LIVE_CLAIM_ALLOWED | korisnik to danas može da uradi u `/app` (V2 NG) i to je dokazano |
| CLAIM_AFTER_V2_RECONNECTION | backend radi i dokazan je (legacy ili `/app-v2`); tvrdnja se vraća kada se talas završi |
| INTERNAL_ONLY_NO_MARKETING | postoji, ali nije za marketing (admin, founder, interna metrika) |
| DO_NOT_CLAIM | nedokazano, pokvareno, duplikat ili rizično |
| UNKNOWN | nije moguće utvrditi bez produkcije |

| Istinitost stare tvrdnje | Značenje |
|---|---|
| PROVEN_CURRENT | tačno i dostupno danas u `/app` |
| PROVEN_HISTORICAL | tačno u kodu i bilo dostupno u legacy UI; danas sakriveno |
| PARTIAL | delimično tačno |
| UNSUPPORTED | nema dokaza da radi |
| FALSE/STALE | suprotno od koda |
| UNKNOWN | — |

---

## 1. Novi sajt (`site/index.html`, posle NS004): stanje danas

| Tvrdnja | Sposobnost | Istinitost | Status |
|---|---|---|---|
| Lista aktivnih predmeta, pretraga po nazivu/broju/strankama, sortiranje | CAP-001 | PROVEN_CURRENT | LIVE_CLAIM_ALLOWED |
| Detalj predmeta: broj, vrsta, tužilac/tuženi, vrednost spora, povezani klijenti | CAP-002 | PROVEN_CURRENT | LIVE_CLAIM_ALLOWED |
| Dokumenti predmeta, izdvojen tekst, jasno „tekst nije izdvojen" | CAP-003 | PROVEN_CURRENT | LIVE_CLAIM_ALLOWED |
| „Svaki nalog vidi samo predmete kojima ima pristup" | CAP-001/002 + auth | PROVEN_CURRENT (auth 401 probe + NS003/NS004 provere) | LIVE_CLAIM_ALLOWED |
| „Greška je greška", nikad prazna lista | V2 NG `predmet.js` validacija odgovora | PROVEN_CURRENT | LIVE_CLAIM_ALLOWED |
| Pravne stranice (privatnost, uslovi, DPA, AI, bezbednosni list) | CAP-168 | PROVEN_CURRENT | LIVE_CLAIM_ALLOWED |

**Presuda:** novi sajt je tačan. Tvrdi samo ono što V2 NG zaista radi. Rizik nije laž, nego to da je sajt *siromašan* u odnosu na ono što backend ume.

---

## 2. Stari sajt (`f1d29b32`): tvrdnje po celinama

### Celina 01 — Prijem spisa

| Stara tvrdnja | Sposobnost | Istinitost | Status danas |
|---|---|---|---|
| Prevučete ceo folder, svaki fajl ima svoj posao u pozadini, „obrađeno N od M" | CAP-020 | PROVEN_HISTORICAL (memorija: Phase 0+1A live-verified) | CLAIM_AFTER_V2_RECONNECTION (talas 4) |
| PDF bez tekstualnog sloja: sistem sam pročita sliku stranice | CAP-011 | **UNSUPPORTED** (OCR nikad live-verifikovan; jedini test pao) | **DO_NOT_CLAIM** do dokaza |
| Skenirani svežanj od nekoliko stotina strana sam se deli na dokumente | CAP-020 (segmentacija) | UNSUPPORTED (zavisi od OCR-a) | DO_NOT_CLAIM |
| Izvlače se broj predmeta, sud, sudija, stranke, rok, iznos, svako sa pouzdanošću | CAP-020 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION |
| Prepoznaje kom postojećem predmetu dokument pripada; pita kad nije siguran | CAP-020 / CAP-188 | PARTIAL | CLAIM_AFTER_V2_RECONNECTION |
| Rokovi se iz dokumenata prepoznaju automatski | CAP-070 | PARTIAL (kandidati da; **potvrda postoji samo u founder `/app-v2`**) | CLAIM_AFTER_V2_RECONNECTION (talas 3) |
| Original se čuva šifrovan; isti fajl dvaput ne pravi duplikat | CAP-020 | PROVEN_HISTORICAL (kod) | CLAIM_AFTER_V2_RECONNECTION |
| Poređenje dokumenata i traženje protivrečnosti | CAP-014 | PROVEN_HISTORICAL (sajt iskreno kaže da kvalitet nije meren) | CLAIM_AFTER_V2_RECONNECTION |
| **„U proizvodu ne postoji radnja brisanja dokumenta"** | CAP-012 | **FALSE/STALE**: `DELETE /api/predmeti/{id}/dokumenti/{dok_id}` postoji i zovu ga `/app-v2` i legacy | **ne ponavljati** |

### Celina 02 — Vođenje predmeta

| Stara tvrdnja | Sposobnost | Istinitost | Status danas |
|---|---|---|---|
| Jedan deterministički opis predmeta za sve AI module | CAP-120 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION (talas 6) |
| Radni prostor u jednom pozivu (stranke, dokumenti, rokovi, praksa, rizik, spremnost) | CAP-008 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION (talas 1) |
| Podaci jednog predmeta ne ulaze u analizu drugog | trust boundary | PROVEN_HISTORICAL (memorija: COI i Trust Boundary closure) | CLAIM_AFTER_V2_RECONNECTION |
| Slični raniji predmeti po vrsti spora i oblasti | CAP-114 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION (talas 6) |
| Uspešnost kancelarije po tipu spora iz upisanih ishoda | CAP-113 + CAP-130 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION (talas 6) |
| Deljenje: zadaci, **memorija firme**, pristup dodeljenom predmetu | CAP-094, **CAP-132**, CAP-092 | PARTIAL: zadaci i deljenje predmeta da; **memorija firme nikad nije imala UI** | zadaci i deljenje: CLAIM_AFTER (talas 5); memorija firme: **DO_NOT_CLAIM** |
| Sistem pamti ispravke AI teksta i koristi ih kasnije | CAP-068 | PARTIAL (3/4 rute bez pozivaoca) | DO_NOT_CLAIM |

### Celina 03 — Pravno istraživanje

| Stara tvrdnja | Sposobnost | Istinitost | Status danas |
|---|---|---|---|
| Prepoznaje nameru (pitanje, praksa, nacrt, rok, beleška) | CAP-040 intent ruter | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION (talas 2) |
| Pretraga po smislu; izričito naveden član se povlači doslovno | CAP-040 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION |
| Citiran član ili broj presude mora postojati u dohvaćenom tekstu, inače blokada | CAP-040 citation guard | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION |
| Do 5 izvora + oznaka pouzdanosti | CAP-040 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION |
| Nema pouzdanog izvora → nema odgovora, model se ne poziva | CAP-040 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION |

### Celina 04 — Izrada nacrta

| Stara tvrdnja | Sposobnost | Istinitost | Status danas |
|---|---|---|---|
| Svaki citat nosi oznaku izvora | CAP-060 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION (talas 2) |
| Izmišljen član se menja oznakom „proveriti relevantan član" | CAP-060 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION |
| Obavezna napomena da advokat pregleda nacrt | CAP-060 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION |

### Celina 05 — Strategija

| Stara tvrdnja | Sposobnost | Istinitost | Status danas |
|---|---|---|---|
| Napad iz uloge protivnika, pregled ugovora, revizija nacrta, simulirana rasprava | CAP-110 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION (talas 6) |
| Nivo rizika i spremnost računa program, AI samo objašnjava | CAP-121 / risk_engine | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION |
| Razlikuje praćen predmet od nalepljenog teksta | CAP-110 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION |
| Tuđi predmet daje odbijanje pre upita, modela i naplate | CAP-110 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION |

### Celina 06 — Kancelarija

| Stara tvrdnja | Sposobnost | Istinitost | Status danas |
|---|---|---|---|
| Kartoteka klijenata, šifrovani matični podaci, evidencija otkrivanja | CAP-030/031 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION (talas 1) |
| Sukob interesa u jednoj radnji, sa ćirilicom i greškama u kucanju | CAP-032 | PROVEN_HISTORICAL (COI fail-closed) | CLAIM_AFTER_V2_RECONNECTION (talas 1) |
| Tajmer + advokatska tarifa | CAP-100 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION (talas 5) |
| Faktura + **UBL e-faktura za državni sistem** | CAP-100 / **CAP-102** | PARTIAL: faktura da; slanje u SEF nije dokazano | faktura: CLAIM_AFTER; SEF: **DO_NOT_CLAIM** do dokaza |
| Prava po ulogama, radnja bez ovlašćenja se odbija | CAP-091 / permissions | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION (talas 5) |
| Audit lanac postoji, ekran ne postoji | CAP-165 | PROVEN_CURRENT (iskreno formulisano) | INTERNAL_ONLY_NO_MARKETING |

### Ostale stare strane

| Strana / tvrdnja | Sposobnost | Istinitost | Status danas |
|---|---|---|---|
| `bezbednost`: šest karika (izolacija predmeta, odbijanje ubačenog naloga, kapija, fail-closed, trag, baza odbija izmenu) | security slojevi | PROVEN_HISTORICAL (kod + testovi; „potvrde treće strane ne" je iskreno) | CLAIM_AFTER_V2_RECONNECTION za izolaciju u V2; ostalo INTERNAL |
| `tehnologija`: brojeve računa program; izmišljen član se ne propušta; sloj za više dobavljača | CAP-040/060/121 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION |
| `web3`: due diligence, ZDI/MiCA, CARF/DAC8, sankciona provera, poreklo sredstava, pametni ugovor | CAP-150/151 | PROVEN_HISTORICAL (`/app-v2/uskladjenost` + legacy); svežina OFAC liste nije proverena | CLAIM_AFTER_V2_RECONNECTION (zaseban proizvod, talas 7) |
| `vizija`: banke, osiguranje, notarijat | — | nije tvrdnja o sposobnosti | INTERNAL_ONLY_NO_MARKETING (pravac, ne funkcija) |
| `za-advokate`: „Prvih pet minuta" (brifing), „Pre ročišta…", „Naplata obavljenog rada" | CAP-081, CAP-116, CAP-100 | PROVEN_HISTORICAL | CLAIM_AFTER_V2_RECONNECTION (talasi 3, 6, 5) |

---

## 3. Sažetak

| Status | Broj sposobnosti u popisu |
|---|---|
| LIVE_CLAIM_ALLOWED | 7 (3 proizvodne + sajt, ljuska, nalog, status) |
| CLAIM_AFTER_V2_RECONNECTION | 52 |
| INTERNAL_ONLY_NO_MARKETING | 18 |
| DO_NOT_CLAIM | 54 |

**Na sajtu sme danas:** samo pregled predmeta, detalj i čitanje dokumenta, plus načela (stvarni podaci, sopstveni predmeti, greška je greška) i pravne stranice. Sve to novi sajt već radi.

**Blokirano dok se ne dokaže:**
- OCR i deljenje skeniranog svežnja;
- memorija firme;
- slanje u SEF;
- automatski podsetnici (email cron pada);
- „sistem uči iz ispravki";
- procenti predviđanja ishoda;
- agenti.

**Stalno zabranjeno ponoviti:** „u proizvodu ne postoji brisanje dokumenta" (FALSE/STALE).
