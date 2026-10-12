# VCR002 — glavno stanje programa

**Grana i stanje:**
- grana: `program/vcr002-beta-operational-closure`;
- Draft PR **#20**;
- osnova `main` = produkcija **`b36235a3`**, potvrđeno na `/health`.

**Ništa nije spojeno ni pušteno:**
- nema migracija ni promena tajni;
- nema Cron-a ni promena cena;
- nema plaćenih poziva modela;
- nije poslat nijedan email ni SMS.

## Zadaci

| Zadatak | Status | Najviši nivo dokaza | Commit |
|---|---|---|---|
| T00 osnovica | `PASS_LIVE` | LIVE (javni ugovor, `/health`) + CI | `514d0f24` |
| T01 prijavljena QA sesija | `BLOCKED_AUTHENTICATION` | — | `514d0f24` |
| T02 OCR / Smart Intake | `PASS_ISOLATED` (produkciona slika); LIVE `BLOCKED_AUTHENTICATION` | ISOLATED | `514d0f24` |
| T03 Bojanov tok sa više dokumenata | `PASS_ISOLATED` + `FIX-T03-1` | ISOLATED | `4a51a2c8` |
| T04 podsetnici (B10) | `PASS_IMPLEMENTED` (kod); isporuka `BLOCKED_AUTHORITY` | ISOLATED | `ed6e1431` |
| T05 paralelni savetnici | `PASS_IMPLEMENTED` | ISOLATED | `86fa7e5e` |
| T06 niz savetnika | `PASS_IMPLEMENTED` | ISOLATED | `fbd5b24c` |
| T07 savetnici u V2 | `PASS_IMPLEMENTED` | BROWSER_INTEGRATION (pravi `api.app`) | `aabbff26` |
| T08 V1 → V2 paritet | `PASS` (presude) | — | `aabbff26` |
| T09 autonomija | `PASS_ISOLATED` / `BLOCKED_AUTHORITY` | ISOLATED (pravi PostgreSQL) | `aabbff26` |
| T10 zahtevi | Bojan: vidi `VCR002_REQUIREMENTS_STATE.md`; Miroslav `BLOCKED_REQUIREMENTS_SOURCE` | ISOLATED | `aabbff26` |
| T11 integraciona kapija | vidi `VCR002_RELEASE_HANDOFF.md` | CI + BROWSER_INTEGRATION | — |
| **RC FIX 1** integritet brisanja dokumenta | `PASS_ISOLATED` (ruta + pravi PostgreSQL 17); migracija 137 **nije primenjena** | ISOLATED | `80dc114e` |
| **RC FIX 2** oporavak plaćenog niza | `CLOSED_BY_DISABLE`: postojeća infrastruktura ne može da uskladi plaćen rad, pa je ulaz u V2 isključen | ISOLATED + BROWSER_INTEGRATION | `a1468152` |
| **RC FIX 3** AI tvrdnje i protivrečnosti u pravnom pitanju | `PASS_ISOLATED` | ISOLATED | `056a48e6` |

## Ispravljeni proizvodni kvarovi (svi sa reprodukcijom, negativnom kontrolom i regresijom)

1. **`FIX-T03-1`:** obrisan dokument je ostavljao svoje AI tvrdnje aktivne. Ulazile su u Genome, kontekst pitanja i Analizu.
2. **`FIX-T04-1`:** dva potvrđena roka istog dana u istom predmetu, pa podsetnik nikad nije poslat, a izveštaj je tvrdio „preskočeno“.
3. **`FIX-T04-2`:** predmet u brisanju je slao podsetnik.
4. **`FIX-T04-3`:** SMS cron je svaki dan prijavljivao uspeh, a server je odgovarao 401.
5. **`FIX-T05`:** paralelni savetnici su bili bez provere citata, kontekst tuđeg predmeta je tiho postajao opšti, sirova greška provajdera je išla klijentu, budžet se nije proveravao pre poziva, dupli savetnik se plaćao dvaput, a pogrešan tip je davao 500.
6. **`FIX-T05-1`:** izuzet „opšte poznat“ član je prikazivan kao „potvrđen u pravnoj bazi“ i bez ijednog izvora. Kvar je iz VCR001 i važio je i za `/run`.
7. **`FIX-T06`:** u nizu savetnika izlaz prethodnog koraka je ulazio bez granice poverenja; provere citata nije bilo; zaštita od ponavljanja je bila samo keš procesa; sirova greška je išla klijentu.
8. **Opis predmeta** ulazio je u prompt savetnika bez granice poverenja (i za `/run`).
9. **RC FIX 1:** brisanje dokumenta je prijavljivalo uspeh i kad AI tvrdnje nisu povučene (`tvrdnje_povucene: -1`). Pad posle brisanja reda ostavljao ih je trajno aktivne i bez veze sa izvorom.
10. **RC FIX 2:** pad radnika usred plaćenog niza gubio je plaćen rad, a nova radnja ga je ponovo naplaćivala. Niz je isključen u V2.
11. **RC FIX 3:** pravno pitanje je AI tvrdnje slalo kao „Utvrđene činjenice“, a protivrečne bez oznake.

## Odluke osnivača (detalji u `VCR002_RELEASE_HANDOFF.md` §15)

QA nalog · puštanje kandidata · `CRON_SECRET`/`CRON_TOKEN` i test primalac · SMS cron (prihvatiti cron ključ ili ugasiti posao) · migracija 136 i autonomija · pilot predmet · Miroslavljev izvorni dokument · strategija/prediktor/šabloni · migracija 137 · trajna evidencija koraka niza (za ponovno uključenje). **Kandidat za puštanje: `056a48e6`.**
