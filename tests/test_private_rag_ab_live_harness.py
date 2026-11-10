"""Offline safety checks for the opt-in live Pinecone A/B harness.

These tests validate the harness gates and recovery manifest only. They are
not represented as live Pinecone/Auth isolation evidence.
"""
from __future__ import annotations

import json
import ast
from pathlib import Path
import subprocess

import pytest

from scripts import private_rag_ab_live as harness


def test_default_preflight_is_read_only_and_names_missing_credentials(monkeypatch):
    for name in harness.REQUIRED_ENV + (
        "VINDEX_PRIVATE_RAG_AB_APPROVAL", "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    plan = harness._preflight(require_credentials=False)
    assert plan["writes"] == 0
    assert plan["openai_chat_completions"] == 0
    assert plan["missing"] == list(harness.REQUIRED_ENV)
    assert plan["max_vectors"] == 6
    assert plan["max_queries"] == 16


def test_preflight_rejects_wrong_supabase_project_and_index(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://unrelated.supabase.co")
    with pytest.raises(RuntimeError, match="not the pre-approved project"):
        harness._preflight(require_credentials=False)
    monkeypatch.setenv("SUPABASE_URL", f"https://{harness.EXPECTED_PROJECT_REF}.supabase.co")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "another-index")
    with pytest.raises(RuntimeError, match="not the expected existing index"):
        harness._preflight(require_credentials=False)


def test_manifest_has_bounded_synthetic_scope_and_unique_exact_cleanup_ids():
    one, two = harness._new_manifest(), harness._new_manifest()
    assert one["run_id"] != two["run_id"]
    assert len(one["users"]) == 4
    assert len(one["matters"]) == 3
    assert len(one["vectors"]) <= harness.VECTOR_LIMIT == 6
    assert all("@example.invalid" in u["email"] for u in one["users"].values())
    assert len({v["id"] for v in one["vectors"]}) == len(one["vectors"])
    assert all(v["id"].startswith(f"vindex-ab-{one['run_id']}-") for v in one["vectors"])
    assert all(v["namespace"].startswith(("kancelarija_", "user_", "tmp_")) for v in one["vectors"])
    assert json.loads(json.dumps(one))["cleanup"]["verified"] is False


def test_live_execute_refuses_missing_credentials_before_any_manifest_or_provider_access(monkeypatch, capsys):
    for name in harness.REQUIRED_ENV + ("VINDEX_PRIVATE_RAG_AB_APPROVAL",):
        monkeypatch.delenv(name, raising=False)
    manifest = Path(__file__).with_name("must-not-exist-private-rag-ab.json")
    assert not manifest.exists()
    current = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, cwd=harness.REPO_ROOT).stdout.strip()
    assert harness.main(["--execute", "--expected-sha", current, "--manifest", str(manifest)]) == 2
    assert not manifest.exists()
    output = capsys.readouterr().err
    assert "SUPABASE_URL" in output
    assert "PINECONE_API_KEY" in output
    assert "Recovery manifest" not in output


def test_cleanup_implementation_never_uses_broad_delete_and_targets_exact_ids():
    import inspect

    source = inspect.getsource(harness._clean)
    parsed = ast.parse(source)
    assert not any(isinstance(n, ast.Attribute) and n.attr == "delete_all" for n in ast.walk(parsed))
    assert '.eq("id", row_id)' in source
    assert "index.delete(ids=ids, namespace=ns)" in source
    assert "index.fetch(ids=ids, namespace=ns)" in source


def test_cleanup_rejects_modified_manifest_before_touching_any_adapter():
    manifest = harness._new_manifest()
    manifest["vectors"][0]["id"] = "unrelated-client-vector"

    class _MustNotBeCalled:
        def __getattr__(self, name):
            raise AssertionError(f"cleanup adapter touched before manifest validation: {name}")

    with pytest.raises(RuntimeError, match="vector IDs/namespaces"):
        harness._clean(_MustNotBeCalled(), _MustNotBeCalled(), Path("unused.json"), manifest)


def test_source_pin_matches_pinned_candidate_and_both_question_variants():
    harness._require_source_pin()

