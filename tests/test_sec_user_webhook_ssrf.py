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


def test_trigger_preskace_interni_url(k, monkeypatch):
    import asyncio
    import routers.integracije as ig
    k.baza.redovi += [
        {"id": "a", "user_id": UID, "url": "https://interni.example/h", "aktivan": True, "events": ["predmet.kreiran"], "secret": None},
        {"id": "b", "user_id": UID, "url": "https://javni.example/h", "aktivan": True, "events": ["predmet.kreiran"], "secret": None},
    ]
    asyncio.run(ig.trigger_webhook("predmet.kreiran", UID, {"x": 1}))
    assert k.poslato == ["https://javni.example/h"]


# ── DNS rebinding / TOCTOU (2026-10-26) ─────────────────────────────────────────────────────────────────────
# Ranije: validator je razrešio ime, a urllib ga je pri povezivanju razrešio PONOVO (i čitao HTTPS_PROXY) — DNS je
# mogao da odgovori javnom adresom proveri i 169.254.169.254 konekciji. Sada slanje razrešava jednom i TCP otvara
# samo ka proverenoj adresi. Mreža je zamenjena: getaddrinfo vraća zadat niz odgovora, create_connection beleži
# adresu i vraća kraj socketpair-a, TLS kontekst beleži server_hostname (pravi kontekst se proverava posebno).

JAVNA, PRIVATNA = "93.184.216.34", "169.254.169.254"
ODGOVOR_200 = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


@pytest.fixture
def mreza(monkeypatch):
    import routers.integracije as ig
    m = types.SimpleNamespace(odgovori=[], dns_pozivi=0, konekcije=[], sni=[], odgovor=ODGOVOR_200, zahtevi=[])

    def _gai(host, port, *a, **kw):
        m.dns_pozivi += 1
        ip = m.odgovori.pop(0) if len(m.odgovori) > 1 else m.odgovori[0]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    def _poveži(adresa, timeout=None, *a, **kw):
        m.konekcije.append(adresa)
        klijent, server = socket.socketpair()
        server.sendall(m.odgovor)
        m.zahtevi.append(server)
        return klijent

    class _TLS:
        def wrap_socket(self, sock, server_hostname=None, **kw):
            m.sni.append(server_hostname)
            return sock

    monkeypatch.setattr(socket, "getaddrinfo", _gai)
    monkeypatch.setattr(socket, "create_connection", _poveži)
    monkeypatch.setattr(ig, "_TLS_KONTEKST", _TLS())
    yield m
    for s in m.zahtevi:
        s.close()


def _primljeno(m):
    s = m.zahtevi[-1]
    s.settimeout(2)
    deo, sve = b"x", b""
    while deo:
        try:
            deo = s.recv(65536)
        except (socket.timeout, OSError):
            break
        sve += deo
    return sve.decode("latin-1")


def test_dns_rebinding_izmedju_provere_i_slanja_privatna_adresa_ne_dobija_konekciju(mreza):
    """Ruta proveri ime (javno), DNS se zatim promeni na metadata adresu: konekcija se ne otvara uopšte."""
    import routers.integracije as ig
    from shared.deps import get_current_user
    from shared.rate import limiter
    baza = _Baza()
    baza.redovi.append({"id": "wh-1", "user_id": UID, "url": "https://rebind.example/h", "aktivan": True, "events": ["test"]})
    mreza.odgovori = [JAVNA, PRIVATNA]
    app = FastAPI()
    app.include_router(ig.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": UID, "email": "wh@example.invalid"}
    import unittest.mock as um
    with um.patch.object(ig, "_get_supa", lambda: baza), um.patch.object(limiter, "enabled", False):
        r = TestClient(app, raise_server_exceptions=False).post("/api/webhooks/test/wh-1")
    assert mreza.dns_pozivi == 2
    assert mreza.konekcije == []
    assert r.status_code == 200 and r.json()["success"] is False


def test_konekcija_ide_na_proverenu_adresu_a_tls_identitet_je_hostname(mreza):
    """Ime se razrešava tačno jednom; posle toga DNS vraća privatnu adresu, ali TCP ide na proverenu javnu."""
    import routers.integracije as ig
    mreza.odgovori = [JAVNA, PRIVATNA]
    assert ig._slanje_webhook_sync("https://javni.example/put?a=1", '{"x":1}', "tajna") is True
    assert mreza.dns_pozivi == 1
    assert mreza.konekcije == [(JAVNA, 443)]
    assert mreza.sni == ["javni.example"]
    zahtev = _primljeno(mreza)
    assert zahtev.startswith("POST /put?a=1 HTTP/1.1\r\n")
    assert "Host: javni.example\r\n" in zahtev and "X-Vindex-Signature: sha256=" in zahtev


def test_privatna_adresa_pri_slanju_nikad_ne_dobija_konekciju(mreza):
    import routers.integracije as ig
    for ip in (PRIVATNA, "10.0.0.7", "127.0.0.1", "::1", "::ffff:10.0.0.7", "0.0.0.0"):
        mreza.odgovori = [ip]
        assert ig._slanje_webhook_sync("https://javni.example/h", "{}", None) is False, ip
    assert mreza.konekcije == []


def test_vezana_konekcija_odbija_neproverenu_adresu_i_bez_razresavanja(mreza):
    """Druga linija odbrane: connect() sam proverava adresu na koju ide."""
    import routers.integracije as ig
    with pytest.raises(ConnectionRefusedError):
        ig._VezanaHTTPS("javni.example", PRIVATNA).connect()
    assert mreza.konekcije == [] and mreza.dns_pozivi == 0


def test_preusmeravanje_se_ne_prati(mreza):
    import routers.integracije as ig
    mreza.odgovori = [JAVNA]
    mreza.odgovor = (b"HTTP/1.1 302 Found\r\nLocation: http://169.254.169.254/latest/meta-data/\r\n"
                     b"Content-Length: 0\r\nConnection: close\r\n\r\n")
    assert ig._slanje_webhook_sync("https://javni.example/h", "{}", None) is False
    assert mreza.konekcije == [(JAVNA, 443)]


def test_proxy_iz_okruzenja_se_ne_koristi(mreza, monkeypatch):
    import routers.integracije as ig
    for ime in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(ime, "http://10.0.0.1:3128")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    mreza.odgovori = [JAVNA]
    assert ig._slanje_webhook_sync("https://javni.example/h", "{}", None) is True
    assert mreza.konekcije == [(JAVNA, 443)]


def test_tls_kontekst_proverava_sertifikat_i_hostname():
    import ssl
    import routers.integracije as ig
    assert ig._TLS_KONTEKST.verify_mode == ssl.CERT_REQUIRED and ig._TLS_KONTEKST.check_hostname is True
    assert ig._VezanaHTTPS("javni.example", JAVNA)._context is ig._TLS_KONTEKST


def test_registracija_odbija_ipv4_mapiranu_privatnu_adresu(k):
    ADRESE["mapirana.example"] = "::ffff:10.0.0.7"
    try:
        r = k.c.post("/api/webhooks", json={"url": "https://mapirana.example/h", "events": ["predmet.kreiran"]})
    finally:
        del ADRESE["mapirana.example"]
    assert r.status_code == 400 and k.baza.redovi == []
