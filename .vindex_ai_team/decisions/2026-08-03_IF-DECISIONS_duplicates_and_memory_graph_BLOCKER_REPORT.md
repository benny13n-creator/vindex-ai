# Blocker Report — three findings needing a founder decision, not a wiring fix

**Mission:** Operation Invisible Features (BETA-003), 2026-08-03.
**Status:** BLOCKED on founder input for all three. No code changed for any of them.

---

## 1. Client CSV import — two full implementations, only the less-safe one live

**Finding:** `routers/import_klijenti.py` implements a 3-step import: download a template → upload +
preview with column-mapping → execute only after explicit confirmation. It has zero frontend callers.
The frontend instead calls `klijenti/router.py:1435`'s `POST /klijenti/import-csv` — a simpler
one-shot import with fixed expected columns, no preview, no confirmation step
(`static/vindex.js:4946`).

**Why this isn't a safe wiring fix:** the *safer* implementation is the dead one. Wiring it in means
choosing one of:
1. Replace the live one-shot import with the safer preview-then-confirm flow entirely (a real UX
   change to an existing, presumably-in-use feature).
2. Add the safer flow as a second "advanced import" option alongside the existing one (more UI surface,
   two ways to do the same thing — a duplicate the app would then be knowingly keeping, not just
   discovering).
3. Leave the safer implementation dead and consider it superseded design work.

This is a product decision (which import experience the founder wants live), not an engineering one —
matches this mission's own Stop Condition ("Founder Design Decision"). Not guessed at.

## 2. WhatsApp notifications — two full Twilio implementations, only the simpler one live

**Finding:** `routers/whatsapp_notif.py` is a dedicated WhatsApp subscription system (its own
`whatsapp_pretplate`/`whatsapp_send_log` tables, granular per-notification-type preferences,
registration flow). Zero frontend callers. The live system is `routers/sms.py` — same underlying
Twilio integration, but exposed as a single `whatsapp: bool` flag on the SMS delivery profile
(`vindex.js:2836`/`:2858` → `POST /sms/telefon`), which is read and does correctly route messages via
WhatsApp-formatted numbers (`sms.py:201-202,285-287`).

**Assessment:** the simpler live system already covers the core lawyer need (choose WhatsApp vs. SMS
for delivery). The dedicated subscription router adds granularity (which specific notification types
go via WhatsApp) that no evidence in this investigation suggests lawyers are asking for. **This reads
as a legitimate cleanup/deletion candidate, not a reconnection candidate** — but deleting a fully-built
feature is itself a decision worth the founder making explicitly, not something this mission unilaterally
removes. Recommendation: confirm the simpler flag-based approach is intentionally the final design
before either deleting `whatsapp_notif.py` or reconnecting it.

## 3. Memory Graph (`routers/memory_graph.py`) — genuinely dead, but not safely wireable as a simple query box

**Finding:** `GET /api/memory-graph/upit` (natural-language query over the firm's relationship graph —
"every case where partner A used argument X before judge Z and won") is real, sophisticated, and has
zero frontend callers — the single most interesting Bucket-A finding of this census, matching the
founder's own product-philosophy documents' description of institutional-memory value.

**Why this can't just get a query box tonight:** `memory_graph_edges` (the table the query reads) has
exactly **one writer in the entire repository** — the also-dead `POST /memory-graph/dodaj-vezu` manual
entry endpoint. Nothing in Case Genome, Case Pipeline, Evidence Vault, or any extraction pipeline
auto-populates it. Confirmed by reading `graph_upit`'s own code: if `memory_graph_edges` has zero rows
for the firm, it returns *"Graf je prazan. Počnite da dodajete veze između entiteta."* ("The graph is
empty. Start adding connections."). Shipping a query UI tonight would show every real lawyer an empty
graph, forever, unless they also separately discover and use the equally-unwired manual "add a
relationship" endpoint one relationship at a time — not a usable feature, a UI for a feature that
doesn't yet populate itself.

**What would need deciding before this is a safe wiring task:**
1. Does the founder want manual relationship entry as the intended UX (in which case BOTH `/upit` and
   `/dodaj-vezu` need UI, and the query box alone tonight would be actively misleading)?
2. Or should relationships be auto-extracted from existing case data (Case Genome's `pravna_teorija`,
   Evidence Vault's `pravni_elementi`, decision log entries)? That would be **new AI/extraction logic**,
   explicitly forbidden by this mission's own charter ("Do NOT implement new AI").

Recommendation: leave `memory_graph` on the board as `NEEDS_SCOPING` pending this specific founder
call, rather than ship a technically-connected but practically-useless empty query box.

---

## Mission Board disposition
`IF-003` (import_klijenti), `IF-004` (whatsapp_notif), `IF-005` (memory_graph) all added as
`NEEDS_SCOPING` — founder decision required for each, per this report.
