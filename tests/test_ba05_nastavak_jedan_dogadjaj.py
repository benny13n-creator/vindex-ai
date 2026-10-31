# -*- coding: utf-8 -*-
"""PR #62 nezavisni pregled L1: ponovni pokušaj finalizacije posle pada NAKON upisa DOCUMENT_ACCEPTED ne sme da
napravi drugi događaj za isto prihvatanje (drugi Genome i, sa 145, drugi red „Dokument prihvaćen“).

Posao sa dva akta: prvi je sadržajem isti kao dokument koji je u predmet ranije uneo DRUGI posao, drugi je nov.
Prvi pokušaj upiše drugi akt i događaj, pa pukne. Nastavak ne upisuje ništa novo. Identitet događaja nastavka mora biti
isti kao prvog pokušaja: dokument koji je u predmet uneo drugi posao nije „prethodni pokušaj ovog posla“.
Stvarne rute, stvaran dispečer; baza u memoriji.
"""
import io
from datetime import datetime, timedelta, timezone

import routers.case_dna as cd
from tests import ns005_harness as _h  # noqa: F401
from tests.test_ba01_rok_identitet import A, Model, _predmet, _prikaci, lanac, solo  # noqa: F401
from tests.test_n1_zlatni_prijem import _do_kraja
from tests.test_osb002_solo_tok import _do_kraja_dogadjaja

PRVI = ["OSNOVNI SUD U BEOGRADU", "RESENJE", "Posl. br. P 7714/2026", "Rok za zalbu na troskove istice 12.11.2026. godine."]
DRUGI = ["OSNOVNI SUD U NOVOM SADU", "PRESUDA", "Posl. br. P 2222/2026", "Rok za uplatu dodatne sudske takse istice 20.11.2026. godine."]


def _dva_akta():
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for redovi in (PRVI, DRUGI):
        for i, r in enumerate(redovi):
            c.drawString(50, 800 - 20 * i, r)
        c.showPage()
    c.save()
    return buf.getvalue()


def test_nastavak_posle_pada_nakon_dogadjaja_ne_pravi_drugi_dogadjaj(lanac, monkeypatch):
    import services.event_bus as eb
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    _prikaci(k, b, pid, PRVI, "prvi.pdf")                                       # drugi posao je uneo PRVI akt
    pre = {d["id"] for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid}
    assert len(pre) == 1

    r = k.post("/api/smart-intake/documents", files=[("files", ("dva.pdf", _dva_akta(), "application/pdf"))], headers=A)
    jid = r.json()["rezultati"][0]["job_id"]
    _do_kraja()
    prijemi = [d["id"] for d in b.tabele["intake_documents"] if d["intake_job_id"] == jid]
    assert len(prijemi) == 2, "dva akta"
    for e in b.tabele["extracted_entities"]:
        if e["document_id"] in prijemi and e["entity_type"] == "case_number":
            e["corrected_value"], e["reviewed"] = "P 7714/2026", True              # advokat: isti predmet
    if k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()["job"]["status"] == "awaiting_review":
        k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A)
        _do_kraja()

    pravi = eb.emit_durable
    stanje = {"pad": True}

    async def _emit_pa_pad(tip, *a, **kw):
        rez = await pravi(tip, *a, **kw)
        if tip == eb.EventType.DOCUMENT_ACCEPTED and stanje["pad"]:
            stanje["pad"] = False
            raise RuntimeError("proces pukao posle upisa događaja (test)")
        return rez
    monkeypatch.setattr(eb, "emit_durable", _emit_pa_pad)
    k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    monkeypatch.setattr(eb, "emit_durable", pravi)

    def _prihvatanja():
        return [e for e in b.tabele["events"] if e.get("event_type") == "DocumentAccepted"
                and (e.get("payload") or {}).get("intake_job_id") == jid]
    assert len(_prihvatanja()) == 1, "prvi pokušaj je upisao događaj"
    novi = {d["id"] for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid} - pre
    assert len(novi) == 1                                                       # drugi akt upisan, prvi je duplikat

    posao = next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)
    posao["finalizing_at"] = (datetime.now(timezone.utc) - timedelta(seconds=121)).isoformat()
    posao.pop("assimilation_complete", None)
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    assert f.status_code == 200, f.text
    _do_kraja_dogadjaja(b)
    assert len(_prihvatanja()) == 1, [(e["id"][:8], e["payload"].get("dokument_ids")) for e in _prihvatanja()]
    accepted = [h for h in b.tabele["predmet_hronologija"] if h["predmet_id"] == pid
                and (h.get("dogadjaj") or "").startswith("Dokument prihvaćen — dva.pdf")]
    assert len(accepted) == 1
