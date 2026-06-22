# -*- coding: utf-8 -*-
"""
Matter Intelligence Dashboard — AI ocena zdravlja predmeta.

GET /api/matter-intel/predmeti/{predmet_id}
Vraća: snaga_dokaza, procesni_rizik, nedostajuci_dokazi, predstojeći_rokovi,
       sledeca_radnja (GPT-4o-mini), health_score (0-100)
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from shared.deps import _get_supa, get_current_user
from shared.constants import EXPECTED_DOCS as _EXPECTED_DOCS

logger = logging.getLogger("vindex.matter_intel")
router = APIRouter(prefix="/api/matter-intel", tags=["matter_intel"])

_INTEL_SYSTEM = """Ti si pravni asistent koji analizira stanje predmeta.

Na osnovu datih podataka, u 2 rečenice formuliši KONKRETNU SLEDEĆU RADNJU advokata.
Budi direktan i specifičan. Srpski jezik. Bez uvoda.

Format:
SLEDEĆA RADNJA: [konkretna akcija]
RAZLOG: [kratko objašnjenje zašto]"""


@router.get("/predmeti/{predmet_id}")
async def get_matter_intel(predmet_id: str, user=Depends(get_current_user)):
    supa = _get_supa()
    uid  = user["user_id"]

    pr = supa.table("predmeti").select(
        "id,naziv,tip,status,rizik,opis,created_at"
    ).eq("id", predmet_id).eq("user_id", uid).execute()
    if not pr.data:
        raise HTTPException(status_code=404)
    predmet = pr.data[0]
    tip     = predmet.get("tip") or "ostalo"

    # ── Dokazi analiza ───────────────────────────────────────────────────────
    dokazi_r = supa.table("predmet_dokazi").select(
        "snaga,kategorija,pravni_element"
    ).eq("predmet_id", predmet_id).is_("deleted_at", "null").execute()
    dokazi = dokazi_r.data or []

    snaga_count = {"jaka": 0, "srednja": 0, "slaba": 0}
    for d in dokazi:
        s = d.get("snaga","srednja")
        if s in snaga_count:
            snaga_count[s] += 1
    ukupno = sum(snaga_count.values())

    if ukupno == 0:
        snaga_label = "Nema dokaza"
        snaga_pct   = 0
    else:
        jaka_pct  = snaga_count["jaka"] / ukupno
        sred_pct  = snaga_count["srednja"] / ukupno
        if jaka_pct >= 0.5:
            snaga_label = "Jaka"
            snaga_pct   = int(jaka_pct * 100)
        elif jaka_pct + sred_pct >= 0.6:
            snaga_label = "Srednja"
            snaga_pct   = int((jaka_pct + sred_pct) * 100)
        else:
            snaga_label = "Slaba"
            snaga_pct   = max(10, int(jaka_pct * 100))

    # ── Nedostajući dokumenti ────────────────────────────────────────────────
    expected = _EXPECTED_DOCS.get(tip, _EXPECTED_DOCS["ostalo"])
    dok_r = supa.table("predmet_dokumenti").select("tip_dokaza").eq(
        "predmet_id", predmet_id).is_("deleted_at", "null").execute()
    postojeci_tipovi = {d.get("tip_dokaza") for d in (dok_r.data or []) if d.get("tip_dokaza")}
    nedostajuci = [t for t in expected if t not in postojeci_tipovi]

    # ── Rokovi ──────────────────────────────────────────────────────────────
    rok_r = supa.table("predmet_rokovi").select(
        "naziv,datum_isteka,status"
    ).eq("predmet_id", predmet_id).order("datum_isteka").execute()
    now = datetime.now(timezone.utc)
    predstojeći = 0
    kriticni    = 0
    for r in (rok_r.data or []):
        try:
            dt = datetime.fromisoformat((r.get("datum_isteka","") or "").replace("Z","+00:00"))
            dana = (dt - now).days
            if 0 <= dana <= 30:
                predstojeći += 1
            if 0 <= dana <= 7:
                kriticni += 1
        except Exception:
            pass

    # ── Procesni rizik ───────────────────────────────────────────────────────
    rizik_score = 50
    if ukupno == 0:              rizik_score += 20
    elif snaga_label == "Jaka":  rizik_score -= 20
    elif snaga_label == "Slaba": rizik_score += 15
    if len(nedostajuci) >= 3:    rizik_score += 15
    if kriticni > 0:             rizik_score += 20

    if rizik_score <= 35:
        procesni_rizik = "Nizak"
        rizik_boja     = "green"
    elif rizik_score <= 60:
        procesni_rizik = "Srednji"
        rizik_boja     = "orange"
    else:
        procesni_rizik = "Visok"
        rizik_boja     = "red"

    # ── Health score ─────────────────────────────────────────────────────────
    health = 100 - rizik_score
    health = max(5, min(95, health))

    # ── Sledeća radnja (GPT) ─────────────────────────────────────────────────
    sledeca_radnja = _compute_next_action(predmet, snaga_label, nedostajuci, predstojeći, kriticni)

    # ── Trend aktivnosti (poslednjih 3×7 dana) ───────────────────────────────
    trend = _compute_trend(supa, predmet_id, now)

    # ── Health log: snimi dnevni snapshot i vrati istoriju ───────────────────
    health_history = _log_and_fetch_health(supa, predmet_id, health, procesni_rizik, now)

    return {
        "snaga_dokaza":     snaga_label,
        "snaga_pct":        snaga_pct,
        "snaga_detalji":    snaga_count,
        "procesni_rizik":   procesni_rizik,
        "rizik_boja":       rizik_boja,
        "nedostajuci_dokazi": nedostajuci,
        "nedostajuci_count":  len(nedostajuci),
        "predstojeći_rokovi": predstojeći,
        "kriticni_rokovi":    kriticni,
        "health_score":       health,
        "sledeca_radnja":     sledeca_radnja,
        "trend":              trend,
        "health_history":     health_history,
    }


def _log_and_fetch_health(supa, predmet_id: str, health: int, rizik_label: str, now: datetime) -> list:
    """
    Snimi dnevni health_score snapshot i vrati poslednjih 30 dana.
    Gracefully ignoriše greške (tabela možda ne postoji pre migracije 026).
    Vraća: [{"date": "YYYY-MM-DD", "score": int}, ...] ili []
    """
    try:
        today = now.date().isoformat()
        today_start = f"{today}T00:00:00+00:00"
        tomorrow    = f"{now.date().isoformat()}T23:59:59+00:00"

        # Upiši samo jednom dnevno (idempotentno)
        existing = supa.table("predmet_health_log").select("id") \
            .eq("predmet_id", predmet_id) \
            .gte("logged_at", today_start) \
            .lte("logged_at", tomorrow) \
            .limit(1).execute()

        if not existing.data:
            supa.table("predmet_health_log").insert({
                "predmet_id": predmet_id,
                "health_score": health,
                "rizik_label": rizik_label,
            }).execute()
    except Exception:
        pass  # tabela još ne postoji — migracija 026 nije primenjena

    try:
        from datetime import timedelta
        since = (now - timedelta(days=30)).isoformat()
        rows = supa.table("predmet_health_log").select("health_score,logged_at") \
            .eq("predmet_id", predmet_id) \
            .gte("logged_at", since) \
            .order("logged_at") \
            .execute()

        # Grupiši po danu — uzmi poslednji zapis po danu
        daily: dict[str, int] = {}
        for row in (rows.data or []):
            d = (row.get("logged_at","") or "")[:10]
            if d:
                daily[d] = row["health_score"]

        return [{"date": d, "score": s} for d, s in sorted(daily.items())]
    except Exception:
        return []


def _compute_trend(supa, predmet_id: str, now: datetime) -> str:
    """Trend aktivnosti: poredi broj Q&A unosa u 3 uzastopna perioda od 7 dana."""
    try:
        from datetime import timedelta
        p1_start = (now - timedelta(days=7)).isoformat()
        p2_start = (now - timedelta(days=14)).isoformat()
        p3_start = (now - timedelta(days=21)).isoformat()

        def _count(after: str, before: str) -> int:
            r = supa.table("predmet_istorija").select("id", count="exact") \
                .eq("predmet_id", predmet_id) \
                .gte("created_at", after).lt("created_at", before).execute()
            return r.count or 0

        c1 = _count(p1_start, now.isoformat())   # najnoviji period
        c2 = _count(p2_start, p1_start)
        c3 = _count(p3_start, p2_start)

        if c1 == 0 and c2 == 0 and c3 == 0:
            return None
        if c1 > c2:
            return "raste"
        if c1 < c2:
            return "opada"
        return "stagnira"
    except Exception:
        return None


def _compute_next_action(predmet: dict, snaga: str, nedostajuci: list, predstojeći: int, kriticni: int) -> str:
    """GPT-4o-mini formuliše sledeću konkretnu radnju."""
    _TIPOVI_SR = {
        "parnicno":"parničnom","krivicno":"krivičnom","radno":"radnom",
        "upravno":"upravnom","porodicno":"porodičnom","privredno":"privrednom",
        "nepokretnosti":"predmetu nepokretnosti","ostalo":"predmetu",
    }
    tip_sr = _TIPOVI_SR.get(predmet.get("tip","ostalo"), "predmetu")

    # Brza rule-based preporuka (bez GPT troškova za svaki otvoreni predmet)
    if kriticni > 0:
        return f"SLEDEĆA RADNJA: Hitno pregledati {kriticni} kritičan rok(a) u narednih 7 dana.\nRAZLOG: Propuštanje procesnog roka je nepopravljiva šteta."
    if snaga == "Nema dokaza":
        return f"SLEDEĆA RADNJA: Prikupiti i uploadovati početne dokaze za {tip_sr} predmet.\nRAZLOG: Bez ikakvih dokaza nije moguće izgraditi strategiju odbrane."
    if nedostajuci:
        _LABELS = {
            "sudska_odluka":"sudsku odluku/presudu", "podnesak":"podnesak stranke",
            "ugovor":"relevantni ugovor", "dopis":"pisanu komunikaciju",
            "medicinska_dokumentacija":"medicinski nalaz", "finansijska_dokumentacija":"finansijsku dokumentaciju",
            "javna_isprava":"javnu ispravu", "vestacki_nalaz":"nalaz veštaka",
        }
        prvi = _LABELS.get(nedostajuci[0], nedostajuci[0])
        return f"SLEDEĆA RADNJA: Pribaviti {prvi} koji nedostaje u spisu.\nRAZLOG: Ovaj dokument je tipično ključan za {tip_sr} predmet."
    if predstojeći >= 3:
        return f"SLEDEĆA RADNJA: Napraviti plan za {predstojeći} predstojeća roka — prioritizovati po hitnosti.\nRAZLOG: Više paralelnih rokova povećava rizik od propuštanja."
    if snaga == "Slaba":
        return "SLEDEĆA RADNJA: Razmotriti mogućnost nalaza veštaka ili pribavljanja dodatnih svedoka.\nRAZLOG: Trenutni dokazi su slabe snage i ne pružaju dovoljnu osnovu za tužbu."
    return "SLEDEĆA RADNJA: Pokrenuti AI strategijsku analizu predmeta (Strategija tab).\nRAZLOG: Predmet ima solidnu osnovu — vreme je za konkretnu pravnu strategiju."
