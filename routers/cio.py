# -*- coding: utf-8 -*-
"""
Vindex AI — Chief Intelligence Officer (CIO)

Ne čeka pitanje. Svaki dan skenira kompletni portfelj kancelarije i
pronalazi šta je najvažnije — i šta advokat JOŠ NIJE PRIMETIO.

Program Omega, Sprint 004 (2026-08-06) — Unified Legal Workspace:
`cio_preporuka` ("JEDNA konkretna akcija — danas") je GPT-generisana
portfolio-nivo narativna procena, NE kanonski operativni izvor. Kanonski
odgovor na "šta advokat treba danas da radi" je sada `GET /api/workspace`
(deterministički, sourced po stavci — docs/omega/CANONICAL_WORKSPACE_SPEC.md).
Ovaj modul OSTAJE kao dopunska strateška perspektiva (Responsibility Matrix
odluka: "postaje podmodul", docs/omega/UNIFIED_WORKSPACE_ARCHITECTURE.md) —
nije integrisan u case_actions/Workspace ovaj sprint (van bezbednog obima:
GPT prompt/ponašanje ovog live, naplativog modula nije menjano).

GET  /api/cio/daily    — dnevni CIO izveštaj (keširan 6h)
POST /api/cio/run      — forsiraj regenerisanje
GET  /api/cio/history  — poslednjih 7 dana
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user
from shared.llm_retry import llm_retry
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.sentry import capture_exception as _sentry_capture
from shared.usage import UsageService
from shared.case_context import build_case_context
from shared.case_readiness import READY, CRITICAL_GAP, BLOCKED
from shared.genome_validator import validate_predmet_reference

logger = logging.getLogger("vindex.cio")
router = APIRouter(prefix="/api/cio", tags=["cio"])

# Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-046 remainder): in-process-only
# coalescing state for cio_daily's claim-loser wait, same shape as
# routers/case_dna.py's _genome_refresh_inflight/_genome_refresh_done_event.
# A plain dict/set (not cross-process) -- helps the common same-worker race,
# honestly does not close a cross-worker race (disclosed, not silently claimed).
_cio_daily_inflight: set = set()
_cio_daily_done_event: dict = {}
_CIO_DAILY_COALESCE_WAIT_TIMEOUT = 60.0

# ── CIO sistem prompt ─────────────────────────────────────────────────────────

_CIO_SYSTEM = """Ti si Chief Intelligence Officer (CIO) pravne kancelarije.

TVOJ POSAO NIJE DA ODGOVARAS NA PITANJA. TVOJ POSAO JE DA DOLAZIS SA ODGOVORIMA.

Svaki dan skenujes kompletan portfelj i pronalazis ono sto advokat JOS NIJE PRIMETIO.
Koristis: Case Genome modele predmeta + Firm DNA + Lekcije + Obrasce uspeha.

Vrati SAMO validan JSON (bez markdown):
{
  "cio_preporuka": "JEDNA konkretna akcija sa najvecim uticajem — danas, imenuj predmet",
  "najveci_rizik": {
    "predmet_id": "uuid tacno iz portfolija",
    "predmet_naziv": "...",
    "rizik": "Konkretan opis — sta moze da propadne i zasto",
    "kriticnost": 94,
    "akcija": "Sta tacno uraditi u sledecih 24h"
  },
  "najveca_prilika": {
    "predmet_id": "uuid",
    "predmet_naziv": "...",
    "prilika": "Opis prilike koja se ne koristi — konkretno",
    "akcija": "Sta uraditi da se iskoristi"
  },
  "zapostavljen_predmet": {
    "predmet_id": "uuid",
    "predmet_naziv": "...",
    "dana_bez_aktivnosti": 18,
    "rizik_zapustanja": "Sta se moze dogoditi ako se ne reaguje"
  },
  "neprimecena_kontradikcija": {
    "predmet_id": "uuid",
    "predmet_naziv": "...",
    "kontradikcija": "Tacno sta se kosi u dokazima ili cinjenicama",
    "tezina": "kriticna|vazna",
    "preporuka": "Konkretna akcija"
  },
  "kriticni_rok": {
    "predmet_id": "uuid",
    "predmet_naziv": "...",
    "rok_naziv": "Naziv roka",
    "datum": "YYYY-MM-DD",
    "dana_do": 13,
    "akcija": "Sta tacno uraditi"
  },
  "suboptimalna_strategija": {
    "predmet_id": "uuid",
    "predmet_naziv": "...",
    "problem": "Zasto strategija vise nije optimalna u svetlu novih podataka",
    "preporuka": "Predlozena izmena strategije"
  },
  "slicni_predmet": {
    "predmet_id": "uuid",
    "predmet_naziv": "...",
    "slicnost": "Cemu lici iz prethodne prakse — konkretna paralela",
    "lekcija": "Sta se moze direktno primeniti"
  },
  "cio_zakljucak": "2-3 recenice o opstem zdravlju portfolija — iskreno, bez optimizma",
  "pouzdanost": "visoka|srednja|niska"
}

STROGA PRAVILA:
- Popuni SVE kljuceve. Ako nemas podataka za neki, stavi null za ceo objekat.
- predmet_id mora biti UUID tacno preuzet iz ulaznih podataka.
- Budi konkretan — imenuj predmete, opisi rizike precizno. Nikad genericki.
- kriticnost 0-100 (100 = odmah reagovati, predmet u opasnosti).
- zapostavljen_predmet = predmet sa najvecim dana_bez_aktivnosti koji ima aktivni rizik.
- kriticni_rok = rok koji istice najranije u sledecih 60 dana (status=aktivan).
- neprimecena_kontradikcija = kontradikcija tezina=kriticna koja jos nije adresovana.
- suboptimalna_strategija = predmet cija strategija nije pracena novim dokazima ili gecosima.
- slicni_predmet = predmet koji se podudara sa dobijenim sporom iz lekcija ili obrazaca.
- cio_preporuka = JEDNA akcija, ne lista. Imenuj predmet. Reci tacno sta uraditi.
- Ekavica strogo — nikada ijekavica.
- Budi iskren o slabostima portfelja. CIO koji utesava nije CIO."""


# ── Portfolio builder ─────────────────────────────────────────────────────────

def _kompaktan_predmet(p: dict, cc: Optional[dict], danas: date) -> Optional[dict]:
    """Izvlaci kljucne signale iz jednog predmeta za CIO analizu.

    Program Tau, Master Sprint 008 ("Canonical Executive Intelligence
    Consolidation"): `cc` je `shared/case_context.py::build_case_context()`-ov
    izlaz za OVAJ predmet (lightweight mode) -- svaka od signala ispod
    (snaga/najslabija_tacka/rokovi_aktivni/kontradikcije_kriticne/
    nedostaje_kriticno) sada čita KANONSKI, gap_engine/case_readiness-
    normalizovan izvor umesto sirovog `case_dna` polja direktno
    (docs/tau/CIO_FORENSIC_REPORT.md). `rokovi_aktivni` posebno prelazi sa
    Genome-ovog sopstvenog GPT-ekstrahovanog `rokovi_kriticni[]` (treći,
    ranije nepoznat izvor rokova, van `rocista`/`rokovi` podele koju
    TAU-013 već imenuje) na kanonski `deadlines` (stvarna `rocista` tabela).

    `strategija_cilj`/`zakljucak` nemaju kanonski ekvivalent (canonical
    `key_facts` nosi samo `pravna_teorija`/`snaga_predmeta_procent`/
    `najslabija_tacka` -- ne i `strategija`/`zakljucak`) -- zadržano
    direktno iz `case_dna` kao namerni Korak-5 izuzetak
    (docs/tau/MIGRATION_TEMPLATE.md), ne kao zaobilaznica migracije."""
    genome = p.get("case_dna") or {}
    key_facts = (cc or {}).get("key_facts") or {}
    kf = key_facts.get("value")
    if not kf:
        return None  # isti guard kao pre -- genome_computed=False znaci key_facts.value je None

    now = datetime.now(timezone.utc)
    upd = p.get("updated_at") or ""
    dana_neakt = 0
    if upd:
        try:
            upd_dt = datetime.fromisoformat(upd.replace("Z", "+00:00"))
            dana_neakt = (now - upd_dt).days
        except Exception:
            pass

    rokovi_aktivni = []
    for r in ((cc.get("deadlines") or {}).get("value") or []):
        if r.get("proslo"):
            continue
        datum = r.get("datum")
        if not datum:
            continue
        try:
            rok_dt = date.fromisoformat(str(datum)[:10])
            dana_do = (rok_dt - danas).days
            if 0 <= dana_do <= 60:
                rokovi_aktivni.append({
                    "naziv": r.get("sud", "")[:60] or "Rok",
                    "datum": str(datum)[:10],
                    "dana_do": dana_do,
                    "opis": (r.get("status") or "")[:50],
                })
        except Exception:
            pass

    nt = kf.get("najslabija_tacka") or {}
    strat = genome.get("strategija") or {}
    kontr_kriticne = [
        g for g in ((cc.get("contradictions") or {}).get("value") or [])
        if g.get("pouzdanost") == "visoka"
    ]
    ned_kriticno = sum(
        1 for g in ((cc.get("missing_evidence") or {}).get("value") or [])
        if g.get("pouzdanost") == "visoka"
    )

    return {
        "id":                   p.get("id"),
        "naziv":                p.get("naziv", ""),
        "oblast":               p.get("oblast_prava", ""),
        "snaga":                kf.get("snaga_predmeta_procent"),
        "dana_bez_aktivnosti":  dana_neakt,
        "najslabija_tacka":     {
            "rizik":      (nt.get("rizik") or "")[:80],
            "kriticnost": nt.get("kriticnost"),
        } if nt.get("rizik") else None,
        "rokovi_aktivni":       sorted(rokovi_aktivni, key=lambda x: x["dana_do"])[:3],
        "kontradikcije_kriticne": [
            {"opis": (g.get("razlog") or "")[:70]} for g in kontr_kriticne[:2]
        ],
        "nedostaje_kriticno":   ned_kriticno,
        "strategija_cilj":      (strat.get("primarni_cilj") or genome.get("strategija_osnova") or "")[:70],
        "zakljucak":            (genome.get("zakljucak") or "")[:100],
    }


@llm_retry
async def _pozovi_cio_api(client, user_msg: str):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške."""
    return await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _CIO_SYSTEM},
            {"role": "user",   "content": user_msg[:14000]},
        ],
        response_format={"type": "json_object"},
        temperature=0.15,
        max_tokens=2500,
    )


async def _generiši_cio_izvestaj(uid: str, supa) -> dict:
    """Skenira kompletni portfelj i generise dnevni CIO izvestaj."""
    danas = date.today()

    # `predmeti` se mora dohvatiti PRVI -- kanonska petlja ispod zavisi od
    # njegovih id-jeva. `firm_dna`/`lessons_learned`/`case_patterns` NEMAJU tu
    # zavisnost -- Faza 7 (Performance) je zatekla da su ranije sve 4 bile u
    # ISTOM gather-u, što je nepotrebno blokiralo kanonsku petlju da čeka na
    # 3 upita koja joj ništa ne dostavljaju. Popravljeno odmah (Faza 8): ova
    # 3 sada trče KONKURENTNO sa kanonskom petljom, ne pre nje.
    # Program Phoenix, Mission 014 (LIVINGSYS-DEBT-003): the 40-case cap and its
    # oldest-first ordering are unchanged (raising/removing the cap is a genuine
    # perf tradeoff at scale, and re-ordering needs a founder product decision on
    # which cases should represent a truncated portfolio -- neither attempted
    # here). This mission closes ONLY the disclosure gap: the report used to
    # present the capped, biased sample as the true portfolio total with zero
    # signal anywhere that it was truncated. A cheap count-only query (no row
    # data) now makes that fact visible in the response.
    # pred_r keeps its ORIGINAL fail-hard behavior (a genuine DB error here must
    # still propagate and become the caller's existing 500, not be silently
    # reinterpreted as "0 active cases" -- that would be a new silent-failure
    # bug of exactly the class this whole program exists to close). count_r is
    # a disclosure nice-to-have, not core data, and fails soft on its own --
    # launched concurrently (asyncio.create_task) so this disclosure doesn't
    # add sequential latency to the report's own critical path.
    _count_task = asyncio.create_task(asyncio.to_thread(
        lambda: supa.table("predmeti")
        .select("id", count="exact")
        .eq("user_id", uid)
        .in_("status", ["aktivan", "u_toku", "pending"])
        .limit(1)
        .execute()
    ))
    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
        .select("id,naziv,oblast_prava,updated_at,case_dna")
        .eq("user_id", uid)
        .in_("status", ["aktivan", "u_toku", "pending"])
        .order("updated_at", desc=False)
        .limit(40)
        .execute()
    )
    predmeti_raw = pred_r.data or []
    try:
        count_r = await _count_task
        total_aktivnih_u_bazi = count_r.count if isinstance(count_r.count, int) else len(predmeti_raw)
    except Exception as _count_exc:
        logger.warning("[CIO] count upit neuspešan (nastavljam bez truncated signala): %s", _count_exc)
        total_aktivnih_u_bazi = len(predmeti_raw)
    portfolio_truncated = total_aktivnih_u_bazi > len(predmeti_raw)

    # Program Tau, Master Sprint 008: kanonski kontekst po predmetu (lightweight
    # mode -- dokumenti nisu potrebni za portfolio-nivo signale), isti obrazac
    # koji morning_briefing.py (Tau 002) i case_commander.py-ov jutarnji brifing
    # (Tau 007) već koriste za portfolio-wide petlju. Fail-soft: neuspeh za
    # JEDAN predmet ne ruši ceo CIO izveštaj -- taj predmet jednostavno biva
    # isključen iz portfolija (isto ponašanje kao stari kod za predmete bez
    # Genome modela). Trči konkurentno sa fdna/lek/patt ispod (Faza 8 popravka)
    # -- 2 odvojena gather-a (ne 1 zajednički) da bi fdna/lek/patt zadržali
    # svoje ORIGINALNO ponašanje (greška se propagira, ne guta se), dok
    # cc_results ostaje fail-soft samo za sebe.
    (fdna_r, lek_r, patt_r), cc_results = await asyncio.gather(
        asyncio.gather(
            asyncio.to_thread(
                lambda: supa.table("firm_dna")
                .select("pattern,frekvencija,uzoraka")
                .eq("user_id", uid)
                .eq("aktuelna", True)
                .order("frekvencija", desc=True)
                .limit(6)
                .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("lessons_learned")
                .select("sadrzaj,kategorija,pouzdanost,broj_predmeta")
                .eq("user_id", uid)
                .in_("status_lekcije", ["usvojena_praksa"])
                .order("pouzdanost", desc=True)
                .limit(8)
                .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("case_patterns")
                .select("tip_spora,faktor,pobede,porazi,ukupno")
                .eq("user_id", uid)
                .order("pobede", desc=True)
                .limit(8)
                .execute()
            ),
        ),
        asyncio.gather(
            *[build_case_context(p["id"], uid, supa, include_documents=False) for p in predmeti_raw],
            return_exceptions=True,
        ),
    )
    cc_by_id = {
        p["id"]: cc for p, cc in zip(predmeti_raw, cc_results)
        if not isinstance(cc, Exception) and cc and not cc.get("error")
    }

    # Kompaktni portfolio za GPT
    portfolio = []
    for p in predmeti_raw:
        komp = _kompaktan_predmet(p, cc_by_id.get(p["id"]), danas)
        if komp:
            portfolio.append(komp)

    if not portfolio:
        # Program Phoenix, Mission 015 (LIVINGSYS-DEBT-019): the single message below
        # used to fire for BOTH "you have zero active cases" and "you have active
        # cases but none has a Genome model yet" -- worded only for the 2nd, so a
        # brand-new user with literally no cases saw "Generišite Genome za aktivne
        # predmete" (generate Genome for your active cases), implying cases exist
        # that don't.
        _cio_preporuka = (
            "Nemate aktivnih predmeta. Kreirajte predmet da biste dobili CIO uvid."
            if not predmeti_raw else
            "Nema aktivnih predmeta sa Case Genome modelom. Generišite Genome za aktivne predmete."
        )
        return {
            "datum":              danas.isoformat(),
            "cio_preporuka":      _cio_preporuka,
            "portfolio_zdravlje": {
                "ukupno_aktivnih": len(predmeti_raw), "sa_genomom": 0,
                "ukupno_u_bazi": total_aktivnih_u_bazi, "truncated": portfolio_truncated,
            },
            "predmeta_analizirano": 0,
            "pouzdanost":         "niska",
        }

    # Firm context tekst
    firm_ctx_parts = []
    fdna = fdna_r.data or []
    if fdna:
        firm_ctx_parts.append("FIRM DNA — kako kancelarija razmislja:\n" + "\n".join(
            f"- {d.get('pattern','')[:80]} (frekvencija: {d.get('frekvencija',0)})"
            for d in fdna
        ))
    lekcije = lek_r.data or []
    if lekcije:
        firm_ctx_parts.append("USVOJENE LEKCIJE iz prethodnih predmeta:\n" + "\n".join(
            f"- [{l.get('pouzdanost','?')}] {l.get('sadrzaj','')[:100]}"
            for l in lekcije
        ))
    patt = patt_r.data or []
    if patt:
        firm_ctx_parts.append("OBRASCI USPEHA (tip spora → win rate):\n" + "\n".join(
            f"- {cp.get('tip_spora','')}: {cp.get('faktor','')[:50]} "
            f"({cp.get('pobede',0)}/{cp.get('ukupno',1)} predmeta)"
            for cp in patt
        ))

    firm_ctx = "\n\n".join(firm_ctx_parts)

    # Portfolio statistike
    snage = [p["snaga"] for p in portfolio if p["snaga"] is not None]
    prosecna_snaga = round(sum(snage) / len(snage)) if snage else 0

    user_msg = (
        f"PORTFOLIO KANCELARIJE: {len(portfolio)} aktivnih predmeta sa Genome modelom\n"
        f"Prosecna snaga predmeta: {prosecna_snaga}%\n\n"
        f"PREDMETI (kompaktni prikaz):\n{json.dumps(portfolio, ensure_ascii=False, separators=(',',':'))}\n\n"
        + (f"{firm_ctx}" if firm_ctx else "Napomena: Firma jos nema akumuliranu DNA/lekcije.")
    )

    import openai
    client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = await _pozovi_cio_api(client, user_msg)

    try:
        izvestaj = json.loads(resp.choices[0].message.content or "{}")
    except Exception as _je:
        _sentry_capture(_je)
        izvestaj = {}

    # Deterministicke statistike (ne GPT)
    jakih  = sum(1 for p in portfolio if (p["snaga"] or 0) >= 65)
    slabih = sum(1 for p in portfolio if (p["snaga"] or 0) < 40)
    # Program Tau, Master Sprint 008: "kriticnih_rizika" je ranije brojao
    # Genome-ovu sopstvenu ad hoc kriticnost>=85 heuristiku (najslabija_tacka)
    # -- sada broji kanonski readiness.status in (CRITICAL_GAP, BLOCKED), isti
    # prag koji Workspace/Commander/Court Predictor/Hearing CC već koriste za
    # "ovaj predmet je kritičan" (docs/tau/EXECUTIVE_CONSOLIDATION.md).
    kriticnih_rizika = sum(
        1 for p in portfolio
        if ((cc_by_id.get(p["id"]) or {}).get("readiness") or {}).get("value", {}).get("status") in (CRITICAL_GAP, BLOCKED)
    )
    sa_kriticnim_rokovima = sum(1 for p in portfolio
                                if any(r["dana_do"] <= 7 for r in (p.get("rokovi_aktivni") or [])))

    # Program Tau, Master Sprint 008, Faza 5 (GPT Boundary): GPT bira KOJI
    # predmet je najveci_rizik/kriticni_rok/itd. i izmislja kriticnost -- ovde
    # se ta tvrdnja proverava protiv kanonskog stanja, ne prihvata bez provere.
    # Ponovo koristi POSTOJEĆI validator (shared/genome_validator.py::
    # validate_predmet_reference), ISTU funkciju koju case_commander.py's own
    # _cross_case_analiza već koristi za identičnu proveru -- nema novog
    # algoritma. Puni UUID se prosleđuje umesto 8-slovnog prefiksa (funkcija
    # je generička nad bilo kojim identifikator-string ključem, samo joj je
    # ime/poruka istorijski pisana za prefiks-oblik).
    poznati = {p["id"]: p.get("naziv", "") for p in predmeti_raw}
    readiness_by_id = {
        pid: ((cc.get("readiness") or {}).get("value") or {}).get("status")
        for pid, cc in cc_by_id.items()
    }
    _KRITICNOST_CAP_KAD_READY = 40

    def _validan_predmet_id(blok: Optional[dict]) -> bool:
        if not blok or not blok.get("predmet_id"):
            return False
        flags = validate_predmet_reference(blok.get("predmet_id"), poznati, blok.get("predmet_naziv"))
        return not flags

    for _kljuc in ("najveci_rizik", "najveca_prilika", "zapostavljen_predmet",
                   "neprimecena_kontradikcija", "kriticni_rok", "suboptimalna_strategija", "slicni_predmet"):
        _blok = izvestaj.get(_kljuc)
        if _blok and not _validan_predmet_id(_blok):
            izvestaj[_kljuc] = None

    # Operation Single Brain (2026-08-07), AI Boundary gap: the top-level "pouzdanost"
    # (GPT's own self-declared confidence in the WHOLE briefing) was never enum-validated --
    # unlike the per-block predmet_id references just above, which already go through
    # validate_predmet_reference(). Same guard pattern applied elsewhere this mission
    # (routers/court_predictor.py's opponent_intel pouzdanost, shared/genome_validator.py's
    # genome_kompletnost): unrecognized input fails safe toward "niska", not passed through.
    _p = izvestaj.get("pouzdanost")
    izvestaj["pouzdanost"] = _p if _p in ("visoka", "srednja", "niska") else "niska"

    _nr = izvestaj.get("najveci_rizik")
    if _nr:
        # BLACKSWAN-AI-002 fix (Operation Black Swan, Mission 001, AI Attack): the READY-
        # specific semantic cap below only ever fired for readiness==READY -- for every
        # OTHER readiness state (e.g. PARTIALLY_READY), an out-of-spec GPT value reached
        # the response completely unclamped. Reproduced: kriticnost=400 (spec 0-100) for a
        # PARTIALLY_READY case reached the API response unchanged. Basic range sanity now
        # applies unconditionally, independent of readiness state; the stricter
        # READY-specific cap below is an ADDITIONAL semantic constraint on top of this,
        # not a replacement for it.
        _k0 = _nr.get("kriticnost")
        if isinstance(_k0, (int, float)):
            _nr["kriticnost"] = max(0, min(100, _k0))
    if _nr and readiness_by_id.get(_nr.get("predmet_id")) == READY:
        _k = _nr.get("kriticnost")
        if isinstance(_k, (int, float)) and _k > _KRITICNOST_CAP_KAD_READY:
            _nr["kriticnost"] = _KRITICNOST_CAP_KAD_READY

    _kr = izvestaj.get("kriticni_rok")
    if _kr and _kr.get("predmet_id"):
        _prava_meta = next((p for p in portfolio if p["id"] == _kr["predmet_id"]), None)
        _stvarni_rokovi = {r["datum"] for r in (_prava_meta.get("rokovi_aktivni") or [])} if _prava_meta else set()
        if not _stvarni_rokovi or str(_kr.get("datum", ""))[:10] not in _stvarni_rokovi:
            izvestaj["kriticni_rok"] = None

    izvestaj["portfolio_zdravlje"] = {
        "ukupno_aktivnih":      len(portfolio),
        "jakih":                jakih,
        "srednje":              len(portfolio) - jakih - slabih,
        "slabih":               slabih,
        "prosecna_snaga":       prosecna_snaga,
        "kriticnih_rizika":     kriticnih_rizika,
        "kriticnih_rokova_7d":  sa_kriticnim_rokovima,
        # Program Phoenix, Mission 014 (LIVINGSYS-DEBT-003): disclosure-only fix
        # -- the 40-case cap and its oldest-first ordering are unchanged, but the
        # report no longer presents that capped, biased sample as the true
        # portfolio total with zero signal that it's truncated.
        "ukupno_u_bazi":        total_aktivnih_u_bazi,
        "truncated":            portfolio_truncated,
    }
    izvestaj["datum"]               = danas.isoformat()
    izvestaj["predmeta_analizirano"] = len(portfolio)

    logger.info("[CIO] izvestaj generisan uid=%.8s predmeta=%d prosecna_snaga=%d%%",
                uid, len(portfolio), prosecna_snaga)
    return izvestaj


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/daily")
@limiter.limit("30/minute")
async def cio_daily(request: Request, user=Depends(PermissionService.require("cio"))):
    """Vraca dnevni CIO izvestaj. Generise se jednom i kesira 6 sati."""
    uid  = user["user_id"]
    supa = _get_supa()
    now  = datetime.now(timezone.utc)
    danes_iso = date.today().isoformat()

    # Kes — 6 sati
    try:
        cached = await asyncio.to_thread(
            lambda: supa.table("cio_dnevni_izvestaj")
            .select("izvestaj,predmeta_analizirano,created_at")
            .eq("user_id", uid)
            .eq("datum", danes_iso)
            .single()
            .execute()
        )
        if cached.data:
            ts_str = cached.data.get("created_at", "")
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if (now - ts).total_seconds() < 21600:
                    return {
                        "izvestaj":             cached.data["izvestaj"],
                        "predmeta_analizirano": cached.data.get("predmeta_analizirano", 0),
                        "iz_kesa":              True,
                        "generisano_u":         ts_str,
                    }
    except Exception:
        pass

    # Operation Singular Intelligence, Mission 002 (Team 8, reproduced): the cache-check
    # above and the charge/persist below are not atomic -- two near-simultaneous /daily
    # calls for the same user (e.g. two open tabs both loading the dashboard) could both
    # pass the cache-miss check before either one's row lands, both generate, and both
    # call UsageService.consume -- a real double-charge for what the user experiences as
    # one dashboard load. Fixed with a 2-step claim, reusing only existing columns/
    # constraints (no new migration), same idiom as case_actions' CREATE path
    # (services/case_evolution.py):
    #   1. UPDATE today's row IF it exists but is stale (created_at older than the SAME
    #      6h cutoff already used by the cache check above) -- a legitimate same-day
    #      refresh after cache expiry takes over its own prior row.
    #   2. If step 1 matched nothing (no row for today yet), INSERT a fresh placeholder,
    #      relying on the table's own `UNIQUE (user_id, datum)` (migration 050) as the
    #      real race-breaker: if a concurrent request's INSERT already won, this one's
    #      INSERT fails with a unique violation -- that (and only that) is the genuine
    #      lost-race case, distinct from "existing row is simply stale" above.
    # A losing request still returns ITS OWN freshly-generated report to its own caller
    # (no functional loss for that request), it just isn't the one charged or cached.
    _stale_cutoff = (now.timestamp() - 21600)
    claimed = False
    try:
        _upd = await asyncio.to_thread(
            lambda: supa.table("cio_dnevni_izvestaj").update({
                "izvestaj": {}, "predmeta_analizirano": 0, "created_at": now.isoformat(),
            }).eq("user_id", uid).eq("datum", danes_iso).lt(
                "created_at", datetime.fromtimestamp(_stale_cutoff, tz=timezone.utc).isoformat()
            ).execute()
        )
        if _upd and _upd.data:
            claimed = True
    except Exception as _claim_exc:
        logger.warning("[CIO] claim-update greška (nastavljam): %s", _claim_exc)

    if not claimed:
        try:
            await asyncio.to_thread(
                lambda: supa.table("cio_dnevni_izvestaj").insert({
                    "user_id": uid, "datum": danes_iso, "izvestaj": {}, "predmeta_analizirano": 0,
                }).execute()
            )
            claimed = True
        except Exception as _claim_exc:
            if "duplicate key" not in str(_claim_exc).lower() and "unique" not in str(_claim_exc).lower():
                logger.warning("[CIO] claim-insert greška (nastavljam bez keš-zaštite): %s", _claim_exc)
                claimed = True  # nepoznata greška (npr. tabela nedostupna) -- ne blokiraj generisanje/naplatu

    # Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-046 remainder): a losing request
    # used to unconditionally pay its own full GPT generation cost before even
    # checking the claim result -- wasteful for the common same-process case (2
    # tabs, 1 gunicorn worker). If an in-process winner is already generating for
    # this exact (uid, datum), wait (bounded) for it and return ITS persisted
    # report instead of generating a 2nd one. Same coalescing shape Mission 012
    # already proved for Genome refresh (case_dna.py's _genome_refresh_inflight/
    # _genome_refresh_done_event) -- in-process only (a plain dict/set), so a
    # cross-worker race still falls through to the pre-fix behavior below,
    # honestly, not silently claimed as fully solved.
    _coalesce_key = f"{uid}:{danes_iso}"
    if not claimed and _coalesce_key in _cio_daily_inflight:
        _done_event = _cio_daily_done_event.get(_coalesce_key)
        if _done_event is not None:
            try:
                await asyncio.wait_for(_done_event.wait(), timeout=_CIO_DAILY_COALESCE_WAIT_TIMEOUT)
                _fresh = await asyncio.to_thread(
                    lambda: supa.table("cio_dnevni_izvestaj")
                        .select("izvestaj,predmeta_analizirano,created_at")
                        .eq("user_id", uid).eq("datum", danes_iso).single().execute()
                )
                if _fresh.data and _fresh.data.get("izvestaj"):
                    return {
                        "izvestaj":             _fresh.data["izvestaj"],
                        "predmeta_analizirano": _fresh.data.get("predmeta_analizirano", 0),
                        "iz_kesa":              True,
                        "generisano_u":         _fresh.data.get("created_at", now.isoformat()),
                    }
            except (asyncio.TimeoutError, Exception) as _coalesce_exc:
                logger.warning("[CIO] coalesce-wait greška/timeout (nastavljam sa sopstvenom generacijom): %s", _coalesce_exc)

    if claimed:
        _cio_daily_inflight.add(_coalesce_key)
        _cio_daily_done_event[_coalesce_key] = asyncio.Event()

    # Generisi
    try:
        izvestaj = await _generiši_cio_izvestaj(uid, supa)
    except Exception as e:
        _sentry_capture(e)
        logger.error("[CIO] daily greška: %s", e)
        raise HTTPException(500, f"CIO greška: {e}")
    finally:
        if claimed:
            _my_event = _cio_daily_done_event.pop(_coalesce_key, None)
            _cio_daily_inflight.discard(_coalesce_key)
            if _my_event is not None:
                _my_event.set()

    if not claimed:
        # Izgubljena trka za danasnji izvestaj -- neko drugi konkurentni poziv je vec
        # naplatio i uskoro upisuje. Ne naplacuj ponovo, ne prepisuj njegov red.
        return {
            "izvestaj":             izvestaj,
            "predmeta_analizirano": izvestaj.get("predmeta_analizirano", 0),
            "iz_kesa":              False,
            "generisano_u":         now.isoformat(),
        }

    # _generiši_cio_izvestaj vraca rano (bez GPT poziva) kad portfolio nema Genome
    # modela — predmeta_analizirano ostaje 0 u tom slucaju, ne naplacuj kredit tada.
    if izvestaj.get("predmeta_analizirano"):
        await UsageService.consume(uid, user.get("email", ""), "cio")

    # Snimi (azurira placeholder red koji je claim-insert upravo napravio)
    try:
        await asyncio.to_thread(
            lambda: supa.table("cio_dnevni_izvestaj").update({
                "izvestaj":            izvestaj,
                "predmeta_analizirano": izvestaj.get("predmeta_analizirano", 0),
            }).eq("user_id", uid).eq("datum", danes_iso).execute()
        )
    except Exception as ue:
        logger.warning("[CIO] update greška: %s", ue)

    return {
        "izvestaj":             izvestaj,
        "predmeta_analizirano": izvestaj.get("predmeta_analizirano", 0),
        "iz_kesa":              False,
        "generisano_u":         now.isoformat(),
    }


@router.post("/run")
@limiter.limit("10/minute")
async def cio_run(request: Request, user=Depends(PermissionService.require("cio"))):
    """Forsira regenerisanje CIO izvestaja — ignoriše kes."""
    uid  = user["user_id"]
    supa = _get_supa()
    now  = datetime.now(timezone.utc)
    danes_iso = date.today().isoformat()

    try:
        izvestaj = await _generiši_cio_izvestaj(uid, supa)
    except Exception as e:
        _sentry_capture(e)
        logger.error("[CIO] run greška: %s", e)
        raise HTTPException(500, f"CIO greška: {e}")

    # Program Phoenix, Mission 012 (LIVINGSYS-DEBT-046): /run had NO claim/lock at
    # all, unlike /daily's own 2-step claim above -- two literally-concurrent
    # force-regenerate calls (double-click, two tabs) both charged a credit. Reuses
    # the exact same idiom and the same UNIQUE(user_id, datum) constraint (migration
    # 050) /daily's claim already relies on, but with a SHORT (5s) staleness window
    # instead of /daily's 6h one: /run's whole purpose is "regenerate right now, even
    # if a cache exists," so a genuine repeat force-regenerate seconds/minutes later
    # must still claim and charge normally -- only a literally-simultaneous double-
    # click should lose the race.
    _claim_window_seconds = 5
    _stale_cutoff_iso = (now - timedelta(seconds=_claim_window_seconds)).isoformat()
    claimed = False
    try:
        _upd = await asyncio.to_thread(
            lambda: supa.table("cio_dnevni_izvestaj").update({
                "created_at": now.isoformat(),
            }).eq("user_id", uid).eq("datum", danes_iso).lt("created_at", _stale_cutoff_iso).execute()
        )
        if _upd and _upd.data:
            claimed = True
    except Exception as _claim_exc:
        logger.warning("[CIO] run claim-update greška (nastavljam): %s", _claim_exc)

    if not claimed:
        try:
            await asyncio.to_thread(
                lambda: supa.table("cio_dnevni_izvestaj").insert({
                    "user_id": uid, "datum": danes_iso, "izvestaj": {}, "predmeta_analizirano": 0,
                }).execute()
            )
            claimed = True
        except Exception as _claim_exc:
            if "duplicate key" not in str(_claim_exc).lower() and "unique" not in str(_claim_exc).lower():
                logger.warning("[CIO] run claim-insert greška (nastavljam bez keš-zaštite): %s", _claim_exc)
                claimed = True  # nepoznata greška -- ne blokiraj generisanje/naplatu

    if not claimed:
        # Izgubljena trka -- neko drugi konkurentni /run poziv je upravo naplatio i
        # uskoro upisuje svoj rezultat. Ne naplaćuj ponovo, ne prepisuj njegov red.
        return {
            "izvestaj":             izvestaj,
            "predmeta_analizirano": izvestaj.get("predmeta_analizirano", 0),
            "iz_kesa":              False,
            "generisano_u":         now.isoformat(),
        }

    if izvestaj.get("predmeta_analizirano"):
        await UsageService.consume(uid, user.get("email", ""), "cio")

    try:
        await asyncio.to_thread(
            lambda: supa.table("cio_dnevni_izvestaj").upsert({
                "user_id":             uid,
                "datum":               danes_iso,
                "izvestaj":            izvestaj,
                "predmeta_analizirano": izvestaj.get("predmeta_analizirano", 0),
            }, on_conflict="user_id,datum").execute()
        )
    except Exception:
        pass

    return {
        "izvestaj":             izvestaj,
        "predmeta_analizirano": izvestaj.get("predmeta_analizirano", 0),
        "iz_kesa":              False,
        "generisano_u":         now.isoformat(),
    }


@router.get("/history")
@limiter.limit("30/minute")
async def cio_history(request: Request, user=Depends(get_current_user), limit: int = 7):
    """Poslednjih N dana CIO izvestaja."""
    uid  = user["user_id"]
    supa = _get_supa()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("cio_dnevni_izvestaj")
            .select("datum,predmeta_analizirano,created_at,izvestaj")
            .eq("user_id", uid)
            .order("datum", desc=True)
            .limit(min(limit, 30))
            .execute()
        )
        rows = r.data or []
        # Vrati sazeti prikaz (ne ceo izvestaj)
        return {
            "history": [
                {
                    "datum":               row["datum"],
                    "predmeta_analizirano": row.get("predmeta_analizirano"),
                    "created_at":          row.get("created_at"),
                    "cio_preporuka":       (row.get("izvestaj") or {}).get("cio_preporuka", ""),
                    "pouzdanost":          (row.get("izvestaj") or {}).get("pouzdanost", ""),
                    "portfolio_zdravlje":  (row.get("izvestaj") or {}).get("portfolio_zdravlje"),
                }
                for row in rows
            ]
        }
    except Exception as e:
        raise HTTPException(500, str(e))
