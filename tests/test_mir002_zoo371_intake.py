# -*- coding: utf-8 -*-
"""MIR002 S06 — uputstvo savetnika „intake“ navodi opšti rok zastarelosti iz čl. 371 ZOO.

Čl. 371 ZOO: potraživanja zastarevaju za deset godina, ako zakonom nije određen neki drugi rok zastarelosti. Uputstvo je
navodilo 3 godine (nalaz MIR002, odobrena ispravka osnivača 2026-11-03), a glasilo kao „Sl. gl. RS 29/1978“ (ispravno:
„Službeni list SFRJ“, br. 29/78; MIR002 final closure). Opseg: samo ova tvrdnja u uputstvu intake;
ostala uputstva savetnika ostaju zaključana (`tests/test_mir001_c3b_pravila.py`).
"""
import re


def _redovi_371(tekst: str) -> list:
    return [r.strip() for r in tekst.splitlines() if re.search(r"čl\.\s*371\s+ZOO", r)]


def test_intake_opsti_rok_cl_371_zoo_je_deset_godina_uz_izuzetak_zakona():
    import routers.multi_agent as MA
    [red] = _redovi_371(MA._AGENTS["intake"]["system"])
    assert "10 godina" in red, red
    assert "osim kada zakon" in red, red
    assert not re.search(r"\b3\s*god", red), red


def test_intake_cl_371_zoo_navodi_tacno_glasilo():
    """Izvor: ZOO, „Službeni list SFRJ“, br. 29/78 (VKS, Rev2 1222/2026; lokalno `main.py` PROPISI). Nije „Sl. gl. RS“."""
    import routers.multi_agent as MA
    [red] = _redovi_371(MA._AGENTS["intake"]["system"])
    assert "Sl. list SFRJ, br. 29/78" in red, red
    assert "Sl. gl. RS" not in red, red


def test_nijedno_uputstvo_savetnika_ne_vezuje_cl_371_zoo_za_tri_godine():
    import routers.multi_agent as MA
    for agent, cfg in MA._AGENTS.items():
        for red in _redovi_371(cfg["system"]):
            assert not re.search(r"\b3\s*god", red), (agent, red)
