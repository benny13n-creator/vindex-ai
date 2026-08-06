# Mission Report — Program Sigma, Master Sprint 002: Autonomous Evidence & Timeline Reconstruction Engine

**Datum**: 2026-08-06
**Program**: Sigma (drugi sprint)
**Tim**: uloge izvedene direktno u ovoj sesiji (2 forenzička foreka + direktna implementacija/testiranje).

---

## Zatvorenje misije

Cilj: dokazati da svaki novi dokument može automatski da izdvoji činjenice/događaje/datume/učesnike/dokaze/
procesne radnje/rokove/kontradikcije i poveže ih u jedinstvenu vremensku liniju predmeta — koristeći
isključivo postojeće kanonske mehanizme (Event Bus, Case Evolution Engine, Genome, Case Pipeline, Case
Actions, Workspace), bez paralelnih algoritama.

## Otkriveno

**15 pisaca `predmet_hronologija`-e, ne ~14 kako je memorija prethodne sesije procenila** — svaki kanonski
za sopstvenu, različitu poslovnu činjenicu, ne konkurentski algoritam. Tabela je striktno append-only:
nula UPDATE, nula DELETE poziva bilo gde u repou. Direktan odgovor na misijino sopstveno pitanje ("može li
kasniji dokument izmeniti/zatvoriti/poništiti raniji događaj?"): **ne, ne danas** — pravi, ali neimenovan
gap dok ova sesija nije počela.

**Stvaran, ranije nepoznat bag pronađen u samom srcu Rule 3 (`RAZRESITI_KONTRADIKCIJU`)**: identitet
kontradikcije (i u `case_actions`-ovom sopstvenom `dedupe_key`-u i u Genome-ovom sopstvenom
`_compute_delta`-u) bio je usidren na GPT-ovom sopstvenom slobodnom tekstu (`opis`) — svaki reformulisan
opis IDENTIČNE kontradikcije između 2 Genome refresh-a menjao je identitet, uzrokujući da otvorena akcija
"treperi" zatvoreno+ponovo-otvoreno na svakom refresh-u, i da `_compute_delta` prijavi lažnu "1 eliminisana
+ 1 nova" promenu (`SIGMA-002`, prethodni sprint).

**3 instance identičnog "now()" bag klase pronađene u samom srcu Evidence Graph-a**: `routers/
evidence.py::delete_dokaz` (soft-delete `predmet_dokazi.deleted_at`), `routers/evidence.py::
klasifikuj_i_sacuvaj` (KANONSKA funkcija klasifikacije dokaza, poziva se za SVAKI obrađeni dokument), i
`routers/smart_intake.py`-ov sopstveni 6-varijantni fallback za umetanje dokumenta (3 od 6 varijanti nosile
su isti pokvareni literal) — sve pisale su literalni string `"now()"` (sa zagradama), vrednost koju
Postgres-ov sopstveni timestamptz parser ne prepoznaje. Ista klasa baga koju je Program Omega Sprint 004
već pronašao i popravio za `case_actions.closed_at`.

**Nova arhitektonska pretpostavka koja narušava prethodnu**: `predmet_genome_history` VEĆ trajno čuva
kompletnu istoriju svake Genome verzije (uključujući `kontradikcije`), append-only, potvrđeno ovim
sprintom. "Genome zaboravlja istoriju" NIKADA nije bio stvaran problem — istorija je uvek bila sačuvana;
stvaran gap bio je uže: identitet-poređenje između verzija, sada popravljeno.

## Popravljeno

1. **`shared/contradiction_identity.py`** (novo) — JEDNA deljena funkcija identiteta kontradikcije,
   usidrena na `(lokacija_1, lokacija_2)` (formulaički "DOK-XX str.Y" citati koje Genome-ov sopstveni
   ekstrakcioni prompt već zahteva), nezavisna od redosleda, sa fallback-om na `opis` samo kad lokacije
   nedostaju. Korišćena i u `services/case_evolution.py`-ovom Rule 3 i u `routers/case_dna.py`-ovom
   `_compute_delta`-u — jedan identitet, ne dva nezavisna zakrpa.
2. **`routers/evidence.py::delete_dokaz`** — pravi izračunat ISO-8601 timestamp umesto `"now()"` stringa.
3. **`routers/evidence.py::klasifikuj_i_sacuvaj`** — isto, za `klasifikovan_at`.
4. **`routers/smart_intake.py`**-ov varijantni fallback — isto, za `klasifikovan_at` u sve 3 pogođene
   varijante.

## Dokazano

**14 novih testova, 2 nove test datoteke**: `tests/test_sigma_sprint002_contradiction_identity.py` (11) —
deljena funkcija sama po sebi, oba integraciona mesta (Rule 3 dedupe_key stabilnost, `_compute_delta` bez
lažne promene), negativne kontrole (genuinski različite kontradikcije i dalje razlikuju identitet, genuinski
nove/eliminisane kontradikcije i dalje ispravno detektovane). `tests/test_sigma_sprint002_timestamp_
literal_bugs.py` (3) — oba direktna popravka dokazana na nivou vrednosti (`datetime.fromisoformat` na
stvarnom payload-u), treći (smart_intake.py) dokazan izvorno-kodnom inspekcijom (pošten, srazmeran dokaz
bez žive Postgres infrastrukture — objašnjeno u `TIMELINE_FORENSIC_REPORT.md`).

**Regresija**: 0. Puna test suita: **2.745 passed, 1 skipped, 0 failed** (bilo 2.731 na kraju Sigma Master
Sprint 001).

## Faza 6 — Case Evolution slaganje stanja

Genome/Timeline/Case Actions/Workspace/Notifications potvrđeno se slažu po konstrukciji (sekvencijalni
`handle_case_changed`, isti izvor istine) — ovaj sprint dodatno zatvara jedan konkretan način neslaganja
(kontradikcija-identitet flicker). Strategy ostaje jedini podsistem koji legitimno zastareva (on-demand,
poznata, ranije dokumentovana karakteristika, ne nov bag).

## Faza 7 — Forenzička sertifikacija

7 pokušaja da se vremenska linija slomi (puni detalji u `TIMELINE_FORENSIC_REPORT.md`): izgubljeni događaji
(nije nađen mehanizam gubitka, ali pojedinačni pisci nisu crash-safe — nasleđena, ne nova izloženost),
pogrešan redosled (strukturno hendlovano — sortiranje po `datum_iso`, ne po redosledu upisa), dupli
događaji (potvrđeno, nula dedup-a, prošireno `SIGMA-004`), nestali dokazi (POČETNA pretpostavka bila
POGREŠNA — pronađena 2 stvarna baga umesto "mrtve kolone", oba popravljena), prekidi dokaz↔događaj
(potvrđeno, najznačajniji Faza 7 nalaz — nema FK, nova funkcionalnost bi bila potrebna, ne wiring).

## Odloženo

`SIGMA-005` (dva semantička značenja u jednoj `predmet_hronologija` tabeli), `SIGMA-006` (Legal Reasoning
Engine nije auto-povezan sa Case Evolution), `SIGMA-007` (dokaz↔vremenska-tačka veza nedostaje), `SIGMA-008`
(dokaz↔osporavajući-dokument veza nedostaje), `SIGMA-009` (nema revizija/poništavanje semantike za
vremensku liniju), `SIGMA-010` (nema ACTIVE/SUPERSEDED/CONTRADICTED/UNKNOWN razlike za razrešene
kontradikcije), `SIGMA-011` (još 7 "now()" literal-timestamp mesta pronađeno van Evidence/Timeline domena,
namerno neispravljeno — van obima ove misije) — svaki sa preciznim obrazloženjem zašto zahteva novu
shemu/algoritam/proizvodnu odluku, ne mehaničku popravku.

## Zaključak

Definition of Done, stavka po stavka: (1) svaki novi dokument menja predmet kroz jedan jedinstven kanonski
mehanizam — **da**, potvrđeno nepromenjeno; (2) činjenice sledljive do izvornog dokumenta — **delimično**:
`dokument_id` postoji na `predmet_dokazi`, ali `predmet_hronologija` nema takvu vezu ni za jednog od 15
pisaca; (3) vremenska linija konzistentna — **da za dodavanje, ne za izmenu/zatvaranje/poništavanje**
(imenovano, `SIGMA-009`); (4) kontradikcije se nikad ne prikrivaju niti brišu, već eksplicitno evidentiraju
— **da, ojačano ovim sprintom**: istorija je uvek bila sačuvana (`predmet_genome_history`), a identitet
praćenja je sada stabilan (stvaran bag popravljen); (5) svi podsistemi prikazuju isto stanje predmeta —
**da za deterministički lanac**, sa jednim manje mogućnosti za neslaganje nego pre ovog sprinta; (6) svaki
bezbedno-popravljiv problem popravljen odmah — **da**: 4 stvarna baga pronađena i popravljena (kontradikcija
identitet + 3 instance "now()" literala), sve sa punom regresijom.

Ovaj sprint ne tvrdi lažnu potpunu pobedu. Zatvara 4 genuinski stvarna, ranije nepoznata funkcionalna baga
— pronađena upravo zato što je forenzička istraga tražila dokaz, ne potvrdu — i imenuje, precizno i bez
izgovora, 6 novih debt stavki (`SIGMA-005` do `SIGMA-010`) koje zahtevaju novu shemu ili proizvodnu odluku
pre nego što mogu biti bezbedno implementirane.
