# -*- coding: utf-8 -*-
"""TENFRONTS-M02 — GET /email-notif/profil za korisnika BEZ profila.

supabase==2.28.3: `maybe_single().execute()` vraća `None` kada red ne postoji (ne objekat sa praznim
`.data`). Ruta je čitala `res.data` → 500, a stari UI (`emailNotifLoad`, static/vindex.js) na `!r.ok`
tiho izlazi: adresa „—“ i bez ikakve informacije o SMTP-u. Odgovor mora da nosi istinit `smtp_ok` i bez
profila, bez kreiranja profila i bez slanja."""
import json
import os
import re
import shutil
import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

KOREN = os.path.join(os.path.dirname(__file__), "..")
NODE = shutil.which("node")


class _Upit:
    def __init__(self, baza, red):
        self.baza, self.red = baza, red

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def maybe_single(self): return self

    def upsert(self, *a, **k):
        self.baza.upisi.append(a)
        return self

    def execute(self):
        if self.red is None:
            return None                       # stvarno ponašanje postgrest 2.28.3 za 0 redova
        class R: pass
        r = R(); r.data = self.red
        return r


class _Baza:
    def __init__(self, red=None):
        self.red, self.upisi = red, []

    def table(self, ime):
        assert ime == "korisnik_email_notif"
        return _Upit(self, self.red)


def _get(monkeypatch, red, smtp_host):
    import routers.email_notif as en
    from shared.deps import get_current_user
    from shared.rate import limiter
    baza = _Baza(red)
    poslato = []
    monkeypatch.setattr(en, "_get_supa", lambda: baza)
    monkeypatch.setattr(en, "_SMTP_HOST", smtp_host)
    monkeypatch.setattr(en, "_smtp_send", lambda *a, **k: poslato.append(a))
    monkeypatch.setattr(limiter, "enabled", False)
    app = FastAPI()
    app.include_router(en.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u-1", "email": "advokat@example.invalid"}
    r = TestClient(app, raise_server_exceptions=False).get("/email-notif/profil")
    return r, baza, poslato


@pytest.mark.parametrize("host,ocekivano", [("smtp.test.invalid", True), ("", False)])
def test_bez_profila_istinit_smtp_ok_bez_kreiranja_i_slanja(monkeypatch, host, ocekivano):
    r, baza, poslato = _get(monkeypatch, None, host)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["smtp_ok"] is ocekivano
    assert d["aktivan"] is False                       # bez izričitog uključivanja ostaje isključeno
    assert baza.upisi == [] and poslato == []          # profil se ne kreira, ništa se ne šalje
    assert not any(k in json.dumps(d) for k in ("smtp.test.invalid", "EMAIL_SMTP_PASS"))


@pytest.mark.parametrize("host,ocekivano", [("smtp.test.invalid", True), ("", False)])
def test_postojeci_profil_nepromenjen(monkeypatch, host, ocekivano):
    red = {"user_id": "u-1", "aktivan": True, "dan_7": False, "dan_3": True, "dan_1": True, "nedeljni": False}
    r, baza, _ = _get(monkeypatch, red, host)
    d = r.json()
    assert r.status_code == 200 and d["smtp_ok"] is ocekivano
    assert (d["aktivan"], d["dan_7"], d["dan_3"], d["dan_1"], d["nedeljni"]) == (True, False, True, True, False)
    assert baza.upisi == []


def test_bez_profila_i_sa_profilom_isti_kljucevi_stanja(monkeypatch):
    bez, _, _ = _get(monkeypatch, None, "smtp.test.invalid")
    sa, _, _ = _get(monkeypatch, {"user_id": "u-1", "aktivan": False, "dan_7": True, "dan_3": True,
                                  "dan_1": True, "nedeljni": True}, "smtp.test.invalid")
    kljucevi = {"aktivan", "dan_7", "dan_3", "dan_1", "email", "smtp_ok"}
    assert kljucevi <= set(bez.json()) and kljucevi <= set(sa.json())


# ── potrošač: stvarna `emailNotifLoad` iz static/vindex.js u Node-u ────────────────────────────────

def _funkcija():
    with open(os.path.join(KOREN, "static", "vindex.js"), encoding="utf-8") as f:
        src = f.read()
    i = src.index("async function emailNotifLoad()")
    j = src.index("\nfunction _enMsg(", i)
    return src[i:j]


NODE_SKRIPTA = r"""
const odgovor = JSON.parse(process.argv[1]);           // `node -e`: prvi dodatni argument je argv[1]
const status = Number(process.argv[2]);
const el = {};
const document = {
  getElementById(id) { return el[id] || (el[id] = {id, style: {}, children: [], textContent: '', checked: false,
                                                   appendChild(c) { this.children.push(c); }}); },
  createElement() { return {style: {}, textContent: ''}; }
};
var currentSession = {access_token: 'x'};
async function fetch() { return {ok: status >= 200 && status < 300, json: async () => odgovor}; }
%FUNKCIJA%
emailNotifLoad().then(() => {
  const sec = el['email-notif-section'];
  console.log(JSON.stringify({upozorenje: !!(sec && sec.children.length), adresa: (el['email-notif-addr']||{}).textContent}));
});
"""


def _ui(odgovor, status=200):
    skripta = NODE_SKRIPTA.replace("%FUNKCIJA%", _funkcija())
    r = subprocess.run([NODE, "-e", skripta, json.dumps(odgovor), str(status)],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(NODE is None, reason="node nije dostupan")
def test_ui_odsustvo_smtp_ok_cita_kao_nekonfigurisan():
    """Zašto `smtp_ok` mora postojati i bez profila: potrošač odsustvo tumači kao „nije konfigurisan“."""
    assert _ui({"aktivan": False, "email": "a@example.invalid"})["upozorenje"] is True


@pytest.mark.skipif(NODE is None, reason="node nije dostupan")
@pytest.mark.parametrize("host,upozorenje", [("smtp.test.invalid", False), ("", True)])
def test_ui_sa_stvarnim_odgovorom_rute_bez_profila(monkeypatch, host, upozorenje):
    r, _, _ = _get(monkeypatch, None, host)
    stanje = _ui(r.json(), r.status_code)
    assert stanje["upozorenje"] is upozorenje
    assert stanje["adresa"] == "advokat@example.invalid"
