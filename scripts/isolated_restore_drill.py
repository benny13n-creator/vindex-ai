#!/usr/bin/env python3
"""Disposable synthetic DB + encrypted-object backup/restore drill.

This proves the local artifact procedure only. It does not inspect or prove
production provider backups, schedules, RPO, RTO, or key escrow.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path)


def _synthetic_pdf(label: str) -> bytes:
    """Build a minimal one-page PDF without adding a PDF-library dependency."""
    content = f"BT /F1 12 Tf 30 150 Td ({label}) Tj ET\n".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


def _create_synthetic_state(root: Path, key: bytes) -> tuple[Path, Path, dict]:
    snapshot_started = datetime.now(timezone.utc)
    db = root / "primary.sqlite"
    storage = root / "storage"
    storage.mkdir(parents=True)
    conn = _connect(db)
    conn.executescript(
        """
        CREATE TABLE tenants(id TEXT PRIMARY KEY);
        CREATE TABLE matters(id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id));
        CREATE TABLE documents(id TEXT PRIMARY KEY, matter_id TEXT NOT NULL REFERENCES matters(id), object_key TEXT NOT NULL, sha256 TEXT NOT NULL, extracted_text TEXT NOT NULL, source TEXT NOT NULL);
        CREATE TABLE audit(seq INTEGER PRIMARY KEY, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL, action TEXT NOT NULL);
        INSERT INTO tenants VALUES ('tenant-a'), ('tenant-b');
        INSERT INTO matters VALUES ('matter-a', 'tenant-a'), ('matter-b', 'tenant-b');
        """
    )
    originals = {
        "tenant-a/matter-a/doc-a.pdf": _synthetic_pdf("Synthetic tenant A legal test document"),
        "tenant-b/matter-b/doc-b.pdf": _synthetic_pdf("Synthetic tenant B legal test document"),
    }
    manifest_objects = []
    for object_key, raw in originals.items():
        nonce = hashlib.sha256(object_key.encode()).digest()[:12]
        encrypted = nonce + AESGCM(key).encrypt(nonce, raw, object_key.encode())
        dest = storage / object_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(encrypted)
        tenant, matter, name = object_key.split("/")
        doc_id = "doc-a" if tenant == "tenant-a" else "doc-b"
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, matter, object_key, hashlib.sha256(raw).hexdigest(), "synthetic extracted text", name),
        )
        manifest_objects.append({"key": object_key, "encrypted_sha256": hashlib.sha256(encrypted).hexdigest()})
    prev = "GENESIS"
    for seq, action in enumerate(("matter_created", "document_uploaded"), start=1):
        digest = hashlib.sha256(f"{prev}|{seq}|{action}".encode()).hexdigest()
        conn.execute("INSERT INTO audit VALUES (?, ?, ?, ?)", (seq, prev, digest, action))
        prev = digest
    conn.commit()
    conn.close()
    return db, storage, {
        "objects": manifest_objects,
        "tenants": 2,
        "matters": 2,
        "documents": 2,
        "audit_rows": 2,
        "database_sha256": hashlib.sha256(db.read_bytes()).hexdigest(),
        "snapshot_started_at": snapshot_started.isoformat(),
        "snapshot_completed_at": datetime.now(timezone.utc).isoformat(),
    }


def _verify(db: Path, storage: Path, key: bytes, manifest: dict) -> dict:
    assert hashlib.sha256(db.read_bytes()).hexdigest() == manifest["database_sha256"]
    conn = _connect(db)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    rows = conn.execute("SELECT id, matter_id, object_key, sha256 FROM documents ORDER BY id").fetchall()
    assert len(rows) == manifest["documents"]
    referenced_keys = {row[2] for row in rows}
    stored_keys = {path.relative_to(storage).as_posix() for path in storage.rglob("*") if path.is_file()}
    assert stored_keys == referenced_keys
    assert conn.execute("SELECT count(*) FROM tenants").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM matters").fetchone()[0] == 2
    audit = conn.execute("SELECT seq, prev_hash, entry_hash, action FROM audit ORDER BY seq").fetchall()
    prev = "GENESIS"
    for seq, prior, digest, action in audit:
        assert prior == prev
        assert digest == hashlib.sha256(f"{prior}|{seq}|{action}".encode()).hexdigest()
        prev = digest
    verified = []
    for doc_id, matter_id, object_key, expected_hash in rows:
        encrypted = (storage / object_key).read_bytes()
        encrypted_hash = hashlib.sha256(encrypted).hexdigest()
        expected_encrypted = next(item["encrypted_sha256"] for item in manifest["objects"] if item["key"] == object_key)
        assert encrypted_hash == expected_encrypted
        raw = AESGCM(key).decrypt(encrypted[:12], encrypted[12:], object_key.encode())
        assert raw.startswith(b"%PDF-1.4\n") and raw.endswith(b"%%EOF\n")
        assert hashlib.sha256(raw).hexdigest() == expected_hash
        tenant = object_key.split("/")[0]
        assert conn.execute("SELECT 1 FROM matters WHERE id=? AND tenant_id=?", (matter_id, tenant)).fetchone()
        verified.append({"document_id": doc_id, "original_sha256": expected_hash, "encrypted_sha256": encrypted_hash})
    # Cross-tenant authorization control: tenant B cannot resolve tenant A matter.
    assert conn.execute("SELECT 1 FROM matters WHERE id='matter-a' AND tenant_id='tenant-b'").fetchone() is None
    conn.close()
    return {"documents": verified, "audit_rows_verified": len(audit), "tenant_isolation": "PASS"}


def _restore_archive(backup: Path, destination: Path, manifest: dict) -> None:
    """Restore only a complete, hash-matching archive into an empty target."""
    if not backup.is_file():
        raise FileNotFoundError("backup artifact is unavailable")
    actual_hash = hashlib.sha256(backup.read_bytes()).hexdigest()
    if actual_hash != manifest.get("backup_sha256"):
        raise ValueError("backup artifact hash does not match retained manifest")
    try:
        snapshot_started = datetime.fromisoformat(manifest["snapshot_started_at"])
        snapshot_completed = datetime.fromisoformat(manifest["snapshot_completed_at"])
        backup_created = datetime.fromisoformat(manifest["backup_created_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("backup manifest timestamps are missing or invalid") from exc
    if not snapshot_started <= snapshot_completed <= backup_created:
        raise ValueError("backup manifest timestamps are inconsistent")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("restore target must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(backup) as archive:
        corrupt_member = archive.testzip()
        if corrupt_member:
            raise ValueError(f"corrupt backup member: {corrupt_member}")
        archive.extractall(destination)


def run_drill(destination: Path | None = None, artifacts_dir: Path | None = None) -> dict:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="vindex-restore-drill-") as temp:
        root = Path(temp)
        primary = root / "primary"
        primary.mkdir()
        key = AESGCM.generate_key(bit_length=256)
        db, storage, counts = _create_synthetic_state(primary, key)
        # Recovery key is held separately from the backup artifact, modeling a
        # separately authorized recovery mechanism. It is never written to the report.
        key_file = root / "separate-recovery-key.bin"
        key_file.write_bytes(key)
        backup = root / "synthetic-backup.zip"
        with zipfile.ZipFile(backup, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(db, "database/primary.sqlite")
            for path in storage.rglob("*"):
                if path.is_file():
                    archive.write(path, "storage/" + path.relative_to(storage).as_posix())
        manifest = {
            **counts,
            "backup_created_at": datetime.now(timezone.utc).isoformat(),
            "database_sha256": hashlib.sha256(db.read_bytes()).hexdigest(),
            "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        # Destroy the primary state. Restore only from the captured archive.
        shutil.rmtree(primary)
        restored = root / "restored"
        # Recovery consumes the retained manifest artifact, not fixture data
        # regenerated from the deleted primary environment.
        restore_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _restore_archive(backup, restored, restore_manifest)
        result = _verify(
            restored / "database/primary.sqlite",
            restored / "storage",
            key_file.read_bytes(),
            restore_manifest,
        )
        report = {
            "status": "ISOLATED_SYNTHETIC_RESTORE_PASS",
            "scope": "local synthetic SQLite + encrypted object artifacts only",
            "restore_duration_seconds": round(time.monotonic() - started, 3),
            "backup_sha256": restore_manifest["backup_sha256"],
            "backup_created_at": restore_manifest["backup_created_at"],
            "database_counts": {k: counts[k] for k in ("tenants", "matters", "documents", "audit_rows")},
            **result,
            "production_backup_status": "UNKNOWN",
            "production_rpo": "UNKNOWN",
            "production_rto": "UNKNOWN",
        }
        if artifacts_dir:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, artifacts_dir / "synthetic-backup.zip")
            shutil.copy2(key_file, artifacts_dir / "separate-recovery-key.bin")
            shutil.copy2(manifest_path, artifacts_dir / "manifest.json")
        if destination:
            destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--artifacts-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_drill(args.out, args.artifacts_dir), indent=2))
