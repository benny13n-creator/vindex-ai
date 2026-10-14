# -*- coding: utf-8 -*-
"""
Vindex AI — shared/rok_izvor.py

N03-FD6 — PROMENA IZVORA POSLE POTVRDE ROKA (upozorenje, ne opoziv).

Zaseban modul namerno: `shared/rok_potvrda.py` je jedini PISAC i jedini
CITAC odluke (FAZA 6.4.3/6.5, strukturno zakljucano testovima) i ne sme
gledati dokumente. Ovaj modul odluku samo CITA da bi znao KADA je doneta;
nikad je ne menja, ne opoziva i ne utice na `sme_pristupiti`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from shared.rok_potvrda import AKCIJA_POTVRDA, procitaj_lanac


def _vreme(v) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def izvor_uklonjen_posle_potvrde(redovi: Iterable[dict]) -> set:
    """N03-FD6 — POTVRDJENI rokovi u cijem je predmetu POSLE potvrde uklonjen dokument.

    Ovo je UPOZORENJE ZA PREGLED, ne ponistenje: potvrda advokata se ne brise,
    ne prepisuje i ne opoziva, i rok i dalje prolazi kanonsku politiku.

    Zasto samo upozorenje: veza rok -> dokument se ne moze DOKAZATI. Smart
    Intake rok nema `dokument_id`; Genome rok ga ima, ali je to model-pripisan
    izvor, a brisanje dokumenta ga ionako postavlja na NULL (FK ON DELETE SET
    NULL, migracija 126) — u trenutku promene veza nestaje. Zato se tvrdi samo
    ono sto JESTE dokazivo: u predmetu je posle potvrde uklonjen dokument
    (trajni `SourceInvalidated` dogadjaj, migracija 131/137). Da li je rok
    poticao iz njega, ne zna se — i tako se i kaze.

    Nova potvrda posle uklanjanja (advokat je ponovo pregledao) gasi upozorenje.
    Ulaz su redovi vec ograniceni na vlasnika (`id`, `predmet_id`). Pad citanja
    dize izuzetak — pozivalac mora reci da provera nije uradjena.
    """
    redovi = [r for r in (redovi or []) if r.get("id") and r.get("predmet_id")]
    if not redovi:
        return set()
    from shared.deps import _get_supa
    supa = _get_supa()
    ids = [str(r["id"]) for r in redovi]
    # NS2B-C F1: ceo lanac po stranama ili izuzetak (jedan upit je tiho secen na 1000 redova).
    lanac = procitaj_lanac(ids, "action, resource_id, seq, created_at")
    # NS2B-C: isto pravilo kao `rok_potvrda.odluke` — odbijanje je zavrsno, pa potvrda
    # upisana posle odbijanja (trka/zastareo prozor) ne vraca rok u „potvrdjen".
    potvrdjen_u: dict = {}
    odbijeni: set = set()
    for z in lanac:
        rid = str(z.get("resource_id"))
        if z.get("action") == AKCIJA_POTVRDA:
            if rid not in odbijeni:
                potvrdjen_u[rid] = _vreme(z.get("created_at"))
        else:
            odbijeni.add(rid)
            potvrdjen_u.pop(rid, None)
    if not potvrdjen_u:
        return set()
    predmeti = sorted({str(r["predmet_id"]) for r in redovi if str(r["id"]) in potvrdjen_u})
    dog = (supa.table("events")
           .select("predmet_id, created_at, payload")
           .eq("event_type", "SourceInvalidated")
           .in_("predmet_id", predmeti)
           .execute())
    poslednje_uklanjanje: dict = {}
    for e in (dog.data or []):
        if ((e.get("payload") or {}).get("source_type")) != "dokument":
            continue
        t = _vreme(e.get("created_at"))
        pid = str(e.get("predmet_id"))
        if t and (pid not in poslednje_uklanjanje or t > poslednje_uklanjanje[pid]):
            poslednje_uklanjanje[pid] = t
    out = set()
    for r in redovi:
        rid, pid = str(r["id"]), str(r["predmet_id"])
        t_potvrde, t_uklanjanja = potvrdjen_u.get(rid), poslednje_uklanjanje.get(pid)
        if t_potvrde and t_uklanjanja and t_uklanjanja > t_potvrde:
            out.add(rid)
    return out
