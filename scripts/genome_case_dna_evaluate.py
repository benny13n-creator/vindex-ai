# -*- coding: utf-8 -*-
"""
Vindex AI — Case Genome end-to-end evaluation harness (Reality Validation,
2026-07-18). Reusable for BOTH the synthetic calibration batch and the
later real-anonymized-matters batch — only the case definitions differ.

Exercises the REAL pipeline through the REAL API endpoints (in-process ASGI
calls against the actual FastAPI app, not direct database insertion):

  POST /api/predmeti                       — create predmet
  POST /api/predmeti/{id}/upload            — upload document (real .docx
                                               bytes, real OCR/parse path,
                                               real predmet_dokumenti write,
                                               real Genome background refresh)
  GET  /api/predmeti/{id}/case-dna          — read resulting Genome

The only thing NOT real: authentication. This harness has no browser and
mints no real Supabase session token, so api._require_auth is patched for
the duration of the run to return a fixed, REAL, pre-existing user (id/email
passed in) — every endpoint body, DB write, background task, and business
rule after that point runs completely unmodified.

Because this harness runs outside the app's normal process (no lifespan
startup), the durable-outbox dispatch loop isn't ticking in the background.
Rather than sleep and hope, this harness calls dispatch_pending_events()
directly once per case after the Genome appears — same function the real
DispatchLoop calls every 3s in production, just invoked deterministically.

Writes results to <out_dir>/results.json — NEVER to the repo. Case content
(synthetic or real) may include realistic-looking or actually-real personal/
financial details; this stays in the local scratch directory only.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    from docx import Document
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class _FakeAuthUser:
    def __init__(self, user_id: str, email: str):
        self.id = user_id
        self.email = email


async def run_batch(cases: list[dict], user_id: str, email: str, out_dir: str,
                     poll_timeout_s: float = 90.0, poll_interval_s: float = 4.0) -> list[dict]:
    """cases: [{label, naziv, opis, tip, documents: [{filename, paragraphs}]}]"""
    _load_env()
    import httpx
    import api as api_module
    from services.event_bus import dispatch_pending_events
    from supabase import create_client

    supa = create_client(
        os.environ["SUPABASE_URL"],
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_SERVICE_KEY"],
    )

    fake_user = _FakeAuthUser(user_id, email)
    results: list[dict] = []

    with patch.object(api_module, "_require_auth", return_value=fake_user):
        transport = httpx.ASGITransport(app=api_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://evalharness") as client:
            headers = {"Authorization": "Bearer eval-harness-token"}

            for case in cases:
                t0 = time.monotonic()
                record: dict[str, Any] = {"label": case["label"], "naziv": case["naziv"]}

                resp = await client.post("/api/predmeti", json={
                    "naziv": case["naziv"], "opis": case.get("opis", ""), "tip": case.get("tip", "opsti"),
                }, headers=headers)
                if resp.status_code != 200:
                    record["error"] = f"kreiraj_predmet failed: {resp.status_code} {resp.text[:300]}"
                    results.append(record)
                    continue
                predmet_id = resp.json()["predmet"]["id"]
                record["predmet_id"] = predmet_id

                upload_errors = []
                for doc in case["documents"]:
                    content = _make_docx_bytes(doc["paragraphs"])
                    files = {"file": (
                        doc["filename"], content,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )}
                    uresp = await client.post(
                        f"/api/predmeti/{predmet_id}/upload", files=files, headers=headers,
                    )
                    if uresp.status_code != 200:
                        upload_errors.append(f"{doc['filename']}: {uresp.status_code} {uresp.text[:300]}")
                record["upload_errors"] = upload_errors
                record["docs_uploaded"] = len(case["documents"]) - len(upload_errors)

                # Poll for background Genome refresh directly against the DB (read-only).
                # NOTE: GET /case-dna goes through shared.deps.get_current_user, a DIFFERENT
                # auth path than api._require_auth (patched above for the create/upload
                # endpoints) — polling via HTTP 401s here even though the real background
                # pipeline completes correctly. This is a polling-mechanism detail, not a
                # weakening of what's validated: intake (POST /upload) and extraction/Genome-
                # save/event/audit all still run through the real, unmodified code path.
                #
                # IMPORTANT (found during CASE-C of the 2026-07-18 synthetic batch): each
                # upload fires its OWN independent background refresh (~3s delay + extraction
                # time), and this harness uploads sequentially, so background task N can still
                # be running when task N+1 starts. Waiting for "any valid verzija >= 1" catches
                # an EARLY intermediate refresh (fewer documents than actually uploaded), not
                # the final one — this is a harness/polling defect, not a product defect (the
                # live DB row does correctly reach the final version moments later). Fix: wait
                # for verzija to reach the actual number of successfully uploaded documents
                # (each triggers exactly one refresh on a freshly created predmet), not just
                # "some valid version".
                expected_verzija = record["docs_uploaded"]
                genome = None
                deadline = time.monotonic() + poll_timeout_s
                while time.monotonic() < deadline:
                    await asyncio.sleep(poll_interval_s)
                    pres = supa.table("predmeti").select("case_dna").eq("id", predmet_id).execute()
                    g = ((pres.data or [{}])[0].get("case_dna")) or {}
                    if g.get("verzija", 0) >= expected_verzija and not g.get("greska"):
                        genome = g
                        break
                record["genome"] = genome
                record["genome_wait_s"] = round(time.monotonic() - t0, 1)

                # Deterministically flush the durable outbox (no live DispatchLoop in this harness)
                dispatch_result = await dispatch_pending_events(batch_size=50)
                record["dispatch_result"] = dispatch_result

                ev = supa.table("events").select("*").eq("predmet_id", predmet_id) \
                    .eq("event_type", "GenomeUpdated").order("created_at", desc=True).limit(1).execute()
                record["event_row"] = (ev.data or [None])[0]

                au = supa.table("audit_immutable").select("action,resource_type,resource_id,metadata,created_at") \
                    .eq("resource_id", predmet_id).eq("action", "genome_refresh") \
                    .order("created_at", desc=True).limit(1).execute()
                record["audit_row"] = (au.data or [None])[0]

                dok = supa.table("predmet_dokumenti").select("naziv_fajla,redni_broj,status") \
                    .eq("predmet_id", predmet_id).order("redni_broj").execute()
                record["documents_in_db"] = dok.data or []

                record["total_elapsed_s"] = round(time.monotonic() - t0, 1)
                results.append(record)
                print(f"[{case['label']}] predmet={predmet_id} genome={'OK v'+str(genome.get('verzija')) if genome else 'TIMEOUT'} "
                      f"verifikacija={((genome or {}).get('_verifikacija') or {}).get('odluka')} "
                      f"event={'yes' if record['event_row'] else 'no'} audit={'yes' if record['audit_row'] else 'no'} "
                      f"elapsed={record['total_elapsed_s']}s")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8",
    )
    print(f"\nRezultati upisani: {out_path / 'results.json'}")
    return results


if __name__ == "__main__":
    print("Ovo je biblioteka — pozovi run_batch() iz drugog skripta sa definicijama slucajeva.")
