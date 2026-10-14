# -*- coding: utf-8 -*-
"""NS2B-C F1 — lanac odluka o roku se cita CEO ili nikako.

Nalaz nezavisnog pregleda: `odluke()` (i `rok_izvor`) citali su `audit_immutable` jednim upitom bez
opsega. PostgREST `max-rows` (1000) takav odgovor TIHO sece, a redovi su rastuci po `seq` — dakle
padaju NAJNOVIJE odluke. Kasnije odbijanje je nestajalo i odbijen rok je citan kao CONFIRMED u svakom
grupnom citaocu (ICS, SMS cron za sve korisnike, portal, email, Viber, WhatsApp, jutarnji pregled,
kontrolna tabla) i u proveri pre potvrde. Pogorsanje: svaka ponovljena potvrda je upisivala nov red.

Lazni PostgREST ispod postuje filtere, `order(seq)`, `gt(seq)`, `limit` i — kao pravi server — vraca
NAJVISE `max_rows` redova bez obzira na `limit`. Sinteticki podaci.
"""
import pytest

from shared import rok_potvrda as rp
from shared.rok_izvor import izvor_uklonjen_posle_potvrde

P, O = rp.AKCIJA_POTVRDA, rp.AKCIJA_ODBIJANJE


class _Upit:
    def __init__(self, srv):
        self.srv, self.f, self.red, self.lim, self.ids = srv, [], None, None, None

    def select(self, *_a, **_k): return self
    def eq(self, c, v): self.f.append(lambda r: r.get(c) == v); return self

    def in_(self, c, vs):
        s = set(vs)
        if c == "resource_id":
            self.ids = len(s)
        self.f.append(lambda r: r.get(c) in s)
        return self

    def gt(self, c, v): self.f.append(lambda r: r.get(c) is not None and r.get(c) > v); return self
    def order(self, c, desc=False): self.red = (c, desc); return self
    def limit(self, n): self.lim = n; return self

    def execute(self):
        self.srv.upiti.append(self.ids)
        if len(self.srv.upiti) in self.srv.pada_na:
            raise RuntimeError('{"code": "57014", "message": "statement timeout"}')
        out = [r for r in self.srv.redovi if all(f(r) for f in self.f)]
        if self.red:
            out.sort(key=lambda r: r[self.red[0]], reverse=self.red[1])
        n = self.srv.max_rows if self.lim is None else min(self.lim, self.srv.max_rows)
        out = [dict(r) for r in out[:n]]
        if self.srv.izmena:
            out = self.srv.izmena(out)
        return type("R", (), {"data": out})()


class _Srv:
    def __init__(self, redovi, max_rows=1000, pada_na=(), izmena=None):
        self.redovi, self.max_rows, self.pada_na, self.izmena = redovi, max_rows, set(pada_na), izmena
        self.upiti: list = []

    def table(self, ime):
        assert ime == "audit_immutable", ime
        return _Upit(self)


def _red(seq, rid, akcija, t=None):
    r = {"seq": seq, "resource_type": "rok", "resource_id": rid, "action": akcija}
    if t:
        r["created_at"] = t
    return r


def _sa(monkeypatch, srv):
    monkeypatch.setattr("shared.deps._get_supa", lambda: srv)
    return srv


def _slucaj_1():
    """Jedan rok: 1000 (ponovljenih) potvrda, pa jedno odbijanje (seq 1001)."""
    return [_red(i, "r-1", P) for i in range(1, 1001)] + [_red(1001, "r-1", O)], ["r-1"], "r-1"


def _slucaj_2():
    """Grupno citanje: 999 drugih potvrdjenih rokova, pa cilj potvrdjen (1000) i odbijen (1001)."""
    redovi = [_red(i, f"x-{i}", P) for i in range(1, 1000)]
    redovi += [_red(1000, "t", P), _red(1001, "t", O)]
    return redovi, [f"x-{i}" for i in range(1, 1000)] + ["t"], "t"


# ── recenzentova sonda + max-rows nizi od strane ─────────────────────────────────────────────────
@pytest.mark.parametrize("max_rows", [1000, 300, 1])
@pytest.mark.parametrize("slucaj", [_slucaj_1, _slucaj_2], ids=["1000_potvrda_pa_odbijanje", "999_drugih_pa_cilj"])
def test_odbijanje_iza_granice_max_rows_je_REJECTED(monkeypatch, slucaj, max_rows):
    redovi, ids, cilj = slucaj()
    _sa(monkeypatch, _Srv(redovi, max_rows=max_rows))
    assert rp.odluke(ids).get(cilj) == rp.STANJE_ODBIJEN
    assert rp.odluke(ids, True).get(cilj) == rp.STANJE_ODBIJEN
    assert cilj not in rp.potvrdjeni_ids(ids)
    if cilj == "t":
        # Ostali rokovi su i dalje potvrdjeni — stranicenje ne gubi ni jedan red.
        assert len(rp.potvrdjeni_ids(ids)) == 999


def test_rok_izvor_vidi_odbijanje_iza_granice(monkeypatch):
    """`rok_izvor` je imao isti plafon: potvrda pre uklanjanja dokumenta + odbijanje iza granice
    davalo je upozorenje za ODBIJEN rok (kao da je potvrdjen)."""
    redovi = [_red(i, "r-1", P, "2025-03-20T10:00:00+00:00") for i in range(1, 1001)]
    redovi.append(_red(1001, "r-1", O, "2025-03-23T10:00:00+00:00"))
    srv = _sa(monkeypatch, _Srv(redovi, max_rows=300))

    class _Dog:
        def select(self, *a): return self
        def eq(self, *a): return self
        def in_(self, *a): return self
        def execute(self):
            return type("R", (), {"data": [{"predmet_id": "p-1", "created_at": "2025-03-21T10:00:00+00:00",
                                            "payload": {"source_type": "dokument"}}]})()
    srv.table = lambda ime: _Dog() if ime == "events" else _Upit(srv)
    assert izvor_uklonjen_posle_potvrde([{"id": "r-1", "predmet_id": "p-1"}]) == set()


def test_rok_izvor_vidi_potvrdu_iza_granice(monkeypatch):
    """Obrnuto: potvrda cilja je iza granice (1200 drugih redova pre nje) — upozorenje MORA postojati."""
    redovi = [_red(i, f"x-{i % 50}", P, "2025-03-19T10:00:00+00:00") for i in range(1, 1201)]
    redovi.append(_red(1201, "r-1", P, "2025-03-20T10:00:00+00:00"))
    srv = _sa(monkeypatch, _Srv(redovi, max_rows=1000))

    class _Dog:
        def select(self, *a): return self
        def eq(self, *a): return self
        def in_(self, *a): return self
        def execute(self):
            return type("R", (), {"data": [{"predmet_id": "p-1", "created_at": "2025-03-21T10:00:00+00:00",
                                            "payload": {"source_type": "dokument"}}]})()
    srv.table = lambda ime: _Dog() if ime == "events" else _Upit(srv)
    redovi_roka = [{"id": f"x-{i}", "predmet_id": "p-x"} for i in range(50)] + [{"id": "r-1", "predmet_id": "p-1"}]
    assert izvor_uklonjen_posle_potvrde(redovi_roka) == {"r-1"}


# ── pad strane / neispravno stranicenje → nikad CONFIRMED ────────────────────────────────────────
@pytest.mark.parametrize("pada_na", [1, 2, 3])
def test_pad_bilo_koje_strane_strogo_dize_nestrogo_nista_potvrdjeno(monkeypatch, pada_na):
    redovi = [_red(i, "r-1", P) for i in range(1, 11)]
    _sa(monkeypatch, _Srv(redovi, max_rows=4, pada_na=[pada_na]))        # strane: 4, 4, 2, prazna
    with pytest.raises(Exception):
        rp.odluke(["r-1"], True)
    _sa(monkeypatch, _Srv(redovi, max_rows=4, pada_na=[pada_na]))
    assert rp.odluke(["r-1"]) == {}
    _sa(monkeypatch, _Srv(redovi, max_rows=4, pada_na=[pada_na]))
    assert rp.potvrdjeni_ids(["r-1"]) == set()


@pytest.mark.parametrize("izmena", [
    lambda s: s + s[-1:],                                       # duplikat unutar strane
    lambda s: list(reversed(s)),                                # strana van redosleda
    lambda s: [dict(r, seq=1) for r in s],                      # server ignorise `gt` (ista strana stalno)
    lambda s: [dict(r, seq=str(r["seq"])) for r in s],          # seq nije ceo broj
    lambda s: [{k: v for k, v in r.items() if k != "seq"} for r in s],   # seq nedostaje
], ids=["duplikat", "van_redosleda", "ignorise_gt", "seq_tekst", "bez_seq"])
def test_neispravno_stranicenje_je_greska_ne_potvrda(monkeypatch, izmena):
    redovi = [_red(i, "r-1", P) for i in range(1, 6)]
    _sa(monkeypatch, _Srv(redovi, max_rows=2, izmena=izmena))
    with pytest.raises(RuntimeError):
        rp.odluke(["r-1"], True)
    assert rp.odluke(["r-1"]) == {} and rp.potvrdjeni_ids(["r-1"]) == set()


def test_ograniceno_iteriranje(monkeypatch):
    """Server koji bi vracao strane bez kraja ne moze da zaglavi citanje — granica je greska."""
    monkeypatch.setattr(rp, "_MAX_STRANA", 5)
    redovi = [_red(i, "r-1", P) for i in range(1, 100)]
    _sa(monkeypatch, _Srv(redovi, max_rows=1))
    with pytest.raises(RuntimeError):
        rp.odluke(["r-1"], True)
    assert rp.odluke(["r-1"]) == {}


def test_veliki_skup_idjeva_ide_u_grupama(monkeypatch):
    """Cron salje rokove svih korisnika: `in.(...)` ide u URL, pa najvise `_IDS_PO_UPITU` po upitu."""
    ids = [f"r-{i}" for i in range(250)]
    redovi = [_red(i + 1, f"r-{i}", P) for i in range(250)] + [_red(1000, "r-249", O), _red(1001, "r-0", O)]
    srv = _sa(monkeypatch, _Srv(redovi, max_rows=1000))
    stanja = rp.odluke(ids, True)
    assert stanja["r-0"] == stanja["r-249"] == rp.STANJE_ODBIJEN
    assert sum(1 for s in stanja.values() if s == rp.STANJE_POTVRDJEN) == 248
    assert max(srv.upiti) <= rp._IDS_PO_UPITU and len(srv.upiti) == 6   # 3 grupe x (strana + prazna)


def test_kraj_samo_na_praznoj_strani(monkeypatch):
    """Kratka strana NIJE kraj (max-rows nizi od `_STRANA`): citanje staje tek na praznoj."""
    redovi = [_red(i, "r-1", P) for i in range(1, 8)]
    srv = _sa(monkeypatch, _Srv(redovi, max_rows=3))
    assert rp.odluke(["r-1"], True) == {"r-1": rp.STANJE_POTVRDJEN}
    assert len(srv.upiti) == 4                                            # 3 + 3 + 1 + prazna


# ── idempotentna odluka na ruti (stvaran api.app, stvaran log_action) ─────────────────────────────
from tests.ns005_harness import ocisti, pripremi, zaglavlje  # noqa: E402
from shared import rokovi as rokovi_domen  # noqa: E402


@pytest.fixture
def ok(monkeypatch):
    rokovi_domen._resetuj_sondu()
    import shared.audit_immutable as audit
    pravi = audit.log_action
    k, b = pripremi(monkeypatch, {
        "predmeti": [{"id": "pred-A-1", "user_id": "uid-A", "naziv": "Predmet A", "status": "aktivan"}],
        "predmet_hronologija": [
            {"id": "r-1", "user_id": "uid-A", "predmet_id": "pred-A-1", "dogadjaj": "Rok za odgovor",
             "datum_iso": "2099-01-10", "vaznost": "visok", "izvor": "AI_EXTRACTED", "vrsta": "rok"}],
        "audit_immutable": [], "events": []})
    monkeypatch.setattr(audit, "log_action", pravi)
    yield k, b
    rokovi_domen._resetuj_sondu()
    ocisti()


def _post(k, akcija):
    return k.post(f"/api/rokovi/r-1/{akcija}", json={}, headers=zaglavlje("A"))


def _lanac(b):
    return [z["action"] for z in b.tabele["audit_immutable"] if z.get("resource_id") == "r-1"]


def test_ponovljena_potvrda_ne_upisuje(ok):
    k, b = ok
    assert _post(k, "potvrdi").json()["odluka_zabelezena"] is True
    for _ in range(5):
        r = _post(k, "potvrdi")
        assert r.status_code == 200
        assert r.json()["stanje_odluke"] == rp.STANJE_POTVRDJEN and r.json()["odluka_zabelezena"] is False
    assert _lanac(b) == [P]


def test_ponovljeno_odbijanje_ne_upisuje_a_odbijanje_potvrdjenog_upisuje(ok):
    k, b = ok
    assert _post(k, "potvrdi").status_code == 200
    assert _post(k, "odbij").json()["odluka_zabelezena"] is True
    r = _post(k, "odbij")
    assert r.status_code == 200 and r.json()["odluka_zabelezena"] is False
    assert r.json()["stanje_odluke"] == rp.STANJE_ODBIJEN
    assert _lanac(b) == [P, O]


def test_ponovna_potvrda_kad_provera_izvora_padne_503_bez_upisa(ok, monkeypatch):
    import routers.rok_odluka as ro
    k, b = ok
    assert _post(k, "potvrdi").status_code == 200

    def _pada(_redovi):
        raise RuntimeError("events nedostupan")
    monkeypatch.setattr(ro, "izvor_uklonjen_posle_potvrde", _pada)
    r = _post(k, "potvrdi")
    assert r.status_code == 503 and "odluka_zabelezena" not in r.json()
    assert _lanac(b) == [P]


def test_odbijanje_se_upisuje_i_kad_citanje_pre_padne(ok, monkeypatch):
    """Oduzimanje izvrsivosti je bezbedan smer: neprocitan lanac ne blokira odbijanje."""
    import routers.rok_odluka as ro
    k, b = ok
    pravo = ro.odluke
    poziv = {"n": 0}

    def _prvi_pada(ids, strogo=False):
        poziv["n"] += 1
        if poziv["n"] == 1:
            raise RuntimeError("lanac nedostupan")
        return pravo(ids, strogo)
    monkeypatch.setattr(ro, "odluke", _prvi_pada)
    r = _post(k, "odbij")
    assert r.status_code == 200 and r.json()["odluka_zabelezena"] is True
    assert _lanac(b) == [O]


def test_ruta_stranici_kroz_harness(ok, monkeypatch):
    """Stvarna ruta nad harness bazom sa stranom od 1 reda: odbijanje posle 3 potvrde je vidljivo."""
    k, b = ok
    monkeypatch.setattr(rp, "_STRANA", 1)
    for a in (P, P, P, O):
        b.table("audit_immutable").insert({"action": a, "resource_type": "rok", "resource_id": "r-1",
                                           "user_id": "uid-A"}).execute()
    assert rp.odluke(["r-1"], True) == {"r-1": rp.STANJE_ODBIJEN}
    assert _post(k, "potvrdi").status_code == 409
