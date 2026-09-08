# VINDEX APPLICATION — OWNER REVIEW

Purpose: help you judge the frozen prototype as it actually is. This document does not argue for the
design — see `ARCHITECTURE-ADVERSARIAL-REVIEW.md` for the attempt to disprove it. Screenshots below
are persisted, unmodified captures of the exact frozen build in `prototype/vindex-next-app/`.

---

## Danas (Home)

**Screenshots**: `review/danas-1440.png`, `review/danas-1024.png`, `review/danas-390.png`,
`review/mobile-nav-open-390.png`

- **Page purpose**: answer "what needs my attention today, across every open case" in one glance.
- **Primary user question answered**: *Šta zahteva moju pažnju?*
- **Primary action**: "Novi predmet" (start a new case).
- **Secondary actions**: "Svi predmeti" (go to the registry); switch to Kalendar / Brifing /
  Obaveštenja via the sub-nav.
- **Visible information zones**: (1) black header band — day identity, one-sentence summary, primary
  action, the sphere; (2) paper work surface — Traži pažnju (urgent), Uskoro (upcoming), a side rail
  (recently completed, recently opened, one link to the AI briefing).
- **Deliberately excluded information** (with reason, from the Home Architecture document): firm
  finance/KPIs, a separate firm-wide task list, legal-research shortcuts, portfolio statistics,
  account plan/usage meters, a generic activity feed, Usklađenost status. Each was evaluated against
  a real need and rejected on its own terms, not omitted by oversight.
- **Known architectural weaknesses** (see adversarial review for full detail):
  - The sphere shows two real, cheaply-computable metrics (Aktivni predmeti, Aktivni rokovi) next to
    two metrics with **no current business definition or data source** (Novi klijenti, Nepročitani
    dokumenti) — P0-1.
  - A real, shipped workflow (creating a case *from* an uploaded document, not the other way around)
    is completely absent from this screen and from the reasoning that shaped it — P1-1.
  - The "Nalog" account link is undersized for touch (32×20px against a 44px guideline) — P1-5.

---

## Predmet (case workspace)

**Screenshots**: `review/predmet-1440.png`, `review/predmet-1024.png`

- **Page purpose**: everything about one case, on one continuous surface.
- **Primary user question answered**: *Šta se dešava u ovom predmetu i šta treba da uradim?*
- **Primary action**: open a spis, add a spis, or resolve a rok — whichever the user came for; the
  screen does not force a single primary action the way Danas does, by design (a case workspace is
  browsed, not funneled).
- **Secondary actions**: per-section "Dodaj spis" / "Dodaj rok" / "Nova stavka."
- **Visible information zones**: identity header (case name, status, client, case number, area of
  law) → Spisi → Rokovi i zadaci → Naplata → Saradnja → Napredno (profitability, comparison,
  deletion — visually demoted, not hidden).
- **Deliberately excluded information**: no case-health score, no AI-generated summary blended with
  case facts, no fabricated percentage of anything — matching the existing, already-shipped Dosije's
  own stated constraints.
- **Known architectural weaknesses**:
  - Never shown with a large number of spisi/rokovi (only 3 of each) — untested at real-world volume
    — P2-2.
  - Sits on a `predmet_id`-scoped, litigation-shaped schema (`tuzilac`/`tuzeni`/`vrednost_spora`)
    that will need a decision before a second professional vertical is built on the same object —
    P1-2.

---

## Dokument (evidence/reading surface)

**Screenshot**: `review/dokument-1440.png`

- **Page purpose**: read one document at full attention, nothing else competing for it.
- **Primary user question answered**: *Šta ovaj dokument stvarno kaže?*
- **Primary action**: read; "back to case" is the only navigation offered.
- **Secondary actions**: none by design — this is intentionally the least action-dense screen in the
  product.
- **Visible information zones**: document identity (type, date, source, availability) → full body
  text in a single reading column.
- **Deliberately excluded information**: no AI summary in place of the real text, no inline
  annotation tools, no sidebar — matching V2's existing Čitač contract exactly.
- **Known architectural weaknesses**: none specific to this screen beyond the general accessibility
  findings (§20 of the adversarial review, which apply site-wide, not to this screen specifically).

---

## Registar (Predmeti list — data-dense surface)

**Screenshots**: `review/registar-1440.png`, `review/registar-390.png`

- **Page purpose**: find a case by scanning, not by remembering where it lives.
- **Primary user question answered**: *Koji je ovo predmet i gde je?*
- **Primary action**: "Novi predmet."
- **Secondary actions**: search-as-you-type, "Filteri."
- **Visible information zones**: one continuous row list — name/area, court, client, last activity,
  status — no cards, no grid, matching V2's own "red je red, ne kartica" rule.
- **Deliberately excluded information**: no bulk actions, no inline editing, no per-row menu — kept
  as a pure finding tool, not a management console.
- **Known architectural weaknesses**:
  - Shown with 7 curated rows; pagination (`PO_STRANI = 50` in real V2) was never actually exercised
    in this prototype, nor was a 0-result search state — P2-2.
  - Mobile (390px) drops the court column entirely rather than reflowing it — acceptable, but not
    stress-tested against a name long enough to wrap three lines.

---

## Cross-cutting, all screens

- **Shell**: identical on all four screens — wordmark (with the canonical red "x"), four nav spaces,
  global search with a visible Ctrl/Cmd+K accelerator, account link. Confirmed functionally
  interactive (mobile hamburger opens/closes; verified, not just styled) — `mobile-nav-open-390.png`.
- **Static QA**: 0 horizontal overflow at 1440/1024/390 on every screen; no broken links or anchors;
  no missing accessible names; no duplicate IDs — full detail in the adversarial review, §21.
- **What this document intentionally does not do**: argue that the prototype is finished, or that its
  gaps are acceptable. That judgment is the owner's, using the weaknesses listed above and the fuller
  evidence in `ARCHITECTURE-ADVERSARIAL-REVIEW.md`.
