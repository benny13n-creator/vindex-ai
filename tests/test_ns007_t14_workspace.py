"""NS007 Task 14 — Workspace: korpa „Vindex je pripremio" (READY_FOR_REVIEW radni proizvodi), aditivno.

Samo vlasnikovi, samo aktivni predmeti, samo READY; ne ulazi u druge korpe ni u `ukupno_aktivnih`; tabela ne postoji
(kod pre migracije 136) → korpa isključena a tabla potpuna; druga greška → nepročitan izvor; 0 poziva modela.
"""
import pytest

import tests.ns007_fake as f7

PA, PZ, PB = ("aaaaaaaa-1111-4000-8000-00000000000a", "aaaaaaaa-2222-4000-8000-00000000000a",
              "bbbbbbbb-1111-4000-8000-00000000000b")


def _rad(wid, uid, pid, status="READY_FOR_REVIEW", ready="2026-10-10T03:00:00+00:00", naslov="Priprema za ročište"):
    return {"id": wid, "user_id": uid, "predmet_id": pid, "agent_type": "hearing_prep", "work_type": "HEARING_PREP",
            "trigger_type": "ROCISTE", "trigger_ref": "r", "dedupe_key": wid, "reason": "Ročište sutra (11.10.2026.)",
            "cost_class": "PAID", "budget_key": "b", "status": status, "title": naslov, "summary": "Sažetak",
            "quality_state": "AI_PREPARED_FOR_REVIEW", "ready_at": ready, "content_json": {"x": 1}}


@pytest.fixture
def svet(monkeypatch):
    k, baza = f7.pripremi(monkeypatch, {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Petrović protiv Gradnja Invest DOO", "status": "aktivan"},
                     {"id": PZ, "user_id": "uid-A", "naziv": "Zatvoren predmet", "status": "zatvoren"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Tajni predmet B", "status": "aktivan"}],
        "autonomy_work_items": [_rad("w1", "uid-A", PA, ready="2026-10-10T03:00:00+00:00"),
                                _rad("w2", "uid-A", PA, ready="2026-10-10T04:00:00+00:00", naslov="Nova praksa"),
                                _rad("w3", "uid-A", PA, status="QUEUED"), _rad("w4", "uid-A", PA, status="ACCEPTED"),
                                _rad("w5", "uid-A", PA, status="SUPERSEDED"), _rad("w6", "uid-A", PZ),
                                _rad("w7", "uid-B", PB, naslov="Tajna priprema B")],
        "case_actions": [], "zadaci": [], "intake_jobs": []})
    yield k, baza, monkeypatch
    f7.ocisti()


def test_korpa_samo_spremno_svoje_aktivno_bez_modela(svet):
    k, _, mp = svet
    import openai

    class _Z:
        def __init__(self, *a, **kw):
            raise AssertionError("Workspace ne zove model")
    mp.setattr(openai, "OpenAI", _Z)
    mp.setattr(openai, "AsyncOpenAI", _Z)
    w = k.get("/api/workspace", headers=f7.zaglavlje("A")).json()
    assert [x["id"] for x in w["vindex_je_pripremio"]] == ["w2", "w1"], "samo READY, svoje, aktivni predmet, najnovije prvo"
    x = w["vindex_je_pripremio"][1]
    assert x == {"vrsta": "pripremljeno", "id": "w1", "predmet_id": PA, "predmet_naziv": "Petrović protiv Gradnja Invest DOO",
                 "naslov": "Priprema za ročište", "tip": "HEARING_PREP", "razlog": "Ročište sutra (11.10.2026.)",
                 "sazetak": "Sažetak", "kvalitet": "AI_PREPARED_FOR_REVIEW", "pripremljeno": "2026-10-10T03:00:00+00:00",
                 "case_action_id": None}
    assert w["vindex_je_pripremio_stanje"] == "OK" and w["provera_potpuna"] is True
    assert w["ukupno_aktivnih"] == 0, "pripremljen rad nije zadatak"
    for korpa in ("danas", "kriticno", "predstojece", "za_pregled", "na_cekanju", "zavrseno_nedavno"):
        assert all(s.get("vrsta") != "pripremljeno" for s in w[korpa])
    assert "Tajna priprema B" not in str(w) and "Tajni predmet B" not in str(w)
    b = k.get("/api/workspace", headers=f7.zaglavlje("B")).json()
    assert [x["id"] for x in b["vindex_je_pripremio"]] == ["w7"]


def test_tabela_ne_postoji_korpa_iskljucena_tabla_potpuna(svet):
    k, baza, _ = svet
    baza.greske["autonomy_work_items"] = RuntimeError(
        '{"code": "PGRST205", "message": "Could not find the table \'public.autonomy_work_items\' in the schema cache"}')
    w = k.get("/api/workspace", headers=f7.zaglavlje("A")).json()
    assert w["vindex_je_pripremio"] == [] and w["vindex_je_pripremio_stanje"] == "NIJE_UKLJUCENO"
    assert w["provera_potpuna"] is True and w["degradirani_izvori"] == []


def test_druga_greska_je_neprocitan_izvor(svet):
    k, baza, _ = svet
    baza.greske["autonomy_work_items"] = RuntimeError("canceling statement due to statement timeout")
    w = k.get("/api/workspace", headers=f7.zaglavlje("A")).json()
    assert w["vindex_je_pripremio"] == [] and w["vindex_je_pripremio_stanje"] == "NIJE_PROCITANO"
    assert w["provera_potpuna"] is False and "pripremljeni rad" in w["degradirani_izvori"]


def test_rad_drugog_korisnika_na_mom_predmetu_se_ne_prikazuje(svet):
    """Odbrana u dubinu: oštećen red (rad korisnika B zakačen za predmet A) ne ulazi u tablu korisnika A."""
    k, baza, _ = svet
    baza.tabele["autonomy_work_items"].append(_rad("w8", "uid-B", PA, naslov="Tuđi rad na mom predmetu"))
    w = k.get("/api/workspace", headers=f7.zaglavlje("A")).json()
    assert "w8" not in [x["id"] for x in w["vindex_je_pripremio"]]
