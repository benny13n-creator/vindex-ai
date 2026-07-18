# Case Genome Level 5 — Alignment (2026-07-18)

Ovo NIJE novi audit i NIJE novi roadmap. Autoritativna osnova ostaje:
`VINDEX_AI_ARCHITECTURE_BIBLE_v1.0.md`, `CASE_GENOME_GAP_ANALYSIS_2026-07-18.md`,
`VINDEX_AI_90_DAY_EXECUTION_PLAN_2026-07-18.md`,
`PHASE_1_EXECUTION_CHECKLIST_2026-07-18.md`. "Level 5" iz ovog dokumenta je
dugoročni ciljni okvir (11 modela + 4 sposobnosti iz Level 5 master prompt-a),
korišćen samo kao sočivo za mapiranje već postojećih odluka — ne kao razlog
za novu arhitekturu. Nijedna stavka ispod ne menja Fazu 1-3 iz 90-dnevnog
plana; jedno malo zapažanje je označeno u sekciji 5 kao razmatranje, ne kao
promena obima.

---

## 1. Koji postojeći Faza 1/2/3 zadaci direktno pomeraju Genome ka Level 5

| Zadatak (iz 90-dnevnog plana) | Level 5 sposobnost/model koji pogađa | Kako |
|---|---|---|
| 1.1 Event Bus → Genome wiring | **Autonomous Updating** + osnova za **Case State Machine** | Svaki Genome update postaje detektabilan događaj — preduslov za "sistem detektuje šta se promenilo i šta treba da se preračuna", ne samo da se Genome ručno osveži |
| 1.2 Genome Audit Trail | **Audit Model** (direktno, jedan od 11 imenovanih modela) + **Complete Explainability** | Ko/kada/zašto/koji agent/pre-posle za svaku promenu — tačno ono što Level 5 traži pod "svaki zaključak zahteva provenance" |
| 1.3 Genome Verification Layer (advisory) | **Controlled Autonomy** + **Complete Explainability** | Level 5 eksplicitno zabranjuje "silently change critical legal conclusions" i "hide uncertainty" — advisory, non-blocking validator koji flaguje nepodržane tvrdnje umesto da ih tiho prihvati je direktna implementacija tog principa, ne buduća ideja |
| 2.1 Smart Intake finalize instrumentacija | **Controlled Autonomy** (definiše gde je granica) | Meri da li advokati žele kontrolnu tačku ili punu automatizaciju — ovo JESTE pitanje "šta sistem sme da radi bez čoveka", samo mereno umesto pretpostavljeno |
| 2.2 Sitni dug (prefix fix, helper konsolidacija) | Podržava **Rule 5: Reliability beats complexity** (iz Level 5 master prompt-a) | Indirektno — smanjuje tehnički dug koji bi otežao bilo koju buduću Level 5 nadogradnju |
| 3.1 Data ingestion reliability | **Persistent Understanding** (temelj za pouzdano znanje) | Pogađa RAG/pravno istraživanje, ne Genome ekstrakciju direktno (već objašnjeno u 90-dnevnom planu) — i dalje relevantno za Level 5 jer "understanding" uključuje pravni kontekst, ne samo dokumenta predmeta |

**Zaključak sekcije 1:** sva tri zadatka Faze 1 nisu slučajno usklađena sa
Level 5 — ona SU minimalni, dokazano-niskog-rizika koraci ka tačno onim
sposobnostima koje master prompt traži (Audit Model, Explainability,
Controlled Autonomy). Ovo je razlog da se ne pravi paralelan plan: postojeći
plan već ide u tom pravcu, samo bez tog imena.

---

## 2. Koje Level 5 sposobnosti su već delimično implementirane

Direktno iz `CASE_GENOME_GAP_ANALYSIS_2026-07-18.md` i Bible Deo III, mapirano
na Level 5 rečnik:

| Level 5 model/sposobnost | Stanje | Dokaz |
|---|---|---|
| Fact Model | Delimično — ravna lista, ne graf | `case_dna.py` polja, Fact Graph odsutan (Bible Deo VI) |
| Evidence Model | Delimično | `dokazi_rang`, `evidence.py`, nema audit trail/human-override po dokazu |
| Timeline Model | Delimično | `intelligence_timeline.py` + `datumi_kljucni`/`rokovi_kriticni` |
| Legal Reasoning Model | Delimično | `pravna_teorija` blok, jedna teorija ne alternativne |
| Strategy Model | **Implementirano** (funkcionalno) | `strategija.py` 7 endpoint-a + genome `strategija` blok |
| Risk Model | Delimično, solidno pokriveno | `matter_intel.py` 5-dim semafor, `najslabija_tacka` |
| Action Model | Delimično | `_compute_next_action`, nema task-objekat (assignee/rok) |
| Learning Model | Delimično, znatno | `learning.py` 1195 linija — outcome/counterfactual/lessons/firm_dna, ali odvojeno od Genome-a (SST kršenje) |
| Audit Model | **Odsutno za Genome danas** — postaje delimično posle 1.2 | `audit_immutable.py` postoji kao primitiv, nije povezan na Genome pre Faze 1 |
| Version History | Delimično, više od očekivanog | auto-increment `verzija` + `predmet_genome_history`, nema rollback |
| Case State Machine | **Odsutno u potpunosti** | Nema eksplicitan state-machine model nigde u kodu — Genome ima verziju i polja, ne formalna stanja/tranzicije |

---

## 3. Koje Level 5 sposobnosti su namerno odložene

Iz Bible Deo X, Track 2 (Rule A — čeka dokaz), sada eksplicitno mapirano na
Level 5 rečnik:

- **Case State Machine** (formalna stanja + tranzicije, ne samo verzija broj)
- **Impact Propagation** — inkrementalno preračunavanje umesto punog
  regenerate-a (danas: svaki refresh je pun re-generate)
- **Fact Graph** — tipizirani Fact→Evidence→Claim→Argument→Rule→Risk lanac
- **Critic Layer kao blocking gate** (1.3 u Fazi 1 je advisory-only po dizajnu
  — pravi "blokira save dok se ne potvrdi" gate je odložen)
- **Version restore/rollback** (istorija je danas read-only)
- **Cross-module Genome wiring** za Firm DNA, Red Team, Digital Twin (danas
  žive kao odvojeno stanje, kršeći SST princip)
- **Internal Agent Registry sa tipiziranim kontraktima** (danas: 6 slobodnih
  prompt-ova + ruter, bez šeme)

Ovo nije "nikad" — ovo je "ne dok dokaz ne postoji", u skladu sa Rule A.

---

## 4. Koja buduća unapređenja zahtevaju dokaz pre implementacije

Ista lista kao sekcija 3 (odloženo = čeka dokaz su isti skup po Rule A) plus
jedan dodatni: **puna Legal Reasoning alternativa-teorija podrška** (Genome
danas ima jednu teoriju, ne alternativne). Sve stavke čekaju jedan od četiri
izvora: LEC, Hall of Shame, Office Accuracy Dashboard, stvaran korisnik/pilot.

Status izvora na 2026-07-18 (iz gap analize, nepromenjeno otkad je poslednji
put provereno): `evaluation/lec/annotations.json` i
`evaluation/hall_of_shame/incidents.json` prazni. Nijedna od stavki u sekciji
3 trenutno nema dokaz koji bi je otključao za Track 2 rad.

---

## 5. Da li neki trenutni Faza 1 zadatak treba da se prilagodi

**Ne menja se obim.** Jedno zapažanje vredno beleženja, bez akcije sada:

`1.1`-ov novi `EventType.GENOME_UPDATED` je jedan generički event tip. Ako
se Case State Machine ikad prioritetizuje (sekcija 3, čeka dokaz), koristio
bi razlikovane tranzicije (npr. `predmet_kreiran → dokumenti_prikupljeni →
analiza_zavrsena`), ne jedan flat event. **Predlog bez promene obima:** kad se
1.1 implementira, uključiti `trigger` (upload/ročište/manual — vrednost koja
već postoji u `case_dna.py`-jevoj `_TRIGGER_LABEL` mapi) u event `payload`,
ne samo u audit `metadata` (1.2). Ovo je nula dodatnog rizika/posla u 1.1 samog
po sebi (polje već postoji, samo se dodaje u već postojeći insert), a
sprečava da se `events` tabela mora naknadno re-populisati ako State Machine
rad ikad počne. Ne zahteva odobrenje van postojećeg 1.1 checklist-a — ovo je
detalj implementacije 1.1, ne nova stavka.

Van ovoga: nijedan Faza 1/2/3 zadatak ne treba da se doda, ukloni, ili
reordinira zbog Level 5 okvira. Postojeći redosled (1.1 → 1.2 → 1.3, zatim
Faza 2, zatim Faza 3) ostaje.

---

## Zaključak

Level 5 master prompt ne otkriva rupu u postojećem planu — potvrđuje ga.
Sve što taj prompt traži kao "prvo uradi audit i roadmap" već postoji,
verifikovano naspram živog koda, ne naspram dokumentacije. Sledeći korak
ostaje ono što je već bio pre ovog dokumenta: pregled i odobrenje
`PHASE_1_EXECUTION_CHECKLIST_2026-07-18.md`, zatim implementacija 1.1 → 1.2 →
1.3.
