# -*- coding: utf-8 -*-
"""S08: real audit writer stores JSON text inside PostgreSQL JSONB."""
import json
from datetime import date, timedelta
from unittest.mock import patch
import pytest
from shared import rok_ispravka as RI
from shared.rok_potvrda import AKCIJA_ODBIJANJE, AKCIJA_POTVRDA
from tests.test_n4_ispravka_roka import _predlog, lanac  # noqa: F401
from tests.test_osb002_solo_tok import A, solo  # noqa: F401

class _Rows:
    def table(self, name):
        assert name == "predmet_hronologija"
        return self
    def select(self, *a):
        return self
    def eq(self, *a):
        return self
    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=[{"id": "corrected"}])

@pytest.mark.parametrize("encoded", [False, True], ids=["jsonb-object", "jsonb-string"])
def test_both_correction_readers_handle_audit_wire(encoded):
    rejection = {"napomena": RI.napomena_odbijanja("corrected")}
    confirmed = {"napomena": RI.napomena_ispravke("original")}
    if encoded:
        rejection, confirmed = json.dumps(rejection), json.dumps(confirmed)
    with patch("shared.rok_potvrda.procitaj_lanac",
               return_value=[{"seq": 1, "action": AKCIJA_ODBIJANJE, "resource_id": "original", "metadata": rejection}]):
        assert RI.ispravka_iz_odbijanja("original") == "corrected"
    with patch("shared.rok_potvrda.procitaj_lanac",
               return_value=[{"seq": 2, "action": AKCIJA_POTVRDA, "resource_id": "corrected", "metadata": confirmed}]):
        assert RI.postojeca_ispravka(_Rows(), uid="uid-A", predlog={"predmet_id": "p-1"},
                                    rok_id="original") == "corrected"

@pytest.mark.parametrize("bad", ["{bad", "[]", "null", [], 17])
def test_invalid_audit_metadata_fails_closed(bad):
    with patch("shared.rok_potvrda.procitaj_lanac",
               return_value=[{"seq": 1, "action": AKCIJA_ODBIJANJE, "resource_id": "original", "metadata": bad}]):
        with pytest.raises(ValueError, match="Invalid correction audit metadata"):
            RI.ispravka_iz_odbijanja("original")
    with patch("shared.rok_potvrda.procitaj_lanac",
               return_value=[{"seq": 2, "action": AKCIJA_POTVRDA, "resource_id": "corrected", "metadata": bad}]):
        with pytest.raises(ValueError, match="Invalid correction audit metadata"):
            RI.postojeca_ispravka(_Rows(), uid="uid-A", predlog={"predmet_id": "p-1"},
                                  rok_id="original")

def _serialize_audit_rows(b):
    for row in b.tabele.get("audit_immutable", []):
        if isinstance(row.get("metadata"), dict):
            row["metadata"] = json.dumps(row["metadata"], ensure_ascii=False)

def _d(n):
    return (date.today() + timedelta(days=n)).isoformat()

def test_repeated_correction_then_second_confirmation_after_json_string_roundtrip(lanac):
    k, b = lanac
    _predlog(b)
    first = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    assert first.status_code == 200, first.text
    _serialize_audit_rows(b)
    audit_before = len(b.tabele["audit_immutable"])
    deadlines_before = len(b.tabele["predmet_hronologija"])
    repeated = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    assert repeated.status_code == 409, repeated.text
    assert k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=A).status_code == 409
    assert len(b.tabele["audit_immutable"]) == audit_before
    assert len(b.tabele["predmet_hronologija"]) == deadlines_before
    _predlog(b, rid="second-ai", pid="p-1", dana=20)
    second = k.post("/api/rokovi/second-ai/potvrdi", json={}, headers=A)
    assert second.status_code == 200, second.text

def test_resume_interrupted_correction_after_json_string_roundtrip(lanac):
    k, b = lanac
    _predlog(b)
    b.lanac_puca = "rok_potvrdjen"
    first = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    assert first.status_code == 503
    b.lanac_puca = None
    _serialize_audit_rows(b)
    before = len(b.tabele["predmet_hronologija"])
    resumed = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    assert resumed.status_code == 200, resumed.text
    assert len(b.tabele["predmet_hronologija"]) == before
