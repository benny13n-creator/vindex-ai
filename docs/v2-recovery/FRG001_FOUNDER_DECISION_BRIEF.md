# FRG001 — odluka za osnivača

**Preporuka: USLOVNI GO.** Oba poslednja blokatora su zatvorena kodom i testovima koji padaju bez ispravke. Ništa nije spojeno ni deployovano.
Oznake: **P** dokazano · **I** zaključeno · **U** nepoznato.

## A. Integritet dokumenta (BETA-DEF-004) — **PASS**
| Pitanje | Odgovor |
|---|---|
| Da li je reprodukovano? | **Da (P).** Pad upisa događaja posle upisa dokumenta: odgovor 200, posao „prikačen“, dokument trajno bez dokaza. Ni ponovni pokušaj to nije menjao. |
| Može li se nepotpuno stanje otkriti? | **Da (P).** Posao ostaje neprikačen (V2 opet nudi „Prikači“), a dokument se u analizi prikazuje kao „nije klasifikovan“. |
| Može li se oporaviti? | **Da (P).** Ponovno „Prikači“ dovršava isti dokument, bez duplikata dokumenta, događaja i dokaza. |
| Automatski, ručno ili nepodržano? | **Ručno pokrenuto, deterministično.** Automatski oporavak bi tražio nov zakazan proces, a on nije pravljen. |
| Treba li migracija? | **Ne.** |

**Usput nađen i ispravljen kvar (P):** mehanizam za stabilan ID događaja nikad nije radio sa pravom verzijom supabase biblioteke, pa svaki takav upis pada. Zbog toga se **COI provera iz Smart Intake-a u produkciji verovatno nikad ne zakazuje** (I; produkcioni logovi nisu čitani). Testovi to nisu videli jer je test-zamena bila blaža od prave biblioteke. Posle deploy-a COI provere počinju stvarno da rade, pa se mogu pojaviti prva COI upozorenja.

## B. Pravni autoritet (zakon + član) — **PASS**
| Pitanje | Odgovor |
|---|---|
| Da li je zaobilaženje reprodukovano? | **Da (P).** Stari čuvar je propuštao: „član 201 Zakona B“ kad je 201 samo u Zakonu A; svaki ćirilični citat; i svaki odgovor u kome model napiše „nije dostupno“. |
| Koji identitet izvora se proverava? | Zaglavlje izvora iz baze zakona (`ZAKON:` i `ČLAN:` iz metapodataka korpusa), nikad tekst modela. |
| Da li se pogrešan par zakon/član odbija? | **Da (P).** Isto važi za član koji nije u tom zakonu, za zakon čiji izvor nije dostavljen i za član označen kao brisan. |
| Da li aplikacija i dalje daje pomoć uz jasnu neizvesnost? | **Da (P).** Blokira se samo pravni deo (postojeća politika); činjenice iz dokumenta ostaju; citat bez naziva zakona ostaje na starom nivou. |
| Šta se NE proverava | Verzija zakona (datum važenja) i pravna ispravnost zaključka. To se nigde ne tvrdi. |

## C. Inženjerski dokazi
- **SHA:** početni `db37af55` (PR #14), kod `b5b9d5a8`, završni = commit ovog dokumenta (samo dokumentacija). Produkcija `80c3902` nedirnuta (P).
- **Izmenjeno:**
  - kod: `routers/smart_intake.py`, `services/event_bus.py`, `main.py`;
  - testovi: 3 nova FRG001 fajla (43 testa) i 11 usklađenih postojećih.
- **Pre ispravke:** 9/11 testova Task A i 12 testova Task B pada na starom kodu. Test na pravom klijentu pada sa `TypeError` (P).
- **Posle ispravke:** svi prolaze. Mutacije: 4/4 i 6/6 uhvaćene (P).
- **Lokalna regresija:** 184 fajla, isto seme, poređenje po imenu testa: **0 novih padova**, izlazni kod 1 na obe strane zbog istog starog pada (P).
- **CI (P), u poređenju sa PR #14 po imenu testa:** 0 novih padova.
  - Test Suite 3.11 i 3.13: 175 = 175 (stari padovi), 8587 prema 8544 prošlih.
  - Produkcioni Python: 197 = 197.
  - Security i V2 NG (uključujući ceo solo tok u pregledaču): zeleni.
- **Docker (P):** build, pokretanje i srpski OCR u slici prolaze.
- **Draft PR:** https://github.com/benny13n-creator/vindex-ai/pull/15 (cilja granu PR #14).

## D. Preporuka: **USLOVNI GO**
Uslovi koji ostaju:
1. **JWT izuzetak (iz OSB003, i dalje obavezan).** Bez odobrenja: NO-GO.
2. **Spajanje redom:** #12 → #13 → #14 → #15 u RC1, pa RC1 → `main`.
3. **Prihvatiti tri promene ponašanja:**
   - nepotpuno prikačivanje sada vraća grešku umesto lažnog uspeha;
   - čuvar citata je strožiji, pa može da blokira više odgovora koji citiraju zakon koji nije pronađen (stopa u produkciji je nepoznata, pratiti posle deploy-a);
   - COI iz Smart Intake-a počinje da radi.
4. **Postojeći V2 dokumenti u produkciji:** verovatno nemaju dokaze, a izgledaju obrađeno (I, kvar ispravljen u OSB002). Posle deploy-a ručno „Reklasifikuj“ u starom UI-ju (troši kredit), ili prihvatiti.

**Jedan sledeći korak:** potpišite JWT odluku, pa pregledajte PR #12 → #13 → #14 → #15 tim redom.
