"""NS003 Task 6 — proba rollout-a V2 preview-a na PRODUKCIONOM Docker image-u.

Nije pytest test. Pokreće ga CI (`.github/workflows/v2-ng.yml`, job `rehearsal`)
na hostu sa Docker-om:  python tests/v2_ng_docker_rehearsal.py <image>

Isti image, tri uzastopna kontejnera sa PODRAZUMEVANOM komandom image-a
(`uvicorn api:app`, sa lifespan-om — kao u produkciji), `--network none`,
samo lažne vrednosti okruženja:
  A  preview flag ODSUTAN  → /health radi, legacy rute rade, /v2/preview* = 404
  B  flag = true           → /v2/preview(/) → ?rezim=live, demo samo eksplicitno,
                              src/ fonts/ brand/ služe tačne bajtove, ostalo 404
  C  flag ponovo ODSUTAN   → preview odmah nestaje (kill switch), legacy isti kao A
Zahtevi idu iz SAMOG kontejnera na 127.0.0.1 (docker exec), pa ni proba ni
aplikacija nemaju spoljnu mrežu. Pokušaji spoljne mreže pri startu se beleže
iz loga kontejnera kao INFO (očekivano: lažno okruženje bez mreže).
Ne koristi produkcione tajne, ne dira nijedan spoljni servis.
"""
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

KOREN = Path(__file__).resolve().parent.parent
NG = KOREN / "frontend-v2-ng"
IMAGE = sys.argv[1]
LAZNO = {
    "SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_ANON_KEY": "fake-anon-key",
    "SUPABASE_SERVICE_KEY": "fake-service-key", "SUPABASE_JWT_SECRET": "fake-jwt-secret-longer-than-32-chars-ok",
    "OPENAI_API_KEY": "sk-fake", "PINECONE_API_KEY": "fake-pinecone", "PINECONE_HOST": "https://fake.pinecone.io",
    "FIELD_ENCRYPTION_KEY": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "FOUNDER_EMAILS": "ci@example.com", "PORT": "8000",
}
KANONSKI_LOGO = {
    "Vindex_Transparent_EXACT_LOOK.svg": "a69b32383295eb8c3850bb01581bb370433bb1761a935f88f878a1fc4afffc3f",
    "Vindex_Protected_Light_Surface.png": "7485ddff765080615bcd90f04f383762770c41d8cf9e24fb21171088024eeae9",
}
LEGACY = ["/health", "/", "/app", "/app-v2", "/sw.js", "/manifest.json", "/offline", "/static/vindex.js", "/static/sw.js", "/api/predmeti"]
# NS004: primarni /app, stabilni asseti i legacy rezerva.
PRIMARNI = ["/app-legacy", "/app-legacy?posle=app", "/v2/app/src/app.js", "/v2/app/src/runtime.js",
            "/v2/app/brand/Vindex_Transparent_EXACT_LOOK.svg", "/v2/app/tests/live-api.mjs", "/v2/app/package.json"]
PREVIEW = ["/v2/preview", "/v2/preview/", "/v2/preview?x=1", "/v2/preview/?rezim=live", "/v2/preview/?rezim=demo",
           "/v2/preview/src/app.js", "/v2/preview/src/runtime.js", "/v2/preview/fonts/ibm-plex-sans/400.css",
           "/v2/preview/brand/Vindex_Transparent_EXACT_LOOK.svg", "/v2/preview/brand/Vindex_Protected_Light_Surface.png"]
SKRIVENO = ["/v2/preview/tests/live-api.mjs", "/v2/preview/README.md", "/v2/preview/package.json", "/v2/preview/serve.mjs",
            "/v2/preview/brand/Vindex_Approved_Reference_Source.png", "/v2/preview/brand/MANIFEST_SHA256.txt",
            "/v2/preview/brand/%2e%2e/serve.mjs", "/v2/preview/index.html"]

# Izvršava se U kontejneru: http.client ne prati preusmerenja.
SONDA = r'''
import hashlib, http.client, json, re, sys
out = {}
for put in sys.argv[1:]:
    c = http.client.HTTPConnection("127.0.0.1", 8000, timeout=20)
    c.request("GET", put)
    r = c.getresponse(); b = r.read()
    n = re.sub(rb"\?v=[A-Za-z0-9._-]+", b"?v=X", b)
    n = re.sub(rb"/v2/@[A-Za-z0-9._-]+/", b"/v2/@X/", n)
    n = re.sub(rb'"pid":\d+', b'"pid":0', n)
    out[put] = {"status": r.status, "loc": r.getheader("location", ""), "ct": r.getheader("content-type", ""),
                "xrt": r.getheader("x-robots-tag", ""), "sha": hashlib.sha256(b).hexdigest(), "norm": hashlib.sha256(n).hexdigest(),
                "telo": b[:300].decode("utf-8", "replace") if put == "/health" else ""}
print("@@" + json.dumps(out))
'''

pada = ukupno = 0


def zapisi(grupa, naziv, ok, detalj=""):
    global pada, ukupno
    ukupno += 1
    pada += not ok
    print(f"{'PASS' if ok else 'FAIL'}  [{grupa}] {naziv}{' — ' + str(detalj) if detalj else ''}", flush=True)


def docker(*a, provera=True):
    r = subprocess.run(["docker", *a], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if provera and r.returncode != 0:
        raise RuntimeError(f"docker {a[0]}: {r.stderr[-500:]}")
    return r.stdout.strip()


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def stanje(ime, flag, primarni=None):
    k = f"vx-rehearsal-{ime.lower()}"
    docker("rm", "-f", k, provera=False)
    dodatno = {**({"VINDEX_V2_NG_PREVIEW_ENABLED": flag} if flag else {}), **({"VINDEX_V2_NG_PRIMARY_ENABLED": primarni} if primarni else {})}
    env = [x for kv in {**LAZNO, **dodatno}.items() for x in ("-e", f"{kv[0]}={kv[1]}")]
    docker("run", "-d", "--name", k, "--network", "none", *env, IMAGE)  # podrazumevani CMD image-a
    spreman = False
    for _ in range(90):
        if docker("inspect", "-f", "{{.State.Running}}", k, provera=False) != "true":
            break
        r = subprocess.run(["docker", "exec", k, "python", "-c",
                            "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=3)"], capture_output=True)
        if r.returncode == 0:
            spreman = True
            break
        time.sleep(2)
    info = json.loads(docker("inspect", k))[0]
    log = docker("logs", k, provera=False) + subprocess.run(["docker", "logs", k], capture_output=True, text=True, errors="replace").stderr
    zapisi(ime, "kontejner (podrazumevani CMD: uvicorn api:app) je podignut i /health odgovara", spreman, "" if spreman else log[-600:])
    zapisi(ime, "mreža kontejnera je 'none' i image je isti", info["HostConfig"]["NetworkMode"] == "none" and info["Image"] == SLIKA,
           info["HostConfig"]["NetworkMode"])
    rez = {}
    if spreman:
        izlaz = docker("exec", k, "python", "-c", SONDA, *LEGACY, *PREVIEW, *SKRIVENO, *PRIMARNI)
        rez = json.loads([x for x in izlaz.splitlines() if x.startswith("@@")][-1][2:])
    spolja = [l for l in log.splitlines() if re.search(r"Temporary failure in name resolution|Name or service not known|Network is unreachable|ConnectError|nodename nor servname|getaddrinfo", l)]
    print(f"INFO  [{ime}] pokušaji spoljne mreže pri startu (blokirani, očekivano uz lažno okruženje): {len(spolja)} linija loga", flush=True)
    for l in sorted(set(re.sub(r"\d+", "N", l)[:140] for l in spolja))[:6]:
        print(f"INFO  [{ime}]     {l}", flush=True)
    uklj = "[V2-NG] preview UKLJUČEN" in log
    if rez:
        rez["_primarni_log"] = "[V2-NG] PRIMARNI /app" in log
        rez["_app_telo"] = docker("exec", k, "python", "-c",
                                  "import urllib.request as u;print(u.urlopen('http://127.0.0.1:8000/app').read().decode())")
    docker("rm", "-f", k, provera=False)
    return rez, uklj


SLIKA = docker("image", "inspect", "-f", "{{.Id}}", IMAGE)

# ── A: preview flag odsutan ──────────────────────────────────────────────
a, uklj_a = stanje("A-OFF", None)
if a:
    zapisi("A-OFF", "/health 200, status ok", a["/health"]["status"] == 200 and '"status":"ok"' in a["/health"]["telo"].replace(" ", ""), a["/health"]["telo"][:80])
    zapisi("A-OFF", "legacy rute rade (/, /app, /app-v2, /sw.js, /manifest.json, /offline, /static/*)",
           all(a[p]["status"] == 200 for p in LEGACY if p not in ("/api/predmeti",)), {p: a[p]["status"] for p in LEGACY})
    zapisi("A-OFF", "API ostaje zaštićen (/api/predmeti bez tokena = 401)", a["/api/predmeti"]["status"] == 401)
    zapisi("A-OFF", "svaka /v2/preview* putanja = 404 (nijedna V2 ljuska nije izložena)", all(a[p]["status"] == 404 for p in PREVIEW + SKRIVENO),
           {p: a[p]["status"] for p in PREVIEW + SKRIVENO if a[p]["status"] != 404})
zapisi("A-OFF", "log ne prijavljuje uključen preview", not uklj_a)

# ── B: preview flag = true ───────────────────────────────────────────────
b, uklj_b = stanje("B-ON", "true")
if b:
    zapisi("B-ON", "/v2/preview → 307 /v2/preview/?rezim=live", b["/v2/preview"]["status"] == 307 and b["/v2/preview"]["loc"] == "/v2/preview/?rezim=live", b["/v2/preview"]["loc"])
    zapisi("B-ON", "/v2/preview/ → 307 /v2/preview/?rezim=live (podrazumevano LIVE, nikad demo)", b["/v2/preview/"]["status"] == 307 and b["/v2/preview/"]["loc"] == "/v2/preview/?rezim=live", b["/v2/preview/"]["loc"])
    zapisi("B-ON", "postojeći upit se čuva (/v2/preview?x=1 → ?x=1&rezim=live)", b["/v2/preview?x=1"]["loc"] == "/v2/preview/?x=1&rezim=live", b["/v2/preview?x=1"]["loc"])
    idx = sha(NG / "index.html")
    zapisi("B-ON", "?rezim=live služi V2 index (bajt-identičan onom koji je e2e proverio u pregledaču)", b["/v2/preview/?rezim=live"]["status"] == 200 and b["/v2/preview/?rezim=live"]["sha"] == idx)
    zapisi("B-ON", "?rezim=demo ostaje dostupan samo eksplicitno, isti index (demo je jasno označen u pregledaču)", b["/v2/preview/?rezim=demo"]["status"] == 200 and b["/v2/preview/?rezim=demo"]["sha"] == idx)
    zapisi("B-ON", "HTML i preusmerenja nose X-Robots-Tag noindex, nofollow, noarchive",
           all(b[p]["xrt"] == "noindex, nofollow, noarchive" for p in ("/v2/preview", "/v2/preview/", "/v2/preview/?rezim=live")))
    zapisi("B-ON", "src/ i fonts/ služe tačne bajtove", b["/v2/preview/src/app.js"]["sha"] == sha(NG / "src/app.js") and b["/v2/preview/src/runtime.js"]["sha"] == sha(NG / "src/runtime.js")
           and b["/v2/preview/fonts/ibm-plex-sans/400.css"]["status"] == 200)
    zapisi("B-ON", "brand/ služi oba kanonska logo fajla, bajt-identična paketu",
           all(b["/v2/preview/brand/" + i]["status"] == 200 and b["/v2/preview/brand/" + i]["sha"] == s for i, s in KANONSKI_LOGO.items()))
    zapisi("B-ON", "tests/, README, package.json, serve.mjs, referenca, manifest, traversal → 404", all(b[p]["status"] == 404 for p in SKRIVENO),
           {p: b[p]["status"] for p in SKRIVENO if b[p]["status"] != 404})
    zapisi("B-ON", "API ostaje zaštićen (401)", b["/api/predmeti"]["status"] == 401)
    if a:
        razl = [p for p in LEGACY if (a[p]["status"], a[p]["norm"], a[p]["ct"]) != (b[p]["status"], b[p]["norm"], b[p]["ct"])]
        zapisi("B-ON", "legacy rute identične stanju A (preview ništa ne zaklanja)", not razl, razl)
zapisi("B-ON", "log prijavljuje uključen preview", uklj_b)

# ── C: kill switch — flag ponovo odsutan ─────────────────────────────────
c, uklj_c = stanje("C-OFF", None)
if c:
    zapisi("C-OFF", "preview odmah nestaje: svaka /v2/preview* putanja = 404", all(c[p]["status"] == 404 for p in PREVIEW + SKRIVENO))
    if a:
        razl = [p for p in LEGACY + PREVIEW + SKRIVENO if (a[p]["status"], a[p]["norm"], a[p]["ct"]) != (c[p]["status"], c[p]["norm"], c[p]["ct"])]
        zapisi("C-OFF", "ponašanje identično stanju A (legacy i preview)", not razl, razl)
zapisi("C-OFF", "log ne prijavljuje uključen preview", not uklj_c)
if a:
    zapisi("A-OFF", "primarni isključen: /app-legacy = /app (legacy), /v2/app/* = 404",
           a["/app-legacy"]["norm"] == a["/app"]["norm"] and all(a[p]["status"] == 404 for p in PRIMARNI if p.startswith("/v2/app/"))
           and "v2/app/src" not in a["_app_telo"] and not a["_primarni_log"])

# ── D: primarni /app uključen (preview ostaje isključen) ─────────────────
d, _ = stanje("D-PRIMARY-ON", None, primarni="true")
if d:
    zapisi("D-PRIMARY-ON", "/app je V2 NG sa assetima sa /v2/app/ (ne /v2/preview)", d["/app"]["status"] == 200 and 'src="/v2/app/src/runtime.js"' in d["_app_telo"]
           and "/v2/preview/" not in d["_app_telo"] and d["_primarni_log"])
    zapisi("D-PRIMARY-ON", "/v2/app asseti bajt-identični repozitorijumu, logo kanonski",
           d["/v2/app/src/app.js"]["sha"] == sha(NG / "src/app.js") and d["/v2/app/src/runtime.js"]["sha"] == sha(NG / "src/runtime.js")
           and d["/v2/app/brand/Vindex_Transparent_EXACT_LOOK.svg"]["sha"] == KANONSKI_LOGO["Vindex_Transparent_EXACT_LOOK.svg"])
    zapisi("D-PRIMARY-ON", "tests/ i package.json nisu izloženi", d["/v2/app/tests/live-api.mjs"]["status"] == 404 and d["/v2/app/package.json"]["status"] == 404)
    if a:
        zapisi("D-PRIMARY-ON", "/app-legacy = klasičan /app iz stanja A (rezerva)", d["/app-legacy"]["norm"] == a["/app"]["norm"])
        zapisi("D-PRIMARY-ON", "/app-legacy?posle=app = legacy + skript povratka", d["/app-legacy?posle=app"]["status"] == 200 and d["/app-legacy?posle=app"]["norm"] != a["/app"]["norm"])
        razl = [p for p in LEGACY if p != "/app" and (a[p]["status"], a[p]["norm"]) != (d[p]["status"], d[p]["norm"])]
        zapisi("D-PRIMARY-ON", "ostale rute identične stanju A; preview i dalje 404 (nezavisan)", not razl and all(d[p]["status"] == 404 for p in PREVIEW), razl)

# ── E: primarni ponovo isključen — /app je odmah legacy, bez izmene koda ─
e, _ = stanje("E-PRIMARY-OFF", None)
if e and a:
    razl = [p for p in LEGACY + PREVIEW + SKRIVENO + PRIMARNI if (a[p]["status"], a[p]["norm"]) != (e[p]["status"], e[p]["norm"])]
    zapisi("E-PRIMARY-OFF", "posle restarta bez prekidača: identično stanju A (legacy /app)", not razl and not e["_primarni_log"], razl)

print(f"\n{ukupno - pada}/{ukupno} PASS", flush=True)
sys.exit(1 if pada else 0)
