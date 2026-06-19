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

logger = logging.getLogger("vindex.matter_intel")
router = APIRouter(prefix="/api/matter-intel", tags=["matter_intel"])

# Očekivani tipovi dokaza po tipu spora
_EXPECTED_DOCS: dict = {
    "parnicno":     ["sudska_odluka", "podnesak", "ugovor", "dopis"],
    "krivicno":     ["sudska_odluka", "podnesak", "medicinska_dokumentacija", "vestacki_nalaz"],
    "radno":        ["ugovor", "dopis", "finansijska_dokumentacija", "sudska_odluka"],
    "upravno":      ["javna_isprava", "podnesak", "dopis", "sudska_odluka"],
    "porodicno":    ["javna_isprava", "medicinska_dokumentacija", "finansijska_dokumentacija", "sudska_odluka"],
    "nasledjivanje":["javna_isprava", "ugovor", "sudska_odluka", "dopis"],
    "privredno":    ["ugovor", "finansijska_dokumentacija", "dopis", "sudska_odluka"],
    "nepokretnosti":["javna_isprava", "ugovor", "sudska_odluka", "dopis"],
    "ostalo":       ["podnesak", "dopis"],
}

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
    }


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
