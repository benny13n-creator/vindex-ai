# Faza 1 — Execution Checklist (od 2026-07-18)

**Status: istraživanje i plan. Nula izmena aplikativnog koda urađeno da bi se
ovo napisalo** (jedini pokrenut kod je `scripts/audit_state.py` — postojeći,
read-only audit skript koji ne menja ništa, samo generiše izveštaj). Ne
implementirati ništa iz ovog dokumenta dok se checklist ne pregleda i odobri
stavku po stavku.

Prati format iz `VINDEX_AI_90_DAY_EXECUTION_PLAN_2026-07-18.md` Faza 1: za
svaku stavku — tačni fajlovi, migracije, API rizik, test strategija, rollback,
Rule C metrike.

---

## Pre-Phase spike — rezultat (rešeno danas, bez čekanja na founder-a)

| Spike | Pitanje | Odgovor |
|---|---|---|
| S1 | Da li su migracije 043/044 primenjene na produkciji? | **DA.** `python scripts/audit_state.py` pokrenut uživo protiv produkcione Supabase baze (2026-07-18 19:40 UTC) — `audit_immutable`, `ai_forensics`, `security_events`, `user_daily_activity`, `chain_anchors` tabele postoje live. Nisu na listi od 3/41 nepotpunih migracija (`STATE_AUDIT.md`). |
| S2 | Da li `log_action()` već nosi ko/kada/zašto/agent/pre-posle polja? | **Delimično.** Signature (`shared/audit_immutable.py:57-64`): `action, user_id, resource_type, resource_id, ip, metadata`. Ko=`user_id` ✓, kada=`created_at` auto-timestamp ✓. "Zašto"/"agent"/"pre-posle" NEMAJU dedikovane kolone — idu u `metadata` (slobodan JSONB), što je dovoljno za potrebu, samo treba disciplina šta se tačno upisuje u taj dict. Dodatno: `action` mora biti u `AUDITABLE_ACTIONS` skupu (`:33-52`) — trenutno nema nijednog Genome unosa, treba dodati (Python set, ne migracija). |

---

## 1.1 — Event Bus → Genome wiring

**Tačni fajlovi:**
- `services/event_bus.py` — dodati `GENOME_UPDATED = "GenomeUpdated"` u `EventType` enum (`:31-45`).
- `routers/case_dna.py` — insert u `events` tabelu posle uspešnog `predmeti.case_dna` update-a, na dva mesta: `refresh_case_dna` (`:459-468`, posle `.update(...).execute()`) i `_run_genome_background` (`:339-345`, isto mesto).

**Bitna arhitektonska odluka (nije trivijalna, ne pretpostavlja se):**
Postojeći durable-outbox primer (`enqueue_intake_job`, `migrations/073...sql:141-`)
piše u `events` tabelu IZ POSTGRES RPC FUNKCIJE, u istoj transakciji kao
promena stanja — to je izvor njegove "ništa se ne gubi" garancije. Genome
danas piše `case_dna` kroz obično `supa.table("predmeti").update()`, ne kroz
RPC. Dve opcije:

- **Opcija A (puni paritet, treba migracija):** nova RPC funkcija
  `refresh_genome_and_emit(...)` koja atomski radi `UPDATE predmeti` + `INSERT
  events` u jednoj transakciji, po uzoru na `enqueue_intake_job`. Veći posao,
  nulti rizik od izgubljenog eventa čak i pri crash-u između koraka.
- **Opcija B (bez migracije, mali rizik prozor):** dva sekvencijalna Python
  poziva — postojeći `.update()` pa zatim `.table("events").insert()`. Ako
  proces padne tačno između njih, event se izgubi, ali Genome podatak je
  ispravan. Ovaj rizik je iste klase kao već postojeći rizik u istom fajlu —
  `_save_genome_history` takođe nije atomski sa glavnim update-om danas.

**Preporuka za Fazu 1: Opcija B.** Ne uvodi novu vrstu rizika u odnosu na ono
što `case_dna.py` već prihvata, ne traži migraciju, može da se izmeri (Rule C
ispod) da li je stopa izgubljenih eventa realno primetna pre nego što se
ulaže u Opciju A.

**Bitno — NE zvati i `emit()` (in-memory) I DB insert za isti event.**
`dispatch_pending_events()` će kasnije sam pozvati `bus.publish_async()` za
svaki red koji pročita iz `events` tabele. Ako se `emit()` pozove odmah PLUS
upiše se u tabelu, isti handler bi se pokrenuo dvaput. Koristiti isključivo
DB-insert put, dosledno tome kako `enqueue_intake_job` radi (ne zove Python
`emit()` uopšte).

**Migracije:** NEMA (za Opciju B). `events` tabela već ima `predmet_id`,
`payload` JSONB, `user_id`, `event_type` — sve što treba, bez šema izmene.

**API rizik:** Nizak. Insert je posle postojećeg response-a već izračunat —
javni ugovor `POST/GET .../case-dna*` se ne menja. Jedini rizik: ako
Supabase insert u `events` baci grešku, mora biti uhvaćen i logovan (ne sme
srušiti request) — isti pattern kao postojeći `_save_genome_history` try/except.

**Test strategija:**
1. Unit: pozvati insert helper direktno, proveriti novi red u `events` sa
   `event_type='GenomeUpdated'`, tačan `predmet_id`, `payload` sa bar
   `verzija` i `snaga_predmeta_procent`.
2. Integracija: posle triggera, ručno pozvati `dispatch_pending_events()`,
   proveriti da `dispatched_at` postane not-null (dokazuje da red nije u
   `unknown_type` grani — enum mora da prepozna string).
3. Regresija: `tests/test_intake_e2e_restart.py` i `test_intake_phase0.py`
   moraju ostati zeleni nepromenjeni — dokazuje da deljena `events` tabela/
   dispatch loop nije pokvarena za Smart Intake dodavanjem novog tipa.
4. Ručni smoke test: 3 stvarna refresh-a (upload/ročište/manual endpoint) na
   test predmetu, potvrditi 3 nova reda.

**Rollback:** Čist `git revert` — nema migracije, nema šema promene. Redovi
već upisani u `events` sa `GenomeUpdated` ostaju (append-only filozofija),
inertni su dok ništa ne postane subscriber u 1.2 — bezopasno.

**Rule C:**
- Pre: 0 Genome-triggered eventa ikad.
- Posle: 100% od sva 3 trigera producira tačno 1 event; 0 duplikata na 20
  uzastopnih refresh-a.
- Merenje: broj `events` redova `event_type='GenomeUpdated'` naspram broja
  `case_dna` update poziva (postojeći `logger.info` brojevi) u istom prozoru.

---

## 1.2 — Genome Audit Trail

**Tačni fajlovi:**
- `shared/audit_immutable.py` — dodati `"genome_refresh"` u `AUDITABLE_ACTIONS`
  (`:33-52`, jedna linija).
- `services/event_bus.py` — nova handler funkcija `on_genome_updated(event)`
  (po uzoru na `on_rok_kritican` itd., `:61-` blok), registrovana u
  `_register_defaults()` (`:159-163`) za `EventType.GENOME_UPDATED`. Handler
  zove `log_action()` sa `metadata` koji nosi ono što `log_action()` nema kao
  kolonu: `{"trigger": ..., "agent": "case_dna_extractor", "verzija": ...,
  "snaga_pre": ..., "snaga_posle": ..., "razlog": <kratak tekst delta-e>}`.

**Zašto event-consumer put, ne direktan poziv iz case_dna.py:** rešava dve
stvari odjednom — daje Genome-u audit trail I dokazuje da Event Bus (1.1)
ima stvarnog potrošača, ne samo infrastrukturu koja postoji a niko je ne
koristi. Cena: kašnjenje do sledećeg dispatch tick-a (`_DISPATCH_POLL_
INTERVAL_S = 3.0`, `services/event_bus.py:311`) — max 3 sekunde, prihvatljivo
za audit svrhu (ne mora biti trenutno, mora biti pouzdano).

**Migracije:** NEMA. `audit_immutable` tabela već postoji live (S1). Novo
polje u `AUDITABLE_ACTIONS` je Python set literal, ne šema.

**API rizik:** Nula — interno, ništa u javnom ugovoru se ne menja. `log_action()`
već sama hvata sopstvene greške i vraća `None` bez rušenja pozivaoca
(`:75-80`) — ovo je već bezbedno po dizajnu.

**Test strategija:**
1. Unit: trigeruj Genome refresh, ručno pozovi `dispatch_pending_events()`,
   proveri novi red u `audit_immutable` sa `action='genome_refresh'`, tačan
   `resource_id`, `metadata` sa agent/trigger/delta poljima.
2. Integracija: pozovi `verify_chain_integrity()` posle nekoliko genome-
   trigerovanih audit upisa izmešanih sa drugim akcijama (login, upload) —
   hash lanac mora ostati neprekinut (dokazuje da deljeni append-only upis
   nije narušen novim pozivaocem).
3. Regresija: potvrditi da postojeće akcije (login, dokument_upload...) i
   dalje rade nepromenjeno posle dodavanja 2 nova stringa u skup.

**Rollback:** Ukloniti handler registraciju + novi string iz skupa. **NIKAD
ne brisati redove iz `audit_immutable`** čak ni pri rollback-u — tabela je
insert-only po dizajnu (komentar u fajlu), brisanje bi polomilo hash lanac za
sve upise posle. Stari `genome_refresh` redovi ostaju kao neškodljiva istorija.

**Rule C:**
- Pre: 0 audit zapisa za Genome promene.
- Posle: 100% Genome mutacija proizvodi audit red sa svih polja popunjenih
  (ko/kada u kolonama, zašto/agent/pre-posle u metadata) u roku od jednog
  dispatch ciklusa (≤3s).
- Merenje: broj `GenomeUpdated` eventa dispečovanih naspram broja
  `audit_immutable` redova sa `resource_type='predmet' AND action=
  'genome_refresh'` u istom prozoru, cilj 1:1.

---

## 1.3 — Genome Verification Layer (Critic Layer v1, advisory-only)

**Tačni fajlovi:**
- NOVI fajl: `shared/genome_validator.py` (uz `shared/audit_immutable.py`,
  `shared/permissions.py` — isto mesto za cross-cutting logiku van rutera).
- `routers/case_dna.py` — poziv posle `_extract_genome()` a pre snimanja, u
  `refresh_case_dna` i `_run_genome_background`. Rezultat ide u novo polje
  `genome["_verifikacija"]` (underscore-prefiks, isti obrazac kao postojeći
  `_genome_docs_count`) — **advisory, ne blokira save u v1.**
- **Van obima za 1.3:** `static/vindex.js` — nikakva UI izmena. Prikazivanje
  `_verifikacija` korisniku je posebna Rule A/B odluka za kasnije, ne deo
  ovog Rule B posla.

**Ispravka založene pretpostavke (već iz 90-dnevnog plana, ovde precizirano):**
`analiza/validator.py` se NE kopira. Direktno reusable importom, bez izmene
originala:
- `validate_law_refs()` (`analiza/validator.py:289-308`) — radi nad bilo kojim
  `findings`-oblik dict-om sa `law_ref` poljem; Genome-ov `pravna_teorija.
  relevantni_zakoni` treba mali adapter (lista stringova → lista dict-ova sa
  `law_ref` ključem) da bi prošla kroz istu funkciju bez izmene nje same.

Nove funkcije koje MORAJU biti napisane (Genome nema `findings` niz, ima
sopstveni oblik):
- `validate_dokazi_rang(genome, predmet_dokumenti)` — proverava da svaki
  `naziv` u `dokazi_rang` postoji među stvarnim `predmet_dokumenti.naziv_fajla`
  za taj predmet; ako ne, premešta u `_verifikacija.nepodrzano`.
- `validate_kontradikcije_lokacije(genome, predmet_dokumenti)` — proverava da
  `lokacija_1`/`lokacija_2` referenciraju realne DOK-XX brojeve koji postoje.

**Migracije:** NEMA za v1 — `_verifikacija` je novi ključ unutar postojeće
`case_dna` JSONB kolone, nema šema izmene.

**API rizik:**
- `GET .../case-dna` odgovor dobija novo opciono polje u JSON blob-u —
  aditivno, ne bi trebalo da pokvari postojeće konzumente (`static/vindex.js`,
  `multi_agent.py` koji čita ceo Genome kontekst) DOK GOD ništa ne
  pretpostavlja zatvorenu šemu. **Proveriti pre implementacije:** grep
  frontend/`multi_agent.py` za bilo kakvu strogu validaciju/whitelisting
  ključeva Genome objekta koja bi mogla da odbaci nepoznat ključ.
- Rizik lažnih pozitiva (validator flaguje ispravnu tvrdnju kao nepodržanu) —
  zato v1 ostaje advisory/log-only dok bootstrap uzorak (ispod) ne pokaže
  prihvatljivu preciznost.

**Test strategija:**
1. **Prvo** izgraditi bootstrap uzorak (20-30 postojećih Genome izlaza iz
   produkcije + njihovi izvorni dokumenti) — ovo je i test fixture i Rule C
   baseline, isti korak služi obema svrhama.
2. Unit po funkciji: `validate_dokazi_rang` — Genome sa `dokazi_rang` unosom
   koji referencira nepostojeći naziv → mora biti flagovan; validan slučaj →
   ništa flagovano.
3. `validate_law_refs` reuse — unit test sa poznatim zakonskim kodom (ne
   flaguje) i nepoznatim (flaguje), potvrđuje adapter sloj radi ispravno bez
   izmene originalne funkcije.
4. Regresija: `tests/test_hallucination_guard.py` i `test_analiza_validator.py`
   ostaju zeleni nepromenjeni — potvrđuje da import-only reuse ne dira
   originalni fajl.

**Rollback:** Ukloniti pozive iz `case_dna.py` + obrisati novi fajl. Postojeći
`case_dna` redovi sa zaostalim `_verifikacija` ključem su neškodljivi mrtvi
podaci, ista filozofija kao 1.1/1.2.

**Rule C:**
- Pre: pokrenuti bootstrap uzorak PRE pisanja ijedne nove validacione funkcije
  — ovo je korak 0 od 1.3, ne opcioni deo. Broj nepodržanih tvrdnji iz tog
  uzorka postaje stvarna bazna vrednost (founder-ov 40%/25%/15% primer je
  oblik cilja, ne unapred zadata brojka).
- Posle: isti bootstrap metod na novom uzorku iste veličine, uporediti stopu
  flagovanja i ručno potvrđenu preciznost (da li je flagovano zaista bilo
  nepodržano, ili je validator preterao).
- Merenje: ručni/poluautomatski pregled, dokumentovan kao mali ad hoc
  artefakt — može da koristi isti format kao LEC anotacije bez da bude
  zvaničan LEC unos (LEC popunjavanje ostaje founder-ov zaseban 30-dnevni
  zadatak, poslovna traka).

---

## Redosled izvršenja (posle odobrenja ovog checklist-a)

1.1 → 1.2 → 1.3 korak 0 (bootstrap uzorak) → 1.3 implementacija. Svaka
stavka dobija svoj commit, svoj test-run, i svoje Rule C merenje pre nego što
sledeća počne — ne raditi sve tri odjednom u jednom PR-u.
