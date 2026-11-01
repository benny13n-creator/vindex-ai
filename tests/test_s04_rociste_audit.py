# -*- coding: utf-8 -*-
"""S04 (N3) — istorija promena ročišta. Status („otkazano“, „održano“, „vrati na zakazano“) i datum se menjaju
u istom redu `rocista`; jedini trag je bio događaj `ROCISTE_ZAKAZANO` bez prethodnog stanja. Ko je i kada otkazao
ročište, i šta je bilo pre, nije bilo nigde zapisano. Svaka USPEŠNA izmena sada ostavlja audit zapis sa prethodnim
i novim stanjem; odbijena izmena (zastareo prikaz, nastavak odloženog, tuđ nalog) ne ostavlja ništa.
Stvarne rute nad bazom u memoriji, uz stvarnu proveru `AUDITABLE_ACTIONS` (fixture `lanac`)."""
from datetime import timedelta

from routers.email_notif import _danas_beograd
from tests.test_n3_rocista import _predmet, lanac  # noqa: F401 — `lanac` je fixture
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401

SUD = "Osnovni sud u Beogradu"


def _izmene(b, rid):
    return [x for x in b.tabele.get("audit_immutable", []) if x["action"] == "rociste_izmena" and x["resource_id"] == rid]


def _zakazi(k, pid, dana):
    r = k.post("/api/rocista", json={"predmet_id": pid, "sud": SUD, "datum": (_danas_beograd() + timedelta(days=dana)).isoformat(),
                                     "vreme": "10:00"}, headers=A)
    assert r.status_code == 200, r.text
    return r.json()["rociste"]


def test_promene_stanja_i_datuma_ostavljaju_istoriju_sa_prethodnim_stanjem(lanac):
    k, b = lanac
    pid = _predmet(k)
    r1 = _zakazi(k, pid, 10)
    d_novi = (_danas_beograd() + timedelta(days=12)).isoformat()
    assert k.patch(f"/api/rocista/{r1['id']}", json={"status": "otkazano"}, headers=A).status_code == 200
    assert k.patch(f"/api/rocista/{r1['id']}", json={"status": "zakazano"}, headers=A).status_code == 200
    assert k.patch(f"/api/rocista/{r1['id']}", json={"datum": d_novi, "vreme": "11:30"}, headers=A).status_code == 200
    assert k.patch(f"/api/rocista/{r1['id']}", json={"status": "odrzano"}, headers=A).status_code == 200

    z = _izmene(b, r1["id"])
    assert [x["user_id"] for x in z] == ["uid-A"] * 4 and all(x["resource_type"] == "rociste" for x in z)
    m = [x["metadata"] for x in z]
    assert [(x["prethodno"]["status"], x["novo"]["status"]) for x in m] == [
        ("zakazano", "otkazano"), ("otkazano", "zakazano"), ("zakazano", "zakazano"), ("zakazano", "odrzano")]
    assert (m[2]["prethodno"]["datum"], m[2]["novo"]["datum"]) == (r1["datum"], d_novi)
    assert (m[2]["prethodno"]["vreme"], m[2]["novo"]["vreme"]) == ("10:00", "11:30")
    assert all(x["predmet_id"] == pid for x in m)
    # „novo“ je stanje reda POSLE upisa (i nepromenjena polja), ne samo telo zahteva
    assert m[0]["novo"] == {"status": "otkazano", "datum": r1["datum"], "vreme": "10:00", "sud": SUD, "sudnica": None}
    assert m[0]["prethodno"] == {**m[0]["novo"], "status": "zakazano"}
    assert sorted(m[2]["polja"]) == ["datum", "vreme"] and m[0]["polja"] == ["status"]


def test_odbijene_izmene_ne_ostavljaju_istoriju(lanac):
    k, b = lanac
    pid = _predmet(k)
    r1 = _zakazi(k, pid, 10)
    # zastareo prikaz: drugi tab je već promenio stanje
    r = k.patch(f"/api/rocista/{r1['id']}", json={"napomena": "Ponesite punomoćje."}, headers=A)
    star = r.json()["rociste"]["updated_at"]
    assert k.patch(f"/api/rocista/{r1['id']}", json={"status": "odrzano", "if_updated_at": star}, headers=A).status_code == 200
    r = k.patch(f"/api/rocista/{r1['id']}", json={"status": "otkazano", "if_updated_at": star}, headers=A)
    assert r.status_code == 409
    # tuđ nalog
    assert k.patch(f"/api/rocista/{r1['id']}", json={"status": "otkazano"}, headers=B).status_code == 404
    # vraćanje odloženog posle zakazanog nastavka
    r2 = _zakazi(k, pid, 20)
    assert k.patch(f"/api/rocista/{r2['id']}", json={"status": "odlozeno"}, headers=A).status_code == 200
    _zakazi(k, pid, 40)
    assert k.patch(f"/api/rocista/{r2['id']}", json={"status": "zakazano"}, headers=A).status_code == 409

    assert [(x["metadata"]["polja"], x["metadata"]["prethodno"]["status"], x["metadata"]["novo"]["status"]) for x in _izmene(b, r1["id"])] == [
        (["napomena"], "zakazano", "zakazano"), (["status"], "zakazano", "odrzano")]
    assert [(x["metadata"]["prethodno"]["status"], x["metadata"]["novo"]["status"]) for x in _izmene(b, r2["id"])] == [
        ("zakazano", "odlozeno")]
    assert not [x for x in b.tabele.get("audit_immutable", []) if x["user_id"] == "uid-B"]
    assert next(x for x in b.tabele["rocista"] if x["id"] == r1["id"])["status"] == "odrzano"


def test_pad_audita_vraca_izmenu_i_kaze_istinu(lanac, monkeypatch):
    """Fail-closed (kao `routers/sporna_tacka.py`): bez zapisa istorije izmena ne ostaje — 503 i red je kakav je bio."""
    import shared.audit_immutable as AUD
    k, b = lanac
    pid = _predmet(k)
    r1 = _zakazi(k, pid, 10)
    orig = AUD.log_action

    async def _pad(action, *a, **kw):
        return None if action == "rociste_izmena" else await orig(action, *a, **kw)
    monkeypatch.setattr(AUD, "log_action", _pad)
    r = k.patch(f"/api/rocista/{r1['id']}", json={"status": "otkazano", "datum": (_danas_beograd() + timedelta(days=15)).isoformat()},
                headers=A)
    assert r.status_code == 503, r.text            # detalj 5xx zamenjuje globalni handler generičkom porukom
    red = next(x for x in b.tabele["rocista"] if x["id"] == r1["id"])
    assert ((red.get("status") or "zakazano"), red["datum"]) == ("zakazano", r1["datum"])
    assert _izmene(b, r1["id"]) == []


def test_bez_if_updated_at_istovremena_izmena_ne_daje_netacnu_istoriju(lanac, monkeypatch):
    """Legacy/API poziv bez `if_updated_at`: drugi tab upiše „održano“ između čitanja i upisa → 409, ništa prepisano,
    nijedan zapis sa netačnim „prethodno“."""
    k, b = lanac
    pid = _predmet(k)
    r1 = _zakazi(k, pid, 10)
    assert k.patch(f"/api/rocista/{r1['id']}", json={"napomena": "prva"}, headers=A).status_code == 200   # updated_at postoji
    pravi = b.table

    def table(ime):
        q = pravi(ime)
        if ime == "rocista":
            upd = q.update

            def update(polja, *a, **kw):
                red = next(x for x in b.tabele["rocista"] if x["id"] == r1["id"])
                red.update({"status": "odrzano", "updated_at": "drugi-tab"})    # drugi tab, posle našeg čitanja
                return upd(polja, *a, **kw)
            q.update = update
        return q
    monkeypatch.setattr(b, "table", table)
    r = k.patch(f"/api/rocista/{r1['id']}", json={"status": "otkazano"}, headers=A)
    monkeypatch.setattr(b, "table", pravi)
    assert r.status_code == 409, r.text
    assert next(x for x in b.tabele["rocista"] if x["id"] == r1["id"])["status"] == "odrzano"
    assert [x["metadata"]["polja"] for x in _izmene(b, r1["id"])] == [["napomena"]]
