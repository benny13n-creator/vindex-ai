# -*- coding: utf-8 -*-
"""P0 (Settings Master Sprint) — B10: interval podsetnika je ispravan u TEST emailu i u zakazivanju.

PROBLEM (osnivač, 2026-10-26): testni email je za 7, 3 i 1 dan uvek govorio „Za 3 dana“ —
`POST /email-notif/test` je zvao `_email_html(..., dana_pre=3)` hardkodovano.

UGOVOR POSLE ISPRAVKE
  * bez `interval` → samo provera dostave; poruka ne tvrdi nijedan interval ni rok;
  * `interval` ∈ {1, 3, 7} (strogo: ne bool, ne "3", ne 3.0) → TEST primer tog intervala: isti naslov i
    šablon kao zakazani podsetnik, oznaka TEST, izmišljen rok na dan Srbija-danas + interval;
  * interval mora biti uključen i sačuvan u profilu VLASNIKA; ništa iz tela ne bira korisnika;
  * zakazivanje (`posalji_podsetnike`) bira tačno dan_N za rok na danas + N, bez prelivanja.

NIJEDAN TEST NE ŠALJE PRAVI EMAIL — `_smtp_send` je uvek zamenjen.
"""
import asyncio
import re
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tests import test_b10_reminder_claim as b10
from tests import test_tenfronts_m10_primalac as m10

INTERVALI = (1, 3, 7)


@pytest.fixture(autouse=True)
def _potvrdjeno(monkeypatch):
    import routers.email_notif as en
    monkeypatch.setattr(en, "_potvrdjeni_ids", lambda ids: {str(i) for i in ids if i})


def _notif(**dani):
    return [{"user_id": m10.UID, "aktivan": True, "nedeljni": True,
             "dan_7": False, "dan_3": False, "dan_1": False, **dani}]


def _sat(monkeypatch, utc: datetime):
    """Zamrzava „sada“ za `_danas_beograd` (TEST primer)."""
    import routers.email_notif as en

    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return utc if tz is None else utc.astimezone(tz)
    monkeypatch.setattr(en, "datetime", _DT)


# ═══ TEST email: matrica 7/3/1 ═══════════════════════════════════════════════

SADA = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)      # Beograd 11:00, 26. 10. 2026.
OCEKIVANO = {
    7: ("TEST — Vindex AI — Za 7 dana — kritični rokovi", "Za 7 dana — kritični rokovi", "2026-11-02"),
    3: ("TEST — Vindex AI — Za 3 dana — kritični rokovi", "Za 3 dana — kritični rokovi", "2026-10-29"),
    1: ("TEST — Vindex AI — Sutra ističe rok!", "Sutra ističe rok!", "2026-10-27"),
}


@pytest.mark.parametrize("n", INTERVALI)
def test_test_email_prikazuje_izabrani_interval(monkeypatch, n):
    _sat(monkeypatch, SADA)
    k, poslato = m10._klijent(monkeypatch, m10.PROFILI, notif=_notif(dan_7=True, dan_3=True, dan_1=True))
    r = k.post("/email-notif/test", json={"interval": n})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "poslato_na": m10.PROFIL, "interval": n}
    (to, subj, html), = poslato
    naslov, zaglavlje, datum = OCEKIVANO[n]
    assert to == m10.PROFIL and subj == naslov
    assert zaglavlje in html and datum in html
    assert "TEST — primer obaveštenja" in html and "nemaju pravno dejstvo" in html
    for drugi in INTERVALI:
        if drugi != n:
            assert OCEKIVANO[drugi][1] not in html and OCEKIVANO[drugi][2] not in html, \
                f"interval {drugi} se prelio u test za {n}"


def test_naslov_testa_je_naslov_zakazanog_podsetnika():
    import routers.email_notif as en
    for n in INTERVALI:
        assert OCEKIVANO[n][0] == "TEST — " + en._naslov_podsetnika(n)


@pytest.mark.parametrize("telo", [None, {}], ids=["bez_tela_V1", "prazno_V2"])
def test_bez_intervala_samo_provera_dostave_bez_tvrdnje_o_intervalu(monkeypatch, telo):
    k, poslato = m10._klijent(monkeypatch, m10.PROFILI)          # bez profila obaveštenja — kao ranije
    r = k.post("/email-notif/test") if telo is None else k.post("/email-notif/test", json=telo)
    assert r.status_code == 200, r.text
    assert r.json()["interval"] is None
    (to, subj, html), = poslato
    assert "TEST" in subj and "provera dostave" in subj
    assert not re.search(r"\b(dana|Sutra|rok!)", subj)
    assert "Za 3 dana" not in html and "Za 7 dana" not in html and "Sutra" not in html


@pytest.mark.parametrize("vrednost", ["3", True, False, 3.0, 2, 0, -1, 30, [3], {"n": 3}])
def test_nedozvoljen_interval_odbijen_bez_slanja(monkeypatch, vrednost):
    k, poslato = m10._klijent(monkeypatch, m10.PROFILI, notif=_notif(dan_7=True, dan_3=True, dan_1=True))
    r = k.post("/email-notif/test", json={"interval": vrednost})
    assert r.status_code == 422 and poslato == []


@pytest.mark.parametrize("n,profil", [
    (7, _notif(dan_3=True)), (3, _notif(dan_1=True, dan_7=True)), (1, _notif(dan_7=True)),
    (7, [{**_notif(dan_7=True)[0], "aktivan": False}]), (3, None),
], ids=["7_iskljucen", "3_iskljucen", "1_iskljucen", "profil_neaktivan", "bez_profila"])
def test_interval_mora_biti_ukljucen_i_sacuvan(monkeypatch, n, profil):
    k, poslato = m10._klijent(monkeypatch, m10.PROFILI, notif=profil)
    r = k.post("/email-notif/test", json={"interval": n})
    assert r.status_code == 409 and poslato == []


def test_telo_ne_bira_korisnika(monkeypatch):
    """`user_id` u telu je odbijen (extra=forbid) — ne ignorisan, ne upotrebljen."""
    k, poslato = m10._klijent(monkeypatch, m10.PROFILI, notif=_notif(dan_7=True))
    r = k.post("/email-notif/test", json={"interval": 7, "user_id": m10.DRUGI})
    assert r.status_code == 422 and poslato == []


def test_tudji_profil_ne_otkljucava_interval(monkeypatch):
    """B ima uključen 7, A nema — A ne može da dobije primer 7 na osnovu B-ovog reda."""
    tudji = [{"user_id": m10.DRUGI, "aktivan": True, "dan_7": True, "dan_3": True, "dan_1": True}]
    k, poslato = m10._klijent(monkeypatch, m10.PROFILI, notif=tudji)
    assert k.post("/email-notif/test", json={"interval": 7}).status_code == 409 and poslato == []


def test_bez_smtp_ni_primer_ni_dostava(monkeypatch):
    k, poslato = m10._klijent(monkeypatch, m10.PROFILI, smtp="", notif=_notif(dan_7=True))
    assert k.post("/email-notif/test", json={"interval": 7}).status_code == 503
    assert k.post("/email-notif/test").status_code == 503 and poslato == []


def test_smtp_greska_nije_uspeh(monkeypatch):
    import routers.email_notif as en
    k, _ = m10._klijent(monkeypatch, m10.PROFILI, notif=_notif(dan_7=True))
    monkeypatch.setattr(en, "_smtp_send", lambda *a: (_ for _ in ()).throw(RuntimeError("421")))
    r = k.post("/email-notif/test", json={"interval": 7})
    assert r.status_code == 502 and "ok" not in r.json()


# ═══ Vremenska zona TEST primera ═════════════════════════════════════════════

@pytest.mark.parametrize("utc,beograd", [
    (datetime(2026, 10, 26, 22, 59, tzinfo=timezone.utc), date(2026, 10, 26)),   # CET 23:59
    (datetime(2026, 10, 26, 23, 30, tzinfo=timezone.utc), date(2026, 10, 27)),   # CET 00:30 sledećeg dana
    (datetime(2026, 7, 15, 21, 59, tzinfo=timezone.utc), date(2026, 7, 15)),     # CEST 23:59
    (datetime(2026, 7, 15, 22, 30, tzinfo=timezone.utc), date(2026, 7, 16)),     # CEST 00:30
    (datetime(2026, 10, 24, 22, 30, tzinfo=timezone.utc), date(2026, 10, 25)),   # pre kraja DST (01:00 UTC)
    (datetime(2026, 3, 28, 23, 30, tzinfo=timezone.utc), date(2026, 3, 29)),     # CET pre početka DST
    (datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc), date(2027, 1, 1)),     # prelazak godine
])
def test_danas_beograd(utc, beograd):
    import routers.email_notif as en
    assert en._danas_beograd(utc) == beograd


def test_danas_beograd_isti_kao_tz_baza_cele_godine():
    zi = pytest.importorskip("zoneinfo")
    try:
        bg = zi.ZoneInfo("Europe/Belgrade")
    except Exception:
        pytest.skip("tz baza nije dostupna")
    import routers.email_notif as en
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    while t.year == 2026:
        assert en._danas_beograd(t) == t.astimezone(bg).date(), t
        t += timedelta(minutes=30)


def test_test_email_posle_ponoci_u_beogradu_koristi_beogradski_dan(monkeypatch):
    """23:30 UTC = 00:30 u Beogradu (27. 10.) — primer za 7 dana mora biti 3. 11, ne 2. 11."""
    _sat(monkeypatch, datetime(2026, 10, 26, 23, 30, tzinfo=timezone.utc))
    k, poslato = m10._klijent(monkeypatch, m10.PROFILI, notif=_notif(dan_7=True))
    assert k.post("/email-notif/test", json={"interval": 7}).status_code == 200
    html = poslato[0][2]
    assert "2026-11-03" in html and "2026-11-02" not in html


# ═══ Zakazivanje: matrica 7/3/1 nad stvarnim endpoint-om i stvarnim šablonom ═

DANAS = date(2026, 10, 26)


def _zamrzni_dan(dan):
    import routers.email_notif as en

    import contextlib
    from tests.test_g2_podsetnici_raspored import u_vreme

    class _D(date):
        @classmethod
        def today(cls):
            return dan
    s = contextlib.ExitStack()
    s.enter_context(patch.object(en, "date", _D))
    s.enter_context(u_vreme(dan))        # S2: dnevno slanje čita `_sada`
    return s


def _baza(dani, danas=DANAS):
    rokovi = [{**b10._rok((danas + timedelta(days=n)).isoformat()), "id": f"rok-{n}", "dogadjaj": f"Rok R{n}"}
              for n in INTERVALI]
    baza = b10.FakeBaza(rokovi)
    baza.tabele["korisnik_email_notif"][0].update({"dan_1": False, "dan_3": False, "dan_7": False, **dani})
    return baza


def _cron(baza, danas=DANAS, smtp_puca=False):
    import routers.email_notif as en
    poslati = []

    def _smtp(to, subj, html):
        if smtp_puca:
            raise RuntimeError("SMTP 421")
        poslati.append((to, subj, html))
    with _zamrzni_dan(danas), patch.object(en, "_SMTP_HOST", "smtp.test.invalid"), \
            patch.object(en, "_get_supa", return_value=baza), patch.object(en, "_smtp_send", _smtp):
        rez = asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))
    return rez, poslati


@pytest.mark.parametrize("n", INTERVALI)
def test_zakazivanje_samo_ukljuceni_interval(n):
    rez, poslati = _cron(_baza({f"dan_{n}": True}))
    kasni = [p for p in poslati if p[1].endswith("uskoro")]
    regularni = [p for p in poslati if not p[1].endswith("uskoro")]
    # S2 (D2): rokovi BLIŽI od jedinog uključenog praga, za koje taj prag nikad nije poslat, dobijaju JEDAN dodatni
    # podsetnik (zaseban email) — redovni šablon praga n i dalje nosi samo svoj rok.
    blizi = [m for m in INTERVALI if m < n]
    assert len(kasni) == (1 if blizi else 0) and rez["poslato"] == 1 + len(kasni), rez
    if blizi:
        assert all(f"Rok R{m}" in kasni[0][2] for m in blizi) and f"Rok R{n}" not in kasni[0][2]
    (to, subj, html), = regularni
    naslov, zaglavlje, datum = OCEKIVANO[n]
    assert subj == naslov.removeprefix("TEST — ") and zaglavlje in html and datum in html
    assert f"Rok R{n}" in html
    for drugi in INTERVALI:
        if drugi != n:
            assert f"Rok R{drugi}" not in html and OCEKIVANO[drugi][2] not in html
    assert "TEST" not in html, "oznaka TEST u stvarnom podsetniku"


def test_zakazivanje_sva_tri_bez_prelivanja_i_bez_duplog_pokusaja():
    baza = _baza({"dan_1": True, "dan_3": True, "dan_7": True})
    rez, poslati = _cron(baza)
    assert rez["poslato"] == 3
    po_naslovu = {s: h for _, s, h in poslati}
    for n in INTERVALI:
        h = po_naslovu[OCEKIVANO[n][0].removeprefix("TEST — ")]
        assert f"Rok R{n}" in h and all(f"Rok R{m}" not in h for m in INTERVALI if m != n)
    assert sorted(r["svrha"] for r in baza.log) == ["prag_1", "prag_3", "prag_7"]
    rez2, poslati2 = _cron(baza)
    assert poslati2 == [] and rez2["poslato"] == 0 and len(baza.log) == 3


def test_zakazivanje_nijedan_interval_nista():
    baza = _baza({})
    rez, poslati = _cron(baza)
    assert poslati == [] and baza.log == [] and rez["poslato"] == 0


@pytest.mark.parametrize("n", INTERVALI)
def test_zakazivanje_nepotvrdjen_rok_ne_salje(monkeypatch, n):
    import routers.email_notif as en
    monkeypatch.setattr(en, "_potvrdjeni_ids", lambda ids: set())
    baza = _baza({f"dan_{n}": True})
    rez, poslati = _cron(baza)
    assert poslati == [] and baza.log == []


@pytest.mark.parametrize("status", ["zatvoren", "arhiviran", "odbijen"])
def test_zakazivanje_neaktivan_predmet_ne_salje(status):
    baza = _baza({"dan_1": True, "dan_3": True, "dan_7": True})
    baza.tabele["predmeti"][0]["status"] = status
    rez, poslati = _cron(baza)
    assert poslati == [] and baza.log == []


def test_zakazivanje_predmet_u_brisanju_ne_salje():
    baza = _baza({"dan_1": True, "dan_3": True, "dan_7": True})
    baza.tabele["predmeti"][0]["brisanje_zapoceto"] = "2026-10-25T08:00:00+00:00"
    rez, poslati = _cron(baza)
    assert poslati == [] and baza.log == []


def test_zakazivanje_neizvestan_smtp_bez_ponavljanja():
    baza = _baza({"dan_7": True})
    rez, poslati = _cron(baza, smtp_puca=True)
    # redovni (R7) + dodatni (R1, R3 — prag 7 im nikad nije poslat): oba ishoda nepoznata, 3 rezervacije
    assert rez["neisporuceno"] == 2 and len(baza.log) == 3 and {r["stanje"] for r in baza.log} == {"nepoznato"}
    rez2, poslati2 = _cron(baza)
    assert poslati2 == [] and rez2["poslato"] == 0


def test_zakazivanje_prelazak_godine():
    danas = date(2026, 12, 28)
    rez, poslati = _cron(_baza({"dan_7": True}, danas), danas)
    regularni = [p for p in poslati if not p[1].endswith("uskoro")]
    assert len(regularni) == 1 and "2027-01-04" in regularni[0][2]


def test_obican_korisnik_ne_pokrece_zakazivanje(monkeypatch):
    """Korisnik A ne može da izazove slanje (ni za sebe ni za B): ruta traži cron ključ ili osnivača."""
    import routers.email_notif as en
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from shared.rate import limiter
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(en, "_CRON_SECRET", "tajna-cron")
    monkeypatch.setattr(en, "_verify_token", lambda t: {"sub": "u-1", "email": "obican@example.invalid"})
    poslato = []
    monkeypatch.setattr(en, "_smtp_send", lambda *a: poslato.append(a))
    app = FastAPI()
    app.include_router(en.router)
    k = TestClient(app, raise_server_exceptions=False)
    assert k.post("/email-notif/send-reminders", headers={"Authorization": "Bearer x"}).status_code == 403
    assert k.post("/email-notif/send-reminders", headers={"X-Cron-Key": "pogresno"}).status_code == 403
    assert poslato == []
