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
import uuid as _uuid
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


async def _increment_usage(
    user_id: str, feature: str, credits_spent: float, dnevni_limit: Optional[int] = None
) -> int:
    """Atomically count one use of `feature` for `user_id` today.

    Returns the new daily count, or -1 when `dnevni_limit` was already
    reached (in which case NOTHING was counted and the caller must reject).

    B1/B2 (second-order audit, 2026-08-08): this used to be a
    read-modify-write across two PostgREST round-trips —
        SELECT broj_koriscenja  ->  UPDATE broj_koriscenja = <read> + 1
    Two concurrent calls for the same (user_id, feature, dan) both read N and
    both wrote N+1, permanently losing one use in the user's favour. Worse, on
    the day's FIRST call both would INSERT, one would hit
    UNIQUE (user_id, feature_key, dan), and the 23505 was swallowed by the
    bare except below and logged non-fatal — that use was never counted at all.

    This is not a cosmetic counter: `dnevni_limit`/`mesecni_limit` are checked
    against it, and for the two features priced at ZERO credits
    (copilot_ambient dnevni 200, morning_briefing dnevni 5) it is the ONLY
    budget protection that exists.

    Migration 108's increment_feature_usage does check-and-increment in ONE
    statement, so passing `dnevni_limit` here also closes the separate
    check-then-act window in consume() (the limit was read at the top and the
    counter written an entire AI call later).
    """
    today = _today_iso()
    mesec = _month_iso()

    def _rpc() -> int:
        res = _get_supa().rpc("increment_feature_usage", {
            "p_user_id": user_id,
            "p_feature": feature,
            "p_dan": today,
            "p_mesec": mesec,
            "p_credits": float(credits_spent or 0),
            "p_dnevni_limit": dnevni_limit,
        }).execute()
        return res.data if res.data is not None else -1

    try:
        return await asyncio.to_thread(_rpc)
    except Exception as exc:
        # Fail SOFT and fail OPEN, deliberately: the credit itself was already
        # settled by deduct_n_credits, which is the source of truth for money.
        # Blocking a paying lawyer because a usage COUNTER could not be written
        # would be a worse outcome than an uncounted use. Logged on its own
        # marker so a missing migration 108 is visible rather than silent.
        logger.warning(
            "[USAGE] increment_feature_usage RPC failed for feature=%s (migration 108 applied?) "
            "— use not counted, request allowed: %s", feature, exc,
        )
        return 0


def _nedostaje_kolona(exc: Exception) -> bool:
    """Da li greška znači „ta kolona još ne postoji" (migracija 112 nije
    pokrenuta), a ne stvarni kvar (pad konekcije, timeout)?

    Šire je od `shared/audit_immutable._is_missing_column_error`, koje se
    oslanja na Postgres SQLSTATE 42703 / „does not exist". Supabase klijent ne
    priča direktno sa Postgres-om nego sa PostgREST-om, koji za nepoznatu
    kolonu u INSERT payload-u vraća PGRST204 sa porukom oblika
    „Could not find the 'predmet_id' column of 'feature_usage_log' in the
    schema cache" — u njoj NEMA ni „42703" ni „does not exist". Oslanjanje
    samo na postojeći helper bi zato promašilo baš onaj slučaj zbog kog ovaj
    fallback postoji.

    Namerno usko (a ne `except Exception`): stvarni kvar baze mora da propagira
    odmah, bez drugog osuđenog pokušaja upisa.
    """
    try:
        from shared.audit_immutable import _is_missing_column_error
        if _is_missing_column_error(exc):
            return True
    except Exception:
        pass
    msg = str(exc).lower()
    return "pgrst204" in msg or "schema cache" in msg or "42703" in msg


def _kanonski_uuid(vrednost) -> Optional[str]:
    """Vraća `vrednost` u kanonskom UUID obliku, ili None ako to nije UUID.

    RC-112-DEBT-001 — IZMERENO nad pravim PostgreSQL-om, nije pretpostavka:

      `feature_usage_log.predmet_id` je tipa `uuid` (migracija 112:51, jer je
      `predmeti.id` UUID). Upis vrednosti koja nije UUID (npr. „PRED-42") obara
      INSERT sa SQLSTATE 22P02 `invalid input syntax for type uuid: "PRED-42"`.
      Ta poruka NE sadrži ni „42703", ni „does not exist", ni „PGRST204", ni
      „schema cache" — pa `_nedostaje_kolona` vraća False, uski fallback u
      `_log_usage_event` se NE aktivira, izuzetak stiže do spoljnog `except`-a i
      CEO red telemetrije naplate tiho nestaje: ne samo `predmet_id`, nego i
      `user_id`, `feature_key` i `krediti_potroseni`.

      Danas je to nedostižno — nijedan od 137 pozivalaca u `routers/` ne
      prosleđuje `consume(predmet_id=...)`. Postaje dostižno čim prvi počne, a
      to je tačno ono zbog čega je taj keyword argument i dodat.

    ZAŠTO OVDE, A NE PROŠIRENJEM `_nedostaje_kolona` NA 22P02
      * 22P02 znači „vrednost je pogrešnog oblika", ne „kolona ne postoji".
        Helper bi time lagao o sopstvenom imenu i docstring-u.
      * Taj fallback odbacuje OBA provenance polja. Ovde se odbacuje samo
        neupotrebljiv `predmet_id`, dok `correlation_id` (tip `text`, bez
        ograničenja) preživi — a baš on nosi tranzitivni JOIN do predmeta preko
        `ai_forensics` (v. zaglavlje migracije 112). Sačuva se dakle VIŠE
        telemetrije, ne manje.
      * Loša vrednost nikad ne stigne do Postgres-a, pa nema ni drugog
        osuđenog upisa — namera „usko, bez drugog pokušaja" iz
        `_nedostaje_kolona` ostaje netaknuta.

    Vraća se KANONSKI oblik (`str(uuid.UUID(...))`), ne original: Python
    prihvata i zapise koje Postgres odbija (npr. `urn:uuid:` prefiks), pa bi
    propuštanje originala ostavilo usku verziju istog defekta.

    Naplata se ovim NE dira ni u jednoj grani — ovo je isključivo telemetrija.
    """
    try:
        return str(_uuid.UUID(str(vrednost)))
    except (ValueError, AttributeError, TypeError):
        return None


def _provenance_polja(predmet_id: Optional[str] = None) -> dict:
    """Čita `correlation_id`/`predmet_id` iz `shared/ai_provenance` contextvar-a.

    IZMERENO STANJE (Wave 9, §17) — ne pretpostavka:

      * `correlation_id` JESTE dostupan u trenutku naplate. Postavlja ga
        `set_request_context` na auth chokepoint-u (`api.py:3450`,
        `shared/deps.py:326`) pozivom `.set()` BEZ restore-a, pa važi za ceo
        request; sonda potvrđuje da preživi i `asyncio.to_thread` i
        `asyncio.create_task` (pozadinski poslovi).

      * `predmet_id` NIJE dostupan. Živi u `_case_ctx`, koji `case_context`
        vraća na prethodnu vrednost pri izlasku iz `with` bloka. AST merenje
        svih poziva `UsageService.consume` u repou: **0 od 113** leži unutar
        `with case_context(...)` — svi se zovu POSLE bloka (npr.
        `routers/strategija.py:581` je izvan `with _ai_case_ctx`). Zato se
        čitanje iz konteksta ovde zadržava samo kao ispravan fallback za
        buduće pozivaoce, a stvarni put za predmet je eksplicitan
        `consume(predmet_id=...)` — keyword-only, sa default-om, pa nijedan od
        153 postojeća pozivaoca ne mora da se menja.

    Praktična posledica: i kad je `predmet_id` NULL, predmet je i dalje
    dobavljiv TRANZITIVNO, jer `ai_forensics` nosi i `correlation_id` i
    `predmet_id` (JOIN opisan u migraciji 112).

    STROGO fail-soft: bilo koja greška → prazan dict, upis ide kao i do sada.
    """
    polja: dict = {}

    def _upisi_predmet(vrednost, izvor: str) -> None:
        """RC-112-DEBT-001: samo validan UUID sme u `uuid` kolonu.

        Odbacivanje jednog neupotrebljivog metapodatka je uvek bolje od gubitka
        celog reda telemetrije naplate — v. `_kanonski_uuid`.
        """
        kanonski = _kanonski_uuid(vrednost)
        if kanonski is not None:
            polja["predmet_id"] = kanonski
            return
        # Neispravan EKSPLICITAN argument briše i vrednost pročitanu iz
        # konteksta. Pad na contextvar bi upisao DRUGI predmet od onog koji je
        # pozivalac imenovao — pogrešna atribucija naplate je gora od NULL-a,
        # jer NULL znači „nije zabeleženo", a pogrešan UUID tvrdi neistinu
        # (v. COMMENT ON COLUMN u migraciji 112).
        polja.pop("predmet_id", None)
        logger.warning(
            "[USAGE] predmet_id iz izvora %s nije UUID — izostavljen iz telemetrije "
            "da bi red naplate ipak bio upisan (feature_usage_log.predmet_id je tipa uuid, "
            "migracija 112); correlation_id ostaje i vodi do predmeta preko ai_forensics",
            izvor,
        )

    try:
        from shared.ai_provenance import current_context
        ctx = current_context() or {}
        if ctx.get("correlation_id"):
            polja["correlation_id"] = ctx["correlation_id"]
        if ctx.get("predmet_id"):
            _upisi_predmet(ctx["predmet_id"], "contextvar")
    except Exception as exc:
        # Telemetrija nikad ne sme da obori naplatu — ni čitanjem konteksta.
        logger.debug("[USAGE] provenance kontekst nedostupan (non-fatal): %s", exc)
    # Eksplicitan argument je jači od konteksta: pozivalac zna svoj predmet
    # pouzdanije nego contextvar koji je u 113/113 slučajeva već resetovan.
    if predmet_id:
        _upisi_predmet(predmet_id, "argument consume(predmet_id=...)")
    return polja


async def _log_usage_event(
    user_id: str, feature: str, credits_spent: float, ai_model: Optional[str],
    estimated_cost_usd: Optional[float], tokens_prompt: Optional[int],
    tokens_completion: Optional[int], latency_ms: Optional[int],
    predmet_id: Optional[str] = None,
) -> None:
    osnovni = {
        "user_id": user_id,
        "feature_key": feature,
        "krediti_potroseni": credits_spent,
        "ai_model": ai_model,
        "estimated_cost_usd": estimated_cost_usd,
        "tokens_prompt": tokens_prompt,
        "tokens_completion": tokens_completion,
        "latency_ms": latency_ms,
    }
    prov = _provenance_polja(predmet_id)

    def _insert(payload: dict):
        _get_supa().table("feature_usage_log").insert(payload).execute()

    try:
        if prov:
            # „Probaj široko, pa usko" — isti idiom koji repo već koristi za
            # kolone koje čekaju migraciju (`security/ai_forensics.py:310-321`,
            # `shared/audit_immutable.py:401-406`).
            #
            # BEZ ovog fallback-a bi dodavanje kolona bilo REGRESIJA: migraciju
            # 112 vlasnik pokreće ručno, pa bi do tada PostgREST odbijao ceo
            # INSERT zbog nepoznate kolone, spoljni `except` bi to progutao na
            # debug nivou, i SVAKI red telemetrije naplate bi tiho nestajao.
            try:
                await asyncio.to_thread(_insert, {**osnovni, **prov})
                return
            except Exception as sirok_exc:
                if not _nedostaje_kolona(sirok_exc):
                    raise
                logger.debug(
                    "[USAGE] provenance kolone ne postoje (migracija 112 pokrenuta?) "
                    "— upisujem bez njih: %s", sirok_exc,
                )
        await asyncio.to_thread(_insert, osnovni)
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
        predmet_id: Optional[str] = None,
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

        predmet_id (Wave 9, §17) je OPCION i keyword-only — dodat je tako da
        nijedan od 153 postojeća pozivaoca ne mora da se menja, i NE UTIČE na
        gejtovanje, cenu ni na bilo koji deo naplatne semantike. Koristi se
        isključivo za telemetriju: upisuje se u `feature_usage_log.predmet_id`
        (migracija 112) da bi se lanac naplata → predmet mogao dokazati
        spajanjem. Prosleđuje ga onaj pozivalac koji predmet zna; ostali ga
        izostavljaju i kolona ostaje NULL, tačno kao pre ove izmene.

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

        # Fast, friendly pre-check. NOT the enforcement mechanism -- it is a
        # check-then-act read and races by definition. The authoritative daily
        # gate is the atomic increment further down (migration 108), which
        # refuses to count a use that would exceed the limit and returns -1.
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
        # ── AUTHORITATIVE DAILY GATE ──────────────────────────────────────
        # B2: this runs BEFORE the charge, on purpose. The two features whose
        # daily limit is the only budget protection (copilot_ambient,
        # morning_briefing) are priced at ZERO credits, so for exactly the
        # cases where the limit matters there is no charge that can fail after
        # this point. For priced features the credit pre-check above already
        # rejects the common insufficient-balance case, so counting a use whose
        # charge then loses a race is a narrow, documented over-count against
        # the user rather than a silent free use against the business — the
        # same conservative trade-off already accepted for _claim_cooldown_atomic.
        _usage_count = await _increment_usage(user_id, feature, credits, dnevni_limit)
        if _usage_count < 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "DAILY_LIMIT",
                    "feature": feature,
                    "message": "Dostigli ste dnevni limit korišćenja za ovu funkciju. Pokušajte sutra.",
                },
            )

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

        # NIGHT-001 (2026-08-09): the pre-charge _increment_usage above at the
        # daily-gate is the ONLY increment. This second call was left behind by
        # the migration-108 change that moved counting BEFORE the charge, and
        # every successful consume() was therefore counted twice:
        # increment_feature_usage adds 1 to broj_koriscenja and p_credits to
        # krediti_potroseni on each call.
        #
        # Consequences, all silent: every dnevni_limit was effectively halved
        # (copilot_ambient 200->100, morning_briefing 5->3), every mesecni_limit
        # likewise, and GET /api/plans/status told users they had spent twice
        # what their balance actually dropped by.
        #
        # No test caught it because every existing test mocks _increment_usage
        # and none asserts how many times it is called. The regression test
        # added with this fix asserts exactly that.
        await _log_usage_event(
            user_id, feature, credits, ai_model, est_cost,
            tokens_prompt, tokens_completion, latency_ms,
            predmet_id,
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
