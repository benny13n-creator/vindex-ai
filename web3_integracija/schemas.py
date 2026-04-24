# -*- coding: utf-8 -*-
"""
Striktno definisane šeme podataka za Web3→Legal Engine komunikaciju.
Sve klase su serijalizabilne u JSON (ensure_ascii=False → srpski charset).
"""
from __future__ import annotations

import json
import time
import uuid
import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class LegalContext:
    law:          str = "ZOO"
    article:      str = ""    # "262" | "154" | "124"
    breach_type:  str = ""    # human-readable naziv kršenja


@dataclass
class BlockchainData:
    tx_hash:  str   = ""
    amount:   float = 0.0    # u ETH
    status:   str   = ""     # status_uplate | status_dobra | rok_isporuke


@dataclass
class Web3LegalEvent:
    """
    Jedini autorizovani format za komunikaciju između Web3 adaptera i Legal Engine-a.

    Polje 'instruction' sadrži prompt spreman za /api/pitanje.
    Ceo objekat se serijalizuje u JSON i šalje kao vrednost polja "pitanje".
    Legal Engine (GPT-4o) prima JSON string i parsira ga kao strukturirani input.
    """
    source:          str          = "web3_adapter"
    event_id:        str          = field(default_factory=lambda: str(uuid.uuid4()))
    legal_context:   LegalContext = field(default_factory=LegalContext)
    blockchain_data: BlockchainData = field(default_factory=BlockchainData)
    instruction:     str          = ""
    timestamp_iso:   str          = field(
        default_factory=lambda: datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    )
    # Interna polja — ne izvoze se u javni JSON
    _enqueue_ts:  float = field(default_factory=time.monotonic, repr=False, compare=False)
    _retry_count: int   = field(default=0, repr=False, compare=False)

    def to_dict(self) -> dict:
        """Vraća čisti Python rečnik bez internih polja."""
        return {
            "source":          self.source,
            "event_id":        self.event_id,
            "legal_context":   asdict(self.legal_context),
            "blockchain_data": asdict(self.blockchain_data),
            "instruction":     self.instruction,
            "timestamp_iso":   self.timestamp_iso,
        }

    def to_json(self, indent: int = 2) -> str:
        """UTF-8 serializacija — srpski karakteri ostaju čitljivi."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_prompt(self) -> str:
        """
        Konvertuje event u tekstualni prompt kompatibilan sa /api/pitanje.
        Legal Engine prima: { "pitanje": event.to_prompt() }
        """
        return (
            f"{self.instruction}\n\n"
            f"=== STRUKTURIRANI KONTEKST (Web3 adapter) ===\n"
            f"{self.to_json()}"
        )

    def age_seconds(self) -> float:
        """Koliko sekundi event čeka u sistemu od kreiranja."""
        return time.monotonic() - self._enqueue_ts


def event_iz_krsenja(
    tx_hash:       str,
    amount_eth:    float,
    tx_status:     str,
    article:       str,
    breach_type:   str,
    law:           str = "ZOO",
) -> Web3LegalEvent:
    """Fabrika — kreira popunjen Web3LegalEvent iz podataka o kršenju."""
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"vindex:{tx_hash}:{article}"))
    instruction = (
        f"Sistemsko upozorenje: Detektovano kršenje blockchain transakcije {tx_hash}. "
        f"Pravilo: Primeni {law} Član {article} ({breach_type}). "
        f"Akcija: Generiši pravni podnesak."
    )
    return Web3LegalEvent(
        event_id        = event_id,
        legal_context   = LegalContext(law=law, article=article, breach_type=breach_type),
        blockchain_data = BlockchainData(tx_hash=tx_hash, amount=amount_eth, status=tx_status),
        instruction     = instruction,
    )
