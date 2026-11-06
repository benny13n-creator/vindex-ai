# MIR002 — specifikacija prihvatanja: procesno stanje za parničnu strategiju

Savetnik „Parnična strategija“ (`POST /api/agents/run`, `agent=litigation`, `predmet_id`; isto i u paralelnoj analizi `POST /api/agents/run-parallel` i u koraku niza `POST /api/agents/pipeline`). Spis je sintetički Golden
Case (`tests/mir001_golden_case.py`). Testovi su u `tests/test_mir002_litigation_procesno_stanje.py`.

**Šta se dokazuje:** ugovor konteksta, odnosno šta server šalje modelu. **Šta se ne dokazuje:** kvalitet odgovora
stvarnog modela (`AI_CONTENT_QUALITY_NOT_LIVE_VERIFIED`). Nijedan test ne ocenjuje odgovor modela po ključnoj reči ni
po oznaci dokumenta.

**Napomena o redosledu:** ova specifikacija je napisana posle merenja u S01 i posle izmene izvora, a pre pokretanja
testova nad izmenom. Slučajevi su izvedeni iz Golden Case-a i iz MIR001 nalaza, ne iz izlaza nove izmene.

## Šta izvor doslovno kaže i šta nije utvrđeno

| Stavka | Izvor | Doslovno | Ne sme se tvrditi |
|---|---|---|---|
| Odluka suda | DOK-07 | „Sud prihvata predlog za dopunu vestacenja.“ | da je dopuna nužna, izvršena, rešena ili bez dejstva |
| Nalog i rok | DOK-07 | „Sud nalaze tuzenom da dostavi gradjevinski dnevnik u roku od 15 dana.“ | početak roka, tok, istek, postupanje po nalogu |
| Navod stranke | DOK-02, DOK-06 | „Tuzeni tvrdi …“ | da je navod utvrđena činjenica |
| Nalaz veštaka | DOK-05 | „Uzrok prokisnjavanja je …“ | „sud je utvrdio“ |
| Dokaz u spisu | DOK-03 | „povratnicu PK-4471“ | da povratnica nedostaje |
| Kasniji dokument | DOK-08 | „rok od 8 dana od dana dopune nalaza“ | da je akter sud (vrsta dokumenta nije prepoznata) |

## Slučajevi

| ID | Ulaz | Očekivano (provera nad porukom modelu) |
|---|---|---|
| P01 | ceo spis | red DOK-07, akter SUD, vrsta kandidat `SUD_PRIHVATA`, doslovan izvod; natpis kaže da su vrsta i akter KANDIDATI; pravila zabranjuju „sud je utvrdio“ i proširenje izvoda |
| P02 | ceo spis | nijedan red iz DOK-01..DOK-06 nema akter SUD; navodi DOK-02/DOK-06 su akter stranke |
| P03 | ceo spis | nijedan red iz DOK-05 nema akter SUD |
| P04 | ceo spis | „PK-4471“ je u tekstu DOK-03 u poruci; nijedan red NIJE UTVRĐENO ne pominje PK-4471; evidencija: DOK-03 pročitan u celini |
| P05 | ceo spis | „NIJE UTVRĐENO: DOK-07: da li rok od 15 dana teče ili je istekao …“; server ne računa datum (nema 30.07.2026); pravilo u sistemskoj poruci: datum dokumenta nije početak roka |
| P06 | + DOK-08 | izvod „od dana dopune nalaza“ je doslovan; server ne računa datum (nema 28.10.2026); akter DOK-08 nije SUD |
| P07 | + DOK-08 | DOK-08 i DOK-07 su odvojeni redovi; „DOK-08: vrsta dokumenta nije utvrđena“; sporne tačke K-01/K-02 ostaju u poruci |
| P08 | DOK-07 uklonjen postojećom rutom | nema izvoda DOK-07; „nema dokumenta prepoznatog kao sudski“ |
| P09 | DOK-07 bez teksta; greška utvrđivanja; preveliki izvod; više od 30 neutvrđenih stavki; obiman podnesak | „mogu sadržati odluke suda: DOK-07“; „procesno stanje nije utvrđeno (greška sistema)“ bez događaja; skraćenje je obelodanjeno po oznaci dokumenta, blok ostaje u granici; upozorenja o roku, uplati, postupanju i nepročitanom spisu prežive granicu od 30 stavki; odluka suda ima prednost u budžetu izvoda (nalazi nezavisnog pregleda F1/F2) |
| P10 | korisnik B, predmet A; red tuđeg korisnika u predmetu | B: nema bloka ni teksta A; tuđ red se ne pojavljuje u bloku, a stanje kaže da je čitanje nepouzdano |
| P11 | uputstvo upisano u dokument | uputstvo je samo unutar granice sa nonce-om; krivotvorena granica i `[[PS-99]]` su neutralisani; sistemska poruka ga ne sadrži |
| P12 | bez predmeta; nepostojeći predmet | nema bloka ni pravila; `kontekst_predmeta` je `null` / `false` (postojeće ponašanje) |
| G | tarifa bez prava | 403, nula poziva modela, nula naplata; uspešan poziv = tačno jedna naplata |
| H | `drafting` | blok i pravila nacrta nepromenjeni; pravila savetnika ne idu u nacrt |
| I | `research` | sistemska poruka i poruka bez bloka i bez pravila savetnika |
| J | `/run-parallel` sa `research`, `litigation`, `intake`; bez predmeta | litigation: isti događaji u bloku kao na `/run`, pravila savetnika u sistemskoj poruci, bez `[[PS-nn]]`; research i intake bez bloka i sa nepromenjenom sistemskom porukom; `_procesno_stanje` ne ide u API; bez predmeta nema bloka |
| K | `/pipeline` `research → litigation → intake`; bez predmeta | korak litigation: isti događaji kao na `/run`, pravila savetnika, bez `[[PS-nn]]`; research i intake bez bloka; bez predmeta nema bloka. `/pipeline` svaki korak izvršava kroz `run_agent` (isti kod kao `/run`), pa izmena koda nije bila potrebna; test je crven pod dve mutacije (isključena litigation grana u `/run`; `procesno` samo za `drafting`) |
