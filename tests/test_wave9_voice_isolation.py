# -*- coding: utf-8 -*-
"""
Wave 9 / D2 — Voice ostaje van bete, ali FIZIČKI, ne samo u UI-ju.

ZABRANJENO STANJE KOJE OVI TESTOVI ZATVARAJU

    „voice disabled in UI, but raw WSS endpoint still usable"

IZMERENO STANJE PRE IZMENE

Kapija u `routers/voice_realtime.py::_authenticate` JESTE bila fail-closed —
i za tarifu (Governance Wave 2) i za grešku pri čitanju profila. Nalaz nije bio
u toj kapiji nego u tome što je ona bila kapija JEDNOG pozivnog mesta:
`services/voice_orchestrator.py::VoiceOrchestratorSession.start()` otvarao je
sirov WebSocket ka `wss://api.openai.com/v1/realtime` bez ijedne sopstvene
provere. Konstruisati sesiju iz bilo kog drugog konteksta (novi ruter, pozadinski
posao, alat) značilo je otvoriti privilegovani kanal bez ijedne provere prava.

Druga izmerena sitnica u ruteru: `policy.get("aktivno", True)` — podrazumevana
vrednost je bila **True**, dakle „ako ne znam, puštam". Kapija u orkestratoru
čita istu vrednost sa podrazumevanom **False**.

ŠTA NIJE DUPLIRANO

`tests/test_voice_beta_killswitch.py` pokriva kill-switch na HTTP rutama.
`tests/test_gov2_voice_ws_tier_gate.py` pokriva `_authenticate` kao funkciju,
sa mock-ovanim `get_policy`. Ovde se namerno radi drugačije: kroz STVARAN
WebSocket handshake (`TestClient.websocket_connect`) i kroz STVARAN
`feature_registry` put (puni se keš, ne mock-uje se `get_policy`) — pa test
pada i ako se pokvari čitanje registry-ja, ne samo ako se pokvari kapija.
"""
import os
import sys
import time as _time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import shared.feature_registry as _fr  # noqa: E402
import services.voice_orchestrator as vo  # noqa: E402

_NIJE_FOUNDER = "advokat.wave9@test.rs"
_TOKEN_PAYLOAD = {"sub": "u-wave9", "email": _NIJE_FOUNDER}


def _politika(aktivno: bool = True, status: str = "ACTIVE",
              minimum_plan: str = "professional") -> dict:
    """Red `voice` iz `feature_registry`-ja (migracija 064:136)."""
    return {
        "feature_key": "voice", "naziv": "Glasovne komande",
        "aktivno": aktivno, "status": status,
        "minimum_plan": minimum_plan, "addon": None,
        "krediti": 0, "dnevni_limit": None, "mesecni_limit": None,
        "cooldown_seconds": 3, "ai_model": "whisper+tts",
    }


@pytest.fixture(scope="module")
def client():
    from api import app
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def registry():
    """Puni keš registry-ja i vraća ga u prvobitno stanje posle testa.

    `_CACHE_LOADED_AT` mora da se postavi — inače `get_policy` smatra keš
    hladnim i pokušava mrežni poziv (`shared/feature_registry.py:48-68`).
    """
    stari_cache = dict(_fr._CACHE)
    stari_ts = _fr._CACHE_LOADED_AT

    def _postavi(**kw):
        _fr._CACHE["voice"] = _politika(**kw)
        _fr._CACHE_LOADED_AT = _time.monotonic()

    _postavi()
    yield _postavi

    _fr._CACHE.clear()
    _fr._CACHE.update(stari_cache)
    _fr._CACHE_LOADED_AT = stari_ts


@pytest.fixture(autouse=True)
def bez_kill_switcha(monkeypatch):
    monkeypatch.delenv(vo._VOICE_KILL_ENV, raising=False)


def _profil(tarifa: str) -> dict:
    return {
        "subscription_type": tarifa, "addons": [],
        "subscription_expires_at": None, "credits_remaining": 100,
        "is_pro": tarifa != "basic",
    }


def _pokusaj_handshake(client, tarifa: str = "professional"):
    """Stvaran WebSocket handshake kroz FastAPI TestClient.

    Vraća close kod. Ruter radi `accept()` pa tek onda proverava prava, pa se
    odbijanje vidi kao `WebSocketDisconnect` na prvom `receive`, ne kao
    neuspeo handshake — zato se poruka mora zatražiti, inače bi test prolazio
    i sa potpuno otvorenim kanalom.
    """
    from starlette.websockets import WebSocketDisconnect

    with patch("routers.voice_realtime._verify_token", return_value=dict(_TOKEN_PAYLOAD)), \
         patch("shared.permissions._ensure_profile", new=AsyncMock(return_value=_profil(tarifa))):
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/api/voice/realtime/ws?token=tok") as ws:
                ws.receive_text()
    return exc.value.code


# ═══════════════════════════════════════════════════════════════════════════
# 1. HANDSHAKE — stvaran WS, ne grep
# ═══════════════════════════════════════════════════════════════════════════

def test_a_basic_korisnik_ne_moze_da_otvori_kanal(client):
    """Basic je PODRAZUMEVANA tarifa svake nove registracije.

    `voice` traži `professional`. Da ovaj test padne, svaka nova registracija bi
    imala otvoren realtime kanal koji joj je na HTTP-u zatvoren.
    """
    assert _pokusaj_handshake(client, "basic") == 4401


def test_b_professional_je_odbijen_dok_je_voice_ugasen(client, registry):
    """Kill switch je iznad tarife.

    Da je tarifna provera stavljena ispred kill-switcha, gašenje voice-a za
    betu ne bi važilo za naloge koje tarifa inače propušta.
    """
    registry(aktivno=False)
    assert _pokusaj_handshake(client, "professional") == 4401


def test_c_enterprise_je_odbijen_dok_je_voice_ugasen(client, registry):
    """Ista tvrdnja na najvišoj tarifi — kill switch nema tarifni izuzetak."""
    registry(aktivno=False)
    assert _pokusaj_handshake(client, "enterprise") == 4401


# ═══════════════════════════════════════════════════════════════════════════
# 2. FAIL-CLOSED — najvažniji test u fajlu
# ═══════════════════════════════════════════════════════════════════════════

def test_d_greska_pri_citanju_dozvole_ZATVARA_kanal(client):
    """Registry nedostupan → kanal se ZATVARA, ne otvara.

    Namerno se ne mock-uje `get_policy` nego se obara sloj ISPOD njega
    (`_load_sync`) uz prazan keš — tako se meri stvaran put čitanja, uključujući
    i slučaj „red `voice` ne postoji u tabeli" (`get_policy` tada diže
    RuntimeError). Da je bilo gde na tom putu `except: pass`, pad baze bi
    otvarao glasovni kanal svima.
    """
    from starlette.websockets import WebSocketDisconnect

    _fr._CACHE.clear()
    _fr._CACHE_LOADED_AT = 0.0

    with patch.object(_fr, "_load_sync", side_effect=RuntimeError("supabase down")), \
         patch("routers.voice_realtime._verify_token", return_value=dict(_TOKEN_PAYLOAD)), \
         patch("shared.permissions._ensure_profile", new=AsyncMock(return_value=_profil("enterprise"))):
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/api/voice/realtime/ws?token=tok") as ws:
                ws.receive_text()

    assert exc.value.code in (4401, 1011), (
        f"kanal je otvoren uprkos tome što dozvola nije mogla da se pročita "
        f"(close kod {exc.value.code}) — FAIL-OPEN"
    )


@pytest.mark.asyncio
async def test_e_orkestrator_odbija_kad_registry_puca():
    """Ista tvrdnja na sirovom chokepoint-u, nezavisno od rutera.

    Kapija u ruteru pokriva jedno pozivno mesto. Ova pokriva mesto gde se
    konekcija ka OpenAI-ju stvarno otvara.
    """
    with patch("shared.feature_registry.get_policy",
               new=AsyncMock(side_effect=RuntimeError("registry nedostupan"))):
        with pytest.raises(vo.VoiceEntitlementError):
            await vo.proveri_voice_dozvolu({"user_id": "u1", "email": _NIJE_FOUNDER})


@pytest.mark.asyncio
async def test_f_prazna_politika_znaci_ISKLJUCENO_ne_ukljuceno():
    """DEFAULT DISABLED.

    Ako red postoji ali je bez `aktivno` (nepotpun red, delimična migracija,
    ručna izmena u Supabase Dashboard-u), podrazumevana vrednost mora biti
    ISKLJUČENO. Ruter na istom mestu čita `.get("aktivno", True)` — v. izveštaj,
    to je izvan opsega ovog agenta.
    """
    with patch("shared.feature_registry.get_policy", new=AsyncMock(return_value={})):
        with pytest.raises(vo.VoiceEntitlementError):
            await vo.proveri_voice_dozvolu({"user_id": "u1", "email": _NIJE_FOUNDER})


@pytest.mark.asyncio
async def test_g_odbijena_sesija_ne_otvara_upstream():
    """Dokaz da odbijanje znači „nijedan bajt nije otišao".

    Bez ovoga bi „sesija je odbijena" moglo da znači i „konekcija je otvorena
    pa zatvorena", što za sirov WSS ka OpenAI-ju nije isto.
    """
    fabrika = AsyncMock(name="_connect_openai_realtime")
    sesija = vo.VoiceOrchestratorSession(MagicMock(), {"user_id": "u1", "email": _NIJE_FOUNDER},
                                         openai_ws_factory=fabrika)
    with patch("shared.feature_registry.get_policy",
               new=AsyncMock(return_value=_politika(aktivno=False))):
        with pytest.raises(vo.VoiceEntitlementError):
            await sesija.start()

    fabrika.assert_not_awaited()
    assert sesija.upstream is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. KILL SWITCH — env nivo, radi i kad je baza nedostupna
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("tarifa", ["professional", "enterprise"])
async def test_h_env_kill_switch_odbija_bez_obzira_na_tarifu(monkeypatch, tarifa):
    """`VINDEX_VOICE_KILL=1` gasi sirov WSS kanal bez ijednog upita ka bazi.

    Kill switch u bazi (`feature_registry.voice.aktivno`) je kanonski i pokriva
    HTTP i WS. Ovaj env prekidač postoji zato što kanonski zavisi od iste baze
    čiji pad je scenario u testu `test_d` — vlasniku treba prekidač koji radi i
    tada.
    """
    monkeypatch.setenv(vo._VOICE_KILL_ENV, "1")
    get_policy = AsyncMock(return_value=_politika())
    with patch("shared.feature_registry.get_policy", new=get_policy), \
         patch("shared.permissions._ensure_profile", new=AsyncMock(return_value=_profil(tarifa))):
        with pytest.raises(vo.VoiceEntitlementError) as exc:
            await vo.proveri_voice_dozvolu({"user_id": "u1", "email": _NIJE_FOUNDER})

    assert "VINDEX_VOICE_KILL" in str(exc.value)
    get_policy.assert_not_awaited(), "kill switch mora da radi i kad je baza nedostupna"


def test_i_env_kill_switch_zatvara_stvaran_handshake(client, monkeypatch):
    """Prekidač mora da važi na stvarnoj ruti, ne samo u pomoćnoj funkciji."""
    monkeypatch.setenv(vo._VOICE_KILL_ENV, "1")
    assert _pokusaj_handshake(client, "enterprise") in (4401, 1011)


# ═══════════════════════════════════════════════════════════════════════════
# 4. POZITIVNA KONTROLA — bez nje sve gore znači samo „kanal je mrtav"
# ═══════════════════════════════════════════════════════════════════════════

def test_j_pun_entitlement_otvara_kanal_i_ostavlja_provenance(client):
    """Professional + `aktivno=true` + bez kill switcha → handshake PROLAZI.

    Istovremeno se meri i mandat §13.5: ako voice ostane aktivan za nekog, taj
    put mora imati provenance trag. Do ove izmene sirov WSS nije ostavljao
    NIJEDAN red — sesija je bila potpuno nevidljiva u `ai_forensics`.
    """
    class _LazniUpstream:
        def __init__(self):
            self.sent = []

        async def send(self, raw):
            self.sent.append(raw)

        async def close(self):
            pass

    upstream = _LazniUpstream()

    async def _bez_relaya(self):
        return

    prov = AsyncMock()
    with patch("routers.voice_realtime._verify_token", return_value=dict(_TOKEN_PAYLOAD)), \
         patch("shared.permissions._ensure_profile", new=AsyncMock(return_value=_profil("professional"))), \
         patch("services.voice_orchestrator._connect_openai_realtime",
               new=AsyncMock(return_value=upstream)), \
         patch("security.ai_forensics.log_provenance_from_wrapper", new=prov), \
         patch.object(vo.VoiceOrchestratorSession, "relay_client_to_upstream", new=_bez_relaya), \
         patch.object(vo.VoiceOrchestratorSession, "relay_upstream_to_client", new=_bez_relaya):
        with client.websocket_connect("/api/voice/realtime/ws?token=tok") as ws:
            ws.close()

    assert upstream.sent, "sesija je otvorena ali session.update nikad nije poslat"

    import routers.voice_realtime as vr
    assert vr._active_sessions.get("u-wave9", 0) == 0, "brojač sesija nije dekrementovan"

    prov.assert_awaited()
    kw = prov.await_args.kwargs
    assert kw["model_provider"] == "openai-realtime-raw-wss"
    assert kw["operation_name"] == "voice_realtime_session"
    assert kw["user_id"] == "u-wave9"
