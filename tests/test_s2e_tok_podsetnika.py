# -*- coding: utf-8 -*-
"""S2-E — Bojanov tok podsetnika od kraja do kraja kroz STVARNE rute (prijem, ročišta, odluka o roku) i stvaran
lanac odluka u bazi u memoriji; slanje je stvarna `posalji_podsetnike` sa lažnim SMTP-om. Bez pravih podataka i
bez pravog emaila. Dani nisu simulirani — svi datumi su relativni od današnjeg."""
import html as _html
from datetime import date, timedelta

from tests.test_n3_rocista import _predmet
from tests.test_n4_ispravka_roka import _predlog, _stanje, lanac  # noqa: F401
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401
from tests.test_v3_podsetnici_identitet import _cron


def _d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def _profil(b):
    b.tabele.setdefault("korisnik_email_notif", []).append(
        {"user_id": "uid-A", "aktivan": True, "dan_1": True, "dan_3": True, "dan_7": False})
    b.tabele.setdefault("profiles", []).append({"id": "uid-A", "email": "advokat@example.invalid"})
    b.tabele.setdefault("email_notif_log", [])


def test_s2e_tok_rociste_predlog_ispravka_slanje_otkazivanje_i_tudji_korisnik(lanac):
    k, b = lanac
    p1 = _predmet(k, A, "Predmet jedan")
    p2 = _predmet(k, A, "Predmet dva")
    pb = _predmet(k, B, "Predmet korisnika B")
    _profil(b)

    # 1–4: ročišta (advokat ih unosi — nisu AI predlog); B ne može da dira A-ovo ročište
    h1 = k.post("/api/rocista", json={"predmet_id": p1, "sud": "Osnovni sud u Beogradu", "datum": _d(1), "vreme": "10:00"}, headers=A)
    assert h1.status_code == 200, h1.text
    h2 = k.post("/api/rocista", json={"predmet_id": p2, "sud": "Viši sud u Beogradu", "datum": _d(3)}, headers=A).json()["rociste"]
    assert k.post("/api/rocista", json={"predmet_id": pb, "sud": "TUDJI SUD", "datum": _d(1)}, headers=B).status_code == 200
    assert k.post("/api/rocista", json={"predmet_id": p1, "sud": "Upad", "datum": _d(1)}, headers=B).status_code in (403, 404)
    assert k.patch(f"/api/rocista/{h2['id']}", json={"status": "otkazano"}, headers=B).status_code in (403, 404)

    # 5–6: AI predlog roka (sutra — isti datum i predmet kao ročište, pogrešan datum) ne aktivira ništa
    _predlog(b, rid="rok-ai", uid="uid-A", pid=p1, dana=1)
    assert k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=B).status_code in (403, 404)
    assert k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(3)}, headers=B).status_code in (403, 404)

    # 14 (pre slanja): otkazano ročište u drugom predmetu
    assert k.patch(f"/api/rocista/{h2['id']}", json={"status": "otkazano"}, headers=A).status_code == 200

    # 10: slanje — samo zakazano ročište za sutra; nema predloga, nema otkazanog, nema tuđeg
    rez, poslati = _cron(b)
    assert rez["poslato"] == 1 and len(poslati) == 1, rez
    to, subj, telo = poslati[0][0], poslati[0][1], _html.unescape(poslati[0][2])
    assert to == "advokat@example.invalid" and "ročište" in subj
    assert "Osnovni sud u Beogradu" in telo and "Rok za tužbu" not in telo and "Viši sud" not in telo and "TUDJI" not in telo

    # 7–9: advokat ispravlja datum predloga (za 3 dana) → predlog REJECTED, nov rok CONFIRMED
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(3)}, headers=A)
    assert r.status_code == 200, r.text
    nov = r.json()["rok_id"]
    assert _stanje(k, "rok-ai") == "REJECTED" and _stanje(k, nov) == "CONFIRMED"

    # 12–13: drugi događaj posle prvog slanja istog dana, ali na DRUGOM pragu (3) → nov ključ, šalje se odmah
    rez, poslati = _cron(b)
    assert rez["poslato"] == 1 and len(poslati) == 1, rez
    telo = _html.unescape(poslati[0][2])
    assert "Rok za tužbu" in telo and _d(3) in telo and _d(1) not in telo and "Viši sud" not in telo

    # 11: deduplikacija — ponovljeno slanje ništa ne šalje
    rez, poslati = _cron(b)
    assert poslati == [] and rez["poslato"] == 0
    assert sorted((r["predmet_id"], r["datum_roka"], r["dana_pre"]) for r in b.tabele["email_notif_log"]) == \
        sorted([(p1, _d(1), 1), (p1, _d(3), 3)])
    assert {r["user_id"] for r in b.tabele["email_notif_log"]} == {"uid-A"}

    # 15: V3-L1 — ročište istog predmeta i datuma upisano posle slanja istog dana NE dopunjuje podsetnik (ključ bez
    # identiteta događaja; ograničenje, ne prolaz). Ulazi u prag 1 tog datuma (nov ključ).
    assert k.post("/api/rocista", json={"predmet_id": p1, "sud": "Prekršajni sud", "datum": _d(3)}, headers=A).status_code == 200
    assert _cron(b)[1] == []


def test_s2e_potvrda_istog_predmeta_istog_praga_posle_slanja_ne_ulazi_isti_dan(lanac):
    """Izmereno V3-L1 kroz stvarne rute: ročište sutra poslato, AI rok za sutra potvrđen posle — isti dan ništa;
    prag 1 je poslednji, pa ovaj rok email NIKAD ne dobija (G). Na „Danas“ ostaje vidljiv."""
    k, b = lanac
    p1 = _predmet(k, A, "Predmet jedan")
    _profil(b)
    assert k.post("/api/rocista", json={"predmet_id": p1, "sud": "Osnovni sud u Beogradu", "datum": _d(1)}, headers=A).status_code == 200
    _predlog(b, rid="rok-ai", uid="uid-A", pid=p1, dana=1)
    prvi = _cron(b)[1]
    assert len(prvi) == 1 and "Rok za tužbu" not in _html.unescape(prvi[0][2])
    assert k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=A).status_code == 200
    assert _cron(b)[1] == []
