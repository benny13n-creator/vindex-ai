from pathlib import Path
import sys
import sqlite3

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.isolated_restore_drill import _create_synthetic_state, _restore_archive, _verify, run_drill
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def test_backup_destroy_restore_verifies_db_objects_sources_audit_and_tenants(tmp_path):
    report = run_drill(tmp_path / "report.json", tmp_path / "artifacts")
    assert report["status"] == "ISOLATED_SYNTHETIC_RESTORE_PASS"
    assert report["database_counts"] == {
        "tenants": 2, "matters": 2, "documents": 2, "audit_rows": 2
    }
    assert report["tenant_isolation"] == "PASS"
    assert len(report["documents"]) == 2
    assert report["production_backup_status"] == "UNKNOWN"
    assert (tmp_path / "artifacts/synthetic-backup.zip").exists()
    assert (tmp_path / "artifacts/separate-recovery-key.bin").exists()
    assert (tmp_path / "artifacts/manifest.json").exists()
    assert "key" not in report


def test_missing_object_after_restore_fails(tmp_path):
    key = AESGCM.generate_key(bit_length=256)
    primary = tmp_path / "primary"
    primary.mkdir()
    db, storage, manifest = _create_synthetic_state(primary, key)
    (storage / "tenant-a/matter-a/doc-a.pdf").unlink()
    with pytest.raises(AssertionError):
        _verify(db, storage, key, manifest)


def test_modified_encrypted_object_fails_integrity_check(tmp_path):
    key = AESGCM.generate_key(bit_length=256)
    primary = tmp_path / "primary"
    primary.mkdir()
    db, storage, manifest = _create_synthetic_state(primary, key)
    obj = storage / "tenant-b/matter-b/doc-b.pdf"
    obj.write_bytes(obj.read_bytes() + b"tamper")
    with pytest.raises(AssertionError):
        _verify(db, storage, key, manifest)


def test_wrong_recovery_key_fails_decryption(tmp_path):
    key = AESGCM.generate_key(bit_length=256)
    primary = tmp_path / "primary"
    primary.mkdir()
    db, storage, manifest = _create_synthetic_state(primary, key)
    with pytest.raises(Exception):
        _verify(db, storage, AESGCM.generate_key(bit_length=256), manifest)


def test_object_without_database_reference_fails(tmp_path):
    key = AESGCM.generate_key(bit_length=256)
    primary = tmp_path / "primary"
    primary.mkdir()
    db, storage, manifest = _create_synthetic_state(primary, key)
    orphan = storage / "tenant-a/matter-a/orphan.pdf"
    orphan.write_bytes(b"encrypted synthetic orphan")
    with pytest.raises(AssertionError):
        _verify(db, storage, key, manifest)


def test_wrong_database_original_hash_fails(tmp_path):
    key = AESGCM.generate_key(bit_length=256)
    primary = tmp_path / "primary"
    primary.mkdir()
    db, storage, manifest = _create_synthetic_state(primary, key)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE documents SET sha256=? WHERE id='doc-a'", ("0" * 64,))
    conn.commit()
    conn.close()
    # The DB artifact digest catches altered metadata before object decryption.
    with pytest.raises(AssertionError):
        _verify(db, storage, key, manifest)


def test_corrupt_audit_chain_fails_after_database_digest_is_updated(tmp_path):
    import hashlib

    key = AESGCM.generate_key(bit_length=256)
    primary = tmp_path / "primary"
    primary.mkdir()
    db, storage, manifest = _create_synthetic_state(primary, key)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE audit SET prev_hash=? WHERE seq=2", ("f" * 64,))
    conn.commit()
    conn.close()
    # Model a newly captured artifact whose DB hash matches but whose audit
    # chain is internally inconsistent.
    manifest["database_sha256"] = hashlib.sha256(db.read_bytes()).hexdigest()
    with pytest.raises(AssertionError):
        _verify(db, storage, key, manifest)


def test_missing_or_modified_backup_is_rejected_before_restore(tmp_path):
    archive = tmp_path / "backup.zip"
    archive.write_bytes(b"synthetic backup artifact")
    target = tmp_path / "restore"
    manifest = {"backup_sha256": "0" * 64}
    with pytest.raises(ValueError, match="hash does not match"):
        _restore_archive(archive, target, manifest)
    assert not target.exists()
    archive.unlink()
    with pytest.raises(FileNotFoundError, match="unavailable"):
        _restore_archive(archive, target, manifest)


def test_inconsistent_snapshot_timestamps_are_rejected(tmp_path):
    import hashlib
    import zipfile

    archive = tmp_path / "backup.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("fixture.txt", "synthetic")
    completed = "2026-11-10T10:00:00+00:00"
    manifest = {
        "backup_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "snapshot_started_at": "2026-11-10T10:01:00+00:00",
        "snapshot_completed_at": completed,
        "backup_created_at": "2026-11-10T10:02:00+00:00",
    }
    with pytest.raises(ValueError, match="timestamps are inconsistent"):
        _restore_archive(archive, tmp_path / "restore", manifest)


def test_dr_runbook_never_promotes_provider_check_to_backup_pass(monkeypatch):
    import scripts.dr_runbook as dr

    query = MagicMock()
    query.select.return_value = query
    query.limit.return_value = query
    query.execute.return_value = SimpleNamespace(data=[])
    supa = MagicMock()
    supa.table.return_value = query
    fake_module = SimpleNamespace(create_client=lambda *_args: supa)
    monkeypatch.setitem(sys.modules, "supabase", fake_module)
    monkeypatch.setenv("SUPABASE_URL", "https://isolated.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "synthetic-test-token")
    dr.CHECK_RESULTS.clear()

    assert dr.check_supabase() is True
    backup_checks = [item for item in dr.CHECK_RESULTS if "backup" in item["name"].lower() or "point-in-time" in item["name"].lower()]
    assert backup_checks
    assert all(item["ok"] is False and item["critical"] is False for item in backup_checks)
    assert all("UNKNOWN" in item["detail"] for item in backup_checks)
