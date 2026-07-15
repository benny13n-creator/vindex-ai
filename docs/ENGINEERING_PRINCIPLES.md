# Vindex AI — Engineering Principles

Standing rules that outlive any single design document or ADR. Where an
ADR records one decision with its own context and alternatives, a
principle here is meant to be checked against *every* future feature,
without re-litigating it each time. Referenced by ADRs; not itself an ADR.

---

## Every AI decision must degrade gracefully

**AI uncertainty is never a fail-stop.** When the system isn't confident
enough to act, it says so specifically and offers the narrowest safe next
step — never a bare error, never a silent guess.

Wrong:
> `Error: could not process document.`

Right:
> "Nisam dovoljno siguran kom predmetu ovo pripada. Evo dva moguća —
> izaberite jedan."

> "Nisam uspeo da pronađem rok u ovom dokumentu. Dokument je sačuvan bez
> rokova — dodajte ga ručno ako postoji."

This isn't a new pattern introduced by this principle — it's the pattern
the Smart Intake Engine design already uses everywhere: the review queue
(never a hard block, always a resolvable state), the Confidence Graph's
"insufficient evidence to guess" language (a specific, honest statement,
not a generic failure), the dead-letter lane (the same actionable OCR
failure message the product already gives today). Writing it down here
makes it a rule the next feature is checked against, not a convention
someone has to infer from reading enough of the codebase.

**Scope — this is not unconditional.** Fail-soft applies to *AI judgment
under uncertainty*: classification, extraction, matching, scoring. It does
**not** apply to system-integrity failures: a malware-positive upload, a
failed auth check, a failed storage write, a broken database constraint.
Those must still fail-stop, loudly. Degrading gracefully on "the file might
be malicious" or "the write didn't actually save" would not be a kindness
to the user — it would hide a real failure behind a reassuring message.
The test: if the uncertainty is about *what the AI concluded*, fail-soft.
If the uncertainty is about *whether the system did what it claims to have
done*, fail-stop.

**How to apply.** Before shipping a new AI-driven action, ask what its
"I'm not sure" state looks like — not whether it has one. If the honest
answer is "it would just error," the feature isn't done. Pair this with
[ADR-0017](adr/0017-automation-safety-levels.md) when deciding *who*
gets asked to resolve the uncertainty (automatic, review queue, or
explicit confirmation) — this principle governs *how* the system behaves
while waiting for that resolution, not who resolves it.
