# Workflow — Commit-Triggered Review

**Status: documented protocol, not wired into an actual git hook or CI job yet.** Wiring this into
a real `pre-commit`/`post-commit` hook or a new `.github/workflows/` job is an infrastructure change
with broader blast radius than documentation (it changes what happens on every future commit or CI
run) — that decision is deliberately left to an explicit founder go-ahead rather than assumed here,
consistent with this project's own standing caution around changes to shared infrastructure.

## The trigger patterns

Not every commit needs a governance pass. These path patterns always do, regardless of how small
the diff looks — because this project's own history (SEC-001 through SEC-073) shows the highest
concentration of severe findings sits exactly in these areas:

| Path pattern | Required review |
|---|---|
| `migrations/*.sql`, `supabase_setup.sql` | Database Architect (`DATABASE_REVIEW.md`), mandatory — per `agents/08_database_architect.md`'s veto on destructive migrations |
| `shared/deps.py`, `shared/permissions.py`, `shared/usage.py`, `klijenti/permissions.py`, anything touching auth/authz | Security & Privacy Architect (`SECURITY_REVIEW.md`), mandatory |
| `shared/ai_client.py`, `security/prompt_guard.py`, any new AI-provider call site | AI System Architect (`AI_DESIGN_REVIEW.md`) + Security & Privacy Architect |
| `security/*.py`, `docs/security/*.md` changes that alter a claim | Security & Privacy Architect, mandatory, and cross-check against `docs/security/PUBLIC_SECURITY_CLAIMS.md` |
| Anything touching `docs/architecture/VINDEX_CORE_CONSOLIDATION.md`-consolidated systems (Case Genome, Legal Reasoning Engine, the entitlement system) | AI CTO — architecture-significance check |
| `static/vindex.js` direct Supabase client writes (`sb.from(...).update(...)`) | Security & Privacy Architect, mandatory — this exact pattern produced SEC-038 |

## What "required review" means in practice, absent a wired hook

Until this is wired into an actual hook or CI job, **Claude Code applies this table manually**: when
about to commit (or when reviewing a diff someone else wrote) that touches any pattern above,
Claude Code runs the corresponding phase from `OPERATING_PROTOCOL.md` before considering the change
complete — the same way `git status`/`git diff` are already checked before any commit per this
project's standing git-safety protocol. This is a discipline applied by the agent doing the work,
not (yet) a mechanically enforced gate.

## If/when this gets wired to an actual hook or CI job

The natural home is a new job in `.github/workflows/security.yml` (already the location of this
project's real, blocking CI scans — gitleaks, bandit, pip-audit, semgrep) that greps the diff's
changed paths against the table above and fails the build if a matching pattern has no corresponding
`decisions/*_SECURITY_REVIEW.md` (or equivalent) referenced in the commit message or PR description.
**This is a future-expansion item** (also noted in `README.md`), not built now — building an
enforcement mechanism before the manual discipline has been exercised even once risks encoding the
wrong shape prematurely.
