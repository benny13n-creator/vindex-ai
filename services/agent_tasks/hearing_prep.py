# -*- coding: utf-8 -*-
"""
Vindex AI — services/agent_tasks/hearing_prep.py

NS007 — HEARING_PREP: Vindex priprema materijal za STVARNO predstojeće ročište pre nego što advokat pita.
Agent trajnog rada (registar: `workers/background_agents._agent_modules`), NE legacy agent preporuka (nema `run`).

PLANIRANJE (`planiraj`) — deterministički, 0 poziva modela. Posao nastaje SAMO ako je sve tačno:
  • ročište iz kanonske tabele `rocista`, status `zakazano`, datum u prozoru [danas, danas + PROZOR] (podrazumevano
    danas i sutra; „danas" = isto `date.today()` kao Case Actions i Workspace);
  • predmet postoji, pripada ISTOM korisniku kao ročište, nije u završnom statusu (`TERMINALNI_STATUSI_PREDMETA`)
    i nije u brisanju (`brisanje_zapoceto`);
  • predmet ima Case Genome (verzija ≥ 1) — bez konteksta predmeta nema ni posla.
  Ključ posla = korisnik + ročište + verzija ročišta (datum, vreme, sud, sudnica) + verzija Genome-a. Promena ročišta
  ili analize = nov ključ; radnik tada stari QUEUED/READY označi SUPERSEDED (ne briše). Ročište koje više ne važi
  (otkazano, odloženo, održano, obrisano, van prozora, predmet zatvoren) poništava QUEUED/READY pripremu.
  Uz posao ide ZAŠTO (`reason`) i veza na postojeću Case Action „pripremiti podnesak" za isto ročište.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import date, timedelta

logger = logging.getLogger("vindex.agent_tasks.hearing_prep")

AGENT_TYPE = "hearing_prep"
WORK_TYPE = "HEARING_PREP"
_MAKS_ROCISTA = 500


def _danas() -> date:
    return date.today()


def _prozor_dana() -> int:
    try:
        return max(0, min(7, int(os.getenv("AUTONOMY_HEARING_WINDOW_DAYS", "1"))))
    except ValueError:
        return 1


def _datum(v):
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def verzija_rocista(r: dict) -> str:
    """Materijalni identitet ročišta: promena bilo čega od ovoga = nova priprema."""
    sirovo = "|".join(str(r.get(k) or "") for k in ("datum", "vreme", "sud", "sudnica"))
    return hashlib.sha256(sirovo.encode("utf-8")).hexdigest()[:12]


def _kada(dani: int) -> str:
    return "danas" if dani == 0 else "sutra" if dani == 1 else f"za {dani} dana"


def _srpski_datum(d: date) -> str:
    return d.strftime("%d.%m.%Y.")


async def _predmeti(supa, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    from shared.audit_immutable import _is_missing_column_error

    def _upit(kolone):
        return supa.table("predmeti").select(kolone).in_("id", ids).execute()
    try:
        r = await asyncio.to_thread(lambda: _upit("id,user_id,status,naziv,case_dna,brisanje_zapoceto"))
    except Exception as e:
        # Ista bezbedna grana kao shared/rag_acl.py: bez migracije 114 tombstone se ne može ni upisati.
        if not _is_missing_column_error(e):
            raise
        r = await asyncio.to_thread(lambda: _upit("id,user_id,status,naziv,case_dna"))
    return {str(p["id"]): p for p in (r.data or [])}


def _razlog_nepodobnosti(roc: dict, pred: dict | None, danas: date, prozor: int) -> str | None:
    from shared.constants import TERMINALNI_STATUSI_PREDMETA
    if roc.get("status") != "zakazano":
        return "ROCISTE_NIJE_ZAKAZANO"
    d = _datum(roc.get("datum"))
    if d is None or not (0 <= (d - danas).days <= prozor):
        return "VAN_PROZORA"
    if pred is None:
        return "PREDMET_NE_POSTOJI"
    if str(pred.get("user_id")) != str(roc.get("user_id")):
        return "VLASNIK_SE_NE_POKLAPA"
    if (pred.get("status") or "") in TERMINALNI_STATUSI_PREDMETA:
        return "PREDMET_ZAVRSEN"
    if pred.get("brisanje_zapoceto"):
        return "PREDMET_U_BRISANJU"
    g = pred.get("case_dna") if isinstance(pred.get("case_dna"), dict) else {}
    if not isinstance(g.get("verzija"), int) or g["verzija"] < 1:
        return "BEZ_GENOMA"
    return None


async def _akcije_za_rocista(supa, predmet_ids: list[str]) -> dict[str, str]:
    """{rociste_id: case_action_id} za otvorene „pripremiti podnesak" radnje (Case Actions, pravilo 1)."""
    if not predmet_ids:
        return {}
    try:
        r = await asyncio.to_thread(lambda: supa.table("case_actions").select("id,dokaz")
                                    .in_("predmet_id", predmet_ids).eq("tip", "PRIPREMITI_PODNESAK")
                                    .eq("status", "open").execute())
    except Exception as e:
        logger.warning("[HEARING_PREP] veza na Case Actions nije pročitana: %s", type(e).__name__)
        return {}   # veza je dodatak, ne uslov: posao se planira i bez nje
    out = {}
    for a in (r.data or []):
        rid = (a.get("dokaz") or {}).get("rociste_id") if isinstance(a.get("dokaz"), dict) else None
        if rid:
            out[str(rid)] = str(a["id"])
    return out


async def planiraj(supa) -> dict:
    from workers.background_agents import _resolve_orgs_batched
    danas, prozor = _danas(), _prozor_dana()
    do = danas + timedelta(days=prozor)
    roc_r = await asyncio.to_thread(lambda: supa.table("rocista")
                                    .select("id,predmet_id,user_id,datum,vreme,sud,sudnica,status")
                                    .eq("status", "zakazano").gte("datum", danas.isoformat()).lte("datum", do.isoformat())
                                    .order("datum").limit(_MAKS_ROCISTA).execute())
    rocista = list(roc_r.data or [])

    # pripreme koje čekaju ili su spremne — da li njihovo ročište još važi?
    cek_r = await asyncio.to_thread(lambda: supa.table("autonomy_work_items")
                                    .select("user_id,predmet_id,trigger_ref")
                                    .eq("work_type", WORK_TYPE).in_("status", ["QUEUED", "READY_FOR_REVIEW"]).execute())
    cekaju = list(cek_r.data or [])
    poznata = {str(r["id"]) for r in rocista}
    nepoznata = sorted({str(c["trigger_ref"]) for c in cekaju} - poznata)
    sva = {str(r["id"]): r for r in rocista}
    if nepoznata:
        dod = await asyncio.to_thread(lambda: supa.table("rocista")
                                      .select("id,predmet_id,user_id,datum,vreme,sud,sudnica,status")
                                      .in_("id", nepoznata).execute())
        sva.update({str(r["id"]): r for r in (dod.data or [])})

    predmeti = await _predmeti(supa, sorted({str(r["predmet_id"]) for r in sva.values()}
                                             | {str(c["predmet_id"]) for c in cekaju}))
    akcije = await _akcije_za_rocista(supa, sorted({str(r["predmet_id"]) for r in rocista}))
    org = await _resolve_orgs_batched(sorted({str(r["user_id"]) for r in rocista}), supa)

    kandidati, preskoceno = [], {}
    for roc in rocista:
        pred = predmeti.get(str(roc["predmet_id"]))
        razlog = _razlog_nepodobnosti(roc, pred, danas, prozor)
        if razlog:
            preskoceno[razlog] = preskoceno.get(razlog, 0) + 1
            continue
        d = _datum(roc["datum"])
        verzija_g = pred["case_dna"]["verzija"]
        vreme = f" u {str(roc['vreme'])[:5]}" if roc.get("vreme") else ""
        kandidati.append({
            "user_id": str(roc["user_id"]), "predmet_id": str(roc["predmet_id"]),
            "agent_type": AGENT_TYPE, "work_type": WORK_TYPE, "trigger_type": "ROCISTE",
            "trigger_ref": str(roc["id"]), "source_version": verzija_g,
            "dedupe_key": f"{WORK_TYPE}:{roc['id']}:{verzija_rocista(roc)}:g{verzija_g}",
            "reason": (f"Ročište {_kada((d - danas).days)} ({_srpski_datum(d)}{vreme}, {roc.get('sud') or 'sud nije naveden'}) — "
                       f"priprema po analizi predmeta v{verzija_g}.")[:500],
            "case_action_id": akcije.get(str(roc["id"])),
            "cost_class": "PAID", "budget_key": org.get(str(roc["user_id"]), (f"solo:{roc['user_id']}",))[0],
            "max_attempts": 2,
        })

    ponisteni = []
    for c in cekaju:
        roc = sva.get(str(c["trigger_ref"]))
        pred = predmeti.get(str(c["predmet_id"]))
        if roc is None or str(roc.get("predmet_id")) != str(c["predmet_id"]) \
                or _razlog_nepodobnosti(roc, pred, danas, prozor) not in (None, "BEZ_GENOMA"):
            ponisteni.append({"user_id": str(c["user_id"]), "predmet_id": str(c["predmet_id"]), "trigger_ref": str(c["trigger_ref"])})
    return {"kandidati": kandidati, "ponisteni": ponisteni, "preskoceno": preskoceno}
