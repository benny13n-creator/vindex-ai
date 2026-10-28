# -*- coding: utf-8 -*-
"""N4 — podsetnici: ročišta u dnevnom podsetniku (Bojan: „podsetnike za ročišta“), samo ZAKAZANA ročišta,
„već poslato“ po PREDMETU, nedeljni pregled bez otkazanih ročišta. NIJEDAN test ne šalje pravi email.
Kapija potvrde roka (AI predlog ne šalje) je nepromenjena i ovde se proverava kroz `_potvrdjeni_ids`."""
import asyncio
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from tests import test_b10_reminder_claim as b10

UID, PID, P2 = b10.UID, b10.PID, "p-2"


def _sutra():
    from routers.email_notif import _danas_beograd
    return (date.today() + timedelta(days=1)).isoformat()


def _rok(rid, datum, predmet=PID, dogadjaj="Rok za žalbu"):
    return {"id": rid, "akter": "Advokat", "izvor": "AI_AUTONOMOUS", "dogadjaj": dogadjaj, "datum_iso": datum,
            "predmet_id": predmet, "user_id": UID, "vaznost": "kritičan"}


def _roc(rid, datum, status="zakazano", predmet=PID):
    return {"id": rid, "predmet_id": predmet, "user_id": UID, "sud": "Osnovni sud u Beogradu", "sudnica": "14",
            "datum": datum, "vreme": "10:00:00", "status": status}


def _pokreni(baza, potvrdjeni=(), smtp_puca=False):
    import routers.email_notif as en
    poslati = []

    def _smtp(to, subj, html):
        if smtp_puca:
            raise RuntimeError("SMTP 421")
        poslati.append((to, subj, html))

    with patch.object(en, "_SMTP_HOST", "smtp.test.invalid"), patch.object(en, "_get_supa", return_value=baza), \
         patch.object(en, "_smtp_send", _smtp), patch.object(en, "_potvrdjeni_ids", lambda ids: {i for i in ids if i in set(potvrdjeni)}):
        rez = asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))
    return rez, poslati


def test_zakazano_rociste_sutra_salje_podsetnik_sa_sudom_i_vremenom():
    b = b10.FakeBaza([])
    b.tabele["rocista"] = [_roc("h1", _sutra())]
    rez, poslati = _pokreni(b)
    assert rez["poslato"] == 1 and len(poslati) == 1, rez
    _, subj, html = poslati[0]
    assert "ročište" in subj and "ističe rok" not in subj
    assert "Ročište — Osnovni sud u Beogradu, sudnica 14" in html and "u 10:00" in html
    assert [r["predmet_id"] for r in b.log] == [PID]


@pytest.mark.parametrize("status", ["otkazano", "odlozeno", "odrzano"])
def test_otkazano_odlozeno_odrzano_rociste_ne_salje(status):
    b = b10.FakeBaza([])
    b.tabele["rocista"] = [_roc("h1", _sutra(), status=status)]
    rez, poslati = _pokreni(b)
    assert poslati == [] and rez["poslato"] == 0 and b.log == []


def test_rociste_arhiviranog_predmeta_ne_salje():
    b = b10.FakeBaza([], arhiviran=True)
    b.tabele["rocista"] = [_roc("h1", _sutra())]
    assert _pokreni(b)[1] == []


def test_iskljucen_profil_ne_salje_ni_rociste():
    for b in (b10.FakeBaza([], aktivan=False), b10.FakeBaza([], dan_1=False)):
        b.tabele["rocista"] = [_roc("h1", _sutra())]
        assert _pokreni(b)[1] == []


def test_nepotvrdjen_ai_rok_ne_ulazi_ni_uz_rociste():
    import routers.email_notif as en
    b = b10.FakeBaza([_rok("r1", _sutra())])
    b.tabele["rocista"] = [_roc("h1", _sutra())]
    html = []
    with patch.object(en, "_email_html", lambda rokovi, *a, **k: html.append(([r["id"] for r in rokovi], [r["id"] for r in k.get("rocista") or []])) or "<html/>"):
        _pokreni(b, potvrdjeni=())
    assert html == [([], ["h1"])]                       # ročište da, nepotvrđen rok NE


def test_vec_poslato_je_po_predmetu_a_ne_po_korisniku():
    """Ranije: pre-provera (user, datum, dan) je gasila podsetnik za DRUGI predmet istog datuma kad je rok
    potvrđen između dva pokretanja istog dana. Sada se šalje samo za predmet koji još nije rezervisan."""
    b = b10.FakeBaza([_rok("r1", _sutra()), _rok("r2", _sutra(), predmet=P2, dogadjaj="Rok u drugom predmetu")])
    b.tabele["predmeti"].append({"id": P2, "user_id": UID, "status": "aktivan"})
    rez1, p1 = _pokreni(b, potvrdjeni=("r1",))
    rez2, p2 = _pokreni(b, potvrdjeni=("r1", "r2"))           # r2 potvrđen posle prvog pokretanja
    assert len(p1) == 1 and len(p2) == 1, (rez1, rez2)
    assert "Rok u drugom predmetu" in p2[0][2] and "Rok za žalbu" not in p2[0][2]   # samo NOV predmet
    assert sorted(r["predmet_id"] for r in b.log) == [PID, P2]
    rez3, p3 = _pokreni(b, potvrdjeni=("r1", "r2"))
    assert p3 == [] and rez3["poslato"] == 0                  # treće pokretanje: ništa dvaput


def test_smtp_pad_rezervisano_neisporuceno_bez_ponavljanja():
    b = b10.FakeBaza([])
    b.tabele["rocista"] = [_roc("h1", _sutra())]
    rez, _ = _pokreni(b, smtp_puca=True)
    assert rez["neisporuceno"] == 1 and rez["poslato"] == 0 and len(b.log) == 1
    rez2, p2 = _pokreni(b)
    assert p2 == [] and rez2["poslato"] == 0                  # ishod nepoznat → nema automatskog ponavljanja


def test_nedeljni_pregled_bez_otkazanih_rocista(monkeypatch):
    import routers.email_notif as en
    U = b10._Upit
    monkeypatch.setattr(U, "gte", lambda self, k, v: U([r for r in self._r if str(r.get(k, "")) >= v], self._t, self._b), raising=False)
    monkeypatch.setattr(U, "lte", lambda self, k, v: U([r for r in self._r if str(r.get(k, "")) <= v], self._t, self._b), raising=False)
    monkeypatch.setattr(U, "order", lambda self, *a, **k: self, raising=False)
    b = b10.FakeBaza([])
    b.tabele["korisnik_email_notif"][0]["nedeljni"] = True
    b.tabele["rocista"] = [_roc("h1", _sutra()), dict(_roc("h2", _sutra(), status="otkazano"), sud="OTKAZANI sud")]
    b.tabele["billing_entries"] = []
    vidjena = []
    with patch.object(en, "_SMTP_HOST", "smtp.test.invalid"), patch.object(en, "_get_supa", return_value=b),          patch.object(en, "_smtp_send", lambda *a: None), patch.object(en, "_potvrdjeni_ids", lambda ids: set()),          patch.object(en, "_weekly_digest_html", lambda ime, rokovi, rocista, *a, **k: vidjena.append([r["dogadjaj"] for r in rocista]) or "<html/>"):
        asyncio.run(en.posalji_nedeljni_sazetak(b10._request(), user={"user_id": "cron", "email": ""}))
    assert vidjena == [["Osnovni sud u Beogradu"]], vidjena
