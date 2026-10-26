# -*- coding: utf-8 -*-
"""VCR001 T01 — adversarijalni slučajevi prijema kroz STVARNU rutu i STVARAN IntakeWorker (fake baza):
opasno ime fajla i sadržaj koji ne odgovara ekstenziji. Ostali slučajevi iz T01 već imaju testove
(v. docs/v2-execution/VCR001_TASK_LEDGER.md, T01)."""
import io

from tests.test_osb002_solo_tok import A, _otpremi, _pdf, _radnik, solo  # noqa: F401


def test_opasno_ime_fajla_ne_ulazi_u_putanju_skladista(solo):
    k, b = solo
    r = _otpremi(k, _pdf(), ime="../../../etc/passwd.pdf")
    assert r.status_code == 202 and r.json()["rezultati"][0]["ok"] is True, r.text
    posao = b.tabele["intake_jobs"][-1]
    assert ".." not in posao["storage_path"] and "passwd" not in posao["storage_path"]
    assert posao["storage_path"].startswith("uid-A/")
    assert _radnik() is True                                       # obrada normalno završava
    assert posao["status"] in ("completed", "awaiting_review"), posao["status"]


def test_png_pod_imenom_pdf_nije_lazno_zavrsen(solo):
    from PIL import Image
    k, b = solo
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="PNG")
    r = _otpremi(k, buf.getvalue(), ime="presuda.pdf")
    assert r.status_code == 202, r.text
    # N1 (2026-10-26): ranije primljen pa „nikad lažno završen“ posle retry-ja; sada odbijen ODMAH po sadržaju
    # (isto pravilo kao za slike) — nema posla, nema čuvanja, pa ni ničega što bi moglo biti prikačeno.
    x = r.json()["rezultati"][0]
    assert x["ok"] is False and "nije PDF" in x["greska"] and "job_id" not in x
    assert b.tabele["intake_jobs"] == [] and b.tabele["predmet_dokumenti"] == []
