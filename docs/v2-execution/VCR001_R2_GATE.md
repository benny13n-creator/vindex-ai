# VCR001 — R2 kapija (kompletan pravni rad: T04–T07) — `PASS`

**Kandidat:** `program/vcr001` @ `b9eb9946` (osnova `main` = produkcija `6ad0b13a`; R1 kandidat `b817fd2d`).
**Nije spojeno ni deployovano.** Merge u `main` i deploy traže zasebnu odluku osnivača za ovaj kandidat.

## Sadržaj kandidata (posle R1)
| Commit | Zadatak | Šta |
|---|---|---|
| `f995f709` | T04 | pravno pitanje: pretraga zna za trenutni predmet (kanonski `case_context`), stanje konteksta |
| `5fc726ea` | T05 | nacrt: otvori / sačuvaj izmene / odobri sačuvan tekst; odobrenje iz preuzetog reda |
| `53de12de` | T06 | savetnik: čuvar citata (`main._klasifikuj_citate`), dokumenti u granici poverenja; ponedeljna mrežna curenja u cron testovima ispravljena |
| `fa5ac520` | T06/T07 | V2: Savetnik za ovaj predmet; Dodaj tvrdnju; Zastarelost potraživanja |
| `3dc32630` | T07 | V2: zadaci predmeta (Rad + Radna lista) |
| `914c6269`, `b9eb9946` | — | knjiga, matrica sposobnosti, checkpoint |

## Dokazi
| Kapija | Rezultat | Nivo |
|---|---|---|
| Test Suite 3.11 / 3.13 | 174 / 174 = T04 osnova (0 novih); u odnosu na `main` 175 → 174 (M19 ispravljen u T04) | CI |
| Production Runtime Parity: byte-compile, Docker build i boot-check | zeleno | CI |
| Production Runtime Parity: pun paket | 197, svi nasleđeni (parametrizovani skupovi identični `main`-u; razlike su samo skraćene linije u logu) | CI |
| Security: gitleaks, SAST, semgrep, dependency | zeleno | CI |
| V2 NG: same-origin E2E nad pravim FastAPI, Docker preview, Python ugovor | zeleno | CI |
| V2 NG: frontend paketi | prvo pokretanje crveno samo `demo-piksel` (šum); ponovljeno pokretanje (run `38191435727`) **zeleno** | CI |
| Lokalno: svih 46 frontend paketa | zeleno (`e2e:dokaz-zastarelost` 23/23, `live-agenti` 23/23, `live-nacrt` 51/51, `live-pitanje` 45/45) | BM / BR |
| Lokalno: pun Python paket | 0 novih u odnosu na lokalnu osnovicu `main` stabla | LI |
| Mutaciono testiranje | T04 6/6, T05 6/6, T06 6/6 | LI |

## Nalazi tokom T04–T07 (ispravljeni pre zatvaranja)
1. **Ponedeljna vremenska bomba u testovima.** Dnevni dispečer ponedeljkom (UTC) pokreće stvarno skeniranje Službenog glasnika. Dva cron testa su tada izlazila na mrežu i obarala NS005 `test_nema_spoljne_mreze`, zavisno od redosleda. Reprodukovano, ispravljeno, dokazano sondom.
2. **Ugovor „cena“.** Prvo učitavanje spiska savetnika van kartice uhvatili su testovi Analize i Pregleda; ispravljeno.
3. **Ponoć UTC.** CI posao koji pređe ponoć ruši testove koji računaju „danas“ (nasleđeno, nije menjano; zabeleženo).

## Otvoreni defekti (nisu blokirajući za R2)
- **`FLAKY-DEMO-PIKSEL`** (`live-browser-matrix`): demo-piksel pada u ~3/7 CI pokretanja sa 3–9 piksela u jednoj vertikalnoj koloni (x≈255–263 ili x≈703), i HEAD↔HEAD. Prag se namerno NE menja; zelen na ponovljenom pokretanju.
- **`TPL-DATUMI`**: šabloni upisuju hronologiju sa izmišljenim datumima. Nije izloženo u V2.
- **`PREDICTOR-DIF`**: model generiše procenat šanse. Nije izloženo u V2.

## Šta R2 NE dokazuje
- Prijavljenu produkcionu proveru (nema test naloga).
- Rad nad stvarnim predmetom (sintetički podaci).
- `run-parallel`/`pipeline` savetnika u V2 (namerno nisu izloženi).
