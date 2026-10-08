"""NS002 Task 5 — STVARNA FastAPI aplikacija za same-origin browser test V2 NG.

Nije pytest test (ne počinje sa `test_`). Pokreće ga
frontend-v2-ng/tests/live-fastapi-e2e.mjs kao zaseban proces.

Šta je STVARNO: api.py, ruta `lista_predmeta`, /v2/preview/ mount, svi
middleware-i, FastAPI/uvicorn HTTP. Šta je ZAMENJENO (samo dve stvari):
  • `api._require_auth` — prihvata isključivo determinističke lažne tokene;
  • `api._get_supa`     — lažni Supabase: beleži projekciju i filtere, PUCA na
                           svaki upis (insert/update/upsert/delete/rpc).
Dodatno: čuvar soketa blokira i beleži SVAKI pokušaj veze van loopback-a
(Supabase, OpenAI, Pinecone, vindex.rs, Railway, bilo šta). Uvicorn radi sa
lifespan="off": nijedan startup posao (workeri, dispečer, warmup) se ne pokreće.

Okruženje dolazi od pozivaoca, izgrađeno OD NULE sa lažnim vrednostima.
Dnevnik (JSON linije) ide u VX_E2E_LOG. Vrednosti tokena se nikad ne upisuju.
"""
import contextvars
import json
import os
import socket
import sys
import threading
import time
import types

LOG = os.environ["VX_E2E_LOG"]
PORT = int(os.environ["VX_E2E_PORT"])
_brava = threading.Lock()
# HTTP putanja zahteva u toku (prenosi se i u asyncio.to_thread) — da bi se
# svaki blokiran spoljni pokušaj pripisao tačnoj ruti.
_PUT = contextvars.ContextVar("vx_put", default="-")


def _zapisi(zapis):
    with _brava, open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(zapis, ensure_ascii=False) + "\n")


# ── 0. Okruženje: nikad stvarna baza ni produkcioni servis ──────────────────
for _k in ("SUPABASE_DB_URL", "DATABASE_URL"):
    if os.environ.get(_k):
        _zapisi({"vrsta": "okruzenje-greska", "kljuc": _k})
        sys.exit(3)
assert os.environ.get("SUPABASE_URL") == "https://fake.supabase.co"
# Bar jedan od V2 prekidača (preview ili, od NS004, primarni /app).
assert "1" in (os.environ.get("VINDEX_V2_NG_PREVIEW_ENABLED"), os.environ.get("VINDEX_V2_NG_PRIMARY_ENABLED"))

# ── 1. Čuvar soketa: samo loopback ──────────────────────────────────────────
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_orig_getaddrinfo = socket.getaddrinfo


def _cilj(adresa):
    return adresa[0] if isinstance(adresa, tuple) and adresa else str(adresa)


def _cuvar(self, adresa):
    host = _cilj(adresa)
    if host not in _LOOPBACK and self.family in (socket.AF_INET, socket.AF_INET6):
        _zapisi({"vrsta": "spoljna-veza-blokirana", "host": str(host)[:80], "put": _PUT.get()})
        raise OSError("e2e harness: spoljna mreža je zabranjena")
    return _orig_connect(self, adresa)


def _cuvar_ex(self, adresa):
    host = _cilj(adresa)
    if host not in _LOOPBACK and self.family in (socket.AF_INET, socket.AF_INET6):
        _zapisi({"vrsta": "spoljna-veza-blokirana", "host": str(host)[:80], "put": _PUT.get()})
        return 111
    return _orig_connect_ex(self, adresa)


def _dns(host, *a, **k):
    if host not in _LOOPBACK and host is not None:
        _zapisi({"vrsta": "spoljni-dns-blokiran", "host": str(host)[:80], "put": _PUT.get()})
        raise socket.gaierror("e2e harness: spoljni DNS je zabranjen")
    return _orig_getaddrinfo(host, *a, **k)


socket.socket.connect = _cuvar
socket.socket.connect_ex = _cuvar_ex
socket.getaddrinfo = _dns

# ── 2. Lažni podaci ─────────────────────────────────────────────────────────
TOKENI = {
    "vx-e2e-A": "korisnik-A", "vx-e2e-B": "korisnik-B", "vx-e2e-240": "korisnik-240",
    "vx-e2e-prazan": "korisnik-prazan", "vx-e2e-1037": "korisnik-1037",
    "vx-e2e-sporiA": "korisnik-sporiA", "vx-e2e-xss": "korisnik-xss",
    "vx-e2e-deleg": "korisnik-deleg",
}
KASNJENJE = {"korisnik-sporiA": 1.5}
XSS = '<img src=x onerror="window.__xss=1">Predmet<script>window.__xss=2</script>'


def _red(vlasnik, i, status="aktivan", brisanje=None, naziv=None):
    return {
        "id": f"{vlasnik}-{i:05d}", "user_id": vlasnik, "naziv": naziv or f"Predmet {vlasnik} broj {i}",
        "tip": "parnicni", "status": status, "broj_predmeta": f"P {1000 + i}/2026",
        "tuzilac": f"Tužilac {i}", "tuzeni": f"Tuženi {i}", "opis": f"opis {i}", "rizik": None,
        "vrednost_spora": 1000 + i, "created_at": f"2026-10-{1 + (i // 60) % 9:02d}T{(i % 24):02d}:00:00+00:00",
        "updated_at": "2026-10-06T10:00:00+00:00", "brisanje_zapoceto": brisanje,
        "case_dna": {"cinjenice": [f"Činjenica {k} predmeta {i}" for k in range(18)]},
    }


BAZA = (
    [_red("korisnik-A", i) for i in range(12)] + [_red("korisnik-A", 900 + i, status="zatvoren") for i in range(3)]
    + [_red("korisnik-B", i) for i in range(12)]
    + [_red("korisnik-240", i) for i in range(240)]
    + [_red("korisnik-1037", i, brisanje=("2026-10-06T10:00:00+00:00" if i % 150 == 7 else None)) for i in range(1037)]
    + [_red("korisnik-sporiA", i) for i in range(12)]
    + [_red("korisnik-xss", 0, naziv=XSS), _red("korisnik-xss", 1)]
)


# NS004: dokumenti, klijenti i delegiranja za detalj predmeta (postojeće rute).
def _dok(predmet, vlasnik, i, tekst, naziv=None):
    return {"id": f"{predmet}-d{i}", "predmet_id": predmet, "user_id": vlasnik, "naziv_fajla": naziv or f"Spis {i + 1} {predmet}.pdf",
            "storage_path": f"intake/{predmet}/{i}", "pinecone_namespace": f"kancelarija_{vlasnik}" if tekst is not None else "",
            "status": "indeksirano", "velicina_kb": 40 + i, "redni_broj": i + 1, "tip_dokaza": "podnesak",
            "created_at": f"2026-09-0{i + 1}T09:00:00+00:00", "tekst_sadrzaj": tekst}


TABELE = {
    "predmet_dokumenti": [
        _dok("korisnik-A-00000", "korisnik-A", 0, "TEKST-A0-d0 sadržaj spisa."), _dok("korisnik-A-00000", "korisnik-A", 1, ""),
        _dok("korisnik-B-00000", "korisnik-B", 0, "TAJNI-TEKST-B0"), _dok("korisnik-B-00001", "korisnik-B", 0, "TAJNI-TEKST-B1"),
        _dok("korisnik-xss-00000", "korisnik-xss", 0, "x", naziv='<script>window.__xss=4</script>spis.pdf'),
    ],
    "predmet_klijenti": [{"predmet_id": "korisnik-A-00000", "klijent_id": "kl-A1", "uloga_klijenta": "tužilac", "napomena": "", "kreirano": "2026-09-01"},
                         {"predmet_id": "korisnik-A-00000", "klijent_id": "kl-B1", "uloga_klijenta": "tuženi", "napomena": "", "kreirano": "2026-09-01"}],
    "klijenti": [{"id": "kl-A1", "user_id": "korisnik-A", "ime": "Ana", "prezime": "Jović", "firma": "", "tip": "fizicko", "status": "aktivan", "deleted_at": None},
                 {"id": "kl-B1", "user_id": "korisnik-B", "ime": "TAJNI", "prezime": "KlijentB", "firma": "", "tip": "fizicko", "status": "aktivan", "deleted_at": None}],
    "predmet_delegiranja": [{"id": "dl1", "predmet_id": "korisnik-B-00001", "na_user_id": "korisnik-deleg", "status": "aktivno"},
                            {"id": "dl2", "predmet_id": "korisnik-B-00002", "na_user_id": "korisnik-deleg", "status": "opozvano"}],
}


class _Upit:
    def __init__(self, tabela):
        self.tabela, self.kolone, self.filteri, self.ilike_, self.opseg = tabela, "*", [], None, None
        self.u_listi, self.je_null, self.jedan = [], [], None

    def select(self, kolone, count=None):
        self.kolone = kolone
        return self

    def eq(self, k, v):
        self.filteri.append((k, v))
        return self

    def ilike(self, k, v):
        self.ilike_ = (k, v)
        return self

    def order(self, *a, **k):
        return self

    def in_(self, k, vrednosti):
        self.u_listi.append((k, list(vrednosti)))
        return self

    def is_(self, k, v):
        self.je_null.append(k)
        return self

    # postgrest 2.28.3: maybe_single() vraća None kad nema reda; single() baca grešku.
    def maybe_single(self):
        self.jedan = "maybe"
        return self

    def single(self):
        self.jedan = "single"
        return self

    def range(self, a, b):
        self.opseg = (a, b)
        return self

    def limit(self, n):
        self.opseg = (0, n - 1)
        return self

    def execute(self):
        _zapisi({"vrsta": "upit", "tabela": self.tabela, "select": self.kolone,
                 "eq": [[k, v] for k, v in self.filteri], "opseg": list(self.opseg) if self.opseg else None})
        izvor = BAZA if self.tabela == "predmeti" else TABELE.get(self.tabela)
        if izvor is None:
            return types.SimpleNamespace(data=[], count=0)
        redovi = [r for r in izvor if all(r.get(k) == v for k, v in self.filteri)
                  and all(r.get(k) in v for k, v in self.u_listi) and all(r.get(k) is None for k in self.je_null)]
        if self.tabela != "predmeti":
            redovi = [dict(r) for r in redovi]
            if self.jedan:
                if not redovi:
                    if self.jedan == "single":
                        raise RuntimeError("postgrest APIError: 0 rows (single)")
                    return None
                return types.SimpleNamespace(data=redovi[0], count=1)
            return types.SimpleNamespace(data=redovi, count=len(redovi))
        vlasnik = dict(self.filteri).get("user_id")
        if vlasnik in KASNJENJE:
            time.sleep(KASNJENJE[vlasnik])
        redovi.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
        ukupno = len(redovi)
        if self.opseg:
            redovi = redovi[self.opseg[0]:self.opseg[1] + 1]
        if self.kolone != "*":
            polja = [c.strip() for c in self.kolone.split(",")]
            redovi = [{c: r.get(c) for c in polja} for r in redovi]
        if self.jedan:
            if not redovi:
                if self.jedan == "single":
                    raise RuntimeError("postgrest APIError: 0 rows (single)")
                return None
            return types.SimpleNamespace(data=dict(redovi[0]), count=1)
        return types.SimpleNamespace(data=redovi, count=ukupno)

    def __getattr__(self, ime):
        if ime in ("insert", "update", "upsert", "delete", "rpc"):
            _zapisi({"vrsta": "UPIS-POKUSAN", "tabela": self.tabela, "metod": ime, "put": _PUT.get()})
            raise AssertionError(f"e2e harness: upis zabranjen ({ime})")
        raise AttributeError(ime)


class _Supa:
    def table(self, ime):
        return _Upit(ime)

    def rpc(self, ime, *a, **k):
        _zapisi({"vrsta": "UPIS-POKUSAN", "tabela": "rpc", "metod": ime, "put": _PUT.get()})
        raise AssertionError("e2e harness: rpc zabranjen")


# ── 3. Stvarna aplikacija sa zamenjenim auth + Supabase ─────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _auth(authorization):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    uid = TOKENI.get(authorization[7:])
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid token")
    return types.SimpleNamespace(id=uid)


api._require_auth = _auth
api._get_supa = lambda: _Supa()


# NS004: preview/download koriste FastAPI zavisnost `get_current_user`.
async def _trenutni(authorization: str = __import__("fastapi").Header(None)):
    return {"user_id": _auth(authorization).id, "email": "e2e@primer.test"}


api.app.dependency_overrides[api.get_current_user] = _trenutni
# Rate limit nije predmet ovog testa (svi zahtevi dolaze sa 127.0.0.1).
api.limiter.enabled = False

# Audit zapis (postojeće ponašanje preview rute) se BELEŽI, ne šalje: odvojeno
# od upisa u podatke korisnika, da test pokaže tačno kada ga V2 izaziva.
import shared.audit_immutable as _audit  # noqa: E402


async def _audit_zapis(akcija, **k):
    _zapisi({"vrsta": "AUDIT", "akcija": akcija, "put": _PUT.get()})


_audit.log_action = _audit_zapis
import routers.dokument as _rdok  # noqa: E402

_rdok._fetch_session_tekst = lambda *a, **k: (_zapisi({"vrsta": "pinecone-fallback", "put": _PUT.get()}), "")[1]
_zapisi({"vrsta": "spreman", "preview_ruta": any(getattr(r, "path", "") == "/v2/preview/" for r in api.app.routes),
         "primarni": api._V2_NG_PRIMARNI_HTML is not None})

import uvicorn  # noqa: E402

async def _sa_putanjom(scope, receive, send):
    # Samo beleži putanju za dnevnik; zahtev ide nepromenjen u api.app.
    _PUT.set(scope.get("path", "-") if scope.get("type") == "http" else scope.get("type", "-"))
    await api.app(scope, receive, send)


uvicorn.run(_sa_putanjom, host="127.0.0.1", port=PORT, lifespan="off", log_level="warning", access_log=False)
