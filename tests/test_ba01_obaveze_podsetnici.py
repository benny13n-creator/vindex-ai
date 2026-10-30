# -*- coding: utf-8 -*-
"""Operation Bojan BA-01 — obaveza od kandidata do podsetnika (Task 8, BA-06/BA-07/BA-08).

Jedan predmet, jedan dokument sa DVA roka (A, B) i običnim datumom → oba NEPOTVRĐENA → potvrda A, odbijanje B →
druga, nezavisna obaveza C (drugi dokument, ISTI datum kao A) → dispečer podsetnika kroz STVARAN `_smtp_send`
(smtplib, STARTTLS, AUTH) prema lokalnom SMTP serveru za hvatanje na 127.0.0.1. Odluke idu kroz STVARAN lanac
odluka (`_potvrdjeni_ids` NIJE zamenjen). Nijedna poruka ne napušta računar; primaoci su `@example.invalid`.
`poslato` = SMTP je PRIHVATIO poruku — to nije prijem u sanduče (REAL_INBOX ostaje zasebna kapija).
Slučajevi otkaza transporta, rezervacije, pada lanca, otkazivanja i autorizacije: tests/test_s2_*.py (v. TEST_RESULTS).
"""
import asyncio
import html as _html
from datetime import timedelta
from unittest.mock import patch

import pytest

import routers.case_dna as cd
import routers.email_notif as en
from routers.email_notif import _danas_beograd
from shared.rok_potvrda import potvrdjeni_ids
from tests import test_b10_reminder_claim as b10
from tests.test_ba01_rok_identitet import Model, _osvezi, _predmet, _prikaci, _rok, _rokovi, _stanja
from tests.test_n7_azuriranje_predmeta import _sr, lanac  # noqa: F401 — fixture
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401 — fixture
from tests.test_s2_smtp_transport_lokalno import LokalniSmtp, _sertifikat

DANAS = _danas_beograd()
A_ROK, B_ROK, OBICAN = DANAS + timedelta(days=1), DANAS + timedelta(days=3), DANAS - timedelta(days=5)
DOK1 = ["OSNOVNI SUD U BEOGRADU", "Posl. br. P 7714/2026 (SINTETICKI)", "PRESUDA", f"Presuda je doneta {_sr(OBICAN)} godine.",
        f"Rok za izjavljivanje zalbe istice {_sr(A_ROK)} godine.",
        f"Rok za dobrovoljno ispunjenje istice {_sr(B_ROK)} godine."]
DOK2 = ["OBAVESTENJE O TAKSI (SINTETICKI)", f"Rok za uplatu sudske takse istice {_sr(A_ROK)} godine."]


def _profil(b, uid, email):
    b.tabele.setdefault("korisnik_email_notif", []).append({"user_id": uid, "aktivan": True, "dan_1": True, "dan_3": True, "dan_7": True})
    b.tabele.setdefault("profiles", []).append({"id": uid, "email": email})
    b.tabele.setdefault("email_notif_log", [])


def _posalji(b, server):
    from shared.rate import limiter
    limiter.reset()
    with patch.object(en, "_get_supa", return_value=b), patch.object(en, "_SMTP_HOST", "127.0.0.1"), \
         patch.object(en, "_SMTP_PORT", server.port), patch.object(en, "_SMTP_USER", "test-korisnik"), \
         patch.object(en, "_SMTP_PASS", "test-lozinka"), patch.object(en, "_FROM_ADDR", "podsetnik@example.invalid"):
        return asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))


@pytest.fixture
def smtp(tmp_path):
    s = LokalniSmtp(*_sertifikat(tmp_path))
    yield s
    s.zatvori()


def _poruke(server):
    """Primalac i HTML telo (dekodirano iz MIME-a, kako ga klijent pošte vidi)."""
    import email
    out = []
    for p in server.primljeno:
        m = email.message_from_bytes(p["telo"]) if isinstance(p["telo"], bytes) else email.message_from_string(p["telo"])
        deo = next(d for d in m.walk() if d.get_content_type() == "text/html")
        out.append((",".join(p["za"]), _html.unescape(deo.get_payload(decode=True).decode("utf-8"))))
    return out


def test_zivotni_ciklus_obaveze_do_podsetnika(lanac, monkeypatch, smtp):
    k, b = lanac
    model = Model([])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    _profil(b, "uid-A", "advokat-a@example.invalid")
    _profil(b, "uid-B", "advokat-b@example.invalid")
    pid = _predmet(k)
    _prikaci(k, b, pid, DOK1, "01 Presuda digitalna.pdf")

    # 1–2: dva kandidata, oba nepotvrđena; običan datum nije rok; nepotvrđeno nikad ne šalje
    r = {h["datum_iso"]: h for h in _rokovi(b, pid)}
    assert sorted(r) == [A_ROK.isoformat(), B_ROK.isoformat()], r
    ra, rb = r[A_ROK.isoformat()], r[B_ROK.isoformat()]
    assert _stanja(k, pid) == {ra["id"]: "UNCONFIRMED", rb["id"]: "UNCONFIRMED"}
    nula = _posalji(b, smtp)
    assert nula["poslato"] == 0 and smtp.primljeno == [], nula

    # 3–4: potvrda A, odbijanje B (dupli klik ne menja ništa)
    for _ in range(2):
        assert k.post(f"/api/rokovi/{ra['id']}/potvrdi", json={}, headers=A).status_code == 200
    assert k.post(f"/api/rokovi/{rb['id']}/odbij", json={"napomena": "nije rok klijenta"}, headers=A).status_code == 200
    assert k.post(f"/api/rokovi/{rb['id']}/potvrdi", json={}, headers=B).status_code == 404
    assert _stanja(k, pid) == {ra["id"]: "CONFIRMED", rb["id"]: "REJECTED"}

    # 5–6: A je izvršiva obaveza (kalendar), B nikad
    assert potvrdjeni_ids([ra["id"], rb["id"]]) == {ra["id"]}
    kal = k.get("/api/kalendar/pregled", headers=A)
    assert kal.status_code == 200 and A_ROK.isoformat() in kal.text

    # 9: nezavisna druga obaveza ISTOG datuma iz drugog dokumenta — zaseban kandidat, ne nasleđuje odluku A
    _prikaci(k, b, pid, DOK2, "02 Taksa.pdf")
    [rc] = [h for h in _rokovi(b, pid) if h["dokument_naziv"] == "02 Taksa.pdf"]
    assert rc["datum_iso"] == A_ROK.isoformat() and _stanja(k, pid)[rc["id"]] == "UNCONFIRMED"
    assert k.post(f"/api/rokovi/{rc['id']}/potvrdi", json={}, headers=A).status_code == 200

    # 7: dispečer → JEDAN email za A (A i C istog dana zajedno), B nikad, drugi korisnik ništa
    rez = _posalji(b, smtp)
    assert rez["poslato"] == 1 and rez["greske"] == 0 and rez["neisporuceno"] == 0, rez
    [(primalac, telo)] = _poruke(smtp)
    assert "advokat-a@example.invalid" in primalac
    import re as _re
    stavke = _re.findall(r"(Rok iz dokumenta \([^)]+\))\s*</td>\s*<td[^>]*>\s*(\d{4}-\d{2}-\d{2})", telo)
    if not stavke:   # oblik tabele nije bitan za tvrdnju — tekst bez oznaka
        tekst = " ".join(_re.sub(r"<[^>]+>", " ", telo).split())
        stavke = _re.findall(r"(Rok iz dokumenta \([^)]+\)) (\d{4}-\d{2}-\d{2})", tekst)
    assert sorted(stavke) == sorted([("Rok iz dokumenta (presuda)", A_ROK.isoformat()), ("Rok iz dokumenta (dokument)", A_ROK.isoformat())]), stavke
    assert B_ROK.isoformat() not in telo
    rez_dog = {str(x["dogadjaj_id"]) for x in b.tabele.get("email_podsetnik_dogadjaj", [])}
    assert {ra["id"], rc["id"]} <= rez_dog and rb["id"] not in rez_dog, rez_dog

    # 8: ponovno pokretanje i ponovna obrada (Genome osvežavanje + ista obrada dokumenta) → nijedna nova obaveza ni slanje
    model.izlaz = [_rok("Žalbeni rok", A_ROK.isoformat(), "x"), _rok("Ispunjenje", B_ROK.isoformat(), "y")]
    _osvezi(pid)
    _prikaci(k, b, pid, DOK1, "01 Presuda digitalna.pdf")
    assert len(_rokovi(b, pid)) == 3
    assert _stanja(k, pid) == {ra["id"]: "CONFIRMED", rb["id"]: "REJECTED", rc["id"]: "CONFIRMED"}
    ponovo = _posalji(b, smtp)
    assert ponovo["poslato"] == 0 and len(smtp.primljeno) == 1, ponovo

    # 10: drugi korisnik sa istim dokumentom — svoje, nepotvrđene obaveze; ne dobija ništa, ne vidi A
    pb = _predmet(k, h=B, ime="Bojana")
    _prikaci(k, b, pb, DOK1, "01 Presuda digitalna.pdf", h=B)
    assert {h["user_id"] for h in _rokovi(b, pb)} == {"uid-B"} and len(_rokovi(b, pb)) == 2
    assert _posalji(b, smtp)["poslato"] == 0 and len(smtp.primljeno) == 1
    assert k.get(f"/api/rokovi/kandidati?predmet_id={pid}", headers=B).json()["rokovi"] == []
