# -*- coding: utf-8 -*-
"""
Vindex AI — shared/case_readiness.py

Program Sigma, Master Sprint 004 (2026-08-06) — "Legal Case Readiness & Action
Planning Engine". Two things, both pure functions over ALREADY-COMPUTED data,
inventing no new detection algorithm — per this sprint's own explicit
architectural constraint ("NE praviti novi Task/Action/Priority/Recommendation
sistem"):

1. `top_open_action()` — the ONE canonical "what should the lawyer do next"
   reader, over `case_actions`' own already-canonical rows (migration 099,
   `services/case_evolution.py::_compute_target_actions`), ordered by
   `shared/attention_priority.py`'s own already-canonical priority order. Every
   consumer that used to independently GPT-guess "the one most urgent action"
   (routers/case_intelligence.py's own AI Briefing, routers/copilot.py's own
   _handle_analiza_predmeta) now calls this instead.

2. `compute_case_readiness()` — the Legal Readiness Model (Phase 4): a
   deterministic 5-state classification (READY/PARTIALLY_READY/BLOCKED/
   CRITICAL_GAP/UNKNOWN), computed EXCLUSIVELY from `case_actions.prioritet`
   (case_actions' own already-canonical, already-deterministic priority — see
   `shared/attention_priority.py`) plus whether any Gap Engine hypothesis-only
   finding exists with no deterministic backing. No GPT call, no GPT number, no
   GPT status string — the exact opposite of `routers/matter_intel.py::
   preflight_check`'s own GPT-generated `status` field (found this sprint, see
   `CASE_READINESS_MODEL.md` for why that field was NOT touched/replaced this
   sprint despite the overlap).

## Why this is 2 functions in 1 new module, not 2 new modules

Both read the exact same input shape (a case's own open `case_actions` rows)
and both exist to answer variations of the mission's own one question ("what
should the lawyer do, and how ready is the case") — splitting them into 2
files would itself be exactly the kind of unnecessary proliferation this
sprint's own founding principle warns against.
"""
from __future__ import annotations

from shared.attention_priority import CANONICAL_ORDER, canonical_sort_key


def top_open_action(case_actions: list[dict]) -> dict | None:
    """Returns the single highest-priority OPEN case_actions row for a case,
    or None if there are none. THE canonical answer to "what's the one most
    urgent thing" — callers that used to ask GPT to invent this (case_
    intelligence.py's own briefing, copilot.py's own _handle_analiza_predmeta)
    now call this instead.

    `case_actions` here is the caller's own already-fetched list of OPEN rows
    for one predmet (this function does no DB I/O of its own, matching every
    other pure function in this codebase's own "no new AI/DB infrastructure"
    idiom for Sprint 003/004's own canonical aggregators)."""
    open_rows = [a for a in (case_actions or []) if a.get("status", "open") == "open"]
    if not open_rows:
        return None
    return min(open_rows, key=lambda a: (canonical_sort_key(a.get("prioritet")), a.get("rok") or "9999-99-99"))


# ─── Legal Readiness Model (Phase 4) ──────────────────────────────────────────

READY            = "READY"
PARTIALLY_READY  = "PARTIALLY_READY"
BLOCKED          = "BLOCKED"
CRITICAL_GAP     = "CRITICAL_GAP"
UNKNOWN          = "UNKNOWN"

READINESS_STATES = (READY, PARTIALLY_READY, BLOCKED, CRITICAL_GAP, UNKNOWN)

# Operation Single Brain (2026-08-07): this exact dict -- {CRITICAL_GAP: 50, BLOCKED: 65}
# -- was independently copy-pasted into 3 GPT success-probability generators
# (routers/hearing_cc.py, routers/digital_twin.py, routers/court_predictor.py), each with
# its own comment explaining it "reuses the same threshold as the other 2 files". A future
# threshold change would need 3 synchronized edits with no compiler/test signal if one was
# missed -- the definition of a duplicate truth this mission's mandate targets. One shared
# constant now; the 3 routers import this instead of redeclaring it.
CAP_BY_READINESS = {CRITICAL_GAP: 50, BLOCKED: 65}

_BLOCKING_TIPOVI = {"PRIBAVITI_DOKAZ", "RAZRESITI_KONTRADIKCIJU"}


def compute_case_readiness(
    case_actions: list[dict] | None,
    gaps: list[dict] | None = None,
    genome_computed: bool = True,
) -> dict:
    """Deterministic 5-state Legal Readiness Model, computed exclusively from
    already-canonical signals:
      - case_actions.prioritet (shared/attention_priority.py's own canonical
        order) — the SAME priority every open action already carries, not a
        new number.
      - shared/gap_engine.py's own Gap records — specifically, whether any
        gap exists that is ONLY a GPT hypothesis (hipoteza=True) with no
        deterministic (hipoteza=False) backing, which caps confidence at
        PARTIALLY_READY even with zero open case_actions (an unconfirmed
        GPT-only concern is not the same as a clean case).

    Rules (checked in this exact order — first match wins):
      1. UNKNOWN         -- Genome has never run for this case (genome_computed=False)
                             AND no case_actions exist yet -- not enough signal to assess.
      2. CRITICAL_GAP     -- any open case_actions row has prioritet == "critical".
      3. BLOCKED          -- any open PRIBAVITI_DOKAZ/RAZRESITI_KONTRADIKCIJU
                             action has prioritet == "high" (a hard
                             prerequisite not yet critical, but blocking
                             confident progress).
      4. PARTIALLY_READY  -- any other open case_actions row exists at all
                             (medium/low/informational), OR a GPT-only
                             (hipoteza=True) gap exists with no deterministic
                             backing for the same concern.
      5. READY            -- zero open case_actions, zero unresolved gaps.

    Returns {"status": one of READINESS_STATES, "razlog": str, "izvor": list[str]}
    -- "razlog"/"izvor" so this is traceable, not a bare label (Phase 6's own
    "svaki element mora imati trag porekla" requirement)."""
    case_actions = case_actions or []
    gaps = gaps or []
    open_actions = [a for a in case_actions if a.get("status", "open") == "open"]

    if not genome_computed and not open_actions:
        return {"status": UNKNOWN, "razlog": "Genome još nije izračunat za ovaj predmet, nema dovoljno signala.", "izvor": []}

    critical = [a for a in open_actions if a.get("prioritet") == "critical"]
    if critical:
        return {
            "status": CRITICAL_GAP,
            "razlog": critical[0].get("razlog") or "Otvorena akcija kritičnog prioriteta.",
            "izvor": [a.get("dedupe_key") for a in critical if a.get("dedupe_key")],
        }

    blocking_high = [
        a for a in open_actions
        if a.get("tip") in _BLOCKING_TIPOVI and a.get("prioritet") == "high"
    ]
    if blocking_high:
        return {
            "status": BLOCKED,
            "razlog": blocking_high[0].get("razlog") or "Nedostaje dokaz ili nerazrešena kontradikcija visokog prioriteta.",
            "izvor": [a.get("dedupe_key") for a in blocking_high if a.get("dedupe_key")],
        }

    hypothesis_only = [g for g in gaps if g.get("hipoteza") is True]
    if open_actions or hypothesis_only:
        source_keys = [a.get("dedupe_key") for a in open_actions if a.get("dedupe_key")]
        source_keys += [g.get("dedupe_key") for g in hypothesis_only if g.get("dedupe_key")]
        razlog = (
            open_actions[0].get("razlog") if open_actions
            else (hypothesis_only[0].get("razlog") or "Genome sugeriše mogući nedostatak, nije potvrđeno.")
        )
        return {"status": PARTIALLY_READY, "razlog": razlog, "izvor": source_keys}

    return {"status": READY, "razlog": "Nema otvorenih akcija niti neotklonjenih praznina.", "izvor": []}


# ─── NS006 Task 7 — pregled spremnosti BEZ pseudo-predviđanja ─────────────────
#
# Čista funkcija nad VEĆ UČITANIM redovima. Računanje ostaje kod kanonskih vlasnika:
# `services/risk_engine.py::calculate_procesni_rizik` / `identify_case_problems` i
# `compute_case_readiness` iznad. Ovde se samo:
#   • svaka dimenzija veže za SVOJ izvor i stanje tog izvora;
#   • izvor koji NIJE pročitan daje `DEGRADED` i `vrednost: None` — nikad 0, nikad
#     „spremno" (FAILED != EMPTY);
#   • nijedna vrednost se ne naziva šansom, verovatnoćom ni predviđanjem ishoda.
# Nema upisa (za razliku od `routers/matter_intel.py::get_matter_intel`, koji pri
# čitanju upisuje `predmet_health_log` i emituje alarme).

SPREMNOST_OK = "OK"
SPREMNOST_DEGRADIRANO = "DEGRADED"
SPREMNOST_NEPOZNATO = "UNKNOWN"


def _dim(kljuc, naziv, vrednost, znacenje, izvor, stanje=SPREMNOST_OK, **dod):
    return {"kljuc": kljuc, "naziv": naziv, "vrednost": vrednost if stanje == SPREMNOST_OK else None,
            "znacenje": znacenje, "izvor": izvor, "stanje": stanje, "klasa": "deterministic", **dod}


def pregled_spremnosti(*, tip_predmeta: str, dokazi: list | None, dokumenti: list | None, rocista: list | None,
                       akcije: list | None, kontradikcije: dict | None, genome_izracunat: bool,
                       izvori: dict | None = None) -> dict:
    from services.risk_engine import calculate_procesni_rizik, identify_case_problems
    from shared.constants import EXPECTED_DOCS
    from shared.evidence_write import pokrivenost_procene

    izvori = dict(izvori or {})
    ok = {k: izvori.get(k, "OK") == "OK" for k in ("dokazi", "dokumenti", "rocista", "akcije", "kontradikcije")}
    zakazana = [r for r in (rocista or []) if (r or {}).get("status") == "zakazano"]
    dim: list[dict] = []

    # 1. Pokrivenost procene dokaza — „N od M tvrdnji ima procenu", ne „snaga X%".
    if ok["dokazi"]:
        p = pokrivenost_procene(dokazi or [])
        dim.append(_dim("pokrivenost_procene", "Tvrdnje sa procenom dokaza",
                        {"procenjeno": p["broj_procenjenih"], "ukupno": p["broj_tvrdnji"], "status": p["status"]},
                        "Koliko tvrdnji ima procenu dokazne snage (čovek ili pronađeno u izvoru).", "predmet_dokazi"))
    else:
        dim.append(_dim("pokrivenost_procene", "Tvrdnje sa procenom dokaza", None, "Tvrdnje nisu pročitane.",
                        "predmet_dokazi", SPREMNOST_DEGRADIRANO))

    # 2–4. Procesni rizik i njegovi delovi — SAMO ako su sva tri izvora pročitana.
    rizik = None
    if ok["dokazi"] and ok["dokumenti"] and ok["rocista"]:
        rizik = calculate_procesni_rizik(dokazi=dokazi or [], dokumenti=dokumenti or [], rocista=zakazana,
                                         tip_predmeta=tip_predmeta or "ostalo", expected_docs=EXPECTED_DOCS)
    if ok["dokumenti"] and rizik is not None:
        dim.append(_dim("nedostajuci_tipovi", "Nedostajući tipovi dokumenata", list(rizik["nedostajuci_dokazi"]),
                        f"Tipovi dokumenata uobičajeni za ovu vrstu predmeta, a kojih u spisu nema.", "predmet_dokumenti"))
    else:
        dim.append(_dim("nedostajuci_tipovi", "Nedostajući tipovi dokumenata", None,
                        "Dokumenti ili ročišta nisu pročitani.", "predmet_dokumenti", SPREMNOST_DEGRADIRANO))
    if ok["rocista"]:
        from datetime import date as _date
        danas = _date.today()
        dani = []
        for r in zakazana:
            try:
                dani.append((_date.fromisoformat(str(r.get("datum"))[:10]) - danas).days)
            except (TypeError, ValueError):
                continue
        dim.append(_dim("rocista", "Zakazana ročišta",
                        {"u_narednih_30_dana": sum(1 for d in dani if 0 <= d <= 30),
                         "u_narednih_7_dana": sum(1 for d in dani if 0 <= d <= 7),
                         "propustena": sum(1 for d in dani if d < 0)},
                        "Zakazana ročišta po vremenu do održavanja (propuštena = datum prošao, status nepromenjen).", "rocista"))
    else:
        dim.append(_dim("rocista", "Zakazana ročišta", None, "Ročišta nisu pročitana.", "rocista", SPREMNOST_DEGRADIRANO))
    if rizik is not None:
        dim.append(_dim("procesni_rizik", "Procesni rizik (pravilo)", rizik["nivo"],
                        "Pravilo nad dokazima, nedostajućim dokumentima i rokovima (services/risk_engine.py). "
                        "NIJE procena ishoda spora.", "risk_engine",
                        faktori=[p["problem"] for p in identify_case_problems(rizik, tip_predmeta or "ostalo")]))
    else:
        dim.append(_dim("procesni_rizik", "Procesni rizik (pravilo)", None,
                        "Bar jedan izvor (tvrdnje, dokumenti, ročišta) nije pročitan — rizik se ne računa iz delimičnih podataka.",
                        "risk_engine", SPREMNOST_DEGRADIRANO))

    # 5. Kontradikcije (iz sekcije kontradikcija).
    if ok["kontradikcije"] and kontradikcije and kontradikcije.get("sazetak") is not None:
        s = kontradikcije["sazetak"]
        dim.append(_dim("kontradikcije", "Aktivne kontradikcije",
                        {"aktivnih": s["aktivnih"], "kriticnih": s["kriticnih_aktivnih"], "za_pregled": s["za_pregled"],
                         "bez_veze_na_tvrdnje": s["aktivnih_bez_veze_na_tvrdnje"]},
                        "Aktivne sporne tačke među tvrdnjama i dokumentima.", "predmet_contradictions"))
    else:
        dim.append(_dim("kontradikcije", "Aktivne kontradikcije", None, "Kontradikcije nisu pročitane.",
                        "predmet_contradictions", SPREMNOST_DEGRADIRANO))

    # 6. Operativna spremnost — postojeći model nad OTVORENIM akcijama.
    if ok["akcije"]:
        otvorene = [a for a in (akcije or []) if a.get("status", "open") == "open"]
        sp = compute_case_readiness(otvorene, genome_computed=genome_izracunat)
        po_prioritetu = {p: sum(1 for a in otvorene if a.get("prioritet") == p) for p in CANONICAL_ORDER}
        dim.append(_dim("operativna_spremnost", "Operativna spremnost", sp["status"], sp["razlog"],
                        "case_actions", izvor_kljucevi=sp["izvor"], otvorenih_akcija=len(otvorene), po_prioritetu=po_prioritetu))
    else:
        dim.append(_dim("operativna_spremnost", "Operativna spremnost", None,
                        "Akcije nisu pročitane — spremnost se ne procenjuje.", "case_actions", SPREMNOST_DEGRADIRANO))

    degradirano = [d["kljuc"] for d in dim if d["stanje"] != SPREMNOST_OK]
    return {"stanje": SPREMNOST_DEGRADIRANO if degradirano else SPREMNOST_OK, "dimenzije": dim,
            "degradirano": degradirano,
            "napomena": "Pokazatelji su determinističko brojanje i pravila nad podacima predmeta; ni jedan nije predviđanje ishoda."}
