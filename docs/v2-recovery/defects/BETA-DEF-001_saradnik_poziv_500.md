# BETA-DEF-001: poziv člana sa ulogom `saradnik` vraća HTTP 500

- **Otkriveno:** 2026-10-10, tokom RH002 FINAL produkcione verifikacije (sintetički nalozi)
- **Produkcija:** `80c3902be2e06654490972a027a391dbf667dbb4`
- **Status:** OTVOREN. Namerno nije popravljan (van opsega RH002).
- **Ozbiljnost:** visoka za beta onboarding, a nije bezbednosni problem. Poziv kolege je osnovni tok kancelarije, a `saradnik` je **podrazumevana** uloga.

## Simptom
`POST /api/kancelarija/pozovi` sa `uloga="saradnik"` vraća `500` i generičku poruku o grešci. Član nije upisan. Isti poziv sa `uloga="partner"` uspeva.

## Dokazi
| Tvrdnja | Oznaka | Izvor |
|---|---|---|
| Produkcija vraća 500 za `saradnik` | PROVEN | Sintetički poziv na vindex.rs u RH002 FINAL izvršenju |
| Produkciona baza odbija `saradnik` na ograničenju `kancelarija_clanovi_uloga_check` | PROVEN | Ponovljen upis istog reda, sa porukom o kršenju ograničenja |
| Aplikacija nudi `saradnik` i koristi ga kao podrazumevanu vrednost | PROVEN | `routers/kancelarija.py`: `ULOGE` sadrži `saradnik`, a `PozovReq.uloga` ima `default="saradnik"` |
| Repo migracija dozvoljava `saradnik` | PROVEN | `migrations/018_kancelarija.sql:35` |
| Uzrok je odstupanje produkcione šeme od migracije 018 | INFERRED | Tačna definicija produkcionog ograničenja nije pročitana (nema read-only DB pristupa) |
| Isti kvar pogađa i druge putanje koje upisuju `saradnik` | UNKNOWN | Nije mereno |

## Uticaj
Svaki poziv sa podrazumevanom ulogom pada. Korisnik vidi generičku grešku bez objašnjenja. Bezbednosnog uticaja nema: upis se odbija u celosti.

## Predlog (zahteva odobrenje, nije urađeno)
1. Read-only pročitati definiciju produkcionog ograničenja (`pg_get_constraintdef`).
2. Odlučiti koji skup uloga je kanonski. Zatim uskladiti ili ograničenje (migracija) ili ponudu aplikacije, ne oba.
3. Dodati validaciju koja nepodržanu ulogu odbija sa 422 umesto 500, i test koji upoređuje ponuđene uloge sa ograničenjem.
