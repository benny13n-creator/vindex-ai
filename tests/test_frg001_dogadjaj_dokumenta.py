# -*- coding: utf-8 -*-
"""FRG001 Task A — BETA-DEF-004: dokument → trajni događaj, kroz STVARNE rute, STVARAN IntakeWorker i STVARAN
dispečer (harness iz tests/test_osb002_solo_tok.py), sa ubacivanjem kvarova na granici dokument/događaj.

Invarijanta: dokument upisan u predmet nikad ne ostaje TIHO i TRAJNO bez svog događaja. Ako upis događaja padne
(ili proces padne posle upisa dokumenta), posao ne sme da izgleda prikačeno, a ponovni pokušaj mora da dovrši
obradu bez dupliranja dokumenta, događaja ili tvrdnji.
"""
from datetime import datetime, timedelta, timezone

from tests.ns006_fake import dispecuj
from tests.test_osb002_solo_tok import (  # noqa: F401 — `solo` je pytest fixture
    A, B, _do_kraja_dogadjaja, _novi_predmet, _otpremi, _pdf, _radnik, solo,
)

PAD_VEZE = '{"code": "08006", "message": "connection failure"}'


def _spreman_posao(k, b, sadrzaj=None, ime="Resenje o otkazu.pdf", h=A):
    r = _otpremi(k, sadrzaj or _pdf(), ime=ime, h=h)
    assert r.status_code == 202, r.text
    jid = r.json()["rezultati"][0]["job_id"]
    assert _radnik() is True
    posao = next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)
    if posao["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=h).status_code == 200
    return jid, posao


def _finalize(k, jid, pid, h=A):
    return k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=h)


def _dogadjaji(b, tip):
    return [e for e in b.tabele["events"] if e["event_type"] == tip]


def _tvrdnje(b, dok_id):
    return [t for t in b.tabele["predmet_dokazi"] if t.get("dokument_id") == dok_id]


def _ubaci_pad_emitovanja(monkeypatch, tip, izuzetak):
    """Obara `emit_durable` samo za jedan tip događaja; ostali prolaze kroz pravu funkciju."""
    import services.event_bus as eb
    pravi = eb.emit_durable

    async def _emit(event_type, *a, **kw):
        if event_type.value == tip:
            raise izuzetak
        return await pravi(event_type, *a, **kw)
    monkeypatch.setattr(eb, "emit_durable", _emit)
    return lambda: monkeypatch.setattr(eb, "emit_durable", pravi)


def _zavrseno_bez_duplikata(k, b, pid, jid):
    """Zajednička završna provera: tačno jedan dokument, jedan događaj po vrsti, tvrdnje postoje, posao prikačen."""
    from routers.smart_intake import _id_dogadjaja_dokaza, _id_prihvatanja_posla
    _do_kraja_dogadjaja(b)
    doks = [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]
    assert len(doks) == 1, doks
    dok = doks[0]
    nov = _dogadjaji(b, "NewEvidenceRegistered")
    assert [e["id"] for e in nov] == [_id_dogadjaja_dokaza(dok["id"])], [(e["id"], e["payload"]) for e in nov]
    prih = _dogadjaji(b, "DocumentAccepted")
    assert [e["id"] for e in prih] == [_id_prihvatanja_posla(jid)]
    assert all(e["predmet_id"] == pid and e["user_id"] == "uid-A" for e in nov + prih)
    assert dok.get("klasifikovan_at") and _tvrdnje(b, dok["id"]), "dokument je ostao bez tvrdnji"
    posao = next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)
    assert posao["predmet_id"] == pid and posao["assimilation_complete"] is True
    return dok


# ── A1/A2: pad upisa događaja posle upisa dokumenta ──────────────────────────────────────────────────────────

def test_pad_upisa_dogadjaja_nije_lazno_zavrsen_i_ponovni_pokusaj_dovrsava(solo):
    """Ranije (BETA-DEF-004): 200, posao „prikačen“, dokument trajno bez tvrdnji, ponovni pokušaj ništa ne menja."""
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid, posao = _spreman_posao(k, b)
    _do_kraja_dogadjaja(b)
    b.greske["events"] = Exception(PAD_VEZE)
    f = _finalize(k, jid, pid)
    del b.greske["events"]
    assert f.status_code == 503, f.text
    # (detalj 5xx odgovora globalni handler zamenjuje opštom porukom; V2 5xx prikazuje kao „ishod nije poznat“)
    assert len(b.tabele["predmet_dokumenti"]) == 1                     # dokument JESTE sačuvan
    assert posao["predmet_id"] is None and not posao["assimilation_complete"]   # ali posao nije „prikačen“
    assert posao["finalizing_at"] is None                              # zauzeće oslobođeno: odmah ponovljivo
    stanje = k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()
    assert stanje["job"]["predmet_id"] is None and stanje["job"]["status"] == "completed"   # V2 opet nudi „Prikači“
    _do_kraja_dogadjaja(b)
    assert b.tabele["predmet_dokazi"] == []                            # bez događaja nema ni tvrdnji (stanje je nepotpuno)

    f2 = _finalize(k, jid, pid)
    assert f2.status_code == 200, f2.text
    _zavrseno_bez_duplikata(k, b, pid, jid)


def test_prekid_procesa_posle_upisa_dokumenta_pa_nastavak(solo, monkeypatch):
    """Proces umre između upisa dokumenta i upisa događaja (ništa se ne hvata). Posle isteka zauzeća (120 s)
    nastavak dovršava isti dokument, u istom predmetu."""
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid, posao = _spreman_posao(k, b)

    class _Prekid(BaseException):
        pass
    vrati = _ubaci_pad_emitovanja(monkeypatch, "NewEvidenceRegistered", _Prekid())
    assert _finalize(k, jid, pid).status_code == 500                    # zahtev je umro usred rada
    vrati()
    assert len(b.tabele["predmet_dokumenti"]) == 1 and _dogadjaji(b, "NewEvidenceRegistered") == []
    assert posao["predmet_id"] is None and posao["finalizing_at"]       # nije prikačen; zauzeće još sveže
    assert _finalize(k, jid, pid).status_code == 409                    # istovremeni/brzi pokušaj: „u toku“
    posao["finalizing_at"] = (datetime.now(timezone.utc) - timedelta(seconds=121)).isoformat()
    f = _finalize(k, jid, pid)
    assert f.status_code == 200, f.text
    _zavrseno_bez_duplikata(k, b, pid, jid)


def test_pad_samo_document_accepted_pa_oporavak_bez_duplog_dogadjaja_dokaza(solo, monkeypatch):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid, posao = _spreman_posao(k, b)
    vrati = _ubaci_pad_emitovanja(monkeypatch, "DocumentAccepted", RuntimeError(PAD_VEZE))
    assert _finalize(k, jid, pid).status_code == 503
    vrati()
    assert len(_dogadjaji(b, "NewEvidenceRegistered")) == 1 and _dogadjaji(b, "DocumentAccepted") == []
    assert posao["predmet_id"] is None
    _do_kraja_dogadjaja(b)                                              # dokaz se klasifikuje već sada
    assert _finalize(k, jid, pid).status_code == 200
    _zavrseno_bez_duplikata(k, b, pid, jid)
    assert next(p for p in b.tabele["predmeti"] if p["id"] == pid)["case_dna"].get("verzija")   # Genome osvežen


def test_baza_pada_i_tokom_oporavka_stanje_ostaje_nepotpuno_i_oporavljivo(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid, posao = _spreman_posao(k, b)
    for _ in range(2):
        b.greske["events"] = Exception(PAD_VEZE)
        assert _finalize(k, jid, pid).status_code == 503
        del b.greske["events"]
        assert len(b.tabele["predmet_dokumenti"]) == 1 and posao["predmet_id"] is None
    assert _finalize(k, jid, pid).status_code == 200
    _zavrseno_bez_duplikata(k, b, pid, jid)


# ── A4: ponavljanje, duplikati, istovremenost ────────────────────────────────────────────────────────────────

def test_identican_zahtev_i_dupla_isporuka_ne_dupliraju_nista(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid, _ = _spreman_posao(k, b)
    assert _finalize(k, jid, pid).status_code == 200
    dok = _zavrseno_bez_duplikata(k, b, pid, jid)
    pre = (len(b.tabele["events"]), len(b.tabele["predmet_dokazi"]), len(b.tabele["predmet_dokumenti"]))
    for _ in range(2):                                                  # identičan zahtev
        r = _finalize(k, jid, pid)
        assert r.status_code == 200 and r.json()["already_finalized"] is True
    for e in b.tabele["events"]:                                        # ponovna isporuka istih događaja
        e["dispatched_at"] = None
        e["claimed_at"] = None
    _do_kraja_dogadjaja(b)
    assert (len(b.tabele["events"]), len(b.tabele["predmet_dokazi"]), len(b.tabele["predmet_dokumenti"])) == pre
    assert _tvrdnje(b, dok["id"])


def test_ponovni_upis_istog_dogadjaja_je_no_op(solo):
    """Stabilan identitet: drugi upis istog NEW_EVIDENCE_REGISTERED (npr. oporavak posle uspešnog upisa) ne pravi red."""
    import asyncio
    from routers.smart_intake import _id_dogadjaja_dokaza
    from services.event_bus import EventType, emit_durable
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid, _ = _spreman_posao(k, b)
    assert _finalize(k, jid, pid).status_code == 200
    dok = b.tabele["predmet_dokumenti"][0]
    pre = len(b.tabele["events"])
    asyncio.run(emit_durable(EventType.NEW_EVIDENCE_REGISTERED, "uid-A", pid, {"dokument_id": dok["id"]},
                             event_id=_id_dogadjaja_dokaza(dok["id"])))
    assert len(b.tabele["events"]) == pre


def test_dogadjaj_postoji_ali_posledica_padne_pa_dispecer_oporavlja(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid, _ = _spreman_posao(k, b)
    assert _finalize(k, jid, pid).status_code == 200
    b.greske["predmet_dokazi"] = Exception('{"code": "57014", "message": "statement timeout"}')
    dispecuj()
    del b.greske["predmet_dokazi"]
    ev = _dogadjaji(b, "NewEvidenceRegistered")[0]
    assert not ev.get("dispatched_at") and ev.get("last_error")         # nije lažno završeno; ostaje u retry-ju
    assert not b.tabele["predmet_dokumenti"][0].get("klasifikovan_at")
    ev["claimed_at"] = None
    _zavrseno_bez_duplikata(k, b, pid, jid)


def test_istovremena_finalizacija_drugi_poziv_409_bez_upisa(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid, posao = _spreman_posao(k, b)
    posao["finalizing_at"] = datetime.now(timezone.utc).isoformat()      # prvi poziv drži zauzeće
    r = _finalize(k, jid, pid)
    assert r.status_code == 409
    assert b.tabele["predmet_dokumenti"] == [] and _dogadjaji(b, "NewEvidenceRegistered") == []


# ── A4: granice korisnika i predmeta ─────────────────────────────────────────────────────────────────────────

def test_tudj_korisnik_ne_moze_da_dovrsi_niti_pokrene_dogadjaj_za_tudj_dokument(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid, posao = _spreman_posao(k, b)
    b.greske["events"] = Exception(PAD_VEZE)
    assert _finalize(k, jid, pid).status_code == 503
    del b.greske["events"]
    pb = k.post("/api/predmeti", json={"naziv": "Predmet korisnika B"}, headers=B).json()["predmet"]["id"]
    assert _finalize(k, jid, pb, h=B).status_code == 404                 # tuđ posao
    assert _finalize(k, jid, pid, h=B).status_code == 404
    assert _dogadjaji(b, "NewEvidenceRegistered") == []                  # B nije izazvao nijedan događaj
    # B šalje ISTI sadržaj u SVOJ predmet: njegov dokument je zaseban; A-in neklasifikovan dokument se ne dira.
    jb, _ = _spreman_posao(k, b, h=B)
    assert _finalize(k, jb, pb, h=B).status_code == 200
    a_dok = next(d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid)
    for e in _dogadjaji(b, "NewEvidenceRegistered"):
        assert e["payload"]["dokument_id"] != a_dok["id"] and e["predmet_id"] == pb and e["user_id"] == "uid-B"
    assert _finalize(k, jid, pid).status_code == 200                     # A se oporavlja nezavisno
    _do_kraja_dogadjaja(b)
    assert _tvrdnje(b, a_dok["id"])
    for e in b.tabele["events"]:
        if e["event_type"] == "NewEvidenceRegistered":
            d = next(x for x in b.tabele["predmet_dokumenti"] if x["id"] == e["payload"]["dokument_id"])
            assert d["predmet_id"] == e["predmet_id"] and d["user_id"] == e["user_id"]


def test_nastavak_ostaje_u_predmetu_gde_je_dokument_upisan(solo):
    """Posle nepotpunog prvog pokušaja u predmet P1, pokušaj sa P2 NE premešta dokument i NE emituje događaj za P2:
    postojeći nastavak (`source_intake_job_id`) vraća isti P1, a događaj nosi predmet u kome dokument stvarno jeste."""
    k, b = solo
    _, p1 = _novi_predmet(k, b)
    p2 = k.post("/api/predmeti", json={"naziv": "Drugi predmet"}, headers=A).json()["predmet"]["id"]
    jid, _ = _spreman_posao(k, b)
    b.greske["events"] = Exception(PAD_VEZE)
    assert _finalize(k, jid, p1).status_code == 503
    del b.greske["events"]
    r = _finalize(k, jid, p2)
    assert r.status_code == 200 and r.json()["predmet_id"] == p1          # V2 ovo prikazuje kao „drugi predmet“
    assert [d["predmet_id"] for d in b.tabele["predmet_dokumenti"]] == [p1]
    assert {e["predmet_id"] for e in b.tabele["events"] if e["event_type"] in ("NewEvidenceRegistered", "DocumentAccepted")} == {p1}


# ── Zapisi nastali PRE ispravke ──────────────────────────────────────────────────────────────────────────────

def test_zapis_pre_ispravke_nije_automatski_oporavljen_ali_je_vidljiv(solo):
    """Posao koji je stari kod već obeležio kao prikačen, a dokument nema događaj: brzi izlaz ga ne dira (nema
    automatskog oporavka), ali V2 analiza dokument prikazuje kao „nije klasifikovan“ — stanje nije tiho."""
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid, posao = _spreman_posao(k, b)
    assert _finalize(k, jid, pid).status_code == 200
    b.tabele["events"].clear()                                           # stari kod: događaj izgubljen, posao „gotov“
    dok = b.tabele["predmet_dokumenti"][0]
    r = _finalize(k, jid, pid)
    assert r.status_code == 200 and r.json()["already_finalized"] is True and b.tabele["events"] == []
    ziv = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A).json()
    stanja = {d["id"]: d["klasifikacija"]["stanje"] for d in ziv["dokazi"]["dokumenti"]}
    assert stanja[dok["id"]] == "NIJE_KLASIFIKOVAN"
