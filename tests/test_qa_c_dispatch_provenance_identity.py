# -*- coding: utf-8 -*-
"""QA-C (2026-10-15) — identitet u AI provenance kontekstu tokom pozadinskog dispatch-a.

Nalaz (produkcija, read-only): AI pozivi iz handlera koje pokrece `dispatch_pending_events()` nisu imali
korisnika u `shared.ai_provenance` kontekstu, pa je `ai_forensics` red (user_id NOT NULL) propadao — 30 dana:
0 redova `case_pipeline` naspram 3 roka koje je Pipeline (AI) predlozio. Ovi testovi drze ugovor ispravke:

  * vlasnik je `events.user_id` reda koji se dispecuje — nikad prethodni red, spoljni kontekst ni izmisljen;
  * nevalidan/odsutan identitet ostaje None;
  * kontekst se vraca posle svakog reda, i kad handler baci izuzetak (retry/dead-letter netaknuti);
  * `correlation_id` reda se cuva.

Sinteticki podaci, bez mreze: OpenAI odgovara `httpx.MockTransport`, Supabase je lazni klijent.
"""
import asyncio
import json

import httpx
import pytest
from unittest.mock import MagicMock, patch

from api import app  # noqa: F401 -- bootstraps _patch_prompt_guard() (stvarna AI granica + provenance)

from services import event_bus as eb
import shared.ai_provenance as ai_provenance

U_A = "0a0a0a0a-0000-4000-8000-00000000000a"
U_B = "0b0b0b0b-0000-4000-8000-00000000000b"
P_A = "1a1a1a1a-0000-4000-8000-00000000001a"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _cist_kontekst():
    ai_provenance._request_ctx.set({})
    ai_provenance._case_ctx.set({})
    yield
    ai_provenance._request_ctx.set({})
    ai_provenance._case_ctx.set({})


def _supa(redovi, inserti=None, update=None):
    """Lazni Supabase: `events` vraca zadate redove (put bez RPC-a), ostale tabele prazne; belezi upise."""
    inserti = inserti if inserti is not None else []
    update = update if update is not None else []

    def _table(name):
        c = MagicMock()
        for m in ("select", "is_", "order", "limit", "eq", "neq", "like", "in_", "maybe_single", "single"):
            getattr(c, m).return_value = c
        r = MagicMock(); r.data = list(redovi) if name == "events" else []
        c.execute = MagicMock(return_value=r)

        def _ins(red):
            inserti.append((name, red)); return c
        c.insert = MagicMock(side_effect=_ins)

        def _upd(p):
            update.append((name, p)); return c
        c.update = MagicMock(side_effect=_upd)
        return c

    s = MagicMock()
    s.table = MagicMock(side_effect=_table)
    s.rpc = MagicMock(side_effect=Exception("PGRST202: Could not find the function public.claim_pending_events"))
    return s


def _red(rid, user_id, tip="rok_dodan", cid=None, attempts=0, predmet_id=None, payload=None):
    return {"id": rid, "event_type": tip, "user_id": user_id, "predmet_id": predmet_id,
            "payload": payload or {}, "dispatch_attempts": attempts, "correlation_id": cid}


async def _dispecuj(redovi, handleri, inserti=None, update=None):
    supa = _supa(redovi, inserti, update)
    with patch("shared.deps._get_supa", return_value=supa), patch.object(eb.bus, "_handlers", handleri):
        return await eb.dispatch_pending_events()


def _belezi(vidjeno, baci_za=()):
    async def _h(e):
        ctx = ai_provenance.current_context()
        vidjeno.append((e.event_id, ctx.get("user_id"), ctx.get("correlation_id")))
        if e.event_id in baci_za:
            raise RuntimeError("sinteticki pad handlera")
    return _h


# ── 1. PredmetKreiran → stvaran Case Pipeline korak → stvarna AI granica → ai_forensics red ─────────────────────

def _openai_mock_transport(pozivi):
    def _odgovor(request: httpx.Request) -> httpx.Response:
        pozivi.append(request.url.path)
        return httpx.Response(200, json={
            "id": "chatcmpl-qa", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": json.dumps({"rokovi": []})}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        })
    return httpx.MockTransport(_odgovor)


@pytest.mark.anyio
async def test_predmet_kreiran_ai_poziv_u_dispatchu_upisuje_forensics_red_vlasnika_i_korelacije():
    from openai import AsyncOpenAI
    from services import case_pipeline

    pozivi, inserti = [], []
    pravi_klijent = lambda **kw: AsyncOpenAI(api_key="sk-qa-sinteticki",  # noqa: E731
                                             http_client=httpx.AsyncClient(transport=_openai_mock_transport(pozivi)))

    async def _pipeline(predmet_id, user_id, skip_steps=frozenset()):
        # stvaran korak 3 (ekstrakcija rokova iz opisa), samo bez baze i mreze
        return await case_pipeline._step_ekstrakcija_rokova(
            supa_forenzika, predmet_id, user_id,
            {"naziv": "QA sinteticki", "opis": "Sinteticki opis predmeta: isporuka robe je ugovorena za kraj meseca."})

    supa_forenzika = _supa([], inserti)
    red = _red("evt-pk", U_A, tip="predmet_kreiran", cid="cid-predmet-a", predmet_id=P_A)
    with patch("services.case_pipeline.AsyncOpenAI", side_effect=pravi_klijent), \
         patch("services.case_pipeline.run_case_pipeline", side_effect=_pipeline), \
         patch("api._get_supa", return_value=supa_forenzika):
        rez = await _dispecuj([red], {eb.EventType.PREDMET_KREIRAN: [eb.on_predmet_kreiran]}, inserti)
        for _ in range(50):                                   # forensics upis je fire-and-forget (shared.bg)
            if any(t == "ai_forensics" for t, _ in inserti):
                break
            await asyncio.sleep(0.02)

    assert rez["dispecovano"] == 1 and rez["greske"] == 0
    assert pozivi == ["/v1/chat/completions"]                 # AI poziv je stvarno prosao kroz granicu
    forenzika = [r for t, r in inserti if t == "ai_forensics"]
    assert len(forenzika) == 1, inserti
    assert forenzika[0]["user_id"] == U_A
    assert forenzika[0]["correlation_id"] == "cid-predmet-a"
    # bez sirovog sadrzaja: samo hesevi prompta/odgovora
    assert "Sinteticki opis" not in json.dumps(forenzika[0], ensure_ascii=False)


@pytest.mark.anyio
async def test_bez_ispravke_isti_poziv_nema_korisnika():
    """Kontrola: ista AI granica bez dispatch konteksta daje user_id=None (ono sto je produkcija upisivala)."""
    from shared import ai_client
    uhvaceno = {}

    async def _log(**kw):
        uhvaceno.update(kw)
    resp = MagicMock(); resp.choices = []; resp.usage = None; resp.model = "gpt-4o-mini"
    with patch("security.ai_forensics.log_provenance_from_wrapper", _log):
        ai_client._capture_chat_provenance(MagicMock(), {"model": "m", "messages": [{"role": "user", "content": "x"}]}, resp, 1)
        await asyncio.sleep(0.05)
    assert "user_id" in uhvaceno and uhvaceno["user_id"] is None


# ── 2. Izolacija izmedju dogadjaja ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_dva_uzastopna_dogadjaja_razlicitih_korisnika_su_izolovana():
    vidjeno = []
    rez = await _dispecuj([_red("e1", U_A, cid="c1"), _red("e2", U_B, cid="c2")],
                          {eb.EventType.ROK_DODAN: [_belezi(vidjeno)]})
    assert rez["dispecovano"] == 2
    assert vidjeno == [("e1", U_A, "c1"), ("e2", U_B, "c2")]


@pytest.mark.anyio
@pytest.mark.parametrize("los", [None, "", "   ", "u1", "pred-1", "not-a-uuid", 42,
                                 "{" + U_B + "}", U_B.replace("-", ""), "urn:uuid:" + U_B])
async def test_nevalidan_identitet_ne_nasledjuje_prethodni_red_ni_spoljni_kontekst(los):
    ai_provenance.set_request_context(user_id="spoljni-korisnik", correlation_id="spoljni-cid")
    vidjeno = []
    await _dispecuj([_red("e1", U_A, cid="c1"), _red("e2", los, cid="c2")],
                    {eb.EventType.ROK_DODAN: [_belezi(vidjeno)]})
    assert vidjeno == [("e1", U_A, "c1"), ("e2", None, "c2")]
    # spoljni kontekst je netaknut posle dispatch-a
    assert ai_provenance.current_context().get("user_id") == "spoljni-korisnik"
    assert ai_provenance.current_context().get("correlation_id") == "spoljni-cid"


@pytest.mark.anyio
async def test_spoljni_kontekst_ne_procuri_u_dogadjaj_bez_korisnika():
    """Dispatch pozvan unutar zahteva korisnika X: dogadjaj bez vlasnika NE sme da dobije X."""
    ai_provenance.set_request_context(user_id=U_B, correlation_id="zahtev-x")
    vidjeno = []
    await _dispecuj([_red("e1", None)], {eb.EventType.ROK_DODAN: [_belezi(vidjeno)]})
    assert vidjeno[0][1] is None and vidjeno[0][2] != "zahtev-x"


# ── 3. Izuzetak u handleru: kontekst se vraca, retry/dead-letter netaknuti ───────────────────────────────────────

@pytest.mark.anyio
async def test_izuzetak_u_handleru_ne_ostavlja_kontekst_i_retry_je_isti():
    vidjeno, update = [], []
    rez = await _dispecuj([_red("e1", U_A, cid="c1"), _red("e2", None, cid="c2")],
                          {eb.EventType.ROK_DODAN: [_belezi(vidjeno, baci_za={"e1"})]}, update=update)
    assert vidjeno == [("e1", U_A, "c1"), ("e2", None, "c2")]
    assert ai_provenance.current_context().get("user_id") is None
    assert rez["greske"] == 1 and rez["dispecovano"] == 1 and rez["dead_letter"] == 0
    retry = [p for t, p in update if t == "events" and "dispatch_attempts" in p]
    assert len(retry) == 1 and retry[0]["dispatch_attempts"] == 1 and "dispatched_at" not in retry[0]


@pytest.mark.anyio
async def test_dead_letter_nepromenjen_i_kontekst_vracen():
    vidjeno, update = [], []
    rez = await _dispecuj([_red("e1", U_A, cid="c1", attempts=eb.MAX_DISPATCH_ATTEMPTS - 1), _red("e2", U_B, cid="c2")],
                          {eb.EventType.ROK_DODAN: [_belezi(vidjeno, baci_za={"e1"})]}, update=update)
    assert rez["dead_letter"] == 1 and rez["dispecovano"] == 1
    dl = [p for t, p in update if t == "events" and str(p.get("last_error", "")).startswith(eb.DEAD_LETTER_MARKER)]
    assert len(dl) == 1 and dl[0]["dispatch_attempts"] == eb.MAX_DISPATCH_ATTEMPTS
    assert vidjeno[1] == ("e2", U_B, "c2")
    assert ai_provenance.current_context().get("user_id") is None


# ── 4. correlation_id ───────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_red_bez_korelacije_ne_nasledjuje_korelaciju_prethodnog_reda():
    vidjeno = []
    await _dispecuj([_red("e1", U_A, cid="c1"), _red("e2", U_A, cid=None)],
                    {eb.EventType.ROK_DODAN: [_belezi(vidjeno)]})
    assert vidjeno[0][2] == "c1"
    assert vidjeno[1][2] and vidjeno[1][2] != "c1"


@pytest.mark.anyio
async def test_dogadjaj_i_dalje_nosi_originalni_user_id_reda():
    """Ownership dogadjaja se ne menja: handler dobija isti `event.user_id` kao pre ispravke."""
    dobijeno = []

    async def _h(e):
        dobijeno.append(e.user_id)
    await _dispecuj([_red("e1", U_A), _red("e2", None), _red("e3", "pred-1")], {eb.EventType.ROK_DODAN: [_h]})
    assert dobijeno == [U_A, "", "pred-1"]


# ── 5. _vlasnik_dogadjaja ───────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ulaz,izlaz", [
    (U_A, U_A), ("  " + U_A + "  ", U_A), (U_A.upper(), U_A),
    (None, None), ("", None), ("  ", None), (42, None), ("u1", None), ("pred-1", None),
    ("{" + U_A + "}", None), (U_A.replace("-", ""), None), ("urn:uuid:" + U_A, None),
])
def test_vlasnik_dogadjaja(ulaz, izlaz):
    assert eb._vlasnik_dogadjaja(ulaz) == izlaz
