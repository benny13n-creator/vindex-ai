# MIGRATION FORENSICS — migracije 002–072

**Misija:** čisto forenzička. Nijedna migracija nije pokrenuta. Nijedan produkcijski fajl,
migracija ni test nije menjan. Sve sonde su READ-ONLY (`select ... limit(0)` za postojanje
šeme; ograničeni `select` samo nad redovima koje su same migracije trebalo da ubace).

**Baseline:** `e811433d`
**Datum:** 2026-08-13
**Obim:** 62 fajla — `002`–`026` (25) + `036`–`072` (37). Rupe 27–35 ne postoje (dato).

---

## 0. Metod i granice dokaza

| Sloj | Alat | Može da dokaže |
|---|---|---|
| Postojanje tabele | `supa.table(T).select(c).limit(0)` | tabela postoji / `PGRST205` = ne postoji |
| Postojanje kolone | `supa.table(T).select(col).limit(0)` | kolona postoji / `42703` = ne postoji |
| Izvršenje DML-a | ciljani `select` nad seed redovima | red postoji sa očekivanom vrednošću |
| anon dohvatljivost | REST GET sa javnim anon ključem (samo SELECT) | grant + RLS ishod za čitanje |

**Šta PostgREST NE MOŽE** → verdikt je `UNKNOWN`, nikad „ne postoji":
indeksi, trigeri, funkcije, RLS politike, CHECK/FK/UNIQUE constraint-i, grantovi,
enum tipovi, komentari, nullability (`DROP NOT NULL`), DEFAULT vrednosti, storage bucket-i.

**PUBLIC MIGRATION HISTORY = ABSENT** (dato). Zato je kolona `HISTORY` = `ABSENT` za
svih 62 migracije, i **prisustvo šeme nikad nije dokaz izvršenja migracije**.
Verdikt `MIGRATION VERIFIED APPLIED` dodeljen je isključivo tamo gde postoji
**dokaz izvršenja na nivou podataka** — red koji je migracija trebalo da upiše stvarno
postoji sa tačno očekivanim vrednostima, i nijedan drugi put u kodu ne piše tu vrednost.

**Legenda kolona**
`SCHEMA`: PRESENT / PARTIAL / ABSENT ·
`DATA`: N/A (nema DML) / VERIFIED / VACUOUS (0 redova, UPDATE bez efekta) / UNVERIFIABLE ·
`RERUN`: SAFE_TO_RERUN / CONDITIONALLY_SAFE / UNSAFE_TO_RERUN

---

## 1. Zbirni rezultat

| Verdikt | Broj | Migracije |
|---|---|---|
| `MIGRATION VERIFIED APPLIED` | **10** | 024, 059, 064, 065, 066, 068, 069, 070, 071, 072 |
| `SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE` | **51** | sve ostale |
| `MIGRATION VERIFIED NOT APPLIED` | **1** | **023** |
| `PARTIAL EXECUTION / SCHEMA DRIFT` | 0 | — |
| `UNKNOWN` | 0 | — |

| Rerun bezbednost | Broj |
|---|---|
| `SAFE_TO_RERUN` | 34 |
| `CONDITIONALLY_SAFE` | 5 |
| `UNSAFE_TO_RERUN` | 23 |

**Sve sondirano:** 130 tabela/view-ova, 187 kolona, 19 DML dokaznih upita, 25 anon-RLS
provera. Ukupno **7 dokazano nedostajućih objekata**, svi koncentrisani u jednoj migraciji
(023) plus jedan namerno obrisan kasnijom migracijom (075).

---

## 2. Matrica

| # | VERSION | FILE | PURPOSE | OBJECTS (sondirano) | HISTORY | SCHEMA | DATA | RERUN SAFETY | RISK | VERDICT |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 002 | `002_klijenti_crm.sql` | Klijenti CRM P1–P8, GDPR retention | 4 tab (`user_roles`,`klijenti_audit`,`klijent_dokumenti`,`klijent_komunikacija`) ✓, 1 view (`klijenti_retention_candidates`) ✓, 11 kol na `klijenti` ✓, 3 kol na `predmet_klijenti` ✓; 12 idx / 6 RLS pol / 2 trig / 1 fn / 6 grant / 2 comment = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P1 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 2 | 003 | `003_billing.sql` | Fakture, billing entries, tajmer | 3 tab ✓ (`fakture`,`billing_entries`,`timer_sessions`); 3 fn, 3 trig, 3 RLS pol, 8 idx = UNKNOWN | ABSENT | PRESENT | N/A | CONDITIONALLY_SAFE | P1 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 3 | 004 | `004_klijenti_fixes.sql` | maticni_broj, datum_nastanka, tip CHECK | `klijenti.maticni_broj` ✓, `.datum_nastanka` ✓, `.tip` ✓; CHECK `klijenti_tip_check` = UNKNOWN | ABSENT | PRESENT | N/A | CONDITIONALLY_SAFE | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 4 | 005 | `005_rocista.sql` | Ročišta | `rocista` ✓ (+`datum` ✓); 3 idx, 4 pol, grant = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 5 | 006 | `006_tarife.sql` | Satnica + AKS custom stavke | `tarife` ✓, `tarifne_stavke_custom` ✓; 2 uq idx, fn, 2 trig, 2 pol = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P1 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 6 | 007 | `007_ingest_jobs.sql` | Batch ingest job tracking | `ingest_jobs` ✓ (0 red.); CHECK, RLS pol = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 7 | 008 | `008_sef_recurring.sql` | SEF e-faktura + ponavljajuće | 4 tab ✓ (`sef_podesavanja`,`sef_log`,`recurring_templates`,`email_log`); 3 idx, 4 pol = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | **P1** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 8 | 009 | `009_notifications_analytics.sql` | Usage analytics + notifikacije | `usage_events` ✓, `notifications` ✓; 4 idx, 3 pol, 2 grant = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 9 | 010 | `010_client_portal.sql` | Klijentski portal tokeni | `client_portal_tokens` ✓; 3 idx, 2 pol, grant = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | **P0** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 10 | 011 | `011_saradnja.sql` | Multi-advokat saradnja | `predmet_saradnici` ✓; 3 idx, 4 pol, grant = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | **P0** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 11 | 012 | `012_sms_notifikacije.sql` | SMS/WhatsApp profil | `korisnik_sms_profil` ✓; 3 pol, fn, trig = UNKNOWN | ABSENT | PRESENT | N/A | **UNSAFE_TO_RERUN** | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 12 | 013 | `013_client_portal_uploads.sql` | Klijentski upload | `client_portal_uploads` ✓; 4 idx, 2 pol, storage bucket `portal-uploads` = UNKNOWN | ABSENT | PRESENT | N/A | **UNSAFE_TO_RERUN** | P1 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 13 | 014 | `014_security_fixes.sql` | RLS na `predmet_klijenti` | 3 kol ✓ (`uloga_klijenta`,`napomena`,`kreirano`); ENABLE RLS + `pk_owner_all` = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | **P0** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 14 | 015 | `015_predmeti_extra_fields.sql` | tuzilac/tuzeni/rizik/vrednost | 4 kol na `predmeti` ✓ | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P3 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 15 | 016 | `016_evidence_vault.sql` | Evidence Vault klasifikacija | 4 kol na `predmet_dokumenti` ✓, `predmet_dokazi` ✓; 3 idx, pol, 2 grant = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 16 | 017 | `017_scraper_state.sql` | Auto-scraper state | `discovered_bilteni` ✓ (0 red.); 2 idx, pol = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | **P1** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 17 | 018 | `018_kancelarija.sql` | Kancelarija + članovi | `kancelarije` ✓ (0 red.), `kancelarija_clanovi` ✓ (0 red.); 4 idx, pol, 2 grant = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P1 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 18 | 019 | `019_api_kljucevi.sql` | API ključevi za integracije | `api_kljucevi` ✓; 3 idx, pol, grant = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | **P0** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 19 | 020 | `020_law_docs.sql` | Praćenje ingestovanih PDF zakona | `law_docs` ✓ (0 red.); 2 idx, RLS bez politike, grant = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P3 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 20 | 021 | `021_email_notif.sql` | Email podsetnici za rokove | `korisnik_email_notif` ✓, `email_notif_log` ✓ (5 kol ✓); idx, pol, 3 grant = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 21 | 022 | `022_weekly_digest.sql` | Nedeljni digest opt-in | `korisnik_email_notif.nedeljni` ✓; `email_notif_log.predmet_id DROP NOT NULL` = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P3 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 22 | **023** | `023_stability_500_users.sql` | 5 indeksa za 500+ korisnika | 1/5 izvodljiv (`ai_cache.expires_at` ✓); **4/5 referišu objekte koji DOKAZANO ne postoje** | ABSENT | **ABSENT** | N/A | SAFE_TO_RERUN (ali će pući) | **P2** | **MIGRATION VERIFIED NOT APPLIED** |
| 23 | 024 | `024_plans_usage.sql` | Planovi + potrošnja + limiti | `korisnik_plan` ✓ (0), `korisnik_usage` ✓ (0), `plan_limits` ✓; **4/4 seed reda tačna** | ABSENT | PRESENT | **VERIFIED** | **UNSAFE_TO_RERUN** | **P1** | **MIGRATION VERIFIED APPLIED** |
| 24 | 025 | `025_onboarding_emails.sql` | Onboarding email sekvenca | `onboarding_email_log` ✓, `profiles.registered_at` ✓; uq idx, pol = UNKNOWN | ABSENT | PRESENT | N/A | **UNSAFE_TO_RERUN** | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 25 | 026 | `026_predmet_health_log.sql` | Istorija health score-a | `predmet_health_log` ✓; idx, 2 pol = UNKNOWN | ABSENT | PRESENT | N/A | **UNSAFE_TO_RERUN** | P3 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 26 | 036 | `036_decision_log.sql` | Decision Log + Proactive Alerts | `decision_log` ✓, `proactive_alerts` ✓; 5 idx, 2 pol = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 27 | 037 | `037_learning_loop.sql` | Outcome feedback engine | `outcome_log` ✓, `case_patterns` ✓, `recommendation_log` ✓; 5 idx, 3 pol = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 28 | 038 | `038_deep_learning.sql` | RCA, lekcije, counterfactual, Firm DNA | 2+3 kol ✓, `lessons_learned` ✓, `counterfactual_log` ✓, `firm_dna` ✓; 7 idx, 3 pol = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 29 | 039 | `039_epistemic_confidence.sql` | Epistemic confidence layer | 8 kol `lessons_learned` ✓, 3 kol `firm_dna` ✓, 2 kol `counterfactual_log` ✓, `impact_metrics` ✓; 3 idx, pol, DROP CONSTRAINT = UNKNOWN | ABSENT | PRESENT | N/A | CONDITIONALLY_SAFE | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 30 | 040 | `040_faza5_org_intelligence.sql` | Style checker + knowledge transfer | 6 tab ✓ (`style_profili`,`style_analize`,`knowledge_profiles`,`knowledge_upiti`,`knowledge_izvori`,`client_twin_profili`); 6 idx, 6 pol = UNKNOWN | ABSENT | PRESENT | N/A | **UNSAFE_TO_RERUN** | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 31 | 041 | `041_confidence_audit_hygiene.sql` | Confidence audit + hygiene | 4 kol `recommendation_log` ✓, `confidence_audit_log` ✓, 3 kol `lessons_learned` ✓, `knowledge_hygiene_log` ✓; 4 idx, 2 pol = UNKNOWN | ABSENT | PRESENT | N/A | **UNSAFE_TO_RERUN** | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 32 | 042 | `042_mesecna_upotreba_db.sql` | Mesečna potrošnja kredita u DB | `user_credits.mesecno_korisceno` ✓, `.mesec` ✓ (12 red.); idx, 2 comment = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | **P1** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 33 | 043 | `043_security_bulletproof.sql` | Hash-chain audit, AI forensics, sec events | `audit_immutable` ✓ (**15.760 red.**), `ai_forensics` ✓ (124), `security_events` ✓ (**2.760**), 3 kol `audit_log` ✓; fn `protect_audit_immutable`, trig, 2 pol, 7 idx = UNKNOWN | ABSENT | PRESENT | N/A | **UNSAFE_TO_RERUN** | **P0** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 34 | 044 | `044_anomaly_detection.sql` | Behavioral anomaly detection | `user_daily_activity` ✓, `chain_anchors` ✓; fn `protect_chain_anchors`+`get_activity_averages`, trig, 2 pol, idx, 3 grant = UNKNOWN | ABSENT | PRESENT | N/A | **UNSAFE_TO_RERUN** | P1 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 35 | 045 | `045_firm_intelligence.sql` | Firm Intelligence Layer | 6 kol `kancelarije` ✓, `ai_corrections` ✓, `firm_style_profile` ✓, `zakoni_monitoring` ✓ (0), `zadaci` ✓, view `case_profitability` ✓, `case_benchmarks` ✓ (0); 9 idx, 3 pol, 6 grant = UNKNOWN | ABSENT | PRESENT | **VACUOUS** (`kancelarije` 0 red. → `UPDATE pinecone_namespace` bez efekta) | **UNSAFE_TO_RERUN** | **P0** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 36 | 046 | `046_firm_memory.sql` | Firm Memory Engine | 2 kol `ai_corrections` ✓, `memory_entries` ✓ (0), `partner_profiles` ✓, `judge_patterns` ✓, `client_memory` ✓; 7 idx, 4 pol, 4 grant = UNKNOWN | ABSENT | PRESENT | N/A | **UNSAFE_TO_RERUN** | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 37 | 047 | `047_trust_graph_workflow.sql` | Trust score, memory graph, workflow | 6 kol `memory_entries` ✓, `memory_graph_edges` ✓, `workflow_templates` ✓, `workflow_instances` ✓, `workflow_steps` ✓; 9 idx, 4 pol, 4 grant = UNKNOWN | ABSENT | PRESENT | **VACUOUS** (`memory_entries` 0 red.) | **UNSAFE_TO_RERUN** | P1 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 38 | 048 | `048_reliability_hardening.sql` | Reliability & UX hardening | `apr_lookup_log` ✓, 3 kol `praceni_predmeti` ✓, 4 kol `portal_status_log` ✓, `korisnik_viber_profil` ✓ +3 kol ✓, 3 kol `korisnik_sms_profil` ✓, `notification_log` ✓, `cron_runs` ✓ (5 red.); 8 idx, 8 pol = UNKNOWN | ABSENT | PRESENT | N/A | **UNSAFE_TO_RERUN** | P1 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 39 | 049 | `049_health_observability.sql` | Health + admin dashboard | 2 kol `portal_status_log` ✓, `praceni_predmeti.consecutive_failures` ✓, `notification_log.message_text` ✓, `support_tickets` ✓ (1 red.) +2 kol ✓, `beta_users` ✓ (0); 3 idx, 3 pol = UNKNOWN | ABSENT | PRESENT | N/A | **UNSAFE_TO_RERUN** | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 40 | 050 | `050_cio_dnevni_izvestaj.sql` | CIO dnevni izveštaj (keš) | `cio_dnevni_izvestaj` ✓; idx, 3 pol = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 41 | 051 | `051_plans_usage_schema_fix.sql` | Novi resursi + plan CHECK | 8 kol `korisnik_usage` ✓; `korisnik_plan_plan_type_check` = UNKNOWN | ABSENT | PRESENT | N/A | CONDITIONALLY_SAFE | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 42 | 052 | `052_twin_simulacije.sql` | Digital Twin simulacije | `twin_simulacije` ✓; idx, 2 pol = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 43 | 053 | `053_orphaned_inline_schemas.sql` | 6 orphan tabela iz komentara u kodu | 6 tab ✓ (`onboarding_state`,`user_knowledge`,`simulator_partije`,`whatsapp_pretplate`,`whatsapp_send_log`,`discovery_queue`); 6 idx, 8 pol = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 44 | 054 | `054_predmet_delegiranja.sql` | Enterprise delegacija predmeta | `predmet_delegiranja` ✓; 2 idx, 2 pol, 3 FK = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P1 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 45 | 055 | `055_waitlist.sql` | Waitlist prijave | `waitlist` ✓ (**0 red.**); uq idx `lower(email)`, pol = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 46 | 056 | `056_tos_acceptances.sql` | ToS + AI consent (compliance) | `tos_acceptances` ✓ (**2 red.** — tabela je živa); idx, 2 pol, UNIQUE = UNKNOWN | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | **P1** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 47 | 057 | `057_active_orphaned_tables.sql` | 9 tabela koje aktivni endpointi zovu | 9/9 tab ✓ | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 48 | 058 | `058_briefing_saradnja_memory_webhooks.sql` | 7 dodatnih orphan tabela | **6/7 ✓**; `vindex_memory` **nedostaje — namerno obrisana migracijom 075** (`DROP TABLE`), potvrđeno i nepostojanjem `feature_registry` reda `vindex_memory` | ABSENT | PRESENT (6/7 + 1 supersedirana) | N/A | SAFE_TO_RERUN (**vratila bi obrisanu tabelu**) | **P1** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 49 | 059 | `059_workflow_solo_i_sistemski_predlosci.sql` | Solo advokati + 4 sistemska predloška | **4/4 sistemska predloška postoje sa tačnim `naziv`+`tip_predmeta`+`kancelarija_id IS NULL`**; `DROP NOT NULL`, 2 pol = UNKNOWN | ABSENT | PRESENT | **VERIFIED** | SAFE_TO_RERUN | P2 | **MIGRATION VERIFIED APPLIED** |
| 50 | 060 | `060_digitalna_imovina_activation.sql` | Add-on aktivacioni flag | `profiles.digitalna_imovina_aktivirano` ✓ (0 naloga `true`) | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 51 | 061 | `061_fix_missing_profiles_columns.sql` | 5 nedostajućih `profiles` kolona | 5/5 kol ✓ (`is_pro`,`full_name`,`plan`,`trial_kraj`,`onboarding_done`); fn `set_user_pro` = UNKNOWN | ABSENT | PRESENT | UNVERIFIABLE (konzistentno: 12 profila, 1 `onboarding_done=false`, 1 `is_pro=true`; 1/3 founder emaila postoji i jeste `is_pro`) | **UNSAFE_TO_RERUN** | **P1** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 52 | 062 | `062_digitalna_imovina_standalone.sql` | Standalone tarifni flag | `profiles.digitalna_imovina_standalone` ✓ (0 `true`) | ABSENT | PRESENT | N/A | SAFE_TO_RERUN | P2 | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 53 | 063 | `063_entitlement_system.sql` | Entitlement sistem (subscription_type) | 4 kol `profiles` ✓; 4 comment = UNKNOWN | ABSENT | PRESENT | UNVERIFIABLE (konzistentno: basic 11 / professional 1 / enterprise 0 = 12; `expires_set`=1 = `is_pro`=1; addons backfill VACUOUS — 0 naloga sa DA flagovima) | **UNSAFE_TO_RERUN** | **P1** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 54 | 064 | `064_feature_registry.sql` | Feature Registry + seed 69 funkcija | `feature_registry` ✓ (14 kol ✓), `feature_usage` ✓ (9 red.); **broj redova 70 se tačno rekonciliše: 69 (064) + 1 (066) + 1 (083) − 1 (075) = 70**; 7 uzorkovanih redova vrednosno identično migraciji | ABSENT | PRESENT | **VERIFIED** | **UNSAFE_TO_RERUN** | **P0** | **MIGRATION VERIFIED APPLIED** |
| 55 | 065 | `065_feature_registry_v2.sql` | Životni ciklus funkcije + audit + view | 6 kol ✓, `feature_registry_audit` ✓ (**2 red.**), `feature_dependencies` ✓ (0 — namerno), `feature_usage_log` ✓ (0), view `feature_analytics` ✓; **7/7 uzorkovanih UPDATE-a tačno, uključujući sva 3 `cooldown_seconds` (2/3/5)** | ABSENT | PRESENT | **VERIFIED** | **UNSAFE_TO_RERUN** | **P1** | **MIGRATION VERIFIED APPLIED** |
| 56 | 066 | `066_digital_twin_feature.sql` | Nedostajući `digital_twin` red | Red postoji sa tačno `naziv`/`krediti=3`/`priority=MEDIUM`/`estimated_cost_usd=0.054`/`ai_model=gpt-4o` | ABSENT | PRESENT | **VERIFIED** | SAFE_TO_RERUN | P2 | **MIGRATION VERIFIED APPLIED** |
| 57 | 067 | `067_seat_lifecycle.sql` | Seat lifecycle (5 stanja) | 3 kol `kancelarija_clanovi` ✓, `kancelarija_seat_audit` ✓ (0); CHECK, DEFAULT, idx, pol, 2 comment = UNKNOWN | ABSENT | PRESENT | **VACUOUS** (`kancelarija_clanovi` 0 red. → 3 backfill UPDATE-a bez efekta) | **UNSAFE_TO_RERUN** | **P1** | SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE |
| 58 | 068 | `068_tier_config.sql` | Tier config (cene, mesta) | `tier_config` ✓ (9 kol ✓), `tier_config_audit` ✓ (**2 red.**); **3/3 seed reda tačna** (29/278.40/1, 79/758.40/1, 249/2390.40/3 + 49) | ABSENT | PRESENT | **VERIFIED** | **UNSAFE_TO_RERUN** | **P1** | **MIGRATION VERIFIED APPLIED** |
| 59 | 069 | `069_feature_registry_credit_multiplier.sql` | `credit_multiplier` | Kolona ✓; **3/3 UPDATE-a tačna**: `strategija`=6, `digital_twin`=3, `strategy_simulator`=2 (kontrola `case_dna`=1) | ABSENT | PRESENT | **VERIFIED** | **UNSAFE_TO_RERUN** | **P1** | **MIGRATION VERIFIED APPLIED** |
| 60 | 070 | `070_feature_registry_feature_type.sql` | `feature_type` + `chargeable` | 2 kol ✓; **4/4 UPDATE-a potvrđena na nivou reda**: FOUNDATION=6 (tačno tih 6), ADDON=8, 4 placeholder-a `COMING_SOON`, `firm_memory`+`knowledge_hygiene` `krediti=0`+`chargeable=false` | ABSENT | PRESENT | **VERIFIED** | **UNSAFE_TO_RERUN** | **P1** | **MIGRATION VERIFIED APPLIED** |
| 61 | 071 | `071_business_groups.sql` | 7 poslovnih celina + FK | `business_groups` ✓ (**7 red.**, `display_order` 1..7 tačno), `business_groups_audit` ✓ (0), `feature_registry.business_group_id` ✓; **dodela se rekonciliše: 59 sa grupom (60 − `vindex_memory`) + 11 bez (6 FOUNDATION + 4 COMING_SOON + `copilot_ambient` iz 083)** | ABSENT | PRESENT | **VERIFIED** | **UNSAFE_TO_RERUN** | P2 | **MIGRATION VERIFIED APPLIED** |
| 62 | 072 | `072_business_groups_content.sql` | Prodajni sadržaj kartica | 3 kol ✓ (`tagline`,`value_statement`,`best_for`); **7/7 UPDATE-a vrednosno potvrđeno**, uključujući 3 preimenovanja (`Pravna analiza`, `Dokumenti i dokazi`, `Digitalna imovina i usklađenost`) i sve `best_for` nizove | ABSENT | PRESENT | **VERIFIED** | **UNSAFE_TO_RERUN** | P3 | **MIGRATION VERIFIED APPLIED** |

---

## 3. Jedina dokazano neprimenjena migracija — `023_stability_500_users.sql`

Verdikt **`MIGRATION VERIFIED NOT APPLIED`**. Migracija sadrži 5 `CREATE INDEX IF NOT EXISTS`
naredbi. **Četiri od pet referišu objekte koji dokazano ne postoje u bazi:**

| # | Naredba iz 023 | Sonda | Rezultat |
|---|---|---|---|
| 1 | `ai_cache (expires_at)` | `select expires_at` | ✓ **izvodljivo** |
| 2 | `email_notif_log (user_id, tip, created_at DESC)` | `select tip` / `select created_at` | ✗ **`42703` — `email_notif_log.tip` NE POSTOJI**; ✗ **`email_notif_log.created_at` NE POSTOJI** |
| 3 | `predmeti (user_id, status, created_at DESC) WHERE obrisan = false` | `select obrisan` | ✗ **`42703` — `predmeti.obrisan` NE POSTOJI** |
| 4 | `rokovi (user_id, datum) WHERE obrisan = false` | `select *` | ✗ **`PGRST205` — tabela `public.rokovi` NE POSTOJI** |
| 5 | `klijenti (user_id, created_at DESC) WHERE obrisan = false` | `select obrisan` | ✗ **`42703` — `klijenti.obrisan` NE POSTOJI** |

Dopunski dokaz (isključuje „kolona se drugačije zove"):

- `email_notif_log` stvarno ima: `id, user_id, predmet_id, datum_roka, dana_pre, poslato_at`
  (svih 5 potvrđeno `select`-om) — dakle 023 je pisana prema šemi koja se nikad nije poklopila
  sa onom koju je 021 stvarno kreirala.
- `predmeti` nema **nijednu** soft-delete kolonu: `obrisan`, `deleted_at`, `arhiviran`,
  `aktivan`, `obrisano`, `is_deleted` — sve `42703`. (`predmeti.status` postoji.)
- `klijenti` ima `deleted_at` (iz 002), **ne** `obrisan`.

**Posledica (P2, funkcionalnost/performanse):** pet indeksa namenjenih upravo hot-path
upitima na 500+ korisnika (dashboard po `user_id+status`, kalendar rokova, weekly digest,
AI cache eviction) ne postoji u bazi.

**Kolateralni nalaz (P2, van same migracije):** tabela `public.rokovi` ne postoji, a
**13 poziva u 9 fajlova** je gađa preko istog PostgREST klijenta:
`api.py`, `routers/case_commander.py`, `routers/dashboard.py`, `routers/decision_replay.py`,
`routers/integrations.py`, `routers/morning_briefing.py`, `routers/whatsapp_notif.py`,
`routers/zadaci.py`, `routers/zastarelost.py`. Svaki takav poziv vraća `PGRST205`.
Nijedna migracija u celom `migrations/` direktorijumu ne kreira `rokovi`.

**Rerun:** `SAFE_TO_RERUN` u smislu da nema nijedne destruktivne naredbe — ali će pući na
naredbi #2 i, u transakcionom Supabase SQL Editor-u, ne primeniti ni indeks #1.

---

## 4. P0 stavke (bezbednost / cross-tenant / auth)

### P0-1 — `064` rerun vraća P0 rupu koju je `110` zatvorio (`feature_usage` kvota upisiva od strane korisnika)
`064_feature_registry.sql` kreira:
```
CREATE POLICY "feature_usage_self" ON public.feature_usage FOR ALL USING (user_id::text = auth.uid()::text);
```
`110_rls_lockdown_idempotent.sql` (B-01, označen P0) je **tačno tu politiku obrisao** i
zamenio je `feature_usage_self_read` (samo SELECT) + `REVOKE INSERT, UPDATE, DELETE ... FROM
authenticated, anon`, jer je omogućavala da autentifikovani korisnik obriše sopstvene
`feature_usage` redove i **resetuje sopstvenu kvotu / brojač naplate**.
Ponovno pokretanje 064 rekreira `feature_usage_self`. U transakcionom SQL Editor-u skripta
bi prethodno pukla na duplikatu `feature_registry_service_role` (42710) i rollback-ovala se —
ali izvršena naredbu-po-naredbu, ili posle ručnog čišćenja duplikata, **P0 rupa se vraća**.
`feature_usage` trenutno ima 9 redova.

### P0-2 — `045` kreira dve tabele bez ijednog `ENABLE ROW LEVEL SECURITY`
`case_benchmarks` i `zakoni_monitoring` su u `045_firm_intelligence.sql` kreirane samo sa
`GRANT`-ovima — bez `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` i bez ijedne politike.
`110` je ovo nezavisno identifikovao kao B-02 („jedine dve tabele u šemi koje se kreiraju a
nikad ne dobiju RLS... i čitljive i zagadive od strane neautentifikovanog posetioca sa
isporučenim anon ključem"). `case_benchmarks` po dizajnu drži `ishod`/`vrednost_rsd`/
`naplaceno_rsd` iz svih opt-in kancelarija.
**Status ispravke = UNKNOWN**: obe tabele su trenutno prazne (0 redova), pa anon sonda vraća
`200` sa 0 redova bez obzira da li je RLS uključen. Sonda pisanja je zabranjena mandatom.

### P0-3 — `017` politika bez `TO` klauzule; `110` je preskočio ispravku jer tabela „ne postoji"
`017_scraper_state.sql`:
```
CREATE POLICY "service_role_discovered_bilteni" ON discovered_bilteni USING (true) WITH CHECK (true);
```
Nema `TO service_role` → politika važi za `PUBLIC`, sa `USING(true)` **i** `WITH CHECK(true)`.
`110` ima petlju koja upravo ovo ispravlja i eksplicitno navodi `discovered_bilteni`, ali uz
komentar: *„skipped automatically where it does not exist — which is the case in this database
today."* **Sonda pokazuje da tabela `discovered_bilteni` DANAS POSTOJI.** Dakle ispravka za
nju nije primenjena. anon `GET` vraća `200` (grant postoji), tabela je prazna (0 redova) pa
je čitanje bez efekta danas, ali politika je otvorena i za upis.
*Sekundarna implikacija:* isti nesklad baca sumnju na to da li je `110` uopšte primenjen na
ovu bazu — što je van obima ove misije, ali je direktna posledica ovog nalaza.

### P0-4 — `043` rerun može ostaviti audit log bez zaštite od izmene
`043_security_bulletproof.sql` sadrži `DROP TRIGGER IF EXISTS trg_protect_audit_immutable` pa
`CREATE TRIGGER`, i dve **neograđene** `CREATE POLICY` (`audit_immutable_admin_read`,
`ai_forensics_owner_read`) koje bi u reranu pukle sa `42710`. Ako se skripta izvrši
naredbu-po-naredbu (autocommit), prekid posle `DROP TRIGGER` ostavlja `audit_immutable`
(**15.760 redova**) bez trigera koji brani `UPDATE`/`DELETE`. Postojanje trigera danas =
`UNKNOWN` (PostgREST ga ne vidi).

### P0-5 — tabele sa cross-tenant značajem čije je RLS stanje `UNKNOWN`
`010` `client_portal_tokens` (token_hash pristupa predmetu), `011` `predmet_saradnici`
(deljenje predmeta između advokata), `014` `predmet_klijenti` (sama migracija postoji zato
što je to bila jedina tabela bez RLS), `019` `api_kljucevi`. Kolone su potvrđene, **politike
nisu proverljive PostgREST-om**. Za `019` dodatno: `kljuc TEXT NOT NULL UNIQUE` čuva API
ključ u plaintextu, ne hash.

---

## 5. P1 stavke (GDPR / audit / provenance / naplata)

| ID | Migracija | Nalaz |
|---|---|---|
| P1-1 | **061** | `UPDATE public.profiles SET onboarding_done = TRUE;` — **jedini `UPDATE` bez `WHERE` u celom opsegu**. Rerun bi svakom korisniku (uključujući 1 nalog koji je danas `false`) označio onboarding kao završen. Uz to re-dodeljuje `is_pro=TRUE` za 3 hardkodovana emaila. |
| P1-2 | **063** | `UPDATE profiles SET subscription_type='professional', subscription_expires_at = now() + interval '30 days' WHERE is_pro = true` — svaki rerun **ponovo dodeljuje i produžava 30-dnevni Legacy Professional entitlement** svakom `is_pro` nalogu. Direktan uticaj na naplatu. |
| P1-3 | **065** | 68 slepih `UPDATE ... WHERE feature_key=` nad `feature_registry` (priority, estimated_cost_usd, cooldown_seconds). `feature_registry_audit` **već ima 2 reda** → Admin Feature Console je korišćen. Rerun bi prebrisao stvarne founder-ove izmene monetizacije na migracione default-e. |
| P1-4 | **069** | 3 `UPDATE`-a nad `credit_multiplier` (6/3/2). To je **direktan faktor naplate kredita**; rerun vraća migracione vrednosti preko konzolnih izmena. |
| P1-5 | **070** | 4 `UPDATE`-a nad `feature_type`/`status`/`krediti`/`chargeable`. Rerun bi vratio `COMING_SOON` i `chargeable=false` bez obzira na kasnije odluke. |
| P1-6 | **024** | `INSERT INTO plan_limits ... ON CONFLICT (plan_type) DO UPDATE SET ...` — rerun **prebrisuje** limite plana na seed vrednosti. Uz to 3 neograđene `CREATE POLICY`. |
| P1-7 | **068** | `tier_config_audit` ima **2 reda** → cene su menjane kroz konzolu. `INSERT` je `ON CONFLICT DO NOTHING` (cene bezbedne), ali 3 neograđene `CREATE POLICY` obaraju rerun. |
| P1-8 | **042** | `user_credits.mesecno_korisceno`/`mesec` (12 redova) — jezgro brojanja kredita; indeks i komentari `UNKNOWN`. |
| P1-9 | **008** | `sef_podesavanja.api_key TEXT NOT NULL` — SEF API ključ u plaintextu; migracija sama piše „AES-256 enkripcija preporučena", ali ništa je ne sprovodi. |
| P1-10 | **058** | `integracije.access_token` / `.refresh_token` kao običan `text` — Google Calendar OAuth tokeni bez enkripcije. Isti obrazac kao P1-9. |
| P1-11 | **058** | Rerun bi **ponovo kreirao `public.vindex_memory`**, poništavajući uklanjanje mrtvog koda iz migracije 075 (koje je potvrđeno: tabele nema i `feature_registry` red `vindex_memory` ne postoji). |
| P1-12 | **056** | `tos_acceptances` postoji i ima 2 reda, ali je ukupno **12 profila** — ToS/AI-consent je zabeležen za 2 od 12 naloga. RLS/UNIQUE `UNKNOWN`. GDPR/compliance trag. |
| P1-13 | **067** | Seat lifecycle backfill je **VACUOUS** — `kancelarija_clanovi` i `kancelarije` imaju 0 redova. CHECK constraint (`ACTIVE/INVITED/PENDING/SUSPENDED/REMOVED`) i `DEFAULT 'INVITED'` su `UNKNOWN`; nijedan enterprise seat put nije dokazan. |
| P1-14 | **047** | `wi_firma_read` i `ws_firma_read` su **zamenjene migracijom 059** (podrška solo advokatima). Rerun 047 bi ih vratio na firma-only verziju i ponovo prekinuo vidljivost workflow-a za solo advokate. |
| P1-15 | **013** | Storage bucket `portal-uploads` se pominje samo kao ručna instrukcija u komentaru — **nijedna migracija ga ne kreira niti mu postavlja politike**. Stanje `UNKNOWN`; klijentski upload-i idu tamo. |

---

## 6. Zapažanja iz podataka (nisu nalazi, ali su relevantna)

- **Prazne tabele koje bi trebalo da su žive:** `kancelarije` (0), `kancelarija_clanovi` (0),
  `memory_entries` (0), `waitlist` (0), `korisnik_plan` (0), `korisnik_usage` (0),
  `feature_usage_log` (0), `law_docs` (0), `beta_users` (0), `zakoni_monitoring` (0),
  `case_benchmarks` (0), `discovered_bilteni` (0), `ingest_jobs` (0).
  Zbog njih su backfill UPDATE-i u 045, 047 i 067 vakuumski — nemaju šta da promene.
- **Žive tabele:** `audit_immutable` 15.760, `security_events` 2.760, `ai_forensics` 124,
  `predmeti` 19, `profiles` 12, `user_credits` 12, `feature_usage` 9, `cron_runs` 5,
  `klijenti` 5, `tos_acceptances` 2, `feature_registry_audit` 2, `tier_config_audit` 2,
  `support_tickets` 1.
- **anon (javni ključ) SELECT provera, 25 tabela:** sve vraćaju `200/206` (grant postoji),
  ali **RLS odseca redove** svuda gde podaci postoje — `klijenti` 5→0, `predmeti` 19→0,
  `profiles` 12→0, `audit_immutable` 15.760→0, `security_events` 2.760→0, `user_credits` 12→0.
  Dva izuzetka su namerna: `plan_limits` (4 reda, politika `USING (true)` iz 024) i
  **`workflow_templates` (4 reda)** — `wt_firma_read` iz 047 ima granu `kancelarija_id IS NULL`,
  pa neautentifikovani posetilac čita 4 sistemska predloška iz 059. Niska osetljivost (**P3**).
- **`copilot_ambient`** (dodat migracijom 083, van obima) ima `status=ACTIVE`,
  `feature_type=SUBSCRIPTION`, `minimum_plan=professional`, ali `business_group_id = NULL` →
  prodaje se u Professional tarifi a **ne može da se pojavi u Pricing Matrix-u** koji se
  izvodi spajanjem sa `business_groups`. (**P3**, vlasnik je 083, ne 071.)

---

## 7. Rerun bezbednost — sažetak obrazaca

**`UNSAFE_TO_RERUN` (23):** 012, 013, 024, 025, 026, 040, 041, 043, 044, 045, 046, 047, 048,
049, 061, 063, 064, 065, 067, 068, 069, 070, 071, 072
*(dominantan uzrok: `CREATE POLICY` bez prethodnog `DROP POLICY IF EXISTS` i bez
`pg_policies` guard-a → `42710 duplicate_object`; drugi uzrok: slepi `UPDATE` koji prebrisuje
admin-konfigurisane podatke)*

**`CONDITIONALLY_SAFE` (5):** 003 (`CREATE OR REPLACE FUNCTION get_next_broj_fakture` vraća
telo RPC-a koji je 104 dokumentovao kao izvor trke; ACL iz 102 preživljava jer
`CREATE OR REPLACE` čuva privilegije), 004 (`DROP CONSTRAINT` po `LIKE '%tip%'` — preširok
uzorak nad `klijenti`), 039 (`DROP CONSTRAINT firm_dna_user_id_pattern_key`), 051
(`DROP`+`ADD CONSTRAINT korisnik_plan_plan_type_check`), 067 (`DROP`+`ADD CONSTRAINT` +
neograđena politika).

**`SAFE_TO_RERUN` (34):** sve ostale — dosledno `IF NOT EXISTS` / `DROP ... IF EXISTS` /
`ON CONFLICT` / `WHERE NOT EXISTS` / `pg_policies` guard.

**Nema u celom opsegu:** `CREATE TABLE` bez `IF NOT EXISTS` · `CREATE INDEX` bez
`IF NOT EXISTS` · `DROP TABLE` · `DELETE` · izmena enum tipa · `REVOKE` ·
kreiranje storage bucket-a.
Sva 4 `ADD COLUMN` bez `IF NOT EXISTS` (002, 043) su unutar `DO $$` blokova koji prethodno
proveravaju `information_schema.columns` — nisu hazard.

---

## 8. Šta ostaje nedokazivo bez SQL pristupa

Za sve migracije u opsegu sledeći artefakti su `UNKNOWN` i **ne smeju se izveštavati kao
prisutni ni kao odsutni**: ~200 indeksa, ~150 RLS politika, 12 trigera, 11 funkcija,
svi CHECK/FK/UNIQUE constraint-i, svi `GRANT`-ovi, svi `COMMENT`-i, sve `DEFAULT` vrednosti,
sve `NOT NULL` promene (022, 059), i storage bucket `portal-uploads` (013).

Za njihovo razrešenje potreban je direktan SQL pristup (`SUPABASE_DB_URL`, koji je i dalje
neisporučen) i read-only upiti nad `pg_indexes`, `pg_policies`, `pg_trigger`, `pg_proc`,
`pg_constraint`, `information_schema.role_table_grants`, `storage.buckets`.
