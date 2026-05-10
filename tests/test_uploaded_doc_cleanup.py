# -*- coding: utf-8 -*-
"""Tests for uploaded_doc.cleanup — mocked Pinecone."""

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from uploaded_doc.cleanup import cleanup_expired


def _future_iso(hours: int = 24) -> str:
    dt = datetime.now(tz=timezone.utc) + timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _past_iso(hours: int = 25) -> str:
    dt = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_index_mock(namespaces: dict, query_responses: dict) -> MagicMock:
    """Build a mock Pinecone index.

    namespaces: {ns_name: vector_count}
    query_responses: {ns_name: expires_at_iso or None (empty)}
    """
    mock_index = MagicMock()
    mock_index.describe_index_stats.return_value = {
        "namespaces": {
            ns: {"vector_count": count}
            for ns, count in namespaces.items()
        }
    }

    def _query(vector, top_k, namespace, include_metadata):
        exp = query_responses.get(namespace)
        if exp is None:
            return {"matches": []}
        return {
            "matches": [{"metadata": {"expires_at": exp}}]
        }

    mock_index.query.side_effect = _query
    return mock_index


# ─── Test 13: dry_run does not call delete ───────────────────────────────────

def test_cleanup_dry_run_doesnt_delete():
    mock_index = _make_index_mock(
        namespaces={"tmp_abc": 5, "tmp_xyz": 3},
        query_responses={"tmp_abc": _past_iso(), "tmp_xyz": _past_iso()},
    )

    with patch("uploaded_doc.cleanup._get_pinecone_index", return_value=mock_index):
        result = cleanup_expired(dry_run=True)

    mock_index.delete.assert_not_called()
    assert result["namespaces_deleted"] == 2
    assert result["chunks_deleted"] == 8
    assert result["namespaces_inspected"] == 2


# ─── Test 14: deletes only expired namespaces ────────────────────────────────

def test_cleanup_deletes_only_expired_ns():
    mock_index = _make_index_mock(
        namespaces={"tmp_expired1": 4, "tmp_expired2": 6, "tmp_live": 3},
        query_responses={
            "tmp_expired1": _past_iso(26),
            "tmp_expired2": _past_iso(2),
            "tmp_live": _future_iso(22),
        },
    )

    with patch("uploaded_doc.cleanup._get_pinecone_index", return_value=mock_index):
        result = cleanup_expired(dry_run=False)

    assert result["namespaces_deleted"] == 2
    assert result["chunks_deleted"] == 10
    assert result["namespaces_inspected"] == 3

    deleted_namespaces = [
        c.kwargs.get("namespace") or c.args[-1]
        for c in mock_index.delete.call_args_list
    ]
    assert "tmp_expired1" in deleted_namespaces
    assert "tmp_expired2" in deleted_namespaces
    assert "tmp_live" not in deleted_namespaces


# ─── Test 15: skips non-tmp namespaces ──────────────────────────────────────

def test_cleanup_skips_non_tmp_ns():
    mock_index = _make_index_mock(
        namespaces={
            "__default__": 17688,
            "sudska_praksa": 1479,
            "tmp_old": 7,
        },
        query_responses={"tmp_old": _past_iso()},
    )

    with patch("uploaded_doc.cleanup._get_pinecone_index", return_value=mock_index):
        result = cleanup_expired(dry_run=False)

    assert result["namespaces_inspected"] == 1
    assert result["namespaces_deleted"] == 1
    assert result["chunks_deleted"] == 7

    # Ensure production namespaces never touched
    for c in mock_index.delete.call_args_list:
        ns = c.kwargs.get("namespace", "")
        assert ns.startswith("tmp_"), f"Non-tmp namespace deleted: {ns}"


# ─── Test 16: no tmp namespaces ─────────────────────────────────────────────

def test_cleanup_handles_no_tmp_namespaces():
    mock_index = _make_index_mock(
        namespaces={"__default__": 17688, "sudska_praksa": 1479},
        query_responses={},
    )

    with patch("uploaded_doc.cleanup._get_pinecone_index", return_value=mock_index):
        result = cleanup_expired(dry_run=False)

    assert result["namespaces_inspected"] == 0
    assert result["namespaces_deleted"] == 0
    assert result["chunks_deleted"] == 0
    mock_index.delete.assert_not_called()
