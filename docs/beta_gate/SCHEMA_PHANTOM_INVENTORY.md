# SCHEMA PHANTOM INVENTORY — §2 fantomska šema

**Baseline:** `2a2e799c` · **Režim:** READ-ONLY (nijedan DDL/DML nije izvršen; sve produkcijske
provere su `GET /rest/v1/...?select=<kolona>&limit=0` sonde).

**Izvor istine za produkciju:** PostgREST OpenAPI koren (`GET {SUPABASE_URL}/rest/v1/`) —
**166 objekata, 1.631 kolona, 16 RPC funkcija**. Svaka tvrdnja „kolona ne postoji" dole je
potvrđena live sondom koja je vratila `HTTP 400 / SQLSTATE 42703`.

**Metod (kod):** sweep nad 1.816 fajlova (`*.py`, `*.js`, `*.html`, `*.ts`, `*.tsx`, `*.vue`,
`*.sql`, `*.json`, `*.md`); 1.533 direktna pristupna mesta + 29 razrešenih indirektnih
(helper-funkcije koje primaju ime tabele kao literal). Backend = `.table("x")`/`.from_("x")` u
`*.py`; frontend = `.from('x')` u `*.js`/`*.html`. Docstring nije ugovor — merodavan je kod.

---

## 0. Rezime

| Kategorija | Broj |
|---|---|
| Objekata u produkciji | 166 |
| Referenciraju i backend i frontend | 1 |
| Samo backend | 147 |
| Samo frontend | 1 |
| Referencira ih SAMO test kod | 3 |
| Ne referencira ih NIKO | 14 |
| **A** — nema ni u produkciji ni u migracijama | 3 |
| **B** — ima u migracijama, nema u produkciji | 3 |
| **C** — ima u oba, šema se razlikuje | 3 |
| **D** — tabela postoji, ali runtime koristi nepostojeće kolone | **23 tabela / 64 kolona** |
| Fantomskih RPC poziva | 0 |
| RPC u produkciji koje niko ne poziva | 4 |

---

## 1. Kategorija D — tabela postoji, kolone ne postoje (NAJVREDNIJA)

Sve dole navedene kolone su **live sondirane** i vraćaju `42703 column ... does not exist`.
PostgREST odbija ceo zahtev (HTTP 400) — nije reč o tihom ignorisanju polja.

Pun ugovor po objektu (§1) je u `docs/beta_gate/SCHEMA_CONTRACT_166.csv`.

### `billing_entries` — P1 — 7 nepostojećih kolona

- **Nedostaje pri čitanju:** `cena_po_jedinici`, `fakturisano`, `iznos`, `jedinica`, `klijent_id`, `kolicina`, `ukupno`
- **Nedostaje pri upisu:** —
- **Stvarne kolone u produkciji:** `bodovi`, `created_at`, `datum`, `faktura_id`, `id`, `iznos_rsd`, `obracunato`, `opis`, `predmet_id`, `sati`, `tarifa_naziv`, `tarifa_sifra`, `tip`, `updated_at`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/billing_reports.py:176` | R | `klijent_id` |
| `routers/billing_reports.py:235` | R | `klijent_id` |
| `routers/ccc.py:68` | R | `iznos` |
| `routers/health_index.py:89` | R | `iznos` |
| `routers/multi_agent.py:595` | R | `cena_po_jedinici`, `fakturisano`, `jedinica`, `kolicina`, `ukupno` |
| `routers/outcome_intel.py:179` | R | `iznos` |

### `case_actions` — P0 — 1 nepostojeća kolona

- **Nedostaje pri čitanju:** `user_id`
- **Nedostaje pri upisu:** —
- **Stvarne kolone u produkciji:** `closed_at`, `confidence`, `correlation_id`, `created_at`, `dedupe_key`, `dokaz`, `event_id`, `id`, `izvor_dokumenti`, `kreirao`, `predmet_id`, `prioritet`, `razlog`, `rok`, `status`, `tip`, `updated_at`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/predmeti_close.py:211` | W | `user_id` |
| `routers/predmeti_close.py:396` | W | `user_id` |

### `case_patterns` — P0 — 3 nepostojećih kolona

- **Nedostaje pri čitanju:** `ukupno_predmeta`, `uspeh_stopa`, `uzoraka`
- **Nedostaje pri upisu:** `ukupno_predmeta`
- **Stvarne kolone u produkciji:** `faktor`, `id`, `pobede`, `porazi`, `tip_spora`, `ukupno`, `updated_at`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/benchmarking.py:350` | R | `uzoraka` |
| `routers/court_predictor.py:1637` | R | `uzoraka` |
| `routers/court_predictor.py:1790` | R | `uzoraka` |
| `services/learning_engine.py:202` | R | `ukupno_predmeta` |
| `services/learning_engine.py:219` | W | `ukupno_predmeta` |
| `services/learning_engine.py:228` | W | `ukupno_predmeta` |
| `services/learning_engine.py:329` | R | `ukupno_predmeta`, `uspeh_stopa` |

### `chain_anchors` — P1 — 2 nepostojećih kolona

- **Nedostaje pri čitanju:** `anchored_at`
- **Nedostaje pri upisu:** `anchored_at`, `hash_256`
- **Stvarne kolone u produkciji:** `created_at`, `date`, `id`, `record_count`, `root_hash`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `api.py:1842` | R | `anchored_at` |
| `api.py:2195` | W | `anchored_at`, `hash_256` |
| `api.py:2203` | W | `anchored_at`, `hash_256` |
| `routers/admin_dashboard.py:246` | R | `anchored_at` |
| `routers/proof.py:290` | R | `anchored_at` |

### `client_portal_tokens` — P0 — 1 nepostojeća kolona

- **Nedostaje pri čitanju:** —
- **Nedostaje pri upisu:** `klijent_pregledao`
- **Stvarne kolone u produkciji:** `created_at`, `expires_at`, `id`, `is_active`, `klijent_email`, `predmet_id`, `token_hash`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/client_portal.py:860` | W | `klijent_pregledao` |

### `decision_log` — P0 — 3 nepostojećih kolona

- **Nedostaje pri čitanju:** `alternativa`, `opis`, `tip_odluke`
- **Nedostaje pri upisu:** `opis`, `tip_odluke`
- **Stvarne kolone u produkciji:** `akcija`, `alternative`, `created_at`, `id`, `kontekst`, `predmet_id`, `urgentnost`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/case_intelligence.py:159` | R | `alternativa`, `opis`, `tip_odluke` |
| `routers/case_intelligence.py:484` | W | `opis`, `tip_odluke` |
| `routers/case_intelligence.py:554` | R | `opis`, `tip_odluke` |
| `routers/decision_replay.py:89` | R | `alternativa`, `opis`, `tip_odluke` |

### `fakture` — P1 — 2 nepostojećih kolona

- **Nedostaje pri čitanju:** `iznos_rsd`, `klijent_id`
- **Nedostaje pri upisu:** —
- **Stvarne kolone u produkciji:** `broj_fakture`, `created_at`, `datum_dospeca`, `datum_fakture`, `id`, `is_proforma`, `iznos_bez_pdv`, `iznos_sa_pdv`, `klijent_adresa`, `klijent_naziv`, `klijent_pib`, `napomena`, `pdv_iznos`, `predmet_id`, `status`, `updated_at`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/billing_reports.py:72` | R | `iznos_rsd`, `klijent_id` |
| `routers/billing_reports.py:407` | R | `iznos_rsd`, `klijent_id` |
| `routers/billing_reports.py:542` | R | `iznos_rsd` |

### `feedback` — P0 — 1 nepostojeća kolona

- **Nedostaje pri čitanju:** —
- **Nedostaje pri upisu:** `q_hash`
- **Stvarne kolone u produkciji:** `created_at`, `id`, `tip`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/drafting.py:830` | W | `q_hash` |

### `kancelarija_clanovi` — P0 — 1 nepostojeća kolona

- **Nedostaje pri čitanju:** `clan_id`
- **Nedostaje pri upisu:** —
- **Stvarne kolone u produkciji:** `email`, `id`, `invited_at`, `invited_by`, `joined_at`, `kancelarija_id`, `removed_at`, `removed_reason`, `status`, `suspended_at`, `uloga`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `workers/background_agents.py:91` | R | `clan_id` |
| `workers/background_agents.py:110` | R | `clan_id` |

### `klijent_komunikacija` — P0 — 2 nepostojećih kolona

- **Nedostaje pri čitanju:** `created_at`, `kanal`
- **Nedostaje pri upisu:** —
- **Stvarne kolone u produkciji:** `datum_vreme`, `id`, `klijent_id`, `kratak_opis`, `kreirano`, `tip`, `ucesnik_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `klijenti/router.py:1428` | R | `created_at`, `kanal` |

### `klijenti` — P0 — 7 nepostojećih kolona

- **Nedostaje pri čitanju:** `created_at`, `jmbg_mb`, `napomene`, `naziv_firme`, `naziv_kompanije`, `pib`, `tip_lica`
- **Nedostaje pri upisu:** —
- **Stvarne kolone u produkciji:** `adresa`, `aktivan`, `azurirano`, `broj_pasosa_encrypted`, `connected_persons`, `datum_nastanka`, `datum_poslednje_aktivnosti`, `deleted_at`, `email`, `firma`, `id`, `ime`, `jmbg_encrypted`, `kreirano`, `maticni_broj`, `napomena`, `pib_encrypted`, `pravni_osnov_obrade`, `prezime`, `saglasnost_datum`, `saglasnost_dokument_id`, `status`, `telefon`, `tip`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `klijenti/router.py:246` | R | `created_at` |
| `routers/billing_reports.py:81` | R | `naziv_firme` |
| `routers/billing_reports.py:183` | R | `naziv_firme` |
| `routers/billing_reports.py:241` | R | `naziv_firme` |
| `routers/billing_reports.py:414` | R | `naziv_firme` |
| `routers/client_twin.py:93` | R | `napomene`, `tip_lica` |
| `routers/conflict_check.py:207` | R | `pib` |
| `routers/morning_briefing.py:133` | R | `naziv_kompanije` |
| `routers/search.py:60` | R | `naziv_firme`, `pib` |
| `scripts/migrate_jmbg_encrypt.py:60` | R | `jmbg_mb` |
| `scripts/migrate_jmbg_encrypt.py:67` | R | `jmbg_mb` |

### `lessons_learned` — P0 — 1 nepostojeća kolona

- **Nedostaje pri čitanju:** `sadrzaj`
- **Nedostaje pri upisu:** —
- **Stvarne kolone u produkciji:** `broj_predmeta`, `created_at`, `grupa_id`, `id`, `kategorija`, `lecija`, `oblast_prava`, `period_do`, `period_od`, `poslednji_pristup`, `potvrdio`, `potvrdjeno_at`, `pouzdanost`, `predmet_id`, `primenjljivo_na`, `pristupi`, `status_lekcije`, `tip_spora`, `user_id`, `vaznost`, `zastarela`, `zastarela_at`, `zastarela_razlog`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/case_intelligence.py:123` | R | `sadrzaj` |
| `routers/cio.py:309` | R | `sadrzaj` |
| `routers/learning.py:804` | R | `sadrzaj` |
| `services/knowledge_hygiene.py:48` | R | `sadrzaj` |
| `services/knowledge_hygiene.py:266` | R | `sadrzaj` |

### `predmet_beleske` — P0 — 2 nepostojećih kolona

- **Nedostaje pri čitanju:** —
- **Nedostaje pri upisu:** `tekst`, `tip`
- **Stvarne kolone u produkciji:** `created_at`, `id`, `predmet_id`, `sadrzaj`, `updated_at`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/doc_templates.py:232` | W | `tekst`, `tip` |

### `predmet_dokumenti` — P0 — 1 nepostojeća kolona

- **Nedostaje pri čitanju:** —
- **Nedostaje pri upisu:** `session_id`
- **Stvarne kolone u produkciji:** `ai_tags`, `content_sha256`, `created_at`, `id`, `klasifikovan_at`, `naziv_fajla`, `pinecone_namespace`, `pravni_elementi`, `predmet_id`, `redni_broj`, `source_intake_job_id`, `source_intake_job_segment_id`, `status`, `storage_path`, `tekst_sadrzaj`, `tip_dokaza`, `user_id`, `velicina_kb`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/intake.py:318` | W | `session_id` |

### `predmet_hronologija` — P0 — 2 nepostojećih kolona

- **Nedostaje pri čitanju:** `naziv`, `tip_roka`
- **Nedostaje pri upisu:** —
- **Stvarne kolone u produkciji:** `akter`, `created_at`, `datum`, `datum_iso`, `dogadjaj`, `dokument_naziv`, `id`, `predmet_id`, `user_id`, `vaznost`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/client_portal.py:452` | R | `tip_roka` |
| `routers/voice.py:142` | R | `naziv` |

### `predmet_komentari` — P0 — 1 nepostojeća kolona

- **Nedostaje pri čitanju:** `created_at`
- **Nedostaje pri upisu:** —
- **Stvarne kolone u produkciji:** `id`, `izmenjeno`, `kreirano`, `predmet_id`, `tekst`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/case_commander.py:156` | R | `created_at` |
| `routers/case_commander.py:620` | R | `created_at` |
| `routers/client_twin.py:110` | R | `created_at` |
| `routers/dashboard.py:459` | R | `created_at` |
| `routers/digital_twin.py:176` | R | `created_at` |
| `routers/evidence_graph.py:214` | R | `created_at` |
| `routers/komentari.py:100` | R | `created_at` |
| `shared/case_context.py:276` | R | `created_at` |

### `predmeti` — P0 — 12 nepostojećih kolona

- **Nedostaje pri čitanju:** `datum_otvaranja`, `datum_zatvaranja`, `ishod`, `klijent_id`, `oblast`, `oblast_prava`, `protivnik`, `stranka`, `stranke`, `sud`, `tip_postupka`, `tip_spora`
- **Nedostaje pri upisu:** `oblast`
- **Stvarne kolone u produkciji:** `broj_predmeta`, `case_dna`, `created_at`, `id`, `kanban_faza`, `naziv`, `opis`, `rizik`, `status`, `tip`, `tuzeni`, `tuzilac`, `updated_at`, `user_id`, `vrednost_spora`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/case_commander.py:606` | R | `protivnik`, `sud`, `tip_postupka` |
| `routers/case_intelligence.py:111` | R | `klijent_id`, `oblast_prava` |
| `routers/ccc.py:27` | R | `oblast` |
| `routers/cio.py:270` | R | `oblast_prava` |
| `routers/client_twin.py:101` | R | `ishod`, `klijent_id` |
| `routers/decision_replay.py:81` | R | `datum_otvaranja`, `datum_zatvaranja`, `ishod`, `oblast_prava` |
| `routers/evidence_graph.py:198` | R | `oblast` |
| `routers/gdpr.py:176` | R | `tip_spora` |
| `routers/health_index.py:327` | R | `oblast` |
| `routers/intelligence_timeline.py:61` | R | `oblast` |
| `routers/knowledge_graph.py:29` | R | `oblast` |
| `routers/matter_intel.py:515` | R | `sud` |
| `routers/morning_briefing.py:106` | R | `protivnik`, `stranka` |
| `routers/precedenti.py:62` | R | `oblast` |
| `routers/precedenti.py:73` | R | `oblast` |
| `routers/precedenti.py:80` | R | `oblast` |
| `routers/precedenti.py:87` | R | `oblast` |
| `routers/strategy_simulator.py:122` | R | `stranke` |
| `routers/voice.py:121` | R | `oblast` |
| `services/agent_tasks/court_portal_watcher.py:166` | R | `oblast_prava` |
| `services/agent_tasks/precedents_radar.py:108` | R | `oblast_prava` |
| `api.py:4249 (PATCH whitelist `allowed`)` | W | `oblast` |

### `proactive_alerts` — P0 — 3 nepostojećih kolona

- **Nedostaje pri čitanju:** `hitnost`, `tekst_alerta`, `tip_alerta`
- **Nedostaje pri upisu:** —
- **Stvarne kolone u produkciji:** `created_at`, `id`, `naslov`, `opis`, `predmet_id`, `procitana`, `tip`, `urgentnost`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/decision_replay.py:130` | R | `hitnost`, `tekst_alerta`, `tip_alerta` |

### `profiles` — P0 — 3 nepostojećih kolona

- **Nedostaje pri čitanju:** `benchmark_opt_in`
- **Nedostaje pri upisu:** `benchmark_opt_in`, `naziv_firme`, `specijalizacija`
- **Stvarne kolone u produkciji:** `addons`, `briefing_aktivan`, `created_at`, `credits_remaining`, `digitalna_imovina_aktivirano`, `digitalna_imovina_standalone`, `email`, `full_name`, `id`, `is_pro`, `onboarding_done`, `plan`, `registered_at`, `subscription_expires_at`, `subscription_seats_extra`, `subscription_type`, `trial_kraj`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `api.py:2849` | W | `naziv_firme`, `specijalizacija` |
| `routers/benchmarking.py:107` | W | `benchmark_opt_in` |
| `routers/benchmarking.py:143` | R | `benchmark_opt_in` |
| `routers/predmeti_close.py:141` | R | `benchmark_opt_in` |

### `recommendation_log` — P0 — 5 nepostojećih kolona

- **Nedostaje pri čitanju:** `ishod`, `preporuka`, `tip_slucaja`
- **Nedostaje pri upisu:** `tekst`, `tip`
- **Stvarne kolone u produkciji:** `bila_tacna`, `confidence_band`, `confidence_score`, `created_at`, `id`, `ishod_pozitivan`, `izvori_tezina`, `kontekst`, `oblast_prava`, `predmet_id`, `prihvacena`, `tekst_preporuke`, `tip_preporuke`, `user_id`, `valid_until`, `zastarela`, `zastarela_razlog`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/confidence_audit.py:80` | R | `preporuka`, `tip_slucaja` |
| `routers/court_predictor.py:1829` | R | `ishod` |
| `routers/decision_replay.py:113` | R | `preporuka`, `tip_slucaja` |
| `services/confidence_auditor.py:288` | R | `preporuka`, `tip_slucaja` |
| `services/learning_engine.py:61` | W | `tekst`, `tip` |

### `rocista` — P0 — 2 nepostojećih kolona

- **Nedostaje pri čitanju:** `naziv`, `tip_rocista`
- **Nedostaje pri upisu:** —
- **Stvarne kolone u produkciji:** `broj_predmeta_suda`, `created_at`, `datum`, `id`, `napomena`, `predmet_id`, `status`, `sud`, `sudnica`, `updated_at`, `user_id`, `vreme`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/knowledge_graph.py:139` | R | `tip_rocista` |
| `routers/whatsapp_notif.py:425` | R | `naziv` |

### `timer_sessions` — P0 — 1 nepostojeća kolona

- **Nedostaje pri čitanju:** —
- **Nedostaje pri upisu:** `tip`
- **Stvarne kolone u produkciji:** `aktivan`, `created_at`, `id`, `opis`, `predmet_id`, `start_at`, `stop_at`, `trajanje_s`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/intake.py:381` | W | `tip` |

### `usage_events` — P1 — 1 nepostojeća kolona

- **Nedostaje pri čitanju:** —
- **Nedostaje pri upisu:** `meta`
- **Stvarne kolone u produkciji:** `action`, `created_at`, `feature`, `id`, `metadata`, `predmet_id`, `user_id`

| Mesto u kodu | Smer | Kolone |
|---|---|---|
| `routers/voice.py:569` | W | `meta` |
| `workers/background_agents.py:180` | W | `meta` |

### D-dodatak — pokvarena PostgREST `embed` relacija

Pored kolona, jedna ugrađena (embed) relacija ne postoji u produkciji:

| Mesto | Upit | Rezultat sonde |
|---|---|---|
| `routers/zadaci.py:256` | `zadaci.select("*, predmeti(naziv)")` | `HTTP 400 PGRST200` — nema FK veze `zadaci` → `predmeti` u šemi `public` |

Ostalih 6 embed relacija u kodu (`kancelarija_clanovi→kancelarije`, `predmet_hronologija→predmeti`,
`predmet_klijenti→klijenti`, `predmet_klijenti→predmeti`, `predmeti→predmet_klijenti`,
`workflow_steps→workflow_instances`) su sondirane i **rade**.

---

## 2. Kategorija A — nema ni u produkciji ni u migracijama

| Tabela | Krit. | Mesta u kodu | Sonda |
|---|---|---|---|
| `klijenti_dokumenti` | P0 | 1 × — `klijenti/router.py:1422` | `404 PGRST205` — hint: `public.klijent_dokumenti` |
| `rokovi` | P0 | 13 × — `api.py:2639`, `routers/case_commander.py:134`, `routers/case_commander.py:610`, `routers/dashboard.py:141` … | `404 PGRST205` |
| `user_activity_profile` | P0 | 1 × — `security/anomaly_detection.py:153` | `404 PGRST205` — hint: `public.firm_style_profile` |

---

## 3. Kategorija B — ima u migracijama, nema u produkciji

| Tabela | Krit. | Definisana u | Mesta u kodu | Sonda |
|---|---|---|---|---|
| `api_costs` | P0 | `supabase_migration.sql` | `shared/cost.py:97` | `404 PGRST205` |
| `ratio_decidendi` | P2 | `supabase_migration.sql` | `routers/praksa.py:311`, `routers/praksa.py:330` | `404 PGRST205` |
| `reported_errors` | P0 | `supabase_migration.sql` | `static/vindex.js:8068` | `404 PGRST205` |

Napomena: sve tri su definisane **isključivo** u legacy `supabase_migration.sql` /
`supabase_setup.sql`, nikada u numerisanom `migrations/` lancu — dakle nikad primenjene.

Dodatno: `vindex_memory` postoji u migracijama (`075_remove_vindex_memory.sql` je uklanja),
nema je u produkciji, i **nijedan kod je ne referencira** — uredno zatvoreno, nije nalaz.

---

## 4. Kategorija C — postoji u oba, šema se razlikuje

Kolone deklarisane u SQL fajlovima repoa kojih **nema** u produkciji (sve sondirane):

| Tabela | Kolone iz migracija koje nedostaju u produkciji | Fajl |
|---|---|---|
| `evidence_grafovi` | `updated_at` | `057_active_orphaned_tables.sql` |
| `feedback` | `odgovor`, `pitanje`, `q_hash` | `supabase_migration.sql`, `supabase_setup.sql` |
| `push_subscriptions` | `created_at` | `057_active_orphaned_tables.sql` |

`feedback` je ujedno i D-nalaz: `supabase_setup.sql` deklariše `pitanje`/`odgovor`/`q_hash`,
produkcijska tabela ima samo `id, user_id, tip, created_at`, a `routers/drafting.py:830`
upisuje `q_hash`. Tj. tabela je u produkciji nastala iz drugog izvora nego što repo tvrdi.

---

## 5. RPC funkcije (16 u produkciji)

**Fantomskih RPC poziva: 0.** Svih 12 RPC imena koja kod poziva postoje u produkciji.

| RPC | Poziva ga kod | Status |
|---|---|---|
| `_sec031_fix_fk` | — | MRTAV — nema pozivaoca u repou |
| `claim_intake_finalize` | 1 | koristi se |
| `claim_intake_job` | 1 | koristi se |
| `claim_pending_events` | 1 | koristi se |
| `complete_intake_job` | 1 | koristi se |
| `deduct_credit` | 5 | koristi se |
| `deduct_n_credits` | 2 | koristi se |
| `enqueue_intake_job` | 1 | koristi se |
| `fail_intake_job` | 1 | koristi se |
| `get_activity_averages` | 1 | koristi se |
| `get_next_broj_fakture` | — | MRTAV — nema pozivaoca u repou |
| `increment_feature_usage` | 1 | koristi se |
| `increment_monthly_usage` | 1 | koristi se |
| `refund_n_credits` | 1 | koristi se |
| `refund_one_credit` | — | MRTAV — nema pozivaoca u repou |
| `set_user_pro` | — | MRTAV — nema pozivaoca u repou |

- `refund_one_credit` je mrtva jer `shared/deps.py::_refund_one_credit` delegira na
  `refund_n_credits(user_id, 1)`.
- `get_next_broj_fakture` i `set_user_pro` su zaključane migracijom 102 i nemaju pozivaoca.
- `_sec031_fix_fk` je jednokratni migracioni helper iz `077_…`, ne runtime RPC.
- `scripts/migration_drift_check.py:121` namerno poziva nepostojeći
  `vindex_drift_control_xyz` kao negativnu kontrolu — nije fantom.

---

## 6. Objekti bez ijedne reference u kodu

Postoje u produkciji, ali ih ne dodiruje ni backend ni frontend ni testovi.
Broj redova očitan `Prefer: count=exact` sondom.

| Objekat | Redova u produkciji |
|---|---|
| `agent_runs` | 17 |
| `applications` | 1 |
| `feature_analytics` | 0 |
| `filter_results` | 301 |
| `firma_clanovi` | 0 |
| `firma_pozivnice` | 0 |
| `impact_metrics` | 0 |
| `jobs` | 301 |
| `klijenti_retention_candidates` | 0 |
| `plan_limits` | 4 |
| `system_state` | 7 |
| `uploaded_documents` | 0 |
| `v_manual_queue` | 0 |
| `v_qualified_jobs` | 0 |

---

## 7. Granice ovog nalaza (šta NIJE dokazano)

| Ograničenje | Posledica |
|---|---|
| 26 mesta ima `.insert()`/`.update()` sa payload-om u promenljivoj; 9 je pročitano ručno (§7.1), 17 ostaje statički nerazrešivo | njihov skup upisanih kolona je **UNKNOWN**, ne „prazan" |
| 33 poziva `.table(<promenljiva>)` — 8 razrešeno iz literalnih lista, ostali su generički helperi (`scripts/`, `tests/`) | ime tabele na tim mestima je **UNKNOWN** |
| `select("*")` ne otkriva koje kolone kod zaista čita iz odgovora | D-nalazi su donja granica |
| Sonde dokazuju **postojanje** kolone, ne tip/NOT NULL/RLS ponašanje | tipska neslaganja nisu pokrivena |

### 7.1 Blind spots pročitani ručno i zatvoreni

| Mesto | Payload | Ishod |
|---|---|---|
| `api.py:4277` | `allowed` | **NALAZ** — whitelist `{naziv, opis, tip, status, tuzilac, tuzeni, oblast, rizik, vrednost_spora}` sadrži `oblast`, kolone nema u produkciji |
| `security/chain_anchor.py:157` | `payload` | čisto — `date, root_hash, record_count, created_at` sve postoje |
| `routers/evidence.py:299` | `rows` | čisto — `stranica/paragraf/start_offset/end_offset` postoje (migracija 080 JESTE primenjena) |
| `routers/evidence.py:315` | `legacy_rows` | čisto — podskup prethodnog |
| `services/confidence_auditor.py:117` | `rows_to_upsert` | čisto — svih 8 kolona postoji |
| `routers/intake.py:371` | `r` | čisto — `billing_row` koristi samo postojeće kolone |
| `routers/intake.py:415` | `hron_rows` | čisto — svih 7 kolona postoji |
| `routers/intake.py:324` | `r` | čisto (`_doc_row`) — ali obuhvatajući poziv dodaje `session_id`, vidi D-nalaz `predmet_dokumenti` |
| `routers/billing.py:316` | `patch` | čisto — `opis, bodovi, sati, iznos_rsd, datum` |

### 7.2 Blind spots koji ostaju UNKNOWN

| Tabela | Mesto |
|---|---|
| `ai_forensics` | `security/ai_forensics.py:129` — `insert(safe_data)` |
| `ai_forensics` | `security/ai_forensics.py:179` — `insert(safe)` |
| `ai_forensics` | `security/ai_forensics.py:377` — `insert(safe)` |
| `ai_forensics` | `security/ai_forensics.py:411` — `insert(safe_legacy)` |
| `case_actions` | `services/case_evolution.py:1061` — `insert(r)` |
| `fakture` | `routers/recurring.py:325` — `insert(faktura_row)` |
| `feature_usage_log` | `shared/usage.py:401` — `insert(payload)` |
| `ingest_jobs` | `routers/batch_ingest.py:67` — `update(fields)` |
| `klijenti` | `klijenti/router.py:1677` — `insert(r)` |
| `klijenti` | `routers/import_klijenti.py:195` — `insert(b)` |
| `klijenti` | `routers/intake.py:978` — `insert(r)` |
| `notifications` | `routers/notifications.py:356` — `insert(new_notifs)` |
| `notifications` | `services/case_evolution.py:1201` — `update(r)` |
| `notifications` | `services/case_evolution.py:1207` — `insert(r)` |
| `predmet_dokumenti` | `api.py:5309` — `insert(_row_no_hash)` |
| `predmet_dokumenti` | `routers/smart_intake.py:1524` — `insert(r)` |
| `predmet_hronologija` | `api.py:5020` — `insert(_hrow)` |

Ukupno: 9 zatvoreno ručnim čitanjem izvora (1 nalaz), 17 ostaje UNKNOWN.

---

## 8. Status prethodno prijavljenih „poznatih fantoma"

| Ime | Status |
|---|---|
| `rokovi` | **POTVRĐEN** — 13 mesta u produkcijskom kodu, `404 PGRST205` |
| `api_costs` | **POTVRĐEN** — `shared/cost.py:97` upisuje, tabela ne postoji |
| `ratio_decidendi` | **POTVRĐEN** — `routers/praksa.py:311,330` |
| `reported_errors` | **POTVRĐEN** — `static/vindex.js:8068`; jedina fantomska tabela koja se dosegne SAMO iz frontenda (zato ju je `*.py`-only grep ranije promašio) |
| `predmet_rokovi` | **NIJE FANTOM** — ime se u celom repou pojavljuje samo kao deo naziva test funkcije (`tests/test_tau008_cio_consolidation.py:116`); nijedan kod ne pristupa toj tabeli |

Novootkrivene fantomske tabele izvan te liste: `klijenti_dokumenti` (P0, `klijenti/router.py:1422` — tipfeler, produkcija ima `klijent_dokumenti`) i `user_activity_profile` (P0, `security/anomaly_detection.py:153`).
