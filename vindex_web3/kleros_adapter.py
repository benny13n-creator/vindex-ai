# -*- coding: utf-8 -*-
"""
Kleros v2 adapter. Deterministic evidence packaging. Zero AI.
evidence_hash = SHA-256(sorted-key JSON of evidence dict).
metaevidence_uri is a simulated IPFS CID (SHA-256 of pipeline_id).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from ._logging  import get_logger
from .interfaces import KlerosPackage, LegalFinding

logger = get_logger(__name__)

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class KlerosAdapter:
    """
    Prepares and verifies Kleros v2 evidence packages.

    prepare_case() is deterministic — same LegalFinding always produces
    the same KlerosPackage (modulo created_at, which callers may freeze).
    """

    def prepare_case(self, finding: LegalFinding) -> KlerosPackage:
        evidence = {
            "pipeline_id":  finding.pipeline_id,
            "tx_hash":      finding.dokazi.tx_hash,
            "block_number": finding.dokazi.block_number,
            "timestamp":    finding.dokazi.timestamp.isoformat(),
            "value_eth":    str(finding.dokazi.vrednost_eth),
            "event_type":   finding.dokazi.event_type,
            "from_address": finding.dokazi.from_address,
            "to_address":   finding.dokazi.to_address,
            "pravni_osnov": {
                "zakon": finding.pravni_osnov.zakon,
                "clan":  finding.pravni_osnov.clan,
            },
        }
        evidence_hash    = _sha256_sorted(evidence)
        metaevidence_uri = _simulated_ipfs_cid(finding.pipeline_id)

        case_description = (
            f"{finding.upozorenje}\n\n"
            f"Pravna kategorija: {finding.pravni_osnov.pravna_kategorija}\n"
            f"Zakon: {finding.pravni_osnov.zakon}, član {finding.pravni_osnov.clan}\n"
            f"Opis: {finding.pravni_osnov.opis}\n\n"
            f"Akcija: {finding.akcija}"
        )[:2000]

        pkg = KlerosPackage(
            case_description  = case_description,
            evidence_hash     = evidence_hash,
            metaevidence_uri  = metaevidence_uri,
            pipeline_id       = finding.pipeline_id,
            finding_summary   = finding.upozorenje,
            parties           = {
                "from": finding.dokazi.from_address,
                "to":   finding.dokazi.to_address,
            },
            value_eth         = finding.dokazi.vrednost_eth,
            created_at        = datetime.now(timezone.utc),
        )

        logger.info(
            "kleros_adapter.package_prepared",
            extra={
                "pipeline_id":    finding.pipeline_id,
                "evidence_hash":  evidence_hash,
                "kleros_ready":   finding.kleros_ready,
            },
        )
        return pkg

    @staticmethod
    def verify_package(pkg: KlerosPackage) -> bool:
        """
        Structural verification (not cryptographic proof).
        Returns True if all required fields are well-formed.
        """
        checks = [
            bool(pkg.pipeline_id),
            bool(_SHA256_RE.match(pkg.evidence_hash)),
            pkg.metaevidence_uri.startswith("ipfs://"),
            bool(pkg.case_description),
            len(pkg.case_description) <= 2000,
            "from" in pkg.parties and "to" in pkg.parties,
        ]
        ok = all(checks)
        logger.info(
            "kleros_adapter.verify",
            extra={"pipeline_id": pkg.pipeline_id, "valid": ok},
        )
        return ok


def _sha256_sorted(obj: dict) -> str:
    """SHA-256 of sorted-key JSON, lowercase hex."""
    canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _simulated_ipfs_cid(pipeline_id: str) -> str:
    """Deterministic simulated IPFS CID: ipfs://Qm<sha256[:44]>."""
    digest = hashlib.sha256(pipeline_id.encode()).hexdigest()
    return f"ipfs://Qm{digest[:44]}"
