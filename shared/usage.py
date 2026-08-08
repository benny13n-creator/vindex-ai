# -*- coding: utf-8 -*-
"""
Vindex AI — shared/usage.py

UsageService — odvojen sloj od PermissionService. PermissionService odgovara
"ima li nalog PRAVO da pristupi funkciji" (tarifa/addon); UsageService
odgovara "da li ima BUDžET/PRAVO UČESTALOSTI da je iskoristi SADA" (krediti,
dnevni/mesečni limit, cooldown) — sve čitano iz feature_registry (migracije
064/065), NE prosleđeno kao parametar iz endpoint-a.

Upotreba u routeru — DVA ODVOJENA poziva, tim redosledom. feature_key je
RAW STRING (isti kao feature_registry.feature_key) — namerno nema Python
FEATURE_* konstanti, to bi bio drugi izvor istine pored baze:

    from shared.permissions import PermissionService
    from shared.usage import UsageService

    @router.post("/api/case-dna/refresh")
    async def refresh(
        user: dict = Depends(PermissionService.require("case_dna")),
    ):
        ... (generiši AI odgovor) ...
        await UsageService.consume(user["user_id"], user["email"], "case_dna")

Opciona telemetrija (tokens_prompt/tokens_completion/latency_ms) se popunjava
POSTEPENO kako se svaki endpoint ožičava — nije obavezna, feature_usage_log
red se piše i bez nje (samo ta polja ostaju NULL dok se ne doda).

Endpoint NE zna koliko feature košta — to je Registry-jeva odgovornost.
Ne prikazuje tehničke detalje (OpenAI tokene, broj poziva modelu) nikad
korisniku — samo "Mesečni AI fond" i preostali broj kredita (frontend-ova
odgovornost preko postojećeg userCredits/updateCreditDisplay obrasca).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status

from shared.deps import (
    _deduct_credit,
    _deduct_n_credits,
    _get_credits,
    _get_supa,
    _is_founder,
    _refund_n_credits,
)
from shared.feature_registry import get_policy

logger = logging.getLogger("vindex.usage")

FOUNDER_BALANCE = 9999


def _today_iso() -> str:
    return date.today().isoformat()


def _month_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _get_usage_row(user_id: str, feature: str) -> Optional[dict]:
    def _q():
        return (
            _get_supa()
            .table("feature_usage")
            .select("broj_koriscenja, mesec")
            .eq("user_id", user_id)
            .eq("feature_key", feature)
            .eq("dan", _today_iso())
            .maybe_single()
            .execute()
        )
    try:
        res = await asyncio.to_thread(_q)
        return res.data
    except Exception as exc:
        logger.warning("[USAGE] _get_usage_row greška (non-fatal): %s", exc)
        return None


async def _get_monthly_count(user_id: str, feature: str) -> int:
    def _q():
        return (
            _get_supa()
            .table("feature_usage")
            .select("broj_koriscenja")
            .eq("user_id", user_id)
            .eq("feature_key", feature)
            .eq("mesec", _month_iso())
            .execute()
        )
    try:
        res = await asyncio.to_thread(_q)
        return sum((r.get("broj_koriscenja") or 0) for r in (res.data or []))
    except Exception as exc:
        logger.warning("[USAGE] _get_monthly_count greška (non-fatal): %s", exc)
        return 0


async def _seconds_since_last_call(user_id: str, feature: str) -> Optional[float]:
    def _q():
        return (
            _get_supa()
            .table("feature_usage_log")
            .select("created_at")
            .eq("user_id", user_id)
            .eq("feature_key", feature)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    try:
        res = await asyncio.to_thread(_q)
        rows = res.data or []
        if not rows:
            return None
        last = datetime.fromisoformat(rows[0]["created_at"].replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - last).total_seconds()
    except Exception as exc:
        logger.warning("[USAGE] _seconds_since_last_call greška (non-fatal): %s", exc)
        return None


# Program Phoenix, Mission 012 (LIVINGSYS-DEBT-012, TOCTOU sub-item): consume()
# used to READ "seconds since last call" (_seconds_since_last_call, above) and
# only much later — after limit/credit checks — WRITE the new call's timestamp
# (_increment_usage/_log_usage_event, at the very end). Two concurrent requests
# for the same user+feature landing between that read and that write both see
# "cooldown satisfied" and both proceed, bypassing the cooldown entirely for
# that race window. Reuses feature_usage's existing UNIQUE(user_id, feature_key,
# dan) constraint (migration 064) — no new migration — to make the check-and-
# claim a single atomic DB operation instead of a separate read then a later
# write. Deliberate, disclosed behavior change: because the claim now happens
# BEFORE the daily/monthly-limit and credit checks (moving it any later would
# reopen the same race), a call that fails those LATER checks still consumes
# this cooldown window — a strictly more conservative (never less safe)
# outcome, and the only way to close the race without a migration.
async def _claim_cooldown_atomic(user_id: str, feature: str, cooldown: float) -> bool:
    today = _today_iso()
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(seconds=cooldown)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    def _try_update():
        return (
            _get_supa().table("feature_usage")
            .update({"updated_at": now_iso})
            .eq("user_id", user_id).eq("feature_key", feature).eq("dan", today)
            .lt("updated_at", cutoff_iso)
            .execute()
        )
    res = await asyncio.to_thread(_try_update)
    if res.data:
        return True  # atomically claimed: today's row existed and was stale enough

    def _row_exists():
        return (
            _get_supa().table("feature_usage")
            .select("id").eq("user_id", user_id).eq("feature_key", feature).eq("dan", today)
            .maybe_single().execute()
        )
    exists = await asyncio.to_thread(_row_exists)
    if exists.data:
        return False  # row exists, updated_at too recent -- cooldown genuinely active

    def _try_insert():
        return (
            _get_supa().table("feature_usage").insert({
                "user_id": user_id, "feature_key": feature, "dan": today,
                "mesec": _month_iso(), "broj_koriscenja": 0, "krediti_potroseni": 0,
            }).execute()
        )
    try:
        await asyncio.to_thread(_try_insert)
        return True  # first call of the day -- claimed via insert
    except Exception as exc:
        if "23505" in str(exc) or "duplicate key" in str(exc).lower():
            # Lost the race to insert today's first row -- a concurrent request
            # just created it; treat conservatively as cooldown-not-yet-elapsed.
            return False
        raise


async def _increment_usage(user_id: str, feature: str, credits_spent: float) -> None:
    today = _today_iso()
    mesec = _month_iso()

    def _upsert():
        supa = _get_supa()
        existing = (
            supa.table("feature_usage")
            .select("broj_koriscenja, krediti_potroseni")
            .eq("user_id", user_id)
            .eq("feature_key", feature)
            .eq("dan", today)
            .maybe_single()
            .execute()
        )
        if existing.data:
            supa.table("feature_usage").update({
                "broj_koriscenja": (existing.data.get("broj_koriscenja") or 0) + 1,
                "krediti_potroseni": float(existing.data.get("krediti_potroseni") or 0) + credits_spent,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("user_id", user_id).eq("feature_key", feature).eq("dan", today).execute()
        else:
            supa.table("feature_usage").insert({
                "user_id": user_id,
                "feature_key": feature,
                "dan": today,
                "mesec": mesec,
                "broj_koriscenja": 1,
                "krediti_potroseni": credits_spent,
            }).execute()

    try:
        await asyncio.to_thread(_upsert)
    except Exception as exc:
        # Ne blokiraj korisnika zbog greške u brojanju upotrebe — kredit je već
        # (ili nije) potrošen preko atomičnog RPC-a, to je izvor istine za novac.
        logger.warning("[USAGE] _increment_usage greška (non-fatal): %s", exc)


async def _log_usage_event(
    user_id: str, feature: str, credits_spent: float, ai_model: Optional[str],
    estimated_cost_usd: Optional[float], tokens_prompt: Optional[int],
    tokens_completion: Optional[int], latency_ms: Optional[int],
) -> None:
    def _insert():
        _get_supa().table("feature_usage_log").insert({
            "user_id": user_id,
            "feature_key": feature,
            "krediti_potroseni": credits_spent,
            "ai_model": ai_model,
            "estimated_cost_usd": estimated_cost_usd,
            "tokens_prompt": tokens_prompt,
            "tokens_completion": tokens_completion,
            "latency_ms": latency_ms,
        }).execute()
    try:
        await asyncio.to_thread(_insert)
    except Exception as exc:
        # Analitika je best-effort — nikad ne blokira korisnika (migracija 065
        # možda još nije pokrenuta na ovom okruženju).
        logger.debug("[USAGE] _log_usage_event greška (non-fatal): %s", exc)


class UsageService:
    @staticmethod
    async def consume(
        user_id: str,
        email: str,
        feature: str,
        *,
        multiplier: Optional[int] = None,
        tokens_prompt: Optional[int] = None,
        tokens_completion: Optional[int] = None,
        latency_ms: Optional[int] = None,
    ) -> int:
        """
        multiplier: za operacije koje su N puta skuplje od registrovane bazne
        cene (npr. strategija/kompletna-analiza pokreće 6 modula = 6x cena
        jednog modula) — bez potrebe za posebnim feature_key redom u bazi za
        svaku takvu varijantu. Broji se kao JEDNA upotreba za dnevni/mesečni
        limit (jedan poziv), ali troši multiplier x krediti.

        Podrazumevano (multiplier=None) čita se feature_registry.credit_multiplier
        (migracija 069, Admin Console editabilno, isti izvor kao krediti) —
        NIKAD hardkodovano u pozivaocu. Eksplicitan multiplier= je rezervisan
        ISKLJUČIVO za DINAMIČKE slučajeve gde je faktor izračunat u runtime-u
        i nema smisla u statičnoj tabeli (npr. multi_agent.py-jev broj stvarno
        pozvanih agenata) — ne za poslovne odluke koje bi trebalo da budu
        Admin Console-editabilne bez deploy-a.

        Proverava cooldown, dnevni/mesečni limit, zatim atomično oduzima
        kredite — SVE vrednosti (osim opcione telemetrije) čitane iz
        feature_registry (Admin Feature Console), NIKAD prosleđene kao
        parametar. Founder nikad ne plaća i ne trpi cooldown/limite (samo
        aktivno=false kill-switch ga zaustavlja, to je provereno u
        PermissionService pre ovog poziva).

        tokens_prompt/tokens_completion/latency_ms su OPCIONI — endpoint ih
        prosleđuje ako ih ima (za feature_analytics), izostavljanje ne menja
        gejtovanje.

        Vraća preostali broj kredita. Baca HTTPException(402/429) ako nema
        budžeta ili je cooldown aktivan.
        """
        policy = await get_policy(feature)
        effective_multiplier = multiplier if multiplier is not None else policy.get("credit_multiplier", 1)
        credits = float(policy.get("krediti") or 0) * max(float(effective_multiplier or 1), 1)
        dnevni_limit = policy.get("dnevni_limit")
        mesecni_limit = policy.get("mesecni_limit")
        cooldown = policy.get("cooldown_seconds")
        ai_model = policy.get("ai_model")
        est_cost = policy.get("estimated_cost_usd")

        if _is_founder(email):
            return FOUNDER_BALANCE

        if cooldown:
            claimed = await _claim_cooldown_atomic(user_id, feature, cooldown)
            if not claimed:
                elapsed = await _seconds_since_last_call(user_id, feature)
                preostalo_cd = round(cooldown - elapsed) if elapsed is not None else round(cooldown)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "COOLDOWN",
                        "feature": feature,
                        "message": f"Sačekajte {preostalo_cd}s pre sledećeg poziva ove funkcije.",
                    },
                )

        if dnevni_limit is not None:
            row = await _get_usage_row(user_id, feature)
            used_today = (row or {}).get("broj_koriscenja") or 0
            if used_today >= dnevni_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "DAILY_LIMIT",
                        "feature": feature,
                        "message": "Dostigli ste dnevni limit korišćenja za ovu funkciju. Pokušajte sutra.",
                    },
                )

        if mesecni_limit is not None:
            used_month = await _get_monthly_count(user_id, feature)
            if used_month >= mesecni_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "MONTHLY_LIMIT",
                        "feature": feature,
                        "message": "Dostigli ste mesečni limit korišćenja za ovu funkciju.",
                    },
                )

        # Beta Gate Blocker Closure (2026-08-08): the charge amount is resolved
        # to a whole number ONCE, here, and every branch below keys off it.
        # Previously the branch condition was `credits > 0` with an inner
        # `credits == 1` check, which meant a fractional registry price
        # (0 < krediti*multiplier < 1) fell into the n-credit path as
        # `int(0.5) == 0`. Migration 107 now correctly rejects p_n <= 0 with
        # -1 ("not charged"), which the caller turns into a 402 -- so a
        # fractional-priced feature would start failing outright. Resolving n
        # up front keeps that case behaving exactly as it always has (no
        # charge, no error) while making p_n <= 0 unreachable from the app.
        # The database rejects it independently anyway; this is defence in depth.
        n_credits = int(credits)
        if n_credits > 0:
            trenutno = await asyncio.to_thread(_get_credits, user_id)
            if trenutno < n_credits:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "code": "NO_CREDITS",
                        "feature": feature,
                        "message": (
                            "Nemate dovoljno kredita u mesečnom AI fondu za ovu funkciju. "
                            "Dokupite dodatni paket kredita ili sačekajte mesečni reset."
                        ),
                        "credits_remaining": trenutno,
                    },
                )
            # NOTE: the pre-check above is an optimisation for the common case
            # (fast, friendly 402 with the real balance). It is NOT the safety
            # mechanism -- it is a check-then-act read and races by definition.
            # The authoritative guard is the atomic conditional UPDATE inside
            # deduct_n_credits (migration 107): a caller that loses the race
            # gets -1 back and is rejected below, regardless of what the
            # pre-check saw.
            #
            # CREDIT-CONSUME-001 (CRITICAL, adversarial review 2026-08-08):
            # this used to route n_credits == 1 to _deduct_credit instead.
            # That function IS atomic (its UPDATE carries
            # `AND credits_remaining > 0`), but its RETURN CONTRACT is wrong:
            # production's body (supabase_setup.sql:139) ends its NOT-FOUND
            # branch with `RETURN COALESCE(new_credits, 0)` -- it returns the
            # CURRENT BALANCE, never a negative. So `preostalo < 0` below was
            # unreachable on that branch, the 402 never fired, and the paid
            # operation was delivered anyway. Reproduced against real
            # PostgreSQL: balance 1, 40 concurrent consume() calls -> 37
            # granted, 36 of them free.
            #
            # n == 1 is the DOMINANT price in feature_registry
            # (ai_pravna_pitanja, copilot, strategija at multiplier=1, ~25
            # more), so this was the widest credit hole in the product -- and
            # it survived the migration-107 work because 107 only ever
            # touched deduct_n_credits.
            #
            # Fixed by removing the special case entirely: every charge, of
            # every size including 1, now goes through the single function
            # whose contract is defined and tested (>=0 charged, -1 not
            # charged). Chosen over patching deduct_credit's return value
            # because it needs no further production migration, and because
            # one charging primitive cannot drift from another. Note the repo
            # contains two CONTRADICTORY deduct_credit definitions
            # (supabase_migration.sql:74 returns -1, supabase_setup.sql:139
            # returns 0) -- exactly the drift this removes reliance on.
            preostalo = await asyncio.to_thread(_deduct_n_credits, user_id, email, n_credits)
            if preostalo < 0:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "code": "NO_CREDITS",
                        "feature": feature,
                        "message": "Nemate dovoljno kredita u mesečnom AI fondu za ovu funkciju.",
                        "credits_remaining": 0,
                    },
                )
        else:
            preostalo = await asyncio.to_thread(_get_credits, user_id)

        await _increment_usage(user_id, feature, credits)
        await _log_usage_event(
            user_id, feature, credits, ai_model, est_cost,
            tokens_prompt, tokens_completion, latency_ms,
        )
        return preostalo

    @staticmethod
    async def balance(user_id: str, email: str) -> int:
        if _is_founder(email):
            return FOUNDER_BALANCE
        return await asyncio.to_thread(_get_credits, user_id)

    @staticmethod
    async def refund(
        user_id: str,
        email: str,
        feature: str,
        *,
        multiplier: Optional[int] = None,
        credits: Optional[int] = None,
    ) -> None:
        """Best-effort refund (npr. greška u generisanju posle uspešnog consume()).

        Beta Gate Blocker Closure (2026-08-08) — two defects fixed here:

        1. ASYMMETRY: this used to refund `krediti` while consume() charges
           `krediti * credit_multiplier`. For a 6x feature (strategija) a
           failed operation charged 12 and refunded 2 -- the user silently
           lost 10 credits for work they never received. The multiplier is now
           resolved with the SAME rule consume() uses, so charge and refund
           are symmetric by construction rather than by coincidence.
           `multiplier=` mirrors consume()'s own escape hatch for runtime-
           computed factors (e.g. multi_agent's actual agent count); a caller
           that charged with an explicit multiplier must refund with the same
           one.

        2. N ROUND-TRIPS -> 1: it looped `_refund_one_credit` once per credit,
           i.e. 12 separate non-atomic increments for a 6x feature, each its
           own race window. Now a single atomic refund_n_credits call
           (migration 107).
        """
        if _is_founder(email):
            return

        # CREDIT-REFUND-002 (HIGH, adversarial review 2026-08-08):
        # recomputing the amount from the registry is only symmetric with
        # consume() when the caller ALSO let consume() use the registry
        # multiplier. Three routers deliberately override it
        # (routers/strategija.py passes multiplier=1 against a registry
        # credit_multiplier of 6; digital_twin 3; strategy_simulator 2), so a
        # recomputed refund would return 6 for a 1-credit charge -- MINTING 5
        # credits per failure. Reproduced against the real database.
        #
        # `credits=` is therefore the preferred call form: pass the exact
        # amount consume() actually charged and no recomputation happens at
        # all. `multiplier=` remains for callers that know their runtime
        # factor. The registry fallback is kept only for the (majority)
        # callers that charge at the registry price, where it is exact.
        if credits is None:
            policy = await get_policy(feature)
            effective_multiplier = multiplier if multiplier is not None else policy.get("credit_multiplier", 1)
            credits = int(float(policy.get("krediti") or 0) * max(float(effective_multiplier or 1), 1))
        credits = int(credits)
        if credits <= 0:
            return
        await asyncio.to_thread(_refund_n_credits, user_id, credits)
