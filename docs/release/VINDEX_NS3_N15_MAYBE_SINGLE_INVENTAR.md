# VINDEX — NS3-N15 inventar: `maybe_single().execute()` → `.data` bez provere `None`

Biblioteka: supabase/postgrest **2.28.3** (requirements) — `SyncMaybeSingleRequestBuilder.execute` za 0 redova **vraća `None`** (pročitan izvor instalirane biblioteke). Čitanje `.data` tada diže `AttributeError` → HTTP 500.

Metod: AST skener (`scratchpad/ns3/ms_scan.py`, nije u repou) nad `routers/`, `shared/`, `services/`, `api.py`: svaka dodela izraza sa `maybe_single()` i PRVO čitanje `<var>.data` posle nje. „Zaštićeno“ = provera same promenljive (`is None`, `if not var:`, `var and`, `(var or`, `x.data if var else`). „U try“ = čitanje unutar `try` sa `except Exception/AttributeError`. Heuristika — svako mesto ispod je KANDIDAT, ne dokazan defekt, osim pet izvršenih.

| | baza `469085b6` | posle NS3-N15 |
|---|---|---|
| dodela + čitanje | 184 | 184 |
| bez zaštite | 132 | 124 |
| bez zaštite i van `try` | 68 | 60 |


## Ispravljeno (RED → GREEN kroz stvarni handler, `tests/test_ns3_n15_maybe_single_nema_reda.py`)

| Mesto | Klasa | Pre | Posle |
|---|---|---|---|
| `routers/case_dna.py:1291` `get_case_dna` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) | 500 | prazno stanje / 404 |
| `routers/copilot_ambient.py:53` `_proveri_vlasnistvo_predmeta` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) | 500 | prazno stanje / 404 |
| `routers/gdpr.py:166` `gdpr_export` | opcioni red — prazno stanje je u kodu, stvarno 500 | 500 | prazno stanje / 404 |
| `routers/gdpr.py:166` `_fetch` | opcioni red — prazno stanje je u kodu, stvarno 500 | 500 | prazno stanje / 404 |
| `routers/gdpr.py:188` `gdpr_export` | opcioni red — prazno stanje je u kodu, stvarno 500 | 500 | prazno stanje / 404 |
| `routers/gdpr.py:188` `_fetch` | opcioni red — prazno stanje je u kodu, stvarno 500 | 500 | prazno stanje / 404 |
| `routers/rokovi_lanac.py:430` `post_rokovi_lanac` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) | 500 | prazno stanje / 404 |
| `routers/whatsapp_notif.py:506` `get_pretplata` | opcioni red — prazno stanje je u kodu, stvarno 500 | 500 | prazno stanje / 404 |

## Preostali kandidati — NIJE menjano (bez izvršenog dokaza; klasa je automatska procena)

| Mesto | Funkcija | Kod | Procena |
|---|---|---|---|
| `api.py:3118` | `portal_predmet_data` | `if not tok_r.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `api.py:5226` | `update_predmet` | `if not exists.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `api.py:5301` | `update_kanban_faza` | `if not exists.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `api.py:7212` | `predmet_dokument_obrisi` | `if not row.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `api.py:7498` | `predmet_workspace` | `if not pred.data or _je_u_brisanju(pred.data):` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/agent_notifications.py:82` | `_resolve` | `if not existing.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/batch_ingest.py:267` | `get_ingest_job` | `if not result.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/billing.py:264` | `billing_entry_create` | `if not pred_check.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/billing.py:284` | `billing_entry_create` | `if custom_r.data:` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/billing.py:331` | `billing_entry_update` | `if not ex.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/billing.py:373` | `billing_entry_delete` | `if not ex.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/billing.py:434` | `timer_start` | `if not pred_check.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/billing.py:775` | `konvertuj_proformu` | `if not f_r.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/billing.py:805` | `faktura_pdf` | `if not f_r.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/billing.py:858` | `posalji_fakturu_email` | `if not f_r.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/billing.py:868` | `posalji_fakturu_email` | `to_email = (kl_r.data or {}).get("email", "")` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/case_commander.py:974` | `commander_jutarnji` | `k   = (korisnik_r.data if not isinstance(korisnik_r, Exception) else None) or {}` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/case_dna.py:1349` | `_refresh_case_dna_body` | `if not pred_check.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/case_dna.py:1587` | `get_genome_history` | `if not pr.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/case_intelligence.py:118` | `_gather_case_data` | `predmet = predmet_row.data or {}` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/client_portal.py:815` | `client_portal_obrisi_upload` | `if not meta_r.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/copilot.py:1225` | `_handle_akcija_rok` | `if not pred_ok.data:` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/copilot.py:1313` | `_handle_akcija_beleska` | `if not pred_ok.data:` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/copilot.py:1374` | `_handle_akcija_povezi_klijenta` | `if not pred_ok.data:` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/copilot.py:1470` | `_handle_predlozi` | `if not pred_r.data:` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/copilot.py:1696` | `_handle_naplati_radnju` | `if pred_ok.data:` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/corrections.py:278` | `capture_correction` | `if not pred_ok.data:` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/doc_templates.py:227` | `sacuvaj_dokument` | `if not pred.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/drafting.py:1375` | `staging_approve` | `if not row_res.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/drafting.py:1415` | `staging_approve` | `cur = current.data or {}` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/drafting.py:1460` | `staging_reject` | `if not row_res.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/enterprise.py:64` | `_get_firma_id` | `if admin_r.data:` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/enterprise.py:75` | `_get_firma_id` | `if not member_r.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/enterprise.py:237` | `delegiraj_predmet` | `if not pred_r.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/export.py:179` | `get_predmet_pdf_export` | `if not predmet_res.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/integracije.py:493` | `webhook_test` | `if not r.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/integrations.py:220` | `test_webhook` | `if not r.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/integrations.py:391` | `gcal_sync_rokovi` | `if not tok_r.data or not tok_r.data.get("access_token"):` | NEPOZNATO bez specifikacije |
| `routers/kancelarija.py:173` | `moja_kancelarija` | `if pending.data:` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/kancelarija.py:173` | `_fetch` | `if pending.data:` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/kancelarija.py:584` | `promeni_ulogu` | `if not row.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/kancelarija.py:584` | `_change_role` | `if not row.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/komentari.py:61` | `post_komentar` | `if not own.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/komentari.py:95` | `get_komentari` | `if not own.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/law_upload.py:285` | `obrisi_zakon` | `if not res.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/predmeti_close.py:95` | `zatvori_predmet` | `if not pred_res.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/predmeti_close.py:275` | `get_predmet_ishod` | `if not pred_res.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/recurring.py:216` | `get_recurring` | `if not res.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/recurring.py:242` | `patch_recurring` | `if not chk.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/recurring.py:290` | `delete_recurring` | `if not chk.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/recurring.py:341` | `generisi_iz_sablona` | `if not tpl_res.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/rocista.py:313` | `izmeni_rociste` | `if not exists.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/sef.py:547` | `get_sef_status` | `if not log_r.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/ugovor_zastupanja.py:333` | `post_generiši_ugovor` | `if not pred_res.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/whatsapp_notif.py:290` | `posalji_rok` | `pretplata = pretplata_r.data` | NEPOZNATO bez specifikacije |
| `routers/whatsapp_notif.py:326` | `posalji_rok` | `if predmet_r.data:` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `routers/workflow.py:207` | `pokreni_workflow` | `if not pred_r.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `routers/workflow.py:227` | `pokreni_workflow` | `if not tmpl_r.data:` | vlasništvo/obavezan red — namera 403/404, stvarno 500 (fail-closed, pogrešan kod) |
| `shared/seats.py:82` | `get_seat_summary` | `return prof_r.data or {}, clan_r.data or []` | opcioni red — prazno stanje je u kodu, stvarno 500 |
| `shared/seats.py:82` | `_fetch` | `return prof_r.data or {}, clan_r.data or []` | opcioni red — prazno stanje je u kodu, stvarno 500 |

**Zabranjeno i nije urađeno:** masovna zamena `.single()` ↔ `.maybe_single()`. Red vlasništva koji ne postoji MORA ostati odbijanje — ispravka menja samo 500 u nameravani 404, nikad u dozvolu.

