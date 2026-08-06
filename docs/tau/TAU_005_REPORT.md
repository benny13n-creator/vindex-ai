# Mission Report — Program Tau, Master Sprint 005: Court Predictor Canonical Context Reconstruction

**Datum**: 2026-08-06
**Program**: Tau (peti sprint)
**Tim**: 6 imenovanih uloga (Architect, GPT Integration Engineer, Legal Reasoning Engineer, Forensic
Auditor, Performance Engineer, Test Engineer), izvedene kroz 2 paralelna forenzička foreka (Faza 1) +
direktna implementacija (Faze 2-9).

---

## Zatvorenje misije

Cilj: ne novi Court Predictor, ne nove predikcije, ne novi modeli — jedini cilj je da Court Predictor prvi
put ZAISTA analizira predmet kojem pripada. Ovo je prvi sprint koji je u potpunosti posvećen JEDNOM fajlu
(`routers/court_predictor.py`), direktan nastavak `TAU-011` nalaza iz Master Sprint 004 (`predmet_id`
primljen na svih 7 endpoint-a, ali nikad korišćen za dohvat stanja predmeta).

## Otkriveno (Faza 1 — nije pretpostavljeno da je TAU-011 tačan, ponovo dokazano)

2 nezavisna foreka (Forensic Auditor + kombinovana Performance/Legal Reasoning uloga) nezavisno su
rekonstruisala nalaz od nule, ne oslanjajući se na tekst Master Sprint 004. Oba potvrđuju: `TAU-011` važi za
svih 7 endpoint-a, bez izuzetka, bez novog skrivenog puta.

Jedan genuinno nov detalj ove dublje provere: **`judge_profile`-ov request model (`ime_sudije`, `sud`,
`tip_postupka`, `predmet_id`) nema NIJEDNO polje sa opisom predmeta** — strukturno je o sudiji/sudu u
apstraktnom smislu, ne o konkretnom predmetu, isti oblik kao `strategija.py`-ov "bez veze sa predmetom"
nalaz iz Tau 002/003. Ovo je zahtevalo DRUGAČIJI, lakši tretman migracije za taj jedan endpoint.

Ispravka tvrdnje iz prethodnog sprinta: Master Sprint 004-ov `GPT_COST_ANALYSIS.md` je tvrdio da Court
Predictor "ponovo hrani prethodni rezultat `[:8000]` karaktera kroz 3 uzastopna poziva." Direktna
re-verifikacija ovog sprinta je pokazala da je to netačno: svako `[:8000]` odsecanje je za `predictor_analize`
audit-tabelu (upis), nikad za drugi GPT poziv. **Svih 7 endpoint-a poziva GPT tačno jednom.**

Direktnim čitanjem `static/vindex.js` (ne oslanjajući se na pretpostavku) potvrđeno je: glavni "Predikcija
ishoda" UI alat (`stratPokreni()`) NE šalje `predmet_id` uopšte u svom stvarnom, živom pozivu — samo
`battle_report`-ova zasebna funkcija ga uslovno šalje (`activePredmetId`, kad postoji). Ovo je direktno
oblikovalo dizajn migracije ka USLOVNOM obogaćivanju (koristi kanonski kontekst kad je dostupan, sačuvaj
tačno postojeće ponašanje kad nije) — ne prisilnom zahtevu koji bi bio tačan u teoriji, a irelevantan za
5-6 od 7 endpoint-a u njihovom stvarnom saobraćaju danas.

## Popravljeno (Faza 2 — migracija na isključivo `shared/case_context.py`)

Svih 7 endpoint-a sada dohvata stanje predmeta isključivo preko `build_case_context()` (jedan kanonski
izvor), kroz tanak fail-soft omotač `_dohvati_case_context_ako_postoji` (vraća `None` bez `predmet_id`, ili
na grešku — nikad ne ruši poziv) i formatting funkciju `_case_context_blok`:

1. **`prediktuj_ishod`, `battle_report`** — puni režim (`include_documents=True`, stvarni izvodi dokumenata,
   Document Visibility Engine iz Tau 002, ponovo iskorišćen ne re-implementiran). Nova deterministička
   granica: `procenat_min`/`procenat_max` se prisilno spuštaju na 50%/65% kad je kanonski status
   `CRITICAL_GAP`/`BLOCKED` — GPT ne može da nadglasa ovo nikakvom formulacijom u odgovoru (dokazano
   adversarial testom, Faza 5).
2. **`hearing_prep_brief`** — lagani režim + `rociste_potvrdjeno_u_sistemu`: unakrsna provera prijavljenog
   datuma ročišta protiv stvarnih `rocista` redova.
3. **`argument_reputation`** — lagani režim, argumenti koji se oslanjaju na nedostajuće dokaze dobijaju nižu
   `uspesnost_procena`.
4. **`judge_profile`** — najlakši tretman (bez case-description polja): `sud_neslaganje_sa_predmetom` —
   unakrsna provera prijavljenog suda protiv kanonskog suda predmeta.
5. **`opponent_intel`** — lagani režim, DODAT uz postojeću (ne zamenjenu) cross-portfolio pretragu po imenu
   protivnika — dva genuinno različita signala, oba zadržana.
6. **`confidence_check`** — `_calc_confidence_nivo` proširen opcionim `readiness_status` parametrom koji
   ZAMENJUJE (ne dodaje) postojeće `dokazi_count` pravilo kad je dostupan — `_CONFIDENCE_MAX_SCORE` namerno
   ostaje konstanta 9, čuvajući DC-004 invarijantu (nivo i procenat moraju poticati iz istog skora).

Uz to, `_rag_praksa_blok` sada vraća `tuple[str, list[dict]]` — tekst blok PLUS stvarna lista pronađene
prakse. Novo `koriscena_praksa` polje na `prediktuj_ishod`/`battle_report` iskreno prijavljuje šta je STVARNO
pretraženo/pronađeno (ne traži od GPT-a da samo-citira, izbegavajući nov halucinacijski problem) —
zatvara `TAU-014`.

## Dokazano

**21 novi test** (`tests/test_tau005_court_predictor_migration.py`), uključujući zastavnički adversarial
test: otrovani GPT odgovor tvrdi 85-95% dok je kanonski status CRITICAL_GAP — asertovano da se i
`procenat_min` i `procenat_max` prisilno spuštaju na 50, bez obzira šta GPT tvrdi. Concurrency test (2
paralelna predmeta različitog statusa ne kontaminiraju jedan drugog) i replay test (identičan poziv dvaput
daje identičan rezultat) takođe prolaze — Faza 9 zahtevi.

**Kompletnost migracije (Faza 7)**: pun `supa.table()` inventar cele datoteke, red-po-red klasifikovan —
nula preostalih pojedinačnih (single-case) bespoke dohvata konteksta bilo gde u fajlu. 2 namerna izuzetka
(cross-portfolio pretraga u `opponent_intel`, firm-wide agregacija u `confidence_check`) potvrđena kao
genuinno drugačiji oblik signala, ne previđeni zaobilazak.

**Regresija**: 0. Puna test suita: **2.875 passed, 1 skipped, 0 failed** (bilo 2.854 na kraju Master Sprint
004 — tačno +21, poklapa se sa novim fajlom testova).

**Kontekst-sertifikacija (Faza 3)**: 10 od 13 stavki sa liste misije sertifikovano za
`prediktuj_ishod`/`battle_report` (Genome, Dokumenti, Dokazi delimično, Kontradikcije, Nedostajući dokazi,
Rokovi, Radnje predmeta, Spremnost strukturno primenjena, Stranke, Ročišta, delimično Sud). OCR metapodaci i
strukturirani podaci o sudu NE postoje nigde u kanonskom ugovoru (`TAU-013`, van obima ovog sprinta) —
imenovano, ne prećutano.

**Troškovi (Faza 6)**: procenjeno mesečno ≈$42-48 (bilo ≈$40), povećanje skoncentrisano u 2 endpoint-a sa
punim kontekstom. Razmotreno i ODBAČENO: lagani režim za `prediktuj_ishod`/`battle_report` — dokazna snaga
je centralna za njihov zadatak, gubitak kvaliteta je izričito zabranjen Fazom 6.

## Zatvoreni dug

- **`TAU-011`** (Critical) — ZATVOREN. Svih 7 endpoint-a migrirano na isključivo `build_case_context()`.
- **`TAU-014`** (Medium) — ZATVOREN. `koriscena_praksa` polje implementirano tačno po originalnoj preporuci.
- **`TAU-012`** (High) — AŽURIRAN. Broj revidiran sa 17+ na 16+ (court_predictor.py više nije u zaostatku).

## Odloženo

`TAU-012` (16+ preostalih fajlova, van obima ovog sprinta po eksplicitnoj instrukciji — "ne mešati sa
drugim migracijama"), `TAU-013` (OCR metapodaci i strukturirani podaci o sudu i dalje ne postoje nigde u
kanonskom ugovoru — proširenje ugovora je zaseban zadatak), `TAU-015`, `TAU-016` (nepromenjeni, van obima).

## Zaključak

Court Predictor sada prvi put zaista analizira predmet kojem pripada — kad taj predmet postoji u sistemu.
Migracija je uslovna po dizajnu (ne prisilna), jer je stvarna živa upotreba (potvrđena čitanjem frontend
koda, ne pretpostavljena) pretežno bez `predmet_id`-a za 5 od 7 endpoint-a. Deterministička granica na
procentu pobede je konkretan, testiran, adversarial-otporan mehanizam — ne samo prompt instrukcija — koji
sprečava GPT da tvrdi neosnovanu sigurnost. Nijedan novi context builder, wrapper, ili predictor nije
napravljen; migracija je potpuna, dokazana inventarom, bez zaobilaska. Sledeći korak nije nasumičan nastavak
na preostalih 16+ fajlova — vidi `TAU_006_HANDOVER.md`.
