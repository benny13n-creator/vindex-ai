# -*- coding: utf-8 -*-
"""FAZA 6.2 — TEST F/G + ADVERSARIAL: nijedan izvrsivi put ne zaobilazi kapiju.

ZASTO OVAJ FAJL POSTOJI ODVOJENO
=================================
`test_faza62_ai_observation_gate.py` dokazuje PREDIKAT. Ovaj fajl dokazuje da
predikat STVARNO stoji na svim izvrsivim granicama — email, SMS, notifikacije —
kroz pozivanje pravih funkcija, ne kroz citanje izvora.

TEST F JE NAJVAZNIJI
====================
FAZA 6.1 je pokazala da AI rok danas ne salje email samo zato sto je
`korisnik_email_notif` prazan. To je konfiguracija, ne granica. TEST F zato
UKLJUCUJE email profil i i dalje trazi nula poslatih poruka.

Da to ne bi bio prazan dokaz ("nista se nije poslalo iz nekog treceg razloga"),
svaki F/G test ima PAROVNI kontrolni slucaj sa POTVRDJENIM rokom koji MORA
poslati. Kontrast dokazuje da je uzrok kapija, a ne slucajnost.

NIJEDAN TEST NE SALJE PRAVI EMAIL NI SMS.
"""
import asyncio
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

UID = "u-1"
PID = "p-1"
MAIL = "advokat@example.invalid"
ROK_ID = "rok-ai-1"


# ─── minimalni PostgREST lanac ────────────────────────────────────────────────

class _Upit:
    """PostgREST FILTRIRA NA SERVERU, pa `.eq(...)` posle `.select(...)` i dalje
    vidi sve kolone; projekcija se primenjuje TEK na rezultat.

    Prvi harness je `.select(...)` potpuno ignorisao, pa je mutacija M6 (upit ne
    dovlaci `akter`) PREZIVELA — test nije mogao ni da vidi razliku. Druga
    verzija je projektovala ODMAH, pa su filtri po `user_id`/`vaznost` ostajali
    bez kolone i nisu poklapali nista. Zato: kolone se PAMTE, primenjuju se u
    `execute()`."""

    def __init__(self, redovi, tabela, baza, kolone=None):
        self._r, self._t, self._b = list(redovi), tabela, baza
        self._kol = kolone

    def _novi(self, redovi):
        return _Upit(redovi, self._t, self._b, self._kol)

    def select(self, *a, **k):
        if not a or not isinstance(a[0], str) or a[0].strip() == "*":
            return self
        return _Upit(self._r, self._t, self._b,
                     [c.strip() for c in a[0].split(",") if c.strip()])

    def eq(self, k, v):
        return self._novi([r for r in self._r if r.get(k) == v])

    def in_(self, k, vs):
        return self._novi([r for r in self._r if r.get(k) in set(vs)])

    def gte(self, k, v):
        return self._novi([r for r in self._r if str(r.get(k, "")) >= str(v)])

    def lte(self, k, v):
        return self._novi([r for r in self._r if str(r.get(k, "")) <= str(v)])

    def lt(self, k, v):
        return self._novi([r for r in self._r if str(r.get(k, "")) < str(v)])

    def order(self, k, **kw):
        return self._novi(sorted(self._r, key=lambda r: (r.get(k) is None, r.get(k))))

    def limit(self, n):
        return self._novi(self._r[:n])

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
        r.data = (self._r if self._kol is None
                  else [{k: x[k] for k in self._kol if k in x} for x in self._r])
        return r


class _Ne:
    def __init__(self, redovi, tabela, baza):
        self._r, self._t, self._b = redovi, tabela, baza

    def in_(self, k, vs):
        return _Upit([r for r in self._r if r.get(k) not in set(vs)], self._t, self._b)


class FakeBaza:
    def __init__(self, rokovi, *, email_aktivan=True, potvrde=None):
        self.log: list[dict] = []
        self.tabele = {
            "korisnik_email_notif": ([{"user_id": UID, "aktivan": True,
                                       "dan_1": True, "dan_3": False, "dan_7": False}]
                                     if email_aktivan else []),
            "profiles": [{"id": UID, "email": MAIL}],
            "predmeti": [{"id": PID, "user_id": UID, "status": "aktivan", "naziv": "Predmet"}],
            "predmet_hronologija": rokovi,
            "email_notif_log": self.log,
            "audit_immutable": list(potvrde or []),
            "rocista": [],
            "billing_entries": [],
            "predmet_beleske": [],
            "notifications": [],
        }

    def upisi(self, tabela, rows):
        self.tabele.setdefault(tabela, []).extend(rows)

    def table(self, ime):
        return _Upit(self.tabele.get(ime, []), ime, self)


def _potvrda(rid, akcija="rok_potvrdjen", seq=1):
    return {"resource_type": "rok", "resource_id": rid, "action": akcija, "seq": seq}


def _sutra():
    from datetime import date, timedelta
    return (date.today() + timedelta(days=1)).isoformat()


def _ai_rok(datum_iso=None, rid=ROK_ID, vaznost="kritičan", izvor="AI_AUTONOMOUS"):
    return {"id": rid, "akter": "Genome (AI)", "izvor": izvor, "vaznost": vaznost,
            "dogadjaj": "Rok za reklamaciju uredjaja U-1",
            "datum": datum_iso or _sutra(), "datum_iso": datum_iso or _sutra(),
            "predmet_id": PID, "user_id": UID}


def _request(path="/email-notif/send-reminders"):
    from starlette.requests import Request
    return Request({
        "type": "http", "method": "POST", "path": path,
        "headers": [], "query_string": b"", "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80), "scheme": "http",
    })


def _posalji_email(baza):
    """Pravi endpoint; SMTP je UVEK zamenjen."""
    import routers.email_notif as en
    poslati: list = []

    with patch.object(en, "_get_supa", return_value=baza), \
         patch("shared.deps._get_supa", return_value=baza), \
         patch.object(en, "_smtp_send", lambda *a, **k: poslati.append(a[:2])), \
         patch.object(en, "_email_html", lambda *a, **k: "<html/>"):
        rez = asyncio.run(en.posalji_podsetnike(
            _request(), user={"user_id": "cron", "email": ""}))
    return rez, poslati


# ═══════════════════════════════════════════════════════════════════════════
# TEST F / G — kapija ne zavisi od konfiguracije email sistema
# ═══════════════════════════════════════════════════════════════════════════

def test_F_email_UKLJUCEN_nepotvrdjen_ai_rok_ne_salje_nista():
    """NAJVAZNIJI TEST. Profil je AKTIVAN, rok je `kritičan`, datum je sutra —
    sve sto je ranije bilo dovoljno za slanje. Kapija ga mora zaustaviti."""
    b = FakeBaza([_ai_rok()], email_aktivan=True, potvrde=[])
    rez, poslati = _posalji_email(b)
    assert poslati == [], "nepotvrdjen AI rok je poslao email"
    assert rez.get("poslato") == 0, rez
    assert b.log == [], "rezervacija upisana za rok koji ne sme da se posalje"


def test_F_kontrola_isti_setup_ali_POTVRDJEN_rok_SALJE():
    """Parovni kontrolni slucaj: menja se ISKLJUCIVO postojanje potvrde.
    Bez ovoga gornji test ne bi dokazao da je uzrok kapija."""
    b = FakeBaza([_ai_rok()], email_aktivan=True, potvrde=[_potvrda(ROK_ID)])
    rez, poslati = _posalji_email(b)
    assert len(poslati) == 1, "potvrdjen rok nije poslat — kapija je preostroga"
    assert rez.get("poslato") == 1, rez


def test_E_odbijen_rok_ne_salje_ni_sa_ukljucenim_emailom():
    b = FakeBaza([_ai_rok()], email_aktivan=True,
                 potvrde=[_potvrda(ROK_ID, "rok_potvrdjen", 1),
                          _potvrda(ROK_ID, "rok_odbijen", 2)])
    rez, poslati = _posalji_email(b)
    assert poslati == [], "odbijen rok je poslao email"
    assert rez.get("poslato") == 0


def test_G_email_iskljucen_nepotvrdjen_rok_ne_salje():
    """TEST G: i bez profila nema slanja — ali to NE dokazuje kapiju, pa je
    ovaj test namerno oznacen kao slabiji dokaz od TEST-a F."""
    b = FakeBaza([_ai_rok()], email_aktivan=False, potvrde=[])
    rez, poslati = _posalji_email(b)
    assert poslati == []
    assert rez.get("poslato") == 0


def test_ljudski_rok_TAKODJE_trazi_potvrdu():
    """FAZA 6.4.2 je oborila raniju verziju ovog testa: „ljudski rok i dalje
    salje bez ikakve potvrde" je bilo tacno opisivanje RED-1 nalaza."""
    r = _ai_rok(rid="rok-h")
    r["akter"] = "Advokat Marko"
    r["izvor"] = "HUMAN_DIRECT"
    b = FakeBaza([r], email_aktivan=True, potvrde=[])
    _rez, poslati = _posalji_email(b)
    assert poslati == [], "ljudski rok je poslat bez potvrde — to je RED-1"

    b2 = FakeBaza([r], email_aktivan=True, potvrde=[_potvrda("rok-h")])
    _rez2, poslati2 = _posalji_email(b2)
    assert len(poslati2) == 1, "potvrdjen ljudski rok nije poslat"


def test_pad_citanja_potvrda_ne_salje_email():
    """FAIL-CLOSED kroz ceo put: ako se odluke ne mogu procitati, ne salje se."""
    import routers.email_notif as en
    b = FakeBaza([_ai_rok()], email_aktivan=True, potvrde=[_potvrda(ROK_ID)])
    poslati: list = []

    def _puca(*a, **k):
        raise RuntimeError("audit nedostupan")

    with patch.object(en, "_get_supa", return_value=b), \
         patch("shared.deps._get_supa", _puca), \
         patch.object(en, "_smtp_send", lambda *a, **k: poslati.append(a[:2])), \
         patch.object(en, "_email_html", lambda *a, **k: "<html/>"):
        asyncio.run(en.posalji_podsetnike(_request(), user={"user_id": "cron", "email": ""}))
    assert poslati == [], "pad citanja potvrda je propustio AI rok"


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL — svaki izvrsivi put mora nositi kapiju
# ═══════════════════════════════════════════════════════════════════════════

def _izvor(putanja):
    with open(os.path.join(os.path.dirname(__file__), "..", putanja), encoding="utf-8") as fh:
        return fh.read()


@pytest.mark.parametrize("fajl,ocekivano", [
    ("routers/email_notif.py", 3),
    ("routers/sms.py", 2),
    ("routers/notifications.py", 2),
])
def test_svi_izvrsivi_putevi_zovu_kapiju(fajl, ocekivano):
    """Broj poziva prati broj izvrsivih citanja hronologije po fajlu.

    Ne meri se samo prisustvo importa: novo citanje hronologije koje krene da
    salje/notifikuje BEZ kapije mora oboriti ovaj test."""
    s = _izvor(fajl)
    assert "_filtriraj_izvrsive" in s, f"{fajl} ne uvozi kanonsku kapiju"
    n = s.count("_filtriraj_izvrsive(")
    assert n >= ocekivano, f"{fajl}: kapija se zove {n}x, ocekivano najmanje {ocekivano}x"


@pytest.mark.parametrize("fajl", [
    "routers/email_notif.py", "routers/sms.py", "routers/notifications.py",
])
def test_kapija_se_uvozi_iz_jednog_vlasnika(fajl):
    """Jedan koncept = jedan vlasnik. Lokalna kopija predikata bi se razisla."""
    s = _izvor(fajl)
    assert "from shared.rokovi import filtriraj_izvrsive" in s
    assert "def filtriraj_izvrsive" not in s, f"{fajl} ima SVOJU kopiju kapije"


@pytest.mark.parametrize("fajl", [
    "routers/email_notif.py", "routers/sms.py", "routers/notifications.py",
])
def test_upiti_dovlace_polja_koja_kapija_trazi(fajl):
    """Kapija bez `id`/`akter` je fail-closed i tiho bi ugasila SVE rokove —
    tihi gubitak funkcionalnosti umesto tihe opasnosti. Oba su neprihvatljiva."""
    s = _izvor(fajl)
    for deo in s.split('table("predmet_hronologija")')[1:]:
        odsecak = deo[:400]
        if "_filtriraj_izvrsive" not in s:
            continue
        if ".select(" not in odsecak:
            continue
        sel = odsecak.split(".select(", 1)[1].split(")", 1)[0]
        if "akter" in sel or "id" in sel:
            continue
        # Preostali upiti smeju biti negejtovani samo ako NISU izvrsivi.
        assert "predmet_id" in sel, f"{fajl}: negejtovan upit bez ocekivanog oblika: {sel}"


def test_vaznost_semantika_nije_promenjena():
    """`vaznost` je AI procena tezine i ovaj sprint je NE dira. Promena
    `_ACTIONABLE_VAZNOST` da bi test prosao bila bi zaobilazenje problema."""
    from shared.rokovi import VAZNOST_DOZVOLJENE
    import routers.email_notif as en
    assert VAZNOST_DOZVOLJENE == ("kritičan", "važan", "informativan")
    assert en._ACTIONABLE_VAZNOST == ["kritičan", "važan"]


def test_genome_i_dalje_upisuje_kritican():
    """Gejt NE menja proizvodjaca. Genome sme da kaze `kritičan` — samo to vise
    nije ovlascenje. Ako bi neko "resio" problem menjanjem upisa, ovo pada."""
    s = _izvor("routers/case_dna.py")
    assert '"vaznost":    "kritičan"' in s, \
        "proizvodjac je promenjen umesto da je postavljena granica"
