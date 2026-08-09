# -*- coding: utf-8 -*-
"""
Sprint 5, item 1 — whose percentage is it?

Chosen over consolidating the six competing producers, and the reasoning is the
finding itself: PredictorRequest had NO field for the side the lawyer
represents. The prompt asked for "procenat sanse za uspeh" and for
"kontra-argumente koje suprotna strana moze koristiti" -- implying the reader is
a party -- but never established which one. The model inferred the side from the
free-text description, and a case description naturally reads from the
claimant's perspective.

A defence lawyer could therefore be shown 70% that is the PLAINTIFF's chance.
Consolidating six ambiguous numbers into one ambiguous number does not fix that;
it centralises it. So the subject gets attached first.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_prompt_names_the_side_when_it_is_supplied():
    """The instruction must bind the percentage to a specific party, not leave
    the model to choose."""
    from routers.court_predictor import _strana_instrukcija

    for strana, mora_sadrzati in (
        ("tuzilac", "TUŽIOCA"),
        ("tuzeni", "TUŽENOG"),
        ("podnosilac", "PODNOSIOCA"),
    ):
        txt = _strana_instrukcija(strana)
        assert mora_sadrzati in txt, f"{strana}: prompt must name the party"
        assert "VEROVATNOCA USPEHA ZA" in txt
        assert "a ne za suprotnu stranu" in txt


def test_prompt_refuses_to_let_the_model_pick_a_side_silently():
    """When the side is unknown the model must be told to state, in the analysis
    text, which side the number refers to -- rather than quietly choosing one."""
    from routers.court_predictor import _strana_instrukcija

    txt = _strana_instrukcija(None)
    assert "NIJE navedena" in txt
    assert "MORAS" in txt and "na koju se stranu procenat odnosi" in txt


def test_unknown_side_value_is_treated_as_unspecified_not_guessed():
    """A typo or an unexpected value must degrade to the honest branch."""
    from routers.court_predictor import _strana_instrukcija

    assert "NIJE navedena" in _strana_instrukcija("nesto-drugo")
    assert "NIJE navedena" in _strana_instrukcija("")


def test_request_model_accepts_the_side_and_defaults_to_none():
    """Optional on purpose: existing clients do not send it, and their requests
    must keep working -- they simply get the honest 'unspecified' handling."""
    from routers.court_predictor import PredictorRequest

    req = PredictorRequest(opis_predmeta="x", tip_postupka="gradjansko", cinjenicni_opis="y")
    assert req.strana is None

    req2 = PredictorRequest(opis_predmeta="x", tip_postupka="gradjansko",
                            cinjenicni_opis="y", strana="tuzeni")
    assert req2.strana == "tuzeni"


def test_response_carries_the_subject_of_the_number():
    """The percentage must never leave the backend without saying whose it is."""
    import inspect
    import routers.court_predictor as cp

    src = inspect.getsource(cp.prediktuj_ishod)
    assert '"procenat_strana"' in src
    assert '"procenat_znacenje"' in src


def test_frontend_renders_the_subject_next_to_the_number():
    """PROGBETA-001 put this number on screen. Putting an ambiguous number on
    screen raises the stakes, so the subject has to go with it."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "static" / "vindex.js").read_text(encoding="utf-8")

    i_num = js.index("data.procenat_min + '% – '")
    window = js[i_num:i_num + 900]
    assert "procenat_znacenje" in window, "the subject must render with the number"
    assert "nije određena" in window, "and must say so when it is unknown"


# ═══════════════════════════════════════════════════════════════════════════
# Sprint 5, item 2 — migration drift detector
# ═══════════════════════════════════════════════════════════════════════════
# Migration 109 aborted with 42P01 on a table that migrations/ declares and the
# database did not have. The repository's migration list and the live schema had
# silently diverged, and nothing could notice short of a migration crashing into
# the gap.

def test_parser_ignores_create_table_mentioned_in_a_comment():
    """The first version of this tool reported four fictional tables -- IF, bi,
    iznad and one more -- because several migrations DISCUSS
    'CREATE TABLE IF NOT EXISTS' in a comment and the regex matched the next
    word. A drift detector that invents tables is not one anybody reads twice."""
    import tempfile
    from pathlib import Path
    from scripts.migration_drift_check import _parse_tables

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "001_x.sql").write_text(
            "-- Bezbedno za ponovljeno pokretanje (CREATE TABLE IF NOT EXISTS).\n"
            "-- CREATE TABLE IF NOT EXISTS bi to tiho preskocio\n"
            "CREATE TABLE IF NOT EXISTS public.stvarna_tabela (\n"
            "  id UUID PRIMARY KEY\n"
            ");\n",
            encoding="utf-8",
        )
        found = _parse_tables(Path(d))

    assert set(found) == {"stvarna_tabela"}, f"parsed junk: {sorted(found)}"


def test_parser_reads_function_parameter_names_from_the_migration():
    """Three times during this investigation a probe reported a function MISSING
    that was present, because it guessed the parameter names. PostgREST resolves
    an RPC by exact named arguments, and a wrong set returns PGRST202 --
    indistinguishable from 'no such function'. The names must come from the
    migration, never from a guess."""
    import tempfile
    from pathlib import Path
    from scripts.migration_drift_check import _parse_functions

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "002_y.sql").write_text(
            "CREATE OR REPLACE FUNCTION public.moja_fn(\n"
            "    p_user_id UUID,\n"
            "    p_broj    INTEGER DEFAULT 0\n"
            ")\nRETURNS INTEGER\nLANGUAGE plpgsql AS $$ BEGIN RETURN 1; END; $$;\n",
            encoding="utf-8",
        )
        found = _parse_functions(Path(d))

    assert "moja_fn" in found
    assert found["moja_fn"][1] == ["p_user_id", "p_broj"]
