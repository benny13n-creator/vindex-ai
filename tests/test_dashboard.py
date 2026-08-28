# -*- coding: utf-8 -*-
"""
Tests for routers/dashboard.py — Command Center + Matter Health Score.
All tests run without live Supabase (mocked with table-name routing).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
import pytest
from starlette.requests import Request as StarletteRequest

# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req(path="/api/dashboard/command-center"):
    scope = {"type":"http","method":"GET","headers":[],"query_string":b"","path":path,
             "app":MagicMock(),"state":MagicMock()}
    return StarletteRequest(scope=scope)


def _user():
    return {"user_id": "aaaa0000-0000-0000-0000-000000000001", "email": "test@vindex.rs"}


UID  = "aaaa0000-0000-0000-0000-000000000001"
PID  = "cccc0000-0000-0000-0000-000000000003"
PID2 = "dddd0000-0000-0000-0000-000000000004"


def _make_chain(data):
    """Return a mock chain that always returns `data` on .execute()."""
    chain = MagicMock()
    for attr in ['select','eq','neq','gte','lte','like','order','limit','execute',
                 'insert','update','delete','is_','in_','desc']:
        setattr(chain, attr, MagicMock(return_value=chain))
    r = MagicMock(); r.data = data
    chain.execute = MagicMock(return_value=r)
    return chain


def _make_cc_supa(predmeti=None, rocista=None, rokovi=None, risks=None,
                  beleske=None, dokumenti=None, ist_recent=None, rokovi_tabela=None,
                  dokazi=None):
    """
    Route by table name — safe for concurrent asyncio.gather calls.
    predmet_istorija is queried twice; discriminated by select() fields:
    - risk query selects "odgovor" → returns risks data
    - recent query selects only "predmet_id" → returns ist_recent data

    rokovi_tabela: rows from the separate "rokovi" table (nightly repair,
    2026-07-24) — distinct from "rokovi" the local variable name (which
    historically held predmet_hronologija rows; kept as-is to avoid
    touching every existing call site in this file).

    dokazi: predmet_dokazi rows (Operation Single Brain, 2026-08-07) -- feeds the
    LIVE calculate_procesni_rizik call now used for "current" risk (predmeti_visok_rizik);
    `dokumenti`/`rocista` are also reused for that live computation (this mock doesn't
    apply real column-selection/date filtering, so the same rows answer every query
    against that table name).
    """
    supa = MagicMock()
    risk_data    = risks      or []
    ist_rec_data = ist_recent or []

    table_map = {
        "predmeti":            predmeti      or [],
        "rocista":             rocista       or [],
        "predmet_hronologija": rokovi        or [],
        "predmet_beleske":     beleske       or [],
        "predmet_dokumenti":   dokumenti     or [],
        "rokovi":              rokovi_tabela or [],
        "predmet_dokazi":      dokazi        or [],
    }

    def _table(name):
        if name == "predmet_istorija":
            # Discriminate by select fields — thread-safe, no call counter needed
            def _select(fields):
                data = risk_data if "odgovor" in fields else ist_rec_data
                return _make_chain(data)
            chain = MagicMock()
            chain.select = MagicMock(side_effect=_select)
            return chain
        return _make_chain(table_map.get(name, []))

    supa.table = MagicMock(side_effect=_table)
    return supa


def _make_health_supa(pred=None, bel=None, risk=None, kom=None, hron=None, dok=None, roc=None, dokazi=None):
    """Route health queries by table name — each table queried at most once.
    `risk`/`hron` params are kept for signature compatibility with older
    call sites in this file but no longer read by matter_health_score since
    Project Sentinel (2026-08-03) delegated scoring to
    services/risk_engine.py::calculate_procesni_rizik — `dokazi` (predmet_dokazi)
    is the new input that actually drives the risk portion of the score."""
    supa = MagicMock()
    table_map = {
        "predmeti":            pred   or [],
        "predmet_beleske":     bel    or [],
        "predmet_istorija":    risk   or [],
        "predmet_komentari":   kom    or [],
        "predmet_hronologija": hron   or [],
        "predmet_dokumenti":   dok    or [],
        "rocista":             roc    or [],
        "predmet_dokazi":      dokazi or [],
    }
    supa.table = MagicMock(side_effect=lambda name: _make_chain(table_map.get(name, [])))
    return supa


# ═══════════════════════════════════════════════════════════════════════════════
# 1. command_center — happy path
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_cc_returns_required_keys():
    from routers.dashboard import command_center
    supa = _make_cc_supa(
        predmeti=[{"id": PID, "naziv": "Test", "status": "aktivan", "updated_at": "2026-01-01"}]
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    required = {"ukupno_predmeta","ukupno_aktivnih","rokovi_7_dana","hitni_rokovi",
                "neaktivni_30_dana","summary","danasnja_rocista","predmeti_visok_rizik",
                "pad_procene","novi_dokumenti","ai_preporuke","statistike"}
    assert required.issubset(set(result.keys()))


@pytest.mark.anyio
async def test_cc_predmeti_query_is_capped_and_ordered():
    """Final Beta Gate F25 (LOW-MEDIUM): the predmeti query used to have no
    .order()/.limit() at all, relying entirely on PostgREST's own implicit
    default cap -- invisible even on inspection. Now explicit."""
    from routers import dashboard

    # _make_cc_supa builds a FRESH chain per supa.table(name) call (no
    # caching), so a second supa.table("predmeti") call in the assertion
    # below would inspect a different mock than the one command_center
    # actually used -- cache by name here instead, same shape otherwise.
    _chains: dict = {}

    def _table(name):
        if name not in _chains:
            _chains[name] = _make_chain(
                [{"id": PID, "naziv": "Test", "status": "aktivan", "updated_at": "2026-01-01"}]
                if name == "predmeti" else []
            )
        return _chains[name]

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch.object(dashboard, "_get_supa", return_value=supa):
        result = await dashboard.command_center(request=_req(), user=_user())

    _chains["predmeti"].order.assert_any_call("updated_at", desc=True)
    _chains["predmeti"].limit.assert_any_call(dashboard._DASHBOARD_PREDMETI_CAP)
    assert result["predmeti_truncated"] is False


@pytest.mark.anyio
async def test_cc_discloses_predmeti_truncated_when_cap_reached():
    from routers import dashboard

    fake_cap = 3
    preds = [{"id": f"p{i}", "naziv": f"P{i}", "status": "aktivan", "updated_at": "2026-01-01"} for i in range(fake_cap)]
    supa = _make_cc_supa(predmeti=preds)

    with patch.object(dashboard, "_get_supa", return_value=supa), \
         patch.object(dashboard, "_DASHBOARD_PREDMETI_CAP", fake_cap):
        result = await dashboard.command_center(request=_req(), user=_user())

    assert result["predmeti_truncated"] is True


@pytest.mark.anyio
async def test_cc_empty_state():
    from routers.dashboard import command_center
    supa = _make_cc_supa()
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert result["ukupno_aktivnih"] == 0
    assert result["danasnja_rocista"] == []
    assert result["hitni_rokovi"] == []
    assert result["ai_preporuke"] == []
    assert "kontrolom" in result["summary"].lower()


@pytest.mark.anyio
async def test_cc_counts_aktivni():
    from routers.dashboard import command_center
    preds = [
        {"id": PID,  "naziv": "A", "status": "aktivan",  "updated_at": "2026-01-01"},
        {"id": PID2, "naziv": "B", "status": "zatvoren", "updated_at": "2026-01-01"},
    ]
    supa = _make_cc_supa(predmeti=preds)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert result["ukupno_predmeta"] == 2
    assert result["ukupno_aktivnih"] == 1


@pytest.mark.anyio
async def test_cc_rocista_today():
    from routers.dashboard import command_center
    from datetime import date
    today = date.today().isoformat()
    preds   = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    rocista = [{"id": "r1", "predmet_id": PID, "sud": "Viši sud", "datum": today, "vreme": "10:00:00", "status": "zakazano"}]
    supa = _make_cc_supa(predmeti=preds, rocista=rocista)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["danasnja_rocista"]) == 1
    assert result["danasnja_rocista"][0]["sud"] == "Viši sud"


@pytest.mark.anyio
async def test_cc_hitni_rokovi_within_48h():
    from routers.dashboard import command_center
    from datetime import date, timedelta
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    preds  = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    rokovi = [{"predmet_id": PID, "dogadjaj": "Rok za žalbu", "datum_iso": tomorrow, "vaznost": "kritičan"}]
    supa   = _make_cc_supa(predmeti=preds, rokovi=rokovi)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["hitni_rokovi"]) == 1
    assert result["hitni_rokovi"][0]["dogadjaj"] == "Rok za žalbu"


@pytest.mark.anyio
async def test_cc_rokovi_dolaze_iz_KANONSKOG_izvora():
    """BETA-DEADLINE-DOMAIN-001 (2026-08-14) — zamenjuje dva testa spajanja.

    STARI UGOVOR
        „Rok upisan kroz tabelu `rokovi` mora se pojaviti na Command Centru
        zajedno sa rokovima iz `predmet_hronologija`." (Nightly repair
        2026-07-24, Faza 2, stavka 5.)

    ZASTO JE STARI BIO POGRESAN
        Tabela `rokovi` NE POSTOJI u produkciji (`PGRST205`) i u celom repou
        nema nijedan `INSERT`/`UPDATE`/`UPSERT`/`DELETE` nad njom. Ta polovina
        spajanja vracala je nula redova svakog dana od kad je dodata, a
        `_safe()` je gutao gresku -- pa se „nema rokova" i „nisam mogao da
        pogledam" nisu razlikovali. Stari test je prolazio samo zato sto je
        njegov lazni Supabase izmisljao redove koje produkcija ne moze imati.

    NOVI UGOVOR
        Jedan kanonski izvor (`predmet_hronologija` preko `shared/rokovi.py`).
        Prazna lista je istina SAMO uz `rokovi_dostupni: True`.
    """
    from routers.dashboard import command_center
    from datetime import date, timedelta
    sutra = (date.today() + timedelta(days=1)).isoformat()
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    hron  = [{"id": "h1", "predmet_id": PID, "dogadjaj": "Žalba na presudu",
              "datum_iso": sutra, "vaznost": "kritičan", "akter": ""}]
    supa = _make_cc_supa(predmeti=preds, rokovi=hron)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())

    assert result["rokovi_dostupni"] is True
    assert any(r["dogadjaj"] == "Žalba na presudu" for r in result["rokovi_7_dana"])
    assert any(r["dogadjaj"] == "Žalba na presudu" for r in result["hitni_rokovi"])
    assert all(r["izvor"] == "predmet_hronologija" for r in result["rokovi_7_dana"])


@pytest.mark.anyio
async def test_cc_neuspeh_citanja_rokova_NIJE_prazan_dan():
    """NAJVAZNIJI TEST U OVOM FAJLU.

    Pad upita nad rokovima ranije je prolazio kroz `_safe()` i zavrsavao kao
    prazna lista -- ekran je tvrdio „Sve je pod kontrolom".
    """
    from routers.dashboard import command_center
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    supa = _make_cc_supa(predmeti=preds)

    async def _pao(*a, **k):
        from shared import rokovi as R
        return R.Rezultat(stanje=R.Stanje.NEUSPEH, rokovi=[], razlog="baza pala")

    with patch("routers.dashboard._get_supa", return_value=supa),          patch("routers.dashboard._rokovi_domen.rokovi_za_korisnika", new=_pao):
        result = await command_center(request=_req(), user=_user())

    assert result["rokovi_dostupni"] is False
    assert result["rokovi_7_dana"] == []
    assert "Sve je pod kontrolom" not in result["summary"], result["summary"]
    assert "nisu dostupni" in result["summary"]


@pytest.mark.anyio
async def test_cc_visok_rizik_detection():
    """Operation Single Brain (2026-08-07): 'current' risk is now computed LIVE via
    calculate_procesni_rizik, not read from the predmet_istorija cache -- a case with zero
    uploaded evidence and zero documents is deterministically 'Visok' by that engine's own
    formula (ukupno==0 -> +20 to rizik_score), same as every other live risk surface."""
    from routers.dashboard import command_center
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    supa  = _make_cc_supa(predmeti=preds, dokazi=[], dokumenti=[], rocista=[])
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["predmeti_visok_rizik"]) == 1
    assert result["predmeti_visok_rizik"][0]["rizik_nivo"] == "visok"


@pytest.mark.anyio
async def test_cc_pad_procene():
    """Operation Single Brain (2026-08-07): pad_procene now compares the LIVE current risk
    against the most recent HISTORICAL snapshot (not two historical snapshots against each
    other) -- the exact fix for the stale-cache bug Red Team reproduced on this endpoint.
    Case has zero evidence/documents (-> live 'Visok', same as the test above); the cache's
    only entry says the case was 'nizak' as of its last snapshot -- a genuine risk increase."""
    from routers.dashboard import command_center
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    risks = [
        {"predmet_id": PID, "odgovor": json.dumps({"nivo": "nizak"}), "created_at": "2026-06-01"},
    ]
    supa = _make_cc_supa(predmeti=preds, risks=risks, dokazi=[], dokumenti=[], rocista=[])
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["pad_procene"]) == 1
    assert result["pad_procene"][0]["prethodni_rizik"] == "nizak"
    assert result["pad_procene"][0]["trenutni_rizik"] == "visok"


@pytest.mark.anyio
async def test_cc_visok_rizik_reflects_live_data_not_stale_cache():
    """The Red Team's own flagship reproduction, restated as a regression test on THIS endpoint
    specifically (a sibling of api.py::predmeti_dashboard, which Operation One Truth already
    fixed -- this one was missed until Operation Single Brain). A stale cache claiming 'nizak'
    must not suppress a live-computed 'visok'."""
    from routers.dashboard import command_center
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    stale_cache = [{"predmet_id": PID, "odgovor": json.dumps({"nivo": "nizak"}), "created_at": "2020-01-01"}]
    supa = _make_cc_supa(predmeti=preds, risks=stale_cache, dokazi=[], dokumenti=[], rocista=[])
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["predmeti_visok_rizik"]) == 1
    assert result["predmeti_visok_rizik"][0]["rizik_nivo"] == "visok"


@pytest.mark.anyio
async def test_cc_neaktivni_predmeti():
    from routers.dashboard import command_center
    preds = [
        {"id": PID,  "naziv": "Aktivan", "status": "aktivan", "updated_at": "2026-05-01"},
        {"id": PID2, "naziv": "Neaktiv", "status": "aktivan", "updated_at": "2026-01-01"},
    ]
    # PID has recent beleska → active. PID2 has nothing → neaktivan.
    beleske    = [{"predmet_id": PID}]
    ist_recent = []
    supa = _make_cc_supa(predmeti=preds, beleske=beleske, ist_recent=ist_recent)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    neaktivni_ids = [n["predmet_id"] for n in result["neaktivni_30_dana"]]
    assert PID2 in neaktivni_ids
    assert PID not in neaktivni_ids


@pytest.mark.anyio
async def test_cc_novi_dokumenti():
    from routers.dashboard import command_center
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-06-01"}]
    docs  = [{"id": "d1", "predmet_id": PID, "naziv_fajla": "ugovor.pdf", "created_at": "2026-06-14T10:00:00"}]
    supa  = _make_cc_supa(predmeti=preds, dokumenti=docs)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["novi_dokumenti"]) == 1
    assert result["novi_dokumenti"][0]["naziv_fajla"] == "ugovor.pdf"


@pytest.mark.anyio
async def test_cc_ai_preporuke_generated():
    from routers.dashboard import command_center
    from datetime import date
    today = date.today().isoformat()
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    rocs  = [{"id": "r1", "predmet_id": PID, "sud": "Sud", "datum": today, "vreme": "09:00:00", "status": "zakazano"}]
    supa  = _make_cc_supa(predmeti=preds, rocista=rocs)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["ai_preporuke"]) >= 1
    assert any("ročiš" in p.lower() for p in result["ai_preporuke"])


@pytest.mark.anyio
async def test_cc_statistike_keys():
    from routers.dashboard import command_center
    supa = _make_cc_supa()
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    for k in ("ukupno_aktivnih","danasnja_rocista","hitni_rokovi","predmeti_visok_rizik","neaktivni"):
        assert k in result["statistike"]


@pytest.mark.anyio
async def test_cc_handles_db_exceptions():
    from routers.dashboard import command_center
    supa = MagicMock()
    supa.table.side_effect = Exception("DB down")
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert result["ukupno_predmeta"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. matter_health_score
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_health_404_missing_predmet():
    from routers.dashboard import matter_health_score
    from fastapi import HTTPException
    supa = _make_health_supa(pred=[])
    with patch("routers.dashboard._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_health_max_score():
    """Project Sentinel (2026-08-03): score/status now come exclusively from
    services/risk_engine.py::calculate_procesni_rizik (same source ccc.py and
    matter_intel.py already use) instead of this endpoint's own 5-category
    formula. With strong evidence (jaka), no missing expected doc types, and
    no critical (0-7 day) rociste, the risk formula's own floor for
    rizik_score is 30 (the only available discount is -20 for "Jaka" off a
    base of 50) → health_score=70, nivo="Nizak" → status="zdrav"."""
    from routers.dashboard import matter_health_score
    far_future = (date.today() + timedelta(days=60)).isoformat()
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}],
        bel=[{"id": "b1"}],                                            # aktivnost present
        # TASK 004A: fixture EKSPLICITNO predstavlja procenjenu dokaznu stavku.
        # Scenario ovog testa je „predmet SA jakim dokazom" -- da bi to bio jak
        # dokaz, neko ga je morao proceniti. Do TASK-a 004 se to podrazumevalo
        # jer je `snaga` bila NOT NULL DEFAULT 'srednja'; sada provenance mora
        # biti izrečena. `covek` = advokat je izričito ocenio snagu.
        dokazi=[{"snaga": "jaka", "izvor_snage": "covek"}],            # snaga_dokaza=Jaka
        dok=[{"id": "d1", "tip_dokaza": "podnesak"},
             {"id": "d2", "tip_dokaza": "dopis"}],                     # covers both EXPECTED_DOCS["ostalo"]
        roc=[{"datum": far_future}],                                   # non-critical, but present
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["score"] == 70
    assert result["status"] == "zdrav"
    assert result["razlozi"] == []
    assert result["faktori"]["ima_rociste"] is True


@pytest.mark.anyio
async def test_health_kriticno_no_activity_high_risk():
    """No dokazi at all (+20) plus a critical (within 7 days) rociste (+20)
    → rizik_score=90 → health_score=10, nivo="Visok" → status="kriticno"."""
    from routers.dashboard import matter_health_score
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}],
        bel=[], kom=[],
        dokazi=[],
        dok=[],
        roc=[{"datum": tomorrow}],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["score"] < 50
    assert result["status"] == "kriticno"
    assert len(result["razlozi"]) >= 2


@pytest.mark.anyio
async def test_health_faktori_aktivnost_reports_real_subscore_not_total():
    """NIGHTLY REPAIR (2026-07-24), Faza 2 item 7: faktori.aktivnost used
    to be a nonsensical re-derivation from the TOTAL score. This test picks
    a case with no activity but a real (non-zero) total health_score, to
    prove aktivnost is reported independently of the total."""
    from routers.dashboard import matter_health_score
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}],
        bel=[], kom=[],                      # NEMA aktivnosti -> aktivnost poeni = 0
        # TASK 004A: Fixture explicitly represents an assessed evidence item.
        # Tvrdnja ovog testa je `faktori.aktivnost == 0` nezavisno od totala;
        # `score == 70` je SPOREDNA premisa koja samo obezbeđuje da total nije
        # nula. Premisa se čuva time što se dokaz izriče kao procenjen -- ne
        # menjanjem očekivanog broja.
        dokazi=[{"snaga": "jaka", "izvor_snage": "covek"}],  # health_score=70 (non-zero, non-25-coincidence)
        dok=[{"id": "d1", "tip_dokaza": "podnesak"}, {"id": "d2", "tip_dokaza": "dopis"}],
        roc=[],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["score"] == 70
    assert result["faktori"]["aktivnost"] == 0


@pytest.mark.anyio
async def test_health_faktori_aktivnost_reports_25_when_activity_present():
    from routers.dashboard import matter_health_score
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}],
        bel=[{"id": "b1"}],                  # ima aktivnosti -> 25 poena
        dokazi=[{"snaga": "jaka"}],
        dok=[{"id": "d1", "tip_dokaza": "podnesak"}, {"id": "d2", "tip_dokaza": "dopis"}],
        roc=[],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["faktori"]["aktivnost"] == 25


@pytest.mark.anyio
async def test_health_upozorenje_range():
    """dokazi snage "srednja" doesn't move rizik_score off its base of 50
    (only "Jaka"/-20 and "Slaba"/+15 do) → health_score=50, nivo="Srednji"
    → status="upozorenje"."""
    from routers.dashboard import matter_health_score
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}],
        bel=[],
        # TASK 004A: Fixture explicitly represents an assessed evidence item.
        # `srednja` kao PROCENJENA vrednost može poticati isključivo od čoveka:
        # DC-005 vraća `srednja` samo kada tvrdnju NIJE našao, a to je po F4
        # ugovoru `podrazumevano` (neprocenjeno), ne `dc005`.
        dokazi=[{"snaga": "srednja", "izvor_snage": "covek"}],
        dok=[{"id": "d1", "tip_dokaza": "podnesak"}, {"id": "d2", "tip_dokaza": "dopis"}],
        roc=[],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["score"] == 50
    assert result["status"] == "upozorenje"


@pytest.mark.anyio
async def test_health_returns_predmet_id():
    from routers.dashboard import matter_health_score
    supa = _make_health_supa(pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}])
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["predmet_id"] == PID
    assert "score" in result
    assert "status" in result
    assert "razlozi" in result
    assert "faktori" in result


@pytest.mark.anyio
async def test_health_hitni_rokovi_reduce_score():
    """Project Sentinel (2026-08-03): 'hitnih_rokova' now comes from
    calculate_procesni_rizik's kriticni_rokovi count, which reads the
    `rocista` table (0-7 day window), not predmet_hronologija's `vaznost`
    tag (48h window) the old formula used — a different canonical source,
    same observable guarantee: multiple near-term hearings visibly reduce
    the score and appear in razlozi."""
    from routers.dashboard import matter_health_score
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}],
        bel=[{"id": "b1"}],
        dokazi=[{"snaga": "jaka"}],
        dok=[{"id": "d1", "tip_dokaza": "podnesak"}, {"id": "d2", "tip_dokaza": "dopis"}],
        roc=[{"datum": tomorrow}, {"datum": tomorrow}],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["faktori"]["hitnih_rokova"] == 2
    assert any("kritičan rok" in r.lower() for r in result["razlozi"])


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Router registration
# ═══════════════════════════════════════════════════════════════════════════════

def test_router_has_command_center():
    from routers.dashboard import router
    paths = [r.path for r in router.routes]
    assert "/api/dashboard/command-center" in paths


def test_router_has_health():
    from routers.dashboard import router
    paths = [r.path for r in router.routes]
    assert "/api/predmeti/{predmet_id}/health" in paths


def test_router_tags():
    from routers.dashboard import router
    assert "dashboard" in router.tags
