# -*- coding: utf-8 -*-
"""OSB003 Task 1 — pokušaj da se obori ispravka c148d342 (Smart Intake → tvrdnje) kroz STVARNE rute.

Isti harness i isti tok kao tests/test_osb002_solo_tok.py (stvarne rute, stvaran intake worker, stvaran
dispečer, baza u memoriji sa jedinstvenošću i DEFAULT-ima iz migracija). Simulirani su samo modeli i
embedding/Pinecone. Svaki test ostavlja trajno stanje i proverava ga posle napada.
"""
import io

import pytest

from tests.ns006_fake import dispecuj
from tests.test_osb002_solo_tok import (  # noqa: F401 — `solo` je pytest fixture
    A, B, _do_kraja_dogadjaja, _novi_predmet, _otpremi, _pdf, _prijem_dokumenta, _radnik, solo,
)


def _ai_tvrdnje(b, dok_id):
    return [d for d in b.tabele["predmet_dokazi"] if d.get("dokument_id") == dok_id]


def test_privremeni_pad_upisa_tvrdnji_ne_gubi_tvrdnje_trajno(solo):
    """Invarijanta: prihvaćen dokument ne sme tiho da izgubi tvrdnje. Upis u predmet_dokazi padne JEDNOM
    (prolazna greška baze) — posle ponovnog pokušaja događaja tvrdnje moraju postojati."""
    k, b = solo
    _, pid = _novi_predmet(k, b)
    _prijem_dokumenta(k, b, pid)
    dok = next(d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid)
    b.greske["predmet_dokazi"] = Exception('{"code": "57014", "message": "canceling statement due to statement timeout"}')
    dispecuj()                                   # prva isporuka: upis tvrdnji pada
    del b.greske["predmet_dokazi"]
    for e in b.tabele["events"]:                 # backoff istekao — ponovna isporuka
        e["claimed_at"] = None
        e["next_attempt_at"] = None if "next_attempt_at" in e else None
    for _ in range(5):
        dispecuj()
    assert _ai_tvrdnje(b, dok["id"]), "tvrdnje su trajno izgubljene posle jedne prolazne greške"
    assert any("17.03.2025" in d["tvrdnja"] for d in _ai_tvrdnje(b, dok["id"]))
    # i bez duplikata
    vrednosti = [d["tvrdnja"] for d in _ai_tvrdnje(b, dok["id"])]
    assert len(vrednosti) == len(set(vrednosti)), vrednosti


def _pdf2():
    return _pdf(["POSTA SRBIJE - DOSTAVNICA", "Broj posiljke: RR 123456789 RS",
                 "Primalac: Marko Petrovic, Beograd, ulica Nemanjina 4",
                 "Posiljka je urucena primaocu dana 25.03.2025. godine.",
                 "Posiljalac: Gradnja Invest DOO Beograd, pravna sluzba",
                 "Potpis primaoca i dostavljaca nalaze se na poledjini."])


def test_dva_dokumenta_u_jednom_slanju_svaki_svoje_tvrdnje(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    r = k.post("/api/smart-intake/documents", headers=A,
               files=[("files", ("Resenje.pdf", _pdf(), "application/pdf")), ("files", ("Dostavnica.pdf", _pdf2(), "application/pdf"))])
    assert r.status_code == 202 and [x["ok"] for x in r.json()["rezultati"]] == [True, True], r.text
    jids = [x["job_id"] for x in r.json()["rezultati"]]
    assert len(set(jids)) == 2
    while _radnik():
        pass
    for jid in jids:
        if next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)["status"] == "awaiting_review":
            assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=A).status_code == 200
        assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).status_code == 200
    _do_kraja_dogadjaja(b)
    doks = {d["naziv_fajla"]: d for d in b.tabele["predmet_dokumenti"]}
    assert set(doks) == {"Resenje.pdf", "Dostavnica.pdf"}
    t1, t2 = _ai_tvrdnje(b, doks["Resenje.pdf"]["id"]), _ai_tvrdnje(b, doks["Dostavnica.pdf"]["id"])
    assert t1 and t2
    assert all("17.03.2025" in x["tvrdnja"] for x in t1) and all("25.03.2025" in x["tvrdnja"] for x in t2)
    assert all(x["predmet_id"] == pid and x["user_id"] == "uid-A" for x in t1 + t2)
    assert all(x.get("izvor_tvrdnje") == "ai_klasifikacija" for x in t1 + t2)          # nikad „potvrdio advokat"
    assert sorted(d["redni_broj"] for d in doks.values()) == [1, 2]
    assert all(d.get("klasifikovan_at") for d in doks.values())


def test_istovremena_finalizacija_drugi_poziv_ne_pravi_nista(solo):
    """Atomsko zauzimanje je u SQL-u (claim_intake_finalize, migracija 092/095). Ovde: dok prvi poziv drži
    zauzeće (svež finalizing_at), drugi dobija 409 i ne upisuje ništa; posle završetka vraća already_finalized."""
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid = _otpremi(k, _pdf()).json()["rezultati"][0]["job_id"]
    assert _radnik() is True
    if b.tabele["intake_jobs"][0]["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=A).status_code == 200
    from datetime import datetime, timezone
    b.tabele["intake_jobs"][0]["finalizing_at"] = datetime.now(timezone.utc).isoformat()   # „prvi" poziv u toku
    drugi = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    assert drugi.status_code == 409 and b.tabele["predmet_dokumenti"] == []
    b.tabele["intake_jobs"][0]["finalizing_at"] = None
    prvi = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    ponovo = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    assert prvi.status_code == 200 and ponovo.status_code == 200 and ponovo.json().get("already_finalized") is True
    assert len(b.tabele["predmet_dokumenti"]) == 1


def test_legitimno_klasifikovan_dokument_se_ne_klasifikuje_ponovo(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    _prijem_dokumenta(k, b, pid)
    _do_kraja_dogadjaja(b)
    dok = b.tabele["predmet_dokumenti"][0]
    pre = [dict(x) for x in _ai_tvrdnje(b, dok["id"])]
    assert pre and dok.get("klasifikovan_at")
    import asyncio
    from services.event_bus import EventType, emit_durable
    asyncio.run(emit_durable(EventType.NEW_EVIDENCE_REGISTERED, "uid-A", pid, {"dokument_id": dok["id"], "naziv": "x", "trigger": "test"}))
    _do_kraja_dogadjaja(b)
    posle = _ai_tvrdnje(b, dok["id"])
    assert [x["id"] for x in posle] == [x["id"] for x in pre]
    c = [x for x in b.tabele["case_evolution_consequences"] if x["consequence_name"] == "evidence_classification"]
    assert any(x.get("result_ref") == "skipped_already_classified" for x in c)


def test_pad_upisa_znaka_posle_tvrdnji_preostali_prozor(solo):
    """Preostali prozor posle ispravke: tvrdnje upisane, pa padne JEDINI sledeći upis (`klasifikovan_at`).
    Posledica se ponavlja (znak prazan) i tvrdnje se upisuju ponovo. Meri se i beleži: duplikat je
    VIDLJIV, ne tih gubitak. Ne uvodi se drugi sistem idempotencije (shared/evidence_write.py INVARIANT 4)."""
    k, b = solo
    _, pid = _novi_predmet(k, b)
    _prijem_dokumenta(k, b, pid)
    dok = b.tabele["predmet_dokumenti"][0]
    import tests.ns005_harness as h5
    orig = h5._Upit.execute
    stanje = {"pao": False}

    def _pad_jednom(self):
        if (self.t == "predmet_dokumenti" and self.radnja[0] == "update" and set(self.radnja[1] or {}) == {"klasifikovan_at"}
                and not stanje["pao"]):
            stanje["pao"] = True
            raise Exception('{"code": "57014", "message": "statement timeout"}')
        return orig(self)
    h5._Upit.execute = _pad_jednom
    try:
        dispecuj()
    finally:
        h5._Upit.execute = orig
    assert stanje["pao"]
    for e in b.tabele["events"]:
        e["claimed_at"] = None
    _do_kraja_dogadjaja(b)
    t = _ai_tvrdnje(b, dok["id"])
    assert t, "tvrdnje izgubljene"
    assert b.tabele["predmet_dokumenti"][0].get("klasifikovan_at")
    # Izmereno: 2 reda za 1 tvrdnju (vidljiv duplikat, ne gubitak). Logički identitet (migracija 116:
    # sha256(predmet|verzija|tvrdnja), namerno NIJE UNIQUE) je isti — potrošači po identitetu vide jednu tvrdnju.
    assert len({x["identitet"] for x in t}) == len({x["tvrdnja"] for x in t}), [(x["tvrdnja"], x["identitet"]) for x in t]
    assert all(x["identitet"] for x in t)
