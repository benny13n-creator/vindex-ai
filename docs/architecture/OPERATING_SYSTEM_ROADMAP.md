# Vindex AI — Operating System Connectivity Roadmap (2026-07-19)

**Core obećanje proizvoda koje se ovde proverava:** *"Advokat donosi
pravnu odluku. Sistem automatski vodi operativni deo predmeta."*

Ovo je druga runda dubinskog konektivnost audita (nastavak
`OPERATING_SYSTEM_CONNECTIVITY_AUDIT.md`), sprovedena kroz 2 dodatna
paralelna istraživanja (OCR/notifikacije/task-kreiranje; sistematska
pretraga marketing/UI teksta naspram stvarnog ponašanja), plus sinteza
iz prethodne runde. Isključivo analiza — nijedna linija koda nije
menjana. Svaki nalaz ima file:line dokaz.

**Najhitniji pojedinačni nalaz cele ove runde, pre bilo čega drugog:**
landing stranica (pre-signup marketing, `index.html:4067`) tvrdi:
*"Automatska obaveštenja 7, 2 i 1 dan pre isteka. Sistem prati rokove
umesto vas."* Ovo je **javno obećanje potencijalnom klijentu pre nego
što se uopšte registruje** — i dokaz iz koda sugeriše da vrlo verovatno
ne radi u produkciji (videti Deo Trust Analysis, nalaz #1). Ovo je
ozbiljnije od bilo kog internog UX nedostatka jer je to obećanje dato
PRE poverenja koje bi trebalo da se tek izgradi.

---

# TASK 1 — End-to-end Case Lifecycle Audit

Polazna tačka: advokat otprema prvi dokument (`POST /api/predmeti/{id}/upload`,
`api.py` — jedini live put na main grani).

| Korak | Postoji | Povezano sa produkcijom | Triger | Ručna akcija potrebna | Prioritet |
|---|---|---|---|---|---|
| 1. Upload dokumenta | DA | DA | Klik "Otpremi" | Izbor fajla, klik | — (radi) |
| 2. OCR | DA (`uploaded_doc/extractor.py:32-86`) | DA, automatski fallback | Detekcija <30 chars/str ili <80 ukupno (`extractor.py:25-27`) | Nijedna — transparentan fallback | — (radi, bolje nego ranije pretpostavljeno) |
| 3. Klasifikacija (Evidence Vault) | DA (`routers/evidence.py`) | DA | Automatski posle uploada (`api.py:3909-3914`) | Nijedna | — (radi) |
| 4. Ekstrakcija entiteta/činjenica | DA, ALI dva odvojena sistema | Delimično — Genome ekstrahuje ceo dokument u kontekstu predmeta; Smart Intake (entity-po-entity, sa confidence) **nije live na main** | Automatski (Genome) | Nijedna za Genome deo | — (Genome radi; Smart Intake čeka merge odluku) |
| 5. Kreiranje klijenta | DA | DA | Ručna forma | Ime, ostalo opciono | — (radi, namerno ručno) |
| 6. Kreiranje predmeta | DA | DA (kreira se), **NE** (ne pokreće ništa dalje) | 5-koračni wizard | Popuna/potvrda polja | **P0 — vidi Deo 2** |
| 7. Genome generacija | DA | DA | Automatski posle uploada (fire-and-forget) | Nijedna | — (radi) |
| 8. Evidence analiza | DA | DA (sopstveni prikaz), **NE** (nepovezano sa Genome) | Automatski posle uploada | Nijedna | P1 (namerno odloženo, Faza 1.3) |
| 9. Strategy generacija | DA | DA (kad se pokrene) | **Isključivo ručan klik** | Klik + (sada auto-popunjen) kontekst | — (namerno ručno, ispravna granica) |
| 10. Detekcija roka | Delimično | **NE** za buduće rokove | GPT ekstrahuje `rokovi_kriticni[]` u Genome, ostaje zarobljeno | Ručan ZPP lanac unos | **P0 — vidi Deo 2/3** |
| 11. Kreiranje timeline događaja | Delimično | DA za PROŠLE događaje (auto iz teksta), NE za BUDUĆE rokove | GPT ekstrakcija (prošlost), ručan unos (budućnost) | Za buduće rokove: da | P1 |
| 12. Notifikacije | DA (kod postoji, 3 sistema) | **VEROVATNO NE** — zahtevaju eksterni cron poziv koji `Procfile` ne definiše | Trebalo bi: scheduled cron. Danas: nepoznato da li se ikad poziva | Korisnik mora sam otvoriti ekran da vidi bilo šta | **P0 — vidi Deo 2/5** |
| 13. Zadaci/akcije | DA | DA (kad se ručno kreira) | **Isključivo ručno** — potvrđeno 0 automatskih kreiranja iz bilo kog drugog modula | Uvek ručno | P1 |
| 14. Zatvaranje predmeta | DA (`routers/predmeti_close.py`) | DA, dobro povezano | Ručan klik "Potvrdi zatvaranje" | Klik + izbor ishoda | — (radi ispravno) |

---

# TASK 2 — Automation Gap Analysis

## Event emitters bez konzumenata

- `DocumentJobEnqueued/Completed/Failed` (3 tipa) — emituju se preko SQL
  RPC-a (`migrations/073_intake_foundations.sql`), nula registrovanih
  handlera u `services/event_bus.py::_register_defaults()`. **P2** (deo
  neaktivne Smart Intake grane, ne main puta).

## Konzumenti bez emitera

- `PredmetKreiran` → `on_predmet_kreiran` bi pokrenuo kompletan
  `run_case_pipeline()` — event se nikad ne emituje za standardni
  intake put. **P0.**
- `RokKritican` → `on_rok_kritican` bi kreirao `proactive_alerts` —
  nikad emitovan. **P0** (direktno vezano za notifikacije, Task 3).
- `HealthScorePromenjen` → `on_health_score_promenjen` bi upozorio na
  nizak health score — nikad emitovan. **P1.**

## Servisi koji postoje ali se nikad ne pozivaju (van standardnog puta)

- `services/case_pipeline.py::run_case_pipeline()` — pozvan samo za
  "kreiranje iz šablona". **P0.**
- `routers/zastarelost.py::guardian_scan/guardian` (Deadline Guardian) —
  nula UI referenci. **P0.**
- `routers/email_notif.py`, `whatsapp_notif.py`, `morning_briefing.py`
  cron endpoint-i — grade i rade ispravno, ali `Procfile` (repo root)
  definiše SAMO `web: gunicorn api:app`, nijedan cron/worker proces tip.
  **Ne može se 100% potvrditi iz koda da li eksterni scheduler postoji
  van repo-a (npr. Render/Railway dashboard konfiguracija) — ovo je
  jak signal, ne dokaz.** **P0, hitno za proveru** (Task 3/5).

## Baza polja koja se nikad ne popunjavaju

- `rokovi` tabela — 7+ modula je čita (`case_commander.py`, `decision_
  replay.py`, `integrations.py`, `morning_briefing.py`, `whatsapp_
  notif.py`, `zadaci.py`, `zastarelost.py`), nula pisaca nađeno u kodu,
  nula CREATE TABLE migracija nađeno. **P1, hitno za proveru žive baze.**
- `ocr_used`/OCR kvalitet — upisuje se kao Pinecone metadata tag, nikad
  se ne čita nizvodno niti utiče na bilo koji confidence prikaz. **P2.**

## UI funkcije koje impliciraju automatizaciju a su ručne

- Onboarding "ZPP rokovi se računaju automatski" — kalkulacija je
  automatska, TRIGER je ručan (već poznato, blago netačna nijansa,
  ne kritično). **P2.**
- Landing stranica "Sistem prati rokove umesto vas" — videti Deo
  Trust Analysis #1. **P0.**
- Tri "unlock" modal poruke (Knowledge Transfer/Firm DNA/Intelligence
  Engine na 15/20/30 predmeta) — videti Trust Analysis #2-4. **P0/P1.**

## Backend automatizacija nevidljiva korisnicima

- `run_case_pipeline()`-ova mini-strategija (GPT-4o-mini, kad se
  pipeline pokrene preko "iz šablona" puta) piše u `predmet_istorija`
  tagovano "[Strategija Pipeline]" — korisnik koji vidi ovo u istoriji
  nema objašnjenje da je ovo DRUGAČIJI sistem od 8 Strategy modula koje
  poznaje. **P2, konfuzija ne netačnost.**

---

# TASK 3 — Deadline System Deep Audit

## Trenutno stanje — može li Vindex automatski:

| Sposobnost | Postoji? | Dokaz |
|---|---|---|
| Detektovati tip dokumenta | **DA** | Evidence Vault, `routers/evidence.py` |
| Identifikovati procesni događaj | **DELIMIČNO** | Genome GPT može prepoznati, ALI nema determinističku vezu tip_dokaza→procesni_dogadjaj |
| Izračunati rok | **DA, deterministički, kad se ručno pokrene** | `routers/rokovi_lanac.py::_TIPOVI` katalog, pravi pravni osnov po roku |
| Kreirati timeline događaj | **DELIMIČNO** | Samo ako je ZPP lanac ručno pokrenut sa predmet_id |
| Obavestiti advokata | **VEROVATNO NE** | Cron infrastruktura postoji, isporuka neizvesna (Task 2) |
| Predložiti akciju | **NE, specifično za rokove** | Genome "sledeći koraci" je opštiji, ne rok-fokusiran |

## Minimalna arhitektura povezivanja (predlog, ne implementacija)

```
Dokument otpremljen
       ↓
Evidence Vault klasifikuje kao "sudska_odluka" (VEĆ RADI, automatski)
       ↓
[NOVA VEZA — determinističko mapiranje, ne AI]
tip_dokaza="sudska_odluka" → mapira se na jedan ili više
_TIPOVI ključeva iz rokovi_lanac.py (npr. "dostava_presude_prvostepene")
       ↓
Sistem kreira PENDING (nepotvrđen) rok-predlog, NE konačan rok
       ↓
Advokat dobija zahtev za potvrdu:
  "Otkrivena moguća presuda. Da li je datum prijema [X]?
   Ako potvrdite, izračunaćemo rok za žalbu (ZPP čl. 374, 15 dana)."
       ↓
Advokat potvrđuje/ispravlja datum → TEK TADA se kreira stvaran,
actionable rok u sistemu
```

**Zašto je koraci "potvrda" obavezan, ne opcion:** klasifikacija
dokumenta je AI/probabilistička (Evidence Vault GPT poziv može
pogrešiti tip dokumenta). Kalkulacija roka JE deterministička (prava
matematika iz ZPP kataloga) — ali GARBAGE IN/GARBAGE OUT važi: pogrešna
AI klasifikacija bi proizvela pogrešan, ali uverljivo prikazan
deterministički rok. **Razdvajanje je eksplicitno:** AI sme da PREDLOŽI
koji tip roka je moguć; determinizam sme da IZRAČUNA tačan datum kad je
tip potvrđen; nijedan deo lanca ne sme da SAM potvrdi finalni,
obavezujući rok bez advokatovog pregleda. Ovo je isti princip kao
"bolje bez izvora nego lažni izvor" iz Trust Layer runde, primenjen na
rokove: bolje predlog koji čeka potvrdu nego tih, samouveren pogrešan
rok.

---

# TASK 4 — "Autonomous Law Firm Assistant Test"

Scenario: senior advokat otprema novu tužbu. Šta i dalje zahteva
njegovu pažnju, a sistem bi REALNO mogao da preuzme (sa postojećom
infrastrukturom, ne izmišljenom)?

1. **Potvrda mogućeg roka iz klasifikovanog dokumenta** — sistem bi
   mogao da predloži (Task 3 dizajn), danas advokat mora sam da otvori
   ZPP lanac i sve ručno unese.
2. **Prva orijentacija predmeta (risk snapshot, HCC briefing)** —
   `run_case_pipeline()` VEĆ RADI ovo, samo za "iz šablona" put.
   Standardni put ostavlja advokata bez ovoga iako je kod gotov.
3. **Provera da li se rok uopšte prati** — danas nema pouzdanog
   signala (notifikacije neizvesne), advokat mora sam da se seti da
   proveri Rokovi tab periodično.
4. **Kreiranje podsetnika/zadatka za sebe na osnovu Genome nalaza**
   (npr. "nedostaje: odgovor druge strane") — Genome to POKAZUJE, ali
   ne kreira zadatak automatski; advokat mora ručno da ode u Zadaci tab
   i sam upiše.
5. **Znanje da li je ijedna od 4 "sledeći korak" preporuka
   međusobno konzistentna** — advokat danas ne zna da ih ima više,
   nema način da proveri da li se slažu.

Ono što advokat I DALJE treba da radi, i TREBALO BI da nastavi sam
(namerno van obima autonomije): odluka koju strategiju koristiti,
formulacija argumenata, konačna potvrda bilo kog roka pre nego što
postane obavezujući, sve što se šalje sudu ili klijentu.

---

# TASK 5 — Trust Analysis

### Nalaz #1 — KRITIČAN: landing stranica marketing tvrdnja

- **Promise:** `index.html:4067` — *"Automatska obaveštenja 7, 2 i 1
  dan pre isteka. Sistem prati rokove umesto vas."* (pre-signup
  marketing tekst, ne in-app copy).
- **Reality:** `email_notif.py` ima kod koji bi ovo radio (7/3/1-dan
  logika postoji, blago se razlikuje od "7/2/1" u marketing tekstu —
  sitna nedoslednost i u samom broju dana), ALI zahteva eksterni cron
  poziv na `/api/cron/daily` sa `CRON_SECRET` header-om. `Procfile`
  definiše samo `web` proces — nema potvrde da nešto ikad poziva taj
  endpoint u produkciji.
- **Risk:** NAJVIŠI u celom dokumentu — javno obećanje potencijalnom
  klijentu, pre poverenja, o funkciji koja verovatno ne radi.
- **Fix:** (a) hitno proveriti da li cron postoji van repo-a (hosting
  dashboard); ako ne postoji, (b1) ili ga konfigurisati PRE nego što se
  ovaj tekst pokaže ijednom prospektu, ili (b2) privremeno ukloniti/
  ublažiti tvrdnju dok se ne potvrdi da radi.

### Nalaz #2-4 — Tri "unlock" modal poruke bez potvrđenog odredišta

- **Promise:** "Knowledge Transfer" (15. predmet), "Firm DNA" (20.
  predmet), "Intelligence Engine" (30. predmet) — sve obećavaju
  automatsko učenje/analizu/predviđanje na osnovu istorije kancelarije.
- **Reality:** nijedna od tri nije mapirana u `_VX_PD_LOCK_MAP`
  (`vindex.js:9857-9862`) na stvaran pane; grep za odgovarajuće
  funkcije/pane-ove vraća 0 pogodaka.
- **Risk:** korisnik koji dostigne 15/20/30 predmeta i klikne na
  otključanu "nagradu" nailazi na nešto što možda ne postoji —
  isti "obećava a ne isporučuje" obrazac koji je Trust Layer runda
  eksplicitno pokušavala da eliminiše na drugom mestu.
- **Fix:** proveriti da li ijedna od tri ima realno odredište pre nego
  što bilo koji beta korisnik (500+ predmeta/god firma bi ovo dostigla
  brzo) naiđe na njih; ako ne, ukloniti/preformulisati pre šireg pilota.

### Nalaz #5 — manja nedoslednost, niska ozbiljnost

- **Promise:** Onboarding "ZPP rokovi se računaju automatski".
- **Reality:** kalkulacija automatska, triger ručan (već poznato iz
  Founder Playbook rada).
- **Risk:** nizak — nijansa, ne netačnost.
- **Fix:** već zabeleženo u Founder Playbook-u kao napomena za
  foundera kako da to precizno objasni; nije neophodna UI izmena.

### Kontrolni nalazi — obećanja koja SE SLAŽU sa stvarnošću

"Automatsko pisanje tužbi/žalbi" (PRO modal), "Analiza dokumenta —
automatski izvlači ključne klauzule" (kc-ai-card), "Jedan klik pokreće
svih 6 modula" (Kompletna analiza opis), onboarding "Sistem će
automatski analizirati dokument" — sva potvrđena kao tačna, AI korak
JESTE automatski nakon eksplicitnog korisničkog uploada/klika, što je
razumno tumačenje reči "automatski" u ovom kontekstu.

---

# TASK 6 — VINDEX OPERATING SYSTEM CONNECTIVITY ROADMAP

## Faza 1 — Kritične konekcije pre šireg beta širenja

1. **Proveriti/rešiti notifikacioni cron** — najveći prioritet u celom
   dokumentu, jer je javno obećanje na landing stranici u pitanju. Ili
   potvrditi da eksterni scheduler postoji i radi, ili privremeno
   uskladiti marketing tekst sa stvarnošću.
2. **Proveriti tri "unlock" modal odredišta** — pre nego što ijedan
   pilot korisnik (500+ predmeta/god firma) na njih naiđe.
3. **Emitovati `PREDMET_KREIRAN` iz standardnog intake puta** —
   aktivira već izgrađen `run_case_pipeline()`, jedna izmena, veliki
   povratni efekat.
4. **Proveriti `rokovi` tabelu na živoj bazi** — potvrditi da li 7+
   modula koji je čitaju ikad dobijaju stvaran podatak.
5. **Popuniti core audit trail akcije** (predmet_create, dokument_
   upload, klijent_create, login) — compliance rizik, ne samo UX.

## Faza 2 — Važna automatizaciona poboljšanja

1. Deterministička veza tip_dokaza → mogući tip roka, sa obaveznom
   advokatovom potvrdom (Task 3 dizajn) — ne novi AI poziv, samo
   mapiranje + potvrda-UI.
2. Materijalizacija Genome `rokovi_kriticni[]` u stvarne, actionable
   rokove (isti obrazac, potvrda pre konačnog upisa).
3. Surface-ovati Deadline Guardian rezultat u UI (backend već postoji).
4. Razjasniti/konsolidovati 4 nezavisna "sledeći korak" sistema — bar
   vizuelno razdvojiti ih ("ovo je opšta preporuka" vs. "ovo je
   workflow korak") da se ne dožive kao kontradiktorni.

## Faza 3 — Budući autonomni tokovi (posle pilot dokaza)

1. Automatski predlog zadatka iz Genome `nedostaje`/`najslabija_tacka`
   (predlog, advokat potvrđuje pre nego što postane stvaran zadatak).
2. Kanban "Završen" → opciona finalna faktura/arhivski checklist.
3. Ponovno razmatranje Evidence↔Genome tvrdnja-dokaz veze (Faza 1.3
   odluka je bila svesno odlaganje, ne trajna zabrana — vredi
   preispitati SA stvarnim pilot podacima, ne pre).
4. Objedinjen "šta se dešava sa ovim predmetom" prikaz koji kombinuje
   već izgrađen HCC briefing + risk snapshot (iz `case_pipeline`) sa
   Genome prikazom, dosledno za svaki predmet, ne samo "iz šablona" put.

## Pravila poštovana u ovom planu

Nijedna stavka ne zahteva nov AI model, nov event tip (12 već postoji),
niti novu arhitekturu — svaka faza povezuje ili izlaže već izgrađenu
funkcionalnost, sa obaveznim advokatovim potvrdom pre bilo koje
akcije sa pravnom posledicom (rok, zadatak, faktura).

---

# Brutalna, kod-zasnovana ocena

**"Da li se Vindex AI danas ponaša kao automatizovan pravni operativni
sistem koji tvrdi da jeste?"**

**Ne — i ovog puta odgovor nosi dodatnu, ozbiljniju notu u odnosu na
prvi connectivity audit.** Prvi audit je pokazao da je unutrašnja
arhitektura nepovezana, ali internа. Ova runda je pokazala da se
nepovezanost proteže i na **javno, pre-signup obećanje** ("sistem prati
rokove umesto vas") koje trenutno nema potvrđen mehanizam isporuke u
produkciji. Razlika je bitna: interni arhitektonski dug je nešto što
tim popravlja u svom tempu; neispunjeno javno obećanje advokatu koji
razmatra da poveri predmete klijenata sistemu je rizik koji ne čeka.

Pozitivna strana ostaje ista kao u prvom auditu, i ovde je dodatno
potvrđena: skoro sve što bi "operativni sistem" trebalo da radi je već
NAPISANO — case pipeline, deadline guardian, notifikacioni cron
endpoint-i, deterministički rok-katalog. Ono što nedostaje nije
inteligencija niti čak povezivanje u apstraktnom smislu — nedostaje
**potvrda da su te veze stvarno uključene i da rade u produkciji**, ne
samo u kodu. Pre bilo kakvog daljeg razvoja, Faza 1 stavka #1 (cron
provera) treba da bude prva stvar koja se radi — ne zato što je
tehnički najzanimljivija, nego zato što je jedina stavka u ovom
dokumentu gde je razlika između "kod postoji" i "obećanje se ispunjava"
već data korisniku unapred, pre nego što je imao šansu da posumnja.
