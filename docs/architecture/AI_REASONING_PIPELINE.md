# AI Reasoning Pipeline — Program Beta (Masterprompt 002), Phase 6

## Kanonski redosled (svaki AI operacija u platformi TREBA da prati ovaj tok)

```
1. FACTS        — podaci iz OCR/Extraction/Metadata/Genome/DB/Events, NIKAD od LLM-a
2. EVIDENCE      — da li je svaka činjenica traceable nazad do izvora?
   VALIDATION      (grounding check: _lociraj_tvrdnju / quality_gate / verify_genome princip)
3. LEGAL RULES   — deterministička pravna pravila (rokovi, procesni statusi) — ne LLM diskrecija
4. REASONING     — LLM rezonuje NAD validiranim činjenicama (ne izmišlja nove)
5. CONFIDENCE    — kod računa broj iz already-ekstrahovanih signala (§ CONFIDENCE_MODEL_SPECIFICATION.md)
6. RECOMMENDATION — LLM predlaže akciju, jasno odvojeno od FACTS/INFERENCE (Princip 2)
7. EXPLANATION   — svaki zaključak mora odgovoriti NA OSNOVU ČEGA (koje činjenice, dokumenti, članovi)
8. AUDIT         — case_context() + log_action, correlation_id
9. PROVENANCE    — knowledge_sources / retrieval_query / retrieved_context_ids POPUNJENI, ne samo dostupni
10. UI           — trust signal proporcionalan stvarnoj pouzdanosti (ne uniformno "AI je rekao")
```

Nijedan modul ne sme preskočiti korake 1-3 pre nego što pozove LLM (Princip
1: Facts Before AI). Nijedan modul ne sme preskočiti korak 5 kad
deterministički signal postoji (Princip 4: Deterministic Core).

## Referentne implementacije po koraku (VEĆ POSTOJE u repou — ne izmišljati)

| Korak | Najbolji živi primer | Zašto je referentan |
|---|---|---|
| 1. Facts | `services/risk_engine.py::identify_case_problems` | Čist Python, nula LLM poziva, izračunato iz realnih DB brojeva pre bilo kog AI koraka |
| 2. Evidence Validation | `routers/evidence.py::_lociraj_tvrdnju` | Deterministic substring/fuzzy match, fail-soft (nikad ne izmišlja lokaciju) |
| 3. Legal Rules | `services/quality_gate.py::_verify_citation` | Citat ili postoji u indeksiranom korpusu ili ne — binarno, kod-nametnuto |
| 4. Reasoning (constrained) | `routers/zadaci.py::ai_analiziraj_predmet` | Prompt eksplicitno zabranjuje LLM-u da "pretpostavlja" mimo injektovanih `_otkriveni_problemi`; fallback path reprodukuje ISTU logiku bez LLM-a |
| 5. Confidence | `shared/genome_validator.py::compute_snaga_score` | Vidi CONFIDENCE_MODEL_SPECIFICATION.md |
| 6. Recommendation (labeled) | `case_dna.py` Genome shema (implicitno) | `strategija`/`nedostaje`/`upozorenja` grupisani odvojeno od FACT polja u schema strukturi |
| 7. Explanation | `main.py::ask_agent` hard-refuse logika | Citat ili postoji ili se pitanje NIKAD ne šalje modelu — eksplicitniji od bilo kog drugog modula u platformi |
| 8. Audit | `shared/ai_provenance.py::case_context()` | Kanonski context manager, korišćen (posle ove misije) i u Compare docs |
| 9. Provenance | `shared/ai_provenance.py` parametri | Postoje, povezani do `ai_forensics.py` — populacija je gap, ne infrastruktura `[PROGBETA-002]` |
| 10. UI trust signal | `static/vindex.js:17430-17490` Genome `_verifikacija` block | Ne-kolapsibilan, prominentan po dizajnu ("sakriti trust signal iza klika bi poništilo razlog zašto je napravljen") |

## Šta ovaj pipeline NIJE

Nije nova infrastruktura za izgradnju. Svaka referentna implementacija iznad
već postoji i radi u produkciji. Ovaj dokument je **imenovanje** postojećeg,
dokazanog obrasca kao platformski standard — isto što je Program Alpha
uradio za strukturnu duplikaciju, primenjeno ovde na AI-rezonovanje.
Buduće AI funkcije se procenjuju protiv OVE liste pre nego što se piše nova
logika: "koji od ovih 10 koraka već ima referentnu implementaciju koju mogu
da reuse-ujem?"

## Kako se ovaj pipeline primenio u implementaciji ove misije

- **Evidence Vault `snaga`** — koraci 2→5 povezani (grounding rezultat → confidence).
- **Compare docs** — koraci 8, 2, 10 dodati (provenance wrapping, DOK-XX
  evidence check, UI ⚠ signal) na modul koji ih je sve preskakao.
- **`/kompletna-analiza` `sistemsko_upozorenje`** — korak 5 prebačen sa LLM
  diskrecije (koja je bila korak 4-shaped — "rezonuj o pravilu") na kod
  (korak 5-shaped — "izračunaj pravilo").

## Odloženo (dizajnirano, implementacija van bounded scope-a ove sesije)

- **Strategy Engine deljeni scorer (`PROGBETA-001`)** — korak 5 nedostaje na 4
  mesta. Dizajn: nova `shared/litigation_confidence.py::compute_litigation_score()`
  po uzoru na `_calc_confidence_nivo`, ulazi: RAG hit count (već fetch-ovan,
  neiskorišćen), VKS hit count (NE postoji poziv danas — treba dodati), `case_patterns`
  firm history (NE postoji poziv danas — treba dodati, ključ: `tip_postupka`).
  Implementacija zahteva novo ožičenje 2 signala pre nego što scorer uopšte
  može da postoji — Phase 7 rad, ne lokalna zakrpa jednog endpointa.
- **RAG provenance threading (`PROGBETA-002`)** — korak 9 nedostaje na ~15+
  mesta. Mehanizam postoji end-to-end, fix je čisto "thread `retrieval_meta`
  u `case_context()`" ponovljeno na svakom pozivnom mestu. Odloženo jer
  obim (15+ heterogenih poziva kroz Copilot/Strategy/LRE/Drafting) nosi
  realan rizik od nekonzistentne primene ako se ubrza u istoj sesiji kao
  ostatak ove misije — zaslužuje sopstveni, potpuno testiran prolaz.
- **`quality_gate` generalizacija za Strategy Engine/Genome (`PROGBETA-003`)**
  — korak 3 postoji samo u Drafting. `_extract_article_citations`/
  `_verify_citation` već rade nad proizvoljnim tekstom (nisu Drafting-
  specifični po dizajnu), pa je portabilnost verovatna, ali nije potvrđena
  čitanjem stvarnog integracionog koda na 2 nova poziv-mesta — treba
  potvrditi pre implementacije, ne pretpostaviti.
- **Copilot fact/inference schema separacija (`PROGBETA-005`)** — korak 6
  (recommendation/inference labeling) nedostaje u akcija handlerima.
  Zahteva shema promenu (razdvojiti `datum_iso` fact polje od `vaznost`
  inference polja sa sopstvenim confidence/marker) kroz 4 handler funkcije
  — arhitektonska, ne prompt izmena.
- **Genome `heatmap`/`najslabija_tacka` deterministic scoring (`PROGBETA-004`)**
  — za razliku od `compute_snaga_score` (koji reuse-uje već-ekstrahovan
  `snaga_faktori`), heatmap dimenzije NEMAJU ekvivalentnu već-ekstrahovanu
  faktor-listu iz koje bi se agregirale — trebalo bi prvo proširiti Genome
  ekstrakcionu šemu da vrati eksplicitne per-dimenziju faktore, pa tek onda
  napisati `compute_*()` nad njima. Ovo je redizajn ekstrakcije, ne samo
  post-processor — veći obim nego što je izgledalo iz inicijalnog nalaza.
