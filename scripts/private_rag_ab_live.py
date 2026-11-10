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


def _git_blob_sha(filename: str, *, repo_root: Path = REPO_ROOT) -> str:
    """Hash source after normalizing only Windows CRLF line endings.

    The harness pins Git blob IDs. A Windows checkout may contain CRLF even
    when its checked-in blob contains LF; hashing the path directly then
    reports a different ID. Normalize CRLF to LF, pass those exact bytes to
    Git's blob hasher, and keep comparing the resulting ID with the fixed
    approved blob SHA. No other content or filter transformation is applied.
    """
    source = (repo_root / filename).read_bytes().replace(b"\r\n", b"\n")
    result = subprocess.run(
        ["git", "hash-object", "--stdin"],
        check=True, capture_output=True, cwd=repo_root, input=source,
    )
    return result.stdout.decode("ascii").strip()


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
    import subprocess

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


def _preflight(*, require_credentials: bool) -> dict[str, Any]:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key, "").strip()]
    if require_credentials and missing:
        raise RuntimeError("Missing protected process variables: " + ", ".join(missing))
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
    if require_credentials and os.environ.get("VINDEX_PRIVATE_RAG_AB_APPROVAL") != approval_marker:
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


def _new_manifest() -> dict[str, Any]:
    run = uuid.uuid4().hex
    office_id = str(uuid.uuid4())
    matters = {role: str(uuid.uuid4()) for role in ("A", "B", "C")}
    return {
        "schema": 1,
        "run_id": run,
        "source_sha": PINNED_SOURCE_SHA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target": {},
        "state": "planned",
        "users": {
            role: {"id": None, "email": f"vindex-ab-{run}-{role.lower()}@example.invalid"}
            for role in ("A", "B", "C", "D")
        },
        "office": {"id": office_id},
        "memberships": {role: str(uuid.uuid4()) for role in ("C", "D")},
        "matters": matters,
        "delegation": str(uuid.uuid4()),
        "vectors": [
            {"id": f"vindex-ab-{run}-a", "namespace": f"kancelarija_{office_id}", "matter": "A", "owner": "A"},
            {"id": f"vindex-ab-{run}-c", "namespace": f"kancelarija_{office_id}", "matter": "C", "owner": "C"},
            {"id": f"vindex-ab-{run}-b", "namespace": "user__pending__B", "matter": "B", "owner": "B"},
            {"id": f"vindex-ab-{run}-tmp-a", "namespace": f"tmp_{run}", "matter": "A", "owner": "A", "temporary": True},
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


def _seed_rows(service, manifest: dict[str, Any]) -> None:
    run = manifest["run_id"]
    users = {role: row["id"] for role, row in manifest["users"].items()}
    office = manifest["office"]["id"]
    service.table("kancelarije").insert({
        "id": office, "naziv": f"Vindex synthetic A/B {run[:8]}", "admin_uid": users["A"],
    }).execute()
    for role in ("A", "B", "C"):
        service.table("predmeti").insert({
            "id": manifest["matters"][role],
            "user_id": users[role],
            "naziv": f"Vindex synthetic A/B {run[:8]} {role}",
            "opis": "Synthetic retrieval isolation fixture; no client data.",
            "tip": "opsti",
            "status": "aktivan",
        }).execute()
    for role in ("C", "D"):
        service.table("kancelarija_clanovi").insert({
            "id": manifest["memberships"][role],
            "kancelarija_id": office,
            "email": manifest["users"][role]["email"],
            "user_id": users[role],
            "uloga": "saradnik",
            "status": "ACTIVE",
            "invited_by": users["A"],
            "joined_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    service.table("predmet_delegiranja").insert({
        "id": manifest["delegation"],
        "predmet_id": manifest["matters"]["A"],
        "od_user_id": users["A"],
        "na_user_id": users["D"],
        "napomena": f"Synthetic private RAG A/B run {run}",
        "status": "aktivno",
    }).execute()


def _fixture_vector(role: str, run_id: str) -> dict[str, Any]:
    # Fixed synthetic vector; the real Pinecone index and Vindex filtering/query
    # are exercised. No OpenAI embedding or chat-completion request is made.
    text = f"SYNTHETIC_PRIVATE_RAG_AB_{run_id}_{role}_CONTENT"
    return {
        "text": text,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "values": [1.0] + [0.0] * (VECTOR_DIM - 1),
    }


def _validate_manifest_for_cleanup(manifest: dict[str, Any]) -> None:
    """Reject a modified recovery manifest before it can name deletion targets."""
    run = manifest.get("run_id")
    if manifest.get("schema") != 1 or manifest.get("source_sha") != PINNED_SOURCE_SHA:
        raise RuntimeError("Manifest schema/source pin is not supported")
    if not isinstance(run, str) or not re.fullmatch(r"[0-9a-f]{32}", run):
        raise RuntimeError("Manifest run id is malformed")
    users = manifest.get("users")
    if not isinstance(users, dict) or set(users) != {"A", "B", "C", "D"}:
        raise RuntimeError("Manifest identity set is malformed")
    for role, record in users.items():
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

    expected_vectors = {
        f"vindex-ab-{run}-a": (f"kancelarija_{office_id}", "A", "A", False),
        f"vindex-ab-{run}-c": (f"kancelarija_{office_id}", "C", "C", False),
        f"vindex-ab-{run}-b": (
            f"user_{users['B']['id']}" if users["B"]["id"] else "user__pending__B",
            "B", "B", False,
        ),
        f"vindex-ab-{run}-tmp-a": (f"tmp_{run}", "A", "A", True),
    }
    vectors = manifest.get("vectors")
    if not isinstance(vectors, list) or len(vectors) > VECTOR_LIMIT:
        raise RuntimeError("Manifest vector set is malformed or exceeds the cap")
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


def _clean(service, index, path: Path, manifest: dict[str, Any]) -> None:
    _validate_manifest_for_cleanup(manifest)
    manifest["cleanup"]["attempted"] = True
    _write_manifest(path, manifest)
    errors: list[str] = []
    for ns in sorted({v["namespace"] for v in manifest["vectors"]}):
        ids = [v["id"] for v in manifest["vectors"] if v["namespace"] == ns]
        try:
            index.delete(ids=ids, namespace=ns)
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
        except Exception as exc:
            errors.append(f"vector cleanup failed for exact namespace {ns}: {type(exc).__name__}")
    # Exact IDs only. No broad deletes or delete_all.
    table_ids = (
        ("predmet_delegiranja", [manifest["delegation"]]),
        ("kancelarija_clanovi", list(manifest["memberships"].values())),
        ("predmeti", list(manifest["matters"].values())),
        ("kancelarije", [manifest["office"]["id"]]),
    )
    for table, ids in table_ids:
        for row_id in ids:
            try:
                expected = _synthetic_row_expectation(manifest, table, row_id)
                existing = (service.table(table).select("*").eq("id", row_id).execute().data or [])
                if any(any(row.get(key) != value for key, value in expected.items()) for row in existing):
                    errors.append(f"refusing non-synthetic row cleanup: table={table}, id={row_id}")
                    continue
                service.table(table).delete().eq("id", row_id).execute()
                remaining = (service.table(table).select("id").eq("id", row_id).limit(1).execute().data or [])
                if remaining:
                    errors.append(f"row cleanup not verified: table={table}, id={row_id}")
            except Exception as exc:
                errors.append(f"row cleanup failed: table={table}, id={row_id}, error={type(exc).__name__}")
    for record in manifest["users"].values():
        user_id = record.get("id")
        if not user_id:
            # Auth may commit a create-user request whose response is lost.
            # Resolve only this manifest's exact random example.invalid email.
            try:
                page = 1
                while True:
                    response = service.auth.admin.list_users(page=page, per_page=100)
                    candidates = getattr(response, "users", None) or []
                    match = next((u for u in candidates if getattr(u, "email", None) == record["email"]), None)
                    if match:
                        user_id = str(match.id)
                        record["id"] = user_id
                        _write_manifest(path, manifest)
                        break
                    if len(candidates) < 100:
                        break
                    page += 1
            except Exception as exc:
                errors.append(f"exact synthetic auth lookup failed for {record['email']}: {type(exc).__name__}")
        if user_id:
            try:
                try:
                    auth_record = service.auth.admin.get_user_by_id(user_id)
                except Exception as lookup_exc:
                    if _auth_not_found(lookup_exc):
                        continue
                    raise
                auth_user = getattr(auth_record, "user", None)
                if auth_user and (
                    getattr(auth_user, "email", None) != record["email"]
                    or (getattr(auth_user, "user_metadata", {}) or {}).get("vindex_private_rag_ab_run") != manifest["run_id"]
                ):
                    errors.append(f"refusing non-synthetic auth cleanup for exact id {user_id}")
                    continue
                if not auth_user:
                    continue
                service.auth.admin.delete_user(user_id)
                try:
                    still_there = service.auth.admin.get_user_by_id(user_id)
                    if getattr(still_there, "user", None):
                        errors.append(f"auth cleanup not verified for exact synthetic id {user_id}")
                except Exception as verify_exc:
                    if not _auth_not_found(verify_exc):
                        errors.append(f"auth cleanup verification failed for exact synthetic id {user_id}: {type(verify_exc).__name__}")
            except Exception as exc:
                errors.append(f"auth cleanup failed for exact synthetic id {user_id}: {type(exc).__name__}")
    manifest["cleanup"]["errors"] = errors
    manifest["cleanup"]["verified"] = not errors
    manifest["state"] = "clean" if not errors else "cleanup_required"
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_manifest(path, manifest)
    if errors:
        raise RuntimeError("Cleanup could not be verified; inspect the durable manifest")


def _execute(path: Path) -> int:
    target = _preflight(require_credentials=True)
    _require_source_pin(require_cache_source=True)
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
    service, anon = _auth_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"], os.environ["SUPABASE_SERVICE_KEY"],
    )
    manifest = _new_manifest()
    manifest["target"] = target
    manifest["candidate_sha"] = target["candidate_sha"]
    manifest["_manifest_path"] = str(path)
    _write_manifest(path, manifest)  # durable recovery plan before the first remote write
    manifest["state"] = "creating_auth"
    _write_manifest(path, manifest)
    try:
        uids = _create_auth_users(service, anon, manifest)
        if uids != {r: row["id"] for r, row in manifest["users"].items()}:
            raise RuntimeError("Verified synthetic identity set differs from the manifest")
        _seed_rows(service, manifest)
        manifest["state"] = "creating_vectors"
        _write_manifest(path, manifest)
        vectors_by_namespace: dict[str, list[dict[str, Any]]] = {}
        for vector in manifest["vectors"]:
            if vector["owner"] == "B":
                vector["namespace"] = f"user_{uids['B']}"
            fixture = _fixture_vector(vector["owner"], manifest["run_id"])
            vector["text_sha256"] = fixture["text_sha256"]
            vectors_by_namespace.setdefault(vector["namespace"], []).append({
                "id": vector["id"], "values": fixture["values"],
                "metadata": {
                    "type": "tmp_doc" if vector.get("temporary") else "case_doc",
                    "predmet_id": manifest["matters"][vector["matter"]],
                    "owner_user_id": uids[vector["owner"]],
                    "kancelarija_id": manifest["office"]["id"] if vector["owner"] in ("A", "C", "D") else None,
                    "text": fixture["text"], "source_filename": "synthetic-fixture.txt",
                },
            })
        if sum(map(len, vectors_by_namespace.values())) > VECTOR_LIMIT:
            raise RuntimeError("Fixture vector cap exceeded")
        _write_manifest(path, manifest)
        for namespace, vectors in vectors_by_namespace.items():
            index.upsert(vectors=vectors, namespace=namespace)
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

        markers = {r: _fixture_vector(r, manifest["run_id"])["text"] for r in "ABCD"}
        cases = [
            ("A_owner_positive", "A", [markers["A"]], [], None, False, True),
            ("B_owner_positive", "B", [markers["B"]], [], None, False, True),
            ("B_cannot_read_A", "B", [markers["A"]], [expected_office_ns, f"user_{uids['A']}", f"tmp_{manifest['run_id']}"], expected_office_ns, False, False),
            ("C_same_office_denied", "C", [markers["A"]], [expected_office_ns], expected_office_ns, False, False),
            ("D_delegated_A_positive", "D", [markers["A"]], [], None, False, True),
            ("D_not_C", "D", [markers["C"]], [], None, False, False),
            ("A_temp_positive", "A", [markers["A"]], [f"tmp_{manifest['run_id']}"], None, False, True),
            ("C_foreign_temp_denied", "C", [markers["A"]], [f"tmp_{manifest['run_id']}"], None, False, False),
            ("C_explicit_foreign_namespace_denied", "C", [markers["A"]], [], f"user_{uids['A']}", False, False),
            ("C_extra_private_namespaces_denied", "C", [markers["A"]], [expected_office_ns, f"user_{uids['A']}"], None, False, False),
            ("A_acl_failure_fail_closed", "A", [markers["A"]], [], expected_office_ns, True, False),
            ("U_missing_identity_fail_closed", None, [markers["A"]], [f"tmp_{manifest['run_id']}"], expected_office_ns, False, False),
        ]
        if len(cases) > MAX_QUERIES:
            raise RuntimeError("Query cap exceeded")
        for name, role, forbidden, extras, foreign, acl_fail, expected_positive in cases:
            docs, meta, query_trace = _retrieval(
                index, service, uids[role] if role else None, extra=extras or None,
                foreign_namespace=foreign, fail_acl=acl_fail,
            )
            blob = json.dumps({"docs": docs, "meta": meta}, ensure_ascii=False, default=str)
            marker_presence = {m: m in blob for m in forbidden}
            passed = all(marker_presence.values()) if expected_positive else not any(marker_presence.values())
            if name == "A_acl_failure_fail_closed":
                passed = not any(marker_presence.values())
            manifest["assertions"].append({
                "name": name, "role": role, "expected_positive": expected_positive,
                "marker_hashes": [hashlib.sha256(m.encode()).hexdigest() for m in forbidden],
                "marker_present": list(marker_presence.values()), "passed": passed,
                "pinecone_queries": query_trace,
            })
            if sum(len(a.get("pinecone_queries", [])) for a in manifest["assertions"]) > MAX_QUERIES:
                raise RuntimeError(f"Actual Pinecone query count exceeds the cap of {MAX_QUERIES}")
            _write_manifest(path, manifest)
            if not passed:
                raise RuntimeError(f"A/B assertion failed: {name}")

        # Distinct adversarial attempt: C explicitly supplies A's matter as a
        # requested ACL expansion. The real retrieval boundary intersects this
        # request with C's server-derived ACL; the resulting empty set must skip
        # the private namespace query entirely.
        marker_a = markers["A"]
        docs, meta, query_trace = _retrieval(
            index, service, uids["C"],
            dozvoljeni_predmeti=[manifest["matters"]["A"]],
        )
        acl_expansion_ok = not _contains(docs, meta, marker_a) and not query_trace
        manifest["assertions"].append({
            "name": "C_attacker_acl_expansion_denied", "role": "C",
            "marker_hashes": [hashlib.sha256(marker_a.encode()).hexdigest()],
            "marker_present": [_contains(docs, meta, marker_a)],
            "passed": acl_expansion_ok, "pinecone_queries": query_trace,
        })
        _write_manifest(path, manifest)
        if not acl_expansion_ok:
            raise RuntimeError("Caller-supplied ACL expanded access to an undelegated matter")
        service.table("predmet_delegiranja").update({"status": "otkazano"}).eq("id", manifest["delegation"]).execute()
        docs, meta, query_trace = _retrieval(index, service, uids["D"])
        marker_a = markers["A"]
        revoked_ok = not _contains(docs, meta, marker_a)
        manifest["assertions"].append({
            "name": "D_revoked_delegation_denied", "role": "D",
            "marker_hashes": [hashlib.sha256(marker_a.encode()).hexdigest()],
            "marker_present": [_contains(docs, meta, marker_a)], "passed": revoked_ok,
            "pinecone_queries": query_trace,
        })
        if sum(len(a.get("pinecone_queries", [])) for a in manifest["assertions"]) > MAX_QUERIES:
            raise RuntimeError(f"Actual Pinecone query count exceeds the cap of {MAX_QUERIES}")
        _write_manifest(path, manifest)
        if not revoked_ok:
            raise RuntimeError("Revoked delegation still returned the synthetic passage")
        manifest["state"] = "assertions_passed"
        _write_manifest(path, manifest)
        print(json.dumps({"status": "AB_ASSERTIONS_PASS", "run_id": manifest["run_id"],
                          "queries": len(manifest["assertions"]), "vectors": len(manifest["vectors"]),
                          "text_hashes": [v.get("text_sha256") for v in manifest["vectors"]]}, indent=2))
    finally:
        _clean(service, index, path, manifest)
    print(json.dumps({"cleanup_verified": manifest["cleanup"]["verified"],
                      "state": manifest["state"], "manifest": str(path)}, indent=2))
    return 0


def _cleanup_only(path: Path) -> int:
    target = _preflight(require_credentials=True)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _validate_manifest_for_cleanup(manifest)
    original = manifest.get("target", {})
    for key in ("supabase_project_ref", "pinecone_index_name", "pinecone_host_fingerprint"):
        if original.get(key) != target.get(key):
            raise RuntimeError(f"Cleanup target mismatch for {key}; no deletion performed")
    from pinecone import Pinecone

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
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
    parser.add_argument("--manifest", type=Path, default=None, help="durable recovery manifest path")
    parser.add_argument("--expected-sha", default=None, help="exact current PR HEAD required with --execute")
    args = parser.parse_args(argv)
    path = args.manifest
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
            return _execute(path)
        except Exception as exc:
            print(f"EXECUTION_STOPPED: {type(exc).__name__}: {exc}", file=sys.stderr)
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
