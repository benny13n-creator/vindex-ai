# VINDEX APPLICATION — HOME ARCHITECTURE

Purpose: prevent Danas (Home) from becoming a dumping ground. Every candidate function is recorded
here with the reason it was retained, demoted to contextual, or rejected outright. This builds on
the existing, already-shipped Danas screen (`v2/features/danas/view.js`) rather than redesigning it
from a blank page — see `VINDEX-APPLICATION-UX-ARCHITECTURE-v1.md` §0 for why.

Home must answer, within seconds: *Šta zahteva moju pažnju? Gde sam stao? Šta se promenilo? Šta
mogu odmah da uradim?*

---

| Function | Source / evidence | User need | Frequency | Urgency | Placement | Visible mode | Reason |
|---|---|---|---|---|---|---|---|
| Traži pažnju (priority stream: overdue/critical items) | `domain/danas.js::komponujDanas`, tier1 | "What can't wait" | Every login | High | **Main column, top** | Always visible when non-empty | Direct answer to "šta zahteva moju pažnju" — the single reason Danas exists |
| Uskoro (upcoming stream) | Same, tier2 | "What's coming" | Every login | Medium | **Main column, below Traži pažnju** | Always visible when non-empty | Answers "šta mi sledi," second-highest urgency |
| Mirna rečenica kad je dan prazan | `view.js` empty-state branch | Confirms nothing was missed, not silence | Whenever both streams are empty | Low (by design) | **Main column** | Replaces the two streams | Already-proven pattern: an empty day must say so calmly, not show three separate "nothing here" messages |
| Nedavno završeno | `view.js::iscrtajZavrseno` | "Gde sam stao" (what did I just finish) | Every login | Low | **Side rail, always** | Independent of main-column content | Explicitly a *permanent* rail item in V2 already, not a fallback — context and attention are treated as independent information |
| Nedavno otvoreno (recent cases) | `view.js::nedavniPredmeti` | "Gde sam stao" (what was I just working on) | Every login | Low | **Side rail, always** | Same as above | Same reasoning; also the fastest path back into interrupted work |
| Brifing (AI end-of/start-of-day narrative) | `danas/brifing.js` | "Šta se promenilo," in narrative form | On demand | Low | **Side rail: one link only** ("Jutarnji brifing →") | Link always visible; content never inlined | Kept deliberately separate from deterministic fact per V2's own rule — AI narrative must never blend with confirmed data on the same line |
| Kalendar (week view) | `danas/kalendar.js` | "Šta me čeka" this week, not just today | Weekly-ish | Medium | **One switch-item in the Danas/Kalendar/Brifing/Obaveštenja toggle**, not inlined on Home | A related but distinct question from "today" | Already its own sub-screen; inlining a calendar grid into Home would violate §10's "not a feature directory" |
| Obaveštenja (notifications) | `danas/obavestenja.js` | System messages | As they occur | Varies | **Same toggle as Kalendar/Brifing** | Not inlined | Same reasoning — a notification feed is a distinct read, not a Home widget |
| **Vindex sphere: four signals** (Aktivni predmeti / Stavke koje traže pažnju / Uskoro / Novi predmeti) | New for this sprint; signal set corrected per `APPLICATION-ARCHITECTURE-CONTRACT-v1.md` §3–4 — see that document for the full data-contract resolution (Model B: canonical four-signal object, configurable definitions; the original "Aktivni rokovi" narrowed the same tier1 count Traži pažnju already shows, "Novi klijenti" had no defined time boundary anywhere in the codebase, and "Nepročitani dokumenti" has no read/unread tracking at all — all three superseded) | An instant, wordless read of "how loud is today" before reading a single line of text | Every login | Ambient | **Black header band, above the paper work surface** | Always visible, values are representative/dummy in this prototype | Directly requested by the brief (§8) as the functional brand object; placed where it cannot compete with or duplicate Traži pažnju/Uskoro — it summarizes, it does not replace, the detailed streams below it |
| Global "Novi predmet" | `predmeti/nov.js`, already a real route | Fastest path to the single highest-value creation action | Frequent | High when needed | **Primary button, Danas header band** | Always visible | A global creation action belongs at the point of highest traffic (Home), consistent with §10's candidate list; only one creation action is promoted to a button — not a menu of every possible "new X" |
| Global search / Pretraga | `shell.js`, already global (header + Ctrl/Cmd+K) | Find anything without navigating tabs | Frequent | High when needed | **Global shell, not duplicated on Home** | Always visible (it's in the header on every screen) | Already global — repeating it as a second Home-specific search box would be exactly the "same action available from multiple confusing locations" failure §4 warns against |
| Document-first predmet creation (`v2/features/predmeti/uvoz.js`, "Iz dokumenta") | **Correction**: an earlier version of this document stated no such capability exists in V2 and rejected it outright. That was factually wrong — `uvoz.js` already ships DOCUMENT → CLASSIFICATION → PREDMET as a real, structurally co-equal sibling of manual creation (its own header comment: *"PREDMET NASTAJE IZ DOKUMENTA, ALI NE BEZ ADVOKATA"*). See `APPLICATION-ARCHITECTURE-CONTRACT-v1.md` §5 for the full corrected placement decision. | "I have a document; let Vindex start the case instead of me typing it in" | Likely frequent — placed as a structural equal to manual creation in the real product, though no usage telemetry exists to confirm actual frequency | High when needed | **Secondary action, Danas header band, beside "Novi predmet"** | Always visible, visually subordinate | A real, shipped workflow whose multi-step/asynchronous shape argues for secondary rather than primary weight — visible by default, not hidden behind a menu, not equal to the primary action. Retained. |
| Zadaci (tasks) list, firm-wide | Exists only inside Dosije · Rokovi per case | "What am I supposed to do" | Frequent | Medium | **Not surfaced separately — already folded into Traži pažnju/Uskoro as work-items** | Folded in | The capability matrix shows no cross-case "my tasks" endpoint; the closest real thing is already inside the tier1/tier2 stream. Adding a second, separate "Zadaci" list on Home would duplicate that stream. Rejected as a separate block. |
| Finansije / firm KPIs (revenue, profitability) | `kancelarija/*`, `dosije/profitabilnost.js` | "How is the firm doing" | Weekly/monthly | Low daily urgency | **Not on Home — lives in Kancelarija and per-case Dosije** | Contextual only | Firm finance is a distinct, lower-frequency question from "what needs my attention today"; inlining it would be the "twelve dashboard sections" failure §10 explicitly forbids. Rejected. |
| Znanje / legal-research shortcuts | `znanje/*` | Quick jump into research | Frequent, but self-directed (not attention-driven) | Low urgency as a Home item | **Not on Home — reached via global nav** | Not shown | Research is initiated by the user's own need, not by something Vindex needs to flag; it does not belong in an attention-triage screen. Rejected as a Home block, kept as a nav item. |
| Portfolio kancelarije | Legacy hidden tab; V2: folded into Kancelarija | Firm-wide case overview | Low | Low | **Not on Home** | Contextual only (inside Kancelarija) | Low frequency, low urgency by the matrix's own classification; belongs to NAPREDNO/POVREMENO, not Home. Rejected. |
| Digitalna imovina / Usklađenost status | `uskladjenost/*`, BLOCKED (G1–G5) | N/A | N/A | N/A | **Not on Home** | Not shown to anyone without the permission; and even then, not on Home | The module cannot yet cite sources for its own conclusions (a backend gap, not a UI one) — surfacing it on Home before it is trustworthy would misrepresent product maturity. Rejected outright for this sprint. |
| Generic "activity feed" / audit log | Not a distinct existing capability — closest is per-case hronologija | Reassurance that changes are tracked | Rare, defensive read | Low | **Not on Home** | Not shown | No evidence this is a real, named user need distinct from Nedavno završeno/otvoreno, which already cover it. Adding it would be inventing a capability. Rejected. |
| Version/system status badges, plan/usage meter | H9 in capability matrix (plan/usage), IMPLEMENTED but low frequency | Awareness of account limits | Rare | Low | **Not on Home — belongs in account/Kancelarija area** | Not shown | Low frequency + low urgency; showing it permanently on Home would be visual noise for a need most sessions never have. Rejected as a Home element. |

---

## Final Home shape (result of the table above, corrected)

**Two zones only**, matching the black-scene/paper-scene split already built:

1. **Black header band**: wordmark context (inherited from shell), the sphere with its four
   ambient signals (§3–4 of the Architecture Contract), one summary sentence (existing `sazetak`
   mechanism), primary "Novi predmet" action, secondary document-first ("Iz dokumenta") action.
2. **Paper work surface, two columns**: main column (Traži pažnju → Uskoro, or the calm empty-state
   sentence), side rail (Nedavno završeno, Nedavno otvoreno, one link to Brifing).

Nothing else. Nine candidate functions were evaluated; **five were rejected outright**, **three were
folded into existing mechanisms instead of becoming new blocks**, and **two are genuinely new to
Home** — the sphere, and the document-first action restored by the correction above (it already
existed in the product; what's new is only its Home placement). Everything else on the final Home
surface was already there before this sprint began.
