# -*- coding: utf-8 -*-
"""
Vindex AI — shared/postgrest_compat.py

JEDNO MESTO NA KOM SE POPRAVLJA UGOVOR `maybe_single()`.

ŠTA JE MERENO

`postgrest==2.28.3` (`SyncMaybeSingleRequestBuilder.execute`) vraća **`None`**
kad upit nema nijedan red — ne objekat odgovora sa `data=None`. Kod koji piše

    red = supa.table("t").select("*").eq("id", x).maybe_single().execute()
    if not red.data:
        raise HTTPException(404, ...)

tada ne podiže 404 nego **`AttributeError` → HTTP 500**, a grana koja je trebalo
da vrati 404 nikad se ne izvrši.

Prebrojano u ovom repozitorijumu: **230 poziva `maybe_single()`, od toga 201 bez
zaštite**. Odsustvo reda je NORMALNO stanje — pogotovo za novog korisnika, kome
još ne postoji nijedan red ni u jednoj tabeli.

Mereno stvarnim HTTP pozivom tokom NIGHT STABILIZATION 001: otvaranje predmeta
(`GET /api/predmeti/{id}/workspace`) vraćalo je 500 i vlasniku predmeta, jer
`UsageService.consume` → `_claim_cooldown_atomic` (`shared/usage.py:168`) čita
`exists.data` na redu `feature_usage` koji za novog korisnika ne postoji.

ZAŠTO ŠIM, A NE 201 IZMENA

Nekoliko fajlova je ovo već rešavalo pojedinačno (`res.data if res else None` u
`shared/intake_documents.py`, `services/case_evolution.py`, `routers/
client_portal.py`, `shared/case_context.py`) — svaki tek pošto bi pukao u
produkciji. To je isti obrazac koji Core Consolidation zabranjuje: jedno
ponašanje, 201 mesta na kojima se mora zapamtiti.

Ugovor se zato vraća na mesto na kom je i pokvaren — na granici biblioteke, u
jednoj funkciji. Kod koji je već zaštićen (`res.data if res else None`) radi
neizmenjeno: `.data` i dalje daje `None`, pa je izraz i dalje `None`.

ŠTA OVO NE RADI

Ne menja nijedan drugi ishod: greške, višestruki redovi i uspešni upiti prolaze
netaknuti. Ne dira `single()` — on po dizajnu diže grešku na 0 redova i to je
odvojena odluka svakog pozivaoca.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_OZNAKA = "_vindex_maybe_single_shim"


def _omotaj(klasa) -> bool:
    """Vraća True ako je šim upravo primenjen na ovu klasu."""
    izvorni = getattr(klasa, "execute", None)
    if izvorni is None or getattr(izvorni, _OZNAKA, False):
        return False

    from postgrest.base_request_builder import SingleAPIResponse

    if getattr(klasa, "__module__", "").startswith("postgrest._async"):
        async def execute(self, *a, **k):
            r = await izvorni(self, *a, **k)
            return r if r is not None else SingleAPIResponse(data=None, count=None)
    else:
        def execute(self, *a, **k):
            r = izvorni(self, *a, **k)
            return r if r is not None else SingleAPIResponse(data=None, count=None)

    setattr(execute, _OZNAKA, True)
    klasa.execute = execute
    return True


def primeni() -> int:
    """Idempotentno. Vraća broj klasa na koje je šim primenjen ovim pozivom."""
    primenjeno = 0
    try:
        from postgrest._sync.request_builder import SyncMaybeSingleRequestBuilder
        primenjeno += int(_omotaj(SyncMaybeSingleRequestBuilder))
    except Exception as exc:  # pragma: no cover — zavisi od verzije biblioteke
        logger.warning("[PGRST-COMPAT] sync šim nije primenjen: %s", exc)
    try:
        from postgrest._async.request_builder import AsyncMaybeSingleRequestBuilder
        primenjeno += int(_omotaj(AsyncMaybeSingleRequestBuilder))
    except Exception as exc:  # pragma: no cover
        logger.warning("[PGRST-COMPAT] async šim nije primenjen: %s", exc)
    if primenjeno:
        logger.info("[PGRST-COMPAT] maybe_single() ugovor normalizovan na %d klasi/e", primenjeno)
    return primenjeno


def je_primenjen() -> bool:
    """Za testove i dijagnostiku — da li ugovor trenutno važi."""
    try:
        from postgrest._sync.request_builder import SyncMaybeSingleRequestBuilder
        return bool(getattr(SyncMaybeSingleRequestBuilder.execute, _OZNAKA, False))
    except Exception:
        return False
