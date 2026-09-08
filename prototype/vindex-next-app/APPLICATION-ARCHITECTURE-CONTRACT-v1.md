# VINDEX APPLICATION — ARCHITECTURE CONTRACT v1

Status: **proposed governing contract for future implementation, not yet owner-locked.**
This document resolves the open questions raised by `ARCHITECTURE-ADVERSARIAL-REVIEW.md`. It does not
modify the frozen prototype, production code, or the database. Every rule below is actionable — a
future implementer should be able to make a decision by consulting this document without re-deriving
the reasoning.

---

## 1. Platform vs. vertical boundary

Proven, not assumed, per concept (full reasoning in the adversarial review §3):

| PLATFORM DNA (survives any vertical) | VINDEX LEGAL CONFIGURATION (Legal-specific today) |
|---|---|
| Black/bone/red material grammar | `predmeti.tuzilac` / `.tuzeni` / `.vrednost_spora` fields |
| Source Serif 4 / Source Sans 3 / JetBrains Mono, and their three roles | Legal research sources (statute/case-law corpus) under Znanje |
| The sphere as a four-signal ambient object | The sphere's *current* four signal definitions (§3 below) |
| Horizontal navigation as "durable mental spaces, never features" | The specific five space names (four generalize as-is; Usklađenost is explicitly vertical) |
| Danas's two-tier attention model (Traži pažnju / Uskoro) and its admission contract | The specific trigger *types* that populate it (ročište, rok) |
| Global search-as-accelerator, never modal-only | — |
| Progressive disclosure (anchor strip over tabs, below-the-fold advanced sections) | — |
| "A top-level item is a mental space" navigation constitution | — |
| The principle that Predmet-equivalent objects organize all work | The word "Predmet" and its Legal-shaped schema (§7) |

**Why each classification was earned, not assumed**: every PLATFORM DNA row was tested in the
adversarial review by asking whether it still makes sense if the trigger vocabulary or vertical
changes — the visual grammar, the type roles, the sphere-as-object, the navigation rule, and the
attention model all passed that test without modification. Every LEGAL CONFIGURATION row failed the
same test — a notarial file has no `tuzilac`, and the sphere's "Novi klijenti" is not even a settled
concept in Legal itself yet (§3), let alone portable.

**Objective this boundary serves**: a future vertical should be able to arrive with new trigger types,
new Znanje sources, and new sphere signal *values* — without anyone needing to touch the shell, the
type system, the navigation rule, or the attention admission contract. Legal must not be weakened to
make this true; nothing above asks Legal to become generic.

---

## 2. Home responsibility (single governing sentence)

> **Danas exists to tell the user, in under a few seconds, what in their open work has changed or
> become urgent since they last looked, and to give them exactly one obvious way to start the most
> common new thing — nothing that is true does not belong on it, and nothing that is not both true
> and worth acting on does.**

This is deliberately not "everything important," "dashboard," or "overview" — it names three
concrete, testable duties (what changed/is urgent, orientation on continuing work, one obvious
start-point) and one explicit exclusion (informational-only content, per the Traži pažnju admission
contract below).

**Danas the name vs. the information model**: the name does not calendar-bind the model. Direct
evidence (adversarial review §6): the shipped `radnaStavka()` item type already renders
calendar-independent urgent items (e.g. "Kritično — Rešenje suda još nije pregledano," no date field
at all) under the same Danas roof as dated items, with no contradiction. "Danas" means *what is true
right now*, not *what is on today's calendar*. This rule is retained as-is; no rename is proposed or
required.

### Admission contracts

**TRAŽI PAŽNJU**
- Why it exists: the single highest-urgency question Home answers.
- May enter: overdue deadlines, imminent deadlines, unconfirmed system-proposed deadlines, unread
  documents the system knows changed case posture, tasks with a due signal, failed processing needing
  a human fallback, missing information blocking a system step.
- Must never enter: plain notifications, billing events (unless the billing event *is* an overdue
  payment, which re-enters as a deadline-shaped item, not a "billing" category), security/account
  events, system-surfaced intelligence with no deadline or document attached (routes to Brifing
  instead, never inlined — already shipped behavior).
- Ordering: two tiers only (critical/overdue first, then time-window-approaching), never a third tier,
  never per-category grouping.
- Expiration: an item leaves only when its underlying state resolves (deadline confirmed/passed and
  handled, document read, task completed) — never on a timer, never by being "seen."
- Empty state: one calm sentence, never multiple "nothing here" messages per category (shipped
  behavior, retained).
- Click destination: the specific object's relevant section (Predmet · Rokovi, Predmet · Spisi) —
  never a generic "see all" list, unless a real destination for the aggregate exists (it usually does
  not; see the "+N" rule already shipped in `view.js`).

**USKORO**
- Why it exists: answers "what's next," distinct from "what can't wait."
- May enter: confirmed deadlines/ročišta beyond the immediate window.
- Must never enter: anything already in Traži pažnju; anything with no confirmed date.
- Ordering: chronological.
- Expiration: rolls into Traži pažnju as its window closes, or resolves.
- Empty state: the item simply doesn't render; Uskoro can be legitimately empty while Traži pažnju is
  not, and vice versa — no forced parity between the two sections.
- Click destination: same rule as Traži pažnju.

**NEDAVNO (rail: završeno / otvoreno)**
- Why it exists: answers "where did I leave off" — a permanent orientation aid, not a fallback shown
  only when the main streams are empty (already shipped; retained deliberately, per Wave 2's own
  documented reasoning that attention and context are independent information).
- May enter: recently completed case actions; recently opened cases (by `created_at`, named
  accurately as such, not as "recently used").
- Must never enter: anything requiring action (that belongs in Traži pažnju/Uskoro, not here).
- Ordering: recency.
- Expiration: rolling window (matches existing implementation, not renegotiated here).
- Empty state: the section is simply omitted if empty; no placeholder text needed for a
  non-primary rail element.
- Click destination: the object itself.

**PRIMARY ACTION**
- Why it exists: gives every visit to Home exactly one obvious way to start the single most common
  new-work action, so a user is never staring at Home wondering how to begin.
- May enter: exactly one visually dominant action.
- Must never enter: a second action at equal visual weight (that defeats the purpose; see §5/§6 for
  how a second real workflow is handled without violating this).
- Click destination: the start of that workflow.

**SPHERE**
- Why it exists: an ambient, wordless read of "how loud is today," resolved fully in §3 below.

---

## 3. Sphere contract (P0 resolution)

**SPHERE VISUAL CONTRACT — LOCKED, unchanged from the owner-approved asset:** complete dark faceted
sphere, canonical red fissures, no red circumference, no artificial separators between the four
signal slots, zero → ivory, non-zero → `#8E0B23`. Nothing in this section touches the visual object.

**SPHERE DATA CONTRACT — MODEL B, not Model A.**

Attempting to falsify Model B (configurable signals) before accepting it: the strongest case for
Model A (permanently these four metrics) is visual/brand simplicity — one fewer configuration surface
to maintain, one sentence to explain forever. That case fails on the evidence already gathered:
two of the *current* four metrics are not implementable today without new product decisions and, in
one case, new tracking infrastructure (below). If the visual object's identity were locked to these
four specific labels, the day either gets a real definition, the object itself would need to change —
which is precisely the coupling this review exists to prevent. Model B — a canonical four-*signal*
object whose specific signal definitions are supplied by the active product/vertical configuration —
survives the attempt to falsify it and is adopted.

**SIGNAL SLOT CONTRACT**: the sphere always has exactly four slots, each independently bound to
`{ label: string, value: integer | null, state: "zero" | "nonzero" | "unavailable" }`. A slot's
label and value both come from configuration, never from ad hoc UI code.

**LABEL CONTRACT**: a slot's label must name a real, currently-true count in the visible language
(Serbian for Legal today) — never an abbreviation, never a technical field name.

**VALUE CONTRACT**: a slot's value must be produced by a real, defined aggregation. A slot may not
display a number for which no business definition exists (this is the rule "Novi klijenti" violates
today).

**ZERO/NONZERO PRESENTATION CONTRACT**: unchanged — 0 renders ivory, any positive integer renders
`#8E0B23`. No third color, no severity gradient, no exceptions.

**CLICK/INTERACTION CONTRACT**: a slot is clickable **only if** a real destination screen exists that
shows the full set the count summarizes. Per the adversarial review, no such aggregate destination
exists for any of the four current slots today (Danas's own "+N" links follow the identical rule
already). **Default: the sphere's slots are not links in the current implementation.** This is
re-evaluated per slot, not globally, if a real cross-case aggregate view is ever built.

**MISSING-DATA CONTRACT — the sphere must never fabricate a value.** If a slot's metric is not
computable from product truth:
- The slot enters `state: "unavailable"` and renders as a clean dash or omitted numeral with its
  label dimmed — never a fabricated `0` (a false `0` claims "we checked and there are none," which is
  a stronger and different claim than "we don't track this yet").
- The slot is **not** silently dropped from the layout (that would break the four-slot visual
  identity the owner approved) — it stays in its position, visibly inert, until its data contract is
  met.
- No alternative "proxy" signal is auto-substituted without a product decision (see §4's replacement
  recommendation, which *is* such a decision, made explicitly, not automatically).

---

## 4. Current Legal sphere signals (recommended, not yet owner-locked)

Scored against user value / actionability / computability / semantic precision / frequency of change
/ Home relevance, using only real, evidenced Vindex Legal capabilities:

| Candidate | User value | Actionability | Computability today | Semantic precision | Verdict |
|---|---|---|---|---|---|
| Aktivni predmeti | High | Medium (orientation, not a click-trigger) | **Real** — `predmeti.status` | High | **Recommended, slot 1** |
| Stavke koje traže pažnju (today's Traži pažnju count) | Highest | Highest | **Real** — already computed by `komponujDanas` for the Danas stream itself | High | **Recommended, slot 2** — supersedes the narrower "Aktivni rokovi," since it correctly includes both deadlines and case-action/document triggers already unified in one stream |
| Uskoro (upcoming count) | Medium | Medium | **Real** — same computation, other tier | High | **Recommended, slot 3** |
| Novi klijenti | Medium (if it existed) | Low | **Not computable — "novi" has no defined boundary anywhere in the codebase** | **None — undefined** | **Rejected as written** |
| Novi predmeti (cases opened in a defined recent window) | Medium-high | Low-medium | **Real** — `predmeti.created_at`-equivalent creation event is unambiguous (case creation is a real, singular, already-timestamped event, unlike "client newness") | High, once a window (e.g. 7 days) is chosen | **Recommended, slot 4** — the truthful substitute for "Novi klijenti": same growth/intake intent, but bound to an event that actually has a clear boundary |
| Nepročitani dokumenti | Medium (if it existed) | Medium | **Not computable — no read/unread tracking exists anywhere in `routers/` or `shared/`** | None — no data source | **Rejected, no adequate substitute found** — unlike "novi klijenti," there is no other already-tracked entity with equivalent semantics; this slot has no honest same-effort replacement |

**Recommendation: three of the four night-sprint signals are replaced or kept, and the fourth has no
honest same-effort substitute.**

1. **Aktivni predmeti** — kept.
2. **Stavke koje traže pažnju** — replaces "Aktivni rokovi" (broader, already computed, more
   actionable).
3. **Uskoro** — new, real, already computed.
4. **Novi predmeti (poslednjih N dana)** — replaces "Novi klijenti"; **requires one owner decision**
   (the window length, e.g. 7 vs. 30 days) before it can ship, but the underlying event is real and
   unambiguous, unlike client "newness."

**"Nepročitani dokumenti" has no recommended replacement in this document.** Per the Missing-Data
Contract, it should render as `state: "unavailable"` until the owner decides whether read-tracking is
worth building, or a different fourth signal is chosen. This document does not choose one on the
owner's behalf.

---

## 5. Document-first workflow — placement decision

Full mechanics confirmed by direct code reading (`v2/features/predmeti/uvoz.js`, not just summary):

- **Exact entry point today**: `/app-v2/predmeti/uvoz`, reached via a two-tab switcher ("Ručno" /
  "Iz dokumenta") on the case-creation screen — a co-equal sibling of manual creation, not a hidden
  option.
- **User intent**: "I have a real document (presuda/tužba/ugovor); let Vindex start the case instead
  of me typing it in."
- **Prerequisites**: a file only. No existing predmet required.
- **Creates new, or attaches to existing?** **Create-only.** `blokFinalizovanja()` always calls
  `/api/smart-intake/jobs/{id}/finalize`, which creates a predmet. No code path attaches an uploaded
  document to an *existing* predmet from this screen.
- **Validation behavior**: client requires a file before submit; finalize is blocked
  (`nedostaciUvoza()`) until the lawyer explicitly selects which party is their client — enforced
  because conflict-of-interest checking depends on it, not as a generic required-field rule.
- **Error behavior** (extensive, already correct — not being changed here): distinguishes a clean
  upload failure from a network interruption *during* the write (the latter explicitly says "may have
  been created, check the registry before retrying" rather than claiming failure); distinguishes three
  distinct conflict-of-interest states (scheduled / not scheduled / not triggered because the party
  was unknown) and never states "no conflict" as a possible outcome; handles rate-limiting (429) with
  its own message; gives up *watching* a slow job after 5 minutes without claiming the job itself
  failed.
- **Likely intended frequency**: placed as a structural equal to manual creation (not buried, not a
  secondary link), which is evidence of *intended* frequent use — no usage telemetry exists to prove
  *actual* frequency.
- **Should Home expose it directly?** The workflow is multi-step and asynchronous (upload → minutes of
  server processing → review extracted fields → an explicit conflict-relevant decision → finalize),
  which is a different shape from "Novi predmet"'s instant form. This shape argues for exposing it as
  a **secondary, textual, lower-weight action** next to the primary "Novi predmet" button — not equal
  visual weight (that would violate the one-primary-action rule), and not omitted (that repeats the
  night sprint's factual error).

**Decision**:
- **PRIMARY HOME ACTION**: "Novi predmet" (unchanged).
- **SECONDARY HOME ACTION**: a textual link to `/app-v2/predmeti/uvoz` — visually subordinate, always
  present, e.g. positioned as a second, quieter option beside or beneath the primary button.
- **CONTEXTUAL ACTION**: remains available inside Predmeti's own "Nov predmet" screen (unchanged;
  it is not being removed from where it already lives).
- **GLOBAL ACTION**: not promoted to the shell/nav bar — it is a creation-flavored action, not a
  navigation destination.
- **NOT HOME AS PRIMARY**: correct to keep "Novi predmet" as the single dominant action; "one primary
  Home action" is about visual weight and decision load, not about how many real workflows exist.

---

## 6. Primary action architecture

Tested patterns for exposing the second workflow without clutter:
- A generic "+" menu was considered and **rejected** — it is a SaaS convention with no basis in any
  existing Vindex pattern, and it would hide, not reveal, the distinction between "type it in" and
  "let the system read it," which matters here (the two flows have materially different shapes and
  guarantees, unlike a typical app's undifferentiated "create" menu items).
- A split-button (primary action with a dropdown arrow for the second mode) was considered and
  **rejected** — it hides the second option behind an extra interaction for a workflow this document
  just established is likely used often, which contradicts not artificially restricting real, useful
  actions (§B6's own instruction).
- **Chosen pattern: a plain secondary text link beside the primary button** — visible by default (no
  extra click to discover it), visually subordinate (smaller, not filled red), consistent with how
  Danas already pairs "Novi predmet" / "Svi predmeti" as primary/secondary today. This is the smallest
  change to the existing pattern language that fully answers §5's decision.

---

## 7. Core work-object rule

**CURRENT LEGAL OBJECT**: Predmet — unchanged, not renamed, not refactored.

**POTENTIAL PLATFORM-LEVEL CONCEPT (internal only, not yet justified for implementation)**: a
canonical "work object" identity that Predmet would be *an instance of*, with Legal-specific fields
(`tuzilac`, `tuzeni`, `vrednost_spora`) moved to a Legal-specific extension rather than living on the
shared table.

**VERTICAL PRESENTATION**: Legal continues to see, use, and say "Predmet" exactly as today — this
document does not authorize any visible or behavioral change for the current product.

**DATA BOUNDARY (what would belong to a universal work-object identity, if built)**: identity, status,
ownership/tenancy, timestamps, and the object's relationships to clients/documents/deadlines/billing —
i.e. everything the 146-file `predmet_id` coupling actually depends on today, which is generic
plumbing, not litigation content.

**VERTICAL EXTENSION BOUNDARY (what should eventually live outside universal identity)**: fields whose
meaning is specific to how one vertical characterizes its own work — `tuzilac`/`tuzeni`/`vrednost_spora`
for Legal; their equivalents (if any) for a future vertical would live in that vertical's own
extension, not as more nullable columns on the shared table.

**MIGRATION TRIGGER — the concrete condition, stated so it can be checked objectively later**:

> Abstraction becomes justified at the point a **second vertical's work object needs its own
> required or frequently-populated fields that do not fit the existing nullable-Legal-column
> pattern without becoming meaningless clutter for Legal** — i.e., the moment adding vertical #2 would
> mean adding columns to `predmeti` that are irrelevant to every Legal record. Until that moment,
> continuing to serve Legal exactly as today, with `predmet_id` as the shared identity, is correct and
> should not be pre-emptively refactored. This document explicitly does **not** recommend building
> the abstraction now — only names the trigger so the decision isn't made too late or too early by
> accident.

---

## 8. Navigation constitution

**Candidate rule, tested**: *"A top-level navigation item represents a durable user mental space,
never an individual feature."*

**Attempt to falsify**: does a genuinely important new capability ever deserve an exception? Tested
against a concrete case (a hypothetical firm-wide analytics capability) in the adversarial review —
the rule correctly resolves it *inside* Kancelarija ("how I run the firm") rather than forcing a sixth
nav item, which is evidence the rule is load-bearing, not decorative. **The rule survives.**

- **Maximum practical top-level complexity**: four to five named spaces. This is not an arbitrary
  number — it is the count a first-time user can hold in working memory without a menu to remind them,
  and it is what the current, already-validated Danas/Predmeti/Znanje/Kancelarija(+Usklađenost) set
  already uses.
- **When a new module may become top level**: only when it represents a genuinely new *mental space* —
  a different question the user comes to Vindex to answer, not answerable by "which existing space is
  this closest to."
- **When it must remain contextual**: when it only makes sense attached to an already-open object
  (case, client, document) — it belongs inside that object's own workspace, not in the shell.
- **When it belongs inside an existing space**: when it's a new *view* on an existing mental space
  (firm analytics inside Kancelarija; a new research source type inside Znanje) rather than a new
  question.
- **When product/vertical configuration may alter top level**: Usklađenost is the existing, working
  proof — a vertical-specific space, permission-gated, invisible to accounts without it, added without
  disturbing the other four. This is the sanctioned mechanism for vertical-specific top-level
  additions; no other mechanism is introduced here.

---

## 9. "Znanje" boundary

**Verdict: KEEP WITH STRICT BOUNDARY.**

Legal research and case law were confirmed to share one coherent user intent ("what does the
applicable rule/precedent say about X," answered from two source types under one question). The
legacy "Vindex Intelligence" merge's coherence **could not be independently confirmed** from evidence
gathered this session (its exact legacy scope was not re-verified) — this is recorded as open, not
resolved by assumption, and is not a reason to change anything today.

**Resolved this sprint (remediation Phase 10), by repository evidence**: `static/vindex.js` shows the
legacy `aiws` tab (labeled "Vindex Intelligence") is a shell around **five previously-independent
tabs**, declared verbatim in code as `var _AIWS_MODES = { q:'zakon', a:'analiza', n:'nacrti',
t:'strategija', ob:'oblasti' }` (line ~2166 area) plus a best-effort write path to a learning engine
(`routers/learning.py`, `_pred_prosediUcenju` — case outcomes feeding `case_patterns`/`outcome_log`/
`lessons`). Checked against the Znanje boundary above:

- `q` (zakon — statute/case-law Q&A) and `ob` (oblasti — legal-area browsing): **fit** — both answer
  "what does an external rule/precedent say," Znanje's own definition.
- `a` (analiza — document analysis), `n` (nacrti — draft generation), `t` (strategija — case strategy):
  **do not fit** — these operate on the firm's own case/document, which is a drafting-acceleration or
  case-specific intent, not external research. §9 already places drafting under Predmeti/Šabloni for
  exactly this reason.
- The learning-engine write path is firm-internal accumulated knowledge ("what do *we* already know"),
  which §9 explicitly excludes from Znanje "without a separate, explicit decision" — no such decision
  exists.

**Verdict**: the legacy "Vindex Intelligence" label names a grab-bag of five capabilities, not one
coherent Znanje-shaped intent — a wholesale merge into Znanje as currently labeled would violate this
document's own boundary. This finding does not require any change to the current prototype (no Znanje
screen exists among the four required screens this sprint), and it is not authorization to touch the
legacy app. It is carried forward as a documented constraint on any *future* production Znanje
implementation: only the `q`/`ob` slice merges cleanly; `a`/`n`/`t` belong with Predmet-scoped work,
and the learning-engine write path needs its own explicit placement decision before it can be folded
into anything.

**BELONGS IN ZNANJE**: anything that answers "what does an external rule, statute, or precedent say" —
i.e., research questions whose source of truth is outside the firm's own case data.

**DOES NOT BELONG IN ZNANJE**: document templates (Šabloni — correctly lives under Predmeti today,
since "give me a document to draft from" is a drafting-acceleration intent, not a research intent);
any future firm-internal knowledge base (a firm's own accumulated precedent/notes is "what do *we*
already know," a different intent from "what does the *law* say," and must not be folded in here
without a separate, explicit decision); case-specific facts (those belong in the relevant Predmet).

**Open item carried forward, not resolved here**: confirm "Vindex Intelligence"'s actual legacy scope
before treating its merge into Znanje as settled.

---

## 10. "Kancelarija" boundary

**Verdict: KEEP WITH STRICT BOUNDARY** (previously undocumented anywhere in the repository — this is
the first time the boundary has been written down).

**Candidate principle tested**: *"Kancelarija contains organization-level operational management that
is not owned by an individual Predmet."* Attempted falsification against each real, evidenced
category:
- Finance (firm-level) — passes: firm-wide financial state is not any one case's property.
- Portfolio (case-wide overview) — passes **only as a statistic**; the moment it becomes a way to
  open or edit one specific case's data, it has silently become a second Predmeti registry, which
  must not happen (see boundary below).
- Settings — passes: firm configuration is not case-owned.
- Staff/roles — no shipped capability found to test; principle would apply if built (organization-wide
  role management is not any one case's property).

No category tested contradicts the principle; it is adopted.

**BELONGS IN KANCELARIJA**: the firm's finances in aggregate, its configuration, its case portfolio
*as a statistic* (counts, distributions, trends).

**MUST NEVER BE PUT THERE**: an individual case's, client's, or document's own content or editable
line items. A case's own Naplata entries belong in that case's Dosije; Kancelarija may show the
*aggregate* of all cases' billing, never a control that edits one case's billing.

---

## 11. Serbian terminology rules

No renames performed or recommended for current production UI. Evaluated per the four required
lenses:

| Term | Legal precision | General comprehension | Future-vertical compatibility | Current consistency | Decision |
|---|---|---|---|---|---|
| Danas | N/A (not a legal term) | High | High — name doesn't reference Legal at all | Consistent (V2) | Keep |
| Predmet/Predmeti | High (correct legal-register term) | High | Low as a *word* (a notary wouldn't call their work "predmet"), but the *concept* generalizes — see §16 | Consistent | Keep for Legal; a future vertical would use its own word for the same underlying object, not be forced into "Predmet" |
| Dokument/Dokumenti | Generic, precise enough | High | High | Legacy-app only | No action (legacy app untouched) |
| Spis/Spisi | High (correct legal-register term for a case document) | Medium-high | Medium — "spis" is legal/administrative vocabulary, less universal than "dokument" but not litigation-exclusive | Consistent (V2) | Keep |
| Znanje | Low precision by design (deliberately abstract to cover two merged legacy concepts) | Medium — more abstract than what it replaced | High | New in V2 | Keep, flagged for user testing per the UX Architecture doc (unchanged conclusion) |
| Kancelarija | N/A | High | High — "how I run my office" translates directly to any professional-services vertical | Consistent | Keep |
| Rok/Rokovi | High | High | High — every regulated vertical has deadline-with-consequence concepts | Consistent | Keep |
| Zadatak/Zadaci | N/A | High | High | V2 fixed a legacy spelling inconsistency (Zadatci/Zadaci); V2's spelling retained | Keep |
| Klijent/Klijenti | High | High | High — every vertical has a party-of-record | Consistent | Keep |

**Explicit principle**: Legal terminology is not softened or genericized in anticipation of
hypothetical future users. The architecture's compatibility with future verticals comes from the
platform/vertical boundary (§1) and the navigation mechanism (§8), not from watering down today's
words.

---

## 12. Material system contract

**Superseded rule**: ~~"Bone is every work surface."~~ Falsified in the adversarial review the moment
a genuine counter-example (a relationship/transaction graph) was considered — such visualizations
commonly read better on a dark canvas for the same reason the sphere itself does (edge/glow contrast
range), and no built screen contradicts this, since none of the four prototype screens are that kind
of surface.

**Adopted rule**:
> **Bone is the default material for reading, input, evidence, and structured operational work.
> Black is the system environment and may also host a specialized analytical canvas where the
> information representation objectively benefits from it — never as a stylistic choice, and never as
> the default for a new screen merely because it looks distinctive.**

All four built prototype screens remain fully bone except Danas's header band — this rule does not
change anything already built; it only prevents "every" from becoming a false, brittle statement the
day an analytical canvas is legitimately needed.

---

## 13. Red semantic contract

Current distinct uses, named explicitly (adversarial review §16): brand mark, active-nav indicator,
focus ring, sphere fissures, sphere non-zero count, one destructive link, "Kritično" label text — five
to six jobs on one hue.

**No new color is introduced.** Instead, the contract requires every use of red **except the sphere's
count and the brand mark itself** to carry at least one redundant, non-color signal:

- **BRAND**: color only, by definition (a logo doesn't need a redundant signal for what it is).
- **INTERACTION** (active nav, focus): must also carry position (active nav is always the current
  page, indicated by browser navigation state too) or transience (focus rings are inherently
  temporary and context-bound by convention) — already true today.
- **ATTENTION** ("Kritično" label, sphere non-zero): should carry wording or position redundancy
  where possible. The sphere's non-zero count is the one identified case relying on color alone
  (§ adversarial review §16) — accepted as a scoped, documented exception because the sphere is
  explicitly an ambient/ wordless object by design (§3), not because the general rule is waived.
- **DESTRUCTIVE**: must always carry wording ("Obriši," an unambiguous verb) and position (lowest in
  a demoted/advanced section) in addition to color — already true today ("Obriši predmet").

**Explicit prohibition, restated as a standing rule**: red must never be applied to a new UI element
solely to signal generic "importance." If a future screen wants a "this needs attention" affordance
similar to the sphere's, that is a new, separately-justified decision — it does not inherit red
automatically from this precedent.

---

## 14. Minimalism constitution

**Definition adopted**: *Minimalism means reducing the number of decisions a user must make to
proceed — not reducing the number of visible controls.* A screen with more visible, well-organized
controls but zero hidden menus can be more minimal, by this definition, than a sparse screen that
hides a frequently-needed action.

**Review method for future changes** (applied retroactively to this sprint's own work in the
adversarial review, and to be applied to every future proposed simplification):
1. Count navigation decisions required for the target workflow (not clicks — decisions; a single
   unambiguous click is not a "decision" in the costly sense).
2. Count actual interactions (clicks/taps/keystrokes).
3. Count context switches (does the user leave the object they were working in and have to find
   their way back).
4. Does the workflow depend on a hidden menu the user must already know exists?
5. Is the user's location obvious throughout?
6. If something goes wrong, can the user recover without starting over?

**Failure condition, stated explicitly**: a visual simplification that increases any of (1)–(4) for a
real, evidenced workflow **fails this constitution**, regardless of how much calmer the resulting
screen looks. This is the exact standard the adversarial review applied to find the one confirmed
regression (document-first case creation dropped from Home's evaluated workflow set entirely, §5) —
that finding is what this constitution is written to catch earlier next time.

---

## 15. Multi-role behavior

Evidence: only one space-visibility gate exists today (`uskladjenost`, `v2/app.js:52`); no other space
or Home content varies by role; capability-level gates exist (`shared/permissions.py`,
`require_credits`/`require_pro`) but do not affect navigation or Home layout. Effectively a
single-tier product today, plus one gated vertical module.

**Principles for when more roles exist** (not implemented, no roles invented):
- **HIDDEN**: the correct default for an entire *space* the user's role/plan cannot use at all —
  already the shipped pattern (Usklađenost), extend the same mechanism rather than inventing a second
  one.
- **VISIBLE BUT DISABLED**: never used for whole spaces (this is the exact "promise the product can't
  keep" anti-pattern the codebase already explicitly rejects for spaces). May be acceptable for a
  single *action* inside an otherwise-visible space, if and only if the disabled state explains why in
  plain language at the point of the control — not left to be discovered by clicking.
- **NOT APPLICABLE**: content that a role could theoretically see but that is empty for them (e.g., a
  junior associate with zero assigned cases) should use the existing calm-empty-state pattern, not a
  permission-flavored message — the two situations look identical to the user and should read
  identically.

**Unresolved, honestly**: whether Home's *content* (not just space visibility) should ever vary by
role (e.g., a supervising partner seeing firm-wide urgency vs. an associate seeing only their own) has
no precedent to evaluate — this is a real open product question, not a design failure, since the
scenario has never existed in the product.

---

## 16. Non-goals of this document

- Does not rename any visible production term.
- Does not implement the sphere's configuration mechanism, the secondary Home action, or any other
  decision recorded above.
- Does not create, propose, or schedule a database migration.
- Does not decide the "novi predmeti" time window (owner decision, explicitly deferred).
- Does not decide whether to build read/unread document tracking (owner decision, explicitly
  deferred).
- Does not resolve "Vindex Intelligence"'s exact legacy scope (evidence-gathering task, not done in
  this pass).
- Does not authorize touching the frozen prototype's HTML/CSS/sphere asset/navigation/terminology.
- Does not authorize production integration, deployment, or further prototype iteration — that is the
  owner's decision, taken after reading this document.
