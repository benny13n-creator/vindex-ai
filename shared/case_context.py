# -*- coding: utf-8 -*-
"""
Vindex AI — shared/case_context.py

Program Tau, Master Sprint 002 (2026-08-06) — "Canonical Case Context Engine".

THE single canonical entry point for "what does GPT see about this case."
Tau Sprint 001 found 4 independent, hand-rolled context-assembly functions
(`case_commander.py`, `case_intelligence.py`, `copilot.py`, `morning_briefing.py`),
each with a different, non-overlapping blind spot — none gives GPT documents +
Genome + evidence + actions together. This module ends that fragmentation by
construction: it is the ONE place that assembles a case's full context, and
Phase 5 migrates the 3 modules that can be migrated (see
`AI_ENTRY_POINT_MIGRATION_REPORT.md` for why `strategija.py` cannot — it has
no `predmet_id`-driven request model at all, confirmed in
`CONTEXT_BUILDER_REGISTRY.md`) to call `build_case_context()` instead of
running their own bespoke queries.

## What this module explicitly does NOT do (Tau 002's own "ZABRANJENO" list)

- Does not build a new Genome/Evidence system — every fact-bearing field below
  is read from an already-canonical source (`case_dna`, `shared/gap_engine.py`,
  `shared/case_readiness.py`, `services/risk_engine.py`, `case_actions`,
  `rocista`, `predmet_hronologija`) via a direct call, never re-derived.
- Does not build a parallel document sampler — Layer 4 (`_select_documents` /
  `_excerpt`) calls `routers/cross_doc.py::_uzorkuj_dokument`, the one existing
  stride-based sampler already proven to handle late-document content
  correctly, rather than reimplementing truncation logic a 5th time.
- Does not use GPT summarization as a substitute for structured data —
  `document_summaries` below is a deterministic excerpt-preview, not a new AI
  call. Zero GPT calls happen anywhere in this module.
- Does not send all N documents of a large case directly to the model — see
  Layer 4/5 below for how a 500-document case stays within a bounded budget
  while keeping every document individually reachable.

## Provenance: every field carries {value, source, owner, refresh, timestamp}

Phase 2's own explicit requirement ("izvor, vlasnik, način osvežavanja").
`context_field()` is the one constructor — mirrors the idiom Sigma Sprint 005
established in `shared/commander_schema.py` (never leave provenance to
convention), adapted for THIS contract's own 3-attribute requirement.

## Document Visibility Engine (Phase 3) — the 5 layers

Layer 1 (case metadata) = `case_identity`/`participants`/`procedural_status`.
Layer 2 (Genome facts) = `key_facts`/`contradictions`/part of `missing_evidence`.
Layer 3 (evidence graph) = `evidence_graph`.
Layer 4 (relevant document excerpts) = `relevant_documents.included` — a
  bounded, budget-respecting sample computed by `_select_documents`: the
  `MAX_RECENT_ALWAYS_INCLUDED` most recent documents are always included
  (recency signal), plus a deterministic stride sample across the FULL
  remaining set (not just the head — this is the specific bug this module
  exists to fix; `case_commander.py`'s own prior `[:10]` slice on an
  unordered fetch meant the same 10 documents dominated forever regardless
  of case size).
Layer 5 (on-demand deep retrieval) = `get_document_full_text()` — any
  document NOT in the Layer 4 sample is listed in
  `relevant_documents.not_included_but_retrievable` with its own `dokument_id`
  and this function's own name as the retrieval path. This is how the
  mission's "nijedan relevantan dokument ne može ostati trajno nevidljiv"
  requirement is actually satisfied at 500+/1000+ document scale: not by
  cramming everything into one prompt (impossible), but by guaranteeing every
  document has a working, deterministic, individually-addressable path to
  full text, whether or not it happened to be sampled into THIS call's
  excerpt set.

## Determinism (Phase 7's own requirement)

No randomness anywhere in this module (no `random` import). Document
selection depends only on the fetched row set's own `redni_broj`/`created_at`
ordering and a fixed stride formula — the same case, unchanged, produces the
same `CaseContext` every call, from any process, after any restart. No
module-level cache or shared mutable state exists, so concurrent calls for
different (or the same) case never interfere with each other.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from services.risk_engine import calculate_procesni_rizik, identify_case_problems
from shared.constants import EXPECTED_DOCS
from shared.case_readiness import compute_case_readiness, top_open_action
from shared.gap_engine import collect_case_gaps

CONTRACT_VERSION = "1.0.0"

# Layer 4 budget — deliberately generous vs. case_commander.py's old 8000/2000
# (which fed only 10 of up to 20 fetched documents, always the same 10): this
# module handles the "many more documents than fit" problem via document-level
# selection (_select_documents), not by shrinking the per-document budget.
DOC_EXCERPT_BUDGET_PER_DOC = 1500
MAX_DOCS_INCLUDED = 15
MAX_RECENT_ALWAYS_INCLUDED = 5


def context_field(value: Any, source: str, owner: str, refresh: str) -> dict:
    """Every CaseContext field carries this shape. Phase 2's own explicit
    provenance requirement, plus a timestamp for Phase 6's auditability
    requirement."""
    return {
        "value": value,
        "source": source,
        "owner": owner,
        "refresh": refresh,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _fetch_raw(predmet_id: str, uid: str, supa, include_documents: bool = True) -> dict:
    """The ONE place these 7 tables are queried for context-assembly purposes.
    Phase 5 migrates case_intelligence.py/copilot.py/morning_briefing.py off
    their own bespoke fetch blocks onto build_case_context() (below), which
    calls this. `include_documents=False` skips the predmet_dokumenti query
    entirely -- for a portfolio-wide caller looping over many cases
    (morning_briefing.py), paying for a document fetch + excerpt pass on
    every case every morning is real, avoidable cost for signal that digest
    doesn't need (Phase 6's own cost-control mandate)."""
    async def _skip():
        return None

    # Program Lambda, Master Sprint 001 (Performance Auditor finding): this
    # query used to select `tekst_sadrzaj` (full document text) for EVERY row
    # matching predmet_id, unconditionally -- the 500/1000-document tests
    # (test_tau002_case_context.py) only ever exercised _select_documents()
    # directly on an in-memory list, never this SQL query itself, so they
    # never proved this fetch scales. At 5,000-10,000 real document rows,
    # this single query would pull that many full-text rows over the network
    # before _select_documents()'s own bounding logic (MAX_DOCS_INCLUDED=15)
    # ever runs. Fixed here, not by adding a row LIMIT (that would silently
    # break the stride-sampler's own "visibility across the FULL set"
    # guarantee for any case past the limit) -- instead, `tekst_sadrzaj` is
    # dropped from THIS metadata-only query entirely and fetched separately,
    # by build_case_context() below, ONLY for the ~15 documents
    # _select_documents() actually selects. Every row is still visited here
    # (so selection/recency/stride logic sees the true full set, unchanged
    # behavior), just without the expensive text column for the ~99% of rows
    # that won't be included anyway.
    dok_awaitable = (
        asyncio.to_thread(
            # order by redni_broj -- NOT the unordered fetch case_commander.py's
            # own pre-Tau-002 _dohvati_predmet_kontekst used, which is exactly
            # why the same static head-slice dominated forever on a growing case.
            lambda: supa.table("predmet_dokumenti")
                .select("id, naziv_fajla, created_at, tip_dokaza, status, redni_broj")
                .eq("predmet_id", predmet_id)
                .order("redni_broj")
                .execute()
        )
        if include_documents else _skip()
    )

    (pred_r, dok_r, dokazi_r, rocista_r, actions_r, hron_r, kom_r) = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti").select("*")
                .eq("id", predmet_id).eq("user_id", uid).maybe_single().execute()
        ),
        dok_awaitable,
        asyncio.to_thread(
            lambda: supa.table("predmet_dokazi")
                .select("id, snaga, kategorija, pravni_element")
                .eq("predmet_id", predmet_id)
                .is_("deleted_at", "null")
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("id, sud, datum, status")
                .eq("predmet_id", predmet_id)
                # BLACKSWAN-HIGH-007: bounded, same reasoning as predmet_hronologija below.
                .order("datum", desc=True)
                .limit(50)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("case_actions")
                .select("tip, razlog, dokaz, prioritet, rok, dedupe_key, status")
                .eq("predmet_id", predmet_id)
                .eq("status", "open")
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_hronologija")
                .select("dogadjaj, datum_iso, vaznost")
                .eq("predmet_id", predmet_id)
                # BLACKSWAN-HIGH-007 fix (Operation Black Swan, Mission 001, Scenario 12):
                # was unbounded -- unlike the sibling predmet_komentari query 2 lines below
                # (which already has .limit(5)). Every case-changing event during a long
                # session adds a row here; build_case_context() gets called on every AI-
                # context build for the same active case, re-fetching the ENTIRE, ever-
                # growing history each time even though every downstream consumer only
                # uses the first several rows (e.g. hearing_cc.py's own `timeline[:8]`).
                # SIMULATED (Black Swan Team 7): 500 sequential actions -> row fetch grew
                # 5->500 (101.7x), 16.1x slower per call, 25,250 cumulative rows fetched
                # across one session's context builds vs 800 if bounded to what's used.
                # Switched to recency-first (desc) + bounded, consistent with this
                # session's other document/event sampling fixes (case_commander.py,
                # zakon_monitoring.py, multi_agent.py) -- the most recent events are the
                # most relevant "what's the current state of this case" signal, and a
                # downstream consumer wanting chronological-ascending display order can
                # still reverse this bounded list cheaply in Python.
                .order("datum_iso", desc=True)
                .limit(50)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_komentari")
                .select("tekst, created_at")
                .eq("predmet_id", predmet_id)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
        ),
        return_exceptions=True,
    )

    def _safe(r):
        if isinstance(r, Exception):
            return []
        return getattr(r, "data", None) or []

    def _safe_one(r):
        if isinstance(r, Exception):
            return {}
        return getattr(r, "data", None) or {}

    return {
        "predmet":      _safe_one(pred_r),
        "dokumenti":    _safe(dok_r),
        "dokazi":       _safe(dokazi_r),
        "rocista":      _safe(rocista_r),
        "case_actions": _safe(actions_r),
        "hronologija":  _safe(hron_r),
        "komentari":    _safe(kom_r),
    }


def _select_documents(dokumenti: list[dict]) -> tuple[list[dict], list[dict]]:
    """Document Visibility Engine, Layer 4 selection. Deterministic: always
    includes the MAX_RECENT_ALWAYS_INCLUDED most recently created documents,
    plus a fixed-stride sample across the full remaining set (by redni_broj
    order, as fetched) so a 500-document case doesn't permanently hide
    documents 21-500 the way a static [:20]/[:10] slice would. Returns
    (included, not_included) — not_included carries enough identity
    (dokument_id) for Layer 5 (get_document_full_text) to retrieve any of
    them on demand."""
    if not dokumenti:
        return [], []
    if len(dokumenti) <= MAX_DOCS_INCLUDED:
        return list(dokumenti), []

    # Sort by redni_broj first (stable identity ordering) regardless of the
    # order rows arrived in -- a caller-side fetch is expected to already use
    # .order("redni_broj"), but this function does not TRUST that: the same
    # document SET must select the same result no matter what order it's
    # handed in (Phase 7's own determinism requirement, and the mission's own
    # "dokumenti van redosleda" extreme test).
    by_redni_broj = sorted(dokumenti, key=lambda d: (d.get("redni_broj") is None, d.get("redni_broj"), d.get("id") or ""))

    by_recency = sorted(by_redni_broj, key=lambda d: (d.get("created_at") or "", d.get("id") or ""), reverse=True)
    recent_ids = {d.get("id") for d in by_recency[:MAX_RECENT_ALWAYS_INCLUDED]}
    included = list(by_recency[:MAX_RECENT_ALWAYS_INCLUDED])

    remainder = [d for d in by_redni_broj if d.get("id") not in recent_ids]
    slots_left = max(0, MAX_DOCS_INCLUDED - len(included))
    if remainder and slots_left:
        korak = max(1, len(remainder) // slots_left)
        included += remainder[::korak][:slots_left]

    included_ids = {d.get("id") for d in included}
    not_included = [d for d in dokumenti if d.get("id") not in included_ids]
    return included, not_included


async def _fetch_document_texts(dokument_ids: list[str], predmet_id: str, supa) -> dict[str, str]:
    """Program Lambda, Master Sprint 001: the targeted 2nd-phase fetch that
    makes the metadata-only query in _fetch_raw safe -- pulls `tekst_sadrzaj`
    for ONLY the bounded set of documents _select_documents() already chose
    (<= MAX_DOCS_INCLUDED), by id, in one query. Not a new context builder:
    same table, same predmet_id scope, just a 2nd query instead of one
    unconditionally-wide one. Fail-soft: a failure here degrades to empty
    text for the affected documents (same as any other _fetch_raw field),
    never raises."""
    if not dokument_ids:
        return {}
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("id, tekst_sadrzaj")
                .eq("predmet_id", predmet_id)
                .in_("id", dokument_ids)
                .execute()
        )
        rows = getattr(r, "data", None) or []
        return {row.get("id"): (row.get("tekst_sadrzaj") or "") for row in rows}
    except Exception:
        return {}


def _excerpt(tekst: str, budget: int = DOC_EXCERPT_BUDGET_PER_DOC) -> tuple[str, bool]:
    """Layer 4 within-document sampling — reuses routers/cross_doc.py's own
    stride-based sampler (Program Celina, AKCIJA 2, 2026-07-24) rather than
    reimplementing truncation, per this sprint's own explicit
    'ne praviti paralelne context builder-e' constraint."""
    from routers.cross_doc import _uzorkuj_dokument
    return _uzorkuj_dokument(tekst or "", budget=budget)


def _label_past_vs_upcoming(rocista: list[dict]) -> list[dict]:
    """Program Tau, Master Sprint 004 (2026-08-06): `rocista` is fetched with
    no date filter -- both past and future hearings are in the same list,
    and Phase 2's own context-quality audit found nothing distinguishes them
    (item #15, 'Previous hearings' -- present but undifferentiated). Adds a
    `proslo` (bool) field per row, computed from `datum` vs. today -- so a
    prompt built from this field can tell GPT "this hearing already
    happened" vs "this is scheduled," without changing which table is read
    or adding a second deadline source (only `rocista.status` existed as an
    outcome signal before; still the only one -- this labels timing, not
    outcome, which this platform doesn't track anywhere yet)."""
    from datetime import date as _date
    danas = _date.today().isoformat()
    out = []
    for r in rocista or []:
        row = dict(r)
        datum = str(r.get("datum") or "")[:10]
        row["proslo"] = bool(datum) and datum < danas
        out.append(row)
    return out


def _group_dokazi(dokazi: list[dict]) -> dict:
    grupe: dict[str, dict] = {}
    for d in dokazi or []:
        kat = d.get("kategorija") or "nekategorisano"
        g = grupe.setdefault(kat, {"broj": 0, "po_snazi": {}})
        g["broj"] += 1
        snaga = d.get("snaga") or "nepoznato"
        g["po_snazi"][snaga] = g["po_snazi"].get(snaga, 0) + 1
    return grupe


async def get_document_full_text(predmet_id: str, uid: str, dokument_id: str, supa) -> dict:
    """Document Visibility Engine, Layer 5 — on-demand deep retrieval. The
    proof that no relevant document is PERMANENTLY invisible: whether or not
    a document was sampled into a given build_case_context() call's Layer 4
    excerpt set, it remains reachable through this single, RLS-scoped,
    deterministic lookup by id. Returns {"found": False} rather than raising
    if the document doesn't exist or doesn't belong to this predmet/user —
    callers decide how to handle that, this function doesn't assume."""
    # Lambda Certification 003 (2026-08-06) -- ranije se `uid` parametar
    # primao ali NIKAD nije korišćen u upitu, iako docstring ovde tvrdi
    # "RLS-scoped" -- backend svuda koristi service-role klijenta koji RLS
    # potpuno zaobilazi (shared/deps.py::_get_supa), pa je stvarna zaštita
    # bila samo `predmet_id` filter. Dormant nalaz (nula poziva ovoj funkciji
    # postoji igde u repou danas), ali upravo zato što je ovo dokumentovani
    # "safety net" za skaliranje (Layer 5), ispravljeno pre nego što ga bilo
    # koja buduća ruta poveže -- isti obrazac kao svaki drugi predmet_dokumenti
    # upit u ovom fajlu.
    row = await asyncio.to_thread(
        lambda: supa.table("predmet_dokumenti")
            .select("id, naziv_fajla, tekst_sadrzaj, tip_dokaza, status, redni_broj, created_at")
            .eq("id", dokument_id)
            .eq("predmet_id", predmet_id)
            .eq("user_id", uid)
            .maybe_single()
            .execute()
    )
    data = getattr(row, "data", None)
    if not data:
        return {"found": False, "dokument_id": dokument_id}
    return {
        "found": True,
        "dokument_id": data.get("id"),
        "naziv": data.get("naziv_fajla"),
        "tekst_sadrzaj": data.get("tekst_sadrzaj") or "",
        "tip_dokaza": data.get("tip_dokaza"),
        "redni_broj": data.get("redni_broj"),
    }


async def build_case_context(predmet_id: str, uid: str, supa, include_documents: bool = True) -> dict:
    """THE canonical CaseContext entry point. Every fact-bearing field reads
    an already-canonical source directly — this function computes nothing new
    except document selection (Layer 4, a visibility concern, not a new
    business decision) and the aggregation/grouping shown below.

    `include_documents=False` (see `_fetch_raw`) skips Layer 4/5 entirely --
    for a portfolio-wide, many-cases-per-call consumer (morning_briefing.py)
    that only needs the cheap Layers 1-3 (identity/readiness/actions/
    deadlines), this avoids a document fetch + excerpt pass per case, per
    run, for signal that consumer doesn't use. `relevant_documents`/
    `document_summaries` are still present and correctly shaped in the
    response, just carrying an explicit "not fetched for this call" marker
    rather than silently implying zero documents exist."""
    raw = await _fetch_raw(predmet_id, uid, supa, include_documents=include_documents)
    predmet = raw["predmet"]
    if not predmet:
        return {"error": "predmet_not_found", "predmet_id": predmet_id, "contract_version": CONTRACT_VERSION}

    case_dna = predmet.get("case_dna") or {}
    genome_computed = bool(case_dna) and not case_dna.get("greska")
    tip_predmeta = predmet.get("tip_postupka") or predmet.get("oblast") or ""

    rizik = calculate_procesni_rizik(
        dokazi=raw["dokazi"], dokumenti=raw["dokumenti"], rocista=raw["rocista"],
        tip_predmeta=tip_predmeta, expected_docs=EXPECTED_DOCS,
    )
    problemi = identify_case_problems(rizik, tip_predmeta)
    gaps = collect_case_gaps(problemi, case_dna)
    readiness = compute_case_readiness(raw["case_actions"], gaps, genome_computed=genome_computed)
    top_action = top_open_action(raw["case_actions"])

    included_docs, not_included_docs = _select_documents(raw["dokumenti"]) if include_documents else ([], [])

    # Program Lambda, Master Sprint 001: _fetch_raw's own predmet_dokumenti
    # query no longer carries tekst_sadrzaj (metadata-only, see its own
    # comment) -- fetch the actual text ONLY for the bounded `included_docs`
    # set (<= MAX_DOCS_INCLUDED), never for the full per-case document count.
    if included_docs:
        tekst_by_id = await _fetch_document_texts(
            [d.get("id") for d in included_docs if d.get("id")], predmet_id, supa
        )
        for d in included_docs:
            d["tekst_sadrzaj"] = tekst_by_id.get(d.get("id"), "")

    excerpts = []
    sampled_within_doc = []
    for d in included_docs:
        tekst, sampled = _excerpt(d.get("tekst_sadrzaj") or "")
        if sampled:
            sampled_within_doc.append(d.get("naziv_fajla"))
        excerpts.append({
            "dokument_id": d.get("id"), "naziv": d.get("naziv_fajla"),
            "redni_broj": d.get("redni_broj"), "excerpt": tekst, "sampled_within_doc": sampled,
        })

    not_included_refs = [
        {
            "dokument_id": d.get("id"), "naziv": d.get("naziv_fajla"), "redni_broj": d.get("redni_broj"),
            "retrieval": "shared.case_context.get_document_full_text(predmet_id, uid, dokument_id, supa)",
        }
        for d in not_included_docs
    ]

    contradictions_list = [g for g in gaps if g["tip"] == "KONTRADIKCIJA"]
    missing_list = [g for g in gaps if g["tip"] != "KONTRADIKCIJA"]

    now = datetime.now(timezone.utc).isoformat()

    return {
        "contract_version": CONTRACT_VERSION,
        "case_identity": context_field(
            {
                "id": predmet.get("id"), "naziv": predmet.get("naziv"),
                "tip_postupka": tip_predmeta, "sud": predmet.get("sud"),
                "status": predmet.get("status"),
                "vrednost_spora": predmet.get("vrednost_spora") or predmet.get("vrednost"),
            },
            source="predmeti", owner="predmeti table", refresh="real-time read-through",
        ),
        "participants": context_field(
            {"stranka": predmet.get("stranka"), "protivnik": predmet.get("protivnik"), "klijent_id": predmet.get("klijent_id")},
            source="predmeti", owner="predmeti table", refresh="real-time read-through",
        ),
        "procedural_status": context_field(
            {"status": predmet.get("status"), "readiness_status": readiness["status"], "readiness_razlog": readiness["razlog"]},
            source="predmeti.status + shared/case_readiness.py::compute_case_readiness",
            owner="predmeti table / case_readiness.py", refresh="real-time",
        ),
        "timeline": context_field(
            raw["hronologija"],
            source="predmet_hronologija", owner="services/case_evolution.py (writer)",
            refresh="event-driven (written on case-changing events)",
        ),
        "key_facts": context_field(
            {
                "pravna_teorija": case_dna.get("pravna_teorija"),
                "snaga_predmeta_procent": case_dna.get("snaga_predmeta_procent"),
                "najslabija_tacka": case_dna.get("najslabija_tacka"),
            } if genome_computed else None,
            source="predmeti.case_dna (Genome)", owner="routers/case_dna.py (Genome extraction)",
            refresh="on Genome refresh (manual or auto-triggered)",
        ),
        "evidence_graph": context_field(
            {"ukupno_dokaza": len(raw["dokazi"]), "po_kategoriji": _group_dokazi(raw["dokazi"])},
            source="predmet_dokazi", owner="predmet_dokazi table", refresh="real-time read-through",
        ),
        "contradictions": context_field(
            contradictions_list,
            source="shared/gap_engine.py::gaps_from_contradictions (case_dna.kontradikcije[], identity via shared/contradiction_identity.py)",
            owner="Genome extraction + gap_engine.py normalizer", refresh="on Genome refresh",
        ),
        "missing_evidence": context_field(
            missing_list,
            source="shared/gap_engine.py::collect_case_gaps",
            owner="gap_engine.py (aggregates services/risk_engine.py + Genome)",
            refresh="real-time (pure function over already-fetched data)",
        ),
        "deadlines": context_field(
            _label_past_vs_upcoming(raw["rocista"]), source="rocista", owner="rocista table",
            refresh="real-time read-through (canonical deadline source since Sigma Sprint 005)",
        ),
        "active_actions": context_field(
            raw["case_actions"], source="case_actions", owner="services/case_evolution.py (writer)",
            refresh="event-driven (written on Genome/document/deadline change)",
        ),
        "readiness": context_field(
            readiness, source="shared/case_readiness.py::compute_case_readiness",
            owner="case_readiness.py", refresh="real-time (pure function over case_actions + gaps)",
        ),
        "relevant_documents": context_field(
            {
                "included": excerpts,
                "not_included_but_retrievable": not_included_refs,
                "total_documents": len(raw["dokumenti"]) if include_documents else None,
                "sampled_within_doc": sampled_within_doc,
                "fetched_this_call": include_documents,
            },
            source="predmet_dokumenti + Document Visibility Engine Layer 4" if include_documents
                else "not fetched -- caller requested include_documents=False (lightweight mode)",
            owner="shared/case_context.py::_select_documents (reuses routers/cross_doc.py's stride sampler)",
            refresh="real-time per call, deterministic given the same document set",
        ),
        "document_summaries": context_field(
            [{"dokument_id": e["dokument_id"], "naziv": e["naziv"], "preview": e["excerpt"][:200]} for e in excerpts],
            source="Document Visibility Engine Layer 4 excerpts (deterministic truncation, NOT a GPT summary)" if include_documents
                else "not fetched -- caller requested include_documents=False (lightweight mode)",
            owner="shared/case_context.py", refresh="real-time per call",
        ),
        "audit_metadata": context_field(
            {
                "predmet_id": predmet_id, "generated_at": now, "genome_computed": genome_computed,
                "top_action_dedupe_key": (top_action or {}).get("dedupe_key"),
                "doc_count_total": len(raw["dokumenti"]), "doc_count_included": len(excerpts),
                "doc_count_retrievable_on_demand": len(not_included_refs),
            },
            source="shared/case_context.py (self-reporting)", owner="shared/case_context.py",
            refresh="generated fresh every call",
        ),
    }
