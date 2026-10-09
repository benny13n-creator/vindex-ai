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


class NeuspehPosla(Exception):
    """Izvršilac javlja POŠTEN, konačan neuspeh (kontekst predmeta, izvor nije proveren, ročište više ne važi…):
    posao postaje FAILED sa bezbednim kodom i NE ponavlja se. Bilo koji drugi izuzetak = prolazna greška: zakup
    ističe i posao se ponovo zauzima, najviše `max_attempts` puta."""

    def __init__(self, kod: str):
        super().__init__(kod)
        self.kod = kod


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
    # NS007 Task 26: isti ključ = IDENTIČNE ulazne verzije (npr. ročište greškom „odloženo", pa vraćeno). Ako je postojeći
    # red SUPERSEDED, on se OBNAVLJA: sa proizvodom → nazad na pregled (sadržaj je i dalje tačan), bez proizvoda → u red.
    # Bez ovoga bi okidač koji se vratio ostao bez ijedne pripreme. Odbijen, prihvaćen ili neuspeo red se NE dira.
    sada = _sada()
    obnova = await asyncio.to_thread(lambda: supa.table(TABELA_POSLOVA).update({
        "status": READY, "updated_at": sada, "safe_error_code": None,
    }).eq("user_id", kandidat["user_id"]).eq("dedupe_key", kandidat["dedupe_key"]).eq("status", SUPERSEDED)
      .not_.is_("content_json", "null").execute())
    if obnova.data:
        return {"ishod": "OBNOVLJENO", "id": obnova.data[0]["id"], "status": READY}
    obnova = await asyncio.to_thread(lambda: supa.table(TABELA_POSLOVA).update({
        "status": QUEUED, "queued_at": sada, "updated_at": sada, "safe_error_code": None,
    }).eq("user_id", kandidat["user_id"]).eq("dedupe_key", kandidat["dedupe_key"]).eq("status", SUPERSEDED)
      .is_("content_json", "null").execute())
    if obnova.data:
        return {"ishod": "OBNOVLJENO", "id": obnova.data[0]["id"], "status": QUEUED}
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


async def zastareli(supa, user_id: str, predmet_id: str, work_type: str, trigger_ref: str, osim_kljuca: str) -> list:
    """Isti okidač, DRUGA verzija (npr. promenjeno ročište): stari QUEUED/READY postaju SUPERSEDED (ne brišu se).
    Vraća id-jeve zastarelih stavki (za revizioni trag)."""
    r = await asyncio.to_thread(lambda: supa.table(TABELA_POSLOVA).update({
        "status": SUPERSEDED, "updated_at": _sada(), "safe_error_code": "TRIGGER_CHANGED",
    }).eq("user_id", user_id).eq("predmet_id", predmet_id).eq("work_type", work_type)
      .eq("trigger_ref", trigger_ref).in_("status", [QUEUED, READY]).neq("dedupe_key", osim_kljuca).execute())
    return [str(x["id"]) for x in (r.data or [])]


async def jos_vazi_zakup(supa, work_id: str, owner: str) -> bool:
    """Neposredno pre skupog koraka: posao je i dalje RUNNING, zakup je NAŠ i nije istekao."""
    r = await asyncio.to_thread(lambda: supa.table(TABELA_POSLOVA).select("status,lease_owner,lease_expires_at")
                                .eq("id", work_id).limit(1).execute())
    red = (r.data or [None])[0]
    if not red or red.get("status") != RUNNING or str(red.get("lease_owner")) != str(owner):
        return False
    try:
        return datetime.fromisoformat(str(red["lease_expires_at"]).replace("Z", "+00:00")) > datetime.now(timezone.utc)
    except (TypeError, ValueError, KeyError):
        return False


async def ucitaj_predmete(supa, ids: list) -> dict:
    """Predmeti za planiranje i kapije: {id: red} sa statusom, vlasnikom, Genome-om i tombstone-om brisanja.
    Kolona `brisanje_zapoceto` (114) se čita kao u `shared/rag_acl.py`: bez nje tombstone ne može ni da postoji,
    pa je grana bez filtera bezbedna — ali SAMO za grešku nepostojeće kolone; svaka druga greška se propušta."""
    if not ids:
        return {}
    from shared.audit_immutable import _is_missing_column_error

    def _upit(kolone):
        return supa.table("predmeti").select(kolone).in_("id", list(ids)).execute()
    try:
        r = await asyncio.to_thread(lambda: _upit("id,user_id,status,naziv,case_dna,brisanje_zapoceto"))
    except Exception as e:
        if not _is_missing_column_error(e):
            raise
        r = await asyncio.to_thread(lambda: _upit("id,user_id,status,naziv,case_dna"))
    return {str(p["id"]): p for p in (r.data or [])}


_BEZBEDNA_POLJA = ("work_type", "agent_type", "trigger_type", "trigger_ref", "source_version", "attempt_count",
                   "budget_units", "cost_class", "quality_state", "safe_error_code", "status", "run_id", "konacno",
                   "recommendation_id", "case_action_id", "model", "obnovljeno")


async def revizija(akcija: str, user_id: str, work_id: str, predmet_id: str | None, meta: dict) -> bool:
    """Nepromenjiv trag kroz POSTOJEĆEG vlasnika (`audit_immutable.log_action`). Korelacija = id radne stavke
    (isti id nosi i AI proveniencija izvršioca). Metapodaci se FILTRIRAJU na bezbedna polja — naslov, razlog,
    sažetak i sadržaj nikad ne ulaze u trag. Vraća False kad upis nije uspeo — pozivalac to BROJI.
    Politika: trag nije kapija — rad se nastavlja i kad revizija ne uspe, ali se uspeh nikad ne tvrdi."""
    from shared.audit_immutable import log_action
    bezbedno = {k: v for k, v in (meta or {}).items() if k in _BEZBEDNA_POLJA}
    if predmet_id:
        bezbedno["predmet_id"] = str(predmet_id)
    try:
        rid = await log_action(akcija, user_id=str(user_id), resource_type="autonomy_work_item",
                               resource_id=str(work_id), metadata=bezbedno, correlation_id=str(work_id))
    except Exception:
        rid = None
    return bool(rid)


def novi_vlasnik() -> str:
    return str(uuid.uuid4())
