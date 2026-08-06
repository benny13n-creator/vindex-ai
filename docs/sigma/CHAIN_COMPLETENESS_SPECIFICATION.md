# Chain Completeness Specification — Program Sigma, Master Sprint 003 (2026-08-06)

Phase 4 deliverable: verify whether every procedural chain (decision→proof of delivery, appeal→proof of
filing, submission→referenced attachment, power of attorney presence) has its own completeness check.

## Confirmed this sprint: no pairing checks exist anywhere

`routers/ugovor_zastupanja.py` was read directly — it is a contract-**generation** tool only
(`_generiši_ugovor`), zero "nedostaje"/"missing" logic, zero check for whether a case already has a
punomoćje linked or whether one is expected but absent. `routers/rocista.py`'s own field set has no
delivery/dostavnica tracking column. No file anywhere checks "case has a court decision → does it also have
a delivery receipt" or "case has an appeal → does it have proof of filing" pairing. **This entire Phase 4
concept is genuinely unbuilt** — not legacy, not a projection of something else, absent.

## Why this was not implemented blind this sprint

Each of the mission's own named chains is a real legal-domain rule with real correctness stakes:

- **Punomoćje (power of attorney) presence** — NOT every case needs one (a lawyer representing themselves,
  in-house counsel, or a case type where representation authority is established differently). A blanket
  "flag every case with no `ugovor_zastupanja` row" would produce a real, visible false-positive rate on
  day one — directly the kind of finding Phase 7's own "lažno pozitivni GAP-ovi" certification exists to
  catch, so it should not be shipped without that certification actually being able to test it against
  real case-type variation.
- **Appeal → proof of filing** — requires first reliably CLASSIFYING a document as "an appeal" (a
  `tip_dokaza` value) and a second document as "proof this specific appeal was filed" (not just any court
  filing) — a real classification/matching decision, not a schema lookup.
- **Decision → delivery receipt** — same shape: needs the decision to specifically be one this case's own
  timeline "relies on" (a deadline calculation basis), and a delivery receipt document/timeline entry
  specifically tied to THAT decision, not any decision.

None of these are safely automatable as a same-sprint mechanical fix without either (a) new document
classification categories/rules (real new algorithmic surface, the "no parallel heuristics per module" the
founding principle warns against unless centralized), or (b) a founder-level decision on acceptable
false-positive tolerance for a feature whose entire value proposition is "don't waste a lawyer's trust with
noise."

## Recommended design (not implemented this sprint)

Same shape as `DOCUMENT_EXPECTATION_ENGINE.md`'s own recommendation — a new gap type,
`GAP_TIP_NEPOTPUN_LANAC`, populated through the SAME single centralized mechanism
(`shared/gap_engine.py`), not a new per-chain heuristic module. Two implementation paths, both
requiring product input before building:

1. **Punomoćje specifically** — the simplest, most mechanically safe of the 4 examples (a single
   existence check: does this predmet have an `ugovor_zastupanja` row?), BUT still needs a founder decision
   on which case types genuinely require one before it can ship without a real false-positive problem.
2. **Document-pair chains (appeal/decision/delivery)** — needs the SAME extraction extension
   `DOCUMENT_EXPECTATION_ENGINE.md` already proposes for referenced-attachment detection — Genome's own
   single extraction pass reasoning about pairing, not a new GPT call, not a new heuristic per chain type.

Recorded as `SIGMA-014` (punomoćje presence, lower implementation risk once case-type scoping is decided)
and folded into `SIGMA-013`'s own broader extraction-extension scope for the document-pair chains
(appeal/decision/delivery), since both need the identical Genome-prompt-extension mechanism.

## What Phase 4 certification WOULD need, once built (documented now so it isn't re-derived later)

Per Phase 7's own mandate ("lažno pozitivni GAP-ovi... propušteni GAP-ovi... nestabilni rezultati između
dva pokretanja"), any future chain-completeness implementation needs, before shipping: a labeled test set
of real (or realistic synthetic) case document sets with KNOWN correct answers for each of the 4 chain
types, run twice to confirm stability (Genome's own GPT-driven extraction is not perfectly deterministic
run-to-run — already an established characteristic of this platform, not new to this finding), and an
explicit false-positive-rate tolerance decision from the founder before default-enabling it for every case.
