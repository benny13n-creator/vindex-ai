# FRI001 — GO / NO-GO za osnivača

**Preporuka: USLOVNI GO** za tačan SHA kandidata, posle vaše odluke A i C. Ništa nije spojeno ni deployovano.
Oznake: **P** dokazano · **I** zaključeno · **U** nepoznato.

## 1. Tačno stanje
- Produkcija `main`: `80c3902b` · RC1: `036854c0` · PR #12 `ad028bde` · #13 `8901a249` · #14 `db37af55` · #15 `df5feb36`.
- **Kandidat:** grana `release/v2-solo-final-candidate`. Kod je na `c7b809f1`, a završni commit dodaje samo ova dva dokumenta.
- **Draft PR #16 → main:** https://github.com/benny13n-creator/vindex-ai/pull/16

## 2. Šta je dokazano (P)
- **Istorija je potpuna:** `main` → RC1 → #12 → #13 → #14 → #15 → kandidat, svaki korak predak sledećeg. Nijedna ispravka nije izgubljena (RH001/RH002, NS006–008, ONS001, OSB002, OSB003, FRG001), proveren je sadržaj, ne samo istorija.
- **COI:** lanac proveren do upozorenja koje advokat vidi. Posle FRG001 bi se prvi put aktivirao, pa sam pronašao i ispravio 3 kvara:
  - **predmet je prijavljivao sukob sam sa sobom** (posle deploy-a bi svaki prijem sa klijentom u starom čarobnjaku dao lažno upozorenje);
  - podudaranje imena je predstavljano kao „Ne možete zastupati“; sada „Mogući sukob — potrebna provera“;
  - duplo upozorenje posle prekida.

  Neuspela provera se nikad ne predstavlja kao „nema sukoba“. Tuđi podaci ne ulaze ni u proveru ni u upozorenje.
- **V2 solo tok COI uopšte ne pokreće.**
- **Dokument:** lažan uspeh nije moguć; ponovni pokušaj dovršava isti dokument; bez duplikata, bez dodatne naplate; prihvaćen dokument se ne prepisuje.
- **Citati:** pogrešan zakon, nepostojeći ili brisan član ne prolaze kao provereni; ćirilica i padeži se prepoznaju. Verzija zakona i pravna ispravnost se ne tvrde.
- **Bezbednost:** nema curenja između korisnika ni u memoriji kancelarije (RH001/RH002); JWT: 0 prihvaćenih falsifikata; autonomija isključena; nema novih tajni (gitleaks 0 nalaza, pozitivna kontrola uhvaćena).
- **CI na tačnom SHA:** 0 novih padova u odnosu na `main` i na #15 (175/175/197 istih starih padova).
  - Docker, srpski OCR u slici i ceo solo tok u pregledaču (23/23) prolaze.
  - Security je zelen, ali pip-audit samo uz izuzetak.

## 3. Materijalni rizici koji ostaju
1. **JWT CVE-2026-85394** nema zakrpu. Izuzetak je u izdanju, a **vi ga niste odobrili** (P). Bez odobrenja: NO-GO.
2. **COI u V2 ne postoji kao vidljiv tok** (P). Upozorenja se vide samo u starom UI-ju (brifinzi), a trajno neuspela provera se ne javlja nikome.
3. **Postojeći V2 dokumenti u produkciji** verovatno nemaju dokaze, a izgledaju obrađeno (I). Ne mogu se pouzdano izdvojiti (U). Ručno „Reklasifikuj“ u starom UI-ju.
4. **Strožiji čuvar citata** može blokirati više odgovora; stopa u produkciji nije poznata (U). Pratiti posle deploy-a.
5. **Rollback** je tehnički dostupan (`80c3902b`; I za Render). Pre rollback-a treba proveriti neisporučene COI događaje (inače bi ih stari kod obradio sa starim kvarovima).
6. **Produkcija još nije videla ovaj kod** (U): nema produkcionog smoke testa.

## 4. Vaše odluke (odvojene)
- **A. JWT CVE-2026-85394.** Preporuka: prihvatiti rizik na **90 dana**, samo dok svaki `decode` ima tačno jedan algoritam, a produkcioni JWKS samo ES256 ključ sa `alg`; ponovni pregled odmah ako izađe zakrpa, promeni se JWKS ili se doda ruta koja čita JWT. Ovo je **samo** prihvatanje bezbednosnog rizika, ne odobrenje izdanja.
- **B. COI semantika (bez promene sada).**
  - Da li za solo betu prihvatate da COI iz Smart Intake-a radi samo u starom čarobnjaku, a V2 ga ne prikazuje?
  - Da li stara provera „ime prvo“ sme i dalje da kaže „Ne možete zastupati… (čl. 42 Zakona o advokaturi)“ za podudaranje imena?

  Preporuka: prihvatiti za betu; prikaz COI u V2 i ujednačenje formulacije su sledeći posao.
- **C. Spajanje i deploy tačnog SHA.** Merge PR #16 (ili lanca #12 → #15 + FRI001) u `main` i deploy završnog SHA ove grane. Posle deploy-a ide ograničen produkcioni smoke test (vaš nalog, troši kredite). Uključivanje V2 za sve (`VINDEX_V2_NG_PRIMARY_ENABLED`) je **zasebna** odluka; bez nje se menja samo backend.

## 5. Verdikt
**USLOVNI GO.** Uslovi: A potpisano, B prihvaćeno, C eksplicitno odobreno za tačan SHA.

**Jedan sledeći korak:** potpišite odluku A (JWT).
