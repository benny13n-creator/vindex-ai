# -*- coding: utf-8 -*-
"""NS005 Task 14 — intake red u lažnom Supabase-u (tests/ns005_harness.py), VERNO SQL-u
migracija 073 (enqueue/claim/complete/fail) i 095 (claim_intake_finalize). Nije pytest test.

Svaka funkcija prati telo plpgsql funkcije red po red; razlike u odnosu na pravu bazu su samo
one koje nemaju smisla u jednom procesu (FOR UPDATE SKIP LOCKED → jedan proces nema konkurentnu
transakciju; atomičnost više upisa → Python lista se menja bez prekida).
"""
import uuid
from datetime import datetime, timedelta, timezone


def _sada():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat()


def _dt(v):
    if not v:
        return None
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _audit(b, job_id, dogadjaj, posle):
    b.tabele.setdefault("intake_audit_log", []).append({"id": str(uuid.uuid4()), "intake_job_id": job_id, "event_type": dogadjaj,
                                                        "actor": "system", "after": posle, "created_at": _iso(_sada())})


def _dogadjaj(b, tip, payload, user_id=None):
    b.tabele.setdefault("events", []).append({"id": str(uuid.uuid4()), "event_type": tip, "user_id": user_id, "payload": payload,
                                              "created_at": _iso(_sada())})


def enqueue_intake_job(b, p):
    poslovi = b.tabele.setdefault("intake_jobs", [])
    if p.get("p_idempotency_key") is not None:
        for j in poslovi:
            if j.get("idempotency_key") == p["p_idempotency_key"]:
                return j["id"]
    jid = str(uuid.uuid4())
    sada = _iso(_sada())
    poslovi.append({
        "id": jid, "source": p["p_source"], "content_sha256": p["p_content_sha256"], "storage_path": p["p_storage_path"],
        "uploaded_by": p["p_uploaded_by"], "kancelarija_id": p.get("p_kancelarija_id"), "idempotency_key": p.get("p_idempotency_key"),
        "status": "received", "attempts": 0, "next_retry_at": None, "claimed_at": None, "last_error": None,
        "created_at": sada, "completed_at": None, "original_filename": None, "mime_type": None,
        "predmet_id": None, "finalizing_at": None, "assimilation_complete": False,
    })
    _audit(b, jid, "job_created", {"status": "received", "source": p["p_source"]})
    _dogadjaj(b, "DocumentJobEnqueued", {"intake_job_id": jid, "source": p["p_source"]}, p["p_uploaded_by"])
    return jid


def claim_intake_job(b, p):
    sada = _sada()
    kandidati = [j for j in b.tabele.get("intake_jobs", []) if j["status"] == p["p_from_status"]
                 and (j.get("next_retry_at") is None or _dt(j["next_retry_at"]) <= sada)]
    if not kandidati:
        return []
    j = sorted(kandidati, key=lambda x: x["created_at"])[0]
    j["status"], j["claimed_at"] = p["p_to_status"], _iso(sada)
    return [dict(j)]


def complete_intake_job(b, p):
    for j in b.tabele.get("intake_jobs", []):
        if j["id"] == p["p_job_id"]:
            j["status"], j["completed_at"] = "completed", _iso(_sada())
    _audit(b, p["p_job_id"], "job_completed", {"status": "completed"})
    _dogadjaj(b, "DocumentJobCompleted", {"intake_job_id": p["p_job_id"]})
    return None


def fail_intake_job(b, p):
    for j in b.tabele.get("intake_jobs", []):
        if j["id"] != p["p_job_id"]:
            continue
        if p["p_new_attempts"] >= p["p_max_attempts"]:
            j.update(status="failed", attempts=p["p_new_attempts"], last_error=p["p_error"])
            _audit(b, j["id"], "job_dead_lettered", {"attempts": p["p_new_attempts"], "error": p["p_error"]})
            _dogadjaj(b, "DocumentJobFailed", {"intake_job_id": j["id"], "attempts": p["p_new_attempts"], "error": p["p_error"]})
        else:
            j.update(status="received", attempts=p["p_new_attempts"], next_retry_at=p.get("p_next_retry_at"),
                     last_error=p["p_error"], claimed_at=None)
            _audit(b, j["id"], "job_retry_scheduled", {"attempts": p["p_new_attempts"], "error": p["p_error"]})
    return None


def claim_intake_finalize(b, p):
    sada = _sada()
    granica = sada - timedelta(seconds=int(p.get("p_stale_after_seconds") or 120))
    for j in b.tabele.get("intake_jobs", []):
        if j["id"] == p["p_job_id"] and not j.get("assimilation_complete") and \
                (j.get("finalizing_at") is None or _dt(j["finalizing_at"]) < granica):
            j["finalizing_at"] = _iso(sada)
            return [dict(j)]
    return []


# DEFAULT vrednosti kolona iz migracije 074 (intake_documents, extracted_entities, intake_review_queue).
PODRAZUMEVANO = {
    "intake_documents": {"ocr_used": False},
    "extracted_entities": {"reviewed": False, "corrected_value": None},
    "intake_review_queue": {"low_confidence_fields": [], "resolved_at": None},
}


def ukljuci(baza):
    for t, kol in PODRAZUMEVANO.items():
        baza.podrazumevano.setdefault(t, {}).update(kol)
    baza.rpc_impl.update({
        "enqueue_intake_job": enqueue_intake_job,
        "claim_intake_job": claim_intake_job,
        "complete_intake_job": complete_intake_job,
        "fail_intake_job": fail_intake_job,
        "claim_intake_finalize": claim_intake_finalize,
    })
    return baza
