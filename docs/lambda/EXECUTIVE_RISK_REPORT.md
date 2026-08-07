# EXECUTIVE_RISK_REPORT — Program Lambda, Certification 008

For the founder. Non-technical summary, risk-ranked, with the one action that matters most stated first.

## The one thing to do before anything else

**Run migrations 102 and 103 against production Supabase.** These were written back in Certification 002
to close a real, live vulnerability: right now, any logged-in user can drain another user's paid credits to
zero, or grant themselves free permanent PRO access, through two different paths (a database function with
no ownership check, and a permissions gap on the profiles table). The fix has existed for a while — it just
hasn't been run yet. This is the single highest-priority item in this entire certification, and it predates
this sprint (this sprint re-confirmed it's still true, it didn't discover it new).

## What this sprint found and fixed, in plain terms

- **A real invoice-numbering bug**: if a lawyer double-clicked "create invoice" (or had two tabs open),
  the system could create two invoices with the identical official number — a compliance problem for
  Serbian sequential invoicing rules. Fixed.
- **A billing bug**: if the AI assistant (the main Q&A feature) failed to answer due to an OpenAI outage,
  the system was charging the lawyer a credit anyway with no refund. Fixed — now refunds automatically on a
  genuine failure, same as it already did for other failure types.
- **A dashboard bug**: the Law Firm Health Index (an overview score) was silently breaking due to a
  database column that doesn't exist, quietly showing wrong (empty) numbers for 4 of its components
  instead of an error. Fixed.
- **A privacy gap**: a document-analysis feature let an authenticated user read another firm's permanently-
  stored case documents if they somehow obtained or guessed the case's internal ID — no ownership check was
  ever run. Fixed.
- **Several places where the system knew something went wrong but never told the lawyer**: a new case
  created via document upload where 0 documents actually attached, an AI legal analysis silently based on
  the wrong court, a search that returned "no results" when part of the search actually failed rather than
  genuinely finding nothing. All three now surface a clear warning to the lawyer instead of staying silent.
- **A scalability risk in the nightly automation**: the background AI agents that run every night could,
  as the number of active users grows, silently process fewer and fewer of them within the time window —
  not crash, just quietly do less. Now processes several users at once instead of one at a time, fitting
  more work into the same window.
- **A live-typing AI assistant (the Word/browser copilot) had no check that its legal citation suggestions
  were actually grounded in real source material** — only a prompt instruction telling it not to make things
  up, no code-level verification. Fixed — a citation is now dropped rather than shown if it can't be
  verified against what the AI actually retrieved.

Full technical detail for each: `docs/lambda/LAMBDA008_CERTIFICATION_REPORT.md`.

## What's flagged but deliberately not touched this sprint

- **9 more dead/unused backend features**, similar to the onboarding-system finding from a previous
  sprint — not broken, just unused code sitting in the app. Whether to delete them or finish/revive them is
  your call, not something to decide automatically. Full list in the Architectural Debt Register.
- **One remaining duplicate risk-calculation** in the case-uncertainty dashboard — lower priority, real but
  not urgent, needs a slightly bigger fix than this sprint's time budget allowed.

## Bottom line

Once migrations 102/103 are run, this sprint found no other CRITICAL, currently-exploitable issue. The
platform's foundation (ownership checks across 136+ endpoints, tenant isolation, RLS, AI provenance
tracking) was independently re-swept and held up well — most of what this sprint found and fixed were real
but contained bugs, not systemic failures. See `BETA_READINESS_FINAL.md` for the formal go/no-go statement.
