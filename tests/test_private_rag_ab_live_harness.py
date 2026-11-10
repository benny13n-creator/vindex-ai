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


def test_cache_source_guard_accepts_none_and_bare_early_returns_but_not_missing_guard():
    tree = ast.parse("""
def _cache_get():
    if _autentifikovan_privatni_rag_kontekst():
        return None
    return cached

def _cache_set():
    if _autentifikovan_privatni_rag_kontekst():
        return
    persist()

def _unsafe_cache_get():
    if _autentifikovan_privatni_rag_kontekst():
        audit_only()
    return cached
""")
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert harness._has_authenticated_cache_bypass(functions["_cache_get"])
    assert harness._has_authenticated_cache_bypass(functions["_cache_set"])
    assert not harness._has_authenticated_cache_bypass(functions["_unsafe_cache_get"])


def test_source_pin_matches_pinned_candidate_and_both_question_variants():
    harness._require_source_pin()


def test_git_blob_source_pin_normalizes_windows_crlf_without_weakening_pin(tmp_path):
    """Normalize only CRLF; meaningful source changes still change the blob ID."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "core.autocrlf", "true"], cwd=repo, check=True,
    )
    source = repo / "main.py"
    source.write_bytes(b"first line\r\nsecond line\r\n")

    raw_sha = subprocess.run(
        ["git", "hash-object", "--no-filters", "--", "main.py"], cwd=repo,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    canonical_sha = subprocess.run(
        ["git", "hash-object", "--stdin"], cwd=repo,
        input=b"first line\nsecond line\n", check=True,
        capture_output=True,
    ).stdout.decode("ascii").strip()

    assert raw_sha != canonical_sha
    assert harness._git_blob_sha("main.py", repo_root=repo) == canonical_sha
    assert canonical_sha != "0" * 40, "the comparison must still be against a concrete blob hash"

    source.write_bytes(b"first line changed\r\nsecond line\r\n")
    assert harness._git_blob_sha("main.py", repo_root=repo) != canonical_sha


def test_retrieval_harness_uses_derived_acl_for_owner_and_same_office_denial():
    """Exercise the harness's real retrieve_documents path against a filter-aware adapter.

    This is an offline harness proof, not live Pinecone evidence. It ensures the
    positive owner query reaches its marker and the same-office non-owner query
    is constrained by the ACL derived from request identity.
    """
    from types import SimpleNamespace

    uid_a, uid_c = "synthetic-user-a", "synthetic-user-c"
    matter_a, matter_c = "synthetic-matter-a", "synthetic-matter-c"
    office = "synthetic-office"
    marker_a = "SYNTHETIC_PRIVATE_RAG_AB_OWNER_A_MARKER_" + "A" * 64
    marker_c = "SYNTHETIC_PRIVATE_RAG_AB_MEMBER_C_MARKER_" + "C" * 64

    class _Query:
        def __init__(self, table):
            self.table_name = table
            self.filters = []
            self.single = False

        def select(self, *args, **kwargs):
            return self

        def eq(self, key, value):
            self.filters.append(("eq", key, value))
            return self

        def in_(self, key, values):
            self.filters.append(("in", key, list(values)))
            return self

        def is_(self, key, value):
            self.filters.append(("is", key, None if value == "null" else value))
            return self

        def maybe_single(self):
            self.single = True
            return self

        def execute(self):
            rows = {
                "kancelarije": [{"id": office, "admin_uid": uid_a}],
                "kancelarija_clanovi": [
                    {"kancelarija_id": office, "user_id": uid_c, "status": "ACTIVE"},
                ],
                "predmeti": [
                    {"id": matter_a, "user_id": uid_a, "brisanje_zapoceto": None},
                    {"id": matter_c, "user_id": uid_c, "brisanje_zapoceto": None},
                ],
                "predmet_delegiranja": [],
            }.get(self.table_name, [])

            def matches(row):
                for op, key, value in self.filters:
                    found = row.get(key)
                    if op == "eq" and found != value:
                        return False
                    if op == "in" and found not in value:
                        return False
                    if op == "is" and found is not value:
                        return False
                return True

            selected = [row for row in rows if matches(row)]
            if self.single:
                data = selected[0] if selected else None
            else:
                data = selected
            return SimpleNamespace(data=data)

    class _Service:
        def table(self, name):
            return _Query(name)

    class _FilterAwarePinecone:
        def __init__(self):
            self.vectors = {
                (f"kancelarija_{office}", "a"): {
                    "type": "case_doc", "predmet_id": matter_a, "text": marker_a,
                    "source_filename": "synthetic-a.txt", "owner_user_id": uid_a,
                },
                (f"kancelarija_{office}", "c"): {
                    "type": "case_doc", "predmet_id": matter_c, "text": marker_c,
                    "source_filename": "synthetic-c.txt", "owner_user_id": uid_c,
                },
            }
            self.queries = []

        def query(self, *, vector, top_k, namespace, include_metadata, **kwargs):
            filt = kwargs.get("filter") or {}
            self.queries.append({"namespace": namespace, "filter": filt})
            allowed_types = filt.get("type", {}).get("$in")
            allowed_matters = filt.get("predmet_id", {}).get("$in")
            matches = []
            for (ns, vector_id), metadata in self.vectors.items():
                if ns != namespace:
                    continue
                if allowed_types is not None and metadata["type"] not in allowed_types:
                    continue
                if allowed_matters is not None and metadata["predmet_id"] not in allowed_matters:
                    continue
                matches.append(SimpleNamespace(id=vector_id, metadata=metadata, score=0.99))
            return SimpleNamespace(matches=matches[:top_k])

    index = _FilterAwarePinecone()
    service = _Service()
    docs_a, meta_a, trace_a = harness._retrieval(index, service, uid_a)
    docs_c, meta_c, trace_c = harness._retrieval(index, service, uid_c)

    assert marker_a in "\n".join(docs_a)
    assert marker_a not in json.dumps({"docs": docs_c, "meta": meta_c}, ensure_ascii=False)
    assert marker_c in "\n".join(docs_c), "C positive control must retrieve its own marker"
    assert trace_a and trace_c
    assert all(q["filter"]["predmet_id"]["$in"] == [matter_a] for q in trace_a)
    assert all(q["filter"]["predmet_id"]["$in"] == [matter_c] for q in trace_c)
    assert len(index.queries) >= 2


def test_retrieval_harness_explicit_acl_expansion_is_separate_and_intersected():
    """A caller-supplied foreign matter cannot expand C's server-derived ACL."""
    from types import SimpleNamespace

    uid_c, matter_c, matter_a = "synthetic-user-c", "synthetic-matter-c", "synthetic-matter-a"
    office = "synthetic-office"

    class _Service:
        def table(self, name):
            class Q:
                def __init__(self):
                    self.filters = []
                    self.single = False
                def select(self, *a, **k): return self
                def eq(self, k, v): self.filters.append(("eq", k, v)); return self
                def in_(self, k, v): self.filters.append(("in", k, list(v))); return self
                def is_(self, k, v): self.filters.append(("is", k, None if v == "null" else v)); return self
                def maybe_single(self):
                    self.single = True
                    return self
                def execute(self):
                    rows = {
                        "kancelarije": [],
                        "kancelarija_clanovi": [{"kancelarija_id": office, "user_id": uid_c, "status": "ACTIVE"}],
                        "predmeti": [{"id": matter_c, "user_id": uid_c, "brisanje_zapoceto": None}],
                        "predmet_delegiranja": [],
                    }.get(name, [])
                    def ok(row):
                        return all(
                            (op == "eq" and row.get(k) == v) or
                            (op == "in" and row.get(k) in v) or
                            (op == "is" and row.get(k) is v)
                            for op, k, v in self.filters
                        )
                    selected = [r for r in rows if ok(r)]
                    return SimpleNamespace(data=(selected[0] if selected else None) if self.single else selected)
            return Q()

    marker_a = "SYNTHETIC_PRIVATE_RAG_AB_OWNER_A_MARKER_" + "A" * 64

    class _Index:
        def __init__(self): self.queries = []
        def query(self, *, namespace, top_k, **kwargs):
            filt = kwargs.get("filter") or {}
            self.queries.append(filt)
            metadata = {"type": "case_doc", "predmet_id": matter_a, "text": marker_a,
                        "source_filename": "synthetic-a.txt", "owner_user_id": "synthetic-user-a"}
            types = filt.get("type", {}).get("$in")
            matters = filt.get("predmet_id", {}).get("$in")
            allowed = namespace == f"kancelarija_{office}" and (types is None or metadata["type"] in types) and (matters is None or metadata["predmet_id"] in matters)
            matches = [SimpleNamespace(id="a", metadata=metadata, score=0.99)] if allowed else []
            return SimpleNamespace(matches=matches[:top_k])

    index = _Index()
    docs, meta, trace = harness._retrieval(index, _Service(), uid_c, dozvoljeni_predmeti=[matter_a])
    assert marker_a not in json.dumps({"docs": docs, "meta": meta}, ensure_ascii=False)
    # C's server-derived ACL contains only matter_c; intersecting it with the
    # attacker-supplied [matter_a] is empty, so private retrieval is skipped.
    assert trace == []
    assert index.queries == []


