# Bojan BA-01 — acceptance i closure ledger

Izvor zahteva: osnivačev ugovor „OPERATION BOJAN BA-01“ (2026-10-30), deo II, BA-01…BA-08 — prenet doslovno u sažetku ispod.
Dokument „VINDEX — CANONICAL OPERATING RULES“ nije u repozitorijumu; na njega upućuje `VINDEX_V2_FOUNDER_EXECUTION_DIRECTION.md`.
Prethodni dokaz: `BA-GOLDEN-01-EVIDENCE/` (lokalno, van repozitorijuma; sintetički podaci).

## Osnovica (Task 0)

| Stavka | Vrednost |
|---|---|
| `origin/main` | `16a8831e1be8816abf74f18852724ee29dae0a2b` (Merge PR #60) |
| Produkcija `/health` | `commit: 16a8831` (2026-10-30) |
| CI na osnovici | 11/11 success (GitHub check-runs) |
| Grana | `bojan/ba01-intake-integrity` iz `origin/main`, čist worktree |

## BA-01…BA-08 (sažetak ugovora)

| BA | Zahtev |
|---|---|
| BA-01 | jedan klijent, jedan predmet, opis i cilj sačuvani; bez duplog predmeta na retry |
| BA-02 | digitalni PDF, sken PDF, PNG/JPG, DOCX u nameravani predmet; stvaran OCR; neuspeo OCR nikad kao uspešno čitanje |
| BA-03 | broj predmeta, sud, stranke, iznos i činjenice odgovaraju izvoru; nesigurno ostaje nesigurno; bez izmišljenog izvora |
| BA-04 | procesni događaji dostupni advokatu u hronološkom toku predmeta, sa datumom, izvorom i oznakom nesigurnosti; „Dokument prihvaćen“ nije dokaz |
| BA-05 | svaki jasno dokazan rok kao zaseban kandidat; običan datum nije rok; nema duplog kandidata za ISTU obavezu; različite obaveze se ne spajaju zbog datuma, dokumenta ili kategorije |
| BA-06 | AI rok `UNCONFIRMED` do potvrde; samo potvrđen je izvršiv; odbijanje ostaje; potvrda/ispravka/retry/ponovna obrada ne kvare odluku |
| BA-07 | ispravan podsetnik za izvršive obaveze; odbijeno/nepotvrđeno nikad; retry, neuspela isporuka i dedup istiniti; real inbox NIJE odobren |
| BA-08 | nov dokument obogaćuje ISTI predmet; bez duplih dokumenata/obaveza/lažnih unosa hronologije; ispravke ostaju; izolacija korisnika |

## Zatvaranje po zadacima

| Task | Stanje | Dokaz |
|---|---|---|
| 0 | PASS | ova tabela; CI osnovice 11/11 |
| 1 | PASS | reprodukcije A/B/C/D na osnovici (sud „… Posl“ 0.90; „dinara“; Genome 9 kandidata za 3 obaveze; događaji samo u Analizi) |
| 2 | PASS | `e0cdfe48` — `tests/test_ba01_ekstrakcija.py` |
| 3 | PASS | `cb984b6e` — isti fajl, iznos kao Decimal + valuta |
| 4 | PASS | ugovor identiteta (klasa = izvorni dokument + datum, ograničena dokazom iz teksta; nerazrešen izvor = tačan tekst) |
| 5 | PASS | `e4458b5c` — `tests/test_ba01_rok_identitet.py`, 8/8 mutacija ubijeno |
| 6 | PASS | `7060c591` — `tests/test_ba01_vise_rokova.py` (stvaran OCR), 7/7 mutacija ubijeno |
| 7 | PASS | `533fd80c` — `tests/test_ba01_procesna_hronologija.py`, `frontend-v2-ng/tests/live-ba01-hronologija.mjs` 37/37 |
| 8 | PASS (izolovano) | `bd0cb491` — lokalni SMTP, stvaran lanac odluka; svita podsetnika 240/240 sa PostgreSQL 17 |
| 9 | PASS | `0e117238` — zlatni slučaj D (stvaran OCR); stvaran model 3 varijante: 0 duplikata, 0 običnih datuma kao rok |
| 10 | u toku | puna svita: isti 9 padova kao osnovica (po ID-ju); CI i Draft PR |

Nije dokazano ovim sprintom: produkcioni E2E, stvarna isporuka emaila (pauza nepromenjena), Bojanovo prihvatanje.
Postojeći dupli Genome predlozi u produkciji ostaju (nijedan produkcioni red nije menjan); nov kod ih ne umnožava.

## BA05 — identitet obaveze (PR #61 završna kapija → korekcija)

Kapija PR61 (2026-10-30) je oborila presudu `READY_FOR_CONTROLLED_LIVE_TEST`: brojni identitet klase je tiho gubio
obaveze — (A) dva različita `scan.pdf` istog datuma, (B2) Genome A pa B u sledećem osvežavanju; (B1) dve parafraze A
„punile“ su klasu. Dodatno nađeno: nastavak prekinutog prikačivanja preskakao je rokove (drugi rok trajno izostajao).

| Stavka | Stanje |
|---|---|
| Identitet | `obaveza_kljuc` = sha256(heš teksta dokumenta, datum, dokazna fraza iz teksta) — `shared/rokovi.kljuc_obaveze`; nikad tekst modela, naslov, ime fajla ni broj redova |
| Šema | migracija 144: kolona + `UNIQUE (predmet_id, obaveza_kljuc) WHERE obaveza_kljuc IS NOT NULL` + CHECK oblika; zatečeni redovi NULL; **NIJE primenjena na produkciju** (pre spajanja, osnivač) |
| Smart Intake | rokovi posle upisa dokumenata (tekst + heš poznati), i na nastavku; ključ umesto imena fajla |
| Genome | 1 dokazana obaveza datuma → stavke modela su ona; ≥ 2 → svaka dokazana obaveza sa citatom iz izvora; 0 → jedan AI predlog po (dokument, datum); nerazrešen izvor → tačan tekst (N03-FD2) |
| Testovi | `tests/test_ba05_identitet_obaveze.py`, `tests/test_ba05_migracija_144_postgres.py` (pravi PostgreSQL, trka dva procesa); 9/9 mutacija ubijeno |
| Kolizija izvora (2026-10-30) | ista vrsta i datum u ISTOM dokumentu, različit subjekat („Za tužioca rok za …“ / „… ističe D za tuženog“) → fraza je odsecala subjekat pre „rok za“ i nije gledala deo reda posle datuma → isti ključ, druga obaveza tiho nestajala (dokazano na `04b38efd`). Fraza = ceo red (pre datuma, bez zatvorene oznake odeljka „POUKA O PRAVNOM LEKU:“, + posle datuma do kraja reda/sledećeg datuma); `KLJUC_VERZIJA` BA05v2 (144 nigde primenjena — nema zatečenih v1 ključeva). Ista obaveza dvaput (isti red) = 1; subjekat u DRUGOM redu (naslov iznad) = nerešiva dvosmislenost teksta, ostaje granica |
