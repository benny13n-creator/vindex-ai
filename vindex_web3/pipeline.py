# -*- coding: utf-8 -*-
"""
Web3LegalPipeline — orchestrates all stages with 10s timeout per event.
process_batch() uses asyncio.gather + Semaphore(50) for concurrency control.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from ._logging        import get_logger
from .dispute_detector import DisputeDetector
from .interfaces       import BlockchainEvent, KlerosPackage, LegalFinding
from .kleros_adapter   import KlerosAdapter
from .legal_formatter  import LegalFormatter
from .legal_mapper     import LegalMapper
from .web3_adapter     import Web3Adapter

logger = get_logger(__name__)

_PIPELINE_TIMEOUT_S  = 10.0
_BATCH_CONCURRENCY   = 50


@dataclass
class PipelineResult:
    """Output of a single pipeline run."""

    tx_hash:        str
    event:          BlockchainEvent
    finding:        LegalFinding
    kleros_package: KlerosPackage | None   # None when kleros_ready=False
    duration_ms:    float
    stages:         dict[str, float]       # stage → elapsed ms at completion


class Web3LegalPipeline:
    """
    Stateless orchestrator. Each process() call is independent.
    Components are injected at construction — easy to mock in tests.
    """

    def __init__(
        self,
        adapter:   Web3Adapter    | None = None,
        mapper:    LegalMapper    | None = None,
        detector:  DisputeDetector| None = None,
        formatter: LegalFormatter | None = None,
        kleros:    KlerosAdapter  | None = None,
    ) -> None:
        self._adapter   = adapter   or Web3Adapter()
        self._mapper    = mapper    or LegalMapper()
        self._detector  = detector  or DisputeDetector()
        self._formatter = formatter or LegalFormatter()
        self._kleros    = kleros    or KlerosAdapter()

    async def process(self, tx_hash: str) -> PipelineResult:
        """
        Run all stages for a single tx_hash with a 10s overall timeout.
        Raises asyncio.TimeoutError if the pipeline exceeds 10s.
        """
        async with asyncio.timeout(_PIPELINE_TIMEOUT_S):
            return await self._run(tx_hash)

    async def process_batch(self, tx_hashes: list[str]) -> list[PipelineResult]:
        """
        Process multiple tx_hashes concurrently (max 50 in flight).
        Exceptions per-item are caught and logged — never propagated.
        Returns results in the same order as input (failed items are None).
        """
        sem = asyncio.Semaphore(_BATCH_CONCURRENCY)

        async def _guarded(tx: str) -> PipelineResult | None:
            async with sem:
                try:
                    return await self.process(tx)
                except Exception as exc:
                    logger.warning(
                        "pipeline.batch_item_failed",
                        extra={"tx_hash": tx, "error": str(exc)},
                    )
                    return None

        tasks = [asyncio.create_task(_guarded(tx)) for tx in tx_hashes]
        return list(await asyncio.gather(*tasks))

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _run(self, tx_hash: str) -> PipelineResult:
        t0     = time.monotonic()
        stages: dict[str, float] = {}

        # Stage 1: fetch
        event = await self._adapter.fetch_event(tx_hash)
        stages["fetch"] = _ms(t0)
        logger.info("pipeline.stage.fetch", extra={"tx_hash": tx_hash, "ms": stages["fetch"]})

        # Stage 2: map
        mapping = self._mapper.map(event)
        stages["map"] = _ms(t0)
        logger.info("pipeline.stage.map", extra={"tx_hash": tx_hash, "ms": stages["map"]})

        # Stage 3: detect dispute
        dispute = self._detector.detect(event)
        stages["detect"] = _ms(t0)
        logger.info("pipeline.stage.detect", extra={"tx_hash": tx_hash, "ms": stages["detect"],
                                                     "dispute": dispute.dispute})

        # Stage 4: format
        finding = self._formatter.format(event, mapping, dispute)
        stages["format"] = _ms(t0)
        logger.info("pipeline.stage.format", extra={"tx_hash": tx_hash, "ms": stages["format"]})

        # Stage 5: Kleros (only when kleros_ready)
        kleros_pkg: KlerosPackage | None = None
        if finding.kleros_ready:
            kleros_pkg = self._kleros.prepare_case(finding)
        stages["kleros"] = _ms(t0)

        total_ms = _ms(t0)
        logger.info(
            "pipeline.complete",
            extra={
                "tx_hash":     tx_hash,
                "total_ms":    total_ms,
                "kleros_ready":finding.kleros_ready,
                "pipeline_id": finding.pipeline_id,
            },
        )

        return PipelineResult(
            tx_hash        = tx_hash,
            event          = event,
            finding        = finding,
            kleros_package = kleros_pkg,
            duration_ms    = total_ms,
            stages         = stages,
        )


def _ms(t0: float) -> float:
    return round((time.monotonic() - t0) * 1_000, 2)
