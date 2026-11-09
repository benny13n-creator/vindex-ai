"""Offline Golden Case provider replay through the real drafting route."""
import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.test_mir002_litigation_procesno_stanje import lit, solo  # noqa: F401
from tests.test_osb002_solo_tok import A, B

RAW = Path(__file__).with_name("fixtures") / "beta_mir03_adviser_8553_run1.json"
SENTENCE = "Izjašnjenje na nalaz veštaka od 15.06.2026. (DOK-05). Datum dostave nije utvrđen."


def _model(monkeypatch, raw):
    from routers import multi_agent

    calls = []

    def odgovor(*args):
        calls.append(args[-1])
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=raw), finish_reason="stop"
        )])

    monkeypatch.setattr(multi_agent, "_pozovi_nacrt_api", odgovor)
    return calls


def _draft(k, pid, headers=A):
    return k.post("/api/agents/run", json={
        "agent": "drafting", "task": "Sastavi izjašnjenje na nalaz veštaka.", "predmet_id": pid,
    }, headers=headers)


@pytest.mark.parametrize("sentence", [
    "Nalaz veštaka od 15.06.2026. dostavljen je strankama (DOK-05).",
    "Veštakov nalaz je dostavljen 15.06.2026. (DOK-05).",
    "Tužilac je primio nalaz veštaka 15.06.2026. (DOK-05).",
    "Вештаков налаз је уручен 15.06.2026. (DOK-05).",
    "Nalaz veštaka je dostavljen strankama (DOK-05).",
])
@pytest.mark.parametrize("field", ["tekst_za_sud", "napomene_za_advokata"])
def test_nepotvrdjena_dostava_ne_postaje_nacrt(lit, monkeypatch, sentence, field):
    k, b, pid, _, _ = lit
    response = {"tekst_za_sud": SENTENCE, "napomene_za_advokata": []}
    response[field] = sentence if field == "tekst_za_sud" else [sentence]
    _model(monkeypatch, json.dumps(response))
    r = _draft(k, pid)
    assert r.status_code == 502, r.text
    assert not b.naplate and not b.tabele["staging_memory"]


def test_arhivirani_raw_odbijen_pre_naplate_i_pregleda(lit, monkeypatch):
    k, b, pid, _, _ = lit
    raw = RAW.read_bytes()
    assert sha256(raw).hexdigest() == "e003ce75a71cd9e00d5a4901a9f2e38c9bd6e57476a50cddabc9b509bd9eac6f"
    calls = _model(monkeypatch, raw.decode())
    assert _draft(k, pid, B).status_code == 404 and not calls
    h = {**A, "Idempotency-Key": str(uuid4())}
    assert _draft(k, pid, h).status_code == 502
    again = _draft(k, pid, h)
    assert again.status_code == 502 and again.headers.get("idempotent-replayed") == "true"
    assert len(calls) == 1 and not b.naplate and not b.tabele["staging_memory"]


@pytest.mark.parametrize("sentence", [
    SENTENCE,
    "Nalaz veštaka nije dostavljen strankama 15.06.2026. (DOK-05).",
    "Ako je nalaz veštaka dostavljen 15.06.2026, proveriti dostavnicu (DOK-05).",
    "Veštak navodi da je prokišnjavanje posledica izvođačke greške (DOK-05).",
    "Nakon što bude dostavljen građevinski dnevnik iz naloga suda (DOK-07), razmotriti nalaz veštaka (DOK-05).",
])
def test_datum_nalaza_negacija_i_uslov_ne_postaju_tvrdnja_o_dostavi(lit, monkeypatch, sentence):
    k, b, pid, _, _ = lit
    _model(monkeypatch, json.dumps({"tekst_za_sud": sentence, "napomene_za_advokata": [SENTENCE]}))
    r = _draft(k, pid)
    assert r.status_code == 200, r.text
    assert r.json()["predlog_teksta"] == sentence
    assert len(b.naplate) == 1


@pytest.mark.parametrize("izmena,status", [("povucen", 409), ("promenjen", 409),
                                          ("primalac", 502), ("citiran", 502), ("tokom_kvaliteta", 409),
                                          ("jsonb_string", 200), ("neispravna_potvrda", 502)])
def test_potvrdjeni_izvor_mora_podrzati_tvrdnju_posle_modela(lit, monkeypatch, izmena, status):
    from tests import mir001_golden_case as gc
    from tests.test_mir002_litigation_procesno_stanje import _dodaj_dokument, _dok_predmeta

    k, b, pid, _, _ = lit
    uvod = ("Sud konstatuje da punomocnik tuzioca navodi da je" if izmena == "citiran" else "Sud konstatuje da je")
    novi = {**gc.KASNIJI, "ime": "08 Zapisnik o dostavi.pdf", "strana": "sud", "vrsta": "zapisnik",
            "redovi": [gc.SUD, "ZAPISNIK SA ROCISTA (SINTETICKI PREDMET)",
                       f"{uvod} nalaz vestaka dostavljen tuziocu dana 15.06.2026. godine."]}
    _dodaj_dokument(k, b, pid, novi)
    did = next(d["id"] for d in _dok_predmeta(b, pid) if d["naziv_fajla"] == novi["ime"])
    b.tabele["audit_immutable"].append({
        "seq": 1, "user_id": "uid-A", "resource_id": did, "resource_type": "predmet_dokumenti",
        "action": "dokument_vrsta_ispravljena", "metadata": {"novo": "court_decision"},
    })
    if izmena in ("jsonb_string", "neispravna_potvrda"):
        b.tabele["audit_immutable"][-1]["metadata"] = json.dumps({"novo": "court_decision"})
    if izmena == "neispravna_potvrda":
        b.tabele["audit_immutable"].append({**b.tabele["audit_immutable"][-1], "seq": 2, "metadata": "{"})
    from routers import multi_agent
    primalac = "tuženom" if izmena == "primalac" else "tužiocu"
    raw = json.dumps({"tekst_za_sud": f"Nalaz veštaka dostavljen je {primalac} 15.06.2026. (DOK-08).",
                      "napomene_za_advokata": []})
    _model(monkeypatch, raw)
    odgovor = multi_agent._pozovi_nacrt_api

    def promeni(*args):
        if izmena in ("povucen", "promenjen"):
            q = b.table("predmet_dokumenti")
            q = q.delete() if izmena == "povucen" else q.update({"tekst_sadrzaj": "Izmenjen zapisnik."})
            q.eq("id", did).execute()
        return odgovor(*args)

    monkeypatch.setattr(multi_agent, "_pozovi_nacrt_api", promeni)
    if izmena == "tokom_kvaliteta":
        from services import quality_gate

        async def kvalitet(*args):
            b.table("predmet_dokumenti").delete().eq("id", did).execute()
            return {"confidence_score": 0.5, "detail": {}}

        monkeypatch.setattr(quality_gate, "evaluate_draft_quality", kvalitet)
    response = _draft(k, pid)
    assert response.status_code == status, response.text
    assert len(b.naplate) == len(b.tabele["staging_memory"]) == (1 if status == 200 else 0)


def test_odbicen_upis_predloga_nema_uspeh_neto_debit_ni_duplo_izvrsenje(lit, monkeypatch):
    from postgrest.exceptions import APIError

    k, b, pid, _, _ = lit
    calls = _model(monkeypatch, json.dumps({"tekst_za_sud": SENTENCE, "napomene_za_advokata": []}))
    query = type(b.table("staging_memory"))
    execute = query.execute

    def odbij_upis(self):
        if self.t == "staging_memory" and self.radnja[0] == "insert":
            raise APIError({"code": "23514", "message": "Synthetic rejected INSERT"})
        return execute(self)

    monkeypatch.setattr(query, "execute", odbij_upis)
    headers = {**A, "Idempotency-Key": str(uuid4())}
    assert _draft(k, pid, headers).status_code == 503
    again = _draft(k, pid, headers)
    assert again.status_code == 503 and again.headers.get("idempotent-replayed") == "true"
    assert len(calls) == 1 and not b.naplate and not b.tabele["staging_memory"]


@pytest.mark.parametrize("upisan", [True, False])
def test_izgubljen_odgovor_upisa_ne_pravi_duplikat_ni_nepotvrdjen_povracaj(lit, monkeypatch, upisan):
    from unittest.mock import AsyncMock
    from shared.usage import UsageService

    k, b, pid, _, _ = lit
    calls = _model(monkeypatch, json.dumps({"tekst_za_sud": SENTENCE, "napomene_za_advokata": []}))
    query = type(b.table("staging_memory"))
    execute = query.execute

    def izgubi_odgovor(self):
        if self.t == "staging_memory" and self.radnja[0] == "insert":
            if upisan:
                execute(self)
            raise TimeoutError("Synthetic lost write response")
        return execute(self)

    refund = AsyncMock()
    monkeypatch.setattr(UsageService, "refund", refund)
    monkeypatch.setattr(query, "execute", izgubi_odgovor)
    headers = {**A, "Idempotency-Key": str(uuid4())}
    status = 200 if upisan else 503
    assert _draft(k, pid, headers).status_code == status
    again = _draft(k, pid, headers)
    assert again.status_code == status and again.headers.get("idempotent-replayed") == "true"
    assert len(calls) == 1 and len(b.naplate) == int(upisan)
    assert len(b.tabele["staging_memory"]) == int(upisan)
    refund.assert_not_awaited()
