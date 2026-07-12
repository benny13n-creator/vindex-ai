# -*- coding: utf-8 -*-
"""
Vindex AI — Outcome Feedback Engine + Collective Intelligence

Kada se predmet zatvori, sistem pita advokata:
- Kako se završilo?
- Šta je bilo presudno?

Na osnovu toga:
1. Trenira se model za buduće preporuke (case_patterns)
2. Gradi se Collective Intelligence (firmina istorija)
3. Confidence Calibration postaje tačnija
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.learning")
router = APIRouter(prefix="/api/learning", tags=["learning"])

# ─── Konstante ────────────────────────────────────────────────────────────────

_VALIDNI_ISHODI = {"pobeda", "poraz", "nagodba", "odustajanje"}

_FAKTORI_LABELS = {
    "vestacenje":          "Veštačenje",
    "svedoci":             "Svedoci",
    "zastarelost":         "Zastarelost potražnja",
    "procesna_greska":     "Procesna greška protivnika",
    "novi_dokaz":          "Novi dokaz",
    "nagodba_sporazum":    "Sporazum o nagodbi",
    "sudska_praksa":       "Sudska praksa",
    "pisana_komunikacija": "Pisana komunikacija",
    "finansijska_dok":     "Finansijska dokumentacija",
}

# ─── Pydantic modeli ──────────────────────────────────────────────────────────

class OutcomeRequest(BaseModel):
    predmet_id: str
    ishod: str = Field(..., description="pobeda | poraz | nagodba | odustajanje")
    presudni_faktori: List[str] = Field(default_factory=list)
    trajanje_meseci: Optional[int] = None
    vrednost_spora_rsd: Optional[float] = None
    komentar: Optional[str] = None
    uzroci: List[str] = Field(default_factory=list, description="ZASTO je predmet izgubljen/dobijen")
    kontekst_poraza: Optional[str] = Field(None, description="Slobodan opis konteksta poraza")
    generisi_lekcije: bool = Field(False, description="Automatski generisi Lessons Learned")


class CounterfactualRequest(BaseModel):
    predmet_id: str
    hipoteza: str = Field(..., description="Sto-ako hipoteza, npr. 'Da smo prihvatili nagodbu od 50k RSD'")
    tip_hipoteze: str = Field("ostalo", description="nagodba | strateski | takticki | procesni | ostalo")
    odgovor: Optional[str] = None
    komentar: Optional[str] = None


class RecommendationFeedbackRequest(BaseModel):
    recommendation_id: str
    prihvacena: bool


class LessonConfirmationRequest(BaseModel):
    akcija: str = Field(..., description="potvrdi | odbaci")
    komentar: Optional[str] = None
    oblast_prava: Optional[str] = Field(None, description="poresko | radno | procesno | obligaciono | ustavno")


# ─── Interni helperi ──────────────────────────────────────────────────────────

def _safe(r) -> list:
    if isinstance(r, Exception):
        return []
    return getattr(r, "data", None) or []


def _safe_one(r) -> dict:
    if isinstance(r, Exception):
        return {}
    d = getattr(r, "data", None)
    if isinstance(d, list):
        return d[0] if d else {}
    return d or {}


async def _dohvati_predmet(supa, predmet_id: str, uid: str) -> dict:
    r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id,naziv,tip,opis,status")
            .eq("id", predmet_id)
            .eq("user_id", uid)
            .limit(1)
            .execute()
    )
    rows = _safe(r)
    if not rows:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")
    return rows[0]


# ─── ENDPOINT 1: Zabeleži ishod predmeta ──────────────────────────────────────

@router.post("/outcome")
@limiter.limit("10/minute")
async def zabeleži_ishod(
    req: OutcomeRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Kada se predmet zatvori — advokat beleži ishod i presudne faktore.
    Sistem uči i gradi Collective Intelligence kancelarije.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    if req.ishod not in _VALIDNI_ISHODI:
        raise HTTPException(status_code=422, detail=f"Ishod mora biti: {', '.join(_VALIDNI_ISHODI)}")

    predmet = await _dohvati_predmet(supa, req.predmet_id, uid)
    tip_spora = predmet.get("tip", "ostalo")

    faktori_azurirani = 0
    preporuke_azurirane = 0

    # 1. Upsert outcome_log (uključuje root cause analizu)
    try:
        await asyncio.to_thread(
            lambda: supa.table("outcome_log").upsert({
                "predmet_id":        req.predmet_id,
                "user_id":           uid,
                "ishod":             req.ishod,
                "presudni_faktori":  req.presudni_faktori,
                "trajanje_meseci":   req.trajanje_meseci,
                "vrednost_spora_rsd": req.vrednost_spora_rsd,
                "komentar":          (req.komentar or "")[:2000],
                "tip_spora":         tip_spora,
                "uzroci":            req.uzroci[:10],
                "kontekst_poraza":   (req.kontekst_poraza or "")[:3000],
            }, on_conflict="predmet_id").execute()
        )
    except Exception as e:
        logger.warning("[LEARNING] outcome_log upsert greška (tabela možda ne postoji): %s", e)

    # 2. Update case_patterns za svaki faktor
    je_pobeda = req.ishod == "pobeda"
    je_poraz  = req.ishod == "poraz"
    for faktor in req.presudni_faktori[:10]:
        try:
            existing = await asyncio.to_thread(
                lambda f=faktor: supa.table("case_patterns")
                    .select("id,pobede,porazi")
                    .eq("user_id", uid)
                    .eq("tip_spora", tip_spora)
                    .eq("faktor", f)
                    .limit(1)
                    .execute()
            )
            rows = _safe(existing)
            if rows:
                row = rows[0]
                await asyncio.to_thread(
                    lambda r=row, f=faktor: supa.table("case_patterns").update({
                        "pobede": r["pobede"] + (1 if je_pobeda else 0),
                        "porazi": r["porazi"] + (1 if je_poraz  else 0),
                        "ukupno": r.get("ukupno", r["pobede"] + r["porazi"]) + 1,
                    }).eq("id", r["id"]).execute()
                )
            else:
                await asyncio.to_thread(
                    lambda f=faktor: supa.table("case_patterns").insert({
                        "user_id":   uid,
                        "tip_spora": tip_spora,
                        "faktor":    f,
                        "pobede":    1 if je_pobeda else 0,
                        "porazi":    1 if je_poraz  else 0,
                        "ukupno":    1,
                    }).execute()
                )
            faktori_azurirani += 1
        except Exception as e:
            logger.warning("[LEARNING] case_patterns greška za faktor %s: %s", faktor, e)

    # 3. Ažuriraj recommendation_log za ovaj predmet
    if req.ishod in ("pobeda", "poraz"):
        ishod_poz = req.ishod == "pobeda"
        try:
            rec_r = await asyncio.to_thread(
                lambda: supa.table("recommendation_log")
                    .select("id")
                    .eq("predmet_id", req.predmet_id)
                    .eq("user_id", uid)
                    .execute()
            )
            recs = _safe(rec_r)
            for rec in recs:
                try:
                    await asyncio.to_thread(
                        lambda rid=rec["id"]: supa.table("recommendation_log")
                            .update({"ishod_pozitivan": ishod_poz})
                            .eq("id", rid)
                            .execute()
                    )
                    preporuke_azurirane += 1
                except Exception:
                    pass
        except Exception as e:
            logger.warning("[LEARNING] recommendation_log update greška: %s", e)

    # 4. Ažuriraj status predmeta — uvek "zatvoren" (isti vokabular kao
    # /api/predmeti/{id}/zatvori); pobeda/poraz se čuvaju u outcome_log/
    # ishod polju, ne u statusu — status "zatvoren_uspesno"/"zatvoren_neuspesno"
    # bi tiho slomio svako filtriranje po statusu u ostatku aplikacije
    # (kanban, liste, pred_load) koje očekuje tačno "zatvoren".
    novi_status = "zatvoren"
    try:
        await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .update({"status": novi_status})
                .eq("id", req.predmet_id)
                .eq("user_id", uid)
                .execute()
        )
    except Exception as e:
        logger.warning("[LEARNING] predmet status update greška: %s", e)

    if req.ishod == "pobeda":
        poruka = "Čestitamo! Iskustvo sa ovim predmetom sada pomaže budućim analizama."
    elif req.ishod == "poraz":
        poruka = "Zabeležili smo ishod. Svaki predmet — čak i poraz — uči sistem da bude bolji."
    else:
        poruka = "Ishod zabeležen. Iskustvo sa ovim predmetom doprinosi Vindex Intelligence bazi."

    # Opciono: automatski generisi Lessons Learned u pozadini
    lekcije_generisane = 0
    if req.generisi_lekcije:
        try:
            from services.learning_engine import learning
            lekcije = await learning.generate_lessons_learned(
                user_id=uid,
                predmet_id=req.predmet_id,
                ishod=req.ishod,
                presudni_faktori=req.presudni_faktori,
                komentar=req.komentar,
                tip_spora=tip_spora,
                uzroci=req.uzroci or [],
                kontekst_poraza=req.kontekst_poraza,
            )
            lekcije_generisane = await learning.save_lessons(uid, req.predmet_id, lekcije, tip_spora)
        except Exception as e:
            logger.warning("[LEARNING] auto lessons greška: %s", e)

    return {
        "ok":                   True,
        "ishod":                req.ishod,
        "faktori_azurirani":    faktori_azurirani,
        "preporuke_azurirane":  preporuke_azurirane,
        "novi_status":          novi_status,
        "lekcije_generisane":   lekcije_generisane,
        "poruka":               poruka,
    }


# ─── ENDPOINT 2: Pitanja za feedback ──────────────────────────────────────────

@router.get("/feedback-questions/{predmet_id}")
@limiter.limit("30/minute")
async def get_feedback_questions(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vraća pitanja koja treba prikazati korisniku kada zatvori predmet."""
    uid  = user["user_id"]
    supa = _get_supa()

    predmet = await _dohvati_predmet(supa, predmet_id, uid)

    # Prethodni outcome ako postoji
    prethodni = None
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("outcome_log")
                .select("ishod,presudni_faktori,trajanje_meseci,komentar")
                .eq("predmet_id", predmet_id)
                .limit(1)
                .execute()
        )
        rows = _safe(r)
        if rows:
            prethodni = rows[0]
    except Exception:
        pass

    return {
        "predmet_id":       predmet_id,
        "predmet_naziv":    predmet.get("naziv", ""),
        "pitanja": [
            {
                "id":    "ishod",
                "tekst": "Kako se predmet završio?",
                "tip":   "single_choice",
                "opcije": ["Pobeda", "Poraz", "Nagodba", "Odustajanje"],
                "vrednosti": ["pobeda", "poraz", "nagodba", "odustajanje"],
            },
            {
                "id":    "presudni_faktori",
                "tekst": "Šta je bilo presudno za ishod? (može više odgovora)",
                "tip":   "multi_choice",
                "opcije": list(_FAKTORI_LABELS.values()),
                "vrednosti": list(_FAKTORI_LABELS.keys()),
            },
            {
                "id":       "trajanje",
                "tekst":    "Koliko je trajao predmet (meseci)?",
                "tip":      "number",
                "obavezno": False,
            },
            {
                "id":       "komentar",
                "tekst":    "Šta biste napravili drugačije?",
                "tip":      "text",
                "obavezno": False,
                "placeholder": "Slobodan komentar — pomaže Vindex Intelligence bazi...",
            },
        ],
        "prethodni_outcome": prethodni,
    }


# ─── ENDPOINT 3: Feedback na konkretnu preporuku ──────────────────────────────

@router.post("/recommendation-feedback")
@limiter.limit("30/minute")
async def recommendation_feedback(
    req: RecommendationFeedbackRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Advokat prihvata ili odbija konkretnu AI preporuku. Sistem uči."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        await asyncio.to_thread(
            lambda: supa.table("recommendation_log")
                .update({"prihvacena": req.prihvacena})
                .eq("id", req.recommendation_id)
                .eq("user_id", uid)
                .execute()
        )
    except Exception as e:
        logger.warning("[LEARNING] recommendation feedback greška: %s", e)

    return {
        "ok":      True,
        "message": "Hvala na povratnoj informaciji. Sistem uči.",
        "prihvacena": req.prihvacena,
    }


# ─── ENDPOINT 4: Slični predmeti (Collective Intelligence) ────────────────────

@router.get("/slicni-predmeti/{predmet_id}")
@limiter.limit("10/minute")
async def slicni_predmeti(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Collective Intelligence — nađi slične zatvorene predmete iz firmine istorije.
    Na osnovu iskustva kancelarije preporučuje strategiju.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    predmet = await _dohvati_predmet(supa, predmet_id, uid)

    # Dohvati zatvorene predmete sa outcome
    try:
        zatvoreni_r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id,naziv,tip,opis,status")
                .eq("user_id", uid)
                .neq("id", predmet_id)
                .like("status", "zatvoren%")
                .limit(50)
                .execute()
        )
        zatvoreni = _safe(zatvoreni_r)
    except Exception as e:
        logger.warning("[LEARNING] zatvoreni predmeti greška: %s", e)
        return {"slicni_predmeti": [], "ukupno_slicnih": 0, "strategija_preporuka": ""}

    if not zatvoreni:
        return {"slicni_predmeti": [], "ukupno_slicnih": 0, "strategija_preporuka": ""}

    # Dohvati outcome_log za zatvorene predmete
    zids = [p["id"] for p in zatvoreni[:30]]
    try:
        outcomes_r = await asyncio.to_thread(
            lambda: supa.table("outcome_log")
                .select("predmet_id,ishod,presudni_faktori,trajanje_meseci,komentar")
                .in_("predmet_id", zids)
                .execute()
        )
        outcomes_map = {o["predmet_id"]: o for o in _safe(outcomes_r)}
    except Exception:
        outcomes_map = {}

    # Samo predmeti sa poznatim ishodom
    sa_ishodom = [p for p in zatvoreni if p["id"] in outcomes_map]
    if not sa_ishodom:
        return {"slicni_predmeti": [], "ukupno_slicnih": 0, "strategija_preporuka": ""}

    # GPT-4o-mini rangira sličnost
    lista_txt = "\n".join(
        f'[{i+1}] predmet_id={p["id"][:8]} naziv="{p.get("naziv","")[:60]}" '
        f'tip={p.get("tip","?")}'
        for i, p in enumerate(sa_ishodom[:20])
    )

    prompt = (
        f'Tekući predmet:\n'
        f'naziv="{predmet.get("naziv","")[:100]}" tip={predmet.get("tip","?")} '
        f'opis="{(predmet.get("opis") or "")[:300]}"\n\n'
        f'Zatvoreni predmeti kancelarije:\n{lista_txt}\n\n'
        f'Rangira top 5 najsličnijih. Vrati SAMO JSON niz:\n'
        f'[{{"predmet_id_prefix":"prva 8 slova","slicnost":85,"razlog":"..."}}]\n'
        f'Ekavica. Budi konkretan o razlogu sličnosti.'
    )

    rangirani = []
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = await asyncio.to_thread(
            lambda: oai.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.1,
                max_tokens=600,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Vraćaš SAMO JSON objekat sa ključem 'rezultati' koji sadrži niz. Ekavica."},
                    {"role": "user",   "content": prompt},
                ],
            )
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        rangirani = raw.get("rezultati") or raw.get("slicni") or []
        if isinstance(rangirani, dict):
            rangirani = list(rangirani.values())
    except Exception as e:
        logger.warning("[LEARNING] GPT sličnost greška: %s", e)
        # Fallback: vrati prvih 5 istog tipa
        rangirani = [
            {"predmet_id_prefix": p["id"][:8], "slicnost": 60, "razlog": "Isti tip spora"}
            for p in sa_ishodom[:5]
            if p.get("tip") == predmet.get("tip")
        ]

    # Enrich sa outcome podacima
    predmet_by_prefix = {p["id"][:8]: p for p in sa_ishodom}
    result = []
    for r in rangirani[:5]:
        prefix = r.get("predmet_id_prefix", "")[:8]
        p = predmet_by_prefix.get(prefix)
        if not p:
            continue
        outcome = outcomes_map.get(p["id"], {})
        result.append({
            "predmet_id":         p["id"],
            "naziv":              p.get("naziv", ""),
            "tip":                p.get("tip", ""),
            "ishod":              outcome.get("ishod", "nepoznato"),
            "trajanje_meseci":    outcome.get("trajanje_meseci"),
            "presudni_faktori":   outcome.get("presudni_faktori", []),
            "komentar":           outcome.get("komentar", ""),
            "slicnost":           r.get("slicnost", 0),
            "razlog":             r.get("razlog", ""),
        })

    # Strategijska preporuka
    strategija = ""
    if result:
        pobede = [x for x in result if x["ishod"] == "pobeda"]
        win_r  = round(len(pobede) / len(result) * 100) if result else 0
        top_faktori: dict[str, int] = {}
        for p in pobede:
            for f in (p.get("presudni_faktori") or []):
                top_faktori[f] = top_faktori.get(f, 0) + 1
        top = sorted(top_faktori.items(), key=lambda x: x[1], reverse=True)[:2]
        top_names = [_FAKTORI_LABELS.get(f, f) for f, _ in top]
        strategija = (
            f"Na osnovu {len(result)} sličnih predmeta (win rate {win_r}%)"
            + (f", {top_names[0]} je bio presudni faktor u pobedama." if top_names else ".")
        )

    return {
        "slicni_predmeti":     result,
        "ukupno_slicnih":      len(result),
        "strategija_preporuka": strategija,
    }


# ─── ENDPOINT 5: Performance Report (firmina statistika učenja) ───────────────

@router.get("/performance-report")
@limiter.limit("5/minute")
async def performance_report(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Firmina statistika učenja — win rate po tipu spora, top faktori uspeha,
    AI uvid iz istorije kancelarije.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Dohvati sve outcome_log za korisnika
    try:
        outcomes_r = await asyncio.to_thread(
            lambda: supa.table("outcome_log")
                .select("predmet_id,ishod,tip_spora,presudni_faktori,trajanje_meseci")
                .eq("user_id", uid)
                .order("created_at", desc=True)
                .limit(500)
                .execute()
        )
        outcomes = _safe(outcomes_r)
    except Exception as e:
        logger.warning("[LEARNING] outcome_log read greška: %s", e)
        outcomes = []

    # Dohvati case_patterns
    try:
        patterns_r = await asyncio.to_thread(
            lambda: supa.table("case_patterns")
                .select("tip_spora,faktor,pobede,porazi,ukupno")
                .eq("user_id", uid)
                .order("pobede", desc=True)
                .limit(100)
                .execute()
        )
        patterns = _safe(patterns_r)
    except Exception:
        patterns = []

    # Agregiraj po tipu spora
    po_tipu: dict[str, dict] = {}
    faktori_uspeha: dict[str, list] = {}

    for o in outcomes:
        tip = o.get("tip_spora") or "ostalo"
        if tip not in po_tipu:
            po_tipu[tip] = {"pobede": 0, "porazi": 0, "nagodbe": 0, "ostalo": 0, "ukupno": 0}
        po_tipu[tip]["ukupno"] += 1
        ishod = o.get("ishod", "")
        if ishod == "pobeda":      po_tipu[tip]["pobede"]  += 1
        elif ishod == "poraz":     po_tipu[tip]["porazi"]  += 1
        elif ishod == "nagodba":   po_tipu[tip]["nagodbe"] += 1
        else:                      po_tipu[tip]["ostalo"]  += 1

    po_tipu_lista = []
    for tip, st in po_tipu.items():
        wr = round(st["pobede"] / st["ukupno"] * 100, 1) if st["ukupno"] else 0
        # Top faktor uspeha/poraza iz patterns
        tp_faktori = [p for p in patterns if p.get("tip_spora") == tip]
        top_uspeh = sorted(tp_faktori, key=lambda x: x.get("pobede", 0), reverse=True)
        top_poraz  = sorted(tp_faktori, key=lambda x: x.get("porazi", 0), reverse=True)
        po_tipu_lista.append({
            "tip":               tip,
            "ukupno":            st["ukupno"],
            "pobede":            st["pobede"],
            "porazi":            st["porazi"],
            "nagodbe":           st["nagodbe"],
            "win_rate":          wr,
            "top_faktor_uspeha": top_uspeh[0]["faktor"] if top_uspeh else None,
            "top_faktor_poraza": top_poraz[0]["faktor"] if top_poraz else None,
        })

    # Top faktori uspeha globalno
    top_faktori_uspeha = sorted(
        [
            {
                "faktor":       p["faktor"],
                "uspeh_stopa":  round(p["pobede"] / p["ukupno"] * 100, 1) if p.get("ukupno") else 0,
                "uzoraka":      p.get("ukupno", 0),
                "label":        _FAKTORI_LABELS.get(p["faktor"], p["faktor"]),
            }
            for p in patterns if p.get("ukupno", 0) >= 2
        ],
        key=lambda x: x["uspeh_stopa"],
        reverse=True,
    )[:8]

    # AI uvid
    ai_uvid = ""
    preporuke = []
    if outcomes:
        ukupno = len(outcomes)
        ukupno_pobeda = sum(1 for o in outcomes if o.get("ishod") == "pobeda")
        win_rate_total = round(ukupno_pobeda / ukupno * 100, 1) if ukupno else 0

        ctx = (
            f"Ukupno zatvorenih predmeta: {ukupno}\n"
            f"Globalni win rate: {win_rate_total}%\n"
            f"Po tipu spora: " +
            ", ".join(f"{t['tip']} {t['win_rate']}%" for t in po_tipu_lista[:5]) + "\n"
            f"Top faktori uspeha: " +
            ", ".join(f"{f['label']} ({f['uspeh_stopa']}%)" for f in top_faktori_uspeha[:3])
        )
        try:
            from openai import OpenAI
            oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            resp = await asyncio.to_thread(
                lambda: oai.chat.completions.create(
                    model="gpt-4o-mini",
                    temperature=0.3,
                    max_tokens=400,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Analiziraš statistiku advokatske kancelarije i daješ uvide. "
                                "Vrati JSON: {\"uvid\": \"...\", \"preporuke\": [\"...\", \"...\", \"...\"]}. "
                                "uvid max 150 reči. preporuke: 3 konkretne akcije. Ekavica strogo."
                            ),
                        },
                        {"role": "user", "content": ctx},
                    ],
                )
            )
            parsed = json.loads(resp.choices[0].message.content or "{}")
            ai_uvid   = parsed.get("uvid", "")
            preporuke = parsed.get("preporuke", [])
        except Exception as e:
            logger.warning("[LEARNING] GPT performance report greška: %s", e)
            ai_uvid = f"Na osnovu {ukupno} zatvorenih predmeta, globalni win rate je {win_rate_total}%."

    return {
        "ukupno_predmeta_sa_ishodom": len(outcomes),
        "po_tipu_spora":              po_tipu_lista,
        "top_faktori_uspeha":         top_faktori_uspeha,
        "ai_uvid":                    ai_uvid,
        "preporuke_za_poboljsanje":   preporuke,
    }


# ─── ENDPOINT 6: Generiši Lessons Learned za predmet ─────────────────────────

@router.post("/predmeti/{predmet_id}/lessons")
@limiter.limit("5/minute")
async def generisi_lekcije(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Generiše i čuva Lessons Learned posle zatvorenog predmeta.
    Institucijska memorija — ostaje i kada partner ode.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    predmet = await _dohvati_predmet(supa, predmet_id, uid)
    tip_spora = predmet.get("tip", "ostalo")

    # Dohvati outcome za ovaj predmet
    try:
        out_r = await asyncio.to_thread(
            lambda: supa.table("outcome_log")
                .select("ishod,presudni_faktori,komentar,uzroci,kontekst_poraza")
                .eq("predmet_id", predmet_id)
                .limit(1)
                .execute()
        )
        out = _safe_one(out_r)
    except Exception:
        out = {}

    if not out.get("ishod"):
        raise HTTPException(status_code=422, detail="Predmet nema zabeležen ishod. Najpre zabeleži ishod.")

    from services.learning_engine import learning
    lekcije = await learning.generate_lessons_learned(
        user_id=uid,
        predmet_id=predmet_id,
        ishod=out["ishod"],
        presudni_faktori=out.get("presudni_faktori") or [],
        komentar=out.get("komentar"),
        tip_spora=tip_spora,
        uzroci=out.get("uzroci") or [],
        kontekst_poraza=out.get("kontekst_poraza"),
    )

    sacuvano = await learning.save_lessons(uid, predmet_id, lekcije, tip_spora)

    return {
        "ok":         True,
        "sacuvano":   sacuvano,
        "lekcije":    lekcije,
        "predmet_id": predmet_id,
        "tip_spora":  tip_spora,
        "poruka":     f"Generisano {sacuvano} lekcija iz predmeta. Institucijska memorija ažurirana.",
    }


# ─── ENDPOINT 7: Prikaži lekcije za predmet ──────────────────────────────────

@router.get("/predmeti/{predmet_id}/lessons")
@limiter.limit("30/minute")
async def get_lekcije_predmeta(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Sve Lessons Learned za konkretan predmet."""
    uid  = user["user_id"]
    supa = _get_supa()

    await _dohvati_predmet(supa, predmet_id, uid)

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("lessons_learned")
                .select("id,sadrzaj,kategorija,vaznost,primenjljivo_na,zastarela,zastarela_razlog,created_at")
                .eq("user_id", uid)
                .eq("predmet_id", predmet_id)
                .order("vaznost", desc=True)
                .execute()
        )
        lekcije = _safe(r)
    except Exception as e:
        logger.warning("[LEARNING] get lessons predmet greška: %s", e)
        lekcije = []

    return {
        "predmet_id": predmet_id,
        "ukupno":     len(lekcije),
        "lekcije":    lekcije,
    }


# ─── ENDPOINT 8: Sve lekcije kancelarije ──────────────────────────────────────

@router.get("/lessons")
@limiter.limit("10/minute")
async def get_sve_lekcije(
    request: Request,
    user: dict = Depends(get_current_user),
    tip_spora: Optional[str] = None,
    kategorija: Optional[str] = None,
    samo_aktivne: bool = True,
    limit: int = 50,
):
    """
    Institutionalna memorija kancelarije — sve lekcije iz svih predmeta.
    Filterable po tipu spora, kategoriji i statusu zastarelosti.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        q = (
            supa.table("lessons_learned")
            .select("id,predmet_id,tip_spora,lecija,kategorija,vaznost,primenjljivo_na,zastarela,zastarela_razlog,created_at")
            .eq("user_id", uid)
        )
        if tip_spora:
            q = q.eq("tip_spora", tip_spora)
        if kategorija:
            q = q.eq("kategorija", kategorija)
        if samo_aktivne:
            q = q.eq("zastarela", False)
        r = await asyncio.to_thread(
            lambda: q.order("vaznost", desc=True).limit(min(limit, 200)).execute()
        )
        lekcije = _safe(r)
    except Exception as e:
        logger.warning("[LEARNING] get sve lekcije greška: %s", e)
        lekcije = []

    # Epistemic badges: status + upozorenje za mali uzorak
    for l in lekcije:
        st = l.get("status_lekcije", "predlog_ai")
        n  = l.get("broj_predmeta") or 0
        if st == "usvojena_praksa":
            l["badge"]      = "Interna praksa"
            l["upozorenje"] = None
        elif st == "odbijena":
            l["badge"]      = "Odbijena"
            l["upozorenje"] = None
        else:
            l["badge"] = "Predlog AI"
            if n > 0 and n < 3:
                l["upozorenje"] = f"Zasnovano na malom uzorku ({n} predmet{'a' if n > 1 else ''}) — proverite pre primene"
            else:
                l["upozorenje"] = None

    # Grupiše po kategoriji za preglednost
    po_kategoriji: dict[str, list] = {}
    for l in lekcije:
        kat = l.get("kategorija", "ostalo")
        po_kategoriji.setdefault(kat, []).append(l)

    return {
        "ukupno":          len(lekcije),
        "samo_aktivne":    samo_aktivne,
        "po_kategoriji":   po_kategoriji,
        "lekcije":         lekcije,
    }


# ─── ENDPOINT 9: Counterfactual Learning (što-ako analiza) ────────────────────

@router.post("/counterfactual")
@limiter.limit("5/minute")
async def counterfactual_analiza(
    req: CounterfactualRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Što-ako analiza: 'Da smo prihvatili nagodbu od 50.000 RSD, šta bi se desilo?'
    AI analizira alternativni razvoj predmeta i izvlači lekciju za budućnost.
    """
    uid = user["user_id"]
    supa = _get_supa()

    await _dohvati_predmet(supa, req.predmet_id, uid)

    from services.learning_engine import learning
    result = await learning.generate_counterfactual_analysis(
        user_id=uid,
        predmet_id=req.predmet_id,
        hipoteza=req.hipoteza,
        tip_hipoteze=req.tip_hipoteze,
        odgovor=req.odgovor,
        komentar=req.komentar,
    )

    return {
        "ok":           True,
        **result,
        "tip_odgovora": "simulacija",
        "disclaimer":   "Ovo je simulacija zasnovana na dostupnim podacima i obrascima, a ne tvrdnja o tome šta bi se sigurno dogodilo.",
        "poruka":       "Counterfactual analiza sačuvana. Pomaže sistemu da uči iz alternativnih scenarija.",
    }


# ─── ENDPOINT 10: Counterfactual istorija predmeta ───────────────────────────

@router.get("/predmeti/{predmet_id}/counterfactual")
@limiter.limit("20/minute")
async def get_counterfactual_istorija(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Sve što-ako analize za konkretan predmet."""
    uid  = user["user_id"]
    supa = _get_supa()

    await _dohvati_predmet(supa, predmet_id, uid)

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("counterfactual_log")
                .select("id,hipoteza,tip_hipoteze,odgovor,komentar,ai_procena,created_at")
                .eq("user_id", uid)
                .eq("predmet_id", predmet_id)
                .order("created_at", desc=True)
                .execute()
        )
        analize = _safe(r)
    except Exception as e:
        logger.warning("[LEARNING] get counterfactual greška: %s", e)
        analize = []

    return {"predmet_id": predmet_id, "ukupno": len(analize), "analize": analize}


# ─── ENDPOINT 11: Firm DNA — organizaciona inteligencija ──────────────────────

@router.get("/firm-dna")
@limiter.limit("5/minute")
async def get_firm_dna(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Obrasci ponašanja kancelarije ekstrahovani iz istorije predmeta.
    'Kancelarija uvek angažuje veštaka u radnim sporovima' — tipičan Firm DNA obrazac.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("firm_dna")
                .select("id,pattern,tip,advokat,frekvencija,uzoraka,primer,valid_until,updated_at")
                .eq("user_id", uid)
                .order("frekvencija", desc=True)
                .limit(30)
                .execute()
        )
        obrasci = _safe(r)
    except Exception as e:
        logger.warning("[LEARNING] get firm_dna greška: %s", e)
        obrasci = []

    po_tipu: dict[str, list] = {}
    for o in obrasci:
        tip = o.get("tip", "ostalo")
        po_tipu.setdefault(tip, []).append(o)

    return {
        "ukupno_obrazaca": len(obrasci),
        "po_tipu":         po_tipu,
        "obrasci":         obrasci,
        "napomena":        "Osvežite Firm DNA posle svakih 5+ novih zatvorenih predmeta." if not obrasci else None,
    }


@router.post("/firm-dna/refresh")
@limiter.limit("2/minute")
async def refresh_firm_dna(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Ponovo ekstrahuje Firm DNA iz celokupne istorije kancelarije.
    Koristiti posle svakih 5-10 novih zatvorenih predmeta.
    """
    uid = user["user_id"]

    from services.learning_engine import learning
    obrasci = await learning.extract_firm_dna(uid)

    if not obrasci:
        return {
            "ok":      False,
            "poruka":  "Potrebno je najmanje 3 zatvorena predmeta sa poznatim ishodima za Firm DNA ekstrakciju.",
            "obrasci": [],
        }

    return {
        "ok":              True,
        "ukupno_obrazaca": len(obrasci),
        "obrasci":         obrasci,
        "poruka":          f"Firm DNA osvežena: {len(obrasci)} obrazaca ekstrahovano iz istorije kancelarije.",
    }


# ─── ENDPOINT 12: Knowledge Decay — provera zastarelosti lekcija ─────────────

@router.patch("/lessons/{lesson_id}/decay-check")
@limiter.limit("20/minute")
async def proveri_zastarelost_lekcije(
    lesson_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Proverava da li je lekcija zastarela (>18 meseci ili RAG kontradikcija).
    Automatski je označava kao zastarelu ako je uslov ispunjen.
    """
    uid = user["user_id"]

    from services.learning_engine import learning
    je_zastarela = await learning.check_knowledge_decay(uid, lesson_id)

    return {
        "lesson_id":   lesson_id,
        "je_zastarela": je_zastarela,
        "poruka": (
            "Lekcija je označena kao zastarela. Proverite aktuelnu sudsku praksu."
            if je_zastarela else
            "Lekcija je i dalje aktuelna."
        ),
    }


# ─── ENDPOINT 14: Partner potvrđuje ili odbacuje AI lekciju ──────────────────
# Meta-filter: Da li ova lekcija poboljšava kvalitet odluka ili samo dodaje buku?
# Partner kao epistemic gate — AI predlaže, čovek potvrđuje.

@router.patch("/lessons/{lesson_id}/potvrdi")
@limiter.limit("30/minute")
async def potvrdi_lekciju(
    lesson_id: str,
    req: LessonConfirmationRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Partner kancelarije potvrđuje ili odbacuje AI lekciju.
    Potvrđena lekcija dobija status 'Interna praksa' i postaje vidljiva timu.
    """
    if req.akcija not in ("potvrdi", "odbaci"):
        raise HTTPException(status_code=422, detail="Akcija mora biti 'potvrdi' ili 'odbaci'.")

    uid  = user["user_id"]
    supa = _get_supa()

    # Ownership check
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("lessons_learned")
                .select("id,lecija,status_lekcije,broj_predmeta")
                .eq("id", lesson_id)
                .eq("user_id", uid)
                .limit(1)
                .execute()
        )
        rows = _safe(r)
        if not rows:
            raise HTTPException(status_code=404, detail="Lekcija nije pronađena.")
        lekcija = rows[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("[LEARNING] potvrdi lekciju dohvat: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri dohvatu lekcije.")

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    if req.akcija == "potvrdi":
        update_data = {
            "status_lekcije": "usvojena_praksa",
            "potvrdio":       uid,
            "potvrdjeno_at":  now_iso,
        }
        if req.oblast_prava:
            update_data["oblast_prava"] = req.oblast_prava
        novi_status = "usvojena_praksa"
        poruka      = "Lekcija je potvrđena kao interna praksa kancelarije."
        znacaj      = "Ova lekcija je sada vidljiva svim kolegama kao usvojena praksa."
    else:
        update_data = {
            "status_lekcije":  "odbijena",
            "zastarela":       True,
            "zastarela_razlog": (req.komentar or "Odbacio partner")[:500],
            "zastarela_at":    now_iso,
        }
        novi_status = "odbijena"
        poruka      = "Lekcija je odbijena i uklonjena iz aktivne baze znanja."
        znacaj      = "AI sistem registruje ovo odbijanje i uči iz njega."

    try:
        await asyncio.to_thread(
            lambda: supa.table("lessons_learned")
                .update(update_data)
                .eq("id", lesson_id)
                .eq("user_id", uid)
                .execute()
        )
    except Exception as e:
        logger.warning("[LEARNING] potvrdi lekciju update: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri ažuriranju lekcije.")

    return {
        "ok":         True,
        "lesson_id":  lesson_id,
        "novi_status": novi_status,
        "lecija":     lekcija.get("lecija", "")[:200],
        "poruka":     poruka,
        "znacaj":     znacaj,
    }


# ─── ENDPOINT 15: Firm DNA history — evolucija kancelarije kroz verzije ───────
# Kancelarije evoluiraju. Firm DNA v1→v2→v3 cuva istoriju organizacionog učenja.

@router.get("/firm-dna/history")
@limiter.limit("10/minute")
async def get_firm_dna_history(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Prikazuje sve verzije Firm DNA za korisnika.
    'Od 2027. kancelarija je promenila pristup privrednim sporovima.'
    """
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("firm_dna")
                .select("id,pattern,tip,advokat,frekvencija,uzoraka,primer,verzija,verzija_od,aktuelna,created_at")
                .eq("user_id", uid)
                .order("verzija", desc=True)
                .limit(200)
                .execute()
        )
        svi_obrasci = _safe(r)
    except Exception as e:
        logger.warning("[LEARNING] firm_dna history greška: %s", e)
        svi_obrasci = []

    # Grupišemo po verziji
    po_verziji: dict[int, dict] = {}
    for o in svi_obrasci:
        v = o.get("verzija") or 1
        if v not in po_verziji:
            po_verziji[v] = {
                "verzija":    v,
                "aktuelna":   o.get("aktuelna", False),
                "verzija_od": o.get("verzija_od"),
                "obrazaca":   0,
                "obrasci":    [],
            }
        po_verziji[v]["obrazaca"] += 1
        po_verziji[v]["obrasci"].append(o)

    verzije = sorted(po_verziji.values(), key=lambda x: x["verzija"], reverse=True)
    ukupno  = len(verzije)

    if ukupno == 0:
        return {
            "ukupno_verzija": 0,
            "verzije":        [],
            "poruka":         "Firm DNA još nije generisana. Pokrenite ekstrakciju.",
        }

    return {
        "ukupno_verzija": ukupno,
        "verzije":        verzije,
        "poruka": (
            f"Kancelarija ima {ukupno} {'verziju' if ukupno == 1 else 'verzije' if ukupno < 5 else 'verzija'} DNK. "
            "Ovo omogućava praćenje evolucije prakse."
        ),
    }


# ─── ENDPOINT 16: Impact Report — ROI i uticaj AI sistema ────────────────────
# "Da li sistem zaista menja način rada?" — jedino pitanje koje je važno.

@router.get("/impact-report")
@limiter.limit("5/minute")
async def impact_report(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Meri stvarni uticaj AI sistema na rad kancelarije.
    Prihvacenost preporuka, potvrdjene lekcije, win rate.
    Jedini report koji menja razgovor sa kupcem.
    """
    uid = user["user_id"]

    from services.learning_engine import learning
    try:
        report = await learning.calculate_impact_report(uid)
    except Exception as e:
        logger.error("[LEARNING] impact report greška: %s", e)
        return {
            "greska": True,
            "poruka": "Nema dovoljno podataka za impact report. Nastavite da koristite sistem.",
        }

    return report
