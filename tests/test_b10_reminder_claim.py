# -*- coding: utf-8 -*-
"""B10 — POUZDANOST PODSETNIKA: trajni claim PRE slanja.

ŠTA JE BIO PROBLEM
==================
`posalji_podsetnike` je slao email pa TEK ONDA upisivao u `email_notif_log`, i to
u `except Exception: pass`. Dva prozora duplikata:

  (a) slanje uspe, upis padne  → sledeći cron šalje PONOVO;
  (b) dva paralelna cron poziva prođu istu `dup` proveru → OBA pošalju.

ŠTA JE SADA
===========
Upis je pomeren PRE slanja i koristi POSTOJEĆI
`UNIQUE(user_id, predmet_id, datum_roka, dana_pre)` iz migracije 021 kao trajnu
rezervaciju. Bez nove kolone i bez nove tabele.

GRANICA KOJA SE NE PRELAZI
==========================
Ovo je **at-most-once pokušaj slanja**, NE exactly-once isporuka. Baza i SMTP ne
mogu biti u istoj transakciji. Ako slanje padne posle rezervacije, automatskog
ponavljanja NEMA — ono bi vratilo tačno prozor koji se zatvara. Takav ishod je
`neisporuceno` i traži ručnu proveru.

NIJEDAN TEST OVDE NE ŠALJE PRAVI EMAIL — `_smtp_send` je uvek zamenjen.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

UID = "u-1"
PID = "p-1"
MAIL = "test@example.invalid"


class _Upit:
    """Minimalni PostgREST lanac nad listom redova."""

    def __init__(self, redovi, tabela, baza):
        self._r, self._t, self._b = list(redovi), tabela, baza

    def select(self, *a, **k):
        return self

    def eq(self, kol, v):
        return _Upit([r for r in self._r if r.get(kol) == v], self._t, self._b)

    def in_(self, kol, vs):
        return _Upit([r for r in self._r if r.get(kol) in set(vs)], self._t, self._b)

    def limit(self, n):
        return _Upit(self._r[:n], self._t, self._b)

    @property
    def not_(self):
        return _Ne(self._r, self._t, self._b)

    def insert(self, rows):
        self._b.upisi(self._t, rows if isinstance(rows, list) else [rows])
        return self

    def execute(self):
        class R:
            pass
        r = R()
        r.data = self._r
        return r


class _Ne:
    def __init__(self, redovi, tabela, baza):
        self._r, self._t, self._b = redovi, tabela, baza

    def in_(self, kol, vs):
        return _Upit([r for r in self._r if r.get(kol) not in set(vs)], self._t, self._b)


class FakeBaza:
    """Simulira SAMO ono što je bitno: UNIQUE nad email_notif_log."""

    KLJUC = ("user_id", "predmet_id", "datum_roka", "dana_pre")

    def __init__(self, rokovi, aktivan=True, dan_1=True, arhiviran=False):
        self.log: list[dict] = []
        self.insert_puca = False           # simulira pad upisa (ne UNIQUE)
        # Modeluje STVARNU trku: oba procesa procitaju log PRE nego sto je
        # ijedan upisao, pa oba prodju `dup` provjeru. Tek UNIQUE ih razdvaja.
        # Bez ovoga drugi SEKVENCIJALNI prolaz zaustavi `dup` i rezervacija se
        # nikad ne testira -- sto je i otkriveno kad je mutacija M2 prezivela.
        self.sakrij_log_od_select = False
        self.tabele = {
            "korisnik_email_notif": [{"user_id": UID, "aktivan": aktivan,
                                      "dan_1": dan_1, "dan_3": False, "dan_7": False}],
            "profiles": [{"id": UID, "email": MAIL}],
            "predmeti": [{"id": PID, "user_id": UID,
                          "status": "arhiviran" if arhiviran else "aktivan"}],
            "predmet_hronologija": rokovi,
            "email_notif_log": self.log,
        }

    def upisi(self, tabela, rows):
        if tabela != "email_notif_log":
            self.tabele.setdefault(tabela, []).extend(rows)
            return
        if self.insert_puca:
            raise RuntimeError("connection reset by peer")
        postojeci = {tuple(str(r.get(k)) for k in self.KLJUC) for r in self.log}
        for row in rows:
            if tuple(str(row.get(k)) for k in self.KLJUC) in postojeci:
                raise RuntimeError(
                    '{"code":"23505","message":"duplicate key value violates '
                    'unique constraint \\"email_notif_log_user_id_predmet_id_key\\""}')
        self.log.extend(rows)

    def table(self, ime):
        redovi = self.tabele.get(ime, [])
        if ime == "email_notif_log" and self.sakrij_log_od_select:
            redovi = []          # `dup` provera vidi prazno; UNIQUE i dalje vazi
        return _Upit(redovi, ime, self)


def _rok(datum_iso):
    # FAZA 6.2: upit sada dovlaci i `id`/`akter` jer ih trazi kapija
    # `shared/rokovi.py::sme_pokrenuti_obavezu`. Fixture ih dobija da bi ostao
    # VERAN stvarnom redu; `akter` je ljudski, jer B10 meri rezervaciju pre
    # slanja, a ne granicu AI opazanja (to meri test_faza62_*).
    return {"id": f"rok-{datum_iso}", "akter": "Advokat Marko", "izvor": "HUMAN_DIRECT",
            "dogadjaj": "Rok za žalbu", "datum_iso": datum_iso,
            "predmet_id": PID, "user_id": UID, "vaznost": "kritičan"}


def _sutra():
    from datetime import date, timedelta
    return (date.today() + timedelta(days=1)).isoformat()


def _request():
    """Stvarni starlette Request — rate limiter (slowapi) odbija MagicMock."""
    from starlette.requests import Request
    return Request({
        "type": "http", "method": "POST", "path": "/email-notif/send-reminders",
        "headers": [], "query_string": b"", "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80), "scheme": "http",
    })


def _pokreni(baza, smtp_puca=False):
    """Poziva stvarni endpoint; SMTP je UVEK zamenjen."""
    import routers.email_notif as en

    poslati: list = []

    def _fake_smtp(to_addr, subject, html):
        if smtp_puca:
            raise RuntimeError("SMTP 421 service unavailable")
        poslati.append((to_addr, subject))

    with patch.object(en, "_get_supa", return_value=baza), \
         patch.object(en, "_smtp_send", _fake_smtp), \
         patch.object(en, "_email_html", lambda *a, **k: "<html/>"):
        rez = asyncio.run(en.posalji_podsetnike(_request(), user={"user_id": "cron", "email": ""}))
    return rez, poslati


# ═══════════════════════════════════════════════════════════════════════════

def test_r1_normalno_slanje_jedan_zapis_jedan_send():
    b = FakeBaza([_rok(_sutra())])
    rez, poslati = _pokreni(b)
    assert rez["poslato"] == 1, rez
    assert len(poslati) == 1
    assert len(b.log) == 1, "rezervacija nije upisana"


def test_r2_dva_paralelna_crona_daju_najvise_jedan_send():
    """Drugi prolaz nad ISTIM stanjem loga simulira drugi proces koji je prošao
    `dup` proveru pre nego što je prvi upisao."""
    b = FakeBaza([_rok(_sutra())])
    rez1, poslati1 = _pokreni(b)
    # Drugi proces je `dup` provjeru obavio PRE nego sto je prvi upisao —
    # zato mu se log sakriva od SELECT-a. UNIQUE ostaje na snazi.
    b.sakrij_log_od_select = True
    rez2, poslati2 = _pokreni(b)
    assert len(poslati1) + len(poslati2) == 1, "isti podsetnik poslat dvaput"
    assert len(b.log) == 1, "duplirana rezervacija"
    # „Neko drugi je već rezervisao" NIJE kvar — mora se razlikovati od greške,
    # inače operativni izveštaj laže o zdravlju sistema. Bez ove tvrdnje
    # mutacija koja ignoriše 23505 preživljava: i tada se ne šalje, ali se
    # normalna paralelna trka prijavljuje kao greška.
    assert rez2["preskoceno"] == 1, f"UNIQUE sudar nije prepoznat kao rezervacija: {rez2}"
    assert rez2["greske"] == 0, f"paralelna trka prijavljena kao greška: {rez2}"


def test_r3_smtp_pad_ne_daje_lazan_sent_status():
    b = FakeBaza([_rok(_sutra())])
    rez, poslati = _pokreni(b, smtp_puca=True)
    assert rez["poslato"] == 0, "pad SMTP-a prijavljen kao poslato"
    assert poslati == []
    assert rez["neisporuceno"] == 1, rez


def test_r4_neisporuceno_se_ne_ponavlja_automatski():
    """Rezervacija ostaje → sledeći cron NE pokušava ponovo. To je namerno:
    automatsko ponavljanje bi vratilo prozor duplikata."""
    b = FakeBaza([_rok(_sutra())])
    _pokreni(b, smtp_puca=True)
    assert len(b.log) == 1, "rezervacija je obrisana — ponovno slanje bi bilo moguće"
    rez2, poslati2 = _pokreni(b)
    assert poslati2 == [], "posle neisporučenog automatski je pokušano ponovo"
    assert rez2["poslato"] == 0


def test_r5_ponovni_cron_posle_uspeha_ne_salje_ponovo():
    b = FakeBaza([_rok(_sutra())])
    _pokreni(b)
    rez2, poslati2 = _pokreni(b)
    assert poslati2 == []
    assert rez2["poslato"] == 0
    assert len(b.log) == 1


def test_r6_iskljucena_preferenca_ne_salje():
    b = FakeBaza([_rok(_sutra())], dan_1=False)
    rez, poslati = _pokreni(b)
    assert poslati == []
    assert len(b.log) == 0, "rezervisano iako korisnik ne želi podsetnik"


def test_r6b_neaktivan_profil_ne_salje():
    b = FakeBaza([_rok(_sutra())], aktivan=False)
    rez, poslati = _pokreni(b)
    assert poslati == []


def test_r7_arhiviran_predmet_ne_salje():
    b = FakeBaza([_rok(_sutra())], arhiviran=True)
    rez, poslati = _pokreni(b)
    assert poslati == [], "podsetnik za arhiviran predmet"
    assert len(b.log) == 0


def test_r8_pad_rezervacije_ne_salje_i_ne_guta_gresku():
    """Fail-closed: bolje neposlato nego poslato bez evidencije."""
    b = FakeBaza([_rok(_sutra())])
    b.insert_puca = True
    rez, poslati = _pokreni(b)
    assert poslati == [], "poslato iako rezervacija nije uspela"
    assert rez["greske"] == 1, "greška je progutana"
    assert rez["poslato"] == 0


def test_rezervacija_ide_PRE_slanja():
    """Redosled je ceo invariant — zaključan i nad izvorom."""
    put = os.path.join(os.path.dirname(__file__), "..", "routers", "email_notif.py")
    with open(put, encoding="utf-8") as fh:
        s = fh.read()
    i = s.index("async def posalji_podsetnike")
    telo = s[i:s.index("# ─── Weekly Digest", i)]
    assert telo.index("claim_rows") < telo.index("_smtp_send(to_addr"), \
        "upis u log je opet POSLE slanja — prozor duplikata je vraćen"


def test_upis_u_log_nije_u_except_pass():
    put = os.path.join(os.path.dirname(__file__), "..", "routers", "email_notif.py")
    with open(put, encoding="utf-8") as fh:
        s = fh.read()
    i = s.index("async def posalji_podsetnike")
    telo = s[i:s.index("# ─── Weekly Digest", i)]
    assert "except Exception:\n                            pass" not in telo, \
        "pad upisa u log se opet tiho guta"
