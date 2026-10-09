# -*- coding: utf-8 -*-
"""NS005 — stvarne FastAPI rute nad stanjem u memoriji, dva korisnika.

Nije test (ne počinje sa `test_`). Uvoze ga tests/test_ns005_*.py.

STVARNO: api.py, sve rute i njihove provere vlasništva, FastAPI/Starlette
HTTP preko TestClient-a. ZAMENJENO: (1) provera tokena — deterministički
lažni tokeni A/B/C; (2) Supabase — tabele u memoriji koje STVARNO primenjuju
filtere i STVARNO upisuju, pa test može da dokaže da tuđ red nije pročitan,
izmenjen ni povezan; (3) mreža — svaka veza van loopback-a puca.

Ništa ne ide u produkciju: SUPABASE_URL je lažan, OpenAI/Pinecone nedostupni.
"""
from __future__ import annotations

import copy
import sys
import itertools
import os
import socket
import types
import uuid
from datetime import datetime, timezone

# ── Mreža: samo loopback ─────────────────────────────────────────────────────
_LOOP = {"127.0.0.1", "::1", "localhost", "testserver"}
_orig_connect = socket.socket.connect
SPOLJNI_POKUSAJI: list = []


def _cuvar(self, adresa):
    host = adresa[0] if isinstance(adresa, tuple) and adresa else str(adresa)
    if host not in _LOOP and self.family in (socket.AF_INET, socket.AF_INET6):
        SPOLJNI_POKUSAJI.append(str(host))
        raise OSError("ns005 harness: spoljna mreža je zabranjena")
    return _orig_connect(self, adresa)


socket.socket.connect = _cuvar

# Lažne vrednosti (samo ako već nisu postavljene) — api.py ih traži pri uvozu.
for _k, _v in (("OPENAI_API_KEY", "sk-fake-ns005"), ("PINECONE_API_KEY", "fake-pinecone"),
               ("PINECONE_HOST", "https://fake.pinecone.io"), ("FOUNDER_EMAILS", "ci@example.com")):
    os.environ.setdefault(_k, _v)

TOKENI = {"tok-A": "uid-A", "tok-B": "uid-B", "tok-C": "uid-C"}


def zaglavlje(korisnik: str) -> dict:
    return {"Authorization": "Bearer tok-" + korisnik}


_brojac = itertools.count(1)


def _sada():
    # Mikrosekunde + brojač: redosled upisa je deterministički i u istoj sekundi.
    return datetime.now(timezone.utc).isoformat()


class _Rez(types.SimpleNamespace):
    pass


class _Upit:
    def __init__(self, baza, tabela):
        self.b, self.t = baza, tabela
        self.filt = []          # (op, kolona, vrednost)
        self.kol = "*"
        self.redosled = None
        self.opseg = None
        self.jedan = None
        self.radnja = ("select", None)
        self.brojanje = None

    # ── čitanje ──
    def select(self, kolone="*", count=None, **k):
        self.kol, self.brojanje = kolone, count
        return self

    def _f(self, op, k, v):
        self.filt.append((op, k, v))
        return self

    def eq(self, k, v): return self._f("eq", k, v)
    def neq(self, k, v): return self._f("neq", k, v)
    def gte(self, k, v): return self._f("gte", k, v)
    def gt(self, k, v): return self._f("gt", k, v)
    def lte(self, k, v): return self._f("lte", k, v)
    def lt(self, k, v): return self._f("lt", k, v)
    def in_(self, k, v): return self._f("in", k, list(v))
    def ilike(self, k, v): return self._f("ilike", k, v)
    def like(self, k, v): return self._f("ilike", k, v)

    def is_(self, k, v):
        return self._f("is", k, None if str(v).lower() == "null" else v)

    def not_(self, *a, **k):
        return self

    def or_(self, izraz, *a, **k):
        delovi = []
        for d in str(izraz).split(","):
            p = d.split(".", 2)
            if len(p) == 3:
                delovi.append((p[0], p[1], p[2]))
        return self._f("or", None, delovi)

    def contains(self, *a, **k):
        return self

    def order(self, kolona, desc=False, **k):
        self.redosled = (kolona, desc)
        return self

    def limit(self, n, *a, **k):
        self.opseg = (0, n - 1)
        return self

    def offset(self, n, *a, **k):
        duzina = (self.opseg[1] - self.opseg[0]) if self.opseg else 10 ** 9
        self.opseg = (n, n + duzina)
        return self

    def range(self, a, b, *x, **k):
        self.opseg = (a, b)
        return self

    def maybe_single(self):
        self.jedan = "maybe"
        return self

    def single(self):
        self.jedan = "single"
        return self

    # ── pisanje ──
    def insert(self, red, *a, **k):
        self.radnja = ("insert", red)
        return self

    def upsert(self, red, *a, **k):
        self.radnja = ("upsert", red)
        return self

    def update(self, polja, *a, **k):
        self.radnja = ("update", polja)
        return self

    def delete(self, *a, **k):
        self.radnja = ("delete", None)
        return self

    # ── izvršenje ──
    @staticmethod
    def _poklapa(r, op, k, v):
        x = r.get(k)
        if op == "eq":
            return x == v or (x is not None and v is not None and str(x) == str(v))
        if op == "neq":
            return str(x) != str(v)
        if op == "in":
            return x in v or str(x) in [str(y) for y in v]
        if op == "is":
            return x is None if v is None else x == v
        if op == "ilike":
            return x is not None and str(v).strip("%").lower() in str(x).lower()
        if x is None:
            return False
        if op == "gte": return str(x) >= str(v)
        if op == "gt": return str(x) > str(v)
        if op == "lte": return str(x) <= str(v)
        if op == "lt": return str(x) < str(v)
        return True

    def _filtrirani(self):
        redovi = self.b.tabele.setdefault(self.t, [])
        out = []
        for r in redovi:
            ok = True
            for op, k, v in self.filt:
                if op == "or":
                    if not any(self._poklapa(r, o2, k2, v2.replace("*", "%")) for k2, o2, v2 in v):
                        ok = False
                elif not self._poklapa(r, op, k, v):
                    ok = False
                if not ok:
                    break
            if ok:
                out.append(r)
        return out

    def _projekcija(self, r):
        """Kao PostgREST: vraćaju se SAMO tražene kolone; `tabela(k1,k2)` se ugnježđuje
        preko `<tabela bez s/i>_id` ili `predmet_id`."""
        if not self.kol or self.kol.strip() == "*":
            return r
        delovi, dubina, bafer = [], 0, ""
        for c in self.kol:
            if c == "(":
                dubina += 1
            elif c == ")":
                dubina -= 1
            if c == "," and dubina == 0:
                delovi.append(bafer.strip())
                bafer = ""
            else:
                bafer += c
        if bafer.strip():
            delovi.append(bafer.strip())
        out = {}
        for d in delovi:
            if "(" in d:
                ime, kol = d.split("(", 1)
                ime, kol = ime.strip(), [x.strip() for x in kol.rstrip(")").split(",")]
                strani = {"predmeti": "predmet_id", "kancelarije": "kancelarija_id"}.get(ime, ime.rstrip("i") + "_id")
                kljuc = r.get(strani)
                povezan = next((x for x in self.b.tabele.get(ime, []) if x.get("id") == kljuc), None)
                if povezan is None:
                    out[ime] = None
                elif kol == ["*"]:
                    out[ime] = copy.deepcopy(povezan)
                else:
                    out[ime] = {c: povezan.get(c) for c in kol}
            elif d == "*":
                out.update(r)
            else:
                out[d] = r.get(d)
        return out

    def execute(self):
        vrsta, telo = self.radnja
        self.b.dnevnik.append({"tabela": self.t, "radnja": vrsta, "filteri": [(o, k) for o, k, _ in self.filt]})
        if self.t in self.b.greske:
            raise self.b.greske[self.t]
        if vrsta in ("insert", "upsert"):
            novi = telo if isinstance(telo, list) else [telo]
            ubaceni = []
            for r in novi:
                r = copy.deepcopy(r)
                r.setdefault("id", str(uuid.uuid4()))
                r.setdefault("created_at", _sada())
                r.setdefault("kreirano", r["created_at"])
                r.setdefault("_rb", next(_brojac))
                for _kol, _vr in self.b.podrazumevano.get(self.t, {}).items():   # DEFAULT vrednosti kolona iz migracija
                    r.setdefault(_kol, copy.deepcopy(_vr))
                if self.t == "timer_sessions":  # kao DEFAULT now() / DEFAULT TRUE iz 003_billing.sql
                    r.setdefault("start_at", r["created_at"]); r.setdefault("aktivan", True)
                if self.t == "audit_immutable":  # seq je BIGSERIAL (redosled lanca odluka)
                    r.setdefault("seq", next(_brojac))
                kljuc = self.b.jedinstveno.get(self.t)
                if kljuc and vrsta == "insert" and any(all(x.get(c) == r.get(c) for c in kljuc) for x in self.b.tabele.get(self.t, [])):
                    # Kao PRIMARY KEY u Postgres-u: drugi INSERT istog kljuca pada (PostgREST APIError 23505).
                    raise Exception('{"code": "23505", "message": "duplicate key value violates unique constraint"}')
                if vrsta == "upsert":
                    self.b.tabele.setdefault(self.t, [])[:] = [x for x in self.b.tabele.get(self.t, []) if x.get("id") != r["id"]]
                self.b.tabele.setdefault(self.t, []).append(r)
                ubaceni.append(copy.deepcopy(r))
            return _Rez(data=ubaceni, count=len(ubaceni))
        pogodjeni = self._filtrirani()
        if vrsta == "update":
            for r in pogodjeni:
                r.update(copy.deepcopy(telo))
                # Isto kao trigger `update_predmeti_updated_at`: svaki UPDATE pomera updated_at.
                if self.t == "predmeti" or "updated_at" in r:
                    r["updated_at"] = _sada() + "#" + str(next(_brojac))
            return _Rez(data=[copy.deepcopy(r) for r in pogodjeni], count=len(pogodjeni))
        if vrsta == "delete":
            ids = {id(r) for r in pogodjeni}
            self.b.tabele[self.t] = [r for r in self.b.tabele.get(self.t, []) if id(r) not in ids]
            return _Rez(data=[copy.deepcopy(r) for r in pogodjeni], count=len(pogodjeni))
        redovi = [self._projekcija(copy.deepcopy(r)) for r in pogodjeni]
        if self.redosled:
            k, desc = self.redosled
            # Brojevi se porede kao brojevi (kao Postgres za BIGSERIAL/numeric): kao tekst bi 99 bilo posle 100.
            redovi.sort(key=lambda r: ((0, r.get(k), "") if isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool)
                                       else (1, 0, str(r.get(k) or "")), r.get("_rb", 0)), reverse=desc)
        ukupno = len(redovi)
        if self.opseg:
            redovi = redovi[self.opseg[0]:self.opseg[1] + 1]
        if self.jedan:
            if not redovi:
                if self.jedan == "single":
                    raise RuntimeError("postgrest APIError: 0 rows (single)")
                # Isto kao produkcija: shared/postgrest_compat.py normalizuje maybe_single()
                # tako da za 0 redova vraća odgovor sa data=None (ne None).
                return _Rez(data=None, count=None)
            return _Rez(data=redovi[0], count=1)
        return _Rez(data=redovi, count=ukupno)


class _Kofa:
    def __init__(self, sadrzaj, ime):
        self._s, self._ime = sadrzaj, ime

    def upload(self, path, file, file_options=None):
        k = (self._ime, path)
        if k in self._s and str((file_options or {}).get("upsert", "false")).lower() != "true":
            raise Exception("Duplicate: The resource already exists (409)")
        self._s[k] = bytes(file)
        return types.SimpleNamespace(path=path)

    def download(self, path):
        k = (self._ime, path)
        if k not in self._s:
            raise Exception("Object not found (404)")
        return self._s[k]

    def remove(self, paths):
        for p in paths:
            self._s.pop((self._ime, p), None)
        return []


class _Skladiste:
    """Supabase Storage u memoriji: `storage.from_(kofa).upload/download/remove`; `sadrzaj[(kofa, putanja)]`."""

    def __init__(self):
        self.sadrzaj = {}

    def from_(self, ime):
        return _Kofa(self.sadrzaj, ime)


class Baza:
    """Supabase u memoriji: `baza.tabele[ime]` je lista redova."""

    def __init__(self, tabele=None):
        self.tabele = copy.deepcopy(tabele or {})
        self.dnevnik = []
        self.greske = {}
        # Jedinstvenost koju baza sprovodi (migracija 134: PRIMARY KEY (user_id, idempotency_key)).
        self.jedinstveno = {"v2_mutation_idempotency": ("user_id", "idempotency_key")}
        # RPC implementacije po imenu (npr. intake red u tests/ns005_intake_fake.py); bez nje rpc vraća [].
        self.rpc_impl = {}
        self.podrazumevano = {}   # {tabela: {kolona: DEFAULT}} — kao DEFAULT u šemi
        self.storage = _Skladiste()

    def table(self, ime):
        return _Upit(self, ime)

    def from_(self, ime):
        return _Upit(self, ime)

    def rpc(self, ime, params=None, *a, **k):
        self.dnevnik.append({"tabela": "rpc:" + ime, "radnja": "rpc", "filteri": []})
        impl = self.rpc_impl.get(ime)
        if impl is None:
            return types.SimpleNamespace(execute=lambda: _Rez(data=[], count=0))

        def _izvrsi():
            if ("rpc:" + ime) in self.greske:
                raise self.greske["rpc:" + ime]
            d = impl(self, dict(params or {}))
            return _Rez(data=d, count=len(d) if isinstance(d, list) else 1)
        return types.SimpleNamespace(execute=_izvrsi)

    def upisi(self, tabela):
        return [z for z in self.dnevnik if z["tabela"] == tabela and z["radnja"] in ("insert", "update", "upsert", "delete")]


def pripremi(monkeypatch, tabele=None):
    """Vraća (TestClient, Baza) nad STVARNIM api.app sa zamenjenim auth/Supabase."""
    import api
    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    baza = Baza(tabele)

    def _auth(authorization):
        if not authorization or not str(authorization).startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Unauthorized")
        uid = TOKENI.get(str(authorization)[7:])
        if not uid:
            raise HTTPException(status_code=401, detail="Invalid token")
        return types.SimpleNamespace(id=uid, email=uid + "@primer.test")

    async def _trenutni(authorization: str = __import__("fastapi").Header(None)):
        u = _auth(authorization)
        return {"user_id": u.id, "email": u.email}

    monkeypatch.setattr(api, "_require_auth", _auth)
    monkeypatch.setattr(api, "_get_supa", lambda: baza)

    # Ruteri koji uvoze `_get_supa`/`_verify_token` direktno (from shared.deps import ...)
    # drže SVOJU referencu — zamenjuje se svaka, da nijedan put ne ode van memorije.
    import sys as _sys

    def _verify(tok):
        uid = TOKENI.get(str(tok))
        return {"sub": uid, "email": uid + "@primer.test"} if uid else None
    for _ime, _mod in list(_sys.modules.items()):
        if _mod is None or not (_ime.startswith(("routers.", "klijenti.", "shared.", "services.")) or _ime == "shared"):
            continue
        if hasattr(_mod, "_get_supa"):
            monkeypatch.setattr(_mod, "_get_supa", lambda: baza, raising=False)
        if hasattr(_mod, "_verify_token"):
            monkeypatch.setattr(_mod, "_verify_token", _verify, raising=False)
    api.app.dependency_overrides[api.get_current_user] = _trenutni
    monkeypatch.setattr(api.limiter, "enabled", False)
    try:
        import shared.deps as deps
        monkeypatch.setattr(deps, "_get_supa", lambda: baza, raising=False)
    except Exception:
        pass
    try:
        import shared.audit_immutable as audit

        async def _audit(*a, **k):
            return None
        monkeypatch.setattr(audit, "log_action", _audit)
    except Exception:
        pass
    # main._client pamti OpenAI klijent pri prvom pozivu; bez ovoga bi klijent napravljen u NS005 testu
    # preživeo test i zaobišao `patch("openai.OpenAI")` u kasnijim testovima (izmereno: test_intake_original_file_storage).
    _main = sys.modules.get("main")
    if _main is not None and hasattr(_main, "_client"):
        monkeypatch.setattr(_main, "_client", None)
    # Isto za keširane klijente pretrage (embedding/Pinecone/Cohere): ruta kao /api/praksa/search u NS005
    # testu bi ih inače napravila stvarne i ostavila za sledeće testove.
    _ret = sys.modules.get("app.services.retrieve")
    for _ime in ("_EMBEDDINGS", "_CLIENT", "_COHERE_CLIENT", "_PINECONE_INDEX"):
        if _ret is not None and hasattr(_ret, _ime):
            monkeypatch.setattr(_ret, _ime, None)
    klijent = TestClient(api.app, raise_server_exceptions=False)
    return klijent, baza


def ocisti():
    import api
    api.app.dependency_overrides.pop(api.get_current_user, None)
