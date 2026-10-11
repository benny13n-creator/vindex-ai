# -*- coding: utf-8 -*-
"""FRI001 Task 3 — COI lanac, kroz STVARNE rute, STVARAN IntakeWorker, STVARAN dispečer i STVARNU proveru sukoba:

Smart Intake finalize (stari čarobnjak šalje `klijent_strana`) → NEW_CLIENT_LINKED (stabilan `event_id` po poslu)
→ dispatch_pending_events → case_evolution._consequence_conflict_check → routers/intake._run_conflict_check
→ proactive_alerts → GET /api/briefing/alerts (ono što advokat čita).

V2 prikačivanje (`{predmet_id}` bez `klijent_strana`) NE emituje događaj — `COI_NOT_APPLICABLE` (test ispod).
Do FRG001 se ovaj događaj u produkciji nije upisivao (supabase-py `insert()` nema `ignore_duplicates`), pa je sve
ispod ponašanje koje se posle deploy-a PRVI PUT aktivira.
"""
import asyncio

from tests.ns006_fake import dispecuj
from tests.test_osb002_solo_tok import (  # noqa: F401 — `solo` je pytest fixture
    A, B, _do_kraja_dogadjaja, _novi_predmet, _otpremi, _pdf, _radnik, solo,
)

PAD = Exception('{"code": "57014", "message": "statement timeout"}')


def _posao(k, b, h=A):
    r = _otpremi(k, _pdf(), h=h)
    assert r.status_code == 202, r.text
    jid = r.json()["rezultati"][0]["job_id"]
    assert _radnik() is True
    posao = next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)
    if posao["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=h).status_code == 200
    return jid


def _finalize_carobnjak(k, jid, h=A, strana="plaintiff"):
    """Kao stari čarobnjak (static/vindex.js): bez predmet_id, sa `klijent_strana`."""
    return k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"klijent_strana": strana}, headers=h)


def _coi_dogadjaji(b):
    return [e for e in b.tabele["events"] if e["event_type"] == "NewClientLinked"]


def _coi_upozorenja(b, uid="uid-A"):
    return [a for a in b.tabele["proactive_alerts"] if a["tip"] == "sukob_interesa" and a["user_id"] == uid]


def _posledica(b):
    return [c for c in b.tabele["case_evolution_consequences"] if c["consequence_name"] == "conflict_check"]


def _postojeci_klijent(k, b, ime, prezime, uloga="tuzilac", h=A, naziv="Raniji predmet"):
    kl = k.post("/klijenti", json={"ime": ime, "prezime": prezime}, headers=h)
    assert kl.status_code == 200, kl.text
    kid = kl.json()["klijent"]["id"]
    pid = k.post("/api/predmeti", json={"naziv": naziv}, headers=h).json()["predmet"]["id"]
    v = k.post(f"/api/predmeti/{pid}/confirm-links", json={"klijent_ids": [kid], "uloga": uloga}, headers=h)
    assert v.status_code == 200, v.text
    return kid, pid


def _upozorenja_api(k, h=A):
    r = k.get("/api/briefing/alerts", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    return d.get("alerts", d) if isinstance(d, dict) else d


# 0 — V2 put ne zakazuje COI
def test_v2_prikacivanje_ne_emituje_coi(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid = _posao(k, b)
    r = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    assert r.status_code == 200 and r.json()["coi_status"] == "COI_NOT_APPLICABLE"
    assert _coi_dogadjaji(b) == []


# 1
def test_nema_sukoba_nije_predstavljen_kao_cist_pre_provere(solo):
    k, b = solo
    jid = _posao(k, b)
    r = _finalize_carobnjak(k, jid)
    assert r.status_code == 200, r.text
    assert r.json()["coi_status"] == "COI_PENDING"            # zakazano, NE „nema sukoba“
    assert len(_coi_dogadjaji(b)) == 1
    _do_kraja_dogadjaja(b)
    assert [c["status"] for c in _posledica(b)] == ["completed"]
    assert _coi_upozorenja(b) == []


# 2 + 13
def test_moguc_sukob_nije_predstavljen_kao_pravno_potvrdjen(solo):
    k, b = solo
    _postojeci_klijent(k, b, "Gradnja", "Invest DOO", uloga="tuzilac")    # protivna strana je vaš klijent
    jid = _posao(k, b)
    assert _finalize_carobnjak(k, jid).status_code == 200
    _do_kraja_dogadjaja(b)
    up = _coi_upozorenja(b)
    assert len(up) == 1, up
    tekst = (up[0]["naslov"] + " " + up[0]["opis"]).lower()
    assert "mogu" in tekst and "provera" in tekst                     # „mogući“, „potrebna provera“
    assert "ne možete zastupati" not in tekst and "postoji blokirajuci" not in tekst
    assert up[0]["urgentnost"] == "hitna"                            # ozbiljnost podudaranja ostaje
    api = _upozorenja_api(k)
    assert any(a.get("tip") == "sukob_interesa" for a in api)        # vidi ga TAČAN advokat


# 3
def test_provera_ne_moze_da_se_izvrsi_nije_cisto(solo):
    k, b = solo
    jid = _posao(k, b)
    assert _finalize_carobnjak(k, jid).status_code == 200
    b.greske["klijenti"] = PAD
    dispecuj()
    del b.greske["klijenti"]
    ev = _coi_dogadjaji(b)[0]
    assert not ev.get("dispatched_at") and "nije izvršena" in (ev.get("last_error") or "")
    assert all(c["status"] != "completed" for c in _posledica(b))     # UNKNOWN nije postao CLEAR
    assert _coi_upozorenja(b) == []
    ev["claimed_at"] = None
    _do_kraja_dogadjaja(b)                                           # posle oporavka provera se izvrši
    assert [c["status"] for c in _posledica(b)] == ["completed"]


# 4
def test_bez_podataka_o_stranci_nema_dogadjaja_ni_lazne_provere(solo, monkeypatch):
    """Advokat bira stranu (tužilac), a dokument tužioca ne navodi: nema imena → nema događaja, `COI_NOT_APPLICABLE`
    (ne „čisto“). Provera se ne izmišlja nad praznim imenom."""
    import shared.intake_extract as ex

    async def _samo_tuzeni(tekst):
        return {"defendant": ("Gradnja Invest DOO Beograd", 0.6)}
    monkeypatch.setattr(ex, "extract_free_text_entities", _samo_tuzeni)
    k, b = solo
    jid = _posao(k, b)
    r = _finalize_carobnjak(k, jid)
    assert r.status_code == 200, r.text
    assert r.json()["coi_status"] == "COI_NOT_APPLICABLE" and _coi_dogadjaji(b) == []


# 5 + 14
def test_upisan_a_neisporucen_dogadjaj_ne_gubi_zakasneli_rezultat(solo):
    k, b = solo
    _postojeci_klijent(k, b, "Gradnja", "Invest DOO")
    jid = _posao(k, b)
    assert _finalize_carobnjak(k, jid).status_code == 200
    assert _coi_dogadjaji(b) and _coi_upozorenja(b) == []            # još nije isporučen
    _do_kraja_dogadjaja(b)                                           # kasnije: rezultat stiže
    assert len(_coi_upozorenja(b)) == 1


# 6 + 7
def test_ponovna_isporuka_i_dupli_upis_ne_dupliraju_upozorenje(solo):
    from services.event_bus import EventType, emit_durable
    k, b = solo
    _postojeci_klijent(k, b, "Gradnja", "Invest DOO")
    jid = _posao(k, b)
    assert _finalize_carobnjak(k, jid).status_code == 200
    r2 = _finalize_carobnjak(k, jid)
    assert r2.status_code == 200 and r2.json().get("already_finalized") is True
    ev = _coi_dogadjaji(b)
    assert len(ev) == 1
    asyncio.run(emit_durable(EventType.NEW_CLIENT_LINKED, "uid-A", ev[0]["predmet_id"], ev[0]["payload"],
                             event_id=ev[0]["id"]))                  # dupli upis istog događaja
    assert len(_coi_dogadjaji(b)) == 1
    _do_kraja_dogadjaja(b)
    for e in b.tabele["events"]:
        e["dispatched_at"] = None
        e["claimed_at"] = None
    _do_kraja_dogadjaja(b)                                           # replay
    assert len(_coi_upozorenja(b)) == 1


# 8
def test_istovremena_obrada_istog_dogadjaja_jedna_posledica(solo):
    from services.case_evolution import handle_case_changed
    from services.event_bus import Event, EventType
    k, b = solo
    _postojeci_klijent(k, b, "Gradnja", "Invest DOO")
    jid = _posao(k, b)
    assert _finalize_carobnjak(k, jid).status_code == 200
    red = _coi_dogadjaji(b)[0]
    dog = Event(type=EventType.NEW_CLIENT_LINKED, user_id=red["user_id"], predmet_id=red["predmet_id"],
                payload=red["payload"], event_id=red["id"])

    async def _dva():
        return await asyncio.gather(handle_case_changed(dog), handle_case_changed(dog), return_exceptions=True)
    asyncio.run(_dva())
    assert len(_coi_upozorenja(b)) == 1 and len(_posledica(b)) == 1


# 9
def test_pad_posle_delimicnog_rezultata_ne_duplira_upozorenje(solo, monkeypatch):
    """Upozorenje je upisano, ali beleženje završene posledice padne (prekid). Ponovna obrada posle isteka
    zastarelosti ne sme da napravi drugo isto upozorenje."""
    import services.case_evolution as ce
    k, b = solo
    _postojeci_klijent(k, b, "Gradnja", "Invest DOO")
    jid = _posao(k, b)
    assert _finalize_carobnjak(k, jid).status_code == 200
    pravi = ce._mark_completed if hasattr(ce, "_mark_completed") else None
    assert pravi is not None

    async def _pad(*a, **kw):
        raise RuntimeError("prekid posle upisa upozorenja")
    monkeypatch.setattr(ce, "_mark_completed", _pad)
    dispecuj()
    assert len(_coi_upozorenja(b)) == 1
    monkeypatch.setattr(ce, "_mark_completed", pravi)
    for c in b.tabele["case_evolution_consequences"]:                # „zaglavljene“ posledice → zastarele
        if c.get("status") != "completed":
            c["updated_at"] = "2000-01-01T00:00:00+00:00"
    for e in b.tabele["events"]:
        e["claimed_at"] = None
    _do_kraja_dogadjaja(b)
    assert [c["status"] for c in _posledica(b)] == ["completed"]
    assert len(_coi_upozorenja(b)) == 1, [a["opis"] for a in _coi_upozorenja(b)]


# 10 + 11
def test_tudji_klijenti_i_predmeti_ne_ulaze_u_proveru_niti_upozorenja(solo):
    k, b = solo
    _postojeci_klijent(k, b, "Gradnja", "Invest DOO", h=B, naziv="Tajni predmet korisnika B")
    jid = _posao(k, b, h=A)
    assert _finalize_carobnjak(k, jid, h=A).status_code == 200
    _do_kraja_dogadjaja(b)
    assert _coi_upozorenja(b, "uid-A") == []                         # B-ov klijent nije A-ov sukob
    assert _coi_upozorenja(b, "uid-B") == []
    assert not any("Tajni predmet" in (a.get("opis") or "") for a in b.tabele["proactive_alerts"])
    assert _upozorenja_api(k, h=B) == [] or all(a.get("tip") != "sukob_interesa" for a in _upozorenja_api(k, h=B))
    jb = _posao(k, b, h=B)
    assert k.post(f"/api/smart-intake/jobs/{jb}/finalize", json={"klijent_strana": "plaintiff"}, headers=A).status_code == 404


# 12
def test_vise_slicnih_imena_sva_kandidati_bez_pogadjanja(solo):
    k, b = solo
    _postojeci_klijent(k, b, "Gradnja", "Invest DOO", naziv="Prvi")
    _postojeci_klijent(k, b, "Gradnja", "Invest d.o.o.", naziv="Drugi")
    jid = _posao(k, b)
    assert _finalize_carobnjak(k, jid).status_code == 200
    _do_kraja_dogadjaja(b)
    up = _coi_upozorenja(b)
    assert len(up) == 1
    assert "Prvi" in up[0]["opis"] and "Drugi" in up[0]["opis"]       # oba kandidata, nijedan izabran


def test_posledica_ne_pokrece_spoljnu_pravnu_radnju(solo):
    k, b = solo
    _postojeci_klijent(k, b, "Gradnja", "Invest DOO")
    jid = _posao(k, b)
    assert _finalize_carobnjak(k, jid).status_code == 200
    pre = len(b.dnevnik)
    _do_kraja_dogadjaja(b)
    pisano = {d["tabela"] for d in b.dnevnik[pre:] if d.get("radnja") in ("insert", "upsert", "update", "delete")}
    dozvoljeno = {"events", "case_evolution_consequences", "proactive_alerts", "audit_immutable", "predmet_dokazi",
                  "predmet_dokumenti", "predmeti", "predmet_hronologija", "predmet_genome_history", "case_actions",
                  "predmet_issues", "predmet_contradictions", "predmet_contradiction_claims", "notifications",
                  "staging_memory", "predmet_istorija"}
    assert pisano <= dozvoljeno, pisano - dozvoljeno
    assert not {"email_queue", "sms_queue", "podnesci", "autonomy_work_items"} & pisano
