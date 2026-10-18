# -*- coding: utf-8 -*-
"""NS3-N04 — povlačenje saglasnosti za email podsetnike ne sme da izgleda uspešno kada nije uspelo.

Stari UI (`static/vindex.js::emailNotifDeaktivaj`) šalje `DELETE /email-notif/profil`. Pre ispravke je poruku
„Email notifikacije deaktivirane.“ prikazivao BEZ provere odgovora — i za 500 (baza), 429 (limiter) i 401
(istekla sesija). Advokat je verovao da su podsetnici isključeni, a red `korisnik_email_notif` je ostajao
aktivan. Obrazac iz iste datoteke (`emailNotifSacuvaj`, `emailNotifTest`) već proverava `r.ok`.

Stvarne funkcije `emailNotifDeaktivaj` i `_enMsg` izvršavaju se u Node-u; `fetch`, `_vxConfirm` i DOM su lažni.
`emailNotifLoad` je zamenjen brojačem (meri se samo da li je stanje ponovo učitano)."""
import json
import os
import shutil
import subprocess

import pytest

KOREN = os.path.join(os.path.dirname(__file__), "..")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node nije dostupan")
USPEH = "Email notifikacije deaktivirane."


def _funkcija(src, ime):
    i = src.index("function " + ime + "(")
    if src[i - 6:i] == "async ":
        i -= 6
    nivo, j = 0, src.index("{", i)
    for k in range(j, len(src)):
        nivo += {"{": 1, "}": -1}.get(src[k], 0)
        if nivo == 0:
            return src[i:k + 1]
    raise AssertionError(ime)


SKRIPTA = r"""
const sc = JSON.parse(process.argv[1]);
const el = {textContent: '', style: {}};
const document = { getElementById: (id) => id === 'en-msg' ? el : null };
function setTimeout() {}
var currentSession = sc.sesija ? {access_token: 't'} : null;
const pozivi = []; let ucitano = 0;
async function emailNotifLoad() { ucitano++; }
function _vxConfirm(msg, onOk) { return onOk(); }
async function fetch(url, opts) {
  pozivi.push({url, metod: opts && opts.method});
  if (sc.mreza) throw new Error('net');
  return {ok: sc.status >= 200 && sc.status < 300, status: sc.status,
          json: async () => (sc.telo === undefined ? {} : sc.telo)};
}
%IZVOR%
(async () => {
  await emailNotifDeaktivaj();
  await new Promise(r => setImmediate(r));
  console.log(JSON.stringify({poruka: el.textContent, boja: el.style.color, pozivi, ucitano}));
})();
"""


def _pokreni(**sc):
    sc.setdefault("sesija", True)
    src = open(os.path.join(KOREN, "static", "vindex.js"), encoding="utf-8").read()
    izvor = _funkcija(src, "_enMsg") + "\n" + _funkcija(src, "emailNotifDeaktivaj")
    r = subprocess.run([NODE, "-e", SKRIPTA.replace("%IZVOR%", izvor), json.dumps(sc)],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("status,telo", [
    (500, {"detail": "Internal Server Error"}),
    (429, {"error": "Rate limit exceeded"}),
    (401, {"detail": "Sesija je istekla."}),
    (503, None),
])
def test_neuspeo_odgovor_ne_tvrdi_deaktivaciju(status, telo):
    s = _pokreni(status=status, telo=telo)
    assert s["pozivi"] == [{"url": "/email-notif/profil", "metod": "DELETE"}]
    assert s["poruka"] != USPEH, f"HTTP {status} prikazan kao uspešna deaktivacija"
    assert s["poruka"] and s["boja"] == "#f87171"


def test_detalj_servera_se_prikazuje():
    s = _pokreni(status=401, telo={"detail": "Sesija je istekla."})
    assert s["poruka"] == "Sesija je istekla."


def test_uspeh_i_dalje_potvrdjen_i_stanje_ponovo_ucitano():
    s = _pokreni(status=200, telo={"ok": True})
    assert s["poruka"] == USPEH and s["ucitano"] == 1


def test_mrezna_greska_nije_uspeh():
    s = _pokreni(mreza=True)
    assert s["poruka"] != USPEH and s["boja"] == "#f87171"


def test_neuspeh_ponovo_ucitava_stvarno_stanje():
    s = _pokreni(status=500, telo={})
    assert s["ucitano"] == 1, "posle neuspeha ekran mora pokazati stvarno (i dalje aktivno) stanje"


def test_bez_sesije_nema_zahteva():
    s = _pokreni(sesija=False, status=200)
    assert s["pozivi"] == [] and s["poruka"] == ""
