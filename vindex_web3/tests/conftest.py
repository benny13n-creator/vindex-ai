# -*- coding: utf-8 -*-
"""Pytest fixtures shared across vindex_web3 test modules."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from vindex_web3.interfaces import BlockchainEvent

_BASE_TX = "0x" + "a" * 62 + "01"


def _make_event(**overrides) -> BlockchainEvent:
    defaults = dict(
        tx_hash      = _BASE_TX,
        event_type   = "transfer",
        from_address = "0x" + "1" * 40,
        to_address   = "0x" + "2" * 40,
        value_eth    = Decimal("1.0"),
        timestamp    = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        block_number = 1_000_000,
        raw_data     = {},
    )
    defaults.update(overrides)
    return BlockchainEvent(**defaults)


@pytest.fixture
def transfer_event() -> BlockchainEvent:
    return _make_event()


@pytest.fixture
def payment_failed_high() -> BlockchainEvent:
    return _make_event(
        tx_hash    = "0x" + "b" * 62 + "02",
        event_type = "payment_failed",
        value_eth  = Decimal("0.5"),
    )


@pytest.fixture
def zero_transfer() -> BlockchainEvent:
    return _make_event(
        tx_hash    = "0x" + "c" * 62 + "03",
        event_type = "transfer",
        value_eth  = Decimal("0"),
    )


@pytest.fixture
def contract_call_stale() -> BlockchainEvent:
    return _make_event(
        tx_hash    = "0x" + "d" * 62 + "04",
        event_type = "contract_call",
        timestamp  = datetime(2020, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def mint_event() -> BlockchainEvent:
    return _make_event(
        tx_hash    = "0x" + "e" * 62 + "05",
        event_type = "mint",
        value_eth  = Decimal("0"),
    )
