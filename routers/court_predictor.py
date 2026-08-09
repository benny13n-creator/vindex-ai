# -*- coding: utf-8 -*-
"""
Vindex AI — routers/court_predictor.py

AI Court Predictor: predviđa ishod sudskog postupka na osnovu
opisa predmeta, sudske prakse i pravnih argumenata.

Endpoints:
  POST /api/predictor/analiza        — predviđanje ishoda + šansa za uspeh
  GET  /api/predictor/faktori        — lista faktora koji utiču na predviđanje
  POST /api/predictor/battle-report  — kompletna strateška analiza pre ročišta
  POST /api/predictor/hearing-prep   — 1-stranični brief za ročište
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService
from shared.sentry import capture_exception as _sentry_capture
from shared.llm_retry import llm_retry
from shared.case_context import build_case_context
from shared.case_readiness import READY, CRITICAL_GAP, BLOCKED, CAP_BY_READINESS

try:
    # CELINA 2 (2026-07-24): koristi javni retrieve_sudska_praksa (Celina 1 mu
    # je dodala Cohere/GPT re-rank prolaz) umesto direktnih niskonivoovskih
    # _pretraga_praksa/_ugradi_query poziva -- ranije je court_predictor.py
    # imao sopstvenu, izolovanu RAG logiku koja NIJE dobijala re-rank
    # poboljšanje niti fail-soft embed guard koje su ostali RAG potrošači
    # (routers/praksa.py, routers/oblasti.py) dobili u Celini 1.
    from app.services.retrieve import retrieve_sudska_praksa
    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False

logger = logging.getLogger("vindex.court_predictor")
router = APIRouter(tags=["court-predictor"])


_STRANA_LABELE = {
    "tuzilac":    "TUŽIOCA (strana koju advokat zastupa)",
    "tuzeni":     "TUŽENOG (strana koju advokat zastupa)",
    "podnosilac": "PODNOSIOCA (strana koju advokat zastupa)",
    "protivnik":  "PROTIVNE STRANE u odnosu na podnosioca (strana koju advokat zastupa)",
}


def _strana_instrukcija(strana: Optional[str]) -> str:
    """S5-1: makes the SUBJECT of the percentage explicit in the prompt.

    Without this the model decided for itself whose chance it was estimating,
    and the answer reached the lawyer as "šansa za uspeh" with no subject
    attached to it.
    """
    label = _STRANA_LABELE.get((strana or "").strip().lower())
    if label:
        return (
            "\n\nAnaliziraj i daj strukturisano predvidjanje ishoda. "
            f"procenat_min i procenat_max moraju biti VEROVATNOCA USPEHA ZA {label}, "
            "a ne za suprotnu stranu. U tekstu analize eksplicitno napisi na koju "
            "se stranu procenat odnosi."
        )
    # No side supplied: do not let the model pick one silently.
    return (
        "\n\nAnaliziraj i daj strukturisano predvidjanje ishoda sa procentom sanse za uspeh."
        "\nVAZNO: strana koju advokat zastupa NIJE navedena. U tekstu analize MORAS "
        "eksplicitno napisati na koju se stranu procenat odnosi (npr. 'procenat se "
        "odnosi na tuzioca'), jer se inace ne moze znati ciji je broj."
    )


class PredictorRequest(BaseModel):
    opis_predmeta: str
    tip_postupka: str                          # gradjansko|krivicno|radno|upravno|privredno
    cinjenicni_opis: str
    # S5-1 (2026-08-09): WHOSE chance is this percentage?
    #
    # There was no such field. The prompt asked for "procenat sanse za uspeh"
    # and for "kontra-argumente koje suprotna strana moze koristiti" -- implying
    # the reader is a party -- but never established WHICH party. The model
    # therefore inferred the side from the free-text description, and a case
    # description naturally reads from the claimant's perspective.
    #
    # So a defence lawyer could be shown "70%" that is the PLAINTIFF's chance
    # and read it as their own. A number whose subject is undefined is worse
    # than no number, and PROGBETA-001 has just made this one prominent in the
    # UI, which raises the stakes rather than lowering them.
    #
    # Optional, because existing clients do not send it. When it is absent the
    # response says so explicitly instead of letting the reader assume the
    # number is theirs.
    strana: Optional[str] = None               # tuzilac|tuzeni|podnosilac|protivnik|None
    dokazi: Optional[list[str]] = []
    suprotna_strana_argumenti: Optional[str] = None
    sud: Optional[str] = None
    predmet_id: Optional[str] = None


_PREDICTOR_SYSTEM = """Ti si ekspertni pravni analiticar sa 30 godina iskustva u srpskom pravosudju.
Analiziras pravne predmete i daješ procenu ishoda na osnovu:
- Vazeceg zakonodavstva Republike Srbije
- Sudske prakse srpskih sudova (dostavljena ispod ako je pronadjena)
- Jacine i relevantnosti dokaza
- Procesnih prednosti/nedostataka

STROGO pravilo:
1. Nikad ne garantuj ishod — uvek navedi procenat KAO OPSEG i objasni nesigurnost.
2. Navedi kontra-argumente koje suprotna strana moze koristiti.
3. Preporuci konkretne korake za jacanje pozicije.
4. Ako je dostavljena sudska praksa ispod, oslanjaj se na nju za konkretne primere;
   ako NIJE dostavljena, jasno navedi da je procena bazirana na opštem pravnom znanju.

Odgovori ISKLJUČIVO validnim JSON-om (bez markdown fenci):
{
  "procenat_min": 55,
  "procenat_max": 70,
  "analiza": "Pun tekst analize sa naslovima PROCENA ISHODA / KLJUCNI FAKTORI ZA i PROTIV / PREPORUCENA STRATEGIJA / RIZICI (markdown ** naslovi dozvoljeni unutar ovog stringa)",
  "kljucni_faktori_za": ["faktor 1", "faktor 2"],
  "kljucni_faktori_protiv": ["faktor 1", "faktor 2"],
  "preporucena_strategija": "konkretna preporuka",
  "rizici": ["rizik 1", "rizik 2"]
}

procenat_min/procenat_max: 0-100, min <= max, nikad tacna jedna vrednost bez opsega.

Ako je dole dat blok "STVARNO STANJE PREDMETA U SISTEMU" -- to je već izračunata, kanonska istina o
ovom predmetu (readiness, Genome, nedostajući dokazi, kontradikcije). Uskladi svoju procenu sa njom --
ne izmišljaj suprotnu ocenu snage predmeta bez razloga, i eksplicitno pomeni u kljucni_faktori_protiv
svaki nedostajući dokaz ili kontradikciju koja je tamo navedena."""


@llm_retry
def _pozovi_predictor_api(oai_client, user_prompt: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo prediktuj_ishod -- izdvojen jer
    vanjska funkcija ima sopstveni try/except."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _PREDICTOR_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1500,
        temperature=0.3,
        timeout=25.0,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or "{}"


def _rag_praksa_blok(query: str, top_k: int) -> tuple[str, list[dict]]:
    """CELINA 2 (2026-07-24): zajednički helper -- pretražuje sudsku praksu
    preko retrieve_sudska_praksa (Celina 1: Cohere/GPT re-rank) i formatira
    je u tekstualni blok za prompt. Nikad ne baca -- vraća prazan string na
    grešku, pozivalac dodaje napomenu da RAG nije dostupan.

    Program Tau, Master Sprint 005 (2026-08-06) -- vraća i strukturovanu
    listu retrieved odluka (TAU-014's own fix: `koriscena_praksa` u odgovoru
    je sada STVARNO ono što je pretraženo/dostupno, ne GPT-ovo sopstveno
    necitirano tvrdjenje o procentu). Ne trazi da GPT sam cituje broj odluke
    (izbegava hallucination-grounding rizik) -- umesto toga posteno prikazuje
    sta je STVARNO pronadjeno, pored procenta."""
    if not _RAG_AVAILABLE:
        return "", []
    try:
        odluke = retrieve_sudska_praksa(query[:300], top_k)
    except Exception as exc:
        _sentry_capture(exc)
        logger.warning("[PREDICTOR] RAG greška: %s", exc)
        return "", []
    if not odluke:
        return "", []
    delovi = []
    lista = []
    for m in odluke:
        meta = getattr(m, "metadata", {}) or {}
        court = meta.get("court") or meta.get("sud") or "Sud"
        broj = meta.get("decision_number") or ""
        tekst = (meta.get("text") or meta.get("parent_text") or "").strip()[:400]
        if tekst:
            delovi.append(f"[{court} {broj}] {tekst}")
            lista.append({"sud": court, "broj": broj or None})
    return "\n\n".join(delovi), lista


def _case_context_blok(cc: Optional[dict]) -> str:
    """Program Tau, Master Sprint 005 (2026-08-06) -- formats
    shared/case_context.py::build_case_context()'s own canonical fields into
    a text block for GPT context. Reused across every endpoint below that
    accepts predmet_id -- NOT a new context source, this only presents the
    ONE canonical builder's own already-fetched data (same idiom as
    case_commander.py's own _formatiraj_kontekst / case_intelligence.py's
    own _build_context_text, both pre-existing consumers of their own
    canonical data)."""
    if not cc or cc.get("error"):
        return ""
    delovi = []

    readiness = (cc.get("readiness") or {}).get("value") or {}
    if readiness.get("status"):
        delovi.append(f"READINESS PREDMETA (kanonski status iz sistema): {readiness['status']} — {readiness.get('razlog','')}")

    key_facts = (cc.get("key_facts") or {}).get("value")
    if key_facts:
        pt = key_facts.get("pravna_teorija") or {}
        if isinstance(pt, dict) and pt.get("sustina_spora"):
            delovi.append(f"GENOME — suština spora (već izračunato): {pt['sustina_spora']}")
        if key_facts.get("snaga_predmeta_procent") is not None:
            delovi.append(f"GENOME — snaga predmeta (već izračunata, ne izmišljaj novu): {key_facts['snaga_predmeta_procent']}%")
        nt = key_facts.get("najslabija_tacka") or {}
        if isinstance(nt, dict) and nt.get("rizik"):
            delovi.append(f"GENOME — najslabija tačka: {nt['rizik']} (kritičnost {nt.get('kriticnost','?')})")

    missing = ((cc.get("missing_evidence") or {}).get("value")) or []
    if missing:
        delovi.append("NEDOSTAJUĆI DOKAZI (kanonski, iz Gap Engine-a): " + "; ".join(
            g.get("razlog", "") for g in missing[:5] if g.get("razlog")))

    contra = ((cc.get("contradictions") or {}).get("value")) or []
    if contra:
        delovi.append("KONTRADIKCIJE U PREDMETU (kanonske, iz Genome-a): " + "; ".join(
            g.get("razlog", "") for g in contra[:5] if g.get("razlog")))

    actions = ((cc.get("active_actions") or {}).get("value")) or []
    if actions:
        delovi.append(f"OTVORENE AKCIJE U SISTEMU ({len(actions)}): " + "; ".join(
            (a.get("razlog") or "")[:100] for a in actions[:5]))

    deadlines = ((cc.get("deadlines") or {}).get("value")) or []
    upcoming = [d for d in deadlines if not d.get("proslo")]
    if upcoming:
        delovi.append(f"PREDSTOJEĆA ROČIŠTA/ROKOVI ({len(upcoming)}): " + "; ".join(
            f"{d.get('sud','')} {d.get('datum','')}" for d in upcoming[:5]))

    participants = (cc.get("participants") or {}).get("value") or {}
    if participants.get("stranka") or participants.get("protivnik"):
        delovi.append(f"STRANKE (iz sistema, proveri protiv unetih): {participants.get('stranka','?')} protiv {participants.get('protivnik','?')}")

    # Only populated when the caller passed include_documents=True
    # (prediktuj_ishod/battle_report) -- Document Visibility Engine's own
    # bounded excerpt set (Tau 002), reused as-is, not re-sampled here.
    rel_docs = ((cc.get("relevant_documents") or {}).get("value")) or {}
    included = rel_docs.get("included") or []
    if included:
        doc_delovi = [f"  - {d.get('naziv','')}: {(d.get('excerpt') or '')[:600]}" for d in included[:8]]
        not_included_n = len(rel_docs.get("not_included_but_retrievable") or [])
        delovi.append("DOKUMENTI U DOSIJEU (stvaran sadržaj, iz sistema):\n" + "\n".join(doc_delovi) + (
            f"\n  (+ još {not_included_n} dokumenata u dosijeu, nisu prikazani ovde)" if not_included_n else ""))

    if not delovi:
        return ""
    return "STVARNO STANJE PREDMETA U SISTEMU (kanonski izvor — koristi OVO kao osnovu, ne izmišljaj suprotno):\n" + "\n".join(delovi)


async def _dohvati_case_context_ako_postoji(predmet_id: Optional[str], uid: str, supa, include_documents: bool = False) -> Optional[dict]:
    """Program Tau, Master Sprint 005 -- thin, fail-soft wrapper around a
    single build_case_context() call, reused by every endpoint below. Not a
    new context builder (it calls the ONE canonical function directly and
    does nothing else); exists only so 7 call sites don't each repeat the
    same try/except. Returns None when predmet_id is absent (most live
    calls today -- this whole file's own UI is primarily a "paste your case
    text" tool, not always opened from a tracked case) or when the fetch
    fails -- callers must already handle a missing case context gracefully
    since that's the CURRENT, unmigrated behavior for every one of these
    endpoints.

    `include_documents` defaults False (lightweight -- readiness/Genome/gaps/
    actions/deadlines only, no document fetch) since 5 of this file's own 7
    endpoints don't center their reasoning on raw document text. Phase 3's
    own context-certification found `prediktuj_ishod`/`battle_report`
    specifically SHOULD see real evidence excerpts (their whole job is
    analyzing the case's own strength) -- those 2 call sites pass True."""
    if not predmet_id:
        return None
    try:
        return await build_case_context(predmet_id, uid, supa, include_documents=include_documents)
    except Exception as exc:
        _sentry_capture(exc)
        logger.warning("[PREDICTOR] build_case_context greška (nastavlja bez kanonskog konteksta): %s", exc)
        return None


async def _verifikovan_predmet_id(predmet_id: Optional[str], uid: str, supa) -> Optional[str]:
    """Program Lambda, Certification 002 (Ownership & IDOR): every one of this
    file's own 7 analysis-persist inserts stored `predmet_id` verbatim from
    the request body with no ownership check -- a caller could tag their own
    `predictor_analize`/`hearing_briefovi` row with someone else's case id.
    No cross-tenant READ resulted (every read of these tables is already
    scoped by `user_id`), but the row itself was FK-pollution. Returns the id
    back unchanged only if it actually belongs to `uid`, else None (same
    "silently drop the untrusted id" shape already used for `dokument_id` in
    `routers/evidence.py::add_dokaz`)."""
    if not predmet_id:
        return None
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", uid).maybe_single().execute()
        )
        return predmet_id if r.data else None
    except Exception:
        return None


@router.post("/api/predictor/analiza")
@limiter.limit("10/minute")
async def prediktuj_ishod(
    request: Request,
    payload: PredictorRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """AI predviđanje ishoda sudskog postupka."""
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    if not payload.opis_predmeta or len(payload.opis_predmeta) < 20:
        raise HTTPException(status_code=400, detail="Opis predmeta je prekratak (minimum 20 karaktera).")

    if payload.tip_postupka not in ["gradjansko", "krivicno", "radno", "upravno", "privredno"]:
        raise HTTPException(status_code=400, detail="Nepoznat tip postupka.")

    dokazi_txt = "\n".join([f"- {d}" for d in payload.dokazi]) if payload.dokazi else "Nisu navedeni"

    # CELINA 2 (2026-07-24): sistemski prompt tvrdi da se analiza bazira na
    # "sudskoj praksi srpskih sudova", ali ranije nijedan poziv nije stvarno
    # pretraživao praksu -- procena je bila isključivo iz opšteg znanja
    # modela. Sada stvarno pretražuje pre nego što tvrdi da je koristila.
    rag_query = f"{payload.tip_postupka} {payload.cinjenicni_opis}"[:600]
    rag_kontekst, koriscena_praksa = await asyncio.to_thread(_rag_praksa_blok, rag_query, 6)

    # Program Tau, Master Sprint 005 (2026-08-06) -- TAU-011's own fix: when
    # predmet_id is present, this is no longer a "paste your own text and
    # get a prediction blind to the tracked case" call. See
    # _dohvati_case_context_ako_postoji's own docstring for why this stays
    # None (not an error) when predmet_id is absent -- most live calls to
    # this specific endpoint today have no predmet_id at all (the shared
    # Strategija-tab UI is a general-purpose tool, not always opened from a
    # tracked case). include_documents=True -- this endpoint's whole job is
    # analyzing the case's own evidentiary strength, so real document
    # excerpts (not just readiness/Genome signals) belong in its prompt.
    case_context = await _dohvati_case_context_ako_postoji(payload.predmet_id, uid, supa, include_documents=True)
    case_context_blok = _case_context_blok(case_context)

    user_prompt = f"""PREDMET ZA ANALIZU:

Tip postupka: {payload.tip_postupka.upper()}
Sud: {payload.sud or "Nije navedeno"}

OPIS: {payload.opis_predmeta}

CINJENICE:
{payload.cinjenicni_opis}

DOSTUPNI DOKAZI:
{dokazi_txt}

ARGUMENTI SUPROTNE STRANE:
{payload.suprotna_strana_argumenti or "Nisu poznati"}
""" + (
        f"\nRELEVANTNA SUDSKA PRAKSA:\n{rag_kontekst}\n"
        if rag_kontekst else
        "\nNapomena: nije pronađena relevantna sudska praksa u bazi — procena bazirana na opštem pravnom znanju.\n"
    ) + (f"\n{case_context_blok}\n" if case_context_blok else ""
    ) + _strana_instrukcija(payload.strana)

    try:
        from openai import OpenAI
        from shared.ai_provenance import case_context as _ai_case_ctx
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="prediktuj_ishod"):
            raw = await asyncio.to_thread(_pozovi_predictor_api, oai, user_prompt)
        import json as _json
        rezultat = _json.loads(raw)
        analiza = (rezultat.get("analiza") or "").strip()

        # Operation Single Brain (2026-08-07): unconditional range sanity, applied
        # regardless of readiness status (and even if case_context itself failed to
        # fetch, unlike the conditional cap below) -- matches hearing_cc.py's own
        # BLACKSWAN-AI-003 fix. This mission's Team 4 (AI Boundary) confirmed this
        # endpoint previously returned procenat_min/procenat_max raw whenever
        # readiness wasn't at an extreme, with no floor/ceiling and no min<=max
        # ordering check at all.
        for _k in ("procenat_min", "procenat_max"):
            _v0 = rezultat.get(_k)
            if isinstance(_v0, (int, float)):
                rezultat[_k] = max(0, min(100, _v0))

        # Program Tau, Master Sprint 005 -- Phase 4 grounding requirement:
        # a case in a canonically CRITICAL_GAP/BLOCKED readiness state must
        # not structurally receive a confident high percentage that ignores
        # that fact. Deterministic cap, not a 2nd GPT opinion -- reuses
        # shared/case_readiness.py's own already-computed status, invents no
        # new scoring.
        if case_context and not case_context.get("error"):
            _readiness_status = ((case_context.get("readiness") or {}).get("value") or {}).get("status")
            # Operation Single Brain (2026-08-07): sourced from shared/case_readiness.py's
            # CAP_BY_READINESS -- this file, digital_twin.py, and hearing_cc.py all import
            # the same dict now instead of each redeclaring an identical copy.
            _cap = CAP_BY_READINESS.get(_readiness_status)
            if _cap is not None:
                for _k in ("procenat_min", "procenat_max"):
                    _v = rezultat.get(_k)
                    if isinstance(_v, (int, float)) and _v > _cap:
                        rezultat[_k] = _cap

        # Operation Single Brain (2026-08-07): the prompt instructs GPT to keep
        # min<=max but nothing enforced it -- Team 4 found no ordering check existed.
        # If GPT (or the cap above, in a pathological case) inverted the pair, swap
        # them rather than shipping a nonsensical "min > max" range to the lawyer.
        _pmin, _pmax = rezultat.get("procenat_min"), rezultat.get("procenat_max")
        if isinstance(_pmin, (int, float)) and isinstance(_pmax, (int, float)) and _pmin > _pmax:
            rezultat["procenat_min"], rezultat["procenat_max"] = _pmax, _pmin

        # Sacuvaj analizu
        try:
            _pid = await _verifikovan_predmet_id(payload.predmet_id, uid, supa)
            await asyncio.to_thread(
                lambda: supa.table("predictor_analize").insert({
                    "user_id":      uid,
                    "predmet_id":   _pid,
                    "tip_postupka": payload.tip_postupka,
                    "opis":         payload.opis_predmeta[:500],
                    "analiza":      analiza[:5000],
                }).execute()
            )
            from shared.audit_immutable import log_action
            asyncio.create_task(log_action(
                action="court_predictor_analiza", user_id=uid,
                resource_type="predmet", resource_id=payload.predmet_id,
            ))
        except Exception as _exc:
            _sentry_capture(_exc)
            pass

        preostalo = await UsageService.consume(uid, email, "court_predictor")

        return {
            "analiza":                analiza,
            "procenat_min":           rezultat.get("procenat_min"),
            "procenat_max":           rezultat.get("procenat_max"),
            # S5-1: the number now travels with its subject. None means the
            # caller did not say which side they represent, and the UI must say
            # so rather than implying the percentage is theirs.
            "procenat_strana":        (payload.strana or "").strip().lower() or None,
            "procenat_znacenje":      (
                _STRANA_LABELE.get((payload.strana or "").strip().lower())
                or "Strana nije navedena — u tekstu analize piše na koju se stranu procenat odnosi."
            ),
            "kljucni_faktori_za":     rezultat.get("kljucni_faktori_za", []),
            "kljucni_faktori_protiv": rezultat.get("kljucni_faktori_protiv", []),
            "preporucena_strategija": rezultat.get("preporucena_strategija", ""),
            "rizici":                 rezultat.get("rizici", []),
            "rag_dostupan":           bool(rag_kontekst),
            # TAU-014 fix: the ACTUAL retrieved precedent set, not a GPT claim
            # about which ones it used -- honest reporting, no new grounding
            # mechanism needed since nothing here trusts a GPT-made citation.
            "koriscena_praksa":       koriscena_praksa,
            "tip_postupka":           payload.tip_postupka,
            # TAU-011 fix: whether this specific call actually consulted the
            # tracked case's own canonical state (readiness/Genome/gaps),
            # not just caller-typed text.
            "kontekst_predmeta_koriscen": bool(case_context_blok),
            "credits_remaining":      preostalo,
            # Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-026): read-only
            # disclosure, same reasoning as routers/digital_twin.py's own note.
            "top_open_action":        ((case_context or {}).get("top_open_action") or {}).get("value"),
            # Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-025): additive
            # AI-advisory marker, same narrow disclosure as Digital Twin's own
            # (routers/digital_twin.py) -- see that file's note for full
            # reasoning on why full Case Commander schema parity is out of
            # bounded-fix scope.
            "ai_generated":           True,
        }

    except HTTPException:
        raise
    except Exception as e:
        _sentry_capture(e)
        logger.error("Court predictor greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri analizi: {str(e)}")


# ── Battle Report ─────────────────────────────────────────────────────────────

class BattleReportRequest(BaseModel):
    predmet_id:      Optional[str]       = None
    tip_postupka:    str
    opis_predmeta:   str
    sud:             Optional[str]       = None
    sudija:          Optional[str]       = None
    protivnicki_adv: Optional[str]       = None
    protivnik_naziv: Optional[str]       = None
    vrednost_spora:  Optional[str]       = None
    dokazi:          Optional[list[str]] = []


_BATTLE_REPORT_SYSTEM = """Ti si ekspertni pravni strateg sa 30 godina iskustva u srpskim sudovima.
Pises BATTLE REPORT — strateski dokument koji advokatu govori sve sto treba da zna pre rocista.

Format UVEK mora biti:

## ANALIZA TUZENE STRANE
[Ko je protivnik, kakva je njihova pravna pozicija, sta znamo o njima]

## ANALIZA SUDA / SUDIJE
[Na osnovu navedenog suda i sudije: tendencije, poznati obrasci odlucivanja. Ako sudija nije naveden — navedi opste karakteristike tog suda.]

## GDE CE NAPADATI
[Konkretne rupe u tvojoj poziciji koje ce protivna strana iskoristiti]

## GDE GRESE
[Slabosti protivnika koje mozes iskoristiti]

## KRITICNI FAKTORI
[2-3 faktora koji ce presuditi ishod]

## PREPORUCENA STRATEGIJA
[Konkretna taktika — ne genericka, nego prilagodjena ovom predmetu]

## RIZIK SCENARIJI
- Optimisticno (X%-Y%): [sta se mora desiti]
- Realisticno (X%-Y%): [najverovatniji ishod]
- Pesimisticno (X%-Y%): [sta moze poci naopako]

Ako je dostavljena SUDSKA PRAKSA ispod, oslanjaj se na konkretne odluke u
sekciji ANALIZA SUDA / SUDIJE i KRITICNI FAKTORI; ako nije dostavljena, jasno
navedi da je ta sekcija bazirana na opštem znanju, ne na konkretnoj praksi.

Ako je dat blok "STVARNO STANJE PREDMETA U SISTEMU" — to je već izračunata,
kanonska istina (readiness, Genome, nedostajući dokazi, kontradikcije, otvorene
akcije). U sekciji GDE CE NAPADATI i KRITICNI FAKTORI eksplicitno uzmi u obzir
svaki nedostajući dokaz/kontradikciju odatle — ne izmišljaj drugačiju sliku
predmeta od one koju sistem već zna.

Ekavica. Direktan ton. Bez uvoda i zakljucka — samo analiza."""


@llm_retry
def _pozovi_battle_report_api(oai_client, user_prompt: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo battle_report -- izdvojen jer
    vanjska funkcija ima sopstveni try/except."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _BATTLE_REPORT_SYSTEM},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=2000,
        temperature=0.3,
        timeout=25.0,
    )
    return resp.choices[0].message.content.strip()


@router.post("/api/predictor/battle-report")
@limiter.limit("10/minute")
async def battle_report(
    request: Request,
    payload: BattleReportRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """
    Battle Report: kompletna strateška analiza pre ročišta.
    Analizira sudiju, protivnika, slabosti i strategiju.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    if not payload.opis_predmeta or len(payload.opis_predmeta) < 30:
        raise HTTPException(status_code=400, detail="Opis predmeta je prekratak.")

    if payload.tip_postupka not in ["gradjansko", "krivicno", "radno", "upravno", "privredno"]:
        raise HTTPException(status_code=400, detail="Nepoznat tip postupka.")

    dokazi_txt = "\n".join([f"- {d}" for d in payload.dokazi]) if payload.dokazi else "Nisu navedeni"

    # CELINA 2 (2026-07-24): ista popravka kao prediktuj_ishod -- Battle
    # Report obećava analizu suda/sudije "na osnovu poznatih obrazaca", ali
    # ranije nikad nije pretraživao sudsku praksu.
    rag_query = f"{payload.tip_postupka} {payload.sud or ''} {payload.sudija or ''} {payload.opis_predmeta}"[:600]
    rag_kontekst, koriscena_praksa = await asyncio.to_thread(_rag_praksa_blok, rag_query, 6)

    # Program Tau, Master Sprint 005 -- TAU-011 fix, same pattern as
    # prediktuj_ishod above. This is the ONE endpoint in this file whose own
    # live frontend caller (stratBattleReport) already sends predmet_id when
    # available (activePredmetId) -- so this migration has immediate live
    # effect, not just a dormant capability. include_documents=True for the
    # same reason as prediktuj_ishod -- a battle-prep document needs real
    # evidence, not just readiness/Genome signals.
    case_context = await _dohvati_case_context_ako_postoji(payload.predmet_id, uid, supa, include_documents=True)
    case_context_blok = _case_context_blok(case_context)

    user_prompt = f"""BATTLE REPORT — PRIPREMA ZA POSTUPAK

Tip postupka: {payload.tip_postupka.upper()}
Sud: {payload.sud or "Nije naveden"}
Sudija: {payload.sudija or "Nije poznat"}
Protivnicka strana: {payload.protivnik_naziv or "Nije navedena"}
Protivnicka advokatska kancelarija: {payload.protivnicki_adv or "Nije poznata"}
Vrednost spora: {payload.vrednost_spora or "Nije navedena"}

OPIS PREDMETA:
{payload.opis_predmeta}

DOSTUPNI DOKAZI:
{dokazi_txt}
""" + (
        f"\nSUDSKA PRAKSA:\n{rag_kontekst}\n" if rag_kontekst else
        "\nNapomena: nije pronađena relevantna sudska praksa u bazi.\n"
    ) + (f"\n{case_context_blok}\n" if case_context_blok else ""
    ) + "\nNapravi kompletan Battle Report."

    try:
        from openai import OpenAI
        from shared.ai_provenance import case_context as _ai_case_ctx
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="battle_report"):
            report = await asyncio.to_thread(_pozovi_battle_report_api, oai, user_prompt)

        try:
            _pid = await _verifikovan_predmet_id(payload.predmet_id, uid, supa)
            await asyncio.to_thread(
                lambda: supa.table("predictor_analize").insert({
                    "user_id":      uid,
                    "predmet_id":   _pid,
                    "tip_postupka": payload.tip_postupka,
                    "opis":         payload.opis_predmeta[:500],
                    "analiza":      report[:8000],
                    "tip_analize":  "battle_report",
                }).execute()
            )
            from shared.audit_immutable import log_action
            asyncio.create_task(log_action(
                action="court_predictor_analiza", user_id=uid,
                resource_type="predmet", resource_id=payload.predmet_id,
            ))
        except Exception as _exc:
            _sentry_capture(_exc)
            pass

        preostalo = await UsageService.consume(uid, email, "court_predictor")

        return {
            "battle_report":      report,
            "tip_postupka":       payload.tip_postupka,
            "sud":                payload.sud,
            "rag_dostupan":       bool(rag_kontekst),
            "koriscena_praksa":   koriscena_praksa,
            "kontekst_predmeta_koriscen": bool(case_context_blok),
            "credits_remaining":  preostalo,
        }

    except HTTPException:
        raise
    except Exception as e:
        _sentry_capture(e)
        logger.error("Battle report greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri generisanju: {str(e)}")


# ── Hearing Prep Auto-Brief ────────────────────────────────────────────────────

class HearingPrepRequest(BaseModel):
    predmet_id:         Optional[str] = None
    rociste_naziv:      str
    datum_rocista:      str
    tip_postupka:       str
    opis_predmeta:      str
    poslednji_podnesak: Optional[str] = None


_HEARING_PREP_SYSTEM = """Ti si iskusni pravni asistent koji priprema advokata za rociste.
Pises 1-stranicki briefing koji advokat moze da procita za 5 minuta pre ulaska u sudnicu.

Format:
## STA OCEKIVATI DANAS
[Kratko — sta ce se verovatno desiti na ovom rocistu]

## KLJUCNI ARGUMENTI (za poneti sa sobom)
[3-5 najvaznijih argumenata, s referencama na dokaze]

## MOGUCA PITANJA SUDA
[2-3 pitanja koja sudija moze postaviti i predlozeni odgovori]

## AKO PROTIVNA STRANA KAZE...
[1-2 verovatna napada i kako odgovoriti]

## NE ZABORAVI
[Dokumenta, potvrde, overene kopije koje treba poneti]

Ako je dat blok "STVARNO STANJE PREDMETA U SISTEMU" — u KLJUCNI ARGUMENTI eksplicitno pomeni otvorene
akcije i nedostajuće dokaze odatle ako postoje relevantni za ovo ročište.

Koncizan, direktan, praktican. Ekavica."""


@llm_retry
def _pozovi_hearing_prep_api(oai_client, user_msg: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo hearing_prep_brief."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _HEARING_PREP_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=1000,
        temperature=0.4,
        timeout=25.0,
    )
    return resp.choices[0].message.content.strip()


@router.post("/api/predictor/hearing-prep")
@limiter.limit("20/minute")
async def hearing_prep_brief(
    request: Request,
    payload: HearingPrepRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """
    Auto-brief za ročište — 1 stranica, sve što treba znati pre ulaska u sudnicu.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    if not payload.opis_predmeta or len(payload.opis_predmeta) < 20:
        raise HTTPException(status_code=400, detail="Opis predmeta je prekratak.")

    podnesak_txt = (
        f"\nPoslednji podnesak / belezka:\n{payload.poslednji_podnesak[:1000]}"
        if payload.poslednji_podnesak else ""
    )

    # Program Tau, Master Sprint 005 -- TAU-011 fix, same pattern as the
    # other endpoints. Also: a real, checkable cross-check that had no
    # mechanism before -- does payload.datum_rocista actually match a real
    # rociste this case has on file? A caller could type any date; this
    # doesn't block the brief (still fail-soft, per this file's own
    # convention), it just tells GPT the truth so it doesn't build false
    # confidence into "STA OCEKIVATI DANAS."
    case_context = await _dohvati_case_context_ako_postoji(payload.predmet_id, uid, supa)
    case_context_blok = _case_context_blok(case_context)
    rociste_potvrdjeno = False
    if case_context and not case_context.get("error"):
        _deadlines = ((case_context.get("deadlines") or {}).get("value")) or []
        rociste_potvrdjeno = any(str(d.get("datum") or "")[:10] == payload.datum_rocista[:10] for d in _deadlines)
        if case_context_blok and not rociste_potvrdjeno:
            case_context_blok += f"\nNAPOMENA: datum ročišta ({payload.datum_rocista}) NE odgovara nijednom zabeleženom ročištu/roku za ovaj predmet u sistemu — proveri da li je datum tačan."

    user_msg = f"""PRIPREMA ZA ROCISTE: {payload.rociste_naziv}
Datum: {payload.datum_rocista}
Tip: {payload.tip_postupka}

{payload.opis_predmeta}{podnesak_txt}""" + (f"\n\n{case_context_blok}" if case_context_blok else "")

    try:
        from openai import OpenAI
        from shared.ai_provenance import case_context as _ai_case_ctx
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="hearing_prep"):
            brief = await asyncio.to_thread(_pozovi_hearing_prep_api, oai, user_msg)

        if payload.predmet_id:
            try:
                _pid = await _verifikovan_predmet_id(payload.predmet_id, uid, supa)
                if _pid:
                    await asyncio.to_thread(
                        lambda: supa.table("hearing_briefovi").insert({
                            "user_id":       uid,
                            "predmet_id":    _pid,
                            "rociste_naziv": payload.rociste_naziv,
                            "datum":         payload.datum_rocista,
                            "brief":         brief[:5000],
                        }).execute()
                    )
                from shared.audit_immutable import log_action
                asyncio.create_task(log_action(
                    action="court_predictor_analiza", user_id=uid,
                    resource_type="predmet", resource_id=payload.predmet_id,
                ))
            except Exception as _exc:
                _sentry_capture(_exc)
                pass

        preostalo = await UsageService.consume(uid, email, "court_predictor")

        return {
            "brief":              brief,
            "rociste_naziv":      payload.rociste_naziv,
            "datum_rocista":      payload.datum_rocista,
            "rociste_potvrdjeno_u_sistemu": rociste_potvrdjeno if case_context else None,
            "kontekst_predmeta_koriscen": bool(case_context_blok),
            "credits_remaining":  preostalo,
        }

    except HTTPException:
        raise
    except Exception as e:
        _sentry_capture(e)
        logger.error("Hearing prep greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri generisanju: {str(e)}")


# ── Faktori ───────────────────────────────────────────────────────────────────

@router.get("/api/predictor/faktori")
async def get_faktori(user: dict = Depends(get_current_user)):
    """Lista faktora koji utiču na ishod po tipu postupka."""
    return {
        "faktori": {
            "gradjansko": [
                "Jacina pisanih dokaza (ugovori, priznanice)",
                "Svedoci i njihova verodostojnost",
                "Zastarelost potrazivanja",
                "Teret dokazivanja",
                "Sudska praksa u slicnim slucajevima",
            ],
            "krivicno": [
                "Alibi optuzenog",
                "Verodostojnost svedoka",
                "Materijalni dokazi i lanac staranja",
                "Vestacenja (sudski vestaci)",
                "Prethodne osude",
            ],
            "radno": [
                "Pismeni otkazni akt i procedure",
                "Evidencija o radu i ucinku",
                "Kolektivni ugovor i pravilnik",
                "Rok za osporavanje otkaza",
                "Diskriminatorski osnov",
            ],
            "upravno": [
                "Zakonitost upravnog akta",
                "Postovanje procedure donosenja",
                "Obrazlozenost odluke",
                "Rok za zalbu",
                "Nadleznost organa",
            ],
            "privredno": [
                "Ugovorna dokumentacija",
                "Finansijski izvestaji i vestak",
                "Registracioni podaci privrednog subjekta",
                "Likvidnost tuzene strane",
                "Medjunarodna arbitraza (ako postoji klauzula)",
            ],
        }
    }


# ── Argument Reputation Engine ────────────────────────────────────────────────

class ArgumentReputationRequest(BaseModel):
    tip_spora: str
    argumenti: list[str]
    sud: Optional[str] = None
    predmet_id: Optional[str] = None


_ARG_REPUTATION_SYSTEM = """Ti si srpski pravni analitičar sa pristupom sudskoj praksi.
Analiziraš argumente koje advokat planira da koristi u postupku i procenjuješ njihovu uspešnost
na osnovu dostavljenih odluka sudova.

Odgovori SAMO validnim JSON-om:
{
  "argumenti_analiza": [
    {
      "argument": "tekst argumenta",
      "uspesnost_procena": 72,
      "boja": "zelena",
      "obrazlozenje": "U 70%+ relevantnih odluka sudovi su prihvatali ovaj tip argumenta...",
      "preporuka": "Konkretan savet kako da se pojača ovaj argument",
      "relevantne_odluke": 5
    }
  ],
  "ukupna_snaga": 68,
  "slabosti": ["Argument X je slabo potkrepljen praksom..."],
  "preporuceni_redosled": ["argument najjači", "argument srednji"],
  "alternativni_argumenti": ["Razmotrite dodavanje argumenta o..."]
}

Pravila:
- uspesnost_procena 0-100 (0=nikad ne prolazi, 100=uvek prolazi)
- boja: "zelena" ako >=65, "žuta" ako 35-64, "crvena" ako <35
- Ekavica strogo. Nema ijekavice.
- Budi konkretan, ne generički.
- Ako je dat blok "STVARNO STANJE PREDMETA U SISTEMU" — argument koji se oslanja na dokaz koji je tamo
  označen kao nedostajući mora dobiti nižu uspesnost_procena i to mora biti pomenuto u obrazloženje."""


@llm_retry
def _pozovi_arg_reputation_api(oai_client, user_msg: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo argument_reputation."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _ARG_REPUTATION_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=2000,
        temperature=0.25,
        timeout=25.0,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or "{}"


@router.post("/api/predictor/argument-reputation")
@limiter.limit("5/minute")
async def argument_reputation(
    request: Request,
    payload: ArgumentReputationRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """
    Argument Reputation Engine — procenjuje uspešnost argumenata na osnovu 54k+ srpskih odluka.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    if not payload.argumenti:
        raise HTTPException(status_code=400, detail="Morate navesti najmanje jedan argument.")
    if len(payload.argumenti) > 10:
        raise HTTPException(status_code=400, detail="Maksimalno 10 argumenata po zahtevu.")

    # RAG pretraga za svaki argument
    rag_kontekst = ""
    # Program Phoenix, Mission 009 (LIVINGSYS-DEBT-047): only the first 5 of up to 10 allowed
    # arguments ever get a real retrieval pass below -- arguments 6-10's "relevantne_odluke"
    # claim is pure model output with zero grounding. Extending retrieval to all 10 is real
    # added latency/cost; this tracks which arguments actually got a grounded pass so the
    # response can disclose it per-argument instead of silently presenting all 10 the same way.
    _grounded_argumenti: set[str] = set()
    if _RAG_AVAILABLE:
        try:
            rag_delovi = []
            for arg in payload.argumenti[:5]:
                query = f"{payload.tip_spora} {arg} {payload.sud or ''}"
                odluke = await asyncio.to_thread(retrieve_sudska_praksa, query.strip()[:300], 4)
                if odluke:
                    _grounded_argumenti.add(arg)
                    tekstovi = []
                    for m in odluke:
                        meta = getattr(m, "metadata", {}) or {}
                        court = meta.get("court") or meta.get("sud") or "Sud"
                        # CELINA 2 (2026-07-24) bug fix: metadata ključ je "text"
                        # (i "parent_text" kao fallback), ne "tekst" -- pinecone
                        # match objekti takodje nemaju .page_content (to je
                        # LangChain Document konvencija, ne Pinecone SDK). Ova
                        # tri poziva su ranije UVEK slala prazan tekst modelu.
                        tekst = (meta.get("text") or meta.get("parent_text") or "")[:400]
                        tekstovi.append(f"[{court}] {tekst}")
                    rag_delovi.append(
                        f"ARGUMENT: {arg}\nODLUKE ({len(odluke)}):\n" + "\n".join(tekstovi)
                    )
            rag_kontekst = "\n\n".join(rag_delovi)
        except Exception as e:
            _sentry_capture(e)
            logger.warning("[ARG_REP] RAG greška: %s", e)

    pouzdanost_napomena = "" if rag_kontekst else "\nNapomena: RAG nije dostupan — analiza bazirana samo na znanju modela."

    # Program Tau, Master Sprint 005 -- TAU-011 fix, same pattern.
    case_context = await _dohvati_case_context_ako_postoji(payload.predmet_id, uid, supa)
    case_context_blok = _case_context_blok(case_context)

    user_msg = (
        f"Tip spora: {payload.tip_spora}\n"
        f"Sud: {payload.sud or 'nije naveden'}\n\n"
        f"ARGUMENTI ZA ANALIZU:\n" +
        "\n".join(f"- {a}" for a in payload.argumenti) +
        (f"\n\nRELEVANTNA SUDSKA PRAKSA:\n{rag_kontekst}" if rag_kontekst else "") +
        pouzdanost_napomena +
        (f"\n\n{case_context_blok}" if case_context_blok else "")
    )

    from openai import OpenAI
    from shared.ai_provenance import case_context as _ai_case_ctx
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    try:
        import json
        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="argument_reputation"):
            raw = await asyncio.to_thread(_pozovi_arg_reputation_api, oai, user_msg)
        rezultat = json.loads(raw)
        # Program Gamma (2026-08-04) -- prompt sam navodi proverljivo pravilo
        # (linija ~593: "zelena" >=65 / "žuta" 35-64 / "crvena" <35) ali je
        # 'boja' vracana sirova, nikad provezena protiv sopstvenog
        # uspesnost_procena -- ista klasa koju je Program Beta popravio za
        # sistemsko_upozorenje. Kod ovde racuna boju iz vec vracenog broja,
        # ne trazi novi LLM poziv.
        # Olympus Faza 10 governance nalaz (2026-08-04, AI Governance):
        # response_format=json_object garantuje samo validan JSON na vrhu,
        # ne da je uspesnost_procena STVARNO int (npr. GPT vratio "72" kao
        # string) -- prethodna verzija je u tom slucaju tiho preskakala
        # prevoznjenje i propustala sirovu (potencijalno neuskladjenu) boju.
        # Sada se pokusava bezbedna koercija pre odustajanja.
        for _a in (rezultat.get("argumenti_analiza") or []):
            if not isinstance(_a, dict):
                continue
            # Program Phoenix, Mission 009 (LIVINGSYS-DEBT-047): disclose whether this specific
            # argument's "relevantne_odluke"/uspesnost_procena claim had a real retrieval pass
            # behind it -- a text-match miss (model paraphrased the argument back) fails safe
            # to False rather than overclaiming grounding.
            _a["rag_grounded"] = (_a.get("argument") or "").strip() in _grounded_argumenti
            _proc = _a.get("uspesnost_procena")
            if isinstance(_proc, str):
                try:
                    _proc = float(_proc.strip())
                except (ValueError, TypeError):
                    _proc = None
            if isinstance(_proc, (int, float)):
                # Operation One Truth (2026-08-07): 'boja' was already correctly
                # re-derived from this number (Program Gamma fix above), but the
                # number itself was never clamped to its own documented 0-100 range
                # -- unlike snaga_predmeta_procent's sibling clamp in case_dna.py, a
                # fabricated out-of-range GPT claim here reached the lawyer's screen
                # and predictor_analize (persisted, never re-validated on read).
                _proc = max(0, min(100, _proc))
                _a["uspesnost_procena"] = _proc
                _a["boja"] = "zelena" if _proc >= 65 else ("žuta" if _proc >= 35 else "crvena")
        _ukupna = rezultat.get("ukupna_snaga")
        if isinstance(_ukupna, str):
            try:
                _ukupna = float(_ukupna.strip())
            except (ValueError, TypeError):
                _ukupna = None
        if isinstance(_ukupna, (int, float)):
            rezultat["ukupna_snaga"] = max(0, min(100, _ukupna))

        # Operation Single Brain, Mission 002 (SINGLEBRAIN-DEBT-002 closure): this endpoint
        # was range-clamped (above) but never readiness-capped, unlike its sibling
        # prediktuj_ishod in this same file -- a CRITICAL_GAP/BLOCKED case could still show
        # a confident, uncapped argument-success percentage here while every other success-
        # probability surface on the same case was already capped. Same CAP_BY_READINESS
        # constant, same pattern, 6th consumer now.
        if case_context and not case_context.get("error"):
            _readiness_status = ((case_context.get("readiness") or {}).get("value") or {}).get("status")
            _cap = CAP_BY_READINESS.get(_readiness_status)
            if _cap is not None:
                for _a in (rezultat.get("argumenti_analiza") or []):
                    if isinstance(_a, dict):
                        _p = _a.get("uspesnost_procena")
                        if isinstance(_p, (int, float)) and _p > _cap:
                            _a["uspesnost_procena"] = _cap
                            _a["boja"] = "zelena" if _cap >= 65 else ("žuta" if _cap >= 35 else "crvena")
                _uk = rezultat.get("ukupna_snaga")
                if isinstance(_uk, (int, float)) and _uk > _cap:
                    rezultat["ukupna_snaga"] = _cap
    except Exception as e:
        _sentry_capture(e)
        logger.error("[ARG_REP] GPT greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri analizi: {str(e)}")

    try:
        _pid = await _verifikovan_predmet_id(payload.predmet_id, uid, supa)
        await asyncio.to_thread(
            lambda: supa.table("predictor_analize").insert({
                "user_id":      uid,
                "predmet_id":   _pid,
                "tip_postupka": payload.tip_spora,
                "opis":         "; ".join(payload.argumenti)[:500],
                "analiza":      json.dumps(rezultat, ensure_ascii=False)[:8000],
                "tip_analize":  "argument_reputation",
            }).execute()
        )
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            action="court_predictor_analiza", user_id=uid,
            resource_type="predmet", resource_id=payload.predmet_id,
        ))
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    preostalo = await UsageService.consume(uid, email, "court_predictor")

    return {
        **rezultat,
        "tip_spora":         payload.tip_spora,
        "rag_dostupan":      _RAG_AVAILABLE and bool(rag_kontekst),
        "kontekst_predmeta_koriscen": bool(case_context_blok),
        "credits_remaining": preostalo,
    }


# ── Judge Intelligence Profiler ───────────────────────────────────────────────

class JudgeProfileRequest(BaseModel):
    ime_sudije: Optional[str] = None
    sud: str
    tip_postupka: str
    predmet_id: Optional[str] = None


_JUDGE_PROFILE_SYSTEM = """Ti si srpski pravni analitičar koji profilira sudije i sudove
na osnovu sudske prakse. Cilj je da advokatu pomogneš da razumeš sa kim ima posla.

Odgovori SAMO validnim JSON-om:
{
  "sud": "naziv suda",
  "sudija": "ime sudije ili 'nije naveden'",
  "ukupno_odluka_analizirano": 12,
  "profil": {
    "tendencije": ["Sklon detaljnoj analizi pisanih dokaza", "Brzo odbacuje procesne prigovore"],
    "prosecno_trajanje_meseci": 14,
    "stopa_potvrdjivanja_zalbi": 35,
    "preferirani_argumenti": ["pisani dokazi", "ekspertska mišljenja"],
    "faktori_koje_ceni": ["uredna procesna dokumentacija", "jasna hronologija događaja"],
    "cega_se_kloniti": ["nejasni podnesci", "nedostatak pisanih dokaza"]
  },
  "strateska_preporuka": "Konkretna taktika prilagođena ovom sudu/sudiji",
  "pouzdanost_profila": "srednja",
  "upozorenje": "Profil baziran na sudskoj praksi, ne na ličnim podacima o sudiji."
}

- pouzdanost_profila: 'visoka' (10+ odluka), 'srednja' (5-9), 'niska' (<5 ili nema RAG)
- Ekavica strogo. Nema ijekavice."""


@llm_retry
def _pozovi_judge_profile_api(oai_client, user_msg: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo judge_profile."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _JUDGE_PROFILE_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=1500,
        temperature=0.2,
        timeout=25.0,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or "{}"


@router.post("/api/predictor/judge-profile")
@limiter.limit("5/minute")
async def judge_profile(
    request: Request,
    payload: JudgeProfileRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """
    Judge Intelligence Profiler — analiza suda/sudije iz 54k+ srpskih odluka.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    rag_kontekst = ""
    odluke_count = 0
    if _RAG_AVAILABLE:
        try:
            query = f"{payload.sud} {payload.ime_sudije or ''} {payload.tip_postupka} odluka presuda".strip()
            odluke = await asyncio.to_thread(retrieve_sudska_praksa, query[:300], 15)
            odluke_count = len(odluke)
            if odluke:
                delovi = []
                for m in odluke:
                    meta = getattr(m, "metadata", {}) or {}
                    court = meta.get("court") or meta.get("sud") or payload.sud
                    tekst = (meta.get("text") or meta.get("parent_text") or "")[:500]
                    delovi.append(f"[{court}] {tekst}")
                rag_kontekst = "\n\n".join(delovi)
        except Exception as e:
            _sentry_capture(e)
            logger.warning("[JUDGE_PROF] RAG greška: %s", e)

    # Program Tau, Master Sprint 005 -- TAU-011 fix. Per
    # docs/tau/COURT_PREDICTOR_FORENSIC_REPORT.md's own finding, this
    # endpoint's own request model has NO case-description field at all --
    # it's architecturally about a court/judge, not a specific case, the
    # same way strategija.py's own request models were found (Tau 002/003)
    # to have no predmet_id at all. Full context injection doesn't fit here;
    # the one legitimate, checkable thing case context adds is whether the
    # caller-typed court name actually matches the tracked case's own court.
    case_context = await _dohvati_case_context_ako_postoji(payload.predmet_id, uid, supa)
    sud_neslaganje = None
    if case_context and not case_context.get("error"):
        _case_sud = ((case_context.get("case_identity") or {}).get("value") or {}).get("sud")
        if _case_sud and payload.sud and _case_sud.strip().lower() != payload.sud.strip().lower():
            sud_neslaganje = _case_sud

    user_msg = (
        f"Sud: {payload.sud}\n"
        f"Sudija: {payload.ime_sudije or 'nije naveden'}\n"
        f"Tip postupka: {payload.tip_postupka}\n"
        f"Broj analiziranih odluka: {odluke_count}\n" +
        (f"\nRELEVANTNA PRAKSA:\n{rag_kontekst}" if rag_kontekst else
         "\nNapomena: RAG nije dostupan — analiza bazirana na opštem znanju o srpskim sudovima.")
    )

    from openai import OpenAI
    import json
    from shared.ai_provenance import case_context as _ai_case_ctx
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    try:
        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="judge_profile"):
            raw = await asyncio.to_thread(_pozovi_judge_profile_api, oai, user_msg)
        rezultat = json.loads(raw)
        rezultat["ukupno_odluka_analizirano"] = odluke_count
        # Program Gamma (2026-08-04) -- prompt sam navodi proverljivo pravilo
        # (linija ~747: "visoka" 10+/"srednja" 5-9/"niska" <5 ili nema RAG),
        # ali srednji opseg (5-9) je ranije ispao iz if/elif-a i tiho ostajao
        # na sirovoj GPT vrednosti -- jedini neproveren slucaj u inace vec
        # deterministicki izracunatom polju. Zatvoreno eksplicitnim else.
        if not _RAG_AVAILABLE or odluke_count < 5:
            rezultat["pouzdanost_profila"] = "niska"
        elif odluke_count >= 10:
            rezultat["pouzdanost_profila"] = "visoka"
        else:
            rezultat["pouzdanost_profila"] = "srednja"
        # Operation One Truth (2026-08-07): fields like stopa_potvrdjivanja_zalbi
        # ("appeal confirmation rate") and prosecno_trajanje_meseci are fully
        # GPT-invented -- no per-judge outcome database is queried anywhere in
        # this codebase (only general case-law RAG). Unlike ukupno_odluka_
        # analizirano/pouzdanost_profila above, which ARE grounded in the real
        # RAG hit count, these specific-sounding numbers were presented with no
        # signal they aren't measured. Disclosed explicitly rather than removed
        # (a founder product decision on whether to keep asking GPT for them at
        # all is separate from this mission's honesty-of-labeling scope).
        if isinstance(rezultat.get("profil"), dict):
            rezultat["profil"]["napomena_procena"] = (
                "Stopa potvrđivanja žalbi i prosečno trajanje su AI procene bazirane na opštem "
                "obrascu iz sudske prakse, ne izmerene statistike za ovog konkretnog sudiju."
            )
    except Exception as e:
        _sentry_capture(e)
        logger.error("[JUDGE_PROF] GPT greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri profilisanju: {str(e)}")

    try:
        _pid = await _verifikovan_predmet_id(payload.predmet_id, uid, supa)
        await asyncio.to_thread(
            lambda: supa.table("predictor_analize").insert({
                "user_id":      uid,
                "predmet_id":   _pid,
                "tip_postupka": payload.tip_postupka,
                "opis":         f"Sud: {payload.sud} | Sudija: {payload.ime_sudije or 'N/A'}",
                "analiza":      json.dumps(rezultat, ensure_ascii=False)[:8000],
                "tip_analize":  "judge_profile",
            }).execute()
        )
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            action="court_predictor_analiza", user_id=uid,
            resource_type="predmet", resource_id=payload.predmet_id,
        ))
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    preostalo = await UsageService.consume(uid, email, "court_predictor")

    return {
        **rezultat,
        "sud_neslaganje_sa_predmetom": sud_neslaganje,
        "credits_remaining": preostalo,
    }


# ── Opponent Intelligence ─────────────────────────────────────────────────────

class OpponentIntelRequest(BaseModel):
    protivnik_naziv: str
    protivnicki_adv: Optional[str] = None
    tip_postupka: str
    predmet_id: Optional[str] = None
    poznate_informacije: Optional[str] = None


_OPPONENT_INTEL_SYSTEM = """Ti si špijun-strateg koji prikuplja obaveštajne podatke o protivnoj strani u sudskom postupku.
Cilj je da advokatu pružiš sve što treba da zna o protivniku PRE nego što uđe u sudnicu.

Odgovori SAMO validnim JSON-om:
{
  "protivnik": "naziv protivnika",
  "advokatska_kancelarija": "naziv kancelarije ili 'nije naveden'",
  "analiza": {
    "poznati_stil": "Opis stila vođenja postupka na osnovu dostupnih podataka...",
    "taktike": ["Taktika 1", "Taktika 2"],
    "stopa_nagodbi": "nepoznato",
    "slabosti": ["Slabost 1", "Slabost 2"],
    "snage": ["Snaga 1", "Snaga 2"]
  },
  "preporucena_taktika": "Konkretna taktika za ovog protivnika",
  "upozorenja": ["Upozorenje 1", "Upozorenje 2"],
  "pouzdanost": "niska"
}

- stopa_nagodbi: "visoka" | "niska" | "nepoznato"
- pouzdanost: "visoka" (puno podataka) | "srednja" | "niska" (malo ili nimalo podataka)
- Ekavica strogo. Nema ijekavice.
- Budi direktan i konkretan, ne generički."""


@llm_retry
def _pozovi_opponent_intel_api(oai_client, user_msg: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo opponent_intel."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _OPPONENT_INTEL_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=1500,
        temperature=0.3,
        timeout=25.0,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or "{}"


@router.post("/api/predictor/opponent-intel")
@limiter.limit("5/minute")
async def opponent_intel(
    request: Request,
    payload: OpponentIntelRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """
    Opponent Intelligence — analiza protivne strane iz sudske prakse i internog CRM-a.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    # Interna istorija sa ovim protivnikom
    interni_kontekst = ""
    _interni_hit_count = 0
    try:
        hist_r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("naziv, status, opis")
                .eq("user_id", uid)
                .ilike("opis", f"%{payload.protivnik_naziv[:30]}%")
                .limit(5)
                .execute()
        )
        if hist_r.data:
            _interni_hit_count = len(hist_r.data)
            interni_kontekst = "INTERNI PREDMETI SA OVIM PROTIVNIKOM:\n" + "\n".join(
                f"- {p.get('naziv','?')} [{p.get('status','?')}]: {(p.get('opis') or '')[:150]}"
                for p in hist_r.data
            )
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    # RAG pretraga
    rag_kontekst = ""
    _rag_hit_count = 0
    if _RAG_AVAILABLE:
        try:
            query = f"{payload.protivnik_naziv} {payload.protivnicki_adv or ''} {payload.tip_postupka}".strip()
            odluke = await asyncio.to_thread(retrieve_sudska_praksa, query[:300], 8)
            if odluke:
                _rag_hit_count = len(odluke)
                delovi = []
                for m in odluke:
                    meta = getattr(m, "metadata", {}) or {}
                    court = meta.get("court") or meta.get("sud") or "Sud"
                    tekst = (meta.get("text") or meta.get("parent_text") or "")[:400]
                    delovi.append(f"[{court}] {tekst}")
                rag_kontekst = "RELEVANTNA SUDSKA PRAKSA:\n" + "\n\n".join(delovi)
        except Exception as e:
            _sentry_capture(e)
            logger.warning("[OPP_INTEL] RAG greška: %s", e)

    # Program Tau, Master Sprint 005 -- TAU-011 fix. The existing internal-
    # history search above is cross-PORTFOLIO (other cases mentioning this
    # opponent) -- a genuinely different shape than build_case_context()'s
    # own single-case scope, kept as-is per the grounding-design spec (not
    # replaced). This ADDS the current case's own canonical picture
    # alongside it, when predmet_id is present.
    case_context = await _dohvati_case_context_ako_postoji(payload.predmet_id, uid, supa)
    case_context_blok = _case_context_blok(case_context)

    user_msg = (
        f"Protivnik: {payload.protivnik_naziv}\n"
        f"Advokatska kancelarija: {payload.protivnicki_adv or 'nije navedena'}\n"
        f"Tip postupka: {payload.tip_postupka}\n"
        + (f"\nPoznate informacije: {payload.poznate_informacije[:500]}\n"
           if payload.poznate_informacije else "")
        + (f"\n{interni_kontekst}\n" if interni_kontekst else "")
        + (f"\n{rag_kontekst}" if rag_kontekst else
           "\nNapomena: Nema dostupnih podataka iz sudske prakse — analiza bazirana na opštem znanju.")
        + (f"\n\n{case_context_blok}" if case_context_blok else "")
    )

    from openai import OpenAI
    import json
    from shared.ai_provenance import case_context as _ai_case_ctx
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    try:
        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="opponent_intel"):
            raw = await asyncio.to_thread(_pozovi_opponent_intel_api, oai, user_msg)
        rezultat = json.loads(raw)

        # Operation Single Brain (2026-08-07), AI Boundary gap #7: "pouzdanost" was mostly
        # GPT self-declared -- forced to "niska" only when data was literally zero, meaning
        # a single thin RAG hit let GPT freely claim "visoka" unchecked (Team 4's own
        # reproduction). Two fixes, same evidence-volume-tiering pattern this file already
        # uses for judge_profile's pouzdanost_profila a few hundred lines up (not a new
        # algorithm, the same one applied here):
        # 1. Enum-validate the raw value first -- an out-of-spec GPT string no longer
        #    silently bypasses the tiering below.
        # 2. A "visoka" claim needs real evidence volume behind it (>=3 combined hits),
        #    not just >0 -- one weak RAG hit can no longer buy an unchallenged "visoka".
        _total_hits = _rag_hit_count + _interni_hit_count
        _p = rezultat.get("pouzdanost")
        _p = _p if _p in ("visoka", "srednja", "niska") else "niska"
        if _total_hits == 0:
            _p = "niska"
        elif _total_hits < 3 and _p == "visoka":
            _p = "srednja"
        rezultat["pouzdanost"] = _p
    except Exception as e:
        _sentry_capture(e)
        logger.error("[OPP_INTEL] GPT greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri analizi protivnika: {str(e)}")

    try:
        _pid = await _verifikovan_predmet_id(payload.predmet_id, uid, supa)
        await asyncio.to_thread(
            lambda: supa.table("predictor_analize").insert({
                "user_id":      uid,
                "predmet_id":   _pid,
                "tip_postupka": payload.tip_postupka,
                "opis":         f"Protivnik: {payload.protivnik_naziv} | Adv: {payload.protivnicki_adv or 'N/A'}",
                "analiza":      json.dumps(rezultat, ensure_ascii=False)[:8000],
                "tip_analize":  "opponent_intel",
            }).execute()
        )
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            action="court_predictor_analiza", user_id=uid,
            resource_type="predmet", resource_id=payload.predmet_id,
        ))
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    preostalo = await UsageService.consume(uid, email, "court_predictor")

    return {
        **rezultat,
        "ima_internih_predmeta": bool(interni_kontekst),
        "rag_dostupan":          _RAG_AVAILABLE and bool(rag_kontekst),
        "kontekst_predmeta_koriscen": bool(case_context_blok),
        "credits_remaining":     preostalo,
    }


# ── Confidence Calibration ────────────────────────────────────────────────────

class ConfidenceCheckRequest(BaseModel):
    tip_spora: str  # "radno"|"parnicno"|"krivicno"|"upravno"|"privredno"
    opis_predmeta: str
    sud: Optional[str] = None
    predmet_id: Optional[str] = None
    dokazi: Optional[list[str]] = []


_CONFIDENCE_MAX_SCORE = 9  # 3 (rag) + 3 (vks) + 2 (kancelarija) + 1 (dokazi)


def _procenat_iz_score(score: int) -> int:
    """Program Alpha (2026-08-04): deterministički izvodi procenat poverenja
    iz istog `score`-a koji već odredjuje `nivo`, umesto da drugi, nezavisan
    GPT poziv nagadja sopstveni broj. Pre ovoga, `nivo` i `procenat` su bila
    DVA autora jedne percipirane vrednosti (Critical po Program Alpha's
    sopstvenom pravilu "dva autora istog podatka") -- ništa nije sprečavalo
    nivo="NISKO" da se prikaže pored procenat=78. Opseg 20-80% namerno nikad
    ne tvrdi apsolutnu (0% ili 100%) sigurnost."""
    score = max(0, min(_CONFIDENCE_MAX_SCORE, score))
    return 20 + round((score / _CONFIDENCE_MAX_SCORE) * 60)


def _calc_confidence_nivo(
    rag_hits: int,
    vks_hits: int,
    kancelarija_data: Optional[dict],
    dokazi_count: int,
    readiness_status: Optional[str] = None,
) -> tuple[str, str, list[str], list[str], int]:
    """Vraća (nivo, boja, faktori_plus, faktori_minus, score).

    Program Tau, Master Sprint 005 (2026-08-06) -- `readiness_status` je novi,
    OPCIONI parametar (default None -- postojeći poziv bez case context-a
    ponasa se identicno kao pre). Kad je dostupan (predmet_id prisutan,
    shared/case_readiness.py::compute_case_readiness vec izracunat), zamenjuje
    caller-typed `dokazi_count` kao osnov za POSLEDNJU (1-poensku) komponentu
    skora -- kanonski, sistemski poznat status je pouzdaniji signal od broja
    stringova koje je pozivalac uneo u ovaj konkretan poziv. `_CONFIDENCE_MAX_SCORE`
    OSTAJE 9 u oba slucaja -- ovo ne dodaje novu dimenziju skora, samo bira
    boji izvor za postojecu, vec race namenjen "koliko je predmet potkovan"
    signalu, ocuvavajuci DC-004's own "jedan skor, jedan nivo, jedan procenat"
    invarijantu (Program Alpha, 2026-08-04) bez ikakve promene praga/max_score."""
    score = 0
    faktori_plus: list[str] = []
    faktori_minus: list[str] = []

    if rag_hits >= 15:
        score += 3
        faktori_plus.append(f"{rag_hits} sličnih predmeta u sudskoj praksi")
    elif rag_hits >= 5:
        score += 2
        faktori_plus.append(f"{rag_hits} sličnih predmeta u sudskoj praksi")
    else:
        faktori_minus.append(f"Svega {rag_hits} sličnih predmeta — ograničena referentna baza")

    if vks_hits >= 5:
        score += 3
        faktori_plus.append(f"{vks_hits} presuda Vrhovnog kasacionog suda")
    elif vks_hits >= 2:
        score += 1
        faktori_plus.append(f"{vks_hits} presuda Vrhovnog kasacionog suda")
    else:
        faktori_minus.append("Nema direktnih presuda VKS na ovu temu")

    if kancelarija_data:
        uzoraka = kancelarija_data.get("uzoraka", 0)
        wr = kancelarija_data.get("win_rate", 0)
        if uzoraka >= 5:
            score += 2
            faktori_plus.append(f"Kancelarija: {uzoraka} predmeta, win rate {wr}%")
        elif uzoraka > 0:
            score += 1
            faktori_plus.append(f"Kancelarija: {uzoraka} prethodnih predmeta")
        else:
            faktori_minus.append("Nema istorijata ove firme za ovaj tip spora")
    else:
        faktori_minus.append("Nema istorijata ove firme za ovaj tip spora")

    if readiness_status is not None:
        if readiness_status == READY:
            score += 1
            faktori_plus.append("Predmet je kanonski spreman za postupak (readiness: READY)")
        elif readiness_status in (CRITICAL_GAP, BLOCKED):
            faktori_minus.append(f"Predmet ima kritičan nedostatak po kanonskom statusu (readiness: {readiness_status})")
        elif dokazi_count >= 4:
            score += 1
            faktori_plus.append(f"Dobro dokumentovan predmet ({dokazi_count} dokaza)")
        elif dokazi_count == 0:
            faktori_minus.append("Dokazi nisu navedeni — nepotpuna analiza")
    elif dokazi_count >= 4:
        score += 1
        faktori_plus.append(f"Dobro dokumentovan predmet ({dokazi_count} dokaza)")
    elif dokazi_count == 0:
        faktori_minus.append("Dokazi nisu navedeni — nepotpuna analiza")

    if score >= 7:
        return "VISOKO", "zelena", faktori_plus, faktori_minus, score
    elif score >= 4:
        return "SREDNJE", "žuta", faktori_plus, faktori_minus, score
    else:
        return "NISKO", "crvena", faktori_plus, faktori_minus, score


@llm_retry
def _pozovi_confidence_api(oai_client, gpt_prompt: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo confidence_check."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=150,
        timeout=25.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Ti si srpski pravni analitičar. Odgovaraj SAMO validnim JSON-om. Ekavica."},
            {"role": "user",   "content": gpt_prompt},
        ],
    )
    return resp.choices[0].message.content or "{}"


@router.post("/api/predictor/confidence-check")
@limiter.limit("10/minute")
async def confidence_check(
    request: Request,
    payload: ConfidenceCheckRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """
    Confidence Calibration — ne vraća samo procenat nego strukturirani dokaz:
    VISOKO POVERENJE: 194 slična predmeta, 17 VKS presuda, win rate 73%.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    if not payload.opis_predmeta or len(payload.opis_predmeta) < 20:
        raise HTTPException(status_code=400, detail="Opis predmeta je prekratak.")

    if payload.tip_spora not in ("radno", "parnicno", "krivicno", "upravno", "privredno"):
        raise HTTPException(status_code=400, detail="Nepoznat tip spora.")

    # Korak 1: RAG pretraga sličnih odluka
    rag_hits = 0
    vks_hits = 0
    if _RAG_AVAILABLE:
        try:
            hits = await asyncio.to_thread(retrieve_sudska_praksa, payload.opis_predmeta[:600], 20)
            rag_hits = len(hits)
            vks_hits = sum(
                1 for h in hits
                if "Vrhovni kasacioni" in str(getattr(h, "metadata", {}).get("court", ""))
                or "VKS" in str(getattr(h, "metadata", {}).get("court", ""))
            )
        except Exception as e:
            _sentry_capture(e)
            logger.debug("[CONFIDENCE] RAG greška: %s", e)

    # Korak 2: Firmini podaci iz case_patterns
    kancelarija_data: Optional[dict] = None
    try:
        patterns_r = await asyncio.to_thread(
            lambda: supa.table("case_patterns")
                .select("faktor,pobede,porazi,uzoraka")
                .eq("user_id", uid)
                .eq("tip_spora", payload.tip_spora)
                .order("uzoraka", desc=True)
                .limit(10)
                .execute()
        )
        rows = patterns_r.data or []
        if rows:
            total = sum((r.get("pobede", 0) + r.get("porazi", 0)) for r in rows)
            wins  = sum(r.get("pobede", 0) for r in rows)
            kancelarija_data = {
                "uzoraka":    total,
                "win_rate":   round(wins / max(1, total) * 100, 1),
                "top_faktor": rows[0].get("faktor") if rows else None,
            }
    except Exception as e:
        _sentry_capture(e)
        logger.debug("[CONFIDENCE] case_patterns greška: %s", e)

    # Program Tau, Master Sprint 005 -- TAU-011 fix. See _calc_confidence_nivo's
    # own docstring for exactly how readiness_status participates in the
    # SAME score (never a 2nd, competing signal).
    case_context = await _dohvati_case_context_ako_postoji(payload.predmet_id, uid, supa)
    readiness_status = None
    if case_context and not case_context.get("error"):
        readiness_status = ((case_context.get("readiness") or {}).get("value") or {}).get("status")

    # Korak 3: Nivo pouzdanosti + deterministički procenat izveden IZ ISTOG
    # score-a (Program Alpha, 2026-08-04) -- ranije je "procenat" bio drugi,
    # nezavisan autor iste percipirane vrednosti (vidi _procenat_iz_score).
    nivo, boja, faktori_plus, faktori_minus, _confidence_score = _calc_confidence_nivo(
        rag_hits, vks_hits, kancelarija_data, len(payload.dokazi or []), readiness_status=readiness_status,
    )
    procenat = _procenat_iz_score(_confidence_score)

    # Korak 4: GPT-4o-mini — SAMO kratko obrazloženje/rizik, NIKAD procenat
    # (taj broj je sada isključivo deterministički, iznad).
    razlog     = ""
    kljucni_rizik = ""
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        dokazi_txt = ", ".join(payload.dokazi[:5]) if payload.dokazi else "nisu navedeni"
        gpt_prompt = (
            f"Predmet ({payload.tip_spora}), procenjeni nivo poverenja: {nivo}.\n\n"
            f"{payload.opis_predmeta[:800]}\n\n"
            f"Dokazi: {dokazi_txt}\n"
            f"Sud: {payload.sud or 'nije naveden'}\n\n"
            'Odgovori SAMO JSON-om: {"razlog_kratko": "...", "kljucni_rizik": "..."}\n'
            "Ekavica. Max 30 reči za razlog. NE navodi procenat ni broj — samo kratko obrazloženje i ključni rizik."
        )
        from shared.ai_provenance import case_context as _ai_case_ctx
        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="confidence_check"):
            raw = await asyncio.to_thread(_pozovi_confidence_api, oai, gpt_prompt)
        import json as _json
        gpt_data    = _json.loads(raw)
        razlog      = gpt_data.get("razlog_kratko", "")
        kljucni_rizik = gpt_data.get("kljucni_rizik", "")
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[CONFIDENCE] GPT greška: %s", e)

    # Korak 5: Compose poruka za korisnika
    wr_deo = (
        f" i {kancelarija_data['uzoraka']} predmeta vaše kancelarije "
        f"sa win rate od {kancelarija_data['win_rate']}%"
        if kancelarija_data and kancelarija_data.get("uzoraka", 0) > 0
        else ""
    )
    poruka = (
        f"Na osnovu {rag_hits} sličnih predmeta iz sudske prakse"
        f"{wr_deo}, procenjujem {nivo} poverenje u ovu analizu."
    )

    # Sačuvaj u predictor_analize
    try:
        _pid = await _verifikovan_predmet_id(payload.predmet_id, uid, supa)
        await asyncio.to_thread(
            lambda: supa.table("predictor_analize").insert({
                "user_id":      uid,
                "predmet_id":   _pid,
                "tip_postupka": payload.tip_spora,
                "opis":         payload.opis_predmeta[:500],
                "analiza":      f"NIVO: {nivo} | PROCENAT: {procenat}% | {razlog}",
                "tip_analize":  "confidence_check",
            }).execute()
        )
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            action="court_predictor_analiza", user_id=uid,
            resource_type="predmet", resource_id=payload.predmet_id,
        ))
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    preostalo = await UsageService.consume(uid, email, "court_predictor")

    return {
        "nivo_pouzdanosti":   nivo,
        "boja":               boja,
        "procenat":           procenat,
        "razlog":             razlog,
        "kljucni_rizik":      kljucni_rizik,
        "faktori_plus":       faktori_plus,
        "faktori_minus":      faktori_minus,
        "kancelarija_data":   kancelarija_data,
        "rag_statistika": {
            "slicnih_presuda": rag_hits,
            "vks_presuda":     vks_hits,
        },
        "poruka_korisniku":   poruka,
        "kontekst_predmeta_koriscen": readiness_status is not None,
        "credits_remaining":  preostalo,
    }


# ── Learning Stats ─────────────────────────────────────────────────────────────

@router.get("/api/predictor/learning-stats")
@limiter.limit("20/minute")
async def learning_stats(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Dashboard statistika učenja: win rate kancelarije po tipu spora,
    broj AI analiza, performanse preporuka.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Broj AI analiza
    ukupno_analiza = 0
    try:
        cnt_r = await asyncio.to_thread(
            lambda: supa.table("predictor_analize")
                .select("id", count="exact")
                .eq("user_id", uid)
                .execute()
        )
        ukupno_analiza = cnt_r.count or 0
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    # Win rate po tipu spora iz case_patterns
    tip_spora_performanse: list[dict] = []
    ukupni_win_rate: Optional[float] = None
    try:
        patterns_r = await asyncio.to_thread(
            lambda: supa.table("case_patterns")
                .select("tip_spora,pobede,porazi,uzoraka")
                .eq("user_id", uid)
                .execute()
        )
        rows = patterns_r.data or []
        if rows:
            agg: dict[str, dict] = {}
            for r in rows:
                tip = r.get("tip_spora", "ostalo")
                if tip not in agg:
                    agg[tip] = {"pobede": 0, "porazi": 0}
                agg[tip]["pobede"] += r.get("pobede", 0)
                agg[tip]["porazi"] += r.get("porazi", 0)

            for tip, d in agg.items():
                ukupno = d["pobede"] + d["porazi"]
                if ukupno > 0:
                    tip_spora_performanse.append({
                        "tip":      tip,
                        "win_rate": round(d["pobede"] / ukupno * 100, 1),
                        "uzoraka":  ukupno,
                    })

            tip_spora_performanse.sort(key=lambda x: x["uzoraka"], reverse=True)

            sve_pobede = sum(d["pobede"] for d in agg.values())
            sve_ukupno = sum(d["pobede"] + d["porazi"] for d in agg.values())
            if sve_ukupno > 0:
                ukupni_win_rate = round(sve_pobede / sve_ukupno * 100, 1)
    except Exception as e:
        _sentry_capture(e)
        logger.debug("[LEARNING_STATS] case_patterns greška: %s", e)

    # Broj recommendation_log unosa (prihvaćene/odbijene preporuke)
    prihvaceno = 0
    odbijeno   = 0
    try:
        rec_r = await asyncio.to_thread(
            lambda: supa.table("recommendation_log")
                .select("ishod")
                .eq("user_id", uid)
                .execute()
        )
        for r in (rec_r.data or []):
            if r.get("ishod") == "prihvacena":
                prihvaceno += 1
            elif r.get("ishod") == "odbijena":
                odbijeno += 1
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    if ukupni_win_rate is not None:
        poruka = (
            f"Na osnovu {sum(p['uzoraka'] for p in tip_spora_performanse)} predmeta, "
            f"vaš prosečni win rate je {ukupni_win_rate}%."
        )
    elif ukupno_analiza > 0:
        poruka = f"Pokrenuto {ukupno_analiza} AI analiza. Dodajte ishode predmeta za statistiku uspešnosti."
    else:
        poruka = "Pokrenite prve AI analize da bi sistem počeo da uči iz vaše prakse."

    return {
        "ukupno_analiza":        ukupno_analiza,
        "win_rate_kancelarije":  ukupni_win_rate,
        "tip_spora_performanse": tip_spora_performanse,
        "preporuke_prihvaceno":  prihvaceno,
        "preporuke_odbijeno":    odbijeno,
        "poruka":                poruka,
    }
