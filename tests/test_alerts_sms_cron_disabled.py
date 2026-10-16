# -*- coding: utf-8 -*-
"""SMS cron — automatsko pokretanje isključeno (night/deadlines-alerts-vcr002, T08).

Ruta `/sms/send-reminders` prima samo osnivačev JWT, a zakazani posao je slao `CRON_TOKEN` (401 svaki dan).
Do odluke osnivača nema automatskog SMS pokretanja; autorizacija SMS rute ostaje nepromenjena."""
import glob
import inspect
import os

import yaml

KOREN = os.path.join(os.path.dirname(__file__), "..")
SMS = os.path.join(KOREN, ".github", "workflows", "sms-cron.yml")
AUTOMATSKI = {"schedule", "push", "pull_request", "pull_request_target", "workflow_run",
              "repository_dispatch", "release", "merge_group", "check_suite", "deployment"}


def _okidaci(putanja):
    with open(putanja, encoding="utf-8") as f:
        wf = yaml.safe_load(f)
    on = wf.get("on", wf.get(True))            # PyYAML čita goli ključ `on` kao True
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return set(on)
    return set(on or {})


def test_sms_workflow_postoji_i_ima_samo_rucni_okidac():
    assert os.path.exists(SMS), "workflow obrisan — kontrolisano ponovno uključivanje mora ostati moguće"
    assert _okidaci(SMS) == {"workflow_dispatch"}


def test_nijedan_drugi_workflow_ne_poziva_sms_rutu_automatski():
    for putanja in glob.glob(os.path.join(KOREN, ".github", "workflows", "*.y*ml")):
        with open(putanja, encoding="utf-8") as f:
            tekst = f.read()
        if "/sms/" in tekst:
            assert _okidaci(putanja) <= {"workflow_dispatch"}, putanja


def test_sms_ruta_i_dalje_trazi_osnivacku_sesiju():
    """Bez novog bypass-a: ista zavisnost i ista provera osnivača kao pre sprinta."""
    import routers.sms as sms
    src = inspect.getsource(sms.posalji_podsetnike)
    assert "Depends(get_current_user)" in src
    assert "_FOUNDER_EMAILS" in src and "status_code=403" in src
    assert "X-Cron-Key" not in src and "CRON_SECRET" not in src
