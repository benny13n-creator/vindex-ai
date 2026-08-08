# -*- coding: utf-8 -*-
"""
Vindex AI — routers/hearing_cc.py
Hearing Command Center (PRO) — Phase: Intelligence

POST /api/rociste/command-center
  Generiše 12-sektorski borbeni brifing za predstojeće ročište.
  Cena: 3 kredita | PRO-only
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from shared.deps import _audit, _get_supa, get_current_user
from shared.llm_retry import llm_retry
from shared.permissions import PermissionService
from shared.sentry import capture_exception as _sentry_capture
from shared.usage import UsageService
from shared.cost import begin_cost_tracking, log_cost_to_db
from shared.rate import limiter
from shared.case_context import build_case_context
from shared.case_readiness import CRITICAL_GAP, BLOCKED, CAP_BY_READINESS

logger = logging.getLogger("vindex.hearing_cc")
router = APIRouter(tags=["hearing_cc"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


@llm_retry
async def _pozovi_hcc_api(oai, **kwargs):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške."""
    return await oai.chat.completions.create(**kwargs)

# ─── System prompts ───────────────────────────────────────────────────────────

_SYSTEM_GRADJANSKI = """Ti si elitni parničar sa 30 godina iskustva u srpskim parničnim postupcima.
Pripremaš sveobuhvatan borbeni brifing za predstojeće ročište u parničnom postupku.
Posebno analiziraj: teret dokazivanja (čl. 231 ZPP), procesne rokove, prekluziju dokaza,
koncentracijsko načelo (čl. 307-308 ZPP), te mogućnost presude zbog izostanka.
Odgovori ISKLJUČIVO na srpskom jeziku. Svi argumenti moraju imati osnov u ZPP i materijalnom pravu."""

_SYSTEM_KRIVICNI = """Ti si iskusan krivični branilac/tužilac sa 30 godina iskustva u srpskom krivičnom pravu.
Pripremaš brifing za krivično ročište / glavno pretresanje.
Posebno analiziraj: presumpciju nevinosti, teret dokazivanja tužilaštva, isključenje nezakonito
pribavljenih dokaza (čl. 84 ZKP), pravo na odbranu, zastarelost krivičnog gonjenja.
Odgovori ISKLJUČIVO na srpskom jeziku. Reference na ZKP i KZ Srbije."""

_SYSTEM_UPRAVNI = """Ti si specijalizovani pravnik za upravni postupak i upravni spor u Srbiji.
Pripremaš brifing za ročište pred upravnim sudom ili u upravnom postupku.
Posebno analiziraj: rokove za žalbu i tužbu (čl. 17 ZUSUS), diskreciona ovlašćenja uprave,
načelo zakonitosti, pravo na izjašnjenje (čl. 9 ZUP), razloge poništaja upravnog akta.
Odgovori ISKLJUČIVO na srpskom jeziku. Reference na ZUP, ZUSUS i posebne zakone."""

_SYSTEM_PRIVREDNI = """Ti si iskusni advokat specijalizovan za privrednopravne sporove pred privrednim sudovima u Srbiji.
Pripremaš sveobuhvatan borbeni brifing za predstojeće ročište u privrednom sporu.

SPECIFIKUM PRIVREDNIH SUDOVA:
- Nadležnost: Zakon o uređenju sudova — privredni sudovi sude u sporovima između privrednih subjekata
- Hitnost: privrednopravni sporovi imaju zakonski prioritet i kraće rokove (čl. 467 ZPP)
- Dokazi: poslovne knjige (čl. 55-59 Zakona o računovodstvu), finansijski izveštaji, fakture, izvodi, veštačenje
- ZPD (Zakon o privrednim društvima) — odgovornost direktora, kapital, skupštinska odluka, zastupanje
- ZOSL (Zakon o stečaju) — ako je stranka u stečaju ili likvidaciji, posebni prioriteti potraživanja
- ZOO (Zakon o obligacionim odnosima) — ugovorni osnov, odgovornost, raskid, naknada štete
- ZPP — parničný postupak pred privrednim sudom (iste procesne odredbe, ali hitno)

BRIFING SEKCIJE:
1. Stranke i kapacitet (privredno pravno lice, zastupnik, ovlašćenja, matični br./PIB)
2. Predmet spora (ugovorni osnov, vrednost potraživanja, kamate, troškovi)
3. Ključni dokazi (poslovne knjige, fakture, ugovori, izvodi — šta imamo, šta nedostaje)
4. Pravni osnov (konkretni članovi ZOO, ZPD, posebnih zakona)
5. Taktika na ročištu (procesne primedbe, predlozi za dokaze, veštačenje)
6. Rizici i alternativni ishodi (stečaj stranke, zastara, prigovor prebijanja)
7. Poravnanje vs. nastavak — komercijalna i pravna procena
8. Sledeći koraci i rokovi

Uvek navodi konkretne zakonske odredbe. Budi koncizan i operativan.
Odgovori ISKLJUČIVO na srpskom jeziku."""

_SYSTEM_RADNI = """Ti si specijalizovani pravnik za radne sporove i zaštitu prava radnika u Srbiji.
Pripremaš brifing za ročište u radnom sporu.
Posebno analiziraj: hitnost radnih sporova (čl. 195 ZOR), teret dokazivanja otkaznog razloga
(čl. 127 ZOR), zabranu diskriminacije (ZBD), zaštitu sindikalnih predstavnika, rokove za sudsku zaštitu.
Odgovori ISKLJUČIVO na srpskom jeziku. Reference na ZOR, ZBD i Kolektivne ugovore."""

_SYSTEM_PROMPTS: dict[str, str] = {
    "gradjanski": _SYSTEM_GRADJANSKI,
    "krivicni":   _SYSTEM_KRIVICNI,
    "upravni":    _SYSTEM_UPRAVNI,
    "privredni":  _SYSTEM_PRIVREDNI,
    "privredno":  _SYSTEM_PRIVREDNI,   # alias
    "radni":      _SYSTEM_RADNI,
}

_VALID_TIP = set(_SYSTEM_PROMPTS.keys())

# Program Tau, Master Sprint 006 ("Canonical Context Migration Factory") — this
# module's own Phase 4 pilot. Appended (not templated into all 5 system
# prompts above, per the Factory's own "no duplicated logic" rule) so GPT
# aligns hearing_score/risk_breakdown/missing_evidence with what the platform
# already knows about this case, rather than re-deriving them from the prompt
# text alone. See docs/tau/CANONICAL_CONTEXT_FACTORY.md Step 4/6.
_CASE_CONTEXT_ALIGNMENT_SUFFIX = """

Ako je ispod dat blok "STVARNO STANJE PREDMETA U SISTEMU": to je kanonski izvor, koristi ga kao osnovu.
Tvoj "missing_evidence" ne sme da protivreci već poznatim nedostajućim dokazima iz tog bloka -- dopuni ih,
ne izmišljaj suprotno. Tvoj "hearing_score" mora biti niži ako blok pokazuje kritičan nedostatak (readiness:
CRITICAL_GAP ili BLOCKED) -- takav predmet ne može biti visoko ocenjen kao "spreman za ročište"."""

# Deterministic ceiling on hearing_score when the canonical readiness status is
# CRITICAL_GAP/BLOCKED -- shared/case_readiness.py::CAP_BY_READINESS, the single
# definition 3 GPT success-probability generators (this file, digital_twin.py,
# court_predictor.py) now import instead of each redeclaring their own copy
# (Operation Single Brain, 2026-08-07 -- 3 independently-pasted copies of the
# identical dict was itself a duplicate-truth finding this mission targets).
_CAP_BY_READINESS = CAP_BY_READINESS

# Final Beta Gate F11 (MEDIUM-HIGH): risk_breakdown.overall enum + canonical
# risk mapping. See the guard applied right after hearing_score's own clamp
# in hearing_command_center below.
_VALID_RISK_OVERALL = {"NIZAK", "SREDNJI", "VISOK"}
_CANONICAL_RISK_TO_OVERALL = {"nizak": "NIZAK", "srednji": "SREDNJI", "visok": "VISOK"}

_JSON_SCHEMA = """{
  "executive_brief": "string — sažetak 3-5 rečenica za ročište",
  "timeline": ["string — 'YYYY-MM-DD — opis događaja'"],
  "win_lose_matrix": {"u_prilog": ["string"], "na_stetu": ["string"]},
  "opposing_counsel": "string — strategija protivne strane + kako kontrirati",
  "judge_attack_mode": "string — ključni pravni argumenti + zakonske reference",
  "missing_evidence": ["string — dokaz koji nedostaje"],
  "witness_analysis": "string — analiza svedoka (ko, šta zna, pouzdanost)",
  "cross_examination": ["string — pitanje za unakrsno ispitivanje"],
  "practice_pack": "string — relevantna sudska praksa i analogije",
  "hearing_checklist": ["string — stavka kontrolne liste"],
  "hearing_score": 0,
  "risk_breakdown": {"overall": "NIZAK|SREDNJI|VISOK", "factors": ["string"]}
}"""


# ─── Pydantic ─────────────────────────────────────────────────────────────────

class HearingCCReq(BaseModel):
    predmet_id:    str = Field(..., min_length=1, max_length=64)
    datum_rocista: str = Field(..., min_length=10, max_length=10)
    tip_postupka:  str = Field(..., min_length=1, max_length=20)

    @field_validator("tip_postupka")
    @classmethod
    def _val_tip(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in _VALID_TIP:
            raise ValueError(f"tip_postupka mora biti jedan od: {sorted(_VALID_TIP)}")
        return v

    @field_validator("datum_rocista")
    @classmethod
    def _val_datum(cls, v: str) -> str:
        from datetime import date
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError("datum_rocista mora biti YYYY-MM-DD")
        return v


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _first(r) -> Optional[dict]:
    return r.data[0] if r.data else None


async def _load_all_context(supa, uid: str, predmet_id: str) -> dict:
    """Program Tau, Master Sprint 006 ("Canonical Context Migration Factory"),
    Phase 4 pilot. `predmet_hronologija` (-> canonical `timeline`) and
    `predmet_dokumenti` (-> canonical `relevant_documents`, real excerpts
    instead of just filenames) are now sourced from `build_case_context()`
    (see `_dohvati_case_context_ako_postoji`/`_case_context_blok` below), not
    fetched here a 2nd time. `predmet_komentari` was fetched here but never
    read by `_build_prompt` -- dead code, removed rather than migrated (Phase
    8's own "fix everything that can be fixed" mandate).

    `predmet_klijenti` (resolved client names), `predmet_beleske` (attorney's
    own case notes), `predmet_istorija` (recent AI Q&A on this case), and
    `rocista` WITH its `vreme`/`napomena` columns are kept here deliberately —
    none has a canonical equivalent with the same fidelity (canonical
    `participants` has no client-name join; canonical `deadlines` carries no
    `vreme`/`napomena`; `predmet_beleske`/`predmet_istorija` have no canonical
    field at all). Named, not silently dropped -- see
    docs/tau/HEARING_CC_MIGRATION_REPORT.md Step 5."""
    results = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("*").eq("id", predmet_id).eq("user_id", uid).limit(1).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_klijenti")
            .select("klijent_id,klijenti(ime,prezime,firma)")
            .eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_beleske")
            .select("sadrzaj,created_at").eq("predmet_id", predmet_id)
            .eq("user_id", uid).order("created_at", desc=True).limit(15).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("pitanje,odgovor,created_at").eq("predmet_id", predmet_id)
            .eq("user_id", uid).order("created_at", desc=True).limit(10).execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("datum,vreme,sud,status,napomena").eq("predmet_id", predmet_id)
            .eq("user_id", uid).order("datum", desc=True).limit(10).execute()),
        return_exceptions=True,
    )

    def _safe(r):
        if isinstance(r, Exception):
            return []
        return r.data or []

    pred_r = results[0]
    return {
        "predmet":     _first(pred_r) if not isinstance(pred_r, Exception) else None,
        "klijenti":    _safe(results[1]),
        "beleske":     _safe(results[2]),
        "istorija":    _safe(results[3]),
        "rocista":     _safe(results[4]),
    }


async def _dohvati_case_context_ako_postoji(predmet_id: str, uid: str, supa, include_documents: bool = True) -> Optional[dict]:
    """Fail-soft canonical-context fetch -- Factory Step 1. Never raises, never
    blocks the endpoint's own pre-existing behavior. Full mode
    (`include_documents=True`) since this module's whole purpose is a
    comprehensive hearing-prep brief, the same reasoning Tau 005 applied to
    court_predictor.py's own 2 evidence-centric endpoints."""
    if not predmet_id:
        return None
    try:
        return await build_case_context(predmet_id, uid, supa, include_documents=include_documents)
    except Exception as exc:
        logger.warning("[HCC] build_case_context greška (nastavlja bez kanonskog konteksta): %s", exc)
        return None


def _case_context_blok(cc: Optional[dict]) -> str:
    """Factory Step 2 formatter -- file-local, not shared, per
    docs/tau/CANONICAL_CONTEXT_FACTORY.md's own "template the pattern, not the
    code" rule. Surfaces exactly what `_load_all_context` above can NOT
    provide: Genome, contradictions, missing evidence, open case actions,
    readiness, timeline, and real document excerpts (vs. filenames only)."""
    if not cc or cc.get("error"):
        return ""

    lines = ["STVARNO STANJE PREDMETA U SISTEMU (kanonski izvor — koristi OVO kao osnovu, ne izmišljaj suprotno):"]

    readiness = (cc.get("readiness") or {}).get("value") or {}
    if readiness.get("status"):
        lines.append(f"  Spremnost predmeta: {readiness['status']} — {readiness.get('razlog', '')}")

    genome = (cc.get("key_facts") or {}).get("value")
    if genome:
        if genome.get("snaga_predmeta_procent") is not None:
            lines.append(f"  Snaga predmeta (Genome): {genome['snaga_predmeta_procent']}%")
        nt = genome.get("najslabija_tacka") or {}
        if nt.get("rizik"):
            lines.append(f"  Najslabija tačka: {nt['rizik']}")

    missing = (cc.get("missing_evidence") or {}).get("value") or []
    if missing:
        lines.append(f"  NEDOSTAJUĆI DOKAZI ({len(missing)}, već poznato sistemu):")
        for m in missing[:5]:
            lines.append(f"    - {m.get('opis', m) if isinstance(m, dict) else m}")

    contra = (cc.get("contradictions") or {}).get("value") or []
    if contra:
        lines.append(f"  KONTRADIKCIJE ({len(contra)}):")
        for k in contra[:5]:
            lines.append(f"    - {k.get('opis', k) if isinstance(k, dict) else k}")

    actions = (cc.get("active_actions") or {}).get("value") or []
    if actions:
        lines.append("  OTVORENE AKCIJE:")
        for a in actions[:3]:
            lines.append(f"    - [{a.get('prioritet', '?')}] {a.get('razlog', '')[:150]}")

    timeline = (cc.get("timeline") or {}).get("value") or []
    if timeline:
        lines.append("  HRONOLOGIJA (kanonska):")
        for h in timeline[:8]:
            lines.append(f"    {h.get('datum_iso', '?')} — {(h.get('dogadjaj') or '')[:150]}")

    docs = ((cc.get("relevant_documents") or {}).get("value") or {})
    included = docs.get("included") or []
    if included:
        lines.append(f"  DOKUMENTI ({docs.get('total_documents', len(included))} ukupno, izvodi ispod):")
        for d in included[:8]:
            izvod = (d.get("excerpt") or "")[:400]
            lines.append(f"    - {d.get('naziv', '')}: {izvod}" if izvod else f"    - {d.get('naziv', '')}")
        not_incl = docs.get("not_included_but_retrievable") or []
        if not_incl:
            lines.append(f"    (+ još {len(not_incl)} dokumenata u dosijeu, nisu prikazani ovde)")

    return "\n".join(lines)


def _build_prompt(ctx: dict, datum_rocista: str, tip_postupka: str, case_context_blok: str = "",
                   case_context: dict | None = None) -> str:
    pred = ctx.get("predmet") or {}
    # Operation One Truth (2026-08-07): this line used to read `predmeti.rizik`, a manually-set,
    # never-recomputed column, bypassing services/risk_engine.py entirely. Now reads the live
    # value from build_case_context()'s "risk" field (added this same mission) when available,
    # falling back to the stale column only if the canonical fetch itself failed.
    _risk_val = ((case_context or {}).get("risk") or {}).get("value") or {}
    _risk_nivo = _risk_val.get("nivo") or pred.get("rizik", "—")
    lines = [
        f"TIP POSTUPKA: {tip_postupka.upper()}",
        f"DATUM ROČIŠTA: {datum_rocista}",
        "",
        f"PREDMET: {pred.get('naziv', '—')}",
        f"Opis: {(pred.get('opis') or '—')[:500]}",
        f"Status: {pred.get('status', '—')} | Rizik: {_risk_nivo}",
        f"Tužilac: {pred.get('tuzilac', '—')} | Tuženi: {pred.get('tuzeni', '—')}",
        f"Oblast: {pred.get('oblast', '—')}",
        "",
    ]

    if ctx["klijenti"]:
        lines.append("KLIJENTI:")
        for k in ctx["klijenti"]:
            kl = k.get("klijenti") or {}
            naziv = f"{kl.get('ime','')} {kl.get('prezime','')}".strip() or kl.get("firma", "?")
            lines.append(f"  - {naziv}")

    if case_context_blok:
        lines.append("\n" + case_context_blok)

    if ctx["beleske"]:
        lines.append("\nBELEŠKE:")
        for b in ctx["beleske"][:8]:
            lines.append(f"  {(b.get('created_at') or '')[:10]}: {(b.get('sadrzaj') or '')[:250]}")

    if ctx["rocista"]:
        lines.append("\nPREĐAŠNJA ROČIŠTA:")
        for r in ctx["rocista"]:
            nap = (r.get("napomena") or "")[:100]
            lines.append(f"  {r.get('datum','?')} {r.get('vreme','')} — {r.get('sud','?')} [{r.get('status','?')}]{(' — '+nap) if nap else ''}")

    if ctx["istorija"]:
        lines.append("\nISTORIJA AI UPITA (izvod):")
        for h in ctx["istorija"][:4]:
            lines.append(f"  Q: {(h.get('pitanje') or '')[:150]}")
            lines.append(f"  A: {(h.get('odgovor') or '')[:250]}")

    lines.append(f"\nGeneriši ISKLJUČIVO validan JSON objekat po sledećem šablonu:\n{_JSON_SCHEMA}")
    lines.append("Sve vrednosti moraju biti na srpskom jeziku. hearing_score mora biti integer 0-100.")
    return "\n".join(lines)


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/api/rociste/command-center")
@limiter.limit("10/minute")
async def hearing_command_center(
    body: HearingCCReq,
    request: Request,
    user: dict = Depends(PermissionService.require("hearing_prep")),
):
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    begin_cost_tracking()

    ctx, case_context = await asyncio.gather(
        _load_all_context(supa, uid, body.predmet_id),
        _dohvati_case_context_ako_postoji(body.predmet_id, uid, supa, include_documents=True),
    )
    if not ctx["predmet"]:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    case_context_blok = _case_context_blok(case_context)
    system_prompt = _SYSTEM_PROMPTS[body.tip_postupka] + (_CASE_CONTEXT_ALIGNMENT_SUFFIX if case_context_blok else "")
    user_prompt   = _build_prompt(ctx, body.datum_rocista, body.tip_postupka, case_context_blok, case_context)

    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)

    try:
        resp = await _pozovi_hcc_api(
            oai,
            model="gpt-4o",
            temperature=0.1,
            max_tokens=4000,
            timeout=120.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
        )
    except Exception as e:
        _sentry_capture(e)
        logger.error("[HCC] OpenAI greška uid=%.8s: %s", uid, e)
        raise HTTPException(status_code=503, detail="AI servis privremeno nedostupan. Pokušajte ponovo.")

    raw = (resp.choices[0].message.content or "{}").strip()
    try:
        brifing = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=503, detail="Neispravan odgovor AI servisa.")

    # BLACKSWAN-AI-003 fix (Operation Black Swan, Mission 001, AI Attack): the readiness-
    # based cap below only covers 2 of the readiness enum's values (CRITICAL_GAP, BLOCKED)
    # -- for any OTHER status (e.g. PARTIALLY_READY), an out-of-spec GPT score reached the
    # response completely unclamped. Reproduced: hearing_score=250 (spec 0-100) with
    # readiness=PARTIALLY_READY reached brifing.hearing_score in the response returned to
    # the lawyer. Basic range sanity now applies unconditionally; the stricter readiness-
    # specific cap below is additional, not a replacement.
    _score0 = brifing.get("hearing_score")
    if isinstance(_score0, (int, float)):
        brifing["hearing_score"] = max(0, min(100, _score0))

    # Factory Step 4 (GPT boundary) -- same deterministic cap Tau 005 proved
    # for court_predictor.py's win-probability, applied here to hearing_score:
    # GPT cannot claim a case is well-prepared for its hearing when the
    # canonical readiness status says otherwise. Applied AFTER parsing, so
    # no prompt-level persuasion can override it.
    if case_context and not case_context.get("error"):
        _readiness_status = ((case_context.get("readiness") or {}).get("value") or {}).get("status")
        _cap = _CAP_BY_READINESS.get(_readiness_status)
        if _cap is not None:
            _score = brifing.get("hearing_score")
            if isinstance(_score, (int, float)) and _score > _cap:
                brifing["hearing_score"] = _cap

    # Final Beta Gate F11 (MEDIUM-HIGH): risk_breakdown.overall is a SECOND,
    # independent GPT risk read in this same JSON object -- unlike its
    # sibling field hearing_score (clamped just above), it had ZERO
    # validation, so a malformed/out-of-spec value reached the lawyer
    # verbatim as a prominent colored badge with no disclosure that it's an
    # independent AI estimate (unlike cio.py's cio_preporuka, which DOES
    # carry that disclosure). 4th recurrence of the "guarded headline field,
    # missed sibling field" pattern (Genome heatmap, dokazi_rang,
    # argument_reputation were the first 3). Deliberately NOT silently
    # overwritten to match the canonical value when both are well-formed --
    # a hearing-specific risk read can legitimately diverge from the case's
    # overall risk -- but the platform value + explicit disclosure are
    # always attached so the lawyer can see them disagree instead of
    # silently trusting whichever one rendered first.
    _rb = brifing.get("risk_breakdown")
    if isinstance(_rb, dict):
        _canonical_risk_nivo = None
        if case_context and not case_context.get("error"):
            _canonical_risk_nivo = ((case_context.get("risk") or {}).get("value") or {}).get("nivo")
        _overall = _rb.get("overall")
        if not isinstance(_overall, str) or _overall.strip().upper() not in _VALID_RISK_OVERALL:
            # Fail safe to the canonical platform risk when GPT's own value is
            # missing/malformed; if even that is unavailable, fail safe to the
            # most conservative value (VISOK), never to a validation gap.
            _rb["overall"] = _CANONICAL_RISK_TO_OVERALL.get((_canonical_risk_nivo or "").lower(), "VISOK")
        else:
            _rb["overall"] = _overall.strip().upper()
        _rb["platform_risk_nivo"] = _canonical_risk_nivo
        _rb["independent_estimate"] = True

    preostalo = await UsageService.consume(uid, email, "hearing_prep")
    asyncio.create_task(log_cost_to_db(uid, "hearing_command_center"))
    asyncio.create_task(_audit(uid, "hearing_command_center", body.predmet_id[:16]))

    logger.info("[HCC] uid=%.8s predmet=%s tip=%s score=%s",
                uid, body.predmet_id, body.tip_postupka, brifing.get("hearing_score"))

    return {
        "ok":                        True,
        "predmet_id":                body.predmet_id,
        "datum_rocista":             body.datum_rocista,
        "tip_postupka":              body.tip_postupka,
        "brifing":                   brifing,
        "krediti_preostalo":         preostalo,
        "kontekst_predmeta_koriscen": bool(case_context_blok),
        # Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-025): see
        # routers/digital_twin.py's note on this same additive disclosure marker.
        "ai_generated":              True,
    }


# ─── Cross-examination generator ─────────────────────────────────────────────

class CrossExamRequest(BaseModel):
    predmet_id:    str = Field(..., min_length=1, max_length=64)
    svedok_opis:   str = Field(..., min_length=5, max_length=1000)
    tema:          str = Field(..., min_length=5, max_length=2000)
    nasa_pozicija: str = Field(..., min_length=3, max_length=500)
    tip_postupka:  str = Field("gradjanski", max_length=20)

    @field_validator("tip_postupka")
    @classmethod
    def _val_tip(cls, v: str) -> str:
        return v.lower().strip()


@router.post("/api/rociste/cross-exam")
@limiter.limit("10/minute")
async def cross_examination(
    body: CrossExamRequest,
    request: Request,
    user: dict = Depends(PermissionService.require("hearing_prep")),
):
    """Generiše listu pitanja za unakrsno ispitivanje svedoka/veštaka (1 kredit)."""
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    # Factory pilot, lightweight mode: this endpoint's reasoning task is about
    # ONE witness's testimony, not the case's own documents -- full mode
    # (Step 3's own decision rule) isn't warranted, but knowing the case's
    # real contradictions/missing evidence can sharpen which questions matter.
    case_context = await _dohvati_case_context_ako_postoji(body.predmet_id, uid, supa, include_documents=False)
    case_context_blok = _case_context_blok(case_context)

    # PROD-SYNTAX-001 (2026-08-08): this block used to be built INLINE inside
    # the f-string below, as
    #     {("\n" + case_context_blok + "\n...\n") if case_context_blok else ""}
    # A backslash inside an f-string EXPRESSION is a SyntaxError on Python
    # 3.11 and only became legal in 3.12 (PEP 701). Local dev runs 3.13, so it
    # parsed here and the whole test suite passed; production runs
    # python:3.11-slim (Dockerfile) and could not even IMPORT the module --
    # api.py's router import failed, gunicorn workers exited 3, and the
    # service never booted. Hoisted out of the f-string so the expression
    # part contains no backslash and the string is valid on both versions.
    _ctx_prompt_blok = ""
    if case_context_blok:
        _ctx_prompt_blok = (
            "\n" + case_context_blok
            + "\nAko je gornji blok dat, iskoristi poznate kontradikcije/nedostajuće "
              "dokaze da izoštriš pitanja koja tačno tim ciljaju.\n"
        )

    prompt = f"""Si iskusni parničar sa 25 godina iskustva. Pripremaš pitanja za unakrsno ispitivanje svedoka.

TIP POSTUPKA: {body.tip_postupka.upper()}
NAŠA POZICIJA: {body.nasa_pozicija}
SVEDOK (ko je, šta zna, kakva je njegova uloga): {body.svedok_opis}
TEMA SVEDOČENJA (o čemu svedoči, šta tvrdi): {body.tema}
{_ctx_prompt_blok}
Generiši listu od 15-20 preciznih pitanja za unakrsno ispitivanje ovog svedoka.

## Pitanja za utvrđivanje kredibiliteta svedoka
(Lično poznavanje, pristranost, odnos sa strankom, interes u ishodu)
1. ...

## Pitanja za utvrđivanje činjenica
(Gde je bio, šta je video/čuo/znao, redosled događaja, direktno opažanje vs. zaključak)
1. ...

## Pitanja za slabljenje iskaza
(Kontradikcije sa ranijim izjavama, nemoguće tvrdnje, šta nije video, šta nije znao)
1. ...

## Zaključna pitanja
(Finalna poenta koja potkrepljuje naš narativ)
1. ...

Za svako pitanje koje je "dvostruko sečivo" (može nas povrediti ako svedok odgovori neočekivano) dodaj ⚠️ na kraju.
Sva pitanja moraju biti zatvorena (da/ne) ili precizno usmerena — bez otvorenih pitanja.
Odgovori ISKLJUČIVO na srpskom jeziku."""

    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)

    try:
        resp = await _pozovi_hcc_api(
            oai,
            model="gpt-4o",
            temperature=0.2,
            max_tokens=2500,
            timeout=60.0,
            messages=[
                {"role": "system", "content": "Ti si elitni parničar koji priprema precizna pitanja za unakrsno ispitivanje. Odgovaraj ISKLJUČIVO na srpskom."},
                {"role": "user",   "content": prompt},
            ],
        )
    except Exception as e:
        _sentry_capture(e)
        logger.error("[CrossExam] OpenAI greška uid=%.8s: %s", uid, e)
        raise HTTPException(status_code=503, detail="AI servis privremeno nedostupan.")

    pitanja = (resp.choices[0].message.content or "").strip()

    preostalo = await UsageService.consume(uid, email, "hearing_prep")
    asyncio.create_task(_audit(uid, "cross_examination", body.predmet_id[:16]))

    logger.info("[CrossExam] uid=%.8s predmet=%s tip=%s", uid, body.predmet_id, body.tip_postupka)

    return {
        "ok":                        True,
        "predmet_id":                body.predmet_id,
        "pitanja":                   pitanja,
        "krediti_preostalo":         preostalo,
        "kontekst_predmeta_koriscen": bool(case_context_blok),
        # Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-025): see
        # routers/digital_twin.py's note on this same additive disclosure marker.
        "ai_generated":              True,
    }


# ─── Brifing export (plain text) ─────────────────────────────────────────────

class BrifingExportReq(BaseModel):
    predmet_naziv:  str = Field("Predmet", max_length=200)
    datum_rocista:  str = Field("", max_length=10)
    tip_postupka:   str = Field("", max_length=20)
    brifing:        dict


@router.post("/api/rociste/command-center/export")
@limiter.limit("20/minute")
async def export_brifing(
    body: BrifingExportReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Konvertuje brifing JSON u plain text za copy/paste ili štampanje."""
    b = body.brifing
    lines = [
        "=" * 65,
        f"ROČIŠNI BRIFING — Vindex AI",
        f"Predmet:      {body.predmet_naziv}",
        f"Datum ročišta: {body.datum_rocista}",
        f"Tip postupka: {body.tip_postupka.upper()}",
        f"Ocena spremi: {b.get('hearing_score', '—')}/100",
        "=" * 65,
        "",
        "## SAŽETAK",
        b.get("executive_brief", "—"),
        "",
    ]

    if b.get("win_lose_matrix"):
        wlm = b["win_lose_matrix"]
        lines += ["## U PRILOG"]
        for item in (wlm.get("u_prilog") or []):
            lines.append(f"  + {item}")
        lines += ["", "## NA ŠTETU"]
        for item in (wlm.get("na_stetu") or []):
            lines.append(f"  - {item}")
        lines.append("")

    if b.get("timeline"):
        lines += ["## HRONOLOGIJA"]
        for t in b["timeline"]:
            lines.append(f"  {t}")
        lines.append("")

    if b.get("opposing_counsel"):
        lines += ["## STRATEGIJA PROTIVNE STRANE", b["opposing_counsel"], ""]

    if b.get("judge_attack_mode"):
        lines += ["## KLJUČNI PRAVNI ARGUMENTI", b["judge_attack_mode"], ""]

    if b.get("witness_analysis"):
        lines += ["## ANALIZA SVEDOKA", b["witness_analysis"], ""]

    if b.get("cross_examination"):
        lines += ["## PITANJA ZA UNAKRSNO ISPITIVANJE"]
        for q in b["cross_examination"]:
            lines.append(f"  ? {q}")
        lines.append("")

    if b.get("missing_evidence"):
        lines += ["## NEDOSTAJUĆI DOKAZI"]
        for e in b["missing_evidence"]:
            lines.append(f"  ! {e}")
        lines.append("")

    if b.get("practice_pack"):
        lines += ["## SUDSKA PRAKSA", b["practice_pack"], ""]

    if b.get("hearing_checklist"):
        lines += ["## KONTROLNA LISTA"]
        for c in b["hearing_checklist"]:
            lines.append(f"  ☐ {c}")
        lines.append("")

    if b.get("risk_breakdown"):
        rb = b["risk_breakdown"]
        lines += [f"## PROCENA RIZIKA: {rb.get('overall', '—')}"]
        for f_ in (rb.get("factors") or []):
            lines.append(f"  • {f_}")
        lines.append("")

    lines += ["=" * 65, "Generisano uz pomoć Vindex AI — za informativne svrhe.", "=" * 65]

    return {"tekst": "\n".join(lines)}
