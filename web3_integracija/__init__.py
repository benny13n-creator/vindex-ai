# -*- coding: utf-8 -*-
"""
web3_integracija v2.0 — produkcijski Web3/Blockchain adapter za VindexAI.

JEDINI dozvoljeni interfejs sa Legal Engine-om:
    event.to_prompt()   → str  → POST /api/pitanje { "pitanje": <str> }
    event.to_json()     → str  → za audit trail / logove
    event.to_dict()     → dict → za programatski pristup

Primer minimalne integracije (bez menjanja postojećih fajlova):

    import asyncio, aiohttp
    from web3_integracija import simuliraj_blockchain_dogadjaj, Web3QueueEngine

    async def posalji(event):
        async with aiohttp.ClientSession() as s:
            await s.post(
                "https://vindex.ai/api/pitanje",
                json={"pitanje": event.to_prompt()},
                headers={"Authorization": "Bearer <token>"},
            )

    async def main():
        engine = Web3QueueEngine(dispatch_fn=posalji)
        await engine.start()

        r = simuliraj_blockchain_dogadjaj("nepotpuna_uplata")
        await engine.enqueue(r["event"])

        await engine.stop()

    asyncio.run(main())
"""

from .schemas       import Web3LegalEvent, LegalContext, BlockchainData, event_iz_krsenja
from .zoo_mapping   import ZOO_KATALOG, detektuj_krsenje, DetekcijaKrsenja
from .web3_adapter  import Web3Adapter
from .queue_engine  import Web3QueueEngine
from .health        import HealthMonitor, HealthStatus
from .rate_limiter  import TokenBucketRateLimiter
from .retry         import exponential_backoff, MaxRetriesExceeded, log_error
from .demo          import (
    simuliraj_blockchain_dogadjaj,
    pokreni_sve_scenarije,
    spike_test,
    get_health_status,
)

__all__ = [
    # Schemas
    "Web3LegalEvent", "LegalContext", "BlockchainData", "event_iz_krsenja",
    # ZOO
    "ZOO_KATALOG", "detektuj_krsenje", "DetekcijaKrsenja",
    # Adapter
    "Web3Adapter",
    # Engine
    "Web3QueueEngine",
    # Monitoring
    "HealthMonitor", "HealthStatus", "get_health_status",
    # Infrastructure
    "TokenBucketRateLimiter", "exponential_backoff", "MaxRetriesExceeded", "log_error",
    # Demo
    "simuliraj_blockchain_dogadjaj", "pokreni_sve_scenarije", "spike_test",
]

__version__ = "2.0.0"
