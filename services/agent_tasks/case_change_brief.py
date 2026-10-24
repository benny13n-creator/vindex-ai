# -*- coding: utf-8 -*-
"""
Vindex AI — services/agent_tasks/case_change_brief.py
MIR001 TASK-08 — CASE_CHANGE_BRIEF: posle materijalne promene u predmetu (prihvaćen nov dokument) Vindex, bez zasebnog
zahteva advokata, priprema INTERNI pregled promene — šta se promenilo, iz kog izvora, i koje radnje je ta promena
otvorila — za ljudski pregled. Agent trajnog rada u POSTOJEĆEM NS007 ugovoru (tip je već dozvoljen u migraciji 136,
`routers/autonomy.py` i V2 `pripremljeno.js`): nova tabela, migracija ni ovlašćenje nisu potrebni.

PLANIRANJE — deterministički, 0 poziva modela. Posao nastaje SAMO ako je tačno:
  • trajni događaj `DocumentAccepted` ili `DocumentBatchCompleted` za predmet u poslednjih `PROZOR_DANA` dana;
  • predmet postoji, pripada ISTOM korisniku kao događaj, nije završen ni u brisanju i ima Case Genome (verzija ≥ 2 —
    bez prethodne verzije nema „promene“).
  Ključ posla = korisnik + predmet + verzija Genome-a: ista verzija = jedan pregled (bez duplikata kroz cikluse), nova
  verzija = nov ključ, a radnik prethodni QUEUED/READY označi SUPERSEDED. Predmet koji je u međuvremenu završen ili
  ušao u brisanje poništava pregled koji čeka.
IZVRŠENJE — deterministički, BEZ modela (`cost_class = FREE`, ne troši budžet): sadržaj je isključivo NS006
`genome-v2/promene` (vlasništvo prvo, samo čitanje) i radnje koje je događaj osvežio. Nema pravnih zaključaka, nema
slanja, nema izmene predmeta. Bez materijalne promene nema proizvoda (pošten neuspeh `NO_MATERIAL_CHANGE`).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("vindex.agent_tasks.case_change_brief")

AGENT_TYPE = "case_evolution"
WORK_TYPE = "CASE_CHANGE_BRIEF"
PROZOR_DANA = 7
_MAKS_DOGADJAJA = 500
_MAKS_STAVKI = 30
_DOGADJAJI = ("DocumentAccepted", "DocumentBatchCompleted")
# Promena samo brojača (dokumenata/tvrdnji u analizi) ili samoprovere analize nije materijalna: pregled se pravi kad se
# promenio rok, protivrečnost ili kad je promena otvorila NOVU radnju.
_SAMO_BROJACI = ("dokumenti_analize", "tvrdnje_analize", "provera_analize")


def _razlog_nepodobnosti(pred: dict | None, uid: str) -> str | None:
    from shared.constants import TERMINALNI_STATUSI_PREDMETA
    if pred is None:
        return "PREDMET_NE_POSTOJI"
    if str(pred.get("user_id")) != str(uid):
        return "VLASNIK_SE_NE_POKLAPA"
    if (pred.get("status") or "") in TERMINALNI_STATUSI_PREDMETA:
        return "PREDMET_ZAVRSEN"
    if pred.get("brisanje_zapoceto"):
        return "PREDMET_U_BRISANJU"
    g = pred.get("case_dna") if isinstance(pred.get("case_dna"), dict) else {}
    if not isinstance(g.get("verzija"), int) or g["verzija"] < 2:
        return "BEZ_PRETHODNE_VERZIJE"
    return None


async def planiraj(supa) -> dict:
    from services.autonomy import ucitaj_predmete
    from workers.background_agents import _resolve_orgs_batched
    od = (datetime.now(timezone.utc) - timedelta(days=PROZOR_DANA)).isoformat()
    ev = await asyncio.to_thread(lambda: supa.table("events").select("predmet_id,user_id,event_type,created_at")
                                 .in_("event_type", list(_DOGADJAJI)).gte("created_at", od)
                                 .order("created_at", desc=True).limit(_MAKS_DOGADJAJA).execute())
    parovi = {}
    for e in (ev.data or []):
        if e.get("predmet_id") and e.get("user_id"):
            parovi.setdefault((str(e["user_id"]), str(e["predmet_id"])), e)
    cek_r = await asyncio.to_thread(lambda: supa.table("autonomy_work_items").select("user_id,predmet_id,trigger_ref")
                                    .eq("work_type", WORK_TYPE).in_("status", ["QUEUED", "READY_FOR_REVIEW"]).execute())
    cekaju = list(cek_r.data or [])
    predmeti = await ucitaj_predmete(supa, sorted({p for _, p in parovi} | {str(c["predmet_id"]) for c in cekaju}))
    org = await _resolve_orgs_batched(sorted({u for u, _ in parovi}), supa)

    kandidati, preskoceno = [], {}
    for (uid, pid), e in parovi.items():
        pred = predmeti.get(pid)
        razlog = _razlog_nepodobnosti(pred, uid)
        if razlog:
            preskoceno[razlog] = preskoceno.get(razlog, 0) + 1
            continue
        v = pred["case_dna"]["verzija"]
        kandidati.append({
            "user_id": uid, "predmet_id": pid, "agent_type": AGENT_TYPE, "work_type": WORK_TYPE,
            # trigger_ref po VERZIJI: pregled poredi dve fiksne verzije (v-1 → v), pa ga novija verzija ne zastareva —
            # inače bi kasnija nematerijalna promena (npr. punomoćje) poništila nepregledan materijalni pregled.
            "trigger_type": "GENOME_VERSION", "trigger_ref": f"{pid}:g{v}", "source_version": v,
            "dedupe_key": f"{WORK_TYPE}:{pid}:g{v}",
            # Razlog se piše pri planiranju — ne tvrdi uzročnost koju tek izvršenje proverava (CHANGE_NOT_FROM_DOCUMENT).
            "reason": (f"U predmet je primljen dokument ({str(e.get('created_at') or '')[:10]}). Pregled promene analize "
                       f"predmeta (v{v}) priprema se samo ako je tu promenu proizveo prijem dokumenta.")[:500],
            "cost_class": "FREE", "budget_key": org.get(uid, (f"solo:{uid}",))[0], "max_attempts": 2,
        })
    ponisteni = [{"user_id": str(c["user_id"]), "predmet_id": str(c["predmet_id"]), "trigger_ref": str(c["trigger_ref"])}
                 for c in cekaju
                 if _razlog_nepodobnosti(predmeti.get(str(c["predmet_id"])), str(c["user_id"])) in
                 ("PREDMET_NE_POSTOJI", "VLASNIK_SE_NE_POKLAPA", "PREDMET_ZAVRSEN", "PREDMET_U_BRISANJU")]
    return {"kandidati": kandidati, "ponisteni": ponisteni, "preskoceno": preskoceno}


async def izvrsi(supa, item: dict) -> dict:
    from fastapi import HTTPException
    from routers.case_dna import sastavi_promene_predmeta, ucitaj_promene_predmeta
    from services import autonomy as au
    from shared.constants import TERMINALNI_STATUSI_PREDMETA

    uid, pid = str(item["user_id"]), str(item["predmet_id"])
    try:
        izv = await ucitaj_promene_predmeta(supa, pid, uid)           # vlasništvo prvo (404 za tuđ/nepostojeći)
    except HTTPException as e:
        if e.status_code == 404:
            raise au.NeuspehPosla("MATTER_NOT_ACCESSIBLE")
        raise RuntimeError("MATTER_OWNERSHIP_UNKNOWN")
    pred = (await au.ucitaj_predmete(supa, [pid])).get(pid)
    if pred is None or str(pred.get("user_id")) != uid:
        raise au.NeuspehPosla("MATTER_NOT_ACCESSIBLE")
    if (pred.get("status") or "") in TERMINALNI_STATUSI_PREDMETA or pred.get("brisanje_zapoceto"):
        raise au.NeuspehPosla("MATTER_NOT_ACTIVE")
    g = izv["case_dna"] if isinstance(izv["case_dna"], dict) else {}
    if g.get("verzija") != item.get("source_version"):
        raise au.NeuspehPosla("SOURCE_VERSION_CHANGED")
    if any(v != "OK" for v in izv["izvori"].values()):
        raise RuntimeError("CONTEXT_DEGRADED")                         # prolazno: bez proizvoda, ponavlja se ograničeno
    # Okidač mora biti DOKAZIV: verziju v je proizveo trajni događaj prijema dokumenta za ISTI predmet i korisnika.
    # Inače (ručno osvežavanje, ročište, ili događaj prijema koji nije pomerio analizu) razlog „primljen je nov dokument“
    # ne bi bio tačan — pošten neuspeh, bez proizvoda.
    from routers.case_dna import _ZP_TRIGGER_DOGADJAJ
    okidac = str(izv.get("okidac") or "")
    ev_id = okidac[len(_ZP_TRIGGER_DOGADJAJ):] if okidac.startswith(_ZP_TRIGGER_DOGADJAJ) else ""
    ev = []
    if ev_id:
        ev = (await asyncio.to_thread(lambda: supa.table("events").select("id").eq("id", ev_id).eq("predmet_id", pid)
                                      .eq("user_id", uid).in_("event_type", list(_DOGADJAJI)).limit(1).execute())).data or []
    if not ev:
        raise au.NeuspehPosla("CHANGE_NOT_FROM_DOCUMENT")
    pp = sastavi_promene_predmeta(izv)
    promene = [{k: s.get(k) for k in ("vrsta", "oznaka", "opis", "poreklo", "staro", "novo")} for s in (pp.get("promene") or [])]
    # NOVE radnje: nastale u ovoj promeni (događaj osvežava i ranije otvorene, pa `event_id` sam nije dovoljan)
    nastala = str(pp.get("nastala") or "")
    akcije = [{k: a.get(k) for k in ("id", "tip", "razlog", "prioritet", "rok", "status")}
              for a in (pp.get("akcije_dogadjaja") or [])
              if a.get("status") == "open" and (not nastala or str(a.get("created_at") or "") >= nastala)]
    if not [p for p in promene if p.get("vrsta") not in _SAMO_BROJACI] and not akcije:
        raise au.NeuspehPosla("NO_MATERIAL_CHANGE")
    naziv = pred.get("naziv") or "predmet"
    v = g.get("verzija")
    return {
        "title": f"Promena predmeta — {naziv} (analiza v{v})"[:300],
        "summary": (f"{len(promene)} promena u analizi predmeta (v{(v or 1) - 1} → v{v}); "
                    f"{len(akcije)} novih radnji iz ove promene. Ništa nije poslato ni izmenjeno — pregled je za vas.")[:2000],
        "content": {"vrsta": WORK_TYPE, "schema": "cb-1", "verzija": v, "prethodna_verzija": pp.get("prethodna_verzija"),
                    "okidac": pp.get("okidac"), "promene": promene[:_MAKS_STAVKI], "promena_ukupno": len(promene),
                    "radnje": akcije[:_MAKS_STAVKI], "nepoznato": pp.get("nepoznato") or []},
        "source_refs": [{"vrsta": "genome_verzija", "predmet_id": pid, "verzija": v}]
                       + [{"vrsta": "case_action", "id": a["id"]} for a in akcije[:_MAKS_STAVKI]],
        "quality_state": au.DETERMINISTICKO,
    }
