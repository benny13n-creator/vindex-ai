# -*- coding: utf-8 -*-
"""
Vindex AI — scripts/backfill_case_actions.py

Program Omega, Sprint 005 (2026-08-06) — Unified Operational Experience.

Zasto postoji: `case_actions` (Program Omega Sprint 003) se popunjava
ISKLJUCIVO kao posledica 4 dogadjaja (DOCUMENT_ACCEPTED, REVIEW_ACCEPTED,
ROCISTE_ZAKAZANO, DOCUMENT_BATCH_COMPLETED) — ispravno, deo Case Evolution
Engine-a, nijedan novi orkestrator. Ali to znaci da SVAKI predmet kreiran
PRE nego sto je Sprint 003 pusten u produkciju ima NULA `case_actions`
redova dok mu se sledeci put ne desi jedan od ta 4 dogadjaja — Workspace
(GET /api/workspace, Sprint 004/005) je za taj predmet TIHO PRAZAN, ne
zato sto predmet nema stvarnih rizika/rokova, vec zato sto niko jos nije
"dirnuo" taj predmet otkad je novi Action Engine postojao. Ovo je pronadjeno
tokom Sprint 005-ove Faze 7 forenzicke provere, imenovano kao OMEGA-014
(docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md).

Sta radi: za SVAKI predmet u `predmeti`, poziva TACNO istu, nepromenjenu
logiku koju `services/case_evolution.py::_consequence_refresh_case_actions`
koristi (_compute_target_actions + reconciliation) — ne racuna nista novo,
ne duplira algoritam, samo pokrece VEC POSTOJECI, VEC TESTIRANI put jednom
za svaki predmet koji ga jos nikad nije video. `event_id=None` na upisanim
redovima (nema stvarnog dogadjaja iza backfill-a — kolona je nullable,
migracija 099) — `correlation_id` je jedinstven po pokretanju skripte, tako
da se svi upisi iz jednog pokretanja mogu naci u audit logu zajedno.

Bezbedno za ponovno pokretanje: reconciliation logika je vec idempotentna
(ista kao za svaki pravi dogadjaj) — drugo pokretanje nad istim predmetima
ne pravi duplikate, samo potvrdjuje/azurira postojece redove.

Pokreni: python scripts/backfill_case_actions.py [--dry-run] [--user-id UID]
Zahteva .env sa SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY.

NAMERNO NIJE automatski pokrenuto ni ovde ni bilo gde u aplikaciji — ovo je
jednokratna migraciona operacija nad postojecim podacima, ista predostroznost
kao i za SQL migracije u ovom projektu (osnivac pokrece rucno kada odluci).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


async def _main(dry_run: bool, only_user_id: str | None) -> None:
    from services.case_evolution import _consequence_refresh_case_actions
    from services.event_bus import Event, EventType
    from shared.deps import _get_supa

    supa = _get_supa()
    correlation_id = f"backfill-case-actions-{uuid.uuid4().hex[:12]}"

    q = supa.table("predmeti").select("id,user_id,naziv")
    if only_user_id:
        q = q.eq("user_id", only_user_id)
    res = await asyncio.to_thread(q.execute)
    predmeti = res.data or []

    print(f"[backfill] {len(predmeti)} predmeta pronadjeno" + (f" (user_id={only_user_id})" if only_user_id else ""))
    print(f"[backfill] correlation_id={correlation_id} dry_run={dry_run}")

    ukupno_created = ukupno_updated = ukupno_closed = 0
    greske = 0

    for i, p in enumerate(predmeti, start=1):
        predmet_id = p["id"]
        if dry_run:
            print(f"[{i}/{len(predmeti)}] {predmet_id} ({p.get('naziv','')}) -- dry-run, preskoceno")
            continue
        event = Event(
            type=EventType.DOCUMENT_BATCH_COMPLETED,
            user_id=p.get("user_id") or "backfill",
            predmet_id=predmet_id,
            payload={"reason": "OMEGA-014_backfill"},
            correlation_id=correlation_id,
            event_id=None,
        )
        try:
            result = await _consequence_refresh_case_actions(event)
            print(f"[{i}/{len(predmeti)}] {predmet_id} ({p.get('naziv','')}) -- {result}")
            parts = dict(kv.split("=") for kv in result.split())
            ukupno_created += int(parts.get("created", 0))
            ukupno_updated += int(parts.get("updated", 0))
            ukupno_closed  += int(parts.get("closed", 0))
        except Exception as exc:
            greske += 1
            print(f"[{i}/{len(predmeti)}] {predmet_id} -- GRESKA: {exc}")

    print("\n[backfill] Zavrseno.")
    print(f"[backfill] created={ukupno_created} updated={ukupno_updated} closed={ukupno_closed} greske={greske}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Samo prikazi koliko predmeta bi bilo obradjeno, ne upisuj nista.")
    parser.add_argument("--user-id", default=None, help="Ogranici backfill na jednog korisnika (testiranje pre punog pokretanja).")
    args = parser.parse_args()
    asyncio.run(_main(dry_run=args.dry_run, only_user_id=args.user_id))
