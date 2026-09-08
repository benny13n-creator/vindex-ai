# VINDEX APPLICATION — VISUAL FOUNDATION v1

Derived from two real sources, not invented: the live **Vindex.rs** website tokens
(`static/site-v4.css`) and the existing **V2 application** tokens (`v2/styles/tokens.css`,
`type.css`). Where they already agreed, this document keeps them. Where they disagreed, the
disagreement is named and resolved explicitly below — this is not a competing design system.

---

## 1. Colors

| Token | Value | Source | Role |
|---|---|---|---|
| `--vx-crna` | `#12110F` | V2 tokens (unchanged) | System/shell scene background |
| `--vx-crna-2` | `#1C1A17` | V2 tokens (unchanged) | Second surface within a black scene |
| `--vx-papir` | `#F6F3ED` | V2 tokens (unchanged) | Active work surface |
| `--vx-papir-2` | `#EFEBE3` | V2 tokens (unchanged) | Second surface within a paper scene |
| `--vx-tx-1 / -2 / -3` (papir) | `#191814` / `#3D3A34` / `#605B52` | V2 tokens (unchanged) | Text on paper, 15.4:1 / 9.6:1 / 5.6:1 |
| `--vx-tx-1 / -2 / -3` (crna) | `#F2EEE7` / `#C6C0B6` / `#948D82` | V2 tokens (unchanged) | Text on black, 15.0:1 / 9.7:1 / 4.9:1 |
| `--vx-linija` / `--vx-linija-jaca` / `--vx-linija-crna` | as V2 | V2 tokens (unchanged) | The one hairline separator system — no second border style introduced |
| **`--vx-crveno`** | **`#8E0B23`** | **Vindex.rs (`--vw-accent`)** | **Canonical brand red — resolved discrepancy, see below** |

### The one real discrepancy, resolved explicitly

V2's existing token file defines its own accent as `--v2-brend: #6E1B22`, a deliberately muted
oxblood chosen to hit 9.1:1 contrast for a *focus ring only*, with an explicit constitutional rule
attached in the token file itself: *"Nikad kao boja teksta sadržaja, nikad kao status"* (never as
content-text color, never as status) — this rule has an internal name in the project's own history,
**BA-1** ("brand ≠ status"), won after a prior incident where brand and status color got confused.

The website's canonical red is `#8E0B23` — brighter, more saturated, and it is what the brief
explicitly names as canonical for the application too (§5: "VINDEX RED = #8E0B23").

**Resolution used in this prototype:** adopt `#8E0B23` as the single canonical red going forward,
per the brief's explicit instruction to derive from the website. `#6E1B22` is superseded, not kept
as a second red. BA-1's *rule* (red is never a general status color) is kept in full — see the red
usage budget below — but the *value* changes to match the website. This is named here so it reads
as a deliberate decision the next engineer can find, not a silent drift between two reds living in
two parts of the same product.

### Red usage budget (BA-1, preserved)

Permitted:
- The brand mark (V incision, the "x" in Vindex) — decorative-brand context only.
- The sphere's fissures (ambient brand object, not work-surface content).
- Focus rings.
- The active-space indicator in the shell nav.
- **The sphere's four counts, specifically, when value > 0** — an explicit, narrow, owner-directed
  exception scoped to those four numbers only (brief §8). This is flagged, not hidden: elsewhere in
  the application (tables, badges, lists, the existing `--vx-st-*` semantic tokens for
  aktivno/mirovanje/završeno/greška) red continues to mean only what it already means, and a count
  or status elsewhere in the product does **not** inherit "red = attention" from the sphere. If a
  future screen wants a similar "count going red when non-zero" affordance, that is a new decision
  to make explicitly, not an automatic extension of this one.

Never permitted: red as page body text color, red as a decorative icon color, red repeated on every
active element, red used for more than one semantic meaning on the same screen.

---

## 2. Typography

Already fully aligned between V2 and the website — **no change needed, no new family introduced**:

| Role | Family | Used for |
|---|---|---|
| Serif | Source Serif 4, weight 600 | Space names in the shell (`Danas`, `Predmeti`…), section titles (`v2-naslov`), page-level identity statements |
| Sans | Source Sans 3 | All operational UI: body text, controls, labels, navigation |
| Mono | JetBrains Mono, tabular numerals | Dates, timestamps, sphere's four numeric values, metadata, anything compared vertically or copied verbatim |

Existing type scale kept as-is: eyebrow/field labels 11px uppercase 0.06–0.08em tracking (never
smaller — the codebase's own comment notes this is exactly where a prior WCAG gate failed), body
15px, meta 13px, section titles `clamp(26px, 3.4vw, 34px)`.

---

## 3. Spacing, surfaces, radius

- Radius: **0**, everywhere. Already enforced in V2 (`--v2-radijus: 0`); not revisited.
- No shadows, no gradients used decoratively. The sphere's own illumination is part of the reused
  image asset, not a CSS glow applied to a UI chrome element.
- Hairlines only, two weights (`--vx-linija`, `--vx-linija-jaca`), no second border style.
- Density is task-adaptive, not uniform (brief §17), and this was already true in V2 before this
  sprint: `--v2-mera-registar` (1440px, operational registers), `--v2-mera-predmet` (1280px, case
  work), `--v2-mera-danas` (960px, scannable obligation rows), `--v2-mera-citanje` (72ch, long-form
  reading) are four *different* deliberately-chosen measures, not one universal content width. Kept
  unchanged; the prototype's four work surfaces each use the measure that already matches their
  task.

---

## 4. Work-surface behavior (prototyped, not assumed — see screenshots)

| Screen | Dominant scene | What recedes |
|---|---|---|
| Danas (Home) | Black header band (system) → paper work surface below | Sphere is confined to the black band only |
| Predmet (Dosije) | Paper, continuous | No sphere, no black scene except the persistent shell header |
| Dokument (Čitač) | Paper, single reading column | Same — reading surface dominates completely |
| Registar (Predmeti list) | Paper, dense row list | Same |

This confirms the brief's §15 transition model held up under an actual build rather than remaining
a diagram: opening any real object (a case, a document, a registry) hands the screen to the paper
surface; only Home keeps a visible black band, and only Home shows the sphere.

---

## 5. The sphere — implementation

- **Asset**: a provided reference render (black/graphite faceted sphere, red fissures, no red ring,
  no red circumference) is reused as a real image (`assets/sphere.png`), the same way the website's
  own logo artwork is reused rather than redrawn from a text description. It is cropped to its
  content bounds and placed on the identical `--vx-crna` scene so no visible seam remains.
- **The four values are live DOM text, not baked into the image** — an absolutely-positioned overlay
  sits on the sphere's own dark central facet and renders four labeled numbers in a 2×2 arrangement:
  `AKTIVNI PREDMETI`, `AKTIVNI ROKOVI`, `NOVI KLIJENTI`, `NEPROČITANI DOKUMENTI`. This lets the
  prototype demonstrate both a "quiet" state (all zero, ivory) and a "busy" state (several red) from
  the same asset, per brief §8.
- **Color rule**: value `0` → ivory/white (`--vx-tx-1-crna`); value `> 0` → `--vx-crveno`. No third
  color, no severity gradient.
- **No card, no separators, no quadrant borders** around the four values — confirmed visually in the
  screenshots (§7 below); they sit directly on the sphere's own dark facet.
- **Placement rule**: Danas only. Confirmed absent from Predmet, Dokument, and Registar by
  screenshot, not by assertion.
- **Responsive**: sphere shrinks and the four-value overlay reduces to a tighter 2×2 grid at 1024;
  at 390 the sphere is reduced further and repositioned above the primary action rather than
  dominating the viewport (see §7 mobile screenshot) — its identity (facets + fissures + the four
  values) is preserved, its footprint is not.

---

## 6. Components exercised in this prototype

Page title (serif), section title, eyebrow/field label, primary/secondary/ghost button, text input,
search input (shell), navigation item with active state, table/registry row, status text (semantic
tokens, never red), empty state (Danas "quiet day" sentence), loading skeleton (already a V2
pattern, reused conceptually), destructive-adjacent state (case deletion control referenced but not
re-built). Not every component in a generic design-system checklist was built — only what these five
screens actually needed, per brief §19's own instruction not to build components merely because a
checklist usually has them.

---

## 7. Visual review — screenshots

See the final report for the full path list. Screens rendered at 1440 / 1024 / 390 for Danas and
Predmet; 1440 for Dokument and Registar; 390 for one representative work surface — covering every
mandatory combination in brief §28.

Self-assessment against §28's explicit failure conditions:
- Generic-dashboard test: **not failed** — no card grid exists anywhere in the prototype; Danas's
  own two-column paper layout and the registry's row list are the only repeating structures, and
  both were already the shipped V2 pattern before this sprint, not a new invention.
- AI-generated-generic test: no bento grid, no glassmorphism, no gradient buttons, no rounded pills,
  no emoji, no sparkle iconography anywhere in the four screens.
- Sphere-gimmick test: the sphere appears on exactly one screen (Danas) and is absent everywhere
  work actually happens — it does not follow the user, per brief §9's explicit rule, verified by
  building the other three screens without it rather than by assertion.
