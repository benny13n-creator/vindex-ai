# -*- coding: utf-8 -*-
"""Email podsetnici — lanac od kraja do kraja (night/deadlines-alerts-vcr002, T10).

GitHub workflow (stvarni `run` korak) → X-Cron-Key → stvarna ruta `/email-notif/send-reminders` (stvarni
`_require_cron_or_founder`, `FakeBaza`, SMTP zamenjen) → JSON → validacija u workflow-u → ishod posla.
Lažni `curl` prosleđuje zahtev ruti preko TestClient-a umesto mreže: header koji workflow pošalje je header
koji ruta proverava. Nijedan mrežni poziv, nijedna prava tajna."""
import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests import test_alerts_email_cron_contract as wf
from tests import test_b10_reminder_claim as b10

KLJUC = "test-kljuc-7f3a9c"


@pytest.fixture(autouse=True)
def _potvrdjeno(monkeypatch):
    import routers.email_notif as en
    monkeypatch.setattr(en, "_potvrdjeni_ids", lambda ids: {str(i) for i in ids if i})


def _ruta(baza, header, smtp_puca=False, smtp_host="smtp.test.invalid", serverska_tajna=KLJUC):
    """Stvarna ruta iza stvarne autorizacije; vraća (status, telo, poslati)."""
    import routers.email_notif as en
    from shared.rate import limiter
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(en.router)
    poslati = []

    def _smtp(to, subj, html):
        if smtp_puca:
            raise RuntimeError("SMTP 421")
        poslati.append(subj)
    with patch.object(en, "_CRON_SECRET", serverska_tajna), patch.object(en, "_SMTP_HOST", smtp_host), \
         patch.object(en, "_get_supa", return_value=baza), patch.object(en, "_smtp_send", _smtp), \
         patch.object(en, "_email_html", lambda *a, **k: "<html/>"), patch.object(limiter, "enabled", False):
        r = TestClient(app).post("/email-notif/send-reminders", headers=header)
    return r.status_code, r.text, poslati


def _lanac(tmp_path, baza, **kw):
    """Prvo izvrši rutu sa headerom koji workflow šalje, pa njen stvarni odgovor pusti kroz workflow."""
    kod_wf, izlaz_wf, pozivi = wf.pokreni(tmp_path, "200", {"x": 1})       # samo da dobijemo stvarne argumente
    argumenti = pozivi[0].splitlines()
    header = dict(a.split(": ", 1) for a in argumenti if ": " in a and not a.startswith("http"))
    status, telo, poslati = _ruta(baza, header, **kw)
    (tmp_path / "drugi").mkdir()
    kod, izlaz, _ = wf.pokreni(tmp_path / "drugi", str(status), telo)
    return kod, izlaz, status, json.loads(telo), poslati


def test_potvrdjen_rok_poslat_zeleno_ali_samo_smtp_prihvacen(tmp_path):
    kod, izlaz, status, telo, poslati = _lanac(tmp_path, b10.FakeBaza([b10._rok(b10._sutra())]))
    assert status == 200 and telo["poslato"] == 1 and len(poslati) == 1
    assert kod == 0 and "INBOX_UNCONFIRMED" in izlaz and "DELIVERY_VERIFIED" not in izlaz


def test_smtp_pad_crveno_delivery_unconfirmed(tmp_path):
    kod, izlaz, status, telo, _ = _lanac(tmp_path, b10.FakeBaza([b10._rok(b10._sutra())]), smtp_puca=True)
    assert status == 200 and telo["neisporuceno"] == 1
    assert kod != 0 and "DELIVERY_UNCONFIRMED" in izlaz


def test_smtp_nije_konfigurisan_crveno(tmp_path):
    baza = b10.FakeBaza([b10._rok(b10._sutra())])
    kod, izlaz, status, telo, poslati = _lanac(tmp_path, baza, smtp_host="")
    assert status == 200 and telo["greske"] == 1 and poslati == [] and baza.log == []
    assert kod != 0 and "JOB_FAILED" in izlaz


def test_nema_profila_zeleno_no_recipients(tmp_path):
    baza = b10.FakeBaza([b10._rok(b10._sutra())])
    baza.tabele["korisnik_email_notif"] = []
    kod, izlaz, status, telo, _ = _lanac(tmp_path, baza)
    assert status == 200 and kod == 0 and "NO_RECIPIENTS" in izlaz


def test_nepotvrdjen_rok_zeleno_bez_slanja(tmp_path, monkeypatch):
    import routers.email_notif as en
    monkeypatch.setattr(en, "_potvrdjeni_ids", lambda ids: set())
    rok = {**b10._rok(b10._sutra()), "izvor": "AI_AUTONOMOUS"}
    kod, izlaz, status, telo, poslati = _lanac(tmp_path, b10.FakeBaza([rok]))
    assert poslati == [] and telo["poslato"] == 0 and kod == 0 and "JOB_EXECUTED" in izlaz


def test_neuskladjen_kljuc_403_crveno(tmp_path):
    kod, izlaz, status, _, poslati = _lanac(tmp_path, b10.FakeBaza([b10._rok(b10._sutra())]),
                                            serverska_tajna="druga-vrednost")
    assert status == 403 and poslati == [] and kod != 0


def test_prazna_serverska_tajna_ne_prihvata_prazan_kljuc():
    """`CRON_SECRET` nije podešen na serveru + prazan header → 403 (ne univerzalni prolaz)."""
    status, _, poslati = _ruta(b10.FakeBaza([b10._rok(b10._sutra())]), {"X-Cron-Key": ""}, serverska_tajna="")
    assert status == 403 and poslati == []


def test_ponovljen_lanac_istog_dana_ne_salje_duplikat(tmp_path):
    baza = b10.FakeBaza([b10._rok(b10._sutra())])
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _, _, _, prvi, p1 = _lanac(tmp_path / "a", baza)
    _, _, _, drugi, p2 = _lanac(tmp_path / "b", baza)
    assert prvi["poslato"] == 1 and drugi["poslato"] == 0 and len(p1) == 1 and p2 == []
