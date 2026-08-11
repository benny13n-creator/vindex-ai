# -*- coding: utf-8 -*-
"""
Vindex AI — Async Job Queue

In-memory job store za dugotrajne AI operacije (kompletna_analiza, outcome_intel, batch).
Klijent dobija job_id odmah, pa poluje GET /api/jobs/{job_id} dok status != done/error.

Job lifecycle: pending → running → done | error
TTL: 60 minuta (čišćenje po svakom upisu)
"""
import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from shared.deps import get_current_user

logger = logging.getLogger("vindex.jobs")
router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# ─── In-memory store ──────────────────────────────────────────────────────────
_JOB_TTL_S = 3600  # 60 minuta

# Wave 11 / Z1 — gornja granica starosti za PONOVNU UPOTREBU posla u `pending`.
#
# KVAR KOJI OVO ZATVARA: `pending` je stanje SAMO između `create_job` i prve
# linije `run_in_background` (`update_job(jid, "running")`, :177). U normalnom
# radu traje milisekunde. Ako pozadinski zadatak nikad ne bude pokrenut
# (`background_tasks.add_task` se ne izvrši, worker padne između `create_job` i
# `update_job`), red ostaje `pending` do isteka `_JOB_TTL_S`. Bez ove granice
# svaki identičan zahtev narednih 60 minuta dobija 202 sa `vec_u_toku: true` i
# `job_id` posla koji se nikad neće završiti — korisnik nema ni način da ponovi
# ni signal da nešto nije u redu.
#
# IZMERENI BROJEVI na osnovu kojih je izabrano 180 s:
#   * `routers/strategija.py:556` — kompletna analiza traje 30–90 s (8 GPT-4o
#     poziva). To je vreme provedeno u `running`, ne u `pending`.
#   * `static/vindex.js:3628-3629` — `strat_job_poll` poluje na 4 s i odustaje
#     na `elapsed < 180`, dakle posle 180 s ispisuje „Analiza traje duže nego
#     obično… pokušajte ponovo" (`:3662`). Posle te tačke nijedan klijent više
#     ne poluje taj `job_id`, pa mu ponovna upotreba ne može ničim pomoći —
#     može samo da mu blokira ponovni pokušaj koji mu je frontend upravo
#     predložio.
#   * `_JOB_TTL_S = 3600` — 20x duže od klijentovog praga strpljenja; TTL je
#     čistač memorije, nikad nije bio granica upotrebljivosti.
#
# 180 s je istovremeno 2x duže od najgoreg dokumentovanog trajanja analize i
# ~3 reda veličine duže od trajanja stanja koje ograničava, pa nijedno realno
# kašnjenje u zakazivanju ne može da padne preko njega. Zaštita od duplog
# klika (P1-A) ostaje netaknuta — prozor dvostrukog klika je nekoliko sekundi.
_PENDING_MAX_REUSE_S = 180

_jobs: dict[str, dict] = {}


def _cleanup():
    now = time.time()
    stale = [jid for jid, j in _jobs.items() if now - j["created_at"] > _JOB_TTL_S]
    for jid in stale:
        del _jobs[jid]


def create_job(user_id: str, tip: str, dedupe_key: Optional[str] = None) -> str:
    """Kreira novi posao i vraća job_id.

    P1-A (2026-08-08): with `dedupe_key`, an identical request that is already
    pending or running returns THAT job instead of starting a second one.

    Why this endpoint shape needs it: /kompletna-analiza answers 202 instantly
    and charges 6 credits from inside the background task, once the work
    finishes. A double-click, an impatient re-submit, or any client retry of the
    202 therefore started a second full analysis and billed a second 6 credits
    for one lawyer action -- 12 credits, two identical answers, no way to tell
    afterwards that it happened.

    SCOPE, stated honestly: _jobs is per-process. This dedupes within one worker
    only. That is not a weaker guarantee than the feature it protects -- the job
    store itself is per-process, so GET /api/jobs/{id} can only ever be answered
    by the worker that created the job. Whatever makes polling work makes this
    work. A cross-worker guarantee needs the DB-backed dedupe_key pattern used
    in migrations 099/101, which is a schema change and deliberately not bundled
    in here.
    """
    return create_job_deduped(user_id, tip, dedupe_key)[0]


def create_job_deduped(user_id: str, tip: str, dedupe_key: Optional[str] = None) -> tuple[str, bool]:
    """As create_job, but also reports whether an existing job was reused.

    The caller MUST know: on a reuse it must not schedule the background task a
    second time, or the dedupe accomplishes nothing.
    """
    _cleanup()

    if dedupe_key:
        sada = time.time()
        for j in _jobs.values():
            if (
                j["user_id"] == user_id
                and j["tip"] == tip
                and j.get("dedupe_key") == dedupe_key
                and j["status"] in ("pending", "running")
            ):
                # Wave 11 / Z1: granica starosti važi SAMO za `pending`.
                #
                # `running` znači da je `run_in_background` stvarno startovao —
                # taj posao radi i sam njegov status je dokaz da je worker živ.
                # Ista granica nad njim bi pokrenula DRUGU kompletnu analizu
                # dok prva još traje, i naplatila drugih 6 kredita za jednu
                # advokatovu radnju — tačno kvar koji P1-A dedupe i postoji da
                # spreči. Trajanje u `running` legitimno ume da probije 90 s:
                # `routers/strategija.py:47` radi eksponencijalni backoff na
                # rate-limit/5xx greške provajdera. Posao koji je stvarno
                # zaglavljen u `running` hvata `_JOB_TTL_S`, a njegov ishod
                # (`done`/`error`) ionako oslobađa dedupe.
                if (
                    j["status"] == "pending"
                    and sada - j["created_at"] > _PENDING_MAX_REUSE_S
                ):
                    logger.warning(
                        "[JOB] dedupe PRESKOČEN: %s stoji u `pending` %.0f s (> %s s) — "
                        "pozadinski zadatak očigledno nikad nije pokrenut; pravim nov posao",
                        j["id"][:8], sada - j["created_at"], _PENDING_MAX_REUSE_S,
                    )
                    continue
                logger.info(
                    "[JOB] dedupe pogodak %s tip=%s user=%s — vraćam postojeći posao umesto novog",
                    j["id"][:8], tip, user_id[:8],
                )
                return j["id"], True

    jid = str(uuid.uuid4())
    _jobs[jid] = {
        "dedupe_key": dedupe_key,
        "id":         jid,
        "user_id":    user_id,
        "tip":        tip,
        "status":     "pending",
        "result":     None,
        "error":      None,
        # Wave 9 / G1: strukturisana pratnja uz `error`. `error` ostaje ljudski
        # tekst koji stari frontend čita; ova dva polja su DODATNA i mašinska.
        "error_status": None,
        "error_code":   None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    logger.info("[JOB] kreiran %s tip=%s user=%s", jid[:8], tip, user_id[:8])
    return jid, False


def update_job(
    jid: str,
    status: str,
    result: Any = None,
    error: str = None,
    error_status: Optional[int] = None,
    error_code: Optional[str] = None,
):
    """Upisuje ishod posla.

    `error_status` / `error_code` su DODATNA polja (Wave 9 / G1). Pozivaoci koji
    ih ne prosleđuju ponašaju se identično kao ranije — polja se resetuju na
    None, isto kao `result` i `error`, pa nijedan ishod ne nasledi ostatke
    prethodnog stanja.
    """
    if jid not in _jobs:
        return
    _jobs[jid].update({
        "status":       status,
        "result":       result,
        "error":        error,
        "error_status": error_status,
        "error_code":   error_code,
        "updated_at":   time.time(),
    })
    logger.info("[JOB] %s → %s", jid[:8], status)


def get_job(jid: str, user_id: str) -> Optional[dict]:
    j = _jobs.get(jid)
    if j and j["user_id"] == user_id:
        return j
    return None


# ─── Runner ───────────────────────────────────────────────────────────────────

def _raspakuj_http_gresku(exc: HTTPException) -> tuple[str, Optional[str]]:
    """Iz `HTTPException` izvlači (ljudska_poruka, masinski_kod).

    Konvencija koju ruteri već koriste (npr. `routers/strategija.py:588`):
        HTTPException(402, detail={"code": "NO_CREDITS", "message": "..."})

    Kad `detail` NIJE takav dict, vraća se `str(exc)` — tačno onaj string koji
    je i ranije završavao u `job["error"]`. Time se format za sve postojeće
    slučajeve ne menja; menja se samo tamo gde postoji prava ljudska poruka.
    Ništa iz predmeta/prompta se ne dira — čita se isključivo `detail`.
    """
    detail = getattr(exc, "detail", None)
    kod: Optional[str] = None
    poruka: Optional[str] = None

    if isinstance(detail, dict):
        sirovi_kod = detail.get("code")
        if sirovi_kod is not None and str(sirovi_kod).strip():
            kod = str(sirovi_kod)
        sirova_poruka = detail.get("message")
        if isinstance(sirova_poruka, str) and sirova_poruka.strip():
            poruka = sirova_poruka

    if poruka is None:
        poruka = str(exc)

    return poruka, kod


async def run_in_background(jid: str, coro_factory: Callable, *args, **kwargs):
    """Pokreće korutinu i upisuje rezultat/grešku u job store.

    Poslovni neuspeh (`HTTPException`: 402 nema kredita, 429 cooldown, 403/404)
    razlikuje se od tehničkog. Oba ostaju `status="error"` — nijedan neuspeh ne
    sme da postane `done` niti da nosi `result`. Razlika je samo u tome što
    poslovni slučaj dobija mašinski čitljiv par (`error_status`, `error_code`)
    da frontend zna da prikaže paywall umesto tehničke poruke.
    """
    update_job(jid, "running")
    try:
        result = await coro_factory(*args, **kwargs)
        update_job(jid, "done", result=result)
    except HTTPException as exc:
        poruka, kod = _raspakuj_http_gresku(exc)
        # Namerno `warning`, ne `exception`: ovo je očekivan poslovni ishod
        # (nema kredita / cooldown), ne kvar. Loguje se samo status i kod —
        # nikad `detail` u celini, da poruka ne odvuče sadržaj predmeta u log.
        logger.warning(
            "[JOB] %s poslovna greška: HTTP %s kod=%s", jid[:8], exc.status_code, kod or "-",
        )
        update_job(jid, "error", error=poruka, error_status=exc.status_code, error_code=kod)
    except Exception as exc:
        logger.exception("[JOB] %s greška: %s", jid[:8], exc)
        # Neki izuzeci nemaju poruku — `str(asyncio.TimeoutError())` je PRAZAN
        # string. Bez ovog fallback-a posao završava sa `error=""`, pa klijent
        # prikaže prazan okvir umesto greške; korisniku to izgleda kao da se
        # ništa nije desilo. Upisuje se samo ime klase izuzetka — nikad sadržaj
        # predmeta ni prompta.
        poruka = str(exc).strip() or f"Tehnička greška ({type(exc).__name__})."
        # 500, ne None: klijentu treba jednoznačan diskriminator. `None` se ne
        # razlikuje od „polje ne postoji" (stari zapis, drugi worker), pa bi
        # frontend morao da nagađa. 500 nikada ne može da se pomeša sa poslovnom
        # odlukom (402/429/403/404), pa pravilo „paywall samo za 402" ostaje
        # sigurno. `error_code` ostaje None — mašinski kod se NE izmišlja.
        update_job(jid, "error", error=poruka, error_status=500, error_code=None)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{job_id}")
async def poll_job(job_id: str, user=Depends(get_current_user)):
    """
    Poluje status posla.
    Response:
      { id, tip, status: pending|running|done|error,
        result?, error?, error_status?, error_code?, elapsed_s }

    `error` je nepromenjen ugovor — ljudski tekst koji stari klijent prikazuje.
    `error_status` (HTTP kod poslovnog neuspeha, 500 za tehnički) i `error_code`
    (npr. "NO_CREDITS") su dodati u Wave 9 i uvek su None kad status nije error.
    """
    j = get_job(job_id, user["user_id"])
    if not j:
        raise HTTPException(status_code=404, detail="Posao nije pronađen.")
    elapsed = round(time.time() - j["created_at"], 1)
    je_greska = j["status"] == "error"
    return {
        "id":       j["id"],
        "tip":      j["tip"],
        "status":   j["status"],
        "result":   j["result"] if j["status"] == "done"  else None,
        "error":    j["error"]  if je_greska else None,
        "error_status": j.get("error_status") if je_greska else None,
        "error_code":   j.get("error_code")   if je_greska else None,
        "elapsed_s": elapsed,
    }
