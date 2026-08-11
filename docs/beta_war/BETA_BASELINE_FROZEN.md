# BETA STABILIZATION WAVE 11 — CLOSE, STABILIZE, FREEZE

---

# 1. BASELINE

| | |
|---|---|
| HEAD pre sprinta | `6414d9fd` |
| Regresija | **4758 passed / 1 skipped / 0 failed** · 336 s |
| Stablo | čisto (bez lokalnih `data/` i scraper skripti) |

Baseline je bio zelen, pa je sprint krenuo bez popravke.

---

# 2. KNOWN RISKS CHECKED — 20/20

Auditor je svih 20 stavki verifikovao protiv **stvarnog runtime žičenja**, ne
protiv izveštaja. Nula izmena u toj fazi.

| # | Stavka | Ulaz | Izlaz |
|---|---|---|---|
| 1 | P0-C phantom naplata / migr. 111 | CLOSED | CLOSED |
| 2 | Migracija 112 | CLOSED | CLOSED |
| 3 | Zero-credit preflight | CLOSED | CLOSED |
| 4 | Billing atomicity | CLOSED | CLOSED |
| 5 | Retry/dedupe safety | **STABILIZED** | **CLOSED** |
| 6 | Frontend duplicate-click | CLOSED | CLOSED |
| 7 | Propagacija `predmet_id` | CLOSED | CLOSED |
| 8 | Vlasnička kapija predmeta | CLOSED | CLOSED |
| 9 | Cross-tenant izolacija konteksta | **STABILIZED** | **CLOSED** |
| 10 | Provenance konteksta | CLOSED | CLOSED |
| 11 | Response firewall | CLOSED | CLOSED |
| 12 | Ulazni guard | **STABILIZED** | **CLOSED** |
| 13 | Governance startup policy | CLOSED | CLOSED |
| 14 | Provider interception | CLOSED | CLOSED |
| 15 | Izolacija produkcione/test baze | CLOSED | CLOSED |
| 16 | Append-only ledger | **STABILIZED** | **CLOSED** |
| 17 | Rate limiter singleton | CLOSED | CLOSED |
| 18 | `feature_usage_log.predmet_id` | **STABILIZED** | **CLOSED** |
| 19 | Build/runtime identitet | CLOSED | CLOSED |
| 20 | Poravnanje frontend/backend verzije | **STABILIZED** | **CLOSED** |

**Šest stavki je ušlo kao STABILIZED, svih šest izlazi kao CLOSED.**

---

# 3. REMEDIATIONS MADE

Pet produkcionih fajlova. Svaka izmena je minimalna zakrpa — nijedna nova
apstrakcija, nijedan promenjen javni API, nijedna promenjena naplatna semantika.

### 3.1 `routers/jobs.py` — posao zaglavljen u `pending` blokirao je retry 60 min

`create_job_deduped` je ponovo koristio posao sa `status in ("pending","running")`.
Posao koji nikad ne bude zakazan ostaje `pending` do `_JOB_TTL_S = 3600` — pa
svaki identičan zahtev narednih **60 minuta** dobija `job_id` posla koji se
nikad neće završiti. Bez signala korisniku i bez načina da ponovi.

`_PENDING_MAX_REUSE_S = 180`, izabrano **merenjem**: frontend odustaje na 180 s
(`vindex.js:3628`, `while elapsed < 180`), pa posle toga ponovna upotreba ne može
nikome pomoći — može samo da blokira retry koji je frontend upravo predložio.

Prag **namerno ne važi za `running`**: taj posao stvarno radi, a prekidanje bi
naplatilo drugih 6 kredita za jednu advokatovu radnju.

### 3.2 `shared/case_context.py` — tenant izolacija na izvoru

Od 7 upita samo `predmeti` je nosio `.eq("user_id", uid)`. Ostalih 6 filtrirali
su isključivo po `predmet_id`, pa su za tuđ predmet **tuđi nazivi fajlova,
datumi ročišta i tekst komentara prolazili kroz memoriju procesa**.

Filter nije bio moguć svuda: **`case_actions` nema kolonu `user_id`** (migracija
099), a dodavanje filtera na tabelu bez te kolone tiho bi ispraznilo kontekst —
tačno `predmet_klijenti` kvar iz ranije istorije ovog projekta.

Zato **jedna strukturna izmena umesto pet filtera**: upit nad `predmeti` ide
sinhrono i prvi; `gather` ostalih 6 se ne konstruiše ako vlasništvo nije
potvrđeno.

| | Pre | Posle |
|---|---|---|
| Tuđ predmet | 7 upita | **1** |
| Vlasnik | 8 upita | 8 · rezultat **bajt-identičan** (sha256 zakucan u test) |
| Cena | — | +1 serijalizovan round-trip na uspešnoj putanji |

### 3.3 `shared/ai_client.py` — ulazni guard je postao merljiv

`_analyze` je bio vezan u zatvorenju wrappera, pa **nijedan test nije mogao da
dokaže da se stvarno poziva**. Postojeći su tvrdili „injection nije stigao do
provajdera" — što bi bilo tačno i da poziv nije stigao dotle iz drugog razloga.

Uveden modulski `_analyze_ref` koji wrapper čita pri svakom pozivu.

> **Odstupanje od doslovnog zadatka, prijavljeno:** stroža varijanta (prazna
> referenca = odmah odbij) oborila je 12 zelenih testova. Uzrok nije test-šum:
> `_uninstall_prompt_guard()` čisti referencu, a dve fixture ručno vraćaju
> `Completions.create` iz snimka — stanje na dva mesta koje se može razići.
> Rešenje: prazna referenca → jedan pokušaj kanonskog uvoza → tek onda odbijanje.
> Bezbednosna tvrdnja je *„nijedan neproveren poziv ne prolazi"*, ne *„referenca
> mora biti popunjena"*. Napisana su **dva** testa umesto jednog.

### 3.4 `routers/strategija.py` — `predmet_id` u telemetriji naplate

Migracija 112 je primenjena i `_kanonski_uuid` guard postoji — ali se **nikad
nije izvršavao**: 138 poziva `UsageService.consume` u repou, nijedan nije
prosleđivao `predmet_id`.

Sada **svih 9** endpointa prosleđuje. Iznos naplate nepromenjen — AST poređenje
svih 9 poziva pokazuje da je jedina razlika novi keyword. Orkestrator i dalje
nema `multiplier=`, pa cena ostaje 6× iz registra.

### 3.5 `.gitignore` — `.bak` u javno montiranom `/static`

`*.html.bak` je pokrivao samo HTML, a `static/vindex.js.bak` stoji u direktorijumu
koji je javno montiran (`api.py:817`). Dodato `*.js.bak` / `*.css.bak`, sa
negativnom kontrolom da pravi fajlovi nisu zahvaćeni.

---

# 4. TESTS ADDED/CHANGED

### Novi — 4 fajla

| Fajl | Šta dokazuje |
|---|---|
| `test_wave11_jobs_dedupe.py` | `pending` preko praga → nov posao; **ispod praga → i dalje se koristi** (negativna kontrola); `running` star 3× prag → ne prekida se |
| `test_wave11_context_isolation.py` | broji **izvršene upite po tabeli**, ne sadržaj odgovora; 3 negativne kontrole nad samim harness-om |
| `test_wave11_guard_and_provenance.py` | špijun nad analizatorom se stvarno poziva — **tvrdnja koju do sada niko nije mogao da napiše** |
| `test_wave11_release_identity.py` | sprega `vindex.js` ↔ `sw.js`, sa dve negativne kontrole nad **pravim commit-ima ovog repoa** |

### Prepisani — 3 vakuumska testa, nijedan obrisan, sva tri pooštrena

**`test_wave7_ab_forensics::test_f`** je *reimplementirao* sha256 formulu u
sopstvenom telu i poredio dve svoje kopije — nikad nije dodirnuo produkciju.
Docstring je pritom tvrdio *„Runtime provera, ne čitanje izvora"*. Sada čita
`dedupe_key` koji stvarno stigne do `create_job_deduped`.

**Append-only trigger** nije bio dokazan **nijednim** testom: migracija 043, u
kojoj `trg_protect_audit_immutable` jedino živi, nije bila ni u jednom lancu.
Tvrdnja *„upisan red se ne može obrisati"* — na koju se ceo ovaj program poziva —
počivala je na tome što `.sql` fajl postoji u repou. Sada je 043 na čelu lanca,
a UPDATE i DELETE moraju dići izuzetak, uz pozitivnu kontrolu nad nezaštićenom
tabelom.

**`test_phantom_ai_charges::test_g`** je bežao u `pytest.skip`. Skip nije bio
činjenica o okruženju nego o kodu — a takva se meri.

### Izolacija stanja

`test_rc_beta_flows.py` je dobio `autouse` fixture koja prazni `routers.jobs._jobs`.
**Nijedna tvrdnja nijednog testa nije menjana.**

---

# 5. MUTATION RESULTS

**13 mutacija, sve obaraju očekivane testove.**

| Mutacija | Rezultat |
|---|---|
| uklonjen `pending` prag | *„zahtev je ponovo vezan za posao koji stoji u `pending` preko praga"* |
| prag primenjen i na `running` | *„posao koji STVARNO radi je prekinut — jedna advokatova radnja naplaćena dvaput"* |
| uklonjen `_jobs` fixture | **6 od 8 seed-ova palo** |
| uklonjena gate-first zaštita | *„upit nad `predmet_dokumenti` je IZVRŠEN za tuđ predmet (brojač=1)"* · `assert 6 == 0` |
| svi upiti ugašeni | pozitivna kontrola pala — 3 testa |
| analizator tiho propušta | `DID NOT RAISE GovernanceUnavailable` |
| vraćena zatvorena `_analyze` | *„analizator je pozvan 0 puta za JEDAN AI poziv"* |
| uklonjen `predmet_id=` iz naplate | `assert None == 'aaaaaaaa-…'` |
| `predmet_id` van dedupe ključa | **stari `test_f` zelen, novi PADA** |
| `DROP TRIGGER` posle 043 | `DID NOT RAISE RaiseException` × 2 |
| commit `f87f9e45~1`→`f87f9e45` | *„menja `vindex.js`, a `CACHE_NAME` je ostao `vindex-v122`"* |

---

# 6. FULL REGRESSION

| Redosled | Rezultat |
|---|---|
| Fiksni (`-p no:randomly`) | **4818 passed / 1 skipped / 0 failed** · 332 s |
| `--randomly-seed=1` | **4818 / 1 / 0** |
| `--randomly-seed=3` | **4818 / 1 / 0** |
| `--randomly-seed=7` | **4818 / 1 / 0** |

**+60 testova. 0 padova. 0 novih skipova.** Jedini `skipped` je i dalje
`test_apr_integration.py:394` — namerni live-network test iza env prekidača.

## Ovo je bio pravi blocker sprinta

Baseline `4758 / 0 failed` bio je **jedan uzorak jednog `pytest-randomly`
seed-a**. Sa fiksiranim seed-ovima, `tests/test_rc_beta_flows.py` — fajl koji
RC gate uvodi *da bi dokazao 6 beta tokova* — padao je na **6 od 8** pokušaja.

Uzrok: `test_d4` je ostavljao trajno-`pending` posao u `_jobs`, produkcionom
globalnom objektu; `test_d3` i `test_c2` su se na njega deduplikovali i **uopšte
nisu izvršavali granu koju tvrde da mere**.

> Test koji čuva naplatu bio je taj koji je obarao test koji čuva neuspeh.

Zamrznuto zeleno koje se sledeći put samo od sebe pretvori u crveno nije
baseline nego kockanje. Sada su četiri nezavisna redosleda zelena.

---

# 7. REMAINING KNOWN RISKS

Nijedan nije nov. Nijedan nije izmišljen da popuni sekciju.

| Rizik | Zašto ostaje | Beta-blocking? | Traži arhitekturu? | Odluka |
|---|---|---|---|---|
| **`case_actions` nema `user_id`** | Šema (migr. 099). Izolacija te tabele počiva na gate-u iznad + neposgodivom UUID-u. Gate-first je sada strukturno obezbeđen u `case_context`. | **NE** | DA — migracija + backfill | **DEFERRED** |
| **`predmet_id` NULL van `strategija.py`** | 113 poziva `consume` u ostatku repoa i dalje ne prosleđuje. Čista telemetrija; naplata je tačna. | **NE** | NE — po jedan keyword po pozivu | **DEFERRED** |
| **Voice raw WSS van firewall-a** | Voice je van bete; kanal je fail-closed i kill-switch-ovan (Wave 9). | **NE** | DA | **DEFERRED** |
| **Cohere van chokepoint-a** | Trostruki opt-in, podrazumevano isključen (Wave 9). | **NE** | NE | **DEFERRED** |
| **ESCALATE ne ulazi u `ai_forensics`** | Ide u append-only ledger + strukturisan log; `correlation_id` spaja. | **NE** | NE | **DEFERRED** |
| **`_cleanup` briše i `running` posao** | Briše po `created_at` bez obzira na status. Klijent ionako odustaje na 180 s. | **NE** | NE — jedan uslov | **DEFERRED** |
| **7 modula bez pre-flight kapije** | Izloženost 1 GPT poziv umesto 8. | **NE** | NE | **DEFERRED** |
| **Produkcioni `/api/version`** | 403 na ivici (bot zaštita); nije se zaobilazilo. | **NE** | — | **Vlasnik u pretraživaču** |

Migracije 111 i 112 su **ZATVORENE** i ne pojavljuju se ovde.

---

# 8. RELEASE STATUS

```
KNOWN BETA-CRITICAL PROBLEMS  =  CLOSED     (20/20; 6 unapređeno iz STABILIZED)
CRITICAL RUNTIME CONTRACTS    =  ENFORCED   (A billing · B context · C governance · D environment)
REGRESSION                    =  GREEN      (4818/1/0, cetiri nezavisna redosleda)
WORKTREE                      =  CLEAN
```

## 🟢 **VERDICT: GREEN — BETA BASELINE FROZEN**

HEAD: `e1a99018`

**Inženjersko širenje se ovde zaustavlja.** Sledeća faza je stvarna beta
upotreba, ne još jedan forenzički sprint.

---

## Najvredniji nalaz ovog sprinta

Nije nijedan od šest zatvorenih defekata. Nego ovo:

> **Baseline koji se spremao za zamrzavanje nije se reprodukovao.**
> Fajl koji je RC gate uveo *da bi dokazao 6 beta tokova od kraja do kraja*
> padao je u tri četvrtine mogućih redosleda — jer je jedan njegov test trovao
> sledeći kroz produkcioni globalni objekat.

Ista klasa greške koju je RC gate zabeležio kao *„Wave 6 popravka je razoružala
Wave 6 test"* — samo jedan sloj niže. Sada su četiri nezavisna redosleda zelena,
i tek to je baseline koji sme da se zamrzne.
