# -*- coding: utf-8 -*-
"""
vindex_web3 — Production blockchain-to-Serbian-law pipeline.

Public API:
    Web3LegalPipeline   — main orchestrator (process / process_batch)
    PipelineResult      — output dataclass
    BlockchainEvent     — Pydantic v2 blockchain model
    LegalFinding        — full legal analysis output
    LawReference        — multi-law reference (ZOO/ZDI/ZSPNFT/ZPDG)
    KlerosPackage       — Kleros v2 evidence package
    configure_logging   — call once at startup
"""
from ._logging        import configure_logging, get_logger
from .interfaces       import (
    BlockchainEvent,
    DisputeResult,
    EventType,
    KlerosPackage,
    LawReference,
    LegalFinding,
    LegalMapping,
    RiskLevel,
)
from .law_registry     import get_applicable_laws, highest_risk_level
from .pipeline         import PipelineResult, Web3LegalPipeline

__all__ = [
    "Web3LegalPipeline",
    "PipelineResult",
    "BlockchainEvent",
    "LegalFinding",
    "LawReference",
    "KlerosPackage",
    "LegalMapping",
    "DisputeResult",
    "EventType",
    "RiskLevel",
    "get_applicable_laws",
    "highest_risk_level",
    "configure_logging",
    "get_logger",
]
