# -*- coding: utf-8 -*-
"""NS3-N01 — pytest plugin: zabrana SVAKOG spoljnog mrežnog pokušaja, i iz podprocesa.

Učitava se izričito (`-p tests._ns3_mreza_zabrana`), ne automatski: postojeća brana u `conftest.py` namerno
pokriva samo naplative hostove i produkcionu bazu, a deny-all za ceo suite bi oborio stotine testova koji
fail-soft gađaju izmišljene hostove. Ovaj plugin služi kanarincu (`test_ns3_n01_mreza_kanarinac.py`) koji
pokreće cron/notifikacione testove u zasebnom procesu i traži NULA pokušaja.

Dva sloja:
1. Python u ovom procesu: `socket.getaddrinfo` i ne-loopback `socket.connect` se odbijaju i beleže.
2. Podprocesi (bash/curl/node...): `HTTP(S)_PROXY`/`ALL_PROXY` pokazuju na lokalni „sink“ koji beleži ciljni
   host iz prvog reda zahteva i zatvara vezu — ništa se ne prosleđuje. Python-level zakrpa ne vidi podproces;
   ovaj sloj vidi (incident PR #45: pravi `curl` iz testa je gađao produkciju).
Loopback je dozvoljen (event loop na Windows-u, lokalni test servisi).

Dnevnik: JSON linije u fajlu iz `NS3_MREZA_DNEVNIK` (obavezno)."""
import json
import os
import socket
import threading
import traceback

_DNEVNIK = os.environ["NS3_MREZA_DNEVNIK"]
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_TEST = {"id": None}
_lock = threading.Lock()


def _zapisi(vrsta, cilj):
    stek = [f"{os.path.basename(f.filename)}:{f.lineno}" for f in traceback.extract_stack()
            if "site-packages" not in f.filename and "_ns3_mreza_zabrana" not in f.filename][-6:]
    with _lock, open(_DNEVNIK, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"test": _TEST["id"], "vrsta": vrsta, "cilj": str(cilj), "stek": stek}) + "\n")


_pravi_gai = socket.getaddrinfo
_pravi_connect = socket.socket.connect


def _gai(host, *a, **k):
    h = host.decode("ascii", "ignore") if isinstance(host, (bytes, bytearray)) else host
    if h is None or h in _LOOPBACK:
        return _pravi_gai(host, *a, **k)
    _zapisi("dns", h)
    raise socket.gaierror(socket.EAI_NONAME, "NS3 zabrana mreže: DNS odbijen")


def _connect(self, adresa):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not (
            isinstance(adresa, tuple) and str(adresa[0]) in _LOOPBACK):
        _zapisi("connect", adresa)
        raise ConnectionRefusedError("NS3 zabrana mreže: connect odbijen")
    return _pravi_connect(self, adresa)


def _sink():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)

    def _petlja():
        while True:
            try:
                veza, _ = srv.accept()
            except OSError:
                return
            try:
                veza.settimeout(2)
                prvi = veza.recv(4096).split(b"\r\n", 1)[0].decode("latin-1", "replace")
                _zapisi("proksi", prvi[:200] or "<prazno>")
                veza.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            finally:
                veza.close()

    threading.Thread(target=_petlja, daemon=True).start()
    return srv.getsockname()[1]


_port = _sink()
_proksi = f"http://127.0.0.1:{_port}"
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ[_k] = _proksi
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost,::1,testserver"   # Starlette TestClient
os.environ["NODE_USE_ENV_PROXY"] = "1"
os.environ["NS3_MREZA_ZABRANA"] = _proksi
socket.getaddrinfo = _gai
socket.socket.connect = _connect


def pytest_runtest_setup(item):
    _TEST["id"] = item.nodeid
