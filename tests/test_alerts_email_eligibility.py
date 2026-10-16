# -*- coding: utf-8 -*-
"""Email podsetnici — fail-closed podobnost roka (night/deadlines-alerts-vcr002, T07).

Ne ponavlja QA-01: koristi stvarni endpoint nad `test_b10_reminder_claim.FakeBaza` i meri samo dodirne
tačke koje operativni cron otvara. Varijanta baze PROJEKTUJE kolone iz `select(...)` kao PostgREST, jer
rezervni upit bez `brisanje_zapoceto` u stvarnosti uopšte ne vraća tu kolonu."""
import pytest

from tests import test_b10_reminder_claim as b10

POLJA = ("poslato", "greske", "preskoceno", "neisporuceno")
U_BRISANJU = "2026-10-12T08:00:00+00:00"


@pytest.fixture(autouse=True)
def _potvrdjeno(monkeypatch):
    import routers.email_notif as en
    monkeypatch.setattr(en, "_potvrdjeni_ids", lambda ids: {str(i) for i in ids if i})


class _Projekcija:
    """PostgREST lanac: filteri rade nad celim redom, a `execute` vraća SAMO kolone iz `select(...)`."""

    def __init__(self, redovi, kolone=None):
        self._r, self._k = list(redovi), kolone

    def select(self, kolone="*", *a, **k):
        return _Projekcija(self._r, None if kolone in ("*", None) else [c.strip() for c in kolone.split(",")])

    def eq(self, kol, v):
        return _Projekcija([r for r in self._r if r.get(kol) == v], self._k)

    @property
    def not_(self):
        upit = self

        class _Ne:
            def in_(self, kol, vs):
                return _Projekcija([r for r in upit._r if r.get(kol) not in set(vs)], upit._k)
        return _Ne()

    def execute(self):
        class R:
            pass
        r = R()
        r.data = [r_ if self._k is None else {c: r_.get(c) for c in self._k if c in r_} for r_ in self._r]
        return r


class BazaSaGreskom(b10.FakeBaza):
    """`predmeti` upit koji traži `brisanje_zapoceto` baca zadatu grešku; ostali upiti rade normalno."""

    def __init__(self, rokovi, greska=None):
        super().__init__(rokovi)
        self.greska = greska

    def table(self, ime):
        q = super().table(ime)
        if ime != "predmeti":
            return q
        baza = self

        class _Q(_Projekcija):
            def select(self, kolone="*", *a, **k):
                if baza.greska is not None and "brisanje_zapoceto" in str(kolone):
                    raise baza.greska
                return super().select(kolone, *a, **k)
        return _Q(q._r)


def _u_brisanju(baza):
    baza.tabele["predmeti"][0]["brisanje_zapoceto"] = U_BRISANJU
    return baza


def test_kontrola_predmet_u_brisanju_ne_salje_kada_upit_radi():
    rez, poslati = b10._pokreni(_u_brisanju(BazaSaGreskom([b10._rok(b10._sutra())])))
    assert poslati == [] and rez["poslato"] == 0


@pytest.mark.parametrize("greska", [
    RuntimeError("connection reset by peer"),
    TimeoutError("read timeout"),
    RuntimeError('{"code":"57014","message":"canceling statement due to statement timeout"}'),
    RuntimeError('{"code":"PGRST301","message":"JWT expired"}'),
], ids=["reset", "timeout", "statement_timeout", "auth"])
def test_prolazna_greska_ne_otvara_slanje_za_predmet_u_brisanju(greska):
    """Rezervni upit bez kolone ne sme biti dozvola: greška koja NIJE „kolona ne postoji“ = fail-closed."""
    baza = _u_brisanju(BazaSaGreskom([b10._rok(b10._sutra())], greska))
    rez, poslati = b10._pokreni(baza)
    assert poslati == [], "poslat podsetnik za predmet u brisanju"
    assert baza.log == []
    assert rez["greske"] >= 1, "greška provere aktivnog stanja je nevidljiva"


def test_prolazna_greska_ne_salje_ni_za_aktivan_predmet_ali_je_vidljiva():
    baza = BazaSaGreskom([b10._rok(b10._sutra())], RuntimeError("connection reset by peer"))
    rez, poslati = b10._pokreni(baza)
    assert poslati == [] and rez["greske"] == 1 and rez["poslato"] == 0


def test_kolona_ne_postoji_pre_migracije_114_i_dalje_koristi_rezervni_upit():
    """Jedini legitimni razlog za rezervni upit: baza bez kolone (pre 114) — tada tombstone ne može postojati."""
    greska = RuntimeError('{"code":"42703","message":"column predmeti.brisanje_zapoceto does not exist"}')
    rez, poslati = b10._pokreni(BazaSaGreskom([b10._rok(b10._sutra())], greska))
    assert rez["poslato"] == 1 and len(poslati) == 1 and rez["greske"] == 0


@pytest.mark.parametrize("status", ["zatvoren", "arhiviran", "odbijen"])
def test_zatvoren_arhiviran_odbijen_predmet_ne_salje(status):
    baza = BazaSaGreskom([b10._rok(b10._sutra())])
    baza.tabele["predmeti"][0]["status"] = status
    rez, poslati = b10._pokreni(baza)
    assert poslati == [] and rez["poslato"] == 0 and baza.log == []


def test_nepotvrdjen_ai_rok_ne_salje(monkeypatch):
    import routers.email_notif as en
    monkeypatch.setattr(en, "_potvrdjeni_ids", lambda ids: set())
    rok = {**b10._rok(b10._sutra()), "izvor": "AI_AUTONOMOUS"}
    rez, poslati = b10._pokreni(BazaSaGreskom([rok]))
    assert poslati == [] and rez["poslato"] == 0


def test_bez_opt_in_profila_nema_primaoca():
    baza = BazaSaGreskom([b10._rok(b10._sutra())])
    baza.tabele["korisnik_email_notif"][0]["aktivan"] = False
    rez, poslati = b10._pokreni(baza)
    assert poslati == [] and rez["poslato"] == 0


def test_tudji_predmet_nikad_u_tudjem_emailu():
    """Red hronologije korisnika A koji pokazuje na predmet korisnika B ne ulazi u A-ov email."""
    baza = BazaSaGreskom([{**b10._rok(b10._sutra()), "predmet_id": "p-tudji"}])
    baza.tabele["predmeti"].append({"id": "p-tudji", "user_id": "u-2", "status": "aktivan"})
    rez, poslati = b10._pokreni(baza)
    assert poslati == [] and rez["poslato"] == 0 and baza.log == []
