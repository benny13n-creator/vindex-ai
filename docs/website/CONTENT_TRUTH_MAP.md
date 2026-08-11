# VINDEX AI — MAPA ISTINE ZA SADRŽAJ SAJTA

**Faza B — TRUTH / CLAIMS AUDIT. Most između registra tvrdnji i copywritinga.**

- Stanje: `108dc48b`
- Izvori istine: `VINDEX_WEBSITE_CLAIMS_REGISTRY.md` (56 tvrdnji) ·
  `VINDEX_WEBSITE_CAPABILITY_MAP.md` (237 `PRODUCTION` sposobnosti) ·
  `VINDEX_WEBSITE_CONTENT_MAP.md` (struktura i ograde)
- Metod: **nije rađena nova forenzika.** Svaka rečenica ispod izvedena je iz već
  dokazane tvrdnje ili već dokazane sposobnosti. Nijedan produkcioni fajl nije menjan,
  aplikacija nije pokretana.

## Šta je ovaj dokument

Kolona **JAVNA FORMULACIJA** sadrži **doslovan tekst koji sme da stoji na sajtu**.
Copywriting sme da menja ritam i red reči, ali **ne sme da doda nijednu tvrdnju** koje
ovde nema, ni da izbaci ogradu koja je deo rečenice.

## Kako čitati status

| Status | Značenje |
|---|---|
| `VERIFIED` | Rečenica je pokrivena dokazom iz registra ili capability mape, bez ograde. |
| `PARTIALLY_VERIFIED` | Rečenica je tačna **samo sa ogradom koja je ugrađena u samu rečenicu**. Ograda se ne sme skratiti ni pomeriti u fusnotu. |
| `OPISNO` | Nije tvrdnja o proizvodu nego opis problema korisnika. Ne traži dokaz, ali ne sme da sadrži brojku ni statistiku. |
| `ROADMAP` | Sme samo u sekciji „Vizija", nikad kao postojeća funkcija. |

**Pravilo koje je primenjeno svuda:** kada je najbolja dokaziva rečenica slabija nego
što bi marketing hteo, upisana je slabija. Kraća i tačna pobeđuje lepšu i neproverivu.

---

# 1. TABELA JAVNIH FORMULACIJA

| # | Sekcija | JAVNA FORMULACIJA (doslovno) | Dokaz (fajl:linija / test) | Status | Ograničenje |
|---|---|---|---|---|---|
| 1 | Hero | Odgovor sa navedenim propisom. Ili nikakav odgovor. | `main.py:3354-3362`, `app/services/retrieve.py:822-840`, `static/vindex.js:924-955` | VERIFIED | Sme kao naslov. Ispod njega mora stajati rečenica 2, nikad sama. |
| 2 | Hero | Kada postavite pravno pitanje, Vindex vam kaže na kojim propisima počiva odgovor — i ćuti kada pouzdan izvor ne postoji. | `main.py:3354-3362`, `main.py:3504,3613`, `api.py:1438-1439`, `index.html:4028` | VERIFIED | **Namerno je uže od „svaki odgovor".** Analiza dokumenta i nacrti ne vraćaju spisak izvora — v. red 47. |
| 3 | Hero | Vindex zna odakle zna. Kada postavite pravno pitanje, kaže vam na kojim propisima počiva odgovor — i ćuti kada pouzdan izvor ne postoji. | Registry §11; `main.py:3354-3362`, `static/vindex.js:924-955` | PARTIALLY_VERIFIED | Druga rečenica je ograda i **ne sme se odvojiti od prve**. Naslov „Vindex zna odakle zna" sam, bez nje, obećava putanju do dokumenta koja ne postoji. |
| 4 | Hero | Prijavite se za zatvoreno testiranje. | `routers/waitlist.py:143` → `POST /waitlist/prijava`, registrovano `api.py:745` | VERIFIED | Jedini dozvoljen primarni poziv na akciju. Zabranjeno: „Počnite besplatno", „Zakažite demo", „Kontaktirajte prodaju". |
| 5 | Problem | Kontekst predmeta živi u glavi advokata, a ne u sistemu — pa se pri svakoj promeni rekonstruiše iznova. | — | OPISNO | Bez ijedne brojke, bez „istraživanja pokazuju". |
| 6 | Problem | Rokovi stoje u tekstu rešenja i presuda, a ne u kalendaru. | — | OPISNO | Ne sme se nastaviti u „nikad više propuštenih rokova". |
| 7 | Problem | Provera tuđe ili sopstvene tvrdnje znači ponovno čitanje istog spisa. | — | OPISNO | Ne sme se kvantifikovati u sate ni u procente. |
| 8 | Kako radi — korak 1 | Prevučete ceo folder dokumenata odjednom; skenirani PDF i fotografija dokumenta se pročitaju prepoznavanjem teksta, a vi u živo pratite obradu kroz pet faza. | `routers/smart_intake.py:108`, `:1280`, `uploaded_doc/extractor.py:104`, FE `vindex.js:21605`; `test_omega_sprint001_batch_intake.py`, `test_extractor_ocr.py` | VERIFIED | Nijedna tvrdnja o kvalitetu ili brzini prepoznavanja teksta. |
| 9 | Kako radi — korak 2 | Iz dokumenata se izvlače broj predmeta, sud, sudija, stranke, rok i iznos — svako polje sa svojom pouzdanošću; ispod praga sigurnosti dokument čeka vašu potvrdu umesto da se sam upiše. | `shared/intake_extract.py:85-113`, `:192`, `routers/smart_intake.py:356`; `test_intake_extract.py::test_extract_all_entities_returns_all_eight_types`, `test_intake_documents.py` | VERIFIED | Bez procenta tačnosti izvlačenja. |
| 10 | Kako radi — korak 3 | AI moduli ne čitaju vaš spis svaki na svoj način — svi dobijaju isti deterministički opis predmeta, koji se sastavlja bez ijednog poziva modela. | `shared/case_context.py`; `test_tau002_case_context.py::test_build_case_context_has_all_14_contract_fields`, `::test_case_context_module_makes_zero_gpt_calls` | VERIFIED | Ne sme se proširiti u „AI vidi ceo predmet". |
| 11 | Kako radi — korak 4 | Odgovor stiže sa spiskom propisa i članova i oznakom pouzdanosti; kada pouzdanog izvora nema, odgovora nema. | `retrieve.py:822-840`, `:2218`, `main.py:3354-3362`, `static/vindex.js:924-955`, `:6704-6712` | VERIFIED | — |
| 12 | Zašto verovati — dokaz 1 | Brojeve koje vidite — nivo rizika, ocenu spremnosti predmeta, otkrivene probleme — računa program po formuli; AI sme da ih objasni, ali ne i da ih odredi. | `services/risk_engine.py::calculate_procesni_rizik` (pravilo AR-01), `shared/case_readiness.py`, `shared/genome_validator.py`; 10+ test fajlova, `test_sigma_sprint004_case_readiness.py::test_readiness_critical_gap_beats_everything_else` | VERIFIED | **Nikad proširiti u „AI nikad ne presuđuje".** Ograničenje verdikta postoji samo u orkestratoru strategije, ne i na tri samostalne rute (`strategija.py` §Upozorenje). |
| 13 | Zašto verovati — dokaz 2 | Kada AI u nacrtu navede broj člana koji ne postoji u priloženim izvorima, drugi prolaz ga zamenjuje oznakom „proveriti relevantan član" — nikad drugim brojem. | `shared/drafting_grounding.py:17`, `:31`, primena `routers/drafting.py:459` i `drafting/router.py:421`; `test_phoenix_mission_010_drafting_rag_grounding.py::test_generate_draft_critique_neutralizes_hallucinated_article_number` | VERIFIED | Važi za obe putanje izrade nacrta. **Ne važi za generisanje iz šablona** (`routers/doc_templates.py:66-135`), koje nema ni kritički prolaz ni obaveznu napomenu. |
| 14 | Zašto verovati — dokaz 3 | Kad primite novi dokument ili zakažete ročište, predmet se sam osvežava — i to tačno jednom: pad servera usred posla ne izaziva ponovni AI trošak. | `services/case_evolution.py:1245`, `services/event_bus.py:364`; `test_case_evolution.py::test_try_claim_consequence*`, `test_omega_sprint002_case_intelligence.py::test_scenario4_crash_after_genome_before_summary_retry_does_not_redo_genome` | VERIFIED | Automatika se okida na 11 vrsta događaja; ročište se iz aplikacije ne može označiti kao održano, pa taj deo lanca ne kreće. Ne obećavati „sve se dešava samo". |
| 15 | Šta radi danas — Prijem spisa | Otpremanje celog foldera odjednom, prepoznavanje teksta sa skeniranih dokumenata i fotografija, prepoznavanje vrste podneska i vrste dokaza, i razdvajanje skeniranog svežnja na pojedinačne dokumente. | `routers/smart_intake.py:108`, `shared/intake_classify.py`, `routers/evidence.py:216`, `shared/intake_segment.py`; `test_intake_segment.py::test_large_pdf_500_pages_with_20_bundled_documents_all_pages_accounted_for` | VERIFIED | Bez brojeva („13 tipova", „9 tipova") dok ih test ne tvrdi eksplicitno. |
| 16 | Šta radi danas — Vođenje predmeta | Radni prostor predmeta koji u jednom pozivu vraća stranke, dokumente, rokove, beleške, praksu, procenu rizika i ocenu spremnosti, uz hronologiju spojenu iz šest izvora. | `api.py:5655`, `routers/intelligence_timeline.py:56`; `test_omega_sprint005_full_chain_to_workspace.py`, `test_intelligence_timeline.py` | VERIFIED | — |
| 17 | Šta radi danas — Pravno istraživanje | Pretraga propisa i sudske prakse po smislu pitanja, sa direktnim dohvatom kada je član izričito naveden. | `retrieve.py:891-960`, `:992`, `:939`; `test_doc_retrieval.py`, `test_a6_fixes.py::TestDirektanFetchClana` | VERIFIED | **Ne vezivati za globalnu pretragu u aplikaciji** — ona traži „sadrži reč" (`routers/search.py:232`). |
| 18 | Šta radi danas — Izrada nacrta | Nacrti podnesaka i ugovora sa obaveznom oznakom izvora uz svaki citat i obaveznom napomenom da nacrt mora pregledati advokat pre podnošenja. | `routers/drafting.py:597`, `:820`, `shared/drafting_grounding.py:17`; `test_templates_podnesci.py::test_napomena_sistema_u_outputu` | VERIFIED | Nacrt je polazna tačka, ne gotov podnesak — obavezna ograda, v. red 71. |
| 19 | Šta radi danas — Strategija | Alati za preispitivanje sopstvenog predmeta: napad iz uloge protivnika, pregled ugovora uz zakonske odredbe iz baze, revizija nacrta i simulirana rasprava. | `routers/strategija.py:235`, `:378`, `:423`, `:509`; `test_wave9_strategy_context.py` | VERIFIED | **Nikad kao predviđanje ishoda, verovatnoća ni simulacija suda.** Formulacija „alati za preispitivanje sopstvenog predmeta" je obavezna. |
| 20 | Šta radi danas — Kancelarija | Kartoteka klijenata sa zaštitom matičnih podataka, provera sukoba interesa, tajmer i advokatska tarifa, fakture i e-faktura za državni sistem. | `klijenti/router.py:368`, `routers/conflict_check.py:127`, `routers/billing.py:384`, `:588`, `sef_ubl.py:32`; `test_conflict_check.py`, `test_billing_timer_race.py`, `test_sef.py` | VERIFIED | Ne pominjati PDF fakture (pokvarena veza) ni označavanje fakture kao plaćene (nema ekran) — v. red 60. |
| 21 | Dokumenti | Prevučete ceo folder; svaki fajl dobija svoj posao i obrađuje se u pozadini, a kod paketa od nekoliko stotina fajlova dobijate „obrađeno N od M" umesto prekinute veze. | `routers/smart_intake.py:108`, `:71`, `:122`; `test_omega_sprint001_batch_intake.py::test_upload_batch_stops_early_when_time_budget_exceeded_and_reports_remaining` | VERIFIED | — |
| 22 | Dokumenti | Kada PDF nema tekstualni sloj, sistem sam pročita sliku stranice — bez posebnog dugmeta i bez vaše komande. | `uploaded_doc/extractor.py:104`, `:220-259`, pozivi `routers/dokument.py:259`, `api.py:4820`, `shared/intake_worker.py:511`; `test_extractor_ocr.py::test_ocr_success_returns_text_not_scanned` | VERIFIED | **Nijedna tvrdnja o kvalitetu prepoznavanja teksta** — nikad nije mereno nad stvarnim dokumentima. |
| 23 | Dokumenti | Skenirani svežanj od nekoliko stotina strana sam se deli na pojedinačne dokumente. | `shared/intake_segment.py::segment_document`; `test_intake_segment.py::test_large_pdf_500_pages_with_20_bundled_documents_all_pages_accounted_for` | VERIFIED | — |
| 24 | Dokumenti | Po broju predmeta i imenu stranke sistem prepozna kom postojećem predmetu dokument pripada; kada nije siguran, pita vas umesto da pogađa. | `shared/case_assimilation.py:121`, `:166`, `:236`, `routers/smart_intake.py:356`; `test_sprint007_bulletproof_intake.py`, `test_intake_documents.py` | VERIFIED | — |
| 25 | Dokumenti | Originalni fajl se čuva šifrovan, a isti fajl otpremljen dvaput ne pravi duplikat posla. | `routers/smart_intake.py:97`, `:152`, `api.py:4784-4794`; `test_intake_original_file_storage.py::test_upload_stores_original_file_and_writes_real_storage_path` | VERIFIED | — |
| 26 | Dokumenti | Rokovi se iz dokumenata prepoznaju automatski pri unosu, bez posebne komande. | `shared/intake_extract.py:113` → `uploaded_doc/deadline_parser.py::ekstrahuj_rokove`, `api.py:3549-3572`, `routers/intake.py:431-437`; `test_deadline_parser.py`, `test_phase36_rokovi.py` | VERIFIED | **Bez tvrdnje da nijedan rok neće promaći.** Recall ekstrakcije nikad nije meren. |
| 27 | Dokumenti | Vindex upoređuje dokumente istog predmeta i traži protivrečnosti među njima; mehanizam radi, ali kvalitet nalaza još nije meren nad stvarnim predmetima. | `routers/cross_doc.py:295`, `shared/gap_engine.py:151`; `test_cross_doc.py`, `test_sprint6_phase3_cross_doc.py` | PARTIALLY_VERIFIED | Ograda je deo rečenice. `evaluation/phase_0_5/PHASE_0_5_DECISION.md` je i dalje prazan šablon. |
| 28 | Dokumenti | Dokument koji je jednom ušao u spis ne briše se — u proizvodu ne postoji radnja brisanja dokumenta. | `shared/audit_immutable.py:68-71`, `tests/test_gdpr_delete.py:130` | PARTIALLY_VERIFIED | Ne opisivati kao „soft-delete garanciju" ni kao politiku čuvanja. To je posledica toga što ruta za brisanje ne postoji. |
| 29 | Predmet i kancelarijsko znanje | Podaci jednog predmeta ne mogu ući u analizu drugog — vlasništvo se proverava pre nego što ijedan upit nad podacima uopšte krene. | `shared/case_context.py:170-190`, `:226`; `test_wave11_context_isolation.py::test_tudji_predmet_ne_izvrsava_nijedan_upit_nad_podacima`, `::test_vlasnik_dobija_bajt_identican_rezultat` | VERIFIED | — |
| 30 | Predmet i kancelarijsko znanje | Dokumenti iz vaših predmeta trajno ulaze u prostor znanja vaše kancelarije, ali se taj prostor pretražuje samo u automatskoj analizi pri unosu dokumenta — kada postavite pravno pitanje, Vindex pretražuje propise i sudsku praksu, ne i vaše ranije predmete. | `api.py:4715`, `:4757`, `:4891` (upis u `kancelarija_{id}`/`user_{id}`), `retrieve.py:1847-1852` sa jedinim pozivaocem `api.py:5124`; Capability map §6, nalaz 4 | VERIFIED | **Ovo je tačna granica kancelarijskog znanja.** Sve jače od ovoga otpada — v. §3, stavka 3. |
| 31 | Predmet i kancelarijsko znanje | Slične ranije predmete iste kancelarije Vindex pronalazi poređenjem po vrsti spora i pravnoj oblasti, a ne po smislu činjenica. | `routers/precedenti.py:47`, `:80-89`; `test_synapse_precedenti_genome_context.py` | VERIFIED | Zabranjeno predstaviti kao semantičku pretragu sopstvenih predmeta. |
| 32 | Predmet i kancelarijsko znanje | Uspešnost kancelarije po tipu spora računa se iz ishoda koje sami upišete pri zatvaranju predmeta. | `routers/learning.py:126`, `routers/outcome_intel.py:49`; `test_outcome_intel.py::test_with_history_calls_gpt` | VERIFIED | Ne obećavati da sistem sam prepoznaje ishod — ishod upisuje advokat. |
| 33 | Predmet i kancelarijsko znanje | Kada izmenite tekst koji je AI napisao, sistem tu ispravku pamti i koristi kasnije; koliko to menja kvalitet teksta nije mereno. | `routers/corrections.py:232`, `drafting/playbook.py:52`, `:92`, `:115` | PARTIALLY_VERIFIED | Ograda je deo rečenice. `routers/corrections.py` i `drafting/playbook.py` nemaju test. |
| 34 | Predmet i kancelarijsko znanje | Deljenje unutar kancelarije pokriva zadatke, memoriju firme i pristup pojedinačnom predmetu koji dodelite kolegi — ne i automatsko deljenje svih predmeta među članovima. | `kancelarija_id` kao filter na 45 mesta u 8 fajlova, `routers/saradnja.py:125`, `routers/kancelarija.py:632`; `test_kancelarija_seats.py`, `test_saradnja.py` | VERIFIED | — |
| 35 | Predmet i kancelarijsko znanje | Vindex ne uči sam iz svih vaših predmeta: ono što jedan predmet nauči ne ulazi automatski u odgovore na drugom. | Capability map: `routers/learning.py` 14 od 15 ruta bez pozivaoca; `routers/drafting.py:245` (memorija nacrta u praksi prazna); §6 nalaz 4 | VERIFIED | Sekcija „Šta ne radimo" — ovo je diferencijator, ne izvinjenje. |
| 36 | AI analiza | Vindex pretražuje propise po smislu pitanja, a kada izričito navedete član, povlači ga doslovno umesto da nagađa. | `retrieve.py:891-960`, `:992`, prepoznavanje `:693`; `test_a6_fixes.py::TestDirektanFetchClana` | VERIFIED | — |
| 37 | AI analiza | Citiran član mora postojati u tekstu koji je sistem stvarno dohvatio — u suprotnom se odgovor blokira. Isto pravilo važi za brojeve presuda. | `main.py:729` `_proveri_halucinaciju`, `:2865-2887`; `test_c7a_praksa.py::test_t6_guard_blocks_fabricated_praksa` | VERIFIED | Najjača tvrdnja u ovoj sekciji. Ne mešati sa nacrtima — tamo radi drugi mehanizam (red 13). |
| 38 | AI analiza | U predmetu pišete pitanje običnim jezikom; sistem prepozna nameru i sam usmeri na pravno pitanje, praksu, nacrt, rok ili belešku. | `routers/copilot.py:1420`; `test_sprint6g_copilot_billing_gate.py::test_3_authorized_reaches_provider_and_is_charged_once` | VERIFIED | — |
| 39 | AI analiza | Uz svaku procenu stoji napomena da je reč o proceni modela, a ne o izračunatoj statistici. | `routers/strategija.py:107-153`, `:136-138`, FE `static/vindex.js:3814-3827`; `test_tau003_decision_boundary.py::test_all_9_strategija_endpoints_attach_ai_advisory_provenance` | VERIFIED | **Nijedan broj koji AI vrati nije statistika.** Zabranjeno: „verovatnoća ishoda", „predviđa presudu", „procena verodostojnosti iskaza". |
| 40 | AI analiza | Vindex razlikuje analizu izgrađenu nad vašim praćenim predmetom od analize nad tekstom koji ste nalepili — i to vam kaže. | `routers/strategija.py:107-153`, `static/vindex.js:3814-3827`; `test_tau003_decision_boundary.py`, `test_rc_beta_flows.py:500,543,611,647` | VERIFIED | Prikazuje se u kompletnoj analizi. |
| 41 | AI analiza | Kada je analiza sama sebi nesigurna ili kada njeni koraci protivreče jedan drugom, sistem to sam prijavi — to pravilo se računa u kodu, ne traži se od modela. | `routers/strategija.py:1006-1050`, `:1052-1090`; `test_strategija_sistemsko_upozorenje.py::test_orkestrator_sistemsko_upozorenje_racuna_se_deterministicki_ne_llm` | VERIFIED | Važi za kompletnu analizu (orkestrator). Ne generalizovati na sve rute. |
| 42 | AI analiza | Tuđi predmet daje odbijenicu pre ijednog upita u bazu, pre poziva modela i pre naplate. | `routers/strategija.py:193`, `:640-644`; `test_wave9_strategy_context.py::test_c_tudji_predmet_id_daje_404_bez_posla_i_bez_naplate` | VERIFIED | — |
| 43 | Izvori i poverenje | Ispod odgovora na pravno pitanje stoji spisak propisa i članova na kojima odgovor počiva — do pet stavki, u obliku naziv propisa i broj člana. | `retrieve.py:822-840`, `main.py:3504,3613`, `api.py:1438-1439`, `static/vindex.js:924-955`, `index.html:4028`, `static/vindex.css:9636-9679` | VERIFIED | Prikaz je proveren čitanjem koda i CSS-a, **nije pokriven automatskim testom**. Pre snimka ekrana obavezna je jedna živa provera. |
| 44 | Izvori i poverenje | Uz svaki odgovor stoji oznaka pouzdanosti pronađenih izvora — visoka, srednja ili niska. | `retrieve.py:2218`, `static/vindex.js:6692`, `:6704-6712`; `test_celina1_praksa_rag_2026_07_24.py:45` | VERIFIED | — |
| 45 | Izvori i poverenje | Kada Vindex ne pronađe pouzdan izvor za vaše pitanje, on ne odgovara — u tom slučaju se model uopšte ne poziva. Ne dobijate slabiji odgovor koji morate da prepoznate kao slab; ne dobijate nikakav. | `main.py:3354-3362` (`_format_low_response`, bez LLM poziva), `main.py:3139-3149`; RAG confidence testovi | VERIFIED | **Najjača dokaziva tvrdnja na celom sajtu.** Mora biti predstavljena kao vrednost, ne kao izvinjenje. |
| 46 | Izvori i poverenje | Spisak izvora navodi propis i član. Ne vodi klikom do teksta propisa, ne pokazuje na dokument iz vašeg spisa i ne navodi stranu u njemu — do samog člana idete sami. | Registry §3.3, `static/vindex.js:918-923` (izričito objašnjenje zašto citat nije klikabilan) | VERIFIED | Obavezan deo sekcije. Zabranjeno: „kliknite do izvora", „vidite iz kog dokumenta i sa koje strane". |
| 47 | Izvori i poverenje | Spisak izvora prati pravno istraživanje. Analiza dokumenta i izrada nacrta ne vraćaju spisak izvora. | `routers/drafting.py:202-227`, `:692`; Registry §3.2 | VERIFIED | Obavezan deo sekcije. Bez ovoga red 2 postaje netačan. |
| 48 | Izvori i poverenje | U nacrtu svaki citat nosi oznaku izvora iz kog je stvarno došao, a dodeljivanje te oznake navodu koji izvor ne potkrepljuje izričito je zabranjeno. | `shared/drafting_grounding.py:17`, pravilo u promptu `templates/podnesci.py:1465`; `test_faza3_drafting_engine_2026_07_24.py::test_svi_obogacivanje_promptovi_imaju_izvor_pravilo` | VERIFIED | Ovo je zamena za nepostojeći spisak izvora u nacrtima, ne dodatak uz njega. |
| 49 | Governance | Pre nego što vaš tekst ode modelu, prolazi kroz ulaznu proveru koja odbija pokušaj ubacivanja naloga u pitanje — i to pre naplate. | `api.py:3084-3088`, `:3269-3291`, `security/prompt_guard.analyze`; `test_wave11_guard_and_provenance.py::test_g1_b_blokiran_tekst_NE_STIZE_do_provajdera` | VERIFIED | — |
| 50 | Governance | Zaštita nije ugrađena u svako pozivno mesto nego u sam sloj koji poziva model, pa nijedan tekstualni poziv ne može da je zaobiđe; glasovni kanal i ponovno rangiranje rezultata su imenovani izuzeci koji kroz tu kapiju ne prolaze. | `shared/ai_client.py:781-782`, `api.py:28`; `test_rc_cold_start.py`, `test_gov2_runtime_interception.py` | PARTIALLY_VERIFIED | Ograda o izuzecima je deo rečenice i ne sme se izbaciti. Izuzeci su imenovani u samom testu (`services/voice_orchestrator.py`, Cohere). |
| 51 | Governance | Odgovor modela prolazi kroz izlaznu proveru pre nego što stigne do vas; ako sama ta provera otkaže, poziv pada umesto da prođe neproveren. | `security/response_firewall.py`; `test_gov3_response_firewall.py::test_b_pokvaren_odgovor_NE_STIZE_do_pozivaoca`, `::test_e_greska_u_samoj_proveri_ZATVARA` | VERIFIED | — |
| 52 | Governance | Kada bezbednosna kapija oko AI-ja ne može da se podigne, AI poziv se ne izvršava — sistem se zatvara, ne propušta. | `shared/ai_client.py:131-177`, `:640-644`; `test_wave9_governance.py::test_c1_b_sinhroni_klijent_se_NE_MOZE_konstruisati` | VERIFIED | — |
| 53 | Governance | Za svaki AI poziv beleži se koji je model korišćen, koliko je trajao i pod kojim identifikatorom zahteva — bez ijednog ručnog ožičenja na pozivnim mestima. | `shared/ai_client.py:409-465`, `:781-782`, `security/ai_forensics.py:207-311`; `test_mission_atlas_ai_provenance.py`, `test_wave11_guard_and_provenance.py:164` | VERIFIED | — |
| 54 | Governance | Tekst vašeg pitanja i tekst odgovora ne upisuju se u tu evidenciju — čuva se samo kriptografski otisak. | `shared/ai_client.py:445-449`; `test_ai_fabric_governance.py::test_7_successful_call_writes_canonical_audit_without_content` | VERIFIED | — |
| 55 | Governance | Radnje u sistemu upisuju se u evidenciju ulančanu kriptografskim otiskom, koju baza fizički odbija da izmeni ili obriše — provereno izvršavanjem migracije nad pravom bazom podataka. | `migrations/043_security_bulletproof.sql:33-52`, `shared/audit_immutable.py:30`, `:366-381`; `test_rc_migration_gate.py:399`, `:414`, `:453` | VERIFIED | **Bez pominjanja `UNIQUE(prev_hash)`.** Zabranjeno reći „stalno" ili „u CI-ju" — ti testovi se u CI-ju preskaču. |
| 56 | Governance | Za tu evidenciju još ne postoji ekran na kome biste je pregledali — mehanizam je dokazan, korisnički prikaz dolazi kasnije. | Registry §9, stavka 7; Capability map §7, nalaz 4 | VERIFIED | Zabranjeno: „revizorski trag koji možete pregledati". Na sajtu se objašnjava **dijagramom**, nikad snimkom nepostojećeg ekrana. |
| 57 | Za advokate | Ujutru dobijate jedan ekran sa svim što traži pažnju, razvrstano u šest kanti: Danas, Kritično, Predstojeće, Za pregled, Na čekanju, Završeno. | `routers/workspace.py:175`, FE `vindex.js:1733`; `test_omega_sprint004_workspace.py` | VERIFIED | — |
| 58 | Za advokate | Nov predmet otvarate tako što otpremite spis: predmet, stranke i rokovi popune se iz dokumenata, a vi potvrđujete ono u šta sistem nije siguran. | `routers/smart_intake.py:765`, `shared/case_assimilation.py:121`, `routers/smart_intake.py:356`; `test_lz002_evidence_autoclassify.py`, `test_intake_documents.py` | VERIFIED | — |
| 59 | Za advokate | Pre prihvatanja klijenta jednom radnjom proveravate sukob interesa kroz tužioce i tužene, kartoteku, uloge na predmetima i advokate suprotne strane, uz prepoznavanje ćirilice i grešaka u kucanju. | `routers/conflict_check.py:127`, `routers/intake.py:669`; `test_conflict_check.py::test_match_tuzilac_active_conflict`, `::test_only_closed_predmeti_returns_review`, `test_intake_conflict_check.py` | VERIFIED | — |
| 60 | Za advokate | Vreme merite tajmerom na predmetu, radnju birate iz advokatske tarife po vrednosti boda, a od nenaplaćenih stavki pravite fakturu i UBL e-fakturu za državni sistem. | `routers/billing.py:384`, `:54`, `:58-129`, `:588`, `sef_ubl.py:32`; `test_billing_timer_race.py`, `test_tarife.py`, `test_v37_audit_faktura_create.py`, `test_sef.py::test_ubl_xml_structure` | VERIFIED | Ne pominjati preuzimanje PDF fakture (pokvarena veza) ni označavanje fakture kao plaćene (ne postoji u aplikaciji). |
| 61 | Vizija | Klik iz citata do teksta propisa još ne postoji; to je sledeći korak u prikazu porekla odgovora. | `static/vindex.js:922-923` (izričito objašnjenje) | ROADMAP | Samo u „Viziji". Nikad u opisu postojeće funkcije. |
| 62 | Vizija | Objašnjenje zašto je baš taj izvor izabran postoji u sistemu, ali još ne izlazi do korisnika. | `retrieve.py:843-870`, izlaz samo na dijagnostičkoj ruti `api.py:2915` | ROADMAP | Samo u „Viziji". |
| 63 | Vizija | Ekran za pregled nepromenljive evidencije još ne postoji i planiran je. | Registry §7 | ROADMAP | Samo u „Viziji", objašnjeno dijagramom. |
| 64 | Vizija | Sloj za rad sa više dobavljača AI modela je implementiran i testiran; nijedna funkcija još ne ide kroz taj sloj. | `shared/ai_fabric.py:285-452`; `test_ai_fabric_governance.py` (17 prolazi) | ROADMAP | Ograda „nijedna funkcija još ne ide kroz taj sloj" je **doslovno obavezna**. Zabranjeno: „koristimo GPT, Claude i Gemini", „automatski bira najbolji model", „unakrsna provera između modela". |
| 65 | Beta | Vindex je pred zatvorenim testiranjem: nema korisnika, nema preporuka i nema objavljenih rezultata merenja. | Registry §8, §9 stavka 16 | VERIFIED | Ovo je prvo što sekcija kaže, ne poslednje. |
| 66 | Beta | Prijava za zatvoreno testiranje ide preko forme na sajtu; broj mesta je ograničen. | `routers/waitlist.py:143`, registrovano `api.py:745` (javno, bez prijave) | VERIFIED | „Ograničen broj mesta" je operativna odluka, ne merenje. Ne dodavati konkretan broj mesta niti rok. |
| 67 | Beta | Pretplata se u ovoj fazi ne može kupiti u proizvodu i cene nisu objavljene. | `static/vindex.js:124` (`STRIPE_URL = ''`); Registry §9 stavka 14 | VERIFIED | Zajedno sa ovim se uklanja i ruta `/pricing` (`api.py:1550`) — v. `CONTENT_MAP §6.2`. |
| 68 | Beta | Tačnost pojedinih funkcija još nije merena, pa se nijedan procenat tačnosti ni ušteda vremena ne navodi. | `evaluation/phase_0_5/PHASE_0_5_DECISION.md` („TEMPLATE — no data collected yet") | VERIFIED | Poštenije je reći ovo nego ćutati — konkurencija ovo ne piše. |
| 69 | Founding Partner | Ograničen broj advokata koristi Vindex na stvarnim predmetima dok se proizvod još oblikuje; ono što se traži nije novac nego vreme i primedbe, a uslovi učešća dogovaraju se pojedinačno i nisu objavljeni. | `routers/waitlist.py:143` (jedini mehanizam u proizvodu); `static/vindex.js:124` (`STRIPE_URL = ''`) — dokaza za bilo kakvu komercijalnu ponudu **nema** | PARTIALLY_VERIFIED | Ograda „uslovi se dogovaraju pojedinačno i nisu objavljeni" je deo rečenice. Usklađeno sa sestrinskim dokumentom `docs/website/FOUNDING_PARTNER.md`; sve što je tamo označeno kao `ODLUKA VLASNIKA` ostaje van sajta. |
| 70 | Founding Partner | Ni cena, ni popust, ni trajanje bilo kakvog statusa ranog korisnika ne smeju se pojaviti dok ne postoji način da se plati. | `static/vindex.js:124` (`STRIPE_URL = ''`); Registry §9 stavka 14 | VERIFIED | Zabranjeno: „doživotna cena", „50% za osnivače", „Founding Partner paket", „lista čekanja". |
| 71 | FAQ 1 | Da li Vindex piše podneske umesto mene? Ne. Vindex piše nacrt koji je polazna tačka, a ne gotov podnesak, i uz svaki nacrt stoji napomena da ga advokat mora pregledati pre podnošenja. | `routers/drafting.py:646,673,713`, `templates/podnesci.py`; `test_templates_podnesci.py::test_napomena_sistema_u_outputu`, `test_phoenix_mission_010_drafting_rag_grounding.py` | PARTIALLY_VERIFIED | Ograda „polazna tačka, a ne gotov podnesak" je doslovno obavezna. |
| 72 | FAQ 2 | Šta se dešava kada Vindex ne zna odgovor? Odbija da odgovori i model uopšte ne poziva — nema nagađanja u odsustvu izvora. | `main.py:3354-3362` | VERIFIED | — |
| 73 | FAQ 3 | Mogu li da vidim odakle je odgovor? Da — ispod odgovora na pravno pitanje stoji spisak propisa i članova, ali bez linka ka tekstu propisa i bez upućivanja na stranu u vašem dokumentu. | `retrieve.py:822-840`, `static/vindex.js:924-955`, `:922-923` | VERIFIED | — |
| 74 | FAQ 4 | Da li podaci jednog klijenta mogu da procure u drugi predmet? Podaci su razdvojeni po nalogu, provera vlasništva se izvršava pre nego što ijedan upit nad podacima krene, i to je pokriveno testovima. | `shared/case_context.py:170-190`, 541 filter `.eq("user_id", ...)` u 88 fajlova; `test_wave11_context_isolation.py`, `test_sec001_predmet_ownership.py`, `test_beta_lockdown_zadaci_predmet_idor.py` | VERIFIED | **Zabranjeno reći „zaštićeno na nivou baze".** Aplikacija se povezuje service ključem koji RLS zaobilazi. Dozvoljeno je isključivo „razdvojeno po nalogu, pokriveno testovima". |
| 75 | FAQ 5 | Da li se moje pitanje i odgovor negde čuvaju? U evidenciju ulazi samo kriptografski otisak pitanja i odgovora, ne i njihov tekst. | `shared/ai_client.py:445-449`; `test_ai_fabric_governance.py::test_7_successful_call_writes_canonical_audit_without_content` | VERIFIED | Ne proširivati u „vaši podaci se ne koriste za treniranje" — to zavisi od ugovora sa dobavljačem i nije provereno. |
| 76 | FAQ 6 | Koji model Vindex koristi? Vindex koristi jednog dobavljača modela, a model je komponenta koju platforma koristi — ne sam proizvod. | `requirements.txt` (samo `openai`), `shared/ai_client.py:781-782`; `test_wave9_provider_isolation.py::test_a_izmereno_paket_nije_produkcijska_zavisnost` | VERIFIED | Zabranjeno: „koristimo GPT, Claude i Gemini", „Vindex ima sopstveni AI model". |
| 77 | FAQ 7 | Da li AI donosi odluku umesto mene? Ne. Brojeve koje vidite računa program, a AI ih obrazlaže; uz svaku procenu stoji da je reč o proceni modela, a ne o izračunatoj statistici. | `services/risk_engine.py`, `shared/case_readiness.py`, `routers/strategija.py:107-153` | PARTIALLY_VERIFIED | **Ne sme se reći „AI nikad ne presuđuje".** Ograničenje verdikta postoji samo u orkestratoru, ne i na tri samostalne rute. |
| 78 | FAQ 8 | Koliko je Vindex tačan? Tačnost nijedne funkcije još nije merena, pa nijedan procenat ne navodimo — merenje počinje sa zatvorenim testiranjem. | `evaluation/phase_0_5/PHASE_0_5_DECISION.md` | VERIFIED | — |
| 79 | FAQ 9 | Mogu li da izvezem svoje podatke? Da — jednim preuzimanjem dobijate arhivu sa svim svojim podacima, a ako neki deo ne može da se pročita, arhiva se odbacuje umesto da se isporuči nepotpuna. | `routers/data_export.py:66`, `:88-97`, FE `index.html:3478` → `vindex.js:808`; `test_sprint4_silent_failures.py` | VERIFIED | Arhiva sadrži evidenciju o dokumentima, **ne i same originalne fajlove** (`data_export.py:92`) — to mora biti navedeno uz odgovor. |
| 80 | FAQ 10 | Koliko košta? U ovoj fazi Vindex se ne prodaje; prijavljujete se za zatvoreno testiranje, a uslovi korišćenja se dogovaraju pojedinačno. | `static/vindex.js:124`, `routers/waitlist.py:143` | VERIFIED | — |
| 81 | Bezbednost | Podaci su razdvojeni po nalogu, provera vlasništva se izvršava u svakom upitu nad podacima, i ta granica je pokrivena testovima. | 541 filter `.eq("user_id", ...)` u 88 fajlova; `test_sec001_predmet_ownership.py`, `test_wave11_context_isolation.py`, `test_wave9_collaborator_boundary.py` | VERIFIED | **Zabranjeno: „zaštićeno na nivou baze", „RLS štiti vaše podatke", „bank-level", „military-grade".** |
| 82 | Bezbednost | Memorija kancelarije je u pretraživačkom indeksu razdvojena tvrdom pregradom — svaka kancelarija ima sopstveni prostor. | `shared/kancelarija_utils.py:45-58`; `test_institutional_memory_v2.py` | VERIFIED | Jedino mesto gde je razdvajanje pregrada, a ne uslov u upitu — smisleno je to i reći tako. |
| 83 | Bezbednost | Originalni fajl se šifruje pre nego što se sačuva. | `routers/smart_intake.py:97` (AES-GCM), `api.py:4784-4794`; `test_intake_original_file_storage.py` | VERIFIED | Bez naziva algoritma u marketinškom tonu i bez reči „neprobojno". |
| 84 | Bezbednost | Matični podaci klijenta se dešifruju samo ovlašćenim ulogama i svako otkrivanje se upisuje u evidenciju. | `klijenti/router.py:368`; `test_lambda003_klijenti_role_fail_closed.py` | VERIFIED | — |
| 85 | Bezbednost | Prava unutar kancelarije razdvojena su po ulogama; radnja bez ovlašćenja se odbija. | `routers/kancelarija.py:84-88` (HTTP 403 na 8 mesta); `test_kancelarija_seats.py::test_pozovi_non_admin_gets_403` | VERIFIED | Odnosi se na administratorske radnje kancelarije. Ne predstavljati kao punu matricu uloga — `shared/rbac.py` nema nijednog pozivaoca. |
| 86 | Bezbednost | Kod svake izmene koda izvršavaju se testovi na istoj verziji Pythona koju koristi produkcija i više nezavisnih unutrašnjih bezbednosnih provera. | `.github/workflows/tests.yml:2-8`, `:18-22`, `.github/workflows/security.yml` (gitleaks `:73`, bandit `:91`, pip-audit `:126`, semgrep `:139`) | VERIFIED | **Isključivo „unutrašnjih".** Zabranjeno implicirati reviziju treće strane, i zabranjeno reći „svi testovi prolaze" ili „zelena bezbednosna provera". |
| 87 | Bezbednost | Politika privatnosti, uslovi korišćenja, ugovor o obradi podataka, izjava o upotrebi AI-ja, bezbednosni pregled i bezbednosni list javno su dostupni. | `api.py:1509-1547` servira `privacy.html`, `terms.html`, `static/dpa.html`, `static/ai-disclosure.html`, `static/security.html`, `static/bezbednosni-list.html` | VERIFIED | Sekundarni poziv na akciju: „Preuzmite bezbednosni list". Zabranjeno reći „sertifikovani" ili „nezavisno revidirani". |
| 88 | Bezbednost | Nezavisne bezbednosne revizije i sertifikata nema; mehanizmi postoje i opisani su, potvrde treće strane ne. | Registry §8 | VERIFIED | Obavezan deo sekcije. |
| 89 | Bezbednost | Brisanjem naloga anonimizuju se vaši lični podaci, dok spisi ostaju sačuvani zbog obaveze čuvanja dokumentacije. | `routers/gdpr.py:201`, `:219-228`, `:250-253`; `test_gdpr_delete.py` | PARTIALLY_VERIFIED | Ograda je deo rečenice. **Ne sme se reći „brisanjem naloga svi podaci nestaju"** — brisanje je meko i ne poništava prijavu. |

---

# 2. ZABRANJENE FORMULACIJE

Nasleđeno iz `VINDEX_WEBSITE_CLAIMS_REGISTRY.md §10`, prošireno svime što je odbačeno
tokom pisanja gornje tabele. **Nijedna od ovih rečenica ne sme se pojaviti ni u jednom
obliku, ni kao parafraza.**

## 2.1 Nasleđeno iz registra

| Zabranjeno | Zašto |
|---|---|
| bilo koji procenat tačnosti AI-ja | nikad izmeren; okvir za merenje je prazan šablon |
| „štedi X sati" / „X% brže" | nema merenja |
| „koristimo GPT, Claude i Gemini" | produkcija koristi jednog dobavljača; ostali SDK-ovi nisu ni instalirani |
| „automatski bira najbolji model" | nije u upotrebi |
| „unakrsna provera između modela" | postoji samo ugovor, bez izvršavanja |
| „Vindex ima sopstveni AI model" | netačno |
| „GDPR usklađeni" / „sertifikovani" / „revidirano" | mehanizmi postoje, nezavisne potvrde nema |
| „potpuno bezbedno" / „100% sigurno" / „neprobojno" | neodrživo |
| „vaši podaci se ne koriste za treniranje" | zavisi od ugovora sa dobavljačem, neprovereno |
| „eliminiše ljudsku grešku" | suprotno pozicioniranju |
| „nikad više propuštenih rokova" | garancija ishoda |
| „verovatnoća ishoda" / „predviđa presudu" / „simulira sud" | nijedna tačnost izmerena; kod to sam naziva subjektivnom procenom |
| „procena verodostojnosti iskaza" | nikad validirano |
| korisnici, klijenti, partneri, preporuke, logotipi | ne postoje |
| bilo šta o kvalitetu OCR-a | nije mereno |
| bilo šta o brzini ili latenciji | nije mereno |
| pominjanje cene ili plana | ne postoji način da se plati |
| „kliknite do izvora" / „izvor na jedan klik" | citat nije klikabilan, deep-link ne postoji |
| „vidite iz kog dokumenta i sa koje strane" | spisak izvora nosi samo naziv propisa i član |
| „svaki odgovor navodi izvore" | ne važi za analizu dokumenata, nacrte ni nisku pouzdanost |
| „pravni operativni sistem" | kategorija je neodrživa |
| „počni besplatno" kao samouslužni tok | proizvod je pre-beta |
| „svi testovi prolaze" / „zelena bezbednosna provera" | scan tajni je namerno crven; PostgreSQL testovi se u CI-ju preskaču |
| „revizorski trag koji možete pregledati" | korisnički ekran evidencije ne postoji |

## 2.2 Novo — odbačeno u Fazi B

| Zabranjeno | Zašto |
|---|---|
| **„AI nikad ne presuđuje" / „platforma sprečava AI da donese odluku"** | ograničenje verdikta postoji samo u orkestratoru strategije; `/strategija/sudija`, `/strategija/sudija-v2` i `/strategija/litigation` vraćaju slobodan tekst bez serverske provere |
| **„zaštićeno na nivou baze" / „RLS štiti vaše podatke" / „bezbednost na nivou reda"** | aplikacija se povezuje service ključem koji RLS zaobilazi; stvarna granica je 541 ručni filter u kodu. Dozvoljeno isključivo: „razdvojeno po nalogu, pokriveno testovima" |
| **„bank-level security" / „military-grade enkripcija" / „enterprise-grade zaštita"** | prazne kategorije bez ijednog merila; opisuju se mehanizmi, ne pridevi |
| **„Vindex uči iz svih vaših predmeta" / „svaki predmet čini sistem pametnijim"** | memorija kancelarije se pretražuje samo u automatskoj analizi pri unosu dokumenta; 14 od 15 ruta institucionalnog učenja nema pozivaoca; memorija nacrta je u praksi prazna |
| **„semantička pretraga kroz celu vašu kartoteku"** | globalna pretraga u aplikaciji traži „sadrži reč" (`routers/search.py:232`); po smislu se pretražuju propisi i praksa, ne kartoteka |
| **bilo koji broj zakona, presuda ili dokumenata u bazi** | dve žive javne površine tvrde različito („18 zakona" i „847 zakona"); konačan broj presuda ne postoji u repou, uvoz je stao na tvrdim limitima |
| **„preuzmite PDF fakture"** | ruta traži token u zaglavlju, a link je običan `<a href>` → 401 pri kliku |
| **„označite fakturu kao plaćenu"** | ruta postoji, ekran ne |
| **„obrišite nalog i svi podaci nestaju"** | brisanje je meko, anonimizuje ime i email, i ne poništava prijavu |
| **„graf dokaza"** | oba dugmeta gađaju putanju koja na serveru ne postoji |
| **„brifing na e-poštu" / „jutarnji brifing"** | kartica je namerno uklonjena, a preostali kanal zavisi od spoljnog servisa koji nije deo dnevnog dispečera |
| **„obaveštenja na WhatsApp i Viber"** | oba modula su bez ijednog pozivaoca u celom repou |
| **„odgovor stiže u delovima dok se piše" (streaming)** | streaming ruta postoji, frontend je ne koristi, i taj put **ne nosi izvore** |
| **„SLA" / „dostupnost 99,9%"** | ništa od toga se ne meri |
| **„stil kancelarije poboljšava kvalitet nacrta"** | mehanizam radi, efekat nije meren |
| **„Founding Partner" / „doživotna cena" / „popust za osnivače"** | ne postoji nijedan komercijalni mehanizam u proizvodu |
| **„vaš nacrt se piše nad dokumentima predmeta"** | telo zahteva nikad ne nosi `predmet_id`; nacrt se piše iz opisa, propisa i prakse |
| **„pun postupak izrade za svih dvanaest vrsta podneska"** | šest vrsta trenutno ide kraćim putem |

---

# 3. TVRDNJE KOJE SU OTPALE

Šta bi marketing hteo, zašto nema dokaza, i šta je ostalo umesto toga.

| # | Šta bi marketing hteo | Zašto otpada | Šta sme umesto toga |
|---|---|---|---|
| 1 | „Vidite tačno iz kog dokumenta i sa koje strane potiče odgovor." | `_build_izvori` nosi samo `zakon` i `clan`; `doc_passages` nikad ne napušta backend | Red 43 + red 46 zajedno |
| 2 | „Klikom stižete do teksta propisa." | deep-link ne postoji; `static/vindex.js:922-923` izričito objašnjava zašto citat nije klikabilan | Red 61 (Vizija) |
| 3 | „Vindex uči iz svih predmeta vaše kancelarije i to znanje koristi u svakom odgovoru." | memorija kancelarije se pretražuje **samo** u auto-analizi pri unosu (`retrieve.py:1847-1852`, jedini pozivalac `api.py:5124`); 14 od 15 ruta institucionalnog učenja nema pozivaoca; memorija nacrta je u praksi prazna jer `predmet_id` nikad ne stiže | Red 30 + red 31 + red 35 |
| 4 | „Vaši podaci su zaštićeni na nivou baze." | 207 RLS politika je za backend mrtvo slovo — service ključ ih zaobilazi; 12 politika granice kancelarije ne pogađa nijedan red zbog neusaglašene vrednosti statusa | Red 74 + red 81 |
| 5 | „AI nikad ne presuđuje." | ograničenje verdikta samo u orkestratoru; tri samostalne rute vraćaju slobodan tekst, a promptovi izričito traže „USVAJA / ODBIJA" | Red 12 + red 77 |
| 6 | „Štedi X sati nedeljno" / „tačnost X%." | nijedno merenje ne postoji; okvir za merenje je prazan šablon od 2026-07-23 | Red 68 + red 78 |
| 7 | „Koristimo više AI modela i unakrsno ih proveravamo." | nula produkcionih poziva kroz taj sloj; ostali SDK-ovi nisu ni zavisnosti | Red 64 (samo Vizija) |
| 8 | „Revizorski trag koji možete pregledati." | mehanizam je dokazan, ekran ne postoji nigde | Red 55 + red 56 |
| 9 | „Počnite besplatno — 15 upita bez kartice." | krediti se dodeljuju jednom i ne obnavljaju se; `STRIPE_URL` je prazan; tri žive javne površine danas nude tri različite stvari | Red 4 + red 67 + red 80 |
| 10 | „GDPR usklađeni i nezavisno revidirani." | mehanizmi postoje, potvrde treće strane nema | Red 87 + red 88 |
| 11 | „Founding Partner program sa doživotnim uslovima i posebnom cenom." | **u proizvodu ne postoji nijedan komercijalni mehanizam** — ni cena, ni plaćanje, ni status naloga koji bi to nosio. Jedini dokazivi mehanizam je forma za prijavu | Red 69 + red 70 — razmena je pristup za primedbe, ne cena za novac |
| 12 | „Podsetnici stižu na e-poštu, SMS, WhatsApp i Viber." | WhatsApp i Viber rute nemaju nijednog pozivaoca; e-pošta i SMS zavise od spoljnog zakazivača i kredencijala kojih u razvoju nema | ništa — funkcija se izostavlja sa sajta u ovoj fazi |
| 13 | „Analiza iskaza svedoka i procena verodostojnosti." | nijedna validacija; i dalje stoji na `landing.html:948`, što je razlog više da se ukloni | ništa; sme samo kao deo reda 19 („alati za preispitivanje"), bez reči „verodostojnost" |
| 14 | „Graf dokaza vizuelno povezuje stranke, dokumente i tvrdnje." | dugme gađa putanju koja na serveru ne postoji | ništa |
| 15 | „Odgovor stiže u delovima, dok se piše." | streaming ruta postoji ali je frontend ne koristi, i **ne emituje izvore** — obećanje bi se srušilo prvim prebacivanjem | ništa; obaveza prikaza izvora mora se zapisati uz tu rutu pre nego što se ikad uključi |

---

# 4. POKRIVENOST

## 4.1 Brojke

| Mera | Vrednost |
|---|---|
| Ukupno javnih rečenica | **89** |
| `VERIFIED` | **73** |
| `PARTIALLY_VERIFIED` (ograda ugrađena u samu rečenicu) | **9** — redovi 3, 27, 28, 33, 50, 69, 71, 77, 89 |
| `ROADMAP` (samo „Vizija") | **4** — redovi 61, 62, 63, 64 |
| `OPISNO` (bez tvrdnje o proizvodu) | **3** — redovi 5, 6, 7 |
| Sekcija pokriveno | **16 od 16** |
| Sekcija koje stoje **bez ijednog dokaza** | **1** — „Founding Partner" |

Zbir: 73 + 9 + 4 + 3 = 89.

## 4.2 Po sekcijama

| Sekcija | Redova | Najjača rečenica | Stanje |
|---|---|---|---|
| Hero | 4 | red 1 + red 2 | pokriveno |
| Problem | 3 | — | opisno, bez tvrdnji |
| Kako radi | 4 | red 10 | pokriveno |
| Zašto verovati | 3 | red 12 | pokriveno, sve tri nose ogradu u koloni Ograničenje |
| Šta radi danas | 6 | red 17 | pokriveno |
| Dokumenti | 8 | red 22 | pokriveno |
| Predmet i kancelarijsko znanje | 7 | red 29 | pokriveno; red 30 je jedina dozvoljena granica |
| AI analiza | 7 | red 37 | pokriveno |
| Izvori i poverenje | 6 | red 45 | pokriveno; redovi 46 i 47 su **obavezni**, bez njih sekcija laže |
| Governance | 8 | red 52 | pokriveno |
| Za advokate | 4 | red 59 | pokriveno |
| Vizija | 4 | red 64 | pokriveno, sve `ROADMAP` |
| Beta | 4 | red 65 | pokriveno |
| **Founding Partner** | 2 | red 69 | **bez dokaza za ponudu** |
| FAQ | 10 | red 72 | pokriveno; v. napomenu 4.3 |
| Bezbednost | 9 | red 81 | pokriveno |

## 4.3 Dve strukturne napomene

**1. „Founding Partner" nema pokriće ni za jednu komercijalnu rečenicu.**
U repou ne postoji ni cena, ni način plaćanja, ni status naloga koji bi nosio bilo kakav
„partner" nivo. Sve što je dokazivo jeste da postoji forma za prijavu na zatvoreno
testiranje (`routers/waitlist.py:143`). Sekcija je zato održiva **samo kao razmena
pristupa za primedbe**, nikad kao ponuda. Paralelno je nastao sestrinski dokument
`docs/website/FOUNDING_PARTNER.md` sa istim zaključkom; redovi 69 i 70 su usklađeni s
njim i **imaju prednost** kao doslovan tekst za sajt. Sve što je u tom dokumentu
označeno kao `ODLUKA VLASNIKA` ne pojavljuje se na sajtu dok odluka ne padne.

**2. FAQ je u `CONTENT_MAP §3` označen kao „NE praviti sada".**
Redovi 71–80 su napisani i spremni, ali ih treba ugraditi **kao odgovore uz odgovarajuće
sekcije početne strane** (posebno „Izvori i poverenje" i „Bezbednost"), a ne kao zasebnu
FAQ stranu — dok vlasnik ne odluči drugačije. Sadržaj je isti; nosač je drugi.

## 4.4 Šta ostaje kao uslov pre objave

Iz Faze A, i dalje otvoreno — nije rešeno ovim dokumentom:

1. **Prikaz izvora nije pokriven automatskim testom** (`_vxRenderIzvori`). Pre snimka
   ekrana ili tvrdnje „korisnik ovo vidi" potrebna je jedna živa provera.
2. **Pravni identitet firme** (naziv, PIB, matični broj, adresa) nije zapisan nigde u
   repozitorijumu, a postojeće javne strane koriste domen koji se razlikuje od
   produkcionog. Mora biti usaglašeno pre objave.
3. **Tri žive javne površine i dalje govore tri različite stvari** o tome da li se
   proizvod plaća. Sajt to mora zatvoriti, ne zaobići.
