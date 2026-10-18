# NIGHT SPRINT IV — Institucionalno znanje: pouzdanost

**Grana:** `night/ns4-institutional-intelligence` (lokalna, NIJE pushovana)
**Osnova:** `cc8bd5485210f0a9ea67d6f725fc2060a2957b50` (= `origin/main` na početku; stablo identično `f3965dcc`)
**Radna kopija:** `C:/vindex-qa/night-iv`; kontrolna osnova `C:/vindex-qa/night-iv-base` (detached `cc8bd548`)
**Lokalni commit:** vidi §10
**Produkcija:** nedirnuta — nijedan push, merge, deploy, migracija, SQL upis, Pinecone upis, email/SMS ni plaćen poziv modela.

**Završna klasifikacija: PARTIAL PASS — BLOCKERS REMAIN**

---

## 0. Rezime za osnivača

Pet stvarnih grešaka je dokazano i ispravljeno lokalno; tri nalaza su predata tebi na odluku jer bi ispravka
tražila migraciju ili promenu pravila deljenja. Dve sopstvene sumnje sam proverio i **odbacio** (nisu greške).

Ispravljeno (svako: RED na osnovi → GREEN na grani → mutacija pada):
1. **Korekcije advokata su se gubile** kad upis stil-profila padne, i označavale su se „obrađenim" i one koje nikad nisu analizirane.
2. **Ispravljen ishod predmeta je zauvek zadržavao stari** doprinos u `case_patterns` (pobeda → poraz i dalje broji pobedu) — a te brojeve čita procena pouzdanosti (`court_predictor`).
3. **„Slični predmeti" su iz jednog predmeta pravili „win rate 100%"** i tvrdnju o uzroku; bez modela su izmišljali „sličnost 60".
4. **Odobrenje nacrta je za pad Pinecone-a govorilo „ocena ispod praga"** (i u V2 ekranu) — pogrešan razlog.
5. **Nepotpun upis nacrta u indeks je prijavljivan kao „dodat u bazu znanja"**.

Ostaje otvoreno (tvoja odluka): oporavak neuspele promocije ne postoji (treba stanje/migracija); `client_memory`
pokazuje profil tuđeg klijenta kolegi iz kancelarije; RLS politike koriste `aktivan` umesto `ACTIVE` — i **naivna
ispravka bi proširila pristup**, pa je ne predlažem u tom obliku.

Ništa ovde ne dokazuje da produkcija radi: produkcijske tabele učenja su prazne (0 redova), a nijedan od ovih tokova
nije izvršen uživo.

---

## 1. Identitet

| | |
|---|---|
| Početni `origin/main` | `cc8bd548` (Merge PR #46) — poklapa se sa referencom iz zadatka |
| Merge-base grane | `cc8bd548` |
| Divergencija | nema; glavna radna kopija (`legal-agent`, 172 nepovezane izmene) nije dirana |

## 2. Matrica sedam zadataka

| # | Zadatak | STATUS | Odluka |
|---|---|---|---|
| 1 | Rekonstrukcija toka učenja | PASS (mapa, §3) | Close |
| 2 | Članstvo i autorizacija memorije | PASS za app-sloj; RLS nalaz + `client_memory` nalaz | Treba odluka osnivača (§11 O1, O2) |
| 3 | Ishodi i idempotentnost | PASS (2 ispravke) | Close; trka ostaje samoisceljujuća, ne atomska (§8) |
| 4 | Korekcije bez gubitka | PASS (1 ispravka, 2 dela) | Close; ostatak prozora §8 |
| 5 | Staging odobrenje i oporavak | PARTIAL — poruka i tvrdnja ispravljene; **oporavak BLOCKED** | Treba odluka (§11 O3) |
| 6 | Put čitanja (grounded) | PASS (postojeće + tabelarni test) | Close |
| 7 | E2E dokazna kapija | PASS lokalno (1 E2E test, 12 koraka); korak 8 beleži blocker | Close lokalno |

## 3. Task 1 — mapa tokova (izvor: kod, ne dokumentacija)

Legenda: **I**=implementirano, **W**=povezano sa UI, **T**=testirano, **P**=dokazano u produkciji.

| Tok | Ulaz (pozivalac) | Autorizacija | Trajni upis | Idempotentnost | Potrošač | I/W/T/P |
|---|---|---|---|---|---|---|
| A. Zatvaranje → ishod → budući predmeti | `POST /api/learning/outcome` (`routers/learning.py:165`); **samo legacy UI** `static/vindex.js:22846`, fire-and-forget, greška se guta | vlasnik predmeta (`_dohvati_predmet`, `user_id`) | `outcome_log` (UNIQUE `predmet_id`), `case_patterns`, `predmeti.status`, hronologija, `MatterBecameTerminal` | isti ishod = bez efekata (NS008 T2); **NS4: brojači preračunati iz `outcome_log`** | Law Brain `ucitaj_ishode` (V2), `court_predictor`, `case_intelligence`, `benchmarking`, `cio` | I W(legacy) T — P: **UNKNOWN** (0 redova u prod) |
| B. Preporuka → feedback → ishod | `POST /api/learning/recommendation-feedback` — **nema UI pozivaoca** | `user_id` filter | `recommendation_log.prihvacena` | update postavlja vrednost | `confidence_auditor` | I T(delimično) — vraća `ok: True` i kad upis padne ili pogodi 0 redova (**nalaz, nije ispravljen**: ruta je nedostižna iz UI) |
| C. Izmena advokata → korekcija → stil-profil | `POST /api/corrections/capture`; **samo legacy UI** `static/vindex.js:6432` (kopiranje izmenjenog podneska) | dozvola `corrections`; `predmet_id` samo vlasnikov (inače `None`) | `ai_corrections`; agregat `firm_style_profile` | **NS4: potvrda tačne serije po id-u, tek posle upisa profila** | **nijedan generator ne čita `firm_style_profile`** (grep: samo `proof.py`, `GET /style-profile`) | I W(legacy) T — P: UNKNOWN |
| D. Nacrt → staging → overa → Pinecone | generisanje → `_stage_draft_for_review` (`drafting.py:245`); V2 `frontend-v2-ng/src/nacrt-predmeta.js:90–181`; legacy `vindex.js:22489+` | `user_id` vlasnik staging reda | `staging_memory` → `predmet_dokumenti` + vektori `LAWYER_VERIFIED` (`parent_id`, `origin_chain`) | brava `pending→approved` (F16); deterministički ID vektora (`verzija_dokumenta`) | RAG `retrieve.py:2413` + Law Brain preko `vazece_overe` | I W(V2) T — P: UNKNOWN |
| E. Memorija kancelarije → autorizacija → AI kontekst | `/api/firma-memorija/*`, `/api/memory-graph/*`; Law Brain `ucitaj_memoriju` | kancelarija iz servera (`get_kancelarija_id_sync`, `status='ACTIVE'`); predmet/klijent beleške kroz `shared/memorija_vidljivost` (RH001) | `memory_entries`, `memory_graph_edges`, `judge_patterns`, `client_memory`, `partner_profiles` | nema (ručni unosi) | Law Brain, chat grafa, `kontekst-za-ai` (**nema internog pozivaoca**) | I T — `client_memory` bez vlasnika (§11 O2) |
| F. Retrieval → autorizacija → poreklo → odgovor | `retrieve_documents` (`app/services/retrieve.py:1945`) | namespace i `dozvoljeni_predmeti` IZVEDENI iz identiteta (`retrieve.py:1896–2088`), parametri pozivaoca se samo sužavaju | — (čitanje) | — | generisanje odgovora | I W T — P: UNKNOWN |

Mrtav kod (zabeleženo, nije menjano): `services/learning_engine.log_outcome/_update_patterns` nemaju pozivaoca i pišu
nepostojeću kolonu `ukupno_predmeta`. Dve implementacije postoje, radi samo `routers/learning.py`.

## 4. Potvrđena postojeća funkcionalnost (bez izmene)

- Ishod: isti ishod se ne broji dvaput, `Idempotency-Key`, pad čitanja/upisa ne zatvara predmet (NS008 T2, S1-5).
- Zatvaranje bez ishoda ne izmišlja ishod: Law Brain → `OUTCOME_UNKNOWN` (NS008 T2; NS4 `test_zatvaranje_ne_izmislja_ishod`).
- Staging: brava protiv dvostrukog odobrenja (F16), promoviše se tekst iz preuzetog reda (VCR001 T05), prag 0.85 i
  ljudska overa oba nužna, odbijanje posle promocije odmah gasi vektor (`vazece_overe`, NS008 T21 — **namerno**,
  vidi §5 odbačeno).
- Memorija: RH001 granica predmet/klijent beleški, bajt-identični odgovori, REMOVED/SUSPENDED/INVITED (NS008 T19).
- RAG: izveden namespace + ACL, karantin injekcija (B-U-004), `AI_GENERATED` isključen, `LAWYER_VERIFIED` samo uz važeću overu.

## 5. Dokazane greške i ispravke

Format: PROBLEM → DOKAZ → MINIMALNA ISPRAVKA → TEST → NEGATIVNA KONTROLA → REZULTAT.

### D1/D2 — korekcije (Task 4) — `routers/corrections.py:566–585`
- **Problem:** (D1) greška upisa `firm_style_profile` samo logovana, korekcije ipak `processed=True`; (D2) potvrda `WHERE kancelarija_id AND processed=false` — i redovi preko `.limit(50)` i upisani posle čitanja serije.
- **Dokaz:** PROVEN — čitanje koda i `tests/test_ns4_t4_korekcije_bez_gubitka.py` na osnovi: 4 failed / 3 passed.
- **Ispravka:** pad profila → `{"ok": False}` bez potvrde; potvrda `.in_("id", ids)` tačne serije; pad potvrde prijavljen.
- **Mutacije:** M1 (bez povratka na pad profila) → 1 pad; M2 (bez `.in_` id) → 2 pada.
- **Rezultat:** 7/7 na grani.

### D3/D4 — `case_patterns` i slični predmeti (Task 3) — `routers/learning.py:113–145, 247–257, 482–490, 617–637`
- **Problem D3:** brojači se uvećavaju samo pri prvom ishodu: ispravka pobeda→poraz, promena faktora i promena vrste spora zadržavaju stari doprinos; dva istovremena prva slanja oba uvećavaju.
- **Dokaz:** PROVEN — `test_ns4_t3_ishod_brojaci.py` na osnovi 4 failed / 6 passed. Postojeći NS008 test „ispravka ne duplira brojače" proveravao je samo `ukupno`, ne pobede/poraze.
- **Ispravka:** `_preracunaj_obrasce` — brojači za (korisnik, vrsta spora) kao funkcija `outcome_log`-a (stranice po 1000, `strana_ili_prazna`), za trenutnu i prethodnu vrstu; isti ishod ne dira ništa.
- **Mutacije:** M3 (samo prvi ishod) → 3 pada; M4 (bez stare vrste) → 1; M5 (bez brojanja poraza) → 4; M8 (stranica bez `strana_ili_prazna`) → 1.
- **Samouhvaćena greška:** prva verzija preračuna je stranicila `.range()` bez zaštite od offseta iza kraja (tačno 1000 ishoda → PGRST103 → preračun tiho pada). Uhvatila ju je postojeća klasna provera `test_z017_registar_offset::test_nijedan_range_nije_nezasticen` u punom suite-u; ispravljeno kanonskim `shared/stranicenje.strana_ili_prazna` + test `test_tacno_puna_strana_ne_obara_preracun`.
- **Problem D4:** `GET /api/learning/slicni-predmeti` (bez UI pozivaoca) za 1 predmet: „win rate 100%", „X je bio presudni faktor u pobedama"; bez modela „sličnost 60".
- **Ispravka:** uzorak uvek naveden, `< 3` → `NEDOVOLJNO_PODATAKA`, bez procenta, opis „advokati su navodili", napomena da nije predviđanje ni uzrok; `slicnost=None` bez modela.
- **Dokaz:** `test_ns4_t3_slicni_predmeti_iskreno.py` na osnovi 4/4 failed, na grani 4/4.

### D5/D6 — odobrenje nacrta (Task 5) — `routers/drafting.py:440–442, 1427–1460`; `frontend-v2-ng/src/nacrt-predmeta.js:125–127`
- **Problem D5:** svaki neuspeh promocije → poruka „confidence_score (0.95) je ispod praga 0.85"; V2 ekran isto („ocena kvaliteta nije dovoljna").
- **Problem D6:** `_promote_staged_draft_to_pinecone` vraćao `True` i kad `ingest_session` upiše manje delova → „dodat u bazu znanja", `pinecone_indexed=True`.
- **Dokaz:** PROVEN — `test_ns4_t5_promocija_iskreno.py` na osnovi 4 failed / 3 passed.
- **Ispravka:** povratna vrednost = `_indeksiran`; odgovor nosi `razlog` (`INDEKSIRANJE_NIJE_USPELO` | `ISPOD_PRAGA`); V2 prikazuje poruku po razlogu (`node --check` OK).
- **Mutacije:** M6 (`return True`) → 1 pad; M7 (bez grane neuspeha) → 2 pada.

### Odbačene sopstvene sumnje (nisu greške)
- **„Odbijanje bez uslova `pending`"** — namerno: NS008 T21 opoziv posle promocije; `vazece_overe` odmah prestaje da servira vektor. Nije menjano.
- **„`maybe_single()` → 500 kod korekcija/odobrenja"** (navedeno u N15 inventaru) — u produkciji ga neutrališe `shared/postgrest_compat.py` (izvršeno: `shim: True` posle uvoza `shared.deps`). Nije menjano; N15 inventar je u tom delu zastareo.

## 6. Komande i izlazi

| Komanda (iz `C:/vindex-qa/night-iv`, `-p no:randomly`) | Rezultat |
|---|---|
| ciljni skup osnove (39 fajlova) na `cc8bd548` pre izmena | 539 passed |
| novi NS4 testovi na OSNOVI (negativna kontrola) | 17 failed, 36 passed, 1 xfailed (pre dodavanja testa strane iza kraja, koji na osnovi prolazi jer osnova ne straniči) |
| novi NS4 testovi na GRANI | 54 passed, 1 xfailed (strogi, §11 O2) |
| ciljni skup + NS4 + srodni (ishodi, slični, RH001, N06) na grani | 651 passed, 1 skipped, 1 xfailed |
| pun suite `tests/test_*.py` na čistoj OSNOVI `cc8bd548` | 16 failed, 11227 passed, 227 skipped, 2 xfailed |
| pun suite `tests/test_*.py` na GRANI (konačno stanje) | 16 failed, 11281 passed, 227 skipped, 3 xfailed — **isti 16 ID-eva kao osnova, 0 novih, 0 nestalih**; +54 passed / +1 xfailed = novi NS4 testovi |
| prvi pun suite na grani (pre zaštite strane) | 17 failed — jedini novi: `test_z017_registar_offset::test_nijedan_range_nije_nezasticen` (moja greška, ispravljena, §5) |
| `py_compile` 3 rutera, uvoz, `node --check`, `git diff --check` | OK |

Postojeći pad nezavisan od ovog sprinta: `test_ns008_t21_revocation.py::test_deaktivirana_beleska_nestaje` pada
kada se pokrene POSLE `test_beta_gate_staging_approve_race.py`, `test_institutional_memory_v2.py`,
`test_vcr001_t05_nacrt_trajan.py` — reprodukovano na čistom `cc8bd548` (1 failed, 42 passed); sam fajl 9/9.

## 7. Bezbednost i izolacija

- Nijedan zahtev ne prima ID kancelarije od klijenta; podmetnut `kancelarija_id` u upitu i telu se ignoriše (PROVEN, `test_ns4_t2`).
- SUSPENDED / REMOVED / INVITED / PENDING / zastarelo `aktivan` ne vide znanje kancelarije kroz legacy rute; pozitivna kontrola: ACTIVE vidi opštu belešku (PROVEN).
- Solo advokat: prazno znanje, upis 400 (PROVEN). Beleška uz tuđ / nepostojeći / neispravan predmet: isti 404, ništa upisano (PROVEN).
- Overen vektor važi samo za `approved` + `is_lawyer_approved` + isti predmet; na čekanju, odbijen, bez overe, pozajmljen, nepostojeći, bez roditelja → ne (`test_ns4_t6`, 9 slučajeva; mutacija → 1 pad). Greška baze se propušta (fail-closed).
- Mreža: conftest čuvar je u ovom sprintu **dva puta oborio** test koji je pokušao pravi poziv modela (to je ispravno ponašanje); svi modeli su zatim zamenjeni.

## 8. Integritet podataka i preostali prozori

- `case_patterns` (INFERRED): preračun je idempotentan; dva istovremena preračuna različitih predmeta iste vrste mogu
  upisati zastareo zbir (poslednji pisac), koji se ispravlja pri sledećem upisu ishoda te vrste. Nije atomski — za to treba SQL funkcija (migracija).
- Korekcije (INFERRED): ako profil uspe, a potvrda padne, sledeći prolaz ponovo broji te redove u `korekcija_count`; dva istovremena prolaza (`asyncio.create_task` posle svake korekcije ≥ 10) mogu dvaput brojati. `korekcija_count` danas niko ne koristi za generisanje. Zatvaranje traži kolonu stanja (migracija).
- Pravne korekcije ulaze u isti stil-agregat i u uzorak modela za „preferirane fraze". Danas bez posledice (nijedan potrošač profila) — **preduslov** pre nego što se profil poveže sa generisanjem: isključiti `tip_korekcije='pravna'` i `[negacija_znacenja]`.
- Klasifikacija korekcije pri padu modela tiho postaje `stil` (`corrections.py:223`). Original korekcije se ne gubi (PROVEN, E2E korak 4).
- Quality Gate (ASSUMED ispravnost): obrazac citata ne prepoznaje padež „članu 15" (samo „član 15") — takav citat se ne broji ni kao nađen; primećeno u E2E.

## 9. Izmenjeni fajlovi

| Fajl | + / − | Zašto |
|---|---|---|
| `routers/corrections.py` | +11 / −3 | D1, D2 |
| `routers/learning.py` | +86 / −51 | D3, D4 (+ zaštita strane iza kraja) |
| `routers/drafting.py` | +14 / −3 | D5, D6 |
| `frontend-v2-ng/src/nacrt-predmeta.js` | +1 / −0 | D5 (poruka po razlogu) |
| `tests/test_ns4_t2_kancelarija_granica.py` | 115 (novi) | Task 2 |
| `tests/test_ns4_t3_ishod_brojaci.py` | 162 (novi) | Task 3 |
| `tests/test_ns4_t3_slicni_predmeti_iskreno.py` | 98 (novi) | Task 3 |
| `tests/test_ns4_t4_korekcije_bez_gubitka.py` | 134 (novi) | Task 4 |
| `tests/test_ns4_t5_promocija_iskreno.py` | 118 (novi) | Task 5 |
| `tests/test_ns4_t6_vazece_overe.py` | 45 (novi) | Task 6 |
| `tests/test_ns4_t7_e2e_institucionalno_znanje.py` | 185 (novi) | Task 7 |
| ovaj izveštaj | novi | §5 Final deliverable |

Nisu dirani: OCR001, VCR002, rokovi, podsetnici, `services/event_bus.py`, migracije, vektorski identitet (NS3 M05 ostaje nezavisan).

## 10. Lokalni commit

Vidi poruku u terminalu (jedan commit na `night/ns4-institutional-intelligence`, nije pushovan).

## 11. Za odluku osnivača (migracija ili pravilo proizvoda)

**O1 — RLS `aktivan` vs `ACTIVE` (PROVEN u repou; produkcija po tvom read-only uvidu ista).**
Migracija 067 je pretvorila `aktivan`→`ACTIVE` i CHECK više ne dozvoljava `aktivan`. Politike koje i dalje traže
`status = 'aktivan'`: `fsp_member_read` (045:84), `zadaci_firma_read` (045:140), `memory_firma_read` (046:44),
`pp_firma_read` (046:89), `jp_firma_read` (046:130), `cm_firma_read` (046:171), `mge_firma_read` (047:61),
`wt_firma_read` (047:94), `wi_firma_read` (059:33), `ws_firma_read` (059:48).
*Uticaj:* nijedan član koji nije admin ne prolazi ove politike → **zatvoreno (manje pristupa), ne curenje**. Backend
koristi service ključ (`shared/deps.py:92–103`, zaobilazi RLS), a nijedan frontend ne čita ove tabele direktno, pa
danas nema efekta u radu.
*Zašto NE naivna zamena `'aktivan'`→`'ACTIVE'`:* RLS ovde zna samo za kancelariju, ne za predmet — ispravka bi dala
SVAKOM članu direktno čitanje predmetnih i klijentskih beleški kolega, što RH001 u app-sloju izričito zabranjuje.
*Predlog (nije primenjen):* (a) ostaviti zatvoreno i dokumentovati da je backend jedina staza, ili (b) zameniti ove
politike eksplicitnim „samo service_role" (`USING (false)` za `authenticated`). Odluka: koja varijanta, i ko pokreće migraciju.

**O2 — `client_memory` bez vlasnika (PROVEN, strogi xfail `test_kolega_ne_vidi_profil_tudjeg_klijenta`).**
`GET /api/firma-memorija/klijent/{ime}` i `kontekst-za-ai` vraćaju profil klijenta po IMENU svakom članu kancelarije
(npr. „NIKAD ne prihvata nagodbu", napomene). `memory_entries` beleške o klijentu su posle RH001 samo vlasnikove —
ova paralelna tabela nije. Tabela nema `user_id`; ispravka = model vlasništva → odluka: da li je profil klijenta
deljen u kancelariji (onda je ovo namerno) ili vlasnikov (onda migracija + backfill vlasnika preko `klijent_id`).

**O3 — oporavak neuspele promocije (BLOCKED).**
Posle pada Pinecone-a red ostaje `approved`, `pinecone_indexed=false`; ponovno odobrenje vraća „već obrađen" i ne
promoviše (nema duplikata — PROVEN), ali ni oporavka nema. Siguran ponovni pokušaj traži: stanje promocije
(`promotion_state`: `pending|in_progress|done|failed` + `promotion_attempts`) uz uslovni prelaz kao F16; ponovni
upis istim `verzija_dokumenta` ID-evima (vektori se prepisuju, ne dupliraju); `predmet_dokumenti` red samo ako ne
postoji za `parent_id` (danas se pravi pri svakom uspehu). Ugovor: migracija + jedna ruta „ponovi upis" (vlasnik).

**O4 — legacy UI guta grešku upisa ishoda** (`static/vindex.js:22845–22857`): advokat ne zna da ishod nije sačuvan. Ispravka je UI (poruka), van ovog sprinta.

## 12. Iskrena E2E procena

`test_ns4_t7_e2e_institucionalno_znanje.py` prolazi 12 koraka kroz stvarne rute nad lažnom bazom: primalac ne
postaje tužilac; korekcija preživljava pad profila; ishod se ne duplira; izmena advokata je ono što ide u promociju;
pad promocije daje tačan razlog; B ne vidi ništa; novi predmet dobija sličan predmet sa objašnjenjem, overen rad sa
poreklom `AI_GENERATED → LAWYER_VERIFIED`, uzorak 1 označen kao mali, bez „šanse/%"; ništa spoljno nije pozvano.
Na osnovi isti test pada (korak 4).
**Šta ovo NE dokazuje:** da produkcija radi; ponašanje pravog Pinecone-a, Supabase-a, PostgREST max-rows, modela i
konkurentnosti između procesa; da je AI „pametniji" (nema kontrolisanog poređenja). Produkcijske tabele učenja su
prazne — nijedan od tokova A–D nije izvršen uživo.

## 13. Sledeći ručni korak za osnivača

Na test nalogu (ne pravom predmetu): otvori sintetički predmet u V2, generiši nacrt, izmeni jednu rečenicu, sačuvaj,
odobri. Očekivano: poruka „odobren i dodat u bazu znanja" ili, ako upis padne, nova poruka „upis … nije uspeo" —
**nikad** „ocena kvaliteta nije dovoljna" za nacrt sa dobrom ocenom. Zatim u Supabase (read-only) proveri da red
`staging_memory` ima `status='approved'` i da `pinecone_indexed` odgovara poruci.
