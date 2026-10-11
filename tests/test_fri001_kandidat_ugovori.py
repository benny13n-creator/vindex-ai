# -*- coding: utf-8 -*-
"""FRI001 Task 4 — ugovori oporavka dokumenta koje FRG001 nije posebno merio, na integrisanom kandidatu
(stvarne rute, IntakeWorker, dispečer): naplata pri neuspehu/ponovnom pokušaju i nepromenjenost već prihvaćenog
dokumenta. Ostatak (lažan uspeh, vidljivost, isti dokument, bez duplikata, tuđi predmet) pokrivaju
tests/test_frg001_dogadjaj_dokumenta.py i test_frg001_zakon_clan_vezivanje.py, koji se puštaju na istom SHA.
"""
import copy

from tests.test_osb002_solo_tok import (  # noqa: F401 — `solo` je pytest fixture
    A, _do_kraja_dogadjaja, _novi_predmet, _otpremi, _pdf, _radnik, solo,
)

PAD_VEZE = Exception('{"code": "08006", "message": "connection failure"}')


def _spreman(k, b, sadrzaj=None):
    r = _otpremi(k, sadrzaj or _pdf())
    jid = r.json()["rezultati"][0]["job_id"]
    assert _radnik() is True
    posao = next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)
    if posao["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=A).status_code == 200
    return jid


def test_neuspeh_i_ponovni_pokusaj_ne_naplacuju_nista_vise(solo):
    """Finalize i automatska klasifikacija ne naplaćuju (naplaćuje se otpremanje i ručno „Reklasifikuj“).
    Pad + ponovni pokušaj mora imati isti broj naplata kao čist prolaz."""
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid = _spreman(k, b)
    pre = len(b.naplate)
    b.greske["events"] = PAD_VEZE
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).status_code == 503
    del b.greske["events"]
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).status_code == 200
    _do_kraja_dogadjaja(b)
    assert len(b.naplate) == pre, b.naplate[pre:]


def test_prihvacen_dokument_se_ne_prepisuje_ponavljanjem(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    pdf = _pdf()
    jid = _spreman(k, b, pdf)
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).status_code == 200
    _do_kraja_dogadjaja(b)
    dok = copy.deepcopy(b.tabele["predmet_dokumenti"])
    tvrdnje = copy.deepcopy(b.tabele["predmet_dokazi"])
    assert dok[0].get("klasifikovan_at") and tvrdnje
    # identičan zahtev, ponovo otpremljen isti fajl (isti posao), replay događaja
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).json()["already_finalized"]
    assert _otpremi(k, pdf).json()["rezultati"][0]["job_id"] == jid          # isti bajtovi = isti posao
    drugi = _spreman(k, b)                                                   # isti tekst, drugi bajtovi = nov posao
    assert drugi != jid
    r = k.post(f"/api/smart-intake/jobs/{drugi}/finalize", json={"predmet_id": pid}, headers=A)
    assert r.status_code == 200 and r.json()["dokumenti"][0].get("razlog") == "vec_obradjen_preskocen"
    for e in b.tabele["events"]:
        e["dispatched_at"] = None
        e["claimed_at"] = None
    _do_kraja_dogadjaja(b)
    assert b.tabele["predmet_dokumenti"] == dok
    assert b.tabele["predmet_dokazi"] == tvrdnje
