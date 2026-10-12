# -*- coding: utf-8 -*-
"""VCR002 Task 04 — postojeći podsetnici za rokove (routers/email_notif.py::posalji_podsetnike), bez novog planera.

Dopunjuje tests/test_b10_reminder_claim.py tamo gde njegova lažna baza nije verna Postgres-u:
  * UNIQUE(user_id, predmet_id, datum_roka, dana_pre) (migracija 021) važi i UNUTAR jednog višerednog INSERT-a —
    dva potvrđena roka istog dana u istom predmetu ne smeju da obore rezervaciju i tiho preskoče podsetnik.
  * predmet u brisanju (BETA-DEL-001, `brisanje_zapoceto`) ne šalje podsetnik.
  * stvarna kapija potvrde (shared/rok_potvrda + shared/rokovi): nepotvrđen, odbijen i „potvrđen pa odbijen“
    AI rok NE šalju; potvrđen šalje — odluke se čitaju iz lanca `audit_immutable`, ne zamenjuju se.
  * odgovor rute nikad ne tvrdi slanje koje se nije desilo.

NIJEDAN TEST NE ŠALJE PRAVI EMAIL — `_smtp_send` je uvek zamenjen.
"""
from datetime import date, timedelta

import pytest

from tests import test_b10_reminder_claim as b10

UID, PID, P2 = b10.UID, b10.PID, "p-2"


class StrogaBaza(b10.FakeBaza):
    """Kao b10.FakeBaza, ali UNIQUE važi i među redovima ISTOG INSERT-a (Postgres: ceo iskaz pada)."""

    def upisi(self, tabela, rows):
        if tabela == "email_notif_log":
            kljucevi = [tuple(str(r.get(k)) for k in self.KLJUC) for r in rows]
            if len(set(kljucevi)) != len(kljucevi):
                raise RuntimeError('{"code":"23505","message":"duplicate key value violates unique constraint"}')
        return super().upisi(tabela, rows)


def _rok(rid, datum, predmet=PID, izvor="HUMAN_DIRECT", dogadjaj="Rok za žalbu"):
    return {"id": rid, "akter": "Advokat", "izvor": izvor, "dogadjaj": dogadjaj, "datum_iso": datum,
            "predmet_id": predmet, "user_id": UID, "vaznost": "kritičan"}


def _sutra():
    return (date.today() + timedelta(days=1)).isoformat()


def test_dva_potvrdjena_roka_istog_dana_u_istom_predmetu_jedan_email_sa_oba(monkeypatch):
    import routers.email_notif as en
    monkeypatch.setattr(en, "_potvrdjeni_ids", lambda ids: {str(i) for i in ids if i})
    sadrzaj = []
    monkeypatch.setattr(en, "_email_html", lambda rokovi, *a, **k: sadrzaj.append([r["dogadjaj"] for r in rokovi]) or "<html/>")
    baza = StrogaBaza([_rok("r1", _sutra(), dogadjaj="Rok za žalbu"), _rok("r2", _sutra(), dogadjaj="Rok za odgovor na tužbu")])
    import unittest.mock as um
    with um.patch.object(en, "_get_supa", return_value=baza):
        poslati = []
        with um.patch.object(en, "_smtp_send", lambda to, subj, html: poslati.append((to, subj))):
            import asyncio
            rez = asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))
    assert len(poslati) == 1 and rez["poslato"] == 1, (rez, poslati)                  # podsetnik NIJE tiho preskočen
    assert sorted(sadrzaj[0]) == ["Rok za odgovor na tužbu", "Rok za žalbu"]          # oba roka u istom emailu
    assert len(baza.log) == 1                                                        # jedna rezervacija po (predmet, datum, dan)


def test_rokovi_dva_predmeta_istog_dana_dve_rezervacije_jedan_email(monkeypatch):
    import routers.email_notif as en
    monkeypatch.setattr(en, "_potvrdjeni_ids", lambda ids: {str(i) for i in ids if i})
    baza = StrogaBaza([_rok("r1", _sutra()), _rok("r2", _sutra(), predmet=P2)])
    baza.tabele["predmeti"].append({"id": P2, "user_id": UID, "status": "aktivan"})
    rez, poslati = b10._pokreni(baza)
    assert len(poslati) == 1 and rez["poslato"] == 1
    assert sorted(r["predmet_id"] for r in baza.log) == [PID, P2]


def test_ponovljen_cron_posle_dva_roka_istog_dana_ne_salje_ponovo(monkeypatch):
    import routers.email_notif as en
    monkeypatch.setattr(en, "_potvrdjeni_ids", lambda ids: {str(i) for i in ids if i})
    baza = StrogaBaza([_rok("r1", _sutra()), _rok("r2", _sutra())])
    _, p1 = b10._pokreni(baza)
    rez2, p2 = b10._pokreni(baza)
    assert len(p1) == 1 and p2 == [] and rez2["poslato"] == 0


def test_predmet_u_brisanju_ne_salje(monkeypatch):
    import routers.email_notif as en
    monkeypatch.setattr(en, "_potvrdjeni_ids", lambda ids: {str(i) for i in ids if i})
    baza = StrogaBaza([_rok("r1", _sutra())])
    baza.tabele["predmeti"][0]["brisanje_zapoceto"] = "2026-10-12T08:00:00+00:00"
    rez, poslati = b10._pokreni(baza)
    assert poslati == [] and rez["poslato"] == 0 and baza.log == []


# ── stvarna kapija potvrde: odluke iz lanca audit_immutable ──────────────────────────────────────────────────
class _Lanac:
    """`audit_immutable` čitanje koje radi shared/rok_potvrda.odluke(): select().eq().in_().in_().order().execute()."""

    def __init__(self, odluke):
        self.odluke = odluke                    # [(rok_id, akcija), ...] redom po seq

    def table(self, ime):
        assert ime == "audit_immutable", ime
        return self

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def order(self, *a, **k): return self

    def execute(self):
        import types
        return types.SimpleNamespace(data=[{"action": a, "resource_id": r, "seq": i} for i, (r, a) in enumerate(self.odluke)])


@pytest.mark.parametrize("odluke,salje", [
    ([], False),                                                    # nepotvrđen AI rok
    ([("ai-1", "ODBIJANJE")], False),                               # odbijen
    ([("ai-1", "POTVRDA"), ("ai-1", "ODBIJANJE")], False),          # potvrđen pa odbijen — poslednja odluka pobeđuje
    ([("ai-1", "POTVRDA")], True),                                  # potvrđen
], ids=["nepotvrdjen", "odbijen", "potvrdjen_pa_odbijen", "potvrdjen"])
def test_samo_potvrdjen_ai_rok_salje_email_kroz_stvarnu_kapiju(monkeypatch, odluke, salje):
    import routers.email_notif as en
    import shared.rok_potvrda as rp
    akcije = {"POTVRDA": rp.AKCIJA_POTVRDA, "ODBIJANJE": rp.AKCIJA_ODBIJANJE}
    lanac = _Lanac([(r, akcije[a]) for r, a in odluke])
    monkeypatch.setattr("shared.deps._get_supa", lambda: lanac)
    baza = StrogaBaza([_rok("ai-1", _sutra(), izvor="AI_AUTONOMOUS", dogadjaj="Rok iz dokumenta")])
    rez, poslati = b10._pokreni(baza)
    assert (len(poslati) == 1) is salje, (odluke, rez, poslati)
    assert rez["poslato"] == (1 if salje else 0)
    assert (len(baza.log) == 1) is salje                             # bez rezervacije za ono što se ne šalje


def test_pad_citanja_lanca_odluka_ne_salje_nista(monkeypatch):
    import routers.email_notif as en

    class _Pukla:
        def table(self, *a): raise RuntimeError("baza nedostupna")
    monkeypatch.setattr("shared.deps._get_supa", lambda: _Pukla())
    baza = StrogaBaza([_rok("ai-1", _sutra(), izvor="AI_AUTONOMOUS")])
    rez, poslati = b10._pokreni(baza)
    assert poslati == [] and rez["poslato"] == 0                     # fail-closed


def test_bez_tajne_ili_sa_pogresnim_kljucem_403_a_sa_ispravnim_prolazi(monkeypatch):
    import routers.email_notif as en
    from fastapi.testclient import TestClient
    from fastapi import FastAPI, Depends
    app = FastAPI()

    @app.post("/probe")
    async def _probe(user: dict = Depends(en._require_cron_or_founder)):
        return {"ok": True, "uid": user["user_id"]}
    k = TestClient(app)
    monkeypatch.setattr(en, "_CRON_SECRET", "")
    assert k.post("/probe", headers={"X-Cron-Key": ""}).status_code == 403          # neconfigurisana tajna: nikad prazno = prazno
    assert k.post("/probe", headers={"X-Cron-Key": "bilo-sta"}).status_code == 403
    monkeypatch.setattr(en, "_CRON_SECRET", "s" * 40)
    assert k.post("/probe").status_code == 403
    assert k.post("/probe", headers={"X-Cron-Key": "x" * 40}).status_code == 403
    assert k.post("/probe", headers={"Authorization": "Bearer " + "s" * 40}).status_code == 403   # Bearer nije ključ
    r = k.post("/probe", headers={"X-Cron-Key": "s" * 40})
    assert r.status_code == 200 and r.json()["uid"] == "cron-scheduler"
