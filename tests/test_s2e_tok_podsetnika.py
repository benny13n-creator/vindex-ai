# -*- coding: utf-8 -*-
"""S2-E / Gate F — Bojanov tok podsetnika od kraja do kraja kroz STVARNE rute (prijem, ročišta, odluka o roku),
stvaran lanac odluka u bazi u memoriji, stvarnu `posalji_podsetnike` i hitnu proveru posle radnje (pozadinski zadatak
rute), sa STVARNIM `_smtp_send` prema lokalnom SMTP serveru na 127.0.0.1. Bez pravih podataka i bez pravog emaila
(primaoci `@example.invalid`). Datumi su relativni od današnjeg; „sutra“ se simulira samo za dnevno slanje."""
import email as _email
import html as _html
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tests.test_n3_rocista import _predmet
from tests.test_n4_ispravka_roka import _predlog, _stanje, lanac  # noqa: F401
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401
from tests.test_s2_smtp_transport_lokalno import LokalniSmtp, _sertifikat


def _d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def _profil(b):
    b.tabele.setdefault("korisnik_email_notif", []).append(
        {"user_id": "uid-A", "aktivan": True, "dan_1": True, "dan_3": True, "dan_7": False})
    b.tabele.setdefault("profiles", []).append({"id": "uid-A", "email": "advokat@example.invalid"})
    for t in ("email_notif_log", "email_podsetnik_dogadjaj", "email_podsetnik_pokretanje"):
        b.tabele.setdefault(t, [])


@pytest.fixture
def smtp(tmp_path, monkeypatch):
    import routers.email_notif as en
    s = LokalniSmtp(*_sertifikat(tmp_path))
    monkeypatch.setattr(en, "_SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(en, "_SMTP_PORT", s.port)
    monkeypatch.setattr(en, "_SMTP_USER", "test-korisnik")
    monkeypatch.setattr(en, "_SMTP_PASS", "test-lozinka")
    monkeypatch.setattr(en, "_FROM_ADDR", "podsetnik@example.invalid")
    yield s
    s.zatvori()


def _poruke(s, od=0):
    out = []
    for m in s.primljeno[od:]:
        p = _email.message_from_bytes(m["telo"])
        h = next(d for d in p.walk() if d.get_content_type() == "text/html").get_payload(decode=True).decode()
        out.append((m["za"], str(_email.header.make_header(_email.header.decode_header(p["Subject"]))), _html.unescape(h)))
    return out


def _cron(pomak_dana=0):
    import asyncio
    import routers.email_notif as en
    from shared.rate import limiter
    from tests import test_b10_reminder_claim as b10
    limiter.reset()
    sada = datetime.now(timezone.utc) + timedelta(days=pomak_dana)
    with patch.object(en, "_sada", lambda: sada):
        return asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))


def _istorija(b):
    return sorted((r["tip"], r["svrha"], r["stanje"], r["datum_dogadjaja"]) for r in b.tabele["email_podsetnik_dogadjaj"])


def test_s2e_integrisani_tok_redovno_kasno_pad_oporavak_otkazivanje(lanac, smtp):
    k, b = lanac
    p1 = _predmet(k, A, "Predmet jedan")
    p2 = _predmet(k, A, "Predmet dva")
    pb = _predmet(k, B, "Predmet korisnika B")
    _profil(b)

    # Ročište za sutra pre dnevnog slanja: hitna provera ga NE šalje (dnevno slanje tek dolazi i obuhvatiće ga).
    assert k.post("/api/rocista", json={"predmet_id": p1, "sud": "Osnovni sud u Beogradu", "datum": _d(1),
                                        "vreme": "10:00"}, headers=A).status_code == 200
    assert smtp.primljeno == []
    # AI predlog roka za sutra: nepotvrđen → ništa. Korisnik B ne može ni da ga potvrdi ni da zakaže u A-ovom predmetu.
    _predlog(b, rid="rok-ai", uid="uid-A", pid=p1, dana=1)
    assert k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=B).status_code in (403, 404)
    assert k.post("/api/rocista", json={"predmet_id": p1, "sud": "Upad", "datum": _d(1)}, headers=B).status_code in (403, 404)
    assert k.post("/api/rocista", json={"predmet_id": pb, "sud": "TUDJI SUD", "datum": _d(1)}, headers=B).status_code == 200

    # 1) Redovno dnevno slanje: prag 1 — samo zakazano ročište; predlog i tuđe ročište ne ulaze.
    rez = _cron()
    assert rez["poslato"] == 1 and rez["greske"] == 0, rez
    (za, naslov, telo), = _poruke(smtp)
    assert za == ["advokat@example.invalid"] and "ročište" in naslov
    assert "Osnovni sud u Beogradu" in telo and "Rok za tužbu" not in telo and "TUDJI" not in telo

    # 2) Advokat potvrđuje rok POSLE dnevnog slanja (isti predmet, isti datum): hitna provera šalje ODMAH samo rok.
    assert k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=A).status_code == 200
    (za, naslov, telo), = _poruke(smtp, 1)
    assert "Rok za tužbu" in telo and "Osnovni sud" not in telo
    # ponovljena potvrda i ponovljeno dnevno slanje: ništa novo
    assert k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=A).status_code == 200
    assert _cron()["poslato"] == 0 and len(smtp.primljeno) == 2

    # 3) Ročište DANAS, zakazano kasno, vreme još predstoji → dodatni podsetnik odmah. Već počelo → ništa.
    assert k.post("/api/rocista", json={"predmet_id": p2, "sud": "Viši sud u Beogradu", "datum": _d(0),
                                        "vreme": "23:59"}, headers=A).status_code == 200
    (za, naslov, telo), = _poruke(smtp, 2)
    assert naslov == "Vindex AI — Podsetnik: ročište uskoro" and "Viši sud u Beogradu" in telo and "DANAS" in telo
    assert k.post("/api/rocista", json={"predmet_id": p2, "sud": "Već počelo", "datum": _d(0),
                                        "vreme": "00:00"}, headers=A).status_code == 200
    assert len(smtp.primljeno) == 3

    # 4) Pad transporta (pogrešna SMTP lozinka) pri kasnom ročištu: radnja uspeva, poruka nije predata (neuspeh);
    #    posle ispravke dnevno slanje ga isporučuje JEDNOM.
    smtp.auth_pada = True
    assert k.post("/api/rocista", json={"predmet_id": p2, "sud": "Prekršajni sud", "datum": _d(0),
                                        "vreme": "23:58"}, headers=A).status_code == 200
    assert len(smtp.primljeno) == 3
    smtp.auth_pada = False
    rez = _cron()
    assert rez["poslato"] == 1 and rez["kasni"] == 1, rez
    (za, naslov, telo), = _poruke(smtp, 3)
    assert "Prekršajni sud" in telo and "Viši sud" not in telo
    assert _cron()["poslato"] == 0

    # 5) Otkazivanje i pomeranje pre sutrašnjeg slanja.
    h4 = k.post("/api/rocista", json={"predmet_id": p1, "sud": "Otkazano ročište", "datum": _d(2)}, headers=A).json()["rociste"]
    h5 = k.post("/api/rocista", json={"predmet_id": p1, "sud": "Pomereno ročište", "datum": _d(2)}, headers=A).json()["rociste"]
    assert k.patch(f"/api/rocista/{h4['id']}", json={"status": "otkazano"}, headers=A).status_code == 200
    assert k.patch(f"/api/rocista/{h5['id']}", json={"datum": _d(5)}, headers=A).status_code == 200
    assert len(smtp.primljeno) == 4
    rez = _cron(pomak_dana=1)                                                 # sutra: _d(2) je prag 1, _d(5) za 4 dana
    assert rez["poslato"] == 0 and len(smtp.primljeno) == 4, rez              # otkazano i pomereno: ništa
    rez = _cron(pomak_dana=2)                                                 # prekosutra: _d(5) je prag 3
    (za, naslov, telo), = _poruke(smtp, 4)
    assert "Pomereno ročište" in telo and _d(5) in telo and "Otkazano" not in telo and "Za 3 dana" in naslov, rez

    # 6) Istorija: samo A, svaka stavka jednom, stanja istinita.
    assert {r["user_id"] for r in b.tabele["email_podsetnik_dogadjaj"]} == {"uid-A"}
    ist = [x for x in _istorija(b) if x[3] in (_d(0), _d(1))]
    assert ist == sorted([("rociste", "prag_1", "poslato", _d(1)), ("rok", "prag_1", "poslato", _d(1)),
                          ("rociste", "kasni", "poslato", _d(0)), ("rociste", "kasni", "poslato", _d(0))]), ist
    assert max(r["pokusaja"] for r in b.tabele["email_podsetnik_dogadjaj"]) == 2   # pad + uspešno ponavljanje
    assert all(m["za"] == ["advokat@example.invalid"] for m in smtp.primljeno)
    assert _stanje(k, "rok-ai") == "CONFIRMED"


def test_s2e_ispravka_posle_slanja_salje_ispravljen_datum_a_ne_predlog(lanac, smtp):
    k, b = lanac
    p1 = _predmet(k, A, "Predmet jedan")
    _profil(b)
    _predlog(b, rid="rok-ai", uid="uid-A", pid=p1, dana=1)
    assert _cron()["poslato"] == 0                                            # predlog: ništa
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(0)}, headers=A)   # tačan rok je DANAS
    assert r.status_code == 200, r.text
    (za, naslov, telo), = _poruke(smtp)
    assert "ističe DANAS" in telo and _d(0) in telo and _d(1) not in telo
    assert _stanje(k, "rok-ai") == "REJECTED" and _stanje(k, r.json()["rok_id"]) == "CONFIRMED"
    assert _cron()["poslato"] == 0


def test_s2e_iskljuceni_podsetnici_ni_hitna_provera_ne_salje(lanac, smtp):
    k, b = lanac
    p1 = _predmet(k, A, "Predmet jedan")
    _profil(b)
    b.tabele["korisnik_email_notif"][0]["aktivan"] = False
    assert k.post("/api/rocista", json={"predmet_id": p1, "sud": "Osnovni sud", "datum": _d(0), "vreme": "23:59"},
                  headers=A).status_code == 200
    assert smtp.primljeno == [] and b.tabele["email_podsetnik_dogadjaj"] == []
