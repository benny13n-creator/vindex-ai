# -*- coding: utf-8 -*-
"""
Vindex AI — shared/evidence_graph.py

NS006 Task 4 — GRAF DOKAZA kao PROJEKCIJA postojećih redova, ne nova baza.

    TVRDNJA ↔ DOKUMENT ↔ PRAVNI ELEMENT ↔ PROTIVREČNOST ↔ POREKLO

Izvori su isključivo već postojeći: `predmet_dokazi` (tvrdnje, jedini pisac
shared/evidence_write.py), `predmet_dokumenti` (dokumenti + klasifikacija) i
perzistirane V2 kontradikcije (`services/v2_projection.py::ucitaj_v2_kontradikcije`).
Ništa se ne upisuje i ništa se ne zaključuje mimo onoga što redovi kažu.

Za svaku tvrdnju graf odgovara na pitanja iz mandata — ili kaže da ne zna:
  • šta se tvrdi                    → `vrednost`
  • ko tvrdi (čovek / model)        → `poreklo` (shared/genome_contract.py::poreklo_tvrdnje)
  • koji dokument je podržava        → `dokument_id` (samo dokument OVOG predmeta)
  • gde u dokumentu                  → `lokacija` (samo ako je pronađena u tekstu)
  • koji pravni element              → `pravni_element` ili `null` = nepoznato
  • da li joj se protivreči          → lista V2 kontradikcija, ili `null` = nepoznato
  • da li je bez potpore             → `potpora`

Klasifikacija dokumenta koja je PALA (`ai_tags._klasifikacija_greska`, Phoenix 006)
ostaje neuspeh: tip se tada NE prikazuje (podrazumevano „ostalo" nije rezultat).
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from shared.genome_contract import (
    DEGRADIRANO, KLASE_POREKLA, OK, PRAZNO, Razresavac, tvrdnja_u_stavku,
)

POTPORA_LOCIRANA = "LOCIRANA_U_DOKUMENTU"      # tvrdnja pronađena u tekstu svog dokumenta
POTPORA_DOKUMENT = "DOKUMENT_BEZ_LOKACIJE"     # vezana za dokument, mesto nije pronađeno
POTPORA_NEMA = "BEZ_POTPORE"                   # nije vezana ni za jedan dokument ovog predmeta

KLASIFIKACIJA_USPESNA = "USPESNA"
KLASIFIKACIJA_NEUSPESNA = "NEUSPESNA"
KLASIFIKACIJA_NIJE = "NIJE_KLASIFIKOVAN"


def _ai_tags(v: Any) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip():
        try:
            d = json.loads(v)
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}
    return {}


def klasifikacija_dokumenta(d: dict) -> dict:
    tagovi = _ai_tags(d.get("ai_tags"))
    if tagovi.get("_klasifikacija_greska"):
        return {"stanje": KLASIFIKACIJA_NEUSPESNA, "tip": None}
    if not d.get("klasifikovan_at"):
        return {"stanje": KLASIFIKACIJA_NIJE, "tip": None}
    return {"stanje": KLASIFIKACIJA_USPESNA, "tip": d.get("tip_dokaza")}


def _kljuc_elementa(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    k = re.sub(r"\s+", " ", v).strip().lower()
    return "element:" + k if k else None


def sastavi_graf(*, dokazi: Optional[list], dokumenti: Optional[list],
                 v2_kontradikcije: Optional[list], izvori: Optional[dict] = None,
                 legacy_kontradikcija: int = 0) -> dict:
    """Čista projekcija. `v2_kontradikcije=None` znači „nije pročitano" (protivrečnosti
    po tvrdnji su tada NEPOZNATE, ne prazne). `legacy_kontradikcija` je broj
    kontradikcija iz analize bez trajne veze na tvrdnje — ako ih ima a V2 ih nema,
    protivrečnost po tvrdnji je takođe NEPOZNATA."""
    izvori = dict(izvori or {})
    if izvori.get("dokazi", "OK") != "OK":
        return {"stanje": DEGRADIRANO, "tvrdnje": [], "dokumenti": [], "pravni_elementi": [], "veze": [],
                "sazetak": None, "razlog": "Tvrdnje predmeta nisu pročitane."}
    dok_ok = izvori.get("dokumenti", "OK") == "OK"
    raz = Razresavac(dokumenti if dok_ok else [])

    # protivrečnosti po tvrdnji: samo iz V2 (trajni UUID tvrdnji)
    if v2_kontradikcije is None or izvori.get("kontradikcije", "OK") != "OK":
        protiv: Optional[dict] = None
        razlog_protiv = "Kontradikcije nisu pročitane."
    elif not v2_kontradikcije and legacy_kontradikcija:
        protiv = None
        razlog_protiv = "Analiza navodi kontradikcije, ali bez trajne veze na tvrdnje."
    else:
        protiv = {}
        razlog_protiv = None
        for k in v2_kontradikcije:
            for c in k.get("claim_ids") or []:
                protiv.setdefault(str(c), []).append(str(k.get("id")))

    redovi = sorted((d for d in (dokazi or []) if isinstance(d, dict) and d.get("id") and d.get("deleted_at") is None),
                    key=lambda d: str(d["id"]))
    tvrdnje, veze, elementi = [], [], {}
    for r in redovi:
        s = tvrdnja_u_stavku(r, raz)
        if s["lokacija"]:
            s["potpora"] = POTPORA_LOCIRANA
        elif s["dokument_id"]:
            s["potpora"] = POTPORA_DOKUMENT
        else:
            s["potpora"] = POTPORA_NEMA
        s["protivrecnosti"] = None if protiv is None else sorted(protiv.get(s["id"], []))
        kel = _kljuc_elementa(s["pravni_element"])
        s["pravni_element_kljuc"] = kel
        tvrdnje.append(s)
        if s["dokument_id"]:
            veze.append({"od": s["id"], "do": s["dokument_id"], "vrsta": "potpora",
                         "lokacija": s["lokacija"]})
        if kel:
            elementi.setdefault(kel, {"kljuc": kel, "naziv": s["pravni_element"], "tvrdnje": []})["tvrdnje"].append(s["id"])
            veze.append({"od": s["id"], "do": kel, "vrsta": "element"})
    if protiv:
        for k in sorted(v2_kontradikcije or [], key=lambda x: str(x.get("id"))):
            clanovi = sorted(str(c) for c in (k.get("claim_ids") or []))
            for i, a in enumerate(clanovi):
                for b in clanovi[i + 1:]:
                    veze.append({"od": a, "do": b, "vrsta": "protivrecnost", "kontradikcija_id": str(k.get("id"))})

    po_dok: dict[str, int] = {}
    for s in tvrdnje:
        if s["dokument_id"]:
            po_dok[s["dokument_id"]] = po_dok.get(s["dokument_id"], 0) + 1
    dok_cvorovi = []
    if dok_ok:
        for d in sorted((x for x in (dokumenti or []) if isinstance(x, dict) and x.get("id")), key=lambda x: str(x["id"])):
            dok_cvorovi.append({"id": str(d["id"]), "naziv": d.get("naziv_fajla"), "redni_broj": d.get("redni_broj"),
                                "klasifikacija": klasifikacija_dokumenta(d), "broj_tvrdnji": po_dok.get(str(d["id"]), 0)})

    sazetak = {
        "tvrdnji": len(tvrdnje),
        "po_poreklu": {k: sum(1 for s in tvrdnje if s["poreklo"] == k) for k in KLASE_POREKLA},
        "locirano": sum(1 for s in tvrdnje if s["potpora"] == POTPORA_LOCIRANA),
        "vezano_za_dokument_bez_lokacije": sum(1 for s in tvrdnje if s["potpora"] == POTPORA_DOKUMENT),
        "bez_potpore": sum(1 for s in tvrdnje if s["potpora"] == POTPORA_NEMA),
        "sa_pravnim_elementom": sum(1 for s in tvrdnje if s["pravni_element"]),
        "procenjene_snage": sum(1 for s in tvrdnje if s["snaga_procenjena"]),
        "u_protivrecnosti": None if protiv is None else sum(1 for s in tvrdnje if s["protivrecnosti"]),
        "dokumenata": len(dok_cvorovi) if dok_ok else None,
        "neuspesnih_klasifikacija": (sum(1 for d in dok_cvorovi if d["klasifikacija"]["stanje"] == KLASIFIKACIJA_NEUSPESNA)
                                     if dok_ok else None),
    }
    return {
        "stanje": OK if tvrdnje else PRAZNO,
        "tvrdnje": tvrdnje,
        "dokumenti": dok_cvorovi,
        "dokumenti_stanje": OK if dok_ok else DEGRADIRANO,
        "pravni_elementi": [elementi[k] for k in sorted(elementi)],
        "veze": veze,
        "protivrecnosti_razlog": razlog_protiv,
        "sazetak": sazetak,
    }
