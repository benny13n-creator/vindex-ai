# -*- coding: utf-8 -*-
"""JRC001 — kontrola roka odobrenog izuzetka CVE-2026-85394 (security/izuzeci_ranjivosti.py) sa UBAČENIM datumom:
pre, na dan i posle isteka; neispravan ili nepotpun zapis nikad ne prolazi; izuzetak se ne sme tiho proširiti."""
import copy
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

KOREN = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("izuzeci_ranjivosti", KOREN / "security" / "izuzeci_ranjivosti.py")
iz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(iz)

META = json.loads((KOREN / "security" / "izuzeci_ranjivosti.json").read_text(encoding="utf-8"))
REQ = (KOREN / "requirements.txt").read_text(encoding="utf-8")
WF = (KOREN / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")


def _g(meta=None, danas=date(2026, 12, 1), req=REQ, wf=WF):
    return iz.proveri(META if meta is None else meta, danas, req, wf, koren=KOREN)


def test_zapis_odgovara_odluci_osnivaca():
    z = META["CVE-2026-85394"]
    assert (z["paket"], z["verzija"], z["odobreno"], z["vazi_do"]) == ("python-jose", "3.5.0", "2026-10-11", "2027-01-09")
    assert set(META) == {"CVE-2026-85394"}                     # odobrenje pokriva SAMO ovaj CVE
    assert (date(2027, 1, 9) - date(2026, 10, 11)).days == 90


@pytest.mark.parametrize("danas,ok", [
    (date(2026, 10, 10), False),     # pre odobrenja
    (date(2026, 10, 11), True),      # dan odobrenja
    (date(2026, 12, 31), True),
    (date(2027, 1, 9), True),        # poslednji dan važenja
    (date(2027, 1, 10), False),      # istekao — nema automatskog produženja
    (date(2027, 6, 1), False),
])
def test_rok_pre_na_dan_i_posle_isteka(danas, ok):
    greske = _g(danas=danas)
    assert (greske == []) is ok, greske
    if danas > date(2027, 1, 9):
        assert any("ISTEKLO" in x for x in greske)


def test_main_sa_ubacenim_datumom_daje_izlazne_kodove():
    assert iz.main([], danas=date(2027, 1, 9)) == 0
    assert iz.main([], danas=date(2027, 1, 10)) == 1


@pytest.mark.parametrize("pokvari", [
    lambda m: {},
    lambda m: [],
    lambda m: {"CVE-2026-85394": "tekst"},
    lambda m: {"CVE-2026-85394": {**m["CVE-2026-85394"], "vazi_do": None}},
    lambda m: {"CVE-2026-85394": {k: v for k, v in m["CVE-2026-85394"].items() if k != "vlasnik"}},
    lambda m: {"CVE-2026-85394": {**m["CVE-2026-85394"], "vazi_do": "2027-13-40"}},
    lambda m: {"CVE-2026-85394": {**m["CVE-2026-85394"], "vazi_do": "9.1.2027"}},
    lambda m: {"CVE-2026-85394": {**m["CVE-2026-85394"], "vazi_do": "2027-01-10"}},     # 91 dan
    lambda m: {"CVE-2026-85394": {**m["CVE-2026-85394"], "vazi_do": "2026-10-01"}},     # pre odobrenja
    lambda m: {"CVE-2026-85394": {**m["CVE-2026-85394"], "odluka": "docs/ne_postoji.md"}},
])
def test_neispravan_ili_nepotpun_zapis_nikad_ne_prolazi(pokvari):
    assert _g(meta=pokvari(copy.deepcopy(META))) != []


def test_druga_verzija_paketa_trazi_ponovni_pregled():
    assert _g(req=REQ.replace("python-jose[cryptography]==3.5.0", "python-jose[cryptography]==3.5.1")) != []
    assert _g(req=REQ.replace("python-jose[cryptography]==3.5.0", "python-jose[cryptography]>=3.5.0")) != []
    assert _g(req=REQ.replace("python-jose[cryptography]==3.5.0\n", "")) != []


def test_izuzetak_se_ne_sme_tiho_prosiriti_ni_ukloniti():
    nov = WF.replace("--ignore-vuln CVE-2026-85394", "--ignore-vuln CVE-2026-85394 \\\n            --ignore-vuln CVE-2099-00001")
    assert any("CVE-2099-00001" in x for x in _g(wf=nov))
    bez = WF.replace(" \\\n            --ignore-vuln CVE-2026-85394", "")
    assert bez != WF and _g(wf=bez) != []
    dupli = WF.replace("--ignore-vuln CVE-2026-85394", "--ignore-vuln CVE-2026-85394 --ignore-vuln CVE-2026-85394")
    assert _g(wf=dupli) != []


def test_pip_audit_nije_oslabljen_i_kontrola_ide_pre_njega():
    """Isti pip-audit poziv (blokira, -r requirements.txt, tačno dva ignore-a) i provera roka u ISTOM poslu, pre njega."""
    posao = WF[WF.index("  dependency-scan:"):WF.index("  semgrep-core:")]
    assert "pip-audit -r requirements.txt" in posao
    assert sorted(__import__("re").findall(r"--ignore-vuln\s+(\S+)", posao)) == ["CVE-2026-85394", "PYSEC-2026-1325"]
    assert "continue-on-error" not in posao
    assert posao.index("security/izuzeci_ranjivosti.py") < posao.index("pip-audit -r requirements.txt")
