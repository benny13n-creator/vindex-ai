# -*- coding: utf-8 -*-
"""MIR001 FINAL RELEASE GATES, TASK-R3 — READ-ONLY inventar produkcije za procenu povratka (samo GET, sa straničenjem).
Čita SAMO kolone `tip, status, is_lawyer_approved, pinecone_indexed, confidence_score` iz `staging_memory` i broj
`predmet_dokumenti` redova nastalih promocijom nacrta (`storage_path` počinje sa `draft/staging/`). Bez teksta, bez
identifikatora, bez ključeva u izlazu. Ništa ne upisuje. Ispisuje SAMO agregatne brojeve.
Upotreba: python -I -X utf8 MIR001_R3_PROD_INVENTAR.py"""
import os
import json
import urllib.request
from collections import Counter

env = {}
for l in open(os.environ.get("VINDEX_ENV_FILE", ".env"), encoding="utf-8"):
    if "=" in l and not l.lstrip().startswith("#"):
        k, v = l.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
URL, KEY = env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_SERVICE_KEY"]
PRAG = 0.85
NOVI_TIPOVI = ("nacrt_iz_spisa", "dokument_za_sud")


def get(putanja):
    out, od = [], 0
    while True:
        req = urllib.request.Request(f"{URL}/rest/v1/{putanja}", method="GET",
                                     headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                                              "Range-Unit": "items", "Range": f"{od}-{od + 999}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
        out += d
        if len(d) < 1000:
            return out
        od += 1000


st = get("staging_memory?select=tip,status,is_lawyer_approved,pinecone_indexed,confidence_score")
iznad = lambda r: float(r.get("confidence_score") or 0) >= PRAG  # noqa: E731
rez = {
    "staging_ukupno": len(st),
    "po_statusu": dict(Counter(r["status"] for r in st)),
    "novi_tipovi_ukupno": sum(1 for r in st if r["tip"] in NOVI_TIPOVI),
    "novi_tipovi_po_tipu_i_statusu": dict(Counter(f"{r['tip']}:{r['status']}" for r in st if r["tip"] in NOVI_TIPOVI)),
    # stari kod: „odobri" bi uneo u bazu znanja (na čekanju, ocena ≥ prag)
    "na_cekanju_iznad_praga": sum(1 for r in st if r["status"] == "pending" and iznad(r)),
    # stari kod: „Ponovi upis" (odobren, potvrđen advokatom, nije indeksiran, ocena ≥ prag)
    "ponovni_upis_kandidati": sum(1 for r in st if r["status"] == "approved" and r.get("is_lawyer_approved") is True
                                  and r.get("pinecone_indexed") is not True and iznad(r)),
    "odobreno_indeksirano": sum(1 for r in st if r["status"] == "approved" and r.get("pinecone_indexed") is True),
    "odbijeno_a_indeksirano": sum(1 for r in st if r["status"] == "rejected" and r.get("pinecone_indexed") is True),
    "tipovi_ukupno": len({r["tip"] for r in st}),
}
dok = get("predmet_dokumenti?select=id&storage_path=like.draft%2Fstaging%2F*")
rez["predmet_dokumenti_iz_promocije_nacrta"] = len(dok)


def broj(putanja):
    """(HTTP status, ukupan broj) preko HEAD + `Prefer: count=exact` — bez ijednog reda podataka."""
    import urllib.error
    req = urllib.request.Request(f"{URL}/rest/v1/{putanja}", method="HEAD",
                                 headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Prefer": "count=exact"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, (r.headers.get("Content-Range") or "").split("/")[-1]
    except urllib.error.HTTPError as e:
        return e.code, None


# provera da upit zaista radi (a ne da tiho vraća prazno): nepostojeća kolona MORA dati 400
rez["kontrola_upit_radi"] = broj("staging_memory?select=nepostojeca_kolona")[0] == 400
rez["staging_count_exact"] = broj("staging_memory?select=id")[1]
rez["predmeti"] = broj("predmeti?select=id")[1]
rez["predmet_dokumenti"] = broj("predmet_dokumenti?select=id")[1]
rez["case_actions_otvorene"] = broj("case_actions?select=id&status=eq.open")[1]
# NS007: tabela trajnog autonomnog rada (migracija 136). 404 = tabela ne postoji → NS007 nema gde da upiše rad.
rez["ns007_autonomy_work_items_http"] = broj("autonomy_work_items?select=id")[0]
print(json.dumps(rez, ensure_ascii=False, indent=1))
