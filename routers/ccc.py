# -*- coding: utf-8 -*-
"""
Case Command Center — jedan API poziv koji agregira sve podatke predmeta.

GET /api/ccc/predmeti/{predmet_id}
Vraća: predmet, matter_intel, dokazi, rokovi, billing, aktivnosti, sudska_praksa
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from shared.deps import _get_supa, get_current_user
from shared.constants import EXPECTED_DOCS as _EXPECTED_DOCS
from services.risk_engine import calculate_procesni_rizik

logger = logging.getLogger("vindex.ccc")
router = APIRouter(prefix="/api/ccc", tags=["ccc"])


@router.get("/predmeti/{predmet_id}")
async def get_ccc(predmet_id: str, user=Depends(get_current_user)):
    supa = _get_supa()
    uid  = user["user_id"]

    # ── Ownership check ─────────────────────────────────────────────────────
    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select(
            "id,naziv,tip,status,oblast,tuzilac,tuzeni,rizik,vrednost_spora,opis,created_at"
        ).eq("id", predmet_id).eq("user_id", uid).execute()
    )
    if not pr.data:
        raise HTTPException(status_code=404)
    predmet = pr.data[0]

    # ── Svih 6 upita paralelno ───────────────────────────────────────────────
    (
        dokazi_r,
        dok_count_r,
        rok_r,
        be_r,
        hron_r,
        kl_r,
    ) = await asyncio.gather(
        # Operation Single Brain (2026-08-07): .is_("deleted_at","null") added -- this query
        # was the only one of 4 canonical-risk consumers (matter_intel.py, api.py::predmet_
        # workspace, shared/case_context.py all already exclude soft-deleted evidence) that
        # counted a deleted predmet_dokazi row into the risk formula. Execution-tested by
        # this mission's Team 6: in one scenario this bug and the tip_dokaza bug (fixed
        # alongside this one) happened to cancel out to a coincidentally-matching health_score
        # between two endpoints, masking both real defects.
        asyncio.to_thread(lambda: supa.table("predmet_dokazi").select(
            "snaga,kategorija"
        ).eq("predmet_id", predmet_id).is_("deleted_at", "null").execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("id,naziv_fajla,status,tip_dokaza").eq(
            "predmet_id", predmet_id).execute()),
        # Operation Single Brain, Mission 002 (Team 6 finding): the `.limit(10)` here was
        # the ONLY difference between this query and matter_intel.py's own unbounded
        # equivalent, even though BOTH feed the identical calculate_procesni_rizik() call
        # below -- for a case with more hearings than the cap (ordered by nearest date
        # ASCENDING with no future-only filter, so a docket with several past hearings
        # could push upcoming ones past the cutoff entirely), this endpoint's health/
        # risk badge could diverge from Matter Intel's for the same case, and a genuinely
        # critical upcoming hearing could be invisible to both risk calc and display.
        # Unbounded now, matching matter_intel.py exactly -- one input set, not two.
        asyncio.to_thread(lambda: supa.table("rocista").select(
            "id,sud,datum,status,napomena"
        ).eq("predmet_id", predmet_id).order("datum").execute()),
        asyncio.to_thread(lambda: supa.table("billing_entries").select(
            "iznos,obracunato"
        ).eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select(
            "dogadjaj,akter,datum,vaznost"
        ).eq("predmet_id", predmet_id).order("datum_iso", desc=True).limit(8).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_klijenti").select(
            "uloga,klijenti(ime,prezime,firma)"
        ).eq("predmet_id", predmet_id).limit(4).execute()),
        return_exceptions=True,
    )

    # ── Dokazi statistika ────────────────────────────────────────────────────
    dokazi = (dokazi_r.data if not isinstance(dokazi_r, Exception) else []) or []
    dok_stats = {"jaka": 0, "srednja": 0, "slaba": 0, "ukupno": len(dokazi)}
    for d in dokazi:
        s = d.get("snaga", "srednja")
        if s in dok_stats:
            dok_stats[s] += 1

    # ── Dokumenti broji ─────────────────────────────────────────────────────
    tip_stat: dict = {}
    for d in ((dok_count_r.data if not isinstance(dok_count_r, Exception) else []) or []):
        t = d.get("tip_dokaza") or "neklasifikovan"
        tip_stat[t] = tip_stat.get(t, 0) + 1

    # ── Rokovi (sledeći 30 dana) ─────────────────────────────────────────────
    # Operation One Truth (2026-08-07): this per-row loop used to also compute
    # `predstojeći`'s aggregate count by comparing a naive datetime (from a plain
    # "YYYY-MM-DD" via +"T00:00:00") against timezone-AWARE `now` -- Python raises
    # TypeError on that subtraction, silently swallowed by the bare except, so
    # `dana` stayed None and `predstojeći` stayed 0 for every hearing stored as a
    # plain date (the realistic Postgres DATE shape). The correct aggregate is
    # already computed a few lines below via the canonical calculate_procesni_rizik
    # (services/risk_engine.py, itself fixed for this exact bug by Project Synapse)
    # -- this loop now ONLY builds per-row "dana_ostalo" for display, using the
    # same calendar-date-diff fix, and no longer re-derives the aggregate count or
    # picks the critical hearing independently; both come from the canonical
    # engine's output below.
    now = datetime.now(timezone.utc)
    rokovi_data = []
    for r in ((rok_r.data if not isinstance(rok_r, Exception) else []) or []):
        dana = None
        try:
            ds = r.get("datum", "") or ""
            if ds:
                dana = (datetime.fromisoformat(ds).date() - now.date()).days if len(ds) == 10 \
                    else (datetime.fromisoformat(ds.replace("Z", "+00:00")).date() - now.date()).days
        except Exception:
            pass
        rokovi_data.append({**r, "dana_ostalo": dana})

    # ── Billing summary ──────────────────────────────────────────────────────
    billing_data = {"uneseno": 0, "nenaplaceno": 0, "naplaceno": 0}
    try:
        for e in ((be_r.data if not isinstance(be_r, Exception) else []) or []):
            iznos = float(e.get("iznos") or 0)
            billing_data["uneseno"] += iznos
            if e.get("obracunato"):
                billing_data["naplaceno"] += iznos
            else:
                billing_data["nenaplaceno"] += iznos
    except Exception as exc:
        logger.debug("[CCC] billing greška: %s", exc)

    # ── Klijenti ─────────────────────────────────────────────────────────────
    klijenti = []
    try:
        for k in ((kl_r.data if not isinstance(kl_r, Exception) else []) or []):
            ki = k.get("klijenti") or {}
            klijenti.append({
                "uloga": k.get("uloga", ""),
                "ime": ((ki.get("ime","") + " " + ki.get("prezime","")).strip()
                        or ki.get("firma","Klijent"))
            })
    except Exception as exc:
        logger.debug("[CCC] klijenti greška: %s", exc)

    # ── Nedostajući dokumenti + health_score ─────────────────────────────────
    # Project Nexus (2026-08-03): ovaj blok je ranije RUČNO računao i
    # "nedostajuci" (bez ikad selektovanog tip_dokaza -- gore sad ispravljeno
    # -- pa je "nedostajuci" UVEK bio kompletna expected lista, bez obzira šta
    # je stvarno otpremljeno) i sopstvenu kopiju health_score formule
    # (_compute_health, ispod, uklonjena) koja je hardkodovala nedostajuci_count=0
    # i imala svoj, nezavisno pokvaren naivni/svesni datetime bag (isti oblik
    # kao bag ispravljen u services/risk_engine.py par misija ranije). Sad
    # poziva ISTU deterministicku funkciju koju koristi Matter Intelligence
    # (services/risk_engine.py::calculate_procesni_rizik) -- jedan izvor
    # istine za "health_score"/"nedostajući dokazi" umesto dva koja mogu dati
    # različit odgovor za isti predmet pod istim imenom polja.
    _dok_count_data = (dok_count_r.data if not isinstance(dok_count_r, Exception) else []) or []
    _rok_raw = (rok_r.data if not isinstance(rok_r, Exception) else []) or []
    _rizik = calculate_procesni_rizik(
        dokazi=dokazi, dokumenti=_dok_count_data, rocista=_rok_raw,
        tip_predmeta=predmet.get("tip", "ostalo"), expected_docs=_EXPECTED_DOCS,
    )
    nedostajuci = _rizik["nedostajuci_dokazi"]
    health_score = _rizik["health_score"]

    # Operation One Truth (2026-08-07): both values below used to be re-derived by this
    # module's own (buggy) loop above. Now sourced directly from the canonical engine's
    # already-computed output -- `predstojeći` is the same count Matter Intel/Cockpit show
    # for this case, and `kritican_rok` is picked from the canonical `kriticni_rocista` list
    # (which, per BLACKSWAN-CRIT-002, correctly includes overdue hearings as MORE urgent,
    # not excluded) rather than a second, narrower 0<=dana<=7-only window.
    predstojeći = _rizik["predstojeći_rokovi"]
    kritican_rok = None
    _kriticni_ids = {r.get("id") for r in _rizik.get("kriticni_rocista") or [] if r.get("id")}
    if _kriticni_ids:
        _kriticni_rows = [r for r in rokovi_data if r.get("id") in _kriticni_ids]
        if _kriticni_rows:
            kritican_rok = sorted(_kriticni_rows, key=lambda x: x.get("dana_ostalo") if x.get("dana_ostalo") is not None else 9999)[0]

    return {
        "predmet":          predmet,
        "klijenti":         klijenti,
        "dok_stats":        dok_stats,
        "tip_stat":         tip_stat,
        "rokovi":           rokovi_data,
        "predstojeći":      predstojeći,
        "billing":          billing_data,
        "aktivnosti":       (hron_r.data if not isinstance(hron_r, Exception) else []) or [],
        "health_score":     health_score,
        "nedostajuci":      nedostajuci,
        "kritican_rok":     kritican_rok,
    }
