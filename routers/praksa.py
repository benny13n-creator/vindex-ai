# -*- coding: utf-8 -*-
"""
Vindex AI — routers/praksa.py

F3.1 /api/sudska-praksa/grupisano
F3.2 /api/praksa/ratio
F3.3 /api/praksa/uporedi
F3.x /api/praksa/search
"""
import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

logger = logging.getLogger("vindex.api")
router = APIRouter()

_VALID_MATTERS    = frozenset({"Građanska", "Zaštita prava", "Upravna", "Krivična"})

# Kompletna mreža sudova RS po Sl. gl. RS 101/2019 + Vrhovni upravni sud 2023
SUDOVI_SRBIJE: dict[str, str] = {
    # Vrhovna instanca
    "VKS":    "Vrhovni kasacioni sud",
    "US":     "Ustavni sud Srbije",
    # Apelacioni sudovi
    "AS_BG":  "Apelacioni sud u Beogradu",
    "AS_NS":  "Apelacioni sud u Novom Sadu",
    "AS_NI":  "Apelacioni sud u Nišu",
    "AS_KG":  "Apelacioni sud u Kragujevcu",
    # Privredni apelacioni
    "PAS":    "Privredni apelacioni sud",
    # Upravni sudovi
    "VUS":    "Vrhovni upravni sud",
    "US_ADM": "Upravni sud",
    # Viši sudovi
    "VSS_BG": "Viši sud u Beogradu",
    "VSS_NS": "Viši sud u Novom Sadu",
    "VSS_NI": "Viši sud u Nišu",
    "VSS_KG": "Viši sud u Kragujevcu",
    "VSS_SK": "Viši sud u Šapcu",
    "VSS_VJ": "Viši sud u Valjevu",
    "VSS_ZA": "Viši sud u Zaječaru",
    "VSS_ZR": "Viši sud u Zrenjaninu",
    "VSS_JA": "Viši sud u Jagodini",
    "VSS_KC": "Viši sud u Kraljevu",
    "VSS_KS": "Viši sud u Kosovskoj Mitrovici",
    "VSS_LZ": "Viši sud u Leskovcu",
    "VSS_NP": "Viši sud u Negotinu",
    "VSS_PC": "Viši sud u Pančevu",
    "VSS_PI": "Viši sud u Pirotu",
    "VSS_PZ": "Viši sud u Požarevcu",
    "VSS_PK": "Viši sud u Prokuplju",
    "VSS_SM": "Viši sud u Smederevu",
    "VSS_SO": "Viši sud u Somboru",
    "VSS_SR": "Viši sud u Sremskoj Mitrovici",
    "VSS_SU": "Viši sud u Subotici",
    "VSS_UZ": "Viši sud u Užicu",
    "VSS_VR": "Viši sud u Vranju",
    "VSS_VB": "Viši sud u Vrbasu",
    # Privredni sudovi
    "PS_BG":  "Privredni sud u Beogradu",
    "PS_NS":  "Privredni sud u Novom Sadu",
    "PS_NI":  "Privredni sud u Nišu",
    "PS_KG":  "Privredni sud u Kragujevcu",
    "PS_SK":  "Privredni sud u Šapcu",
    "PS_VJ":  "Privredni sud u Valjevu",
    "PS_ZR":  "Privredni sud u Zrenjaninu",
    "PS_JA":  "Privredni sud u Jagodini",
    "PS_KC":  "Privredni sud u Kraljevu",
    "PS_LZ":  "Privredni sud u Leskovcu",
    "PS_PC":  "Privredni sud u Pančevu",
    "PS_PZ":  "Privredni sud u Požarevcu",
    "PS_SM":  "Privredni sud u Smederevu",
    "PS_SO":  "Privredni sud u Somboru",
    "PS_SR":  "Privredni sud u Sremskoj Mitrovici",
    "PS_UZ":  "Privredni sud u Užicu",
    # Specijalni / međunarodni
    "ESLJP":  "Evropski sud za ljudska prava",
    "MKS":    "Međunarodni krivični sud",
}

# Skup punih naziva za brzu validaciju (vrednosti iz dicts + stari nazivi iz baze)
_VALID_COURTS: frozenset = frozenset(SUDOVI_SRBIJE.values()) | frozenset({
    "Vrhovni sud", "Vrhovni sud Srbije",
    "Osnovni sud u Beogradu", "Osnovni sud u Novom Sadu",
})

_PRAKSA_NS_SEARCH = "sudska_praksa"
_KEYWORD_FALLBACK_THRESHOLD = 0.45  # semantic score ispod ovog → keyword fallback


# ── Models ────────────────────────────────────────────────────────────────────

class PraksaSearchReq(BaseModel):
    query:     Optional[str] = None
    matter:    Optional[str] = None
    court:     Optional[str] = None
    year_from: Optional[int] = None
    year_to:   Optional[int] = None
    limit:     int = Field(default=10, ge=1, le=50)
    offset:    int = Field(default=0, ge=0)

    @field_validator("query")
    @classmethod
    def ocisti_query(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return v


class RatioReq(BaseModel):
    decisions: list[dict]


class UporediReq(BaseModel):
    odluka_a: str
    odluka_b: str


# ── /api/praksa/search helpers ────────────────────────────────────────────────

def _keyword_fallback_sync(
    query: str,
    top_k: int,
    filter_dict: Optional[dict],
    index,
) -> list:
    """Keyword-reranking fallback: širi semantic query + keyword hit scoring po metadata."""
    import math as _math
    from app.services.retrieve import _ugradi_query
    try:
        keywords = [w.lower() for w in query.split() if len(w) > 3]
        if not keywords:
            return []
        vector = _ugradi_query(query)
        res = index.query(
            vector=vector,
            top_k=top_k * 4,
            filter=filter_dict,
            namespace=_PRAKSA_NS_SEARCH,
            include_metadata=True,
        )
        scored = []
        for m in res.matches:
            meta = m.metadata or {}
            haystack = " ".join(filter(None, [
                meta.get("text", ""),
                meta.get("kljucne_reci", ""),
                meta.get("matter", ""),
                meta.get("court", ""),
                meta.get("decision_number", ""),
            ])).lower()
            hits = sum(1 for kw in keywords if kw in haystack)
            if hits > 0:
                scored.append((hits, m.score, m))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [m for _, _, m in scored[:top_k]]
    except Exception as e:
        logger.warning("[PRAKSA] Keyword fallback greška: %s", e)
        return []


def _praksa_search_sync(
    query:     Optional[str],
    matter:    Optional[str],
    court:     Optional[str],
    year_from: Optional[int],
    year_to:   Optional[int],
    limit:     int,
    offset:    int,
) -> dict:
    import re as _re
    from app.services.retrieve import _get_index, _ugradi_query

    filters: dict = {}
    if matter:
        filters["matter"] = {"$eq": matter}
    if court:
        filters["court"] = {"$eq": court}
    filter_dict: Optional[dict] = filters if filters else None

    has_query = bool(query and query.strip())
    if has_query:
        vector = _ugradi_query(query)
    else:
        import math as _math
        _dim = 3072
        vector = [1.0 / _math.sqrt(_dim)] * _dim

    top_k = 300 if has_query else 1500

    index = _get_index()
    res = index.query(
        vector=vector,
        top_k=top_k,
        filter=filter_dict,
        namespace=_PRAKSA_NS_SEARCH,
        include_metadata=True,
    )

    # Keyword fallback: ako semantic scores nisu dovoljno visoki, rerankiraj po ključnim rečima
    raw_matches = res.matches
    if has_query and raw_matches:
        max_score = max((m.score for m in raw_matches), default=0.0)
        if max_score < _KEYWORD_FALLBACK_THRESHOLD:
            logger.info("[PRAKSA] Semantic max_score=%.3f < %.2f — keyword fallback",
                        max_score, _KEYWORD_FALLBACK_THRESHOLD)
            fallback = _keyword_fallback_sync(query, top_k, filter_dict, index)
            if fallback:
                raw_matches = fallback

    groups: dict[str, dict] = {}
    for m in raw_matches:
        meta = m.metadata or {}
        dn = (meta.get("decision_number") or "").strip() or m.id
        if dn not in groups:
            groups[dn] = {
                "decision_number": dn,
                "decision_date":   meta.get("decision_date", ""),
                "court":           meta.get("court", ""),
                "matter":          meta.get("matter", ""),
                "chunks":          [],
                "max_score":       m.score,
            }
        groups[dn]["chunks"].append({
            "section":     meta.get("section", ""),
            "text":        meta.get("text", "") or meta.get("parent_text", ""),
            "chunk_index": meta.get("chunk_index") or 0,
            "score":       m.score,
        })
        if m.score > groups[dn]["max_score"]:
            groups[dn]["max_score"] = m.score

    decisions_raw: list[dict] = []
    for g in groups.values():
        chunks = sorted(g["chunks"], key=lambda c: c["chunk_index"])
        izreka_full   = " ".join(c["text"] for c in chunks if c["section"] == "IZREKA").strip()
        obrazloz_full = " ".join(c["text"] for c in chunks if c["section"] == "OBRAZLOŽENJE").strip()
        decisions_raw.append({
            "decision_number":   g["decision_number"],
            "decision_date":     g["decision_date"],
            "court":             g["court"],
            "matter":            g["matter"],
            "izreka_preview":    izreka_full[:400],
            "izreka_full":       izreka_full,
            "obrazlozenje_full": obrazloz_full,
            "score":             round(g["max_score"], 6),
            "citat_format":      f"{g['court']}, {g['decision_number']}, od {g['decision_date']}.".strip(" ,"),
        })

    if year_from is not None or year_to is not None:
        filtered: list[dict] = []
        for d in decisions_raw:
            yr_m = _re.match(r"(\d{4})", d["decision_date"] or "")
            if not yr_m:
                continue
            yr = int(yr_m.group(1))
            if year_from is not None and yr < year_from:
                continue
            if year_to is not None and yr > year_to:
                continue
            filtered.append(d)
        decisions_raw = filtered

    if has_query:
        decisions_raw.sort(key=lambda d: d["score"], reverse=True)
    else:
        decisions_raw.sort(key=lambda d: d["decision_date"] or "", reverse=True)

    total = len(decisions_raw)
    return {
        "total":     total,
        "page":      offset // limit + 1,
        "limit":     limit,
        "decisions": decisions_raw[offset: offset + limit],
    }


# ── /api/praksa/ratio helpers ─────────────────────────────────────────────────

_RATIO_SYSTEM_PROMPT = (
    "Ti si asistent za analizu sudskih presuda Vrhovnog suda Republike Srbije. "
    "Iz dostavljenog teksta izvuci ISKLJUČIVO ratio decidendi — ključni pravni stav "
    "koji je temelj odluke. "
    "PRAVILA: Maksimalno 3 rečenice srpskim jezikom (ekavica). "
    "Samo pravni stav suda — ne činjenice slučaja, ne opis stranaka, ne izreka. "
    "Format: piši u trećem licu ('Sud je zauzeo stav...', 'Sud smatra...'). "
    "Ako tekst ne sadrži jasno pravno obrazloženje, odgovori samo: "
    "'Obrazloženje nije dostupno u dostavljenom tekstu.'"
)

_IZREKA_ONLY = "__IZREKA_ONLY__"


def _get_ratio_from_cache(decision_number: str) -> Optional[str]:
    try:
        r = (_get_supa()
             .table("ratio_decidendi")
             .select("ratio")
             .eq("decision_number", decision_number)
             .limit(1)
             .execute())
        if r.data:
            return r.data[0]["ratio"]
    except Exception as e:
        logger.debug("[RATIO] Cache miss/error for %r: %s", decision_number, e)
    return None


def _save_ratio_to_cache(decision_number: str, ratio: str) -> None:
    try:
        _get_supa().table("ratio_decidendi").upsert(
            {"decision_number": decision_number, "ratio": ratio},
            on_conflict="decision_number",
        ).execute()
    except Exception as e:
        logger.warning("[RATIO] Cache save failed for %r: %s", decision_number, e)


def _extract_ratio_sync(decision_number: str, tekst: str) -> str:
    """Check cache → GPT-4o mini → cache. Thread-safe, never throws."""
    if not decision_number:
        return ""
    cached = _get_ratio_from_cache(decision_number)
    if cached:
        logger.debug("[RATIO] HIT %r", decision_number)
        return cached
    tekst_stripped = (tekst or "").strip()
    logger.info("[RATIO] MISS %r — text_len=%d preview=%r",
                decision_number, len(tekst_stripped), tekst_stripped[:80])
    if len(tekst_stripped) < 60:
        logger.info("[RATIO] IZREKA_ONLY %r — tekst: %r", decision_number, tekst_stripped)
        return _IZREKA_ONLY
    try:
        from openai import OpenAI as _OAI
        client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.1,
            max_tokens=220,
            messages=[
                {"role": "system", "content": _RATIO_SYSTEM_PROMPT},
                {"role": "user",   "content": tekst_stripped[:3000]},
            ],
        )
        ratio = (resp.choices[0].message.content or "").strip()
        logger.info("[RATIO] GPT response %r → %r", decision_number, ratio[:120])
    except Exception as e:
        logger.warning("[RATIO] GPT failed for %r: %s", decision_number, e)
        return ""
    if not ratio or "nije dostupno" in ratio.lower():
        return ""
    _save_ratio_to_cache(decision_number, ratio)
    logger.info("[RATIO] MISS→extracted %r (%d chars)", decision_number, len(ratio))
    return ratio


# ── /api/praksa/uporedi helpers ───────────────────────────────────────────────

_UPOREDI_SYSTEM_PROMPT = (
    "Ti si pravni asistent specijalizovan za srpsko pravo. "
    "Analiziraš dve sudske odluke i praviš uporednu analizu. "
    "Budi koncizan i precizan. Piši na srpskom jeziku, ekavica."
)

_UPOREDI_USER_TEMPLATE = (
    "ODLUKA A: {broj_a} ({datum_a}, {sud_a})\n{tekst_a}\n\n---\n\n"
    "ODLUKA B: {broj_b} ({datum_b}, {sud_b})\n{tekst_b}\n\n---\n\n"
    "Napravi uporednu analizu u sledećim sekcijama:\n\n"
    "## 1. PRAVNA PITANJA\n"
    "Koja pravna pitanja rešava svaka odluka? Jesu li ista ili srodna?\n\n"
    "## 2. SLIČNOSTI U ARGUMENTACIJI\n"
    "Gde se sudovi slažu u pravnom rezonovanju?\n\n"
    "## 3. RAZLIKE U ZAKLJUČKU\n"
    "U čemu se odluke razlikuju — ishod, tumačenje zakona, primenjeni standardi?\n\n"
    "## 4. AUTORITET I AKTUELNOST\n"
    "Koja odluka ima veći pravni autoritet (viši sud, noviji datum, precedentni značaj)?\n\n"
    "## 5. PREPORUKA ZA KONKRETNI PREDMET\n"
    "Koja je odluka relevantnija kao argument u postupku i zašto? Daj konkretnu preporuku."
)


def _fetch_decision_chunks(dn: str) -> tuple:
    """Fetch all chunks for a decision from sudska_praksa (and upravna_praksa).
    Returns (meta_dict, full_text) or raises ValueError if not found."""
    import math as _math
    from app.services.retrieve import _get_index
    index = _get_index()
    _dim = 3072
    dummy_vec = [1.0 / _math.sqrt(_dim)] * _dim

    all_chunks: list = []
    meta: dict = {}
    for ns in ("sudska_praksa", "upravna_praksa"):
        try:
            res = index.query(
                vector=dummy_vec,
                top_k=20,
                namespace=ns,
                include_metadata=True,
                filter={"decision_number": {"$eq": dn}},
            )
            for m in res.matches:
                md = m.metadata or {}
                if not meta and md.get("decision_number"):
                    meta = {
                        "broj":   md.get("decision_number", dn),
                        "datum":  md.get("decision_date", ""),
                        "sud":    md.get("court", ""),
                        "oblast": md.get("matter", ""),
                    }
                txt = (md.get("text") or md.get("parent_text") or "").strip()
                if txt:
                    all_chunks.append({
                        "section":     md.get("section", ""),
                        "text":        txt,
                        "chunk_index": int(md.get("chunk_index") or 0),
                    })
        except Exception as _fe:
            logger.debug("[UPOREDI] ns=%s fetch failed for %r: %s", ns, dn, _fe)

    if not all_chunks:
        raise ValueError(f"Odluka \"{dn}\" nije pronađena u bazi sudskih odluka.")

    _sec_order = {"HEADER": 0, "IZREKA": 1, "OBRAZLOŽENJE": 2}
    all_chunks.sort(key=lambda c: (_sec_order.get(c["section"], 9), c["chunk_index"]))
    full_text = "\n\n".join(c["text"] for c in all_chunks)[:4500]
    if not meta:
        meta = {"broj": dn, "datum": "", "sud": "", "oblast": ""}
    return meta, full_text


def _uporedi_sync(dn_a: str, dn_b: str) -> dict:
    try:
        meta_a, tekst_a = _fetch_decision_chunks(dn_a)
    except ValueError as e:
        return {"error": str(e)}
    try:
        meta_b, tekst_b = _fetch_decision_chunks(dn_b)
    except ValueError as e:
        return {"error": str(e)}

    user_msg = _UPOREDI_USER_TEMPLATE.format(
        broj_a=meta_a["broj"],
        datum_a=meta_a["datum"] or "nepoznat datum",
        sud_a=meta_a["sud"] or "nepoznat sud",
        tekst_a=tekst_a,
        broj_b=meta_b["broj"],
        datum_b=meta_b["datum"] or "nepoznat datum",
        sud_b=meta_b["sud"] or "nepoznat sud",
        tekst_b=tekst_b,
    )
    try:
        from openai import OpenAI as _OAI
        client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.2,
            max_tokens=1400,
            messages=[
                {"role": "system", "content": _UPOREDI_SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
        )
        analiza = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("[UPOREDI] GPT failed: %s", e)
        return {"error": "Greška pri generisanju analize. Pokušajte ponovo."}

    logger.info("[UPOREDI] %r vs %r → %d chars", dn_a, dn_b, len(analiza))
    return {"odluka_a": meta_a, "odluka_b": meta_b, "analiza": analiza}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/api/praksa/search")
@limiter.limit("30/minute")
async def praksa_search(req: PraksaSearchReq, request: Request, user: dict = Depends(get_current_user)):
    """Faceted case-law search over sudska_praksa Pinecone namespace."""
    if req.matter and req.matter not in _VALID_MATTERS:
        return JSONResponse(
            status_code=400,
            content={"error": "Nevalidan matter filter",
                     "detail": f"Dozvoljena vrednost: {sorted(_VALID_MATTERS)}"},
        )
    if req.court and req.court not in _VALID_COURTS:
        return JSONResponse(
            status_code=400,
            content={"error": "Nevalidan court filter",
                     "detail": f"Dozvoljena vrednost: {sorted(_VALID_COURTS)}"},
        )
    if (req.year_from is not None and req.year_to is not None
            and req.year_from > req.year_to):
        return JSONResponse(
            status_code=400,
            content={"error": "Nevalidan opseg godina",
                     "detail": "year_from mora biti ≤ year_to"},
        )
    try:
        result = await asyncio.to_thread(
            _praksa_search_sync,
            req.query, req.matter, req.court,
            req.year_from, req.year_to,
            req.limit, req.offset,
        )
        return result
    except Exception as exc:
        logger.exception("Greška u /api/praksa/search")
        return JSONResponse(
            status_code=500,
            content={"error": "Greška Pinecone servisa", "detail": str(exc)[:200]},
        )


@router.post("/api/praksa/ratio")
@limiter.limit("20/minute")
async def praksa_ratio(req: RatioReq, request: Request, user: dict = Depends(get_current_user)):
    """Phase 3.2: Batch extract/serve ratio decidendi with Supabase caching."""
    if not req.decisions:
        return {"ratios": {}}
    if len(req.decisions) > 20:
        return JSONResponse(status_code=400, content={"error": "Maksimalno 20 odluka"})

    async def _one(d: dict):
        dn   = (d.get("decision_number") or "").strip()
        text = (d.get("text") or "").strip()[:3000]
        if not dn:
            return None, None
        ratio = await asyncio.to_thread(_extract_ratio_sync, dn, text)
        return dn, ratio

    results = await asyncio.gather(*[_one(d) for d in req.decisions], return_exceptions=True)
    ratios = {}
    for r in results:
        if isinstance(r, Exception) or r is None:
            continue
        dn, ratio = r
        if dn and ratio:
            ratios[dn] = ratio
    return {"ratios": ratios}


@router.post("/api/praksa/uporedi")
@limiter.limit("10/minute")
async def praksa_uporedi(
    req: UporediReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Phase 3.3: Compare two court decisions via GPT-4o analysis."""
    dn_a = (req.odluka_a or "").strip()
    dn_b = (req.odluka_b or "").strip()
    if not dn_a or not dn_b:
        return JSONResponse(status_code=400, content={"error": "Oba broja odluke su obavezna."})
    if len(dn_a) > 100 or len(dn_b) > 100:
        return JSONResponse(status_code=400, content={"error": "Broj odluke predugačak."})
    if dn_a.lower() == dn_b.lower():
        return JSONResponse(status_code=400, content={"error": "Odaberite dve različite odluke."})
    try:
        result = await asyncio.to_thread(_uporedi_sync, dn_a, dn_b)
        return result
    except Exception:
        logger.exception("Greška u /api/praksa/uporedi")
        return JSONResponse(status_code=500, content={"error": "Interna greška servera."})


@router.get("/api/praksa/sudovi")
async def get_sudovi():
    """Vraća kompletnu listu srpskih sudova za frontend dropdown."""
    categories = {
        "vrhovna": [],
        "apelacioni": [],
        "privredni_apelacioni": [],
        "upravni": [],
        "visi": [],
        "privredni": [],
        "specijalni": [],
    }
    for kod, naziv in SUDOVI_SRBIJE.items():
        if kod in ("VKS", "US"):
            categories["vrhovna"].append({"kod": kod, "naziv": naziv})
        elif kod.startswith("AS_"):
            categories["apelacioni"].append({"kod": kod, "naziv": naziv})
        elif kod == "PAS":
            categories["privredni_apelacioni"].append({"kod": kod, "naziv": naziv})
        elif kod in ("VUS", "US_ADM"):
            categories["upravni"].append({"kod": kod, "naziv": naziv})
        elif kod.startswith("VSS_"):
            categories["visi"].append({"kod": kod, "naziv": naziv})
        elif kod.startswith("PS_"):
            categories["privredni"].append({"kod": kod, "naziv": naziv})
        else:
            categories["specijalni"].append({"kod": kod, "naziv": naziv})
    return {
        "sudovi": [{"kod": k, "naziv": v} for k, v in SUDOVI_SRBIJE.items()],
        "kategorije": categories,
        "ukupno": len(SUDOVI_SRBIJE),
    }


@router.get("/api/sudska-praksa/grupisano")
@limiter.limit("20/minute")
async def sudska_praksa_grupisano(query: str, request: Request, user: dict = Depends(get_current_user)):
    """Phase 3.1: Retrieve top-10 decisions grouped by outcome (tuzilac/tuzeni/mesovito)."""
    q = (query or "").strip()
    if not q:
        return JSONResponse(status_code=400, content={"error": "query je obavezan"})
    if len(q) > 400:
        return JSONResponse(status_code=400, content={"error": "query predugačak (max 400 znakova)"})
    try:
        from app.services.retrieve import retrieve_grupisano
        result = await asyncio.to_thread(retrieve_grupisano, q, 10)
        return result
    except Exception as exc:
        logger.exception("Greška u /api/sudska-praksa/grupisano")
        return JSONResponse(
            status_code=500,
            content={"error": "Greška Pinecone servisa", "detail": str(exc)[:200]},
        )


# ── P4 — Argument Mapping ─────────────────────────────────────────────────────

_ARGUMENT_MAP_SYSTEM = """Ti si pravni analitičar specijalizovan za srpsku sudsku praksu.
Dato je pravno pitanje/argument i lista sudskih odluka.
Za SVAKU odluku odredi da li podržava, suprotstavlja ili je neutralna u odnosu na dati argument.

Odgovori ISKLJUČIVO u JSON formatu:
{
  "za_mene": [{"decision_number": str, "court": str, "decision_date": str, "razlog": str, "izreka_preview": str}],
  "protiv_mene": [{"decision_number": str, "court": str, "decision_date": str, "razlog": str, "izreka_preview": str}],
  "neutralno": [{"decision_number": str, "court": str, "decision_date": str, "razlog": str, "izreka_preview": str}]
}

Razlog: 1-2 rečenice zašto je odluka za/protiv/neutralna.
Budi precizan — ne halucinuj. Ako nisi siguran, stavi u neutralno."""


class ArgumentMapReq(BaseModel):
    argument: str = Field(..., min_length=10, max_length=2000, description="Pravni argument/pozicija stranke")
    q:        Optional[str] = Field(default=None, max_length=400, description="Opcioni query za pretragu prakse (default = argument)")


@router.post("/api/praksa/argument-map")
@limiter.limit("10/minute")
async def argument_map(
    req: ArgumentMapReq,
    request: Request,
    user: dict = Depends(PermissionService.require("sudska_praksa")),
):
    """
    Argument Mapping — klasifikuje sudsku praksu u ZA/PROTIV/NEUTRALNO za dati argument.
    Vraća strukturiran prikaz koji direktno podržava ili opovrgava pravnu poziciju.
    """
    search_q = (req.q or req.argument)[:400]

    # Fetch top-15 results from Pinecone
    try:
        from app.services.retrieve import retrieve_sudska_praksa as _rp
        matches = await asyncio.to_thread(_rp, search_q, 15)
    except Exception as exc:
        logger.error("[ARGUMENT-MAP] Pinecone greška: %s", exc)
        return JSONResponse(status_code=500, content={"error": "Greška pri pretrazi prakse."})

    if not matches:
        return {"argument": req.argument, "za_mene": [], "protiv_mene": [], "neutralno": [], "ukupno": 0}

    # Build score_map: decision_number → pinecone similarity score
    score_map: dict = {}
    decisions_text = ""
    for i, m in enumerate(matches, 1):
        meta = m.get("metadata", {})
        dn = meta.get("decision_number", "")
        if dn:
            score_map[dn] = round(m.get("score", 0), 4)
        decisions_text += (
            f"\n[{i}] Broj: {dn or '?'} | Sud: {meta.get('court','?')} | "
            f"Datum: {meta.get('decision_date','?')}\n"
            f"Izreka: {meta.get('izreka_preview', meta.get('tekst',''))[:300]}\n"
        )

    import os as _os, json as _json
    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=_os.getenv("OPENAI_API_KEY", ""))

    try:
        resp = await oai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _ARGUMENT_MAP_SYSTEM},
                {"role": "user",   "content": f"MOJ ARGUMENT:\n{req.argument}\n\nSUDSKE ODLUKE:{decisions_text}"},
            ],
        )
        result = _json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:
        logger.error("[ARGUMENT-MAP] OpenAI greška: %s", exc)
        return JSONResponse(status_code=500, content={"error": "Greška pri klasifikaciji argumenata."})

    za      = result.get("za_mene", [])
    protiv  = result.get("protiv_mene", [])
    neutral = result.get("neutralno", [])

    def _confidence(group: list) -> int:
        if not group:
            return 0
        scores = [score_map.get(item.get("decision_number", ""), 0.5) for item in group]
        return min(99, round(sum(scores) / len(scores) * 100))

    total = len(za) + len(protiv) + len(neutral)

    await UsageService.consume(user["user_id"], user.get("email", ""), "sudska_praksa")

    return {
        "argument":    req.argument,
        "za_mene":     za,
        "protiv_mene": protiv,
        "neutralno":   neutral,
        "ukupno":      total,
        "rezime": {
            "za_count":          len(za),
            "za_pouzdanost":     _confidence(za),
            "protiv_count":      len(protiv),
            "protiv_pouzdanost": _confidence(protiv),
            "neutral_count":     len(neutral),
        },
    }


# ── P8 — Semantic Precedent Matching ─────────────────────────────────────────

_SLICNI_SYSTEM = (
    "Ti si pravni asistent specijalizovan za srpsku sudsku praksu. "
    "Dato je opisani predmet (činjenice + pravno pitanje) i lista sudskih odluka. "
    "Za svaku odluku proceni semantičku sličnost sa opisanim predmetom. "
    "Odgovori ISKLJUČIVO u JSON formatu:\n"
    '{"slicni": [{"decision_number": str, "slicnost_pct": int (0-100), '
    '"slicnost_opis": str}]}\n'
    "slicnost_pct: 0=nema veze, 50=delimično, 90+=visoko relevantna.\n"
    "slicnost_opis: 1-2 rečenice srpskim jezikom zašto je slična.\n"
    "Poredaj od najviše ka najnižoj sličnosti. Ne halucinuj — koristi samo date odluke."
)


class SlicniPredmetiReq(BaseModel):
    cinjenice:     str           = Field(..., min_length=20, max_length=3000, description="Kratki opis činjenica predmeta")
    pravno_pitanje: Optional[str] = Field(default=None, max_length=500, description="Konkretno pravno pitanje (opciono)")
    top_k:         int           = Field(default=5, ge=1, le=15, description="Broj sličnih predmeta koje treba vratiti")


def _slicni_predmeti_sync(cinjenice: str, pravno_pitanje: Optional[str], top_k: int) -> dict:
    import json as _json
    from app.services.retrieve import retrieve_sudska_praksa, process_praksa_chunks

    combined = cinjenice.strip()
    if pravno_pitanje:
        combined += " " + pravno_pitanje.strip()
    combined = combined[:600]

    raw_matches = retrieve_sudska_praksa(combined, top_k=20)
    kandidati = process_praksa_chunks(raw_matches, k=min(top_k * 3, 15))

    if not kandidati:
        return {
            "query_used": combined,
            "ukupno_pronadjeno": 0,
            "slicni": [],
        }

    decisions_text = ""
    for i, d in enumerate(kandidati, 1):
        izreka = (d.get("text") or "")[:300].replace("\n", " ")
        decisions_text += (
            f"\n[{i}] Broj: {d.get('decision_number','?')} | "
            f"Sud: {d.get('court','?')} | Datum: {d.get('date','?')}\n"
            f"Tekst: {izreka}\n"
        )

    from openai import OpenAI as _OAI
    client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=1200,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SLICNI_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"MOJ PREDMET:\nČinjenice: {cinjenice}\n"
                        + (f"Pravno pitanje: {pravno_pitanje}\n" if pravno_pitanje else "")
                        + f"\nSUDSKE ODLUKE:{decisions_text}"
                    ),
                },
            ],
        )
        gpt_result = _json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:
        logger.warning("[SLICNI] GPT greška: %s — vraćam samo vektorski rezultat", exc)
        gpt_result = {"slicni": []}

    gpt_map: dict[str, dict] = {}
    for item in gpt_result.get("slicni", []):
        dn = (item.get("decision_number") or "").strip()
        if dn:
            gpt_map[dn] = item

    merged: list = []
    for d in kandidati:
        dn = d.get("decision_number", "")
        gpt = gpt_map.get(dn, {})
        merged.append({
            "decision_number": dn,
            "court":           d.get("court", ""),
            "decision_date":   d.get("date", ""),
            "matter":          d.get("matter", ""),
            "izreka_preview":  (d.get("text") or "")[:200],
            "score":           round(d.get("score", 0.0), 4),
            "slicnost_pct":    gpt.get("slicnost_pct", 0),
            "slicnost_opis":   gpt.get("slicnost_opis", ""),
        })

    merged.sort(key=lambda x: (x["slicnost_pct"], x["score"]), reverse=True)
    return {
        "query_used":        combined[:200],
        "ukupno_pronadjeno": len(merged),
        "slicni":            merged[:top_k],
    }


@router.post("/api/praksa/slicni-predmeti")
@limiter.limit("15/minute")
async def slicni_predmeti(
    req: SlicniPredmetiReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Semantic Precedent Matching — pronalazi sudske odluke semantički slične opisanom predmetu.
    GPT-4o-mini rangira svaki rezultat po sličnosti i daje kratko objašnjenje.
    """
    try:
        result = await asyncio.to_thread(
            _slicni_predmeti_sync,
            req.cinjenice,
            req.pravno_pitanje,
            req.top_k,
        )
        return result
    except Exception:
        logger.exception("Greška u /api/praksa/slicni-predmeti")
        return JSONResponse(
            status_code=500,
            content={"error": "Interna greška servera."},
        )
