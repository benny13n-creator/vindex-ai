# -*- coding: utf-8 -*-
"""TENFRONTS-M10 — jedan primalac podsetnika, isti u svim putanjama.

Kanonsko pravilo (docs/v2-execution/VCR002_TASK_LEDGER.md:202, spojeno PR #20): „Primalac: isključivo vlasnik
profila (`profiles.email` po `user_id`)“. Zakazani podsetnik ga poštuje. Pre ispravke su druge dve putanje
koristile adresu iz prijave (JWT): oznaka „Šalje se na:“ (GET /email-notif/profil) i probni email
(POST /email-notif/test) — pa probni email nije proveravao stvarnog primaoca, a ekran je mogao da pokaže
adresu na koju podsetnici NE idu. Nikad se ne šalje na obe adrese."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests import test_b10_reminder_claim as b10

PRIJAVA = "prijava@example.invalid"      # adresa iz JWT-a
PROFIL = "profil@example.invalid"        # profiles.email — kanonski primalac
UID, DRUGI = "u-1", "u-2"


class _Upit:
    def __init__(self, redovi):
        self.redovi = list(redovi)

    def select(self, *a, **k): return self

    def eq(self, k, v):
        self.redovi = [r for r in self.redovi if r.get(k) == v]
        return self

    def limit(self, *a, **k): return self
    def maybe_single(self): self._jedan = True; return self

    def execute(self):
        if getattr(self, "_jedan", False):
            if not self.redovi:
                return None                  # postgrest 2.28.3
            class R: pass
            r = R(); r.data = self.redovi[0]; return r
        class R: pass
        r = R(); r.data = self.redovi; return r


class _Baza:
    def __init__(self, profili, notif=None):
        self.t = {"profiles": profili, "korisnik_email_notif": notif or []}

    def table(self, ime):
        return _Upit(self.t.get(ime, []))


def _klijent(monkeypatch, profili, smtp="smtp.test.invalid", notif=None):
    import routers.email_notif as en
    from shared.deps import get_current_user
    from shared.rate import limiter
    poslato = []
    monkeypatch.setattr(en, "_get_supa", lambda: _Baza(profili, notif))
    monkeypatch.setattr(en, "_SMTP_HOST", smtp)
    monkeypatch.setattr(en, "_smtp_send", lambda to, subj, html: poslato.append((to, subj, html)))
    monkeypatch.setattr(limiter, "enabled", False)
    app = FastAPI()
    app.include_router(en.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": UID, "email": PRIJAVA}
    return TestClient(app, raise_server_exceptions=False), poslato


PROFILI = [{"id": UID, "email": PROFIL}, {"id": DRUGI, "email": "tudja@example.invalid"}]


def test_oznaka_prikazuje_stvarnog_primaoca(monkeypatch):
    k, _ = _klijent(monkeypatch, PROFILI)
    assert k.get("/email-notif/profil").json()["email"] == PROFIL


def test_oznaka_sa_aktivnim_profilom_obavestenja_prikazuje_stvarnog_primaoca(monkeypatch):
    notif = [{"user_id": UID, "aktivan": True, "dan_7": True, "dan_3": True, "dan_1": True, "nedeljni": True}]
    k, _ = _klijent(monkeypatch, PROFILI, notif=notif)
    d = k.get("/email-notif/profil").json()
    assert d["aktivan"] is True and d["email"] == PROFIL


def test_probni_email_ide_stvarnom_primaocu_jednom(monkeypatch):
    k, poslato = _klijent(monkeypatch, PROFILI)
    r = k.post("/email-notif/test")
    assert r.status_code == 200, r.text
    assert [p[0] for p in poslato] == [PROFIL]                 # jedan primalac, nikad oba
    assert r.json()["poslato_na"] == PROFIL


def test_sve_adrese_iste(monkeypatch):
    k, poslato = _klijent(monkeypatch, [{"id": UID, "email": PRIJAVA}])
    assert k.get("/email-notif/profil").json()["email"] == PRIJAVA
    assert k.post("/email-notif/test").status_code == 200 and [p[0] for p in poslato] == [PRIJAVA]


def test_bez_adrese_u_profilu_nema_slanja_ni_lazne_oznake(monkeypatch):
    k, poslato = _klijent(monkeypatch, [{"id": UID, "email": ""}, PROFILI[1]])
    assert k.get("/email-notif/profil").json()["email"] in (None, "")
    r = k.post("/email-notif/test")
    assert r.status_code == 400 and poslato == []


def test_bez_reda_profila_nema_slanja(monkeypatch):
    k, poslato = _klijent(monkeypatch, [PROFILI[1]])
    assert k.post("/email-notif/test").status_code == 400 and poslato == []


def test_tudji_profil_se_nikad_ne_koristi(monkeypatch):
    k, poslato = _klijent(monkeypatch, [PROFILI[1]])
    assert "tudja@example.invalid" not in str(k.get("/email-notif/profil").json())
    k.post("/email-notif/test")
    assert all("tudja" not in p[0] for p in poslato)


def test_probni_email_ne_nosi_podatke_predmeta(monkeypatch):
    k, poslato = _klijent(monkeypatch, PROFILI)
    k.post("/email-notif/test")
    html = poslato[0][2]
    assert "Test rok" in html


def test_zakazani_podsetnik_i_dalje_ide_na_profiles_email():
    baza = b10.FakeBaza([b10._rok(b10._sutra())])
    baza.tabele["profiles"] = [{"id": b10.UID, "email": PROFIL}]
    import routers.email_notif as en
    from unittest.mock import patch
    with patch.object(en, "_potvrdjeni_ids", lambda ids: {str(i) for i in ids if i}):
        rez, poslati = b10._pokreni(baza)
    assert [p[0] for p in poslati] == [PROFIL] and rez["poslato"] == 1
