"""Offline safety checks for the opt-in live Pinecone A/B harness.

These tests validate the harness gates and recovery manifest only. They are
not represented as live Pinecone/Auth isolation evidence.
"""
from __future__ import annotations

import json
import ast
import sys
from types import SimpleNamespace
from types import SimpleNamespace
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
    assert '"missing_variables"' in output
    assert "SUPABASE_URL" in output
    assert "PINECONE_API_KEY" in output
    assert "Recovery manifest" not in output


def test_cleanup_implementation_never_uses_broad_delete_and_targets_exact_ids():
    import inspect

    source = inspect.getsource(harness._clean)
    parsed = ast.parse(source)
    assert not any(isinstance(n, ast.Attribute) and n.attr == "delete_all" for n in ast.walk(parsed))
    assert '.eq("id", row_id)' in source
    assert "index.delete(ids=[v[\"id\"] for v in present], namespace=ns)" in source
    assert "index.fetch(ids=ids, namespace=ns)" in source


def test_cleanup_never_deletes_planned_but_unattempted_resources(tmp_path):
    manifest = harness._new_manifest()
    manifest["_manifest_path"] = str(tmp_path / "manifest.json")
    manifest_path = Path(manifest["_manifest_path"])
    harness._write_manifest(manifest_path, manifest)

    class _NoRemoteMutation:
        class auth:
            class admin:
                @staticmethod
                def list_users(**kwargs):
                    raise AssertionError("unattempted identity must not be looked up")
        def __getattr__(self, name):
            if name == "table":
                raise AssertionError("unattempted DB write must not be touched")
            raise AssertionError(f"remote operation unexpectedly called: {name}")

    harness._clean(_NoRemoteMutation(), _NoRemoteMutation(), manifest_path, manifest)
    assert manifest["cleanup"]["verified"] is True
    assert all(v["write_state"] == "NOT_ATTEMPTED" for v in manifest["vectors"])
    assert manifest["database_writes"] == []
    assert all(u["write_state"] == "NOT_ATTEMPTED" for u in manifest["users"].values())


def test_cleanup_reconciles_ambiguous_vector_write_before_exact_delete(tmp_path):
    manifest = harness._new_manifest()
    manifest["_manifest_path"] = str(tmp_path / "manifest.json")
    manifest["users"]["A"].update({"id": "11111111-1111-4111-8111-111111111111"})
    vector = manifest["vectors"][0]
    vector["write_state"] = "ATTEMPTED_UNKNOWN"
    vector["text_sha256"] = harness._fixture_vector("A", manifest["run_id"])["text_sha256"]
    manifest_path = Path(manifest["_manifest_path"])
    harness._write_manifest(manifest_path, manifest)

    class _Index:
        def __init__(self): self.deleted = []
        def fetch(self, *, ids, namespace): return type("R", (), {"vectors": {}})()
        def delete(self, *, ids, namespace): self.deleted.extend(ids)
    class _NoDB:
        def __getattr__(self, name): raise AssertionError("no DB writes were attempted")
    index = _Index()
    harness._clean(_NoDB(), index, manifest_path, manifest)
    assert index.deleted == []
    assert vector["write_state"] == "CONFIRMED_ABSENT"
    assert manifest["cleanup"]["verified"] is True


def test_primary_failure_is_preserved_when_cleanup_also_fails(tmp_path, monkeypatch):
    manifest = harness._new_manifest()
    manifest["_manifest_path"] = str(tmp_path / "manifest.json")
    manifest["stage"] = "auth.create_user.A"
    manifest["users"]["A"]["write_state"] = "ATTEMPTED_UNKNOWN"
    path = Path(manifest["_manifest_path"])
    harness._write_manifest(path, manifest)

    def broken_cleanup(*args):
        raise RuntimeError("cleanup secret must not be included")
    monkeypatch.setattr(harness, "_clean", broken_cleanup)
    error = harness._preserve_primary_failure(
        RuntimeError("primary timeout must remain primary"), object(), object(), path, manifest, "fallback-stage",
    )
    report = harness._safe_error(error, stage="ignored", mutation_attempted=False, manifest_path=path)
    assert report["primary_error"]["exception_type"] == "RuntimeError"
    assert report["primary_error"]["stage"] == "auth.create_user.A"
    assert report["primary_error"]["remote_mutation_attempted"] is True
    assert report["cleanup_error"]["exception_type"] == "RuntimeError"
    assert "secret" not in json.dumps(report)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["state"] == "cleanup_required"
    assert saved["primary_error"]["stage"] == "auth.create_user.A"


def test_primary_failure_is_reported_if_manifest_persistence_also_fails(tmp_path, monkeypatch):
    manifest = harness._new_manifest()
    manifest["_manifest_path"] = str(tmp_path / "manifest.json")
    manifest["users"]["A"]["write_state"] = "ATTEMPTED_UNKNOWN"
    path = Path(manifest["_manifest_path"])
    monkeypatch.setattr(harness, "_write_manifest", lambda *args: (_ for _ in ()).throw(OSError("secret path")))
    monkeypatch.setattr(harness, "_clean", lambda *args: (_ for _ in ()).throw(OSError("cleanup failure")))
    error = harness._preserve_primary_failure(RuntimeError("provider timeout"), object(), object(), path,
                                              manifest, "auth.create_user.A")
    report = harness._safe_error(error, stage="ignored", mutation_attempted=False, manifest_path=path)
    assert report["primary_error"]["exception_type"] == "RuntimeError"
    assert report["cleanup_error"]["exception_type"] == "OSError"
    assert report["journal_error"]["exception_type"] == "OSError"
    assert "secret" not in json.dumps(report)


def test_schema_two_manifest_rejects_unknown_write_state():
    manifest = harness._new_manifest()
    manifest["vectors"][0]["write_state"] = "maybe-written"
    with pytest.raises(RuntimeError, match="vector write state"):
        harness._validate_manifest_for_cleanup(manifest)


def test_incomplete_db_or_auth_reads_never_mean_resource_absent():
    class _Response:
        data = None
        users = None
    class _Query:
        def select(self, *args, **kwargs): return self
        def eq(self, *args, **kwargs): return self
        def limit(self, *args, **kwargs): return self
        def execute(self): return _Response()
    class _Service:
        class auth:
            class admin:
                @staticmethod
                def list_users(**kwargs): return _Response()
        def table(self, name): return _Query()
    with pytest.raises(RuntimeError, match="Incomplete exact-row response"):
        harness._exact_db_rows(_Service(), "predmeti", "synthetic-id")
    with pytest.raises(RuntimeError, match="Incomplete exact synthetic Auth listing"):
        harness._auth_users_page(_Service(), page=1, per_page=100)


@pytest.mark.parametrize("page", [[{"id": "synthetic-user"}], []])
def test_auth_users_page_accepts_verified_direct_list_responses(page):
    service = SimpleNamespace(auth=SimpleNamespace(admin=SimpleNamespace(
        list_users=lambda **kwargs: page,
    )))
    assert harness._auth_users_page(service, page=1, per_page=100) is page


@pytest.mark.parametrize("response", [None, {}, (), "users", SimpleNamespace(users=None),
                                       SimpleNamespace(users=()), SimpleNamespace(users={})])
def test_auth_users_page_rejects_invalid_response_shapes(response):
    service = SimpleNamespace(auth=SimpleNamespace(admin=SimpleNamespace(
        list_users=lambda **kwargs: response,
    )))
    with pytest.raises(RuntimeError, match="Incomplete exact synthetic Auth listing"):
        harness._auth_users_page(service, page=1, per_page=100)


def test_legacy_manifest_reconciliation_uses_direct_list_auth_response(tmp_path):
    manifest = harness._new_manifest()
    manifest["schema"] = 1
    for user in manifest["users"].values():
        user.pop("write_state", None)
    for vector in manifest["vectors"]:
        vector.pop("write_state", None)
    path = tmp_path / "legacy.json"
    harness._write_manifest(path, manifest)
    calls = []

    class _Admin:
        def list_users(self, **kwargs):
            calls.append(kwargs)
            return []  # Actual SDK response shape for an empty page.
    class _Query:
        def select(self, *args, **kwargs): return self
        def eq(self, *args, **kwargs): return self
        def limit(self, *args, **kwargs): return self
        def execute(self): return SimpleNamespace(data=[])
    class _Service:
        auth = SimpleNamespace(admin=_Admin())
        def table(self, name): return _Query()
    class _Index:
        def fetch(self, **kwargs): return SimpleNamespace(vectors={})

    result = harness._inspect_legacy_manifest(_Service(), _Index(), path, manifest)
    assert len(calls) == 4
    assert result["reconciled_absent"] is True
    assert result["auth_users_present"] == []


def test_missing_founder_environment_import_failure_is_reproduced_offline():
    import os
    import sys
    env = dict(os.environ)
    env.pop("FOUNDER_EMAILS", None)
    env["PYTHONPATH"] = str(harness.REPO_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", "import shared.deps"],
        cwd=harness.REPO_ROOT, env=env, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "FOUNDER_EMAILS env var must be set" in result.stderr
    assert "Traceback" in result.stderr


def test_harness_founder_sentinel_is_process_local_and_nonprivileged(monkeypatch):
    import os
    monkeypatch.delenv("FOUNDER_EMAILS", raising=False)
    imported = []
    monkeypatch.setattr("importlib.import_module", lambda name: imported.append(name))
    harness._load_runtime_dependencies()
    assert os.environ["FOUNDER_EMAILS"] == harness.FOUNDER_SENTINEL
    assert harness.FOUNDER_SENTINEL not in {r["email"] for r in harness._new_manifest()["users"].values()}
    assert "shared.deps" in imported


def test_create_auth_user_timeout_is_journaled_before_request(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDER_EMAILS", harness.FOUNDER_SENTINEL)
    manifest = harness._new_manifest()
    path = tmp_path / "auth-timeout.json"
    manifest["_manifest_path"] = str(path)
    harness._write_manifest(path, manifest)
    class _Admin:
        def create_user(self, payload): raise TimeoutError("ambiguous synthetic timeout")
    service = SimpleNamespace(auth=SimpleNamespace(admin=_Admin()))
    with pytest.raises(TimeoutError):
        harness._create_auth_users(service, object(), manifest)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["users"]["A"]["write_state"] == "ATTEMPTED_UNKNOWN"
    assert saved["stage"] == "auth.create_user.A"


def test_partial_database_fixture_journals_success_and_ambiguous_next_write(tmp_path):
    manifest = harness._new_manifest()
    path = tmp_path / "partial-db.json"
    manifest["_manifest_path"] = str(path)
    harness._write_manifest(path, manifest)
    calls = []
    class _Insert:
        def __init__(self, table): self.table_name = table
        def execute(self):
            calls.append(self.table_name)
            if self.table_name == "predmeti": raise TimeoutError("ambiguous row timeout")
    class _Table:
        def __init__(self, name): self.name = name
        def insert(self, payload): return _Insert(self.name)
    class _Service:
        def table(self, name): return _Table(name)
    for role in manifest["users"].values(): role["id"] = str(__import__("uuid").uuid4())
    with pytest.raises(TimeoutError):
        harness._seed_rows(_Service(), manifest, path)
    assert calls == ["kancelarije", "predmeti"]
    states = {(x["key"], x["write_state"]) for x in manifest["database_writes"]}
    assert ("office", "CONFIRMED_CREATED") in states
    assert ("matter_A", "ATTEMPTED_UNKNOWN") in states
    assert len(manifest["database_writes"]) == 2


def test_seed_rows_uses_a_database_allowed_office_member_role(tmp_path):
    manifest = harness._new_manifest()
    path = tmp_path / "member-role.json"
    manifest["_manifest_path"] = str(path)
    harness._write_manifest(path, manifest)
    for user in manifest["users"].values():
        user["id"] = str(__import__("uuid").uuid4())
    inserted = []

    class _Insert:
        def __init__(self, payload): self.payload = payload
        def execute(self): inserted.append(self.payload)
    class _Table:
        def insert(self, payload): return _Insert(payload)
    class _Service:
        def table(self, name): return _Table()

    harness._seed_rows(_Service(), manifest, path)
    memberships = [row for row in inserted if "kancelarija_id" in row]
    assert {row["email"] for row in memberships} == {
        manifest["users"][role]["email"] for role in ("C", "D")
    }
    assert {row["uloga"] for row in memberships} == {"advokat"}


def test_created_b_user_persists_canonical_vector_namespace_immediately(tmp_path, monkeypatch):
    import shared.deps

    manifest = harness._new_manifest()
    path = tmp_path / "b-namespace.json"
    manifest["_manifest_path"] = str(path)
    harness._write_manifest(path, manifest)
    created = {}
    ids = {role: str(__import__("uuid").uuid4()) for role in ("A", "B")}

    class _Admin:
        def create_user(self, payload):
            role = payload["email"].rsplit("-", 1)[1].split("@", 1)[0].upper()
            created[payload["email"]] = ids[role]
            return SimpleNamespace(user=SimpleNamespace(id=ids[role]))
    class _AnonAuth:
        current_id = None
        def sign_in_with_password(self, payload):
            if payload["email"] == manifest["users"]["B"]["email"]:
                raise RuntimeError("synthetic interruption after B auth creation")
            self.current_id = created[payload["email"]]
            return SimpleNamespace(session=SimpleNamespace(access_token=self.current_id, refresh_token="synthetic"))
        def set_session(self, access_token, refresh_token): self.current_id = access_token
        def get_user(self): return SimpleNamespace(user=SimpleNamespace(id=self.current_id))
    service = SimpleNamespace(auth=SimpleNamespace(admin=_Admin()))
    anon = SimpleNamespace(auth=_AnonAuth())
    monkeypatch.setattr(shared.deps, "_verify_token", lambda token: {"sub": token})

    with pytest.raises(RuntimeError, match="interruption after B auth creation"):
        harness._create_auth_users(service, anon, manifest)

    saved = json.loads(path.read_text(encoding="utf-8"))
    b_vector = next(v for v in saved["vectors"] if v["owner"] == "B")
    assert saved["users"]["B"]["id"] == ids["B"]
    assert saved["users"]["B"]["write_state"] == "CONFIRMED_CREATED"
    assert b_vector["namespace"] == f"user_{ids['B']}"
    assert b_vector["write_state"] == "NOT_ATTEMPTED"


def test_partial_seed_failure_allows_exact_cleanup_of_unattempted_pending_b_vector(tmp_path):
    manifest = harness._new_manifest()
    path = tmp_path / "partial-membership-cleanup.json"
    manifest["_manifest_path"] = str(path)
    for user in manifest["users"].values():
        user["id"] = str(__import__("uuid").uuid4())
        user["write_state"] = "CONFIRMED_CREATED"
    # Models an older interrupted run: B Auth exists, but the B vector has
    # not yet been attempted and its planned namespace is still a placeholder.
    manifest["vectors"][2]["namespace"] = "user__pending__B"
    harness._write_manifest(path, manifest)
    rows = {}
    auth_users = {
        user["id"]: SimpleNamespace(
            id=user["id"], email=user["email"],
            user_metadata={"vindex_private_rag_ab_run": manifest["run_id"]},
        ) for user in manifest["users"].values()
    }
    inserted_memberships = []

    class _NotFound(Exception):
        status = 404
    class _Query:
        def __init__(self, table, operation="select", payload=None):
            self.table, self.operation, self.payload, self.row_id = table, operation, payload, None
        def select(self, *_args, **_kwargs): self.operation = "select"; return self
        def insert(self, payload): self.operation, self.payload = "insert", payload; return self
        def delete(self): self.operation = "delete"; return self
        def eq(self, key, value):
            assert key == "id"
            self.row_id = value
            return self
        def limit(self, _n): return self
        def execute(self):
            table_rows = rows.setdefault(self.table, {})
            if self.operation == "insert":
                if self.payload["id"] == manifest["memberships"]["C"]:
                    inserted_memberships.append(self.payload)
                    raise RuntimeError("synthetic membership CHECK violation")
                table_rows[self.payload["id"]] = dict(self.payload)
                return SimpleNamespace(data=[dict(self.payload)])
            if self.operation == "delete":
                table_rows.pop(str(self.row_id), None)
                return SimpleNamespace(data=[])
            row = table_rows.get(str(self.row_id))
            return SimpleNamespace(data=[dict(row)] if row else [])
    class _Admin:
        def get_user_by_id(self, user_id):
            if user_id not in auth_users: raise _NotFound()
            return SimpleNamespace(user=auth_users[user_id])
        def delete_user(self, user_id): auth_users.pop(user_id, None)
    class _Service:
        auth = SimpleNamespace(admin=_Admin())
        def table(self, name): return _Query(name)
    class _Index:
        def fetch(self, **_kwargs): raise AssertionError("no vector upsert was attempted")
        def delete(self, **_kwargs): raise AssertionError("no vector cleanup should be needed")

    service = _Service()
    with pytest.raises(RuntimeError, match="synthetic membership CHECK violation"):
        harness._seed_rows(service, manifest, path)
    assert inserted_memberships[0]["uloga"] == "advokat"
    assert all(v["write_state"] == "NOT_ATTEMPTED" for v in manifest["vectors"])

    harness._clean(service, _Index(), path, manifest)

    assert manifest["cleanup"]["verified"] is True
    assert rows == {"kancelarije": {}, "predmeti": {}, "kancelarija_clanovi": {}}
    assert auth_users == {}
    assert all(v["write_state"] == "NOT_ATTEMPTED" for v in manifest["vectors"])


def test_pending_b_namespace_is_rejected_after_any_vector_write_attempt():
    manifest = harness._new_manifest()
    manifest["users"]["B"]["id"] = str(__import__("uuid").uuid4())
    manifest["vectors"][2]["namespace"] = "user__pending__B"
    manifest["vectors"][2]["write_state"] = "ATTEMPTED_UNKNOWN"
    with pytest.raises(RuntimeError, match="vector IDs/namespaces"):
        harness._validate_manifest_for_cleanup(manifest)


def test_not_found_during_ambiguous_vector_cleanup_is_not_cleanup_proof(tmp_path):
    manifest = harness._new_manifest()
    manifest["_manifest_path"] = str(tmp_path / "not-found.json")
    manifest["vectors"][0]["write_state"] = "ATTEMPTED_UNKNOWN"
    manifest["vectors"][0]["text_sha256"] = harness._fixture_vector("A", manifest["run_id"])["text_sha256"]
    class NotFoundException(Exception):
        status = 404
    class _Index:
        def fetch(self, **kwargs): raise NotFoundException()
        def delete(self, **kwargs): raise AssertionError("failed fetch cannot authorize delete")
    class _Service: pass
    path = Path(manifest["_manifest_path"])
    harness._write_manifest(path, manifest)
    with pytest.raises(RuntimeError, match="Cleanup could not be verified"):
        harness._clean(_Service(), _Index(), path, manifest)
    assert manifest["cleanup"]["verified"] is False
    assert manifest["vectors"][0]["write_state"] == "CLEANUP_FAILED"


def test_live_preflight_rejects_wrong_described_pinecone_host_without_supabase_call(monkeypatch):
    host = "configured-test.svc.pinecone.io"
    for name, value in {
        "SUPABASE_URL": f"https://{harness.EXPECTED_PROJECT_REF}.supabase.co",
        "SUPABASE_ANON_KEY": "placeholder", "SUPABASE_SERVICE_KEY": "placeholder",
        "PINECONE_API_KEY": "placeholder", "PINECONE_HOST": host,
        "PINECONE_INDEX_NAME": harness.EXPECTED_INDEX,
    }.items(): monkeypatch.setenv(name, value)
    monkeypatch.setattr(harness, "_preflight", lambda **kwargs: {
        "candidate_sha": "candidate", "pinecone_index_name": harness.EXPECTED_INDEX,
        "supabase_project_ref": harness.EXPECTED_PROJECT_REF,
    })
    monkeypatch.setattr(harness, "_require_source_pin", lambda **kwargs: True)
    monkeypatch.setattr(harness, "_load_runtime_dependencies", lambda: None)
    monkeypatch.setattr(harness, "_read_manifest_paths", lambda: [])
    class _Pinecone:
        def __init__(self, **kwargs): pass
        def describe_index(self, name): return SimpleNamespace(host="different.svc.pinecone.io", dimension=harness.VECTOR_DIM)
    monkeypatch.setitem(sys.modules, "pinecone", SimpleNamespace(Pinecone=_Pinecone))
    monkeypatch.setattr(harness, "_auth_client", lambda *args: (_ for _ in ()).throw(AssertionError("Supabase should not be reached")))
    with pytest.raises(RuntimeError, match="does not match the named index"):
        harness._preflight_live(expected_sha="candidate")


def test_live_preflight_invalid_supabase_admin_read_fails_closed(monkeypatch):
    host = "configured-test.svc.pinecone.io"
    for name, value in {
        "SUPABASE_URL": f"https://{harness.EXPECTED_PROJECT_REF}.supabase.co",
        "SUPABASE_ANON_KEY": "placeholder", "SUPABASE_SERVICE_KEY": "placeholder",
        "PINECONE_API_KEY": "placeholder", "PINECONE_HOST": host,
        "PINECONE_INDEX_NAME": harness.EXPECTED_INDEX,
    }.items(): monkeypatch.setenv(name, value)
    monkeypatch.setattr(harness, "_preflight", lambda **kwargs: {
        "candidate_sha": "candidate", "pinecone_index_name": harness.EXPECTED_INDEX,
        "pinecone_host_fingerprint": "fp", "supabase_project_ref": harness.EXPECTED_PROJECT_REF,
    })
    monkeypatch.setattr(harness, "_require_source_pin", lambda **kwargs: True)
    monkeypatch.setattr(harness, "_load_runtime_dependencies", lambda: None)
    class _Index:
        def delete(self, **kwargs): raise AssertionError("read-only preflight")
    class _Pinecone:
        def __init__(self, **kwargs): pass
        def describe_index(self, name): return SimpleNamespace(host=host, dimension=harness.VECTOR_DIM)
        def Index(self, **kwargs): return _Index()
    monkeypatch.setitem(sys.modules, "pinecone", SimpleNamespace(Pinecone=_Pinecone))
    class Unauthorized(Exception): status_code=401
    service = SimpleNamespace(auth=SimpleNamespace(admin=SimpleNamespace(list_users=lambda **kwargs: (_ for _ in ()).throw(Unauthorized()))))
    monkeypatch.setattr(harness, "_auth_client", lambda *args: (service, object()))
    with pytest.raises(Unauthorized):
        harness._preflight_live(expected_sha="candidate")


def test_safe_error_keeps_missing_module_and_never_serializes_exception_message():
    exc = ModuleNotFoundError("secret-bearing provider response", name="pinecone")
    detail = harness._safe_error(exc, stage="import", mutation_attempted=False, manifest_path=None)
    assert detail["missing_module"] == "pinecone"
    assert "secret-bearing" not in json.dumps(detail)


def test_preflight_live_requires_exact_candidate_sha_without_provider_access(monkeypatch):
    called = []
    monkeypatch.setattr(harness, "_preflight_live", lambda **kwargs: called.append(kwargs))
    with pytest.raises(SystemExit):
        harness.main(["--preflight-live"])
    assert called == []


def test_preflight_live_uses_provider_reads_only(monkeypatch):
    calls = []
    host = "approved-test-index.svc.pinecone.io"
    for name, value in {
        "SUPABASE_URL": f"https://{harness.EXPECTED_PROJECT_REF}.supabase.co",
        "SUPABASE_ANON_KEY": "test-anon-placeholder",
        "SUPABASE_SERVICE_KEY": "test-service-placeholder",
        "PINECONE_API_KEY": "test-pinecone-placeholder",
        "PINECONE_HOST": host,
        "PINECONE_INDEX_NAME": harness.EXPECTED_INDEX,
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(harness, "_preflight", lambda **kwargs: {
        "candidate_sha": "candidate-sha", "pinecone_index_name": harness.EXPECTED_INDEX,
        "pinecone_host_fingerprint": "fingerprint", "supabase_project_ref": harness.EXPECTED_PROJECT_REF,
    })
    monkeypatch.setattr(harness, "_require_source_pin", lambda **kwargs: True)
    monkeypatch.setattr(harness, "_load_runtime_dependencies", lambda: None)
    monkeypatch.setattr(harness, "_read_manifest_paths", lambda: [])

    class _Index:
        def delete(self, **kwargs): raise AssertionError("preflight must not invoke Pinecone delete")
        def __getattr__(self, name):
            if name == "fetch":
                calls.append("pinecone.fetch")
                return lambda **kwargs: SimpleNamespace(vectors={})
            if name in {"upsert", "delete"}:
                raise AssertionError("live preflight must never mutate Pinecone")
            raise AttributeError(name)
    class _Pinecone:
        def __init__(self, **kwargs): calls.append("pinecone.client")
        def describe_index(self, name):
            calls.append(("pinecone.describe_index", name))
            return SimpleNamespace(host=host, dimension=harness.VECTOR_DIM)
        def Index(self, **kwargs): calls.append(("pinecone.Index", kwargs)); return _Index()
    monkeypatch.setitem(sys.modules, "pinecone", SimpleNamespace(Pinecone=_Pinecone))

    class _Admin:
        def delete_user(self, *args, **kwargs): raise AssertionError("preflight must not delete users")
        def list_users(self, **kwargs): calls.append(("supabase.list_users", kwargs)); return SimpleNamespace(users=[])
    class _Table:
        def delete(self): raise AssertionError("preflight must not delete table rows")
    service = SimpleNamespace(auth=SimpleNamespace(admin=_Admin()), table=lambda name: _Table())
    monkeypatch.setattr(harness, "_auth_client", lambda *args: (service, object()))

    report = harness._preflight_live(expected_sha="candidate-sha")
    assert report["preflight_live"] is True
    assert report["writes"] == 0
    assert report["provider_reads"]["pinecone_describe_index"] == 1
    assert report["provider_reads"]["supabase_admin_list_users"] == 1
    assert all(report["cleanup_capabilities"].values())
    assert [c[0] for c in calls if isinstance(c, tuple)] == [
        "pinecone.describe_index", "pinecone.Index", "supabase.list_users",
    ]


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
    subprocess.run(["git", "config", "user.name", "Pin Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "pin-test@example.invalid"], cwd=repo, check=True)
    source = repo / "main.py"
    source.write_bytes(b"first line\nsecond line\n")
    subprocess.run(["git", "add", "main.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "approved source"], cwd=repo, check=True)
    canonical_sha = subprocess.run(
        ["git", "rev-parse", "HEAD:main.py"], cwd=repo,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    source.write_bytes(b"first line\r\nsecond line\r\n")

    raw_sha = subprocess.run(
        ["git", "hash-object", "--no-filters", "--", "main.py"], cwd=repo,
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    assert raw_sha != canonical_sha
    assert harness._git_blob_sha("main.py", repo_root=repo) == canonical_sha
    assert canonical_sha != "0" * 40, "the comparison must still be against a concrete blob hash"

    source.write_bytes(b"first line changed\r\nsecond line\r\n")
    assert harness._git_blob_sha("main.py", repo_root=repo) == ""


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


