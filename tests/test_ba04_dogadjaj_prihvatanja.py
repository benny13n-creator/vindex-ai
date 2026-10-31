# -*- coding: utf-8 -*-
"""BA04/BA08 (P7714/2026): dva RAZLIČITA prihvatanja dokumenta istog imena u roku od 300 s bila su jedan red
hronologije — idempotencija je poredila vidljiv tekst („Dokument prihvaćen — scan.pdf“), ne identitet događaja.
Identitet je sada `event_id` trajnog događaja (migracija 145); isti događaj ponovljen = jedan red.
"""
import routers.case_dna as cd
from tests.ns006_fake import dispecuj
from tests.test_ba01_rok_identitet import Model, _predmet, _prikaci, lanac, solo  # noqa: F401 — fixture
from tests.test_ba05_rokovi_iz_izvora import TAKSA, TROSKOVI


def _prihvatanja(b, pid):
    return [h for h in b.tabele["predmet_hronologija"]
            if h["predmet_id"] == pid and (h.get("dogadjaj") or "").startswith("Dokument prihvaćen")]


def test_T17_dva_prihvatanja_istog_imena_dva_reda(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    _prikaci(k, b, pid, TROSKOVI, "scan.pdf")
    _prikaci(k, b, pid, TAKSA, "scan.pdf")
    r = _prihvatanja(b, pid)
    assert [h["dogadjaj"] for h in r] == ["Dokument prihvaćen — scan.pdf"] * 2, r
    assert len({h.get("dogadjaj_event_id") for h in r}) == 2 and None not in {h.get("dogadjaj_event_id") for h in r}
    assert {h["user_id"] for h in r} == {"uid-A"}


def test_T18_isti_dogadjaj_ponovljen_posle_upisa_jedan_red(lanac, monkeypatch):
    """Pad posle upisa a pre `completed`: ponovna obrada ISTOG događaja ne pravi drugi red."""
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    _prikaci(k, b, pid, TROSKOVI, "scan.pdf")
    assert len(_prihvatanja(b, pid)) == 1
    for p in b.tabele["case_evolution_consequences"]:
        if p["consequence_name"] == "timeline_entry":
            p["status"] = "failed"
    for e in b.tabele["events"]:
        e["dispatched_at"] = None
    dispecuj()
    dispecuj()
    assert len(_prihvatanja(b, pid)) == 1
