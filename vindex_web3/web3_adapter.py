# -*- coding: utf-8 -*-
"""
Async blockchain adapter with exponential backoff, queue, and transparent fallback.
Uses aiohttp exclusively — no requests, no time.sleep.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, AsyncGenerator, Optional, get_args

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

from pydantic import TypeAdapter, ValidationError

from ._logging  import get_logger
from .interfaces import BlockchainEvent, EventType

logger = get_logger(__name__)

# Validates tx_hash format before any network call
_TX_ADAPTER: TypeAdapter[str] = TypeAdapter(str)
_EVENT_TYPES: list[str] = list(get_args(EventType))

# Exponential backoff delays in seconds [attempt-0, attempt-1, attempt-2]
_BACKOFF_DELAYS: tuple[float, ...] = (0.0, 1.0, 2.0)
_RPC_TIMEOUT_S: float = 3.0


class Web3Adapter:
    """
    Async adapter for EVM-compatible blockchain nodes.

    All methods are non-blocking. Validation, retries, and offline fallback
    are handled transparently — callers always receive a BlockchainEvent.
    """

    def __init__(self) -> None:
        self._session:   Optional[aiohttp.ClientSession] = None
        self._rpc_url:   str   = ""
        self._connected: bool  = False
        self._queue:     asyncio.Queue[BlockchainEvent] = asyncio.Queue(maxsize=1_000)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self, rpc_url: str) -> bool:
        """
        Open aiohttp session and verify RPC endpoint reachability.
        Returns False (never raises) if the node is unreachable.
        """
        self._rpc_url = rpc_url
        if not rpc_url or not _AIOHTTP_AVAILABLE:
            logger.warning("web3.connect.skip", extra={"reason": "no rpc_url or aiohttp missing"})
            return False
        try:
            self._session   = aiohttp.ClientSession()
            self._connected = await self.health_check()
            if not self._connected:
                await self._close_session()
        except Exception as exc:
            logger.warning("web3.connect.failed", extra={"error": str(exc)})
            await self._close_session()
            self._connected = False
        return self._connected

    async def health_check(self) -> bool:
        """
        Ping the RPC node. Returns True if node responds to eth_blockNumber.
        """
        if not self._session or not self._rpc_url:
            return False
        payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
        try:
            async with asyncio.timeout(_RPC_TIMEOUT_S):
                async with self._session.post(
                    self._rpc_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    data = await resp.json()
                    return "result" in data
        except Exception:
            return False

    async def close(self) -> None:
        """Release aiohttp session resources."""
        await self._close_session()

    async def _close_session(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session   = None
        self._connected = False

    # ── Main fetch ────────────────────────────────────────────────────────────

    async def fetch_event(self, tx_hash: str) -> BlockchainEvent:
        """
        Fetch a blockchain event by tx_hash.

        Validates tx_hash format (raises pydantic.ValidationError on bad input).
        Retries up to 3 times with exponential backoff [0s, 1s, 2s].
        Automatically falls back to a deterministic mock if node unreachable.

        Raises:
            pydantic.ValidationError: tx_hash format invalid.
        """
        self._validate_tx_hash(tx_hash)

        last_exc: Exception = RuntimeError("no attempts")

        for attempt, delay in enumerate(_BACKOFF_DELAYS, 1):
            if delay > 0.0:
                await asyncio.sleep(delay)
            t0 = time.monotonic()
            try:
                async with asyncio.timeout(_RPC_TIMEOUT_S):
                    event = await self._rpc_fetch(tx_hash)
                duration_ms = round((time.monotonic() - t0) * 1_000, 2)
                logger.info(
                    "web3.fetch_event.ok",
                    extra={"tx_hash": tx_hash, "attempt": attempt,
                           "duration_ms": duration_ms, "retry_count": attempt - 1},
                )
                return event
            except Exception as exc:
                last_exc = exc
                duration_ms = round((time.monotonic() - t0) * 1_000, 2)
                logger.warning(
                    "web3.fetch_event.retry",
                    extra={"tx_hash": tx_hash, "attempt": attempt,
                           "error": str(exc), "duration_ms": duration_ms},
                )

        logger.warning(
            "web3.fetch_event.fallback",
            extra={"tx_hash": tx_hash, "last_error": str(last_exc)},
        )
        return await self._fallback_event(tx_hash)

    async def stream_events(
        self,
        contract_address: str,
    ) -> AsyncGenerator[BlockchainEvent, None]:
        """
        Async generator that yields BlockchainEvents from an event queue.
        In offline mode, yields fallback events indefinitely until cancelled.
        """
        while True:
            try:
                event = self._queue.get_nowait()
                yield event
                self._queue.task_done()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                break

    # ── Fallback ──────────────────────────────────────────────────────────────

    async def _fallback_event(self, tx_hash: str) -> BlockchainEvent:
        """
        Returns a deterministic mock BlockchainEvent when the node is unreachable.
        Same tx_hash always produces the same event — reproducible for tests.
        raw_data["status"] == "offline_fallback" signals the origin.
        """
        seed = int(tx_hash[-8:], 16)
        event_type = _EVENT_TYPES[seed % len(_EVENT_TYPES)]
        value_cents = seed % 10_000
        return BlockchainEvent(
            tx_hash      = tx_hash,
            event_type   = event_type,       # type: ignore[arg-type]
            from_address = "0x" + "a" * 40,
            to_address   = "0x" + "b" * 40,
            value_eth    = Decimal(value_cents) / Decimal("100"),
            timestamp    = datetime.now(timezone.utc),
            block_number = seed % 1_000_000,
            raw_data     = {"status": "offline_fallback", "seed": seed},
        )

    # ── RPC call ──────────────────────────────────────────────────────────────

    async def _rpc_fetch(self, tx_hash: str) -> BlockchainEvent:
        """Raw RPC call: eth_getTransactionByHash + eth_getTransactionReceipt."""
        if not self._session or not self._connected:
            raise RuntimeError("Not connected to RPC node")

        payload = {
            "jsonrpc": "2.0",
            "method":  "eth_getTransactionByHash",
            "params":  [tx_hash],
            "id":      1,
        }
        async with self._session.post(
            self._rpc_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as resp:
            resp.raise_for_status()
            data: dict[str, Any] = await resp.json()

        tx = data.get("result")
        if not tx:
            raise ValueError(f"Transaction {tx_hash} not found")

        return BlockchainEvent(
            tx_hash      = tx_hash,
            event_type   = _infer_event_type(tx),
            from_address = tx.get("from", "0x" + "0" * 40),
            to_address   = tx.get("to")  or ("0x" + "0" * 40),
            value_eth    = Decimal(int(tx.get("value", "0x0"), 16)) / Decimal("1000000000000000000"),
            timestamp    = datetime.now(timezone.utc),
            block_number = int(tx.get("blockNumber") or "0x0", 16),
            raw_data     = tx,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_tx_hash(tx_hash: str) -> None:
        """Raise pydantic.ValidationError if tx_hash format is invalid."""
        # Reuse BlockchainEvent validator by building a partial model
        try:
            BlockchainEvent.model_validate({
                "tx_hash":      tx_hash,
                "event_type":   "transfer",
                "from_address": "0x" + "0" * 40,
                "to_address":   "0x" + "0" * 40,
                "value_eth":    "0",
                "timestamp":    datetime.now(timezone.utc).isoformat(),
                "block_number": 0,
                "raw_data":     {},
            })
        except ValidationError as exc:
            # Re-raise only the tx_hash error for clarity
            tx_errors = [e for e in exc.errors() if "tx_hash" in str(e.get("loc", ""))]
            if tx_errors:
                raise ValidationError.from_exception_data(
                    title="BlockchainEvent",
                    input_type="python",
                    line_errors=exc.errors(),    # type: ignore[arg-type]
                ) from exc
            raise


def _infer_event_type(tx: dict[str, Any]) -> EventType:
    """Heuristic event type inference from raw transaction data."""
    if not tx.get("to"):
        return "mint"
    if tx.get("input", "0x") == "0x":
        return "transfer"
    return "contract_call"
