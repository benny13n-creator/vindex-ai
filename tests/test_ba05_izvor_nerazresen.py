# -*- coding: utf-8 -*-
"""PR #62 završna kapija — nerazrešen identitet izvora ne sme da završi posledicu `rokovi_iz_izvora`.

Događaj navodi id dokumenta tek POSLE potvrđenog upisa. Kada ga usklađivanje ne nađe u predmetu ovog korisnika:
  1. privremeno nevidljiv               → posledica `failed`, događaj se ponavlja; kad se vrati, kandidat nastaje
  2. obrisan (SourceInvalidated, 137)   → bezbedan preskok (`obrisano`), posledica završena, bez ponavljanja
     predmet u brisanju (114)            → isto
  3. stariji događaj bez identiteta     → `skipped_no_document_identity` (nepromenjeno)
  4. tuđi dokument                      → nikad se ne čita; posledica nikad `completed` (DEAD_LETTER posle 5 pokušaja)
  5. batch delimično razrešen           → razrešeni dobijaju kandidate ODMAH; posledica tek kad je sve razrešeno

Stvaran dispečer (`dispatch_pending_events`), stvarna ruta brisanja; baza u memoriji.
"""
import asyncio
import uuid as _uuid

import routers.case_dna as cd
from shared import rokovi as R
from tests import ns005_harness as _h  # noqa: F401
from tests.ns006_fake import dispecuj
from tests.test_ba01_rok_identitet import A, Model, _pdf, _predmet, _rokovi, _stanja, lanac, solo  # noqa: F401
from tests.test_ba05_rokovi_iz_izvora import TAKSA, TROSKOVI, _dok, _dokumenti, _uskladi
from tests.test_n1_zlatni_prijem import _do_kraja


def _emituj(pid, ids, tip="DOCUMENT_ACCEPTED", uid="uid-A"):
    from services.event_bus import EventType, emit_durable
    eid = str(_uuid.uuid4())
    p = {"dokumenti": ["scan.pdf"] * len(ids), "dokument_ids": list(ids), "trigger": "test"}
    asyncio.run(emit_durable(getattr(EventType, tip), uid, pid, p, event_id=eid))
    return eid


def _posledice(b, eid):
    return {p["consequence_name"]: p for p in b.tabele["case_evolution_consequences"] if p["event_id"] == eid}


def _dogadjaj(b, eid):
    return next(e for e in b.tabele["events"] if e["id"] == eid)


def _sakrij(b, did):
    red = next(d for d in b.tabele["predmet_dokumenti"] if d["id"] == did)
    b.tabele["predmet_dokumenti"].remove(red)
    return red


def _obrisi_rutom(k, b, pid, did):
    from unittest.mock import MagicMock, patch

    from shared.vector_deletion import Ishod, Rezultat
    from tests.test_vcr002_t03_visedokumentni_predmet import _atomsko_rpc, _brisanje_rpc
    b.rpc_impl["invalidate_dokument_relational_and_emit_event"] = _brisanje_rpc
    b.rpc_impl["invalidate_dokument_and_ai_claims_and_emit_event"] = _atomsko_rpc
    with patch("shared.vector_deletion.obrisi_vektore_dokumenta", lambda *x, **kw: Rezultat(Ishod.DELETED, obrisano=1, ocekivano=1)), \
            patch("uploaded_doc.ingest._get_pinecone_index", lambda: MagicMock()):
        r = k.delete(f"/api/predmeti/{pid}/dokumenti/{did}", headers=A)
    assert r.status_code == 200, r.text


# ── 1. privremeno nevidljiv ─────────────────────────────────────────────────────────────────────────────────────────

def test_privremeno_nevidljiv_dokument_ne_zavrsava_posledicu_a_povratak_dovrsava(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    did = _dok(b, pid, "\n".join(TAKSA))
    eid = _emituj(pid, [did])
    red = _sakrij(b, did)
    dispecuj()
    pos = _posledice(b, eid)
    assert pos["rokovi_iz_izvora"]["status"] == "failed" and did[:8] in pos["rokovi_iz_izvora"]["error"], pos
    assert "genome_refresh" not in pos and not _dogadjaj(b, eid).get("dispatched_at")     # nije „obrađen“
    assert _rokovi(b, pid) == []
    b.tabele["predmet_dokumenti"].append(red)                                   # dokument ponovo vidljiv
    dispecuj()
    pos = _posledice(b, eid)
    assert pos["rokovi_iz_izvora"]["status"] == "completed" and "kreirano=1" in pos["rokovi_iz_izvora"]["result_ref"]
    [h] = _rokovi(b, pid)
    assert h["dokument_id"] == did and _stanja(k, pid) == {h["id"]: "UNCONFIRMED"}
    e = _dogadjaj(b, eid)
    assert e.get("dispatched_at") and not (e.get("last_error") or "").startswith("DEAD_LETTER")


# ── 2. obrisan dokument / predmet u brisanju ────────────────────────────────────────────────────────────────────────

def test_obrisan_dokument_je_bezbedan_preskok_bez_ponavljanja(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    _dok(b, pid, "\n".join(TROSKOVI), ime="a.pdf")
    did = _dok(b, pid, "\n".join(TAKSA))
    eid = _emituj(pid, [did])
    _obrisi_rutom(k, b, pid, did)                                               # advokat briše pre obrade događaja
    for _ in range(3):
        dispecuj()
    pos = _posledice(b, eid)["rokovi_iz_izvora"]
    assert pos["status"] == "completed" and "obrisano=1" in pos["result_ref"], pos
    assert _dogadjaj(b, eid).get("dispatched_at") and not _dogadjaj(b, eid).get("last_error")
    assert _rokovi(b, pid) == []                                                # obrisan izvor ne rađa kandidata
    assert asyncio.run(R.uskladi_rokove_iz_izvora(b, pid, "uid-A", dokument_ids=[did]))["obrisano"] == [did]


def test_predmet_u_brisanju_je_bezbedan_preskok(lanac):
    k, b = lanac
    pid = _predmet(k)
    did = _dok(b, pid, "\n".join(TAKSA))
    _sakrij(b, did)
    assert _uskladi(b, pid, [did])["nije_pronadjeno"] == [did]
    next(p for p in b.tabele["predmeti"] if p["id"] == pid)["brisanje_zapoceto"] = "2026-10-31T00:00:00+00:00"
    ishod = _uskladi(b, pid, [did])
    assert ishod["obrisano"] == [did] and ishod["nije_pronadjeno"] == [] and _rokovi(b, pid) == []


# ── 3. stariji događaj bez identiteta ───────────────────────────────────────────────────────────────────────────────

def test_stariji_dogadjaj_bez_identiteta_ostaje_preskok(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    _dok(b, pid, "\n".join(TAKSA))
    eid = _emituj(pid, [])
    dispecuj()
    assert _posledice(b, eid)["rokovi_iz_izvora"]["result_ref"] == "skipped_no_document_identity"
    assert _dogadjaj(b, eid).get("dispatched_at") and _rokovi(b, pid) == []


# ── 4. tuđi dokument ────────────────────────────────────────────────────────────────────────────────────────────────

def test_tudji_dokument_nikad_ne_zavrsava_posledicu_i_ne_cita_se(lanac, monkeypatch):
    from services.event_bus import DEAD_LETTER_MARKER, MAX_DISPATCH_ATTEMPTS, _source_invalidation_event_id
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    tudji = _dok(b, pid, "\n".join(TAKSA), uid="uid-B")
    # ni dokaz brisanja upisan pod TUĐIM korisnikom ne važi za ovog
    b.tabele["events"].append({"id": _source_invalidation_event_id("dokument", tudji), "event_type": "SourceInvalidated",
                               "user_id": "uid-B", "predmet_id": pid, "payload": {},
                               "dispatched_at": "2026-10-31T00:00:00+00:00", "dispatch_attempts": 0})
    eid = _emituj(pid, [tudji])
    for _ in range(MAX_DISPATCH_ATTEMPTS + 1):
        dispecuj()
    assert _posledice(b, eid)["rokovi_iz_izvora"]["status"] == "failed"
    assert (_dogadjaj(b, eid).get("last_error") or "").startswith(DEAD_LETTER_MARKER)      # vidljivo, ne tih uspeh
    assert _rokovi(b, pid) == []


# ── 5. batch delimično razrešen ─────────────────────────────────────────────────────────────────────────────────────

def test_batch_delimicno_razresen_kandidati_odmah_posledica_tek_kad_je_sve_razreseno(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    prvi = _dok(b, pid, "\n".join(TROSKOVI))
    drugi = _dok(b, pid, "\n".join(TAKSA))
    eid = _emituj(pid, [prvi, drugi], tip="DOCUMENT_BATCH_COMPLETED")
    red = _sakrij(b, drugi)
    dispecuj()
    assert _posledice(b, eid)["rokovi_iz_izvora"]["status"] == "failed"
    [h] = _rokovi(b, pid)
    assert h["dokument_id"] == prvi                                             # razrešen nije zadržan
    dispecuj()
    assert [x["id"] for x in _rokovi(b, pid)] == [h["id"]]                      # ponavljanje bez duplikata
    b.tabele["predmet_dokumenti"].append(red)
    dispecuj()
    pos = _posledice(b, eid)["rokovi_iz_izvora"]
    assert pos["status"] == "completed" and "kreirano=1 postoji=1" in pos["result_ref"], pos
    assert {x["dokument_id"] for x in _rokovi(b, pid)} == {prvi, drugi} and len(_rokovi(b, pid)) == 2


def test_batch_delimicno_obrisan_zavrsava_sa_razresenim(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    prvi = _dok(b, pid, "\n".join(TROSKOVI))
    drugi = _dok(b, pid, "\n".join(TAKSA))
    eid = _emituj(pid, [prvi, drugi], tip="DOCUMENT_BATCH_COMPLETED")
    _obrisi_rutom(k, b, pid, drugi)
    dispecuj()
    pos = _posledice(b, eid)["rokovi_iz_izvora"]
    assert pos["status"] == "completed" and "kreirano=1" in pos["result_ref"] and "obrisano=1" in pos["result_ref"], pos
    assert [x["dokument_id"] for x in _rokovi(b, pid)] == [prvi]


def test_batch_obrada_navodi_stvarne_dokumente(lanac, monkeypatch):
    """Stvaran finalize-batch: DOCUMENT_BATCH_COMPLETED nosi id-jeve dokumenata upisanih u toj obradi (ranije samo
    poslove — nestanak dokumenta iz batch-a nije mogao da se primeti)."""
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    poslovi = []
    for redovi, ime in ((TROSKOVI, "a.pdf"), (TAKSA, "b.pdf")):
        r = k.post("/api/smart-intake/documents", files=[("files", (ime, _pdf(redovi), "application/pdf"))], headers=A)
        poslovi.append(r.json()["rezultati"][0]["job_id"])
    _do_kraja()
    for jid in poslovi:
        if k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()["job"]["status"] == "awaiting_review":
            k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A)
    _do_kraja()
    r = k.post("/api/smart-intake/jobs/finalize-batch", json={"job_ids": poslovi}, headers=A)
    assert r.status_code == 200, r.text
    [pid] = [p["predmet_id"] for p in r.json()["predmeti_pogodjeni"]]           # predmet iz broja predmeta u aktu
    [e] = [e for e in b.tabele["events"] if e.get("event_type") == "DocumentBatchCompleted" and e.get("predmet_id") == pid]
    dok = _dokumenti(b, pid)
    assert len(dok) == 2 and sorted(e["payload"]["dokument_ids"]) == sorted(d["id"] for d in dok)
    dispecuj()
    pos = _posledice(b, e["id"])["rokovi_iz_izvora"]
    assert pos["status"] == "completed" and "obrisano=0" in pos["result_ref"], pos
