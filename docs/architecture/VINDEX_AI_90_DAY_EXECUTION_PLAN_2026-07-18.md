# Vindex AI — 90-Day Execution Plan (od 2026-07-18)

Izveden iz `VINDEX_AI_ARCHITECTURE_BIBLE_v1.0.md` Deo X. Ovo je plan, ne vizija —
svaka stavka ima Rule klasifikaciju, zavisnost, rizik i Rule C metriku pre nego
što počne. Realnost izvršenja: jedan founder (ne-tehnički) + Claude Code kao
jedini inženjer. Nedelje ispod su elapsed-time procene pod pretpostavkom
redovnog angažovanja, ne garancija — tempo zavisi od toga koliko brzo founder
može da pregleda rezultate i pokrene migracije (migracije uvek pokreće founder
lično, nikad se ne šalju kao "uradi sam", `feedback_migrations`).

**Dve paralelne trake, ne jedna sekvenca:**
- **Tehnička traka** (ovaj dokument) — Claude Code, Rule B infra + male Rule B
  spike-istrage. Nula Rule A (proizvod-čeka-dokaz) posla dok dokaz ne stigne.
- **Poslovna traka** (founder-ov posao, ne stavlja se u sprint) — popuniti LEC
  (150-200 anotiranih dokumenata), pokrenuti pilot sa 3-5 kancelarija. Ovo
  radi paralelno celih 90 dana i, kad proizvede nalaz, otključava Track 2
  stavke iz Bible koje danas čekaju dokaz.

---

## Pre-Phase spike (dana 1-3, pre nego što Faza 1 formalno počne)

Dve stvari moraju da se provere pre nego što se Rule C metrike za Fazu 1 mogu
pouzdano napisati — bez ovoga bi brojevi ispod bili nagađanje, ne merenje.

| Spike | Pitanje | Zašto je bitno |
|---|---|---|
| S1 | Da li su migracije `043_security_bulletproof.sql` i `044_anomaly_detection.sql` stvarno pokrenute na produkcionoj Supabase bazi? | Bible Deo VII eksplicitno kaže da je ovo nepoznato (repo stanje ≠ DB stanje). `shared/audit_immutable.py` (hash-chain audit log, `log_action()`/`log_action_sync()`/`verify_chain_integrity()`, već postoji i verifikovan u kodu) možda zavisi od tabela iz tih migracija — ako nisu pokrenute, Faza 1 stavka 2 ispod ne može da počne dok se to ne reši. |
| S2 | Koji je tačan signature/šema `log_action()` — da li već nosi ko/kada/šta/agent/pre-posle polja, ili samo deo toga? | Direktno određuje da li je "Genome Audit Trail" mali posao (pozovi postojeću funkciju sa 5 mesta u `case_dna.py`) ili srednji posao (proširi šemu prvo). Ne pretpostavlja se — proverava se pre nego što se piše Rule C cilj za tu stavku. |

Rezultat ova dva spike-a menja procenu trajanja Faze 1 stavke 2 ispod (i,
mogla bi da promeni redosled). Ovo je namerno prva stvar u planu, ne detalj.

---

## FAZA 1 — Reliability Foundation (nedelje 1-3)

Tri poteza founder-a je predložio, u redosledu zavisnosti (ne u redosledu kako
su navedeni originalno — Event Bus prvi jer ništa drugo ne zavisi od njega, a
sve ostalo može da ga koristi):

### 1.1 — Event Bus → Genome wiring

**Klasifikacija:** Rule B (ne menja API, ne menja UX, priprema skalu).

**Šta se tačno radi:** `case_dna.py` refresh/history-write tačke počinju da
emituju event kroz **durable outbox mehanizam** (`dispatch_pending_events` /
`DispatchLoop`, već produkciono testiran preko intake pipeline-a) — NE kroz
mrtvi in-memory `EventBus.publish()`, koji nema garanciju isporuke. Ovo je
namerna odluka: intake pipeline je već dokazao da outbox pattern preživljava
crash usred obrade (11/11 chaos-test provera, vidi `docs/PHASE_PLAN.md`);
ponovna upotreba dokazanog mehanizma je niži rizik nego oživljavanje
netestiranog in-memory bus-a.

**Zavisi od:** ničega. Može da počne odmah posle S1/S2.

**Rizik:** emisija eventa na svaki Genome write mora biti idempotentna (isti
refresh ne sme da proizvede duplirane evente ako se retry desi) — intake
worker-ov `claimed_at`/reap-stale-job pattern već rešava ovaj tačan problem,
kopira se isti pristup, ne izmišlja novi.

**Rule C metrika:**
- Pre: 0 Genome-triggered eventa ikad emitovano.
- Posle: 100% Genome refresh-a (sva 3 trigera: upload, ročište, manual)
  producira tačno jedan event u outbox tabeli; 0 duplikata na 20 uzastopnih
  refresh-a (isti test-metod kao intake chaos-test).
- Merenje: brojanje redova u outbox tabeli nasuprot brojanju `case_dna`
  update poziva u istom vremenskom prozoru.

### 1.2 — Genome Audit Trail

**Klasifikacija:** Rule B, uslovno na rezultat spike S1/S2.

**Šta se tačno radi:** svaka promena Genome-a upisuje ko/kada/zašto/koji
agent/pre-posle. Ako S2 pokaže da `audit_immutable.log_action()` već nosi ova
polja — ovo postaje potrošač eventa iz 1.1 (dispatch handler koji zove
`log_action()`), što ujedno dokazuje da bus iz 1.1 nije mrtva infrastruktura
po drugi put. Ako S2 pokaže da šema ne pokriva "agent" ili "pre-posle" polje,
potrebna je mala migracija (founder pokreće SQL lično, standardna praksa).

**Zavisi od:** 1.1 (ako se implementira kao event consumer — preporučeno) ILI
može biti direktan poziv iz `case_dna.py` bez čekanja na 1.1 ako se S1/S2
pokažu sporim — ovo je fallback, ne prvi izbor.

**Rizik:** `predmet_genome_history` tabela već postoji i radi kao verziona
istorija (ne audit log — razlika je bitna: history čuva stanje, audit čuva
*ko/zašto je promenio*). Ne mešati ih — audit trail se dodaje kao novi sloj
pored postojeće verzione istorije, ne zamenjuje je.

**Rule C metrika:**
- Pre: 0 audit zapisa za bilo koju Genome promenu.
- Posle: 100% Genome mutacija (refresh, buduće ručne izmene) proizvodi audit
  red sa svih 5 polja popunjenih (ko/kada/zašto/agent/pre-posle) u roku od
  jednog request ciklusa.
- Merenje: broj `case_dna` update-a naspram broja odgovarajućih audit redova
  u istom periodu, ciljano 1:1.

### 1.3 — Genome Verification Layer (Critic Layer v1)

**Klasifikacija:** Rule B da počne (infra/reliability), ali sam koncept
"blokiranje lošeg izlaza" mora ostati read-only/advisory u v1 — blokiranje
save-a bi bilo UX promena i vratilo bi ovo na Rule A dok se ne dokaže da je
željeno.

**Bitna ispravka founder-ove pretpostavke:** `analiza/validator.py` NIJE
direktno pluggable na Genome bez posla. Njegove funkcije
(`validate_clause_excerpts`, `validate_clause_refs`) su čvrsto vezane za
`SegmentedDocument` i za `finding`-oblik podataka specifičan za "analiza"
funkciju (clause_excerpt, clause_ref, severity) — Genome nema taj oblik
(nema `findings` niza, ima `dokazi_rang`/`argumenti_za`/`kontradikcije`).

**Šta JESTE direktno reusable:** arhitektonski *obrazac* — non-blocking,
nikad ne baca exception, uvek vraća validan dict, sumnjivo premešta u
`low_confidence_*` umesto da tiho briše (`run_validation_pipeline:313-352` je
referentni template za oblik funkcije). I `validate_law_refs` (`:289-308`) je
gotovo doslovno reusable, jer već proverava law_ref stringove protiv iste
`_POZNATI_ZAKONI` liste koju bi Genome-ov `pravna_teorija.relevantni_zakoni`
i `strategija` mogli da koriste.

**Šta treba NAPISATI novo** (ne kopirati): 2-3 Genome-specifične provere po
istom obrascu — npr. da li `dokazi_rang` referencira dokumente koji stvarno
postoje u `predmet_dokumenti` za taj predmet; da li `kontradikcije.lokacija_1/2`
pokazuju na realne DOK-XX brojeve; reuse `validate_law_refs` bez izmene za
`relevantni_zakoni`.

**Zavisi od:** ničega tehnički, ali baseline (ispod) treba da postoji pre nego
što se piše finalni Rule C cilj.

**Rule C metrika — baseline metod pošto je LEC prazan:** ne čekati pun LEC
(to je 30-dnevni founder-ov posao, poslovna traka). Umesto toga: ručni
bootstrap uzorak — Claude Code (ili founder) ručno pregleda 20-30 postojećih
Genome izlaza iz produkcije naspram njihovih izvornih dokumenata, ručno broji
nepodržane tvrdnje (isti princip kao LEC anotacija, samo mali uzorak, brzo).
Taj broj postaje bazna vrednost. Tek posle toga se piše konkretan cilj
(founder-ov primer od 40%/25%/15% je ilustracija oblika cilja, ne stvaran
broj dok se ne izmeri baseline).
- Pre: [popuniti posle bootstrap uzorka].
- Posle: [cilj se piše u odnosu na izmerenu bazu, ne unapred].
- Merenje: isti bootstrap metod ponovljen na novom uzorku od 20-30 posle
  implementacije.

---

## FAZA 2 — Pipeline Truth (nedelje 4-6)

### 2.1 — Instrumentacija Smart Intake finalize koraka (NE automatizacija)

**Klasifikacija:** Rule B (instrumentacija ne menja UX ni API) koja
proizvodi Rule A dokaz za buduću odluku.

Founder je ovo tačno pogodio: ne pretpostavljati da li advokati žele punu
automatizaciju ili kontrolnu tačku — meriti. Dodati logovanje na
`POST /jobs/{id}/finalize` (`smart_intake.py:327-330`, gde kod već priznaje
gap): vreme između job-completion i finalize-klika, i da li je advokat nešto
promenio pre finalize-a ili samo potvrdio kako jeste.

**Zavisi od:** ničega.

**Rizik:** nizak — čisto dodavanje logging polja, nema promene ponašanja.

**Rule C metrika:**
- Pre: 0 podataka o tome da li advokati menjaju ili samo potvrđuju.
- Posle (posle N=30 finalize događaja ili 30 dana, šta pre nastupi): jasan
  procenat "menja pre potvrde" vs "potvrđuje bez izmene". Ovaj broj — ne
  nagađanje — odlučuje da li auto-finalize ide u Track 2 kao Rule A predlog.

### 2.2 — Sitni dug iz Bible Deo IX (filler, nizak prioritet, radi se usput)

`strategija.py` prefix fix, konsolidacija `_d`/`_safe` helper-a, ispravka
zastarelog docstring-a u `matter_intel.py:_compute_next_action`. Nema Rule C
metrike — trivijalno, radi se kad ima slobodnog vremena između 2.1 i Faze 3,
ne zakazuje se posebno.

---

## FAZA 3 — Data Foundation (nedelje 7-9)

**Zašto je treća, ne prva, iako je founder označio kao "najveća crvena
zastava":** ovo je stvarna crvena zastava, ali pogađa RAG/pravno
istraživanje (zakoni_rs, sudska_praksa namespace), NE Genome ekstrakciju
direktno — Genome čita isključivo dokumenta konkretnog predmeta
(`predmet_dokumenti`), ne pravni korpus. Faza 1-2 poboljšavaju pouzdanost
onoga što Genome već radi danas; Faza 3 poboljšava temelj za RAG-zavisne
delove sistema (chat, pravno istraživanje, agenti koji citiraju zakone).
Oba su bitna — redosled je po tome šta je jeftinije i niže-rizično prvo, ne
po tome šta je "manje bitno".

### 3.1 — Dijagnoza i stabilizacija ingestion-a

**Klasifikacija:** Rule B (popravka postojeće infrastrukture, ne nova
funkcija).

**Šta se radi:** kategorizovati 12+ izvora sa `[GRESKA]` iz
`data/ingest_all_log.txt` — koji su tranzijentne greške (rate limit, mrežni
timeout) nasuprot strukturnih (loš parser za taj format). Rešiti Pinecone
mesečni write-unit cap (5,000,000, pogođen 2026-07-13) sa pravim
budget-aware batch-ovanjem/backoff-om, ne samo "pokušaj ponovo".

**Zavisi od:** ničega tehnički, ali redosled izvora (koji se prvi
popravlja) je founder-ova odluka — koji pravni izvori su najvažniji za
kancelarije u pilotu.

**Rizik:** srednji — Pinecone cap je eksterno ograničenje (mesečni budžet),
ne samo kod bug; može zahtevati da se ingestion razvuče kroz više meseci ili
da se poveća Pinecone plan (trošak, founder-ova odluka, ne tehnička).

**Rule C metrika:**
- Pre: 3 od ~16+ izvora uspešno ingest-ovano (iz postojećeg log-a).
- Posle: definisati cilj tek posle kategorizacije 3.1 (koliko izvora je
  realno popravljivo u ovoj fazi vs. zahteva veći Pinecone plan) — ne pisati
  broj unapred dok se ne zna koliko je grešaka strukturno rešivo.

---

## Nedelje 10-13 — Merenje i re-plan

Bez novog razvoja po difoltu. Ponovo izmeriti sve Rule C metrike iz Faze 1-3,
upisati rezultate (postignuto/nije postignuto, otvoreno, bez ulepšavanja —
isti duh kao Office Accuracy Dashboard koji pošteno vraća prazno stanje).
Proveriti da li je poslovna traka (LEC, pilot) u međuvremenu proizvela nalaz
koji otključava neku Track 2 stavku iz Bible. Ako jeste — ta stavka postaje
kandidat za sledeći 90-dnevni ciklus, sa svojom Rule C metrikom pisanom tada,
ne sada.

---

## Rizik registar (skraćeno, detalji po fazi iznad)

| Rizik | Faza | Mitigacija |
|---|---|---|
| Migracije 043/044 nisu primenjene na produkciji | Pre-Phase | S1 spike pre bilo čega drugog |
| Event emisija nije idempotentna | 1.1 | Kopirati intake worker-ov claimed_at/reap pattern |
| Audit šema ne pokriva potrebna polja | 1.2 | S2 spike; migracija se piše i predaje founder-u da je pokrene lično |
| Genome-specifične validacije lažno odbijaju validne tvrdnje | 1.3 | v1 je advisory/read-only, ne blokira save dok se ne dokaže tačnost na bootstrap uzorku |
| Pinecone mesečni cap ograničava koliko se izvora može popraviti u Fazi 3 | 3.1 | Kategorizacija pre popravke; eskalacija plana je founder-ova odluka, ne tehnička prepreka |

---

## Eksplicitno van obima ovog plana (founder-ova lista, bez izmene)

Neo4j, RDF/OWL grafovske baze; 9 novih agenata; veliki redizajn Genome
JSON šeme; potpuno autonoman sistem bez ljudske kontrolne tačke; fine-tuning
modela. Sve ovo ostaje u Bible Deo X Track 2 ili van dokumenta — vraća se u
razmatranje samo ako Rule A dokaz eksplicitno na njih ukaže, nikad po
difoltu na početku sledećeg ciklusa.
