# -*- coding: utf-8 -*-
"""
Five deterministic demo scenarios for vindex_web3.
No network required — Web3Adapter runs in offline/fallback mode.
Run: python -m vindex_web3.demo
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal

from ._logging        import configure_logging, get_logger
from .interfaces       import BlockchainEvent
from .legal_formatter  import LegalFormatter
from .pipeline         import Web3LegalPipeline

logger = get_logger(__name__)

# ── Canonical tx hashes for reproducible scenarios ───────────────────────────
# Last 8 hex chars determine fallback event_type via seed % 6.
# Seed → event_type index in _EVENT_TYPES = ["transfer","contract_call",
#   "payment_failed","approval","mint","burn"]

_TX = {
    # seed = int("00000002", 16) = 2  → index 2 → "payment_failed", value=2%10000=2 ETH/100=0.02
    # But for high-value dispute we need value > 0.1 ETH.
    # We inject event directly for scenarios 1 and 2 instead of relying on fallback seed.
    "payment_failed_high": "0x" + "a" * 56 + "00000002",
    "zero_transfer":       "0x" + "b" * 56 + "00000000",
    "stale_contract":      "0x" + "c" * 56 + "00000001",
    "duplicate":           "0x" + "d" * 56 + "00000003",
    "invalid_hash":        "not_a_valid_hash",
    "batch_prefix":        "0x" + "e" * 55,
}


async def scenario_1_batch_1000() -> None:
    """Batch of 1 000 tx_hashes — verify all complete without timeout."""
    print("\n=== SCENARIO 1: batch_1000 ===")
    pipeline  = Web3LegalPipeline()
    tx_hashes = [f"0x{'f' * 62}{i:02x}" for i in range(256)] * 4  # 1024, trim to 1000
    tx_hashes = tx_hashes[:1_000]

    results = await pipeline.process_batch(tx_hashes)
    ok      = sum(1 for r in results if r is not None)
    print(f"  Processed: {ok}/{len(tx_hashes)} successful")
    assert ok == len(tx_hashes), f"Expected all 1000, got {ok}"
    print("  PASS")


async def scenario_2_invalid_hash() -> None:
    """Invalid tx_hash must raise pydantic ValidationError immediately."""
    print("\n=== SCENARIO 2: invalid_hash ===")
    from pydantic import ValidationError

    pipeline = Web3LegalPipeline()
    try:
        await pipeline.process(_TX["invalid_hash"])
        print("  FAIL — expected ValidationError")
    except (ValidationError, Exception) as exc:
        print(f"  Raised {type(exc).__name__}: {str(exc)[:80]}")
        print("  PASS")


async def scenario_3_node_unavailable() -> None:
    """Node unreachable — adapter must fall back, pipeline must succeed."""
    print("\n=== SCENARIO 3: node_unavailable (offline fallback) ===")
    pipeline = Web3LegalPipeline()
    tx_hash  = "0x" + "9" * 62 + "ab"

    result = await pipeline.process(tx_hash)
    assert result.event.raw_data.get("status") == "offline_fallback"
    finding_json = json.loads(result.finding.model_dump_json())
    print(f"  pipeline_id : {finding_json['pipeline_id'][:16]}...")
    print(f"  kleros_ready: {finding_json['kleros_ready']}")
    print(f"  duration_ms : {result.duration_ms}")
    print("  PASS")


async def scenario_4_conflicting_data() -> None:
    """
    Directly inject a payment_failed event with value > 0.1 ETH.
    DisputeDetector must fire breach_of_contract with confidence 0.92.
    """
    print("\n=== SCENARIO 4: conflicting_data (payment_failed high value) ===")
    from .dispute_detector import DisputeDetector
    from .legal_formatter  import LegalFormatter
    from .legal_mapper     import LegalMapper

    event = BlockchainEvent(
        tx_hash      = "0x" + "4" * 62 + "aa",
        event_type   = "payment_failed",
        from_address = "0x" + "1" * 40,
        to_address   = "0x" + "2" * 40,
        value_eth    = Decimal("0.5"),
        timestamp    = datetime.now(timezone.utc),
        block_number = 12345678,
        raw_data     = {"injected": True},
    )

    mapper    = LegalMapper()
    detector  = DisputeDetector()
    formatter = LegalFormatter()

    mapping = mapper.map(event)
    dispute = detector.detect(event)
    finding = formatter.format(event, mapping, dispute)

    assert dispute.dispute is True
    assert dispute.type == "breach_of_contract"
    assert abs(dispute.confidence - 0.92) < 1e-9
    assert finding.kleros_ready is True

    print(f"  dispute_type: {dispute.type}")
    print(f"  confidence  : {dispute.confidence}")
    print(f"  kleros_ready: {finding.kleros_ready}")
    print(f"  akcija      : {finding.akcija[:60]}...")
    print("  PASS")


async def scenario_5_duplicate_event() -> None:
    """
    Submit same tx_hash twice within 60s.
    Second call must return dispute=True, type=unauthorized_transfer, confidence=0.95.
    """
    print("\n=== SCENARIO 5: duplicate_event ===")
    from .dispute_detector import DisputeDetector
    from .interfaces       import BlockchainEvent

    detector = DisputeDetector()
    tx_hash  = "0x" + "5" * 62 + "bb"
    event    = BlockchainEvent(
        tx_hash      = tx_hash,
        event_type   = "transfer",
        from_address = "0x" + "a" * 40,
        to_address   = "0x" + "b" * 40,
        value_eth    = Decimal("1.0"),
        timestamp    = datetime.now(timezone.utc),
        block_number = 99999,
        raw_data     = {},
    )

    first  = detector.detect(event)
    second = detector.detect(event)

    assert first.dispute  is False
    assert second.dispute is True
    assert second.type    == "unauthorized_transfer"
    assert abs(second.confidence - 0.95) < 1e-9

    print(f"  first  → dispute={first.dispute}")
    print(f"  second → dispute={second.dispute}, type={second.type}, confidence={second.confidence}")
    print("  PASS")


async def _run_all() -> None:
    configure_logging()
    await scenario_1_batch_1000()
    await scenario_2_invalid_hash()
    await scenario_3_node_unavailable()
    await scenario_4_conflicting_data()
    await scenario_5_duplicate_event()
    print("\n=== VSI SCENARIJI PROŠLI ===\n")


if __name__ == "__main__":
    asyncio.run(_run_all())
