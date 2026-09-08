# VINDEX APPLICATION — UX ARCHITECTURE v1

Status: architecture study + isolated prototype. **No production code changed.**
Companion documents: `VINDEX-APPLICATION-HOME-ARCHITECTURE.md`, `VINDEX-APPLICATION-VISUAL-FOUNDATION-v1.md`.

---

## 0. The single most important finding

Before any design decision was made, the repository was inspected (not assumed). The result changes
the shape of this whole sprint:

**A rewrite that already targets this exact brief exists in production, gated behind a per-session
token route, and is not what regular users see today.** It lives in `v2/`. Its own source comments
state the mission in almost the same words as this sprint's mandate:

> `v2/domain/spaces.js`: *"Korisnik uči ČETIRI mesta, ne osamdeset osam sposobnosti."*
> ("The user learns FOUR places, not eighty-eight capabilities.")

It already has:
- four learnable spaces (`Danas`, `Predmeti`, `Znanje`, `Kancelarija`, + a fifth permission-gated
  `Usklađenost`) instead of the legacy app's 13-tab sidebar
- a rule that an unbuilt or unpermitted space **does not render** — no disabled items, no "coming
  soon" (`spaces.js`: *"Onemogućena navigacija je obećanje koje proizvod ne može da održi"*)
- a Home ("Danas") screen that already rejects cards, widgets, score numbers, and mixes of
  AI text with deterministic fact (`danas/view.js` header comment, verbatim)
- a case workspace ("Dosije") that is one continuous scroll with a sticky anchor strip, not tabs
  (`dosije/view.js`: *"Tab skriva ostatak predmeta i tera advokata da pamti gde je sta"*)
- a document reader that reads in a 72-character column, never a modal or side panel
  (`dosije/citac.js`)
- a case registry where *"red je red, ne kartica"* — a row is a row, not a card
  (`predmeti.css` header)
- design tokens with two clean surfaces (crna/papir), one hairline system, radius 0, no shadows
  (`v2/styles/tokens.css`) — i.e. most of this brief's §7 forbidden-pattern list is **already
  structurally impossible** in this codebase, not a new discipline to impose

**Conclusion this sprint acts on:** the job is not "invent an information architecture from
nothing." The job is (1) validate the existing V2 IA against this brief's principles — it passes
almost everywhere it was checked — (2) resolve the specific gaps and inconsistencies the brief's
own falsification questions surface, (3) supply the one thing V2 genuinely does not have yet: a
visual identity aligned with the now-canonical Vindex.rs system (colors, the new sphere object,
refined type/space rhythm), expressed as an isolated prototype. Re-deriving IA from scratch would
have *thrown away* evidence-based, already-shipped decisions in favor of re-guessing them — the
opposite of §2's instruction not to design from memory.

This document therefore reads as an **audit-and-extend**, not a green-field spec.

---

## 1. Capability inventory (evidence, not re-derivation)

The rigorous function inventory this brief asks for already exists at
`docs/v2/CAPABILITY-MATRIX.md` (304 lines, dated 2026-09-06), built to a stricter bar than a normal
audit: each of **111 capabilities** is classified IMPLEMENTED / PARTIAL / BLOCKED / DEFERRED against
a 10-point test (reachable route, real backend contract, permission behavior, tenant isolation,
loading/empty/error states, mutation proof, responsive proof, test proof).

| Group | Total | IMPLEMENTED | PARTIAL | BLOCKED | DEFERRED |
|---|--:|--:|--:|--:|--:|
| A. Opening a case | 7 | 7 | 0 | 0 | 0 |
| B. Working a case | 30 | 15 | 0 | 0 | 15 |
| C. Documents / evidence | 9 | 6 | 0 | 0 | 3 |
| D. Legal work (research/drafting) | 20 | 7 | 0 | 0 | 13 |
| E. Clients | 11 | 6 | 0 | 0 | 5 |
| F. Office / firm admin | 12 | 7 | 1 | 0 | 4 |
| G. Conditional / digital-asset | 10 | 1 | 0 | 5 | 4 |
| H. Cross-cutting (search, Danas, briefing, calendar, notifications, plan/usage) | 12 | 8 | 0 | 0 | 4 |
| **Total** | **111** | **57** | **1** | **5** | **48** |

Every DEFERRED row carries a one-line reason in the source doc; the two dominant reasons are "AI
conclusion without a provenance contract yet" (14 rows) and "not in the owner's execution order" (15
rows) — i.e. deliberately excluded, not forgotten. **G1–G5 (digital-asset compliance) are BLOCKED,
not deferred**: the module cannot yet cite a source for its own conclusions, a backend gap, not a UI
decision — this sprint does not touch it and does not surface it as if it were ready.

This sprint does **not** re-litigate that matrix. It is treated as the ground truth for "what
exists." Where this document names a capability, it is drawn from that matrix or from direct
reading of the corresponding `v2/features/*` module (cited inline).

### 1.1 Global vs. contextual, as already encoded in the URL structure

V2 already separates these cleanly by route shape, not by convention that could drift:

- **Global** (no object required first): `Danas` (`/app-v2/danas`), global `Pretraga`
  (`/app-v2/pretraga`, also Ctrl/Cmd+K), `Novi predmet` (`/app-v2/predmeti/nov`), account/logout,
  `Znanje` (legal research is not tied to a case), `Kancelarija` (firm-level admin/finance).
- **Contextual** (only exists under an opened object): everything under `/app-v2/predmet/<id>`
  (spisi, rokovi/zadaci, naplata, profitabilnost, saradnja, poređenje, izmena, brisanje) and under
  `/app-v2/klijent/<id>`.

This matches this brief's §3 classification (GLOBALNO / KONTEKST PREDMETA / KONTEKSTUALNA AKCIJA)
almost exactly, and it was already true before this sprint started — confirmed by reading the route
table in `v2/domain/spaces.js` and the per-feature `prostor.js` router files, not assumed from the
sidebar.

### 1.2 What SISTEMSKA INTELIGENCIJA (system-surfaced intelligence) already means here

- **Brifing** (`danas/brifing.js`): an explicit, separate, on-request screen — kept apart from the
  deterministic Danas stream on purpose (`view.js`: *"AI tekst pomešan sa determinističkom
  činjenicom"* is listed under "what this deliberately does not have").
- **Predlog roka** (proposed-deadline decision control, `rokovi/odluka.js`): a system-proposed date
  that requires an explicit Potvrdi/Odbij, never auto-applied.
- Both already obey the brief's implicit rule that system-generated content must be visually and
  interactionally distinct from confirmed fact. Nothing new needed here; the prototype preserves
  this distinction rather than introducing a generic "AI card."

### 1.3 NAPREDNO / POVREMENO (advanced/occasional) — already demoted correctly

Profitabilnost, poređenje (case comparison), saradnja (collaboration), and case deletion all live
**inside** Dosije as expandable sections/controls, not as top-level nav items or Home widgets. This
is already the progressive-disclosure behavior §14 asks for; the prototype's Predmet screen
represents this by anchoring them below the fold under their own named section, not by hiding them
behind an extra click that doesn't exist in production today.

---

## 2. Falsification pass against the existing IA (§4 of the brief)

Applied to each top-level V2 region, using evidence, not intuition:

| Region | Does it need to exist? | Always visible? | Could a novice misread it? | Verdict |
|---|---|---|---|---|
| Danas | Yes — it is the only place "what needs attention across all cases" is answered at all | Yes, it's Home | No — it opens with a single sentence, not a dashboard | **Keep as-is** |
| Predmeti | Yes — "gde radim" is the single highest-frequency need for a lawyer | Yes | No | **Keep as-is** |
| Znanje | Yes — legal research is not case-scoped by nature (you research before you know if you'll take the case) | Yes | Possibly — "Znanje" is more abstract than "Sudska praksa" was; kept anyway because it correctly merges what were two legacy spaces (Vindex Intelligence + Sudska praksa) covering the same real need | **Keep, terminology risk flagged in §5** |
| Kancelarija | Yes — firm-level (not case-level) admin/finance has to live somewhere that isn't a case | Yes | No | **Keep as-is** |
| Usklađenost | Only for permitted accounts | Only when permitted (already enforced) | N/A — invisible to everyone else, which is correct | **Keep, gating already correct** |
| Legacy sidebar's 13 items | No — this is exactly the "exposing backend module ownership instead of user intent" pattern §4 warns about | — | Yes — a first-time user has to learn 13 labels before finding anything | **Superseded by the 4-space model; not carried into the prototype** |

No region survived this pass by being "existing" alone — each had to answer its own "does this need
to exist / does it need to be permanent" test. The legacy 13-item sidebar is the one region that
**fails** and is why V2 does not use it; the prototype builds only on the space that passed.

---

## 3. Canonical Serbian terminology

| Concept | Legacy app | V2 | Prototype uses | Reason |
|---|---|---|---|---|
| Cases | Predmeti | Predmeti | **Predmeti** | Already consistent |
| Clients | Klijenti | Klijenti | **Klijenti** | Already consistent |
| Deadlines | Rokovi (top-level tab) | Folded into Dosije · Rokovi + Danas stream | **Rokovi** (contextual, not top-level) | V2's demotion from global tab to contextual concept is deliberate and correct — a deadline only means something attached to a case; kept |
| Documents (the file object) | "Dokumenti" | "Spisi" | **Spisi** | Real divergence found. "Spis" is the correct Serbian legal-register term for a case document and is what V2 already standardized on inside Dosije; "Dokumenti" survives only in the legacy app. The prototype uses **Spisi** and this document records the divergence so it is a conscious choice, not a silent rename |
| Tasks | "Zadatci" and "Zadaci" (both spellings, same UI element) | Zadaci (inside Dosije · Rokovi) | **Zadaci** | Legacy has an internal inconsistency (both spellings on the same screen); V2 already picked one. Normalized to V2's spelling |
| Legal research | "Sudska praksa" / "Vindex Intelligence" (two separate legacy tabs) | Znanje (merged) | **Znanje** | Deliberate merge of two legacy concepts users experienced as one need |
| Finance | Finansije | Naplata (per-case) + Kancelarija (firm-level) | **Naplata** in Predmet, **Kancelarija** at firm level | Scope-correct: a case's billing is not the same object as the firm's finances |
| Settings | Podešavanja (top-level tab) | Folded into Kancelarija | **Kancelarija** | Settings alone is not a frequent-enough daily need to justify a permanent top-level slot; it is one section inside "how I run the firm" |
| Search | "Pretraži" / "Pretraga" | Pretraga | **Pretraga** | Consistent |
| Home / recent | "Pregled dana" | Danas | **Danas** | Same concept, V2's name is shorter and already shipped |

No term is invented in this prototype that does not already exist in the codebase.

---

## 4. Navigation — derived, not assumed

**Selected model:** V2's existing header-row navigation (`v2/shell/shell.js`) — full-height row,
wordmark left, four (or five) space links inline, search + account right. **Not a sidebar.**

**Why (from the code's own reasoning, corroborated independently):** a legacy-style tall sidebar
listing 13 items forces a user to scan a wall of labels before finding anything, and gives equal
visual weight to a daily action (open a case) and a rare one (portfolio settings). A 4–5 item
horizontal row can be read in one glance, matches "current location always obvious" (the active
space gets a full-height accent underline in the existing shell CSS), and leaves the entire
remaining width to the actual work surface — which matters most on Predmet/document screens where
horizontal space is the scarce resource, not navigation.

**Major alternative rejected:** a narrow icon rail (common in dense SaaS products). Rejected because
Vindex's five space names (`Danas`, `Predmeti`, `Znanje`, `Kancelarija`, `Usklađenost`) do not have
unambiguous icons a first-time, non-technical user could learn — the brief itself warns against
mystery-meat icon navigation implicitly by demanding "consistent terminology" and "no unnecessary
visual noise." Words a lawyer already uses beat glyphs they'd have to learn.

**Also rejected:** collapsing Znanje or Kancelarija under an "More" overflow menu to shrink the row
further. Rejected because both are used at *daily* frequency per the capability matrix (Znanje
underlies all research; Kancelarija owns firm finance/admin used every billing cycle) — hiding a
daily-frequency space behind an extra click fails §11's action-hierarchy rule that primary,
likely-needed actions must not be interpreted as advanced ones merely to save header width.

---

## 5. Complexity-reduction principles actually applied

1. **A bucket is not a UI section.** `Danas` already proves this: the backend's six workspace
   buckets (kritično/danas/za_pregled/predstojeće/na_čekanju/završeno_nedavno) are recombined into
   two user-facing streams (Traži pažnju / Uskoro) before anything reaches the DOM
   (`domain/danas.js::komponujDanas`). The prototype's Home follows the same rule for the sphere's
   four counts: they are framed as answers to a question, not as an enumeration of backend tables.
2. **A number without an explanation is not shown.** Kept from Danas; extended to the sphere (each
   of the four values has an unambiguous one-line Serbian label directly beneath it, not a
   cryptic abbreviation).
3. **Deep links only where a destination provably exists.** Danas already refuses to link a
   cross-case rollup count ("+N") to a screen that cannot actually show all of it. The sphere's
   four numbers are **not** individually clickable in this prototype for the same reason — no
   existing V2 screen aggregates "all unread documents across all cases" as a single filtered view
   today (per the capability matrix); inventing that link would be exactly the "feature must be
   invented to complete the mockup" hard-stop condition in §32. It is documented as an unresolved
   question in §9.
4. **Progressive disclosure by section, not by hiding primary actions.** Dosije's profitability/
   comparison/collaboration blocks sit below the main case content, reachable by scrolling, not by
   an extra menu — satisfying §14's "do not hide primary actions merely to achieve visual
   minimalism" while still keeping occasional-use content out of the first screenful.

---

## 6. Visual-material grammar (see Visual Foundation doc for full spec)

Summary of the rule tested in the prototype: **black = Vindex/system chrome, bone = active work
surface, red = structural signal (never decorative), the sphere = ambient brand object belonging to
system space, not to the work surface.** This was prototyped, not assumed — see §7 below and the
Visual Foundation document for the screen-by-screen material transition actually built.

---

## 7. Sphere role

The sphere is new — no existing asset or code represents it (confirmed by search: no file, no CSS
gradient, no SVG, no doc anywhere in the repository describes it). It was provided as reference
artwork (a rendered black/graphite faceted sphere with red fissures, no red outline, no ring) and is
used in the prototype as a real image asset — the same way the website's own logo artwork is reused
rather than redrawn — with the four live values composited on top as real DOM text, not baked into
the image, so different demo states (zero-heavy day vs. busy day) can both be shown.

Placement rule tested: it appears **only** in the Danas black header band. It is explicitly absent
from Predmet, the document reader, and the data-dense registry — tested directly in the prototype's
four screens, not asserted without checking (see §8 Responsive/Screenshot review in the Visual
Foundation doc).

---

## 8. Progressive disclosure model

| Mechanism | Where used in this prototype | Evidence it already fits V2 |
|---|---|---|
| Object-specific action menu | Dosije's per-section controls (rok/zadatak/beleška forms) | Already the shipped pattern in `dosije/radnje.js` |
| Anchor strip instead of tabs | Dosije | Already shipped (`dosije/view.js`) |
| Command/search accelerator | Ctrl/Cmd+K → `/app-v2/pretraga`, never a modal-only trap | Already shipped (`shell.js`) |
| Below-the-fold advanced sections | Profitabilnost/poređenje/saradnja in Dosije | Already shipped |
| Full-width reading surface for depth, not a drawer | Document reader (`citac.js`) | Already shipped |

Nothing new was invented here; the prototype demonstrates these mechanisms visually rather than
introducing new ones, per §14.

---

## 9. Unresolved questions (explicit, not smoothed over)

1. **The sphere's four counts are not currently computed anywhere.** "Aktivni predmeti," "Aktivni
   rokovi," "Novi klijenti," and "Nepročitani dokumenti" are plausible aggregates of data that
   exists (predmeti, rokovi, klijenti, dokumenti all have real backends per the capability matrix),
   but no endpoint returns exactly these four numbers today. The prototype marks them, in code and
   in the Visual Foundation doc, as **representative dummy values** — this sprint does not invent
   or wire the aggregation logic (§23, §32).
2. **"Novi klijenti" needs a business definition ("new" since when?) before it could ever be real.**
   Not resolved here — an owner decision, not a design decision.
3. **Znanje as a merged term may need user testing.** It is evidence-based (it correctly merges two
   legacy concepts) but it is more abstract than either legacy name; this document flags it rather
   than either keeping two separate spaces (contradicting the four-space model) or asserting
   confidence that isn't earned yet.
4. **Whether the sphere's zero/non-zero red rule conflicts with V2's existing "brand ≠ status"
   constitutional rule** — see Visual Foundation §"Red usage budget" for the full discussion; this
   sprint treats it as a deliberately scoped, owner-directed exception limited to these four values,
   not a precedent for using red as a general status color elsewhere.
5. **Dokumenti vs. Spisi**: this sprint normalizes the prototype to "Spisi" (§3) but does not rename
   anything in the legacy production app — that app still says "Dokumenti" today and continues to
   until an owner decides to retire it.

---

## 10. Rejected alternatives (consolidated)

- A brand-new sidebar-based IA — rejected, see §2 and §4.
- Deriving Home/IA from scratch without reading the existing V2 code — rejected as the opposite of
  this brief's own §2 mandate; would have discarded already-proven decisions.
- Icon-rail navigation — rejected, see §4.
- Collapsing Znanje/Kancelarija into an overflow menu — rejected, see §4.
- Making the sphere's four counts clickable — rejected, see §5 point 3 and §9 point 1 (no real
  destination exists yet).
- Treating the legacy app's 13-tab sidebar as a valid baseline to "clean up" incrementally —
  rejected; V2 already supersedes it, and building on the legacy shell would have reintroduced the
  exact problem (§2, §4).
