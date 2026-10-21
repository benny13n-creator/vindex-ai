# -*- coding: utf-8 -*-
"""Website V2 positioning + feedback: reject false support delivery confirmations."""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import api
from shared.deps import get_current_user


def _poslji(baza, email):
    api.app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "00000000-0000-4000-8000-000000000001",
        "email": "test-korisnik@example.invalid",
    }
    try:
        with patch("routers.support._get_supa", return_value=object()), \
             patch("routers.support._save_ticket", new=AsyncMock(return_value=baza)), \
             patch("routers.support._send_support_email", return_value=email):
            with TestClient(api.app) as k:
                return k.post("/api/support/poruka", json={
                    "kategorija": "ai",
                    "poruka": "Sistem je prikazao netačan odgovor na pravno pitanje.",
                    "kontekst": "/app",
                }, headers={"X-Forwarded-For": "198.51.100.242"})
    finally:
        api.app.dependency_overrides.pop(get_current_user, None)


def test_prijava_ne_sme_biti_lazno_uspesna():
    r = _poslji(False, False)
    assert r.status_code == 503
    assert "nije" in r.json()["detail"].lower()


def test_evidencija_bez_emaila_ne_tvrdi_slatu_poruku():
    r = _poslji(True, False)
    assert r.status_code == 200
    t = r.json()
    assert t["ok"] is True
    assert t["evidentirano"] is True
    assert t["email_poslat"] is False
    assert "nije potvrđena" in t["message"]


def test_email_isporuka_se_prijavljuje_tek_kada_je_potvrdjena():
    r = _poslji(False, True)
    assert r.status_code == 200
    t = r.json()
    assert t["email_poslat"] is True
    assert t["evidentirano"] is False


def test_v2_prijava_ne_salje_sadrzaj_predmeta_automatski():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "frontend-v2-ng/src/feedback-prijava.js").read_text()
    html = (Path(__file__).resolve().parents[1] / "frontend-v2-ng/index.html").read_text()
    assert "/api/support/poruka" in js
    assert "VxSesija" in js and "Authorization" in js
    assert "screenshot_base64" not in js
    assert "localStorage" not in js
    assert "Ne unosite imena klijenata" in html
    assert "benny13.n@gmail.com" in js
