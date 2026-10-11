# RH002 FINAL CLOSURE: dokaz zatvaranja

- **Datum:** 2026-10-10
- **Produkcija:** `80c3902be2e06654490972a027a391dbf667dbb4`. `/health` vraća `commit: 80c3902`, a `origin/main` daje isti pun SHA. Nije se promenila tokom zadatka.
- **Testirani kod:** isti SHA. Jedina razlika je dodat test, a produkcioni kod nije menjan.
- **Grana dokaza:** `rh002/final-closure` od `80c3902` (lokalno; bez merge-a, deploy-a i push-a).
- **Bez:** merge-a, deploy-a, migracija, Cron promena, izmena produkcionih podataka i ispisa tajni.

## 1. Pokrivenost chat memorije pre ovog zadatka
| Šta | Pokriveno? | Gde |
|---|---|---|
| Povratna vrednost `api._fetch_firm_memory_context`: B bez A-ovih beleški, A sa svojim, opšta beleška prisutna, bajt-identično sa i bez A | DA | `test_chat_kontekst_kolege_bez_tudjih_beleski` |
| Memorija kao podatak, ne instrukcija (omotač porekla) | DA | `test_closure_trust_contract.py` |
| Ono što **model stvarno dobija** kroz rutu `/api/pitanje` (ruta → sklapanje → `ask_agent` → poruka modela) | **NE** | — |
| Greška ACL-a ne otvara privatne podatke | **NE** | — |

Postojeći chat testovi `/api/pitanje` zamenjuju `_fetch_firm_memory_context` sa `None`, pa ne mere ACL. Zato je dodat jedan test.

## 2. Novi test
`tests/test_rh001_legacy_memory_acl.py::test_chat_ruta_poruka_modela_bez_tudjih_beleski_i_acl_greska_zatvara`

- **Stvarno:** ruta `POST /api/pitanje`, `_fetch_firm_memory_context` (test potvrđuje da nije zamenjena), `shared/memorija_vidljivost.vidljive_beleske`, `shared/rag_acl` i `main.ask_agent` sa sklapanjem prompta.
- **Zamenjeno:**
  - pretrage korpusa (bez mreže);
  - `_pozovi_openai`, koji hvata system/user poruku i vraća fiksan odgovor;
  - naplata.
- **Svet:** sintetički A i B u istoj kancelariji, B nije delegiran. A ima predmetnu i klijentsku belešku, a postoji i opšta beleška o sudiji.

| Zahtev direktive | Dokaz u testu |
|---|---|
| A dobija svoju predmetnu memoriju | A-ova poruka modela sadrži njegovu predmetnu i klijentsku belešku |
| B ne dobija A-ovu predmetnu/klijentsku memoriju | B-ova poruka ne sadrži nijedan tajni niz (naziv predmeta, sadržaj, ID-jevi predmeta i klijenta) |
| Opšta memorija kancelarije ostaje dostupna | B-ova poruka sadrži opštu belešku i omotač porekla memorije |
| Greška ACL-a ne otkriva privatne podatke | Kad `dozvoljeni_predmeti` baci izuzetak, ni A ni B ne dobijaju memoriju, a zahtev i dalje vraća 200 |
| Test ne prolazi prazno | Svaki zahtev mora da vrati 200 **i** da pozove model. Pitanje je različito po zahtevu, pa keš ne preskače sklapanje. Opšta beleška kod B dokazuje da je memorija stvarno sklopljena |

### Rezultati (`80c3902` + test, Python 3.13, `--randomly-seed=12345`)
| Skup | Rezultat |
|---|---|
| Novi test | 1 passed |
| `test_rh001_legacy_memory_acl.py` (18), `test_closure_trust_contract.py`, `test_ns005_t6_pravno_pitanje.py`, `test_beta_hardening_001.py` | **95 passed, 0 failed** (isto i sa nasumičnim semenom) |

### Mutacije (test mora da padne; kod je posle svake vraćen bajt-identično)
| Mutacija | Ishod |
|---|---|
| M1: chat bez ACL filtera (`all_memories = mem_r.data[:20]`) | UBIJENA: tajna u B-ovoj poruci |
| M2: ACL predmeta zamenjen sa „sve vidljivo“ | UBIJENA: tajna u B-ovoj poruci |
| M3: greška ACL-a „fail-open“ (vrati nefiltrirano) | UBIJENA: memorija prošla uprkos grešci ACL-a |

Defekt u produkcionom kodu nije reprodukovan, pa produkcioni kod nije menjan.

## 3. Preostali audit redovi (51), samo pregled, ništa obrisano
Svi redovi pripadaju isključivo sintetičkim nalozima. Svaki drugi UUID u njima je identifikator praćenja zahteva (`correlation_id`, `audit_reference`), a ne referenca na stvarne podatke. Nijedan red nije operativni podatak koji aplikacija koristi.

| Tabela | Redova | Sadržaj | Zaštita od izmene |
|---|---|---|---|
| `audit_immutable` | 4 | `predmet_create` ×2, `predmet_delete` ×2, hash lanac (`seq`, `prev_hash`, `entry_hash`) | **Nepromenljivo**: trigger blokira UPDATE/DELETE (mig. 043). Brisanje bi prekinulo hash lanac |
| `klijenti_audit` | 1 | `CREATE` klijenta (sintetički email) | **Nepromenljivo**: trigger blokira UPDATE/DELETE (mig. 002) |
| `ai_forensics` | 41 | AI provenance: modul, hash-evi prompta, tokeni, latencija | Append-only: UPDATE blokiran triggerom (mig. 089). DELETE samo kroz retencionu politiku (`retention_service`), ne ad hoc |
| `audit_log` | 5 | `pitanje` ×3, `DELETE` predmeta ×2 (hash pitanja, hash IP-a) | Audit po nameni (samo INSERT grant), ali **bez triggera u repou**: nepromenljivost nije garantovana u bazi |

Zaključak: to su audit zapisi, ne test podaci. Za 47 redova nepromenljivost (ili retencioni režim) sprovodi baza. Za `audit_log` (5) ona važi samo po konvenciji. Ostavljeni su namerno. Identifikatori su samo u privatnom manifestu, izvan repoa.

## 4. Beta defekti otkriveni u RH002 (dokumentovani posebno, nisu popravljani)
- `docs/v2-recovery/defects/BETA-DEF-001_saradnik_poziv_500.md`: poziv sa ulogom `saradnik` vraća 500. To je **podrazumevana** uloga, a produkciono ograničenje je odbija.
- `docs/v2-recovery/defects/BETA-DEF-002_nema_opoziva_delegacije.md`: nema rute za opoziv delegacije predmeta.

## 5. Status po putu
| Put | Status | Osnova |
|---|---|---|
| Čitanje memorije, izmena memorije, graf čitanje/upis, delegacija, dozvoljeno ponašanje | PROVEN u produkciji | RH002 FINAL, sintetički A/B, 46/48 |
| AI chat izolacija | PROVEN na nivou koda na produkcionom SHA | Ovaj test i 3/3 mutacije |
| AI chat kontekst posmatran uživo u produkciji | UNKNOWN | Chat ne prikazuje memoriju, a logovi nisu pregledani |

## 6. Preostali rizici
1. **Istorijska izloženost: UNKNOWN.** Pre `80c3902` kolega je mogao da čita tuđe predmetne i klijentske beleške i da dopisuje veze u tuđ graf. Da li se to desilo nije utvrđeno; logovi nisu pregledani.
2. **Javni repo:** detalji ranjivosti su javno vidljivi od push-a. Produkcija je zakrpljena, ali to ne utiče na rizik iz tačke 1.
3. **Chat uživo nije posmatran:** dokaz je deterministički i na istom SHA, ali nije produkciono merenje (zavisi od toga da Render služi baš taj kod; `/health` to potvrđuje).
4. `audit_log` nije zaštićen triggerom (§3).
5. BETA-DEF-001 i BETA-DEF-002 su otvoreni.
6. Ovim su obuhvaćeni samo kanali memorije kancelarije (RH001/RH002 opseg). Ostali kanali nisu predmet ovog zadatka.

## 7. Status incidenta
**PRODUCTION FIX VERIFIED.**
- Svaki put kojim je curela tuđa memorija zatvoren je i izmeren: uživo u produkciji, a chat kroz stvarnu rutu na identičnom kodu, sa mutacijskim dokazom.
- Procena istorijske izloženosti (rizik 1) ostaje otvorena. Ona ne menja status popravke.
