# -*- coding: utf-8 -*-
"""
CONTRACT 01 (Upload tuzbe) — E2E Verified Coverage check, Faza A
Internal Integration Sprint (2026-07-19). Extended 2026-07-21 (G-001/
G-002 closure, commit 8f54f54) to actually check checks 4/5 instead of
hardcoding False. Extended again same day (G-003/D22 closure, commit
b84fd4b) to actually check check 6 (audit_immutable rows for
predmet_create/dokument_upload) instead of hardcoding False.

Reuses the Reality Validation harness (genome_case_dna_evaluate.run_batch)
to produce REAL evidence for the "Koji test potvrdjuje gotovost" row of
CONTRACT 01 in VINDEX_OPERATING_SYSTEM_CONTRACTS.md. Exercises the real
API (predmet create -> upload -> background Genome refresh -> event
dispatch), then additionally checks predmet_dokazi (Evidence Vault),
which run_batch itself does not check.

PredmetKreiran (checks 4/5): run_batch's predmet-create call goes
through httpx.ASGITransport against the real FastAPI app (in-process,
not mocked), so api.py::kreiraj_predmet's emit(EventType.PREDMET_KREIRAN)
call fires for real. But that emit() is bus.publish() -- in-memory
fire-and-forget, NOT written to the durable 'events' outbox table (that
durability is reserved for GenomeUpdated specifically -- see comment in
routers/case_dna.py::_emit_genome_event). So there is no direct DB row
proving the event itself fired. The only externally observable proof is
downstream: run_case_pipeline's step 9 (_step_istorija) always writes a
'[Pipeline] <date>' predmet_istorija row when the pipeline runs to
completion, and on_predmet_kreiran is the ONLY code path that calls
run_case_pipeline. So checks 4 and 5 are necessarily coupled -- proving
5 proves 4 by construction, not by a weaker assumption.

Creates ONE clearly-labeled test predmet in production. Not deleted
automatically -- kept as a permanent regression case, same policy as the
2026-07-18 synthetic calibration batch.
"""
import asyncio
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from genome_case_dna_evaluate import run_batch  # noqa: E402

FOUNDER_USER_ID = "384a7149-938b-4b83-99e0-8d7524e0581a"
FOUNDER_EMAIL = "benny13.n@gmail.com"

# [E2E CONTRACT01] prefix + datum -- svaki run mora biti odmah prepoznatljiv
# i filtrabilan medju stvarnim predmetima (founderov zahtev, 2026-07-21).
#
# 'opis' namerno nosi STVARAN pravni sadrzaj predmeta, ne opis testa samog
# sebe -- run_case_pipeline()-ov koraci (ekstrakcija_rokova/strategija/hcc/
# risk_snapshot, services/case_pipeline.py) citaju predmeti.opis, NE
# predmet_dokumenti.tekst_sadrzaj (to cita samo Genome, odvojeno). Prazan/
# meta opis bi dao lazan osecaj sigurnosti -- checks 5/7 bi prosli na
# besmislenom ulazu (founderova primedba, 2026-07-21). Sadrzi svih 6
# elemenata koje je founder trazio: stranke, datum dogadjaja, rok, pravni
# osnov, dokaz, potencijalni rizik -- isti predmet kao dokument ispod, ne
# izmisljena druga cinjenica.
CASE = {
    "label": "CONTRACT01-VERIFY",
    "naziv": f"[E2E CONTRACT01] Test predmet {date.today().isoformat()}",
    "opis": (
        "Marko Jovanovic (tuzilac) protiv DOO Alfa Trejd (tuzeni) — potrazivanje "
        "neisplacenih zarada za period januar-mart 2026. u iznosu od 350.000 RSD. "
        "Tuzeni je poslednju isplatu izvrsio 15.12.2025, nakon cega isplate nisu "
        "vrsene uprkos pisanim opomenama tuzioca. Pravni osnov: Zakon o radu (pravo "
        "na zaradu) i ZOO clan 262 (opsta pravila o obavezama). Dokaz: pisane opomene "
        "tuzioca i ugovor o radu. Rok: zastarelost potrazivanja zarade tri godine od "
        "dospelosti (Zakon o radu clan 196); rociste zakazano za 15.09.2026. Rizik: "
        "tuzeni moze osporiti postojanje ili visinu duga."
    ),
    "tip": "radni_spor",
    "documents": [
        {"filename": "tuzba.docx", "paragraphs": [
            "TUZBA",
            "Tuzilac Marko Jovanovic protiv tuzenog DOO Alfa Trejd, zbog neisplacene zarade.",
            "Tuzeni duguje tuziocu iznos od 350.000 RSD na ime neisplacenih zarada za period "
            "januar-mart 2026. godine.",
            "Tuzilac je bio zaposlen kod tuzenog od 01.01.2024. do 31.03.2026. godine, na "
            "poziciji komercijaliste, sa mesecnom bruto zaradom od 120.000 RSD.",
            "Tuzeni je poslednju isplatu zarade izvrsio 15.12.2025. godine, nakon cega isplate "
            "nisu vrsene uprkos vise pisanih opomena tuzioca.",
            "Predlaze se da sud obaveze tuzenog na isplatu duga sa zakonskom zateznom kamatom.",
        ]},
    ],
}


async def main():
    # Windows konzola je cp1252 po default-u -- srpska slova (č/ž/š...) u
    # pipeline porukama rusili su stdout print posle uspesnog zavrsetka testa
    # (2026-07-21 run). Ne utice na rezultate.json (UTF-8 fajl pisanje), samo
    # na terminal prikaz.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    out_dir = str(ROOT / "vindex_scraper_output" / "contract01_verify")
    results = await run_batch(
        cases=[CASE], user_id=FOUNDER_USER_ID, email=FOUNDER_EMAIL,
        out_dir=out_dir, poll_timeout_s=90.0, poll_interval_s=4.0,
    )
    r = results[0]

    from supabase import create_client
    import os
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    supa = create_client(
        os.environ["SUPABASE_URL"],
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_SERVICE_KEY"],
    )
    predmet_id = r.get("predmet_id")
    dokazi = []
    if predmet_id:
        dz = supa.table("predmet_dokazi").select("id,tvrdnja,kategorija").eq("predmet_id", predmet_id).execute()
        dokazi = dz.data or []

    # D22 check: audit_immutable rows for predmet_create/dokument_upload
    # (api.py::kreiraj_predmet / predmet_upload_auto_analyze, commit b84fd4b).
    # Fire-and-forget asyncio.create_task, not outbox-backed -- essentially
    # immediate, but poll briefly for eventual-consistency safety.
    audit_predmet_create = None
    audit_dokument_upload = None
    if predmet_id:
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and not (audit_predmet_create and audit_dokument_upload):
            if not audit_predmet_create:
                ac = supa.table("audit_immutable").select("action,resource_id,created_at") \
                    .eq("resource_type", "predmet").eq("resource_id", predmet_id) \
                    .eq("action", "predmet_create").limit(1).execute()
                if ac.data:
                    audit_predmet_create = ac.data[0]
            if not audit_dokument_upload:
                au = supa.table("audit_immutable").select("action,resource_id,created_at,metadata") \
                    .eq("resource_type", "dokument").eq("action", "dokument_upload") \
                    .order("created_at", desc=True).limit(5).execute()
                for row in (au.data or []):
                    # metadata je snimljen preko json.dumps() (shared/audit_immutable.py::
                    # _build_and_insert) -- vraca se kao STRING, ne parsiran dict.
                    raw_md = row.get("metadata")
                    try:
                        import json as _json2
                        md = _json2.loads(raw_md) if isinstance(raw_md, str) else (raw_md or {})
                    except Exception:
                        md = {}
                    if md.get("predmet_id") == predmet_id:
                        audit_dokument_upload = row
                        break
            if not (audit_predmet_create and audit_dokument_upload):
                await asyncio.sleep(2.0)

    # D3/D9 check: poll predmet_istorija for the pipeline's own completion
    # marker (services/case_pipeline.py::_step_istorija writes '[Pipeline] <date>'
    # unconditionally once all 9 steps finish). Pipeline starts at predmet-create
    # time (well before upload/Genome, which run_batch already waited up to 90s
    # for), so it is very likely already done -- poll briefly to be sure, not to
    # assume.
    pipeline_row = None
    pipeline_steps = None
    if predmet_id:
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            pr = supa.table("predmet_istorija").select("pitanje,odgovor") \
                .eq("predmet_id", predmet_id).like("pitanje", "[Pipeline]%") \
                .order("created_at", desc=True).limit(1).execute()
            if pr.data:
                pipeline_row = pr.data[0]
                break
            await asyncio.sleep(3.0)
        if pipeline_row:
            try:
                import json as _json
                pipeline_steps = _json.loads(pipeline_row.get("odgovor") or "{}")
            except Exception:
                pipeline_steps = None

    pipeline_ran = bool(pipeline_row)

    # AI-generating koraci pipeline-a (razlikuje "pipeline je protrcao" od
    # "pipeline je stvarno generisao sadrzaj") -- ekstrakcija_rokova/strategija/
    # hcc/risk_snapshot su jedini koraci koji zovu GPT; auto_linking/kalendar/
    # istorija su cist DB-read/write, ne dokazuju da je AI izlaz stvaran.
    ai_step_names = {"ekstrakcija_rokova", "strategija", "hcc", "risk_snapshot"}
    ai_output_nonempty = bool(pipeline_steps) and any(
        s.get("status") == "SUCCESS" and s.get("korak") in ai_step_names
        for s in (pipeline_steps.get("koraci") or [])
    )

    print("\n===== CONTRACT 01 — Upload tuzbe: E2E rezultat =====")
    checks = {
        "1. Klasifikacija automatska (predmet_dokumenti popunjen)": bool(r.get("documents_in_db")),
        "2. Evidence Vault upis automatski (predmet_dokazi red postoji)": bool(dokazi),
        "3. Case Genome regeneracija automatska (case_dna sa verzijom)": bool(r.get("genome")),
        "4. PREDMET_KREIRAN event emitovan (D3, zakljuceno iz #5)": pipeline_ran,
        "5. run_case_pipeline pokrenut (D9)": pipeline_ran,
        "6. Audit red za predmet_create/dokument_upload (D22)": bool(audit_predmet_create and audit_dokument_upload),
        "7. Pipeline AI izlaz nije prazan (bar 1 GPT korak SUCCESS)": ai_output_nonempty,
    }
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL/POZNATO'}] {k}")

    print(f"\n  predmet_id: {predmet_id}")
    print(f"  genome verzija: {(r.get('genome') or {}).get('verzija')}")
    print(f"  genome _verifikacija: {(r.get('genome') or {}).get('_verifikacija', {}).get('odluka')}")
    print(f"  GenomeUpdated event red: {'DA' if r.get('event_row') else 'NE'}")
    print(f"  audit_immutable (genome_refresh) red: {'DA' if r.get('audit_row') else 'NE'}")
    print(f"  audit_immutable (predmet_create) red: {'DA' if audit_predmet_create else 'NE'}")
    print(f"  audit_immutable (dokument_upload) red: {'DA' if audit_dokument_upload else 'NE'}")
    print(f"  predmet_dokazi (Evidence Vault) redova: {len(dokazi)}")
    if pipeline_steps:
        print(f"  pipeline koraci: {pipeline_steps.get('uspesno')} uspesno / "
              f"{pipeline_steps.get('preskoceno')} preskoceno / "
              f"{pipeline_steps.get('neuspesno')} neuspesno (od 8 -- korak 9, istorija, belezi ova 8, ne sebe)")
        for s in pipeline_steps.get("koraci", []):
            print(f"    - {s['korak']}: {s['status']} — {s['poruka']}")
    else:
        print("  pipeline koraci: NIJE PRONADJEN '[Pipeline]' red u predmet_istorija u roku od 60s")
    print(f"  upload greske: {r.get('upload_errors')}")
    print(f"  ukupno vreme: {r.get('total_elapsed_s')}s")

    print(f"\n  CONTRACT 01 Verified koraci (od kriticnih 1-3): "
          f"{sum(1 for k in list(checks)[:3] if checks[k])}/3")
    print(f"  CONTRACT 01 Verified koraci (D3/D9, verifikovano 2026-07-21): "
          f"{sum(1 for k in list(checks)[3:5] if checks[k])}/2")
    print(f"  CONTRACT 01 Verified koraci (D22, novo): "
          f"{1 if checks[list(checks)[5]] else 0}/1")


if __name__ == "__main__":
    asyncio.run(main())
