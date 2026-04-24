# -*- coding: utf-8 -*-
"""Full test suite for vindex_web3 pipeline."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from vindex_web3.dispute_detector import DisputeDetector, _DedupStore
from vindex_web3.interfaces        import BlockchainEvent, LawReference, LegalFinding
from vindex_web3.kleros_adapter    import KlerosAdapter, _sha256_sorted, _simulated_ipfs_cid
from vindex_web3.law_registry      import (
    get_applicable_laws, highest_risk_level, get_law_by_key, _REGISTRY, _EVENT_LAW_MAP,
)
from vindex_web3.legal_formatter   import LegalFormatter, _sha256_id
from vindex_web3.legal_mapper      import LegalMapper, MAPPING_TABLE, ZDI_TABLE, ZSPNFT_TABLE, ZPDG_TABLE
from vindex_web3.pipeline          import Web3LegalPipeline
from vindex_web3.web3_adapter      import Web3Adapter


# ── interfaces ────────────────────────────────────────────────────────────────

class TestBlockchainEvent:
    def test_valid(self, transfer_event):
        assert transfer_event.tx_hash.startswith("0x")

    def test_tx_hash_lowercased(self, transfer_event):
        assert transfer_event.tx_hash == transfer_event.tx_hash.lower()

    def test_invalid_tx_hash(self):
        with pytest.raises(ValidationError):
            BlockchainEvent(
                tx_hash="not_valid", event_type="transfer",
                from_address="0x" + "0" * 40, to_address="0x" + "0" * 40,
                value_eth=Decimal("0"), timestamp=datetime.now(timezone.utc),
                block_number=0, raw_data={},
            )

    def test_negative_value_rejected(self):
        with pytest.raises(ValidationError):
            BlockchainEvent(
                tx_hash="0x" + "a" * 64, event_type="transfer",
                from_address="0x" + "0" * 40, to_address="0x" + "0" * 40,
                value_eth=Decimal("-1"), timestamp=datetime.now(timezone.utc),
                block_number=0, raw_data={},
            )

    def test_negative_block_rejected(self):
        with pytest.raises(ValidationError):
            BlockchainEvent(
                tx_hash="0x" + "a" * 64, event_type="transfer",
                from_address="0x" + "0" * 40, to_address="0x" + "0" * 40,
                value_eth=Decimal("0"), timestamp=datetime.now(timezone.utc),
                block_number=-1, raw_data={},
            )


# ── legal_mapper ──────────────────────────────────────────────────────────────

class TestLegalMapper:
    def test_all_event_types_mapped(self):
        mapper = LegalMapper()
        for event_type in MAPPING_TABLE:
            event = BlockchainEvent(
                tx_hash      = "0x" + "f" * 64,
                event_type   = event_type,   # type: ignore[arg-type]
                from_address = "0x" + "0" * 40,
                to_address   = "0x" + "0" * 40,
                value_eth    = Decimal("0"),
                timestamp    = datetime.now(timezone.utc),
                block_number = 0,
                raw_data     = {},
            )
            result = mapper.map(event)
            assert result.zakon == "ZOO"
            assert result.clan > 0

    def test_transfer_maps_to_clan_262(self, transfer_event):
        mapper = LegalMapper()
        result = mapper.map(transfer_event)
        assert result.clan == 262

    def test_contract_call_maps_to_clan_124(self, contract_call_stale):
        mapper = LegalMapper()
        result = mapper.map(contract_call_stale)
        assert result.clan == 124


# ── dispute_detector ─────────────────────────────────────────────────────────

class TestDisputeDetector:
    def test_no_dispute_for_normal_transfer(self, transfer_event):
        detector = DisputeDetector()
        result   = detector.detect(transfer_event)
        assert result.dispute is False
        assert result.type == "no_dispute"
        assert result.confidence == 1.0

    def test_payment_failed_high_value(self, payment_failed_high):
        detector = DisputeDetector()
        result   = detector.detect(payment_failed_high)
        assert result.dispute is True
        assert result.type == "breach_of_contract"
        assert abs(result.confidence - 0.92) < 1e-9

    def test_zero_value_transfer(self, zero_transfer):
        detector = DisputeDetector()
        result   = detector.detect(zero_transfer)
        assert result.dispute is True
        assert result.type == "unauthorized_transfer"
        assert abs(result.confidence - 0.85) < 1e-9

    def test_stale_contract_call(self, contract_call_stale):
        detector = DisputeDetector()
        result   = detector.detect(contract_call_stale)
        assert result.dispute is True
        assert result.type == "contract_violation"
        assert abs(result.confidence - 0.78) < 1e-9

    def test_duplicate_detected(self, transfer_event):
        detector = DisputeDetector()
        first    = detector.detect(transfer_event)
        second   = detector.detect(transfer_event)
        assert first.dispute  is False
        assert second.dispute is True
        assert second.type    == "unauthorized_transfer"
        assert abs(second.confidence - 0.95) < 1e-9

    def test_dedup_evidence_refs_contain_tx_hash(self, transfer_event):
        detector = DisputeDetector()
        detector.detect(transfer_event)
        dup = detector.detect(transfer_event)
        assert any(transfer_event.tx_hash in ref for ref in dup.evidence_refs)


# ── legal_formatter ───────────────────────────────────────────────────────────

class TestLegalFormatter:
    def test_pipeline_id_is_sha256(self, transfer_event):
        from vindex_web3.legal_mapper     import LegalMapper
        from vindex_web3.dispute_detector import DisputeDetector

        formatter = LegalFormatter()
        mapping   = LegalMapper().map(transfer_event)
        dispute   = DisputeDetector().detect(transfer_event)
        finding   = formatter.format(transfer_event, mapping, dispute)

        raw = transfer_event.tx_hash + finding.timestamp.isoformat()
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert finding.pipeline_id == expected

    def test_kleros_ready_false_for_no_dispute(self, transfer_event):
        from vindex_web3.legal_mapper     import LegalMapper
        from vindex_web3.dispute_detector import DisputeDetector

        formatter = LegalFormatter()
        mapping   = LegalMapper().map(transfer_event)
        dispute   = DisputeDetector().detect(transfer_event)
        finding   = formatter.format(transfer_event, mapping, dispute)
        assert finding.kleros_ready is False

    def test_kleros_ready_true_for_high_value_dispute(self, payment_failed_high):
        from vindex_web3.legal_mapper     import LegalMapper
        from vindex_web3.dispute_detector import DisputeDetector

        formatter = LegalFormatter()
        mapping   = LegalMapper().map(payment_failed_high)
        dispute   = DisputeDetector().detect(payment_failed_high)
        finding   = formatter.format(payment_failed_high, mapping, dispute)
        assert finding.kleros_ready is True

    def test_to_json_is_sorted_keys(self, transfer_event):
        from vindex_web3.legal_mapper     import LegalMapper
        from vindex_web3.dispute_detector import DisputeDetector

        formatter = LegalFormatter()
        mapping   = LegalMapper().map(transfer_event)
        dispute   = DisputeDetector().detect(transfer_event)
        finding   = formatter.format(transfer_event, mapping, dispute)
        raw       = LegalFormatter.to_json(finding)
        parsed    = json.loads(raw)
        keys      = list(parsed.keys())
        assert keys == sorted(keys)


# ── kleros_adapter ────────────────────────────────────────────────────────────

class TestKlerosAdapter:
    def _make_finding(self, event: BlockchainEvent) -> LegalFinding:
        from vindex_web3.legal_mapper     import LegalMapper
        from vindex_web3.dispute_detector import DisputeDetector

        mapper    = LegalMapper()
        detector  = DisputeDetector()
        formatter = LegalFormatter()
        return formatter.format(event, mapper.map(event), detector.detect(event))

    def test_prepare_case_valid(self, payment_failed_high):
        adapter = KlerosAdapter()
        finding = self._make_finding(payment_failed_high)
        pkg     = adapter.prepare_case(finding)
        assert pkg.metaevidence_uri.startswith("ipfs://")
        assert len(pkg.evidence_hash) == 64
        assert len(pkg.case_description) <= 2000

    def test_verify_package_true(self, payment_failed_high):
        adapter = KlerosAdapter()
        finding = self._make_finding(payment_failed_high)
        pkg     = adapter.prepare_case(finding)
        assert adapter.verify_package(pkg) is True

    def test_evidence_hash_is_deterministic(self, payment_failed_high):
        adapter  = KlerosAdapter()
        finding  = self._make_finding(payment_failed_high)
        pkg1     = adapter.prepare_case(finding)
        pkg2     = adapter.prepare_case(finding)
        assert pkg1.evidence_hash == pkg2.evidence_hash

    def test_ipfs_uri_format(self):
        uri = _simulated_ipfs_cid("some_pipeline_id")
        assert uri.startswith("ipfs://Qm")
        assert len(uri) > 10


# ── web3_adapter ──────────────────────────────────────────────────────────────

class TestWeb3Adapter:
    @pytest.mark.asyncio
    async def test_fallback_on_no_connection(self):
        adapter = Web3Adapter()
        tx_hash = "0x" + "a" * 62 + "01"
        event   = await adapter.fetch_event(tx_hash)
        assert event.raw_data.get("status") == "offline_fallback"

    @pytest.mark.asyncio
    async def test_invalid_tx_hash_raises(self):
        adapter = Web3Adapter()
        with pytest.raises(Exception):
            await adapter.fetch_event("bad_hash")

    @pytest.mark.asyncio
    async def test_fallback_is_deterministic(self):
        adapter = Web3Adapter()
        tx      = "0x" + "b" * 62 + "22"
        e1      = await adapter.fetch_event(tx)
        e2      = await adapter.fetch_event(tx)
        assert e1.event_type   == e2.event_type
        assert e1.block_number == e2.block_number

    @pytest.mark.asyncio
    async def test_connect_returns_false_without_url(self):
        adapter = Web3Adapter()
        result  = await adapter.connect("")
        assert result is False


# ── pipeline ──────────────────────────────────────────────────────────────────

class TestPipeline:
    @pytest.mark.asyncio
    async def test_process_returns_result(self):
        pipeline = Web3LegalPipeline()
        result   = await pipeline.process("0x" + "c" * 62 + "33")
        assert result.finding.pipeline_id
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_process_invalid_hash_raises(self):
        pipeline = Web3LegalPipeline()
        with pytest.raises(Exception):
            await pipeline.process("invalid")

    @pytest.mark.asyncio
    async def test_batch_returns_all_results(self):
        pipeline  = Web3LegalPipeline()
        tx_hashes = [f"0x{'d' * 62}{i:02x}" for i in range(10)]
        results   = await pipeline.process_batch(tx_hashes)
        assert len(results) == 10
        assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_batch_partial_failure_returns_none(self):
        pipeline = Web3LegalPipeline()
        hashes   = ["0x" + "e" * 62 + "01", "bad_hash", "0x" + "e" * 62 + "02"]
        results  = await pipeline.process_batch(hashes)
        assert results[0] is not None
        assert results[1] is None
        assert results[2] is not None

    @pytest.mark.asyncio
    async def test_kleros_package_attached_when_ready(self):
        from vindex_web3.interfaces import BlockchainEvent
        from decimal import Decimal

        pipeline = Web3LegalPipeline()

        # Force a dispute by injecting an event — use a patched adapter
        class _MockAdapter:
            async def fetch_event(self, tx_hash: str) -> BlockchainEvent:
                return BlockchainEvent(
                    tx_hash      = tx_hash,
                    event_type   = "payment_failed",
                    from_address = "0x" + "1" * 40,
                    to_address   = "0x" + "2" * 40,
                    value_eth    = Decimal("1.0"),
                    timestamp    = datetime.now(timezone.utc),
                    block_number = 1,
                    raw_data     = {},
                )

        pipeline._adapter = _MockAdapter()
        result = await pipeline.process("0x" + "f" * 62 + "99")
        assert result.kleros_package is not None


# ── law_registry (Faza 1) ─────────────────────────────────────────────────────

class TestLawRegistry:
    def test_all_registry_keys_have_valid_risk_levels(self):
        valid = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        for key, ref in _REGISTRY.items():
            assert ref.compliance_risk_level in valid, f"{key} ima nevazeci risk_level"

    def test_all_event_types_in_event_law_map(self):
        from typing import get_args
        from vindex_web3.interfaces import EventType
        for et in get_args(EventType):
            assert et in _EVENT_LAW_MAP, f"{et} nije u _EVENT_LAW_MAP"

    def test_get_applicable_laws_transfer(self):
        laws = get_applicable_laws("transfer")
        codes = {l.law_code for l in laws}
        assert "ZOO"    in codes
        assert "ZDI"    in codes
        assert "ZSPNFT" in codes
        assert "ZPDG"   in codes

    def test_get_applicable_laws_mint(self):
        laws = get_applicable_laws("mint")
        codes = {l.law_code for l in laws}
        assert "ZOO"  in codes
        assert "ZDI"  in codes
        assert "ZPDG" in codes

    def test_get_applicable_laws_unknown_returns_empty(self):
        assert get_applicable_laws("nepostoji") == []

    def test_highest_risk_payment_failed_is_critical(self):
        laws = get_applicable_laws("payment_failed")
        level = highest_risk_level(laws)
        assert level == "CRITICAL"

    def test_highest_risk_empty_list_is_low(self):
        assert highest_risk_level([]) == "LOW"

    def test_highest_risk_approval_is_medium(self):
        laws = get_applicable_laws("approval")
        level = highest_risk_level(laws)
        assert level == "MEDIUM"

    def test_get_law_by_key_zspnft_47(self):
        ref = get_law_by_key("ZSPNFT_47")
        assert ref is not None
        assert ref.compliance_risk_level == "CRITICAL"
        assert ref.article_number == "47"

    def test_get_law_by_key_missing_returns_none(self):
        assert get_law_by_key("NEPOSTOJI_999") is None

    def test_law_reference_is_pydantic_model(self):
        ref = get_law_by_key("ZOO_262")
        assert isinstance(ref, LawReference)
        d = ref.model_dump()
        assert "law_code" in d
        assert "compliance_risk_level" in d


# ── legal_mapper proširenje (Faza 1) ─────────────────────────────────────────

class TestLegalMapperExtended:
    def test_zdi_table_covers_transfer(self):
        assert "transfer" in ZDI_TABLE
        assert ZDI_TABLE["transfer"].zakon == "ZDI"

    def test_zdi_table_mint_maps_to_clan_9(self):
        assert ZDI_TABLE["mint"].clan == 9

    def test_zspnft_table_payment_failed_maps_to_clan_47(self):
        assert "payment_failed" in ZSPNFT_TABLE
        assert ZSPNFT_TABLE["payment_failed"].clan == 47

    def test_zpdg_table_mint_is_tax_article(self):
        assert "mint" in ZPDG_TABLE
        assert ZPDG_TABLE["mint"].zakon == "ZPDG"

    def test_map_all_laws_transfer_returns_multiple(self, transfer_event):
        mapper = LegalMapper()
        all_laws = mapper.map_all_laws(transfer_event)
        law_codes = {m.zakon for m in all_laws}
        assert "ZOO" in law_codes
        assert "ZDI" in law_codes
        assert "ZSPNFT" in law_codes

    def test_map_all_laws_burn_returns_zoo_zdi_zpdg(self, mint_event):
        from vindex_web3.tests.conftest import _make_event
        burn_event = _make_event(
            tx_hash    = "0x" + "f" * 62 + "bb",
            event_type = "burn",
        )
        mapper   = LegalMapper()
        all_laws = mapper.map_all_laws(burn_event)
        codes    = {m.zakon for m in all_laws}
        assert "ZOO"  in codes
        assert "ZDI"  in codes
        assert "ZPDG" in codes

    def test_map_returns_primary_zoo_only(self, transfer_event):
        mapper  = LegalMapper()
        primary = mapper.map(transfer_event)
        assert primary.zakon == "ZOO"


# ── legal_formatter novi polja (Faza 1) ───────────────────────────────────────

class TestLegalFormatterFaza1:
    def _finding(self, event):
        mapper    = LegalMapper()
        detector  = DisputeDetector()
        formatter = LegalFormatter()
        return formatter.format(event, mapper.map(event), detector.detect(event))

    def test_applicable_laws_populated(self, transfer_event):
        finding = self._finding(transfer_event)
        assert len(finding.applicable_laws) > 0

    def test_primary_law_is_zoo(self, transfer_event):
        finding = self._finding(transfer_event)
        assert finding.primary_law == "ZOO"

    def test_risk_level_payment_failed_is_critical(self, payment_failed_high):
        finding = self._finding(payment_failed_high)
        assert finding.risk_level == "CRITICAL"

    def test_risk_level_approval_is_medium(self):
        from vindex_web3.tests.conftest import _make_event
        event   = _make_event(
            tx_hash    = "0x" + "a" * 62 + "cc",
            event_type = "approval",
        )
        finding = self._finding(event)
        assert finding.risk_level == "MEDIUM"

    def test_to_json_includes_applicable_laws(self, transfer_event):
        finding = self._finding(transfer_event)
        raw     = LegalFormatter.to_json(finding)
        parsed  = json.loads(raw)
        assert "applicable_laws" in parsed
        assert isinstance(parsed["applicable_laws"], list)
        assert len(parsed["applicable_laws"]) > 0

    def test_to_json_includes_risk_level(self, transfer_event):
        finding = self._finding(transfer_event)
        raw     = LegalFormatter.to_json(finding)
        parsed  = json.loads(raw)
        assert "risk_level" in parsed
        assert parsed["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
