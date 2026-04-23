# -*- coding: utf-8 -*-
"""
Pydantic v2 shared models for vindex_web3.
Defined first — all other modules import from here.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

# ── Type aliases ──────────────────────────────────────────────────────────────

EventType   = Literal["transfer", "contract_call", "payment_failed",
                      "approval", "mint", "burn"]
DisputeType = Literal["breach_of_contract", "non_payment",
                      "unauthorized_transfer", "contract_violation", "no_dispute"]
RiskLevel   = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

_TX_PATTERN   = re.compile(r"^0x[a-fA-F0-9]{64}$")
_ADDR_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")

_RISK_ORDER: dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


# ── Core blockchain model ─────────────────────────────────────────────────────

class BlockchainEvent(BaseModel):
    """Normalized blockchain event. tx_hash must be 0x + 64 hex chars."""

    tx_hash:      str
    event_type:   EventType
    from_address: str
    to_address:   str
    value_eth:    Decimal
    timestamp:    datetime
    block_number: int
    raw_data:     dict[str, Any]

    @field_validator("tx_hash")
    @classmethod
    def validate_tx_hash(cls, v: str) -> str:
        if not _TX_PATTERN.match(v):
            raise ValueError(
                f"tx_hash must match ^0x[a-fA-F0-9]{{64}}$, got {v!r}"
            )
        return v.lower()

    @field_validator("from_address", "to_address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        if not _ADDR_PATTERN.match(v):
            raise ValueError(f"EVM address must be 0x + 40 hex chars, got {v!r}")
        return v.lower()

    @field_validator("value_eth")
    @classmethod
    def validate_value(cls, v: Decimal) -> Decimal:
        if v < Decimal("0"):
            raise ValueError("value_eth cannot be negative")
        return v

    @field_validator("block_number")
    @classmethod
    def validate_block(cls, v: int) -> int:
        if v < 0:
            raise ValueError("block_number cannot be negative")
        return v


# ── Legal mapping ─────────────────────────────────────────────────────────────

class LegalMapping(BaseModel):
    """Deterministic mapping from blockchain event type to Serbian law."""

    pravna_kategorija: str
    zakon:             str
    clan:              int
    opis:              str
    weight:            int = 1   # priority: higher = more primary in multi-law results


# ── Multi-law reference ───────────────────────────────────────────────────────

class LawReference(BaseModel):
    """
    Reference to a specific article in one of the four covered Serbian laws.
    Used in LegalFinding.applicable_laws for multi-law coverage.
    """

    law_code:             str        # e.g. "ZOO", "ZDI", "ZSPNFT", "ZPDG"
    law_name_sr:          str        # full Serbian name
    article_number:       str        # "262", "72b", etc.
    article_title_sr:     str
    article_summary_sr:   str
    compliance_risk_level: RiskLevel


# ── Dispute detection ─────────────────────────────────────────────────────────

class DisputeResult(BaseModel):
    """Output of DisputeDetector.detect()."""

    dispute:       bool
    type:          DisputeType
    confidence:    float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str]


# ── Legal finding (nested models) ─────────────────────────────────────────────

class PravniOsnov(BaseModel):
    """Legal basis section of a finding."""

    zakon:             str
    clan:              int
    opis:              str
    pravna_kategorija: str


class Dokazi(BaseModel):
    """Evidence section derived from blockchain event."""

    tx_hash:       str
    block_number:  int
    timestamp:     datetime
    vrednost_eth:  Decimal
    event_type:    EventType
    from_address:  str
    to_address:    str


class LegalFinding(BaseModel):
    """Complete legal analysis output. pipeline_id is SHA-256 deterministic."""

    upozorenje:      str
    pravni_osnov:    PravniOsnov
    akcija:          str
    dokazi:          Dokazi
    kleros_ready:    bool
    timestamp:       datetime
    pipeline_id:     str               # SHA256(tx_hash + timestamp.isoformat())

    # ── Multi-law coverage (Faza 1) ──
    applicable_laws: list[LawReference] = Field(default_factory=list)
    primary_law:     str               = "ZOO"
    risk_level:      str               = "LOW"   # highest across applicable_laws


# ── Kleros v2 package ─────────────────────────────────────────────────────────

class KlerosPackage(BaseModel):
    """Evidence package compatible with Kleros v2 API."""

    case_description:  Annotated[str, Field(max_length=2000)]
    evidence_hash:     str
    metaevidence_uri:  str
    pipeline_id:       str
    finding_summary:   str
    parties:           dict[str, str]
    value_eth:         Decimal
    created_at:        datetime

    # ── Faza 5 fields (optional — populated only when KLEROS_ENABLED=true) ──
    dispute_id:        str | None = None
    dispute_status:    str | None = None

    @field_validator("evidence_hash")
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        if not re.match(r"^[a-f0-9]{64}$", v):
            raise ValueError("evidence_hash must be lowercase SHA-256 hex")
        return v

    @field_validator("metaevidence_uri")
    @classmethod
    def validate_ipfs_uri(cls, v: str) -> str:
        if not v.startswith("ipfs://"):
            raise ValueError("metaevidence_uri must start with ipfs://")
        return v
