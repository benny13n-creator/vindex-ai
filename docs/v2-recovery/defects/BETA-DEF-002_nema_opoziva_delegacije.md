# BETA-DEF-002: aplikacija nema podržan tok za opoziv delegacije predmeta

- **Otkriveno:** 2026-10-10, tokom RH002 FINAL produkcione verifikacije
- **Produkcija:** `80c3902be2e06654490972a027a391dbf667dbb4`
- **Status:** OTVOREN. Namerno nije popravljan (van opsega RH002).
- **Ozbiljnost:** srednja do visoka, sa bezbednosnim aspektom: pristup koji je dodeljen ne može se povući kroz aplikaciju.

## Simptom
Advokat može da delegira predmet kolegi, ali ne može da opozove delegaciju. Delegat zadržava pristup predmetu i njegovoj memoriji dok neko ručno ne promeni red u bazi.

## Dokazi
| Tvrdnja | Oznaka | Izvor |
|---|---|---|
| Postoje samo rute za dodelu i listanje | PROVEN | `routers/enterprise.py:218` `POST /api/enterprise/predmet/delegiraj` i `:286` `GET /api/enterprise/predmet/delegiranja` |
| Nijedna ruta ne menja `status` niti briše red u `predmet_delegiranja` | PROVEN | Pretraga `routers/`, `api.py`, `main.py`, `shared/` na produkcionom SHA |
| ACL poštuje opoziv kada se status promeni (`status != 'aktivno'` gubi pristup sledećim zahtevom) | PROVEN | Produkcioni test G4 (RH002 FINAL); `tests/test_rh001_legacy_memory_acl.py::test_delegiranje_otvara_predmetnu_belesku_a_opoziv_je_zatvara` |
| Opoziv u RH002 testu urađen je direktnim upisom u bazu, nad sintetičkim redom | PROVEN | RH002 FINAL izveštaj |
| Postoji frontend dugme za opoziv | UNKNOWN | Nije mereno; bez backend rute ono ne bi imalo šta da pozove |

## Uticaj
Kada saradnik napusti kancelariju ili promeni tim, njegov pristup delegiranom predmetu ostaje aktivan. Uklanjanje iz kancelarije možda ga gasi; to nije mereno (UNKNOWN). Jedini put za opoziv je ručna intervencija u bazi.

## Predlog (zahteva odobrenje, nije urađeno)
1. Ruta za opoziv (vlasnik predmeta ili admin kancelarije) postavlja `status='opozvano'` i upisuje audit zapis.
2. Pozitivan i negativan test: samo ovlašćeni mogu da opozovu, a delegat gubi pristup već sledećim zahtevom.
3. Odgovoriti posebno: da li izlazak iz kancelarije automatski opoziva delegacije.
