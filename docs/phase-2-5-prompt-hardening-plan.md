# Phase 2.5 — Prompt Hardening Plan

**Goal:** Address Phase 2.4's three critical failures and one polish item via system prompt augmentation.
**Scope:** Modify only system prompt construction in `main.py` (~80 LOC estimate). No `retrieve.py` changes.
**Target:** Phase 2.4 re-run achieves ≥ 6/7 PASS.
**Branch:** `feature/p2-5-prompt-hardening`

---

## Background

Phase 2.4 (Suzana proxy test) achieved 3–4/7 PASS on a synthetic 20-article employment contract. Three structural failures identified:

1. **Q2 (NDA)** — agent hallucinated into Zakon o digitalnoj imovini for an employment contract question
2. **Q3 (prekovremeni)** — agent missed 32h/mes × 12 = 384h/god > 250h/god ZR 53 violation
3. **Q4 (otkazni rok)** — agent cited correct rule (8–30 dana) but concluded that 15 dana violates minimum 8 (self-contradiction)

Plus one polish item: doc citation format inconsistency (Q1 doesn't use "Korisnikov dokument, Član N" pattern that Q5/Q6 use).

All four are addressable via system prompt changes. No retrieval logic changes required.

---

## Patch 1: Doc-Type Domain Constraint

**Solves:** Issue 1 — cross-domain hallucination (Q2)

### Mechanism

After retrieving doc passages, scan first chunk text for document type indicators. Inject domain constraint into system prompt based on detected type.

**Detection heuristics (regex/keyword match on first 2 chunks):**

| Pattern | Document type | Primary legal framework |
|---------|---------------|-------------------------|
| `UGOVOR O RADU`, `RADNI ODNOS`, `ZAPOSLENI` + `POSLODAVAC` | Employment contract | Zakon o radu (ZR) |
| `UGOVOR O ZAKUPU`, `ZAKUPODAVAC`, `ZAKUPAC` | Lease | ZOO (zakup) |
| `UGOVOR O KUPOPRODAJI`, `PRODAVAC`, `KUPAC` | Sale | ZOO (kupoprodaja) |
| `PUNOMOĆJE`, `OPUNOMOĆENIK` | Power of attorney | ZOO (zastupanje) |
| (else) | Unknown | — (no constraint) |

### Prompt injection

When document type is detected, append to system prompt:

```
DOC CONTEXT TYPE: UGOVOR O RADU.
PRIMARNI legal framework: Zakon o radu (ZR).
NE ANALIZIRAJ pitanje kroz: Zakon o digitalnoj imovini, Zakon o
trgovini, Zakon o privrednim društvima, Zakon o platnim uslugama,
ili druge specijalne zakone — osim ako se eksplicitno pominju u
tekstu samog ugovora.
```

If document type is not detected, no constraint injected (preserves current behavior — fail-open).

### Implementation

New helper function in `main.py`:

```python
def detect_doc_type(passages: list[str]) -> str | None:
    """Return document type string ('ugovor_o_radu', etc.) or None if unknown."""
    if not passages:
        return None
    text = " ".join(passages[:2]).upper()
    if "UGOVOR O RADU" in text or ("ZAPOSLENI" in text and "POSLODAVAC" in text):
        return "ugovor_o_radu"
    if "UGOVOR O ZAKUPU" in text or ("ZAKUPODAVAC" in text and "ZAKUPAC" in text):
        return "ugovor_o_zakupu"
    if "UGOVOR O KUPOPRODAJI" in text or ("PRODAVAC" in text and "KUPAC" in text):
        return "ugovor_o_kupoprodaji"
    return None

DOC_TYPE_CONSTRAINTS = {
    "ugovor_o_radu": """DOC CONTEXT TYPE: UGOVOR O RADU.
PRIMARNI legal framework: Zakon o radu (ZR).
NE ANALIZIRAJ pitanje kroz: Zakon o digitalnoj imovini, Zakon o trgovini,
Zakon o privrednim društvima, Zakon o platnim uslugama, ili druge
specijalne zakone — osim ako se eksplicitno pominju u tekstu ugovora.""",
    # ... others as added
}
```

Wire into `ask_agent` before sys-prompt construction. When `extra_namespaces` present and doc passages retrieved, call `detect_doc_type` and inject corresponding constraint string.

### Acceptance criteria

- Q2 (NDA) no longer references ZDI Član 87 or kripto regulative
- Output mentions ZR (specifically čl. 25, čl. 19, ili odgovarajući članovi o tajnosti u radnom odnosu) or ZOO general business secret provisions
- Other doc-context questions (Q1, Q5, Q6, etc.) unaffected
- 30Q baseline maintained at 19/11/0

---

## Patch 2: Quantitative Consistency Check

**Solves:** Issue 2 — agent missed annual prekovremeni cap (Q3)

### Mechanism

Add explicit reasoning step in system prompt that requires unit conversion and comparison against ALL applicable ZR limits.

### Prompt addition

Add to system prompt (after existing reasoning instructions):

```
KVANTITATIVNA PROVERA (obavezno kada zakon ima više time-unit limita):

Kada zakon definiše više limita u različitim vremenskim jedinicama
(npr. ZR 53: 8h/sed I 250h/god), MORAŠ konvertovati ugovorni broj
u sve relevantne jedinice i proveriti SVE limite:

Konverzije:
- Sed → Mes: × 4.33
- Mes → God: × 12
- Sed → God: × 52

PRIMER ISPRAVNE PROVERE:
Ugovorno: 32h/mes prekovremeni rad
Konverzija u godinu: 32 × 12 = 384h/god
ZR 53 godišnji cap: 250h
Ishod: 384 > 250 → KRŠI godišnji limit iz ZR 53.

Ovaj korak SE EKSPLICITNO NAVODI u PRAVNI ZAKLJUČAK sekciji
sa svim brojevima i konverzijama vidljivim.
```

### Implementation

Pure prompt engineering. No code change. ~15 lines appended to existing sys-prompt string in `main.py`.

### Acceptance criteria

- Q3 (prekovremeni rad) detects 32h/mes × 12 = 384h > 250h cap violation
- Q3 output explicitly shows the conversion (32 × 12 = 384)
- Other questions (Q1, Q5, etc.) unaffected
- No regression on 30Q baseline

---

## Patch 3: Contradiction Guard

**Solves:** Issue 3 — agent cited rule "8–30 dana" then concluded 15 dana violates minimum 8 (Q4)

### Mechanism

Require explicit numerical comparison statement in PRAVNI ZAKLJUČAK whenever ugovorni broj is compared to zakonski opseg.

### Prompt addition

Add to system prompt:

```
PRAVNI ZAKLJUČAK FORMAT — numerička poređenja:

Kada porediš ugovorni broj (X) sa zakonskim opsegom [min, max],
OBAVEZNO eksplicitno navedi sva tri elementa:

1. "Ugovorni broj: X = [vrednost] [jedinica]"
2. "Zakonski opseg: [min] do [max] [jedinica]"
3. "X je [u opsegu / van opsega]"

SAMO AKO X < min ILI X > max, smatraj klauzulu spornom.

PRIMER ISPRAVNOG:
- Ugovorni otkazni rok: 15 radnih dana
- ZR 189 opseg: 8 do 30 radnih dana
- 15 ∈ [8, 30] → u opsegu
- Zaključak: ugovorni rok je u skladu sa ZR 189.

PRIMER POGREŠNOG (NIKAD OVAKO):
"15 dana ne ispunjava minimum 8 dana" — ovo je MATEMATIČKA GREŠKA.
15 > 8, dakle 15 ISPUNJAVA minimum 8.

Pre nego što daš final verdict, IZRAČUNAJ poređenje i validiraj
da je tvoj zaključak konzistentan sa numeričkim odnosima.
```

### Implementation

Pure prompt engineering. ~25 lines appended to sys-prompt.

### Acceptance criteria

- Q4 (otkazni rok) correctly concludes 15 dana je u opsegu [8, 30] i u skladu sa ZR 189
- Q5 still correctly flags 3 godine > 2 godine konkurentska violation
- All numerical comparisons in any output are explicit (show the values)
- No regression on 30Q baseline

---

## Patch 4: Doc Citation Format Enforcement

**Solves:** Issue 4 — citation format inconsistency (Q1 uses informal reference)

### Mechanism

Add format enforcement to system prompt requiring consistent doc citation pattern.

### Prompt addition

```
DOC CITATION FORMAT (kada referenciraš sadržaj korisnikovog dokumenta):

UVEK koristi format: "Korisnikov dokument, Član N: [parafraza ili kratak citat]"

NIKAD ne koristi:
❌ "ugovor predviđa..."
❌ "ovaj ugovor kaže..."
❌ "u ugovoru je navedeno..."
❌ "prema dokumentu..."

PRIMER ISPRAVNOG:
✅ "Korisnikov dokument, Član 3: probni rad traje 3 meseca."
✅ "Korisnikov dokument, Član 13: konkurentska klauzula 3 godine."

PRIMER POGREŠNOG:
❌ "Ugovor predviđa probni rad od 3 meseca."
```

### Implementation

Pure prompt engineering. ~15 lines appended to sys-prompt.

### Acceptance criteria

- All questions that reference document content use "Korisnikov dokument, Član N" format
- No regression on Q5/Q6 which already use correct format
- Q1 now uses correct citation pattern

---

## Implementation Order

All 4 patches go into a single system prompt edit in `main.py`. Single commit. Single deploy.

### Step-by-step

1. Open `main.py`, navigate to system prompt construction (~line 1360 per known location)
2. Add `detect_doc_type` helper function and `DOC_TYPE_CONSTRAINTS` constant near top of file
3. Wire `detect_doc_type` call into `ask_agent` flow — after doc passages retrieved, before sys-prompt assembly
4. Append Patch 2 (quantitative), Patch 3 (contradiction), Patch 4 (citation) blocks to existing sys-prompt template
5. Inject Patch 1 (domain constraint) conditionally based on detect_doc_type result
6. **Local test 1:** 30Q baseline still passes (target: 19/11/0, accept 18-20/8-12/0)
7. **Local test 2:** phase_2_4.py achieves ≥ 6/7 PASS
8. Commit, push, Render auto-deploys
9. **Production retest:** phase_2_4.py achieves ≥ 6/7 PASS
10. Update Phase 2.4 report with Phase 2.5 results

---

## Risks

### Risk 1: Prompt bloat

Adding 4 instruction blocks may increase token usage by ~600–800 tokens per request. Acceptable trade-off given quality gain. Monitor OpenAI cost in production for one week.

### Risk 2: Over-constraining

Domain constraint might miss legitimately overlapping legal frameworks. Examples to watch:
- Employment contract for crypto company — *might* legitimately reference ZDI
- Employment contract with arbitration clause — *might* reference Zakon o arbitraži

Mitigation: constraint says "osim ako se eksplicitno pominju u tekstu" — gives agent escape valve when overlap is real.

### Risk 3: 30Q regression

Prompt changes affect ALL questions, not just doc-context ones. The 30Q test (laws-only, no doc context) might shift.

Mitigation: 30Q must run before merge. If regression > 1 question, iterate prompt to localize changes more carefully.

### Risk 4: New self-contradictions

Adding strict format requirements for numerical comparisons might cause agent to enforce them in places they don't apply (e.g., when comparing legal concepts, not numbers). Watch for over-application.

---

## Acceptance Gate

Phase 2.5 is complete when:

- ✅ All 4 patches deployed (single commit)
- ✅ 30Q baseline maintained at 19/11/0 (or marginal improvement, no regression)
- ✅ `phase_2_4.py` achieves ≥ 6/7 PASS in production
- ✅ Phase 2.4 report updated with Phase 2.5 results section
- ✅ Q2 specifically: no ZDI references for NDA question
- ✅ Q3 specifically: explicit 32 × 12 = 384 conversion shown
- ✅ Q4 specifically: correct verdict (15 ∈ [8, 30] → u opsegu)

Once gate passes → beta access opens for Kika.

---

## Out of Scope for Phase 2.5

Items deferred to later phases:

- **OCR for scanned PDFs** — required for user's actual ugovor (currently scanned). Phase 2.6 candidate.
- **ZOO fallback bug (A6)** — ZOO articles being injected as top match for ZR questions (Q1, Q3, Q6 all hit ZOO). Separate fix in retrieve.py, after Phase 2.5 stable.
- **Q7 enumeration** — agent should not just provide framework but actually apply it. Likely needs multi-pass reasoning. Phase 3 or later.
- **Phase 3 (deadline extraction)** — runs in parallel with Phase 2.5 work or after.
