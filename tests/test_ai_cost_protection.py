# -*- coding: utf-8 -*-
"""
Early Access, Faza A — AI zaštita troška: adversarijalni deterministički dokazi (A6).

ŠTA SE MERI I KAKO
  • Provajder se lažira na HTTP transportu (`httpx.AsyncClient.send`/`httpx.Client.send`),
    ne na nivou funkcije. Zato kroz test prolazi PRAVI OpenAI SDK: njegovi interni
    retry-ji, `_build_request` (brojač pokušaja brane) i SEC-003 wrapperi. „Broj poziva
    provajdera" = broj HTTP zahteva koji je napustio SDK ka api.openai.com.
  • Baza se lažira ugovorom migracija 107/108: `deduct_n_credits` (uslovni atomični
    odbitak, -1 = nije naplaćeno), `refund_n_credits`, `increment_feature_usage` (atomični
    brojač sa dnevnim limitom). Atomičnost je ovde brava; nad stvarnim PostgreSQL-om je
    dokazuje `test_ai_cost_protection_postgres.py`.
  • Rute su prave FastAPI rute sa pravim `PermissionService.require`, pravim
    `UsageService.consume` i pravim middleware-om brane. Jedna je produkciona
    (`/api/style/profil/gradi` iz `api.app`) — dokaz da je brana ožičena u aplikaciji.

Za SVAKI slučaj odbijen pre izvršenja tvrdi se: broj poziva provajdera == 0.
"""
import asyncio
import json
import logging
import os
import sys
import threading
import time
import types
import uuid
from datetime import datetime, timezone

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")   # moduli prave klijente pri uvozu; ključ nije stvaran

import api  # noqa: E402,F401  — instalira SEC-003 wrappere i AI budžet na SDK klasama
import openai  # noqa: E402
from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from shared import ai_budget, deps, feature_registry  # noqa: E402
from shared import usage as usage_mod  # noqa: E402
from shared.ai_budget import AIBudzetMiddleware, AIBudzetOdbijen  # noqa: E402
from shared.permissions import PermissionService  # noqa: E402
from shared.usage import UsageService  # noqa: E402

FOUNDER = "founder@vindex.test"


# ═══════════════════════════════════════════════════════════════════════════
# Lažna baza sa ugovorom migracija 107/108 + ubrizgavanje kvarova
# ═══════════════════════════════════════════════════════════════════════════

class _Res:
    def __init__(self, data):
        self.data = data


class FakeBaza:
    def __init__(self):
        self.lock = threading.Lock()
        self.krediti: dict[str, int] = {}
        self.upotreba: dict[tuple, dict] = {}
        self.log: list[dict] = []
        self.kvar: dict[str, str] = {}      # ime → "raise" | "izgubljen_odgovor"
        self.rpc_pozivi: list[str] = []

    # RPC ugovori (doslovno po SQL telima migracija 107/108)
    def rpc(self, ime, p):
        self.rpc_pozivi.append(ime)
        kvar = self.kvar.get(ime)
        if kvar == "raise":
            raise RuntimeError(f"simuliran pad baze: {ime}")
        with self.lock:
            if ime == "deduct_n_credits":
                n = p["p_n"]
                if n is None or n <= 0 or self.krediti.get(p["p_user_id"], -1) < n:
                    out = -1
                else:
                    self.krediti[p["p_user_id"]] -= n
                    out = self.krediti[p["p_user_id"]]
            elif ime == "refund_n_credits":
                if p["p_n"] is None or p["p_n"] <= 0 or p["p_user_id"] not in self.krediti:
                    out = -1
                else:
                    self.krediti[p["p_user_id"]] += p["p_n"]
                    out = self.krediti[p["p_user_id"]]
            elif ime == "increment_feature_usage":
                k = (p["p_user_id"], p["p_feature"], p["p_dan"])
                red = self.upotreba.get(k)
                lim = p["p_dnevni_limit"]
                if red is None:
                    self.upotreba[k] = {"broj_koriscenja": 1, "krediti_potroseni": p["p_credits"], "mesec": p["p_mesec"]}
                    out = 1
                elif lim is None or red["broj_koriscenja"] < lim:
                    red["broj_koriscenja"] += 1
                    out = red["broj_koriscenja"]
                else:
                    out = -1
            elif ime == "increment_monthly_usage":
                out = 1
            else:
                out = None
        if kvar == "izgubljen_odgovor":
            # Transakcija JE izvršena, odgovor nije stigao (prekid veze posle COMMIT-a).
            raise ConnectionError(f"simuliran izgubljen odgovor baze: {ime}")
        return out


class _Upit:
    def __init__(self, baza: FakeBaza, tabela: str):
        self.b, self.t = baza, tabela
        self.f: dict = {}
        self.op = "select"
        self.payload = None
        self.jedan = False

    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def insert(self, payload, **_k):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload, **_k):
        self.op, self.payload = "update", payload
        return self

    def eq(self, k, v):
        self.f[k] = v
        return self

    def maybe_single(self):
        self.jedan = True
        return self

    def __getattr__(self, _ime):   # order/limit/lt/... — ne utiču na ove tabele
        return lambda *a, **k: self

    def execute(self):
        b = self.b
        if self.t == "user_credits":
            if b.kvar.get("user_credits") == "raise":
                raise RuntimeError("simuliran pad baze: user_credits")
            uid = self.f.get("user_id")
            if self.op == "insert":
                with b.lock:
                    b.krediti.setdefault(self.payload["user_id"], self.payload["credits_remaining"])
                return _Res([self.payload])
            with b.lock:
                return _Res([{"credits_remaining": b.krediti[uid]}] if uid in b.krediti else [])
        if self.t == "profiles":
            return _Res([{"is_pro": False, "subscription_type": "basic", "addons": [], "subscription_expires_at": None,
                          "subscription_seats_extra": 0, "rollout_flags": [], "digitalna_imovina_aktivirano": False,
                          "digitalna_imovina_standalone": False}])
        if self.t == "feature_usage" and self.op == "select":
            with b.lock:
                if "dan" in self.f:
                    red = b.upotreba.get((self.f["user_id"], self.f["feature_key"], self.f["dan"]))
                    return _Res(dict(red) if (red and self.jedan) else ([dict(red)] if red else (None if self.jedan else [])))
                return _Res([dict(r) for (u, f, _d), r in b.upotreba.items()
                             if u == self.f.get("user_id") and f == self.f.get("feature_key")])
        if self.t == "feature_usage_log" and self.op == "insert":
            with b.lock:
                b.log.append(dict(self.payload))
            return _Res([self.payload])
        return _Res([] if not self.jedan else None)


class FakeSupa:
    def __init__(self, baza):
        self.b = baza

    def table(self, ime):
        return _Upit(self.b, ime)

    def rpc(self, ime, params):
        b = self.b
        return types.SimpleNamespace(execute=lambda: _Res(b.rpc(ime, params)))


# ═══════════════════════════════════════════════════════════════════════════
# Lažni provajder na HTTP transportu
# ═══════════════════════════════════════════════════════════════════════════

class Provajder:
    def __init__(self):
        self.lock = threading.Lock()
        self.zahtevi: list[dict] = []
        self.rezim = "ok"            # ok | timeout | 500

    @property
    def broj(self):
        return len(self.zahtevi)

    def odgovor(self, request: httpx.Request) -> httpx.Response:
        with self.lock:
            try:
                telo = json.loads(request.content or b"{}")
            except Exception:
                telo = {}
            self.zahtevi.append({"put": request.url.path, "telo": telo})
        if self.rezim == "timeout":
            raise httpx.ReadTimeout("simuliran timeout provajdera", request=request)
        if self.rezim == "500":
            return httpx.Response(500, json={"error": {"message": "x", "type": "server_error"}}, request=request)
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, request=request, json={
                "object": "list", "model": telo.get("model", "text-embedding-3-small"),
                "data": [{"object": "embedding", "index": 0, "embedding": [0.0, 0.1]}],
                "usage": {"prompt_tokens": 10, "total_tokens": 10}})
        return httpx.Response(200, request=request, json={
            "id": "chatcmpl-test", "object": "chat.completion", "created": 0, "model": telo.get("model", "gpt-4o-mini"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "{\"ok\": true}"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}})


@pytest.fixture
def svet(monkeypatch):
    baza = FakeBaza()
    supa = FakeSupa(baza)
    prov = Provajder()

    monkeypatch.setattr(deps, "_get_supa", lambda: supa)
    monkeypatch.setattr(usage_mod, "_get_supa", lambda: supa)
    monkeypatch.setattr(deps, "FOUNDER_EMAILS", {FOUNDER})

    def _verify(token):
        if not token.startswith("tok-"):
            return None
        uid = token[4:]
        return {"sub": uid, "email": FOUNDER if uid == "founder" else f"{uid}@vindex.test"}
    monkeypatch.setattr(deps, "_verify_token", _verify)

    politike = {
        "t_ai": {"krediti": 2},
        "t_ai_1": {"krediti": 1},
        "t_ai_x3": {"krediti": 1, "credit_multiplier": 3},
        "t_besplatno": {"krediti": 0, "dnevni_limit": 2},
        "style_checker": {"krediti": 1},
        "ai_osnovna_obrada": {"krediti": 0, "dnevni_limit": 300},
    }
    cache = {k: {"feature_key": k, "aktivno": True, "status": "ACTIVE", "minimum_plan": None, "addon": None,
                 "dnevni_limit": None, "mesecni_limit": None, "cooldown_seconds": None, "credit_multiplier": 1,
                 "ai_model": "gpt-4o-mini", **v} for k, v in politike.items()}
    monkeypatch.setattr(feature_registry, "_CACHE", cache)
    monkeypatch.setattr(feature_registry, "_CACHE_LOADED_AT", time.monotonic() + 10 ** 9)
    monkeypatch.setattr(feature_registry, "_DEPS_CACHE_LOADED_AT", time.monotonic() + 10 ** 9)
    monkeypatch.setattr(feature_registry, "_DEPS_CACHE", {})

    orig_async, orig_sync = httpx.AsyncClient.send, httpx.Client.send

    async def _async_send(self, request, *a, **k):
        if request.url.host == "api.openai.com":
            return prov.odgovor(request)
        return await orig_async(self, request, *a, **k)

    def _sync_send(self, request, *a, **k):
        if request.url.host == "api.openai.com":
            return prov.odgovor(request)
        return orig_sync(self, request, *a, **k)
    monkeypatch.setattr(httpx.AsyncClient, "send", _async_send)
    monkeypatch.setattr(httpx.Client, "send", _sync_send)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    monkeypatch.delenv("VINDEX_AI_BUDZET", raising=False)
    ai_budget._resetuj_projekat_za_test()
    yield types.SimpleNamespace(baza=baza, prov=prov)
    ai_budget._resetuj_projekat_za_test()


class _Zapis(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.linije: list[str] = []

    def emit(self, record):
        self.linije.append(record.getMessage())

    @property
    def text(self):
        return "\n".join(self.linije)


@pytest.fixture
def zapis(monkeypatch):
    """Sopstveni handler direktno na loggerima koje tvrdnje čitaju. `caplog` zavisi od
    propagacije do korena, a raniji testovi u punoj sviti (dictConfig sa
    disable_existing_loggers) gase postojeće loggere — tada je `caplog.text` prazan."""
    h = _Zapis()
    # Loggeri MODULA (ne `logging.getLogger`): u punoj sviti neki test zameni registar
    # loggera, pa isto ime vraća drugi objekat od onog u koji moduli pišu.
    zahvaceni = [sys.modules["shared.ai_budget"].logger, sys.modules["shared.deps"].logger]
    for lg in zahvaceni:
        monkeypatch.setattr(lg, "disabled", False)
        lg.addHandler(h)
    # UI fixture-i u sviti zovu `logging.disable(CRITICAL)`; `Logger` kešira
    # `isEnabledFor`, pa samo `logging.disable()` (koji čisti keš) vraća beleženje.
    pre = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    try:
        yield h
    finally:
        logging.disable(pre)
        for lg in zahvaceni:
            lg.removeHandler(h)


# ═══════════════════════════════════════════════════════════════════════════
# Test aplikacija: isti middleware, ista obrada odbijanja, pravi servisi
# ═══════════════════════════════════════════════════════════════════════════

_POSLEDNJA_OP: dict = {}


def _klijent():
    return openai.AsyncOpenAI(api_key="sk-test-not-real", max_retries=2)


async def _chat(model="gpt-4o-mini", sadrzaj="Pitanje.", **kw):
    return await _klijent().chat.completions.create(
        model=model, messages=[{"role": "user", "content": sadrzaj}], **kw)


def _napravi_app():
    app = FastAPI()
    app.add_middleware(AIBudzetMiddleware)

    @app.exception_handler(AIBudzetOdbijen)
    async def _h(request: Request, exc: AIBudzetOdbijen):
        return JSONResponse(status_code=exc.status, content={"detail": exc.detalj})

    # Ista 5xx granica kao produkcija (api.py) — vraća stvarni razlog progutanog odbijanja.
    from starlette.exceptions import HTTPException as _SHE
    app.add_exception_handler(_SHE, api._http_exception_boundary)

    def _zapamti():
        _POSLEDNJA_OP["op"] = ai_budget.tekuca_operacija()

    @app.post("/posle")                      # dominantan obrazac: AI pa consume
    async def posle(user=Depends(PermissionService.require("t_ai"))):
        _zapamti()
        await _chat()
        await UsageService.consume(user["user_id"], user["email"], "t_ai")
        return {"ok": True}

    @app.post("/posle_1")
    async def posle_1(user=Depends(PermissionService.require("t_ai_1"))):
        _zapamti()
        await _chat()
        await UsageService.consume(user["user_id"], user["email"], "t_ai_1")
        return {"ok": True}

    @app.post("/pre")                        # pre-deduct obrazac: consume pa AI
    async def pre(user=Depends(PermissionService.require("t_ai"))):
        _zapamti()
        await UsageService.consume(user["user_id"], user["email"], "t_ai")
        await _chat()
        return {"ok": True}

    @app.post("/x3")
    async def x3(user=Depends(PermissionService.require("t_ai_x3"))):
        _zapamti()
        await _chat()
        await UsageService.consume(user["user_id"], user["email"], "t_ai_x3")
        return {"ok": True}

    @app.post("/x3_modul")                   # ista funkcija (×3), ali jedan modul: consume(multiplier=1)
    async def x3_modul(user=Depends(PermissionService.require("t_ai_x3"))):
        ai_budget.ocekivani_multiplikator(1)
        _zapamti()
        await _chat()
        await UsageService.consume(user["user_id"], user["email"], "t_ai_x3", multiplier=1)
        return {"ok": True}

    @app.post("/x3_neizjavljen")             # multiplier=1 bez izjave: rezerviše se registarska cena, višak se vraća
    async def x3_neizjavljen(user=Depends(PermissionService.require("t_ai_x3"))):
        _zapamti()
        await _chat()
        await UsageService.consume(user["user_id"], user["email"], "t_ai_x3", multiplier=1)
        return {"ok": True}

    @app.post("/savetnici")                  # dinamički: gornja granica 3, naplata po isporučenom (kao run_parallel)
    async def savetnici(uspelo: int, user=Depends(PermissionService.require("t_ai_1"))):
        ai_budget.ocekivani_multiplikator(3)
        _zapamti()
        await asyncio.gather(_chat(), _chat(), _chat())
        if uspelo:
            await UsageService.consume(user["user_id"], user["email"], "t_ai_1", multiplier=uspelo)
        return {"ok": True}

    @app.post("/niz")                        # pipeline: gornja granica 3, svaki korak consume(×1) posle svog poziva
    async def niz(koraka: int, user=Depends(PermissionService.require("t_ai_1"))):
        ai_budget.ocekivani_multiplikator(3)
        _zapamti()
        for _ in range(koraka):
            await _chat()
            await UsageService.consume(user["user_id"], user["email"], "t_ai_1")
        return {"ok": True}

    @app.post("/kasna_izjava")               # izjava POSLE prvog poziva: ignoriše se, beleži se
    async def kasna_izjava(user=Depends(PermissionService.require("t_ai_x3"))):
        _zapamti()
        await _chat()
        ai_budget.ocekivani_multiplikator(1)
        await UsageService.consume(user["user_id"], user["email"], "t_ai_x3")
        return {"ok": True}

    @app.post("/ugnezdeno")                  # tri podpoziva iste operacije, paralelno
    async def ugnezdeno(user=Depends(PermissionService.require("t_ai"))):
        _zapamti()
        await asyncio.gather(_chat(), _chat(), _chat())
        await UsageService.consume(user["user_id"], user["email"], "t_ai")
        return {"ok": True}

    @app.post("/bez_naplate")                # ruta koja AI ne naplaćuje (odluka proizvoda)
    async def bez_naplate(user=Depends(PermissionService.require("t_ai"))):
        _zapamti()
        await _chat()
        return {"ok": True}

    @app.post("/besplatno")                  # 0 kredita, dnevni limit kao jedini budžet
    async def besplatno(user=Depends(PermissionService.require("t_besplatno"))):
        _zapamti()
        await _chat()
        await UsageService.consume(user["user_id"], user["email"], "t_besplatno")
        return {"ok": True}

    @app.post("/proguta")                    # `except Exception` → 500 (849 takvih mesta u routers/)
    async def proguta(user=Depends(PermissionService.require("t_ai"))):
        try:
            await _chat()
            await UsageService.consume(user["user_id"], user["email"], "t_ai")
        except Exception as e:
            raise HTTPException(500, str(e))
        return {"ok": True}

    @app.post("/model")
    async def model(user=Depends(PermissionService.require("t_ai"))):
        await _chat(model="gpt-4.5-preview")
        return {"ok": True}

    @app.post("/veliki")
    async def veliki(user=Depends(PermissionService.require("t_ai"))):
        await _chat(sadrzaj="x" * 400_000)
        return {"ok": True}

    @app.post("/izlaz")
    async def izlaz(user=Depends(PermissionService.require("t_ai"))):
        await _chat(max_tokens=50_000)
        return {"ok": True}

    @app.post("/rucna")                      # samo autentifikacija, bez PermissionService
    async def rucna(user=Depends(deps.get_current_user)):
        await _chat()
        _zapamti()                           # operacija nastaje pri prvom pozivu (automatska)
        return {"ok": True}

    @app.post("/javna")                      # bez prijave
    async def javna():
        await _chat()
        return {"ok": True}

    @app.post("/drugi_nalog")                # kontekst drugog naloga usred operacije
    async def drugi_nalog(user=Depends(PermissionService.require("t_ai"))):
        from shared.ai_provenance import scoped_request_context
        with scoped_request_context(user_id="zrtva"):
            await _chat()
        return {"ok": True}

    @app.post("/sync")                       # sinhroni klijent u niti
    async def sync(user=Depends(PermissionService.require("t_ai"))):
        _zapamti()

        def _poziv():
            return openai.OpenAI(api_key="sk-test-not-real").chat.completions.create(
                model="gpt-4o-mini", messages=[{"role": "user", "content": "x"}])
        await asyncio.to_thread(_poziv)
        await UsageService.consume(user["user_id"], user["email"], "t_ai")
        return {"ok": True}

    @app.post("/negejtovan")                 # SDK resurs koji nije obavijen wrapperom
    async def negejtovan(user=Depends(PermissionService.require("t_ai"))):
        await _klijent().models.list()
        return {"ok": True}

    @app.post("/pozadina")                   # AI u pozadinskom zadatku posle odgovora
    async def pozadina(user=Depends(PermissionService.require("t_ai"))):
        _zapamti()
        from shared.bg import spawn
        _POSLEDNJA_OP["task"] = spawn(_chat(), name="test:pozadina")
        return {"ok": True}

    @app.post("/api/podnesak")               # ruta pod Idempotency-Key zaštitom (ZASTICENE_RUTE)
    async def podnesak(user=Depends(PermissionService.require("t_ai"))):
        await _chat()
        await UsageService.consume(user["user_id"], user["email"], "t_ai")
        return {"ok": True}

    return app


def _zahtev(app, put, uid, **kw):
    async def _r():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url="http://test") as c:
            return await c.post(put, headers={"Authorization": f"Bearer tok-{uid}", **kw.pop("headers", {})}, **kw)
    return asyncio.run(_r())


def _kod(r):
    d = r.json().get("detail")
    return d.get("code") if isinstance(d, dict) else d


# ═══════════════════════════════════════════════════════════════════════════
# A6 — slučajevi
# ═══════════════════════════════════════════════════════════════════════════

def test_0_kredita_nula_poziva_provajdera(svet):
    svet.baza.krediti["u0"] = 0
    r = _zahtev(_napravi_app(), "/posle", "u0")
    assert r.status_code == 402 and _kod(r) == "NO_CREDITS"
    assert svet.prov.broj == 0
    assert svet.baza.krediti["u0"] == 0


def test_1_preostali_kredit_cena_2_odbijeno_cena_1_prolazi(svet):
    app = _napravi_app()
    svet.baza.krediti["u1"] = 1
    r = _zahtev(app, "/posle", "u1")                 # t_ai = 2 kredita
    assert r.status_code == 402 and svet.prov.broj == 0 and svet.baza.krediti["u1"] == 1
    r = _zahtev(app, "/posle_1", "u1")               # t_ai_1 = 1 kredit
    assert r.status_code == 200 and svet.prov.broj == 1 and svet.baza.krediti["u1"] == 0
    r = _zahtev(app, "/posle_1", "u1")
    assert r.status_code == 402 and svet.prov.broj == 1


def test_20_paralelnih_zahteva_stanje_pokriva_tacno_5(svet):
    app = _napravi_app()
    svet.baza.krediti["u20"] = 10                    # t_ai = 2 → tačno 5 operacija

    async def _sve():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            return await asyncio.gather(*[c.post("/posle", headers={"Authorization": "Bearer tok-u20"})
                                          for _ in range(20)])
    odgovori = asyncio.run(_sve())
    uspeh = sum(r.status_code == 200 for r in odgovori)
    assert uspeh == 5, [r.status_code for r in odgovori]
    assert sum(r.status_code == 402 for r in odgovori) == 15
    assert svet.prov.broj == 5, "svaki poziv provajdera mora biti pokriven rezervacijom"
    assert svet.baza.krediti["u20"] == 0
    assert uspeh * 2 + svet.baza.krediti["u20"] == 10


def test_dupli_zahtev_isti_kljuc_jedna_naplata_jedan_poziv(svet, monkeypatch):
    from shared import idempotency

    class _Mem:
        redovi: dict = {}
        brava = threading.Lock()

        def zauzmi(self, red):
            with self.brava:
                k = (red["user_id"], red["idempotency_key"])
                if k in self.redovi:
                    return False
                self.redovi[k] = dict(red)
                return True

        def procitaj(self, user_id, kljuc):
            return self.redovi.get((user_id, kljuc))

        def zavrsi(self, user_id, kljuc, owner_token, polja):
            with self.brava:
                r = self.redovi.get((user_id, kljuc))
                if not r or r["state"] != "IN_PROGRESS" or r["owner_token"] != owner_token:
                    return False
                r.update(polja)
                return True
    _Mem.redovi = {}
    monkeypatch.setattr(idempotency, "_skladiste_fabrika", _Mem)
    app = _napravi_app()
    app.add_middleware(idempotency.IdempotencyMiddleware)
    svet.baza.krediti["ud"] = 10
    kljuc = str(uuid.uuid4())
    r1 = _zahtev(app, "/api/podnesak", "ud", headers={"Idempotency-Key": kljuc})
    r2 = _zahtev(app, "/api/podnesak", "ud", headers={"Idempotency-Key": kljuc})
    assert r1.status_code == 200 and r2.status_code == 200
    assert svet.prov.broj == 1, "ponovljen zahtev sa istim ključem ne sme ponovo da pozove provajdera"
    assert svet.baza.krediti["ud"] == 8, "ponovljen zahtev sa istim ključem ne sme ponovo da naplati"


@pytest.mark.parametrize("kvar,ocekivan", [
    ("increment_feature_usage", 503),   # dnevni brojač je budžet — pad baze NE pušta (bio fail-open)
    ("user_credits", 503),              # stanje se ne može pročitati
    ("deduct_n_credits", 402),          # odbitak pukao → „nije naplaćeno" → odbijeno
])
def test_pad_baze_pri_rezervaciji_blokira(svet, kvar, ocekivan):
    svet.baza.krediti["ub"] = 10
    svet.baza.kvar[kvar] = "raise"
    r = _zahtev(_napravi_app(), "/posle", "ub")
    assert r.status_code == ocekivan, r.text
    assert svet.prov.broj == 0
    assert svet.baza.krediti["ub"] == 10


def test_pad_dnevnog_brojaca_blokira_i_besplatnu_funkciju(svet):
    """Za funkcije sa 0 kredita je dnevni brojač JEDINI budžet: pre ispravke je pad
    `increment_feature_usage` značio „propusti" (shared/usage.py, fail-open)."""
    svet.baza.krediti["uf"] = 0
    svet.baza.kvar["increment_feature_usage"] = "raise"
    r = _zahtev(_napravi_app(), "/besplatno", "uf")
    assert r.status_code == 503 and svet.prov.broj == 0


def test_dnevni_limit_besplatne_funkcije_je_rezervacija(svet):
    app = _napravi_app()
    svet.baza.krediti["ul"] = 0
    assert _zahtev(app, "/besplatno", "ul").status_code == 200
    assert _zahtev(app, "/besplatno", "ul").status_code == 200
    r = _zahtev(app, "/besplatno", "ul")             # dnevni_limit = 2
    assert r.status_code == 429 and _kod(r) == "DAILY_LIMIT"
    assert svet.prov.broj == 2
    dan = list(svet.baza.upotreba)[0]
    assert svet.baza.upotreba[dan]["broj_koriscenja"] == 2, "jedna upotreba po operaciji, bez duplog brojanja"


def test_izgubljen_odgovor_baze_ne_daje_besplatan_poziv(svet, zapis):
    """Odbitak je IZVRŠEN, odgovor nije stigao: poziv se ne izvršava (nema besplatnog
    rada), naplata se ne vraća tiho — beleži se za ručno usklađivanje."""
    svet.baza.krediti["ux"] = 10
    svet.baza.kvar["deduct_n_credits"] = "izgubljen_odgovor"
    r = _zahtev(_napravi_app(), "/posle", "ux")
    assert r.status_code == 402 and svet.prov.broj == 0
    assert svet.baza.krediti["ux"] == 8, "transakcija je izvršena u bazi; nije tiho vraćena"
    assert "CREDIT_RECONCILE" in zapis.text
    svet.baza.kvar.clear()
    r = _zahtev(_napravi_app(), "/posle", "ux")      # ponovni pokušaj = nova, plaćena operacija
    assert r.status_code == 200 and svet.prov.broj == 1 and svet.baza.krediti["ux"] == 6


def test_timeout_provajdera_svi_pokusaji_se_broje_rezervacija_se_zadrzava(svet, zapis):
    svet.baza.krediti["ut"] = 10
    svet.prov.rezim = "timeout"
    r = _zahtev(_napravi_app(), "/posle", "ut")
    assert r.status_code == 500
    op = _POSLEDNJA_OP["op"]
    assert svet.prov.broj == 3, "SDK: 1 + max_retries=2 — svaki HTTP pokušaj je izašao ka provajderu"
    assert op.pokusaja == 3, "brana broji i SDK-ove interne retry-je"
    assert op.nepoznatih == 1
    assert svet.baza.krediti["ut"] == 8, "nepoznat ishod se ne vraća tiho"
    assert "AI_BUDZET_RECONCILE" in zapis.text


def test_definitivna_greska_provajdera_rezervacija_se_vraca(svet):
    svet.baza.krediti["u5"] = 10
    svet.prov.rezim = "500"
    r = _zahtev(_napravi_app(), "/posle", "u5")
    assert r.status_code == 500
    assert svet.prov.broj == 3 and _POSLEDNJA_OP["op"].definitivnih_gresaka == 1
    assert svet.baza.krediti["u5"] == 10, "provajder je odbio zahtev — korisniku se ne naplaćuje neisporučen rad"


def test_neuspeo_povracaj_ne_pravi_kredite_i_beleži_se(svet, zapis):
    svet.baza.krediti["ur"] = 10
    svet.baza.kvar["refund_n_credits"] = "raise"
    r = _zahtev(_napravi_app(), "/bez_naplate", "ur")
    assert r.status_code == 200 and svet.prov.broj == 1
    assert svet.baza.krediti["ur"] == 8, "neuspeo povraćaj: korisnik ostaje zadužen, ništa nije izmišljeno"
    assert "AI_BUDZET_RECONCILE" in zapis.text


def test_ruta_bez_naplate_vraca_rezervaciju_kao_pre(svet):
    """Ruta koja AI ne naplaćuje ostaje besplatna (ponašanje pre brane), ali TRAŽI
    stanje za rezervaciju: nalog sa 0 kredita više ne pokreće plaćen AI."""
    app = _napravi_app()
    svet.baza.krediti["ub2"] = 10
    assert _zahtev(app, "/bez_naplate", "ub2").status_code == 200
    assert svet.baza.krediti["ub2"] == 10 and svet.prov.broj == 1
    svet.baza.krediti["ub3"] = 0
    assert _zahtev(app, "/bez_naplate", "ub3").status_code == 402 and svet.prov.broj == 1


def test_promena_modela_odbijena_pre_rezervacije(svet):
    svet.baza.krediti["um"] = 10
    r = _zahtev(_napravi_app(), "/model", "um")
    assert r.status_code == 403 and _kod(r) == "MODEL_NIJE_DOZVOLJEN"
    assert svet.prov.broj == 0 and svet.baza.krediti["um"] == 10


def test_prevelik_kontekst_i_izlaz_odbijeni(svet):
    app = _napravi_app()
    svet.baza.krediti["uv"] = 10
    r = _zahtev(app, "/veliki", "uv")
    assert r.status_code == 413 and _kod(r) == "ULAZ_PREVELIK"
    r = _zahtev(app, "/izlaz", "uv")
    assert r.status_code == 413 and _kod(r) == "IZLAZ_PREVELIK"
    assert svet.prov.broj == 0 and svet.baza.krediti["uv"] == 10


def test_izlaz_bez_granice_dobija_podrazumevanu(svet):
    svet.baza.krediti["ui"] = 10
    _zahtev(_napravi_app(), "/posle", "ui")
    assert svet.prov.zahtevi[0]["telo"]["max_tokens"] == ai_budget.max_izlaz()


def test_ugnezdeni_podpozivi_jedna_rezervacija_jedna_naplata(svet):
    svet.baza.krediti["un"] = 10
    r = _zahtev(_napravi_app(), "/ugnezdeno", "un")
    assert r.status_code == 200
    assert svet.prov.broj == 3 and _POSLEDNJA_OP["op"].pokusaja == 3
    assert svet.baza.krediti["un"] == 8, "tri paralelna podpoziva = jedna operacija = jedna cena"
    assert svet.baza.rpc_pozivi.count("deduct_n_credits") == 1
    assert svet.baza.rpc_pozivi.count("increment_feature_usage") == 1


def test_granica_pokusaja_po_operaciji(svet, monkeypatch):
    monkeypatch.setenv("VINDEX_AI_MAX_POKUSAJA_OPERACIJE", "2")
    svet.baza.krediti["ug"] = 10
    r = _zahtev(_napravi_app(), "/ugnezdeno", "ug")
    assert r.status_code == 429 and _kod(r) == "OPERACIJA_PREVELIKA"
    assert svet.prov.broj == 2


def test_namirenje_multiplikatora_je_razlika_ne_druga_naplata(svet):
    svet.baza.krediti["u3"] = 10
    r = _zahtev(_napravi_app(), "/x3", "u3")
    assert r.status_code == 200 and svet.prov.broj == 1
    assert svet.baza.krediti["u3"] == 7, "rezervacija 1 + razlika 2 = cena 3 (krediti × multiplikator)"
    assert len(svet.baza.log) == 1 and svet.baza.log[0]["krediti_potroseni"] == 3
    assert svet.baza.log[0]["tokens_prompt"] == 100 and svet.baza.log[0]["tokens_completion"] == 20


def test_pre_deduct_ruta_jedna_naplata(svet):
    svet.baza.krediti["up"] = 10
    r = _zahtev(_napravi_app(), "/pre", "up")
    assert r.status_code == 200 and svet.prov.broj == 1
    assert svet.baza.krediti["up"] == 8
    assert svet.baza.rpc_pozivi.count("deduct_n_credits") == 1


def test_sinhroni_klijent_u_niti_takodje_rezervise(svet):
    svet.baza.krediti["us"] = 0
    assert _zahtev(_napravi_app(), "/sync", "us").status_code == 402
    assert svet.prov.broj == 0
    svet.baza.krediti["us"] = 2
    assert _zahtev(_napravi_app(), "/sync", "us").status_code == 200
    assert svet.prov.broj == 1 and svet.baza.krediti["us"] == 0


def test_progutano_odbijanje_vraca_stvarni_razlog(svet):
    svet.baza.krediti["uq"] = 0
    r = _zahtev(_napravi_app(), "/proguta", "uq")
    assert svet.prov.broj == 0
    assert r.status_code == 402 and _kod(r) == "NO_CREDITS"


def test_rucna_autentifikacija_ide_na_osnovnu_funkciju(svet):
    svet.baza.krediti["ua"] = 0
    r = _zahtev(_napravi_app(), "/rucna", "ua")
    assert r.status_code == 200 and svet.prov.broj == 1
    assert _POSLEDNJA_OP["op"].feature == ai_budget.OSNOVNA_FUNKCIJA
    assert any(k[1] == ai_budget.OSNOVNA_FUNKCIJA for k in svet.baza.upotreba)


def test_osnovna_funkcija_bez_reda_u_registru_odbija(svet, monkeypatch):
    """Migracija 146 nije pokrenuta → nema cene → fail-closed, ne „propusti"."""
    feature_registry._CACHE.pop(ai_budget.OSNOVNA_FUNKCIJA)
    r = _zahtev(_napravi_app(), "/rucna", "ua2")
    assert r.status_code == 503 and svet.prov.broj == 0


def test_javna_ruta_bez_prijave_ne_trosi(svet):
    r = _zahtev(_napravi_app(), "/javna", "niko")
    assert r.status_code == 401 and _kod(r) == "NEVEZAN_HTTP_POZIV"
    assert svet.prov.broj == 0


def test_negejtovan_sdk_resurs_odbijen(svet):
    svet.baza.krediti["uz"] = 10
    r = _zahtev(_napravi_app(), "/negejtovan", "uz")
    assert r.status_code == 503 and _kod(r) == "NEGEJTOVAN_POZIV"
    assert svet.prov.broj == 0


def test_tudji_kontekst_u_operaciji_odbijen(svet):
    svet.baza.krediti["ua3"] = 10
    svet.baza.krediti["zrtva"] = 10
    r = _zahtev(_napravi_app(), "/drugi_nalog", "ua3")
    assert r.status_code == 403 and _kod(r) == "IDENTITET_SE_NE_POKLAPA"
    assert svet.prov.broj == 0
    assert svet.baza.krediti["zrtva"] == 10 and svet.baza.krediti["ua3"] == 10


def test_tudji_token_ne_moze_da_trosi_tudj_budzet(svet):
    """Rezervacija je uvek na nalog iz verifikovanog tokena — nema parametra kojim bi
    zahtev imenovao čiji se budžet troši."""
    app = _napravi_app()
    svet.baza.krediti["napadac"] = 0
    svet.baza.krediti["zrtva2"] = 10
    r = _zahtev(app, "/posle", "napadac", json={"user_id": "zrtva2"})
    assert r.status_code == 402 and svet.prov.broj == 0
    assert svet.baza.krediti["zrtva2"] == 10


def test_projektni_limit_vazi_i_za_foundera(svet, monkeypatch):
    monkeypatch.setenv("VINDEX_AI_PROJEKAT_MESECNI_USD", "0.000001")
    svet.baza.krediti["uk"] = 10
    assert _zahtev(_napravi_app(), "/posle", "uk").status_code == 503
    r = _zahtev(_napravi_app(), "/posle", "founder")
    assert r.status_code == 503 and _kod(r) == "PROJEKTNI_LIMIT"
    assert svet.prov.broj == 0 and svet.baza.krediti["uk"] == 10


def test_projektni_limit_se_puni_stvarnom_potrosnjom(svet, monkeypatch):
    svet.baza.krediti["ue"] = 100
    _zahtev(_napravi_app(), "/posle", "ue")
    stvarno = 100 / 1000 * 0.00015 + 20 / 1000 * 0.0006          # gpt-4o-mini, usage iz odgovora
    assert abs(ai_budget.projektna_potrosnja() - stvarno) < 1e-9
    monkeypatch.setenv("VINDEX_AI_PROJEKAT_MESECNI_USD", str(stvarno))
    assert _zahtev(_napravi_app(), "/posle", "ue").status_code == 503
    assert svet.prov.broj == 1


def test_founder_ne_placa_ali_ostaje_u_granicama(svet):
    app = _napravi_app()
    r = _zahtev(app, "/posle", "founder")
    assert r.status_code == 200 and svet.prov.broj == 1
    assert "founder" not in svet.baza.krediti and "deduct_n_credits" not in svet.baza.rpc_pozivi
    assert _zahtev(app, "/model", "founder").status_code == 403
    assert _zahtev(app, "/veliki", "founder").status_code == 413
    assert svet.prov.broj == 1


def test_pozadinski_zadatak_ostaje_u_operaciji(svet):
    svet.baza.krediti["uz2"] = 10
    app = _napravi_app()

    async def _tok():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/pozadina", headers={"Authorization": "Bearer tok-uz2"})
            await _POSLEDNJA_OP["task"]
            return r
    r = asyncio.run(_tok())
    assert r.status_code == 200 and svet.prov.broj == 1
    op = _POSLEDNJA_OP["op"]
    assert op.pokusaja == 1, "poziv posle odgovora je brojan u operaciju zahteva"
    assert svet.baza.krediti["uz2"] == 8, "pozadinski AI posle zatvaranja operacije rezerviše — nije besplatan"


def test_pozadinski_posao_bez_budzeta_ne_poziva(svet):
    """Smart Intake radnik / event bus: `operacija(vlasnik)`; iscrpljen dnevni limit
    osnovne funkcije → nijedan poziv."""
    feature_registry._CACHE[ai_budget.OSNOVNA_FUNKCIJA]["dnevni_limit"] = 1

    async def _posao():
        with ai_budget.operacija("radnik-u", izvor="test"):
            await _chat()

    asyncio.run(_posao())
    assert svet.prov.broj == 1
    with pytest.raises(AIBudzetOdbijen) as e:
        asyncio.run(_posao())
    assert e.value.status == 429 and svet.prov.broj == 1


def test_sistemska_operacija_bez_korisnika_ide_u_projekat(svet, monkeypatch):
    async def _cron():
        with ai_budget.operacija(None, sistemska=True, izvor="test:cron"):
            await _chat()
    asyncio.run(_cron())
    assert svet.prov.broj == 1 and ai_budget.projektna_potrosnja() > 0
    monkeypatch.setenv("VINDEX_AI_PROJEKAT_MESECNI_USD", "0.000001")
    with pytest.raises(AIBudzetOdbijen):
        asyncio.run(_cron())
    assert svet.prov.broj == 1


def test_ponovljena_registracija_i_oporavak_profila_ne_vracaju_kredite(svet):
    """A5: postojeći red sa 0 kredita ostaje 0 posle čitanja profila (auto-heal upisuje
    početnih 15 SAMO kad red ne postoji). Nijedna putanja u aplikaciji ne briše
    `user_credits` (grep, v. izveštaj) — novi red dobija samo NOV nalog."""
    svet.baza.krediti["ur0"] = 0
    assert deps._ensure_profile("ur0")["credits_remaining"] == 0
    assert deps._ensure_profile("ur0")["credits_remaining"] == 0
    assert svet.baza.krediti["ur0"] == 0
    assert deps._ensure_profile("nov")["credits_remaining"] == deps.BESPLATNI_KREDITI


# ═══════════════════════════════════════════════════════════════════════════
# Ožičenje u PRODUKCIONOJ aplikaciji
# ═══════════════════════════════════════════════════════════════════════════

def test_produkciona_ruta_0_kredita_nula_poziva(svet):
    """`POST /api/style/profil/gradi` (api.app) — AI pa consume, `except Exception` → 500.
    Pre brane: provajder pozvan, pa 402/500. Sada: 0 poziva i stvarni razlog."""
    svet.baza.krediti["prod0"] = 0
    r = _zahtev(api.app, "/api/style/profil/gradi", "prod0", json={"uzorci": ["Tekst uzorka."]})
    assert svet.prov.broj == 0
    assert r.status_code == 402 and _kod(r) == "NO_CREDITS"


def test_produkciona_ruta_sa_kreditom_jedna_naplata(svet, monkeypatch):
    import routers.style_checker as sc
    monkeypatch.setattr(sc, "_get_supa", lambda: FakeSupa(svet.baza))
    svet.baza.krediti["prod1"] = 5
    r = _zahtev(api.app, "/api/style/profil/gradi", "prod1", json={"uzorci": ["Tekst uzorka."]})
    assert svet.prov.broj == 1
    assert r.status_code == 200, r.text
    assert svet.baza.krediti["prod1"] == 4


def test_brojac_pokusaja_je_instaliran_na_sdk_klasama():
    """Ugovor: pre svakog poziva brana garantuje brojač na obe SDK klase (drugi testovi
    u sviti ga smeju skinuti — v. test_brojac_se_obnavlja_ako_ga_je_neko_skinuo)."""
    from openai._base_client import AsyncAPIClient, SyncAPIClient
    ai_budget._osiguraj_brojac()
    assert getattr(SyncAPIClient._build_request, "_vindex_guarded", False)
    assert getattr(AsyncAPIClient._build_request, "_vindex_guarded", False)


def test_rezim_off_je_jedini_izlaz_i_ne_dira_naplatu(svet, monkeypatch):
    """Hitno vraćanje (`VINDEX_AI_BUDZET=off`) vraća TAČNO staro ponašanje — i stari
    propust: nalog sa 0 kredita ponovo izvršava AI. Zato je to odluka, ne podrazumevano."""
    monkeypatch.setenv("VINDEX_AI_BUDZET", "off")
    svet.baza.krediti["uo"] = 0
    r = _zahtev(_napravi_app(), "/posle", "uo")
    assert r.status_code == 402 and svet.prov.broj == 1


def test_brojac_se_obnavlja_ako_ga_je_neko_skinuo(svet):
    """Izmereno u CI-ju (nasumičan redosled): `_uninstall_prompt_guard()` + vraćen sačuvan
    wrapper ostavljali su chat granicu bez brojača pokušaja. Brana ga sada vraća pre
    poziva — SDK retry-ji ostaju brojani."""
    from openai._base_client import AsyncAPIClient, SyncAPIClient

    from shared import ai_client
    for klasa, orig in list(ai_client._orig_build_request.items()):
        klasa._build_request = orig                      # simulacija spoljnog skidanja
    assert not getattr(AsyncAPIClient._build_request, "_vindex_guarded", False)
    svet.baza.krediti["uh"] = 10
    svet.prov.rezim = "timeout"
    _zahtev(_napravi_app(), "/posle", "uh")
    assert getattr(SyncAPIClient._build_request, "_vindex_guarded", False)
    assert getattr(AsyncAPIClient._build_request, "_vindex_guarded", False)
    assert _POSLEDNJA_OP["op"].pokusaja == 3 == svet.prov.broj


# ═══════════════════════════════════════════════════════════════════════════
# Release gate dodatak (2026-11-02): multiplikator poznat PRE poziva provajdera
# ═══════════════════════════════════════════════════════════════════════════
# Ugovor osnivača: ako je puna cena operacije (krediti × credit_multiplier) poznata pre
# poziva provajdera, nalog koji nema punu cenu NE SME da pokrene plaćen poziv.
# `/x3` = registar krediti 1 × credit_multiplier 3, ruta naplaćuje podrazumevani
# multiplikator iz registra (isti obrazac kao `routers/strategija.py` kompletna analiza: 1 × 6).

# P0 ispravka (2026-11-02): rezervacija uzima PUNU cenu pre prvog poziva; ovi testovi su bili
# xfail(strict) reproduktori kvara i sada moraju da prođu bez ikakve oznake.

@pytest.mark.parametrize("stanje", [1, 2])
def test_multiplikator_nedovoljno_za_punu_cenu_nula_poziva(svet, stanje):
    uid = f"um{stanje}"
    svet.baza.krediti[uid] = stanje
    r = _zahtev(_napravi_app(), "/x3", uid)
    print(f"\n[MULTIPLIKATOR] stanje={stanje} cena=3 -> HTTP {r.status_code} kod={_kod(r)} "
          f"pozivi_provajdera={svet.prov.broj} stanje_posle={svet.baza.krediti[uid]}")
    assert r.status_code == 402 and _kod(r) == "NO_CREDITS"
    assert svet.prov.broj == 0, "plaćen poziv provajdera bez pune cene"
    assert svet.baza.krediti[uid] == stanje


def test_multiplikator_dva_paralelna_stanje_za_jednu_punu_cenu(svet):
    """Stanje 3 = jedna puna cena. Dva istovremena zahteva: tačno jedan sme da stigne do provajdera."""
    svet.baza.krediti["umx"] = 3
    app = _napravi_app()

    async def _oba():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url="http://test") as c:
            return await asyncio.gather(*[c.post("/x3", headers={"Authorization": "Bearer tok-umx"}) for _ in range(2)])
    odg = asyncio.run(_oba())
    kodovi = sorted(o.status_code for o in odg)
    print(f"\n[MULTIPLIKATOR] paralelno stanje=3 cena=3 -> {kodovi} pozivi_provajdera={svet.prov.broj} "
          f"stanje_posle={svet.baza.krediti['umx']}")
    assert kodovi == [200, 402]
    assert svet.prov.broj == 1, "neplaćen poziv provajdera"
    assert svet.baza.krediti["umx"] == 0


def test_multiplikator_tacno_puna_cena_jedna_operacija(svet):
    svet.baza.krediti["umt"] = 3
    r = _zahtev(_napravi_app(), "/x3", "umt")
    assert r.status_code == 200 and svet.prov.broj == 1
    assert svet.baza.krediti["umt"] == 0
    assert [e["krediti_potroseni"] for e in svet.baza.log] == [3], "jedan događaj upotrebe, puna cena"
    assert sum(v["broj_koriscenja"] for v in svet.baza.upotreba.values()) == 1


def test_multiplikator_puna_cena_se_rezervise_pre_poziva(svet):
    """U trenutku prvog HTTP pokušaja ka provajderu rezervacija već drži punu cenu."""
    svet.baza.krediti["ump"] = 5
    stanja = []
    orig = svet.prov.odgovor

    def _belezi(request):
        stanja.append(svet.baza.krediti["ump"])
        return orig(request)
    svet.prov.odgovor = _belezi
    r = _zahtev(_napravi_app(), "/x3", "ump")
    assert r.status_code == 200 and stanja == [2], stanja
    assert svet.baza.krediti["ump"] == 2


def test_jedan_modul_multiplier_1_ostaje_bazna_cena(svet):
    """Funkcija ×3 u registru, ruta naplaćuje jedan modul: rezerviše se i naplaćuje 1, ne 3."""
    svet.baza.krediti["um1"] = 1
    r = _zahtev(_napravi_app(), "/x3_modul", "um1")
    assert r.status_code == 200 and svet.prov.broj == 1
    assert svet.baza.krediti["um1"] == 0
    assert [e["krediti_potroseni"] for e in svet.baza.log] == [1]


def test_neizjavljen_multiplier_1_vraca_visak_bez_stvaranja_kredita(svet):
    """Ruta koja ne izjavi multiplikator rezerviše registarsku cenu (konzervativno): sa stanjem 3
    naplata je 1, višak 2 se vraća na kraju operacije — nikad više nego što je oduzeto."""
    svet.baza.krediti["umn"] = 3
    r = _zahtev(_napravi_app(), "/x3_neizjavljen", "umn")
    assert r.status_code == 200 and svet.prov.broj == 1
    assert svet.baza.krediti["umn"] == 2
    assert svet.baza.rpc_pozivi.count("refund_n_credits") == 1, "višak se vraća jednom, na kraju operacije"


def test_kasna_izjava_ne_menja_rezervaciju(svet, zapis):
    svet.baza.krediti["umk"] = 3
    r = _zahtev(_napravi_app(), "/kasna_izjava", "umk")
    assert r.status_code == 200 and svet.baza.krediti["umk"] == 0
    assert "izjavljen POSLE rezervacije" in zapis.text


@pytest.mark.parametrize("uspelo,ocekivano_stanje", [(3, 2), (2, 3), (1, 4), (0, 5)])
def test_dinamicki_delimican_uspeh_naplacuje_samo_isporuceno(svet, uspelo, ocekivano_stanje):
    """Gornja granica 3 rezervisana pre poziva; naplata = isporučeno; ostatak vraćen."""
    uid = f"umd{uspelo}"
    svet.baza.krediti[uid] = 5
    r = _zahtev(_napravi_app(), f"/savetnici?uspelo={uspelo}", uid)
    assert r.status_code == 200 and svet.prov.broj == 3
    assert svet.baza.krediti[uid] == ocekivano_stanje
    assert [e["krediti_potroseni"] for e in svet.baza.log] == ([uspelo] if uspelo else [])


def test_dinamicki_bez_gornje_granice_nula_poziva(svet):
    svet.baza.krediti["umg"] = 2
    r = _zahtev(_napravi_app(), "/savetnici?uspelo=2", "umg")
    assert r.status_code == 402 and svet.prov.broj == 0 and svet.baza.krediti["umg"] == 2


@pytest.mark.parametrize("koraka", [1, 2, 3])
def test_niz_koraka_trosi_istu_rezervaciju_bez_duple_naplate(svet, koraka):
    uid = f"umz{koraka}"
    svet.baza.krediti[uid] = 3
    r = _zahtev(_napravi_app(), f"/niz?koraka={koraka}", uid)
    assert r.status_code == 200 and svet.prov.broj == koraka
    assert svet.baza.krediti[uid] == 3 - koraka
    assert [e["krediti_potroseni"] for e in svet.baza.log] == [1] * koraka
    assert sum(v["broj_koriscenja"] for v in svet.baza.upotreba.values()) == koraka, "jedna upotreba po koraku, kao ranije"


def test_nepoznat_ishod_zadrzava_samo_osnovnu_cenu(svet, zapis):
    """Ugovor pre ispravke: nepoznat ishod bez namirenja zadržava osnovnu cenu (krediti × 1).
    Rezervacija pune cene ne sme da ga pooštri: od 3 rezervisana zadržava se 1, vraća se 2."""
    svet.baza.krediti["umu"] = 5
    svet.prov.rezim = "timeout"
    r = _zahtev(_napravi_app(), "/x3", "umu")
    assert r.status_code >= 500
    assert svet.prov.broj == 3, "SDK retry-ji se broje"
    assert svet.baza.krediti["umu"] == 4
    assert "1 kredita ZADRŽANO" in zapis.text


def test_definitivna_greska_vraca_punu_rezervaciju(svet):
    svet.baza.krediti["ume"] = 5
    svet.prov.rezim = "500"
    r = _zahtev(_napravi_app(), "/x3", "ume")
    assert r.status_code >= 500 and svet.baza.krediti["ume"] == 5


# ═══════════════════════════════════════════════════════════════════════════
# PR #66 final gate (2026-11-04): adversarijalne praznine koje gornji testovi ne pokrivaju
# ═══════════════════════════════════════════════════════════════════════════

def _vrati_brojac():
    from shared import ai_client
    ai_client._instaliraj_brojac_pokusaja()
    ai_budget._osiguraj_brojac()


def test_gate_hook_ne_moze_da_se_postavi_odbija_pre_slanja(svet, monkeypatch):
    """SDK hook je skinut i ne može da se vrati → 503 BROJAC_NEDOSTUPAN, 0 slanja, 0 naplate."""
    from shared import ai_client
    try:
        for klasa, orig in list(ai_client._orig_build_request.items()):
            klasa._build_request = orig
        monkeypatch.setattr(ai_client, "_instaliraj_brojac_pokusaja", lambda: None)
        svet.baza.krediti["gh"] = 10
        r = _zahtev(_napravi_app(), "/posle", "gh")
        assert r.status_code == 503 and _kod(r) == "BROJAC_NEDOSTUPAN", r.text
        assert svet.prov.broj == 0 and svet.baza.krediti["gh"] == 10
    finally:
        monkeypatch.undo()
        _vrati_brojac()


def test_gate_dvostruka_instalacija_broji_jednom_po_slanju(svet):
    """Hook/wrapper postavljen više puta ne sme da broji jedno HTTP slanje dvaput."""
    from shared import ai_client
    for _ in range(3):
        ai_client._instaliraj_brojac_pokusaja()
    svet.baza.krediti["gd"] = 10
    r = _zahtev(_napravi_app(), "/posle", "gd")
    assert r.status_code == 200 and svet.prov.broj == 1 == _POSLEDNJA_OP["op"].pokusaja
    assert svet.baza.krediti["gd"] == 8
    svet.prov.rezim = "timeout"
    _zahtev(_napravi_app(), "/posle", "gd")
    assert svet.prov.broj - 1 == 3 == _POSLEDNJA_OP["op"].pokusaja


def test_gate_greska_transporta_posle_mogucog_slanja_je_nepoznat_ishod(svet, monkeypatch):
    """Prekid veze posle slanja (RemoteProtocolError): svaki pokušaj se broji, osnovna cena
    se zadržava (nepoznat ishod), ništa preko nje se ne naplaćuje."""
    orig = svet.prov.odgovor

    def _prekid(request):
        orig(request)
        raise httpx.RemoteProtocolError("veza prekinuta posle slanja", request=request)
    monkeypatch.setattr(svet.prov, "odgovor", _prekid)
    svet.baza.krediti["gp"] = 10
    r = _zahtev(_napravi_app(), "/posle", "gp")
    assert r.status_code == 500
    op = _POSLEDNJA_OP["op"]
    assert svet.prov.broj == 3 == op.pokusaja and op.nepoznatih == 1
    assert svet.baza.krediti["gp"] == 8


def test_gate_pad_aplikacije_posle_uspesnog_odgovora(svet):
    """Provajder je odgovorio, ruta pada pre `consume()`: jedno slanje, korisnik nije zadužen
    (ugovor: nenamirena rezervacija se vraća), trošak ostaje u projektnom limitu."""
    app = _napravi_app()

    @app.post("/pad_posle")
    async def pad_posle(user=Depends(PermissionService.require("t_ai"))):
        _POSLEDNJA_OP["op"] = ai_budget.tekuca_operacija()
        await _chat()
        raise RuntimeError("greška aplikacije posle odgovora provajdera")

    svet.baza.krediti["ga"] = 10
    r = _zahtev(app, "/pad_posle", "ga")
    assert r.status_code == 500
    assert svet.prov.broj == 1 and _POSLEDNJA_OP["op"].uspesnih == 1
    assert svet.baza.krediti["ga"] == 10
    assert ai_budget.projektna_potrosnja() > 0


def test_gate_dva_naloga_istovremeno_budzeti_izolovani(svet):
    """20 + 20 istovremenih zahteva dva naloga: A (10 kredita, cena 2) najviše 5, B (0) nijedan."""
    app = _napravi_app()
    svet.baza.krediti["na"] = 10
    svet.baza.krediti["nb"] = 0

    async def _sve():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            zahtevi = []
            for _ in range(20):
                zahtevi.append(c.post("/posle", headers={"Authorization": "Bearer tok-na"}))
                zahtevi.append(c.post("/posle", headers={"Authorization": "Bearer tok-nb"}))
            return await asyncio.gather(*zahtevi)
    odgovori = asyncio.run(_sve())
    a, b = odgovori[0::2], odgovori[1::2]
    assert sum(r.status_code == 200 for r in a) == 5 and sum(r.status_code == 200 for r in b) == 0
    assert all(r.status_code == 402 for r in b)
    assert svet.prov.broj == 5
    assert svet.baza.krediti["na"] == 0 and svet.baza.krediti["nb"] == 0


def test_gate_sinhroni_i_asinhroni_klijent_u_istoj_operaciji_jedna_rezervacija(svet):
    """Async poziv + sinhroni klijent u `asyncio.to_thread` u istom zahtevu: kontekst se
    prenosi, jedna rezervacija, jedna naplata, oba slanja brojana u istu operaciju."""
    app = _napravi_app()

    @app.post("/mesano")
    async def mesano(user=Depends(PermissionService.require("t_ai"))):
        _POSLEDNJA_OP["op"] = ai_budget.tekuca_operacija()
        await _chat()

        def _poziv():
            return openai.OpenAI(api_key="sk-test-not-real").chat.completions.create(
                model="gpt-4o-mini", messages=[{"role": "user", "content": "x"}])
        await asyncio.to_thread(_poziv)
        await UsageService.consume(user["user_id"], user["email"], "t_ai")
        return {"ok": True}

    svet.baza.krediti["gm"] = 10
    r = _zahtev(app, "/mesano", "gm")
    assert r.status_code == 200, r.text
    assert svet.prov.broj == 2 == _POSLEDNJA_OP["op"].pokusaja
    assert svet.baza.krediti["gm"] == 8


def test_gate_unutrasnji_sloj_odbija_pre_slanja_nije_nepoznat_ishod(svet):
    """Hook ispod brane (npr. sesijska autorizacija koja se instalira PRE brane) odbija zahtev
    pre slanja: nijedan bajt nije otišao provajderu → to nije pokušaj ni nepoznat ishod;
    rezervacija se vraća u celosti (izmereno na main + PR #66 + PR #68, redosled Word → brana)."""
    from openai._base_client import AsyncAPIClient, SyncAPIClient

    from shared import ai_client
    sacuvano = {k: k.__dict__.get("_build_request") for k in (SyncAPIClient, AsyncAPIClient)}
    try:
        for k in (SyncAPIClient, AsyncAPIClient):
            if "_build_request" in k.__dict__:
                delattr(k, "_build_request")
            prvobitni = k._build_request

            def _unutrasnji(self, options, *, retries_taken=0, _p=prvobitni):
                raise RuntimeError("unutrašnji sloj odbio zahtev pre slanja")
            k._build_request = _unutrasnji
        ai_client._orig_build_request.clear()
        ai_client._instaliraj_brojac_pokusaja()          # brana SPOLJA, unutrašnji sloj ispod nje
        svet.baza.krediti["gi"] = 10
        r = _zahtev(_napravi_app(), "/posle", "gi")
        op = _POSLEDNJA_OP["op"]
        assert r.status_code == 500 and svet.prov.broj == 0
        assert op.pokusaja == 0 and op.nepoznatih == 0, (op.pokusaja, op.nepoznatih)
        assert svet.baza.krediti["gi"] == 10
    finally:
        for k, m in sacuvano.items():
            if m is None:
                if "_build_request" in k.__dict__:
                    delattr(k, "_build_request")
            else:
                k._build_request = m
        ai_client._orig_build_request.clear()
        _vrati_brojac()
