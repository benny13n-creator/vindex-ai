# -*- coding: utf-8 -*-
"""
§9 — Vindex Live (glasovni kanal) van beta površine.

ZAŠTO SE VOICE GASI ZA BETU, A NE INSTRUMENTUJE

Glasovni realtime kanal (`services/voice_orchestrator.py:246`) ide sirovim
WebSocket-om ka OpenAI Realtime API-ju, ne kroz OpenAI SDK. Monkey-patch iz
`shared/ai_client.py` presreće SDK klase, pa taj kanal fizički ne vidi.
Posledica: nijedan `ai_forensics` red ne postoji ni za jednu Vindex Live
sesiju.

Bitna preciznost -- kanal NIJE bez kontrole. Alati sa `mutates_data=True`
traže eksplicitnu potvrdu iz browsera pre izvršenja (`voice_orchestrator.py:14`),
i to je pokriveno testovima u `tests/test_voice_realtime.py`. Voice ne može
tiho da DELUJE. Ali može tiho da SLUŠA -- privilegovani razgovor advokata sa
klijentom prolazi kroz kanal bez traga.

To je pitanje privilegije i GDPR-a, ne funkcionalnosti. Instrumentacija sirovog
WSS kanala je pravi arhitektonski posao. Gašenje funkcije za betu je jedan red
u bazi. Za beta prozor bira se drugo.

ŠTA OVI TESTOVI ŠTITE

Da kill-switch STVARNO zatvara HTTP glasovne rute. Kolona `aktivno` postoji od
migracije 064, ali "deklarisano != sprovedeno" je obrazac koji je ovaj projekat
već platio -- postojanje kolone nije dokaz da je iko čita.

WS putanja je već pokrivena: `tests/test_voice_realtime.py::test_ws_rejects_when_feature_inactive`.
Ovde se namerno NE duplira; pokriva se HTTP putanja koja tamo nije dodirnuta.
"""
import os
import sys
import time as _time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import shared.feature_registry as _fr  # noqa: E402
from shared.permissions import PermissionService  # noqa: E402

_FAKE_USER = {"user_id": "test-user-id", "email": "advokat@test.com"}
_FAKE_PROFILE = {
    "credits_remaining": 100, "is_pro": True,
    "subscription_type": "professional", "addons": [], "subscription_expires_at": None,
}

# Glasovne HTTP rute (`routers/voice.py`), sve tri iza PermissionService.require("voice").
_VOICE_RUTE = ("/api/voice/transcribe", "/api/voice/tts", "/api/voice/command")


def _policy(aktivno: bool) -> dict:
    """Red iz feature_registry-ja za `voice`, prema migraciji 064:136.

    PAŽNJA na `dnevni_limit`. Red glasi `(..., 0, 2, NULL, NULL, 'whisper+tts', NULL)`, pa se
    lako pročita kao „0 kredita, 2 dnevno". Nije tako: 7. kolona je `krediti_po_minutu`, ne
    `dnevni_limit`. `voice` dakle NEMA dnevni limit, a `krediti_po_minutu` ne čita nijedan
    deo enforcement koda -- jedina pojava u repou je forma u Admin Console-u
    (`routers/admin_dashboard.py:417,511`).

    Praktična posledica, i razlog zašto je ovo ovde napisano: glasovni kanal je danas
    besplatan i BEZ gornje granice upotrebe, štiti ga samo cooldown od 3 s
    (`migrations/065_feature_registry_v2.sql:116`). To pojačava argument da se za betu gasi
    kill-switchem umesto da se oslanja na nepostojeći limit.
    """
    return {
        "feature_key": "voice", "naziv": "Glasovne komande", "kategorija": "ai_osnovno",
        "aktivno": aktivno, "status": "ACTIVE",
        "minimum_plan": "professional", "addon": None,
        "krediti": 0, "krediti_po_minutu": 2,
        "dnevni_limit": None, "mesecni_limit": None,
        "cooldown_seconds": 3, "ai_model": "whisper+tts",
    }


@pytest.fixture
def registry(monkeypatch):
    """Puni keš registry-ja umesto da se ide u bazu.

    `_CACHE_LOADED_AT` mora da se postavi, inače `get_policy` smatra keš
    hladnim i pokušava mrežni poziv (`shared/feature_registry.py:48-68`).
    """
    def _set(aktivno: bool):
        _fr._CACHE["voice"] = _policy(aktivno)
        _fr._CACHE_LOADED_AT = _time.monotonic()
    stari = dict(_fr._CACHE)
    yield _set
    _fr._CACHE.clear()
    _fr._CACHE.update(stari)


# ─── 1. KILL-SWITCH ZATVARA GLASOVNI KANAL ──────────────────────────────────

@pytest.mark.asyncio
async def test_a_neaktivan_voice_daje_503(registry):
    """`aktivno=false` mora da zatvori sve tri HTTP glasovne rute odjednom.

    Testira se sama dependency funkcija, ne HTTP sloj -- sve tri rute dele
    isti `PermissionService.require("voice")`, pa je to jedina tačka odluke.
    """
    registry(False)
    dep = PermissionService.require("voice")
    with patch("shared.permissions._ensure_profile", return_value=_FAKE_PROFILE):
        with pytest.raises(HTTPException) as e:
            await dep(user=dict(_FAKE_USER))
    assert e.value.status_code == 503
    assert "onemogućena" in e.value.detail


@pytest.mark.asyncio
async def test_b_founder_NIJE_izuzet_od_kill_switcha(registry):
    """Founder prolazi DEPRECATED i INTERNAL, ali NE i kill-switch.

    `shared/permissions.py:32` to tvrdi u docstringu. Docstring nije garancija
    -- ovaj test je pretvara u garanciju. Da founder prolazio, gašenje voice-a
    za betu ne bi važilo za nalog koji najverovatnije vodi demo.
    """
    registry(False)
    dep = PermissionService.require("voice")
    with patch("shared.permissions._ensure_profile", return_value=_FAKE_PROFILE), \
         patch("shared.permissions._is_founder", return_value=True):
        with pytest.raises(HTTPException) as e:
            await dep(user=dict(_FAKE_USER))
    assert e.value.status_code == 503


# ─── 2. NEGATIVNA KONTROLA ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ng_aktivan_voice_prolazi_gate(registry):
    """Bez ovoga bi testovi iznad prolazili i da `require` uvek diže 503.

    Dokazuje da provera razlikuje dva stanja, a ne da bezuslovno blokira.
    """
    registry(True)
    dep = PermissionService.require("voice")
    with patch("shared.permissions._ensure_profile", return_value=_FAKE_PROFILE), \
         patch("shared.permissions._check_dependencies", new=AsyncMock(return_value=None)):
        user = await dep(user=dict(_FAKE_USER))
    assert user["user_id"] == "test-user-id"


@pytest.mark.asyncio
async def test_ng_basic_korisnik_ne_dobija_503_nego_403(registry):
    """Razlikovanje razloga odbijanja.

    `voice` traži `professional`. Basic korisnik mora da dobije odbijenicu
    zbog TARIFE (403), ne zbog kill-switcha (503). Da su oba 503, ne bismo
    mogli da razlikujemo "ugašeno za betu" od "nemaš plan" ni u logovima ni
    u podršci.
    """
    registry(True)
    dep = PermissionService.require("voice")
    basic = dict(_FAKE_PROFILE, subscription_type="basic", is_pro=False)
    with patch("shared.permissions._ensure_profile", return_value=basic), \
         patch("shared.permissions._check_dependencies", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as e:
            await dep(user=dict(_FAKE_USER))
    assert e.value.status_code != 503, "tarifna odbijenica ne sme da liči na kill-switch"
    assert e.value.status_code in (402, 403)


# ─── 3. UGOVOR: obe putanje dele isti prekidač ──────────────────────────────

def test_c_sve_glasovne_rute_idu_kroz_isti_feature_key():
    """Ako neko sutra doda glasovnu rutu bez `require("voice")`, gašenje za
    betu je ne bi pokrilo, a mi bismo mislili da jeste."""
    izvor = open(
        os.path.join(os.path.dirname(__file__), "..", "routers", "voice.py"),
        encoding="utf-8",
    ).read()
    assert izvor.count('PermissionService.require("voice")') >= 3, (
        "očekivane su najmanje 3 glasovne rute iza require(\"voice\"); ako je "
        "ruta dodata ili uklonjena, proveri da li je i dalje pokrivena "
        "kill-switchem pre nego što promeniš ovaj broj"
    )


def test_d_ws_putanja_takodje_proverava_aktivno():
    """WebSocket ne prolazi kroz FastAPI `Depends`, pa mora sam da proveri.

    Puna funkcionalna provera je u
    `tests/test_voice_realtime.py::test_ws_rejects_when_feature_inactive`.
    Ovde se samo zaključava da provera nije uklonjena iz izvora -- jer bi
    gašenje voice-a tada zatvorilo HTTP a ostavilo otvoren baš onaj kanal
    koji nema telemetriju sadržaja.
    """
    izvor = open(
        os.path.join(os.path.dirname(__file__), "..", "routers", "voice_realtime.py"),
        encoding="utf-8",
    ).read()
    assert 'get_policy("voice")' in izvor
    assert 'policy.get("aktivno"' in izvor
