# ONS001: odluke za osnivača

**Kandidat:** RC1 + `ae1897a1` (Draft PR #12 → `release/v2-rc1`). Detalji: `ONS001_RELEASE_CLOSURE_EVIDENCE.md`.

**Može li RC1 ka beti bez migracije 136 i Cron-a? DA, uz ispravku iz PR #12.**
- Svih 15 merenih V2 ruta radi isto kao sa migracijom.
- Autonomija ne radi ništa: nema poziva modela, nema naplate, nema lažnog „pripremljeno“.
- Jedina 4 kvara (500/503 na ručno sastavljenim zahtevima) su ispravljena.
- CI: 0 novih padova.

## Odluka 1: python-jose CVE izuzetak (bezbednost)
- **Problem:** RC1 u `security.yml` preskače CVE-2026-85394 (CRITICAL). Zakrpljena verzija ne postoji (PyPI 3.5.0 = najnovija).
- **Opcije:**
  - (a) odobriti izuzetak;
  - (b) ne odobriti, pa RC1 ne prolazi pip-audit;
  - (c) zameniti biblioteku (PyJWT je već instaliran).
- **Kompromis:** (a) je brzo, uz dokaz da napad nije dostižan. (c) je prava eliminacija, ali menja autentifikaciju i traži sopstvenu regresiju.
- **Preporuka:** (a) sada, sa uslovom da se izuzetak ukloni kad upstream objavi popravku; (c) planirati posle bete.
- **Dokaz:** 78 pokušaja falsifikata na stvarnim verifikatorima, **0 prihvaćenih**; produkcioni JWKS je ES256 sa `alg`.

## Odluka 2: uloga `saradnik` (BETA-DEF-001)
- **Problem:** podrazumevana uloga u pozivu kolege pada sa 500, jer je produkciona baza ne prihvata. `partner` daje administratorska prava u zadacima i workflow-u, pa nije zamena.
- **Opcije:**
  - (a) migracija koja vraća `saradnik` u produkciono ograničenje (kao u repo migraciji 018);
  - (b) aplikacija prestaje da nudi `saradnik` i bira se druga ne-admin uloga.
- **Kompromis:** (a) čuva postojeću semantiku i kod, ali traži migraciju i prethodno read-only čitanje tačnog ograničenja. (b) je bez migracije, ali menja značenje uloga.
- **Preporuka:** (a). Produkcija ima 0 članova, pa je rizik po podatke nula.
- **Potreban dokaz:** read-only `pg_get_constraintdef` za `kancelarija_clanovi_uloga_check`.

## Odluka 3: opoziv delegacije (BETA-DEF-002)
- **Problem:** nema načina da se delegacija povuče. Ne postoji ni UI za davanje delegacije.
- **Potrebno odlučiti:** (1) ko sme da opozove (preporuka: davalac ili vlasnik predmeta; admin bez implicitnog pristupa); (2) završna vrednost statusa (repo kaže `otkazano`, produkcija je prihvatila `opozvano`); (3) gde u V2 predmetu stoje davanje i opoziv.
- **Kompromis:** ne dirati sada je bezbedno, jer produkcija ima 0 delegacija i 0 članova. Ali čim beta dobije kancelarije, pristup se ne može povući bez baze.
- **Preporuka:** odlučiti pre nego što prvi beta korisnik pozove kolegu, i uraditi to zajedno sa Odlukom 2.
- **Potreban dokaz:** read-only definicija ograničenja `predmet_delegiranja.status`.

## Sledeći korak
Pregledati i odobriti Draft PR #12 ka `release/v2-rc1`, zatim odlučiti o Odluci 1 (CVE izuzetak), jer bez nje RC1 ne prolazi bezbednosnu proveru zavisnosti.
