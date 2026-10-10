# V2 RC1: izveštaj za odluku o izdanju

- **Datum:** 2026-10-10
- **Produkcija:** `80c3902be2e06654490972a027a391dbf667dbb4` (`/health`, provereno na početku i na kraju)
- **Kandidat (kod, testiran):** `2a944c44cc9a21546c3356e39568d7785c8c52f3` na grani `release/v2-rc1`
- **Iznad njega:** samo ovaj dokument (docs commit)
- **Nije urađeno:** nema merge-a u main, deploy-a, migracija, Cron-a ni prepisivanja postojećih grana

## 1. Šta je kandidat
```
80c3902b  produkcija (main, PR #11 = ACL hotfix 4dcaa985 + 9dac6774)
   └─ 2c02b9a2  merge feature/vindex-v2-rh001-ns008 (b7e22551)
        └─ 2a944c44  RH002 FINAL chat test + dokumenti (samo test/docs)
```
- `rh001-ns008` sadrži redom: NS006 → rh001-ns006 → NS007 → rh001-ns007 → NS008 → rh001-ns008, uz hotfix spojen kao `4b3b4da6`.
- Spajanje je prošlo **bez konflikta**. Stablo `2c02b9a2` je **bajt-identično** stablu `rh001-ns008`, pa svi raniji RH001/RH002 dokazi za tu granu važe tačno za ovaj kod.
- Originalne NS006/NS007/NS008 grane **nisu** kandidati, jer ne sadrže hotfix. Ostale su netaknute, kao i rh001 grane.

## 2. Hotfix nije dupliran, pregažen ni izgubljen
| Fajl hotfix-a | Kandidat vs produkcija |
|---|---|
| `shared/memorija_vidljivost.py`, `routers/firm_memory.py`, `routers/memory_graph.py` | identično |
| `api.py` (`_fetch_firm_memory_context`) | ACL deo identičan. Razlika su samo NS007/NS008 rute i događaj završnog statusa predmeta |
| `tests/test_rh001_legacy_memory_acl.py` | test harness zamenjen sa `ns008_fake`, plus RH002 chat test |

Kroz kandidata postoji tačno dva čitaoca memorije kancelarije. Oba koriste isti ACL vlasnik (`memorija_vidljivost` / `rag_acl`): legacy rute i chat (hotfix) i Law Brain (NS008). Jedino drugo čitanje je admin provera šeme (`/api/admin/proof`), koje ne vraća sadržaj. Jedina izmena u `shared/rag_acl.py` **sužava** pristup: delegat ne vidi predmet u brisanju.

## 3. Ciljani testovi na `2a944c44`
Spoljni `timeout 600` i faulthandler (180 s); ishod svakog testa čitan iz JUnit XML-a. Nijedan proces nije prekinut, nijedan test nije visio.

| Grupa | Fajlovi | Exit | Rezultat |
|---|---|---|---|
| Memorija predmeta i klijenta, graf čitanje/upis, delegacija/opoziv | `test_rh001_legacy_memory_acl`, `test_enterprise_delegation`, `test_institutional_memory_v2`, `test_phoenix_mission_003_institutional_memory`, `test_confidentiality_003_rag_acl` | 0 | 72 passed |
| AI kontekst | `test_closure_trust_contract`, `test_ns005_t6_pravno_pitanje` (+ chat testovi u RH001 fajlu) | 0 | 41 passed |
| Law Brain vidljivost | `test_ns008_t*` (ACL matrica t19, opoziv t21, trovanje t20 …), `test_rh001_law_brain_authority` | 0 | 236 passed, 1 skipped (`t22_scale::test_rast_upita_je_sublinearan`, merenje skaliranja) |
| RH001 NS007 korekcije | `test_rh001_hearing_prep_authority`, `test_rh001_scheduler_crash_window` | 0 | 86 passed |
| NS007 bez migracije 136 | `test_ns007_t12_review_api`, `test_ns007_t14_workspace` | 0 | 12 passed |

Ukupno 447 passed, 1 skipped, 0 failed, 0 errors.

Ključni testovi:
- `test_B_ne_vidi_tudje_predmetne_i_klijentske_beleske_ni_veze`
- `test_B_odgovori_bajt_identicni_sa_i_bez_A`
- `test_B_ne_moze_da_pripoji_vezu_tudjem_predmetu_ili_klijentu[7 slučajeva]`
- `test_delegiranje_otvara_predmetnu_belesku_a_opoziv_je_zatvara`
- `test_chat_ruta_poruka_modela_bez_tudjih_beleski_i_acl_greska_zatvara`
- `test_ns008_t19_acl_matrix::*`
- `test_lista_pre_migracije_nije_ukljucena_a_ne_greska`

## 4. Ceo CI (GitHub Actions, `release/v2-rc1`) vs `main` `80c3902b`
| Posao | main | kandidat | Novi padovi |
|---|---|---|---|
| pytest 3.11 | 175 failed / 7877 passed | 175 failed / 8480 passed | **0** |
| pytest 3.13 | 175 failed / 7877 passed | 175 failed / 8481 passed | **0** |
| Produkcioni Python 3.11, ceo skup | 197 failed / 7337 passed | 197 failed / 7940 passed | **0** |
| Docker build i boot-check | 17 passed | 17 passed | 0 |
| Byte-compile 3.11 | success | success | — |

Run ID-jevi: kandidat 38087408719 i 38087410525; main 38067572410 i 38067572369. Padovi postoje i na produkciji: to je poznata CI osnovica od 175, koju ovaj kandidat ne menja.

## 5. Pregled integracionog diff-a (`80c3902b..2a944c44`)
- 150 fajlova: 116 dodato, 34 izmenjeno, **0 obrisano** (PAD-001 §M: nijedna sposobnost nije uklonjena).
- Backend izmene su samo u NS006–NS008 domenu: Living Matter, autonomija, Law Brain, evolucija predmeta, dokazi. Ne diraju se auth, naplata ni ACL memorije.
- Stavke koje traže vašu svest:
  - `requirements.txt`: `pypdf` 6.15.0 → 6.19.0 (NS006).
  - `security.yml`: druga dokumentovana CVE izuzetka, `CVE-2026-85394` (python-jose), sa testom napada na stvarne verifikatore (`test_ns006_t1_jwt_alg_confusion`). Ovo je bezbednosna odluka: izuzetak važi dok upstream ne objavi popravku.
  - `migrations/135` (primenjena) i `migrations/136` (**nije** primenjena) su samo fajlovi u repou. Ništa nije pokrenuto.

## 6. Preostale kapije (NS007)
| Kapija | Stanje | Dokaz |
|---|---|---|
| Migracija 135 | primenjena | PROVEN: produkciona kolona `predmet_dokazi.izvor_tvrdnje` postoji |
| Migracija 136 (`autonomy_cycles`, `autonomy_work_items`) | **NIJE primenjena** | PROVEN: produkcija vraća PGRST205 |
| Render Cron i `AUTONOMY_CRON_SECRET` | nije napravljen | Bez tajne `/api/cron/autonomy` odbija sve |
| Izbor kadence | čeka vas | `NS007_RENDER_CRON_PLAN.md` |

Ako se kandidat pusti **pre** migracije 136, ekran „Danas“ prikazuje korpu „Vindex je pripremio“ kao isključenu (`NIJE_UKLJUCENO`) umesto greške. To pokrivaju testovi. Autonomni rad tada ne radi. Ostale V2 funkcije ne zavise od 136 (INFERRED iz pretrage koda).

## 7. Preostali rizici
1. Istorijska izloženost memorije pre `80c3902`: UNKNOWN (RH002).
2. BETA-DEF-001 (poziv `saradnik` vraća 500) i BETA-DEF-002 (nema opoziva delegacije) su otvoreni. Kandidat ih ne rešava.
3. Kandidat nije pušten u produkciju. Ponašanje na stvarnim podacima i latencija nisu mereni.
4. CVE izuzetak iz §5.

## 8. Preporučeno sledeće odobrenje
Otvoriti Draft PR `release/v2-rc1` → `main` radi vašeg pregleda, **bez** merge-a. Zatim odlučiti o redosledu:
- (a) merge i deploy sa NS007 autonomijom isključenom do migracije 136 i Cron-a; ili
- (b) prvo migracija 136 i Cron, pa jedno izdanje.

Bez obzira na izbor, PR #9 i PR #10 (originalne NS grane, bez hotfix-a) treba zatvoriti ili zameniti ovim kandidatom. Nikako ih ne treba spajati.
