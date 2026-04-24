# -*- coding: utf-8 -*-
"""JSON structured logging for vindex_web3. All modules import from here."""
from __future__ import annotations

import json
import logging
from typing import Any


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    _SKIP: frozenset[str] = frozenset({
        "args", "exc_info", "exc_text", "filename", "funcName", "levelno",
        "lineno", "module", "msecs", "msg", "name", "pathname", "process",
        "processName", "relativeCreated", "stack_info", "thread", "threadName",
        "taskName", "created",
    })

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts":     self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":  record.levelname,
            "logger": record.name,
            "msg":    record.getMessage(),
        }
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        for key, val in record.__dict__.items():
            if key not in self._SKIP and not key.startswith("_"):
                data[key] = val
        return json.dumps(data, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logger with JSON output. Call once at startup."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (JSON-formatted when configure_logging() was called)."""
    return logging.getLogger(name)
