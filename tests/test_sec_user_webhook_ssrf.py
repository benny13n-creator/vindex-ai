# -*- coding: utf-8 -*-
"""SEC 2026-10-26 — routers/integracije.py (tabela user_webhooks) nije imao NIGHT-009 zaštitu.

PROBLEM (dokazano izvorom na main c4a698ae): POST /api/webhooks je čuvao bilo koji URL, a
POST /api/webhooks/test/{id} je sa servera slao POST na njega (urllib, prati preusmeravanja) i uvek vraćao
success: True → slepi SSRF ka unutrašnjim adresama za svakog prijavljenog korisnika.
ISPRAVKA: isti validator kao routers/integrations.py pri upisu i pri svakom slanju; bez praćenja preusmeravanja;
test vraća stvaran ishod. NIJEDAN test ne izlazi na mrežu (getaddrinfo i opener su zamenjeni)."""
import socket
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

UID = "u-wh"


class _Upit:
    def __init__(self, b, t):
        self.b, self.t, self.f, self.jedan, self.red = b, t, [], False, None

    def select(self, *a, **k): return self
    def order(self, *a, **k): return self

    def eq(self, k, v):
        self.f.append((k, v))
        return self

    def maybe_single(self):
        self.jedan = True
        return self

    def insert(self, red):
        self.red = red
        return self

    def execute(self):
        if self.red is not None:
            red = {"id": f"wh-{len(self.b.redovi) + 1}", "aktivan": True, **self.red}
            self.b.redovi.append(red)
            return types.SimpleNamespace(data=[red], count=None)
        redovi = [r for r in self.b.redovi if all(r.get(k) == v for k, v in self.f)]
        if self.jedan:
            return None if not redovi else types.SimpleNamespace(data=redovi[0])
        return types.SimpleNamespace(data=redovi, count=len(redovi))


class _Baza:
    def __init__(self):
        self.redovi = []

    def table(self, t):
        return _Upit(self, t)


ADRESE = {"javni.example": "93.184.216.34", "interni.example": "10.0.0.7", "metadata.example": "169.254.169.254"}


@pytest.fixture
def k(monkeypatch):
    import routers.integracije as ig
    from shared.deps import get_current_user
    from shared.rate import limiter
    baza, poslato = _Baza(), []
    monkeypatch.setattr(ig, "_get_supa", lambda: baza)
    monkeypatch.setattr(limiter, "enabled", False)

    def _gai(host, port, *a, **kw):
        if host in ADRESE:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ADRESE[host], port))]
        try:
            import ipaddress
            ipaddress.ip_address(host)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, port))]
        except ValueError:
            raise OSError("nije razrešeno")
    monkeypatch.setattr(socket, "getaddrinfo", _gai)

    def _slanje(url, payload, secret):
        poslato.append(url)
        return k.ishod
    monkeypatch.setattr(ig, "_slanje_webhook_sync", _slanje)
    app = FastAPI()
    app.include_router(ig.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": UID, "email": "wh@example.invalid"}
    k = types.SimpleNamespace(c=TestClient(app, raise_server_exceptions=False), baza=baza, poslato=poslato, ishod=True)
    return k


LOSI = ["http://javni.example/h", "https://127.0.0.1/h", "https://169.254.169.254/latest/meta-data/",
        "https://interni.example/h", "https://metadata.example/h", "https://javni.example:8443/h",
        "file:///etc/passwd", "ftp://javni.example/h", "https://[::1]/h", "https://nepostoji.example/h"]


@pytest.mark.parametrize("url", LOSI)
def test_registracija_odbija_ne_javni_https(k, url):
    r = k.c.post("/api/webhooks", json={"url": url, "events": ["predmet.kreiran"]})
    assert r.status_code == 400, (url, r.status_code, r.text)
    assert k.baza.redovi == []


def test_registracija_javnog_https_radi(k):
    r = k.c.post("/api/webhooks", json={"url": "https://javni.example/vindex", "events": ["predmet.kreiran"]})
    assert r.status_code == 200 and len(k.baza.redovi) == 1


@pytest.mark.parametrize("url", ["http://127.0.0.1:6379/", "https://169.254.169.254/latest/meta-data/", "https://interni.example/h"])
def test_test_ruta_ne_salje_na_stari_interni_red(k, url):
    """Red upisan pre ispravke (ili host koji je u međuvremenu promenio adresu) se proverava pri slanju."""
    k.baza.redovi.append({"id": "wh-stari", "user_id": UID, "url": url, "aktivan": True, "events": ["test"]})
    r = k.c.post("/api/webhooks/test/wh-stari")
    assert r.status_code == 400 and k.poslato == []


def test_test_ruta_vraca_stvaran_ishod(k):
    k.baza.redovi.append({"id": "wh-1", "user_id": UID, "url": "https://javni.example/h", "aktivan": True, "events": ["test"]})
    k.ishod = False
    r = k.c.post("/api/webhooks/test/wh-1")
    assert r.status_code == 200 and r.json()["success"] is False and k.poslato == ["https://javni.example/h"]
    k.ishod = True
    assert k.c.post("/api/webhooks/test/wh-1").json()["success"] is True


def test_tudji_ili_nepostojeci_webhook_404_ne_500(k):
    k.baza.redovi.append({"id": "wh-tudji", "user_id": "u-drugi", "url": "https://javni.example/h", "aktivan": True})
    assert k.c.post("/api/webhooks/test/wh-tudji").status_code == 404
    assert k.c.post("/api/webhooks/test/ne-postoji").status_code == 404
    assert k.poslato == []


def test_slanje_ne_prati_preusmeravanje():
    import urllib.request
    import routers.integracije as ig
    h = ig._BezPreusmeravanja()
    zahtev = urllib.request.Request("https://javni.example/h", data=b"{}", method="POST")
    assert h.redirect_request(zahtev, None, 302, "Found", {}, "http://169.254.169.254/") is None
    assert any(isinstance(x, ig._BezPreusmeravanja) for x in ig._WEBHOOK_OPENER.handlers)


def test_trigger_preskace_interni_url(k, monkeypatch):
    import asyncio
    import routers.integracije as ig
    k.baza.redovi += [
        {"id": "a", "user_id": UID, "url": "https://interni.example/h", "aktivan": True, "events": ["predmet.kreiran"], "secret": None},
        {"id": "b", "user_id": UID, "url": "https://javni.example/h", "aktivan": True, "events": ["predmet.kreiran"], "secret": None},
    ]
    asyncio.run(ig.trigger_webhook("predmet.kreiran", UID, {"x": 1}))
    assert k.poslato == ["https://javni.example/h"]
