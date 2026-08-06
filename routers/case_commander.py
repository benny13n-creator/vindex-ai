# -*- coding: utf-8 -*-
"""
Vindex AI — routers/case_commander.py

Program Sigma, Master Sprint 005 (2026-08-06) — "Case Commander Consolidation
& Operational Brain Unification". Case Commander is no longer a generator of
its own decisions — it is the CANONICAL OPERATIONAL INTERFACE, displaying
truth `case_actions`/`shared/gap_engine.py`/`shared/case_readiness.py` already
computed, with GPT restricted to explaining/summarizing/rephrasing that truth
(never deciding a new one) — see `docs/sigma/GPT_BOUNDARY_POLICY.md`. Every
returned field carries `shared/commander_schema.py`'s own
{value, source, evidence, confidence, generated_by, timestamp} shape — no
field may exist without a traceable origin.

Program Sigma, Master Sprint 004's own forensic fork found this module had 8
independent GPT recommendation surfaces, none reading canonical sources
(`SIGMA-018`, Architectural Debt Register). This sprint's own forensic
re-verification (2 forks) additionally found NONE of them has a live frontend
caller today (confirmed via repo-wide grep of `static/vindex.js` — the prior
claim in `docs/omega/SHADOW_WORKFLOW_AUDIT.md` that the backend endpoints
"remain unaffected" by the 2026-08-06 dead-frontend-code removal does not hold
under direct re-verification). This made a full, careful rewrite safe to do
in one sprint — no live user is affected by the change in shape.

Endpoints:
  POST /api/commander/analiza      — canonical case snapshot + GPT explanation of 2 genuinely-advisory sections
  POST /api/commander/quick-check  — top canonical action + top canonical gaps, no independent GPT decision
  POST /api/commander/checklist    — generic procedural checklist template (GPT-templated, never claims real completion)
  GET  /api/commander/jutarnji     — portfolio-wide digest, delegates to _cross_case_analiza (now canonical-first)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService
from shared.llm_retry import llm_retry
from shared.sentry import capture_exception as _sentry_capture
from shared.commander_schema import canonical_field, gpt_advisory_field, gpt_explanation_field
from shared.case_readiness import top_open_action, READY, PARTIALLY_READY, BLOCKED, CRITICAL_GAP, UNKNOWN
from shared.case_context import build_case_context

logger = logging.getLogger("vindex.case_commander")
router = APIRouter(tags=["case-commander"])

# ── Sistem prompt — Faza 4 (GPT Boundary Policy): GPT sme SAMO da objašnjava/
# sažima/pretpostavlja o 2 polja koja nemaju kanonski izvor (protivnikova
# strategija, sudska praksa) -- NIKAD da odlučuje status/nedostatak/rizik/
# sledeći korak, koji su sada uvek čitani direktno iz case_actions/Gap
# Engine/Case Readiness Model ispod. ────────────────────────────────────────

_ADVISORY_SYSTEM = """Ti si AI pravni asistent koji SAMO daje kontekstualnu procenu za 2 tačno određena pitanja o predmetu -- ništa drugo.

Vrati ISKLJUČIVO JSON:
{
  "protivnikova_strategija": "<šta će protivna strana verovatno uraditi i zašto, 1-2 rečenice>",
  "sudska_praksa": "<relevantan pattern u sličnim predmetima -- cituj SAMO ako si siguran, inače prazan string>"
}

Ovo su procene, ne činjenice -- ne tvrdi da nešto nedostaje, ne predlaži sledeći korak, ne proceni rizik, ne odlučuj prioritet. Za to postoje drugi, deterministički izvori koje ne smeš da preformulišeš kao svoju sopstvenu odluku. Ekavica, direktan ton, bez uvodnih fraza."""

# ── Modeli ────────────────────────────────────────────────────────────────────

class CommanderRequest(BaseModel):
    predmet_id: str
    dodatni_kontekst: Optional[str] = None
    tip_analize: str = "kompletna"   # "kompletna" | "brza" | "rizici"


class ChecklistRequest(BaseModel):
    predmet_id: str
    tip_postupka: Optional[str] = None

# ── Helperi ───────────────────────────────────────────────────────────────────

async def _dohvati_predmet_kontekst(predmet_id: str, uid: str, supa) -> dict:
    """Paralelno dohvata podatke o predmetu potrebne za GPT-formatirani tekst
    (naziv/opis/rokovi/dokumenta/beleške).

    Program Tau, Master Sprint 007 ("Canonical Reasoning Consolidation"):
    `case_actions`/`dokazi`/`rocista` su ranije dohvatani ovde ISKLJUČIVO da
    nahrane `_kanonski_nalazi`-jev sopstveni, DRUGI poziv
    `calculate_procesni_rizik`/`identify_case_problems`/`collect_case_gaps`/
    `compute_case_readiness` -- iste determinističke funkcije koje
    `shared/case_context.py::build_case_context()` već poziva iznutra. Taj
    duplirani poziv je uklonjen (`_kanonski_nalazi` sada čita
    `build_case_context()`-ov već izračunat `readiness`/`missing_evidence`/
    `active_actions` direktno), pa su ova 3 dohvata postala nepotrebna i
    uklonjena su odavde. `rokovi` (NE `rocista`) i dalje nema kanonski
    ekvivalent (isti TAU-013 nalaz, sada potvrđen i u ovom fajlu) -- zadržano
    za GPT kontekst tekst."""
    pred_r, rokovi_r, dok_r, kom_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("*")
                .eq("id", predmet_id)
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("rokovi")
                .select("naziv, datum, tip, opis")
                .eq("predmet_id", predmet_id)
                .order("datum")
                .limit(10)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("naziv_fajla, created_at, tekst_sadrzaj, tip_dokaza, status")
                .eq("predmet_id", predmet_id)
                .limit(20)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_komentari")
                .select("tekst, created_at")
                .eq("predmet_id", predmet_id)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
        ),
        return_exceptions=True,
    )

    def _safe(r):
        if isinstance(r, Exception):
            return []
        return getattr(r, "data", None) or []

    def _safe_one(r):
        if isinstance(r, Exception):
            return {}
        return getattr(r, "data", None) or {}

    return {
        "predmet":      _safe_one(pred_r),
        "rokovi":       _safe(rokovi_r),
        "dokumenta":    _safe(dok_r),
        "komentari":    _safe(kom_r),
    }


_READINESS_LABEL_SR = {
    READY: "Predmet je spreman -- nema otvorenih akcija niti neotklonjenih praznina.",
    PARTIALLY_READY: "Predmet je delimično spreman -- postoje otvorene stavke nižeg prioriteta.",
    BLOCKED: "Predmet je blokiran -- nedostaje dokaz ili nerazrešena kontradikcija visokog prioriteta.",
    CRITICAL_GAP: "Predmet ima kritičan nedostatak koji zahteva hitnu pažnju.",
    UNKNOWN: "Nema dovoljno podataka da se proceni spremnost predmeta.",
}


async def _kanonski_nalazi(predmet_id: str, uid: str, supa) -> dict:
    """Program Tau, Master Sprint 007 ("Canonical Reasoning Consolidation"):
    gradi STATUS PREDMETA/NEDOSTAJE/RIZICI/PREPORUCENI POTEZ/VREMENSKI
    PRITISAK isključivo čitajući `shared/case_context.py::build_case_context()`-
    ov već izračunat `readiness`/`missing_evidence`/`active_actions` -- nula
    GPT poziva, i (za razliku od Program Sigma Master Sprint 005-ove verzije
    ovog fajla) nula DRUGOG, nezavisnog poziva
    `calculate_procesni_rizik`/`identify_case_problems`/`collect_case_gaps`/
    `compute_case_readiness` na sopstveno dohvaćenim podacima -- ISTE
    determinističke funkcije koje `build_case_context()` već poziva iznutra
    (Tau 006's own Phase 7 finding, docs/tau/FACTORY_CERTIFICATION.md).
    Nema novog helper/wrapper-a: ovo je direktan `await build_case_context(...)`
    poziv, sa inline fail-soft degradacijom, ne novi sistem.

    Svako polje umotano shared/commander_schema.py-jevim kanonskim oblikom
    (Faza 3 -- CASE_COMMANDER_RESPONSE_SCHEMA), nepromenjeno u odnosu na
    prethodnu verziju."""
    try:
        cc = await build_case_context(predmet_id, uid, supa, include_documents=False)
    except Exception as exc:
        logger.warning("[COMMANDER] build_case_context greška (degradira na UNKNOWN): %s", exc)
        cc = None

    if not cc or cc.get("error"):
        readiness = {"status": UNKNOWN, "razlog": "Kanonski kontekst nije dostupan.", "izvor": []}
        missing = []
        open_actions = []
    else:
        readiness = (cc.get("readiness") or {}).get("value") or {"status": UNKNOWN, "razlog": "", "izvor": []}
        missing = (cc.get("missing_evidence") or {}).get("value") or []
        open_actions = (cc.get("active_actions") or {}).get("value") or []

    status_predmeta = canonical_field(
        _READINESS_LABEL_SR.get(readiness["status"], readiness["razlog"]),
        source="case_readiness", evidence=readiness.get("izvor"), confidence="visoka",
    )

    # Program Tau, Master Sprint 007: `nedostaje` sada obuhvata SVE
    # missing_evidence stavke (nije više uže filtrirano na 3 od 5
    # gap_engine tip vrednosti kao pre migracije) -- ispravlja nenamerno
    # isključivanje KRITICAN_ROK/PREDSTOJECI_ROKOVI stavki iz starije
    # verzije (docs/tau/PARALLEL_REASONING_AUDIT.md Finding 2), ne novo
    # ponašanje smišljeno ovaj sprint.
    nedostaje = [
        canonical_field(
            g["razlog"], source=g["izvor"], evidence=g.get("dedupe_key"),
            confidence=g["pouzdanost"],
        )
        for g in missing
    ]

    # `rizici` rekonstruiše STARO ponašanje (samo identify_case_problems-ova
    # stavke) filtriranjem već-izračunatog `missing_evidence`-a po njegovom
    # sopstvenom `izvor` polju -- ne poziva identify_case_problems ponovo.
    # Ovo takođe ispravlja Finding 3 (stari `rizici` je koristio bineran
    # "kritican"->visoka/ostalo->srednja umesto gap_engine-ove kanonske
    # {"kritican":visoka,"vazan":visoka,"info":srednja} mape -- sada
    # dosledno sa `nedostaje`, ne dva različita pravila za isti nalaz).
    rizici = [
        canonical_field(g["razlog"], source=g["izvor"], evidence=g.get("dedupe_key"), confidence=g["pouzdanost"])
        for g in missing
        if g.get("izvor") == "identify_case_problems"
    ]

    top = top_open_action(open_actions)
    if top:
        preporuceni_potez = canonical_field(
            top.get("razlog") or "", source="case_actions", evidence=top.get("dedupe_key"),
            confidence="visoka",
        )
    else:
        preporuceni_potez = canonical_field(
            "Nema otvorenih akcija -- nije identifikovan sledeći korak.",
            source="case_actions", evidence=None, confidence="visoka",
        )

    rokovi_sa_datumom = [a for a in open_actions if a.get("rok")]
    if rokovi_sa_datumom:
        najbliza = min(rokovi_sa_datumom, key=lambda a: a["rok"])
        vremenski_pritisak = canonical_field(
            f"Rok: {najbliza['rok']} -- {najbliza.get('razlog', '')}",
            source="case_actions", evidence=najbliza.get("dedupe_key"), confidence="visoka",
        )
    else:
        vremenski_pritisak = canonical_field(
            "Nema evidentiranih rokova sa otvorenom akcijom.",
            source="case_actions", evidence=None, confidence="visoka",
        )

    return {
        "status_predmeta":    status_predmeta,
        "readiness_status":   readiness["status"],
        "nedostaje":          nedostaje,
        "rizici":             rizici,
        "preporuceni_potez":  preporuceni_potez,
        "vremenski_pritisak": vremenski_pritisak,
    }


# CELINA 2 (2026-07-24): budžet za sadržaj dokumenata u kontekstu -- deljen
# preko svih dokumenata (ne flat po-dokumentu limit) da bi prva 2-3
# dokumenta ne pojela ceo budžet i ostavila ostatak potpuno bez sadržaja.
_KONTEKST_DOK_MAX_TOTAL_CHARS = 8000
_KONTEKST_DOK_MAX_PER_DOC = 2000


def _formatiraj_kontekst(ctx: dict, dodatni: str = "") -> str:
    """Formatira podatke o predmetu u citljiv tekst za AI."""
    p = ctx["predmet"]

    lines = [
        f"NAZIV PREDMETA: {p.get('naziv', 'N/A')}",
        f"STATUS: {p.get('status', 'N/A')}",
        f"STRANKA: {p.get('stranka', 'N/A')}",
        f"PROTIVNIK: {p.get('protivnik', 'N/A')}",
        f"TIP POSTUPKA: {p.get('tip_postupka') or p.get('oblast', 'N/A')}",
        f"SUD: {p.get('sud', 'N/A')}",
        f"VREDNOST SPORA: {p.get('vrednost_spora') or p.get('vrednost', 'N/A')}",
    ]

    if p.get("opis") or p.get("napomena"):
        opis = (p.get("opis") or p.get("napomena") or "")[:500]
        lines.append(f"OPIS: {opis}")

    if ctx["rokovi"]:
        lines.append(f"\nROKOVI ({len(ctx['rokovi'])}):")
        for r in ctx["rokovi"]:
            datum = str(r.get("datum", "N/A"))[:10]
            opis  = (r.get("opis") or "")[:80]
            lines.append(f"  - {r.get('naziv', 'Rok')} | {datum}" + (f" | {opis}" if opis else ""))
    else:
        lines.append("\nROKOVI: Nema unetih rokova")

    if ctx["dokumenta"]:
        lines.append(f"\nDOKUMENTA U SISTEMU ({len(ctx['dokumenta'])}):")
        total_chars = 0
        for d in ctx["dokumenta"][:10]:
            naziv = d.get("naziv_fajla", "N/A")
            tekst = (d.get("tekst_sadrzaj") or "").strip()
            if tekst and total_chars < _KONTEKST_DOK_MAX_TOTAL_CHARS:
                budzet = min(_KONTEKST_DOK_MAX_PER_DOC, _KONTEKST_DOK_MAX_TOTAL_CHARS - total_chars)
                izvod = tekst[:budzet]
                total_chars += len(izvod)
                lines.append(f"  - {naziv}:\n    {izvod}")
            elif tekst:
                lines.append(f"  - {naziv} (sadržaj nije prikazan — dostignut budžet konteksta)")
            else:
                lines.append(f"  - {naziv} (bez ekstrahovanog teksta)")
    else:
        lines.append("\nDOKUMENTA: Nema uploadovanih dokumenata")

    if ctx["komentari"]:
        lines.append("\nPOSLEDNJA BELEZKA:")
        lines.append(f"  {ctx['komentari'][0].get('tekst', '')[:300]}")

    if dodatni:
        lines.append(f"\nDODATNI KONTEKST OD ADVOKATA: {dodatni}")

    return "\n".join(lines)


@llm_retry
def _pozovi_commander_api(oai_client, model: str, messages: list, max_tokens: int, temperature: float) -> str:
    """CELINA 2 (2026-07-24): zajednički retry-ovani OpenAI poziv za sve
    Case Commander endpoint-e (analiza/quick-check/checklist)."""
    resp = oai_client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=25.0,
    )
    return resp.choices[0].message.content.strip()


# ── Endpointi ─────────────────────────────────────────────────────────────────

@router.post("/api/commander/analiza")
@limiter.limit("15/minute")
async def commander_analiza(
    request: Request,
    payload: CommanderRequest,
    user: dict = Depends(PermissionService.require("case_commander")),
):
    """
    Kompletna analiza predmeta — Chief of Staff izvestaj.

    Program Sigma, Master Sprint 005 (2026-08-06): Case Commander više NE
    odlučuje sam šta nedostaje/koji su rizici/koji je sledeći potez/da li
    postoji vremenski pritisak — sve to sada čita direktno iz case_actions/
    Gap Engine/Case Readiness Model (`_kanonski_nalazi`, nula GPT poziva za
    ta polja). GPT poziv koji ostaje je namerno sužen na TAČNO 2 polja koja
    nemaju kanonski izvor (protivnikova strategija, sudska praksa) — Faza 4
    (GPT Boundary Policy). Svako vraćeno polje nosi shared/commander_schema.py's
    own {value, source, evidence, confidence, generated_by, timestamp} oblik.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Program Tau, Master Sprint 007, Phase 7 (Performance): the bespoke fetch
    # and the canonical fetch are independent -- run concurrently instead of
    # sequentially (found during this sprint's own performance measurement,
    # fixed immediately rather than left as a named-but-unfixed finding).
    ctx, kanonsko = await asyncio.gather(
        _dohvati_predmet_kontekst(payload.predmet_id, uid, supa),
        _kanonski_nalazi(payload.predmet_id, uid, supa),
    )

    if not ctx["predmet"]:
        raise HTTPException(status_code=404, detail="Predmet nije pronadjen.")

    predmet_tekst = _formatiraj_kontekst(ctx, payload.dodatni_kontekst or "")
    model = "gpt-4o" if payload.tip_analize in ("kompletna", "rizici") else "gpt-4o-mini"

    protivnikova_strategija = gpt_advisory_field("", model)
    sudska_praksa = gpt_advisory_field("", model)
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        raw = await asyncio.to_thread(
            _pozovi_commander_api, oai, model,
            [
                {"role": "system", "content": _ADVISORY_SYSTEM},
                {"role": "user",   "content": f"Predmet:\n\n{predmet_tekst}"},
            ],
            500, 0.3,
        )
        advisory = json.loads(raw)
        protivnikova_strategija = gpt_advisory_field(advisory.get("protivnikova_strategija", ""), model)
        sudska_praksa = gpt_advisory_field(advisory.get("sudska_praksa", ""), model)
    except Exception as exc:
        _sentry_capture(exc)
        logger.warning("[COMMANDER] Advisory (protivnik/praksa) greška, nastavlja bez njih: %s", exc)

    odgovor = {
        "predmet_id":              payload.predmet_id,
        "predmet_naziv":           ctx["predmet"].get("naziv", ""),
        "tip_analize":             payload.tip_analize,
        "model":                   model,
        "status_predmeta":        kanonsko["status_predmeta"],
        "readiness_status":       kanonsko["readiness_status"],
        "nedostaje":              kanonsko["nedostaje"],
        "rizici":                 kanonsko["rizici"],
        "preporuceni_potez":      kanonsko["preporuceni_potez"],
        "vremenski_pritisak":     kanonsko["vremenski_pritisak"],
        "protivnikova_strategija": protivnikova_strategija,
        "sudska_praksa":          sudska_praksa,
    }

    # Sacuvaj analizu u bazu (ignorisi gresku ako tabela ne postoji)
    try:
        await asyncio.to_thread(
            lambda: supa.table("commander_analize").insert({
                "user_id":    uid,
                "predmet_id": payload.predmet_id,
                "analiza":    json.dumps(odgovor, ensure_ascii=False, default=str)[:8000],
                "tip":        payload.tip_analize,
            }).execute()
        )
    except Exception:
        pass

    await UsageService.consume(uid, user.get("email", ""), "case_commander")

    return odgovor


@router.post("/api/commander/quick-check")
@limiter.limit("30/minute")
async def commander_quick_check(
    request: Request,
    payload: CommanderRequest,
    user: dict = Depends(PermissionService.require("case_commander")),
):
    """
    Brza provera predmeta — do 3 najhitnija nalaza.

    Program Sigma, Master Sprint 005 (2026-08-06): više NE poziva GPT da
    "izmisli" 3 upozorenja iz sirovog konteksta — čita ih direktno iz
    `_kanonski_nalazi` (case_actions/Gap Engine, sortirano po kanonskom
    prioritetu), isti izvor kao `commander_analiza`. Nema GPT poziva u ovom
    endpoint-u uopšte -- brzo, deterministički, bez rizika od izmišljenog nalaza.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Program Tau, Master Sprint 007, Phase 7 (Performance): the bespoke fetch
    # and the canonical fetch are independent -- run concurrently instead of
    # sequentially (found during this sprint's own performance measurement,
    # fixed immediately rather than left as a named-but-unfixed finding).
    ctx, kanonsko = await asyncio.gather(
        _dohvati_predmet_kontekst(payload.predmet_id, uid, supa),
        _kanonski_nalazi(payload.predmet_id, uid, supa),
    )

    if not ctx["predmet"]:
        raise HTTPException(status_code=404, detail="Predmet nije pronadjen.")
    kandidati = [kanonsko["preporuceni_potez"]] + kanonsko["rizici"] + kanonsko["nedostaje"]
    upozorenja = [k for k in kandidati if k["value"]][:3]

    await UsageService.consume(uid, user.get("email", ""), "case_commander")

    return {
        "upozorenja":    upozorenja,
        "predmet_id":    payload.predmet_id,
        "predmet_naziv": ctx["predmet"].get("naziv", ""),
    }


@router.post("/api/commander/checklist")
@limiter.limit("20/minute")
async def commander_checklist(
    request: Request,
    payload: ChecklistRequest,
    user: dict = Depends(PermissionService.require("case_commander")),
):
    """
    Generise proceduranu checklist za predmet.
    Grupisana po fazama: Priprema → Tuzba/Odgovor → Postupak → Zakljucenje.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    ctx = await _dohvati_predmet_kontekst(payload.predmet_id, uid, supa)

    if not ctx["predmet"]:
        raise HTTPException(status_code=404, detail="Predmet nije pronadjen.")

    p   = ctx["predmet"]
    tip = (
        payload.tip_postupka
        or p.get("tip_postupka")
        or p.get("oblast")
        or "gradjansko"
    )
    predmet_tekst = _formatiraj_kontekst(ctx)

    from openai import OpenAI
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    try:
        checklist_tekst = await asyncio.to_thread(
            _pozovi_commander_api, oai, "gpt-4o-mini",
            [{
                "role": "user",
                "content": (
                    f"Napravi kompletnu proceduralnu checklist za {tip} predmet. "
                    "Svaka stavka je konkretna akcija (markdown checkbox format). "
                    "Grupisi u faze: ## Priprema, ## Podnesak/Tuzba, ## Tok postupka, ## Zakljucenje. "
                    "Ekavica.\n\n"
                    + predmet_tekst
                ),
            }],
            900, 0.3,
        )
    except Exception as exc:
        _sentry_capture(exc)
        logger.error("[COMMANDER] Checklist greška: %s", exc)
        raise HTTPException(status_code=502, detail="AI servis trenutno nedostupan. Pokušajte ponovo.")

    # Program Sigma, Master Sprint 005 (2026-08-06) — Faza 4 (GPT Boundary
    # Policy): "completed" ranije uzimao GPT-ov sopstveni [x]/[ ] marker kao
    # istinu — GPT nema NIKAKAV uvid u stvarno stanje predmeta (ovo je
    # generički proceduralni template, ne per-fact nalaz), pa je tvrdnja
    # "ovo je završeno" bila čista izmišljotina bez ijednog dokaza. Ovaj
    # endpoint sada uvek vraća completed=False za SVAKU stavku — GPT sme da
    # predloži KOJE korake predmet tipa X obično zahteva (objašnjenje/
    # template), nikad da tvrdi da je jedan od njih već urađen.
    stavke = []
    for linija in checklist_tekst.split("\n"):
        l = linija.strip()
        if l.startswith("- [ ]") or l.startswith("- [x]") or l.startswith("- [X]"):
            stavke.append({
                "text":      l[5:].strip(),
                "completed": False,
            })

    await UsageService.consume(uid, user.get("email", ""), "case_commander")

    return {
        "checklist_tekst": checklist_tekst,
        "stavke":          stavke,
        "ukupno":          len(stavke),
        "predmet_id":      payload.predmet_id,
        "tip_postupka":    tip,
    }


# ── AI Command Center — Jutarnji brifing ──────────────────────────────────────

async def _dohvati_sve_predmete_za_analizu(user_id: str) -> dict:
    """Paralelno dohvata sve aktivne predmete + rokove/dokumente/komentare iz
    30/7 dana za GPT kontekst tekst, plus (Program Tau, Master Sprint 007)
    kanonski `readiness`/otvorene akcije za SVAKI predmet preko
    `build_case_context()` -- isti obrazac koji `morning_briefing.py` (Tau
    002) već koristi za portfolio-wide digest (lightweight mode, petlja
    preko prikazanih predmeta). Ranije je ovaj fajl sam pozivao
    `compute_case_readiness(actions, [])` sa PRAZNOM listom gaps-ova (vidi
    docs/tau/PARALLEL_REASONING_AUDIT.md Finding 4) -- portfolio prioritet
    je bio jedini u čitavoj 6-modulnoj porodici koji NIJE bio svestan
    Genome kontradikcija/nedostajućih dokaza. Migracija na
    build_case_context() ispravlja i to, ne samo uklanja duplikaciju."""
    from datetime import datetime, timedelta

    danas     = datetime.now().date()
    za_30     = (danas + timedelta(days=30)).isoformat()
    pre_7     = (datetime.now() - timedelta(days=7)).isoformat()
    supa      = _get_supa()

    predmeti_r, rokovi_r, dokumenti_r, komentari_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id, naziv, opis, status, tip_postupka, protivnik, sud, vrednost_spora, created_at")
            .eq("user_id", user_id).eq("status", "aktivan")
            .order("created_at", desc=True).limit(20).execute()),
        asyncio.to_thread(lambda: supa.table("rokovi")
            .select("id, naziv, datum, opis, predmet_id, status")
            .eq("user_id", user_id)
            .gte("datum", danas.isoformat()).lte("datum", za_30)
            .order("datum").limit(50).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
            .select("id, naziv_fajla, predmet_id, created_at")
            .eq("user_id", user_id)
            .gte("created_at", pre_7)
            .order("created_at", desc=True).limit(30).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_komentari")
            .select("id, tekst, predmet_id, created_at")
            .eq("user_id", user_id)
            .gte("created_at", pre_7)
            .order("created_at", desc=True).limit(20).execute()),
        return_exceptions=True,
    )

    def _d(r):
        if isinstance(r, Exception):
            return []
        return getattr(r, "data", None) or []

    predmeti  = _d(predmeti_r)
    rokovi    = _d(rokovi_r)
    dokumenti = _d(dokumenti_r)
    komentari = _d(komentari_r)

    predmeti_map = {p["id"]: {**p, "rokovi": [], "dokumenti": [], "komentari": [], "case_actions": [], "_readiness": {"status": UNKNOWN, "razlog": "Kanonski kontekst nije dostupan.", "izvor": []}} for p in predmeti}
    for r in rokovi:
        if r.get("predmet_id") in predmeti_map:
            predmeti_map[r["predmet_id"]]["rokovi"].append(r)
    for d in dokumenti:
        if d.get("predmet_id") in predmeti_map:
            predmeti_map[d["predmet_id"]]["dokumenti"].append(d)
    for k in komentari:
        if k.get("predmet_id") in predmeti_map:
            predmeti_map[k["predmet_id"]]["komentari"].append(k)

    if predmeti:
        cc_results = await asyncio.gather(
            *[build_case_context(p["id"], user_id, supa, include_documents=False) for p in predmeti],
            return_exceptions=True,
        )
        for p, cc in zip(predmeti, cc_results):
            if isinstance(cc, Exception) or not cc or cc.get("error"):
                continue
            predmeti_map[p["id"]]["case_actions"] = (cc.get("active_actions") or {}).get("value") or []
            predmeti_map[p["id"]]["_readiness"] = (cc.get("readiness") or {}).get("value") or {"status": UNKNOWN, "razlog": "Kanonski kontekst nije dostupan.", "izvor": []}

    return {
        "predmeti":           list(predmeti_map.values()),
        "ukupno_rokova":      len(rokovi),
        "ukupno_dokumentata": len(dokumenti),
    }


@llm_retry
def _pozovi_cross_case_api(oai_client, prompt: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo _cross_case_analiza. oai_client
    je sinhroni OpenAI klijent (isti kao ostatak ovog fajla) -- pozivalac ga
    dispečuje preko asyncio.to_thread, ne await-uje direktno."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Ti si AI pravni operativni asistent. Odgovaraš SAMO validnim JSON-om. Ekavica."},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=1500,
        temperature=0.3,
        timeout=25.0,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content.strip()


_READINESS_RANK = {CRITICAL_GAP: 0, BLOCKED: 1, PARTIALLY_READY: 2, READY: 3, UNKNOWN: 4}


def _kanonski_prioritet_i_rizici(predmeti: list[dict]) -> tuple[Optional[dict], list[dict]]:
    """Program Sigma, Master Sprint 005 (2026-08-06) — zamenjuje GPT-ovo
    sopstveno nagađanje "koji JEDAN predmet treba da bude prioritet danas"
    (bilo `_cross_case_analiza`'s own item 4, live nalaz Sprinta 004's own
    forenzičkog foreka) determinističkim rangiranjem preko
    shared/case_readiness.py -- isti modul, ista logika koju case_actions/
    Workspace već koriste, ne novi algoritam. Takođe zamenjuje GPT-ovo
    sopstveno "RIZICI" nalaženje čitanjem case_actions direktno.

    Program Tau, Master Sprint 007: `readiness` se više NE računa ovde
    pozivom `compute_case_readiness(actions, [])` (koji je uvek prosleđivao
    PRAZNU listu gaps-ova -- Genome-slep prioritet, PARALLEL_REASONING_AUDIT.md
    Finding 4) -- svaki `p` dict sada već nosi `_readiness`, izračunat JEDNOM
    u `_dohvati_sve_predmete_za_analizu` preko `build_case_context()` (pravi
    gaps, ne prazna lista). Ova funkcija samo čita, ne računa ponovo."""
    from shared.attention_priority import canonical_sort_key

    if not predmeti:
        return None, []

    ranked = []
    for p in predmeti:
        actions = p.get("case_actions") or []
        readiness = p.get("_readiness") or {"status": UNKNOWN, "razlog": "Kanonski kontekst nije dostupan.", "izvor": []}
        top = top_open_action(actions)
        rok = (top.get("rok") if top else None) or "9999-99-99"
        ranked.append((_READINESS_RANK.get(readiness["status"], 5), rok, p, readiness, top))
    ranked.sort(key=lambda t: (t[0], t[1]))

    prioritet = None
    _, _, top_predmet, top_readiness, top_action = ranked[0]
    if top_readiness["status"] != READY:
        razlog = (top_action.get("razlog") if top_action else None) or top_readiness["razlog"]
        if top_action and top_action.get("dedupe_key"):
            evidence = top_action["dedupe_key"]
        elif top_readiness.get("izvor"):
            evidence = top_readiness["izvor"][0]
        else:
            evidence = None
        prioritet = {
            "predmet_naziv": top_predmet.get("naziv", ""),
            "predmet_id_prefix": top_predmet["id"][:8],
            "razlog": razlog,
            "source": "case_readiness",
            "evidence": evidence,
        }

    svi_open_actions = []
    for p in predmeti:
        for a in (p.get("case_actions") or []):
            svi_open_actions.append((p, a))
    svi_open_actions.sort(key=lambda pa: canonical_sort_key(pa[1].get("prioritet")))

    rizici = []
    for p, a in svi_open_actions[:5]:
        rizici.append({
            "tip": "rizik",
            "predmet_naziv": p.get("naziv", ""),
            "predmet_id_prefix": p["id"][:8],
            "naslov": (a.get("razlog") or "")[:60],
            "opis": (a.get("razlog") or "")[:200],
            "source": "case_actions",
            "evidence": a.get("dedupe_key"),
        })

    return prioritet, rizici


async def _cross_case_analiza(podaci: dict, ime_korisnika: str) -> dict:
    """Program Sigma, Master Sprint 005 (2026-08-06): PRIORITET i RIZICI su
    sada isključivo deterministički (case_actions + shared/case_readiness.py,
    vidi `_kanonski_prioritet_i_rizici` iznad) -- GPT-4o poziv koji ostaje je
    namerno sužen na TAČNO 2 kategorije koje nemaju kanonski izvor
    (kontradikcije između beleški/dokumenata, nepovezani dokumenti), obe
    vraćene kao gpt_advisory (hipoteza, ne činjenica — vidi
    shared/commander_schema.py). Faza 4 (GPT Boundary Policy)."""
    from datetime import datetime, timedelta
    from openai import OpenAI

    predmeti = podaci["predmeti"]
    n = len(predmeti)

    if n == 0:
        return {
            "nalazeni": False,
            "rezime": "",
            "nalazi": [],
            "prioritet": None,
            "statistike": {"aktivnih": 0, "rizika": 0, "kontradikcija": 0, "nepovezanih": 0, "rokova_hitnih": 0},
        }

    prioritet, rizik_nalazi = _kanonski_prioritet_i_rizici(predmeti)

    predmeti_txt = ""
    for p in predmeti:
        predmeti_txt += f"\n--- PREDMET: {p['naziv']} (ID: {p['id'][:8]}) ---\n"
        predmeti_txt += f"Tip: {p.get('tip_postupka','?')} | Protivnik: {p.get('protivnik','?')} | Sud: {p.get('sud','?')}\n"
        if p.get("opis"):
            predmeti_txt += f"Opis: {p['opis'][:300]}\n"
        if p["rokovi"]:
            predmeti_txt += "Rokovi: " + ", ".join(
                f"{r['naziv']} ({r['datum']})" for r in p["rokovi"][:5]
            ) + "\n"
        if p["dokumenti"]:
            predmeti_txt += "Novi dokumenti: " + ", ".join(d["naziv"] for d in p["dokumenti"][:5]) + "\n"
        if p["komentari"]:
            predmeti_txt += "Beleške: " + " | ".join(
                (k.get("sadrzaj") or k.get("tekst") or "")[:100] for k in p["komentari"][:3]
            ) + "\n"

    danas_str = datetime.now().strftime("%d.%m.%Y")

    prompt = f"""Analiziraj sledeće aktivne pravne predmete advokata {ime_korisnika} (datum: {danas_str}), ISKLJUČIVO za 2 pitanja -- rizik i prioritet dolaze iz drugog, determinističkog izvora i ne treba da ih proceniš:

{predmeti_txt}

Identifikuj:
1. KONTRADIKCIJE — protivrečnosti unutar jednog predmeta ili između beleški i dokumenta (max 3)
2. NEPOVEZANI DOKUMENTI — dokumenti uploadovani u poslednjih 7 dana koji nisu pomenuti u rokovima niti belešci (max 3)

Odgovori SAMO validnim JSON-om:

{{
  "nalazi": [
    {{
      "tip": "kontradikcija" ili "nepovezan_dokument",
      "predmet_naziv": "naziv predmeta",
      "predmet_id_prefix": "prva 8 slova ID-a",
      "naslov": "kratak naslov nalaza (max 60 karaktera)",
      "opis": "konkretan opis (max 200 karaktera)"
    }}
  ],
  "rezime": "jedna rečenica koja opisuje opšte stanje svih predmeta (max 120 karaktera)"
}}

Pravila: Budi konkretan. Ako nema stvarnih nalaza, vrati praznu listu. Ekavica obavezna. tip mora biti tačno: kontradikcija | nepovezan_dokument"""

    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    try:
        # Program Gamma (2026-08-04) -- ovaj poziv je bio jedan od 7 AI-odluka
        # endpointa (4 fajla) bez ijedne provenance karike -- ista klasa koju
        # je Program Beta popravio za compare_docs.
        from shared.ai_provenance import case_context as _ai_case_ctx
        with _ai_case_ctx(module_name="case_commander", operation_name="cross_case_analiza"):
            raw = await asyncio.to_thread(_pozovi_cross_case_api, oai, prompt)
        analiza = json.loads(raw)
        gpt_nalazi = analiza.get("nalazi", [])
        rezime = analiza.get("rezime", "")
        gpt_greska = False
    except Exception as exc:
        # CELINA 2 (2026-07-24): ovaj poziv ranije nije imao try/except --
        # jutarnji brifing ("srce platforme", učitava se za svakog korisnika)
        # bi pukao sa 500 na SVAKI prolazni GPT hiccup. Fail-soft: nastavlja
        # sa kanonskim prioritet/rizik nalazima čak i ako GPT-ov sopstveni
        # (sada opcioni) advisory sloj padne -- ranije je CEO brifing padao
        # zbog OVOG poziva, iako je danas taj poziv odgovoran samo za 2 od
        # ukupno 3 kategorije nalaza.
        _sentry_capture(exc)
        logger.warning("[COMMANDER] Cross-case GPT advisory greška (nastavlja sa kanonskim nalazima): %s", exc)
        gpt_nalazi = []
        rezime = ""
        gpt_greska = True

    # Program Gamma (2026-08-04) -- "kontradikcija"/"nepovezan_dokument"
    # nalazi su ranije vraceni bez ijedne provere da li stvarno referenciraju
    # jedan od predmeta koji su ANALIZIRANI -- isti "izmisljena referenca"
    # rizik koji validate_dok_reference/validate_graph_edge_references vec
    # pokrivaju za Compare/Evidence Graph, ovde prosiren na predmet_id_prefix
    # referencu. Sada primenjeno SAMO na preostale 2 GPT-only kategorije --
    # prioritet/rizik su deterministicki i ne mogu "halucinirati" referencu.
    hard_flags = []
    try:
        from shared.genome_validator import validate_predmet_reference
        poznati = {p["id"][:8]: p.get("naziv", "") for p in predmeti}
        for nalaz in gpt_nalazi:
            hard_flags.extend(validate_predmet_reference(
                nalaz.get("predmet_id_prefix"), poznati, nalaz.get("predmet_naziv"),
            ))
        evidence_check = {"odluka": "require_review" if hard_flags else "approve", "hard_flags": hard_flags, "soft_flags": []}
    except Exception as exc_ev:
        _sentry_capture(exc_ev)
        logger.warning("[COMMANDER] evidence-check greska (nije fatalno): %s", exc_ev)
        evidence_check = None

    nalazi = list(rizik_nalazi) + [
        {**nalaz, "source": "gpt_advisory", "evidence": None} for nalaz in gpt_nalazi
    ]

    za_7  = (datetime.now().date() + timedelta(days=7)).isoformat()
    hitni = [r for p in predmeti for r in p["rokovi"] if r.get("datum", "") <= za_7]

    # Program Sigma, Master Sprint 005 (2026-08-06): "nalazeni" now reflects
    # actual content (any deterministic prioritet/rizik, or any surviving
    # GPT-advisory nalaz) instead of unconditionally True whenever n>0 -- a
    # real behavior IMPROVEMENT over the pre-sprint version: a total GPT
    # outage no longer empties the whole brief, since prioritet/rizici are
    # computed BEFORE the GPT call and don't depend on it. "greska" still
    # separately flags whether the GPT-only advisory layer specifically failed.
    return {
        "nalazeni": bool(prioritet or nalazi),
        "greska": gpt_greska,
        "rezime":   rezime,
        "nalazi":   nalazi,
        "prioritet": prioritet,
        "_evidence_check": evidence_check,
        "statistike": {
            "aktivnih":      n,
            "rizika":        sum(1 for f in nalazi if f["tip"] == "rizik"),
            "kontradikcija": sum(1 for f in nalazi if f["tip"] == "kontradikcija"),
            "nepovezanih":   sum(1 for f in nalazi if f["tip"] == "nepovezan_dokument"),
            "rokova_hitnih": len(hitni),
        },
    }


@router.get("/api/commander/jutarnji")
async def commander_jutarnji(
    user: dict = Depends(PermissionService.require("case_commander")),
):
    """
    AI Command Center jutarnji brifing — portfolio-wide pregled.

    Program Omega, Sprint 004 (2026-08-06) — Unified Legal Workspace: ovaj
    endpoint više nije "srce platforme" (stara samo-opisna tvrdnja). Kanonski
    odgovor na "šta advokat vidi kada otvori Vindex AI" je `GET /api/workspace`
    (deterministički, sourced, services/case_evolution.py::
    _consequence_refresh_case_actions) — vidi docs/omega/CANONICAL_WORKSPACE_SPEC.md.

    Program Sigma, Master Sprint 005 (2026-08-06) — Case Commander Consolidation:
    ovaj endpoint više NIJE čisto GPT-generisana narativna perspektiva —
    delegira na `_cross_case_analiza`, čiji PRIORITET i RIZICI nalazi su sada
    deterministički (case_actions + shared/case_readiness.py); jedino
    KONTRADIKCIJE/NEPOVEZANI DOKUMENTI ostaju GPT-only, eksplicitno tagovani
    kao gpt_advisory (hipoteza, ne činjenica). I dalje dopunski sloj uz
    GET /api/workspace, ne njegova zamena.

    Keširan po korisniku za tekući dan. Analizira SVE aktivne predmete odjednom.
    Prioritet i rizici su sada čitani direktno iz case_actions; kontradikcije i
    nepovezani dokumenti ostaju GPT procena.
    0 kredita — uključeno u pretplatu.
    """
    from datetime import datetime, date

    uid   = user["user_id"]
    danas = date.today().isoformat()
    supa  = _get_supa()

    cached = await asyncio.to_thread(
        lambda: supa.table("commander_jutarnji")
            .select("brifing")
            .eq("user_id", uid)
            .eq("datum", danas)
            .limit(1)
            .execute()
    )
    if cached.data:
        return cached.data[0]["brifing"]

    korisnik_r = await asyncio.to_thread(
        lambda: supa.table("profiles")
            .select("email")
            .eq("id", uid)
            .maybe_single()
            .execute()
    )
    k   = (korisnik_r.data if not isinstance(korisnik_r, Exception) else None) or {}
    ime = k.get("email", "").split("@")[0] or "advokate"

    sat = datetime.now().hour
    if sat < 12:
        pozdrav_prefix = "Dobro jutro"
    elif sat < 18:
        pozdrav_prefix = "Dobar dan"
    else:
        pozdrav_prefix = "Dobro veče"

    podaci  = await _dohvati_sve_predmete_za_analizu(uid)
    n       = len(podaci["predmeti"])
    analiza = await _cross_case_analiza(podaci, ime)

    # _cross_case_analiza vraca rano (bez GPT poziva) kada n == 0 — ne naplacuj kredit tada.
    if n > 0:
        await UsageService.consume(uid, user.get("email", ""), "case_commander")

    if n == 0:
        poruka = "Još uvek nemaš aktivnih predmeta. Dodaj prvi predmet da bi AI Command Center počeo da radi."
    elif n == 1:
        poruka = "Analizirao sam tvoj aktivan predmet."
    else:
        poruka = f"Analizirao sam svih {n} aktivnih predmeta."

    brifing = {
        "pozdrav":      f"{pozdrav_prefix}, {ime}.",
        "poruka":       poruka,
        "datum":        danas,
        "generisan_u":  datetime.now().isoformat(),
        **analiza,
    }

    try:
        await asyncio.to_thread(
            lambda: supa.table("commander_jutarnji")
                .upsert({"user_id": uid, "datum": danas, "brifing": brifing},
                        on_conflict="user_id,datum")
                .execute()
        )
    except Exception:
        pass

    return brifing


@router.post("/api/commander/jutarnji/refresh")
async def commander_jutarnji_refresh(
    user: dict = Depends(PermissionService.require("case_commander")),
):
    """Briše keš za danas i generiše novi brifing (redirect na GET, koji naplacuje kredit)."""
    from datetime import date
    from fastapi.responses import RedirectResponse

    uid  = user["user_id"]
    supa = _get_supa()

    try:
        await asyncio.to_thread(
            lambda: supa.table("commander_jutarnji")
                .delete()
                .eq("user_id", uid)
                .eq("datum", date.today().isoformat())
                .execute()
        )
    except Exception:
        pass

    return RedirectResponse(url="/api/commander/jutarnji", status_code=303)
