# -*- coding: utf-8 -*-
"""
Vindex AI — services/law_brain_ispravke.py

NS008 Task 16 — advokatske ispravke kao institucionalno učenje kancelarije, determinističkim pregledom
(ADR-0006), bez treniranja modela. Ponovo se koristi POSTOJEĆI izričit ugovor ispravke:
`POST /api/smart-intake/entities/{id}/correct` → `extracted_entities.corrected_value` (+ audit `entity_corrected`).

ZATEČENO (dokazano): ADR-0006 opisuje tabelu `entity_corrections` i „lookup-and-boost", ali ni tabela ni kod ne
postoje — ispravka je ostajala zaključana u jednom dokumentu i ista greška se ponavljala u sledećem.

PRAVILA
  • Opseg = kancelarija: ispravke AKTIVNIH članova iste kancelarije (kanonsko razrešavanje
    `get_kancelarija_id_sync`); solo advokat = samo sopstvene. Druga kancelarija nikad.
  • Samo institucionalni entiteti (sudija, sud): to su normalizacije naziva. Imena stranaka, iznosi, rokovi i brojevi
    predmeta su ČINJENICE pojedinačnog predmeta i nikad se ne prenose u drugi predmet.
  • Dvosmislena ispravka (isti original → različite ispravke) → bez predloga.
  • Rezultat je PREDLOG sa poreklom; vrednost ekstrakcije se ne menja dok je advokat ne potvrdi.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

INSTITUCIONALNI = ("judge", "court")
_MAKS_POSLOVA = 300
_DEO = 200


def normalizuj(v: Optional[str]) -> str:
    """Ključ za PREPOZNAVANJE iste vrednosti u novoj ekstrakciji (OCR gubi dijakritike, velika slova, razmake)."""
    s = str(v or "").replace("đ", "dj").replace("Đ", "Dj")
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower()
    s = s.replace("dj", "d")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def _tacno(v: Optional[str]) -> str:
    """Tačan tekst (samo sabijeni razmaci) — ispravka „Petrovic" → „Petrović" JE ispravka."""
    return " ".join(str(v or "").split())


def _in(supa, tabela, kolone, kljuc, ids, dodatni=None) -> list:
    ids = sorted({str(i) for i in ids if i})
    out = []
    for i in range(0, len(ids), _DEO):
        q = supa.table(tabela).select(kolone).in_(kljuc, ids[i:i + _DEO])
        if dodatni:
            q = dodatni(q)
        out.extend(q.execute().data or [])
    return out


def clanovi_kancelarije(supa, user_id: str) -> list:
    from shared.kancelarija_utils import get_kancelarija_id_sync
    kanc = get_kancelarija_id_sync(supa, user_id)
    if not kanc:
        return [str(user_id)]
    clanovi = {str(user_id)}
    r = supa.table("kancelarija_clanovi").select("user_id,status").eq("kancelarija_id", kanc).eq("status", "ACTIVE").execute()
    clanovi |= {str(x["user_id"]) for x in (r.data or []) if x.get("user_id")}
    a = supa.table("kancelarije").select("admin_uid").eq("id", kanc).limit(1).execute()
    clanovi |= {str(x["admin_uid"]) for x in (a.data or []) if x.get("admin_uid")}
    return sorted(clanovi)


def ispravke_kancelarije(supa, user_id: str) -> dict:
    """{(entity_type, normalizovan_original): {ispravka, broj, kada}} — samo nedvosmislene ispravke."""
    clanovi = clanovi_kancelarije(supa, user_id)
    poslovi = []
    for i in range(0, len(clanovi), _DEO):
        poslovi += (supa.table("intake_jobs").select("id,uploaded_by").in_("uploaded_by", clanovi[i:i + _DEO])
                    .order("created_at", desc=True).limit(_MAKS_POSLOVA).execute().data or [])
    poslovi = [p for p in poslovi if str(p.get("uploaded_by")) in set(clanovi)][:_MAKS_POSLOVA]
    if not poslovi:
        return {}
    dokumenti = _in(supa, "intake_documents", "id,intake_job_id", "intake_job_id", [p["id"] for p in poslovi])
    if not dokumenti:
        return {}
    ent = _in(supa, "extracted_entities", "id,document_id,entity_type,value,corrected_value", "document_id",
              [d["id"] for d in dokumenti])
    grupe: dict = {}
    for e in ent:
        if e.get("entity_type") not in INSTITUCIONALNI:
            continue
        orig, isp = _tacno(e.get("value")), _tacno(e.get("corrected_value"))
        if not orig or not isp or orig == isp:
            continue
        grupe.setdefault((e["entity_type"], normalizuj(orig)), []).append((isp, str(e["id"])))
    kada: dict = {}
    sve_id = [eid for v in grupe.values() for _, eid in v]
    if sve_id:
        try:
            for a in _in(supa, "audit_immutable", "resource_id,action,created_at", "resource_id", sve_id,
                         lambda q: q.eq("action", "entity_corrected")):
                rid = str(a.get("resource_id") or "")
                if a.get("created_at") and (rid not in kada or str(a["created_at"]) > kada[rid]):
                    kada[rid] = str(a["created_at"])
        except Exception:
            kada = {}                       # datum je dodatak; bez njega predlog ostaje, datum = nepoznat
    out = {}
    for kljuc, lista in grupe.items():
        razlicite = {i for i, _ in lista}
        if len(razlicite) != 1:
            continue                        # dvosmisleno → nikad sistematski pogrešan odgovor
        datumi = sorted(kada[eid] for _, eid in lista if eid in kada)
        out[kljuc] = {"ispravka": sorted(i for i, _ in lista)[0], "broj": len(lista), "kada": datumi[-1] if datumi else None}
    return out


def predlog_za(entitet: dict, ispravke: dict) -> Optional[dict]:
    """Predlog za JEDAN neprovereni entitet ekstrakcije, ili None."""
    if entitet.get("reviewed") or entitet.get("corrected_value"):
        return None
    if entitet.get("entity_type") not in INSTITUCIONALNI:
        return None
    v = (entitet.get("value") or "").strip()
    nalaz = ispravke.get((entitet.get("entity_type"), normalizuj(v)))
    if not nalaz or nalaz["ispravka"] == _tacno(v):
        return None
    datum = (nalaz["kada"] or "")[:10]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", datum):
        datum = f"{datum[8:10]}.{datum[5:7]}.{datum[0:4]}."
    return {
        "vrednost": nalaz["ispravka"],
        "trust_class": "HUMAN_CORRECTION",
        "broj_ispravki": nalaz["broj"],
        "kada": nalaz["kada"],
        "razlog": (f"Advokat iz vaše kancelarije ispravio je „{v}“ u „{nalaz['ispravka']}“"
                   + (f" ({datum})." if datum else " (datum nije zabeležen).")
                   + " Proverite pre potvrde."),
    }
