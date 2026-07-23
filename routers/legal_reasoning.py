# -*- coding: utf-8 -*-
"""
Vindex AI — routers/legal_reasoning.py

Legal Reasoning Engine — Phase 0 API surface.
docs/architecture/LEGAL_REASONING_ARCHITECTURE.md

Manual trigger only — Phase 0 is explicitly "wired to nothing" (founder,
2026-07-23): no automatic generation on GenomeUpdated, no downstream
consumer. That wiring is Phase 1+ work, gated on its own approval.

Responses are structured data only (ids, counts, per-claim confidence
breakdowns) — never prose. The founder's binding Phase 0 constraint: LRE
must not generate user-facing text.
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from services.legal_reasoning_engine import generate_reasoning_graph
from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.legal_reasoning_router")
router = APIRouter(prefix="/api/predmeti", tags=["legal_reasoning"])


@router.post("/{predmet_id}/reasoning-graph/generate")
@limiter.limit("10/minute")
async def reasoning_graph_generate(predmet_id: str, request: Request, user=Depends(get_current_user)):
    uid = user["user_id"]
    result = await generate_reasoning_graph(predmet_id, uid)
    if result.get("greska") and "graph_id" not in result:
        raise HTTPException(status_code=422, detail=result["greska"])
    try:
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            "reasoning_graph_generated", user_id=uid,
            resource_type="predmet", resource_id=predmet_id,
            metadata={"verzija": result.get("verzija"), "graph_id": result.get("graph_id")},
        ))
    except Exception as exc:
        logger.warning("[LRE] Audit log greška (nije kritično): %s", exc)
    return result


@router.get("/{predmet_id}/reasoning-graph")
async def reasoning_graph_get(predmet_id: str, user=Depends(get_current_user)):
    supa = _get_supa()
    uid = user["user_id"]

    graph_r = await asyncio.to_thread(
        lambda: supa.table("reasoning_graph")
            .select("id,verzija,genome_verzija,trigger_event,status,greska,created_at")
            .eq("predmet_id", predmet_id)
            .eq("user_id", uid)
            .order("verzija", desc=True)
            .limit(1)
            .execute()
    )
    if not graph_r.data:
        raise HTTPException(status_code=404, detail="Nema reasoning grafa za ovaj predmet")
    graph = graph_r.data[0]
    graph_id = graph["id"]

    nodes_r, edges_r, confidence_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("reasoning_nodes").select(
            "id,node_type,label,detalji,created_at"
        ).eq("graph_id", graph_id).execute()),
        asyncio.to_thread(lambda: supa.table("reasoning_edges").select(
            "id,edge_type,from_node_id,to_node_id"
        ).eq("graph_id", graph_id).execute()),
        asyncio.to_thread(lambda: supa.table("reasoning_confidence").select(
            "node_id,evidence_coverage,retrieval_agreement,precedent_support,model_certainty,confidence_total"
        ).eq("predmet_id", predmet_id).execute()),
        return_exceptions=True,
    )

    def _d(r):
        return (r.data if not isinstance(r, Exception) else []) or []

    return {
        "graph": graph,
        "nodes": _d(nodes_r),
        "edges": _d(edges_r),
        "confidence": _d(confidence_r),
    }


@router.get("/{predmet_id}/reasoning-graph/history")
async def reasoning_graph_history(predmet_id: str, user=Depends(get_current_user)):
    supa = _get_supa()
    uid = user["user_id"]
    r = await asyncio.to_thread(
        lambda: supa.table("reasoning_graph")
            .select("id,verzija,genome_verzija,trigger_event,status,created_at")
            .eq("predmet_id", predmet_id)
            .eq("user_id", uid)
            .order("verzija", desc=True)
            .execute()
    )
    return {"predmet_id": predmet_id, "verzije": r.data or []}
