# VINDEX APPLICATION — ARCHITECTURE ADVERSARIAL REVIEW

Status: analysis only. The frozen prototype in `prototype/vindex-next-app/` was **not modified** to
produce this document — see `git status` (no tracked files changed) and the persisted screenshots in
`review/`, recaptured from the untouched HTML/CSS. No production code was read-modified; all backend
citations below are read-only evidence gathered specifically for this review.

Method: every verdict below is falsification-first — the default assumption is that the prototype
decision is wrong until repository evidence says otherwise. Several verdicts below **reverse or
qualify** conclusions written during the night sprint itself; that is the intended outcome of this
gate, not a failure of it.

---

## 3. Vertical-coupling test

| Concept | Verdict | Why |
|---|---|---|
| Danas | **UNIVERSAL** (information model) / CONFIGURABLE (trigger types) | "One triage screen, two urgency tiers, calm empty state" doesn't know what industry it's in. The row *types* that populate it (ročište, rok) are Legal today; a compliance deployment would populate the same two-tier stream with KYC-refresh/reporting triggers instead. The architecture doesn't need to change — the trigger vocabulary would. |
| Predmet | **AMBIGUOUS** — see §4, the dedicated test | Function (the object all work organizes around) reads universal; schema and vocabulary are Legal-coupled today. |
| Klijent | **UNIVERSAL** | Every target vertical has a party-of-record concept (account holder, policyholder, taxpayer). The relationship is universal; only the label is Legal-flavored, which is correct, not a defect (§11 principle: labels aren't genericized pre-emptively). |
| Rok | **UNIVERSAL** | A date with a consequence attached, requiring an explicit confirm/reject (`rokovi/odluka.js`), is a pattern banking compliance (regulatory reporting), insurance (claim-response windows), and tax (filing dates) all need verbatim. Only the deadline's legal basis differs. |
| Dokument / Spis | **UNIVERSAL pattern, vertical-specific word** — see §11 | The 72ch reading surface, deep-link discipline, and empty-vs-failed distinction are vertical-agnostic. |
| Znanje | **NEEDS REVIEW** — see §9 | Intent ("what does the applicable rule say") generalizes; whether the current merge stays coherent as more sources are added is not proven. |
| Kancelarija | **UNIVERSAL**, boundary needs an explicit rule — see §10 | "How I run the firm as a business" is vertical-agnostic; the boundary against Predmeti needs to be written down, not just implied. |
| The sphere | **UNIVERSAL** (visual object) / **CONFIGURABLE** (data contract) | See §5 — the object survives verticals; the four metrics do not, as written. |
| Global search | **UNIVERSAL** | "Find the thing I'm thinking of by name" has no vertical coupling at all. |
| Primary navigation (4–5 spaces) | **UNIVERSAL pattern**, mostly universal instance | Danas/Predmeti/Kancelarija/search would work verbatim in any vertical. Usklađenost is *already* proof the architecture can add a vertical-specific space behind a permission gate without disturbing the other four — this is evidence the pattern scales, not a risk. |
| Home architecture (decision method) | **UNIVERSAL** | The method — evaluate every Home candidate against a real, evidenced need and default to rejection — doesn't reference Legal anywhere in its own logic. |

**Conclusion**: the prototype is closer to *platform architecture with a Legal-flavored vocabulary
layer* than to a Legal-only design. The one real exception — where the coupling goes below vocabulary
into schema — is Predmet, addressed next.

---

## 4. Core work-object test

**What Predmet actually is, structurally**: a `predmeti` table referenced by `predmet_id` across
**146 files under `routers/`** (grep evidence) — this is deep, load-bearing coupling, not a thin
presentation label sitting on a generic table. Nearly every backend capability (spisi, rokovi,
naplata, saradnja, profitabilnost) is scoped by this one foreign key.

**Is it Legal-specific at the schema level?** Yes, partially. Migration `015_predmeti_extra_fields.sql`
added `tuzilac`, `tuzeni`, `rizik`, `vrednost_spora` (plaintiff, defendant, risk, value-in-dispute) as
**nullable** columns directly on `predmeti`. This is litigation vocabulary baked into the core table —
not in a satellite/extension table. The coupling is *soft* (nullable, so a non-litigation record
doesn't break anything by leaving them null) but it is real: a notarial deed or a compliance file has
no "tuženi," and today's schema has no clean place to put whatever *that* record's equivalent
distinguishing fields would be, other than adding more nullable columns to the same table indefinitely.

**Verdict: NEEDS ABSTRACTION LATER.**

Not SAFE AS-IS, because the pattern of bolting nullable vertical-specific columns onto one shared
table is already visible in the migration history and will not stay clean as a second vertical is
added. Not STRUCTURAL RISK, because the coupling is soft (nullable columns, opaque `predmet_id`
foreign keys everywhere else) — nothing here requires a rewrite to keep Legal working, and nothing
here has yet caused an actual defect. The correct time to introduce a canonical internal work-object
identity distinct from the litigation-shaped `predmeti` table is **before** a second vertical is
built against it, not now and not never. This document does not propose a schema change — it records
that one will eventually be needed and names the exact evidence (`015_predmeti_extra_fields.sql`,
146-file coupling) a future decision should start from.

---

## 5. Sphere future-proofing test

Visual object preserved exactly, per instruction. Data contract only:

| Metric | Business meaning | Source entity | Time boundary | Exists today? | Aggregation exists? | Meaningful outside Legal? |
|---|---|---|---|---|---|---|
| Aktivni predmeti | Count of predmeti with an active status | `predmeti.status` (used today by the registry's status column) | None needed (a snapshot count) | Yes | **Yes — cheap.** A count-by-status query needs no schema change. | Yes, immediately — "how many open matters" generalizes to any vertical without modification |
| Aktivni rokovi | Count of active deadlines | Danas's existing `/api/workspace` tier1/tier2 computation (`domain/danas.js::komponujDanas`) | Implicit in "active" (not yet resolved) | Yes | **Yes — already computed as a byproduct of data Danas already fetches.** | Yes |
| Novi klijenti | Count of "new" clients | `klijenti` table | **Undefined.** No code anywhere defines "new" — not since-signup, not a rolling window, nothing | **No — semantically undefined, not just unaggregated** | No | Cannot be evaluated until defined — this is not a vertical-coupling question, it's a missing product decision |
| Nepročitani dokumenti | Count of unread documents | Would need a per-user read/view record on spisi | N/A — no boundary exists because no tracking exists | **No — no read/unread flag or view-tracking concept found anywhere in `routers/` or `shared/`** | No | Cannot be evaluated until it exists |

**Attacking "Novi klijenti" specifically, as instructed**: this metric fails at the definition level,
not the implementation level. "Novi" requires an event boundary (since account creation? since last
login? trailing 30 days?) that has never been chosen. Marking it "representative/dummy" in the night
sprint prototype was the correct interim move, but this line item **cannot be promoted to canon** in
its current form — it needs a product decision before it needs a query.

**A vs. B (is the sphere permanently these four metrics, or a canonical four-signal object with
configurable metric definitions?)**

**B is the safer principle**, and the evidence above is exactly why: two of the four metrics
(Aktivni predmeti, Aktivni rokovi) are real and cheap *today*, from data the product already has,
while the other two are not just unimplemented but **undefined**. If the sphere's identity were
locked to these specific four labels, the day "Novi klijenti" gets a real definition or a compliance
deployment needs a different fourth signal, the *visual object itself* would need to change to
accommodate it — which is the coupling the brief warned about. Treating "four ambient operational
signals, chosen per deployment/product-tier" as the canon, with these four as **the Legal reference
implementation**, keeps the object stable while leaving the metrics honest.

---

## 6. Home ≠ dashboard test

Testing the candidate formulation (A. what needs action / B. what's next relevant / C. where did I
leave off / D. how do I start the most common new work) against the frozen prototype:

- A — Traži pažnju: satisfied.
- B — Uskoro: satisfied.
- C — Nedavno završeno/otvoreno: satisfied.
- D — "Novi predmet" primary button: satisfied, **but only for the single most common new-work
  action.** The formulation says "most common," singular — the prototype respects this (one button,
  not a menu), so it does not fail its own test. It would fail only if a second frequent creation
  action existed and were hidden; none does today per the capability matrix.

**Attempting to disprove it**: the formulation says nothing about *system-surfaced intelligence* that
isn't attached to a deadline or a document (e.g., a Vindex Intelligence finding with no calendar
trigger). The night sprint's Home Architecture doc already rejected inlining "system intelligence" as
a separate Home block and folded it into Brifing instead — this is consistent with the formulation,
not a gap in it, but it means the formulation is incomplete as *written* (it doesn't mention
system-surfaced findings at all) even though the actual Home implementation handles this case
correctly via Brifing. **Recommendation: amend the formulation to an explicit fifth line — "E. Šta mi
sistem otkriva, van rokova i dokumenata" (answered via the Brifing link, never inlined)** — this
closes the gap in the *documentation* without changing the *design*, which already does the right
thing.

**"Danas" as a name — does it create calendar-bound bias?**

Direct evidence against the worry: the "Kritično" item in the prototype (`Rešenje suda još nije
pregledano`) has **no date at all** — its `vx-radna-stavka__kada` field renders the word "Kritično,"
not a day. The underlying production code (`view.js`) already handles this: `radnaStavka()` items
(case_action/task/document-review triggers) are calendar-independent by construction; only
`stavka()` items (confirmed rok/ročište) carry a date. **The name "Danas" does not constrain the
information model** — the model already surfaces non-dated urgent items under the same "Danas" roof
without contradiction, because "Danas" means "what's true right now," not "what's on today's
calendar." Verdict: name is safe.

---

## 7. "Traži pažnju" abuse test

No UI designed here, per instruction — admission contract only.

| Category | Admitted? | Trigger | Why action is required | Priority | Expiration | Dismissible? | Destination |
|---|---|---|---|---|---|---|---|
| Overdue deadline | **Yes** | Date passed, no resolution recorded | Consequence already accruing | Highest | Never (stays until resolved) | No | Predmet · Rokovi |
| Deadline due today/imminent | **Yes** | Date within window | Action window closing | High | Rolls into overdue if missed | No | Predmet · Rokovi |
| Confirm/reject a system-proposed deadline | **Yes** | `rokovi/odluka.js` proposal created | An unconfirmed date has no legal effect until a human accepts it | High | Until confirmed or rejected | No (must be resolved, per existing `kontrolaOdluke` control) | Inline decision control |
| Unread critical document (e.g. new court ruling) | **Yes** | New spis of a type the system knows changes case posture | A ruling changes what's true about the case | High | Until opened | No | Predmet · Spisi (via `citac.html`) |
| Task (zadatak) | **Yes** | User- or system-created task with a due signal | Explicit commitment to do something | Medium | Per task due date | Yes, on completion | Predmet · Rokovi i zadaci |
| Failed processing (e.g. document extraction failure) | **Yes, conditionally** | A pipeline step failed and needs a human fallback | Without action, data silently doesn't exist | High | Until acknowledged | No | Predmet, relevant section |
| Missing information the system needs to proceed | **Yes, conditionally** | A confidence-below-threshold extraction, per V2's existing intake contract | System explicitly refuses to guess (documented behavior in `uvoz.js`/COI flow) | Medium–High | Until supplied | No | Predmet · relevant field |
| Vindex Intelligence finding (no deadline/document attached) | **No — never directly.** | — | — | — | — | — | Routed to **Brifing**, never inlined into Traži pažnju (already the shipped rule, `view.js` header comment) |
| Plain notification (e.g. "your export finished") | **No** | — | Informational, not decision-requiring | — | — | — | Obaveštenja screen only |
| Billing event (invoice sent, payment received) | **No** | — | Informational unless a payment is *overdue* — that case re-enters as a deadline-shaped item, not a "billing event" category | — | — | — | Kancelarija / Naplata |
| System/security warning (e.g. new login, credential change) | **No** | — | Belongs to account security surfaces, not case-attention triage — mixing them would train users to ignore one or the other | — | — | — | Account/security area |

**Testing "informational activity alone must never enter Traži pažnju"**: attempted falsification —
is there a case where something purely informational genuinely deserves top billing? The closest
candidate is a security event (e.g., "someone logged into your account from a new device"), which
*feels* urgent. But routing it into Traži pažnju would conflate two different mental models — "things
about my open cases" and "things about my account" — and the existing V2 architecture already keeps
these separate (Obaveštenja vs. the priority stream). **The principle survives the attempt to
falsify it.**

**Verdict: DEFINED.** A durable admission rule exists — *an item is admitted only if a specific,
resolvable action would change its state, and it is rejected if the only available response is "I
have read this."* This is not merely a restated minimalism preference; it is testable per-item
(every row in the table above was classified by asking exactly this question), which is what makes it
an admission *contract* rather than a slogan.

---

## 8. Navigation scale test

Testing "a top-level item represents a durable user mental space, never an individual feature":

Attack: does this rule survive a scenario where a genuinely important new capability doesn't fit any
existing space? Example — if Vindex added a firm-wide *analytics* capability, does it get a 6th nav
item, or does it belong inside Kancelarija ("how I run the firm")? Per the rule, it belongs inside
Kancelarija (analytics-about-the-firm is not a new *mental space*, it's a new *view within* the
existing "run my firm" space) — the rule correctly resolves this without inventing a new top-level
item, which is evidence the rule is load-bearing, not decorative.

Per-item test:

| Item | Territory owned | Explicitly excluded | Junk-drawer risk | Survives module growth? | Understandable without training? |
|---|---|---|---|---|---|
| Danas | "What needs my attention right now" | Anything not attention-worthy; firm-wide stats; research | Low — the admission contract in §7 is the guard | Yes — new trigger *types* slot into existing tiers | Yes |
| Predmeti | "Where I do case work" | Firm-level finance/admin; legal research not tied to a case | Low | Yes — new per-case capabilities are new sections inside Dosije, not new nav items (already the pattern: profitabilnost, poređenje, saradnja all live inside, not beside, Predmeti) | Yes |
| Znanje | "What does the applicable rule/precedent say" | Case-specific facts; firm admin | **Medium — see §9** | Conditional on §9's resolution | Yes, though more abstract than the legacy names it replaced (flagged in the UX doc already) |
| Kancelarija | "How I run the firm as a business" | Individual case content | **Medium — see §10** | Conditional on §10's boundary being written down and held | Yes |
| Usklađenost (permission-gated) | A specific regulated-vertical module | Everything not digital-asset-compliance-specific | Low — it's a single, narrow, named capability, and it's exactly the mechanism that proves the platform *can* add a vertical module without disturbing the other four | Yes, by construction (proof of scale, not a risk) | Only to the specific audience it's gated to, which is correct |

No item was found today that has already become, or is structurally likely to become, a junk drawer
independent of the two flagged risks below.

---

## 9. "Znanje" junk-drawer test

Capabilities plausibly under Znanje, from evidence: legal research (statute RAG), sudska praksa (case
law), and — per the night-sprint terminology table — the legacy "Vindex Intelligence" tab, all merged.
Šabloni (document templates) is **not** under Znanje; it lives under Predmeti (`predmeti/sabloni.js`)
today, correctly, since "give me a starting document" is a drafting-acceleration intent, not a
research intent — if a future iteration ever pulled templates into Znanje "because it's about legal
content," that would be the junk-drawer failure mode materializing; it has not happened.

Testing whether "legal research," "case law," and "Vindex Intelligence" share one intent: research
(statutes) and case law both answer "what does the law say about X" from two source types — a
coherent single question. Whether "Vindex Intelligence" shares that same intent **could not be fully
confirmed from the evidence gathered this session** — its precise legacy scope (was it purely
research-flavored, or did it include something more like a general AI-assistant surface with a
broader remit?) was not independently re-verified beyond the earlier terminology-table finding that
it was folded into Znanje.

**Verdict: NEEDS REVIEW** — not because a problem was found, but because the merge's coherence rests
on one fact (Vindex Intelligence's actual legacy scope) that this review could not independently
confirm in the time available. This is an honest "unresolved," not a downgrade dressed as caution.

---

## 10. "Kancelarija" junk-drawer test

Categories already folded in per evidence: administration, finance (firm-level, distinct from
per-case Naplata), portfolio (case-wide overview), settings. No staff/roles capability was found in
the capability matrix as a distinct, shipped item to evaluate.

**Defensible boundary, stated explicitly (this review's contribution, not previously written down
anywhere found in the repo):**

> **Belongs in Kancelarija**: anything whose subject is the firm as a business entity — its finances
> in aggregate, its configuration, its case portfolio *as a statistic* (counts, distributions), not as
> a way to open a specific case.
> **Must never be put there**: anything whose subject is a single case, client, or document. A case's
> own Naplata entries belong in that case's Dosije (already correct in the prototype); Kancelarija may
> show the *aggregate* of all cases' billing, never a way to edit one case's line items.

The specific risk this boundary guards against: "portfolio" (a firm-wide case overview) drifting into
duplicating the Predmeti registry if the distinction between *statistic* and *individual-record
access* isn't held. No evidence this has already happened — the capability matrix lists Portfolio as
its own item, separate from the registry — but the boundary has not been written down anywhere
findable before this document, which is itself the debt.

**Verdict: architecture debt (boundary undocumented, not boundary broken).** Not yet a junk drawer;
will become one silently if a future feature is added to Kancelarija without checking it against the
rule above.

---

## 11. Document vs. Spis long-term test

**Spis in V2, confirmed by direct evidence**: consistently a single item. `citac.js` renders one
document per reader screen, addressed by `?spis=<dokId>` (one ID, one document). No usage of "spis"
as a collection noun was found in V2.

**Dokument in the legacy app**: not independently re-verified this session (the earlier night-sprint
fork reported "Dokumenti" as the legacy top-level tab name, implying it names the collection/section,
which is a different grammatical role than V2's "Spis" naming the item) — flagged as an assumption
carried forward, not newly confirmed.

**Does either word create unnecessary Legal coupling?** No. "Spis" (case file/document, a standard
term in Serbian legal and general administrative usage) and "Dokument" (generic "document") are both
already close to vertical-neutral in ordinary Serbian usage — neither is a piece of litigation
jargon in the way "tužilac/tuženi" are. This is a naming-consistency issue, not a vertical-coupling
issue.

**Canonical terminology recommendation** (naming only, not implemented — no rename performed):
**"Spis" for the individual item, reserved for a plural/section label ("Spisi") only when referring to
the collection within a Predmet** — i.e. keep exactly what V2 already does. The legacy app's
"Dokumenti" survives only in the legacy app, which this sprint does not touch. No further action is
recommended beyond what the UX Architecture document (from the night sprint) already recorded.

---

## 12. Document-intake falsification

**This is the most significant reversal produced by this review.**

The night sprint's Home Architecture document stated: *"A document upload with no case attached is
not a real action in this product... Rejected."* This is **proven false** by direct evidence:
`v2/features/predmeti/uvoz.js` (route `/app-v2/predmeti/uvoz`) already implements exactly
DOCUMENT → CLASSIFICATION → PREDMET as a first-class, shipped flow — its own header comment states
the contract in these words: *"PREDMET NASTAJE IZ DOKUMENTA, ALI NE BEZ ADVOKATA"* (the case is
created from the document, but not without the lawyer). The "new predmet" screen has two co-equal
tabs, "Ručno" and "Iz dokumenta" — manual creation is not the only or primary path. The backend
(`routers/dokument.py::dokument_upload`, a `tmp_`-prefixed session storage namespace) confirms
documents are held in temporary, session-scoped storage **before** any `predmet_id` exists, pending
lawyer review and classification.

Answering the specific questions:
- Can a document arrive before its predmet is known? **Yes — already shipped.**
- Does the backend support temporary/unassigned intake? **Yes — session-scoped `tmp_` storage,
  transitional by design, always resolving toward a predmet (not a permanent "unfiled" inbox).**
- Would forcing predmet selection first increase user work? **Yes, measurably — this is exactly what
  `uvoz.js` exists to avoid: extracting predmet identity from the document instead of asking the
  lawyer to type it first.**
- Would unassigned intake create integrity/security risk? **Mitigated already**: the flow is
  session-scoped and always requires lawyer confirmation before a predmet is created — it is not an
  open, unauthenticated inbox.
- **Is Home the correct entry point even though the flow is valid?** No evidence either way was
  found — `uvoz.js` is reached from **Predmeti**, not Danas, today. Whether it *should* also be
  reachable from Home is a genuine open product question, not something this review can resolve from
  existing evidence, since no version of it has ever been placed on Home to observe.

**Verdict: REJECTION QUESTIONABLE.** Not "correct" (the premise the night sprint reasoned from — "no
existing V2 screen does this" — was factually wrong) and not cleanly "incorrect" either, because the
narrower claim actually relevant to Home placement (should *Home specifically* offer document-first
intake) remains a real, unresolved product decision, not something either sprint had evidence to
settle. The Home Architecture document should be corrected to stop citing a nonexistent gap, and the
placement question should be logged as open rather than answered by omission.

---

## 13. Minimalism cost test

Ten highest-frequency workflows (frequency claim grounded in the capability matrix's own IMPLEMENTED
set and Danas's own bucket weighting, not invented):

| Workflow | Current V2 | Prototype | Interaction delta |
|---|---|---|---|
| Open today's most urgent item | Danas → click item | Same | None |
| Open a specific known case | Predmeti search → click row | Registar search → click row | None |
| Create a new case manually | Predmeti → Nov predmet | Danas or Registar → Novi predmet | **Improved** — reachable from Home in the prototype, not only from Predmeti |
| Create a new case from a document | Predmeti → Nov predmet → "Iz dokumenta" tab | **Not represented in the prototype at all** | **Regression risk, not shown as a workflow** — see §12; the prototype's Home doesn't expose this real, frequent path |
| Read a case document | Dosije → Spisi → click → Čitač | Predmet → Spisi → click → Dokument | None |
| Confirm/reject a proposed deadline | Inline control in Danas/Dosije | Same control referenced, present in Predmet's Rokovi section | None |
| Check firm billing status for a case | Dosije → Naplata | Predmet → Naplata | None |
| Search for anything by name | Ctrl/Cmd+K or shell search box | Same | None |
| Review recently completed work | Danas rail | Same | None |
| Jump back into a recently opened case | Danas rail → click | Same | None |

**Flagged regression**: workflow #4 (create-from-document) exists in current V2 and is **not
represented anywhere in the prototype's four screens or its Home Architecture document as a retained
Home candidate** — it was evaluated as if it didn't exist, because the sprint didn't find it. This is
the direct, concrete workflow-level consequence of the §12 finding, not a new issue.

No other workflow shows interaction inflation. The registry (`Registar`) and Predmet screens replicate
V2's existing click-depth exactly; the only structural change tested (the 3-zone header grid, the
sphere) doesn't add a click to any of the ten flows above.

---

## 14. Bone/black material falsification

Screens actually built and checked (not asserted): Danas (mixed), Predmet (100% bone), Dokument
(100% bone), Registar (100% bone). All three non-Home surfaces are fully bone, confirming "bone for
reading, input, evidence, structured operational work" already holds for everything this sprint
built.

Attacking "every work surface is bone" specifically against surfaces **not yet built**: a
relationship map or transaction graph (mentioned in the brief as a stress case) is a fundamentally
different information type — dense node/edge diagrams generally read *better* on a dark canvas
because edge lines and node glow have more available contrast range, and several serious analytical
tools (network/graph visualization specifically) default to dark canvases for exactly this reason,
not as a stylistic choice. Forcing such a canvas onto bone would fight the fill-heavy diagram styling
already used elsewhere in this codebase's own SVG diagrams (the website's `/kako-radi` and
`/tehnologija` diagrams use dark boxes on a dark/mixed scene, not bone boxes on paper, for comparable
node/edge content) — actually contrary evidence: **check needed, not assumed** — this review does not
have a built relationship-map screen to test against, so no verdict can be issued from direct
evidence here.

**Resolution**: the brief's proposed stronger principle — *"Bone is the default material for reading,
input, evidence, and structured operational work; black is the system environment and may also host
specialized analytical canvases where the representation objectively benefits"* — is **adopted as the
more durable rule**, on the strength of the evidence that exists (100% bone across every built work
surface, zero counter-evidence built) plus the standing exception already proven necessary by the
sphere itself (an analytical/ambient object that could not sensibly live on bone). This is a
documentation correction, not a design change: it names the exception the sphere already represents
instead of leaving "every" technically false the day a graph visualization is eventually built.

---

## 15. Serif usage stress test

Direct count in the frozen prototype: `.vx-title` (serif) appears exactly once per screen — the page
identity heading ("Ponedeljak" on Danas, the case name on Predmet, the document title on Dokument,
"Predmeti" on Registar) — plus the shell wordmark. **Zero** table cells, zero row content, zero form
labels, zero button labels, zero metadata anywhere in `foundation.css` or the four HTML pages use
`.vx-serif`/`.vx-title`. Registry rows (`vx-reg-red__naziv`) are sans, bold, not serif, despite being
the "important" column of that screen — confirming serif was reserved for page-level identity, not
extended to "anything that feels important," which is the specific misuse pattern this test is
designed to catch. **No unnecessary serif usage found.**

---

## 16. Red semantic debt test

Distinct meanings red currently carries in the frozen prototype: brand mark (V incision, wordmark x),
active-nav underline, focus ring, sphere fissures/ambient signal, sphere count >0, one destructive
link ("Obriši predmet"), "Kritično" label text. That is **five or six distinct semantic jobs on one
hue**, which is exactly the collision risk the brief names.

Checking whether hierarchy survives without the color doing all the work: active-nav also has
*position* (top of the shell) and *weight* (bold) carrying the same information redundantly — color
is not the only signal. Focus ring is *only* red, but focus rings are transient and contextual by
convention across virtually all software, so a single-purpose transient use is lower collision risk
than a persistent one. The destructive link ("Obriši predmet") relies on color **and** position
(bottom of the "Napredno," lowest-priority section) **and** wording ("Obriši," an unambiguous verb) —
three redundant signals, not one. The sphere's >0 count is the **least defended** use: it relies on
color alone, with no secondary signal (no icon, no border, no positional change) distinguishing an
attention-worthy count from a calm one.

**Verdict**: red is not yet "everything important" — most uses are redundantly signaled by position,
weight, or wording, which is the correct defense against collision. The one genuinely underdefended
case is the sphere's count color, which is also the one place this review already recommends treating
as a scoped, documented exception (§ Visual Foundation, "Red usage budget") rather than a precedent.
No new color is proposed; the existing defense (redundant signaling, explicit exception documentation)
is judged sufficient, provided the exception stays written down and is not silently extended to a
seventh use.

---

## 17. Novice vs. expert failure test

**Attempting to prove failure A (too complex for a novice)**: the most complex single screen is
Predmet, with five sections. A first-time user lands on a screen with a serif case title, a status
dot, three metadata fields, and five named sections separated by hairlines — no cards, no icons to
decode, no unexplained abbreviations. Every section header is a plain Serbian noun phrase already in
professional use (Spisi, Rokovi i zadaci, Naplata, Saradnja, Napredno). **Could not construct a
concrete failure case** — the screen has no element requiring undocumented prior knowledge to
interpret. This does not prove the screen is optimal, only that no specific novice-failure evidence
was found in the frozen build.

**Attempting to prove failure B (over-simplified, expert work is slow)**: a daily expert user's
highest-frequency action is opening a specific case fast. In the prototype, this requires: Ctrl/Cmd+K
→ type → Enter (three inputs, no mouse) or Registar → type in visible search → click a row (two
inputs). Neither path is slower than current V2's equivalent (same search mechanism, same registry
pattern, unchanged). The one concrete piece of expert-workflow evidence *against* the prototype is
the §12/§13 finding: **document-first case creation, a real and probably-frequent expert workflow, is
absent from the prototype entirely** — not slowed down, simply not shown. This is evidence for a
missing workflow, not evidence that an existing workflow got slower.

**Conclusion**: neither failure mode is demonstrated with concrete evidence inside what was built;
the one real finding (missing document-first creation) is a *coverage* gap, not a speed regression.

---

## 18. Empty / large data stress test

- **Predmeti / Registar**: V2 already paginates at `PO_STRANI = 50` with offset/limit (`predmeti/api.js`),
  not a naive fetch-all — confirmed by evidence, not assumed. The prototype's registry shows 7 rows,
  which does not exercise pagination UI at all; **the prototype does not demonstrate what happens at
  page 2, or what a 0-result search looks like** — this is a real gap in what was *shown*, though not
  evidence that the underlying pattern (a hairline row list) breaks at scale, since row-based lists
  don't have the "empty visual space" failure mode that card grids do.
- **Long names**: the registry CSS sets no `text-overflow: ellipsis` and no `white-space: nowrap` on
  `.vx-reg-red__naziv` — a very long case name will wrap the row taller, consistent with V2's own
  documented stance ("skraćivanje trotačkom nije osnovni dizajn registra," `predmeti.css` header) —
  this was inherited correctly, not by accident.
- **Dokumenti/Spisi and Rokovi inside a Predmet**: the frozen Predmet screen shows 3 spisi and 3
  rokovi/zadaci — a case with 200 spisi was not built or tested. Nothing in `foundation.css` limits
  row count or introduces internal scrolling for a long Spisi section, meaning a 200-document case
  would currently produce one very long page — not broken, but **not verified**, and V2's own Dosije
  has no stated pagination strategy for spisi within a single case per the evidence gathered.
- **0 items**: Danas's calm empty-state sentence is real, shipped V2 behavior, correctly represented.
  The Registar's zero-result search state and the Predmet's zero-spisi state were **not built or
  shown** in this prototype.

**Flag**: the prototype's sample data is curated (3–7 items per list everywhere) and several
zero/many states were asserted from the underlying V2 evidence rather than actually rendered and
looked at. This is a real, named limitation, not resolved by this review.

---

## 19. Multi-role test

Evidence: only one permission gate affects space *visibility* today — `uskladjenost`
(`v2/app.js:52`). No other space (Danas/Predmeti/Znanje/Kancelarija) is conditionally rendered, and no
evidence was found that Danas's *content* differs by role — it appears to be the same screen for
every account that can log in. `shared/permissions.py` and credit/plan tier gates
(`shared/deps.py::require_credits`, `require_pro`) exist but gate **capability**, not **navigation or
Home layout**.

- Does everyone see the same Home? **Yes, as far as evidence shows** — there is no role-based Home
  variance to evaluate, positively or negatively.
- Are actions permission-aware? Individual capabilities are (credit/plan gates exist), but the
  *navigation shell* only reacts to the one `uskladjenost` gate.
- Would a low-permission user see dead zones? **Untested — there is currently effectively one
  functional tier** (plus the compliance-space exception), so this scenario has no real precedent to
  observe. Cannot be marked SAFE, because it has never been exercised; cannot be marked UNSAFE,
  because no failure has been observed either.
- Does navigation communicate unavailable areas gracefully? For the one case that exists
  (Usklađenost), yes — the "does not render if not permitted" rule (§ UX Architecture) avoids the
  disabled-item anti-pattern entirely, which is the correct behavior *if* a second gated space is ever
  added.

**Verdict**: not a demonstrated problem, but an **untested assumption** — the architecture's only
real answer to "what does a partial-permission user see" is "nothing changes, except one whole space
disappears." Whether that binary (full space, or space doesn't exist) scales to more granular
permission needs (e.g., a junior associate who should see Predmeti but not Naplata) has no evidence
either way.

---

## 20. Accessibility / aging-user test

Measured directly on the frozen prototype (390px viewport, Playwright):

| Element | Size | Meets 44px guideline? |
|---|---|---|
| `.vx-btn` (primary/ghost buttons) | 343×44 | Yes |
| `.vx-nav-toggle` (hamburger) | 57×55 | Yes |
| `.vx-ljuska__nalog` ("Nalog" account link) | 32×20 | **No** |
| `.vx-obaveza__veza` (inline priority-stream links) | ~165×21 | No, but inline text-flow links are conventionally exempt from the 44px button guideline |
| `.vx-rail-veza` (sidebar links) | ~164×20 | Same as above |

**Concrete finding**: the "Nalog" (account) link is a standalone, isolated navigation control — not
inline text — and at 32×20px is genuinely under-sized for a conservative, non-technical, possibly
older user on a touch device, unlike the inline content links which follow ordinary web-text
convention. This is the one accessibility finding with no reasonable exemption.

Contrast: `--vx-tx-3` (13:1... corrected: 5.6:1 per token file) on papir and `--vx-tx-3-crna` (4.9:1)
on crna both clear WCAG AA for normal text (4.5:1) — inherited correctly from V2's already-computed
tokens, not re-verified from scratch here since the token file itself documents the ratios.

Keyboard: first Tab lands on a focusable element with a visible `outline: auto` (browser default,
2px-equivalent) — focus is not invisible. However, **no skip-to-content link exists in any of the
four prototype pages** (`.vx-sr` is defined in `foundation.css` but never used in markup) — unlike
the production website, which has one. A keyboard user must tab through the full shell nav on every
page load to reach content.

**Verdict: mostly passes, two concrete named gaps** — the undersized "Nalog" control, and the missing
skip-link (present in the sibling website codebase, absent here).

---

## 21. Static quality gate

Run via Playwright against the frozen, unmodified prototype (see `review/` for the exact screenshots
taken during this same pass):

| Check | Result |
|---|---|
| Missing assets | None — all CSS/font/image requests returned 200 |
| Broken internal links | None — every `.html` href across all 4 pages resolves to an existing file |
| Broken internal anchors (`#id`) | None found |
| Horizontal overflow, 1440 / 1024 / 390 | 0px on all 4 pages at all tested widths |
| Duplicate IDs | None found, any page |
| Interactive controls missing an accessible name | None found |
| Images missing `alt` | None found |
| Primary keyboard navigation | Tab reaches interactive elements; visible focus confirmed on first stop |
| Mobile nav open/close | Functionally verified — toggle click sets `data-otvoren`, nav becomes visible, screenshot persisted (`mobile-nav-open-390.png`) |

**Result: PASS**, with the two accessibility gaps recorded in §20 as separate, named findings (not
gate failures — they are sizing/omission issues, not broken functionality).

---

# ISSUE REGISTER

### P0 — would structurally damage future Vindex

**P0-1 — Sphere's "Novi klijenti" and "Nepročitani dokumenti" have no real definition or data source.**
- Evidence: no `created_at`-based "new" business rule found anywhere in `routers/klijenti.py`
  reasoning; no read/unread tracking found anywhere in `routers/` or `shared/`.
- Why it matters long term: if the sphere is promoted to canon with these four labels treated as
  fixed, the product ships a visual promise ("Vindex tracks unread documents") the backend cannot
  keep — a credibility risk of the exact kind this whole project has spent the session eliminating
  from the public website.
- Current prototype assumption: the four labels are final.
- Safer principle: the sphere is a canonical four-*signal* object; specific metrics are a
  product/vertical configuration, and no metric ships as real until its business definition and data
  source both exist (§5, option B).
- Decision required: define "new client" (owner decision) and decide whether "unread document"
  tracking is worth building at all, before either metric is presented as live.
- Implementation impact: none yet — no code exists to fix; this blocks *promoting the sphere to
  canon* with these exact four metrics, not the visual object itself.

### P1 — must resolve before prototype becomes implementation canon

**P1-1 — Home Architecture document rejected document-first case creation based on a false premise.**
- Evidence: `v2/features/predmeti/uvoz.js` already implements DOCUMENT → CLASSIFICATION → PREDMET,
  contradicting the night sprint's stated reason for exclusion.
- Why it matters: a real, shipped, probably-frequent workflow is invisible in the architecture that's
  meant to represent "what Home should be."
- Current prototype assumption: document-first intake doesn't exist as a real product capability.
- Safer principle: re-evaluate whether `uvoz.js`'s flow deserves a Home entry point using the correct
  premise (it exists) — this may still conclude "no," but not for the reason written down today.
- Decision required: product decision on whether Home should surface this path.
- Implementation impact: a Home Architecture doc correction (text only); a possible future Home
  button/link if the decision is yes.

**P1-2 — Predmet's core schema has litigation-specific columns (`tuzilac`, `tuzeni`, `vrednost_spora`)
baked into the shared table, not an extension table.**
- Evidence: `migrations/015_predmeti_extra_fields.sql`; 146-file `predmet_id` coupling across `routers/`.
- Why it matters long term: every additional vertical will either leave these columns null forever
  (harmless but messy) or the table will keep growing nullable vertical-specific columns
  indefinitely (a well-known anti-pattern that becomes expensive to unwind after enough verticals
  exist).
- Current prototype assumption: "Predmet" is implicitly treated as if it were already generic.
- Safer principle: before a second vertical is built, decide whether to introduce a canonical
  internal work-object identity with vertical-specific fields moved to extension tables — a schema
  decision, not a UI one.
- Decision required: owner/engineering decision, out of scope for this or any prototype sprint.
- Implementation impact: potentially significant (schema migration) but explicitly **not** something
  this review recommends doing now — it recommends deciding *when* to do it before it gets more
  expensive.

**P1-3 — "Znanje" merge coherence (legal research + case law + legacy "Vindex Intelligence") not
independently confirmed.**
- Evidence: terminology-table claim from the night sprint, not re-verified this session; "Vindex
  Intelligence"'s actual legacy scope unknown.
- Why it matters: if "Vindex Intelligence" was actually a broader AI-assistant surface rather than a
  research-specific tool, folding it into "Znanje" may already be a junk-drawer in progress.
- Current prototype assumption: the merge is coherent.
- Safer principle: don't assume; read the legacy capability's actual scope before treating the merge
  as settled.
- Decision required: none yet — an evidence-gathering task, not a product decision.
- Implementation impact: none unless the finding reverses the merge.

**P1-4 — Kancelarija/Predmeti/Registar boundary was never written down anywhere in the repository.**
- Evidence: no boundary rule found in any doc; this review had to construct one (§10) from first
  principles.
- Why it matters: an undocumented boundary is a boundary that erodes the first time someone adds a
  feature under time pressure.
- Current prototype assumption: the boundary is "obvious."
- Safer principle: the rule stated in §10 ("subject is the firm as an entity, vs. subject is a single
  case/client/document") should be written into the canonical UX Architecture document, not just this
  review.
- Decision required: none — this is a documentation action.
- Implementation impact: none; documentation only.

**P1-5 — "Nalog" account control is under the 44px touch-target guideline on mobile.**
- Evidence: measured 32×20px at 390px viewport.
- Why it matters: the target user includes conservative, non-technical, potentially older
  professionals — the exact persona most likely to mis-tap a small isolated control.
- Current prototype assumption: acceptable as inline-style text.
- Safer principle: any standalone (non-inline-text-flow) interactive control should meet the 44px
  guideline, regardless of how minor it looks in a mockup.
- Decision required: none — implementation fix, deferred per the no-implementation rule of this phase.
- Implementation impact: minor CSS-only change, not performed in this phase.

### P2 — can be resolved during component/system implementation

- **P2-1**: No skip-to-content link in any of the 4 prototype pages (present on the sibling public
  website, absent here) — §20.
- **P2-2**: Prototype was never shown at pagination page-2, at a 0-result search state, or with a
  long (200+) spisi list inside one Predmet — §18. Not proven broken; not proven fine either.
- **P2-3**: Multi-role/partial-permission Home experience has zero real precedent to test against
  today — §19. Not a defect; an untested assumption worth flagging before more roles exist.
- **P2-4**: Home formulation (§6) doesn't explicitly mention system-surfaced findings without a
  deadline/document attached, even though the actual design (Brifing link) already handles this
  correctly — a documentation completeness gap, not a design gap.

### P3 — optional refinement

- **P3-1**: Bone/black material rule should be restated as "bone is default; black may also host
  specialized analytical canvases where representation objectively benefits" rather than "bone is
  every work surface," to pre-empt a future literal contradiction when a graph/network view is
  eventually built — §14.
