# -*- coding: utf-8 -*-
"""MIR001 FINAL RELEASE GATES, TASK-R4 (tačke 8–9) — READ-ONLY provera produkcije pre puštanja.
Samo HEAD zahtevi sa `Prefer: count=exact` (bez ijednog reda podataka, bez teksta, bez identifikatora) i ponovno
pokretanje R3 agregatnog inventara (`MIR001_R3_PROD_INVENTAR.py`, samo GET/HEAD). Ništa ne upisuje, ne poziva RPC ni
cron. Ključevi se nikad ne ispisuju. Upotreba: python -I -X utf8 MIR001_R4_PROD_PROVERA.py"""
import os
import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

env = {}
for l in open(os.environ.get("VINDEX_ENV_FILE", ".env"), encoding="utf-8"):
    if "=" in l and not l.lstrip().startswith("#"):
        k, v = l.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
URL, KEY = env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_SERVICE_KEY"]


def head(putanja):
    req = urllib.request.Request(f"{URL}/rest/v1/{putanja}", method="HEAD",
                                 headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Prefer": "count=exact"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return {"http": r.status, "broj": (r.headers.get("Content-Range") or "").split("/")[-1]}
    except urllib.error.HTTPError as e:
        return {"http": e.code, "broj": None}


rez = {
    # kontrola: nepostojeća tabela MORA dati 404, nepostojeća kolona 400 — inače zaključci ispod ne važe
    "kontrola_nepostojeca_tabela_http": head("mir001_nepostojeca_tabela?select=id")["http"],
    "kontrola_nepostojeca_kolona_http": head("staging_memory?select=mir001_nepostojeca_kolona")["http"],
    # NS007 (migracija 136): bez ovih tabela ciklus ne može da zauzme prozor ni da upiše rad
    "ns007_autonomy_cycles": head("autonomy_cycles?select=id"),
    "ns007_autonomy_work_items": head("autonomy_work_items?select=id"),
    # mrežno ponavljanje (migracija 134): skladište `Idempotency-Key` — bez njega zaštićene rute vraćaju 503
    "idempotency_v2_mutation_idempotency": head("v2_mutation_idempotency?select=user_id"),
    # migracija 140 (NS4): kolona `promocija_token` u staging_memory (200 = postoji, 400 = ne postoji)
    "m140_staging_promocija_token_http": head("staging_memory?select=promocija_token")["http"],
    # obim podataka koje MIR001 čita (samo broj)
    "predmeti": head("predmeti?select=id")["broj"],
    "predmet_dokumenti": head("predmet_dokumenti?select=id")["broj"],
    "staging_memory": head("staging_memory?select=id")["broj"],
    "case_actions_otvorene": head("case_actions?select=id&status=eq.open")["broj"],
}
print(json.dumps(rez, ensure_ascii=False, indent=1))
r3 = pathlib.Path(__file__).with_name("MIR001_R3_PROD_INVENTAR.py")
print("--- R3 inventar (ponovo) ---")
sys.stdout.flush()
subprocess.run([sys.executable, "-I", "-X", "utf8", str(r3)], check=True)
