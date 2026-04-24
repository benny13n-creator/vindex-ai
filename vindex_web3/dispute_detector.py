# -*- coding: utf-8 -*-
"""
Deterministic rule engine for dispute detection. Zero AI — pure rule table.
Rules are dataclasses, not hardcoded if/else. TTL-based deduplication (60s).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from ._logging  import get_logger
from .interfaces import BlockchainEvent, DisputeResult, DisputeType

logger = get_logger(__name__)

_DEDUP_TTL_S: float = 60.0


@dataclass(frozen=True)
class DisputeRule:
    """Single deterministic dispute rule."""

    name:         str
    dispute_type: DisputeType
    confidence:   float
    predicate:    Callable[[BlockchainEvent], bool]
    evidence_fn:  Callable[[BlockchainEvent], list[str]]


def _eth_gt(threshold: float) -> Callable[[BlockchainEvent], bool]:
    return lambda e: float(e.value_eth) > threshold


def _eth_eq(value: float) -> Callable[[BlockchainEvent], bool]:
    return lambda e: float(e.value_eth) == value


# ── Rule table ────────────────────────────────────────────────────────────────

DISPUTE_RULES: list[DisputeRule] = [
    DisputeRule(
        name         = "payment_failed_high_value",
        dispute_type = "breach_of_contract",
        confidence   = 0.92,
        predicate    = lambda e: (
            e.event_type == "payment_failed" and float(e.value_eth) > 0.1
        ),
        evidence_fn  = lambda e: [
            f"event_type=payment_failed",
            f"value_eth={e.value_eth}",
            f"threshold=0.1_ETH",
            f"tx_hash={e.tx_hash}",
        ],
    ),
    DisputeRule(
        name         = "zero_value_transfer",
        dispute_type = "unauthorized_transfer",
        confidence   = 0.85,
        predicate    = lambda e: (
            e.event_type == "transfer" and float(e.value_eth) == 0.0
        ),
        evidence_fn  = lambda e: [
            f"event_type=transfer",
            f"value_eth=0",
            f"from={e.from_address}",
            f"to={e.to_address}",
            f"tx_hash={e.tx_hash}",
        ],
    ),
    DisputeRule(
        name         = "contract_call_stale",
        dispute_type = "contract_violation",
        confidence   = 0.78,
        predicate    = lambda e: (
            e.event_type == "contract_call"
            and (time.time() - e.timestamp.timestamp()) > 3600
        ),
        evidence_fn  = lambda e: [
            f"event_type=contract_call",
            f"age_s={round(time.time() - e.timestamp.timestamp())}",
            f"threshold_s=3600",
            f"tx_hash={e.tx_hash}",
        ],
    ),
]


# ── Deduplication store ───────────────────────────────────────────────────────

@dataclass
class _DedupStore:
    """In-memory TTL dedup for tx_hash. Thread-safe within single async loop."""

    _seen: dict[str, float] = field(default_factory=dict)

    def is_duplicate(self, tx_hash: str) -> bool:
        now = time.time()
        self._purge(now)
        return tx_hash in self._seen

    def mark(self, tx_hash: str) -> None:
        self._seen[tx_hash] = time.time()

    def _purge(self, now: float) -> None:
        expired = [k for k, t in self._seen.items() if now - t > _DEDUP_TTL_S]
        for k in expired:
            del self._seen[k]


# ── Public detector ───────────────────────────────────────────────────────────

class DisputeDetector:
    """
    Applies DISPUTE_RULES + TTL deduplication to a BlockchainEvent.

    Returns DisputeResult(dispute=False, ...) when no rule fires.
    The duplicate-tx rule has the highest confidence (0.95) and is checked first.
    """

    def __init__(self) -> None:
        self._dedup = _DedupStore()

    def detect(self, event: BlockchainEvent) -> DisputeResult:
        # Duplicate check — highest priority
        if self._dedup.is_duplicate(event.tx_hash):
            logger.info(
                "dispute.duplicate_detected",
                extra={"tx_hash": event.tx_hash},
            )
            return DisputeResult(
                dispute       = True,
                type          = "unauthorized_transfer",
                confidence    = 0.95,
                evidence_refs = [
                    f"duplicate_tx_hash={event.tx_hash}",
                    f"ttl_s={_DEDUP_TTL_S}",
                ],
            )

        self._dedup.mark(event.tx_hash)

        # Rule table scan
        for rule in DISPUTE_RULES:
            try:
                if rule.predicate(event):
                    refs = rule.evidence_fn(event)
                    logger.info(
                        "dispute.rule_fired",
                        extra={
                            "rule":         rule.name,
                            "dispute_type": rule.dispute_type,
                            "confidence":   rule.confidence,
                            "tx_hash":      event.tx_hash,
                        },
                    )
                    return DisputeResult(
                        dispute       = True,
                        type          = rule.dispute_type,
                        confidence    = rule.confidence,
                        evidence_refs = refs,
                    )
            except Exception as exc:
                logger.warning(
                    "dispute.rule_error",
                    extra={"rule": rule.name, "error": str(exc)},
                )

        return DisputeResult(
            dispute       = False,
            type          = "no_dispute",
            confidence    = 1.0,
            evidence_refs = [],
        )
