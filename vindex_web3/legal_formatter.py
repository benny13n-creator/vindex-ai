# -*- coding: utf-8 -*-
"""
Deterministic LegalFinding formatter. SHA-256 pipeline_id. Zero AI.
Output is always sorted-key JSON (UTF-8, ensure_ascii=False).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from ._logging    import get_logger
from .interfaces  import (
    BlockchainEvent, DisputeResult, Dokazi, LegalFinding,
    LegalMapping, PravniOsnov,
)
from .law_registry import get_applicable_laws, highest_risk_level

logger = get_logger(__name__)

_DISPUTE_AKCIJA: dict[str, str] = {
    "breach_of_contract":    "Podnesite tuzbu za naknadu stete (cl. 262 ZOO). Prilozite dokaze o transakciji.",
    "non_payment":           "Pokrenite postupak prinudne naplate. Obratite se notaru ili sudu.",
    "unauthorized_transfer": "Odmah prijavite nadleznom sudu i kriptoberzama. Zahtevajte privremenu meru.",
    "contract_violation":    "Raskinite ugovor i zahtevajte naknadu stete prema cl. 124 ZOO.",
    "no_dispute":            "Nema osnova za spor. Transakcija je regularna.",
}

_DISPUTE_UPOZORENJE: dict[str, str] = {
    "breach_of_contract":    "UPOZORENJE: Detektovano krsenje ugovorne obaveze.",
    "non_payment":           "UPOZORENJE: Evidentirana neizvrsena novcana obaveza.",
    "unauthorized_transfer": "UPOZORENJE: Sumnja na neovlasceni prenos digitalne imovine.",
    "contract_violation":    "UPOZORENJE: Krsenje odredbi pametnog ugovora.",
    "no_dispute":            "INFO: Transakcija bez pravnih nepravilnosti.",
}


class LegalFormatter:
    """
    Produces a deterministic LegalFinding from event + mapping + dispute.
    pipeline_id = SHA-256(tx_hash + timestamp.isoformat()) — never random.
    Faza 1: applicable_laws, primary_law i risk_level se automatski popunjavaju.
    """

    def format(
        self,
        event:   BlockchainEvent,
        mapping: LegalMapping,
        dispute: DisputeResult,
    ) -> LegalFinding:
        now         = datetime.now(timezone.utc)
        pipeline_id = _sha256_id(event.tx_hash, now)

        applicable  = get_applicable_laws(event.event_type)
        risk_level  = highest_risk_level(applicable)

        finding = LegalFinding(
            upozorenje   = _DISPUTE_UPOZORENJE.get(
                dispute.type, "UPOZORENJE: Nepoznat status."
            ),
            pravni_osnov = PravniOsnov(
                zakon             = mapping.zakon,
                clan              = mapping.clan,
                opis              = mapping.opis,
                pravna_kategorija = mapping.pravna_kategorija,
            ),
            akcija       = _DISPUTE_AKCIJA.get(
                dispute.type, "Konsultujte pravnog savetnika."
            ),
            dokazi       = Dokazi(
                tx_hash      = event.tx_hash,
                block_number = event.block_number,
                timestamp    = event.timestamp,
                vrednost_eth = event.value_eth,
                event_type   = event.event_type,
                from_address = event.from_address,
                to_address   = event.to_address,
            ),
            kleros_ready    = dispute.dispute and dispute.confidence >= 0.80,
            timestamp       = now,
            pipeline_id     = pipeline_id,
            applicable_laws = applicable,
            primary_law     = mapping.zakon,
            risk_level      = risk_level,
        )

        logger.info(
            "legal_formatter.finding_created",
            extra={
                "pipeline_id":   pipeline_id,
                "dispute":       dispute.dispute,
                "dispute_type":  dispute.type,
                "kleros_ready":  finding.kleros_ready,
                "risk_level":    risk_level,
                "laws_count":    len(applicable),
                "tx_hash":       event.tx_hash,
            },
        )
        return finding

    @staticmethod
    def to_json(finding: LegalFinding) -> str:
        """Serialize to sorted-key JSON, UTF-8, ensure_ascii=False."""
        return json.dumps(
            json.loads(finding.model_dump_json()),
            sort_keys    = True,
            ensure_ascii = False,
        )


def _sha256_id(tx_hash: str, ts: datetime) -> str:
    raw = tx_hash + ts.isoformat()
    return hashlib.sha256(raw.encode()).hexdigest()
