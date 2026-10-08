# Vindex — mapa očuvanja (šta se NE sme brisati i kada sme)

**Misija:** CAPABILITY RECOVERY FORENSICS 001 · **Osnova:** `51164c92` · **Datum:** 2026-10-08

**Osnovno pravilo:** u ovom trenutku **ništa nije bezbedno za brisanje**. Kolona „safe to remove" je svuda `NE`. Razlog: `/app-legacy` je jedina operativna rezerva i jedini put do oko 230 ruta. Prijava i odjava za V2 NG takođe žive na `/app-legacy` (NS004).

Kolone:
- **status**: primarni statusi sposobnosti iz popisa (01–15);
- **legacy-only**: `DA` = samo legacy UI ga zove; `NE` = postoji V2 pozivalac (V2 NG ili `/app-v2`); `BEZ UI` = nijedan frontend;
- **removal condition**: šta mora biti dokazano pre bilo kakvog uklanjanja.

## 1. Frontend slojevi

| file/path | capability | status | dependency | legacy-only | safe to remove | removal condition |
|---|---|---|---|---|---|---|
| `index.html`, `static/vindex.js`, `static/vx-a11y.js`, `static/supabase.min.js` | ≈ 90 sposobnosti (svi legacy tabovi) | 05 | Supabase auth, `/app-legacy` ruta | DA | NE | svi talasi 1–6 završeni po Definition of Done + founder odluka + period posmatranja bez upotrebe `/app-legacy` |
| `static/sw.js`, `/manifest.json`, `/offline` | CAP-183 PWA | 01 | CACHE_NAME raste na svaki deploy (memorija) | NE | NE | NIKAD dok postoji PWA |
| `/app-legacy` handler u `api.py` (`serve_html_legacy`) | prijava/odjava za V2 NG + rezerva | 02 | `_legacy_sa_povratkom_na_v2` | NE | NE | V2 NG dobije sopstvenu prijavu i odjavu |
| `index-v2.html`, `v2/**` (`/app-v2`) | 125 ruta: izvor gotovih frontend ugovora za talase 1–5 | 05 | `v2_pristup` (rollout, migracija 128) | NE (founder-only) | NE | svaki `v2/features/*/api.js` ugovor prenet u `frontend-v2-ng` i pokriven testom |
| `frontend-v2-ng/**` | CAP-001/002/003 | 01 | `VINDEX_V2_NG_PRIMARY_ENABLED` | NE | NE | NIKAD (primarni) |
| `site/index.html` + pravne stranice | CAP-168 | 01 | — | NE | NE | NIKAD |
| `prototype/vindex-next-app/*.html` (grana `website-rebuild-001`) | — (statički prototipovi) | — | — | — | NE (nije na main) | odluka foundera |

## 2. Biblioteke bez sopstvene rute (kritične)

| file/path | capability | status | dependency | legacy-only | safe to remove | removal condition |
|---|---|---|---|---|---|---|
| `uploaded_doc/extractor.py` | CAP-011 OCR, CAP-010, CAP-013, CAP-020, CAP-060 | 07 | tesseract, pytesseract, pymupdf, pillow, pypdf, python-docx | — | NE | NIKAD (jedini ekstraktor; 5 pozivalaca) |
| `shared/intake_worker.py`, `services/event_bus.py`, `shared/bg.py` | CAP-020, CAP-010 | 05 | startup petlje u `api.py` | — | NE | NIKAD dok postoji Smart Intake |
| `workers/background_agents.py`, `services/agent_tasks/*` | CAP-141, CAP-082, CAP-171 | 08 | `/api/cron/daily`, Render cron (UNKNOWN) | BEZ UI | NE | odluka o agentskom sloju (talas 7) + dokaz da okidač ne postoji ili je ugašen |
| `services/v2_projection.py`, `v2_observation.py`, `v2_contradiction_persistence.py` | CAP-120 Case Genome | 05 | A-serija (deployed) | — | NE | NIKAD (jedini izvor istine o predmetu) |
| `services/case_evolution.py`, `case_pipeline.py` | CAP-126, CAP-023 | 07 / 04 | Case Evolution Phase 2 (čeka) | — | NE | posle Phase 2 forenzike |
| `services/risk_engine.py`, `quality_gate.py`, `decision_log.py` | CAP-121, CAP-008, CAP-122 | 05 | deterministički brojevi | — | NE | NIKAD |
| `services/legal_reasoning_engine.py` | CAP-127 | 04 | migracija 076 | BEZ UI | NE | odluka foundera |
| `services/learning_engine.py`, `knowledge_hygiene.py`, `confidence_auditor.py`, `confidence_calibrator.py` | CAP-131, 134, 136 | 13 / 04 | `case_patterns` | BEZ UI / DA | NE | konsolidacija memorije (talas 7) |
| `services/ambient_analyzer.py`, `voice_orchestrator.py` | CAP-143, CAP-145 | 04 / 05 | Word add-in, OpenAI realtime | — | NE | odluka (talas 7) |
| `services/retention_service.py` | CAP-190 | 03 | — | BEZ UI | NE | zakonska obaveza čuvanja; ne uklanjati |
| `security/agent_isolation.py`, `shared/ai_fabric.py`, `shared/permissions.py` | bezbednosna granica za sve AI rute | — | — | — | NE | NIKAD |
| `.github/workflows/email-cron.yml` | CAP-076 | 07 | X-Cron-Key (ne poklapa se) | — | NE | NIKAD (popraviti, ne brisati) |
| `.github/workflows/sms-cron.yml` | CAP-077 | 04 | Twilio | — | NE | ako se SMS penzioniše |
| `migrations/*.sql` | sve | — | founder ih pokreće | — | **NE, nikad** | istorija šeme se ne briše |

## 3. Backend moduli (automatski izvedeno iz popisa)

| file/path | capability | status | dependency | legacy-only | safe to remove | removal condition |
|---|---|---|---|---|---|---|
| `api.py` | CAP-001, CAP-002, CAP-003, CAP-004, CAP-005, CAP-006, CAP-007, CAP-008, CAP-009, CAP-010, CAP-012, CAP-040, CAP-041, CAP-050, CAP-129, CAP-164, CAP-165, CAP-167, CAP-168, CAP-171, CAP-183, CAP-188, CAP-189 | 01/02/03/04/05/07/13 | BOT_API_KEY; BRIEFING_CRON_SECRET, Render cron (UNKNOWN); OpenAI; Pinecone zakoni,OpenAI,citation guard; Stora | NE | NE | NIKAD (živ put) |
| `klijenti/router.py` | CAP-022, CAP-030, CAP-031, CAP-032, CAP-033, CAP-036, CAP-190 | 03/05/13 | FIELD_ENCRYPTION_KEY; services/retention_service.py | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/admin_dashboard.py` | CAP-164, CAP-165 | 04/05 | chain_anchors, audit_immutable; founder-only | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/agent_notifications.py` | CAP-141 | 08 | /api/cron/daily (Render cron UNKNOWN), migracija 082, AGENT_BUDGET_PER_ORG_DAILY | BEZ UI | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/analytics.py` | CAP-097 | 05 | usage_events | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/apr.py` | CAP-184 | 05 | APR spoljni servis | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/auto_discovery.py` | CAP-048 | 05 | Pinecone | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/batch_ingest.py` | CAP-048 | 05 | Pinecone | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/benchmarking.py` | CAP-103 | 11 | više kancelarija sa podacima | DA | NE | odluka foundera + 0 poziva u prod. logovima + legacy ugašen |
| `routers/billing.py` | CAP-100 | 05 | SMTP | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/billing_reports.py` | CAP-101 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/case_actions.py` | CAP-126 | 07 | services/case_evolution.py | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/case_commander.py` | CAP-117 | 13 | OpenAI | DA | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/case_dna.py` | CAP-120 | 05 | services/v2_projection.py, v2_observation | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/case_intelligence.py` | CAP-122 | 13 | — | DA | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/case_pipeline.py` | CAP-023 | 04 | — | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/ccc.py` | CAP-125 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/cio.py` | CAP-098 | 13 | — | DA | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/client_portal.py` | CAP-034 | 05 | token pristup, Storage, SMS | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/client_twin.py` | CAP-035 | 05 | OpenAI | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/confidence_audit.py` | CAP-136 | 04 | — | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/conflict_check.py` | CAP-032 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/copilot.py` | CAP-142 | 05 | svi moduli | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/copilot_ambient.py` | CAP-143 | 04 | Word add-in distribucija | BEZ UI | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/corrections.py` | CAP-068 | 07 | — | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/court_predictor.py` | CAP-111, CAP-116 | 05/13 | OpenAI; OpenAI, case_patterns | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/cross_doc.py` | CAP-014 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/csv_import.py` | CAP-151 | 05 | blockchain API, OFAC lista | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/dashboard.py` | CAP-096 | 05 | risk_engine | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/data_export.py` | CAP-161 | 05 | Storage | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/decision_replay.py` | CAP-128 | 03 | OpenAI | BEZ UI | NE | odluka foundera + 0 poziva u prod. logovima + legacy ugašen |
| `routers/digital_twin.py` | CAP-112 | 05 | OpenAI | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/doc_templates.py` | CAP-062 | 05 | OpenAI | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/dokument.py` | CAP-013 | 05 | OCR,Pinecone,OpenAI | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/drafting.py` | CAP-060, CAP-061, CAP-063, CAP-064, CAP-065 | 05 | OpenAI; Pinecone namespace po korisniku | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/email_notif.py` | CAP-076 | 07 | GitHub email-cron.yml, X-Cron-Key, SMTP | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/enterprise.py` | CAP-105 | 04 | — | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/evidence.py` | CAP-123 | 05 | predmet_dokazi (izvor istine) | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/evidence_graph.py` | CAP-124 | 13 | OpenAI, Pinecone | DA | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/export.py` | CAP-185, CAP-186 | 05 | _resolve_key; — | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/firm_memory.py` | CAP-132 | 03 | memory_entries | BEZ UI | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/gdpr.py` | CAP-161 | 05 | Storage | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/health_index.py` | CAP-095 | 05 | deterministički | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/hearing_cc.py` | CAP-116 | 13 | OpenAI | DA | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/import_klijenti.py` | CAP-033 | 13 | — | NE | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/inbox.py` | CAP-125 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/intake.py` | CAP-021 | 13 | — | DA | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/integracije.py` | CAP-162, CAP-187 | 13 | API ključevi, HMAC; http odlazni (SSRF) | DA | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/integrations.py` | CAP-163 | 13 | http odlazni (SSRF rizik) | BEZ UI | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/intelligence_timeline.py` | CAP-125 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/interni.py` | CAP-045 | 05 | Pinecone | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/jobs.py` | CAP-169 | 05 | shared/bg.py | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/kalendar.py` | CAP-075 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/kancelarija.py` | CAP-091 | 05 | migracija 067 | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/knowledge_base.py` | CAP-046 | 07 | Pinecone | DA | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/knowledge_graph.py` | CAP-124 | 13 | OpenAI, Pinecone | DA | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/knowledge_hygiene.py` | CAP-134 | 13 | — | BEZ UI | NE | odluka foundera + 0 poziva u prod. logovima + legacy ugašen |
| `routers/knowledge_transfer.py` | CAP-135 | 13 | — | BEZ UI | NE | odluka foundera + 0 poziva u prod. logovima + legacy ugašen |
| `routers/komentari.py` | CAP-093 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/law_upload.py` | CAP-048 | 05 | Pinecone | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/learning.py` | CAP-131 | 13 | case_patterns | DA | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/legal_reasoning.py` | CAP-127 | 04 | migracija 076 | BEZ UI | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/matter_intel.py` | CAP-121 | 07 | risk_engine | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/memory_graph.py` | CAP-133 | 13 | — | BEZ UI | NE | odluka foundera + 0 poziva u prod. logovima + legacy ugašen |
| `routers/morning_briefing.py` | CAP-081 | 07 | cron, SMTP, OpenAI | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/multi_agent.py` | CAP-140 | 05 | OpenAI, Pinecone, PermissionService multi_agent | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/notifications.py` | CAP-080 | 05 | sw.js | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/oblasti.py` | CAP-044 | 13 | — | BEZ UI | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/ofac_screening.py` | CAP-151 | 05 | blockchain API, OFAC lista | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/onboarding.py` | CAP-104 | 12 | — | BEZ UI | NE | odluka foundera + 0 poziva u prod. logovima + legacy ugašen |
| `routers/outcome_intel.py` | CAP-113 | 05 | zatvoreni predmeti sa ishodom (CAP-130) | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/plans.py` | CAP-106 | 05 | shared/permissions.py, rollout_flags (mig 128) | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/portal_monitoring.py` | CAP-082 | 04 | scraping portal.sud.rs, cron | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/portfolio.py` | CAP-090 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/praksa.py` | CAP-042, CAP-043 | 03/05 | Pinecone praksa | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/precedenti.py` | CAP-114 | 05 | — | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/predmeti_close.py` | CAP-130, CAP-188 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/product_intelligence.py` | CAP-164 | 05 | founder-only | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/profitabilnost.py` | CAP-099 | 07 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/proof.py` | CAP-164 | 05 | founder-only | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/push.py` | CAP-080 | 05 | sw.js | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/recurring.py` | CAP-101 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/region.py` | CAP-049 | 11 | OpenAI bez regionalnog korpusa | BEZ UI | NE | odluka foundera + 0 poziva u prod. logovima + legacy ugašen |
| `routers/rocista.py` | CAP-074 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/rok_odluka.py` | CAP-070 | 07 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/rokovi_lanac.py` | CAP-071 | 05 | deterministički | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/saradnja.py` | CAP-092 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/search.py` | CAP-160 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/sef.py` | CAP-102 | 04 | SEF API ključ, sef_podesavanja | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/sesije.py` | CAP-167 | 02 | Supabase auth | NE | NE | NIKAD (živ put) |
| `routers/smart_intake.py` | CAP-020 | 05 | shared/intake_worker.py, OCR, Storage, event_bus | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/sms.py` | CAP-077 | 04 | Twilio, sms-cron.yml (uspeva) | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/source_of_funds.py` | CAP-151 | 05 | blockchain API, OFAC lista | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/status_page.py` | CAP-166 | 04 | — | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/strategija.py` | CAP-110 | 05 | OpenAI, Pinecone, PRO plan | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/strategy_simulator.py` | CAP-115 | 03 | OpenAI | BEZ UI | NE | odluka foundera + 0 poziva u prod. logovima + legacy ugašen |
| `routers/style_checker.py` | CAP-066 | 03 | OpenAI | BEZ UI | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/support.py` | CAP-169 | 05 | shared/bg.py | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/tarife.py` | CAP-100 | 05 | SMTP | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/tos.py` | CAP-167 | 02 | Supabase auth | NE | NE | NIKAD (živ put) |
| `routers/ugovor_zastupanja.py` | CAP-067 | 13 | — | BEZ UI | NE | kanonski vlasnik pokriva sve rute i ima V2 pozivaoca |
| `routers/viber.py` | CAP-078 | 07 | Viber bot token, korisnik_viber_profil | BEZ UI | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/voice.py` | CAP-145 | 05 | OpenAI realtime | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/voice_realtime.py` | CAP-145 | 05 | OpenAI realtime | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/waitlist.py` | CAP-164, CAP-167 | 02/05 | Supabase auth; founder-only | NE | NE | NIKAD (živ put) |
| `routers/wallet_provenance.py` | CAP-151 | 05 | blockchain API, OFAC lista | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/web3.py` | CAP-150 | 05 | OpenAI, ZDI namespace | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/whatsapp_notif.py` | CAP-079 | 08 | Twilio WhatsApp Business odobrenje | BEZ UI | NE | odluka foundera + 0 poziva u prod. logovima + legacy ugašen |
| `routers/workflow.py` | CAP-144 | 05 | — | DA | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/workspace.py` | CAP-125 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/zadaci.py` | CAP-094 | 05 | — | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/zakon_monitoring.py` | CAP-047 | 03 | scraper, cron tajna, OpenAI | BEZ UI | NE | ne pre završetka talasa koji ga vraća u V2 |
| `routers/zastarelost.py` | CAP-072, CAP-073 | 05/13 | deterministički, javno | NE | NE | ne pre završetka talasa koji ga vraća u V2 |
| `uploaded_doc/extractor.py` | CAP-011 | 07 | tesseract binarni (Dockerfile), pytesseract, pymupdf | BEZ UI | NE | ne pre završetka talasa koji ga vraća u V2 |

## 4. Sažetak

| Mera | Broj |
|---|---|
| Backend fajlovi sa rutama u ovoj mapi | 114 |
| Moduli sa bar jednim V2 pozivaocem | 46 |
| Moduli koje zove samo legacy | 49 |
| Moduli bez ikakvog UI-ja | 19 |
| Bezbedno za uklanjanje **danas** | **0** |

**Prvi kandidati za uklanjanje kasnije** (tek posle uslova iz kolone „removal condition" i odluke foundera):
- `routers/strategy_simulator.py`, `decision_replay.py`, `region.py`, `onboarding.py`, `whatsapp_notif.py`;
- memorijski klaster (`memory_graph.py`, `knowledge_hygiene.py`, `knowledge_transfer.py`);
- duplikati prijema (`routers/intake.py` osim `bulk-import`, `klijenti/intake-wizard`);
- `routers/import_klijenti.py`, `routers/oblasti.py`, `routers/ugovor_zastupanja.py`.

Debug rute u `api.py` su već gejtovane (404) i ne diraju se u ovoj misiji.
