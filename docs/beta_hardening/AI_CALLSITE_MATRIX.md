# AI CALL-SITE MATRIX — Vindex AI

**Program:** BETA-HARDENING-001 · **Agent 1 — Call-Site Forensics**
**Baseline commit:** `6fb4a99f`
**Metod:** statička inventura (`git ls-files` + AST) + runtime verifikacija zakrpe u svežem Python procesu
**Obim:** produkcijski Python; isključeni `tests/`, `docs/`, `scripts/`, `migrations/`, `evaluation/`, `data/`
**Izmene produkcijskog koda:** nula — ovaj dokument je jedini novi fajl

---

## 0. Rezime

| Metrika | Vrednost |
|---|---|
| Produkcijskih fajlova sa AI *tragom* (uvoz / pomen / konstanta) | **90** |
| Produkcijskih fajlova sa **izvršnim** AI call-site-om | **70** |
| Ukupno izvršnih AI call-site-ova | **103** |
| `VERIFIED` | **76** |
| `PARTIAL` | **15** |
| `BYPASS` | **12** |
| `UNKNOWN` | **0** |
| `DUPLICATE` | **0** |

### Ocena tvrdnje „81 produkcijski fajl" — **OBORENA**

Filter `openai|OpenAI|langchain|anthropic|generativeai|cohere|litellm|ollama|gpt-4|gpt-3|whisper|embedding`
nad praćenim `.py` fajlovima bez `tests/ docs/ scripts/ migrations/` daje **90**, ne 81.

Reprodukcija:

```bash
git ls-files '*.py' | grep -vE '^(tests|docs|scripts|migrations)/' \
  | xargs grep -lE 'openai|OpenAI|langchain|anthropic|generativeai|cohere|litellm|ollama|gpt-4|gpt-3|whisper|embedding' \
  | sort | wc -l      # -> 90
```

Ali „fajl sa AI tragom" nije jedinica rizika. Od 90 fajlova samo **70** stvarno
izvršava AI poziv; ostalih 20 su tipovi (`shared/commander_schema.py`), cenovnici
modela (`shared/cost.py`, `shared/usage.py`), retry omotač (`shared/llm_retry.py`),
`security/*` moduli koji kapiju **opisuju** ali je ne zovu, i ruteri koji pominju
`embedding` u imenu kolone. Merena jedinica u ovoj matrici je **call-site**, ne fajl.

---

## 1. Kanonska kapija — runtime dokaz

Sveži proces, `import shared.ai_client; _patch_prompt_guard()`:

```
governance_status: {'attempted': True, 'active': True, 'ai_blocked': False,
                    'ai_block_method': None, 'ai_block_reason': None, 'failure_reason': None}

Completions.create          _vindex_guarded = True
AsyncCompletions.create     _vindex_guarded = True
Embeddings.create           _vindex_guarded = True
AsyncEmbeddings.create      _vindex_guarded = True
Transcriptions.create       _vindex_guarded = True
AsyncTranscriptions.create  _vindex_guarded = True
Speech.create               _vindex_guarded = True
AsyncSpeech.create          _vindex_guarded = True
```

Potvrđeno: pojedinačni `client.chat.completions.create(...)` **nije** bypass —
zakrpa je na klasi, pa svaka instanca prolazi kroz nju.

### 1.1 Šta zakrpa NE pokriva (runtime provereno, isti proces)

```
Responses.create        _vindex_guarded = False
AsyncResponses.create   _vindex_guarded = False
Moderations.create      _vindex_guarded = False
Images.generate         _vindex_guarded = False
```

**Ovo je latentna, ne aktivna rupa.** Produkcijski kod danas ne koristi nijednu
od ovih metoda:

```bash
git ls-files '*.py' | grep -vE '^(tests|docs|migrations|scripts)/' \
  | xargs grep -nE '\.responses\.create|\.moderations\.|\.images\.|client\.beta\.'
# -> 0 pogodaka
```

Rizik nije današnji poziv nego to što ne postoji nijedan signal koji bi budući
`client.responses.create(...)` označio kao izlazak iz kapije. OpenAI SDK 2.29.0
(`requirements.txt:4`) Responses API već ima; `langchain_openai` 1.1.14 ga zove
na tri mesta (`chat_models/base.py:1263,1481,1485`) kad je `use_responses_api`
uključen. Vindex tu granu ne koristi jer ne koristi `ChatOpenAI` (v. §4).

### 1.2 Pokrivenost po modalitetu

| Modalitet | Prompt Guard | Response Firewall | Provenance | Timeout 60 s |
|---|---|---|---|---|
| `chat.completions` | **DA** | **DA** | DA | DA |
| `embeddings` | NE — namerno, `shared/ai_client.py:806-822` | NE — vektor nije odgovor | DA | DA (Wave 9/C5) |
| `audio.transcriptions` | N/P — ulaz su bajtovi | **NE** | DA (bez sadržaja) | DA |
| `audio.speech` | N/P | **NE** | DA (bez sadržaja) | DA |

Posledica reda „audio STT": `POST /api/voice/transcribe` (`routers/voice.py:401`)
vraća Whisper transkript **direktno pozivaocu**, bez prolaska kroz Response
Firewall i bez ijednog naknadnog chat poziva koji bi ga filtrirao. Izlaz modela
izlazi iz sistema neproveren. To je `PARTIAL`, ne `BYPASS` — poziv jeste prošao
kroz zakrpu i jeste knjižen — ali je jedina rupa u izlaznoj kontroli koja se
danas stvarno izvršava na korisničkom zahtevu.

---

## 2. Matrica

Legenda:
* **VERIFIED** — ide kroz zakrpljenu SDK metodu, kompletan lanac za svoj modalitet
* **PARTIAL** — ide kroz zakrpu, ali jedna kontrola nedostaje po ugovoru (embeddings / audio)
* **BYPASS** — može da se izvrši a da ne prođe kroz zakrpljenu metodu
* **DUPLICATE / UNKNOWN** — nijedan slučaj

| ID | Fajl:linija | Funkcija | AI operacija | Ulazna tačka | Kroz zakrpu? | Governance | Firewall | Audit | Provenance | Correlation | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AI-001 | `api.py:517` | `_pozovi_openai_sync_api` | chat | centralni omotači + admin dijagnostika | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-002 | `api.py:525` | `_pozovi_openai_async_api` | chat | centralni omotači + admin dijagnostika | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-003 | `api.py:2332` | `_run` | embedding (langchain) | centralni omotači + admin dijagnostika | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-004 | `api.py:2405` | `_run_checks` | embedding (langchain) | centralni omotači + admin dijagnostika | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-005 | `api.py:5349` | `_call_procena` | chat | centralni omotači + admin dijagnostika | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-006 | `api.py:5359` | `_call_hronologija` | chat | centralni omotači + admin dijagnostika | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-007 | `api.py:5381` | `_call_metapodaci` | chat | centralni omotači + admin dijagnostika | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-008 | `app/services/retrieve.py:506` | `_pozovi_chat_api` | chat | biblioteka — pozivaju je ruteri koji je uvoze | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-009 | `app/services/retrieve.py:720` | `_ugradi_query` | embedding (langchain) | biblioteka — pozivaju je ruteri koji je uvoze | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-010 | `app/services/retrieve.py:1385` | `_cohere_rerank` | cohere rerank | biblioteka — pozivaju je ruteri koji je uvoze | **NE** | **NE** | **NE** | sesijski (hash) | sesijski (hash) | DA | **BYPASS** |
| AI-011 | `app/services/retrieve.py:2238` | `_prosiri_query_gpt_wrapper` | chat | biblioteka — pozivaju je ruteri koji je uvoze | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-012 | `debug_rag.py:41` | `main` | embedding (langchain) | `python debug_rag.py` (`__main__`) **i** uvoz iz api.py | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **BYPASS** |
| AI-013 | `drafting/playbook.py:68` | `ingest_playbook` | embedding (langchain) | biblioteka — pozivaju je ruteri koji je uvoze | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-014 | `drafting/playbook.py:99` | `search_playbook` | embedding (langchain) | biblioteka — pozivaju je ruteri koji je uvoze | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-015 | `drafting/router.py:80` | `_call_openai` | chat | biblioteka — pozivaju je ruteri koji je uvoze | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-016 | `ingest_kz.py:49` | `_embed_batch` | embedding | `python ingest_kz.py` (`__main__`) **i** uvoz iz api.py | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **BYPASS** |
| AI-017 | `ingest_kz.py:64` | `delete_kz_vectors` | embedding (langchain) | `python ingest_kz.py` (`__main__`) **i** uvoz iz api.py | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **BYPASS** |
| AI-018 | `ingest_kz.py:158` | `verify` | embedding (langchain) | `python ingest_kz.py` (`__main__`) **i** uvoz iz api.py | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **BYPASS** |
| AI-019 | `ingest_laws.py:227` | `_embed_batch` | embedding | `python ingest_laws.py` (`__main__`) **i** uvoz iz api.py | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **BYPASS** |
| AI-020 | `ingest_misljenja.py:150` | `_embed_batch` | embedding (langchain) | `python ingest_misljenja.py` (`__main__`) **i** uvoz iz api.py | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **BYPASS** |
| AI-021 | `interni_stavovi.py:62` | `ingest_stav` | embedding (langchain) | biblioteka — pozivaju je ruteri koji je uvoze | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-022 | `interni_stavovi.py:94` | `search_stavovi` | embedding (langchain) | biblioteka — pozivaju je ruteri koji je uvoze | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-023 | `klijenti/router.py:1277` | `intake_wizard` | chat | rute `prefiks u api.py` (20) → `intake_wizard` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-024 | `main.py:2305` | `_pozovi_openai` | chat | `python main.py` (`__main__`) **i** uvoz iz api.py | DA | Prompt Guard | DA | DA | DA | DA | **BYPASS** |
| AI-025 | `nacrti/checklist_engine.py:44` | `_pozovi_checklist_api` | chat | biblioteka — pozivaju je ruteri koji je uvoze | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-026 | `routers/auto_discovery.py:164` | `_embed_chunks` | embedding | rute `prefiks u api.py` (4) → `_embed_chunks` | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-027 | `routers/batch_ingest.py:55` | `_embed` | embedding | rute `prefiks u api.py` (5) → `_embed` | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-028 | `routers/case_commander.py:348` | `_pozovi_commander_api` | chat | rute `prefiks u api.py` (5) → `_pozovi_commander_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-029 | `routers/case_commander.py:672` | `_pozovi_cross_case_api` | chat | rute `prefiks u api.py` (5) → `_pozovi_cross_case_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-030 | `routers/case_dna.py:215` | `_pozovi_genome_api` | chat | rute `/api/predmeti` (4) → `_pozovi_genome_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-031 | `routers/case_dna.py:1210` | `_pozovi_compare_api` | chat | rute `/api/predmeti` (4) → `_pozovi_compare_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-032 | `routers/case_intelligence.py:42` | `_pozovi_briefing_api` | chat | rute `/api/intelligence` (2) → `_pozovi_briefing_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-033 | `routers/cio.py:224` | `_pozovi_cio_api` | chat | rute `/api/cio` (3) → `_pozovi_cio_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-034 | `routers/client_twin.py:140` | `_pozovi_twin_api` | chat | rute `/api/client-twin` (5) → `_pozovi_twin_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-035 | `routers/copilot.py:53` | `_pozovi_gpt4o_mini` | chat | rute `prefiks u api.py` (1) → `_pozovi_gpt4o_mini` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-036 | `routers/corrections.py:62` | `_pozovi_correction_api` | chat | rute `/api/corrections` (4) → `_pozovi_correction_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-037 | `routers/court_predictor.py:146` | `_pozovi_predictor_api` | chat | rute `prefiks u api.py` (9) → `_pozovi_predictor_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-038 | `routers/court_predictor.py:552` | `_pozovi_battle_report_api` | chat | rute `prefiks u api.py` (9) → `_pozovi_battle_report_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-039 | `routers/court_predictor.py:712` | `_pozovi_hearing_prep_api` | chat | rute `prefiks u api.py` (9) → `_pozovi_hearing_prep_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-040 | `routers/court_predictor.py:907` | `_pozovi_arg_reputation_api` | chat | rute `prefiks u api.py` (9) → `_pozovi_arg_reputation_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-041 | `routers/court_predictor.py:1138` | `_pozovi_judge_profile_api` | chat | rute `prefiks u api.py` (9) → `_pozovi_judge_profile_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-042 | `routers/court_predictor.py:1317` | `_pozovi_opponent_intel_api` | chat | rute `prefiks u api.py` (9) → `_pozovi_opponent_intel_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-043 | `routers/court_predictor.py:1582` | `_pozovi_confidence_api` | chat | rute `prefiks u api.py` (9) → `_pozovi_confidence_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-044 | `routers/cross_doc.py:38` | `_pozovi_cross_doc_api` | chat | rute `prefiks u api.py` (2) → `_pozovi_cross_doc_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-045 | `routers/decision_replay.py:233` | `_pozovi_replay_api` | chat | rute `/api/predmeti` (2) → `_pozovi_replay_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-046 | `routers/digital_twin.py:56` | `_pozovi_twin_api` | chat | rute `/api/twin` (3) → `_pozovi_twin_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-047 | `routers/doc_templates.py:54` | `_pozovi_doc_template_api` | chat | rute `/api/doc-templates` (3) → `_pozovi_doc_template_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-048 | `routers/dokument.py:75` | `_pozovi_klasifikacija_api` | chat | rute `prefiks u api.py` (6) → `_pozovi_klasifikacija_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-049 | `routers/drafting.py:100` | `_pozovi_drafting_api` | chat | rute `prefiks u api.py` (15) → `_pozovi_drafting_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-050 | `routers/drafting.py:437` | `_pozovi_kriticara` | chat | rute `prefiks u api.py` (15) → `_pozovi_kriticara` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-051 | `routers/evidence.py:67` | `_pozovi_evidence_api` | chat | rute `/api/evidence` (4) → `_pozovi_evidence_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-052 | `routers/evidence_graph.py:115` | `_pozovi_eg_api` | chat | rute `/api/evidence-graph` (3) → `_pozovi_eg_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-053 | `routers/health_index.py:31` | `_pozovi_chief_partner_api` | chat | rute `prefiks u api.py` (1) → `_pozovi_chief_partner_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-054 | `routers/hearing_cc.py:41` | `_pozovi_hcc_api` | chat | rute `prefiks u api.py` (3) → `_pozovi_hcc_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-055 | `routers/intake.py:81` | `_pozovi_intake_api` | chat | rute `prefiks u api.py` (7) → `_pozovi_intake_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-056 | `routers/integracije.py:122` | `_pozovi_integracije_api` | chat | rute `prefiks u api.py` (10) → `_pozovi_integracije_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-057 | `routers/knowledge_base.py:56` | `_pozovi_kb_embed_api` | embedding | rute `prefiks u api.py` (5) → `_pozovi_kb_embed_api` | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-058 | `routers/knowledge_base.py:63` | `_pozovi_kb_tag_api` | chat | rute `prefiks u api.py` (5) → `_pozovi_kb_tag_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-059 | `routers/knowledge_transfer.py:45` | `_pozovi_kt_api` | chat | rute `/api/knowledge` (8) → `_pozovi_kt_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-060 | `routers/law_upload.py:84` | `_embed` | embedding | rute `prefiks u api.py` (3) → `_embed` | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-061 | `routers/learning.py:41` | `_pozovi_learning_api` | chat | rute `/api/learning` (16) → `_pozovi_learning_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-062 | `routers/matter_intel.py:34` | `_pozovi_matter_intel_api` | chat | rute `/api/matter-intel` (3) → `_pozovi_matter_intel_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-063 | `routers/memory_graph.py:47` | `_pozovi_mg_api` | chat | rute `/api/memory-graph` (4) → `_pozovi_mg_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-064 | `routers/morning_briefing.py:53` | `_pozovi_briefing_sync_api` | chat | rute `prefiks u api.py` (9) → `_pozovi_briefing_sync_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-065 | `routers/morning_briefing.py:60` | `_pozovi_briefing_async_api` | chat | rute `prefiks u api.py` (9) → `_pozovi_briefing_async_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-066 | `routers/multi_agent.py:333` | `_pozovi_router_api` | chat | rute `/api/agents` (4) → `_pozovi_router_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-067 | `routers/multi_agent.py:349` | `_pozovi_agent_api` | chat | rute `/api/agents` (4) → `_pozovi_agent_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-068 | `routers/multi_agent.py:367` | `_pozovi_para_api` | chat | rute `/api/agents` (4) → `_pozovi_para_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-069 | `routers/oblasti.py:179` | `_gpt_call` | chat | rute `prefiks u api.py` (3) → `_gpt_call` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-070 | `routers/outcome_intel.py:27` | `_pozovi_outcome_intel_api` | chat | rute `/api/outcome-intel` (1) → `_pozovi_outcome_intel_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-071 | `routers/praksa.py:347` | `_pozovi_ratio_api` | chat | rute `prefiks u api.py` (7) → `_pozovi_ratio_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-072 | `routers/praksa.py:483` | `_pozovi_uporedi_api` | chat | rute `prefiks u api.py` (7) → `_pozovi_uporedi_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-073 | `routers/praksa.py:707` | `_pozovi_argument_map_api` | chat | rute `prefiks u api.py` (7) → `_pozovi_argument_map_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-074 | `routers/praksa.py:830` | `_pozovi_slicni_api` | chat | rute `prefiks u api.py` (7) → `_pozovi_slicni_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-075 | `routers/precedenti.py:30` | `_pozovi_precedenti_api` | chat | rute `/api/precedenti` (1) → `_pozovi_precedenti_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-076 | `routers/profitabilnost.py:47` | `_pozovi_profit_api` | chat | rute `/api/profitabilnost` (4) → `_pozovi_profit_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-077 | `routers/proof.py:101` | `_test_openai` | embedding | rute `/api/admin` (1) → `_test_openai` | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-078 | `routers/region.py:39` | `_pozovi_region_api` | chat | rute `prefiks u api.py` (4) → `_pozovi_region_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-079 | `routers/strategija.py:84` | `_pozovi_strategija_v2_api` | chat | rute `/strategija` (9) → `_pozovi_strategija_v2_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-080 | `routers/strategy_simulator.py:104` | `_pozovi_gpt` | chat | rute `/api/simulator` (4) → `_pozovi_gpt` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-081 | `routers/style_checker.py:42` | `_pozovi_style_api` | chat | rute `/api/style` (7) → `_pozovi_style_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-082 | `routers/voice.py:38` | `_pozovi_voice_chat_api` | chat | rute `/api/voice` (4) → `_pozovi_voice_chat_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-083 | `routers/voice.py:45` | `_pozovi_whisper_api` | audio STT | rute `/api/voice` (4) → `_pozovi_whisper_api` | DA | N/P (bajtovi) | **NE** | DA | DA | DA | **PARTIAL** |
| AI-084 | `routers/voice.py:52` | `_pozovi_tts_api` | audio TTS | rute `/api/voice` (4) → `_pozovi_tts_api` | DA | N/P (bajtovi) | **NE** | DA | DA | DA | **PARTIAL** |
| AI-085 | `routers/web3.py:616` | `_call_gpt` | chat | rute `prefiks u api.py` (12) → `_call_gpt` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-086 | `routers/zadaci.py:51` | `_pozovi_zadaci_api` | chat | rute `/api/zadaci` (9) → `_pozovi_zadaci_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-087 | `routers/zakon_monitoring.py:54` | `_pozovi_zakon_api` | chat | rute `/api/zakon-monitoring` (5) → `_pozovi_zakon_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-088 | `routers/zastarelost.py:33` | `_pozovi_guardian_api` | chat | rute `prefiks u api.py` (9) → `_pozovi_guardian_api` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-089 | `scrape_zdi_mca.py:111` | `generisi_embedding` | embedding | `python scrape_zdi_mca.py` (`__main__`) **i** uvoz iz api.py | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **BYPASS** |
| AI-090 | `services/agent_tasks/precedents_radar.py:51` | `_pozovi_klasifikaciju` | chat | cron `/api/cron/daily` → `workers/background_agents` | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-091 | `services/ambient_analyzer.py:62` | `_pozovi_sugestije_api` | chat | biblioteka — pozivaju je ruteri koji je uvoze | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-092 | `services/case_pipeline.py:37` | `_pozovi_pipeline_api` | chat | biblioteka — pozivaju je ruteri koji je uvoze | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-093 | `services/learning_engine.py:35` | `_pozovi_learning_engine_api` | chat | biblioteka — pozivaju je ruteri koji je uvoze | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-094 | `services/legal_reasoning_engine.py:177` | `_pozovi_reasoning_api` | chat | biblioteka — pozivaju je ruteri koji je uvoze | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-095 | `services/voice_orchestrator.py:379` | `_connect_openai_realtime` | realtime WS | WS `/api/voice-rt/ws` | **NE** | **NE** | **NE** | sesijski | sesijski | DA | **BYPASS** |
| AI-096 | `shared/ai_fabric.py:263` | `generate` | chat | **NEDOSTIŽNO** — nijedan produkcijski uvoz | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-097 | `shared/ai_fabric.py:320` | `generate` | anthropic | **NEDOSTIŽNO** — nijedan produkcijski uvoz | **NE** | **NE** | **NE** | **NE** | **NE** | **NE** | **BYPASS** |
| AI-098 | `shared/ai_fabric.py:378` | `generate` | gemini | **NEDOSTIŽNO** — nijedan produkcijski uvoz | **NE** | **NE** | **NE** | **NE** | **NE** | **NE** | **BYPASS** |
| AI-099 | `shared/intake_classify.py:30` | `_pozovi_classify_api` | chat | biblioteka — pozivaju je ruteri koji je uvoze | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-100 | `shared/intake_extract.py:34` | `_pozovi_extract_api` | chat | biblioteka — pozivaju je ruteri koji je uvoze | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-101 | `strategija.py:21` | `_pozovi_strategija_api` | chat | biblioteka — pozivaju je ruteri koji je uvoze | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |
| AI-102 | `uploaded_doc/ingest.py:75` | `ingest_session` | embedding (langchain) | biblioteka — pozivaju je ruteri koji je uvoze | DA | N/P (namerno) | N/P (vektor) | DA | DA | DA | **PARTIAL** |
| AI-103 | `web3_compliance.py:24` | `_pozovi_web3_api` | chat | biblioteka — pozivaju je ruteri koji je uvoze | DA | Prompt Guard | DA | DA | DA | DA | **VERIFIED** |

---

## 3. Potvrđeni BYPASS-evi — poimence, sa dokazom

### BYPASS-1 · `main.py` CLI mod — ceo RAG agent bez ijedne kontrole

**`main.py:4243`** (`if __name__ == "__main__":` — interaktivni CLI) → **`main.py:2305`**
(`_pozovi_openai` → `_get_client().chat.completions.create(**kwargs)`).

`main.py` ne uvozi `api` i nigde ne zove `_patch_prompt_guard()`. Runtime dokaz,
svež proces:

```
$ python -c "import main; ..."
DOKAZ (import main, bez import api):
  Completions.create._vindex_guarded = False
  Embeddings.create._vindex_guarded  = False
  governance_status = {'attempted': False, 'active': False, 'ai_blocked': False, ...}
```

`attempted=False` je ključan: nije reč o guard-u koji je pao (tada bi se
`_install_ai_kill_switch` aktivirao i poziv bi bio odbijen), nego o guard-u koji
**nikad nije ni pokušan**. Fail-closed brana ne postoji, `openai.OpenAI` nije
otrovan, klijent se konstruiše normalno i poziv prolazi. Nula prompt guard-a,
nula Response Firewall-a, nula provenance reda, nula timeout-a, nula correlation
ID-a.

*Ublažavanje:* produkcijski entrypoint je `gunicorn api:app` (`Procfile:1`) i
`uvicorn api:app` (`Dockerfile` CMD) — u oba slučaja `api.py:28` instalira zakrpu.
CLI mod je razvojni. Ali kanal postoji i ništa ga ne sprečava.

### BYPASS-2..6 · standalone ingest/dijagnostika skripte (isti mehanizam)

Svaka ima `__main__` blok, nijedna ne uvozi `api`, nijedna ne zove
`_patch_prompt_guard()`:

| Fajl:linija | Poziv |
|---|---|
| `debug_rag.py:41` | `OpenAIEmbeddings.embed_query` |
| `ingest_kz.py:49` | `client.embeddings.create` |
| `ingest_kz.py:64`, `ingest_kz.py:158` | `OpenAIEmbeddings.embed_query` |
| `ingest_laws.py:227` | `client.embeddings.create` |
| `ingest_misljenja.py:150` | `OpenAIEmbeddings.embed_documents` |
| `scrape_zdi_mca.py:111` | `client.embeddings.create` |

Isti runtime dokaz kao BYPASS-1 (`_vindex_guarded = False` u procesu bez `import api`).
Uticaj je manji nego kod `main.py` — embeddings ionako nemaju prompt guard ni
firewall po ugovoru — ali se gubi **provenance i timeout**: masovni ingest u
Pinecone se izvršava bez ijednog reda u `ai_forensics`.

### BYPASS-7 · Realtime WebSocket — jedini aktivni bypass na korisničkom zahtevu

**`services/voice_orchestrator.py:379`** (`_connect_openai_realtime` →
`websockets.connect(wss://api.openai.com/v1/realtime?model=...)`),
ulazna tačka **`routers/voice_realtime.py:139-140`** (`@router.websocket("/ws")`).

Ne koristi OpenAI SDK uopšte — sirov WebSocket, hardkodovan URL
(`services/voice_orchestrator.py:46`). Zakrpa je na SDK klasama i nema šta da
presretne.

Šta konkretno nedostaje:
* **Prompt Guard** — nema. Korisnikov govor i `input_audio_transcription`
  (`:228`, `whisper-1`) idu modelu neprovereni.
* **Response Firewall** — nema. `response.audio.delta` i transcript delte se
  prosleđuju pravo u browser (`:269`, `:277`).
* **Provenance** — samo **sesijski** red (`_uknjizi_voice_sesiju_provenance`,
  `:143-185`), bez ijednog karaktera sadržaja i bez po-poruka granularnosti.
* **Timeout** — nema `_with_timeout`; sesija je trajna.

Ovo je jedini bypass koji se izvršava na običan korisnički zahtev u produkciji.
Kod ga **imenuje kao ugovor**, ne kao propust (`shared/ai_client.py:672-675`),
i ima ozbiljno ublažavanje: `:352-372` fail-closed odbija sesiju kad je Azure/EU
konfiguracija aktivna. Ali „dokumentovano" nije „kontrolisano".

### BYPASS-8 · Cohere rerank

**`app/services/retrieve.py:1385`** (`_cohere_rerank` → `co.rerank(...)`).
Drugi SDK (`cohere.Client`), sopstveni transport.

* Provenance: **postoji** — `_uknjizi_cohere_provenance` (`:564`) piše u istu
  `ai_forensics` tabelu, isti `correlation_id`, upit kao SHA-256.
* Prompt Guard / Firewall: nema (rerank nije generativan poziv).

**Praktično je mrtav u produkciji** — trostruka kapija `_cohere_dozvoljen()`
(`:532-549`): paket instaliran **I** `COHERE_API_KEY` **I** eksplicitan
`VINDEX_COHERE_RERANK` opt-in. Prvi uslov sam po sebi ne prolazi: `cohere` **nije
u `requirements.txt`**, a Docker image instalira isključivo iz njega
(`Dockerfile:13`). Fallback je `_gpt_rerank` — upravljan OpenAI poziv.

### BYPASS-9, 10 · `shared/ai_fabric.py` — Anthropic i Gemini adapteri

* **`shared/ai_fabric.py:320`** — `anthropic.Anthropic(...).messages.create(**kw)`
* **`shared/ai_fabric.py:378`** — `genai.GenerativeModel(...).generate_content(...)`

Drugi SDK-ovi, sopstveni transport, **nula** governance-a: nema prompt guard-a,
nema firewall-a, nema provenance-a, nema correlation-a. Zakrpa ih strukturno ne
može dohvatiti.

**Modul je mrtav kod.** Nijedan produkcijski fajl ga ne uvozi:

```bash
git ls-files '*.py' | xargs grep -nE '^\s*(from|import)\s+shared\.ai_fabric'
# -> samo tests/test_ai_fabric_contract.py, tests/test_ai_fabric_governance.py
```

(`shared/audit_immutable.py:211` sadrži samo string `"ai_fabric_call"` u registru
dozvoljenih akcija — nije uvoz.) Dodatno, `anthropic` i `google-generativeai`
nisu u `requirements.txt`, pa u produkcionom image-u ni `import` ne bi prošao.

**Ali kapija tog modula ima realnu grešku, nezavisno od dostižnosti.**
`_govern_request()` (`shared/ai_fabric.py:534-537`) tvrdi da primenjuje postojeći
prompt guard:

```python
try:
    from security.prompt_guard import sanitize_prompt  # type: ignore
    request.prompt = sanitize_prompt(request.prompt)
except ImportError:
    pass
```

`security/prompt_guard.py` **nema** `sanitize_prompt` — ima samo `analyze`
(`security/prompt_guard.py:159`). Runtime dokaz:

```
ImportError: cannot import name 'sanitize_prompt' from 'security.prompt_guard'
```

`except ImportError: pass` guta grešku, pa je jedini bezbednosni korak
provider-neutralne kapije **tihi no-op** — i za OpenAI granu (`:263`) i za
Anthropic/Gemini grane. Da je Fabric ikad uključen, kapija bi tvrdila zaštitu koju
ne pruža. Za OpenAI granu SDK zakrpa i dalje hvata poziv; za druge dve ne hvata
ništa. Ovo već jeste zabeleženo u `tests/test_ai_fabric_governance.py:112`, ali
kao **test koji čuva postojeće stanje**, ne kao otvorena stavka.

### Knjigovodstvo

`ingest_kz.py` nosi tri call-site-a a `main.py` jedan — u tabeli su prebrojani
pojedinačno, pa je ukupan zbir `BYPASS` **redova** 12 uz **10 opisanih mehanizama**.

---

## 4. LangChain sloj — **ide KROZ zakrpu** (empirijski dokaz)

Deset produkcijskih uvoza `langchain_openai`, **svi su `OpenAIEmbeddings`**.
Nijedan `ChatOpenAI`, nijedan `AzureChatOpenAI`:

```bash
git ls-files '*.py' | grep -vE '^(tests|docs|scripts|migrations)/' \
  | xargs grep -nE '^\s*(from|import)\s+langchain'
# -> 10 pogodaka, svi 'from langchain_openai import OpenAIEmbeddings'
```

**Zašto prolazi kroz zakrpu.** `langchain_openai` nema sopstveni transport —
konstruiše OpenAI SDK klijent i drži referencu na `Embeddings` resurs:

* `langchain_openai/embeddings/base.py:432` — `self.client = openai.OpenAI(**client_params, **sync_specific).embeddings`
* poziva ga na `:618`, `:633`, `:740` kao `self.client.create(...)`

`self.client` je instanca `Embeddings`; `.create` se razrešava na **klasi**, a
zakrpa je upravo tamo. Konstrukcija ide preko `openai.OpenAI`, što je i tačka
koju `_install_ai_kill_switch` truje ako guard padne — fail-closed važi i za
LangChain.

**Empirijski dokaz** (`shared.ai_client._orig_embed` zamenjen špijunom, bez mrežnog poziva):

```
DOKAZ: langchain OpenAIEmbeddings -> zakrpljena Embeddings.create: True
kwargs koje je zakrpa videla: {'input': ['probni tekst'],
                               'model': 'text-embedding-3-large',
                               'timeout': 60.0}
```

`timeout: 60.0` nije prosleđen iz LangChain-a — ubacio ga je `_with_timeout()`
iz zakrpe. To je nezavisna potvrda da je poziv prošao kroz wrapper, a ne samo
kroz istoimenu metodu.

**Zapažena latentna rupa.** `ChatOpenAI` (koji Vindex **ne** koristi) ima tri
grane koje bi zaobišle `Completions.create`:
`chat_models/base.py:1263` (`root_client.responses.create`),
`:1481/:1485` (`responses.with_raw_response.parse/create`),
`:1411` (`beta.chat.completions.stream`). Ako se ikad uvede `ChatOpenAI`,
zakrpa ga ne pokriva u tim granama. Danas: neaktivno.

---

## 5. Poziva li ijedan modul AI **pre** instalacije zakrpe? — **NE**

`_patch_prompt_guard()` se zove na `api.py:28`. Sve iznad te linije (`api.py:1-27`)
je stdlib + `fastapi` + `pydantic` + `dotenv` + `slowapi` + `pathlib` — nijedan
repo-lokalni modul osim `shared.ai_client` na `:27`, koji na uvozu ne izvršava
nijedan AI poziv (samo definicije + `_DEFAULT_LLM_TIMEOUT_S` iz `os.getenv`).

Nijedan produkcijski modul nema AI poziv na nivou modula (AST provera: svih 103
call-site-a su unutar `FunctionDef`/`AsyncFunctionDef`, nijedan sa
`func == '<modul>'`). Import-time bypass ne postoji.

---

## 6. Radi li ijedan worker/skript bez `import api`? — **DA, ali ne u produkciji**

**Produkcijski procesi — svi kroz zakrpu:**

| Proces | Komanda | Zakrpa |
|---|---|---|
| Web | `gunicorn api:app -c gunicorn.conf.py` (`Procfile:1`) | DA — `api.py:28` |
| Docker | `uvicorn api:app --host 0.0.0.0` (`Dockerfile` CMD) | DA — `api.py:28` |
| Cron | GitHub Action (`email-cron.yml`) šalje **HTTP `curl`** na `/email-notif/send-reminders` | DA — u web procesu |
| Background agenti | `workers/background_agents.py::run_background_agents`, pozvan iz **`api.py:2076-2077`** (`/api/cron/daily`), in-process `asyncio` | DA — isti proces |
| `services/agent_tasks/*` | lenji uvoz iz `workers/background_agents.py::_agent_registry` | DA — isti proces |

Nema zasebnog worker procesa, nema Celery/RQ, nema drugog `Procfile` reda.
Sav pozadinski AI rad deli proces sa `api:app`.

**Van produkcije — 6 fajlova sa `__main__` koji izvršavaju AI bez `import api`:**
`main.py`, `debug_rag.py`, `ingest_kz.py`, `ingest_laws.py`, `ingest_misljenja.py`,
`scrape_zdi_mca.py` (v. BYPASS-1..6).

---

## 7. `stream=True` — **ne postoji u produkcijskom AI kodu**

```bash
git ls-files '*.py' | grep -vE '^(tests|docs|migrations)/' | xargs grep -nE 'stream\s*=\s*True'
# -> scripts/ingest_ofac_sdn.py:75  (requests.get za preuzimanje OFAC liste, nije AI)
```

Nijedan `chat.completions.create(..., stream=True)`, nijedan `.stream(`, nijedan
`astream`. Svih 5 `StreamingResponse` u repou (`api.py:3542`, `klijenti/router.py:993`,
`routers/billing.py:775`, `routers/billing_reports.py:214`, `routers/data_export.py:123`)
streamuju fajlove/izveštaje, ne LLM tokene.

Dve „stream" putanje koje postoje su drugačije prirode:
1. `routers/voice.py:52` — `audio.speech.create` vraća audio stream; ide kroz
   zakrpljeni `Speech.create`, ali wrapper meri latenciju do **povratka objekta**,
   ne do potrošnje strima, i sadržaj ne prolazi kroz firewall.
2. `services/voice_orchestrator.py:379` — Realtime WebSocket (BYPASS-7).

Napomena o dizajnu: da streaming ikad bude uveden na chat putanji, postojeći
wrapper bi ga **tiho propustio**. `_enforce_response(kwargs, response)`
(`shared/ai_client.py:698`) očekuje `choices[0].message`; `Stream` objekat to
nema, pa bi firewall pao u svoju tolerantnu granu, a `_capture_chat_provenance`
bi upisao `output_hash=None`. Nema tvrdnje koja bi taj slučaj odbila.

---

## 8. Dinamički pozivi — nema ih

```bash
xargs grep -nE 'getattr\([^,]*client|functools\.partial\([^)]*create|getattr\(.*completions|__getattr__'
# -> 0 pogodaka u produkcijskom kodu
```

Svih 103 call-site-a su statički, u obliku `<klijent>.<resurs>.create(...)` ili
LangChain `embed_*`. Nema `getattr`, nema `functools.partial`, nema dinamičkog
razrešavanja imena metode koje bi izbeglo zakrpu.

---

## 9. Sirov HTTP ka model hostovima — jedan slučaj

```bash
xargs grep -nE 'api\.openai\.com|api\.anthropic\.com|generativelanguage|api\.cohere|openai\.azure\.com|wss://'
```

| Pogodak | Priroda |
|---|---|
| `api.py:1155` | CSP `connect-src` string, nije poziv |
| `services/voice_orchestrator.py:46,351` | **BYPASS-7** |

Svi `httpx.AsyncClient` / `requests.post` pozivi u produkciji idu na ne-AI
odredišta: APR (`routers/apr.py:147`), Etherscan (`routers/wallet_provenance.py:88`),
Viber (`routers/viber.py:85,184`), sudski portali (`routers/portal_monitoring.py:99`),
integracije (`routers/integrations.py:229,274,332,406`). `aiohttp` se koristi na
jednom mestu (`vindex_web3/web3_adapter.py:15`) — RPC, ne model.

`litellm` i `ollama` nisu instalirani i ne pojavljuju se u kodu.

---

## 10. Šta nisam mogao da utvrdim

1. **Da li se standalone skripte (BYPASS-1..6) ikad izvršavaju nad produkcionim
   podacima.** Kod dokazuje da *mogu*; operativni dokaz (shell istorija,
   deployment runbook) nije dostupan iz repoa i namerno nisam koristio
   produkcione kredencijale.
2. **Da li je `VINDEX_COHERE_RERANK` postavljen u produkciji.** `.env` nije u
   repou. Ublažavanje je jako (`cohere` nije u `requirements.txt`), ali potvrda
   traži uvid u Railway/Render env.
3. **Da li je `AZURE_OPENAI_KEY`/`AZURE_OPENAI_ENDPOINT` aktivan.** Od toga
   zavisi da li BYPASS-7 uopšte prima sesije (`services/voice_orchestrator.py:352-372`
   fail-closed odbija na Azure konfiguraciji).
4. **Ponašanje wrappera nad pravim `Stream` objektom.** Nema produkcijskog
   streaming poziva nad kojim bi se izmerilo; §7 iznosi analizu koda, ne merenje.
5. **Da li `Responses.create` zaista ostaje nekorišćen posle nadogradnje
   `langchain_openai`.** Zavisi od `use_responses_api` podrazumevane vrednosti u
   budućim verzijama; danas Vindex ne konstruiše `ChatOpenAI` pa je pitanje
   neaktivno.

---

## 11. Prioritetna lista (bez implementacije — Agent 1 ne menja kod)

| # | Nalaz | Ozbiljnost | Osnov |
|---|---|---|---|
| 1 | Realtime WS bez Prompt Guard-a i Response Firewall-a | **VISOKA** | jedini bypass na korisničkom zahtevu; nosi privilegovan razgovor |
| 2 | `/api/voice/transcribe` vraća Whisper transkript bez firewall-a | **VISOKA** | izlaz modela napušta sistem neproveren |
| 3 | `ai_fabric._govern_request` — `sanitize_prompt` ne postoji, `except ImportError: pass` | SREDNJA | kapija tvrdi zaštitu koju nema; danas mrtav kod |
| 4 | `Responses.create` / `Moderations` / `Images` nisu zakrpljeni i nemaju detektor | SREDNJA | prvi budući poziv izlazi iz kapije bez signala |
| 5 | 6 standalone skripti izvršava AI bez zakrpe | SREDNJA | `attempted=False` — ni fail-closed brana ne postoji |
| 6 | Anthropic/Gemini adapteri bez ijedne kontrole | NISKA | mrtav kod + paketi nisu u `requirements.txt` |
| 7 | Streaming chat bi tiho zaobišao firewall | NISKA | latentno; danas nema streaming chat poziva |

---

*Dokument je forenzička inventura. Nijedan produkcijski fajl nije menjan.
`F2-001` i 13 odloženih helpera iz `docs/ux_audit/DEADCODE_FORENSICS.md` nisu dirani.*
