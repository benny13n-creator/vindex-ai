# VCR001 — R1 kapija (kompletan prijem: T00–T03) — `PASS`

**Kandidat:** `program/vcr001` @ `b817fd2d` (osnova `main` = produkcija `6ad0b13a`). **Nije spojeno ni deployovano**: merge u `main` i deploy traže zasebnu odluku osnivača za ovaj kandidat.

## Sadržaj kandidata
| Commit | Zadatak | Šta |
|---|---|---|
| `79d2c1b5` | T00 | izvršni pravac, matrica sposobnosti V1↔V2, matrica zahteva, knjiga, checkpoint |
| `a8a7e16b` | T01 | mešovit PDF: skenirana strana više ne gubi tekst (OCR po strani) |
| `b6c5991d` | T02 | V2 čarobnjak za prijem: iz opisa problema i iz dokumenta, sa proverom sukoba interesa |
| `17dd7057` | T03 | hronologija sa izvorom; rok iz dokumenta → akcija sa poreklom; odluka zatvara akciju |
| `661391bd` | T03 | ns006 demo: pojačana provera (nepotvrđen rok je kritičan i dolazi prvi) |
| `b817fd2d` | T03 | izolacija sonde migracije 129 u testovima; registar Case Evolution |

## Dokazi
| Kapija | Rezultat | Nivo |
|---|---|---|
| Test Suite (Python 3.11 / 3.13) | 175 / 175 padova = **isti skup kao `main`**; 0 novih, 0 nestalih | CI |
| Production Runtime Parity — byte-compile, Docker build + boot-check | zeleno | CI |
| Production Runtime Parity — pun paket na produkcionom Pythonu | 197 padova, svi nasleđeni sa `main` (198) | CI |
| V2 NG — svi `verify*`/`e2e:*` (Ubuntu, Chromium), same-origin E2E nad pravim FastAPI, Docker preview | zeleno | CI |
| Security — secret-scan (gitleaks), sast-core/full, semgrep-core/full, dependency-scan | zeleno | CI |
| Lokalno, svih 42 frontend paketa na `17dd7057` | 41/42; jedini pad (`e2e:demo-ns006` [14]) ispravljen u `661391bd` → 5/5 | BR/BM |
| `e2e:pre136` | izlaz 0; dve FAIL linije su namerna kontrola osetljivosti (`VX_E2E_AUTONOMIJA`) | BR |

## Nalazi tokom kapije (ispravljeni pre zatvaranja)
1. **T03 regresija u CI-ju (20 testova).** Uzrok: procesni keš sonde `rokovi._sema_ima_129` je curio između testova, pa je Rule 6 čitao `predmet_hronologija` u lažnim bazama koje je ne poznaju. Ispravka: autouse fikstura. Dokaz redosledom: bez fiksture 17 failed, sa njom 37 passed. Produkcija nije pogođena (sonda je tamo stvarna, migracija 129 primenjena).
   **Pouka:** ciljana regresija (27 fajlova) nije bila dovoljna. Od T04 pun lokalni Python paket ide pre commit-a.
2. **demo-piksel (HEAD protiv HEAD, 3 piksela)** na `17dd7057`: šum renderovanja, zeleno na `b817fd2d` bez izmene.
3. **Dokumentacija registra** je tvrdila da `MANUAL_CORRECTION_APPLIED` emituje `correct_entity()`. Mereno: nikad nije. Ispravljeno.

## Šta R1 NE dokazuje
- **Prijavljenu produkcionu proveru:** nema test naloga (odluka osnivača).
- **Stvaran predmet:** sve je na sintetičkim podacima (A018 B13 i dalje `BLOCKED — REAL DATA REQUIRED`).
- **OCR na produkcionoj slici:** dokazan je u Docker slici u CI-ju, ne live.
