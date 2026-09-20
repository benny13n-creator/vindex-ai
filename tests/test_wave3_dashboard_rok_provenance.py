# -*- coding: utf-8 -*-
"""
VINDEX AI V1, Wave 3 beta acceptance -- P0 fix regression: dashboard
deadline provenance ("Hitni rokovi" / "Rokovi 7 dana").

PROVEN DEFECT (2026-09-20, Wave 3 Journey F investigation): an AI-autonomous
deadline (predmet_hronologija.izvor = 'AI_AUTONOMOUS', written by
routers/smart_intake.py or routers/case_dna.py with confidence >= the
auto-accept threshold, never seen/confirmed by a human) appeared on the
dashboard's "Hitni rokovi"/"Rokovi 7 dana" -- the one screen a lawyer checks
daily -- visually and functionally identical to a human-confirmed deadline.
Root cause, in two parts:

  1. shared/rokovi.py's `_KOLONE` (the SELECT column list) was written
     BEFORE migration 127 added `predmet_hronologija.izvor` and was never
     updated to select it -- so the domain reader (`_u_rok`) could never
     see the column even though every writer populates it.
  2. routers/dashboard.py's own `rokovi_7` construction filled its response
     "izvor" key with `_rokovi_domen.TABELA` -- a constant equal to the
     TABLE NAME, identical for every row -- not the per-row AI/human
     provenance value. A future reader of that key would reasonably assume
     it already carried the safety-critical signal the rest of this file
     extensively documents "izvor" as canonically meaning.

This does NOT affect the outbound/notification authorization gate
(`shared/rokovi.py::sme_pokrenuti_obavezu`), which reads `izvor` directly
from the raw DB row dict (never through `Rok`) and was already correct and
unchanged by this fix -- confirmed by grep, not assumed. This fix is purely
about the dashboard's TRUTHFUL representation of provenance, nothing more.
"""
import os
from datetime import date

import pytest

import shared.rokovi as rokovi


def test_kolone_select_includes_izvor():
    """Regression guard: if a future edit drops `izvor` from the SELECT
    column list, the dashboard silently goes back to being unable to show
    real provenance -- this must fail loudly, not silently."""
    assert "izvor" in rokovi._KOLONE, (
        "_KOLONE no longer selects `izvor` -- the dashboard cannot "
        "distinguish an AI-autonomous, never-confirmed deadline from a "
        "human one without this column"
    )


def test_u_rok_populates_izvor_from_row():
    red = {
        "id": "rok-1",
        "predmet_id": "pred-1",
        "dogadjaj": "Test rok",
        "datum_iso": "2026-09-30",
        "vaznost": "vazan",
        "akter": "",
        "izvor": "AI_AUTONOMOUS",
    }
    rok = rokovi._u_rok(red, date(2026, 9, 20))
    assert rok is not None
    assert rok.izvor == "AI_AUTONOMOUS"


def test_u_rok_missing_izvor_defaults_to_empty_not_none():
    """A legacy row (pre-migration-127, or any row somehow missing the
    value) must not crash the reader -- empty string, same convention as
    `akter`'s own `(red.get("akter") or "")` default."""
    red = {
        "id": "rok-2",
        "predmet_id": "pred-1",
        "dogadjaj": "Legacy rok",
        "datum_iso": "2026-09-30",
        "vaznost": "vazan",
    }
    rok = rokovi._u_rok(red, date(2026, 9, 20))
    assert rok is not None
    assert rok.izvor == ""


def test_kao_dict_exposes_izvor():
    """The API-facing dict (what actually reaches the dashboard response)
    must carry the field -- a Rok that has it internally but drops it in
    kao_dict() would be just as broken for this defect's purposes."""
    rok = rokovi.Rok(
        izvor_id="rok-1", predmet_id="pred-1", naslov="Test",
        datum=date(2026, 9, 30), vaznost="vazan",
        izvor="AI_AUTONOMOUS",
    )
    d = rok.kao_dict()
    assert d["izvor"] == "AI_AUTONOMOUS"


def test_ai_autonomous_and_human_direct_are_distinguishable_end_to_end():
    """The exact scenario the P0 finding describes: two rows, identical in
    every displayed field except provenance, must NOT collapse to the same
    `izvor` value the way the old `_rokovi_domen.TABELA` constant did."""
    ai_row = {
        "id": "rok-ai", "predmet_id": "pred-1", "dogadjaj": "Rok",
        "datum_iso": "2026-09-30", "vaznost": "vazan",
        "izvor": rokovi.IZVOR_AI_AUTONOMOUS,
    }
    human_row = {
        "id": "rok-human", "predmet_id": "pred-1", "dogadjaj": "Rok",
        "datum_iso": "2026-09-30", "vaznost": "vazan",
        "izvor": rokovi.IZVOR_HUMAN_DIRECT,
    }
    ai_rok = rokovi._u_rok(ai_row, date(2026, 9, 20))
    human_rok = rokovi._u_rok(human_row, date(2026, 9, 20))
    assert ai_rok.izvor != human_rok.izvor
    assert ai_rok.izvor == "AI_AUTONOMOUS"
    assert human_rok.izvor == "HUMAN_DIRECT"


DASHBOARD_PATH = os.path.join(
    os.path.dirname(__file__), "..", "routers", "dashboard.py",
)


def _read_dashboard_source() -> str:
    with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_dashboard_rokovi_7_no_longer_uses_the_constant_table_name_as_izvor():
    """Scope guard against silently reintroducing the exact defect: the
    misleading `"izvor": _rokovi_domen.TABELA` line must not come back."""
    src = _read_dashboard_source()
    assert '"izvor":         _rokovi_domen.TABELA,' not in src
    assert '"izvor": _rokovi_domen.TABELA' not in src


def test_dashboard_rokovi_7_uses_the_real_per_row_izvor():
    src = _read_dashboard_source()
    assert '"izvor":         r.izvor,' in src or '"izvor": r.izvor,' in src, (
        "routers/dashboard.py's rokovi_7 construction no longer exposes "
        "the real per-row provenance value"
    )


def test_execution_gate_still_reads_izvor_from_raw_row_not_from_rok():
    """Non-regression: the actual authorization gate for outbound
    reminders (`sme_pokrenuti_obavezu` -> `sme_pristupiti`) must be
    untouched by this fix -- neither ever constructs a `Rok`, and
    `sme_pristupiti`'s own docstring documents that `izvor` is not read by
    the decision at all (FAZA 6.4.1: provenance is audit data, never
    authorization). This fix only makes provenance visible on the
    dashboard; it must not have added a new dependency here."""
    import inspect
    gate_src = inspect.getsource(rokovi.sme_pokrenuti_obavezu)
    delegate_src = inspect.getsource(rokovi.sme_pristupiti)
    assert "Rok(" not in gate_src
    assert "Rok(" not in delegate_src
    assert "izvor" not in delegate_src.split('"""', 2)[-1], (
        "sme_pristupiti's implementation now references `izvor` -- "
        "provenance must remain audit-only, never authorization"
    )
