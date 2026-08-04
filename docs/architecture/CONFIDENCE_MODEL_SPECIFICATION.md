# Confidence Model Specification — Program Beta (Masterprompt 002)

**Governing rule (mora biti citirana doslovno u kodu gde god je relevantna,
već postoji u `case_dna.py::_verifikacija_alert_text`'s docstring, potvrđeno
fork-om E kao najbolji postojeći izraz principa):**

> "ne izmišlja 'confidence %' ili drugu vrednost koja se stvarno ne računa nigde"

Ni jedna confidence/procenat vrednost u platformi ne sme biti GPT-ovo
samo-prijavljeno mišljenje kad god postoji ijedan already-fetched ili
already-extracted signal iz kog se broj može izračunati. Model rezonuje o
ČINJENICAMA; platforma računa BROJEVE.

## Dokazan obrazac (potvrđen NEZAVISNO 3 puta u ovom repou, hronološki)

1. `analiza/validator.py` Sloj 10 (`compute_executive_summary`) — najstariji,
   originalni presedan.
2. `shared/genome_validator.py::compute_snaga_score()` (2026-07-18,
   Reliability Patch) — eksplicitno cituje #1 kao uzor ("nastavak istog
   principa, ne nova ideja").
3. `routers/court_predictor.py::_calc_confidence_nivo`/`_procenat_iz_score`
   (Program Alpha, 2026-08-04) — nezavisno rešio isti tip defekta, potvrđeno
   FORK B da PREDATI #2, ne obrnuto — dokaz da je ovo platformski princip,
   ne "port jedne popravke".

**Formula obrasca (generalizovana):**
```
baseline (neutralno, npr. 50) + Σ(uticaj već-ekstrahovanih faktora) → clamp[0,100] → kategorija iz istog broja
```
Faktori dolaze iz LLM ekstrakcije KOJA JE VEĆ SPECIFIČNA PO SLUČAJU (npr.
`snaga_faktori`, RAG hit count, VKS hit count, `case_patterns` firma
istorija) — LLM-u se NE traži da direktno proceni finalni broj, samo da
identifikuje/ekstrahuje ulazne činjenice. Broj se računa u kodu iz tih
činjenica, deterministički i reproducibilno.

## Registar SVIH confidence/procenat vrednosti u platformi

| Vrednost | Lokacija | Status | Formula/mehanizam |
|---|---|---|---|
| `get_confidence_level()` (HIGH/MEDIUM/LOW) | `retrieve.py` | ✅ Deterministic | Cosine score vs. imenovani pragovi (0.65/0.52) |
| `_calculate_confidence()` 0-100 | `retrieve.py` | ✅ Deterministic | `similarity(50) + n_results(30) + query_specificity(20)`, dokumentovane težine |
| Court Predictor `procenat`/`nivo` | `court_predictor.py` | ✅ Deterministic | `_calc_confidence_nivo()` score 0-9 → `_procenat_iz_score()` 20-80% |
| Genome `snaga_predmeta_procent` | `case_dna.py`/`genome_validator.py` | ✅ Deterministic | `compute_snaga_score()` |
| `quality_gate.confidence_score` | `services/quality_gate.py` | ✅ Deterministic | `0.6*citation_score + 0.4*completeness_score`, dokumentovano |
| Firm Brain `confidence` | `firm_memory.py` | ✅ Deterministic (ljudski) | Default 1.0, +0.2 po 3+ potvrde, cap 1.0 |
| Regex ekstrakcija confidence | `intake_extract.py` | ✅ Deterministic | Formula iz match-značajnosti |
| Genome `heatmap`, `najslabija_tacka.kriticnost` | `case_dna.py` | ❌ Raw GPT | Nema post-processing. `[PROGBETA-004]` |
| Strategy Engine 4 procenta | `strategija.py` | ❌ Raw GPT ×4 | Nula backend računanja. `[PROGBETA-001]` — najozbiljniji nalaz misije |
| `/kompletna-analiza` `opsta_confidence` (nivo koraka) | `strategija.py` | ⚠️ Prompt-schema-constrained, ne code-validated | Model bira jednu od 3 dozvoljene vrednosti — ne izmišlja broj, ali izbor nije proveren |
| `/kompletna-analiza` `sistemsko_upozorenje` | `strategija.py` | ✅ Deterministic (OD PROGRAM BETA, implementirano) | Kod broji koliko od 5 relevantnih koraka ima `confidence=NISKA`, sam postavlja/uklanja polje — LLM više ne odlučuje |
| Evidence klasifikacija (`tip_dokaza` i sl.) | `evidence.py` | ⚠️ Nema confidence polje uopšte | Nije "lažna" vrednost — vrednost prosto ne postoji. Manji prioritet od lažnih vrednosti. |
| Evidence `snaga` | `evidence.py` | ✅ Deterministic (OD PROGRAM BETA, implementirano) | Izvedeno iz `_lociraj_tvrdnju` grounding rezultata (`jaka`/`srednja`) |
| Compare `_evidence_check.odluka` | `case_dna.py` | ✅ Deterministic (OD PROGRAM BETA, implementirano) | `validate_dok_reference()` — postoji li DOK-XX referenca medju upoređenim dokumentima |
| OCR "confidence" | `intake_worker.py` | ❌ Hardkodovano 0.6 | Placeholder, ne mera. `pytesseract.image_to_data()` postoji, nekorišćen. Van AI-rezonovanje scope-a (measurement gap, ne reasoning defect) — nazvano, ne implementirano. |
| Heuristička klasifikacija 0.85 | `intake_classify.py` | ⚠️ Fiksna konstanta | Namerni prag, ne izmerena vrednost — časno dizajnersko rešenje, ne lažna mera, niži prioritet |
| LLM klasifikacija/ekstrakcija self-report | `intake_classify.py`/`intake_extract.py` | ⚠️ Nedeterministički po prirodi | Časno labelovano u docstring-u kao takvo, `extraction_method` tag postoji za downstream diskontovanje |

## Pravilo za bilo koju BUDUĆU confidence vrednost

Pre nego što se doda bilo koja nova confidence/procenat vrednost u platformu:

1. **Da li već postoji ekstrahovan, slučaj-specifičan signal iz kog se broj
   može izračunati?** Ako da → napiši `compute_*()` funkciju po uzoru na
   `compute_snaga_score`/`_procenat_iz_score`. LLM ekstraktuje ulaze, kod
   računa izlaz.
2. **Da li je vrednost inherentno subjektivna procena bez merljivog
   ulaza (npr. "koliko je ubedljiv ovaj argument")?** Ako da → dozvoljeno je
   LLM self-report, ALI mora biti eksplicitno labelovano kao takvo (isti
   obrazac kao `intake_extract.py`'s `extraction_method` tag) i NIKAD
   prikazano pored deterministički izračunate vrednosti bez vizuelne
   razlike.
3. **Nikad ne dozvoliti 2+ nezavisna generatora za konceptualno istu
   vrednost.** Ako se ista stvar računa na 2+ mesta (kao Strategy Engine-ov
   "verovatnoća uspeha"), to je hitno za konsolidaciju u jednu
   `compute_*()` funkciju, ne za paralelnu popravku svakog mesta posebno.
