# VINDEX AI — MAPA STVARNIH SPOSOBNOSTI (za sajt)

**Faza A — DISCOVERY. Inventar, ne predlog izmena.**

- Datum: 2026-08-11
- Commit: `108dc48b`
- Metod: `api.py` (registruje 115 rutera) → 579 ruta → provera pozivaoca u `static/vindex.js` (23.647 linija) i `index.html` → provera testa u `tests/` (352 fajla, 3.896 test funkcija)
- Pravilo: **sposobnost postoji samo ako je nađena u kodu.** Dokumentacija u `docs/` korišćena je isključivo kao mapa gde da se gleda, nikad kao dokaz.

## Kako čitati status

| Status | Značenje | Sme na sajt? |
|---|---|---|
| `PRODUCTION` | Ruta postoji, registrovana je u `api.py`, i postoji konkretan poziv iz frontenda (navedena linija). | **DA** |
| `IMPLEMENTED_UNWIRED` | Backend kod postoji i često je testiran, ali **nijedan pozivalac** — ni frontend ni drugi backend modul. | **NE** |
| `EXPERIMENTAL` | Iza founder-only provere, admin tokena ili cron zaštite. Korisnik ne može da pokrene. | **NE** |
| `DEAD` | Nije registrovano, nedostižno, ili deklarisano bez ijednog izvršioca. | **NE** |

**Zašto je ova razlika najvažnija stvar u dokumentu:** u ovom repou je više puta potvrđeno da postoji potpuno napisan, testiran modul koji nijedna linija koda ne poziva. Kanonski primer je `shared/ai_fabric.py` — ima nula produkcionih pozivalaca, i `tests/test_ai_fabric_governance.py` to izričito tvrdi kao ugovor (test pada ako se to promeni). Provereno pokretanjem: 17 prošlo.

## Ekrani kojima korisnik stvarno pristupa

Iz `index.html` (glavna navigacija, `setTab`): Pregled dana · Predmeti · Klijenti · Rokovi · Znanje i AI · Sudska praksa · Dokumenti · Šabloni dokumenata · Zadatci · Finansije · Kancelarija · Portfolio kancelarije (nav dugme ima `style="display:none"`) · Podešavanja.

Ako sposobnost nema ulaz ni iz jedne od ovih kartica — ne ide na sajt.

---

## 1. RAD SA DOKUMENTIMA

| Sposobnost | Gde (fajl:linija / ruta) | Test | Status | Šta radi (jezikom advokata) |
|---|---|---|---|---|
| Unos više dokumenata odjednom | `routers/smart_intake.py:108` → `POST /api/smart-intake/documents`; FE `vindex.js:21539`, dugme `index.html:593`, `multiple` input `index.html:2331` | `test_omega_sprint001_batch_intake.py::test_upload_batch_within_time_budget_processes_everything_normally` | `PRODUCTION` | Advokat prevuče ceo folder; svaki fajl dobija svoj broj posla i obrađuje se u pozadini. |
| Zaštita od prekida kod velikih paketa | `routers/smart_intake.py:71` (`_UPLOAD_TIME_BUDGET_S = 90.0`), prekid na `:122` | `test_omega_sprint001_batch_intake.py::test_upload_batch_stops_early_when_time_budget_exceeded_and_reports_remaining` | `PRODUCTION` | Kod paketa od nekoliko stotina fajlova vraća „obrađeno N od M" umesto da veza pukne bez traga. |
| Prepoznavanje teksta (OCR) skeniranih PDF-ova | `uploaded_doc/extractor.py:104` `_ocr_image` (pytesseract + PyMuPDF + Pillow), poziv iz `extract_pdf` `:220-259`, auto-detekcija jezika `:159` | `test_extractor_ocr.py::test_ocr_success_returns_text_not_scanned`, `::test_normal_pdf_skips_ocr` | `PRODUCTION` | Kad PDF nema tekstualni sloj, sistem sam „pročita" sliku stranice. |
| OCR se okida automatski na svakom uploadu | Tri putanje zovu isti `extract()`: `routers/dokument.py:259`, `api.py:4820`, `shared/intake_worker.py:511` | `test_uploaded_doc_api.py::test_upload_rejects_scanned_pdf`; `test_intake_worker_phase1a.py::test_process_ocr_failed_routes_to_review_fail_soft_not_exception` | `PRODUCTION` | Nema posebnog dugmeta „pokreni OCR" — radi samo. |
| OCR fotografija (JPG/PNG) | `uploaded_doc/extractor.py:400` `extract_image`; dozvoljeno `routers/smart_intake.py:88`, `index.html:2331` | `test_extractor_image.py::test_extract_image_jpeg_success`; `test_lawyerday_predmet_upload_images.py` | `PRODUCTION` (samo kroz Smart Intake) | Dokument slikan telefonom može da se otpremi. |
| Uputstvo umesto greške kad OCR ne uspe | `routers/dokument.py:266-276` (HTTP 422 sa 3 preporuke); `extractor.py:11` upisuje u `security_events`; FE `vindex.js:20038` | `test_uploaded_doc_api.py::test_upload_rejects_scanned_pdf` | `PRODUCTION` | Advokat dobija konkretno uputstvo (300 DPI, digitalni PDF, nalepi tekst). |
| Prepoznavanje tipa podneska (13 tipova) | `shared/intake_classify.py:56` heuristika → `:82` `classify_llm` (gpt-4o-mini `:98`); labele `vindex.js:21363-21367` | `test_intake_classify.py::test_classify_heuristic_recognizes_cyrillic_lawsuit`, `::test_classify_llm_rejects_unknown_type` | `PRODUCTION` | Prepoznaje da li je tužba, presuda, žalba, ugovor, punomoćje — i sa kolikom sigurnošću. |
| Klasifikacija dokaza (9 tipova) u Evidence Vault | `routers/evidence.py:216` `klasifikuj_i_sacuvaj` (gpt-4o-mini `:69`); okida se događajem `NEW_EVIDENCE_REGISTERED` iz `api.py:5044` i `smart_intake.py:1543`; FE `vindex.js:18708` | `test_lz002_evidence_autoclassify.py::test_finalize_triggers_evidence_classification_in_background` | `PRODUCTION` | Svaki dokument dobija tip dokaza, pravne elemente, stranke, datume, iznose i ključne činjenice. |
| Ručna reklasifikacija pogrešnog rezultata | `routers/evidence.py:446` → `POST /api/evidence/predmeti/{id}/reklasifikuj/{dok_id}`; FE `vindex.js:18788` | `test_evidence_klasifikacija.py::test_never_raises_even_if_both_fail` | `PRODUCTION` | Advokat kaže „pogrešno si prepoznao"; kredit se ne naplaćuje ako AI padne (`evidence.py:487-490`). |
| Izvlačenje podataka iz dokumenta (8 tipova entiteta) | `shared/intake_extract.py:85-113` (regex) + `:192` (gpt-4o-mini `:211`); FE `vindex.js:21369-21372` | `test_intake_extract.py::test_extract_all_entities_returns_all_eight_types`, `::test_extract_deadline_prefers_legally_significant_date_over_first_mentioned` | `PRODUCTION` | Izvlači broj predmeta, sud, sudiju, stranke, rok, iznos i zakon — svako polje sa svojom pouzdanošću. |
| Razdvajanje više dokumenata iz jednog skena | `shared/intake_segment.py::segment_document`, poziv `shared/intake_worker.py:343` | `test_intake_segment.py::test_large_pdf_500_pages_with_20_bundled_documents_all_pages_accounted_for` | `PRODUCTION` | Skenirani „svežanj" od 500 strana sam se deli na pojedinačne dokumente. |
| Vezivanje dokumenta za predmet (direktno) | `api.py:4715` → `POST /api/predmeti/{id}/upload`, provera vlasništva `:4746`; FE `vindex.js:20031` | `test_lawyerday_predmet_upload_images.py::test_pdf_upload_unaffected_by_the_image_allowlist_widening` | `PRODUCTION` | Iz otvorenog predmeta fajl odmah postaje deo spisa i pokreće procenu. |
| Vezivanje kroz Smart Intake finalizaciju | `routers/smart_intake.py:765` → `POST /api/smart-intake/jobs/{job_id}/finalize`; FE `vindex.js:21830`, `21805` | `test_lz002_evidence_autoclassify.py::test_finalize_triggers_evidence_classification_in_background` | `PRODUCTION` | Prvi fajl kreira predmet, ostali se kače za isti. |
| Prepoznavanje kom postojećem predmetu dokument pripada | `shared/case_assimilation.py:121` `resolve_case_ownership`, `:166` `resolve_client_ownership`, `:236` `find_conflicting_case_numbers`; FE `vindex.js:21838` | `test_sprint007_bulletproof_intake.py`, `test_intake_e2e_restart.py` | `PRODUCTION` | Po broju predmeta i imenu stranke pogodi da li je reč o postojećem predmetu; kad nije siguran — pita. |
| Status obrade dokumenta, uživo | Red `shared/intake_queue.py`, worker `shared/intake_worker.py`, start `api.py:850`; `GET /api/smart-intake/jobs/{job_id}` (`smart_intake.py:257`); FE `vindex.js:21605` (`_siPollJobs`), labele `:21374-21379`, nastavak `:21418` | `test_intake_worker_phase1a.py::test_process_success_path_no_review_when_all_confident`, `::test_process_skips_already_processed_job_idempotent` | `PRODUCTION` | Advokat u živo vidi: Priprema → Prepoznavanje tipa → Izvlačenje podataka → Poređenje sa predmetima → Obrađeno. |
| Red za ljudsku proveru kad AI nije siguran | `routers/smart_intake.py:356` → `.../review/resolve`; FE `vindex.js:21824` | `test_intake_documents.py::test_resolve_review_advances_job_status_and_resolves_review`, `::test_resolve_review_simultaneous_approval_only_one_wins` | `PRODUCTION` | Ispod praga sigurnosti dokument čeka advokata; klik na „Kreiraj predmet" je potvrda. |
| Ispravka pojedinačnog pogrešno pročitanog polja | `routers/smart_intake.py:514` → `.../entities/{entity_id}/correct`; FE `vindex.js:21748` | `test_intake_documents.py::test_correct_entity_preserves_original_writes_corrected` | `PRODUCTION` | Original se čuva radi merenja tačnosti sistema. |
| Odbijanje nepodržanog formata odmah | `routers/smart_intake.py:88` `_ALLOWED_UPLOAD_SUFFIXES` | `test_smart_intake_upload_validation.py::test_mixed_batch_valid_and_invalid_reported_independently` | `PRODUCTION` | U mešovitom paketu loš fajl se prijavi po imenu, ostali prolaze. |
| Prepoznavanje istog fajla otpremljenog dvaput | `routers/smart_intake.py:152` (`idempotency_key = user_id:sha256`); `api.py:4860-4880` | `test_intake_e2e_restart.py` | `PRODUCTION` | Isti fajl otpremljen dvaput ne pravi duplikat posla. |
| Čuvanje originala — šifrovano | Bucket `intake-dokumenti` (`smart_intake.py:60`), AES-GCM pre uploada `smart_intake.py:97`; isti obrazac `api.py:4784-4794` | `test_intake_original_file_storage.py::test_upload_stores_original_file_and_writes_real_storage_path` | `PRODUCTION` | Originalni skenirani/potpisani fajl se čuva šifrovan, ne samo izvučeni tekst. |
| Brisanje „siročeta" kad obrada padne | `api.py:4986-5001` | `test_sprint002_pipeline_a_orphan_cleanup.py::test_predmet_dokumenti_insert_failure_deletes_orphan_blob` | `PRODUCTION` | Ako upis u bazu padne posle uploada, fajl se briše da ne ostane bez vlasnika. |
| Privremeni dokument za brzo pitanje nestaje sam | `routers/dokument.py:252-256`, `:372-377` (temp fajl obrisan), Pinecone TTL 24h `:291`, auto-čišćenje `:323-330`; FE `vindex.js:8891`, `21032` | `test_uploaded_doc_api.py::test_upload_docx_happy_path`, `test_uploaded_doc_cleanup.py` | `PRODUCTION` | Dokument otpremljen samo radi pitanja nestaje posle 24 sata i nigde se ne arhivira. |
| Brisanje dokazne stavke | `routers/evidence.py:416` → `DELETE /api/evidence/predmeti/{id}/dokaz/{dokaz_id}`; FE `vindex.js:18809` | bez direktnog testa (ponašanje opisano `evidence.py:424-437`) | `PRODUCTION` | Meko brisanje tvrdnje/dokaza uz trag. |
| Pitanja o otpremljenom dokumentu | `routers/dokument.py:404` → `POST /api/dokument/pitanje`, provera vlasništva `:170`; FE `vindex.js:8942` | `test_doc_pitanje_api.py`, `test_doc_retrieval.py` | `PRODUCTION` | Advokat pita o konkretnom dokumentu; kredit se ne naplaćuje ako AI padne (`dokument.py:480-486`). |
| Forenzička analiza dokumenta | `routers/dokument.py:491` → `POST /api/dokument/analiza`, segmentacija `analiza/segmenter.py`, GPT-4o; FE `vindex.js:9191`, `21093` | `test_analiza_segmenter.py`, `test_analiza_validator.py` | `PRODUCTION` | Strukturirani izveštaj o dokumentu. Kod dugih dokumenata skraćuje segmente (`dokument.py:537-547`) — nije pravi multi-pass. |
| Izvlačenje rokova iz dokumenta | `routers/dokument.py:593` → `POST /api/dokument/rokovi`, `uploaded_doc/deadline_parser.py`; FE `vindex.js:9288` | `test_deadline_parser.py` | `PRODUCTION` | Iz rešenja/presude izvuče rokove i izračuna datume. Ne troši kredit. |
| Poređenje dokumenata iz predmeta (traženje protivrečnosti) | `routers/cross_doc.py:295` → `POST /api/analiza/cross-doc/predmet` (2–5 dokumenata); FE `vindex.js:11868`, izbor `12310` | `test_cross_doc.py::test_predmet_endpoint_uspesno`, `::test_predmet_endpoint_nedovoljno_dokumenata` | `PRODUCTION` | Pronalazi protivrečnosti između dokumenata istog predmeta. |
| Pregled teksta dokumenta iz spisa | `api.py:5586` → `GET /api/predmeti/{id}/dokumenti/{dok_id}/preview`, audit upis `:5613`; FE `vindex.js:15521` | `test_intake_dokument_view_audit.py` | `PRODUCTION` | Otvara prepoznati tekst i beleži ko ga je i kada gledao. |
| Evidence Vault — pregled i ručni unos dokaza | `routers/evidence.py:326` GET, `:378` POST; FE `vindex.js:18708`, `18800` | bez direktnog testa rute | `PRODUCTION` | Jedan ekran sa svim dokumentima predmeta i matricom dokaza. |
| Graf dokaza — čitanje | `routers/evidence_graph.py:286` → `GET /api/evidence-graph/{predmet_id}`; FE `vindex.js:22773` | bez direktnog testa rute | `PRODUCTION` | Prikazuje poslednji sačuvani graf entiteta i veza. |
| Generisanje dokumenta iz šablona | `routers/doc_templates.py:157` → `POST /api/doc-templates/generisi`, lista `:144`; FE `vindex.js:15436`, `15658` | `test_templates_podnesci.py::test_tacno_8_tipova`, `::test_sablon_nema_neresenih_viticicaste_zagrade` | `PRODUCTION` | Popuni se formular i dobije gotov nacrt podneska. |
| Čuvanje generisanog dokumenta | `routers/doc_templates.py:203` → `.../sacuvaj`; FE `vindex.js:15690` | `test_doc_templates_ownership.py` | `PRODUCTION` | Upisuje se u `predmet_beleske` kao beleška (`doc_templates.py:227-232`), **ne** u `predmet_dokumenti`. |
| Masovni uvoz klijenata i predmeta iz tabele | `routers/intake.py:932` → `POST /api/intake/bulk-import` (do 100 redova); FE `vindex.js:22204` | `test_intake.py`, `test_v39c_audit_bulk_import.py` | `PRODUCTION` | Uvoz tabele klijenata i predmeta. Ne uvozi dokumenta. |
| Izvoz svih podataka (GDPR čl. 20) | `routers/data_export.py:66` → `GET /api/export/complete`; FE `vindex.js:808` | `test_gdpr_delete.py` | `PRODUCTION` | ZIP sa svim podacima. Izvozi evidenciju o dokumentima, **ne i same originalne fajlove** (`data_export.py:92`). |
| Batch finalizacija (ceo paket → jedan predmet, 1 poziv) | `routers/smart_intake.py:1796` → `POST /api/smart-intake/jobs/finalize-batch` | `test_omega_sprint001_batch_intake.py::test_finalize_batch_aggregates_multiple_jobs_into_one_case_summary` | `IMPLEMENTED_UNWIRED` | Postoji brz put; UI umesto toga vrti petlju pojedinačnih poziva (`vindex.js:21805-21830`). |
| Odbijanje dokumenta u redu za proveru | `routers/smart_intake.py:453` → `.../review/reject` | `test_intake_status_writers.py` | `IMPLEMENTED_UNWIRED` | Ne postoji „ovaj dokument je neupotrebljiv, izbaci ga" — UI zna samo potvrdu. |
| Ručno preuzimanje klasifikacije ad-hoc uploada | `routers/dokument.py:566` → `POST /api/dokument/klasifikuj-sesija` | bez testa | `IMPLEMENTED_UNWIRED` | Ruta koju sam upload preporučuje u odgovoru (`dokument.py:366-369`) — niko je ne zove. |
| Poređenje slobodno unetih tekstova | `routers/cross_doc.py:253` → `POST /api/analiza/cross-doc` | `test_cross_doc.py::test_endpoint_uspesno` | `IMPLEMENTED_UNWIRED` | Stariji ulaz gde se tekstovi lepe ručno. |
| Graf dokaza — ručno dodavanje čvora | `routers/evidence_graph.py:339` → `POST /api/evidence-graph/dodaj-cvor` | bez testa | `IMPLEMENTED_UNWIRED` | — |
| Otvaranje predmeta iz šablona | `routers/intake.py:815` → `POST /api/intake/from-template` | `test_phase6_billing_intenti.py` | `IMPLEMENTED_UNWIRED` | Šabloni se prikazuju (`vindex.js:15368`), ali dugme koje bi po njima kreiralo predmet ne postoji. |
| **Graf dokaza — generisanje** | Backend `routers/evidence_graph.py:178` `POST /generisi`; FE `vindex.js:22735` zove `/api/evidence-graph/generi%C5%A1i` (tj. `generiši`) | `test_gamma_evidence_check_wiring.py` (koristi ISPRAVAN put, pa bug nikad nije pao) | `DEAD` (pokvarena veza) | Dugmad „Generiši graf" (`vindex.js:22785`) i „Regeneriši" (`:22997`) gađaju putanju koja na serveru ne postoji. **Provereno nezavisno.** |
| Merenje tačnosti i zdravlja intake sistema | `routers/smart_intake.py:610` `/admin/health`, `:628` `/admin/accuracy` | `test_intake_accuracy.py`, `test_intake_accuracy_benchmark.py` | `EXPERIMENTAL` + bez pozivaoca | Founder-only (`smart_intake.py:91`), nema ekran. |
| Unos zakona u bazu znanja | `routers/law_upload.py:173` → `POST /api/admin/law/upload`; FE `vindex.js:15143`, `15175`, `15199` | bez testa | `EXPERIMENTAL` | Founder-only (`law_upload.py:41-44`). |
| Masovni uvoz biltena sudske prakse | `routers/batch_ingest.py:188` `/api/admin/ingest/job`, `:235`, `:252` | `test_batch_ingest.py` | `EXPERIMENTAL` + bez pozivaoca | Founder-only (`batch_ingest.py:41`); UI ima samo `discover`/`discovered`. |
| Ručno čišćenje isteklih sesija | `routers/dokument.py:380` → `POST /api/dokument/cleanup` (traži `X-Admin-Token`) | `test_uploaded_doc_api.py::test_cleanup_endpoint_requires_token` | `EXPERIMENTAL` + bez pozivaoca | Automatsko čišćenje ipak radi na svakom uploadu. |

### Nedostaci potvrđeni u kodu (bitno za sajt — ne obećavati)

1. **Ne postoji brisanje dokumenta iz predmeta.** Nijedna ruta. `predmet_dokumenti` je čak i van dosega GDPR brisanja naloga (`tests/test_gdpr_delete.py:130`). Nedoslednost: fajl koji je poslao klijent kroz portal **može** da se briše (`routers/client_portal.py:750`, FE `vindex.js:13545`).
2. **Nema „dodaj 10 dokumenata u već otvoreni predmet".** `POST /api/predmeti/{id}/upload` prima tačno jedan fajl (`api.py:4719`). Više fajlova ide samo kroz Smart Intake.
3. **Nema statusa obrade za direktan upload u predmet.** Worker opslužuje samo Smart Intake; `api.py:4715` radi sve sinhrono, korisnik vidi samo spiner.
4. **`.doc` je dozvoljen na ulazu, a ekstraktor ga ne ume.** `api.py:4665` prihvata `.doc`, `uploaded_doc/extractor.py:393-401` nema granu za njega → `ValueError`. **Provereno nezavisno.**
5. **Fotografije backend prima, frontend ih na putanji predmeta blokira.** `api.py:4661-4665` dozvoljava `.jpg/.png`, `vindex.js:21019` propušta samo `['.pdf','.docx','.doc']`.
6. **Klasifikacija na `/api/dokument/upload` se izračuna i baci.** `dokument.py:340-347` pravi GPT poziv, `:343` ga samo loguje, odgovor nosi `klasifikacija: None`. Trošak postoji, korist nula.

---

## 2. PREDMET

| Sposobnost | Gde (fajl:linija / ruta) | Test | Status | Šta radi (jezikom advokata) |
|---|---|---|---|---|
| Radni prostor predmeta (Cockpit) | `api.py:5655` → `GET /api/predmeti/{id}/workspace`; FE `vindex.js:12193` (`pred_loadDetail`), `9701` | `test_singlebrain_phase3_fixes.py::test_predmet_workspace_selects_tip_dokaza`; `test_omega_sprint005_full_chain_to_workspace.py` | `PRODUCTION` | Jednim pozivom vraća predmet, stranke, dokumente, rokove, komentare, beleške, komunikaciju, praksu, AI sažetak, procenu rizika i ocenu spremnosti. |
| Dnevni operativni pregled („šta danas") | `routers/workspace.py:175` → `GET /api/workspace`; FE `vindex.js:1733` (`wsLoad`), poziv iz `dash_load` `:1302` | `test_omega_sprint004_workspace.py::test_empty_workspace_all_buckets_empty` | `PRODUCTION` | Skuplja sve što traži pažnju u kante: Danas / Kritično / Predstojeće / Za pregled / Na čekanju / Završeno. |
| **Deterministički procesni rizik** | `services/risk_engine.py::calculate_procesni_rizik`, poziv `api.py:5758` + `identify_case_problems` `:5776`; koriste ga i `routers/ccc.py:160`, `routers/dashboard.py:281`, `matter_intel`, `case_pipeline`, `hearing_cc` | `test_matter_intel.py`, `test_ccc.py`, `test_dashboard.py`, `test_case_pipeline.py`, `test_hearing_cc.py`, `test_decision_registry_completeness.py` (10+ fajlova) | `PRODUCTION` | Nivo rizika i „otkriveni problemi" računa backend po formuli; AI sme samo da objasni zašto, ne i da odredi broj. |
| Ocena spremnosti predmeta (Case Ready Score) | `routers/case_pipeline.py:25` → `POST /api/predmeti/{id}/pipeline`; FE `vindex.js:10945`, `21268` | `test_case_pipeline.py::test_checklist_has_six_items` | `PRODUCTION` | Pokreće 9-koračnu automatiku posle kreiranja predmeta i vraća ocenu spremnosti sa čeklistom. |
| Otvorene akcije unutar predmeta | `routers/case_actions.py:120` → `GET /api/case-actions/predmeti/{id}`; FE `vindex.js:10723`, poziv `:10706` | `test_omega_sprint004_case_to_workspace_flow.py` | `PRODUCTION` | Prikazuje sistemski detektovane radnje koje predmet zahteva (nedostajući dokaz, blizak rok). |
| Stranke u postupku (4 uloge) | Tabela `predmet_klijenti`; čitanje `api.py:5690`, `3895`; razvrstavanje `api.py:5720-5727` | `test_mission001_predmet_klijenti.py`, `test_pagination_predmeti_klijenti.py` | `PRODUCTION` | Veza predmet↔klijent sa ulogom (stranka / protivna / svedok / ostali) + njihova komunikacija. |
| Vezivanje stranke jednim klikom posle uploada | `api.py:6033` → `POST /api/predmeti/{id}/confirm-links`, upis `:6086`; FE `vindex.js:11281` | `test_sec001_predmet_ownership.py` | `PRODUCTION` | Potvrđuje predlog „ovaj dokument pominje ovog klijenta" i opciono dodaje rok. |
| Hronologija predmeta (spojena iz 6 izvora) | `routers/intelligence_timeline.py:56` → `GET /api/predmeti/{id}/intelligence-timeline`; FE `vindex.js:18548`, pozivi `:10345`, `:11789` | `test_intelligence_timeline.py::test_timeline_includes_audit_predmet_event` | `PRODUCTION` | Spaja predmet, dokumente, ročišta, hronologiju, verzije Genome-a i audit log u jedan tok, uz upozorenje ako neki izvor otkaže. |
| Upis događaja u hronologiju | 10 mesta: `api.py:4705`, `api.py:6100`, `case_dna.py:672`, `rokovi_lanac.py:~425`, `predmeti_close.py:189`, `intake.py:282/415/885`, `copilot.py:810`, `learning.py:274` | `test_phase36_rokovi.py`, `test_predmeti_close.py` | `PRODUCTION` | Svaka bitna radnja upisuje trag u život predmeta. |
| Automatske posledice promene predmeta | `services/case_evolution.py:1245` `CONSEQUENCE_REGISTRY`, dispečer pozvan iz `services/event_bus.py:364` | `test_case_evolution.py::test_try_claim_consequence*`, `test_delta_sprint003_full_convergence.py` | `PRODUCTION` | Kad se predmet promeni, sistem sam osveži procenu, upiše u hronologiju, preračuna akcije i pošalje obaveštenje — **tačno jednom**, bez duplikata. |
| Dokazi / činjenice (Evidence Vault) | Tabela `predmet_dokazi`; `routers/evidence.py` GET/POST/DELETE; FE `vindex.js:18708`, `18788`, `18800`, `18809` | `test_p0d_case_context_integrity.py` | `PRODUCTION` | Unos i reklasifikacija dokaza (snaga, kategorija, pravni element); meko brisanje se svuda poštuje. |
| Automatska klasifikacija novog dokaza | `services/case_evolution.py::_consequence_evidence_classify`, registrovana `:1284`; emiteri `api.py:5048`, `smart_intake.py:1556` | `test_delta_sprint002_event_migration.py` | `PRODUCTION` | Novi dokaz se sam klasifikuje i odmah pokreće preračun akcija. |
| Ročišta — zakazivanje, lista, brisanje | `routers/rocista.py:128` POST (FE `vindex.js:14388`), `:226` GET (FE `:14336`), `:457` DELETE (FE `:14407`) | `test_rocista_kalendar.py::test_rociste_req_valid` | `PRODUCTION` | Zakazivanje uz sud/datum/vreme/sudnicu; okida osvežavanje procene i akcija. |
| Kalendar rokova i ročišta | `routers/kalendar.py:175` → `GET /api/kalendar/pregled`; FE `vindex.js:14194`, `14253`, `14272` | `test_rocista_kalendar.py::test_kalendar_pregled_default_range` | `PRODUCTION` | Spaja ročišta i rokove u jedan kalendar (danas → +30 dana). |
| Izvoz kalendara u Outlook/Google (.ics) | `routers/kalendar.py:209` → `POST /api/kalendar/ics`; FE `vindex.js:14231` | `test_rocista_kalendar.py::test_kalendar_ics_has_vevent` | `PRODUCTION` | Rokovi i ročišta prelaze u lični kalendar. |
| Lanac ZPP procesnih rokova | `routers/rokovi_lanac.py:383` GET (FE `vindex.js:11690`), `:389` POST (FE `:11726`, `11775`, `22456`) | `test_rokovi_lanac.py::test_lanac_sa_predmetom` | `PRODUCTION` | Od datuma prijema presude sam izračuna sve vezane rokove (žalba 15 dana, ZPP čl. 374) i upiše ih u hronologiju. |
| Kalkulator zastarelosti | `routers/zastarelost.py:207` GET tipovi (FE `vindex.js:9435`), `:214` POST (FE `:9475`) | `test_phase36_rokovi.py` | `PRODUCTION` | Za tip potraživanja i datum početka vraća datum zastarelosti, zakonski osnov i preostale dane. |
| Zastarelost → kalendar (.ics) | `routers/zastarelost.py:319` → `POST /rokovi/ics-export`; FE `vindex.js:9392`, `9416` | `test_phase36_rokovi.py` | `PRODUCTION` | Prebacuje izračunati rok u kalendar. |
| Komentari na predmetu | `routers/komentari.py:40` POST (FE `vindex.js:4475`), `:75` GET (FE `:4448`), `:109` PUT (FE `:4489`), `:139` DELETE | `test_v48_put_komentar_guard.py::test_3_foreign_comment_is_404_and_unchanged` | `PRODUCTION` | Interna prepiska tima uz predmet; vlasništvo se proverava unutar samog UPDATE-a. |
| Beleške na predmetu | `api.py:4071` POST (FE `vindex.js:19931`), `:4095` DELETE | `test_sec001_predmet_ownership.py` | `PRODUCTION` | Slobodne beleške, prikazane u Cockpit-u (`vindex.js:12405`). |
| Case Genome — čitanje | `routers/case_dna.py:923` → `GET /api/predmeti/{id}/case-dna`; FE `vindex.js:19970` | `test_case_dna_verifikacija_alert.py` | `PRODUCTION` | Živi model predmeta: pravna teorija, stranke, finansije, kontradikcije, snaga 0–100%, plan, najslabija tačka. |
| Case Genome — ručno osvežavanje | `routers/case_dna.py:957` → `POST .../case-dna/refresh`; FE `vindex.js:17438`, dugme `index.html:1603` | `test_blackswan_mission001.py::test_refresh_case_dna_rejects_concurrent_call_for_same_predmet` | `PRODUCTION` | Ponovo čita sve dokumente i regeneriše procenu; dva istovremena osvežavanja daju 409, ne duplikat. |
| Case Genome — automatsko osvežavanje | `services/case_evolution.py:290`, registrovano na `DOCUMENT_ACCEPTED` / `REVIEW_ACCEPTED` / `ROCISTE_ZAKAZANO` / `DOCUMENT_BATCH_COMPLETED` | `test_case_evolution.py`, `test_omega_sprint002_case_intelligence.py::test_scenario4_crash_after_genome_before_summary_retry_does_not_redo_genome` | `PRODUCTION` | Novi dokument ili ročište sami osvežavaju procenu — bez klika i bez duplog troška pri restartu. |
| Case Genome — istorija verzija i poređenje | `routers/case_dna.py:1165` (FE `vindex.js:18203`), `:1225` (FE `:18351`) | `test_ztc_genome_scale_and_race.py` | `PRODUCTION` | Prikazuje kako je snaga predmeta rasla/padala kroz verzije. |
| Rokovi nađeni u dokumentu ulaze u kalendar | `routers/case_dna.py:~640` `_sync_rokovi_to_hronologija`, upis `:672` | `test_case_dna_events.py` | `PRODUCTION` | Rok koji AI nađe u dokumentu ne ostaje zaključan u analizi — vidi se u kalendaru. |
| **Provera da AI ne izmišlja dokumente** | `shared/genome_validator.py`; koriste `case_dna.py:40`, `cio.py:41`, `evidence_graph.py:250`, `case_commander.py:861` | `test_genome_validator.py::test_dokazi_rang_flags_nonexistent_document` | `PRODUCTION` | Odbija procenu koja se poziva na dokument koji ne postoji; ishod: prihvati / prihvati uz upozorenje / traži pregled. |
| **Jedinstven kontekst predmeta za sve AI module** | `shared/case_context.py`; konzumenti: `case_commander.py:50`, `case_intelligence.py:31`, `cio.py:39`, `court_predictor.py:31`, `digital_twin.py:45`, `hearing_cc.py:28`, `matter_intel.py:23`, `morning_briefing.py:41`, `strategija.py:577` | `test_tau002_case_context.py::test_build_case_context_has_all_14_contract_fields`, `::test_case_context_module_makes_zero_gpt_calls`, `test_wave11_context_isolation.py` | `PRODUCTION` | Jedan deterministički opis predmeta od 14 polja koji koristi 9 AI modula — da svi „gledaju isti predmet". Sam po sebi ne troši AI. |
| **Ograničenje koliko samouvereno AI sme da govori** | `shared/case_readiness.py`; konzumenti `case_pipeline.py:117`, `api.py:5958`, `case_commander.py:49`, `case_intelligence.py:437`, `cio.py:40`, `copilot.py:526/560`, `court_predictor.py:32`, `digital_twin.py:46` | `test_sigma_sprint004_case_readiness.py::test_readiness_critical_gap_beats_everything_else` | `PRODUCTION` | Presuđuje SPREMAN / DELIMIČNO / BLOKIRAN / KRITIČNA PRAZNINA i time ograničava jačinu AI tvrdnji. |
| AI briefing predmeta („jedan sledeći korak") | `routers/case_intelligence.py:400` → `POST /api/intelligence/predmeti/{id}/briefing`; FE `vindex.js:17502`, dugme `index.html:1606` | `test_case_intelligence_briefing_alerts_fix.py`, `test_omega_sprint002_case_intelligence.py` | `PRODUCTION` | Spaja lekcije, memoriju kancelarije, obrasce, alarme i istoriju odluka u jednu preporuku. |
| Zadaci uz predmet (Kanban) + AI predlog zadataka | `routers/zadaci.py:421` (FE `vindex.js:23105`), `:141` (FE `:23124`), `:285` (FE `:23143`), `:377` (FE `:23161`), `:245` (FE `:23176`), `:533` AI (FE `:23388`) | `test_zadaci.py`, `test_beta_lockdown_zadaci_predmet_idor.py`, `test_nexus_zadaci_ai_grounding.py` | `PRODUCTION` | Kanban zadataka uz predmet i AI koji iz predmeta predlaže šta uraditi. |
| Zatvaranje predmeta sa ishodom | `routers/predmeti_close.py:67` → `PATCH /api/predmeti/{id}/zatvori`, upis u hronologiju `:189`; FE `vindex.js:22308` | `test_predmeti_close.py::test_zatvori_concurrent_race_returns_409_not_silent_double_close` | `PRODUCTION` | Zatvara predmet sa ishodom (uspeh / poravnanje / odbijeno) i beleži to. |
| Masovna promena statusa predmeta | `routers/predmeti_close.py:323` → `PATCH /api/predmeti/bulk`; FE `vindex.js:10254`, `10284` | `test_predmeti_close.py` | `PRODUCTION` | Arhiviranje/zatvaranje više predmeta odjednom. |
| Kanban faza predmeta | `api.py:4030` → `PATCH /api/predmeti/{id}/kanban-faza`; FE `vindex.js:10516` | `test_v41_predmet_update_zero_row_guard.py` | `PRODUCTION` | Prevlačenje predmeta kroz faze. |
| Ocena zdravlja portfelja predmeta | `routers/health_index.py:498` → `GET /api/firm/health-index`; FE `vindex.js:1318` | `test_health_index_weak_signals.py::test_weak_signals_uses_hronologija_ishod_not_genome_fields` | `PRODUCTION` | Ocena portfelja + slabi signali; keš od 1h uz obavezan prikaz „iz keša". |
| Case Commander (analiza, brza provera, čeklista, jutarnji pregled) | `routers/case_commander.py:360`, `:450`, `:505`, `:904`, `:1034` — jedini pomen u frontendu je komentar `vindex.js:1301` | `test_tau007_case_commander_consolidation.py` (7 testova) | `IMPLEMENTED_UNWIRED` | 1056 linija radnog, testiranog i potpuno nedostupnog koda. |
| Označavanje ročišta kao održano/odloženo | `routers/rocista.py:269` → `PATCH /api/rocista/{id}` — nema PATCH poziva u frontendu | `test_beta_gate_rociste_consistency.py::test_izmeni_rociste_stale_if_updated_at_rejects_with_409` | `IMPLEMENTED_UNWIRED` | Ruta ima i zaštitu od istovremene izmene, ali korisnik ne može iz UI da promeni status ročišta. |
| Worklist (akcije grupisane po predmetima) | `routers/case_actions.py:61` → `GET /api/case-actions/worklist` | bez direktnog testa rute | `IMPLEMENTED_UNWIRED` | „Predmet A — 2 kritične akcije" se nikad ne prikazuje. |
| Ocena spremnosti — samo očitavanje (jeftino) | `routers/case_pipeline.py:65` → `GET /api/predmeti/{id}/pipeline/status` | `test_case_pipeline.py` (samo pomoćna funkcija) | `IMPLEMENTED_UNWIRED` | Jeftina polovina; UI koristi samo skupi POST. |
| Poslednji sačuvani briefing | `routers/case_intelligence.py:547` → `GET .../briefing/poslednji` | bez testa | `IMPLEMENTED_UNWIRED` | Vratio bi poslednji briefing bez novog troška; UI ga ne traži. |
| Deadline Guardian (skeniranje propuštenih rokova) | `routers/zastarelost.py:363` `/api/rokovi/guardian`, `:463` `/guardian/scan` | `test_phantom_ai_charges.py` (samo naplata) | `IMPLEMENTED_UNWIRED` | Troši AI, a niko ga ne poziva. |
| Kalkulator procesnih rokova sa praznicima | `routers/zastarelost.py:249`, `:294`, `:311`, `:192` | bez testa rute | `IMPLEMENTED_UNWIRED` | Nedostupno iz aplikacije. |
| Lični zadaci i statistika zadataka | `routers/zadaci.py:193`, `:469`, `:344` | `test_zadaci.py::test_statistika_solo_advokat_does_not_crash` | `IMPLEMENTED_UNWIRED` | Postoje i testirani su, nemaju ekran. |
| Ishod zatvorenog predmeta (očitavanje) | `routers/predmeti_close.py:233` → `GET /api/predmeti/{id}/ishod` | `test_predmeti_close.py::test_get_ishod_closed_predmet` | `IMPLEMENTED_UNWIRED` | Ishod se nigde ne prikazuje preko ove rute. |
| Follow-up posle ročišta | `routers/rocista.py:354` → `POST /api/rociste/followup` | bez testa | `IMPLEMENTED_UNWIRED` | Trebalo bi da generiše zadatke posle održanog ročišta. |
| Stara hronologija (dupli izlaz) | `api.py:5470` → `GET /api/predmeti/{id}/hronologija` | bez testa | `IMPLEMENTED_UNWIRED` | Funkcija koja ga je zvala je obrisana (`vindex.js:12461`). |
| Stara AI preporuka za predmet | `api.py:5507` → `GET /api/predmeti/{id}/ai-preporuka` | bez testa | `IMPLEMENTED_UNWIRED` | Duplira ono što Cockpit i briefing već rade. |
| Podsetnici za rokove (email/SMS) | `routers/email_notif.py:256`, `routers/sms.py:217` — obe iza `_require_cron_or_founder` | `test_synapse_health_deadline_events.py` | `EXPERIMENTAL` | Okida ih spoljni cron ili founder, ne korisnik. |
| 7 tipova događaja bez ijednog izvora | `DOKUMENT_UPLOADOVAN`, `ROK_DODAN`, `STRATEGIJA_GENERISANA`, `ANALIZA_ZAHTEVANA`, `DOCUMENT_MODIFIED`, `CONFIDENCE_DROPPED`, `MANUAL_CORRECTION_APPLIED` | — | `DEAD` | Deklarisani u šifrarniku, nijedna linija ih ne kreira — posledice vezane za njih ne mogu da se okinu. |

### Nalazi vredni pažnje

- **Hronologija ima 10 nezavisnih upisivača i nijednog vlasnika.** Svi pišu direktno u `predmet_hronologija`, mimo mehanizma događaja koji `services/case_evolution.py` proglašava kanonskim.
- **11 tipova događaja stvarno nastaje** (`PREDMET_KREIRAN`, `NEW_EVIDENCE_REGISTERED`, `DOCUMENT_ACCEPTED`, `ROCISTE_ZAKAZANO`, `GENOME_UPDATED`, `HEALTH_SCORE_PROMENJEN`, `ROK_KRITICAN` i dr.) — automatika oko njih je stvarna, ali pokriva manje od polovine deklarisanih tipova.

---

## 3. AI ANALIZA

**Kako se određuje cena u kreditima.** Nijedna cena nije u Python kodu. `shared/usage.py::UsageService.consume` čita politiku iz tabele `feature_registry` preko `shared/feature_registry.py::get_policy`. Vrednosti ispod su početne vrednosti iz migracija 064/066/069/083/111 — administrator ih menja bez novog deploy-a.

| Sposobnost | Gde (fajl:linija / ruta) | Test | Status | Krediti | Šta radi (jezikom advokata) |
|---|---|---|---|---|---|
| Copilot — razgovor u predmetu (22 namere) | `routers/copilot.py:1420` → `POST /copilot/chat`; FE `vindex.js:12064` | `test_sprint6g_copilot_billing_gate.py::test_3_authorized_reaches_provider_and_is_charged_once` | `PRODUCTION` | 1 | Advokat piše pitanje u predmetu; sistem prepozna nameru i sam usmeri na pravno pitanje, praksu, nacrt, rok, belešku ili naplatu. |
| AI pravno pitanje nad bazom zakona | `api.py:3059` → `POST /api/pitanje`; FE `vindex.js:7629`, `10602` | `test_blackswan_mission001.py` | `PRODUCTION` | 1 | Pravno istraživanje nad bazom srpskih zakona, sa navedenim izvorima. |
| Pravna procena predmeta | `api.py:4488` → `POST /api/procena`; FE `vindex.js:20119` | bez testa | `PRODUCTION` | 2 | Strukturisana procena predmeta iz iznetih činjenica. |
| AI sažetak stanja predmeta pri otvaranju | `api.py:5655` → `GET /api/predmeti/{id}/workspace`; FE `vindex.js:9701`, `12193` | `test_iron_lawyer_frontend_fixes.py` | `PRODUCTION` | 1 + dnevni limit 50 + pauza 5s | Kad advokat otvori predmet, dobija sažetak stanja. |
| Predikcija ishoda spora | `routers/court_predictor.py:313` → `POST /api/predictor/analiza`; FE `vindex.js:3012` (registar) + `3169` (poziv) | `test_celina2_predictor_commander_2026_07_24.py::test_predictor_api_retry` | `PRODUCTION` | 2 | Procenjuje šansu za uspeh na osnovu srpske prakse, dokaza i argumenata. |
| Priprema pred ročište (Battle Report) | `routers/court_predictor.py:565`; FE `vindex.js:3312` | `test_celina2_predictor_commander_2026_07_24.py::test_battle_report_api_retry` | `PRODUCTION` | 2 | Sudija, protivnik, slabosti, strategija — na jednom mestu. |
| Profil suda / sudije | `routers/court_predictor.py:1152`; FE `vindex.js:3398` | `test_court_predictor_deterministic_derived_fields.py` | `PRODUCTION` | 2 | Profil postupanja suda iz baze odluka. |
| Analiza protivne strane | `routers/court_predictor.py:1331`; FE `vindex.js:3444` | `test_celina2_predictor_commander_2026_07_24.py::test_opponent_intel_api_retry` | `PRODUCTION` | 2 | Spaja sudsku praksu i sopstveni CRM o protivniku. |
| Koliko je argument istorijski uspešan | `routers/court_predictor.py:921`; FE `vindex.js:3480` | `test_celina2_predictor_commander_2026_07_24.py::test_argument_reputation_koristi_retrieve_sudska_praksa_ne_niskonivoovski` | `PRODUCTION` | 2 | Ocenjuje koliko pojedini argument prolazi pred sudom. |
| Provera pouzdanosti procene | `routers/court_predictor.py:1596`; FE `vindex.js:3359` | `test_court_predictor_deterministic_derived_fields.py` | `PRODUCTION` | 2 | Vraća ne samo procenat nego i dokaz: broj sličnih predmeta, presuda, uspešnost. |
| Statistika učenja kancelarije | `routers/court_predictor.py:1758`; FE `vindex.js:2317` | `test_singular_intelligence_fixes.py` | `PRODUCTION` | 0 | Uspešnost po tipu spora, broj AI analiza. |
| Tim savetnika — jedan savetnik | `routers/multi_agent.py:394` → `POST /api/agents/run`; FE `vindex.js:19506` | `test_multi_agent.py::test_run_agent_known` | `PRODUCTION` | 1 | Bira jednog od 6 savetnika (protivnički advokat, sudija...) i traži mišljenje. |
| Tim savetnika — tri paralelno | `routers/multi_agent.py:694`; FE `vindex.js:19562` | `test_multi_agent.py::test_run_parallel_exercises_thread_wrapped_predmet_fetch` | `PRODUCTION` | 1 × broj uspešnih savetnika (`multi_agent.py:793`) | Tri savetnika istovremeno, pa konsolidovan izveštaj. |
| Slični predmeti iz sopstvene kancelarije | `routers/precedenti.py:47`; FE `vindex.js:17567`, `18828`, `18859` | `test_synapse_precedenti_genome_context.py` | `PRODUCTION` | 1 | Pronalazi slične ranije predmete i izvlači naučene lekcije. **Nije semantička pretraga** — poređenje po tipu i oblasti (`precedenti.py:80-89`). |
| Zdravlje i rizik predmeta (bez AI) | `routers/matter_intel.py:45`; FE `vindex.js:18923` | `test_matter_intel.py::test_matter_intel_404` | `PRODUCTION` | 0 | Ocena zdravlja, procesni rizik i nedostajući dokazi — sve deterministički. |
| Uspešnost kancelarije po tipu spora | `routers/outcome_intel.py:49`; FE `vindex.js:17569`, `18892`, `19179`, `22394` | `test_outcome_intel.py::test_with_history_calls_gpt` | `PRODUCTION` | 1 | Procenat uspeha i faktori uspeha za isti tip spora. |
| Komandni centar predmeta | `routers/ccc.py:20`; FE `vindex.js:18999` | `test_ccc.py::test_ccc_health_score_matches_canonical_risk_engine` | `PRODUCTION` | 0 | Jedan poziv skuplja sve: dokaze, rokove, naplatu, ocenu zdravlja. |
| Koliko su AI procene bile tačne | `routers/confidence_audit.py:37`; FE `vindex.js:2353` | `test_phantom_ai_charges.py` | `PRODUCTION` | 0 (migracija 111 spustila sa 1) | Meri koliko su ranije AI procene odgovarale stvarnim ishodima. |
| Spajanje ishoda sa ranijim preporukama | `routers/confidence_audit.py:55`; FE `vindex.js:22323` | `test_mission_migration_coverage.py` | `PRODUCTION` | 0 | Zatvara petlju učenja: stvarni ishod se veže za raniju AI preporuku. |
| Dnevni pregled celog portfelja (CIO) | `routers/cio.py:513` GET, `:692` POST; FE `vindex.js:17636` | `test_phoenix_mission_014_cio_truncation_disclosure.py`, `test_phoenix_mission_012_duplication_race_gaps.py` | `PRODUCTION` | 5, mesečni limit 60 | Dnevni sken svih predmeta: šta gori i gde je najveći rizik. |
| Simulacija tri scenarija razvoja predmeta | `routers/digital_twin.py:283`; FE `vindex.js:19221` | `test_lambda001_beta_readiness_fixes.py` | `PRODUCTION` | **9** (3 × množilac 3, migracija 069) | Tri moguća toka predmeta sa verovatnoćama i tačkama odlučivanja. |
| „Šta ako" analiza | `routers/digital_twin.py:417`; FE `vindex.js:19263` | `test_phoenix_closure_open_items.py` | `PRODUCTION` | **3** | Računa kako hipoteza menja verovatnoću uspeha. |
| Komunikacioni profil klijenta | `routers/client_twin.py:153` (FE `vindex.js:4642`), `:281` (FE `:4584`) | bez testa | `PRODUCTION` | 2 / 0 | Gradi profil klijenta iz istorije predmeta i beleški. |
| Upis ishoda predmeta (sistem uči) | `routers/learning.py:126`; FE `vindex.js:22277` | `test_sprint1_background_tasks.py` | `PRODUCTION` | 0 | Advokat po zatvaranju upisuje ishod i presudne faktore. |
| Tiho učenje stila iz ispravki | `routers/corrections.py:232`; FE `vindex.js:6258` | bez testa | `PRODUCTION` | 0 (namerno besplatno) | Kad advokat izmeni AI tekst, sistem zapamti kako. |
| Šta advokat najviše koristi | `routers/analytics.py:60`, `:80`; FE `vindex.js:15938`, `15043` | bez testa | `PRODUCTION` | 0 | Beleži i prikazuje korišćenje funkcija. |
| Statistika po protivničkim advokatima | `routers/analytics.py:182`; FE `vindex.js:11393` | bez testa | `PRODUCTION` | 0 | Broj predmeta i ishodi po protivniku. |
| Ambient Copilot u Word-u | `routers/copilot_ambient.py:57`; klijent `integrations/word_addin/adapter.js:23` (**ne** `vindex.js`) | `test_copilot_ambient.py::test_analyze_with_owned_predmet_id_succeeds` | `PRODUCTION` (Word dodatak, ne veb aplikacija) | 0 + dnevni limit 200 | Dok advokat kuca u Word-u, predlaže članove zakona i praksu za tekući pasus. |
| Tim savetnika — lančana analiza | `routers/multi_agent.py:852` | posredno `test_multi_agent.py` | `IMPLEMENTED_UNWIRED` | 1 po koraku | Izlaz jednog savetnika ulazi u sledećeg, do 5 koraka. |
| Semafor neizvesnosti / Pre-Flight provera | `routers/matter_intel.py:283`, `:494` | `test_singular_intelligence_002_fixes.py` (preflight) | `IMPLEMENTED_UNWIRED` | 2 | Provera spremnosti pre podneska, ročišta, nagodbe ili žalbe. |
| Jednostranični brief pred sudnicu | `routers/court_predictor.py:725` | `test_tau005_court_predictor_migration.py` | `IMPLEMENTED_UNWIRED` | 2 | — |
| Rekonstrukcija „zašto smo izgubili" | `routers/decision_replay.py:270` | `test_celina4_tech_debt_2026_07_24.py` | `IMPLEMENTED_UNWIRED` | 3 | — |
| Graf pravnog rezonovanja | `routers/legal_reasoning.py:29`, `:48`, `:91` | `test_legal_reasoning_engine.py` | `IMPLEMENTED_UNWIRED` (namerno — dokstring `:8`) | 0 | Nema ni `PermissionService`. |
| Institucionalno učenje — 14 od 15 ruta | `routers/learning.py:329`, `396`, `427`, `579`, `728`, `789`, `825`, `895`, `934`, `966`, `1006`, `1040`, `1071`, `1159`, `1224` | bez testa | `IMPLEMENTED_UNWIRED` | 1 na naplatnim | Lekcije, obrasci kancelarije, „šta bi bilo da", izveštaj o uspešnosti — implementirano, nedostupno. |
| Jutarnji brifing | `routers/morning_briefing.py:552` | `test_tau002_morning_briefing_context.py` | `IMPLEMENTED_UNWIRED` (kartica namerno uklonjena, `docs/omega/WORKSPACE_INTEGRATION_REPORT.md:25`) | 0, dnevni limit 5 | Pregled dana: rokovi, ročišta, prioriteti. |
| Brifing mejlom / noćna prioritizacija | `routers/morning_briefing.py:581`, `603`, `682`, `885`, `981`, `1009`, `1032` | `test_lambda008_certification.py` (cron) | `EXPERIMENTAL` — `POST /api/briefing/cron` **nije** deo `api.py::cron_daily`; zavisi od spoljnog servisa | 0 | Ako spoljni servis nije podešen, funkcija je mrtva bez ijednog signala. |
| Analitika preko svih korisnika | `routers/analytics.py:337`; FE `vindex.js:14643` | bez testa | `EXPERIMENTAL` (founder-only `:349`) | 0 | — |
| Telegram bot | `api.py:2994` → `POST /api/bot/ask` | bez testa | `EXPERIMENTAL` (`X-Api-Key`, zaobilazi Supabase auth) | **0 — nema naplate uopšte** | Isto pravno istraživanje kao `/api/pitanje`, bez `UsageService.consume`. |
| AI odgovor u delovima (stream) | `api.py:3220` | `test_lambda008_certification.py` | `IMPLEMENTED_UNWIRED` (nema `EventSource` u `vindex.js`) | 1 | — |
| Stara AI preporuka za predmet | `api.py:5507` | bez testa | `IMPLEMENTED_UNWIRED` (0 pozivalaca u celom repou) | 1 | `vindex.js:23457` koristi istoimeno polje iz sasvim druge rute (profitabilnost). |

### Ograde nad AI pozivima — na živoj putanji

Ovo je **strukturna** zaštita, ne „po pozivnom mestu": `api.py:28` poziva `_patch_prompt_guard()` pre svih router importa, a on zamenjuje metodu SDK **klase** `Completions.create` / `AsyncCompletions.create` (`shared/ai_client.py:566-700`). Zbog toga svaki produkcioni AI poziv prolazi kroz:

1. **Prompt Guard** (`security/prompt_guard.analyze`) — blokira pokušaj ubacivanja zlonamernog uputstva pre slanja modelu.
2. **Response Firewall** (`security/response_firewall.enforce`) — filtrira odgovor pre nego što stigne do advokata; odluka ide u evidenciju kao `ai_response_firewall_decision`.
3. **Poreklo poziva** (`_capture_chat_provenance` → `security/ai_forensics.py:207`) — model, tokeni, latencija, hash prompta i odgovora, `correlation_id`.
4. **Kill-switch** (`shared/ai_client.py:124`) — ako se zaštita ne učita, AI se **gasi**, ne radi nezaštićen.

Dokaz: `tests/test_gov3_response_firewall.py` vozi stvarni SDK poziv (bez mreže) i meri šta se vrati pozivaocu. Izuzeci po ugovoru, izričito imenovani u samom testu: `services/voice_orchestrator.py` (sirov WSS) i Cohere SDK.

### Ograničenja koja sajt ne sme da prećuti

- **`shared/ai_fabric.py` (672 linije multi-provajder governance) ima nula produkcionih pozivalaca.** Prava zaštita radi na drugom mestu (gore). `tests/test_ai_fabric_governance.py:104-113` to tvrdi kao ugovor. Provereno pokretanjem: prolazi.
- **Poreklo vezano za predmet ima samo 3 od 18 rutera** (`copilot`, `court_predictor`, `morning_briefing`). Ostali dobijaju samo `user_id` i `correlation_id` — AI poziv se ne može forenzički vezati za konkretan predmet.
- **`feature_registry.ai_model` nije izvor istine za model** — model je hardkodiran u ruti. Registar za `copilot` kaže `gpt-4o`, kod koristi `gpt-4o-mini` (`copilot.py:133`, `174`, `479`, `696`, `787`, `856`, `916`, `1179`).
- **Digital Twin košta 3× više nego što opis u bazi tvrdi** — migracija 066 opisuje 3 i 1 kredit, migracija 069 postavlja množilac 3; stvarno je 9 i 3.
- **`GET /api/agents/lista` (`multi_agent.py:386`) nema nikakvu autentifikaciju** — nijedan `Depends`.
- **Naplata je testirana na jednom jedinom mestu** — `test_sprint6g_copilot_billing_gate.py`.

---

## 4. STRATEGIJA

| Sposobnost | Gde (fajl:linija / ruta) | Test | Status | Šta radi (jezikom advokata) |
|---|---|---|---|---|
| Red Team — napad na sopstveni predmet | `routers/strategija.py:235` → `POST /strategija/red-team` (perm `strategija`); prompt `strategija.py:25-123`, 5 varijanti po vrsti postupka; FE `vindex.js:2961` + poziv `:3169` | `test_wave9_strategy_context.py::test_a_sopstveni_predmet_id_dovodi_kanonski_kontekst[red_team]` | `PRODUCTION` | Napada vaš predmet iz uloge protivničkog advokata. Slobodan tekst — nijedan broj se ne računa u pozadini. |
| Simulacija parnice | `routers/strategija.py:283`; prompt `strategija.py:124-150`; FE `vindex.js:2968` + `:3169` | `test_wave9_strategy_context.py::test_e_predmet_a_i_predmet_b_daju_razlicit_kontekst` | `PRODUCTION` | Daje „verovatnoća uspeha X%" i preporuku TUŽBA / ODBRANA / NAGODBA. **Procenat piše model u prozi; server ga ne proverava.** |
| AI Sudija — neutralna ocena | `routers/strategija.py:323`; prompt `strategija.py:151-166`; FE `vindex.js:2975` + `:3169` | `test_wave9_strategy_context.py::test_c2_tudji_sadrzaj_ne_procuri_ni_u_jedan_prompt` | `PRODUCTION` | „Preliminarni stav: TUŽBA OSNOVANA / NEOSNOVANA / NEDOVOLJNO PODATAKA". Slobodan tekst, bez serverske provere. |
| Pregled ugovora uz zakon | `routers/strategija.py:378`; zakoni iz baze `:363` (`_fetch_zakon_ctx`); prompt `strategija.py:167-217`; FE `vindex.js:2982` + `:3169` | `test_wave9_strategy_context.py::test_p3_poreklo_ostaje_razlucivo` | `PRODUCTION` | Pregleda nalepljeni ugovor uz stvarne zakonske odredbe iz baze; vraća kritične i srednje rizike + ocenu BEZBEDAN / RIZIČAN / NEPRIHVATLJIV. |
| Pravni revizor nacrta | `routers/strategija.py:423`; prompt `strategija.py:378-397`; FE `vindex.js:2989` + `:3169` | `test_wave9_strategy_context.py::test_p4_kod_predmet_primarnih_modula_nema_dopunskog_uvoda` | `PRODUCTION` | Recenzira vaš nacrt i predlaže konkretne izmenjene formulacije. |
| Analiza iskaza svedoka | `routers/strategija.py:466`; prompt `strategija.py:433-458`; FE `vindex.js:2996` + `:3169` | `test_wave9_strategy_context.py::test_s_case_context_blok_je_KEYWORD_ONLY` | `PRODUCTION` | Traži unutrašnje protivrečnosti u iskazu i generiše pitanja za unakrsno ispitivanje. |
| Simulirana rasprava (tužilac → branilac → presuda) | `routers/strategija.py:509`; motor `strategija.py:541` (3 uzastopna GPT-4o poziva); FE `vindex.js:3004` + `:3169` | `test_wave9_strategy_context.py::test_n_nema_nedefinisanih_imena` | `PRODUCTION` | Simulira raspravu i „presudu". **Vraća čist tekst bez ograničenja vrednosti** — vidi upozorenje ispod. |
| **Kompletna analiza (orkestrator, 6 koraka)** | `routers/strategija.py:601` (6 kredita, HTTP 202 + praćenje posla); motor `strategija.py:793` (8 GPT poziva); FE `vindex.js:3739` | `test_strategija_sistemsko_upozorenje.py` (9 testova), `test_singlebrain2_readiness_unification.py`, `test_singlebrain2_phase4_chaos.py` | `PRODUCTION` | Lančano: Revizor → Due Diligence → Svedok → Red Team → Sudija v2 → Sinteza, pa jedna preporuka. |
| **Ograničenje AI verdikta** | `strategija.py:963-973` — procena uspeha se seče na 0–100, izreka na trovrednosni šifrarnik sa sigurnosnim padom, pouzdanost na VISOKA/SREDNJA/NISKA sa padom na NISKA | `test_singlebrain2_readiness_unification.py:245` (otrovan odgovor 9999 → 100), `test_singlebrain2_phase4_chaos.py:115` (−9999 → 0..100) | `PRODUCTION` — **samo unutar orkestratora** | Serverski ograničava „verdikt" pre nego što stigne do advokata. |
| **Sistemsko upozorenje i detekcija protivrečnosti** | `strategija.py:1006-1050` i `:1052-1090` — pravilo „≥2 koraka NISKA" i kategorički sudari se **računaju u kodu**, ne u promptu; tehnička greška se broji odvojeno od pravne nesigurnosti | `test_strategija_sistemsko_upozorenje.py::test_orkestrator_sistemsko_upozorenje_racuna_se_deterministicki_ne_llm`, `::test_orkestrator_json_parse_greska_se_ne_broji_kao_stvarna_niska_pouzdanost` | `PRODUCTION` | Kad je analiza sama sebi nesigurna ili sebi protivreči, sistem to sam prijavi — ne oslanja se na to da će model priznati. |
| Napomena o poreklu uz svaki odgovor | `routers/strategija.py:107` `_advisory_provenance` — tekst zavisi od toga da li je kanonski kontekst stvarno učitan | `test_tau003_decision_boundary.py::test_all_9_strategija_endpoints_attach_ai_advisory_provenance` | `PRODUCTION` | Uz svaki odgovor stoji da je reč o AI proceni, ne o izračunatoj statistici, i da li je analiza gledala pravi spis. |
| Provera vlasništva pre svega ostalog | `routers/strategija.py:193` `_gate_i_kontekst` (7 modula) i `:640-644` (orkestrator, pre naplate) | `test_wave9_strategy_context.py::test_c_tudji_predmet_id_daje_404_bez_posla_i_bez_naplate`, `::test_b2_bez_predmet_id_ne_dodiruje_bazu` | `PRODUCTION` | Tuđi predmet daje 404 pre ijednog upita u bazu, pre AI poziva i pre naplate. |
| Provera kredita pre skupe analize | `routers/strategija.py:672-706` | posredno `test_phoenix_mission_004_financial_credit_gating.py` | `PRODUCTION` | Sprečava da korisnik sa 0 kredita pokrene 8 GPT poziva pa dobije grešku. |
| Motor „šta nedostaje" | `shared/gap_engine.py:58-230`; potrošači `shared/case_context.py:85`, `routers/copilot.py:516/546/723`, `services/case_evolution.py:868` | `test_sigma_sprint003_gap_engine.py::test_collect_case_gaps_aggregates_all_three_sources`, `::test_gaps_from_genome_nedostaje_is_always_a_hypothesis` | `PRODUCTION` (biblioteka, kroz Copilot i kontekst predmeta) | Jedno mesto spaja „šta nedostaje" iz tri izvora i svaku AI-izvedenu prazninu obavezno označava kao **hipotezu**, ne činjenicu. |
| Strategija V2 (strukturisan JSON) | `routers/strategija.py:862` → `POST /strategija/v2/analiza` | `test_wave9_strategy_context.py::test_v2_a_kontekst_stize_u_doslovan_prompt`, `test_tau003_decision_boundary.py::test_v2_system_prompt_no_longer_presents_procenat_as_calculated_stat` | `IMPLEMENTED_UNWIRED` | Vraća sirov model-JSON **bez ijednog ograničenja vrednosti** (`strategija.py:944`). |
| Simulator strategije („šahovska partija") | `routers/strategy_simulator.py:204`, `:363`, `:479`, `:510` (2 kredita) | `test_strategy_simulator_audit.py::test_genome_verzija_matches_snapshot_used_for_simulation`, `::test_no_audit_on_gpt_failure` | `IMPLEMENTED_UNWIRED` | Partija poteza protiv protivničkog advokata. Registrovan u `api.py:761`, UI ga ne otvara. |
| Case Commander (5 ruta, 1056 linija) | `routers/case_commander.py:360`, `:450`, `:505`, `:904`, `:1034` | `test_tau007_case_commander_consolidation.py::test_gpt_advisory_cannot_override_canonical_readiness`, `test_sigma_sprint005_commander_consolidation.py::test_gpt_advisory_field_never_carries_evidence` | `IMPLEMENTED_UNWIRED` | Najzreliji „platforma računa, model samo obrazlaže" dizajn u repou — i potpuno nedostupan. Jedini pomen u frontendu je komentar `vindex.js:1301`. |

### Upozorenje o granici „AI ne presuđuje"

Ograničenje verdikta postoji **samo u orkestratoru** (`/strategija/kompletna-analiza`). Samostalne rute `/strategija/sudija-v2`, `/strategija/litigation` i `/strategija/sudija` vraćaju slobodan tekst bez serverske provere, a promptovi izričito traže formulacije tipa „Tužba se USVAJA / DELIMIČNO USVAJA / ODBIJA" i „ko je pobedio". Jedina ograda na tim rutama je tekstualna napomena o poreklu.

**Sajt ne sme da tvrdi da platforma sprečava AI da presuđuje — to važi za jednu od četiri putanje.**

---

## 5. IZRADA NACRTA

| Sposobnost | Gde (fajl:linija / ruta) | Test | Status | Šta radi (jezikom advokata) |
|---|---|---|---|---|
| Spisak vrsta dokumenata | `routers/drafting.py:504` → `GET /api/nacrt/types`; izvor `drafting/templates.py:1363` (18 šablona); FE `vindex.js:6155` | `test_drafting_p42_p43.py::test_get_types_list_sadrzi_sve_expected_tipove`, `test_drafting_p46.py::test_ukupno_tipova` | `PRODUCTION` | Puni izbor vrsta dokumenata. |
| Spisak sudova | `routers/drafting.py:510` → `GET /api/courts`; FE `vindex.js:6180` | bez testa | `PRODUCTION` | Naziv i adresa suda za zaglavlje podneska. |
| **Brzi nacrt — 18 vrsta** | `routers/drafting.py:597` → `POST /api/nacrt` (perm `drafting`); motor `drafting/router.py:465`; šabloni `drafting/templates.py:1162`; FE `vindex.js:7560` + `:7629` | `test_phoenix_mission_010_drafting_rag_grounding.py::test_generate_draft_calls_retrieve_documents_when_available`, `test_sprint6i_nacrt_authorization_error.py::test_1_cross_user_returns_404_not_500` | `PRODUCTION` | Ugovor o radu (određeno/neodređeno), aneks, sporazumni raskid, punomoćje, žalba na presudu, žalba na rešenje, tužba za naknadu štete, tužba u radnom sporu, opomena dužniku, zahtev poslodavcu, obaveštenje o otkazu, kupoprodaja, zakup, prigovor na platni nalog, predlog za privremenu meru, tužba za razvod, krivična prijava. |
| **Puni podnesak (ekstrakcija → izvori → obogaćivanje → kritika) — 12 vrsta** | `routers/drafting.py:820` → `POST /api/podnesak` (perm `drafting`); šabloni `templates/podnesci.py:12` i `:28-860`; FE `vindex.js:7560` + `:7629` | `test_templates_podnesci.py` (39 testova), `test_sprint6c1_drafting_authorization.py::test_podnesak_authorizes_before_generating`, `test_sprint6c2_podnesak_binding.py::test_b_cross_user_reaches_no_provider_call` | `PRODUCTION` (uz ogradu ispod) | Tužba za naknadu štete, žalba parnična, predlog za izvršenje, tužba u radnom sporu, tužba za razvod, prigovor na platni nalog, krivična prijava, predlog za privremenu meru, odgovor na tužbu, žalba krivična, urgencija sudu, prigovor na rešenje o izvršenju. |
| Iz čega se nacrt piše | `routers/drafting.py:948-956` (zakoni i praksa iz baze) + `drafting/router.py:504`; VKS kriterijumi `routers/drafting.py:960-967`; stil kancelarije `drafting/playbook.py:92` | `test_faza3_drafting_engine_2026_07_24.py::test_izvori_kontekst_oznacava_dokumente`, `test_phoenix_mission_010_drafting_rag_grounding.py::test_generate_draft_skips_retrieval_when_rag_unavailable` | `PRODUCTION` | Iz vašeg opisa, zakonskih odredaba i prakse iz baze, VKS orijentacionih kriterijuma i izabranog suda. **Dokumenti iz predmeta ne ulaze** — vidi ogradu. |
| **Obavezno označavanje izvora `[IZVOR-n]`** | `shared/drafting_grounding.py:17` — koriste ga oba puta; pravilo u promptu `templates/podnesci.py:1465` | `test_faza3_drafting_engine_2026_07_24.py::test_svi_obogacivanje_promptovi_imaju_izvor_pravilo`, `test_phoenix_mission_010_drafting_rag_grounding.py::test_both_drafting_surfaces_import_the_same_izvori_kontekst` | `PRODUCTION` | Svaki citat člana mora nositi oznaku izvora iz kog je stvarno došao; dodela oznake navodu koji taj izvor ne potkrepljuje izričito je zabranjena. |
| **Kritički prolaz protiv izmišljenih citata** | `shared/drafting_grounding.py:31` `CRITIQUE_SYSTEM`; primena `routers/drafting.py:459` i `drafting/router.py:421` | `test_faza3_drafting_engine_2026_07_24.py::test_critique_ispravlja_halucinaciju`, `::test_critique_fallback_na_original_ako_poziv_ne_uspe`, `test_phoenix_mission_010_drafting_rag_grounding.py::test_generate_draft_critique_neutralizes_hallucinated_article_number` | `PRODUCTION` | Drugi prolaz proverava izmišljene članove i obavezne formalne elemente; **izmišljen broj člana se zamenjuje oznakom `[proveriti relevantan član]`, nikad drugim brojem**. |
| Obavezna napomena uz svaki nacrt | `templates/podnesci.py` (12 mesta), `drafting/templates.py` (12 mesta) | `test_templates_podnesci.py::test_napomena_sistema_u_outputu` | `PRODUCTION` | „NAPOMENA SISTEMA: … mora biti pregledan od strane ovlašćenog advokata pre podnošenja sudu." |
| Pravila petituma i stila | `templates/podnesci.py:1478`, `:1494`, primena `:1512` | `test_templates_podnesci.py::test_tuzba_razvod_uslovni_petitum_bez_dece`, `::test_predlog_privremena_mera_fumus_i_periculum` | `PRODUCTION` | Traži izvršan petitum sa tačnim iznosom, rokom i kamatom; zabranjuje nejasne alternativne zahteve. |
| Provera usklađenosti sa Zakonom o radu | `drafting/compliance.py:257`, poziv `drafting/router.py:542`; granice `:16-24` | `tests/unit/test_drafting.py` | `PRODUCTION` (ugovori o radu na `/api/nacrt`) | Bez AI, deterministički: upozorava da probni rad preko 6 meseci, konkurentska klauzula preko 2 godine ili godišnji ispod 20 dana krše zakon. |
| Provera kompletnosti pre generisanja | `routers/drafting.py:1031`; motor `nacrti/checklist_engine.py`, konfiguracija `nacrti/checklist_config.py:32`; FE `vindex.js:7600` | `test_nacrti_checklist.py::test_tuzba_naknada_stete_sve_pokriveno`, `test_checklist_config.py` | `PRODUCTION` | Pre generisanja proverava jesu li navedeni obavezni elementi i traži potvrdu ako kritični nedostaju (upozorenje, ne blokada). |
| Stil kancelarije | `routers/drafting.py:517`, `:569`, `:578`; motor `drafting/playbook.py:52/92/115` (odvojen prostor po korisniku); FE `vindex.js:4315`, `4349`, `4282` | bez testa | `PRODUCTION` | Advokat otpremi svoje ranije podneske; nacrti se pišu u stilu te kancelarije. |
| Izvoz nacrta u Word (sa memorandumom) | `routers/drafting.py:1166`; generator `:1066`; FE `vindex.js:22694` | **bez testa** | `PRODUCTION` | Preuzimanje kao .docx sa podacima kancelarije u zaglavlju. |
| Izvoz proizvoljnog teksta u Word | `routers/export.py:37`; `docx_export.py`; FE `vindex.js:4034` | **bez testa** | `PRODUCTION` | Bilo koja analiza se izvozi u .docx. |
| Izvoz predmeta u PDF | `routers/export.py:162`; generator `predmet_pdf.py:121`; FE `vindex.js:12479` | `test_predmet_pdf.py` | `PRODUCTION` | Ceo predmet (dokumenti, beleške, hronologija) kao PDF izveštaj. |
| Analiza dokumenta / sažimanje / ocena odgovora | `routers/drafting.py:692`, `:747`, `:796`; FE `vindex.js:7579`, `7149`, `7972`/`8221` | `test_sprint6m_drafting_billing_http_exception.py` | `PRODUCTION` | — |
| Odobravanje nacrta pre ulaska u memoriju kancelarije | `routers/drafting.py:245`, `:1212`, `:1228`, `:1310`; FE `vindex.js:21939`, `21981`, `21998` | `test_institutional_memory_v2.py`, `test_phoenix_mission_015_low_severity_sweep.py` | `IMPLEMENTED_UNWIRED` u praksi — ekran postoji, ali proizvođač nikad ne opali | Nacrt bi prvo išao u čekaonicu; tek po odobrenju ulazi u memoriju kancelarije. |
| Provera stila pisanja advokata | `routers/style_checker.py:98`, `:155`, `:177`, `:258`, `:279`, `:302`, `:349`; registrovan `api.py:765` | **bez testa** | `IMPLEMENTED_UNWIRED` | 18 KB modula koji gradi profil pisanja, ocenjuje nacrt i prati evoluciju stila — nijedan ekran ga ne otvara. |

### Ograde koje sajt mora da poštuje

1. **6 od 12 tipova podneska tiho zaobilazi bogati postupak.** `vindex.js:6155` učita svih 18 ključeva iz `drafting/templates.py`; šest ključeva postoji u oba rečnika (`tuzba_naknada_stete`, `tuzba_radni_spor`, `tuzba_razvod`, `prigovor_platni_nalog`, `krivicna_prijava`, `predlog_privremena_mera`), pa ih grana na `vindex.js:7560` šalje na jednostavni `/api/nacrt` umesto na `/api/podnesak`. Na pun postupak stižu samo `zalba_parnicna`, `predlog_izvrsenje`, `odgovor_na_tuzbu`, `zalba_krivicna`, `urgencija_sudu`, `prigovor_izvrsenje`. Dodatno je zavisno od trke — dok se lista ne učita, poziv ide na `/api/podnesak`.
2. **Nacrt se nikad ne piše nad dokumentima predmeta.** Telo zahteva na `vindex.js:7583-7589` je `{vrsta, tip, opis, sud_naziv, sud_adresa}` — `predmet_id` se ne šalje nikad. Pošto se `_stage_draft_for_review` poziva samo kad `predmet_id` postoji, cela institucionalna memorija nacrta je u praksi prazna, a ekran za odobravanje uvek vidi praznu listu.
3. **`/api/doc-templates/generisi` je jedini put izrade dokumenta bez ijedne ograde** — sedam šablona u `routers/doc_templates.py:66-135` idu direktno u model: bez izvora, bez `[IZVOR-n]` pravila, bez kritičkog prolaza i bez obavezne napomene koju svih 30 ostalih šablona nose. Ožičen je i naplaćuje se.
4. **Bez testa na izvoznim putanjama**: `POST /api/nacrti/export/docx` (ubacuje podatke firme), `POST /export/docx`, ceo `drafting/playbook.py`, `GET /api/courts`, `POST /api/sazmi`, `POST /api/feedback`.

---

## 6. PRETRAGA

Vektorski indeks: `vindex-ai`, dimenzija 3072, model `text-embedding-3-large` (`app/services/retrieve.py:70-71`).

| Sposobnost | Gde (fajl:linija / ruta) | Test | Status | Šta radi (jezikom advokata) |
|---|---|---|---|---|
| Pretraga po celoj kartoteci | `routers/search.py:232` → `GET /api/search`; FE `vindex.js:13297` (⌘K), `16814` | `test_search.py::test_search_200` (+26 funkcija), `test_lz003_search_extension.py` | `PRODUCTION` | Traži tekst kroz predmete, klijente, dokumente, račune, hronologiju, beleške i zadatke. **Traži „sadrži reč", ne po smislu.** |
| Pretraga zakona po smislu | `app/services/retrieve.py:891` `_semanticka_pretraga`, prostor `zakoni_rs` (`:746`); izloženo kroz `api.py:3059` → `main.py:3227`; FE `vindex.js:7579`, `10602` | `test_faza1_bugfixes_2026_07_24.py`, `test_a6_fixes.py::TestRetrieveDocumentsA6Integration` | `PRODUCTION` | Nađe članove zakona po smislu pitanja, ne po ključnoj reči. |
| Direktan dohvat navedenog člana | `retrieve.py:992` `_direktan_fetch_clana`; prepoznavanje `:693` | `test_a6_fixes.py::TestDirektanFetchClana` (7 funkcija) | `PRODUCTION` | Kad advokat navede „član 175", sistem ga povuče doslovno umesto da nagađa. |
| Sudska praksa u AI odgovoru | `retrieve.py:939`, prostor `sudska_praksa` (`:749`); poziv `main.py:3267` | `test_c7a_praksa.py::test_t1_retrieve_sudska_praksa_returns_metadata` (+16) | `PRODUCTION` | Uz odgovor priloži relevantne presude iz baze odluka. |
| Mišljenja ministarstava | `retrieve.py:923`, prostor `misljenja` (`:752`), prag `:758` | **bez testa** | `PRODUCTION` | Uz odgovor priloži zvanična tumačenja ministarstava. |
| Katalog sudske prakse sa filterima | `routers/praksa.py:529` → `POST /api/praksa/search`; FE `vindex.js:8443`, `8477` | **bez testa** (glavna ruta pretrage prakse) | `PRODUCTION` | Pretraga presuda po sudu, oblasti i godini, grupisano po broju odluke. |
| Rezervno rangiranje po ključnim rečima | `praksa.py:134` `_keyword_fallback_sync` | **bez testa** | `PRODUCTION` | Kad semantika ne pogodi, prebroji ključne reči i preuredi rezultate. |
| Praksa grupisana po ishodu spora | `praksa.py:659` → `retrieve.py:2635`; FE `vindex.js:8699` | `test_celina1_praksa_rag_2026_07_24.py` (samo grana greške) | `PRODUCTION` | Pokaže koliko je sličnih sporova dobio tužilac, a koliko tuženi. |
| Ključni pravni stav iz presude | `praksa.py:569` → `POST /api/praksa/ratio`; FE `vindex.js:8645`, `8811` | `test_celina1_praksa_rag_2026_07_24.py::test_praksa_ratio_api_retry_na_rate_limit` | `PRODUCTION` | Izvuče suštinu presude u tri rečenice. |
| Poređenje dve odluke | `praksa.py:600`; FE `vindex.js:8593` | `test_celina1_praksa_rag_2026_07_24.py::test_praksa_uporedi_api_retry_na_rate_limit` | `PRODUCTION` | Uporedi dve presude i pokaže gde se sudovi razilaze. |
| Mreža predmeta (Knowledge Graph) | `routers/knowledge_graph.py:20`, dohvat prakse `:158-187`; FE `vindex.js:19620` | `test_knowledge_graph.py` (7) | `PRODUCTION` | Nacrta mrežu: stranke, dokumenti, ročišta, zakoni + 3 relevantne presude. |
| Pitanje nad otpremljenim dokumentom | `routers/dokument.py:404` → `main.py:3227` sa privremenim prostorom; FE `vindex.js:8942` | `test_doc_retrieval.py` (4) — **jedna asercija je mrtva**, `:116` `assert ... or True` | `PRODUCTION` | Pitanje o konkretnom otpremljenom ugovoru ili presudi. |
| Indeksiranje otpremljenog dokumenta (privremeno) | `dokument.py:219`, prostor `tmp_{sid}`, rok 24h; FE `vindex.js:8891`, `21032` | `test_uploaded_doc_ingest.py` (4), `test_uploaded_doc_api.py` (8), `test_uploaded_doc_cleanup.py` (4) | `PRODUCTION` | Otpremi dokument, iseca ga i indeksira za analizu. |
| Indeksiranje predmetnih dokumenata (trajno) | `api.py:4715`, `:4757`, `:4891` → `kancelarija_{id}` / `user_{id}` | `test_institutional_rag_upgrade.py` | `PRODUCTION` | Dokument iz predmeta trajno ulazi u memoriju kancelarije. |
| Pretraga memorije kancelarije | `retrieve.py:1847-1852`; **jedini pozivalac** `api.py:5124` | `test_institutional_rag_upgrade.py` | `PRODUCTION`, **ali usko** | Dostupno samo u auto-analizi pri uploadu — **ne** u glavnom `/api/pitanje`. |
| Interni pravni stavovi kancelarije | `routers/interni.py:42`, prostor `interni_stavovi_{uid}`; FE `vindex.js:4394` | bez testa | `PRODUCTION` | Pretraga sopstvenih pravnih stavova po smislu. |
| Propisi o digitalnoj imovini | `routers/web3.py:60`, prostor `web3_zdi_mca`; FE `vindex.js:5001` | bez testa | `PRODUCTION` | Pretraga propisa o digitalnoj imovini. |
| Prerangiranje rezultata modelom | `retrieve.py:1293` `_gpt_rerank` (stvarni podrazumevani) | `test_gpt_reranker.py` (12) | `PRODUCTION` | Model prerangira nađene odlomke po stvarnoj relevantnosti. |
| Prerangiranje spoljnim servisom (Cohere) | `retrieve.py:1359`; kapija `:532` traži `VINDEX_COHERE_RERANK` + ključ, **podrazumevano isključeno** (`:533`) | `test_gpt_reranker.py`, `test_celina1_praksa_rag_2026_07_24.py` | `EXPERIMENTAL` (isključeno) | — |
| Razbijanje složenog pitanja | `retrieve.py:1036` `_dekomponuj_query` (poziv `:1857`), `:1184` `decompose_query`, `:1134` `classify_query_intent` | pojavljuje se samo kao meta za `patch()`; `classify_query_intent` **bez testa** | `PRODUCTION` | Složeno pitanje razbije na 2–3 podpitanja. |
| Hipotetički odgovor kao upit (HyDE) | `retrieve.py:1261`; pozivi `:1871`, `:1891` | samo kao meta za `patch()` | `PRODUCTION` | Napiše zamišljen odgovor pa njime traži prave članove. |
| Samokorekcija pretrage (CRAG) | `retrieve.py:2265` `_crag_petlja`, `:1423`, `:1468` | **bez ijednog testa** | `PRODUCTION` | Ako prvi rezultati nisu dobri, sistem sam proširi pretragu. |
| Prikaz izvora ispod odgovora | `retrieve.py:822` `_build_izvori` → `main.py:3258` → `api.py:1438` → FE `vindex.js:924`, poziv `:7760` | bez direktnog testa | `PRODUCTION` | Ispod odgovora piše naziv zakona i član na kojima počiva. |
| **Zabrana izmišljenih članova** | `main.py:729` `_proveri_halucinaciju`; pozivi `:2858`, `:3656` | `test_c7a_praksa.py::test_t6_guard_*` (3) | `PRODUCTION` | Svaki citiran član **mora** postojati u dohvaćenom tekstu, inače se odgovor blokira. |
| **Zabrana izmišljenih presuda** | `main.py:2865-2887`; ekstraktor `:811` | `test_c7a_praksa.py::test_t6_guard_blocks_fabricated_praksa` | `PRODUCTION` | Broj presude mora postojati u priloženom kontekstu. |
| Zaštita od promašene teme | `main.py:866` `_proveri_tematsku_relevantnost` | bez testa | `PRODUCTION` | Ako je pitanje o krađi a citiran član o oružju, odgovor se degradira. |
| Prednost zvaničnih izvora | `shared/vector_origin.py:35`, `:73`; primena `retrieve.py:2133-2145` | `test_institutional_memory_v2.py` (samo `freshness_weight`) | `PRODUCTION` | Zakon i presuda vrede više od klijentovog dokumenta; stariji dokumenti gube na težini. |
| Unos zakona u indeks (administrator) | `routers/law_upload.py:173`, prostor `zakoni_rs` (`:92`); FE `vindex.js:15143`, `15175`, `15199` | **bez testa** | `PRODUCTION` (founder-only) | Administrator dodaje novi zakon u pravnu bazu. |
| Otkrivanje novih biltena sudova | `batch_ingest.py:312`, `:346`; FE `vindex.js:15214`, `15250` | `test_batch_ingest.py` | `PRODUCTION` (founder-only) | Administrator vidi koji novi bilteni postoje. |
| Sečenje zakona na članove | `semantic_chunker.py:153` | **ceo modul bez ijednog testa** | `PRODUCTION` (van aplikacije) | Priprema zakona za indeksiranje. |
| Sečenje presuda na izreku i obrazloženje | `chunker_case_law.py:244` | `test_chunker_case_law.py` (6, bez mokova) | `PRODUCTION` (van aplikacije) | Priprema presuda za indeksiranje. |
| Slični predmeti iz sudske prakse | `praksa.py:916` → `POST /api/praksa/slicni-predmeti` | `test_slicni_predmeti.py` (13, od toga 4 prolaze prazno) | `IMPLEMENTED_UNWIRED` | Iz opisa činjenica našao bi presude sa sličnim činjeničnim stanjem. |
| Mapa argumenata iz prakse | `praksa.py:721` → `POST /api/praksa/argument-map` | bez testa | `IMPLEMENTED_UNWIRED` | Za dati argument našao bi presude koje ga podržavaju i koje ga obaraju. |
| Lična baza znanja (5 ruta) | `routers/knowledge_base.py:206` i ostale, prostor `kb_{uid}` | bez testa | `IMPLEMENTED_UNWIRED` | Čuvanje i semantička pretraga sopstvenih beleški. |
| Masovni uvoz presuda | `routers/batch_ingest.py:188`, `:235`, `:252` | `test_batch_ingest.py` (28) | `IMPLEMENTED_UNWIRED` | Masovno dodavanje presuda u bazu. |
| Lista sudova iz korpusa | `praksa.py:625` → `GET /api/praksa/sudovi` | bez testa | `IMPLEMENTED_UNWIRED` | Frontend zove **drugu** rutu — `/api/courts` (`drafting.py:510`). |
| Objašnjenje „zašto baš ovaj izvor" | `retrieve.py:843` `_build_match_breakdown`, upis u meta `:2225` | bez testa | `DEAD` | Računa se pri **svakom** pretraživanju i nema nijednog potrošača — ni `main.py`, ni `api.py`, ni frontend. |
| Privatna baza firme u `/api/pitanje` | `api.py:1248` `_get_firma_namespace` → `:3161`; vraća `firm_{16hex}` (migracija `045:29`) | — | `DEAD` | **Nijedan upis u celom repou ne piše u `firm_*` prostor.** Glavni AI put pretražuje prazan prostor. **Provereno nezavisno.** |
| Upravna praksa | `praksa.py:424`, `api.py:4408` čitaju prostor `upravna_praksa` | — | `DEAD` | Čita se, ali ga niko ne puni. |
| Hibridna pretraga (BM25 / sparse) | — | — | **NE POSTOJI** | Nula pogodaka za `bm25`/`sparse`/`hybrid`. Najbliže je rezervno rangiranje po ključnim rečima. |

### Šta je dokazivo indeksirano

Brojevi ispod su navedeni **sa izvorom tvrdnje u repou**. Nijedan nije proveren protiv produkcije.

| Prostor | Vektora | Izvor tvrdnje | Pouzdanost |
|---|---|---|---|
| `zakoni_rs` (zakoni) | 25.822 | commit `64465a42` (2026-07-13), poruka o preimenovanju bezimenog prostora uz kopiranje i proveru pre brisanja | Tvrdnja iz commit poruke, ne merenje posle migracije |
| `sudska_praksa` | 116.494 → 270.364 | `data/pinecone_baseline_2026-07-13.json:37-40`; `data/ingest_all_log_3.txt:3` | Izmereno, ali **konačna cifra ne postoji u repou** |
| `misljenja` | 74 | `data/pinecone_baseline_2026-07-13.json:13-16` | Izmereno |
| `web3_zdi_mca` | 479 | isti fajl, `:49-52` | Izmereno |
| `carf_dac8` | 17 | isti fajl, `:25-28` | Izmereno |

**Zakoni — 30 imenovanih**, sa brojem vektora po zakonu u `docs/INDEX_EXPANSION_LOG.md`: ZOO (1.092 čl. → 2.238 vektora), ZPD (677 → 2.247), ZKP (608 → 1.866), ZIO (538 → 1.399), ZPP (493 → 1.084), PZ (355 → 851), ZZP (195 → 876), ZSPNFT (137 → 884), ZR (288 → 694), ZOUP (217 → 700), ZDI (146 → 664), ZZPL (102 → 593), ZVP (235 → 549), ZPDG (151 → 535), Ustav (203 → 474), ZN (240 → 341), ZUS (78 → 161), plus talas iz juna 2026: ZBSN, ZPIG, ZJN, ZPRK, ZSTEC, ZOS, ZASP, ZDF, ZOA, ZPPI, ZH, ZRDS. Nezavisna potvrda po zakonu: `diag_corpus_audit_post_implementation.json` (29 zakona sa `has_vectors: true`).

**Sudska praksa — 17 registrovanih izvora** (`scripts/ingest_all_sources.py:15-40`): ESLJP, Ustavni sud, Komisija za zaštitu konkurencije, Agencija za sprečavanje korupcije, portal sudskapraksa.sud.rs, VKS, Poverenik za ravnopravnost, Parlament, Ministarstvo finansija, ombudsman APV, Zaštitnik građana, apelacioni bilteni i dr.

### Šta se NE sme tvrditi bez provere produkcije

1. **Konačan broj vektora u sudskoj praksi nije poznat.** `data/ingest_all_log.txt` beleži finalni izveštaj „3 OK, **13 GREŠAKA**", a `ingest_all_log_3.txt` dva tvrda zida: prekoračenje skladišta od 2 GB i mesečnog limita upisa. Uvoz portala je stao na 21.000 od 73.078 odluka. Poslednji izmeren broj je 270.364; koliko je stvarno završilo — nema zapisa.
2. **Ne postoji post-migracioni snimak** koji bi potvrdio da je `zakoni_rs` kompletan sa 25.822 vektora.
3. **Skripte za uvoz zakona i dalje pišu u stari, napušteni prostor.** `ingest_laws.py:297` poziva `index.upsert(vectors=vectors)` **bez `namespace=`** (dakle u `__default__`), a pretraga čita `zakoni_rs`. **Provereno nezavisno.** Ponovno pokretanje danas dalo bi vektore koje pretraga nikad ne vidi.
4. **Advokat koji postavi pitanje kroz `/api/pitanje` nikad ne dobija sadržaj iz ranijih predmeta svoje kancelarije** — memorija kancelarije se pretražuje samo u auto-analizi pri uploadu.
5. **„Slični predmeti" postoje u tri nezavisne implementacije** (`praksa.py:916`, `learning.py:427`, `precedenti.py:47`); prve dve su neožičene, a treća nije semantička.
6. **Rangiranje sadrži ručno naštelovane bonuse za pojedinačne članove** (`retrieve.py:1543-1575`: ZOO 200, ZOO 360-395, ZR 189, PZ 171, ZOO 348, KZ 208), naštelovane po test-pitanjima i **bez ijednog testa**.
7. **Najveće rupe u testovima**: funkcija za bodovanje rezultata, petlja samokorekcije, prepoznavanje namere pitanja, mišljenja ministarstava, ceo `semantic_chunker.py` i `POST /api/praksa/search` — glavna produkciona ruta pretrage prakse.

---

## 7. PLATFORMA

| Sposobnost | Gde (fajl:linija / ruta) | Test | Status | Šta radi (jezikom advokata) |
|---|---|---|---|---|
| Registracija naloga | `api.py:2501` → `POST /api/register`; 15 početnih kredita `:2532` | bez testa | `PRODUCTION` | Otvara nalog i odmah vraća pristupni token. |
| Prijava | **Nema backend rute** — klijent zove Supabase direktno: `vindex.js:242`, `:640` | bez testa | `PRODUCTION` | Lozinka se proverava kod Supabase-a; naš server vidi samo gotov token. |
| Provera tokena na svakom pozivu | `shared/deps.py:284` `get_current_user` — **360 mesta**; unutra `_verify_token` `:229` | posredno u ~15 test fajlova | `PRODUCTION` | Na svakom zaštićenom pozivu proverava ko je korisnik. |
| Odjava sa svih uređaja | `api.py:2660` + evidencija `:2675` | bez testa | `PRODUCTION` | Poništava sve sesije. |
| Evidentiranje neuspelih prijava | `shared/deps.py:266`, pozivi `:290`, `:297` | bez testa | `PRODUCTION` | Svaki neuspeh ostavlja trag u nepromenljivoj evidenciji. |
| Zabrana jednokratnih email adresa | `shared/deps.py:114` + `api.py:2509` (49 domena) | bez testa | `PRODUCTION` | Odbija registraciju sa privremenih adresa. |
| Ograničenje istovremenih uređaja | `routers/sesije.py:84`, `151`, `166`, `185`; limit 1 (Basic) / 2 (PRO) `:27-28` | **bez testa** | `PRODUCTION` | Sprečava deljenje jednog naloga između više advokata. |
| **Jedinstvena kapija dozvola** | `shared/permissions.py:128` `PermissionService.require` — **129 mesta** (126 kroz `Depends`, 3 imperativna) nad **58 feature ključeva** | `test_gov2_voice_ws_tier_gate.py`, `test_phantom_ai_charges.py`, `test_rc_beta_flows.py` | `PRODUCTION` | Jedina kapija koja odlučuje da li nalog sme da otvori funkciju: tarifa, dodatak, kill-switch, zavisnosti. |
| **Politika iz baze, ne iz koda** | `shared/feature_registry.py:85` → tabela `feature_registry` (migracija 064, **69 zasejanih funkcija**), keš 60s; menja se `routers/admin_dashboard.py:495` | `test_feature_type.py`, `test_business_groups.py` | `PRODUCTION` | Cene, limiti i minimalna tarifa se menjaju u administraciji, bez izmene koda i bez novog deploy-a. |
| Vlasnik proizvoda ne zaobilazi vlasništvo nad predmetom | `shared/deps.py:60`; `RuntimeError` ako je lista prazna `:35-38` | `test_sec001_predmet_ownership.py::test_founder_status_does_not_bypass_ownership_check` | `PRODUCTION` | Founder prolazi tarifne kapije, ali ne i proveru čiji je predmet. |
| Administratorska konzola zaključana | `routers/admin_dashboard.py:37` `_require_founder` — **17/17 ruta** | `test_business_groups.py`, `test_tier_config.py` | `PRODUCTION` | Provera je u telu svake funkcije, ne kao zavisnost rutera — nova admin ruta bi bila podrazumevano nezaštićena. |
| Licence / mesta u kancelariji | `shared/seats.py:60`, 11 poziva u `routers/kancelarija.py:274-622` | `test_seats.py` (13), `test_kancelarija_seats.py` (10) | `PRODUCTION` | Broji zauzeta mesta, odbija prekoračenje i piše trajan trag u `kancelarija_seat_audit`. |
| **Izolacija podataka po advokatu** | **541 filter `.eq("user_id", ...)` u 88 fajlova** | `test_sec001_predmet_ownership.py` (6), `test_wave11_context_isolation.py` (11), `test_beta_lockdown_zadaci_predmet_idor.py` (4), `test_wave9_collaborator_boundary.py` (5) | `PRODUCTION` | Granica je **po advokatu** i sprovodi se u svakom upitu. |
| Izolacija vektorske baze | `shared/kancelarija_utils.py:45-58` → `kancelarija_{id}` ili `user_{id}` | `test_institutional_memory_v2.py` | `PRODUCTION` | Jedino mesto gde je razdvajanje tvrda pregrada (odvojen prostor u indeksu), a ne uslov u upitu. |
| Deljenje unutar kancelarije | `kancelarija_id` kao filter na **45 mesta u 8 fajlova** | `test_kancelarija_seats.py` | `PRODUCTION` | Postoji samo na uskom skupu: zadaci, memorija firme, tokovi rada, delegiranje. |
| **Atomsko skidanje kredita** | `shared/deps.py:585` → funkcija u bazi `deduct_n_credits` (migracija 107) | `test_beta_gate_credit_race_postgres.py::test_scenario_C_1_balance_50x1` (+20) — **preskaču se bez lokalnog PostgreSQL-a** | `PRODUCTION` | Jedna naredba skida iznos; dva istovremena zahteva ne mogu oba proći sa istog stanja. |
| Atomski dnevni i mesečni brojači | `shared/usage.py:189` → `increment_feature_usage` (migracija 108), poziv `:556` pre naplate; `shared/deps.py:355` mesečni | `test_atomic_usage_counters_postgres.py::test_concurrent_calls_cannot_exceed_the_daily_limit` (+20) — **isti uslov** | `PRODUCTION` | Dnevni limit se ne može probiti paralelnim zahtevima. |
| Naplata AI potrošnje | `shared/usage.py:432` — **165 poziva u 54 fajla** | `test_usage_multiplier.py`, `test_phantom_ai_charges.py`, `test_beta_gate_credit_race.py` | `PRODUCTION` | Jedino mesto naplate: pauza → dnevni/mesečni limit → skidanje → zapis u dnevnik. |
| Povraćaj kredita kad AI padne | `shared/deps.py:621` → `refund_n_credits` | `test_beta_gate_upload_refund.py`, `test_beta_gate_credit_race_postgres.py::test_deduct_then_compensating_refund_is_net_zero` | `PRODUCTION` | Ako operacija padne posle naplate, kredit se vraća; ako povraćaj ne uspe, radije se ne vrati nego da pokvari stanje. |
| Prikaz kredita korisniku | `api.py:2680` (FE `vindex.js:309`, `350`); `routers/plans.py:46` (FE `vindex.js:2399`) | `test_beta_gate_credits_debug_nondestructive.py` | `PRODUCTION` | Brojač kredita u navigaciji i mesečni pregled po funkciji. |
| **Nepromenljiva evidencija (hash-lanac)** | `shared/audit_immutable.py` — **61 poziv u 30 fajlova** | `test_v34/35/36/36c/36f/37/38/39b/39c/40b/41b_audit_*.py` — **11 fajlova, ~100 test funkcija**, svaki vozi PRAVU rutu i tvrdi „tačno jedan zapis na uspeh, nula na 404/403/409" | `PRODUCTION` | Trajan trag: ko je, kada i nad čim izvršio brisanje ili izmenu (ročišta, zadaci, komentari, fakture, tarife, saradnici, predmeti, klijenti, dokumenti). |
| **Baza fizički odbija izmenu evidencije** | Okidač `trg_protect_audit_immutable` (migracija 043) | `test_rc_migration_gate.py::test_G0_update_reda_audita_dize_izuzetak`, `::test_G0_delete_reda_audita_dize_izuzetak` (protiv živog PostgreSQL-a) | `PRODUCTION` | Izmena i brisanje evidencije nisu mogući — dokaz da zapis nije naknadno menjan. |
| Provera integriteta lanca | `shared/audit_immutable.py::verify_chain_integrity`; `api.py:2174` (founder, 2/min) | `test_celina5_secops_2026_07_24.py` (5) | `PRODUCTION` | Skenira poslednjih 1000 zapisa i javlja da li je lanac prekinut. |
| Dnevni pečat evidencije | `api.py:2203`, `:2214` — `security/chain_anchor.py` | bez testa | `PRODUCTION` (ručno) | Dnevni „pečat" na nezavisnoj lokaciji; pokreće samo vlasnik. |
| **Zaštita AI poziva** | `shared/ai_client.py:566`, pozvano `api.py:28` pre svih router importa; patch na SDK **klasu** | `test_gov3_response_firewall.py`, `test_wave9_governance.py`, `test_gov2_stream_guard_parity.py` | `PRODUCTION` | Svih ~130 mesta koja zovu AI prolazi kroz jednu kapiju; ako se zaštita ne učita, AI se **gasi**. |
| Poreklo AI poziva (forenzika) | `shared/ai_provenance.py:60`, `:77` — **54 poziva u 14 rutera + `api.py`**; upis `security/ai_forensics.py:207` | `test_sprint3_audit_reliability.py` (6) | `PRODUCTION` (na serveru) | Tabela `ai_forensics`: model, tokeni, latencija, hash prompta i odgovora, identifikator zahteva. |
| Prednost zvaničnih izvora u pretrazi | `shared/vector_origin.py:35`, `:73`; primena `app/services/retrieve.py:2133-2145` | `test_institutional_memory_v2.py` | `PRODUCTION` | Zakon i sudska praksa imaju prednost; neoveren AI sadržaj je težinski ugašen. |
| Sledivi identifikator zahteva | `api.py:1027` → zaglavlje `X-Correlation-ID` `:1050` | bez testa | `PRODUCTION` (na serveru) | Jedan zahtev se može pratiti kroz sve sisteme. |
| Izvoz svih podataka (GDPR čl. 20) | `routers/data_export.py:66` → ZIP od 8 JSON fajlova `:88-97`; dugme `index.html:3478` → `vindex.js:803`, `808` | `test_sprint4_silent_failures.py` | `PRODUCTION` | Advokat sam preuzima sve svoje podatke; ako neka tabela ne može da se pročita, ZIP se **odbacuje** umesto da se isporuči nepotpun. |
| Brisanje naloga | `routers/gdpr.py:201`, `_delete()` `:219-228` | `test_gdpr_delete.py` (regresija koja pada ako neko doda kaskadno brisanje) | `PRODUCTION` | **Meko** brisanje: anonimizuje se email i ime; predmeti, klijenti i dokumenti ostaju — namerno, zbog obaveze čuvanja spisa, i to piše u odgovoru `:250-253`. |
| Odjava sa email liste | `routers/gdpr.py:108`, potpisan token `:120` | `test_beta_gate_gdpr_unsub_secret.py` | `PRODUCTION` | Javan link iz email-a, zaštićen potpisom umesto prijavom. |
| Automatsko brisanje starih zapisa | `services/retention_service.py`, pozvano iz dnevnog `api.py:1903` | `test_retention_service.py` | `PRODUCTION` | Periodično briše zapise starije od roka čuvanja. |
| Saglasnost za AI obradu | `routers/tos.py:17`, `:32` → `tos_acceptances.ai_consent` `:46` | bez testa rute | `PRODUCTION` — **fail-open** | Beleži prihvatanje uslova; **na grešku baze vraća „prihvaćeno"** (`:27-28`). |
| Ograničenje broja poziva po IP | `shared/rate.py:107`; `api.py:565`, `:581`; podrazumevano 60/h | `test_sec005_rate_limiting.py`, `test_sec005_failopen_limiter.py`, `test_wave10_rate_limiter_isolation.py` | `PRODUCTION` — **fail-open** | Ako Redis padne, prelazi na brojače u memoriji i u krajnjem slučaju **propušta** zahtev. |
| Ograničenje po korisniku | `api.py:1054`; limiti `:975-976` (AI 60/h, ostalo 600/h) | `test_sec005_rate_limiting.py` | `PRODUCTION` — **fail-open, po radniku** | Brojači su u memoriji procesa (`api.py:970`) → sa N radnika stvarni limit je 60×N. |
| Detekcija neuobičajene aktivnosti | `security/anomaly_detection.py` → `api.py:1095`, `:1114` | bez namenskog testa | `PRODUCTION` — **fail-closed na AI** | Neobičan obrazac gasi AI pozive tom korisniku. |
| Bezbednosna zaglavlja / CSP | `api.py:1131` | `test_api_security.py` | `PRODUCTION` | Standardna zaštita pregledača na svakom odgovoru. |
| Javna stranica statusa | `routers/status_page.py` → `GET /api/status/public`; stranica `static/status.html:83`, servirana `api.py:1516` | bez testa | `PRODUCTION` | Javna stranica dostupnosti servisa. |
| Samoprovera sistema | `routers/proof.py:143`, founder-only `:153`, 10/h | **bez testa** | `EXPERIMENTAL` | Nije korisnička funkcija; pravi stvarni naplativi OpenAI poziv `:99-104` na svaki poziv. |
| Pregled dozvola AI agenata | `security/agent_isolation.py` → `api.py:2191` | bez testa | `EXPERIMENTAL` | Samo pregled — ne sprovodi ništa u toku rada. |
| Drugi GDPR izvoz (uži duplikat) | `routers/gdpr.py:153` (5 tabela) | bez testa | `IMPLEMENTED_UNWIRED` | `vindex.js:837-840` izričito konstatuje da ga niko ne zove. |
| Multi-provajder AI governance | `shared/ai_fabric.py` (672 linije) | `test_ai_fabric_contract.py`, `test_ai_fabric_governance.py` (17 prolazi) | `IMPLEMENTED_UNWIRED` | **Nula produkcionih pozivalaca**, potvrđeno i testom-ugovorom. |
| Zavisnost `require_credits` | `shared/deps.py:657` | bez testa | `IMPLEMENTED_UNWIRED` | Nula `Depends` mesta; sam kod to priznaje na `:693`. |
| Matrica uloga (admin/partner/advokat/pripravnik) | `shared/rbac.py:15-85` | bez testa | `DEAD` | **Nula pozivalaca.** `routers/kancelarija.py:44-47` izričito piše da je namerno ne koristi. Uloga člana se upisuje i prikazuje, ali ne ograničava ništa. |
| RLS politike u bazi | **207 `CREATE POLICY` u 65 migracija**, 176 na `auth.uid()` | `test_rc_migration_gate.py` (samo za tabelu evidencije) | `IMPLEMENTED_UNWIRED` za backend | Aplikacija se povezuje **service ključem** (`shared/deps.py:93`, `api.py:169`) koji RLS zaobilazi po definiciji. RLS je živ samo za 3 tabele kojima pregledač pristupa direktno. |
| 12 RLS politika granice kancelarije | `045:84,140`, `046:44,89,130,171`, `047:61,94,125,163`, `059:33,48` | bez testa | `DEAD` | Traže `status = 'aktivan'`, a `migrations/067_seat_lifecycle.sql:43` je vrednost preimenovao u `'ACTIVE'` — te politike ne pogađaju nijedan red. |
| Deklarisane a nezabeležene radnje | `AUDITABLE_ACTIONS`: `predmet_delete`, `dokument_delete`, `dokument_download`, `login_success`, `password_change`, `2fa_*`, `account_delete`, `admin_access`, `user_role_change`, `api_key_rotation` | konstanta se testira, poziv ne postoji | `DEAD` | Spisak „šta se beleži" obećava više nego što se stvarno beleži. |

### Ograničenja koja sajt ne sme da prećuti

1. **Izolacija podataka ne počiva na bazi nego na kodu.** 207 RLS politika je za backend mrtvo slovo jer se aplikacija povezuje service ključem. Stvarna granica je 541 ručni filter — i ta granica je već tri puta procurela (SEC-001, Beta Lockdown IDOR, Wave 11). Sajt sme da kaže „podaci su razdvojeni po nalogu i to je pokriveno testovima", ali **ne sme da kaže „zaštićeno na nivou baze"**.
2. **„Brisanje naloga" ne poništava prijavu.** `routers/gdpr.py:201-254` menja samo ime i email u profilu. Nema brisanja korisnika ni odjave — korisnik se posle „brisanja" i dalje može prijaviti istim podacima.
3. **Poreklo postoji, ali je korisniku nevidljivo.** `X-Correlation-ID`, `ai_forensics`, oznake porekla izvora — nula pogodaka u `static/vindex.js`. Advokat ne vidi odakle je odgovor došao.
4. **Nema korisničkog pregleda evidencije.** Jedino dugme „Istorija izmena" (`vindex.js:14839`) je founder-only i odnosi se na administraciju.
5. **Najjači dokazi o atomskoj naplati se u praksi ne izvršavaju** — `test_atomic_usage_counters_postgres.py` i `test_beta_gate_credit_race_postgres.py` (~45 funkcija) preskaču se bez lokalnog PostgreSQL-a.
6. **Ograničenje broja poziva je fail-open i po radniku** — deklarisanih 60 AI poziva na sat u praksi je 60×N.
7. **Saglasnost na uslove je fail-open** — ispad baze znači da svi izgledaju kao da su prihvatili.
8. **Evidencijski middleware promašuje naplatu** — `shared/audit.py:19` proverava prefiks `/api/billing`, a ruter je montiran na `/billing`.
9. **Rezervni ključ za proveru tokena je upisan u kod** (`shared/deps.py:126-131`).

---

## 8. KANCELARIJA

| Sposobnost | Gde (fajl:linija / ruta) | Test | Status | Šta radi (jezikom advokata) |
|---|---|---|---|---|
| Kartoteka klijenata — lista i pretraga | `klijenti/router.py:298` → `GET /klijenti`; FE `vindex.js:4507`, `20988`, `22040` | `test_pagination_predmeti_klijenti.py` | `PRODUCTION` | Spisak klijenata sa pretragom po imenu i firmi. |
| Kreiranje i izmena klijenta | `klijenti/router.py:223` POST, `:455` PUT; FE `vindex.js:4846`, `4861` | audit pokriven `test_v39c_audit_bulk_import.py` | `PRODUCTION` | Zavodi fizičko lice ili firmu sa matičnim podacima. |
| Brisanje klijenta uz obavezan trag | `klijenti/router.py:521`; FE `vindex.js:4882` | `test_beta_gate_klijent_delete_audit.py` | `PRODUCTION` | Meko brisanje uz upis u nepromenljivu evidenciju. |
| Zaštita poverljivih podataka (JMBG/PIB) | `klijenti/router.py:368` (`reveal_confidential`); FE `vindex.js:4546`, `4690` | `test_lambda003_klijenti_role_fail_closed.py` | `PRODUCTION` | Dešifruje matične podatke samo ovlašćenim ulogama, uz upis u evidenciju. |
| Vremenska linija klijenta | `klijenti/router.py:1081`; FE `vindex.js:4707` | bez testa | `PRODUCTION` | Hronologija svih događaja po klijentu. |
| Dosije dokumenata klijenta | `klijenti/router.py:894`; FE `vindex.js:4721` | bez testa | `PRODUCTION` | Lista dokumenata vezanih za klijenta (odvojeno od predmeta). |
| Povezivanje klijenta sa predmetom | `api.py:6033`; FE `vindex.js:11281` | `test_mission001_predmet_klijenti.py` | `PRODUCTION` | Jednim klikom vezuje prepoznate klijente iz dokumenta za predmet. |
| **Provera sukoba interesa, 4 sloja** | `routers/conflict_check.py:127` → `POST /api/conflict-check`; FE `vindex.js:19300`, dugme `index.html:2105` | `test_conflict_check.py::test_match_tuzilac_active_conflict`, `::test_only_closed_predmeti_returns_review`, `::test_different_name_returns_clear` (7) + `test_ztc_conflict_check_autowiring.py` | `PRODUCTION` | Pre prihvatanja klijenta pretražuje tužioce i tužene, kartoteku, uloge na predmetima i advokate suprotne strane (ćirilica→latinica, tolerancija na greške u kucanju), uz oznaku „bivši klijent". |
| Provera sukoba u čarobnjaku za prijem | `routers/intake.py:669`; FE `vindex.js:21192` | `test_intake_conflict_check.py` | `PRODUCTION` | Ista provera ugrađena u otvaranje novog predmeta. |
| **Tajmer — pokretanje** | `routers/billing.py:384`; FE `vindex.js:12937` | `test_billing_timer_race.py::test_timer_start_no_existing_active_timer_succeeds`, `::test_timer_start_existing_recent_active_timer_returns_409`, `::test_timer_start_race_conflict_on_insert_returns_409_not_500` | `PRODUCTION` | Startuje merenje vremena na predmetu; sprečava dva tajmera odjednom. |
| Tajmer — zaustavljanje i prikaz aktivnog | `routers/billing.py:438`, `:485`; FE `vindex.js:12955`, `12824` | bez testa | `PRODUCTION` | Zaustavlja merenje i pravi obračunsku stavku. |
| Brzi tajmer bez predmeta | FE `vindex.js:11079-11144` → `POST /billing/entries` | bez testa | `PRODUCTION` | Odbrojavanje u pretražnoj traci; na kraju upisuje stavku rada. |
| Ručni unos i brisanje sati | `routers/billing.py:214` POST, `:323` DELETE, `:357` GET; FE `vindex.js:13003`, `13021`, `12847` | `test_v36_audit_billing_entry.py`, `test_wave9_billing_invariant.py` | `PRODUCTION` | Upisuje utrošene sate ili radnju po tarifi. |
| **AKS advokatska tarifa (71 stavka)** | `routers/billing.py:58-129` `AKS_TARIFA` (T01–T71), vrednost boda `:54` (Sl. gl. RS 56/2025); ruta `:531`; FE `vindex.js:12802`, `20807` | `test_tarife.py` (5 testova modela) | `PRODUCTION` | Padajući spisak radnji sa cenom (bodovi × vrednost boda). |
| Sopstvena satnica | `routers/tarife.py:107`, `:127`; podrazumevano 7.500 RSD (`:41`); FE `vindex.js:7351`, `7395` | `test_tarife.py::test_satnica_req_valid`, `::test_satnica_req_invalid_zero` | `PRODUCTION` | Advokat postavlja svoju satnicu. |
| Posebna satnica po klijentu | `routers/tarife.py:162`, `:184`; FE `vindex.js:7434`, `7452`, `7467` | `test_tarife.py`, `test_v38_audit_tarifa_update.py` (9), `test_v40a_tarifa_removal_guard.py`, `test_v40b_audit_tarifa_delete.py` | `PRODUCTION` | Dogovorena satnica za konkretnog klijenta ima prednost nad opštom. |
| Korekcija cene pojedinačne stavke tarife | `routers/tarife.py:291`, `:315`; FE `vindex.js:7359`, `7409`, `7421` | `test_tarife.py::test_stavka_req_both_none` | `PRODUCTION` | Kancelarija menja cenu bilo koje stavke i vraća je na podrazumevanu. |
| Kreiranje fakture iz nenaplaćenih stavki | `routers/billing.py:588`; FE `vindex.js:13061` | `test_v37_audit_faktura_create.py::test_1_success_emits_exactly_one_audit` (8) | `PRODUCTION` | Pretvara neobračunate stavke rada u fakturu sa brojem, PDV-om i rokom plaćanja. |
| Lista faktura | `routers/billing.py:893`; FE `vindex.js:2558` | `test_phoenix_mission_011_billing_reference_integrity.py` | `PRODUCTION` | Spisak izdatih faktura. |
| Slanje fakture e-poštom | `routers/billing.py:805`; FE `vindex.js:13208` | `test_recurring.py::test_posalji_email_200` | `PRODUCTION` | Šalje PDF fakture klijentu. |
| Ponavljajuće fakture | `routers/recurring.py:91`, `:125`, `:181`, `:281`; FE `vindex.js:13108`, `13153`, `13192`, `13175` | `test_recurring.py::test_list_recurring_200`, `::test_create_recurring_201`, `::test_generisi_faktura_201`, `::test_patch_recurring_deactivate` | `PRODUCTION` | Šabloni za mesečno ili godišnje fakturisanje stalnih klijenata. |
| **SEF / e-faktura — UBL 2.1 XML** | `sef_ubl.py:32`, ruta `routers/sef.py:319`; FE `vindex.js:13807` | `test_sef.py::test_ubl_xml_structure`, `::test_ubl_xml_invoice_lines`, `::test_ubl_xml_xss_escape` (8) | `PRODUCTION` | Pravi zvanični UBL XML fakture za Sistem e-faktura. |
| SEF — podešavanja, slanje, dnevnik | `routers/sef.py:224`, `:264`, `:362`, `:560`; FE `vindex.js:13726`, `13774`, `13795`, `13832` | `test_sef.py::test_sef_podesavanja_req_invalid_pib`; slanje bez testa | `PRODUCTION` | Unos podataka kancelarije i slanje e-fakture u državni sistem. |
| Finansijski izveštaji | `routers/billing_reports.py:48`, `154`, `223`, `306`, `374`, `490`; FE `vindex.js:13869-13872`, `20905`, `13948`, `2545` | `test_billing_reports.py` (33 testa) | `PRODUCTION` | Godišnji promet, dospelost dugovanja, struktura prihoda, izvoz u CSV za knjigovođu. |
| Ko duguje i koliko | `routers/billing.py:951`; FE `vindex.js:2466` | `test_billing_naplata.py::test_billing_router_dugovanja` | `PRODUCTION` | Pregled nenaplaćenih potraživanja. |
| Profitabilnost predmeta | `routers/profitabilnost.py:134`; FE `vindex.js:23411` | bez testa | `PRODUCTION` | Koliko je na predmetu utrošeno sati, naplaćeno i kolika je marža. |
| Ročišta i kalendar | `routers/rocista.py:128`, `:226`, `:269`, `:457`; `routers/kalendar.py:175`, `:209`; FE `vindex.js:14388`, `14336`, `14407`, `14194`, `14231` | `test_rocista_kalendar.py` (`test_rociste_req_valid`, `test_rociste_patch_all_valid_statuses`, `test_kalendar_pregled_default_range`, `test_kalendar_ics_has_vevent`) | `PRODUCTION` | Zakazivanje ročišta, objedinjen kalendar rokova i ročišta, izvoz u .ics. |
| Podsetnici ugrađeni u .ics | `ics_export.py:33-42` | `test_phase36_rokovi.py` | `PRODUCTION` | U svaki događaj ugrađuje alarm 7 dana i 1 dan unapred. |
| **Klijentski portal — pristupni link** | `routers/client_portal.py:214`, potpisan token `:81`, u bazi samo heš `:129`; FE `vindex.js:13432` | `test_client_portal.py::test_generi`, `::test_token_hash_deterministican`, `::test_verifikuj_token_istekao`, `::test_verifikuj_token_tampering` | `PRODUCTION` (generisanje i opoziv) | Advokat pravi vremenski ograničen link i šalje ga klijentu. |
| Klijentski portal — otpremanje dokumenta od klijenta | `routers/client_portal.py:514`; FE `vindex.js:13701` | `test_v36f_audit_client_portal_upload.py` | `PRODUCTION` | Klijent šalje advokatu dokument bez naloga. |
| Advokatski pregled klijentskih otpremanja | `routers/client_portal.py:658`, `:727`, `:750`; FE `vindex.js:13503`, `13535`, `13545` | `test_v36e_client_portal_zero_row_guard.py` | `PRODUCTION` | Lista primljenih fajlova, označavanje „pregledano", brisanje. |
| Obaveštenja u aplikaciji (zvono) | `routers/notifications.py:365`, `:440`, `:466`, `:495`; FE `vindex.js:11447`, `11631`, `11626`, `11652` | `test_omega_sprint007_notification_schema_alignment.py`, `test_beta_gate_notification_group_read.py` | `PRODUCTION` | Obaveštenja o rokovima i ročištima unutar aplikacije. |
| E-pošta — podešavanja i probna poruka | `routers/email_notif.py:183`, `201`, `222`, `233`; FE `vindex.js:15280`, `15325`, `15339`, `15350` | bez testa | `PRODUCTION` | Advokat uključuje podsetnike i šalje probnu poruku. |
| E-pošta — dnevni i nedeljni podsetnici | `routers/email_notif.py:256`, `:450`, `:726`; `.github/workflows/email-cron.yml` + `api.py:1851`, `1867`, `1884` | bez testa | `PRODUCTION` (spoljni cron) | Rokovi koji ističu za 1/3/7 dana; ponedeljkom sažetak. |
| SMS — broj, probna poruka, dnevni podsetnici | `routers/sms.py:115`, `145`, `163`, `177`, `:217`; `.github/workflows/sms-cron.yml`; FE `vindex.js:2621`, `2592`, `2649`, `2637` | `test_omega_sprint007_sms_reminder_dedup.py` | `PRODUCTION` (spoljni cron) | SMS podsetnik za rok koji ističe. |
| Push obaveštenja u pregledaču | `routers/push.py:40`, `:48`; FE `vindex.js:4133`, `4167` | bez testa | `PRODUCTION` | Pretplata na obaveštenja u pregledaču. |
| Moja kancelarija — članovi, pozivnice, uloge | `routers/kancelarija.py:147`, `216`, `246`, `264`, `305`, `372`, `406`, `439`, `477`, `520`, `560`, `591`; FE `vindex.js:2674`, `2814`, `2916`, `2853`, `2830`, `2840`, `2884`, `2894`, `2873`, `2903`, `2930` | `test_kancelarija_seats.py::test_get_clanovi_excludes_removed_by_default` | `PRODUCTION` | Osnivanje kancelarije, pozivanje kolega, suspenzija i uklanjanje članova. |
| Predmeti cele kancelarije | `routers/kancelarija.py:632`; FE `vindex.js:9954` | bez testa | `PRODUCTION` | Zajednički spisak predmeta firme. |
| Deljenje predmeta sa saradnikom | `routers/saradnja.py:125`, `:192`, `:246`, `:361`; FE `vindex.js:11043`, `11067`, `11002`, `10973` | `test_saradnja.py::test_dodaj_req_valid`, `::test_dodaj_req_email_prekratak` | `PRODUCTION` | Kolega dobija pristup konkretnom predmetu (pregled ili izmena); UI sakriva dugmad koja saradnik ne sme. |
| Objedinjeno sanduče i pregled dana | `routers/inbox.py:53`; `routers/dashboard.py:35`; FE `vindex.js:1279`, `1278` | `test_inbox.py::test_inbox_router_path` | `PRODUCTION` | Naslovni ekran sa rokovima, ročištima i alarmima. |
| Ugovor o zastupanju | `routers/ugovor_zastupanja.py:283`; FE `vindex.js:22564` | bez testa | `PRODUCTION` | Pravi nacrt ugovora o zastupanju za klijenta. |
| Uvoz klijenata iz CSV-a | `klijenti/router.py:1523` → `POST /klijenti/import-csv`; FE `vindex.js:4937` | bez testa | `PRODUCTION` | Uvozi klijente iz tabele. |
| **PDF fakture** | `routers/billing.py:755`; FE `vindex.js:13075` je običan `<a href target=_blank>` | bez testa | `DEAD` (pokvarena veza) | Ruta traži `Depends(get_current_user)`, a navigacija pregledača ne nosi zaglavlje sa tokenom → **401 pri kliku**. |
| **Preuzimanje dokumenta klijenta** | `klijenti/router.py:913`; FE `vindex.js:4729` — isti obrazac | bez testa | `DEAD` (pokvarena veza) | Isti uzrok kao gore. |
| Označavanje fakture kao plaćene / storno | `routers/billing.py:876` → `PATCH /billing/faktura/{id}/status` | bez testa | `IMPLEMENTED_UNWIRED` | Advokat može da izda fakturu, ali ne i da je označi kao naplaćenu. |
| Pretvaranje predračuna u fakturu | `routers/billing.py:724` | bez testa | `IMPLEMENTED_UNWIRED` | — |
| Reset zaglavljenog tajmera | `routers/billing.py:500` | bez testa | `IMPLEMENTED_UNWIRED` | Jedini izlaz iz zaglavljenog tajmera, a nema dugme — a `timer/start` vraća 409 dok aktivan tajmer postoji. |
| Izmena postojeće stavke rada | `routers/billing.py:280` `PATCH /billing/entries` | `test_v36_audit_billing_entry.py` | `IMPLEMENTED_UNWIRED` | — |
| Profitabilnost kancelarije (pregled, AI analiza, nenaplaćeno) | `routers/profitabilnost.py:219`, `:296`, `:384` | bez testa | `IMPLEMENTED_UNWIRED` | Pogledi na nivou cele kancelarije nemaju ekran. |
| Naplata: status i pregled po klijentu | `routers/billing.py:1003`, `:1049` | `test_billing_naplata.py::test_billing_router_naplata_status`, `::test_billing_router_po_klijentu` | `IMPLEMENTED_UNWIRED` | Testirano, bez ekrana. |
| SEF — provera prihvaćenosti fakture | `routers/sef.py:523` | bez testa | `IMPLEMENTED_UNWIRED` | — |
| Pretraga tarife / jedna stavka | `routers/tarife.py:264`; `routers/billing.py:554` | bez testa | `IMPLEMENTED_UNWIRED` | UI koristi celu listu. |
| Klijent — vraćanje obrisanog, arhiviranje, evidencija komunikacije, audit, rok čuvanja, analiza odnosa, otpremanje dokumenta | `klijenti/router.py:571`, `1169`, `1051`, `711`, `334`, `1315`, `755` | bez testa | `IMPLEMENTED_UNWIRED` | Sedam ruta bez ijednog ekrana. |
| Zadaci — lični spisak, statistika, preraspodela | `routers/zadaci.py:193`, `:469`, `:344` | `test_zadaci.py::test_statistika_team_member_gets_both_datasets` | `IMPLEMENTED_UNWIRED` | Lični zadaci i prebacivanje zadatka kolegi nemaju ekran. |
| Saradnja — predmeti podeljeni meni, privremeni pristup, evidencija deljenja | `routers/saradnja.py:302`, `:416`, `:470` | bez testa | `IMPLEMENTED_UNWIRED` | Saradnik ne može da vidi spisak predmeta koji su mu ustupljeni. |
| Istorija zauzetih licenci | `routers/kancelarija.py:277` | bez testa | `IMPLEMENTED_UNWIRED` | — |
| Uvoz klijenata sa mapiranjem kolona (3 koraka) | `routers/import_klijenti.py:102`, `:119`, `:156` | bez testa | `IMPLEMENTED_UNWIRED` | Jedini uvoz koji nudi pregled pre upisa — potpuno nedostupan. |
| Ponavljajuće fakture — brisanje šablona | `routers/recurring.py:230` | `test_recurring.py::test_delete_inactive_recurring_204` | `IMPLEMENTED_UNWIRED` | — |
| Duplirani izračun zdravlja predmeta | `routers/dashboard.py:423` | bez testa | `IMPLEMENTED_UNWIRED` | UI koristi `/api/matter-intel/predmeti/{id}`. |
| **WhatsApp — ceo modul (5 ruta)** | `routers/whatsapp_notif.py:194`, `258`, `348`, `481`, `520`; registrovan `api.py:633`, `730` | `test_v46_singleton_unsubscribe_semantics.py` | `DEAD` | **Nula pozivalaca u celom repou** — ni frontend, ni cron, ni drugi ruter. |
| **Viber — 7 ruta** | `routers/viber.py:104`, `170`, `202`, `213`, `241`, `308`, `340` | bez testa | `DEAD` (rute) | Nula poziva iz frontenda, nema cron posla. Funkcija `_viber_send` (`viber.py:64`) **jeste** živa — koriste je `admin_dashboard.py:117` i `portal_monitoring.py:210` za alarme vlasniku sistema. |
| **Zasebna stranica klijentskog portala** | `client_portal.html`, servirana `api.py:2359`; zove `/api/portal/predmet` (`client_portal.html:267`) | bez testa | `DEAD` | Token za nju pravi samo `routers/saradnja.py:416`, koji **nema nijednog pozivaoca**. |
| Stara provera sukoba interesa | `klijenti/router.py:616` → `POST /klijenti/check-conflict` | bez testa | `DEAD` | Funkcija je pregažena u toku izvršavanja: `vindex.js:19330` radi `window.crmPokreniKonflikt = crmPokreniKonfliktNovi`. |
| Stari čarobnjak za prijem klijenta | `klijenti/router.py:1238` | bez testa | `IMPLEMENTED_UNWIRED` | Zamenjen Smart Intake modulom. |

### Ograničenja koja sajt ne sme da prećuti

1. **Dve centralne „papirne" funkcije su neupotrebljive iz aplikacije** — PDF fakture i preuzimanje dokumenta klijenta. Oba su obični `<a href>` linkovi ka rutama koje traže token u zaglavlju.
2. **Klijentski portal ima dva nespojiva sistema.** `routers/client_portal.py:292` pravi link `{APP_BASE_URL}/portal?token=…`, a ruta `/portal` servira `client_portal.html`, koja token proverava u sasvim drugoj tabeli. Prikaz koji odgovara tom tokenu živi u `vindex.js:13574` i pali se samo kad `?token=` stoji na korenu `/`.
3. **Nijedan kanal obaveštenja nema kredencijale u lokalnom `.env`** — nedostaju SMTP, Twilio, Viber i push ključevi (svi dokumentovani u `.env.example`). U razvoju e-pošta, SMS, Viber, WhatsApp i push tiho ne rade.
4. **Faktura se ne može zatvoriti.** Izdavanje radi; označavanje kao plaćene ne postoji u UI.
5. **Tri paralelna sistema za uvoz klijenata**, od kojih je najbogatiji (sa mapiranjem kolona i pregledom) potpuno nedostupan.
6. **`routers/csv_import.py` uprkos imenu nije uvoz klijenata** — to je uvoz berzanskih transakcija za CARF/DAC8 izveštavanje (`csv_import.py:5-17`).

---

## SPOSOBNOSTI KOJE SME DA PRIKAŽE SAJT

Samo `PRODUCTION`. Grupisano po tome kako advokat razmišlja, ne po modulima.

**Prijem i obrada spisa**
- Otpremanje celog foldera dokumenata odjednom, sa prikazom obrade uživo kroz pet faza
- Prepoznavanje teksta (OCR) skeniranih PDF-ova i fotografija dokumenata, automatski
- Prepoznavanje vrste podneska (13 tipova) i vrste dokaza (9 tipova)
- Izvlačenje broja predmeta, suda, sudije, stranaka, roka, iznosa i zakona — svako polje sa svojom pouzdanošću
- Razdvajanje skeniranog svežnja od nekoliko stotina strana na pojedinačne dokumente
- Prepoznavanje kom postojećem predmetu dokument pripada; kad nije siguran — pita
- Red za ljudsku proveru ispod praga sigurnosti, uz ispravku pojedinačnog polja
- Šifrovano čuvanje originalnog fajla; prepoznavanje istog fajla otpremljenog dvaput

**Vođenje predmeta**
- Radni prostor predmeta: stranke, dokumenti, rokovi, komentari, beleške, praksa, procena rizika i ocena spremnosti u jednom pozivu
- Dnevni operativni pregled kroz šest kanti (Danas, Kritično, Predstojeće, Za pregled, Na čekanju, Završeno)
- Hronologija predmeta spojena iz šest izvora, uz upozorenje ako neki izvor otkaže
- Case Genome: pravna teorija, snaga predmeta, kontradikcije i najslabija tačka — sa istorijom verzija i automatskim osvežavanjem na novi dokument ili ročište
- Evidence Vault: matrica dokaza sa snagom, kategorijom i pravnim elementom
- Ročišta, kalendar, izvoz u Outlook/Google, lanac ZPP procesnih rokova, kalkulator zastarelosti
- Kanban zadataka uz predmet i AI predlog zadataka
- Zatvaranje predmeta sa ishodom, uz masovnu promenu statusa

**AI analiza**
- Pravno istraživanje nad bazom srpskih zakona sa navedenim izvorima
- Copilot u predmetu koji prepozna nameru i sam usmeri na pravo mesto
- Predikcija ishoda, profil suda, analiza protivne strane, ocena pojedinačnog argumenta, priprema pred ročište
- Tim od šest savetnika — pojedinačno ili tri paralelno
- Dnevni pregled celog portfelja predmeta
- Simulacija tri scenarija razvoja predmeta i „šta ako" analiza
- Merenje koliko su ranije AI procene bile tačne

**Strategija**
- Napad na sopstveni predmet iz uloge protivnika (Red Team)
- Pregled ugovora uz stvarne zakonske odredbe iz baze
- Revizija nacrta, analiza iskaza svedoka, simulirana rasprava
- Kompletna analiza u šest koraka sa serverski ograničenim verdiktom i deterministički izračunatim sistemskim upozorenjem

**Izrada nacrta**
- 18 vrsta brzih nacrta i 12 vrsta punih podnesaka
- Obavezno označavanje izvora `[IZVOR-n]` i kritički prolaz koji izmišljen broj člana zamenjuje oznakom za proveru
- Obavezna napomena da nacrt mora pregledati advokat pre podnošenja
- Provera kompletnosti pre generisanja; provera usklađenosti ugovora o radu sa zakonom (bez AI)
- Pisanje u stilu kancelarije na osnovu ranijih podnesaka
- Izvoz u Word sa memorandumom i izvoz celog predmeta u PDF

**Pretraga**
- Pretraga zakona po smislu, sa direktnim dohvatom kad je član naveden
- Sudska praksa uz odgovor, katalog sa filterima po sudu/oblasti/godini, ključni pravni stav, poređenje dve odluke, grupisanje po ishodu
- Zabrana izmišljenih članova i izmišljenih presuda — citat mora postojati u dohvaćenom tekstu, inače se odgovor blokira
- Prednost zvaničnih izvora nad neoverenim sadržajem

**Kancelarija**
- Kartoteka klijenata sa zaštitom matičnih podataka i evidencijom ko ih je gledao
- Provera sukoba interesa u četiri sloja, sa prepoznavanjem ćirilice i grešaka u kucanju
- Tajmer, ručni unos sati, AKS tarifa (71 stavka), sopstvena i klijentska satnica
- Fakture iz nenaplaćenih stavki, ponavljajuće fakture, e-faktura (UBL 2.1) za državni sistem
- Finansijski izveštaji i izvoz u CSV za knjigovođu
- Klijentski portal: vremenski ograničen link i prijem dokumenata od klijenta bez naloga
- Kancelarija sa licencama, pozivnicama i deljenjem predmeta sa saradnicima

**Platforma**
- Jedinstvena kapija dozvola na 129 mesta nad 58 funkcija; cene i limiti se menjaju u administraciji bez novog deploy-a
- Nepromenljiva evidencija sa hash-lancem koju baza fizički odbija da izmeni ili obriše
- Zaštita svakog AI poziva: filter ulaza, filter izlaza, zapis porekla i gašenje AI-a ako se zaštita ne učita
- Atomska naplata kredita i povraćaj kad AI padne
- Izvoz svih podataka koji se odbacuje ako je nepotpun

## KOD KOJI POSTOJI ALI NIJE OŽIČEN

**Ne sme na sajt ni u jednom obliku.** Poređano po veličini gubitka.

| Modul | Obim | Zašto boli |
|---|---|---|
| **Case Commander** (`routers/case_commander.py`, 5 ruta) | 1056 linija, 7 zelenih testova | Najzreliji „platforma računa, model samo obrazlaže" dizajn u repou. Jedini pomen u frontendu je komentar `vindex.js:1301`. |
| **Institucionalno učenje** (`routers/learning.py`, 14 od 15 ruta) | Lekcije, obrasci kancelarije, „šta bi bilo da", izveštaj o uspešnosti | Ožičen je samo upis ishoda. Sve što bi od tog upisa napravilo vrednost — nedostupno. |
| **Style Checker** (`routers/style_checker.py`, 7 ruta) | 18 KB, sopstveni feature ključ, **bez ijednog testa** | Profil pisanja advokata, ocena nacrta i evolucija stila. |
| **Strategy Simulator** (`routers/strategy_simulator.py`, 4 rute) | 20 KB, `test_strategy_simulator_audit.py` | Partija poteza protiv protivničkog advokata. |
| **Knowledge Transfer** (`routers/knowledge_transfer.py`, 8 ruta) | Profili znanja, ekstrakcija iz izvora | Nula poziva. |
| **Knowledge Hygiene** (`routers/knowledge_hygiene.py`, 7 ruta) | Skeniranje protivrečnosti, arhiviranje zastarelog | Nula poziva. |
| **Lična baza znanja** (`routers/knowledge_base.py`, 5 ruta) | Sopstveni vektorski prostor po korisniku | Nula poziva, nula testova. |
| **Firm Memory** (`routers/firm_memory.py`, 11 ruta) | Memorija o sudijama, klijentima, partnerima | Nula poziva. |
| **Memory Graph** (`routers/memory_graph.py`, 4 rute) | Mreža veza između entiteta | Nula poziva. |
| **Regionalni AI savet** (`routers/region.py`, 4 rute) | Podrška za susedne jurisdikcije | Nula poziva. |
| **Auto Discovery** (`routers/auto_discovery.py`, 4 rute) | Automatsko otkrivanje izvora | Nula poziva. |
| **Onboarding** (`routers/onboarding.py`, 5 ruta) | Vođenje kroz prve korake | Nula poziva; frontend zove drugu rutu (`api.py` `/api/auth/onboarding/complete`). |
| **Uvoz klijenata sa mapiranjem** (`routers/import_klijenti.py`, 3 rute) | Jedini uvoz sa pregledom pre upisa | Nula poziva; koriste se dva druga, slabija uvoza. |
| **Agent Notifications** (`routers/agent_notifications.py`, 2 rute) | Prihvatanje/odbijanje predloga autonomnih agenata | Nula poziva — pozadinski agenti pišu predloge koje niko ne može prihvatiti. |
| **Deadline Guardian + procesni rokovi** (`routers/zastarelost.py`, 5 ruta) | Skeniranje propuštenih rokova, računanje sa praznicima | Nula poziva, a naplata je uvezana. |
| **Zakon Monitoring** (`routers/zakon_monitoring.py`, 5 ruta) | Praćenje izmena zakona i uticaja na predmete | Nula poziva. |
| **Integracije** (`routers/integrations.py`, 8 ruta) | Webhooks, Google Calendar | Nula poziva. |
| **WhatsApp** (`routers/whatsapp_notif.py`, 5 ruta) | Obaveštenja preko WhatsApp-a | **DEAD** — nula pozivalaca u celom repou. |
| **Viber rute** (`routers/viber.py`, 7 ruta) | Povezivanje naloga, dnevni brifing | **DEAD** — funkcija slanja se koristi samo za alarme vlasniku. |
| **Jutarnji brifing** (`routers/morning_briefing.py`, 9 ruta) | Pregled dana | Kartica namerno uklonjena; preostali kanal zavisi od spoljnog cron servisa koji nije deo dnevnog dispečera. |
| **Ostalo, pojedinačne rute** | Poslednji sačuvani briefing, jeftino očitavanje ocene spremnosti, worklist, označavanje ročišta kao održanog, ishod zatvorenog predmeta, lični zadaci i statistika, preraspodela zadatka, Uncertainty Dashboard, Pre-Flight provera, Decision Replay, Reasoning Graph, `POST /strategija/v2/analiza`, stream odgovora, stara AI preporuka, drugi GDPR izvoz, `shared/ai_fabric.py`, `shared/rbac.py`, `require_credits` | — |

**Pokvarene veze (kod na obe strane postoji, ali se ne sreću):**
- `POST /api/evidence-graph/generisi` — frontend zove `/generi%C5%A1i` (`vindex.js:22735`), backend sluša `/generisi` (`evidence_graph.py:178`). Oba dugmeta za graf dokaza su mrtva.
- PDF fakture i preuzimanje dokumenta klijenta — obični linkovi ka rutama koje traže token u zaglavlju → 401.
- Klijentski portal — link koji advokat pošalje vodi na stranicu koja token proverava u drugoj tabeli.
- `.doc` — dozvoljen na ulazu (`api.py:4665`), ekstraktor ga ne ume (`uploaded_doc/extractor.py:393-401`).

## NAJJAČE TRI STVARI

Kriterijum: nešto što advokat prepoznaje kao svoj problem, što konkurencija teško imitira, i za šta u repou postoji dokaz izvršavanja, a ne samo namere.

### 1. Brojeve računa program, AI ih samo objašnjava

**Zašto je najjače:** ovo je jedina odbrana od pitanja koje svaki advokat postavlja — „a šta ako AI izmisli?". Odgovor nije obećanje nego arhitektura.

**Dokaz u kodu:**
- `services/risk_engine.py::calculate_procesni_rizik` je jedini izvor procesnog rizika. Njegov dokstring nosi pravilo AR-01: nijedan LLM izlaz ne sme biti jedini izvor poslovnog stanja — rizika, statusa, roka, spremnosti ili prioriteta. Koriste ga `api.py:5758`, `routers/ccc.py:160`, `routers/dashboard.py:281`, `matter_intel`, `case_pipeline`, `hearing_cc`; pokriven je u 10+ test fajlova.
- `shared/case_readiness.py` presuđuje SPREMAN / DELIMIČNO / BLOKIRAN / KRITIČNA PRAZNINA i time ograničava koliko samouvereno AI sme da govori; `test_sigma_sprint004_case_readiness.py::test_readiness_critical_gap_beats_everything_else`.
- `shared/case_context.py` daje svim AI modulima isti opis predmeta od 14 polja i **sam ne zove AI** — što je posebno dokazano testom `test_case_context_module_makes_zero_gpt_calls`.
- `shared/genome_validator.py` odbija procenu koja se poziva na dokument koji ne postoji (`test_genome_validator.py::test_dokazi_rang_flags_nonexistent_document`).
- U strategiji: sistemsko upozorenje i detekcija protivrečnosti se **računaju u kodu**, ne traže se od modela (`test_strategija_sistemsko_upozorenje.py::test_orkestrator_sistemsko_upozorenje_racuna_se_deterministicki_ne_llm`), a verdikt orkestratora se serverski ograničava (otrovan odgovor 9999 → 100).

**Ograda za sajt:** ograničenje verdikta ne postoji na tri samostalne strategijske rute. Poruka mora biti „brojevi koje vidite računa program", ne „AI nikad ne presuđuje".

### 2. Nacrt koji ne sme da izmisli citat

**Zašto je najjače:** izmišljen član ili nepostojeća presuda u podnesku je profesionalni rizik, ne neugodnost. Ovde postoji dvostruka brana, i na pretrazi i na pisanju.

**Dokaz u kodu:**
- U pretrazi: `main.py:729` `_proveri_halucinaciju` blokira odgovor ako citiran član ne postoji u dohvaćenom tekstu; `main.py:2865-2887` isto za brojeve presuda. Dokaz: `test_c7a_praksa.py::test_t6_guard_blocks_fabricated_praksa`.
- U pisanju: `shared/drafting_grounding.py:17` nameće `[IZVOR-n]` oznaku uz svaki citat i izričito zabranjuje da se oznaka dodeli navodu koji taj izvor ne potkrepljuje. `shared/drafting_grounding.py:31` je drugi, kritički prolaz — a ključno je **kako** ispravlja: izmišljen broj člana se zamenjuje oznakom `[proveriti relevantan član]`, **nikad drugim brojem**. Dokaz: `test_phoenix_mission_010_drafting_rag_grounding.py::test_generate_draft_critique_neutralizes_hallucinated_article_number`, i test koji tvrdi da obe površine za izradu nacrta uvoze **isti** kritički prompt.
- Svaki nacrt nosi obaveznu napomenu da mora biti pregledan pre podnošenja (`test_templates_podnesci.py::test_napomena_sistema_u_outputu`).
- Rangiranje daje prednost zvaničnim izvorima, a neoveren AI sadržaj ima težinu 0.00 (`shared/vector_origin.py:35`).

**Ograda za sajt:** šest od dvanaest tipova podneska trenutno ide kraćim putem bez kritičkog prolaza, i nacrt se ne piše nad dokumentima predmeta.

### 3. Predmet koji se sam ažurira — tačno jednom

**Zašto je najjače:** ovo je jedina sposobnost iz cele mape koju advokat ne mora da nauči da koristi. Radi dok on radi svoj posao. I ono što je tehnički najteže — radi bez duplikata i bez duplog troška.

**Dokaz u kodu:**
- `services/event_bus.py` piše događaje u trajni red, a `services/case_evolution.py:1245` drži registar posledica. Kad se prihvati dokument ili zakaže ročište, sistem sam osveži Case Genome, upiše u hronologiju, preračuna otvorene akcije i pošalje obaveštenje.
- Ključni dokaz nije da radi, nego da radi **tačno jednom**: `test_case_evolution.py::test_try_claim_consequence*` i `test_omega_sprint002_case_intelligence.py::test_scenario4_crash_after_genome_before_summary_retry_does_not_redo_genome` — pad servera usred lanca ne izaziva ponovni AI trošak pri restartu.
- `test_blackswan_mission001.py::test_refresh_case_dna_rejects_concurrent_call_for_same_predmet` — dva istovremena osvežavanja daju 409, ne dupli zapis.
- `test_omega_sprint004_case_to_workspace_flow.py::test_new_document_finding_flows_to_workspace_with_no_manual_refresh` — nalaz iz novog dokumenta stiže na jutarnju tablu bez ijednog klika.
- Genome ne ostaje zatvoren u sebi: rok koji AI nađe u dokumentu upisuje se u hronologiju i pojavljuje u kalendaru (`case_dna.py:672`).

**Ograda za sajt:** automatika pokriva 11 tipova događaja; 7 deklarisanih tipova nema nijedan izvor, a ročište se ne može označiti kao održano, pa jedan deo lanca nikad ne krene.

---

## Metodološka napomena

Mehanički inventar ruta (prefiks rutera + dekorator, uparen sa tekstualnom pretragom frontenda) daje **lažno pozitivne i lažno negativne rezultate u oba smera**, i nije korišćen kao dokaz:

- Lažno negativni: frontend gradi putanje kao `BASE_URL + '/strategija/red-team'` i drži ih u promenljivama (`vindex.js:2961`), pa pretraga za `/api/strategija` daje nulu iako je ruta ožičena. Nekoliko rutera uopšte nema `/api` prefiks (`/strategija`, `/billing`, `/waitlist`).
- Lažno pozitivni: prefiks rute se poklopi sa srodnom, stvarno ožičenom rutom (`/api/commander/analiza`, `/api/predmeti/{id}/ishod`, `PATCH /api/rocista/{id}`, `/pipeline/status`, `/briefing/poslednji`).
- Nepotpunost: prvi prolaz nije obuhvatio `klijenti/router.py` (21 ruta) ni `routers/conflict_check.py` — dakle celo jezgro kartoteke klijenata.

Svaki `IMPLEMENTED_UNWIRED` i `DEAD` u ovom dokumentu proveren je ručno po četiri kriterijuma: puna putanja, putanja bez `/api`, poslednji segment putanje, i ime funkcije u `static/vindex.js` i `index.html`.
