# -*- coding: utf-8 -*-
"""
Vindex AI — services/autonomy.py

NS007 — JEDINI vlasnik životnog ciklusa autonomnog rada (migracija 136). Nije registar agenata ni raspoređivač:
registar ostaje `workers/background_agents.py`, a ovaj modul samo upisuje, zauzima, završava i zastareva radne
stavke (`autonomy_work_items`) i zauzima prozor ciklusa (`autonomy_cycles`).

PRAVILA
  • Zauzimanje prozora = INSERT; UNIQUE(window_key) odlučuje (23505 → ALREADY_CLAIMED). RUNNING ciklus se nikad
    ne otima.
  • Jedan logički okidač = jedan red: UNIQUE(user_id, dedupe_key), upis sa `ignore_duplicates`.
  • Posao postaje RUNNING ISKLJUČIVO kroz `autonomy_claim_work_item` (zakup + rezervacija budžeta u jednoj
    transakciji). Ako baza ne odgovori, ništa nije zauzeto → nema poziva modela (fail-closed).
  • Rezultat upisuje SAMO vlasnik zakupa, u istoj naredbi kojom posao postaje READY_FOR_REVIEW.
  • AI sadržaj je uvek `AI_PREPARED_FOR_REVIEW`; deterministički `DETERMINISTIC`. Nikad „verifikovano".
  • Nijedna funkcija ovde ne šalje ništa napolje.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("vindex.autonomy")

TABELA_POSLOVA = "autonomy_work_items"
TABELA_CIKLUSA = "autonomy_cycles"

QUEUED, RUNNING, READY, ACCEPTED, REJECTED = "QUEUED", "RUNNING", "READY_FOR_REVIEW", "ACCEPTED", "REJECTED"
FAILED, DEAD_LETTER, SUPERSEDED = "FAILED", "DEAD_LETTER", "SUPERSEDED"
STATUSI = (QUEUED, RUNNING, READY, ACCEPTED, REJECTED, FAILED, DEAD_LETTER, SUPERSEDED)

AI_PRIPREMLJENO = "AI_PREPARED_FOR_REVIEW"
DETERMINISTICKO = "DETERMINISTIC"

_KOD = re.compile(r"^[A-Z0-9_]{1,64}$")
_PROZOR = re.compile(r"^[A-Za-z0-9:_.-]{1,80}$")


def trajanje_zakupa() -> int:
    try:
        return max(30, min(3600, int(os.getenv("AUTONOMY_LEASE_SECONDS", "300"))))
    except ValueError:
        return 300


def budzet_limit() -> Optional[int]:
    """Dnevni broj PLAĆENIH izvršenja po organizaciji. Neispravna vrednost NIJE „bez granice": vraća None, a
    `autonomy_claim_work_item` tada odgovara BUDGET_UNKNOWN (nijedan plaćen posao ne kreće)."""
    try:
        v = int(os.getenv("AUTONOMY_BUDGET_PER_ORG_DAILY", "20"))
    except ValueError:
        return None
    return v if v >= 0 else None


def _sada() -> str:
    return datetime.now(timezone.utc).isoformat()


def _je_sudar(e: Exception) -> bool:
    s = str(e)
    return "23505" in s or "duplicate key" in s.lower()


def _kod(kod: str) -> str:
    return kod if _KOD.match(kod or "") else "UNKNOWN_ERROR"


# ── ciklus ─────────────────────────────────────────────────────────────────────

async def zauzmi_ciklus(supa, window_key: str, run_id: str) -> dict:
    """{"ishod": "CLAIMED" | "ALREADY_CLAIMED"}. Druga greška baze se propušta (pozivalac je prijavljuje)."""
    if not _PROZOR.match(window_key or ""):
        raise ValueError("neispravan window_key")
    try:
        await asyncio.to_thread(lambda: supa.table(TABELA_CIKLUSA).insert(
            {"window_key": window_key, "run_id": run_id, "status": "RUNNING", "claimed_at": _sada()}).execute())
    except Exception as e:
        if _je_sudar(e):
            return {"ishod": "ALREADY_CLAIMED", "window_key": window_key}
        raise
    return {"ishod": "CLAIMED", "window_key": window_key, "run_id": run_id}


async def zavrsi_ciklus(supa, window_key: str, run_id: str, ok: bool, counts: dict,
                        safe_error_code: Optional[str] = None) -> bool:
    r = await asyncio.to_thread(lambda: supa.table(TABELA_CIKLUSA).update({
        "status": "COMPLETED" if ok else "FAILED", "finished_at": _sada(), "counts": counts,
        "safe_error_code": None if ok else _kod(safe_error_code or "CYCLE_FAILED"),
    }).eq("window_key", window_key).eq("run_id", run_id).eq("status", "RUNNING").execute())
    return bool(r.data)


# ── posao ──────────────────────────────────────────────────────────────────────

async def upisi_kandidata(supa, kandidat: dict) -> dict:
    """{"ishod": "QUEUED" | "DUPLICATE", "id"?}. Isti (user_id, dedupe_key) nikad ne pravi drugi red."""
    obavezno = ("user_id", "predmet_id", "agent_type", "work_type", "trigger_type", "trigger_ref",
                "dedupe_key", "reason", "cost_class", "budget_key")
    nedostaje = [k for k in obavezno if not kandidat.get(k)]
    if nedostaje:
        raise ValueError(f"kandidat bez polja: {nedostaje}")
    red = {**kandidat, "status": QUEUED, "queued_at": _sada()}
    r = await asyncio.to_thread(lambda: supa.table(TABELA_POSLOVA).upsert(
        red, on_conflict="user_id,dedupe_key", ignore_duplicates=True).execute())
    if r.data:
        return {"ishod": "QUEUED", "id": r.data[0]["id"]}
    return {"ishod": "DUPLICATE"}


_KONFIGURISANO = object()


async def zauzmi_posao(supa, work_id: str, owner: str, limit=_KONFIGURISANO) -> dict:
    """Jedini put do RUNNING. Greška baze se propušta: pozivalac NE sme da pozove model.
    `limit` podrazumevano = konfigurisan dnevni limit; eksplicitan `None` = nepoznat → BUDGET_UNKNOWN."""
    granica = budzet_limit() if limit is _KONFIGURISANO else limit
    r = await asyncio.to_thread(lambda: supa.rpc("autonomy_claim_work_item", {
        "p_id": work_id, "p_owner": owner, "p_lease_seconds": trajanje_zakupa(), "p_budget_limit": granica,
    }).execute())
    ishod = r.data if isinstance(r.data, dict) else {}
    if ishod.get("ishod") not in ("CLAIMED", "NOT_FOUND", "NOT_CLAIMABLE", "DEAD_LETTER", "BUDGET_EXHAUSTED", "BUDGET_UNKNOWN"):
        raise RuntimeError("autonomy_claim_work_item: neočekivan odgovor")
    return ishod


async def sacuvaj_rezultat(supa, work_id: str, owner: str, *, title: str, summary: str, content: dict,
                           source_refs: list, quality_state: str) -> bool:
    """READY_FOR_REVIEW + proizvod u JEDNOJ naredbi, samo za vlasnika zakupa. False = zakup više nije naš."""
    if quality_state not in (AI_PRIPREMLJENO, DETERMINISTICKO):
        raise ValueError("nepoznato stanje kvaliteta")
    sada = _sada()
    r = await asyncio.to_thread(lambda: supa.table(TABELA_POSLOVA).update({
        "status": READY, "title": title[:300], "summary": summary[:2000], "content_json": content,
        "source_refs": source_refs, "quality_state": quality_state, "ready_at": sada, "updated_at": sada,
        "lease_owner": None, "lease_expires_at": None, "safe_error_code": None,
    }).eq("id", work_id).eq("status", RUNNING).eq("lease_owner", owner).execute())
    return bool(r.data)


async def oznaci_neuspeh(supa, work_id: str, owner: str, kod: str) -> bool:
    """FAILED = pošten, NE ponavlja se (npr. kontekst predmeta ili izvor nije proveren). Bez proizvoda."""
    r = await asyncio.to_thread(lambda: supa.table(TABELA_POSLOVA).update({
        "status": FAILED, "safe_error_code": _kod(kod), "updated_at": _sada(),
        "lease_owner": None, "lease_expires_at": None,
    }).eq("id", work_id).eq("status", RUNNING).eq("lease_owner", owner).execute())
    return bool(r.data)


async def zastareli(supa, user_id: str, predmet_id: str, work_type: str, trigger_ref: str, osim_kljuca: str) -> int:
    """Isti okidač, DRUGA verzija (npr. promenjeno ročište): stari QUEUED/READY postaju SUPERSEDED (ne brišu se)."""
    r = await asyncio.to_thread(lambda: supa.table(TABELA_POSLOVA).update({
        "status": SUPERSEDED, "updated_at": _sada(), "safe_error_code": "TRIGGER_CHANGED",
    }).eq("user_id", user_id).eq("predmet_id", predmet_id).eq("work_type", work_type)
      .eq("trigger_ref", trigger_ref).in_("status", [QUEUED, READY]).neq("dedupe_key", osim_kljuca).execute())
    return len(r.data or [])


def novi_vlasnik() -> str:
    return str(uuid.uuid4())
