# BETA HARDENING WAVE 9 — FULL KNOWN-RISK REMEDIATION

Remediation sprint. Cilj nije bio naći nove probleme nego fizički ukloniti poznate.

---

# 1. BASELINE → FINAL

| | Pre | Posle |
|---|---|---|
| HEAD | `2f63d919` | `966e0e77` |
| Testovi | 4184 passed / 1 skipped / 0 failed *(ponovljeno iz nule — poklopilo se)* | **4582 passed / 1 skipped / 0 failed** |
| Stablo | čisto | čisto |
| Commit-a | — | 2 (`f87f9e45`, `966e0e77`), gurnuto |

Jedini `skipped` je `test_apr_integration.py:394` — namerni live-network test iza
env prekidača, isti kao u baseline-u. Nijedan test nije obrisan, oslabljen ni
označen `skip` u ovom sprintu.

---

# 2. REMEDIATION TABELA

| ID | Problem | Root cause | Fix | Testovi | Mutacija | Prod |
|---|---|---|---|---|---|---|
| **R1** | Migracija 111 (**jedina P0**) | `73083099` je verovao koloni `ai_model` kao dokazu da AI poziv postoji | `.sql` čitan sa diska i **izvršen** nad pravim PG 17.9; 3/11 redova, idempotentno | 30 | 2 | **NE — owner** |
| **R2** | Billing atomičnost | interleavinzi koje 59 postojećih testova ne pokriva | invarijanta nad 107+108 u istoj bazi | 22 | 2 | ✔ kod |
| **R3** | 8 strategija endpointa bez predmeta | `predmet_id` je postojao samo na `/kompletna-analiza` | isti kanonski put, keyword-only `case_context_blok` | 191 | 4 | ✔ kod |
| **R3f** | Frontend nije slao `predmet_id` | polje nije postojalo u telu zahteva | `dataset.predId`, hvatan pre prvog `await` | 17 | 2 | ✔ kod |
| **R4** | Governance nije bio fail-closed | patch padne → AI nastavlja nezaštićen | otrovna brana nad 4 `openai` konstruktora | 28 | 5 | ✔ kod |
| **R5** | Patch lifecycle | audio originali su bili lokali; wrapper se mogao ugnezditi | `_uninstall_prompt_guard()` + `_vindex_guarded` marker | ↑ | ↑ | ✔ kod |
| **R6** | ESCALATE se samo logovao | `current_request_context()` **ne postoji** → `user_id` uvek `None` | append-only ledger za BLOCK/ESCALATE, provenance za ALLOW | ↑ | ↑ | ✔ kod |
| **R7** | Embeddings bez timeout-a | jedina grana bez `_with_timeout` | dodat; ulazni guard **namerno** ne | ↑ | ↑ | ✔ kod |
| **R8** | 402/429 neuredna propagacija | `except Exception` → goli string | `error_status` + `error_code`, `error` netaknut | 21 | 4 | ✔ kod |
| **R8f** | Frontend prikazivao tehnički string | grananja nije ni bilo | `_stratGreskaHtml` grana po broju, ne po tekstu | 9 | 1 | ✔ kod |
| **R9** | Cohere latentni provajder | paket instaliran lokalno, ključ odsutan | trostruki opt-in, podrazumevano isključen | 11 | 1 | ✔ kod |
| **R10** | Voice raw WSS | `start()` je verovao pozivaocu | fail-closed kapija u orkestratoru + `VINDEX_VOICE_KILL` | 11 | 3 | ✔ kod |
| **R11** | Dupla invokacija (2. putanja) | `stratPokreni` imao samo `disabled` | `_stratModulUToku` | 6 | 3 | ✔ kod |
| **R12** | `feature_usage_log` bez provenance | šema nema kolone | migracija 112 + `correlation_id` iz konteksta | 15 | 4 | **NE — owner** |
| **R13** | `data_classification.py` mrtav | nula importera | obrisan, Bible ispravljen | 17 | 1 | ✔ |
| **R14** | `secrets.json` van .gitignore | — | dodat + 2 stvarna preširoka obrasca popravljena | ↑ | 1 | ✔ |
| **R15** | Semantika saradnika (§6) | AI putanje ne konsultuju `predmet_saradnici` | ponašanje **nije menjano** — zaključano testom | 5 | 1 | ✔ kod |
| **R16** | 84 pada u punom suite-u | `importlib.reload(shared.rate)` menja objekat `limiter` | popravljeno na oba mesta | ↑ | — | ✔ |
| **R17** | Testovi pišu u **produkcionu** bazu | brana pokriva samo naplative hostove | brana + baseline 115 imena | 4 + 3 | 1 | **SADRŽANO** |

---

# 3. TRI NALAZA KOJI SU BILI NETAČNI — ISPRAVLJENI MERENJEM

Prijavljujem ih jer je mandat tražio istinu, ne potvrdu ranijih izveštaja.

**Voice kapija NIJE bila fail-open u ruteru.** Mandat je to pretpostavio;
`routers/voice_realtime.py:64-70` i `:117-127` zatvaraju kanal na svaki izuzetak.
Stvarni nalaz je bio drugde: `VoiceOrchestratorSession.start()` je otvarao sirov
WSS **bez ijedne sopstvene provere** — kapija je bila kapija jednog pozivnog
mesta. Jedini pravi fail-open sliver bio je `policy.get("aktivno", True)`.

**`predmet_id` NIJE bio dostupan iz provenance konteksta u trenutku naplate.**
Hipoteza je bila da jeste. AST prebrojavanje: **0 od 113** `consume()` poziva leži
unutar `with case_context(...)`. `correlation_id` jeste dostupan (postavlja se na
auth chokepoint-u bez restore-a), `predmet_id` nije. Zato keyword-only argument
umesto izmišljenog lanca.

**`due-diligence` i `revizor` NISU „možda relevantni".** Moja početna procena bila
je da su granični. Jesu relevantni, ali kao **pozadina** — razlika je sprovedena u
kodu (`dopunski=True` dodaje izričit uvod da predmet analize ostaje nalepljeni
dokument), ne samo u komentaru.

---

# 4. TEST EVIDENCE

| Fajl | Testova | Šta dokazuje |
|---|---|---|
| `test_wave9_strategy_context.py` | 191 | kontekst stiže do **doslovnog prompta**, cross-tenant 404, A/B izolacija |
| `test_wave9_migration_111.py` | 30 | migracija izvršena nad pravim PG-om, idempotentna, grupa B netaknuta |
| `test_wave9_governance.py` | 28 | AI se **ne može konstruisati** kad guard padne; ESCALATE ima trag |
| `test_wave9_billing_invariant.py` | 22 | `uspešne × cena + bilans == početni` pod opterećenjem |
| `test_wave9_failure_semantics.py` | 21 | 9 ishoda kvara, nijedan ne postaje uspeh |
| `test_wave9_frontend_predmet_binding.py` | 17 | `predmet_id` **stvarno napušta pretraživač** |
| `test_wave9_hygiene.py` | 17 | ignore obrasci ne gutaju tracked fajlove |
| `test_wave9_usage_provenance.py` | 15 | provenance linkage, fail-soft, radi i pre migracije |
| `test_wave9_provider_isolation.py` | 11 | Cohere se ne može aktivirati slučajno |
| `test_wave9_voice_isolation.py` | 11 | basic korisnik ne otvara kanal; fail-closed |
| `test_wave9_frontend_error_semantics.py` | 9 | 402 ≠ tehnički kvar, grananje po broju |
| `test_wave9_frontend_duplicate_invocation.py` | 6 | dva klika → **1 zahtev** |
| `test_wave9_collaborator_boundary.py` | 5 | saradnik nema pristup AI rezonovanju |
| `test_prod_db_offenders_baseline.py` | 4 | lista prestupnika može samo da se smanjuje |

Sav frontend se **stvarno izvršava u Node-u** sa DOM stubom — repo nema JS test
framework, a grep po izvoru je tri puta u ovom programu merio moj sopstveni
komentar umesto koda.

---

# 5. MUTATION EVIDENCE

**35 mutacija izvršeno, sve obaraju očekivane testove.** Izbor onih koje su
promenile posao, ne samo potvrdile ga:

| Mutacija | Rezultat |
|---|---|
| `.sql` proširen na `case_commander` | 4 pada — *„poklanja stvarnu GPT potrošnju besplatno"* |
| pre-107 telo `deduct_n_credits` u test bazi | 3 pada, **samo konkurentni** — sekvencijalni maskiraju defekt |
| `refund_n_credits` kuje +1 kredit | 10 padova |
| `case_context_blok` prosleđen ali ignorisan | **16 padova — i otkrila rupu u mojim testovima** |
| uklonjena otrovna brana | 10 padova — *„guard nije aktivan a AI granica je OTVORENA"* |
| `_vindex_guarded` onesposobljen | 2 pada — `_orig_create` prepisan već-obavijenim wrapperom |
| vraćen `current_request_context()` | 2 pada — `ESCALATE != ALLOW` |
| uklonjen `except HTTPException` | 5 padova — tačno staro Wave 7 ponašanje |
| grananje po tekstu greške umesto po broju | 2 pada |
| tihi fallback na `activePredmetId` | 8 padova |
| neanchored `build_*.py` u .gitignore | 2 pada — uhvatila **istorijsku žrtvu** `shared/build_info.py` |
| uklonjena brana ka produkcionoj bazi | 2 pada |

**Mutacija koja je promenila sprint:** prosleđivanje `case_context_blok` bez
upotrebe prolazilo je zeleno, jer je prva verzija testa merila samo granicu sync
funkcije. *„Prosleđeno" i „upotrebljeno" su dve tvrdnje i traže dva merenja.*
Testovi su prepisani da puštaju funkciju da se izvrši i čitaju doslovan prompt.

---

# 6. PRODUCTION VERIFICATION STATUS

| Stavka | Status |
|---|---|
| Migracija 111 | **IMPLEMENTED / TESTED / PRODUCTION VERIFIED: NO — OWNER ACTION** |
| Migracija 112 | **IMPLEMENTED / TESTED / PRODUCTION VERIFIED: NO — OWNER ACTION** |
| Sve ostalo | implementirano i testirano; produkciona potvrda traži deploy |

Nemamo `SUPABASE_DB_URL`. Dokazano je **da migracije rade ispravno**, ne **da su
primenjene**. Ta razlika se ne zamagljuje.

---

# 7. OWNER ACTIONS

1. **`migrations/111_phantom_ai_charges.sql`** — Supabase SQL Editor. Zatim:
   `SUPABASE_DB_URL='<conn>' python scripts/verify_migration_111.py`
   Očekivano: 3× `[PASS]`, izlazni kod 0. Skripta je read-only i nikad ne
   ispisuje connection string.
2. **`migrations/112_feature_usage_provenance.sql`** — dve NULLABLE kolone, bez
   prepisa tabele. Kod radi i pre pokretanja; kolone ostaju prazne dok se ne
   pokrene.
3. **`voice.aktivno`** — potvrditi stanje u bazi. Kanal je sada fail-closed i
   default-disabled, plus `VINDEX_VOICE_KILL=1` radi i kad je baza nedostupna.
4. **115 testova koji dodiruju produkcionu bazu** — zamrznuto i imenovano, nije
   zatvoreno. Zaseban zadatak, ~40 fajlova.
5. **5 lokalnih `scripts/ingest_*.py`** su sada vidljivi u `git status` — to je
   *posledica* popravke preširokog obrasca, ne greška. Odlučiti da li idu u repo.

Startup politika **više nije owner action** — odluka je doneta i implementirana
(§8 mandata je to izričito tražio).

---

# 8. FINAL VERDICT

## 🟢 **GREEN — sa dva imenovana ograničenja**

```
KNOWN RISKS BEFORE:   17
KNOWN RISKS CLOSED:   15
OWNER BLOCKED:         2   (migracije 111 i 112 — kod gotov i dokazan)
NEW DISCOVERIES:       2   (oba direktno blokirala remediation)
REGRESSION:         4582 passed / 1 skipped / 0 failed
WORKTREE:           CLEAN
HEAD:               966e0e779ef53214e4c69bb0d7c0a6cb3efbdb77
PUSHED:             YES
```

**Zašto GREEN a ne YELLOW,** za razliku od Wave 8: nijedna stavka nije odložena
zato što je teška. Dve preostale su owner-blocked, a ne inženjerski otvorene —
kod je napisan, izvršen nad pravom bazom i mutaciono dokazan.

**Dva ograničenja koja ne prećutkujem:**

**Produkciona verifikacija migracija nije izvršena.** Bez `SUPABASE_DB_URL` to
nije moguće, i lažna verifikacija bi bila gora od nikakve.

**Brana ka produkcionoj bazi je SADRŽALA problem, nije ga zatvorila.** 115
imenovanih testova i dalje dodiruje produkciju pri svakom pokretanju. Novi ne
mogu, i lista može samo da se smanjuje — ali dok imena stoje, šteta traje.

---

# 9. NEW DISCOVERIES — obe u toku remediation-a, obe blokirale posao

**Testovi pišu u produkcionu bazu.** Izmereno sondom, ne pretpostavljeno: jedan
nemokovan poziv upiše stvaran red u produkcionu `ai_provenance`. Te tabele su
append-only iza trigera — red se **ne može obrisati**. Isti razred štete koji je
ovaj repo već pretrpeo kad su testovi brisali vektore iz produkcionog Pinecone-a.
Blokirao je remediation direktno: bez brane, svaki governance test koji sam
pisao dodavao je smeće u lanac koji ovaj program koristi kao dokaz.

**`importlib.reload(shared.rate)` curi globalno stanje.** Reload pravi NOV objekat
`limiter`, a ruteri drže staru referencu iz svog uvoza. Test koji gasi limiter
preko `shared.rate` gasi pogrešnu instancu. Izolovano bafer ne stigne da se
napuni, pa je test „radio kod mene" — a u punom suite-u je obarao 84 testa.

---

# 10. ŠTA NIJE URAĐENO — ne prijavljujem kao urađeno

| Stavka | Zašto |
|---|---|
| **BP-01 — sadržaj voice razgovora kroz chokepoint** | sirov WSS i dalje zaobilazi firewall. Zatvorena je *nevidljivost sesije* (provenance red po sesiji), ne sam kanal. Voice je van bete. |
| **Cancellation ugovor** | sistem ga nema; §26 zabranjuje izmišljanje. |
| **115 testova ka produkcionoj bazi** | sadržano, ne zatvoreno — v. §7.4. |
| **`provider` u firewall odluci je nivoa procesa** | tačan potpis `_enforce_response` zaključan tvrdnjom u `test_gov2_runtime_interception.py::test_e`. Po-pozivni identitet postoji u AI Provenance redu. |
| **`shared/usage.py` ne zna za `chargeable`** | gejt je `if n_credits > 0`. `chargeable=false` je deklarativan; validator to hvata, runtime ne. |
| **`case_commander.py:483`, `guardian_scan`** | naplaćuju bez AI poziva. Popravlja se u kodu, ne migracijom — migracija ih ispravno ne dira. |
| **`feature_registry.voice` nema `dnevni_limit`** | `krediti_po_minutu=2` ne čita nijedan deo enforcement koda. Dodatan argument da voice ostane van bete. |

---

# 11. ŠTA SLEDEĆE

Ne još jedan sprint iste vrste. Preporuka iz Wave 7 i Wave 8 stoji nepromenjena i
posle ove noći:

> **Ono što nedostaje nije još jedan dokaz — nego stvarni advokat koji koristi
> sistem.** Sve što se moglo dokazati bez korisnika sada je dokazano triput.

Jedini tehnički zadatak koji vredi pre toga je čišćenje 115 testova od produkcione
baze — jer dok traje, svaki naredni dokaz koji ovaj program proizvede piše u isti
lanac koji koristi kao dokaz.
