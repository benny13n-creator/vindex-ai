# -*- coding: utf-8 -*-
"""
Vindex AI — services/legal_reasoning_engine.py

Legal Reasoning Engine — Phase 0 (docs/architecture/LEGAL_REASONING_ARCHITECTURE.md).

Founder's definition (kept verbatim as the contract this module must honor):
"Legal Reasoning Engine je centralni sloj između Case Genome i svih viših
AI modula. Njegova odgovornost nije da piše tekst niti da donosi konačne
preporuke, već da iz strukturiranih činjenica, dokaza i pravnih izvora
izgradi proverljiv Reasoning Graph koji eksplicitno povezuje činjenice,
pravne elemente, norme i privremene pravne zaključke sa nivoom
pouzdanosti."

Phase 0 binding constraints (founder, 2026-07-23):
  - No user-facing text output. The only output is the structured graph.
  - Wired to nothing: no automatic trigger, no downstream consumer reads
    this yet. Manual generation only (POST /reasoning-graph/generate).
  - Relational storage only (migrations/076_legal_reasoning_engine.sql) —
    jsonb is never the canonical store for graph data (founder decision).
  - Genome's argumenti_za/argumenti_protiv/kontradikcije fields are NOT
    touched by this module — that migration is explicitly Phase 1, not
    Phase 0 (docs/architecture/LEGAL_REASONING_ARCHITECTURE.md Sec 1/12).

Known Phase 0 simplification, stated plainly rather than hidden: retrieval
verification (retrieval_agreement, Sec 10a) is a substring match against
the text chunks app.services.retrieve.retrieve_documents() already
returns, not a structured per-citation lookup — the public retrieval API
does not expose a full per-hit (law, article, score) list, only top-1
metadata plus raw text chunks. Narrower than the target design, real
rather than fabricated precision.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("vindex.legal_reasoning")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

_REASONING_SYSTEM = """Ti si pravni AI koji gradi STRUKTURISAN graf rezonovanja, ne tekst.

Dobijas: (1) listu cinjenica sa ID-jevima (FACT-n), (2) listu dostupnih pravnih izvora sa ID-jevima (SOURCE-n), (3) kratak opis predmeta.

Tvoj zadatak: identifikuj lance rezonovanja — koje cinjenice, kombinovane sa kojim pravnim izvorima, vode do kog pravnog zakljucka (claim).

STROGA PRAVILA:
1. Koristi ISKLJUCIVO FACT-n i SOURCE-n ID-jeve koji su ti dati. NE izmisljaj nove cinjenice niti nove clanove zakona.
2. Ako nijedna cinjenica ne podrzava neki mogu ci zakljucak, ne navodi taj zakljucak.
3. Svaki claim MORA imati bar jednu cinjenicu i bar jedan pravni izvor.
4. model_certainty je TVOJA sopstvena procena sigurnosti (0.0-1.0) — budi konzervativan, ne preteruj.

Vrati ISKLJUCIVO JSON (bez markdown, bez teksta van JSON-a):
{
  "chains": [
    {
      "legal_element": "Kratak naziv pravnog elementa (npr. 'Uzročna veza')",
      "facts": ["FACT-1", "FACT-3"],
      "norms": ["SOURCE-2"],
      "claim": "Kratak, proverljiv pravni zakljucak (NE recenica sa objasnjenjem, samo tvrdnja)",
      "model_certainty": 0.7
    }
  ]
}
Prazna lista "chains" je validan odgovor ako dostupni podaci ne dozvoljavaju nijedan cvrst zakljucak."""


async def _fetch_predmet_and_genome(supa, predmet_id: str, user_id: str) -> dict:
    r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id,naziv,tip,opis,case_dna")
            .eq("id", predmet_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
    )
    return (r.data or {}) if r else {}


async def _fetch_facts(supa, predmet_id: str) -> list[dict]:
    """Facts come from Evidence Vault (predmet_dokazi) — already-classified,
    already-real. LRE does not invent facts, it reasons over existing ones."""
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmet_dokazi")
                .select("id,tvrdnja,kategorija,pravni_element,dokument_id")
                .eq("predmet_id", predmet_id)
                .is_("deleted_at", "null")
                .limit(30)
                .execute()
        )
        return [d for d in (r.data or []) if (d.get("tvrdnja") or "").strip()]
    except Exception as exc:
        logger.warning("[LRE] Fetch facts greška: %s", exc)
        return []


def _fetch_legal_sources_sync(query: str) -> tuple[list[str], dict]:
    """Synchronous wrapper around the existing retrieval engine — reused
    unchanged, LRE does not have its own retrieval pipeline (Sec 4)."""
    from app.services.retrieve import retrieve_documents
    docs, meta = retrieve_documents(query, k=6)
    return docs or [], meta or {}


async def _fetch_legal_sources(query: str) -> tuple[list[str], dict]:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_fetch_legal_sources_sync, query), timeout=15.0
        )
    except Exception as exc:
        logger.warning("[LRE] Fetch legal sources greška: %s", exc)
        return [], {}


def _build_reasoning_prompt(genome: dict, facts: list[dict], sources: list[str]) -> str:
    teorija = genome.get("pravna_teorija") or {}
    identitet = teorija.get("pravni_identitet", "")

    fact_lines = [
        f"FACT-{i+1}: {(f.get('tvrdnja') or '').strip()}"
        + (f" [{f['pravni_element']}]" if f.get("pravni_element") else "")
        for i, f in enumerate(facts)
    ]
    source_lines = [f"SOURCE-{i+1}: {s.strip()[:600]}" for i, s in enumerate(sources)]

    return (
        f"Predmet: {identitet or 'nepoznat identitet'}\n\n"
        f"CINJENICE:\n" + ("\n".join(fact_lines) if fact_lines else "(nema cinjenica u Evidence Vault-u)") + "\n\n"
        f"DOSTUPNI PRAVNI IZVORI:\n" + ("\n".join(source_lines) if source_lines else "(nema pronadjenih izvora)")
    )


async def _call_reasoning_gpt(prompt: str) -> dict:
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-4o", temperature=0.1, max_tokens=2500,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _REASONING_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            ),
            timeout=45.0,
        )
        raw = (resp.choices[0].message.content or "{}").strip()
        return json.loads(raw)
    except Exception as exc:
        logger.warning("[LRE] GPT poziv greška: %s", exc)
        return {"chains": [], "greska": str(exc)[:200]}


def _retrieval_agreement(cited_source_texts: list[str], retrieval_docs: list[str]) -> float:
    """Coarse, honest check (Phase 0 simplification, see module docstring):
    does the cited source text appear as a substring of what was actually
    retrieved? Not a precise per-citation lookup — retrieve_documents()
    does not expose structured per-hit metadata for every result."""
    if not cited_source_texts:
        return 0.0
    combined = " ".join(retrieval_docs).lower()
    hits = sum(1 for t in cited_source_texts if t.strip().lower()[:80] in combined)
    return round(hits / len(cited_source_texts), 3)


def _precedent_support(retrieval_meta: dict) -> float:
    matches = retrieval_meta.get("praksa_matches") or []
    if not matches:
        return 0.0
    scores = [m.get("score", 0) for m in matches[:3] if isinstance(m.get("score"), (int, float))]
    return round(min(1.0, sum(scores) / len(scores)), 3) if scores else 0.0


def compute_confidence(
    evidence_coverage: float,
    retrieval_agreement: float,
    precedent_support: float,
    model_certainty: float,
) -> dict:
    """Weighted formula, founder decision 2026-07-23 (Sec 10a) — three of
    four components are deterministic/computed, not trusted from GPT's own
    self-report. model_certainty is capped at 15% weight specifically so a
    confident-sounding hallucination cannot dominate the score."""
    total = (
        0.35 * evidence_coverage
        + 0.30 * retrieval_agreement
        + 0.20 * precedent_support
        + 0.15 * model_certainty
    )
    return {
        "evidence_coverage": round(evidence_coverage, 3),
        "retrieval_agreement": round(retrieval_agreement, 3),
        "precedent_support": round(precedent_support, 3),
        "model_certainty": round(model_certainty, 3),
        "confidence_total": round(total, 3),
    }


async def generate_reasoning_graph(predmet_id: str, user_id: str) -> dict:
    """
    Phase 0 orchestrator. Returns structured data only (ids, counts,
    per-node summaries) — NO prose, per the founder's binding Phase 0
    constraint. Writes reasoning_graph/reasoning_nodes/reasoning_edges/
    reasoning_evidence/reasoning_sources/reasoning_confidence.
    """
    from shared.deps import _get_supa

    supa = _get_supa()

    predmet = await _fetch_predmet_and_genome(supa, predmet_id, user_id)
    if not predmet:
        return {"greska": "Predmet nije pronadjen"}

    genome = predmet.get("case_dna") or {}
    if not genome or genome.get("greska"):
        return {"greska": "Case Genome ne postoji za ovaj predmet — LRE zahteva Genome kao ulaz (Genome opisuje, LRE zakljucuje)."}

    facts = await _fetch_facts(supa, predmet_id)

    teorija = genome.get("pravna_teorija") or {}
    query_parts = [teorija.get("pravni_identitet", ""), teorija.get("osnov_odgovornosti", "")]
    query = " ".join(p for p in query_parts if p).strip() or (predmet.get("opis") or predmet.get("naziv") or "")
    sources, retrieval_meta = await _fetch_legal_sources(query) if query else ([], {})

    # ── Verzija (Sec 5a — versioned, not overwritten in place) ────────────────
    prev_r = await asyncio.to_thread(
        lambda: supa.table("reasoning_graph")
            .select("verzija")
            .eq("predmet_id", predmet_id)
            .order("verzija", desc=True)
            .limit(1)
            .execute()
    )
    prev_verzija = (prev_r.data[0]["verzija"] if prev_r.data else 0)
    nova_verzija = prev_verzija + 1

    header_insert = await asyncio.to_thread(
        lambda: supa.table("reasoning_graph").insert({
            "predmet_id": predmet_id,
            "user_id": user_id,
            "verzija": nova_verzija,
            "genome_verzija": genome.get("verzija"),
            "trigger_event": "manual_generate",
            "status": "generating",
        }).execute()
    )
    graph_row = (header_insert.data or [{}])[0]
    graph_id = graph_row.get("id")
    if not graph_id:
        return {"greska": "Neuspesan upis reasoning_graph header reda"}

    try:
        prompt = _build_reasoning_prompt(genome, facts, sources)
        gpt_result = await _call_reasoning_gpt(prompt)
        chains = gpt_result.get("chains") or []

        facts_by_ref = {f"FACT-{i+1}": f for i, f in enumerate(facts)}
        sources_by_ref = {f"SOURCE-{i+1}": s for i, s in enumerate(sources)}

        nodes_created = {"Fact": 0, "LegalElement": 0, "Norm": 0, "Claim": 0}
        edges_created = 0
        claims_summary: list[dict] = []

        # Fact nodes — one per referenced FACT-n, created once, reused across chains
        fact_node_ids: dict[str, str] = {}
        source_node_ids: dict[str, str] = {}

        for chain in chains:
            chain_facts = [f for f in (chain.get("facts") or []) if f in facts_by_ref]
            chain_norms = [s for s in (chain.get("norms") or []) if s in sources_by_ref]
            if not chain_facts or not chain_norms or not chain.get("claim"):
                continue  # Sec: every claim must have >=1 fact and >=1 norm — enforced here too, not just prompt-side

            for fref in chain_facts:
                if fref not in fact_node_ids:
                    f = facts_by_ref[fref]
                    n = await asyncio.to_thread(lambda f=f: supa.table("reasoning_nodes").insert({
                        "graph_id": graph_id, "predmet_id": predmet_id, "user_id": user_id,
                        "node_type": "Fact", "label": (f.get("tvrdnja") or "")[:300],
                        "detalji": {"dokument_id": f.get("dokument_id"), "kategorija": f.get("kategorija")},
                    }).execute())
                    fact_node_ids[fref] = (n.data or [{}])[0].get("id")
                    nodes_created["Fact"] += 1
                    await asyncio.to_thread(lambda f=f, node_id=fact_node_ids[fref]: supa.table("reasoning_evidence").insert({
                        "node_id": node_id, "predmet_id": predmet_id, "user_id": user_id,
                        "dokaz_id": f.get("id"), "dokument_id": f.get("dokument_id"),
                    }).execute())

            le_r = await asyncio.to_thread(lambda c=chain: supa.table("reasoning_nodes").insert({
                "graph_id": graph_id, "predmet_id": predmet_id, "user_id": user_id,
                "node_type": "LegalElement", "label": (c.get("legal_element") or "")[:300],
            }).execute())
            le_id = (le_r.data or [{}])[0].get("id")
            nodes_created["LegalElement"] += 1

            for fref in chain_facts:
                await asyncio.to_thread(lambda a=fact_node_ids[fref], b=le_id: supa.table("reasoning_edges").insert({
                    "graph_id": graph_id, "predmet_id": predmet_id, "user_id": user_id,
                    "edge_type": "supports", "from_node_id": a, "to_node_id": b,
                }).execute())
                edges_created += 1

            for sref in chain_norms:
                if sref not in source_node_ids:
                    s_text = sources_by_ref[sref]
                    n = await asyncio.to_thread(lambda s=s_text: supa.table("reasoning_nodes").insert({
                        "graph_id": graph_id, "predmet_id": predmet_id, "user_id": user_id,
                        "node_type": "Norm", "label": s[:300],
                    }).execute())
                    source_node_ids[sref] = (n.data or [{}])[0].get("id")
                    nodes_created["Norm"] += 1
                    await asyncio.to_thread(lambda node_id=source_node_ids[sref]: supa.table("reasoning_sources").insert({
                        "node_id": node_id, "predmet_id": predmet_id, "user_id": user_id,
                        "zakon": retrieval_meta.get("top_law"), "clan": retrieval_meta.get("top_article"),
                        "retrieval_score": retrieval_meta.get("top_score"),
                    }).execute())
                await asyncio.to_thread(lambda a=le_id, b=source_node_ids[sref]: supa.table("reasoning_edges").insert({
                    "graph_id": graph_id, "predmet_id": predmet_id, "user_id": user_id,
                    "edge_type": "satisfies", "from_node_id": a, "to_node_id": b,
                }).execute())
                edges_created += 1

            claim_r = await asyncio.to_thread(lambda c=chain: supa.table("reasoning_nodes").insert({
                "graph_id": graph_id, "predmet_id": predmet_id, "user_id": user_id,
                "node_type": "Claim", "label": (c.get("claim") or "")[:300],
            }).execute())
            claim_id = (claim_r.data or [{}])[0].get("id")
            nodes_created["Claim"] += 1

            for sref in chain_norms:
                await asyncio.to_thread(lambda a=source_node_ids[sref], b=claim_id: supa.table("reasoning_edges").insert({
                    "graph_id": graph_id, "predmet_id": predmet_id, "user_id": user_id,
                    "edge_type": "creates", "from_node_id": a, "to_node_id": b,
                }).execute())
                edges_created += 1

            cited_source_texts = [sources_by_ref[s] for s in chain_norms]
            n_facts_total = len(chain.get("facts") or [])
            evidence_coverage = (len(chain_facts) / n_facts_total) if n_facts_total else 0.0
            conf = compute_confidence(
                evidence_coverage=evidence_coverage,
                retrieval_agreement=_retrieval_agreement(cited_source_texts, sources),
                precedent_support=_precedent_support(retrieval_meta),
                model_certainty=float(chain.get("model_certainty") or 0.0),
            )
            await asyncio.to_thread(lambda claim_id=claim_id, conf=conf: supa.table("reasoning_confidence").insert({
                "node_id": claim_id, "predmet_id": predmet_id, "user_id": user_id,
                **conf,
            }).execute())
            claims_summary.append({"claim_id": claim_id, "label": chain.get("claim"), **conf})

        await asyncio.to_thread(lambda: supa.table("reasoning_graph").update({
            "status": "complete",
        }).eq("id", graph_id).execute())

        return {
            "graph_id": graph_id,
            "predmet_id": predmet_id,
            "verzija": nova_verzija,
            "nodes_created": nodes_created,
            "edges_created": edges_created,
            "claims": claims_summary,
        }
    except Exception as exc:
        logger.warning("[LRE] Generacija neuspesna: %s", exc)
        await asyncio.to_thread(lambda: supa.table("reasoning_graph").update({
            "status": "failed", "greska": str(exc)[:300],
        }).eq("id", graph_id).execute())
        return {"greska": str(exc)[:300], "graph_id": graph_id, "verzija": nova_verzija}
