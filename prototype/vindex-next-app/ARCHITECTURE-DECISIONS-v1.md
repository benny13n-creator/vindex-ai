# VINDEX APPLICATION — ARCHITECTURE DECISIONS v1

Companion register to `APPLICATION-ARCHITECTURE-CONTRACT-v1.md`. Each entry: the decision, its
evidence, the alternatives actually considered, why this one was chosen, what would invalidate it, and
what it costs to implement. No implementation performed.

---

### D1 — Sphere: configurable four-signal object (Model B), not a fixed four-metric object (Model A)

- **Evidence**: `routers/klijenti.py` has no "new since X" business rule for clients; no read/unread
  tracking exists anywhere in `routers/` or `shared/` for documents; conversely `predmeti.status` and
  Danas's own `komponujDanas` tier computation are real and already cheap.
- **Alternatives considered**: Model A (metrics are part of the sphere's fixed identity).
- **Why chosen**: Model A fails immediately against the evidence — two of the four current metrics
  cannot be honestly populated today. Locking the visual object to specific metric labels means the
  object itself would need to change the day a metric's definition changes, which recreates the exact
  coupling problem being solved.
- **What would invalidate it**: if Vindex commits to a single-vertical, single-configuration future
  with no intention of ever changing what the four signals mean — not indicated by anything in the
  product's current direction ("Operativna platforma za odgovorne kancelarije" implies multi-context
  intent).
- **Implementation consequence**: none yet. When built, the sphere component takes four
  `{label, value, state}` slots from configuration rather than hardcoding four labels.

---

### D2 — Current Legal sphere signals: Aktivni predmeti / Stavke koje traže pažnju / Uskoro / Novi predmeti (windowed)

- **Evidence**: full scoring table in the Architecture Contract §4.
- **Alternatives considered**: keeping all four night-sprint labels as-is; keeping only 2-3 signals and
  leaving one or two slots permanently unavailable; inventing a new metric unrelated to the night
  sprint's intent.
- **Why chosen**: "Stavke koje traže pažnju" and "Uskoro" are literally already computed for Danas's
  own main stream — zero new aggregation cost, highest actionability. "Novi predmeti" preserves the
  night sprint's original growth/intake *intent* while binding it to an event (case creation) that
  actually has an unambiguous timestamp, unlike "new client."
- **What would invalidate it**: if the owner decides "new client" growth is a more important signal
  than "new case" growth even without a defined boundary — that's a legitimate product call this
  document doesn't have the authority to make; it would require the owner to also supply the missing
  definition.
- **Implementation consequence**: requires one owner decision (the "recent" window length for "Novi
  predmeti," e.g. 7 vs. 30 days) before this signal can ship; the other three require no new decision,
  only implementation.

---

### D3 — "Nepročitani dokumenti": no replacement recommended, marked unavailable pending a build decision

- **Evidence**: no read/unread tracking mechanism found anywhere in the backend.
- **Alternatives considered**: substituting a different, already-tracked document-related count (e.g.
  "spisi added this week"); silently dropping the fourth slot.
- **Why chosen (i.e., why neither alternative was chosen)**: a substitute count would answer a
  different question than "unread" and would misrepresent itself under the original label; dropping
  the slot contradicts the owner-approved four-slot visual identity. The honest answer is that this
  specific signal requires new tracking infrastructure, which is a build decision, not a naming
  decision — substituting or omitting would both hide that fact.
- **What would invalidate it**: a decision to build document read/view tracking, at which point the
  slot becomes fillable without changing this document's reasoning.
- **Implementation consequence**: none until the owner decides whether read-tracking is worth
  building; until then, the slot renders per the Missing-Data Contract (Architecture Contract §3).

---

### D4 — Home purpose: single governing sentence (Architecture Contract §2), not "everything important"

- **Evidence**: the night sprint's Home Architecture document already rejected 5 of 9 evaluated
  candidates using an implicit version of this standard; this decision makes the standard explicit and
  citable.
- **Alternatives considered**: leaving Home's purpose as an implicit pattern (the night sprint's
  original state); defining it as a literal dashboard/overview (rejected by both sprints already).
- **Why chosen**: a durable, one-sentence, testable definition lets future proposed Home additions be
  checked against a rule instead of re-litigated from scratch each time (which is exactly the failure
  mode "Home becomes a dumping ground" describes).
- **What would invalidate it**: evidence that users need something Home currently and deliberately
  excludes (e.g., firm KPIs) badly enough that the sentence needs to grow — no such evidence exists
  today.
- **Implementation consequence**: none directly; governs future Home-change reviews.

---

### D5 — Document-first case creation: secondary Home action (textual link beside "Novi predmet")

- **Evidence**: `v2/features/predmeti/uvoz.js` full mechanics (Architecture Contract §5) — real,
  shipped, structurally co-equal to manual creation, multi-step/asynchronous by nature.
- **Alternatives considered**: promoting it to equal-weight primary status (two big buttons); a
  generic "+" create menu; a split-button pattern; leaving it excluded from Home entirely (the night
  sprint's original, evidence-contradicted choice).
- **Why chosen**: equal-weight buttons violate the one-primary-action rule (Architecture Contract §2);
  a "+" menu has no precedent anywhere in Vindex and would obscure a meaningful distinction between
  the two creation modes; a split-button hides a likely-frequent action behind an extra interaction.
  A plain secondary text link matches the pattern Danas already uses (primary + one secondary action)
  and adds zero new interaction patterns to the product.
- **What would invalidate it**: real usage data showing document-first creation is used far more often
  than manual creation, which would argue for swapping which one is visually primary — no such data
  exists yet (the workflow has never been exposed on Home to measure).
- **Implementation consequence**: a Home Architecture document correction (already specified in the
  Architecture Contract) plus, eventually, one new link in the Home markup — not performed in this
  phase.

---

### D6 — Predmet abstraction: not performed now; explicit future trigger defined

- **Evidence**: `migrations/015_predmeti_extra_fields.sql` (litigation-specific nullable columns on
  the shared table); 146-file `predmet_id` coupling across `routers/`.
- **Alternatives considered**: abstracting now (introducing a canonical work-object identity ahead of
  need); declaring the current schema permanently fine (ignoring the debt).
- **Why chosen**: abstracting now is premature engineering against a vertical that doesn't exist yet
  and whose actual field needs are unknown — this document explicitly avoids that. Declaring it
  permanently fine ignores real, cited evidence of a pattern (nullable vertical-specific columns) that
  won't stay clean. A named, checkable trigger threads this needle.
- **What would invalidate it**: none — the trigger condition itself (Architecture Contract §7) is the
  invalidation test; it fires the decision to abstract, it doesn't get invalidated itself.
- **Implementation consequence**: none now. When the trigger condition is met, the consequence is a
  real schema/migration decision, explicitly out of scope for any prototype-level document to make
  unilaterally.

---

### D7 — Znanje: kept, with a strict, written boundary; merge coherence flagged open

- **Evidence**: legal research + case law share a confirmed single intent; "Vindex Intelligence"'s
  legacy scope not independently re-verified this session.
- **Alternatives considered**: splitting Znanje back into two spaces (rejected — would undo a
  correctly-evidenced merge of two legacy concepts users experienced as one need); renaming it now
  (explicitly out of scope, §B8/§B19 forbid production renames in this phase).
- **Why chosen**: the boundary (Architecture Contract §9) is enough to prevent drift without needing
  to resolve the one open evidentiary question immediately; the open question is recorded rather than
  either ignored or used to block the whole space.
- **What would invalidate it**: confirming "Vindex Intelligence" was actually a broader, general
  AI-assistant surface rather than research-specific — would require re-evaluating whether it belongs
  under Znanje at all.
- **Implementation consequence**: none now; a follow-up evidence-gathering read of the legacy scope is
  recommended, not performed here.

---

### D8 — Kancelarija: kept, with a strict, newly-written boundary

- **Evidence**: finance/portfolio/settings all evidenced as real capabilities; no boundary previously
  written down anywhere in the repository.
- **Alternatives considered**: leaving the boundary implicit (the state this review found and flagged
  as debt); splitting Kancelarija into multiple spaces (rejected — would violate the navigation
  constitution's "durable mental space" ceiling without evidence any sub-area is used often enough to
  deserve its own top-level slot).
- **Why chosen**: writing the boundary down costs nothing and directly prevents the one concrete risk
  identified (Portfolio silently duplicating the Predmeti registry).
- **What would invalidate it**: evidence that "how I run my firm" is not actually one coherent mental
  space for real users — no such evidence found.
- **Implementation consequence**: none; documentation only.

---

### D9 — Navigation: horizontal, no sidebar, confirmed durable; constitution formalized

- **Evidence**: adversarial review §8 — the "durable mental space, never a feature" rule survived a
  concrete falsification attempt (a hypothetical firm analytics capability correctly resolves inside
  Kancelarija, not as a sixth nav item).
- **Alternatives considered**: sidebar (rejected in the night sprint on comprehension grounds, not
  re-litigated here since no new evidence emerged to challenge that); icon rail (same).
- **Why chosen**: the model survived direct adversarial attack in this phase, which the night sprint's
  original reasoning had not yet been tested against.
- **What would invalidate it**: a real future module that genuinely cannot be classified as either "a
  new mental space" or "belongs inside an existing one" — not encountered yet.
- **Implementation consequence**: none; no navigation change.

---

### D10 — Material system: "bone default, black may also host analytical canvases," replacing "bone = every surface"

- **Evidence**: no built screen contradicts it (all four prototype work surfaces are fully bone); the
  sphere itself already proves a black-hosted, non-reading, non-input, benefit-driven use case exists
  in the product's own visual language.
- **Alternatives considered**: keeping "every work surface is bone" as written (rejected — already
  false the moment a graph/relationship visualization is considered, per the adversarial review); a
  fully open rule with no default (rejected — removes the discipline that kept all four built screens
  consistent).
- **Why chosen**: names the exception the sphere already represents, without weakening the strong
  default that produced four consistent, uncluttered work surfaces.
- **What would invalidate it**: evidence that a "specialized analytical canvas" was used decoratively
  rather than because the representation objectively benefited — a future design-review question, not
  a current one (no such surface has been built).
- **Implementation consequence**: none; no visual change to anything built.

---

### D11 — Red semantics: no new color; redundant-signal requirement formalized

- **Evidence**: adversarial review §16 — five to six distinct current uses of one hue; four of them
  already carry a redundant non-color signal (position, wording, transience); the sphere's non-zero
  count is the one use relying on color alone.
- **Alternatives considered**: adding a second accent color for one of the meanings (rejected —
  explicitly forbidden by the brief and not evidenced as necessary once redundant signaling is
  accounted for); removing red from one of its current uses to reduce collision risk (rejected — no
  specific use was shown to actually be colliding with another in practice).
- **Why chosen**: the redundancy audit shows the palette is not yet "everything important" in
  practice; formalizing the requirement (every future red use must carry a second signal, except the
  sphere's documented, scoped exception) prevents it from becoming that without adding visual
  complexity now.
- **What would invalidate it**: a future screen where two of red's meanings appear adjacent to each
  other with no redundant signal distinguishing them — would need to be caught in that screen's own
  design review.
- **Implementation consequence**: none; no current element changes color or meaning.

---

### D12 — Minimalism: redefined as decision-reduction, with a six-point review method

- **Evidence**: the one confirmed regression this review found (document-first creation dropped from
  Home's evaluated candidate set) was a decision-cost failure, not a click-count failure — the
  workflow wasn't slower where it existed, it was simply invisible from a screen that's supposed to
  represent all real starting points.
- **Alternatives considered**: a pure click-count minimization standard (explicitly rejected by the
  brief itself, §B14); no formal standard at all (the state both sprints operated under until now).
- **Why chosen**: gives future design reviews (including future adversarial passes) a repeatable method
  instead of re-deriving "is this too minimal" from first principles each time.
- **What would invalidate it**: none identified — this is a review method, not a factual claim.
- **Implementation consequence**: none; process/documentation only.
