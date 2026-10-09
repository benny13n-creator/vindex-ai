"""NS007 Task 12 — API pregleda radnih proizvoda.

Lista/detalj: samo vlasnik; filteri; tuđ / nepostojeći / neispravan id → bajt-identičan 404. Prihvati/odbaci: SAMO
odluka o pregledu (READY_FOR_REVIEW → ACCEPTED/REJECTED, ko/kada/razlog) — nijedan upis u druge tabele (Case Actions,
staging_memory, obaveštenja, mejl); drugi put → 409; nije na pregledu → 409. Mrežno ponavljanje istog zahteva sa
istim `Idempotency-Key` → jedan prelaz i isti odgovor.
"""
import uuid

import pytest

import tests.ns007_fake as f7

PA = "aaaaaaaa-1111-4000-8000-00000000000a"
PB = "bbbbbbbb-1111-4000-8000-00000000000b"
WA, WA2, WB = (str(uuid.UUID(int=i)) for i in (11, 12, 13))


def _posao(wid, uid, pid, status="READY_FOR_REVIEW", work_type="HEARING_PREP", naslov="Priprema za ročište"):
    gotov = status in ("READY_FOR_REVIEW", "ACCEPTED", "REJECTED")
    return {"id": wid, "user_id": uid, "predmet_id": pid, "agent_type": "hearing_prep", "work_type": work_type,
            "trigger_type": "ROCISTE", "trigger_ref": "r", "dedupe_key": f"k-{wid}", "reason": "Ročište sutra",
            "cost_class": "PAID", "budget_key": f"solo:{uid}", "status": status, "title": naslov if gotov else None,
            "summary": "Sažetak" if gotov else None, "content_json": {"tajno": f"sadržaj {uid}"} if gotov else None,
            "quality_state": "AI_PREPARED_FOR_REVIEW" if gotov else None, "ready_at": "2026-10-10T03:00:00+00:00" if gotov else None,
            "source_refs": [{"tip": "rociste", "id": "r"}], "updated_at": "2026-10-10T03:00:00+00:00"}


@pytest.fixture
def svet(monkeypatch):
    k, baza = f7.pripremi(monkeypatch, {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Petrović protiv Gradnja Invest DOO", "status": "aktivan"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Tajni predmet B", "status": "aktivan"}],
        "autonomy_work_items": [_posao(WA, "uid-A", PA), _posao(WA2, "uid-A", PA, status="SUPERSEDED"),
                                _posao(WB, "uid-B", PB, naslov="Tajna priprema B")],
        "case_actions": [], "staging_memory": [], "notifications": []})
    yield k, baza
    f7.ocisti()


def H(ko="A", kljuc=None):
    h = f7.zaglavlje(ko)
    if kljuc:
        h["Idempotency-Key"] = kljuc
    return h


def test_lista_samo_svoje_i_filteri(svet):
    k, _ = svet
    r = k.get("/api/autonomy/work-items", headers=H("A")).json()
    assert [s["id"] for s in r["stavke"]] == [WA] and r["stavke"][0]["predmet_naziv"] == "Petrović protiv Gradnja Invest DOO"
    assert "content_json" not in r["stavke"][0], "lista ne nosi sadržaj"
    assert [s["id"] for s in k.get("/api/autonomy/work-items?status=SUPERSEDED", headers=H("A")).json()["stavke"]] == [WA2]
    assert k.get(f"/api/autonomy/work-items?matter_id={PB}", headers=H("A")).json()["stavke"] == [], "tuđ predmet kao filter ne pomaže"
    assert k.get("/api/autonomy/work-items?work_type=PRECEDENT_IMPACT", headers=H("A")).json()["stavke"] == []
    for upit in ("status=SVE", "work_type=X", "matter_id=nije-uuid"):
        assert k.get(f"/api/autonomy/work-items?{upit}", headers=H("A")).status_code == 400
    b = k.get("/api/autonomy/work-items", headers=H("B")).json()
    assert [s["id"] for s in b["stavke"]] == [WB] and "Petrović" not in str(b)
    assert k.get("/api/autonomy/work-items").status_code == 401


def test_detalj_i_isti_404(svet):
    k, _ = svet
    d = k.get(f"/api/autonomy/work-items/{WA}", headers=H("A")).json()
    assert d["content_json"] == {"tajno": "sadržaj uid-A"} and d["source_refs"] and d["reason"] == "Ročište sutra"
    odgovori = [k.get(f"/api/autonomy/work-items/{w}", headers=H("A")) for w in (WB, str(uuid.uuid4()), "nije-uuid")]
    assert all(r.status_code == 404 for r in odgovori) and len({r.content for r in odgovori}) == 1
    assert "Tajna priprema B" not in odgovori[0].text and "uid-B" not in odgovori[0].text


def _drugi_upisi(baza, pre):
    return {z["tabela"] for z in baza.dnevnik[pre:] if z["radnja"] in ("insert", "update", "upsert", "delete")} - {
        "autonomy_work_items", "v2_mutation_idempotency", "audit_immutable"}


def test_prihvati_je_samo_odluka_o_pregledu(svet):
    k, baza = svet
    pre = len(baza.dnevnik)
    r = k.post(f"/api/autonomy/work-items/{WA}/accept", headers=H("A"))
    assert r.status_code == 200 and r.json()["status"] == "ACCEPTED"
    red = next(x for x in baza.tabele["autonomy_work_items"] if x["id"] == WA)
    assert red["status"] == "ACCEPTED" and red["reviewed_by"] == "uid-A" and red["resolved_at"]
    assert _drugi_upisi(baza, pre) == set(), "prihvatanje ne sme da dira Case Actions, staging, obaveštenja, mejl"
    assert k.post(f"/api/autonomy/work-items/{WA}/accept", headers=H("A")).status_code == 409
    assert k.post(f"/api/autonomy/work-items/{WA}/reject", headers=H("A")).status_code == 409


def test_odbaci_sa_razlogom_i_granice(svet):
    k, baza = svet
    assert k.post(f"/api/autonomy/work-items/{WA}/reject", headers=H("A"), json={"razlog": "x" * 1001}).status_code == 422
    r = k.post(f"/api/autonomy/work-items/{WA}/reject", headers=H("A"), json={"razlog": "Ročište je odloženo telefonom."})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    red = next(x for x in baza.tabele["autonomy_work_items"] if x["id"] == WA)
    assert red["review_note"] == "Ročište je odloženo telefonom."


def test_tudj_ili_nije_na_pregledu(svet):
    k, baza = svet
    for put in ("accept", "reject"):
        r = k.post(f"/api/autonomy/work-items/{WB}/{put}", headers=H("A"))
        assert r.status_code == 404 and "Tajna" not in r.text
    assert next(x for x in baza.tabele["autonomy_work_items"] if x["id"] == WB)["status"] == "READY_FOR_REVIEW"
    assert k.post(f"/api/autonomy/work-items/{WA2}/accept", headers=H("A")).status_code == 409, "zastareo rad se ne prihvata"
    assert k.post("/api/autonomy/work-items/nije-uuid/accept", headers=H("A")).status_code == 404


def test_mrezno_ponavljanje_jedan_prelaz(svet):
    k, baza = svet
    kljuc = str(uuid.uuid4())
    r1 = k.post(f"/api/autonomy/work-items/{WA}/accept", headers=H("A", kljuc))
    r2 = k.post(f"/api/autonomy/work-items/{WA}/accept", headers=H("A", kljuc))
    assert r1.status_code == 200 and r2.status_code == 200 and r1.json() == r2.json()
    prelazi = [z for z in baza.dnevnik if z["tabela"] == "autonomy_work_items" and z["radnja"] == "update"]
    assert len(prelazi) == 1, "dva fizička zahteva → jedan prelaz stanja"


def test_ostecen_red_ne_otkriva_naziv_tudjeg_predmeta(svet):
    """Odbrana u dubinu: rad korisnika A koji (greškom) pokazuje na predmet B ne sme da otkrije naziv predmeta B."""
    k, baza = svet
    baza.tabele["autonomy_work_items"].append(_posao(str(uuid.UUID(int=99)), "uid-A", PB))
    r = k.get("/api/autonomy/work-items", headers=H("A"))
    assert "Tajni predmet B" not in r.text
    d = k.get(f"/api/autonomy/work-items/{uuid.UUID(int=99)}", headers=H("A"))
    assert "Tajni predmet B" not in d.text
