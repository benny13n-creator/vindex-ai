# -*- coding: utf-8 -*-
"""N5 — evidencija naplate (Bojan: „da vodi evidenciju o naplati“): stvarne rute routers/billing.py nad lažnom bazom.
  * dvostruko zaustavljanje tajmera (dva taba / ponovljen zahtev) ne sme da napravi DVE stavke naplate;
  * status fakture (izdata → plaćena) se beleži uz očekivano prethodno stanje i zapis u audit_immutable;
    povratak u „nacrt“ (otključava finansijska polja) nije dozvoljen;
  * zbirovi i decimale. Nijedan test ne šalje fakturu ni SEF."""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import api
from tests.ns005_harness import pripremi, ocisti, zaglavlje

PA, PB = "pred-A-1", "pred-B-1"


def _baza():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Predmet A", "status": "aktivan"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "status": "aktivan"}],
        "billing_entries": [], "fakture": [], "timer_sessions": [], "tarifne_stavke_custom": [], "audit_immutable": [],
    }


@pytest.fixture
def ok(monkeypatch):
    k, b = pripremi(monkeypatch, _baza())
    import shared.audit_immutable as AUD

    async def _upis(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, correlation_id=None):
        if action not in AUD.AUDITABLE_ACTIONS:
            return None
        b.tabele["audit_immutable"].append({"action": action, "user_id": user_id, "resource_type": resource_type,
                                            "resource_id": resource_id, "metadata": metadata or {}})
        return "ok"
    monkeypatch.setattr(AUD, "log_action", _upis)
    yield k, b
    ocisti()


def _aktivan_tajmer(b, pre_min=90):
    b.tabele["timer_sessions"].append({"id": "t-1", "user_id": "uid-A", "predmet_id": PA, "opis": "Priprema ročišta", "aktivan": True,
                                       "start_at": (datetime.now(timezone.utc) - timedelta(minutes=pre_min)).isoformat()})


async def _istovremeno(putanja, telo, n=2):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://t") as c:
        return await asyncio.gather(*[c.post(putanja, json=telo, headers=zaglavlje("A")) for _ in range(n)])


def test_dvostruko_zaustavljanje_tajmera_pravi_jednu_stavku(ok):
    k, b = ok
    _aktivan_tajmer(b)
    odg = asyncio.run(_istovremeno("/billing/timer/stop", {"kreiraj_entry": True}))
    stavke = [e for e in b.tabele["billing_entries"] if e["predmet_id"] == PA]
    assert len(stavke) == 1, (stavke, [r.status_code for r in odg])
    assert sorted(r.status_code for r in odg)[0] == 200
    # ponovljen zahtev posle (izgubljen odgovor) — nema aktivnog tajmera, nema nove stavke
    r = k.post("/billing/timer/stop", json={"kreiraj_entry": True}, headers=zaglavlje("A"))
    assert r.status_code in (404, 409) and len([e for e in b.tabele["billing_entries"] if e["predmet_id"] == PA]) == 1


def _faktura(k, iznosi=(1234.56, 765.44)):
    ids = [k.post("/billing/entries", json={"predmet_id": PA, "opis": f"Rad {i}", "iznos_rsd": v}, headers=zaglavlje("A")).json()["entry"]["id"]
           for i, v in enumerate(iznosi)]
    r = k.post("/billing/faktura", json={"predmet_id": PA, "entry_ids": ids, "klijent_naziv": "Ana Jović", "pdv_stopa": 20}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    return r.json()["faktura"]


def test_zbirovi_i_pdv_bez_greske_zaokruzivanja(ok):
    k, b = ok
    f = _faktura(k)
    assert f["iznos_bez_pdv"] == 2000.0 and f["pdv_iznos"] == 400.0 and f["iznos_sa_pdv"] == 2400.0, f
    e = k.get("/billing/entries", params={"predmet_id": PA}, headers=zaglavlje("A")).json()
    assert e["ukupno_rsd"] == 2000.0 and e["obracunato_rsd"] == 2000.0 and e["neobracunato_rsd"] == 0


def test_izdata_pa_placena_uz_ocekivano_stanje_i_trag(ok):
    k, b = ok
    f = _faktura(k)
    put = f"/billing/faktura/{f['id']}/status"
    assert k.patch(put, json={"status": "izdata", "iz_statusa": "nacrt"}, headers=zaglavlje("A")).status_code == 200
    r = k.patch(put, json={"status": "placena", "iz_statusa": "izdata"}, headers=zaglavlje("A"))
    assert r.status_code == 200 and r.json()["status"] == "placena"
    trag = [a for a in b.tabele["audit_immutable"] if a["action"] == "faktura_status_promenjen" and a["resource_id"] == f["id"]]
    assert [(a["metadata"]["iz"], a["metadata"]["u"]) for a in trag] == [("nacrt", "izdata"), ("izdata", "placena")]


def test_zastareo_prikaz_ne_prepisuje_status(ok):
    k, b = ok
    f = _faktura(k)
    put = f"/billing/faktura/{f['id']}/status"
    k.patch(put, json={"status": "izdata", "iz_statusa": "nacrt"}, headers=zaglavlje("A"))
    k.patch(put, json={"status": "stornirana", "iz_statusa": "izdata"}, headers=zaglavlje("A"))   # drugi tab
    r = k.patch(put, json={"status": "placena", "iz_statusa": "izdata"}, headers=zaglavlje("A"))  # zastareo prikaz
    assert r.status_code == 409
    assert next(x for x in b.tabele["fakture"] if x["id"] == f["id"])["status"] == "stornirana"


@pytest.mark.parametrize("iz,u", [("izdata", "nacrt"), ("placena", "nacrt"), ("stornirana", "placena"), ("stornirana", "izdata")])
def test_nedozvoljen_prelaz(ok, iz, u):
    k, b = ok
    f = _faktura(k)
    next(x for x in b.tabele["fakture"] if x["id"] == f["id"])["status"] = iz
    r = k.patch(f"/billing/faktura/{f['id']}/status", json={"status": u}, headers=zaglavlje("A"))
    assert r.status_code == 409, r.text
    assert next(x for x in b.tabele["fakture"] if x["id"] == f["id"])["status"] == iz


def test_tudja_faktura_404(ok):
    k, b = ok
    f = _faktura(k)
    r = k.patch(f"/billing/faktura/{f['id']}/status", json={"status": "placena"}, headers=zaglavlje("B"))
    assert r.status_code == 404
    assert next(x for x in b.tabele["fakture"] if x["id"] == f["id"])["status"] == "nacrt"


def test_zastareo_prikaz_nacrt_ne_stornira_vec_izdatu(ok):
    """Prelaz izdata → stornirana JE dozvoljen, ali advokat je gledao NACRT; bez očekivanog stanja bi stornirao
    fakturu za koju ne zna da je izdata."""
    k, b = ok
    f = _faktura(k)
    put = f"/billing/faktura/{f['id']}/status"
    assert k.patch(put, json={"status": "izdata", "iz_statusa": "nacrt"}, headers=zaglavlje("A")).status_code == 200   # drugi tab
    r = k.patch(put, json={"status": "stornirana", "iz_statusa": "nacrt"}, headers=zaglavlje("A"))                  # zastareo prikaz
    assert r.status_code == 409
    assert next(x for x in b.tabele["fakture"] if x["id"] == f["id"])["status"] == "izdata"


def test_istovremene_promene_statusa_samo_jedna_uspeva(ok):
    k, b = ok
    f = _faktura(k)
    k.patch(f"/billing/faktura/{f['id']}/status", json={"status": "izdata", "iz_statusa": "nacrt"}, headers=zaglavlje("A"))

    async def _dva():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://t") as c:
            return await asyncio.gather(
                c.patch(f"/billing/faktura/{f['id']}/status", json={"status": "placena", "iz_statusa": "izdata"}, headers=zaglavlje("A")),
                c.patch(f"/billing/faktura/{f['id']}/status", json={"status": "stornirana", "iz_statusa": "izdata"}, headers=zaglavlje("A")))
    odg = asyncio.run(_dva())
    assert sorted(r.status_code for r in odg) == [200, 409], [r.text for r in odg]
    trag = [a for a in b.tabele["audit_immutable"] if a["action"] == "faktura_status_promenjen"]
    assert len(trag) == 2                                           # nacrt→izdata + JEDAN od dva


def test_pad_upisa_stavke_vraca_tajmer(ok, monkeypatch):
    k, b = ok
    _aktivan_tajmer(b)
    import routers.billing as BL
    pravi = BL._get_supa

    class _Pada:
        def __init__(self, s):
            self._s = s

        def table(self, ime):
            t = self._s.table(ime)
            if ime == "billing_entries":
                t.insert = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("baza pala"))
            return t
    monkeypatch.setattr(BL, "_get_supa", lambda: _Pada(pravi()))
    from fastapi.testclient import TestClient
    r = TestClient(api.app, raise_server_exceptions=False).post("/billing/timer/stop", json={"kreiraj_entry": True}, headers=zaglavlje("A"))
    assert r.status_code == 503
    assert next(t for t in b.tabele["timer_sessions"] if t["id"] == "t-1")["aktivan"] is True   # rad nije izgubljen
    monkeypatch.setattr(BL, "_get_supa", pravi)
    r2 = k.post("/billing/timer/stop", json={"kreiraj_entry": True}, headers=zaglavlje("A"))
    assert r2.status_code == 200 and len([e for e in b.tabele["billing_entries"] if e["predmet_id"] == PA]) == 1


def test_zaustavljanje_koje_nije_ugasilo_tajmer_ne_pravi_stavku(ok, monkeypatch):
    """Deterministički oblik trke: drugi zahtev je pročitao aktivan tajmer, ali ga je prvi već ugasio — uslovni
    upis (aktivan=true) ne menja ništa, pa drugi ne sme da napravi stavku."""
    k, b = ok
    _aktivan_tajmer(b)
    import routers.billing as BL
    pravi = BL._get_supa

    class _VecUgasen:
        def __init__(self, s):
            self._s = s

        def table(self, ime):
            t = self._s.table(ime)
            if ime == "timer_sessions":
                orig_update = t.update

                def _update(vals):
                    for r in b.tabele["timer_sessions"]:
                        r["aktivan"] = False                      # „prvi zahtev“ je ugasio tajmer u međuvremenu
                    return orig_update(vals)
                t.update = _update
            return t
    monkeypatch.setattr(BL, "_get_supa", lambda: _VecUgasen(pravi()))
    r = k.post("/billing/timer/stop", json={"kreiraj_entry": True}, headers=zaglavlje("A"))
    assert r.status_code == 409 and [e for e in b.tabele["billing_entries"] if e["predmet_id"] == PA] == []


def test_s1_upis_prosao_a_odgovor_pukao_nema_druge_stavke(ok, monkeypatch):
    """S1-C4 (revizija Sektora 1): stavka JE upisana, ali odgovor baze pukne (istek veze). Ranije se tajmer vraćao i
    sledeće zaustavljanje je upisivalo DRUGU stavku za isti rad."""
    k, b = ok
    _aktivan_tajmer(b)
    import routers.billing as BL
    pravi = BL._get_supa

    class _UpisPaPuca:
        def __init__(self, s):
            self._s = s

        def table(self, ime):
            t = self._s.table(ime)
            if ime == "billing_entries":
                orig = t.insert

                def _insert(vals):
                    orig(vals).execute()                               # upis se DOGODIO
                    raise RuntimeError("connection reset")             # … ali odgovor nije stigao
                t.insert = _insert
            return t
    monkeypatch.setattr(BL, "_get_supa", lambda: _UpisPaPuca(pravi()))
    r = k.post("/billing/timer/stop", json={"kreiraj_entry": True}, headers=zaglavlje("A"))
    monkeypatch.setattr(BL, "_get_supa", pravi)
    assert r.status_code == 200 and r.json()["entry"], r.text
    assert next(t for t in b.tabele["timer_sessions"] if t["id"] == "t-1")["aktivan"] is False
    assert k.post("/billing/timer/stop", json={"kreiraj_entry": True}, headers=zaglavlje("A")).status_code in (404, 409)
    assert len([e for e in b.tabele["billing_entries"] if e["predmet_id"] == PA]) == 1


def test_s1e_pad_upisa_ne_prepoznaje_stariju_istu_stavku(ok, monkeypatch):
    """Revizija S1-E: ranije je provera tražila stavku istog opisa/sati/iznosa/datuma, pa je pad upisa DRUGE sesije
    istog dana „našao“ prvu stavku i rad druge sesije se tiho gubio. Provera je sada po id-u ovog upisa."""
    k, b = ok
    _aktivan_tajmer(b)
    b.tabele["billing_entries"].append({"id": "stara", "user_id": "uid-A", "predmet_id": PA, "opis": "Rad po predmetu (tajmer)",
                                        "obracunato": False, "datum": "2000-01-01"})
    import routers.billing as BL
    pravi = BL._get_supa

    class _Pada:
        def __init__(self, s):
            self._s = s

        def table(self, ime):
            t = self._s.table(ime)
            if ime == "billing_entries":
                t.insert = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("baza pala"))
                orig_eq = t.eq

                def _eq(kol, v, *a, **kw):
                    polja.append(kol)
                    return orig_eq(kol, v, *a, **kw)
                t.eq = _eq
            return t
    polja = []
    monkeypatch.setattr(BL, "_get_supa", lambda: _Pada(pravi()))
    r = k.post("/billing/timer/stop", json={"kreiraj_entry": True}, headers=zaglavlje("A"))
    monkeypatch.setattr(BL, "_get_supa", pravi)
    assert r.status_code == 503 and next(t for t in b.tabele["timer_sessions"] if t["id"] == "t-1")["aktivan"] is True
    assert "id" in polja and "opis" not in polja, polja                    # provera po id-u ovog upisa
