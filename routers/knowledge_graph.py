# -*- coding: utf-8 -*-
"""
Legal Knowledge Graph — mreža odnosa predmeta.

Vraća nodes + edges za SVG vizualizaciju:
  Predmet ↔ Klijenti/Stranke ↔ Zakoni ↔ Presude ↔ Dokumenti ↔ Rokovi
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.knowledge_graph")
router = APIRouter(prefix="/api/knowledge-graph", tags=["knowledge_graph"])


@router.get("/predmeti/{predmet_id}")
async def get_knowledge_graph(predmet_id: str, user=Depends(get_current_user)):
    """Vraća nodes i edges za Knowledge Graph predmeta."""
    supa = _get_supa()
    uid = user["user_id"]

    # Ownership check
    pr = supa.table("predmeti").select(
        "id,naziv,tip,status,oblast,tuzilac,tuzeni"
    ).eq("id", predmet_id).eq("user_id", uid).execute()
    if not pr.data:
        raise HTTPException(status_code=404)
    predmet = pr.data[0]

    nodes = []
    edges = []

    # ── Centralni čvor: Predmet ────────────────────────────────────────────────
    nodes.append({
        "id": f"predmet_{predmet_id}",
        "label": predmet.get("naziv", "Predmet")[:28],
        "tip": "predmet",
        "color": "#4aa8ff",
        "radius": 22,
        "meta": {"status": predmet.get("status", ""), "tip": predmet.get("tip", "")},
    })

    # ── Klijenti (stranke) ────────────────────────────────────────────────────
    try:
        pk = supa.table("predmet_klijenti").select(
            "klijent_id,uloga,klijenti(ime,prezime,firma)"
        ).eq("predmet_id", predmet_id).limit(8).execute()
        for r in (pk.data or []):
            k = r.get("klijenti") or {}
            ime = ((k.get("ime", "") + " " + k.get("prezime", "")).strip()
                   or k.get("firma", "Klijent"))[:22]
            kid = f"klijent_{r['klijent_id']}"
            nodes.append({"id": kid, "label": ime, "tip": "klijent", "color": "#7de0a0", "radius": 14,
                          "meta": {"uloga": r.get("uloga", "")}})
            edges.append({"from": f"predmet_{predmet_id}", "to": kid,
                          "label": r.get("uloga", "stranka"), "strength": "strong"})
    except Exception as e:
        logger.debug("[KG] klijenti greška: %s", e)

    # ── Tužilac/Tuženi iz inline polja ────────────────────────────────────────
    if predmet.get("tuzilac"):
        tid = "stranaka_tuzilac"
        nodes.append({"id": tid, "label": predmet["tuzilac"][:22], "tip": "klijent",
                      "color": "#7de0a0", "radius": 12, "meta": {"uloga": "tužilac"}})
        edges.append({"from": f"predmet_{predmet_id}", "to": tid, "label": "tužilac", "strength": "strong"})
    if predmet.get("tuzeni"):
        tid2 = "stranaka_tuzeni"
        nodes.append({"id": tid2, "label": predmet["tuzeni"][:22], "tip": "klijent",
                      "color": "#ff9090", "radius": 12, "meta": {"uloga": "tuženi"}})
        edges.append({"from": f"predmet_{predmet_id}", "to": tid2, "label": "tuženi", "strength": "strong"})

    # ── Dokumenti ─────────────────────────────────────────────────────────────
    try:
        dok = supa.table("predmet_dokumenti").select(
            "id,naziv_fajla,tip_dokaza"
        ).eq("predmet_id", predmet_id).is_("deleted_at", "null").limit(8).execute()
        for d in (dok.data or []):
            did = f"dok_{d['id']}"
            nodes.append({"id": did, "label": (d.get("naziv_fajla") or "Dokument")[:20],
                          "tip": "dokument", "color": "#b89aff", "radius": 11,
                          "meta": {"tip_dokaza": d.get("tip_dokaza") or ""}})
            edges.append({"from": f"predmet_{predmet_id}", "to": did,
                          "label": d.get("tip_dokaza") or "dokument", "strength": "normal"})
    except Exception as e:
        logger.debug("[KG] dokumenti greška: %s", e)

    # ── Rokovi ────────────────────────────────────────────────────────────────
    try:
        rok = supa.table("predmet_rokovi").select(
            "id,naziv,datum_isteka,status"
        ).eq("predmet_id", predmet_id).limit(5).execute()
        for r in (rok.data or []):
            rid = f"rok_{r['id']}"
            nodes.append({"id": rid, "label": (r.get("naziv") or "Rok")[:18],
                          "tip": "rok", "color": "#ff9090", "radius": 10,
                          "meta": {"datum": r.get("datum_isteka", ""), "status": r.get("status", "")}})
            edges.append({"from": f"predmet_{predmet_id}", "to": rid,
                          "label": r.get("datum_isteka", "rok")[:10], "strength": "normal"})
    except Exception as e:
        logger.debug("[KG] rokovi greška: %s", e)

    # ── Sudska praksa iz hronologije (zakon reference) ────────────────────────
    try:
        hron = supa.table("predmet_hronologija").select(
            "dogadjaj,akter,vaznost"
        ).eq("predmet_id", predmet_id).order("datum_iso").limit(6).execute()
        seen_akteri = set()
        for h in (hron.data or []):
            akter = (h.get("akter") or "").strip()
            if akter and akter not in seen_akteri:
                seen_akteri.add(akter)
                aid = f"akter_{akter[:15].replace(' ','_')}"
                nodes.append({"id": aid, "label": akter[:20], "tip": "zakon",
                              "color": "#ffcc50", "radius": 10,
                              "meta": {"vaznost": h.get("vaznost", "")}})
                edges.append({"from": f"predmet_{predmet_id}", "to": aid,
                              "label": h.get("vaznost", ""), "strength": "normal"})
    except Exception as e:
        logger.debug("[KG] hronologija greška: %s", e)

    # ── Oblast zakona ─────────────────────────────────────────────────────────
    if predmet.get("tip"):
        _OBLAST_MAP = {
            "parnicno": "ZPP", "krivicno": "KZ / ZKP", "upravno": "ZUP / ZUS",
            "radno": "Zakon o radu", "porodicno": "Porodični zakon",
            "nasledjivanje": "Zakon o nasleđivanju", "privredno": "ZPD",
            "nepokretnosti": "Zakon o prometu nepokretnosti", "ostalo": "Opšti propisi",
        }
        oblast_label = _OBLAST_MAP.get(predmet.get("tip", ""), predmet.get("tip", ""))
        zid = f"zakon_{predmet.get('tip', 'ostalo')}"
        nodes.append({"id": zid, "label": oblast_label, "tip": "zakon",
                      "color": "#ffcc50", "radius": 13,
                      "meta": {"tip": predmet.get("tip", "")}})
        edges.append({"from": f"predmet_{predmet_id}", "to": zid,
                      "label": "pravni osnov", "strength": "strong"})

    return {"nodes": nodes, "edges": edges, "predmet_naziv": predmet.get("naziv", "")}
