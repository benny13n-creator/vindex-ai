# AI Decision Graph — Program Beta (Masterprompt 002)

**Datum:** 2026-08-04. **Metod:** 5 paralelnih read-only domain fork-ova
(`.vindex_ai_team/decisions/2026-08-04_beta_domain_*_INVENTORY.md`), lično
pročitani u celosti pre pisanja ovog dokumenta. Ne duplira Program Alpha's
strukturno-duplikacioni audit istog dana — ovaj graf je AI-rezonovanje-
specifičan: ko odlučuje, ko koristi, ko sme da menja, ko verifikuje, ko
audituje, za svaku granu.

## Graf: Upload → OCR → Extraction → Genome → Legal Reasoning → Strategy → Briefing → Copilot → Tasks → Alerts → Dashboard

```
Document Upload
  │
  ▼
OCR (pytesseract.image_to_string) ── odlučuje: tekst sadržaja
  │  confidence: HARDKODOVANO 0.6 (placeholder, ne meri se)         [BETA-006, niska]
  │  koristi: sve niže faze
  │  ko sme da menja: samo re-upload
  │  verifikuje: niko
  │  audituje: nema
  ▼
Klasifikacija (heuristic 0.85 fiksno | LLM fallback, self-report)
  │  odlučuje: doc_type
  │  koristi: Evidence Vault, review-queue routing
  │  verifikuje: niko (confidence se NE upisuje dalje od klasifikacije)  [nalaz, § Evidence Chain]
  ▼
Ekstrakcija (regex — deterministički 0.9-0.97 | LLM fallback — self-report, tagovano extraction_method)
  │  koristi: predmet_dokumenti, Evidence Vault kljucne_cinjenice
  ▼
Evidence Vault (routers/evidence.py::_klasifikuj_dokument + _lociraj_tvrdnju)
  │  odlučuje: tip_dokaza, pravni_elementi, kljucne_cinjenice, snaga
  │  snaga: OD PROGRAM BETA (2026-08-04) izvedena iz _lociraj_tvrdnju
  │         nalaza (jaka=grounded, srednja=neverifikovano) — VIŠE SE NE
  │         ODBACUJE već-izračunat signal (implementirano ovom misijom)
  │  verifikuje: _lociraj_tvrdnju (deterministic substring/whitespace match)
  │  audituje: log_action_sync("evidence_klasifikacija")
  ▼
Case Genome (routers/case_dna.py::_extract_genome)
  │  odlučuje: stranke/svedoci/finansije/kontradikcije/snaga_predmeta/
  │            heatmap/dokazi_rang/najslabija_tacka/strategija/upozorenja
  │  snaga_predmeta_procent: DETERMINISTIČKI (compute_snaga_score, backend
  │         arithmetic iz snaga_faktori) — GPT ne bira broj
  │  heatmap, najslabija_tacka.kriticnost: I DALJE raw GPT, bez
  │         deterministic post-processinga                          [PROGBETA-004, srednji]
  │  verifikuje: verify_genome (4 nezavisne provere, advisory, non-blocking)
  │  ko sme da menja: manuelni refresh, background trigger posle upload-a
  │  audituje: shared.ai_provenance.case_context() (module_name=case_dna)
  ▼
Compare Docs (case_dna.py::compare_docs) — genome-adjacentna, 2-dok poredjenje
  │  odlučuje: koji_je_jaci_dokaz, preporuka_advokata, kontradikcije
  │  PRE Program Beta: nula provenance, nula evidence check, nula UI trust
  │         signal (jedini AI poziv u domenu bez ijednog)
  │  OD PROGRAM BETA: case_context() wrapping + validate_dok_reference()
  │         (DOK-XX postojanost) + UI ⚠ signal u _voice_compare_docs
  │         (implementirano ovom misijom)
  ▼
Legal Reasoning Engine (services/legal_reasoning_engine.py) — SOURCE-n grounding
  │  odlučuje: koje citate LLM sme da koristi (samo iz retrieval_meta["izvori"])
  │  ko sme da menja: samo retrieve_documents()'s stvarni Pinecone rezultat
  │  verifikuje: strukturno — izmišljen citat nema SOURCE-n, drop-uje se
  │  ograničenje: ožičeno SAMO u Drafting, ne u Strategy Engine/Genome
                                                                       [nalaz]
  ▼
Strategy Engine (strategija.py, 9 endpointa)
  │  odlučuje: procenat uspeha (4 NEZAVISNA generatora — litigation,
  │            sudija-v2 ×2, v2/analiza, kompletna-analiza)
  │  NAJOZBILJNIJI nalaz misije: worse-than-Court-Predictor-pre-fix — 4
  │         nepomirena autora umesto 2. Sistemski fix (deljeni scorer)
  │         DIZAJNIRAN (§ AI_REASONING_PIPELINE.md) ali implementacija
  │         zahteva novo ožičenje signala (VKS pretraga, case_patterns) na
  │         4 mesta — odloženo, PROGBETA-001
  │  kompletna-analiza sistemsko_upozorenje: OD PROGRAM BETA deterministički
  │         računato u kodu (brojanje NISKA preko 5 koraka), više se ne
  │         oslanja na Synthesis LLM da ispravno primeni pravilo
  │         (implementirano ovom misijom)
  │  citati (član/zakon): ZERO backend verifikacija — čisto prompt-only
  │         ("citiraj iz sopstvenog znanja")                    [PROGBETA-003, visok]
  ▼
Copilot / Morning Briefing (main.py::ask_agent, routers/copilot.py)
  │  ask_agent: DETERMINISTIČKI confidence (cosine threshold + weighted
  │         0-100 score), hard-refuse na LOW / na neverifikovan citat —
  │         najjača Evidence Chain u celoj platformi, model NIKAD ne vidi
  │         pitanje ako citat ne postoji u korpusu
  │  akcija handlers (_handle_akcija_rok i sl.): fact (datum) i inference
  │         (vaznost) izvučeni JEDNIM nediferenciranim pozivom, upisano u
  │         predmet_hronologija bez razlikovanja                [PROGBETA-005, srednji]
  │  Morning Briefing prose: nema grounding proveru na slobodnom tekstu
  │         (nizak rizik — courtesy sažetak, ne autoritativan podatak)
  ▼
Drafting (routers/drafting.py, services/quality_gate.py)
  │  odlučuje: nacrt teksta + confidence_score
  │  quality_gate: DETERMINISTIČKI (0.6*citation+0.4*completeness),
  │         verifikuje SVAKI član-citat protiv realnog indeksiranog korpusa
  │  ograničenje: case-fact fabrikacija (pogrešno ime/datum/iznos) NIJE
  │         provereno — samo prisustvo keyword kategorije, ne tačnost
  │  najjača reusable mehanizam u platformi — trenutno zaključan u ovom
  │         jednom modulu                                       [PROGBETA-003]
  ▼
Task Engine (routers/zadaci.py::ai_analiziraj_predmet)
  │  odlučuje: task predlozi (naziv, opis, prioritet)
  │  POZITIVAN REFERENTNI OBRAZAC: deterministički _otkriveni_problemi
  │         izračunati PRE LLM poziva, ubrizgani u prompt sa eksplicitnom
  │         "ne pretpostavljaj" instrukcijom; failure-path fallback
  │         reprodukuje ISTU logiku bez ijednog LLM poziva
  │  audituje: case_context(knowledge_sources=[...deterministički nalazi])
  │         — pravi, radan explainability primer
  ▼
Alert Engine (shared/proactive_alerts.py, case_dna.py::_delta_alert_text)
  │  odlučuje: alert opis — ČISTO string templating preko VEĆ izračunatih
  │         brojeva, nula LLM poziva
  │  kanonska funkcija (Program Alpha, 2026-08-04): create_proactive_alert()
  ▼
Dashboard (routers/dashboard.py::matter_health_score)
  │  odlučuje: health score — deleguje 100% na calculate_procesni_rizik/
  │         identify_case_problems (isti deterministic risk engine)
  │  nula AI poziva u ovoj grani
```

## Cross-cutting granа: RAG Retrieval (app/services/retrieve.py)

Koristi se od gotovo svake grane iznad (Copilot, Strategy Engine, LRE, Drafting).
`retrieval_meta` (izvori, confidence, match_breakdown) se VRAĆA iz svakog poziva,
ali `case_context()`'s `retrieval_query`/`retrieved_context_ids` parametri
(već postoje u `shared/ai_provenance.py`, već povezani do
`security/ai_forensics.py`) se NE POPUNJAVAJU ni od jednog od ~15+ poziva
mesta. Potvrđeno nezavisno od Program Alpha (isti dan) i 2 Program Beta
fork-a (Legal Reasoning, Search/Tasks) — **isti koren uzrok, treći put
potvrđen**. Sistemski fix je dizajniran (§ AI_REASONING_PIPELINE.md,
PROGBETA-002), implementacija odložena — razlog: "wire the same fix into
15+ heterogenih poziva mesta" nosi realan rizik od nekonzistentne primene
(propušteno mesto), bolje kao sopstveni, potpuno testiran prolaz nego
dodatak na već veliku misiju.

## Phase 7 — Cross-Module Consistency (isti predmet, različiti moduli)

Za isti predmet, sledeći moduli mogu proizvesti NEPOMIRENE zaključke:

| Par modula | Kontradikcija moguća? | Uzrok |
|---|---|---|
| Court Predictor confidence % vs. Strategy Engine 4 procenta | **DA — potvrđeno** | 5 nezavisnih generatora (1 fiksiran ovom misijom pre Programa Beta [Alpha], 4 i dalje otvoreni u Strategy Engine) za konceptualno istu vrednost ("verovatnoća uspeha") |
| Genome `snaga_predmeta_procent` vs. `dokazi_rang` zvezdice | Ublaženo | `_validate_snaga_konzistentnost` soft-proverava odstupanje ≥2 zvezdice — postoji, ali soft (upozorenje, ne blokada) |
| Genome `heatmap`/`najslabija_tacka` vs. `snaga_predmeta_procent` | **DA — nepotvrđeno konzistentnošću** | Nema unakrsne provere između ova dva raw-GPT polja i deterministički izračunatog procenta [PROGBETA-004] |
| Task Engine task-prioritet vs. Dashboard health score | Ne — obe koriste isti `identify_case_problems` | Zajednički koren, konzistentno po dizajnu |
| Compare `koji_je_jaci_dokaz` vs. Genome `dokazi_rang` | Moguće, nisko-verovatno | Različiti pozivi, različit kontekst (2 dok. vs ceo predmet) — nema mehanizma koji bi ih poredio, ali i nema dokaza da se aktivno kontradikuju u praksi (nije testirano na živim podacima) |

**Uzrok, generalno:** svaka kontradikcija u ovoj tabeli potiče od istog
strukturnog obrasca — dva ili više nezavisnih AI poziva proizvode
konceptualno istu vrednost bez deljenog izvora istine. Ovo je TAČNO isti
uzrok koji je Court Predictor-ov fix (Program Alpha) rešio za jedan slučaj i
koji ovaj dokument imenuje kao platformski princip, ne kao izolovan bug.
