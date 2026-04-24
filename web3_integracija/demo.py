# -*- coding: utf-8 -*-
"""
Demo i simulacija Web3 modula — testiranje bez blockchain konekcije.
Uključuje async spike test sa Web3QueueEngine.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import time
from typing import Optional

from .schemas       import Web3LegalEvent, event_iz_krsenja
from .zoo_mapping   import detektuj_krsenje
from .health        import HealthStatus


# ─── Scenariji ────────────────────────────────────────────────────────────────

_SCENARIJI: dict[str, dict] = {
    "nepotpuna_uplata": {
        "tx_hash":       "0x42e4ca69b705de1b497c68a06809069b6f2fcf9da026130564c97e4f1234abcd",
        "amount_eth":    0.75,
        "tx_status":     "Nepotpun",
        "status_dobra":  "Ispravno",
        "rok_isporuke":  "Aktivan",
        "article":       "262",
        "breach_type":   "Pravo na ispunjenje obaveze",
        "opis":          "Kupac je uplatio 0.75 ETH od ugovorenih 1.00 ETH.",
    },
    "nedostatak_dobra": {
        "tx_hash":       "0xf1e2d3c4b5a6f1e2d3c4b5a6f1e2d3c4b5a6f1e2d3c4b5a6f1e2d3c45678ef01",
        "amount_eth":    2.0,
        "tx_status":     "Potpun",
        "status_dobra":  "Sa nedostatkom",
        "rok_isporuke":  "Aktivan",
        "article":       "154",
        "breach_type":   "Odgovornost za štetu",
        "opis":          "Token isporučen sa greškom u metapodacima — licenca nije validna.",
    },
    "istekao_rok": {
        "tx_hash":       "0xcafebabecafebabecafebabecafebabecafebabecafebabecafebabe12345678",
        "amount_eth":    0.5,
        "tx_status":     "Potpun",
        "status_dobra":  "Ispravno",
        "rok_isporuke":  "Istekao",
        "article":       "124",
        "breach_type":   "Raskid ugovora zbog neispunjenja",
        "opis":          "Rok isporuke ugovoren za 30 dana — prekoračen za 15 dana.",
    },
    "multiplo_krsenje": {
        "tx_hash":       "0xabcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        "amount_eth":    0.3,
        "tx_status":     "Nepotpun",
        "status_dobra":  "Sa nedostatkom",
        "rok_isporuke":  "Istekao",
        "article":       "262",  # primarno kršenje
        "breach_type":   "Pravo na ispunjenje obaveze",
        "opis":          "Nepotpuna uplata, neispravan token, prekoračen rok.",
    },
}


# ─── Sync simulacija ──────────────────────────────────────────────────────────

def simuliraj_blockchain_dogadjaj(
    scenario:  str                        = "nepotpuna_uplata",
    timestamp: Optional[datetime.datetime] = None,
) -> dict:
    """
    Kreira simulirani Web3LegalEvent bez mrežne konekcije.

    Vraća:
        {
          "transaction_id": str,
          "scenario":       str,
          "opis":           str,
          "event":          Web3LegalEvent,    ← strukturirani objekat
          "json":           dict,              ← to_dict() za JSON API
          "prompt":         str,               ← spreman za /api/pitanje
          "tip_podneska":   str,
          "clanovi_zoo":    list[str],
        }
    """
    if scenario not in _SCENARIJI:
        raise ValueError(
            f"Nepoznat scenario '{scenario}'. "
            f"Dostupni: {', '.join(_SCENARIJI)}"
        )

    s  = _SCENARIJI[scenario]
    ev = event_iz_krsenja(
        tx_hash     = s["tx_hash"],
        amount_eth  = s["amount_eth"],
        tx_status   = s["tx_status"],
        article     = s["article"],
        breach_type = s["breach_type"],
    )

    # Multiplo kršenje — dodaj sve članove u legal_context napomenu
    if scenario == "multiplo_krsenje":
        krsenja_dict = {
            "status_uplate": s["tx_status"],
            "status_dobra":  s["status_dobra"],
            "rok_isporuke":  s["rok_isporuke"],
        }
        sva_krsenja = detektuj_krsenje(krsenja_dict)
        clanovi     = [k.clan.broj for k in sva_krsenja]
        ev.instruction = (
            f"Sistemsko upozorenje: Detektovana VIŠESTRUKA kršenja blockchain "
            f"transakcije {s['tx_hash']}. "
            f"Primeni ZOO Članove {', '.join(clanovi)}. "
            f"Akcija: Generiši sveobuhvatni pravni podnesak."
        )
    else:
        clanovi = [s["article"]]

    from .web3_adapter import _tip_za_clan
    return {
        "transaction_id": s["tx_hash"],
        "scenario":       scenario,
        "opis":           s["opis"],
        "event":          ev,
        "json":           ev.to_dict(),
        "prompt":         ev.to_prompt(),
        "tip_podneska":   _tip_za_clan(s["article"]),
        "clanovi_zoo":    clanovi,
    }


def pokreni_sve_scenarije() -> list[dict]:
    """Pokreće simulaciju svih scenarija, vraća listu rezultata."""
    return [simuliraj_blockchain_dogadjaj(s) for s in _SCENARIJI]


# ─── Async spike test ─────────────────────────────────────────────────────────

async def spike_test(
    n_eventi:    int   = 100,
    max_rps:     int   = 20,
    worker_count: int  = 4,
) -> HealthStatus:
    """
    Simulira spike od n_eventi eventa u kratkom periodu.
    Verifikuje da queue engine apsorbuje opterećenje bez uglavljivanja.
    Vraća HealthStatus na kraju testa.
    """
    from .queue_engine import Web3QueueEngine

    procesiran: list[str] = []

    async def mock_dispatch(event: Web3LegalEvent) -> None:
        await asyncio.sleep(0.01)  # simuliraj 10ms mrežni poziv
        procesiran.append(event.event_id)

    engine = Web3QueueEngine(
        dispatch_fn    = mock_dispatch,
        max_rps        = max_rps,
        worker_count   = worker_count,
        max_queue_size = n_eventi * 2,
    )
    await engine.start()

    # Pošalji sve evente odjednom (spike)
    eventi = [simuliraj_blockchain_dogadjaj(list(_SCENARIJI.keys())[i % 4])["event"]
              for i in range(n_eventi)]

    enqueue_tasks = [engine.enqueue(ev) for ev in eventi]
    rezultati     = await asyncio.gather(*enqueue_tasks)
    prihvaceno    = sum(1 for r in rezultati if r)

    # Čekaj da se queue isprazni (max 60s)
    try:
        await asyncio.wait_for(engine._queue.join(), timeout=60.0)
    except asyncio.TimeoutError:
        pass

    health = engine.get_health()
    await engine.stop(grace_seconds=5.0)

    print(
        f"\n[spike_test] {n_eventi} eventa | "
        f"prihvaceno={prihvaceno} | "
        f"procesiran={len(procesiran)} | "
        f"health={health.status} | "
        f"avg_lat={health.avg_latency_ms:.1f}ms"
    )
    return health


# ─── get_health_status (globalna helper funkcija) ─────────────────────────────

def get_health_status(engine=None) -> dict:
    """
    Vraća health status adaptera.
    Ako nije prosleđen engine, vraća statičku proveru modula.
    """
    if engine is not None:
        return engine.get_health().to_dict()

    # Statička provera: modul ispravno učitan, imports OK
    from .rate_limiter import TokenBucketRateLimiter
    from .retry        import log_error
    from .health       import HealthMonitor
    from .schemas      import Web3LegalEvent

    rl = TokenBucketRateLimiter(20)
    hm = HealthMonitor(20)
    hm.record_success(0.050)
    st = hm.get_status(queue_size=0, queue_capacity=1000)
    return {
        "status":          "healthy",
        "module_loaded":   True,
        "rate_limiter_rps": rl.max_rps,
        "health_check":    st.to_dict(),
        "note":            "Statička provera — engine nije prosleđen.",
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 72)
    print("WEB3 ADAPTER — PRODUKCIJSKI DEMO")
    print("=" * 72)

    for naziv in _SCENARIJI:
        r = simuliraj_blockchain_dogadjaj(naziv)
        print(f"\n▶ Scenario: {naziv.upper()}")
        print(f"  TX (skraćen): {r['transaction_id'][:26]}...")
        print(f"  ZOO članov:   {r['clanovi_zoo']}")
        print(f"  Tip podneska: {r['tip_podneska']}")
        print(f"\n  JSON event:\n{r['event'].to_json(indent=4)[:400]}...")
        print("-" * 72)

    print("\n▶ Health status:")
    print(json.dumps(get_health_status(), ensure_ascii=False, indent=2))

    print("\n▶ Spike test (100 eventa, 20 RPS, 4 workera)...")
    asyncio.run(spike_test(n_eventi=100))
    print("\nDemo završen.")
