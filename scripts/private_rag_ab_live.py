#!/usr/bin/env python3
"""Bounded, synthetic Pinecone A/B isolation exercise for PR #84.

No provider is contacted by default. ``--execute`` is required before fixture
writes. Credentials are read only from the current protected process
environment; they are never read from .env, persisted, or printed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import re
import secrets
import sys
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

PINNED_SOURCE_SHA = "984af6d817a1fcc12b0896106e72ce769fdc3947"
EXPECTED_PROJECT_REF = "czsxymueizfqrbbgqqob"
EXPECTED_INDEX = "vindex-ai"
PINNED_PINECONE_SDK_VERSION = "8.1.1"
SAFE_PROVIDER_ERROR_CODES = frozenset({
    "INVALID_ARGUMENT", "BAD_REQUEST", "UNAUTHENTICATED", "PERMISSION_DENIED",
    "NOT_FOUND", "ALREADY_EXISTS", "RESOURCE_EXHAUSTED", "INTERNAL", "UNAVAILABLE",
})
EXPECTED_CACHE_MAIN_BLOB = "397d8bd4954b822a91680bd01d5c841a4a1f9223"
EXPECTED_CODE_BLOBS = {
    "api.py": "12bb1cd42f4a093f37215403c82c2823a562e06a",
    "app/services/retrieve.py": "b8b0bfbd7b273473686de4ae8814a5b79175178c",
    "shared/rag_acl.py": "54e73a5861534da3682a7ed154b476c9806822d2",
    "shared/kancelarija_utils.py": "864d19611a8a16965ed63f94a372d42a5512c0e9",
    "shared/ai_provenance.py": "d4cc929e0f2f9554c27d2555d9c3063a0bffd4d9",
}
REQUIRED_ENV = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_KEY",
    "PINECONE_API_KEY",
    "PINECONE_HOST",
    "PINECONE_INDEX_NAME",
)
VECTOR_DIM = 3072
VECTOR_LIMIT = 6
MAX_QUERIES = 16
REPO_ROOT = Path(__file__).resolve().parents[1]
WRITE_STATES = {"NOT_ATTEMPTED", "ATTEMPTED_UNKNOWN", "CONFIRMED_CREATED", "CONFIRMED_ABSENT", "CLEANUP_FAILED"}
FOUNDER_SENTINEL = "vindex-private-rag-harness-sentinel@example.invalid"


class MissingEnvError(RuntimeError):
    def __init__(self, names: list[str]):
        self.missing_names = names
        super().__init__("Required protected process variables are missing")


class HarnessExecutionError(RuntimeError):
    def __init__(self, details: dict[str, Any]):
        self.details = details
        super().__init__("Harness execution failed; inspect sanitized error details")


def _git_blob_sha(filename: str, *, repo_root: Path = REPO_ROOT) -> str:
    """Return HEAD's blob ID only when working source matches its blob.

    `git hash-object <path>` may run path clean filters and therefore need not
    identify the bytes Python reads. Compare those bytes directly with the
    tracked blob, allowing only CRLF/LF checkout normalization, then return
    the tracked object's ID for comparison with the fixed approved pin.
    """
    object_name = f"HEAD:{filename}"
    blob_id = subprocess.run(
        ["git", "rev-parse", "--verify", object_name],
        check=True, capture_output=True, text=True, cwd=repo_root,
    ).stdout.strip()
    tracked = subprocess.run(
        ["git", "cat-file", "blob", object_name],
        check=True, capture_output=True, cwd=repo_root,
    ).stdout
    working = (repo_root / filename).read_bytes()
    if working.replace(b"\r\n", b"\n") != tracked.replace(b"\r\n", b"\n"):
        return ""
    return blob_id


def _has_authenticated_cache_bypass(node: ast.FunctionDef | ast.AsyncFunctionDef | None) -> bool:
    if node is None:
        return False
    for branch in ast.walk(node):
        if not isinstance(branch, ast.If):
            continue
        if not any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_autentifikovan_privatni_rag_kontekst"
            for call in ast.walk(branch.test)
        ):
            continue
        if any(
            isinstance(stmt, ast.Return)
            and (stmt.value is None or isinstance(stmt.value, ast.Constant) and stmt.value.value is None)
            for stmt in ast.walk(branch)
        ):
            return True
    return False


def _manifest_home() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    if not base:
        base = str(Path.home() / ".local" / "state")
    return Path(base) / "VindexAI" / "private-rag-ab"


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".private-rag-ab-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def _require_source_pin(*, require_cache_source: bool = False) -> bool:
    """Pin the application and auth code whose behavior this exercise uses."""

    for filename, expected in EXPECTED_CODE_BLOBS.items():
        if _git_blob_sha(filename) != expected:
            raise RuntimeError(f"Candidate source differs from pinned contract: {filename}")

    # Both public variants must call the same ask_agent path with no legacy
    # office namespace argument. The existing exact-SHA API regression tests
    # exercise these route callsites; this runtime guard prevents a harness
    # invocation against a different route implementation.
    # Read source text rather than importing api.py: its module import calls
    # load_dotenv(), which is expressly outside this harness's credential path.
    api_source = (REPO_ROOT / "api.py").read_text(encoding="utf-8")
    parsed_api = ast.parse(api_source)
    functions = {node.name: node for node in ast.walk(parsed_api) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    standard_node = functions.get("pitanje")
    streaming_node = functions.get("pitanje_stream")
    if not standard_node or not streaming_node:
        raise RuntimeError("Question API variants not found in candidate source")
    lines = api_source.splitlines()
    standard = "\n".join(lines[standard_node.lineno - 1:standard_node.end_lineno])
    streaming = "\n".join(lines[streaming_node.lineno - 1:streaming_node.end_lineno])
    if "rezultat = await pokreni(ask_agent, pitanje_za_agenta, history, None, _mem_ctx)" not in standard:
        raise RuntimeError("Standard question route is not the pinned ACL-safe call path")
    if "rezultat = await pokreni(ask_agent, req.pitanje, history_obj, None, _stream_mem_ctx)" not in streaming:
        raise RuntimeError("Streaming question route is not the pinned ACL-safe call path")
    main_blob = _git_blob_sha("main.py")
    cache_source_matches = main_blob == EXPECTED_CACHE_MAIN_BLOB
    if require_cache_source and not cache_source_matches:
        raise RuntimeError("Candidate main.py differs from the pinned authenticated-cache contract")
    if cache_source_matches:
        main_source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        parsed_main = ast.parse(main_source)
        main_functions = {node.name: node for node in ast.walk(parsed_main) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in ("_cache_get", "_cache_set"):
            node = main_functions.get(name)
            if not _has_authenticated_cache_bypass(node):
                raise RuntimeError(f"Authenticated private-RAG cache bypass missing in {name}")
    return cache_source_matches


def _preflight(*, require_credentials: bool, require_approval: bool = True) -> dict[str, Any]:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key, "").strip()]
    if require_credentials and missing:
        raise MissingEnvError(missing)
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    project_match = re.fullmatch(r"https://([a-z0-9-]+)\.supabase\.co", url, re.I)
    project_ref = project_match.group(1) if project_match else None
    if url and project_ref != EXPECTED_PROJECT_REF:
        raise RuntimeError("Supabase target is not the pre-approved project; no writes performed")
    index_name = os.environ.get("PINECONE_INDEX_NAME", "").strip()
    if index_name and index_name != EXPECTED_INDEX:
        raise RuntimeError("Pinecone index is not the expected existing index; no writes performed")
    host = os.environ.get("PINECONE_HOST", "").strip().lower()
    if host and ("/" in host or "://" in host or not host.endswith("pinecone.io")):
        raise RuntimeError("Pinecone host format is invalid; no writes performed")
    host_fingerprint = hashlib.sha256(host.encode()).hexdigest()[:12] if host else None
    approval_marker = (
        f"{PINNED_SOURCE_SHA}:{project_ref}:{index_name or EXPECTED_INDEX}:{host_fingerprint}"
        if project_ref and host_fingerprint else None
    )
    if require_credentials and require_approval and os.environ.get("VINDEX_PRIVATE_RAG_AB_APPROVAL") != approval_marker:
        raise RuntimeError("One-run marker must exactly match the displayed project/index/host fingerprint")
    import subprocess
    candidate_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
        cwd=REPO_ROOT,
    ).stdout.strip()
    return {
        "missing": missing,
        "supabase_project_ref": project_ref,
        "pinecone_index_name": index_name or EXPECTED_INDEX,
        "pinecone_host_fingerprint": host_fingerprint,
        "approval_marker": approval_marker,
        "candidate_sha": candidate_sha,
        "application_source_sha": PINNED_SOURCE_SHA,
        "writes": 0,
        "openai_chat_completions": 0,
        "max_vectors": VECTOR_LIMIT,
        "max_queries": MAX_QUERIES,
    }


def _safe_error(exc: Exception, *, stage: str, mutation_attempted: bool, manifest_path: Path | None) -> dict[str, Any]:
    """Return useful failure identity without serializing provider messages/secrets."""
    structured = getattr(exc, "details", None)
    if isinstance(structured, dict):
        return structured
    detail: dict[str, Any] = {
        "stage": stage,
        "exception_type": type(exc).__name__,
        "remote_mutation_attempted": mutation_attempted,
        "manifest_path": str(manifest_path) if manifest_path else None,
    }
    module = getattr(exc, "name", None)
    if isinstance(module, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", module):
        detail["missing_module"] = module
    missing_names = getattr(exc, "missing_names", None)
    if isinstance(missing_names, list) and all(isinstance(x, str) and x in REQUIRED_ENV for x in missing_names):
        detail["missing_variables"] = missing_names
    for key in ("status", "status_code"):
        value = getattr(exc, key, None)
        if isinstance(value, int) and 100 <= value <= 599:
            detail["http_status"] = value
            break
    if stage.startswith("pinecone.") and "http_status" in detail:
        detail["provider_reason_category"] = {
            400: "request_validation_rejected",
            401: "provider_authentication_rejected",
            403: "provider_authorization_rejected",
            404: "provider_resource_not_found",
            409: "provider_conflict",
            429: "provider_rate_limited",
        }.get(detail["http_status"],
              "provider_server_error" if detail["http_status"] >= 500 else "provider_request_rejected")
    code = getattr(exc, "code", None)
    normalized_code = str(code).upper() if isinstance(code, (str, int)) else ""
    if normalized_code in SAFE_PROVIDER_ERROR_CODES:
        detail["provider_code"] = normalized_code
    return detail


def _load_runtime_dependencies() -> None:
    """Import the actual Vindex token path without granting harness identities privileges."""
    import importlib

    if not os.environ.get("FOUNDER_EMAILS", "").strip():
        # shared.deps validates this at import time. This process-local sentinel
        # is deliberately unrelated to the generated synthetic identities.
        os.environ["FOUNDER_EMAILS"] = FOUNDER_SENTINEL
    elif FOUNDER_SENTINEL in {x.strip().lower() for x in os.environ["FOUNDER_EMAILS"].split(",")}:
        raise RuntimeError("FOUNDER_EMAILS collides with the harness-only sentinel")
    for name in ("supabase", "pinecone", "shared.deps", "app.services.retrieve", "shared.rag_acl", "shared.kancelarija_utils", "shared.ai_provenance"):
        importlib.import_module(name)


def _read_manifest_paths() -> list[Path]:
    home = _manifest_home()
    return sorted(home.glob("run_*.json")) if home.exists() else []


def _exact_db_rows(service, table: str, row_id: str, columns: str = "*") -> list[dict[str, Any]]:
    response = service.table(table).select(columns).eq("id", row_id).limit(1).execute()
    rows = getattr(response, "data", None)
    if not isinstance(rows, list):
        raise RuntimeError(f"Incomplete exact-row response for {table}:{row_id}")
    return rows


def _auth_users_page(service, *, page: int, per_page: int) -> list[Any]:
    response = service.auth.admin.list_users(page=page, per_page=per_page)
    # Supabase Python SDK versions return the page as a list directly; some
    # compatible wrappers expose the same list through ``.users``. Accept both
    # verified shapes, while rejecting absent or malformed page data.
    users = response if isinstance(response, list) else getattr(response, "users", None)
    if not isinstance(users, list):
        raise RuntimeError("Incomplete exact synthetic Auth listing response")
    return users


def _inspect_legacy_manifest(service, index, path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Read-only exact-resource reconciliation for schema-1 manifests."""
    _validate_manifest_for_cleanup(manifest)
    vectors_present: list[str] = []
    for vector in manifest["vectors"]:
        try:
            response = index.fetch(ids=[vector["id"]], namespace=vector["namespace"])
            found = getattr(response, "vectors", {}) or {}
            if vector["id"] in found:
                vectors_present.append(vector["id"])
        except Exception as exc:
            raise RuntimeError(f"Could not reconcile exact legacy vector id {vector['id']}: {type(exc).__name__}") from None
    db_present: list[str] = []
    for table, ids in (("predmet_delegiranja", [manifest["delegation"]]),
                       ("kancelarija_clanovi", list(manifest["memberships"].values())),
                       ("predmeti", list(manifest["matters"].values())),
                       ("kancelarije", [manifest["office"]["id"]])):
        for row_id in ids:
            try:
                rows = _exact_db_rows(service, table, row_id, "id")
            except Exception as exc:
                raise RuntimeError(f"Could not reconcile exact legacy database id {row_id}: {type(exc).__name__}") from None
            if rows:
                db_present.append(f"{table}:{row_id}")
    auth_present: list[str] = []
    unresolved_users: list[str] = []
    for record in manifest["users"].values():
        user_id = record.get("id")
        try:
            if user_id:
                response = service.auth.admin.get_user_by_id(user_id)
                user = getattr(response, "user", None)
                if user and (getattr(user, "email", None) == record["email"] and
                             (getattr(user, "user_metadata", {}) or {}).get("vindex_private_rag_ab_run") == manifest["run_id"]):
                    auth_present.append(str(user_id))
                elif user:
                    unresolved_users.append("identity-mismatch:" + str(user_id))
                else:
                    unresolved_users.append("incomplete-user-response:" + str(user_id))
            else:
                page = 1
                found = None
                while True:
                    users = _auth_users_page(service, page=page, per_page=100)
                    found = next((u for u in users if getattr(u, "email", None) == record["email"]), None)
                    if found or len(users) < 100:
                        break
                    page += 1
                if found:
                    if (getattr(found, "user_metadata", {}) or {}).get("vindex_private_rag_ab_run") == manifest["run_id"]:
                        auth_present.append(str(found.id))
                    else:
                        unresolved_users.append("identity-mismatch:" + record["email"])
        except Exception as exc:
            if _auth_not_found(exc):
                continue
            unresolved_users.append(type(exc).__name__ + ":" + record["email"])
    return {"manifest": str(path), "run_id": manifest["run_id"], "vectors_present": vectors_present,
            "database_rows_present": db_present, "auth_users_present": auth_present,
            "unresolved_auth_emails": unresolved_users,
            "reconciled_absent": not vectors_present and not db_present and not auth_present and not unresolved_users}


def _preflight_live(*, expected_sha: str | None = None) -> dict[str, Any]:
    """Read-only provider preflight. No Auth, DB, or Pinecone writes are issued."""
    target = _preflight(require_credentials=True, require_approval=False)
    if expected_sha and target["candidate_sha"] != expected_sha:
        raise RuntimeError("Current checkout does not match --expected-sha")
    _require_source_pin(require_cache_source=True)
    _load_runtime_dependencies()
    from pinecone import Pinecone

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    description = pc.describe_index(target["pinecone_index_name"])
    described_host = str(getattr(description, "host", "")).strip().lower()
    configured_host = os.environ["PINECONE_HOST"].strip().lower()
    if not described_host or described_host != configured_host:
        raise RuntimeError("Configured Pinecone host does not match the named index metadata")
    if getattr(description, "dimension", None) != VECTOR_DIM:
        raise RuntimeError("Pinecone index dimension does not match the pinned Vindex contract")
    index = pc.Index(host=os.environ["PINECONE_HOST"].strip())
    service, _ = _auth_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"], os.environ["SUPABASE_SERVICE_KEY"])
    # An authenticated admin list call proves read access only; the result is
    # intentionally discarded to avoid logging account data.
    _auth_users_page(service, page=1, per_page=1)
    cleanup_capabilities = {
        "pinecone_exact_id_delete_method": callable(getattr(index, "delete", None)),
        "supabase_table_delete_method": callable(getattr(service.table("predmeti"), "delete", None)),
        "supabase_auth_delete_user_method": callable(getattr(service.auth.admin, "delete_user", None)),
    }
    if not all(cleanup_capabilities.values()):
        raise RuntimeError("Required exact-scope cleanup methods are unavailable")
    old_runs = []
    for path in _read_manifest_paths():
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            old_runs.append(_inspect_legacy_manifest(service, index, path, manifest))
        except Exception as exc:
            old_runs.append({"manifest": str(path), "blocked": type(exc).__name__})
    unresolved = [r for r in old_runs if r.get("blocked") or not r.get("reconciled_absent", False)]
    if unresolved:
        raise RuntimeError("Prior synthetic run requires exact reconciliation; no new writes permitted: " + json.dumps(unresolved, sort_keys=True))
    return {**target, "provider_reads": {"pinecone_describe_index": 1, "supabase_admin_list_users": 1,
            "prior_manifest_exact_checks": len(old_runs)}, "cleanup_capabilities": cleanup_capabilities,
            "prior_runs": old_runs, "writes": 0,
            "preflight_live": True}


def _new_manifest() -> dict[str, Any]:
    run = uuid.uuid4().hex
    office_id = str(uuid.uuid4())
    matters = {role: str(uuid.uuid4()) for role in ("A", "B", "C")}
    return {
        "schema": 2,
        "run_id": run,
        "source_sha": PINNED_SOURCE_SHA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target": {},
        "state": "planned",
        "users": {
            role: {"id": None, "email": f"vindex-ab-{run}-{role.lower()}@example.invalid",
                  "write_state": "NOT_ATTEMPTED"}
            for role in ("A", "B", "C", "D")
        },
        "office": {"id": office_id},
        "memberships": {role: str(uuid.uuid4()) for role in ("C", "D")},
        "matters": matters,
        "delegation": str(uuid.uuid4()),
        "database_writes": [],
        "delegation_update": {"write_state": "NOT_ATTEMPTED"},
        "vectors": [
            {"id": f"vindex-ab-{run}-a", "namespace": f"kancelarija_{office_id}", "matter": "A", "owner": "A", "write_state": "NOT_ATTEMPTED"},
            {"id": f"vindex-ab-{run}-c", "namespace": f"kancelarija_{office_id}", "matter": "C", "owner": "C", "write_state": "NOT_ATTEMPTED"},
            {"id": f"vindex-ab-{run}-b", "namespace": "user__pending__B", "matter": "B", "owner": "B", "write_state": "NOT_ATTEMPTED"},
            {"id": f"vindex-ab-{run}-tmp-a", "namespace": f"tmp_{run}", "matter": "A", "owner": "A", "temporary": True, "write_state": "NOT_ATTEMPTED"},
        ],
        "assertions": [],
        "cleanup": {"attempted": False, "verified": False, "errors": []},
    }


def _auth_client(url: str, anon_key: str, service_key: str):
    from supabase import create_client

    return create_client(url, service_key), create_client(url, anon_key)


def _create_auth_users(service, anon, manifest: dict[str, Any]) -> dict[str, str]:
    from shared.deps import _verify_token

    result: dict[str, str] = {}
    for role, record in manifest["users"].items():
        password = secrets.token_urlsafe(32)
        record["write_state"] = "ATTEMPTED_UNKNOWN"
        manifest["stage"] = f"auth.create_user.{role}"
        _write_manifest(_active_manifest_path(manifest), manifest)
        created = service.auth.admin.create_user({
            "email": record["email"],
            "password": password,
            "email_confirm": True,
            "user_metadata": {"vindex_private_rag_ab_run": manifest["run_id"]},
        })
        created_user = getattr(created, "user", None)
        if not created_user or not getattr(created_user, "id", None):
            raise RuntimeError(f"Synthetic auth user creation was not confirmed for role {role}")
        record["id"] = str(created_user.id)
        record["write_state"] = "CONFIRMED_CREATED"
        if role == "B":
            b_vector = next((v for v in manifest["vectors"] if v.get("id") == f"vindex-ab-{manifest['run_id']}-b"), None)
            if b_vector is None:
                raise RuntimeError("Manifest is missing the exact synthetic B vector")
            b_vector["namespace"] = f"user_{record['id']}"
        _write_manifest(_active_manifest_path(manifest), manifest)
        session = anon.auth.sign_in_with_password({"email": record["email"], "password": password})
        access_token = getattr(getattr(session, "session", None), "access_token", None)
        if not access_token:
            raise RuntimeError(f"Synthetic auth sign-in failed for role {role}")
        anon.auth.set_session(access_token, session.session.refresh_token)
        verified = anon.auth.get_user()
        verified_user = getattr(verified, "user", None)
        if not verified_user or str(verified_user.id) != record["id"]:
            raise RuntimeError(f"Supabase did not verify test identity {role}")
        # Exercise the existing Vindex verifier with the real synthetic
        # Supabase access token; no model completion is involved. This harness
        # does not dispatch the HTTP route, so the verified subject is later
        # installed into the request-scoped context directly.
        with patch("shared.deps._get_supa", return_value=service):
            payload = _verify_token(access_token)
        if not payload or str(payload.get("sub") or "") != record["id"]:
            raise RuntimeError(f"Vindex JWT verifier did not derive the expected identity for role {role}")
        result[role] = str(payload["sub"])
        # Never persist or log the generated password or bearer token.
    return result


def _active_manifest_path(manifest: dict[str, Any]) -> Path:
    path = manifest.get("_manifest_path")
    if not path:
        raise RuntimeError("Recovery manifest path was not bound before writes")
    return Path(path)


def _seed_rows(service, manifest: dict[str, Any], path: Path) -> None:
    run = manifest["run_id"]
    users = {role: row["id"] for role, row in manifest["users"].items()}
    office = manifest["office"]["id"]
    writes = manifest["database_writes"]
    planned = [
      ("office", "kancelarije", manifest["office"]["id"], {
        "id": office, "naziv": f"Vindex synthetic A/B {run[:8]}", "admin_uid": users["A"],
      }),
    ]
    for role in ("A", "B", "C"):
        planned.append((f"matter_{role}", "predmeti", manifest["matters"][role], {
            "id": manifest["matters"][role],
            "user_id": users[role],
            "naziv": f"Vindex synthetic A/B {run[:8]} {role}",
            "opis": "Synthetic retrieval isolation fixture; no client data.",
            "tip": "opsti",
            "status": "aktivan",
        }))
    for role in ("C", "D"):
        planned.append((f"membership_{role}", "kancelarija_clanovi", manifest["memberships"][role], {
            "id": manifest["memberships"][role],
            "kancelarija_id": office,
            "email": manifest["users"][role]["email"],
            "user_id": users[role],
            "uloga": "advokat",
            "status": "ACTIVE",
            "invited_by": users["A"],
            "joined_at": datetime.now(timezone.utc).isoformat(),
        }))
    planned.append(("delegation", "predmet_delegiranja", manifest["delegation"], {
        "id": manifest["delegation"],
        "predmet_id": manifest["matters"]["A"],
        "od_user_id": users["A"],
        "na_user_id": users["D"],
        "napomena": f"Synthetic private RAG A/B run {run}",
        "status": "aktivno",
    }))
    for key, table, row_id, payload in planned:
        item = {"key": key, "table": table, "id": row_id, "write_state": "ATTEMPTED_UNKNOWN"}
        writes.append(item)
        manifest["stage"] = f"database.insert.{key}"
        _write_manifest(path, manifest)
        service.table(table).insert(payload).execute()
        item["write_state"] = "CONFIRMED_CREATED"
        _write_manifest(path, manifest)


def _fixture_vector(role: str, run_id: str, *, temporary: bool = False) -> dict[str, Any]:
    # Fixed synthetic vector; the real Pinecone index and Vindex filtering/query
    # are exercised. No OpenAI embedding or chat-completion request is made.
    kind = "TMP" if temporary else "CASE"
    text = f"SYNTHETIC_PRIVATE_RAG_AB_{run_id}_{kind}_{role}_CONTENT"
    return {
        "text": text,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "values": [1.0] + [0.0] * (VECTOR_DIM - 1),
    }


def _validate_vector_payloads(vectors_by_namespace: dict[str, list[dict[str, Any]]]) -> None:
    """Validate exact SDK 8.1.1 request objects before any fixture mutation."""
    from importlib.metadata import version
    from pinecone import Vector as PineconeVector

    if version("pinecone") != PINNED_PINECONE_SDK_VERSION:
        raise RuntimeError("Pinecone SDK version does not match the pinned wire contract")
    count = 0
    seen_ids: set[str] = set()
    for namespace, vectors in vectors_by_namespace.items():
        if not isinstance(namespace, str) or not namespace or not isinstance(vectors, list):
            raise RuntimeError("Pinecone namespace/vector payload is malformed")
        for vector in vectors:
            count += 1
            if not isinstance(vector, dict) or set(vector) != {"id", "values", "metadata"}:
                raise RuntimeError("Pinecone vector payload fields are malformed")
            vector_id, values, metadata = vector["id"], vector["values"], vector["metadata"]
            if not isinstance(vector_id, str) or not vector_id or vector_id in seen_ids:
                raise RuntimeError("Pinecone vector ID is malformed or duplicated")
            seen_ids.add(vector_id)
            if (not isinstance(values, list) or len(values) != VECTOR_DIM
                    or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
                           for x in values)):
                raise RuntimeError("Pinecone vector values must be finite numbers at the pinned dimension")
            if not isinstance(metadata, dict) or not metadata:
                raise RuntimeError("Pinecone vector metadata is malformed")
            for key, value in metadata.items():
                if not isinstance(key, str) or not key:
                    raise RuntimeError("Pinecone metadata key is malformed")
                if isinstance(value, str) or isinstance(value, bool) or isinstance(value, int):
                    continue
                if isinstance(value, float) and math.isfinite(value):
                    continue
                if isinstance(value, list) and all(isinstance(item, str) for item in value):
                    continue
                raise RuntimeError("Pinecone metadata contains an unsupported value type")
            try:
                wire_vector = PineconeVector(id=vector_id, values=values, metadata=metadata).to_dict()
            except Exception as exc:
                raise RuntimeError("Pinecone SDK rejected the synthetic vector payload") from exc
            if wire_vector != vector:
                raise RuntimeError("Pinecone SDK serialization changed the synthetic vector payload")
    if count != 4 or count > VECTOR_LIMIT:
        raise RuntimeError("Synthetic Pinecone fixture must contain exactly four bounded vectors")


def _build_vector_payloads(
    manifest: dict[str, Any], uids: dict[str, str] | None = None, *, preflight: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Build and validate the single vector payload path used by preflight and execute."""
    vectors_by_namespace: dict[str, list[dict[str, Any]]] = {}
    seen_ids: set[str] = set()
    for vector in manifest["vectors"]:
        role = vector["owner"]
        user_id = (uids or {}).get(role) or manifest["users"][role].get("id")
        if not user_id and preflight:
            user_id = f"preflight-{role}-{manifest['run_id']}"
        if not isinstance(user_id, str) or not user_id:
            raise RuntimeError(f"Verified fixture identity is missing for role {role}")
        if role == "B":
            namespace = f"user_{user_id}" if not preflight or manifest["users"]["B"].get("id") else "user__pending__B"
            if not preflight:
                vector["namespace"] = namespace
        else:
            namespace = vector["namespace"]
        if vector["id"] in seen_ids:
            raise RuntimeError("Synthetic vector ID is duplicated")
        seen_ids.add(vector["id"])
        temporary = bool(vector.get("temporary"))
        fixture = _fixture_vector(role, manifest["run_id"], temporary=temporary)
        vector["text_sha256"] = fixture["text_sha256"]
        metadata = {
            "type": "tmp_doc" if temporary else "case_doc",
            "predmet_id": manifest["matters"][vector["matter"]],
            "owner_user_id": user_id,
            "text": fixture["text"],
            "source_filename": "synthetic-fixture.txt",
        }
        # A private owner namespace is not an office-membership assertion.
        # Omit the field for independent tenant B instead of serializing null.
        if role in ("A", "C", "D"):
            metadata["kancelarija_id"] = manifest["office"]["id"]
        vectors_by_namespace.setdefault(namespace, []).append({
            "id": vector["id"], "values": fixture["values"], "metadata": metadata,
        })
    _validate_vector_payloads(vectors_by_namespace)
    return vectors_by_namespace


def _validate_manifest_for_cleanup(manifest: dict[str, Any]) -> None:
    """Reject a modified recovery manifest before it can name deletion targets."""
    run = manifest.get("run_id")
    schema = manifest.get("schema")
    if schema not in (1, 2) or manifest.get("source_sha") != PINNED_SOURCE_SHA:
        raise RuntimeError("Manifest schema/source pin is not supported")
    if not isinstance(run, str) or not re.fullmatch(r"[0-9a-f]{32}", run):
        raise RuntimeError("Manifest run id is malformed")
    users = manifest.get("users")
    if not isinstance(users, dict) or set(users) != {"A", "B", "C", "D"}:
        raise RuntimeError("Manifest identity set is malformed")
    for role, record in users.items():
        if schema == 2 and record.get("write_state") not in WRITE_STATES:
            raise RuntimeError(f"Manifest auth write state is malformed for role {role}")
        if record.get("email") != f"vindex-ab-{run}-{role.lower()}@example.invalid":
            raise RuntimeError(f"Manifest synthetic email mismatch for role {role}")
        user_id = record.get("id")
        if user_id is not None:
            try:
                uuid.UUID(str(user_id))
            except (ValueError, TypeError, AttributeError) as exc:
                raise RuntimeError(f"Manifest user id is malformed for role {role}") from exc
    office_id = manifest.get("office", {}).get("id")
    matters = manifest.get("matters")
    memberships = manifest.get("memberships")
    delegation = manifest.get("delegation")
    try:
        uuid.UUID(str(office_id))
        uuid.UUID(str(delegation))
        if not isinstance(matters, dict) or set(matters) != {"A", "B", "C"}:
            raise ValueError("matter roles")
        for value in matters.values():
            uuid.UUID(str(value))
        if not isinstance(memberships, dict) or set(memberships) != {"C", "D"}:
            raise ValueError("membership roles")
        for value in memberships.values():
            uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise RuntimeError("Manifest database ids are malformed") from exc

    vectors = manifest.get("vectors")
    if not isinstance(vectors, list) or len(vectors) > VECTOR_LIMIT:
        raise RuntimeError("Manifest vector set is malformed or exceeds the cap")
    if schema == 2 and any(
        not isinstance(v, dict) or v.get("write_state") not in WRITE_STATES for v in vectors
    ):
        raise RuntimeError("Manifest vector write state is malformed")

    b_vector_id = f"vindex-ab-{run}-b"
    b_vector = next((v for v in vectors if isinstance(v, dict) and v.get("id") == b_vector_id), None)
    b_namespace = f"user_{users['B']['id']}" if users["B"]["id"] else "user__pending__B"
    # A pre-upsert interrupted fixture may still have the planned placeholder
    # even after Auth creation. Permit that exact state only while no Pinecone
    # write was ever journaled; attempted/ambiguous writes must name user B's
    # canonical namespace so cleanup cannot target a different namespace.
    if (schema == 2 and users["B"]["id"] and b_vector is not None
            and b_vector.get("namespace") == "user__pending__B"
            and b_vector.get("write_state") == "NOT_ATTEMPTED"):
        b_namespace = "user__pending__B"

    expected_vectors = {
        f"vindex-ab-{run}-a": (f"kancelarija_{office_id}", "A", "A", False),
        f"vindex-ab-{run}-c": (f"kancelarija_{office_id}", "C", "C", False),
        b_vector_id: (b_namespace, "B", "B", False),
        f"vindex-ab-{run}-tmp-a": (f"tmp_{run}", "A", "A", True),
    }
    observed = {}
    for vector in vectors:
        if not isinstance(vector, dict):
            raise RuntimeError("Manifest vector entry is malformed")
        observed[vector.get("id")] = (
            vector.get("namespace"), vector.get("matter"), vector.get("owner"),
            bool(vector.get("temporary")),
        )
    if observed != expected_vectors:
        raise RuntimeError("Manifest vector IDs/namespaces do not match this synthetic run")
    if schema == 2:
        if not isinstance(manifest.get("database_writes"), list):
            raise RuntimeError("Manifest database write journal is malformed")
        if manifest.get("delegation_update", {}).get("write_state") not in WRITE_STATES:
            raise RuntimeError("Manifest delegation write state is malformed")
        permitted = {
            ("kancelarije", str(office_id)),
            *(('predmeti', str(v)) for v in matters.values()),
            *(('kancelarija_clanovi', str(v)) for v in memberships.values()),
            ("predmet_delegiranja", str(delegation)),
        }
        seen = set()
        for item in manifest["database_writes"]:
            key = (item.get("table"), str(item.get("id")))
            if key not in permitted or key in seen or item.get("write_state") not in WRITE_STATES:
                raise RuntimeError("Manifest database write journal contains an invalid target or state")
            seen.add(key)


def _synthetic_row_expectation(manifest: dict[str, Any], table: str, row_id: str) -> dict[str, Any]:
    run = manifest["run_id"]
    users = {role: row["id"] for role, row in manifest["users"].items()}
    if table == "kancelarije" and row_id == manifest["office"]["id"]:
        return {"id": row_id, "naziv": f"Vindex synthetic A/B {run[:8]}", "admin_uid": users["A"]}
    for role, matter_id in manifest["matters"].items():
        if table == "predmeti" and row_id == matter_id:
            return {
                "id": row_id, "user_id": users[role],
                "naziv": f"Vindex synthetic A/B {run[:8]} {role}",
            }
    for role, membership_id in manifest["memberships"].items():
        if table == "kancelarija_clanovi" and row_id == membership_id:
            return {
                "id": row_id, "kancelarija_id": manifest["office"]["id"],
                "email": manifest["users"][role]["email"], "user_id": users[role],
                "status": "ACTIVE",
            }
    if table == "predmet_delegiranja" and row_id == manifest["delegation"]:
        return {
            "id": row_id, "predmet_id": manifest["matters"]["A"],
            "od_user_id": users["A"], "na_user_id": users["D"],
            "napomena": f"Synthetic private RAG A/B run {run}",
        }
    raise RuntimeError("Manifest requested a database deletion outside its synthetic fixture")


def _auth_not_found(exc: Exception) -> bool:
    return getattr(exc, "status", None) == 404 or getattr(exc, "status_code", None) == 404


def _retrieval(index, service, uid: str, *, extra: list[str] | None = None,
               foreign_namespace: str | None = None, fail_acl: bool = False,
               dozvoljeni_predmeti: list[str] | None = None):
    from shared.ai_provenance import scoped_request_context
    import app.services.retrieve as R
    from shared import deps

    query_vec = [1.0] + [0.0] * (VECTOR_DIM - 1)
    query_trace: list[dict[str, Any]] = []
    original_pretraga = R._pretraga_ns

    def traced_pretraga(vector, namespace, k=5, filter=None):
        query_trace.append({"namespace": namespace, "filter": filter, "top_k": k})
        return original_pretraga(vector, namespace, k=k, filter=filter)

    patches = [
        patch.object(R, "_get_index", return_value=index),
        patch.object(R, "_ugradi_query", return_value=query_vec),
        patch.object(R, "_dekomponuj_query", return_value=[]),
        patch.object(R, "decompose_query", return_value=[]),
        patch.object(R, "_generiši_hyde", return_value=""),
        patch.object(R, "_pretraga_praksa", return_value=[]),
        patch.object(R, "_jedan_retrieval_krug", return_value=([], {})),
        patch.object(R, "_cohere_rerank", side_effect=lambda q, ms, k=3: list(ms)[:k]),
        patch.object(R, "_crag_petlja", side_effect=lambda _q, docs, *a, **k: docs),
        patch.object(R, "_prosiri_query_gpt_wrapper", return_value=[]),
        patch.object(R, "_karantin_chunka", return_value=(False, 0.0)),
        patch.object(R, "_pretraga_ns", side_effect=traced_pretraga),
        patch.object(deps, "_get_supa", return_value=service),
    ]
    if fail_acl:
        patches.append(patch("shared.rag_acl.dozvoljeni_predmeti", side_effect=RuntimeError("synthetic ACL outage")))
    for item in patches:
        item.start()
    try:
        with scoped_request_context(user_id=uid):
            docs, meta = R.retrieve_documents(
                "synthetic private RAG isolation marker", k=6,
                extra_namespaces=extra,
                kancelarija_namespace=foreign_namespace,
                # Normal runs use the server-derived ACL. The optional value
                # is reserved for a distinct adversarial expansion attempt.
                dozvoljeni_predmeti=dozvoljeni_predmeti,
            )
            return docs, meta, query_trace
    finally:
        for item in reversed(patches):
            item.stop()


def _contains(docs: list[str], meta: dict[str, Any], marker: str) -> bool:
    return marker in "\n".join(docs) or marker in json.dumps(meta, ensure_ascii=False, default=str)


def _ab_query_scenarios(manifest: dict[str, Any], uids: dict[str, str]) -> list[dict[str, Any]]:
    run = manifest["run_id"]
    office_ns = f"kancelarija_{manifest['office']['id']}"
    markers = {role: _fixture_vector(role, run)["text"] for role in "ABCD"}
    markers["A_tmp"] = _fixture_vector("A", run, temporary=True)["text"]
    return [
        {"name": "A_owner_positive", "role": "A", "markers": [markers["A"]], "positive": True},
        {"name": "B_owner_positive", "role": "B", "markers": [markers["B"]], "positive": True},
        {"name": "C_owner_positive", "role": "C", "markers": [markers["C"]], "positive": True},
        {"name": "B_cannot_read_A", "role": "B", "markers": [markers["A"]], "positive": False,
         "extra": [office_ns, f"user_{uids['A']}", f"tmp_{run}"], "foreign": office_ns},
        {"name": "C_same_office_denied", "role": "C", "markers": [markers["A"]], "positive": False,
         "extra": [office_ns], "foreign": office_ns},
        {"name": "D_delegated_A_positive", "role": "D", "markers": [markers["A"]], "positive": True},
        {"name": "D_not_C", "role": "D", "markers": [markers["C"]], "positive": False},
        {"name": "A_temp_positive", "role": "A", "markers": [markers["A_tmp"]], "positive": True,
         "extra": [f"tmp_{run}"]},
        {"name": "C_foreign_temp_denied", "role": "C", "markers": [markers["A_tmp"]], "positive": False,
         "extra": [f"tmp_{run}"]},
        {"name": "C_explicit_foreign_namespace_denied", "role": "C", "markers": [markers["A"]],
         "positive": False, "foreign": f"user_{uids['A']}"},
        {"name": "C_extra_private_namespaces_denied", "role": "C", "markers": [markers["A"]],
         "positive": False, "extra": [office_ns, f"user_{uids['A']}"]},
        {"name": "A_acl_failure_fail_closed", "role": "A", "markers": [markers["A"]],
         "positive": False, "foreign": office_ns, "fail_acl": True},
        {"name": "U_missing_identity_fail_closed", "role": None, "markers": [markers["A"]],
         "positive": False, "extra": [f"tmp_{run}"], "foreign": office_ns},
        {"name": "C_attacker_acl_expansion_denied", "role": "C", "markers": [markers["A"]],
         "positive": False, "requested_acl": [manifest["matters"]["A"]], "expect_no_queries": True},
    ]


def _run_ab_query_scenario(index, service, scenario: dict[str, Any], uids: dict[str, str]) -> dict[str, Any]:
    role = scenario["role"]
    docs, meta, query_trace = _retrieval(
        index, service, uids[role] if role else None,
        extra=scenario.get("extra"), foreign_namespace=scenario.get("foreign"),
        fail_acl=bool(scenario.get("fail_acl")),
        dozvoljeni_predmeti=scenario.get("requested_acl"),
    )
    content = json.dumps({"docs": docs, "meta": meta}, ensure_ascii=False, default=str)
    present = [marker in content for marker in scenario["markers"]]
    passed = all(present) if scenario["positive"] else not any(present)
    if scenario.get("expect_no_queries"):
        passed = passed and not query_trace
    return {
        "name": scenario["name"], "role": role,
        "expected_positive": bool(scenario["positive"]),
        "marker_hashes": [hashlib.sha256(m.encode()).hexdigest() for m in scenario["markers"]],
        "marker_present": present, "passed": passed, "pinecone_queries": query_trace,
    }


def _clean(service, index, path: Path, manifest: dict[str, Any]) -> None:
    _validate_manifest_for_cleanup(manifest)
    if manifest.get("schema") != 2:
        raise RuntimeError("Legacy manifest has no durable write journal; cleanup mutation is forbidden")
    manifest["cleanup"]["attempted"] = True
    _write_manifest(path, manifest)
    errors: list[str] = []
    eligible_vectors = [v for v in manifest["vectors"] if v["write_state"] in {"ATTEMPTED_UNKNOWN", "CONFIRMED_CREATED", "CLEANUP_FAILED"}]
    for ns in sorted({v["namespace"] for v in eligible_vectors}):
        items = [v for v in eligible_vectors if v["namespace"] == ns]
        ids = [v["id"] for v in items]
        try:
            # A successful exact-ID fetch proving absence avoids an unnecessary
            # delete. A fetch error is not evidence of absence.
            before = getattr(index.fetch(ids=ids, namespace=ns), "vectors", {}) or {}
            present = [v for v in items if v["id"] in before]
            for item in present:
                record = before[item["id"]]
                metadata = getattr(record, "metadata", None) or (record.get("metadata", {}) if isinstance(record, dict) else {})
                expected_text = _fixture_vector(
                    item["owner"], manifest["run_id"], temporary=bool(item.get("temporary"))
                )["text"]
                expected_owner = manifest["users"][item["owner"]].get("id")
                expected_matter = manifest["matters"][item["matter"]]
                expected_type = "tmp_doc" if item.get("temporary") else "case_doc"
                if (metadata.get("text") != expected_text or metadata.get("owner_user_id") != expected_owner
                        or metadata.get("predmet_id") != expected_matter or metadata.get("type") != expected_type):
                    raise RuntimeError(f"Refusing cleanup of exact vector ID with non-synthetic metadata: {item['id']}")
            for v in items:
                if v["id"] not in before:
                    v["write_state"] = "CONFIRMED_ABSENT"
            if present:
                for v in present:
                    v["write_state"] = "ATTEMPTED_UNKNOWN"
                manifest["stage"] = f"pinecone.delete.{ns}"
                _write_manifest(path, manifest)
                index.delete(ids=[v["id"] for v in present], namespace=ns)
            remaining_ids = set(ids)
            for attempt in range(8):
                remaining = getattr(index.fetch(ids=ids, namespace=ns), "vectors", {}) or {}
                remaining_ids = {i for i in ids if i in remaining}
                if not remaining_ids:
                    break
                if attempt < 7:
                    import time
                    time.sleep(1)
            if remaining_ids:
                errors.append(f"vector cleanup not verified: namespace={ns}, ids={sorted(remaining_ids)}")
                for v in items:
                    if v["id"] in remaining_ids:
                        v["write_state"] = "CLEANUP_FAILED"
            else:
                for v in items:
                    v["write_state"] = "CONFIRMED_ABSENT"
            _write_manifest(path, manifest)
        except Exception as exc:
            errors.append(f"vector cleanup failed for exact namespace {ns}: {type(exc).__name__}")
            for v in items:
                if v["write_state"] != "CONFIRMED_ABSENT":
                    v["write_state"] = "CLEANUP_FAILED"
            _write_manifest(path, manifest)
    # Exact IDs only. No broad deletes or delete_all.
    table_ids = (
        ("predmet_delegiranja", [manifest["delegation"]]),
        ("kancelarija_clanovi", list(manifest["memberships"].values())),
        ("predmeti", list(manifest["matters"].values())),
        ("kancelarije", [manifest["office"]["id"]]),
    )
    attempted_db = {(x["table"], str(x["id"])): x for x in manifest["database_writes"]
                    if x["write_state"] in {"ATTEMPTED_UNKNOWN", "CONFIRMED_CREATED", "CLEANUP_FAILED"}}
    for table, ids in table_ids:
        for row_id in ids:
            item = attempted_db.get((table, str(row_id)))
            if item is None:
                continue
            try:
                expected = _synthetic_row_expectation(manifest, table, row_id)
                existing = _exact_db_rows(service, table, row_id)
                if not existing:
                    item["write_state"] = "CONFIRMED_ABSENT"
                    _write_manifest(path, manifest)
                    continue
                if any(any(row.get(key) != value for key, value in expected.items()) for row in existing):
                    errors.append(f"refusing non-synthetic row cleanup: table={table}, id={row_id}")
                    item["write_state"] = "CLEANUP_FAILED"
                    continue
                item["write_state"] = "ATTEMPTED_UNKNOWN"
                manifest["stage"] = f"database.delete.{table}.{row_id}"
                _write_manifest(path, manifest)
                service.table(table).delete().eq("id", row_id).execute()
                remaining = _exact_db_rows(service, table, row_id, "id")
                if remaining:
                    errors.append(f"row cleanup not verified: table={table}, id={row_id}")
                    item["write_state"] = "CLEANUP_FAILED"
                else:
                    item["write_state"] = "CONFIRMED_ABSENT"
                _write_manifest(path, manifest)
            except Exception as exc:
                errors.append(f"row cleanup failed: table={table}, id={row_id}, error={type(exc).__name__}")
                item["write_state"] = "CLEANUP_FAILED"
                _write_manifest(path, manifest)
    for record in manifest["users"].values():
        if record["write_state"] not in {"ATTEMPTED_UNKNOWN", "CONFIRMED_CREATED", "CLEANUP_FAILED"}:
            continue
        user_id = record.get("id")
        if not user_id and record["write_state"] in {"ATTEMPTED_UNKNOWN", "CLEANUP_FAILED"}:
            # Auth may commit a create-user request whose response is lost.
            # Resolve only this manifest's exact random example.invalid email.
            try:
                page = 1
                while True:
                    candidates = _auth_users_page(service, page=page, per_page=100)
                    match = next((u for u in candidates if getattr(u, "email", None) == record["email"]), None)
                    if match:
                        user_id = str(match.id)
                        record["id"] = user_id
                        _write_manifest(path, manifest)
                        break
                    if len(candidates) < 100:
                        break
                    page += 1
                if not user_id:
                    record["write_state"] = "CONFIRMED_ABSENT"
                    _write_manifest(path, manifest)
            except Exception as exc:
                errors.append(f"exact synthetic auth lookup failed for {record['email']}: {type(exc).__name__}")
        if user_id:
            try:
                try:
                    auth_record = service.auth.admin.get_user_by_id(user_id)
                except Exception as lookup_exc:
                    if _auth_not_found(lookup_exc):
                        record["write_state"] = "CONFIRMED_ABSENT"
                        _write_manifest(path, manifest)
                        continue
                    raise
                auth_user = getattr(auth_record, "user", None)
                if auth_user is None:
                    raise RuntimeError("Incomplete exact Auth user response")
                if auth_user and (
                    getattr(auth_user, "email", None) != record["email"]
                    or (getattr(auth_user, "user_metadata", {}) or {}).get("vindex_private_rag_ab_run") != manifest["run_id"]
                ):
                    errors.append(f"refusing non-synthetic auth cleanup for exact id {user_id}")
                    continue
                if not auth_user:
                    record["write_state"] = "CONFIRMED_ABSENT"
                    _write_manifest(path, manifest)
                    continue
                record["write_state"] = "ATTEMPTED_UNKNOWN"
                manifest["stage"] = f"auth.delete_user.{user_id}"
                _write_manifest(path, manifest)
                service.auth.admin.delete_user(user_id)
                try:
                    still_there = service.auth.admin.get_user_by_id(user_id)
                    errors.append(f"auth cleanup not verified for exact synthetic id {user_id}")
                except Exception as verify_exc:
                    if _auth_not_found(verify_exc):
                        record["write_state"] = "CONFIRMED_ABSENT"
                        _write_manifest(path, manifest)
                    else:
                        errors.append(f"auth cleanup verification failed for exact synthetic id {user_id}: {type(verify_exc).__name__}")
                else:
                    record["write_state"] = "CONFIRMED_ABSENT"
                    _write_manifest(path, manifest)
            except Exception as exc:
                errors.append(f"auth cleanup failed for exact synthetic id {user_id}: {type(exc).__name__}")
                record["write_state"] = "CLEANUP_FAILED"
                _write_manifest(path, manifest)
    manifest["cleanup"]["errors"] = errors
    manifest["cleanup"]["verified"] = not errors
    manifest["state"] = "clean" if not errors else "cleanup_required"
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_manifest(path, manifest)
    if errors:
        raise RuntimeError("Cleanup could not be verified; inspect the durable manifest")


def _preserve_primary_failure(primary: Exception, service, index, path: Path,
                              manifest: dict[str, Any], stage: str) -> HarnessExecutionError:
    attempted = any(u.get("write_state") != "NOT_ATTEMPTED" for u in manifest["users"].values())
    attempted = attempted or any(v.get("write_state") != "NOT_ATTEMPTED" for v in manifest["vectors"])
    attempted = attempted or any(x.get("write_state") != "NOT_ATTEMPTED" for x in manifest["database_writes"])
    attempted = attempted or manifest.get("delegation_update", {}).get("write_state") != "NOT_ATTEMPTED"
    manifest["primary_error"] = _safe_error(primary, stage=manifest.get("stage", stage),
                                              mutation_attempted=attempted, manifest_path=path)
    manifest["state"] = "primary_failed"
    journal_error = None
    try:
        _write_manifest(path, manifest)
    except Exception as exc:
        journal_error = _safe_error(exc, stage="manifest.persist_primary_error",
                                    mutation_attempted=False, manifest_path=path)
    cleanup_error = None
    try:
        _clean(service, index, path, manifest)
    except Exception as exc:
        cleanup_error = _safe_error(exc, stage="cleanup", mutation_attempted=True, manifest_path=path)
        manifest["cleanup_error"] = cleanup_error
        manifest["state"] = "cleanup_required"
        try:
            _write_manifest(path, manifest)
        except Exception as journal_exc:
            journal_error = journal_error or _safe_error(journal_exc, stage="manifest.persist_cleanup_error",
                                                          mutation_attempted=False, manifest_path=path)
    return HarnessExecutionError({"primary_error": manifest["primary_error"],
                                  "cleanup_error": cleanup_error, "journal_error": journal_error,
                                  "manifest_path": str(path)})


def _execute(path: Path) -> int:
    target = _preflight_live()
    _preflight(require_credentials=True)  # require the exact one-run approval marker before writes
    from pinecone import Pinecone

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index_name = os.environ["PINECONE_INDEX_NAME"].strip()
    configured_host = os.environ["PINECONE_HOST"].strip().lower()
    description = pc.describe_index(index_name)
    described_host = str(getattr(description, "host", "")).strip().lower()
    if not described_host or configured_host != described_host:
        raise RuntimeError("Configured Pinecone host does not match the named index metadata")
    index = pc.Index(host=os.environ["PINECONE_HOST"].strip())
    dimension = getattr(description, "dimension", None)
    if dimension != VECTOR_DIM:
        raise RuntimeError(f"Index dimension {dimension!r} does not match pinned Vindex dimension {VECTOR_DIM}")
    manifest = _new_manifest()
    manifest["target"] = target
    manifest["candidate_sha"] = target["candidate_sha"]
    manifest["_manifest_path"] = str(path)
    # Validate every exact request object locally before creating Auth users or
    # database fixtures. The B preflight identity/namespace are placeholders
    # used only for schema validation and are never sent to Pinecone.
    _build_vector_payloads(manifest, preflight=True)
    _write_manifest(path, manifest)  # durable recovery plan before the first remote write
    manifest["state"] = "creating_auth"
    _write_manifest(path, manifest)
    service, anon = _auth_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"], os.environ["SUPABASE_SERVICE_KEY"],
    )
    stage = "auth.create_user"
    try:
        uids = _create_auth_users(service, anon, manifest)
        if uids != {r: row["id"] for r, row in manifest["users"].items()}:
            raise RuntimeError("Verified synthetic identity set differs from the manifest")
        stage = "database.seed_rows"
        _seed_rows(service, manifest, path)
        manifest["state"] = "creating_vectors"
        _write_manifest(path, manifest)
        vectors_by_namespace = _build_vector_payloads(manifest, uids)
        _write_manifest(path, manifest)
        for namespace, vectors in vectors_by_namespace.items():
            stage = f"pinecone.upsert.{namespace}"
            for item in manifest["vectors"]:
                if item["namespace"] == namespace:
                    item["write_state"] = "ATTEMPTED_UNKNOWN"
            manifest["stage"] = stage
            _write_manifest(path, manifest)
            index.upsert(vectors=vectors, namespace=namespace)
            for item in manifest["vectors"]:
                if item["namespace"] == namespace:
                    item["write_state"] = "CONFIRMED_CREATED"
            _write_manifest(path, manifest)
        manifest["state"] = "vectors_upserted"
        _write_manifest(path, manifest)

        # Positive visibility first, with bounded polling, before interpreting
        # any absence as authorization denial.
        for ns, vectors in vectors_by_namespace.items():
            ids = [v["id"] for v in vectors]
            visible = False
            for _ in range(8):
                fetched = getattr(index.fetch(ids=ids, namespace=ns), "vectors", {}) or {}
                if all(i in fetched for i in ids):
                    visible = True
                    break
                import time
                time.sleep(1)
            if not visible:
                raise RuntimeError(f"Positive fixture visibility not proven in namespace {ns}")

        from app.services.retrieve import _vlasnicki_opseg_iz_konteksta
        from shared.ai_provenance import scoped_request_context
        expected_office_ns = f"kancelarija_{manifest['office']['id']}"
        for role in ("A", "C", "D"):
            with scoped_request_context(user_id=uids[role]):
                ns, acl = _vlasnicki_opseg_iz_konteksta()
            if ns != expected_office_ns:
                raise RuntimeError(f"Role {role} did not derive the synthetic office namespace")
            if acl is None:
                raise RuntimeError(f"Role {role} ACL was not resolved")

        for scenario in _ab_query_scenarios(manifest, uids):
            assertion = _run_ab_query_scenario(index, service, scenario, uids)
            manifest["assertions"].append(assertion)
            if sum(len(a.get("pinecone_queries", [])) for a in manifest["assertions"]) > MAX_QUERIES:
                raise RuntimeError(f"Actual Pinecone query count exceeds the cap of {MAX_QUERIES}")
            _write_manifest(path, manifest)
            if not assertion["passed"]:
                raise RuntimeError(f"A/B assertion failed: {assertion['name']}")
        stage = "database.revoke_delegation"
        manifest["delegation_update"]["write_state"] = "ATTEMPTED_UNKNOWN"
        manifest["stage"] = stage
        _write_manifest(path, manifest)
        service.table("predmet_delegiranja").update({"status": "otkazano"}).eq("id", manifest["delegation"]).execute()
        manifest["delegation_update"]["write_state"] = "CONFIRMED_CREATED"
        _write_manifest(path, manifest)
        revoked_case = {
            "name": "D_revoked_delegation_denied", "role": "D",
            "markers": [_fixture_vector("A", manifest["run_id"])["text"]], "positive": False,
        }
        revoked_assertion = _run_ab_query_scenario(index, service, revoked_case, uids)
        manifest["assertions"].append(revoked_assertion)
        if sum(len(a.get("pinecone_queries", [])) for a in manifest["assertions"]) > MAX_QUERIES:
            raise RuntimeError(f"Actual Pinecone query count exceeds the cap of {MAX_QUERIES}")
        _write_manifest(path, manifest)
        if not revoked_assertion["passed"]:
            raise RuntimeError("Revoked delegation still returned the synthetic passage")
        manifest["state"] = "assertions_passed"
        _write_manifest(path, manifest)
    except Exception as primary:
        raise _preserve_primary_failure(primary, service, index, path, manifest, stage) from None
    else:
        _clean(service, index, path, manifest)
        print(json.dumps({"status": "AB_ASSERTIONS_PASS", "run_id": manifest["run_id"],
                          "queries": len(manifest["assertions"]), "vectors": len(manifest["vectors"]),
                          "text_hashes": [v.get("text_sha256") for v in manifest["vectors"]]}, indent=2))
    print(json.dumps({"cleanup_verified": manifest["cleanup"]["verified"],
                      "state": manifest["state"], "manifest": str(path)}, indent=2))
    return 0


def _cleanup_only(path: Path) -> int:
    target = _preflight(require_credentials=True, require_approval=False)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _validate_manifest_for_cleanup(manifest)
    original = manifest.get("target", {})
    for key in ("supabase_project_ref", "pinecone_index_name", "pinecone_host_fingerprint"):
        if original.get(key) != target.get(key):
            raise RuntimeError(f"Cleanup target mismatch for {key}; no deletion performed")
    from pinecone import Pinecone

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    description = pc.describe_index(target["pinecone_index_name"])
    if (str(getattr(description, "host", "")).strip().lower() != os.environ["PINECONE_HOST"].strip().lower()
            or getattr(description, "dimension", None) != VECTOR_DIM):
        raise RuntimeError("Cleanup target index metadata mismatch; no deletion performed")
    index = pc.Index(host=os.environ["PINECONE_HOST"].strip())
    service, _ = _auth_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"], os.environ["SUPABASE_SERVICE_KEY"])
    _clean(service, index, path, manifest)
    print(json.dumps({"cleanup_verified": manifest["cleanup"]["verified"], "manifest": str(path)}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="default: validate source/config/scope only")
    mode.add_argument("--execute", action="store_true", help="create bounded synthetic fixtures and run A/B checks")
    mode.add_argument("--cleanup-only", action="store_true", help="exact-ID cleanup from a saved manifest")
    mode.add_argument("--preflight-live", action="store_true", help="read-only provider/source/legacy-fixture checks")
    parser.add_argument("--manifest", type=Path, default=None, help="durable recovery manifest path")
    parser.add_argument("--expected-sha", default=None, help="exact current PR HEAD required with --execute")
    args = parser.parse_args(argv)
    path = args.manifest
    if args.preflight_live:
        try:
            if not args.expected_sha:
                parser.error("--preflight-live requires --expected-sha <exact PR HEAD>")
            report = _preflight_live(expected_sha=args.expected_sha)
            print(json.dumps({"status": "PREFLIGHT_LIVE_PASS", **report}, indent=2))
            return 0
        except Exception as exc:
            safe = _safe_error(exc, stage="live_preflight", mutation_attempted=False, manifest_path=path)
            print(json.dumps({"status": "PREFLIGHT_LIVE_BLOCKED", "error": safe}, indent=2), file=sys.stderr)
            return 2
    if args.cleanup_only:
        if not path or not path.is_file():
            parser.error("--cleanup-only requires an existing --manifest")
        return _cleanup_only(path)
    if args.execute:
        if not args.expected_sha:
            parser.error("--execute requires --expected-sha <exact PR HEAD>")
        path = path or (_manifest_home() / f"run_{uuid.uuid4().hex}.json")
        try:
            import subprocess
            current_sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            if current_sha != args.expected_sha:
                raise RuntimeError("Current checkout does not match --expected-sha; no writes performed")
            if path.exists():
                raise RuntimeError("Manifest path already exists; refusing to overwrite a recovery record")
            return _execute(path)
        except Exception as exc:
            print(json.dumps({"status": "EXECUTION_STOPPED", "error": _safe_error(
                exc, stage="execution", mutation_attempted=path.exists(), manifest_path=path if path.exists() else None)}, indent=2), file=sys.stderr)
            if path.exists():
                print(f"Recovery manifest: {path}", file=sys.stderr)
            return 2
    try:
        report = _preflight(require_credentials=False)
        report["cache_source_matches_pinned_candidate"] = _require_source_pin()
    except Exception as exc:
        print(f"DRY_RUN_BLOCKED: {type(exc).__name__}: {exc}")
        return 2
    if path is None:
        path = _manifest_home() / "dry-run-plan.json"
        if args.expected_sha and args.expected_sha != report["candidate_sha"]:
            raise RuntimeError("Current checkout does not match --expected-sha")
        print(json.dumps({"status": "DRY_RUN_PASS", **report,
                      "manifest_path_if_executed": str(path),
                      "mutation": False,
                      "query_count_upper_bound": MAX_QUERIES}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

