# Intake Sprint 003 — Fork B (Legal Domain Expert + Evidence & Consistency Auditor)
## Phase 2: Canonical Legal Taxonomy + Phase 4: Confidence Model

**Date**: 2026-08-05. **Scope**: design only, read-only investigation, zero code changes. Builds directly on
Sprint 001's `INTAKE_ARCHITECTURE_REPORT.md` / `INTAKE_SOURCE_OF_TRUTH_MATRIX.md`, `ARCHITECTURAL_DEBT_REGISTER.md`'s
`ALPHA-003`, and `docs/architecture/CONFIDENCE_MODEL_SPECIFICATION.md` (Program Beta's platform-wide confidence
rule) and `EVIDENCE_CHAIN_REGISTRY.md` (item #5). Forbidden this sprint: Genome, Decision Engine, Copilot,
Search, Firm Brain, Timeline, Deadlines, Tasks, Alerts, Briefing — not touched, not designed for.

---

## 0. What already exists, verified directly (not re-derived from the mission prompt's characterization)

The mission prompt's summary of the 4 vocabularies is a starting sketch, not gospel — direct reads found two
corrections worth flagging up front (same discipline Sprint 001 used to resolve its own fork contradiction by
direct grep, not assumption):

- `routers/dokument.py::_klasifikuj_dokaz` is actually a **9-value** taxonomy (`ugovor, presuda, resenje,
  zapisnik, izvestaj, priznanica, dopis, punomocje, ostalo`), not 4-value as the mission brief characterized it.
  Never persisted (`asyncio.create_task` fire-and-forget, or ad-hoc `/klasifikuj-sesija` endpoint response) —
  confirmed against `INTAKE_SOURCE_OF_TRUTH_MATRIX.md`'s statement that this classifier "never writes to
  `predmet_dokumenti`."
- `shared/intake_classify.py` is confirmed **12 types + `other`** (13 total), matching migration
  `074_intake_phase1a.sql`'s `intake_documents.document_type` CHECK constraint exactly (`lawsuit, response,
  appeal, judgment, contract, invoice, power_of_attorney, evidence, email, court_decision, enforcement,
  legal_opinion, other`).
- `shared/constants.py::EXPECTED_DOCS` uses **exactly** `routers/evidence.py`'s 8 non-`ostalo` values as its
  list items (`sudska_odluka, podnesak, ugovor, dopis, medicinska_dokumentacija, finansijska_dokumentacija,
  javna_isprava, vestacki_nalaz`) — confirming the mission brief's claim that `EXPECTED_DOCS` is keyed to
  `evidence.py`'s vocabulary, not a coincidence.
- `predmet_dokazi.kategorija` (migration `016_evidence_vault.sql`) is `CHECK (kategorija IN ('cinjenica',
  'dokaz', 'svedok', 'vestacenje', 'pravni_osnov', 'ostalo'))` — this is an **evidentiary-role** taxonomy (what
  function does this fact/claim play in the case), stored on `predmet_dokazi` (extracted claims), a completely
  different table and a different question than **document-type** classification stored on
  `predmet_dokumenti.tip_dokaza`. This distinction drives §3's decision to exclude "Dokaz" and the media types
  from the document taxonomy (see §3.2, §3.3).
- `docs/architecture/EVIDENCE_CHAIN_REGISTRY.md` row #5 already names Evidence Vault's `tip_dokaza` classification
  as a **Broken** evidence chain link ("Nema grounding provere uopšte... Sistemski kandidat postoji
  [`_lociraj_tvrdnju`/`quality_gate` princip], nije implementiran ovom misijom — van bounded scope-a, kandidat
  za budući prolaz") — this fork's Phase 4 design is explicitly the "future pass" that item was waiting for.
- `ARCHITECTURAL_DEBT_REGISTER.md::ALPHA-003` already diagnosed the exact mechanism of the classifier race
  this taxonomy needs to end: `evidence.py`'s correct-vocabulary classifier runs as an **unawaited**
  `asyncio.create_task` that overwrites `intake_classify.py`'s wrong-vocabulary write only *if it wins the race*
  — "the actual cause (two classifiers) was never removed, only its symptom papered over with call-order
  sequencing." Fixing that call-site race is an implementation decision for a later sprint phase (out of this
  fork's scope, which is taxonomy + confidence design), but the taxonomy below is designed so that **one**
  canonical vocabulary can replace both classifiers' output space without information loss — see §2.4.

---

## 1. Canonical taxonomy — design principles applied

Per the mission charter's four hard requirements, checked against every design choice below:

1. **Legal, not technical.** Every parent category is defined by procedural/legal function (who produced it,
   what role it plays), never by file format. This is why Fotografija/Audio/Video are explicitly excluded
   (§3.3) — "this file is a JPEG" is a technical fact, not a legal one.
2. **Mutually exclusive, collectively exhaustive, `Ostalo` escape hatch.** Parent-level categories are
   designed around genuinely non-overlapping legal-instrument vocabularies (a document is either produced BY a
   court, submitted BY a party, or is a private contract — rarely more than one). Where real ambiguity exists
   (a settlement agreement, an "izveštaj"), §3 names the specific resolution rule rather than leaving it to
   guesswork.
3. **Usable as a classifier target.** Every category below is checked against a concrete textual/structural
   signal in §4 — no category was kept that can't be plausibly detected by keyword, structure, or a documented
   fallback rule.
4. **Reconciles all 4 vocabularies + the founder's example**, full table in §2.

### 1.1 The canonical taxonomy (10 parent categories, subtypes only where an existing vocabulary or the
founder's example actually asked for that granularity — not invented ungrounded)

| # | Canonical parent (`tip_dokaza` value) | Serbian label | Subtypes (optional 2nd level) |
|---|---|---|---|
| 1 | `sudska_odluka` | Sudska odluka | `presuda`, `resenje`, `zakljucak`, `zapisnik_sa_rocista` |
| 2 | `podnesak` | Podnesak | `tuzba`, `odgovor_na_tuzbu`, `zalba`, `prigovor`, `zahtev`, `predlog`, `izvrsni_predlog` |
| 3 | `ugovor` | Ugovor | *(flat — see §1.2)* |
| 4 | `punomocje` | Punomoćje | *(flat, promoted — see §3.1)* |
| 5 | `dopis` | Dopis | `email`, `obavestenje`, `upozorenje`, `pravno_misljenje` *(see §3.5)* |
| 6 | `medicinska_dokumentacija` | Medicinska dokumentacija | `nalaz`, `izvestaj_medicinski`, `otpusna_lista` |
| 7 | `finansijska_dokumentacija` | Finansijska dokumentacija | `faktura`, `izvod`, `priznanica`, `potvrda_o_placanju` |
| 8 | `javna_isprava` | Javna isprava | *(flat)* |
| 9 | `vestacki_nalaz` | Veštački nalaz | *(flat)* |
| 10 | `ostalo` | Ostalo | *(escape hatch, always available, never forced)* |

### 1.2 Why `ugovor` is flat while `sudska_odluka`/`podnesak` are subtyped

Not an oversight — a deliberate asymmetry. `sudska_odluka` and `podnesak` are subtyped because **every one of
the 4 existing vocabularies, and the founder's own example, independently asked for that specific split**
(Presuda vs. Rešenje; Tužba vs. Odgovor na tužbu vs. Žalba). `ugovor` has no such demand anywhere in the 4
systems or the founder's list — `evidence.py`'s own prompt docstring lists contract subtypes only as loose
parenthetical examples ("ugovor o radu, kupoprodajni, zakup, zastupanje"), never as values any code branches
on. Inventing an ungrounded subtype split here would violate the "usable as classifier target" requirement
(no downstream consumer needs it, so there's no signal to validate the split against) and add review-queue
noise for no product benefit. If a future sprint's product need names a real reason (e.g. a rental-specific
workflow), subtyping `ugovor` then is cheap — the taxonomy's 2-level shape already supports it.

### 1.3 Mutual exclusivity worked example: sudsko poravnanje

A concrete test of "legal, not technical": a **court-approved settlement** ("sudsko poravnanje") is a
document literally titled/containing the word "поравнање"/"poravnanje", which a naive keyword classifier would
route toward `ugovor` (settlements are agreements between parties). But under Serbian civil procedure (ZPP), a
court-recorded settlement has the same enforceable legal force as a judgment — a lawyer treats it as
`sudska_odluka`, not `ugovor`. This is exactly why §4's signal design routes on **structural markers specific
to court-issued documents** (case number format, court letterhead, "судско поравнање"/"pred sudom" phrasing)
ahead of the generic `ugovor` keyword when both fire — see §4.2 signal-priority ordering.

---

## 2. Full mapping table — every category in all 4 systems + the founder's example → canonical target

### 2.1 `routers/evidence.py::_klasifikuj_dokument` (9-type Serbian, the taxonomy's anchor)

| Existing category | → Canonical | Justification |
|---|---|---|
| `sudska_odluka` | `sudska_odluka` | Identical — this vocabulary IS the anchor. |
| `podnesak` | `podnesak` | Identical. |
| `ugovor` | `ugovor` | Identical. |
| `dopis` | `dopis` | Identical. |
| `medicinska_dokumentacija` | `medicinska_dokumentacija` | Identical. |
| `finansijska_dokumentacija` | `finansijska_dokumentacija` | Identical. |
| `javna_isprava` | `javna_isprava` | Identical. |
| `vestacki_nalaz` | `vestacki_nalaz` | Identical. |
| `ostalo` | `ostalo` | Identical. |

### 2.2 `shared/intake_classify.py` (12+1 English, migration 074 CHECK constraint)

| Existing category | → Canonical | Justification |
|---|---|---|
| `lawsuit` | `podnesak.tuzba` | A tužba is the founding instance of `podnesak`. |
| `response` | `podnesak.odgovor_na_tuzbu` | Clean 1:1 — the type's own heuristic keyword list already searches for "ODGOVOR NA TUŽBU". |
| `appeal` | `podnesak.zalba` | Clean — heuristic already searches "ŽALBA"/"PRIGOVOR" (see edge case, §3.6, for the prigovor conflation). |
| `judgment` | `sudska_odluka.presuda` | Clean. |
| `contract` | `ugovor` | Clean. |
| `invoice` | `finansijska_dokumentacija.faktura` | Clean — matches `evidence.py`'s own docstring example almost verbatim. |
| `power_of_attorney` | `punomocje` | Clean, and the strongest evidence that `punomocje` deserves top-level promotion — see §3.1. |
| `evidence` | *(no clean canonical home — excluded)* | Edge case, see §3.2. Generic English "evidence" collides with `predmet_dokazi`'s evidentiary-role axis, not a document type. |
| `email` | `dopis.email` | Clean — email is a channel of written correspondence, i.e. a `dopis` subtype. |
| `court_decision` | `sudska_odluka.resenje` | Distinguishes from `judgment`/`presuda` inside the SAME source vocabulary — see §3.6 for the internal `enforcement` inconsistency this reveals. |
| `enforcement` | **Split** — `podnesak.izvrsni_predlog` OR `sudska_odluka.resenje` | Edge case, see §3.6 — the source vocabulary's own heuristic keyword list mixes a party-submitted instrument with a court-issued one under one label. |
| `legal_opinion` | `dopis.pravno_misljenje` | Edge case, see §3.5 — no clean existing home, judgment call explained. |
| `other` | `ostalo` | Clean. |

### 2.3 `routers/dokument.py::_klasifikuj_dokaz` (9-value, ephemeral, never persisted)

| Existing category | → Canonical | Justification |
|---|---|---|
| `ugovor` | `ugovor` | Clean. |
| `presuda` | `sudska_odluka.presuda` | Clean. |
| `resenje` | `sudska_odluka.resenje` | Clean. |
| `zapisnik` | `sudska_odluka.zapisnik_sa_rocista` | Edge case, see §3.7 — a hearing record, produced by the court, procedurally filed alongside decisions; closest clean home even though it is not itself a decision. |
| `izvestaj` | *(context-dependent, no static mapping)* | Edge case, see §3.8 — "izveštaj" (report) is ambiguous across `medicinska_dokumentacija`/`finansijska_dokumentacija`/`vestacki_nalaz` depending on content; a static 1:1 mapping would be wrong for most instances. |
| `priznanica` | `finansijska_dokumentacija.priznanica` | Clean — matches `evidence.py`'s own docstring ("potvrda o plaćanju"). |
| `dopis` | `dopis` | Clean. |
| `punomocje` | `punomocje` | Clean. |
| `ostalo` | `ostalo` | Clean. |

### 2.4 `api.py::_detect_doc_type` (3-value, ephemeral, routes to specialized prompt only)

| Existing category | → Canonical | Justification |
|---|---|---|
| `presuda` | `sudska_odluka.presuda` | Clean, though note this classifier structurally can never say `resenje` — a known granularity ceiling of this ephemeral classifier, not something this design needs to fix since it never persists a value (§ Sprint 001's finding: "cost/maintenance duplication, not a correctness bug"). |
| `ugovor` | `ugovor` | Clean. |
| `opsti` | `ostalo` | `opsti` ("general") is this classifier's fallback bucket — semantically identical to `ostalo`'s role. |

### 2.5 Founder's example taxonomy (starting sketch, not to copy blindly per the mission charter)

| Founder's example | → Canonical | Justification |
|---|---|---|
| Tužba | `podnesak.tuzba` | Clean. |
| Odgovor na tužbu | `podnesak.odgovor_na_tuzbu` | Clean. |
| Žalba | `podnesak.zalba` | Clean. |
| Presuda | `sudska_odluka.presuda` | Clean. |
| Rešenje | `sudska_odluka.resenje` | Clean. |
| Punomoć | `punomocje` | Clean — corroborates §3.1's promotion decision independently of `intake_classify.py`. |
| Dokaz | *(excluded — not a document type)* | Edge case, see §3.2. |
| Medicinska dokumentacija | `medicinska_dokumentacija` | Clean. |
| Finansijska dokumentacija | `finansijska_dokumentacija` | Clean. |
| Ugovor | `ugovor` | Clean. |
| Dopis | `dopis` | Clean. |
| Veštačenje | `vestacki_nalaz` | Clean. |
| Fotografija | *(excluded — not a document type)* | Edge case, see §3.3. |
| Audio | *(excluded — not a document type)* | Edge case, see §3.3. |
| Video | *(excluded — not a document type)* | Edge case, see §3.3. |
| Ostalo | `ostalo` | Clean. |

**Not in the founder's example but load-bearing and kept**: `javna_isprava` — absent from the founder's
starting sketch but structurally required by `EXPECTED_DOCS` across 4 of its 9 case types (`upravno`,
`porodicno`, `nasledjivanje`, `nepokretnosti`). Dropping it would silently break the missing-document detector
(`services/risk_engine.py::calculate_procesni_rizik`) for those case types. Confirms the mission brief's own
framing: the founder's list is a starting example, not the final word.

---

## 3. Edge cases — explicit judgment calls

### 3.1 `Punomoćje` (power of attorney) — promoted to a new top-level canonical category

**Finding**: `evidence.py`'s 9-type vocabulary — the taxonomy's anchor and the one `EXPECTED_DOCS` is keyed
to — has **no category for power of attorney at all**. A punomoćje uploaded today would silently fall into
`ostalo` at that classifier. Yet `intake_classify.py` has `power_of_attorney` as a first-class type, AND the
founder's own example lists "Punomoć" as a top-level category independent of both `podnesak` and `dopis`. Two
of the three real signals available (one existing vocabulary, one fresh founder input) agree this deserves its
own slot; only the taxonomy currently treated as canonical disagrees, and it disagrees by omission, not by a
considered "this belongs elsewhere" decision.

**Decision**: promote `punomocje` to a top-level canonical parent (10th category). Justification beyond
majority vote: a punomoćje is legally and structurally distinct from every other category — it's neither a
court output (`sudska_odluka`), nor a party's substantive filing (`podnesak`), nor routine correspondence
(`dopis`) — it's an authorization instrument with its own fixed legal form (grantor, grantee, scope, notarization
markers), which also makes it one of the *easiest* categories to detect via structural signal (§4.2).

### 3.2 "Dokaz" (evidence) — explicitly excluded from the document-type taxonomy

**Finding**: the founder's example lists "Dokaz" as a document type, and `intake_classify.py` has a generic
`evidence` type. Both collide with an *already-existing, differently-scoped* concept:
`predmet_dokazi.kategorija` (migration 016) is `CHECK (kategorija IN ('cinjenica','dokaz','svedok',
'vestacenje','pravni_osnov','ostalo'))` — a per-*claim* evidentiary-ROLE classification (what function this
fact plays in the case), stored on a completely different table (`predmet_dokazi`, extracted claims) than
document-TYPE classification (`predmet_dokumenti.tip_dokaza`, the whole uploaded file).

**Decision**: exclude "Dokaz"/`evidence` from the canonical document-type taxonomy entirely. A document isn't
"a Dokaz" as a TYPE — almost any document (a contract, a medical finding, an invoice) CAN function as evidence
in a case, which is exactly what `predmet_dokazi.kategorija='dokaz'` already captures at the correct grain,
on the correct table, once that document's facts are extracted into the Evidence Vault. Creating a second
"Dokaz" value at the document-type layer would recreate, inside this taxonomy, precisely the "same word,
two incompatible vocabularies" collision this whole reconciliation exists to eliminate (the exact shape
`GAMMA-010` already named for "urgency" — "field-name collision, incompatible vocab" — this is the same
disease, caught before it's introduced rather than after).

### 3.3 Fotografija / Audio / Video — excluded from the document-type taxonomy, recommended as separate metadata

**Finding**: these are media/file-format facts, not legal-instrument facts — the taxonomy's own charter
requirement #1 ("must be a LEGAL taxonomy... not a technical one") directly excludes them from a document-TYPE
classifier. Consistent with `predmet_dokazi.kategorija` (§3.2): a photo submitted as evidence gets its
evidentiary ROLE captured there (`kategorija='dokaz'`), completely independent of what kind of file it is.

**Decision**: recommend (not implemented — out of scope for this design fork) a separate, purely-deterministic
`file_kind` field derived from MIME type/extension at upload time (`tekstualni_dokument | fotografija | audio |
video`), analogous to how `ocr_used`/`is_scanned` are already handled as file metadata, not document-type
values. Zero LLM guessing needed or appropriate — this is 100% derivable from the file's own bytes/extension,
the same category of fact `ocr_used` already is. A photo, once uploaded, still gets a best-effort `tip_dokaza`
attempt if it contains any OCR-extractable text (e.g. a scanned photo of a presuda page) — it isn't exempted
from classification, it just also carries this orthogonal, deterministic, non-LLM `file_kind` tag. This
recommendation is a design note for whichever future sprint touches `predmet_dokumenti`'s schema — not
something this fork implements.

### 3.4 (reserved — see §3.1 for punomocje, the only true "no clean home" promotion case)

### 3.5 `legal_opinion` ("pravno mišljenje") — judgment call, weakest-confidence mapping in this table

**Finding**: `intake_classify.py` has `legal_opinion` as a first-class type. It has NO clean home in
`evidence.py`'s 9-type anchor vocabulary, and the founder's example doesn't mention it either. It is
conceptually adjacent to, but legally distinct from, `vestacki_nalaz` — a "veštački nalaz" is a court-appointed
or party-retained technical/scientific expert's finding with defined procedural evidentiary weight; a "pravno
mišljenje" is a lawyer's own advisory legal memo/analysis, not evidence submitted under procedural rules.
Conflating the two would blur a distinction lawyers actually care about.

**Decision**: map to `dopis.pravno_misljenje` — functionally, a received or authored legal opinion memo is
written professional communication/advice, which is what `dopis` already covers loosely. This is the weakest
mapping in the entire table — explicitly flagged, not hidden. **Revisit trigger**: if `intake_processing_outcomes`
volume shows `legal_opinion`-shaped documents arriving often enough to matter (a measurable, not a guessed,
trigger — consistent with `intake_processing_outcomes`'s own stated purpose, "za fino podešavanje... kada se
nakupi realan volumen"), promote it to its own top-level category rather than leaving it a `dopis` subtype.

### 3.6 `enforcement` — the source vocabulary's own keyword list is internally inconsistent

**Finding**: `intake_classify.py::_HEURISTICS` defines `enforcement` with keywords `["РЕШЕЊЕ О ИЗВРШЕЊУ",
"IZVRŠNI PREDLOG", "IZVRSNI PREDLOG", "ПРЕДЛОГ ЗА ИЗВРШЕЊЕ"]` — but "rešenje o izvršenju" (an enforcement
ORDER, issued BY the court) and "izvršni predlog"/"predlog za izvršenje" (an enforcement PETITION, submitted
BY a party) are two different instruments with two different legal producers under the SAME label. This is a
genuine pre-existing defect in the source vocabulary, not an artifact of reconciling it — under the current
system, a party's enforcement petition and the court's resulting order are indistinguishable at the
`document_type` field.

**Decision**: split at the canonical level by WHICH keyword matched: `"РЕШЕЊЕ О ИЗВРШЕЊУ"` →
`sudska_odluka.resenje` (court output); `"IZVRŠNI PREDLOG"`/`"ПРЕДЛОГ ЗА ИЗВРШЕЊЕ"` → `podnesak.izvrsni_predlog`
(party submission). This is not a mapping-table compromise — it's a genuine improvement over the source
vocabulary's own internal conflation, made possible because the keyword itself already carries the
disambiguating signal (§4.2 shows this concretely as the enforcement worked example).

### 3.7 `zapisnik` (hearing minutes/record) — closest clean home, not a perfect fit

**Finding**: `dokument.py`'s ephemeral classifier includes `zapisnik`, absent from all 3 other vocabularies. A
zapisnik (record of a hearing, produced and signed by the court registrar) is not itself a decision — it
documents what happened at a hearing, procedurally.

**Decision**: `sudska_odluka.zapisnik_sa_rocista`. Justification: it is produced BY the court (same producer
axis as the rest of `sudska_odluka`), filed in the case chronology alongside decisions, and shares the same
detectable structural signal (court letterhead, case-number header) as the rest of that parent category —
routing it to `podnesak` (party-submission) or `dopis` (correspondence) would be a worse fit on both the
producer-axis and the signal-detectability axis.

### 3.8 `izvestaj` ("report") — no static mapping, context-dependent by design

**Finding**: "izveštaj" is genuinely ambiguous standalone — `evidence.py`'s own docstring already lists
"izveštaj" as an example under `medicinska_dokumentacija` ("nalaz, izveštaj, otpusna lista"), but a financial
report or an expert's written report are also, in ordinary Serbian usage, "izveštaji." Forcing one static
canonical target for this word would misclassify most non-medical instances.

**Decision**: no static row in the mapping table — this is the one category where the classifier (§4) must
disambiguate by CONTENT context rather than by a fixed keyword→category lookup: medical terminology in the
body → `medicinska_dokumentacija.izvestaj_medicinski`; financial/accounting terminology → `finansijska_
dokumentacija`; expert/technical-witness framing → `vestacki_nalaz`; otherwise → `ostalo` rather than a forced
guess. This is a design constraint on the classifier itself (a single-keyword hit on "izveštaj" alone must NOT
be sufficient for a high-confidence classification — see §4.2's signal-combination rule), not a gap in the
mapping table.

---

## 4. Should case-type × document-type expectations be a separate cross-cutting dimension?

**Recommendation: yes, keep `EXPECTED_DOCS` fully separate from the document-type taxonomy itself** — it
already effectively is one (a `dict[case_type, list[canonical_parent]]`), this just formalizes and preserves
that shape rather than folding case-type-awareness into the taxonomy.

**Justification**:
1. **Different axis, different cardinality.** The document taxonomy answers "what legal instrument is this
   ONE document" (a per-document fact). `EXPECTED_DOCS` answers "which document TYPES should a case of THIS
   kind typically have" (a per-case-type, set-valued fact). Merging them (e.g. inventing `ugovor_radno`,
   `ugovor_privredno` as separate taxonomy values per case type) would multiply the taxonomy's size by 9 case
   types for zero classification benefit — a `ugovor` looks the same textually regardless of which case it
   ends up filed under.
2. **`EXPECTED_DOCS` already only needs PARENT-level granularity, never subtype.** `services/risk_engine.py`'s
   consumption (`postojeci_tipovi = {d.get("tip_dokaza") for d in dokumenti...}`; `nedostajuci = [t for t in
   expected if t not in postojeci_tipovi]`) is an exact-string-match set-membership check against parent-level
   values only. This is a second, independent confirmation that the taxonomy's 2-level (parent/subtype) design
   from §1.1 is correctly shaped — case-readiness checks consume the parent level; per-document display/trust
   consumes parent+subtype.
3. **`punomocje` deliberately NOT added into any `EXPECTED_DOCS` case-type list.** Unlike the other 8
   categories (each tied to a specific dispute TYPE — e.g. `medicinska_dokumentacija` for `porodicno`/
   `krivicno`), whether a punomoćje is expected depends on whether the client used a legal representative, a
   fact orthogonal to case type — a `krivicno` case with a self-representing party needs no punomoćje just as
   much as one with counsel needs one regardless of case type. Folding it into `EXPECTED_DOCS` would produce a
   false "missing document" flag for every self-represented client's case, in every case type. This is an
   explicit exclusion, not an oversight — flagged here so a future sprint doesn't "fix" it by adding it back
   without re-deriving this reasoning.

**Required follow-up (not implemented by this fork, design note only)**: `EXPECTED_DOCS`'s 9 case-type lists
currently reference the 8 pre-existing `evidence.py` values verbatim — no code change is needed for those to
keep working under the canonical taxonomy since §2.1 maps them 1:1. The only schema-level change this taxonomy
implies (a later sprint's decision, not this fork's) is widening `intake_documents.document_type`'s migration
074 CHECK constraint from the 13 English values to the canonical Serbian set — the full old→new mapping for
that migration is §2.2's table, ready to hand to whoever writes it. Per this codebase's standing rule, this
fork is not writing that migration SQL itself.

---

## 5. Phase 4 — Confidence Model

### 5.1 Governing constraint (already established platform-wide, not invented here)

`docs/architecture/CONFIDENCE_MODEL_SPECIFICATION.md`'s rule applies verbatim: *"Ni jedna confidence/procenat
vrednost u platformi ne sme biti GPT-ovo samo-prijavljeno mišljenje kad god postoji ijedan already-fetched ili
already-extracted signal iz kog se broj može izračunati."* That spec's own decision rule (§ "Pravilo za bilo
koju BUDUĆU confidence vrednost") is directly applicable: *"Da li već postoji ekstrahovan, slučaj-specifičan
signal iz kog se broj može izračunati? Ako da → napiši `compute_*()` funkciju."* Document classification
clearly has such signals (concrete keywords, structural markers) — this design therefore falls under rule #1
(build a `compute_*()` function), not rule #2 (label-and-tolerate raw self-report), and is proposed as a
**4th independently-confirmed instance** of that spec's proven pattern (`compute_snaga_score` →
`_procenat_iz_score` → `sistemsko_upozorenje` → this).

This directly targets `EVIDENCE_CHAIN_REGISTRY.md` row #5 (`tip_dokaza`/`pravni_elementi`, currently
**Broken**: "Nema grounding provere uopšte... Sistemski kandidat postoji [`_lociraj_tvrdnju`/`quality_gate`
princip], nije implementiran"). This design is that candidate, made concrete.

### 5.2 (a) What "evidence"/"signals used" concretely means for document classification

Four signal categories, explicitly ranked by reliability — never blended into one undifferentiated number
without saying which fired:

1. **Keyword/phrase match** (strongest, already proven) — the SAME mechanism as `intake_classify.py`'s
   existing `_HEURISTICS`/`classify_heuristic()` (first `_HEAD_CHARS`=400 chars, Cyrillic+Latin parallel
   lookup) — this pattern is kept, not replaced, because it already works and is cheap. **Gap found**: the
   current `_HEURISTICS` list covers only 10 of intake_classify's 13 types and has NO entries at all for
   `medicinska_dokumentacija`, `finansijska_dokumentacija` (beyond `invoice`/`FAKTURA`), or `javna_isprava` —
   extending it to cover the full canonical taxonomy (§1.1) is a concrete, bounded implementation task for
   whichever sprint phase builds this (word lists are directly derivable from `evidence.py`'s own prompt
   docstring, which already enumerates good candidate terms per category — no new legal research needed).
2. **Structural markers** — regex/pattern checks independent of specific vocabulary: court-letterhead pattern
   (Osnovni/Viši/Apelacioni sud + "У..." case-number format) for `sudska_odluka`/`javna_isprava`; signature +
   notarization block markers for `punomocje`; tabular/itemized layout with currency amounts for `finansijska_
   dokumentacija`; dated-header + salutation shape for `dopis`. These are genuinely detectable programmatically
   (regex/structure, not semantic judgment) — satisfying the mission's "distinguishable by actual textual/
   structural signals a classifier could plausibly detect" requirement independent of keyword luck.
3. **Filename hint — WEAK ONLY, capped, never sufficient alone.** A user- or scanner-supplied filename
   (`tuzba_finalna.pdf`) is informational but adversarial-prone (any file can be named anything) — it MUST
   never be allowed to push a classification over the auto-accept threshold by itself, and must be visibly
   tagged as a weak signal in the `signals_used` field (§5.5), not silently folded into a blended score.
4. **Case-type prior — conditionally available, weak adjustment only.** When `predmet.tip` is already known at
   classification time (`EXPECTED_DOCS[tip]` gives a Bayesian-style nudge toward more-likely types for that
   case type), this is a legitimate weak signal. **Explicit caveat**: per `INTAKE_ARCHITECTURE_REPORT.md` §1,
   Pipeline B/C is document-first — the case may not exist yet at classification time, so this signal is only
   sometimes available and must degrade gracefully to "absent," never treated as a required input.

### 5.3 (b) How confidence is computed — combination, not raw self-report

Extends the platform's already-proven `baseline + Σ(factor adjustments) → clamp[0,1]` shape
(`CONFIDENCE_MODEL_SPECIFICATION.md`'s "Formula obrasca (generalizovana)"), applied to a categorical
classification instead of a continuous score:

- **Path 1 — deterministic keyword hit** (mirrors today's `classify_heuristic()` 0.85 constant, kept as a
  documented, honest design choice per the spec's own tolerance for "namerni prag, ne izmerena vrednost" —
  not everything needs to become a formula for its own sake). Recommended refinement, still fully
  deterministic: `0.85 base + 0.05 per additional independent corroborating signal (structural marker match,
  case-type-prior agreement), capped at 0.97` — never 1.00, because even a keyword+structural double-hit could
  be a misfiled quote (a cover letter that quotes "TUŽBA" while attaching one, e.g.).
- **Path 2 — no keyword hit, LLM fallback, but NOT via self-reported confidence.** Instead of asking the model
  "how confident are you, 0 to 1" (the exact shape already named unreliable platform-wide — Genome's
  `heatmap`, Strategy Engine's 4 percentages, OCR's hardcoded 0.6), the model is asked to (1) propose a
  canonical type/subtype, AND (2) **quote the literal text span** it based that decision on. A deterministic
  post-hoc verifier then checks whether that quoted span is actually found VERBATIM in the source document —
  this is the exact same mechanism already proven for evidentiary claims (`routers/evidence.py::_lociraj_
  tvrdnju`/`_snaga_iz_lokacije`, Program Beta, 2026-08-04), applied here to the model's classification
  justification instead of a `kljucna_cinjenica`. Confidence is then computed from: `0.5 baseline (neutral) +
  0.30 if the quoted phrase is grounded (found verbatim) + 0.10 if an independent structural marker for that
  category also fires + 0.05 if filename hint agrees (capped, weak) + 0.05 if case-type prior agrees (when
  available) − 0.20 if the LLM's own reasoning contains hedge language ("možda", "nije jasno") — used only as
  a negative signal, never counted upward, since a model hedging honestly is useful information even though
  its raw confidence number is not trusted.` Clamp to [0,1].
- **Explicit rejection of trusting the LLM's raw self-reported number for ANY part of this**, per the mission's
  own instruction to justify that skepticism against this codebase's established precedent: `_snaga_iz_
  lokacije`'s own docstring states the exact same reasoning transplanted here — a claim/classification the
  model can literally point to VERBATIM in the source is a genuinely stronger basis than an unverifiable
  self-report, but "not found" does not mean "wrong" (paraphrase is possible), which is why the baseline stays
  neutral (0.5) rather than punitive when grounding fails, mirroring `_snaga_iz_lokacije`'s own choice to
  default unverified claims to `"srednja"` (neutral), not `"slaba"` (weak). `quality_gate.py`'s
  `evaluate_draft_quality()` is the second precedent applied: never let one failed sub-check zero out the whole
  score (there, a citation-verification exception degrades to a neutral 0.5 component rather than aborting the
  whole gate) — the same fail-soft posture is used here for each signal component.

### 5.4 (c) Thresholds — reuse the existing platform default, differ by GRANULARITY LEVEL not by category identity

- **Reuse `AUTO_ACCEPT_THRESHOLD = 0.90`** (`shared/intake_documents.py`) for PARENT-level classification —
  no new number invented without cause; this is the founder-approved platform default already governing the
  Confidence Graph.
- **Parent-level vs. subtype-level get independent confidence, never blended** — this mirrors migration 074's
  own already-proven design principle that "SVAKO polje... ima sopstveni confidence, ne jedan skor po
  dokumentu" (per-entity, not per-document), applied one level up: a document can be accepted at 0.93 as
  `sudska_odluka` while its `presuda`-vs-`resenje` subtype sits at 0.55 (genuinely harder — a rešenje's title
  block and a presuda's are structurally near-identical, and each necessarily quotes the OTHER'S name in
  boilerplate procedural text — "žalba na ovo rešenje ide u roku od..." legitimately appears inside a
  `resenje`). **Recommendation**: subtype gets a stricter 0.95 threshold, or — more honest than picking a
  single stricter number — if parent clears 0.90 but subtype doesn't clear ITS threshold, accept the parent
  classification and surface ONLY the subtype as a review-queue item (`reason=classification_uncertain`,
  already an allowed value in migration 074's `intake_review_queue.reason` CHECK constraint — no new reason
  code needed), rather than blocking the whole document on subtype ambiguity a lawyer may not even care about
  for that document.
- **`dopis` is explicitly flagged as a structurally-harder category, by design, not a future bug report.**
  `dopis`'s own definition ("pismena komunikacija, obaveštenje, upozorenje") has the weakest fixed-phrase
  signal of all 9 real categories — ordinary correspondence has no reliable opening keyword the way "ТУЖБА" or
  "ПРЕСУДА" does. Recommendation: track `dopis`'s review-queue rate SEPARATELY once `intake_processing_
  outcomes` accumulates volume (the table's own founder-stated purpose — "za fino podešavanje pragova... kada
  se nakupi realan volumen") and expect it structurally higher than `sudska_odluka`/`podnesak`/`punomocje`
  (which have the strongest, most legally-standardized fixed phrases) — so a future engineer doesn't
  mistakenly read "dopis has a 40% review rate" as a broken classifier when it may simply be the honest
  ceiling for that category's inherent signal weakness.
- **`izvestaj`-shaped documents (§3.8) should never clear auto-accept on a single keyword hit** — this is a
  hard rule baked into the classifier design, not a threshold number: "izveštaj" alone must require an
  independent structural/context corroborating signal (medical/financial/expert-witness terminology) before
  even entering Path 1's deterministic-hit branch, precisely because that one word alone is genuinely
  compatible with 3 different canonical parents.

### 5.5 (d) What `reason` and `evidence` must concretely contain — for the lawyer, not the schema

- **`evidence`**: the literal quoted text span (verbatim substring, with page/paragraph/offset located via the
  same `_lociraj_tvrdnju`-style mechanism already built and proven for `kljucne_cinjenice`) that triggered the
  classification. Never a paraphrase, never generic prose like "the document appears to be a lawsuit."
- **`signals_used`**: a structured object, not prose — reusing the exact JSONB shape already established by
  `intake_processing_outcomes.entity_confidence`, not inventing a new shape: `{"keyword_match": {"phrase":
  "TUŽBA", "offset": 42} | null, "structural_marker": {"type": "court_letterhead", "found": true} | null,
  "filename_hint": {"value": "tuzba_finalna.pdf", "weight": "weak"} | null, "case_type_prior": {"tip_predmeta":
  "parnicno", "agrees": true} | "unavailable"}`.
- **`reason`**: ONE short, concrete, actionable sentence — never "AI determined this is a lawsuit with 87%
  confidence" (tells a lawyer nothing to check), always something they can verify in under 10 seconds by
  looking at the document, e.g. *"Naslov na vrhu prve strane sadrži 'TUŽBA'; tekst ne sadrži 'ODGOVOR NA
  TUŽBU', pa je ta alternativa isključena."* This mirrors migration 074's own already-proven `correction_
  reason` design principle ("zašto", not just "šta") applied to the FORWARD classification rather than only to
  a human's later correction of it.
- **`classification_method` tag always present** (`heuristic | llm | llm_grounded`), exactly matching the
  existing `extraction_method`/`classification_method` column pattern already in the schema — a heuristic hit
  and a grounded-LLM guess must never be blended into one undifferentiated number without the method staying
  visible downstream (same principle the Confidence Graph already enforces per-entity).

### 5.6 Explicit self-skepticism, addressed directly

The mission asks this fork to be skeptical of its own design and justify any place it recommends trusting an
LLM's self-report. **This design recommends trusting raw LLM self-reported confidence for document
classification in zero places.** The two places an LLM's output is used at all (Path 2's type/subtype guess,
and its quoted grounding span) are both treated as *proposals* — the type is accepted only after the deterministic
scoring in §5.3 combines it with grounding/structural verification, and the ONLY place a raw model signal
(hedge language) enters the formula, it is used exclusively as a negative/downward adjustment, per the same
asymmetry `_snaga_iz_lokacije` already established (verified-positive is trusted more than an unverifiable
positive; an honest negative signal from the model is still informative even though a positive self-report is
not). This keeps the design inside `CONFIDENCE_MODEL_SPECIFICATION.md`'s decision rule #1 (build a `compute_*`
function) rather than rule #2 (label-and-tolerate self-report) for every component of the score.

---

## 6. Explicit scope boundary / handoff

- **Not implemented**: no code, no migration SQL, no schema change. Per this repo's own standing rule
  (`feedback_migrations.md`), migration SQL is never written by an agent — §4's required follow-up (widening
  migration 074's CHECK constraint) is a design note with a ready-made mapping table (§2.2), for whoever runs
  it.
- **Not touched**: Genome, Decision Engine, Copilot, Search, Firm Brain, Timeline, Deadlines, Tasks, Alerts,
  Briefing — none of `Genome`'s `dokazi_rang`, Copilot's document-facing surfaces, or the Decision Registry
  were read, modified, or designed against beyond the one explicit boundary check already required by the
  charter (§0: confirming this taxonomy doesn't structurally conflict with `predmet_dokazi.tip_dokaza`'s
  existing role, which is exactly why §3.2/§3.3 exclude "Dokaz" and media types rather than silently colliding
  with it).
- **Not decided**: which sprint phase actually rewires `intake_classify.py`'s and `evidence.py`'s call sites
  to a single canonical classifier (the real fix for `ALPHA-003`'s race) — that is an implementation decision
  for a later phase of this sprint or a future one, informed by, but not made by, this taxonomy design.
